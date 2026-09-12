import cv2
import numpy as np
from app.providers.face_provider import create_detector, detect_faces_frame


def test_detect_face_in_portrait():
    import subprocess
    subprocess.run(
        ["rtk", "curl", "-sL", "-o", "/tmp/face_test.jpg",
         "https://storage.googleapis.com/mediapipe-assets/portrait.jpg"],
        capture_output=True,
    )
    det = create_detector()
    bgr = cv2.imread("/tmp/face_test.jpg")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    faces = detect_faces_frame(det, rgb, timestamp=0.0)
    assert len(faces) >= 1
    assert 0 < faces[0]["x"] < 1
    assert 0 < faces[0]["y"] < 1
    assert faces[0]["confidence"] > 0.5
    det.close()
