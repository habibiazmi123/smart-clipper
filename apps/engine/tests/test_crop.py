from app.domain.crop import (
    round_even, crop_window, clamp_center, centers_to_keyframes,
    build_crop_expr, keypoints_for_clip
)


def test_round_even():
    assert round_even(607) == 606
    assert round_even(608) == 608
    assert round_even(1) == 0
    assert round_even(2) == 2


def test_crop_window_9_16():
    w = crop_window(1920, 1080, 9, 16)
    assert w["crop_w"] == 606  # 1080 * 9/16 = 607.5 -> int=607 -> round_even=606
    assert w["crop_h"] == 1080


def test_crop_window_1_1():
    w = crop_window(1920, 1080, 1, 1)
    assert w["crop_w"] == 1080
    assert w["crop_h"] == 1080


def test_clamp_center():
    cx, cy = clamp_center(0.0, 0.5, 608, 1080, 1920, 1080)
    assert cx > 0
    cx2, _ = clamp_center(1.0, 0.5, 608, 1080, 1920, 1080)
    assert cx2 < 1.0


def test_centers_to_keyframes():
    centers = [
        {"time": 0.0, "cx": 0.5, "cy": 0.5},
        {"time": 1.0, "cx": 0.6, "cy": 0.5},
    ]
    kfs = centers_to_keyframes(centers, 1920, 1080, "9:16")
    assert len(kfs) >= 2
    assert "time" in kfs[0]
    assert "center_x" in kfs[0]


def test_build_crop_expr_single():
    kfs = [{"time": 0, "center_x": 0.5, "center_y": 0.5}]
    expr = build_crop_expr(kfs, 1920, 1080, 9, 16)
    assert "606" in expr
