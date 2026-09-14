from app.services.vision_service import smooth_centers, interpolate_centers, adaptive_keyframes


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


def _seg(cx_list, speaker="A", dt=0.1):
    return [{"time": round(i * dt, 3), "cx": cx, "cy": 0.5, "speaker": speaker, "sconf": 0.9}
            for i, cx in enumerate(cx_list)]


def test_adaptive_dense_when_fast():
    # gerak cepat 0.03/sampel -> hampir semua titik disimpan
    seg = _seg([0.30 + i * 0.03 for i in range(10)])
    kfs = adaptive_keyframes(seg)
    assert len(kfs) >= 8, kfs
    assert kfs[0]["time"] == 0.0 and kfs[-1]["time"] == 0.9
    assert all(k["speaker"] == "A" for k in kfs)


def test_adaptive_sparse_when_still():
    # diam total -> cuma titik awal + akhir (max_gap 1.0 tak tersentuh)
    seg = _seg([0.5] * 10)
    kfs = adaptive_keyframes(seg)
    assert len(kfs) == 2, kfs
    assert kfs[0]["cx"] == 0.5 and kfs[-1]["cx"] == 0.5


def test_adaptive_max_gap_bounds_stillness():
    # diam 2.5 detik -> ada titik tiap ~1 detik
    seg = _seg([0.5] * 26, dt=0.1)
    kfs = adaptive_keyframes(seg)
    assert 3 <= len(kfs) <= 5, kfs
    gaps = [b["time"] - a["time"] for a, b in zip(kfs, kfs[1:])]
    assert all(g <= 1.01 for g in gaps), gaps
