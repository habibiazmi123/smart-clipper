from app.services.render_service import build_render_plan, render_plan_to_ffmpeg_args


def test_render_plan_has_crop():
    plan = build_render_plan(
        input_path="/tmp/test.mp4",
        start=0.0, end=5.0,
        keyframes=[{"time": 0.0, "center_x": 0.5, "center_y": 0.5}],
        src_w=1920, src_h=1080,
        aspect="9:16",
    )
    assert plan["input"] == "/tmp/test.mp4"
    assert plan["trim"]["start"] == 0.0
    assert plan["crop"]["aspect_ratio"] == "9:16"


def test_render_plan_to_args():
    plan = build_render_plan(
        input_path="/tmp/test.mp4",
        start=0.0, end=5.0,
        keyframes=[{"time": 0.0, "center_x": 0.5, "center_y": 0.5}],
        src_w=1920, src_h=1080,
        aspect="9:16",
    )
    args = render_plan_to_ffmpeg_args(plan)
    assert "-i" in args
    assert "crop=" in " ".join(args)
    assert "libx264" in args
