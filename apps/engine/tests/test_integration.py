import subprocess
import sqlite3
import json
import os
from pathlib import Path


def test_full_pipeline(tmp_data):
    """End-to-end: generate fixture → import → transcribe → crop → export."""
    fixture = Path(__file__).parent / "fixtures" / "test_video.mp4"
    if not fixture.exists():
        subprocess.run(["bash", str(Path(__file__).parent / "fixtures" / "generate_fixture.sh")], check=True)

    from app.config import settings
    from app.db import init_db, insert_project, insert_clip, insert_crop_keyframes
    from app.services.import_service import extract_metadata, extract_audio
    from app.domain.crop import centers_to_keyframes
    from app.domain.captions import split_words_to_lines, generate_ass
    from app.services.render_service import build_render_plan, render_plan_to_ffmpeg_args, render_clip

    # init
    conn = sqlite3.connect(str(tmp_data / "test.db"))
    init_db(conn)
    insert_project(conn, id="test", name="Integration Test")

    # metadata
    meta = extract_metadata(str(fixture))
    assert meta["width"] == 640
    assert meta["height"] == 480

    # audio
    audio = extract_audio(str(fixture), tmp_data)
    assert audio.exists()

    # crop
    centers = [
        {"time": 0.0, "cx": 0.5, "cy": 0.5},
        {"time": 4.0, "cx": 0.6, "cy": 0.5},
    ]
    kfs = centers_to_keyframes(centers, meta["width"], meta["height"], "9:16")
    insert_clip(conn, id="c1", project_id="test", source_start=0.0, source_end=8.0, aspect_ratio="9:16")
    insert_crop_keyframes(conn, "c1", kfs, source="ai")

    # render
    plan = build_render_plan(
        input_path=str(fixture),
        start=0.0, end=8.0,
        keyframes=kfs,
        src_w=meta["width"], src_h=meta["height"],
        aspect="9:16",
    )
    output = str(tmp_data / "output.mp4")
    render_clip(plan, output)
    assert Path(output).exists()
    assert Path(output).stat().st_size > 1000

    # verify output dimensions
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", output],
        capture_output=True, text=True,
    )
    info = json.loads(result.stdout)
    w = int(info["streams"][0]["width"])
    h = int(info["streams"][0]["height"])
    assert w == 1080
    assert h == 1920

    conn.close()
    print(f"Integration test passed: {output} ({w}x{h})")
