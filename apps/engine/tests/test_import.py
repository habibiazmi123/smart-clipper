import subprocess
from app.services.import_service import extract_metadata


def test_extract_metadata(tmp_data):
    v = tmp_data / "test.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=640x480:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-shortest", str(v)],
        capture_output=True,
    )
    meta = extract_metadata(str(v))
    assert meta["width"] == 640
    assert meta["height"] == 480
    assert meta["duration"] > 2.5
    assert meta["duration"] < 3.5
