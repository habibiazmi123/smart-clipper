from app.domain.hooks import generate_candidates, score_candidate


def test_candidate_generation_at_sentence_boundaries():
    segments = [
        {"start": 0, "end": 3, "text": "First sentence."},
        {"start": 3, "end": 6, "text": "Second sentence."},
        {"start": 6, "end": 10, "text": "Third one."},
    ]
    cands = generate_candidates(segments, duration=10)
    assert len(cands) > 0
    assert all("start" in c and "end" in c for c in cands)
    assert all(c["end"] <= 10.0 + 0.1 for c in cands)


def test_score_strong_hook():
    segs = [{"start": 0, "end": 3, "text": "Nobody tells you this about Go.",
            "confidence": 0.9, "words_json": "[]"}]
    s, reasons, _ = score_candidate({"start": 0, "end": 3}, segs)
    assert 0 <= s <= 100
    assert len(reasons) > 0


def test_score_weak_hook():
    segs = [{"start": 0, "end": 3, "text": "Um so yeah ok.",
            "confidence": 0.5, "words_json": "[]"}]
    s, reasons, weaknesses = score_candidate({"start": 0, "end": 3}, segs)
    assert s < 50
