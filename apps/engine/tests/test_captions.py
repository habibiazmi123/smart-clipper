from app.domain.captions import split_words_to_lines, generate_ass


def test_split_words_basic():
    words = [
        {"word": "Most", "start": 0.0, "end": 0.2},
        {"word": "developers", "start": 0.2, "end": 0.6},
        {"word": "make", "start": 0.6, "end": 0.8},
        {"word": "this", "start": 0.8, "end": 1.0},
        {"word": "mistake", "start": 1.0, "end": 1.3},
    ]
    lines = split_words_to_lines(words, max_chars=30)
    assert len(lines) >= 1
    assert all("text" in l for l in lines)
    assert all("start" in l for l in lines)
    assert lines[0]["start"] == 0.0


def test_split_no_orphan():
    words = [{"word": f"w{i}", "start": float(i), "end": float(i+1)} for i in range(10)]
    lines = split_words_to_lines(words, max_chars=6, max_lines=2)
    for l in lines:
        wc = len(l["text"].split())
        assert wc >= 2 or len(words) < 2


def test_generate_ass():
    lines = [{"text": "TEST", "start": 0.0, "end": 1.0, "words": []}]
    ass = generate_ass(lines, 1080, 1920)
    assert "ScriptType" in ass
    assert "Dialogue" in ass
    assert "TEST" in ass
