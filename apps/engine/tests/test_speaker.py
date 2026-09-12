from app.services.speaker_service import SpeakerTracker, _box_iou


def _face(x, w=0.15, h=0.3, conf=0.9):
    return {"x": x, "y": 0.4, "w": w, "h": h, "confidence": conf}


def test_iou_ids_stable():
    tr = SpeakerTracker()
    r1 = tr.update([_face(0.3), _face(0.7)], {}, True, 0.0)
    r2 = tr.update([_face(0.31), _face(0.69)], {}, True, 0.5)
    assert r1 is not None and r2 is not None
    assert set(tr.tracks) == {"A", "B"}
    # wajah kiri tetap id sama
    left1 = min(tr.tracks, key=lambda tid: tr.tracks[tid]["x"])
    assert tr.tracks[left1]["x"] < 0.5


def test_box_iou_same_is_one():
    b = {"x": 0.5, "y": 0.5, "w": 0.2, "h": 0.3}
    assert abs(_box_iou(b, b) - 1.0) < 1e-6
    far = {"x": 0.9, "y": 0.9, "w": 0.05, "h": 0.05}
    assert _box_iou(b, far) == 0.0


def test_single_face_always_active():
    tr = SpeakerTracker()
    for i in range(5):
        r = tr.update([_face(0.6)], {0: 5.0}, True, i * 0.5)
    assert r["speaker"] == "A"


def test_brief_interjection_does_not_switch():
    """Tanggapan singkat (1-2 window) tidak boleh nyuri crop."""
    tr = SpeakerTracker()
    # A dominan dulu
    for i in range(4):
        tr.update([_face(0.3), _face(0.7)], {0: 8.0, 1: 0.5}, True, i * 0.5)
    assert tr.current == "A"
    # B menyela 2 window saja (< 1.5 detik)
    for i in range(4, 6):
        r = tr.update([_face(0.3), _face(0.7)], {0: 0.5, 1: 9.0}, True, i * 0.5)
    assert r["speaker"] == "A", "sela singkat tidak boleh switch"


def test_sustained_speaker_switches_once():
    tr = SpeakerTracker()
    for i in range(4):
        tr.update([_face(0.3), _face(0.7)], {0: 8.0, 1: 0.5}, True, i * 0.5)
    r = None
    for i in range(4, 10):
        r = tr.update([_face(0.3), _face(0.7)], {0: 0.5, 1: 9.0}, True, i * 0.5)
    assert r["speaker"] == "B"


def test_dropout_holds_framing():
    """Wajah hilang 1-2 sampel (dropout) -> tahan, jangan loncat ke false-positive."""
    tr = SpeakerTracker()
    for i in range(3):
        tr.update([_face(0.3), _face(0.7)], {0: 8.0, 1: 0.5}, True, i * 0.5)
    assert tr.current == "A"
    # A dropout 1 sampel, cuma wajah asing terlihat -> tetap A
    r = tr.update([_face(0.75, conf=0.6)], {0: 9.0}, True, 1.5)
    assert r["speaker"] == "A"
    # A kembali -> tetap A, posisi update
    r = tr.update([_face(0.3), _face(0.75, conf=0.6)], {0: 8.0, 1: 1.0}, True, 2.0)
    assert r["speaker"] == "A"


def test_silence_holds_framing():
    tr = SpeakerTracker()
    for i in range(3):
        tr.update([_face(0.3), _face(0.7)], {0: 8.0, 1: 0.5}, True, i * 0.5)
    # sunyi: B mulut bergerak (noise) tapi tidak speaking -> tetap A
    for i in range(3, 8):
        r = tr.update([_face(0.3), _face(0.7)], {0: 0.1, 1: 9.0}, False, i * 0.5)
    assert r["speaker"] == "A"


def test_no_faces_returns_none():
    tr = SpeakerTracker()
    assert tr.update([], {}, True, 0.0) is None


def test_fast_move_keeps_id_via_centroid():
    """Lompatan cepat (IoU putus) tapi centroid dekat -> id sama, tidak switch."""
    tr = SpeakerTracker()
    tr.update([_face(0.30)], {0: 8.0}, True, 0.0)
    assert tr.current == "A"
    # geser 0.08 dalam 0.5s: IoU bisa putus, centroid tetap dekat
    r = tr.update([_face(0.38, w=0.12, h=0.25)], {0: 8.0}, True, 0.5)
    assert r["speaker"] == "A"
    assert set(tr.tracks) == {"A"}


def test_two_distinct_faces_get_two_ids():
    tr = SpeakerTracker()
    tr.update([_face(0.25), _face(0.70)], {0: 8.0, 1: 1.0}, True, 0.0)
    assert set(tr.tracks) == {"A", "B"}
