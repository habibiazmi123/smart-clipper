import sqlite3
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.config import settings
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
    return {
        "id": p.id, "name": p.name, "status": p.status,
        "clips": [{"id": c.id, "start": c.source_start, "end": c.source_end} for c in clips],
        "hooks": [{"id": h.id, "score": h.score, "start": h.start, "end": h.end} for h in hooks],
    }


@router.post("/projects/{pid}/analyze")
async def analyze_project(pid: str, req: AnalyzeReq):
    conn = _get_conn()
    p = get_project(conn, pid)
    if not p:
        conn.close()
        raise HTTPException(404)

    from app.services.import_service import extract_metadata, download_video, extract_audio
    from app.providers.whisper_provider import transcribe
    from app.domain.hooks import generate_candidates, score_candidate
    from app.db import list_hooks_for_project
    import json

    pdir = settings.DATA_ROOT / "projects" / pid
    update_project(conn, pid, status="downloading")

    # download/import
    source_url = p.source_url
    video_files = list((pdir / "source").glob("*.mp4"))
    if not video_files:
        if source_url.startswith("http"):
            video_path = download_video(pid, source_url, pdir)
        else:
            raise HTTPException(400, "No video found")
    else:
        video_path = video_files[0]

    meta = extract_metadata(str(video_path))
    update_project(conn, pid, status="transcribing")

    # extract audio
    audio_path = extract_audio(str(video_path), pdir)

    # transcribe
    transcript = transcribe(str(audio_path))
    insert_transcript_segments(conn, "t_" + pid, transcript["segments"])

    # hooks
    update_project(conn, pid, status="hooking")
    candidates = generate_candidates(transcript["segments"], meta["duration"])
    for c in candidates[:20]:  # score top 20
        score, reasons, weaknesses = score_candidate(c, transcript["segments"])
        insert_hook_candidate(
            conn, id=str(uuid.uuid4())[:10], project_id=pid,
            start=c["start"], end=c["end"], score=score,
            scores_json=json.dumps({"final": score}),
            reasons_json=json.dumps(reasons),
            weaknesses_json=json.dumps(weaknesses),
        )

    hooks = list_hooks_for_project(conn, pid)
    top_hooks = hooks[:req.num_clips]

    update_project(conn, pid, status="cropping")

    # face detect + crop for each clip
    from app.providers.face_provider import create_detector, detect_faces_frame
    import cv2
    detector = create_detector()
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    for h in top_hooks:
        clip_id = uuid.uuid4().hex[:10]
        insert_clip(conn, id=clip_id, project_id=pid, hook_candidate_id=h.id,
                    source_start=h.start, source_end=h.end, aspect_ratio=req.aspect_ratio)

        # sample frames for face detection
        centers = []
        t = h.start
        while t < h.end:
            frame_idx = int(t * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if ret:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                faces = detect_faces_frame(detector, rgb, t)
                if faces:
                    best = max(faces, key=lambda f: f["confidence"])
                    centers.append({"time": round(t, 3), "cx": best["x"], "cy": best["y"]})
            t += settings.FACE_SAMPLE_INTERVAL

        cap.release()

        from app.services.vision_service import smooth_centers, interpolate_centers
        if centers:
            smoothed = smooth_centers(centers)
            keyframes = interpolate_centers(smoothed)
        else:
            keyframes = [{"time": h.start, "cx": 0.5, "cy": 0.5}]

        from app.domain.crop import centers_to_keyframes
        crop_kfs = centers_to_keyframes(
            [{"time": kf["time"], "cx": kf["cx"], "cy": kf.get("cy", 0.5)} for kf in keyframes],
            meta["width"], meta["height"], req.aspect_ratio
        )
        insert_crop_keyframes(conn, clip_id, crop_kfs, source="ai")

        # captions
        clip_segs = [s for s in transcript["segments"]
                     if s["end"] > h.start and s["start"] < h.end]
        from app.domain.captions import split_words_to_lines, generate_ass
        all_words = []
        for s in clip_segs:
            words = json.loads(s.get("words_json", "[]"))
            for w in words:
                all_words.append(w)
        lines = split_words_to_lines(all_words, max_chars=30, max_lines=2)
        ass_content = generate_ass(lines, meta["width"], meta["height"])
        ass_path = pdir / "exports" / f"{clip_id}.ass"
        ass_path.write_text(ass_content)
        insert_caption(conn, clip_id, 0, h.start, h.end,
                       " ".join(l["text"] for l in lines))

    detector.close()
    update_project(conn, pid, status="ready")
    conn.close()
    return {"status": "analyzed", "clips": len(top_hooks)}
