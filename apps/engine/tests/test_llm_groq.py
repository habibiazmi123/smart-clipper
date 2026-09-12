from app.providers import llm_provider as llm


def test_snap_clamp_dedupe():
    segs = [
        {"start": 0.0, "end": 2.0, "text": "Hello world.", "confidence": 0.9,
         "words_json": '[{"word":"Hello","start":0.0,"end":0.5},{"word":"world.","start":0.6,"end":1.0}]'},
        {"start": 2.0, "end": 5.0, "text": "Nobody tells you this.", "confidence": 0.9, "words_json": "[]"},
    ]
    raw = [
        {"start": 0.33, "end": 99.0, "score": 91, "hook_text": "x", "reasons": ["a"], "weakness": ""},
        {"start": 0.4, "end": 4.0, "score": 80, "hook_text": "y", "reasons": [], "weakness": ""},
    ]
    out = llm.dedupe_hooks(llm.validate_and_snap_hooks(raw, segs, 60))
    assert len(out) == 1
    assert out[0]["end"] - out[0]["start"] <= 60.0
    assert out[0]["start"] in (0.0, 0.6)


def test_chunk_and_fallback(monkeypatch):
    segs = [{"start": float(i), "end": float(i + 1), "text": "word " * 5000,
             "confidence": 0.5, "words_json": "[]"} for i in range(5)]
    chunks = llm.chunk_transcript(segs, max_chars=1000)
    assert len(chunks) >= 2
    monkeypatch.setenv("GROQ_API_KEY", "")
    out = llm.find_hooks(segs, n=3, max_duration=60)
    assert len(out) <= 3 and all(h["source"] == "heuristic" for h in out)
