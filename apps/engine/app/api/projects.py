import sqlite3
import logging
import uuid
import asyncio
import json
from fastapi import APIRouter, HTTPException
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
    insert_project(conn, id=pid, name=req.name or "Untitled", source_url=req.url)
    conn.close()
    return {"id": pid, "name": req.name or "Untitled"}


@router.get("/projects")
def list_projects():
    conn = _get_conn()
    rows = conn.execute("SELECT id,name,status,created_at FROM projects ORDER BY created_at DESC").fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "status": r[2], "created_at": r[3]} for r in rows]


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
        "id": p.id, "name": p.name, "status": p.status, "download_mb": download_mb,
        "clips": [{"id": c.id, "start": c.source_start, "end": c.source_end, "hook_candidate_id": c.hook_candidate_id or ""} for c in clips],
        "hooks": [{"id": h.id, "score": h.score, "start": h.start, "end": h.end,
                   "source": h.source,
                   "reasons": json.loads(h.reasons_json or "[]"),
                   "weakness": (json.loads(h.weaknesses_json or "[]") or [""])[0]} for h in hooks],
    }


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
    update_project(conn, pid, status="downloading")

    # download/import
    source_url = p.source_url
    video_files = list((pdir / "source").glob("*.mp4"))
    if not video_files:
        if source_url.startswith("http"):
            log.info("[pipeline] pid=%s stage=download", pid)
            video_path = download_video(pid, source_url, pdir)
        else:
            update_project(conn, pid, status="failed")
            conn.close()
            return
    else:
        video_path = video_files[0]
        log.info("[pipeline] pid=%s using existing %s", pid, video_path)

    log.info("[pipeline] pid=%s stage=metadata", pid)
    meta = extract_metadata(str(video_path))
    log.info("[pipeline] pid=%s meta %.1fs %dx%d fps=%.1f", pid, meta["duration"], meta["width"], meta["height"], meta["fps"])
    update_project(conn, pid, status="transcribing")

    # extract audio
    log.info("[pipeline] pid=%s stage=audio_extract", pid)
    audio_path = extract_audio(str(video_path), pdir)

    # transcribe
    log.info("[pipeline] pid=%s stage=transcribing", pid)
    transcript = transcribe(str(audio_path))
    conn.execute("DELETE FROM hook_candidates WHERE project_id=?", (pid,))
    conn.execute("DELETE FROM transcript_segments WHERE transcript_id=?", ("t_" + pid,))
    conn.commit()
    insert_transcript_segments(conn, "t_" + pid, transcript["segments"])
    log.info("[pipeline] pid=%s transcript segs=%d", pid, len(transcript["segments"]))

    # hooks via Groq (or heuristic fallback)
    log.info("[pipeline] pid=%s stage=looking_hooks n=%d max_dur=%d", pid, req.num_clips, req.max_duration)
    update_project(conn, pid, status="hooking")
    hooks = find_hooks(transcript["segments"], n=req.num_clips, max_duration=req.max_duration)
    log.info("[pipeline] pid=%s hooks found=%d", pid, len(hooks))
    for h in hooks:
        log.info("[pipeline] pid=%s hook %.1f-%.1f dur=%.0fs score=%.0f %s", pid, h["start"], h["end"], h["end"] - h["start"], h["score"], h.get("hook_text", "")[:80])
        insert_hook_candidate(
            conn, id=str(uuid.uuid4())[:10], project_id=pid,
            start=h["start"], end=h["end"], score=h["score"],
            scores_json=json.dumps({"final": h["score"]}),
            reasons_json=json.dumps(h.get("reasons", [])),
            weaknesses_json=json.dumps([h.get("weakness", "")] if h.get("weakness") else []),
            source=h.get("source", "groq"),
            llm_model=h.get("llm_model", ""),
        )

    # hook siap -> tandai ready dulu biar UI langsung tampil card
    update_project(conn, pid, status="ready")
    conn.commit()
    hook_ids_for_cut = [r[0] for r in conn.execute("SELECT id FROM hook_candidates WHERE project_id=? ORDER BY score DESC", (pid,)).fetchall()]
    nclips_before = conn.execute("SELECT count(*) FROM clips WHERE project_id=?", (pid,)).fetchone()[0]
    log.info("[pipeline] pid=%s hook-ready clips_before=%d total=%.1fs — auto-cut di background", pid, nclips_before, time.time() - t_all)
    conn.close()

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
                update_project(c2, pid, status="cropping")
                create_clips_for_hooks(c2, pid, hook_ids_for_cut, req.aspect_ratio or "9:16")
            except Exception as e:
                log.warning("[pipeline] pid=%s bg auto-cut failed: %s", pid, e)
            finally:
                try:
                    nclips = c2.execute("SELECT count(*) FROM clips WHERE project_id=?", (pid,)).fetchone()[0]
                    update_project(c2, pid, status="ready")
                    log.info("[pipeline] pid=%s bg cropping done clips=%d", pid, nclips)
                except Exception:
                    pass
                c2.close()
        import threading
        threading.Thread(target=_bg_cut, daemon=True).start()
