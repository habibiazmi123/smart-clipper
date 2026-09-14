from app.domain.crop import _is_switch


def _kf(cx, speaker=None, source="ai"):
    return {"center_x": cx, "speaker": speaker, "source": source}


def test_diff_speaker_cuts():
    assert _is_switch(_kf(0.3, "A"), _kf(0.7, "B")) is True


def test_same_speaker_small_glides():
    assert _is_switch(_kf(0.3, "A"), _kf(0.34, "A")) is False


def test_same_speaker_big_jump_cuts():
    # geser jauh = frame kehilangan wajah, jangan glide
    assert _is_switch(_kf(0.3, "A"), _kf(0.5, "A")) is True


def test_manual_fine_correction_glides():
    assert _is_switch(_kf(0.3, "A", "manual"), _kf(0.34, "B", "manual")) is False


def test_manual_big_reposition_cuts():
    assert _is_switch(_kf(0.3, "A", "manual"), _kf(0.7, "B", "manual")) is True


def test_none_cuts_unless_manual_small():
    assert _is_switch(_kf(0.5, None), _kf(0.5, "A")) is True
    assert _is_switch(_kf(0.5, None, "manual"), _kf(0.52, "A", "manual")) is False
