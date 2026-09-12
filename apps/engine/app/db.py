import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    source_url TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'importing',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS media (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    source_url TEXT DEFAULT '',
    path TEXT DEFAULT '',
    title TEXT DEFAULT '',
    channel TEXT DEFAULT '',
    duration REAL DEFAULT 0,
    width INTEGER DEFAULT 0,
    height INTEGER DEFAULT 0,
    fps REAL DEFAULT 0,
    has_audio INTEGER DEFAULT 1,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
CREATE TABLE IF NOT EXISTS transcripts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    language TEXT DEFAULT '',
    path TEXT DEFAULT '',
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
CREATE TABLE IF NOT EXISTS transcript_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL,
    text TEXT DEFAULT '',
    confidence REAL DEFAULT 0,
    speaker TEXT,
    words_json TEXT DEFAULT '[]',
    FOREIGN KEY (transcript_id) REFERENCES transcripts(id)
);
CREATE TABLE IF NOT EXISTS hook_candidates (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL,
    score REAL NOT NULL,
    scores_json TEXT DEFAULT '{}',
    reasons_json TEXT DEFAULT '[]',
    weaknesses_json TEXT DEFAULT '[]',
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    hook_candidate_id TEXT DEFAULT '',
    source_start REAL NOT NULL,
    source_end REAL NOT NULL,
    aspect_ratio TEXT DEFAULT '9:16',
    status TEXT DEFAULT 'draft',
    crop_manually_modified INTEGER DEFAULT 0,
    title TEXT DEFAULT '',
    caption_short TEXT DEFAULT '',
    caption_long TEXT DEFAULT '',
    cta TEXT DEFAULT '',
    hashtags_json TEXT DEFAULT '[]',
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
CREATE TABLE IF NOT EXISTS face_detections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    w REAL NOT NULL,
    h REAL NOT NULL,
    confidence REAL NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
CREATE TABLE IF NOT EXISTS face_tracks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL,
    centers_json TEXT DEFAULT '[]',
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
CREATE TABLE IF NOT EXISTS crop_keyframes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id TEXT NOT NULL,
    time REAL NOT NULL,
    center_x REAL NOT NULL,
    center_y REAL NOT NULL,
    source TEXT DEFAULT 'ai',
    FOREIGN KEY (clip_id) REFERENCES clips(id)
);
CREATE TABLE IF NOT EXISTS captions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    start REAL NOT NULL,
    end REAL NOT NULL,
    text TEXT DEFAULT '',
    words_json TEXT DEFAULT '[]',
    style_json TEXT DEFAULT '{}',
    FOREIGN KEY (clip_id) REFERENCES clips(id)
);
CREATE TABLE IF NOT EXISTS render_jobs (
    id TEXT PRIMARY KEY,
    clip_id TEXT NOT NULL,
    kind TEXT DEFAULT 'export',
    status TEXT DEFAULT 'queued',
    progress REAL DEFAULT 0,
    stage TEXT DEFAULT '',
    error TEXT DEFAULT '',
    output_path TEXT DEFAULT '',
    FOREIGN KEY (clip_id) REFERENCES clips(id)
);
"""


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def insert_project(conn: sqlite3.Connection, **kw) -> object:
    from app.domain.models import Project
    now = _now()
    kw.setdefault("created_at", now)
    kw.setdefault("updated_at", now)
    kw.setdefault("source_url", "")
    conn.execute(
        "INSERT INTO projects (id,name,source_url,status,created_at,updated_at) VALUES (?,?,?,?,?,?)",
        (kw["id"], kw["name"], kw.get("source_url", ""), kw.get("status", "importing"), kw["created_at"], kw["updated_at"]),
    )
    conn.commit()
    return Project(**kw)


def get_project(conn: sqlite3.Connection, project_id: str):
    from app.domain.models import Project
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        return None
    return Project(
        id=row[0], name=row[1], source_url=row[2], status=row[3], created_at=row[4], updated_at=row[5]
    )


def update_project(conn: sqlite3.Connection, project_id: str, **kw) -> None:
    sets = []
    vals = []
    for k, v in kw.items():
        sets.append(f"{k}=?")
        vals.append(v)
    sets.append("updated_at=?")
    vals.append(_now())
    vals.append(project_id)
    conn.execute(f"UPDATE projects SET {','.join(sets)} WHERE id=?", vals)
    conn.commit()


def insert_clip(conn: sqlite3.Connection, **kw) -> object:
    from app.domain.models import Clip
    conn.execute(
        """INSERT INTO clips
        (id,project_id,hook_candidate_id,source_start,source_end,aspect_ratio,status,
         crop_manually_modified,title,caption_short,caption_long,cta,hashtags_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            kw["id"], kw["project_id"], kw.get("hook_candidate_id", ""),
            kw["source_start"], kw["source_end"], kw.get("aspect_ratio", "9:16"),
            kw.get("status", "draft"), int(kw.get("crop_manually_modified", False)),
            kw.get("title", ""), kw.get("caption_short", ""), kw.get("caption_long", ""),
            kw.get("cta", ""), kw.get("hashtags_json", "[]"),
        ),
    )
    conn.commit()
    return Clip(**kw)


def get_clip(conn: sqlite3.Connection, clip_id: str):
    from app.domain.models import Clip
    row = conn.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone()
    if not row:
        return None
    return Clip(
        id=row[0], project_id=row[1], hook_candidate_id=row[2],
        source_start=row[3], source_end=row[4], aspect_ratio=row[5],
        status=row[6], crop_manually_modified=bool(row[7]),
        title=row[8], caption_short=row[9], caption_long=row[10],
        cta=row[11], hashtags_json=row[12],
    )


def update_clip(conn: sqlite3.Connection, clip_id: str, **kw) -> None:
    sets = []
    vals = []
    for k, v in kw.items():
        sets.append(f"{k}=?")
        vals.append(v)
    vals.append(clip_id)
    conn.execute(f"UPDATE clips SET {','.join(sets)} WHERE id=?", vals)
    conn.commit()


def insert_transcript_segments(conn: sqlite3.Connection, transcript_id: str, segments: list[dict]) -> None:
    conn.executemany(
        "INSERT INTO transcript_segments (transcript_id,idx,start,end,text,confidence,speaker,words_json) VALUES (?,?,?,?,?,?,?,?)",
        [(transcript_id, s["idx"], s["start"], s["end"], s["text"], s["confidence"], s.get("speaker"), s.get("words_json", "[]")) for s in segments],
    )
    conn.commit()


def insert_hook_candidate(conn: sqlite3.Connection, **kw) -> object:
    from app.domain.models import HookCandidate
    conn.execute(
        "INSERT INTO hook_candidates (id,project_id,start,end,score,scores_json,reasons_json,weaknesses_json) VALUES (?,?,?,?,?,?,?,?)",
        (kw["id"], kw["project_id"], kw["start"], kw["end"], kw["score"],
         kw.get("scores_json", "{}"), kw.get("reasons_json", "[]"), kw.get("weaknesses_json", "[]")),
    )
    conn.commit()
    return HookCandidate(**kw)


def insert_crop_keyframes(conn: sqlite3.Connection, clip_id: str, keyframes: list[dict], source: str = "ai") -> None:
    conn.executemany(
        "INSERT INTO crop_keyframes (clip_id,time,center_x,center_y,source) VALUES (?,?,?,?,?)",
        [(clip_id, kf["time"], kf["center_x"], kf["center_y"], source) for kf in keyframes],
    )
    conn.commit()


def get_crop_keyframes(conn: sqlite3.Connection, clip_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT time,center_x,center_y,source FROM crop_keyframes WHERE clip_id=? ORDER BY time",
        (clip_id,),
    ).fetchall()
    return [{"time": r[0], "center_x": r[1], "center_y": r[2], "source": r[3]} for r in rows]


def delete_manual_crop_keyframes(conn: sqlite3.Connection, clip_id: str) -> None:
    conn.execute("DELETE FROM crop_keyframes WHERE clip_id=? AND source='manual'", (clip_id,))
    conn.commit()


def insert_face_detection(conn: sqlite3.Connection, project_id: str, ts: float, x: float, y: float, w: float, h: float, conf: float) -> None:
    conn.execute(
        "INSERT INTO face_detections (project_id,timestamp,x,y,w,h,confidence) VALUES (?,?,?,?,?,?,?)",
        (project_id, ts, x, y, w, h, conf),
    )


def flush_face_detections(conn: sqlite3.Connection) -> None:
    conn.commit()


def insert_face_track(conn: sqlite3.Connection, project_id: str, start: float, end: float, centers_json: str) -> None:
    conn.execute(
        "INSERT INTO face_tracks (project_id,start,end,centers_json) VALUES (?,?,?,?)",
        (project_id, start, end, centers_json),
    )
    conn.commit()


def insert_caption(conn: sqlite3.Connection, clip_id: str, idx: int, start: float, end: float, text: str, words_json: str = "[]", style_json: str = "{}") -> None:
    conn.execute(
        "INSERT INTO captions (clip_id,idx,start,end,text,words_json,style_json) VALUES (?,?,?,?,?,?,?)",
        (clip_id, idx, start, end, text, words_json, style_json),
    )
    conn.commit()


def list_clips_for_project(conn: sqlite3.Connection, project_id: str) -> list:
    from app.domain.models import Clip
    rows = conn.execute("SELECT * FROM clips WHERE project_id=? ORDER BY source_start", (project_id,)).fetchall()
    return [
        Clip(id=r[0], project_id=r[1], hook_candidate_id=r[2],
             source_start=r[3], source_end=r[4], aspect_ratio=r[5],
             status=r[6], crop_manually_modified=bool(r[7]),
             title=r[8], caption_short=r[9], caption_long=r[10],
             cta=r[11], hashtags_json=r[12])
        for r in rows
    ]


def list_hooks_for_project(conn: sqlite3.Connection, project_id: str) -> list:
    rows = conn.execute(
        "SELECT id,project_id,start,end,score,scores_json,reasons_json,weaknesses_json FROM hook_candidates WHERE project_id=? ORDER BY score DESC",
        (project_id,),
    ).fetchall()
    from app.domain.models import HookCandidate
    return [HookCandidate(id=r[0], project_id=r[1], start=r[2], end=r[3],
                          score=r[4], scores_json=r[5], reasons_json=r[6],
                          weaknesses_json=r[7]) for r in rows]
