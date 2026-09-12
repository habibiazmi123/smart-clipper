import sqlite3
import uuid
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.config import settings
from app.db import get_clip, update_clip, get_crop_keyframes, delete_manual_crop_keyframes

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


def _clip_words(conn, clip):
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
    return segs, [w for w in words if w["w"]]


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


@router.post("/clips/{clip_id}/export")
def export_clip(clip_id: str, req: ExportReq):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    _, words = _clip_words(conn, c)
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
    ass = generate_karaoke_ass(words, meta["width"], meta["height"], req.style or {})
    (pdir / "exports").mkdir(parents=True, exist_ok=True)
    ass_path = pdir / "exports" / f"{clip_id}_styled.ass"
    ass_path.write_text(ass)
    plan = build_render_plan(str(vids[0]), c.source_start, c.source_end,
                             kfs, meta["width"], meta["height"],
                             c.aspect_ratio or "9:16", str(ass_path))
    out = pdir / "exports" / f"{clip_id}_9x16.mp4"
    render_clip(plan, str(out))
    return FileResponse(str(out), media_type="video/mp4",
                        filename=f"{clip_id}_9x16.mp4")
