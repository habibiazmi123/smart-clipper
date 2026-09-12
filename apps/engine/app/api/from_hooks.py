import json
import logging
import sqlite3
import time
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.config import settings
from app.db import get_project, insert_clip, insert_crop_keyframes, insert_caption

log = logging.getLogger(__name__)

router = APIRouter()


class FromHooksReq(BaseModel):
    hook_ids: list[str]
    aspect_ratio: str = "9:16"


def _get_conn():
    return sqlite3.connect(str(settings.DATA_ROOT / "smartclipper.db"))


def create_clips_for_hooks(conn, pid: str, hook_ids: list[str], aspect_ratio: str = "9:16") -> list[dict]:
    placeholders = ",".join("?" for _ in hook_ids)
    rows = conn.execute(
        f"SELECT id,start,end FROM hook_candidates WHERE project_id=? AND id IN ({placeholders})",
        (pid, *hook_ids)).fetchall()
    if not rows:
        return []
    hook_map = {r[0]: (r[1], r[2]) for r in rows}
    ordered = sorted(((hid, hook_map[hid][0], hook_map[hid][1])
                      for hid in hook_ids if hid in hook_map), key=lambda x: x[1])
    pdir = settings.DATA_ROOT / "projects" / pid
    vids = sorted((pdir / "source").glob("*.mp4"))
    if not vids:
        return []
    video_path = str(vids[0])
    from app.services.import_service import extract_metadata
    meta = extract_metadata(video_path)
    audio_path = str(pdir / "audio" / "audio.wav")
    if not (pdir / "audio" / "audio.wav").exists():
        from app.services.import_service import extract_audio
        audio_path = extract_audio(video_path, pdir)
    transcript_segs = []
    try:
        tid = "t_" + pid
        rows2 = conn.execute(
            "SELECT idx,start,end,text,confidence,words_json FROM transcript_segments WHERE transcript_id=? ORDER BY start",
            (tid,)).fetchall()
        for idx, s, e, text, conf, wj in rows2:
            transcript_segs.append({"idx": idx, "start": s, "end": e, "text": text,
                                    "confidence": conf or 0.5, "words_json": wj or "[]"})
    except Exception:
        pass

    from app.providers.face_provider import create_detector
    from app.services.speaker_service import analyze_clip_speakers, load_wav_mono, SpeakerTracker
    detector = create_detector()
    tracker = SpeakerTracker(sample_interval=settings.FACE_SAMPLE_INTERVAL)
    try:
        wav = load_wav_mono(audio_path)
    except Exception:
        wav = None

    log.info("[from_hooks] pid=%s hooks=%d aspect=%s start cropping", pid, len(ordered), aspect_ratio)
    t0 = time.time()
    created = []
    for idx, (hid, hs, he) in enumerate(ordered):
        log.info("[from_hooks] pid=%s clip %d/%d hook=%s [%.1f-%.1f]", pid, idx + 1, len(ordered), hid, hs, he)
        clip_id = uuid.uuid4().hex[:10]
        insert_clip(conn, id=clip_id, project_id=pid, hook_candidate_id=hid,
                    source_start=hs, source_end=he, aspect_ratio=aspect_ratio)
        centers = analyze_clip_speakers(
            video_path, detector, hs, he, wav=wav,
            transcript_segs=transcript_segs, tracker=tracker)
        from app.services.vision_service import smooth_centers, interpolate_centers
        if centers:
            smoothed = smooth_centers([{"time": c["time"], "cx": c["cx"]} for c in centers])
            keyframes = []
            for kf in interpolate_centers(smoothed):
                near = min(centers, key=lambda c: abs(c["time"] - kf["time"]))
                keyframes.append({**kf, "speaker": near.get("speaker"), "sconf": near.get("sconf")})
            if keyframes and keyframes[0]["time"] > hs:
                first = keyframes[0]
                keyframes.insert(0, {"time": round(hs, 3), "cx": first["cx"],
                                     "cy": first.get("cy", 0.5),
                                     "speaker": first.get("speaker"), "sconf": first.get("sconf")})
            if keyframes and keyframes[-1]["time"] < he:
                last = keyframes[-1]
                keyframes.append({"time": round(he, 3), "cx": last["cx"],
                                  "cy": last.get("cy", 0.5),
                                  "speaker": last.get("speaker"), "sconf": last.get("sconf")})
        else:
            keyframes = [{"time": hs, "cx": 0.5, "cy": 0.5}]
        from app.domain.crop import centers_to_keyframes
        crop_kfs = centers_to_keyframes(
            [{"time": kf["time"], "cx": kf["cx"], "cy": kf.get("cy", 0.5),
              "speaker": kf.get("speaker")} for kf in keyframes],
            meta["width"], meta["height"], aspect_ratio)
        insert_crop_keyframes(conn, clip_id, crop_kfs, source="ai")
        clip_segs = [s for s in transcript_segs if s["end"] > hs and s["start"] < he]
        from app.domain.captions import split_words_to_lines, generate_ass
        all_words = []
        for s in clip_segs:
            try:
                ws = json.loads(s.get("words_json", "[]"))
            except Exception:
                ws = []
            all_words.extend(ws)
        lines = split_words_to_lines(all_words, max_chars=30, max_lines=2)
        ass_content = generate_ass(lines, meta["width"], meta["height"])
        ass_path = pdir / "exports" / f"{clip_id}.ass"
        ass_path.parent.mkdir(parents=True, exist_ok=True)
        ass_path.write_text(ass_content)
        insert_caption(conn, clip_id, 0, hs, he, " ".join(l["text"] for l in lines))
        created.append({"id": clip_id, "start": hs, "end": he, "hook_id": hid})

    log.info("[from_hooks] pid=%s done clips=%d took=%.1fs", pid, len(created), time.time() - t0)
    try:
        detector.close()
    except Exception:
        pass
    return created


@router.post("/projects/{pid}/clips/from-hooks")
def create_clips_from_hooks(pid: str, req: FromHooksReq):
    if not req.hook_ids:
        raise HTTPException(400, "hook_ids required")
    conn = _get_conn()
    p = get_project(conn, pid)
    if not p:
        conn.close()
        raise HTTPException(404)
    created = create_clips_for_hooks(conn, pid, req.hook_ids, req.aspect_ratio or "9:16")
    if not created:
        conn.close()
        raise HTTPException(404, "No matching hooks")
    conn.close()
    return {"clips": created}
