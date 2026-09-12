from app.services.vision_service import smooth_centers, interpolate_centers


def test_smooth_centers_reduces_variance():
    raw = [
        {"time": 0.0, "cx": 0.41},
        {"time": 0.5, "cx": 0.47},
        {"time": 1.0, "cx": 0.42},
        {"time": 1.5, "cx": 0.51},
        {"time": 2.0, "cx": 0.45},
    ]
    smoothed = smooth_centers(raw, alpha=0.15, deadzone=0.02)
    assert len(smoothed) == len(raw)
    raw_range = max(r["cx"] for r in raw) - min(r["cx"] for r in raw)
    sm_range = max(s["cx"] for s in smoothed) - min(s["cx"] for s in smoothed)
    assert sm_range < raw_range


def test_deadzone():
    raw = [{"time": 0.0, "cx": 0.50}, {"time": 0.5, "cx": 0.503}]
    smoothed = smooth_centers(raw, alpha=0.15, deadzone=0.02)
    assert smoothed[1]["cx"] == 0.50  # no movement: within deadzone


def test_interpolate_centers():
    centers = [
        {"time": 0.0, "cx": 0.5, "cy": 0.5},
        {"time": 1.0, "cx": 0.6, "cy": 0.5},
    ]
    result = interpolate_centers(centers, interval=0.5)
    assert len(result) >= 3
    assert result[0]["time"] == 0.0
    assert result[1]["cx"] == 0.55
    assert result[-1]["cx"] == 0.6
