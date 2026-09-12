import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mpy
from mediapipe.tasks.python import vision
from app.config import settings


def create_detector():
    opts = vision.FaceDetectorOptions(
        base_options=mpy.BaseOptions(
            model_asset_path=str(settings.FACE_MODEL),
            delegate=mpy.BaseOptions.Delegate.CPU,
        ),
        running_mode=vision.RunningMode.VIDEO,
        min_detection_confidence=0.5,
    )
    return vision.FaceDetector.create_from_options(opts)


def detect_faces_frame(detector, rgb_frame: np.ndarray, timestamp: float,
                       min_conf: float = 0.5) -> list[dict]:
    """Detect faces in a single RGB frame. Returns normalized 0..1 coords."""
    img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
    result = detector.detect_for_video(img, int(timestamp * 1000))
    faces = []
    for d in result.detections:
        bb = d.bounding_box
        conf = float(d.categories[0].score)
        if conf < min_conf:
            continue
        faces.append({
            "x": round((bb.origin_x + bb.width / 2) / img.width, 4),
            "y": round((bb.origin_y + bb.height / 2) / img.height, 4),
            "w": round(bb.width / img.width, 4),
            "h": round(bb.height / img.height, 4),
            "confidence": round(conf, 4),
        })
    return faces
