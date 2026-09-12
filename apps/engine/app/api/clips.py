import sqlite3
import uuid
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.config import settings
from app.db import get_clip, update_clip, get_crop_keyframes, delete_manual_crop_keyframes
from app.services.render_service import OUTPUT_WIDTH, OUTPUT_HEIGHT

router = APIRouter()


class UpdateClipReq(BaseModel):
    title: str | None = None
    caption_short: str | None = None
    caption_long: str | None = None
    source_start: float | None = None
    source_end: float | None = None


class UpdateKeyframesReq(BaseModel):
    keyframes: list[dict]


def _get_conn():
    return sqlite3.connect(str(settings.DATA_ROOT / "smartclipper.db"))


@router.get("/clips/{clip_id}")
def get_clip_detail(clip_id: str):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    kfs = get_crop_keyframes(conn, clip_id)
    conn.close()
    return {
        "id": c.id, "project_id": c.project_id,
        "source_start": c.source_start, "source_end": c.source_end,
        "aspect_ratio": c.aspect_ratio,
        "crop_manually_modified": c.crop_manually_modified,
        "title": c.title,
        "caption_short": c.caption_short, "caption_long": c.caption_long,
        "cta": c.cta, "keyframes": kfs,
    }


@router.patch("/clips/{clip_id}")
def update_clip_info(clip_id: str, req: UpdateClipReq):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if updates:
        update_clip(conn, clip_id, **updates)
    conn.close()
    return {"status": "updated"}


@router.post("/clips/{clip_id}/keyframes")
def update_keyframes(clip_id: str, req: UpdateKeyframesReq):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    delete_manual_crop_keyframes(conn, clip_id)
    from app.db import insert_crop_keyframes
    insert_crop_keyframes(conn, clip_id, req.keyframes, source="manual")
    update_clip(conn, clip_id, crop_manually_modified=True)
    conn.close()
    return {"status": "updated", "keyframes": len(req.keyframes)}


@router.post("/clips/{clip_id}/reset-crop")
def reset_crop_to_ai(clip_id: str):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    delete_manual_crop_keyframes(conn, clip_id)
    update_clip(conn, clip_id, crop_manually_modified=False)
    conn.close()
    return {"status": "reset_to_ai"}


def _clip_words(conn, clip, relative=False):
    tid = "t_" + clip.project_id
    rows = conn.execute(
        "SELECT id,start,end,text,words_json FROM transcript_segments "
        "WHERE transcript_id=? AND end>? AND start<? ORDER BY start",
        (tid, clip.source_start, clip.source_end)).fetchall()
    segs, words = [], []
    for sid, s, e, text, wj in rows:
        segs.append({"id": sid, "start": s, "end": e, "text": text})
        try:
            ws = json.loads(wj or "[]")
        except Exception:
            ws = []
        for w in ws:
            if w.get("end", 0) > clip.source_start and w.get("start", 0) < clip.source_end:
                words.append({"w": str(w.get("word", "")).strip(),
                              "start": float(w.get("start", s)),
                              "end": float(w.get("end", e))})
    words = [w for w in words if w["w"]]
    if relative:
        # video export di-trim (-ss): timeline mulai 0, jadi ASS harus relatif;
        # kata yang menjulur sebelum awal klip dijepit ke 0
        rel = []
        for w in words:
            s = round(w["start"] - clip.source_start, 3)
            e = round(w["end"] - clip.source_start, 3)
            if e <= 0:
                continue
            rel.append({**w, "start": max(s, 0.0), "end": e})
        words = rel
    return segs, words


def _export_style(style: dict) -> dict:
    s = dict(style or {})
    # samakan proporsi preview: fontSize UI = fontSize/606 lebar crop,
    # lebar crop output 1080 -> skala agar teks tidak kekecilan
    if s.get("font_size"):
        s["font_size"] = round(s["font_size"] * OUTPUT_WIDTH / 606)
    return s


@router.get("/clips/{clip_id}/captions")
def get_clip_captions(clip_id: str):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    segs, words = _clip_words(conn, c)
    conn.close()
    return {"segments": segs, "words": words}


class EditSegReq(BaseModel):
    text: str


@router.patch("/transcript-segments/{seg_id}")
def edit_segment(seg_id: int, req: EditSegReq):
    conn = _get_conn()
    row = conn.execute(
        "SELECT start,end,words_json FROM transcript_segments WHERE id=?",
        (seg_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404)
    start, end = float(row[0]), float(row[1])
    # ponytail: teks baru dibagi rata ke durasi segmen agar timing tidak basi
    parts = req.text.split()
    if parts:
        dur = max(end - start, 0.01)
        per = dur / len(parts)
        words = [{"word": p, "start": round(start + i * per, 3),
                  "end": round(start + (i + 1) * per, 3), "probability": 1.0}
                 for i, p in enumerate(parts)]
        wj = json.dumps(words)
    else:
        wj = "[]"
    conn.execute("UPDATE transcript_segments SET text=?,words_json=? WHERE id=?",
                 (req.text, wj, seg_id))
    conn.commit()
    conn.close()
    return {"status": "updated"}


class ExportReq(BaseModel):
    style: dict = {}
    quality: str = "balanced"


def _export_paths(project_id: str, clip_id: str, quality: str):
    from pathlib import Path
    pdir = settings.DATA_ROOT / "projects" / project_id
    q = quality if quality in ("fast", "balanced", "high") else "balanced"
    return pdir, pdir / "exports" / f"{clip_id}_{q}.mp4", q


async def _do_export_job(job, clip_id: str, quality: str, style: dict):
    """Worker export: jalan di thread, progress ditulis langsung ke job
    (aman dibaca polling GET /jobs). Batal via job.cancelled."""
    import asyncio as _aio
    from app.services.import_service import extract_metadata
    from app.domain.captions import generate_karaoke_ass
    from app.services.render_service import build_render_plan, render_clip_with_progress

    def _gather():
        conn = _get_conn()
        try:
            c = get_clip(conn, clip_id)
            if not c:
                return None
            _, words = _clip_words(conn, c, relative=True)
            kfs = get_crop_keyframes(conn, clip_id)
            return c, words, kfs
        finally:
            conn.close()

    c, words, kfs = await _aio.to_thread(_gather)
    if not c:
        raise RuntimeError("clip not found")
    pdir, out, q = _export_paths(c.project_id, clip_id, quality)
    vids = sorted((pdir / "source").glob("*.mp4"))
    if not vids:
        raise RuntimeError("no video found")
    job.stage = "preparing"
    meta = await _aio.to_thread(extract_metadata, str(vids[0]))
    style = _export_style(style)
    ass = generate_karaoke_ass(words, OUTPUT_WIDTH, OUTPUT_HEIGHT, style or {})
    (pdir / "exports").mkdir(parents=True, exist_ok=True)
    ass_path = pdir / "exports" / f"{clip_id}_{q}_styled.ass"
    ass_path.write_text(ass)
    plan = build_render_plan(str(vids[0]), c.source_start, c.source_end,
                             kfs, meta["width"], meta["height"],
                             c.aspect_ratio or "9:16", str(ass_path), q)

    def _on_progress(frac: float):
        job.stage = "encoding"
        job.progress = round(frac, 4)

    await _aio.to_thread(render_clip_with_progress, plan, str(out),
                         _on_progress, lambda: job.cancelled)
    job.stage = "done"
    job.progress = 1.0


@router.post("/clips/{clip_id}/export-jobs")
async def start_export_job(clip_id: str, req: ExportReq):
    from fastapi import HTTPException as _HTTP
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise _HTTP(404)
    pid = c.project_id
    conn.close()
    from app import jobs as _jobs
    _, _, q = _export_paths(pid, clip_id, req.quality or "balanced")
    job_id = _jobs.enqueue_job("export", pid, _do_export_job,
                               clip_id, q, req.style or {})
    return {"job_id": job_id, "quality": q}


@router.get("/clips/{clip_id}/export-file")
def download_export_file(clip_id: str, quality: str = "balanced"):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    _, out, q = _export_paths(c.project_id, clip_id, quality)
    conn.close()
    if not out.exists():
        raise HTTPException(404, "Export not ready yet")
    return FileResponse(str(out), media_type="video/mp4",
                        filename=f"{clip_id}_{q}.mp4")


@router.post("/clips/{clip_id}/export")
def export_clip(clip_id: str, req: ExportReq):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    _, words = _clip_words(conn, c, relative=True)
    kfs = get_crop_keyframes(conn, clip_id)
    conn.close()
    from pathlib import Path
    pdir = settings.DATA_ROOT / "projects" / c.project_id
    vids = sorted((pdir / "source").glob("*.mp4"))
    if not vids:
        raise HTTPException(404, "No video found")
    from app.services.import_service import extract_metadata
    from app.domain.captions import generate_karaoke_ass
    from app.services.render_service import build_render_plan, render_clip
    meta = extract_metadata(str(vids[0]))
    ass = generate_karaoke_ass(words, OUTPUT_WIDTH, OUTPUT_HEIGHT,
                               _export_style(req.style))
    (pdir / "exports").mkdir(parents=True, exist_ok=True)
    ass_path = pdir / "exports" / f"{clip_id}_styled.ass"
    ass_path.write_text(ass)
    plan = build_render_plan(str(vids[0]), c.source_start, c.source_end,
                             kfs, meta["width"], meta["height"],
                             c.aspect_ratio or "9:16", str(ass_path),
                             req.quality or "balanced")
    out = pdir / "exports" / f"{clip_id}_9x16.mp4"
    render_clip(plan, str(out))
    return FileResponse(str(out), media_type="video/mp4",
                        filename=f"{clip_id}_9x16.mp4")
