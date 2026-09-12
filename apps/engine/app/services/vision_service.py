import cv2
import json
import subprocess
import numpy as np
from app.config import settings


def smooth_centers(raw_centers: list[dict], alpha: float = None, deadzone: float = None) -> list[dict]:
    alpha = alpha or settings.SMOOTHING_ALPHA
    deadzone = deadzone or settings.SMOOTHING_DEADZONE
    if not raw_centers:
        return []
    result = [raw_centers[0].copy()]
    prev = raw_centers[0]["cx"]
    for c in raw_centers[1:]:
        raw = c["cx"]
        smoothed = alpha * raw + (1 - alpha) * prev
        if abs(smoothed - prev) < deadzone:
            smoothed = prev
        result.append({"time": c["time"], "cx": round(smoothed, 4)})
        prev = smoothed
    return result


def interpolate_centers(centers: list[dict], interval: float = None) -> list[dict]:
    interval = interval or settings.KEYFRAME_INTERVAL
    if not centers:
        return []
    duration = centers[-1]["time"] - centers[0]["time"]
    if duration <= 0:
        return [centers[0].copy()]
    result = []
    t = centers[0]["time"]
    while t <= centers[-1]["time"] + 0.001:
        cx = _lerp_keyframes(centers, t, "cx")
        cy = centers[0].get("cy", 0.5)
        result.append({"time": round(t, 2), "cx": round(cx, 4), "cy": round(cy, 4)})
        t += interval
    return result


def _lerp_keyframes(centers, t, key):
    if t <= centers[0]["time"]:
        return centers[0][key]
    for i in range(1, len(centers)):
        if t <= centers[i]["time"]:
            prev = centers[i - 1]
            curr = centers[i]
            frac = (t - prev["time"]) / max(curr["time"] - prev["time"], 0.001)
            return prev[key] + frac * (curr[key] - prev[key])
    return centers[-1][key]


def detect_and_track_video(video_path: str, detector, project_id: str, conn,
                           sample_interval: float = None) -> list[dict]:
    sample_interval = sample_interval or settings.FACE_SAMPLE_INTERVAL
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_interval = max(1, int(fps * sample_interval))
    all_centers = []
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            timestamp = frame_idx / fps
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            from app.providers.face_provider import detect_faces_frame
            faces = detect_faces_frame(detector, rgb, timestamp)
            if faces:
                best = max(faces, key=lambda f: f["confidence"])
                all_centers.append({"time": round(timestamp, 3), "cx": best["x"], "cy": best["y"]})
        frame_idx += 1
    cap.release()
    if not all_centers:
        return []
    smoothed = smooth_centers(all_centers)
    keyframes = interpolate_centers(smoothed)
    import json
    from app.db import insert_face_track
    insert_face_track(conn, project_id, keyframes[0]["time"], keyframes[-1]["time"],
                      json.dumps(keyframes))
    return keyframes
