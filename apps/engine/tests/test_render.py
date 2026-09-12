from app.services.render_service import build_render_plan, render_plan_to_ffmpeg_args
from app.domain.crop import build_crop_expr, clamp_center, crop_window
import re


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
    # audio wajib ter-map (jangan pernah export bisu diam-diam)
    assert "0:a:0?" in args
    assert "-an" not in args


def _eval_x_expr(expr: str, t: float) -> float:
    """Evaluator mini untuk x='...' (lt/gte/aritmetika/t)."""
    m = re.search(r"x='(.*)':y=", expr)
    body = m.group(1)
    ns = {
        "t": t,
        "lt": lambda a, b: 1.0 if a < b else 0.0,
        "gte": lambda a, b: 1.0 if a >= b else 0.0,
        "between": lambda a, b, c: 1.0 if b <= a <= c else 0.0,
    }
    return eval(body, {"__builtins__": {}}, ns)


def _preview_x(kfs, t, src_w=1920, src_h=1080):
    """Mirror interpolateKeyframes() + clamp frontend (half-open + cut)."""
    sk = sorted(kfs, key=lambda k: k["time"])
    if t < sk[0]["time"]:
        cx = sk[0]["center_x"]
    elif t >= sk[-1]["time"]:
        cx = sk[-1]["center_x"]
    else:
        for i in range(1, len(sk)):
            if t < sk[i]["time"]:
                p, c = sk[i - 1], sk[i]
                if p.get("speaker") and c.get("speaker") and p["speaker"] != c["speaker"]:
                    cx = p["center_x"]
                else:
                    f = (t - p["time"]) / max(c["time"] - p["time"], 0.001)
                    cx = p["center_x"] + f * (c["center_x"] - p["center_x"])
                break
    w = crop_window(src_w, src_h, 9, 16)
    cx, _ = clamp_center(cx, 0.5, w["crop_w"], w["crop_h"], src_w, src_h)
    return round(cx * src_w - w["crop_w"] / 2, 2)


def test_crop_expr_matches_preview():
    # ponytail: guard utama preview == export; regresi bug `+` di luar between()
    kfs = [
        {"time": 3.0, "center_x": 0.42, "center_y": 0.5},
        {"time": 5.5, "center_x": 0.60, "center_y": 0.5},
        {"time": 9.0, "center_x": 0.51, "center_y": 0.5},
    ]
    expr = build_crop_expr(kfs, 1920, 1080, 9, 16)
    rel = [{"time": k["time"] - 3.0, "center_x": k["center_x"], "center_y": k["center_y"]} for k in kfs]
    expr_rel = build_crop_expr(rel, 1920, 1080, 9, 16)
    t = 0.0
    while t <= 6.01:
        got = _eval_x_expr(expr_rel, t)
        want = _preview_x(kfs, t + 3.0)
        assert abs(got - want) <= 1.0, f"t={t}: ffmpeg={got} preview={want}"
        t = round(t + 0.1, 10)


def test_crop_expr_holds_outside_range():
    kfs = [
        {"time": 1.0, "center_x": 0.40, "center_y": 0.5},
        {"time": 2.0, "center_x": 0.60, "center_y": 0.5},
    ]
    expr = build_crop_expr(kfs, 1920, 1080, 9, 16)
    assert _eval_x_expr(expr, -0.5) == _eval_x_expr(expr, 0.0) == _preview_x(kfs, 0.0)
    assert _eval_x_expr(expr, 5.0) == _preview_x(kfs, 5.0)


def test_speaker_switch_cuts_no_glide():
    # ganti orang = cut tajam di batas label; orang sama = tetap glide
    kfs = [
        {"time": 9.0, "center_x": 0.557, "center_y": 0.5, "speaker": "A"},
        {"time": 9.5, "center_x": 0.507, "center_y": 0.5, "speaker": "C"},
        {"time": 10.0, "center_x": 0.470, "center_y": 0.5, "speaker": "C"},
        {"time": 10.5, "center_x": 0.470, "center_y": 0.5},  # manual: wildcard
    ]
    expr = build_crop_expr(kfs, 1920, 1080, 9, 16)
    xa = _preview_x(kfs, 9.0)
    # sebelum batas: tahan A (tidak meluncur)
    assert _eval_x_expr(expr, 9.0) == xa
    assert _eval_x_expr(expr, 9.49) == xa
    # tepat di batas: sudah sisi C
    assert _eval_x_expr(expr, 9.5) == _preview_x(kfs, 9.5) != xa
    # dalam speaker sama: glide normal
    mid = _eval_x_expr(expr, 9.75)
    assert abs(mid - _eval_x_expr(expr, 9.5)) > 1.0
    assert abs(mid - _preview_x(kfs, 9.75)) <= 1.0
    # manual tanpa label: glide (bukan cut)
    assert abs(_eval_x_expr(expr, 10.25) - _preview_x(kfs, 10.25)) <= 1.0
