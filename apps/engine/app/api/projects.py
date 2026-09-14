import sqlite3
import logging
import uuid
import asyncio
import json
from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from app.config import settings

log = logging.getLogger(__name__)
from app.db import (
    init_db, insert_project, get_project, update_project,
    insert_transcript_segments, insert_hook_candidate, insert_clip,
    insert_crop_keyframes, list_clips_for_project, list_hooks_for_project,
    insert_face_detection, flush_face_detections, insert_face_track,
    insert_caption, update_clip, get_crop_keyframes,
)

router = APIRouter()


class CreateProjectReq(BaseModel):
    name: str = ""
    url: str = ""


class AnalyzeReq(BaseModel):
    num_clips: int = 5
    max_duration: int = 60
    aspect_ratio: str = "9:16"


def _get_conn():
    return sqlite3.connect(str(settings.DATA_ROOT / "smartclipper.db"))


@router.post("/projects")
def create_project(req: CreateProjectReq):
    pid = uuid.uuid4().hex[:12]
    pdir = settings.DATA_ROOT / "projects" / pid
    pdir.mkdir(parents=True, exist_ok=True)
    for sub in ["source", "audio", "transcript", "analysis", "thumbnails", "previews", "exports"]:
        (pdir / sub).mkdir(exist_ok=True)
    conn = _get_conn()
    init_db(conn)
    name = req.name.strip() if req.name and req.name.strip() else ""
    if not name and req.url.startswith("http"):
        try:
            from app.services.import_service import fetch_youtube_title
            yt = fetch_youtube_title(req.url)
            if yt:
                name = yt
        except Exception:
            pass
    if not name:
        name = "Untitled"
    insert_project(conn, id=pid, name=name, source_url=req.url)
    conn.close()
    return {"id": pid, "name": name}


@router.post("/projects/{pid}/upload")
def upload_project_video(pid: str, file: UploadFile = File(...)):
    import shutil
    from pathlib import Path
    conn = _get_conn()
    p = get_project(conn, pid)
    if not p:
        conn.close()
        raise HTTPException(404)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in settings.VIDEO_EXTENSIONS:
        conn.close()
        raise HTTPException(400, f"Unsupported video type: {ext}")
    pdir = settings.DATA_ROOT / "projects" / pid / "source"
    pdir.mkdir(parents=True, exist_ok=True)
    for f in pdir.iterdir():
        if f.suffix.lower() in settings.VIDEO_EXTENSIONS or f.suffix == ".part":
            try:
                f.unlink()
            except Exception:
                pass
    dest = pdir / f"source{ext}"
    with dest.open("wb") as out:
        shutil.copyfileobj(file.file, out)
    # ponytail: nama = stem file bila masih Untitled
    try:
        if getattr(p, "name", "") in ("", "Untitled"):
            update_project(conn, pid, name=Path(file.filename or pid).stem[:120] or "Untitled",
                           source_url=f"file:{file.filename}")
        else:
            update_project(conn, pid, source_url=f"file:{file.filename}")
    finally:
        conn.close()
    return {"status": "uploaded", "project_id": pid}


@router.get("/projects")
def list_projects():
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT id,name,status,progress,stage,created_at FROM projects ORDER BY created_at DESC").fetchall()
    except sqlite3.OperationalError:
        conn.execute("ALTER TABLE projects ADD COLUMN progress REAL DEFAULT 0")
        conn.execute("ALTER TABLE projects ADD COLUMN stage TEXT DEFAULT ''")
        conn.commit()
        rows = conn.execute("SELECT id,name,status,progress,stage,created_at FROM projects ORDER BY created_at DESC").fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "status": r[2], "progress": r[3] or 0, "stage": r[4] or "", "created_at": r[5]} for r in rows]


@router.get("/projects/{pid}")
def get_project_detail(pid: str):
    conn = _get_conn()
    p = get_project(conn, pid)
    if not p:
        conn.close()
        raise HTTPException(404)
    clips = list_clips_for_project(conn, pid)
    hooks = list_hooks_for_project(conn, pid)
    conn.close()
    download_mb = 0.0
    try:
        pdir2 = settings.DATA_ROOT / "projects" / pid / "source"
        for f in pdir2.iterdir():
            if f.suffix == ".part":
                download_mb = round(f.stat().st_size / 1024 / 1024, 1)
                break
    except Exception:
        pass
    return {
        "id": p.id, "name": p.name, "status": p.status,
        "progress": getattr(p, "progress", 0) or 0,
        "stage": getattr(p, "stage", "") or "",
        "error": getattr(p, "error", "") or "",
        "download_mb": download_mb,
        "clips": [{"id": c.id, "start": c.source_start, "end": c.source_end, "hook_candidate_id": c.hook_candidate_id or ""} for c in clips],
        "hooks": [{"id": h.id, "score": h.score, "start": h.start, "end": h.end,
                   "source": h.source,
                   "reasons": json.loads(h.reasons_json or "[]"),
                   "weakness": (json.loads(h.weaknesses_json or "[]") or [""])[0]} for h in hooks],
    }


@router.delete("/projects/{pid}")
def delete_project(pid: str):
    import shutil
    conn = _get_conn()
    p = get_project(conn, pid)
    if not p:
        conn.close()
        raise HTTPException(404)
    cids = [r[0] for r in conn.execute("SELECT id FROM clips WHERE project_id=?", (pid,)).fetchall()]
    if cids:
        q = ",".join("?" for _ in cids)
        conn.execute(f"DELETE FROM crop_keyframes WHERE clip_id IN ({q})", cids)
        conn.execute("DELETE FROM captions WHERE clip_id IN (SELECT id FROM clips WHERE project_id=?)", (pid,))
        conn.execute("DELETE FROM render_jobs WHERE clip_id IN (SELECT id FROM clips WHERE project_id=?)", (pid,))
        conn.execute("DELETE FROM clips WHERE project_id=?", (pid,))
    conn.execute("DELETE FROM hook_candidates WHERE project_id=?", (pid,))
    conn.execute("DELETE FROM transcript_segments WHERE transcript_id=?", ("t_" + pid,))
    conn.execute("DELETE FROM transcripts WHERE id=?", ("t_" + pid,))
    conn.execute("DELETE FROM face_detections WHERE project_id=?", (pid,))
    conn.execute("DELETE FROM face_tracks WHERE project_id=?", (pid,))
    conn.execute("DELETE FROM projects WHERE id=?", (pid,))
    conn.commit()
    conn.close()
    try:
        shutil.rmtree(settings.DATA_ROOT / "projects" / pid, ignore_errors=True)
    except Exception:
        pass
    return {"status": "deleted"}


@router.post("/projects/{pid}/analyze")
async def analyze_project(pid: str, req: AnalyzeReq):
    conn = _get_conn()
    p = get_project(conn, pid)
    if not p:
        conn.close()
        raise HTTPException(404)
    conn.close()

    def _run_analysis():
        _do_analysis(pid, req)

    asyncio.get_event_loop().run_in_executor(None, _run_analysis)
    return {"status": "analysis_started", "project_id": pid}


def _set_progress(pid: str, progress: float, stage: str, status: str | None = None):
    c = _get_conn()
    try:
        kw: dict = {"progress": round(progress, 3), "stage": stage}
        if status:
            kw["status"] = status
        update_project(c, pid, **kw)
    except Exception:
        pass
    finally:
        c.close()


def _do_analysis(pid: str, req: AnalyzeReq):
    import time
    from app.services.import_service import extract_metadata, download_video, extract_audio
    from app.providers.whisper_provider import transcribe
    from app.providers.llm_provider import find_hooks
    from app.db import list_hooks_for_project
    import json

    t_all = time.time()
    conn = _get_conn()
    p = get_project(conn, pid)
    pdir = settings.DATA_ROOT / "projects" / pid
    log.info("[pipeline] pid=%s start url=%s", pid, p.source_url)
    conn.close()
    _set_progress(pid, 0.02, "Menyiapkan", "downloading")

    # download/import
    source_url = p.source_url
    video_files = [f for ext in settings.VIDEO_EXTENSIONS for f in (pdir / "source").glob(f"*{ext}")]
    if not video_files:
        if source_url.startswith("http"):
            log.info("[pipeline] pid=%s stage=download", pid)
            _set_progress(pid, 0.05, "Download video")
            def _dl_prog(frac: float):
                _set_progress(pid, 0.05 + frac * 0.15, f"Download {int(frac * 100)}%")
            video_path = download_video(pid, source_url, pdir, on_progress=_dl_prog)
            # rename project to YouTube title if still Untitled and video title available
            try:
                cc = _get_conn()
                pp = get_project(cc, pid)
                if pp and pp.name == "Untitled":
                    from app.services.import_service import fetch_youtube_title
                    yt = fetch_youtube_title(source_url)
                    if yt and yt != pp.name:
                        update_project(cc, pid, name=yt)
                        log.info("[pipeline] pid=%s renamed to %s", pid, yt)
                cc.close()
            except Exception:
                pass
        else:
            c2 = _get_conn()
            update_project(c2, pid, status="failed", error="invalid source url")
            c2.close()
            return
    else:
        video_path = video_files[0]
        log.info("[pipeline] pid=%s using existing %s", pid, video_path)

    _set_progress(pid, 0.22, "Membaca metadata")
    meta = extract_metadata(str(video_path))
    log.info("[pipeline] pid=%s meta %.1fs %dx%d fps=%.1f", pid, meta["duration"], meta["width"], meta["height"], meta["fps"])

    _set_progress(pid, 0.25, "Ekstrak audio")
    audio_path = extract_audio(str(video_path), pdir)

    _set_progress(pid, 0.30, "Transcribe audio", "transcribing")
    transcript = transcribe(str(audio_path))
    c2 = _get_conn()
    c2.execute("DELETE FROM hook_candidates WHERE project_id=?", (pid,))
    c2.execute("DELETE FROM transcript_segments WHERE transcript_id=?", ("t_" + pid,))
    c2.commit()
    insert_transcript_segments(c2, "t_" + pid, transcript["segments"])
    c2.commit()
    log.info("[pipeline] pid=%s transcript segs=%d", pid, len(transcript["segments"]))

    # hooks via Groq (or heuristic fallback)
    _set_progress(pid, 0.65, "Analisis hook", "hooking")
    hooks = find_hooks(transcript["segments"], n=req.num_clips, max_duration=req.max_duration)
    log.info("[pipeline] pid=%s hooks found=%d", pid, len(hooks))
    for h in hooks:
        log.info("[pipeline] pid=%s hook %.1f-%.1f dur=%.0fs score=%.0f %s", pid, h["start"], h["end"], h["end"] - h["start"], h["score"], h.get("hook_text", "")[:80])
        insert_hook_candidate(
            c2, id=str(uuid.uuid4())[:10], project_id=pid,
            start=h["start"], end=h["end"], score=h["score"],
            scores_json=json.dumps({"final": h["score"]}),
            reasons_json=json.dumps(h.get("reasons", [])),
            weaknesses_json=json.dumps([h.get("weakness", "")] if h.get("weakness") else []),
            source=h.get("source", "groq"),
            llm_model=h.get("llm_model", ""),
        )

    # hook siap -> flush DB, lanjut ke cropping
    _set_progress(pid, 0.80, "Menyiapkan smart crop")
    hook_ids_for_cut = [r[0] for r in c2.execute("SELECT id FROM hook_candidates WHERE project_id=? ORDER BY score DESC", (pid,)).fetchall()]
    nclips_before = c2.execute("SELECT count(*) FROM clips WHERE project_id=?", (pid,)).fetchone()[0]
    log.info("[pipeline] pid=%s hook-ready clips_before=%d total=%.1fs — auto-cut di background", pid, nclips_before, time.time() - t_all)
    c2.close()

    if hook_ids_for_cut:
        def _bg_cut():
            c2 = _get_conn()
            try:
                c2.execute("DELETE FROM clips WHERE project_id=?", (pid,))
                c2.execute("DELETE FROM crop_keyframes WHERE clip_id IN (SELECT id FROM clips WHERE project_id=?)", (pid,))
                c2.commit()
            except Exception:
                pass
            from app.api.from_hooks import create_clips_for_hooks
            try:
                _set_progress(pid, 0.82, "Smart crop", "cropping")
                create_clips_for_hooks(c2, pid, hook_ids_for_cut, req.aspect_ratio or "9:16",
                                       on_progress=lambda i, n: _set_progress(pid, 0.82 + (i / max(n, 1)) * 0.16, f"Smart crop {min(i + 1, n)}/{n}"))
            except Exception as e:
                log.warning("[pipeline] pid=%s bg auto-cut failed: %s", pid, e, exc_info=True)
                _set_progress(pid, 0.82, str(e)[:80], "failed")
            finally:
                try:
                    c2b = _get_conn()
                    nclips = c2b.execute("SELECT count(*) FROM clips WHERE project_id=?", (pid,)).fetchone()[0]
                    c2b.close()
                    _set_progress(pid, 1.0, "Selesai", "ready")
                    log.info("[pipeline] pid=%s bg cropping done clips=%d", pid, nclips)
                except Exception:
                    pass
                c2.close()
        import threading
        threading.Thread(target=_bg_cut, daemon=True).start()
    else:
        _set_progress(pid, 1.0, "Selesai", "ready")
