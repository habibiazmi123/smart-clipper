import sqlite3
from app.db import init_db, insert_project, get_project


def test_init_creates_tables(tmp_data):
    conn = sqlite3.connect(str(tmp_data / "test.db"))
    init_db(conn)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    assert "projects" in tables
    assert "clips" in tables
    assert "face_detections" in tables
    assert "crop_keyframes" in tables
    conn.close()


def test_project_roundtrip(tmp_data):
    conn = sqlite3.connect(str(tmp_data / "test.db"))
    init_db(conn)
    p = insert_project(conn, id="p1", name="My Video", source_url="https://x.com/v1")
    assert p.id == "p1"
    assert p.name == "My Video"
    loaded = get_project(conn, "p1")
    assert loaded.name == "My Video"
    conn.close()


def test_hook_provenance_columns(tmp_data):
    from app.db import insert_hook_candidate, list_hooks_for_project
    conn = sqlite3.connect(str(tmp_data / "test.db"))
    init_db(conn)
    insert_hook_candidate(conn, id="h1", project_id="p1", start=1.0, end=5.0,
                          score=91.0, llm_model="llama-3.3-70b-versatile", source="groq")
    hooks = list_hooks_for_project(conn, "p1")
    assert hooks[0].source == "groq"
    assert hooks[0].llm_model == "llama-3.3-70b-versatile"
    conn.close()
