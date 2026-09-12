import json
import sqlite3
import sys

from app.db import init_db, insert_hook_candidate
from app.domain.models import HookCandidate


def test_from_hooks_creates_clips_for_selected_only(tmp_data, monkeypatch):
    from app.api.from_hooks import create_clips_from_hooks, FromHooksReq
    from app.config import settings
    import pathlib
    pid = "ph1"
    orig_data = settings.DATA_ROOT
    object.__setattr__(settings, "DATA_ROOT", tmp_data)
    pdir = tmp_data / "projects" / pid
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "source").mkdir(parents=True, exist_ok=True)
    (pdir / "audio").mkdir(parents=True, exist_ok=True)
    (pdir / "exports").mkdir(parents=True, exist_ok=True)
    db_path = str(tmp_data / "smartclipper.db")
    orig_connect = sqlite3.connect

    def patched(path, *a, **kw):
        if str(path) == str(settings.DATA_ROOT / "smartclipper.db"):
            return orig_connect(db_path, *a, **kw)
        return orig_connect(path, *a, **kw)
    monkeypatch.setattr("app.db.sqlite3.connect", patched)

    class PatchedConn(sqlite3.Connection):
        pass
    # ensure _get_conn patch
    monkeypatch.setattr("app.api.from_hooks._get_conn", lambda: orig_connect(db_path))

    conn = orig_connect(db_path)
    init_db(conn)
    conn.execute("INSERT INTO projects (id,name,source_url,status,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                 (pid, "test", "", "ready", "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"))
    conn.commit()
    for hid, s in [("h1", 0.0), ("h2", 10.0), ("h3", 20.0)]:
        insert_hook_candidate(conn, id=hid, project_id=pid, start=s, end=s + 5.0, score=90.0 - s,
                              source="groq")
    conn.close()

    # Mock heavy deps
    monkeypatch.setattr("app.services.import_service.extract_metadata", lambda p: {"width": 1920, "height": 1080})
    monkeypatch.setattr("app.services.import_service.extract_audio", lambda p, d: str(d / "audio.wav"))
    monkeypatch.setattr("app.providers.face_provider.create_detector", lambda: type("D", (), {"close": lambda self: None})())
    monkeypatch.setattr("app.services.speaker_service.load_wav_mono", lambda p: None)
    monkeypatch.setattr("app.services.speaker_service.analyze_clip_speakers", lambda *a, **kw: [])
    # create a dummy mp4 file so exists check passes
    pathlib.Path(pdir / "source" / "dummy.mp4").write_bytes(b"\x00")

    res = create_clips_from_hooks(pid, FromHooksReq(hook_ids=["h1", "h3"]))
    assert len(res["clips"]) == 2
    ids = {c["hook_id"] for c in res["clips"]}
    assert ids == {"h1", "h3"}
    object.__setattr__(settings, "DATA_ROOT", orig_data)
