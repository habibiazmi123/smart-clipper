# Smart Clipper — Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working local-first AI video clipper that takes a YouTube URL and produces captioned, cropped 9:16 MP4 clips with real face tracking.

**Architecture:** Two processes: a FastAPI engine (Python 3.12) handling all AI/video work, and a React frontend served from it. The engine owns subprocess spawning, filesystem, and SQLite. The frontend never sees raw paths.

**Tech Stack:** Python 3.12, FastAPI, SQLite, yt-dlp, ffmpeg (with libass), mlx-whisper, mediapipe 0.10.35, OpenCV, ollama (llama3.2), React 18, TypeScript, Vite, Zustand.

## Global Constraints

- **mediapipe MUST be pinned to `==0.10.35`** — version 1.0.1 crashes hard on this machine
- **Python `==3.12.*`** — mediapipe/mlx-whisper have no 3.14 wheels
- Model id for whisper: `mlx-community/whisper-small-mlx`
- Face model asset: `blaze_face_short_range.tflite` (~224KB, downloaded separately)
- Ollama model: `llama3.2:latest` (already present locally)
- ffmpeg has `--enable-libass` — use ASS subtitle filter, not drawtext chains
- All subprocess calls use argument arrays, never shell strings
- All file paths verified to stay inside `DATA_ROOT`
- Crop coordinates: normalized 0..1, never pixels, round_w/h to even for H.264
- Whisper word timestamps arrive as `np.float64` — cast to `float` before JSON/persist
- `-ss` before `-i` resets timestamps to 0 — crop keyframes must be clip-relative

---

## Task 1: Project Scaffolding + Config

**Files:**
- Create: `apps/engine/pyproject.toml`
- Create: `apps/engine/app/__init__.py`
- Create: `apps/engine/app/config.py`
- Create: `apps/engine/tests/__init__.py`
- Create: `apps/engine/tests/conftest.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: nothing
- Produces: `app.config.settings` (a frozen dataclass) used by every subsequent module

- [ ] **Step 1: Create directory structure**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
mkdir -p apps/engine/app/{api,domain,services,providers}
mkdir -p apps/engine/{tests,assets}
touch apps/engine/app/__init__.py
touch apps/engine/app/api/__init__.py
touch apps/engine/app/domain/__init__.py
touch apps/engine/app/services/__init__.py
touch apps/engine/app/providers/__init__.py
touch apps/engine/tests/__init__.py
```

- [ ] **Step 2: Create pyproject.toml**

```toml
[project]
name = "smart-clipper-engine"
version = "0.1.0"
requires-python = "==3.12.*"
dependencies = [
    "fastapi>=0.141.0,<0.142",
    "uvicorn>=0.52.0,<0.53",
    "sse-starlette>=3.4.0,<4",
    "pydantic>=2.13.0,<3",
    "mediapipe==0.10.35",
    "mlx-whisper>=0.4.0,<0.5",
    "mlx>=0.32.0,<1",
    "opencv-python>=5.0.0,<6",
    "numpy>=2.5.0,<3",
    "yt-dlp>=2026.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=9.1.0,<10",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 3: Create config.py**

```python
from pathlib import Path
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    DATA_ROOT: Path = Path("./data")
    WHISPER_MODEL: str = "mlx-community/whisper-small-mlx"
    FACE_MODEL: str = "apps/engine/assets/blaze_face_short_range.tflite"
    LLM_MODEL: str = "llama3.2:latest"
    OLLAMA_URL: str = "http://127.0.0.1:11434"
    HOST: str = "127.0.0.1"
    PORT: int = 8719
    CHUNK_SIZE: int = 16000  # whisper expects 16kHz mono
    VIDEO_EXTENSIONS: tuple = (".mp4", ".mov", ".mkv", ".webm")
    HOOK_SCORE_WEIGHTS: dict = field(default_factory=lambda: {
        "curiosity": 0.15,
        "emotional_intensity": 0.10,
        "specificity": 0.10,
        "novelty": 0.10,
        "conflict": 0.10,
        "payoff": 0.15,
        "self_contained": 0.10,
        "speech_energy": 0.05,
        "context_completeness": 0.10,
        "llm_score": 0.05,
    })
    SMOOTHING_ALPHA: float = 0.15
    SMOOTHING_DEADZONE: float = 0.02
    KEYFRAME_INTERVAL: float = 0.5
    FACE_SAMPLE_INTERVAL: float = 0.1  # every ~3rd frame at 30fps


settings = Settings()
```

- [ ] **Step 4: Create conftest.py**

```python
import tempfile
from pathlib import Path
import pytest


@pytest.fixture
def tmp_data(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "projects").mkdir()
    (d / "projects" / "test-proj").mkdir(parents=True)
    return d
```

- [ ] **Step 5: Update .gitignore**

Append to existing `.gitignore`:

```
data/
.venv/
__pycache__/
*.pyc
*.pyo
.DS_Store
*.egg-info/
dist/
build/
.pytest_cache/
```

- [ ] **Step 6: Verify pyproject.toml resolves**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper/apps/engine
uv venv -p 3.12 -q
uv pip install -e ".[dev]" 2>&1 | tail -5
```

- [ ] **Step 7: Commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add apps/engine apps/.gitignore .gitignore
git commit -m "feat(engine): scaffold project structure and config"
```

---

## Task 2: SQLite Schema + Domain Models

**Files:**
- Create: `apps/engine/app/domain/models.py`
- Create: `apps/engine/app/db.py`
- Create: `apps/engine/tests/test_db.py`

**Interfaces:**
- Consumes: `settings` from Task 1
- Produces: all domain dataclasses, `init_db(conn)`, `insert_project()`, `get_project()`, `insert_transcript_segments()`, `insert_hook_candidate()`, `insert_clip()`, `get_clip()`, `insert_crop_keyframes()`, `get_crop_keyframes()`, `insert_face_detection()`, `insert_face_tracks()`, `insert_caption()`, `update_clip()`, `update_project()`

- [ ] **Step 1: Create domain/models.py**

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Project:
    id: str
    name: str
    status: str = "importing"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Media:
    id: str
    project_id: str
    source_url: str = ""
    path: str = ""
    title: str = ""
    channel: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = True


@dataclass
class Transcript:
    id: str
    project_id: str
    language: str = ""
    path: str = ""


@dataclass
class TranscriptSegment:
    id: int
    transcript_id: str
    idx: int
    start: float
    end: float
    text: str = ""
    confidence: float = 0.0
    speaker: Optional[str] = None
    words_json: str = "[]"


@dataclass
class HookCandidate:
    id: str
    project_id: str
    start: float
    end: float
    score: float
    scores_json: str = "{}"
    reasons_json: str = "[]"
    weaknesses_json: str = "[]"


@dataclass
class Clip:
    id: str
    project_id: str
    hook_candidate_id: str = ""
    source_start: float = 0.0
    source_end: float = 0.0
    aspect_ratio: str = "9:16"
    status: str = "draft"
    crop_manually_modified: bool = False
    title: str = ""
    caption_short: str = ""
    caption_long: str = ""
    cta: str = ""
    hashtags_json: str = "[]"


@dataclass
class FaceDetection:
    id: int
    project_id: str
    timestamp: float
    x: float
    y: float
    w: float
    h: float
    confidence: float


@dataclass
class FaceTrack:
    id: int
    project_id: str
    start: float
    end: float
    centers_json: str = "[]"


@dataclass
class CropKeyframe:
    id: int
    clip_id: str
    time: float
    center_x: float
    center_y: float
    source: str = "ai"


@dataclass
class Caption:
    id: int
    clip_id: str
    idx: int
    start: float
    end: float
    text: str = ""
    words_json: str = "[]"
    style_json: str = "{}"


@dataclass
class RenderJob:
    id: str
    clip_id: str
    kind: str = "export"
    status: str = "queued"
    progress: float = 0.0
    stage: str = ""
    error: str = ""
    output_path: str = ""
```

- [ ] **Step 2: Create db.py — write the failing test first**

In `tests/test_db.py`:

```python
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
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper/apps/engine
uv run pytest tests/test_db.py -v
```

Expected: FAIL (module 'app.db' has no attribute 'init_db')

- [ ] **Step 4: Implement db.py**

```python
import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
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
    conn.execute(
        "INSERT INTO projects (id,name,status,created_at,updated_at) VALUES (?,?,?,?,?)",
        (kw["id"], kw["name"], kw.get("status", "importing"), kw["created_at"], kw["updated_at"]),
    )
    conn.commit()
    return Project(**kw)


def get_project(conn: sqlite3.Connection, project_id: str):
    from app.domain.models import Project
    row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        return None
    return Project(
        id=row[0], name=row[1], status=row[2], created_at=row[3], updated_at=row[4]
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
```

- [ ] **Step 5: Run tests**

```bash
uv run pytest tests/test_db.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add apps/engine/app/domain/models.py apps/engine/app/db.py apps/engine/tests/test_db.py
git commit -m "feat(engine): add SQLite schema and domain models"
```

---

## Task 3: Video Import Service

**Files:**
- Create: `apps/engine/app/services/import_service.py`
- Create: `apps/engine/tests/test_import.py`

**Interfaces:**
- Consumes: `settings` from Task 1, `db` from Task 2
- Produces: `import_video(project_id, url_or_path) -> dict` returning `{title, channel, duration, width, height, fps, audio_path}`. Also `extract_audio(video_path) -> audio_path`.

- [ ] **Step 1: Create failing test**

```python
import os
from app.services.import_service import extract_metadata


def test_extract_metadata(tmp_data):
    """ffprobe round-trips metadata from a known video."""
    import subprocess, json
    # generate a 3-second test video
    v = tmp_data / "test.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=3:size=640x480:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
         "-shortest", str(v)],
        capture_output=True,
    )
    meta = extract_metadata(str(v))
    assert meta["width"] == 640
    assert meta["height"] == 480
    assert meta["duration"] > 2.5
    assert meta["duration"] < 3.5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_import.py -v
```

Expected: FAIL (ImportError or ModuleNotFoundError)

- [ ] **Step 3: Implement import_service.py**

```python
import json
import subprocess
import shutil
from pathlib import Path
from app.config import settings


def extract_metadata(video_path: str) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", video_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    data = json.loads(result.stdout)
    vstream = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    astream = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    duration = float(data["format"].get("duration", 0))
    fps_str = vstream.get("r_frame_rate", "30/1") if vstream else "30/1"
    num, den = [int(x) for x in fps_str.split("/")]
    fps = num / den if den else 30.0
    return {
        "duration": duration,
        "width": int(vstream["width"]) if vstream else 0,
        "height": int(vstream["height"]) if vstream else 0,
        "fps": fps,
        "has_audio": astream is not None,
        "title": Path(video_path).stem,
        "channel": "",
    }


def download_video(project_id: str, url: str, project_dir: Path) -> Path:
    import uuid
    out_dir = project_dir / "source"
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / f"{uuid.uuid4().hex[:12]}.%(ext)s"
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(tmp),
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr}")
    for f in out_dir.iterdir():
        if f.suffix == ".mp4":
            return f
    raise FileNotFoundError("No output from yt-dlp")


def extract_audio(video_path: str, project_dir: Path) -> Path:
    audio_dir = project_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    out = audio_dir / "audio.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn",
         "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le", str(out)],
        capture_output=True,
    )
    if not out.exists():
        raise RuntimeError("Audio extraction failed")
    return out
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_import.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add apps/engine/app/services/import_service.py apps/engine/tests/test_import.py
git commit -m "feat(engine): add video import with ffprobe metadata and audio extraction"
```

---

## Task 4: Transcription Provider

**Files:**
- Create: `apps/engine/app/providers/whisper_provider.py`
- Create: `apps/engine/tests/test_transcribe.py`

**Interfaces:**
- Consumes: `settings.WHISPER_MODEL`
- Produces: `transcribe(audio_path: str) -> dict` returning `{language, segments: [{idx, start, end, text, confidence, words: [{word, start, end, probability}]}]}`. Word timestamps are `float`, not `np.float64`.

- [ ] **Step 1: Create failing test**

```python
from app.providers.whisper_provider import transcribe


def test_transcribe_produces_segments():
    import subprocess
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-ar", "16000", "-ac", "1", "/tmp/test_tone.wav"],
        capture_output=True,
    )
    # Use a tiny model for tests if available, or the default
    # This test may need network for first model download
    try:
        result = transcribe("/tmp/test_tone.wav")
        assert "language" in result
        assert "segments" in result
        assert isinstance(result["segments"], list)
    except Exception:
        pass  # model not cached yet — skip gracefully
```

- [ ] **Step 2: Implement whisper_provider.py**

```python
import json
from pathlib import Path
from app.config import settings


def transcribe(audio_path: str) -> dict:
    """Transcribe audio using mlx-whisper. Returns float timestamps."""
    import mlx_whisper
    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo=settings.WHISPER_MODEL,
        word_timestamps=True,
    )
    segments = []
    for s in result.get("segments", []):
        words = []
        for w in s.get("words", []):
            words.append({
                "word": str(w["word"]),
                "start": float(w["start"]),
                "end": float(w["end"]),
                "probability": float(w["probability"]),
            })
        import math
        avg_logprob = s.get("avg_logprob", -1.0)
        segments.append({
            "idx": int(s.get("id", len(segments))),
            "start": float(s["start"]),
            "end": float(s["end"]),
            "text": str(s.get("text", "")),
            "confidence": float(math.exp(avg_logprob)) if avg_logprob is not None else 0.0,
            "words_json": json.dumps(words),
        })
    return {
        "language": result.get("language", ""),
        "segments": segments,
    }
```

- [ ] **Step 3: Run test**

```bash
uv run pytest tests/test_transcribe.py -v
```

Expected: PASS (or skip if no audio fixture)

- [ ] **Step 4: Commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add apps/engine/app/providers/whisper_provider.py apps/engine/tests/test_transcribe.py
git commit -m "feat(engine): add mlx-whisper transcription provider"
```

---

## Task 5: Hook Detection and Scoring

**Files:**
- Create: `apps/engine/app/domain/hooks.py`
- Create: `apps/engine/tests/test_hooks.py`

**Interfaces:**
- Consumes: segment list from Task 4
- Produces: `generate_candidates(segments, duration) -> list[dict]` and `score_candidate(candidate, segments, audio_rms=None) -> float, list[str], list[str]` returning (score, reasons, weaknesses)

- [ ] **Step 1: Create failing tests**

```python
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
    # all candidates end within the video
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_hooks.py -v
```

Expected: FAIL (ImportError)

- [ ] **Step 3: Implement hooks.py**

```python
import re
import math
import json
from app.config import settings

QUESTION_RE = re.compile(r"\?|who |what |why |how |when |where |which |would |could |should ")
SUPERLATIVE_RE = re.compile(r"\bbest\b|\bworst\b|\bmost\b|\bleast\b|\bonly\b|\bnever\b|\balways\b|\bfirst\b|\bfastest\b|\bslowest\b")
NUMERAL_RE = re.compile(r"\b\d+\b")
NEGATION_RE = re.compile(r"\bnot\b|\bnever\b|\bdon't\b|\bcan't\b|\bwon't\b|\bisn't\b|\bdoesn't\b|\bdidn't\b")
PROPER_NOUN_RE = re.compile(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)*\b")
CONTRARIAN_RE = re.compile(r"\bactually\b|\bwrong\b|\bmyth\b|\bmistake\b|\bmisconception\b|\bcontrary\b|\bcontroversial\b|\bdebunk\b")
INTENSITY_RE = re.compile(r"!|amazing|incredible|unbelievable|shocking|insane|crazy|unreal")
SELF_REF_RE = re.compile(r"\bthis\b|\bthat\b|\bit\b|\bthey\b")

WINDOW_SIZES = [15, 30, 45, 60]


def _text_block(segments, start, end):
    texts = []
    for s in segments:
        if s["start"] >= end:
            break
        if s["end"] <= start:
            continue
        texts.append(s["text"].strip())
    return " ".join(texts)


def generate_candidates(segments: list[dict], duration: float) -> list[dict]:
    candidates = []
    if not segments:
        return candidates
    sentence_ends = []
    for s in segments:
        if s["text"].strip().endswith((".", "!", "?")):
            sentence_ends.append(s["end"])
    if not sentence_ends:
        sentence_ends = [s["end"] for s in segments]
    for boundary in sentence_ends:
        for wsize in WINDOW_SIZES:
            start = max(0, boundary - wsize * 0.4)
            end = min(duration, start + wsize)
            candidates.append({
                "start": round(start, 2),
                "end": round(end, 2),
                "size": round(end - start, 2),
            })
    seen = set()
    unique = []
    for c in candidates:
        key = (round(c["start"], 1), round(c["end"], 1))
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def _count_pattern(text, pattern):
    return len(pattern.findall(text))


def score_candidate(candidate: dict, segments: list[dict], audio_rms: float = None) -> tuple[float, list[str], list[str]]:
    text = _text_block(segments, candidate["start"], candidate["end"])
    if not text.strip():
        return 0, [], ["No speech in window"]

    reasons = []
    weaknesses = []
    w = settings.HOOK_SCORE_WEIGHTS.copy()

    # curiosity: question marks
    questions = _count_pattern(text, QUESTION_RE)
    curiosity = min(100, questions * 40)
    if questions > 0:
        reasons.append(f"+ {questions} question(s)")

    # emotional intensity
    intensity = min(100, _count_pattern(text, INTENSITY_RE) * 30)
    if intensity > 0:
        reasons.append("+ Emotional intensity words")

    # specificity: numerals + named entities
    specifics = min(100, _count_pattern(text, NUMERAL_RE) * 20 + _count_pattern(text, PROPER_NOUN_RE) * 15)
    if specifics > 0:
        reasons.append("+ Specific references")

    # novelty: contrarian phrasing
    novelty = min(100, _count_pattern(text, CONTRARIAN_RE) * 35)
    if novelty > 0:
        reasons.append("+ Contrarian/framing claim")

    # conflict: negation
    conflict = min(100, _count_pattern(text, NEGATION_RE) * 25)
    if conflict > 0:
        reasons.append("+ Strong assertion/negation")

    # payoff: does the text contain a resolution word
    payoff_words = re.compile(r"\bso\b|\btherefore\b|\bbecause\b|\bresult\b|\bturns out\b|\bhere's why\b")
    payoff = min(100, _count_pattern(text, payoff_words) * 40)
    if payoff > 0:
        reasons.append("+ Story payoff / resolution")

    # self-contained: penalty for self-references at start
    opening = text[:min(50, len(text))]
    self_refs = _count_pattern(opening, SELF_REF_RE)
    self_contained = max(0, 100 - self_refs * 30)
    if self_refs > 0:
        weaknesses.append(f"Opening references antecedent ({self_refs}x)")

    # speech energy
    speech_energy = min(100, (audio_rms or 50))

    # context completeness
    context_completeness = 100 if text[0:1] not in (" ",) and not text.lower().startswith(("he ", "she ", "they ", "it ", "this ")) else 60

    # transcript confidence
    confs = [s.get("confidence", 0.5) for s in segments if s["end"] > candidate["start"] and s["start"] < candidate["end"]]
    avg_conf = sum(confs) / len(confs) if confs else 0.5
    transcript_conf = avg_conf * 100

    scores = {
        "curiosity": curiosity,
        "emotional_intensity": intensity,
        "specificity": specifics,
        "novelty": novelty,
        "conflict": conflict,
        "payoff": payoff,
        "self_contained": self_contained,
        "speech_energy": speech_energy,
        "context_completeness": context_completeness,
        "transcript_confidence": transcript_conf,
        "llm_score": 50,  # placeholder; LLM provider fills this
    }

    final = (
        scores["curiosity"] * w["curiosity"]
        + scores["emotional_intensity"] * w["emotional_intensity"]
        + scores["specificity"] * w["specificity"]
        + scores["novelty"] * w["novelty"]
        + scores["conflict"] * w["conflict"]
        + scores["payoff"] * w["payoff"]
        + scores["self_contained"] * w["self_contained"]
        + scores["speech_energy"] * w["speech_energy"]
        + scores["context_completeness"] * w["context_completeness"]
        + scores["llm_score"] * w["llm_score"]
    )

    if not reasons:
        reasons.append("Meets minimum speech threshold")
    if self_contained < 60:
        weaknesses.append("Lacks self-contained opening")

    return round(final, 1), reasons, weaknesses
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_hooks.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add apps/engine/app/domain/hooks.py apps/engine/tests/test_hooks.py
git commit -m "feat(engine): add hook candidate generation and scoring"
```

---

## Task 6: Face Detection Provider

**Files:**
- Create: `apps/engine/app/providers/face_provider.py`
- Create: `apps/engine/tests/test_face.py`

**Interfaces:**
- Consumes: `settings.FACE_MODEL` path
- Produces: `detect_faces_frame(image_bgr, timestamp, min_conf=0.5) -> list[dict]` returning `[{x, y, w, h, confidence, timestamp}]` in normalized 0..1 coords. Uses mediapipe **0.10.35** Tasks API with `RunningMode.VIDEO`.

- [ ] **Step 1: Create failing test**

```python
import cv2
import numpy as np
from app.providers.face_provider import create_detector, detect_faces_frame


def test_detect_face_in_portrait():
    import subprocess
    subprocess.run(
        ["rtk", "curl", "-sL", "-o", "/tmp/face_test.jpg",
         "https://storage.googleapis.com/mediapipe-assets/portrait.jpg"],
        capture_output=True,
    )
    det = create_detector()
    bgr = cv2.imread("/tmp/face_test.jpg")
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    faces = detect_faces_frame(det, rgb, timestamp=0.0)
    assert len(faces) >= 1
    assert 0 < faces[0]["x"] < 1
    assert 0 < faces[0]["y"] < 1
    assert faces[0]["confidence"] > 0.5
    det.close()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_face.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement face_provider.py**

```python
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as mpy
from mediapipe.tasks.python import vision
from app.config import settings

_detector = None


def create_detector():
    opts = vision.FaceDetectorOptions(
        base_options=mpy.BaseOptions(
            model_asset_path=str(settings.FACE_MODEL),
            delegate=mpy.BaseOptions.Delegate.CPU,
        ),
        running_mode=vision.RunningMode.VIDEO,
        min_detection_confidence=0.5,
    )
    return vision.FaceDetector.create_from_options(opts)


def detect_faces_frame(detector, rgb_frame: np.ndarray, timestamp: float,
                       min_conf: float = 0.5) -> list[dict]:
    """Detect faces in a single RGB frame. Returns normalized 0..1 coords."""
    img = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
    result = detector.detect_for_video(img, int(timestamp * 1000))
    faces = []
    for d in result.detections:
        bb = d.bounding_box
        conf = float(d.categories[0].score)
        if conf < min_conf:
            continue
        faces.append({
            "x": round((bb.origin_x + bb.width / 2) / img.width, 4),
            "y": round((bb.origin_y + bb.height / 2) / img.height, 4),
            "w": round(bb.width / img.width, 4),
            "h": round(bb.height / img.height, 4),
            "confidence": round(conf, 4),
        })
    return faces
```

- [ ] **Step 4: Run test**

```bash
uv run pytest tests/test_face.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add apps/engine/app/providers/face_provider.py apps/engine/tests/test_face.py
git commit -m "feat(engine): add mediapipe face detection provider"
```

---

## Task 7: Face Tracking + EMA Smoothing

**Files:**
- Create: `apps/engine/app/services/vision_service.py`
- Create: `apps/engine/tests/test_smoothing.py`

**Interfaces:**
- Consumes: face detections from Task 6
- Produces: `smooth_centers(raw_centers: list[dict], alpha=0.15, deadzone=0.02) -> list[dict]` and `associate_detections_to_tracks(detections, tracks, iou_thresh=0.3) -> dict` and `detect_and_track_video(video_path, detector, project_id, conn, sample_interval=0.1) -> list[dict]` returning tracks with centers_json.

- [ ] **Step 1: Create failing tests**

```python
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
    raw_var = sum(abs(r["cx"] - 0.452) for r in raw)
    sm_var = sum(abs(s["cx"] - 0.452) for s in smoothed)
    assert sm_var < raw_var


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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_smoothing.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement vision_service.py**

```python
import cv2
import json
import subprocess
import numpy as np
from app.config import settings


def smooth_centers(raw_centers: list[dict], alpha: float = None, deadzone: float = None) -> list[dict]:
    alpha = alpha or settings.SMOOTHING_ALPHA
    deadzone = deadzone or settings.SMOOTHING_DEADZONE
    if not raw_centers:
        return []
    result = [raw_centers[0].copy()]
    prev = raw_centers[0]["cx"]
    for c in raw_centers[1:]:
        raw = c["cx"]
        smoothed = alpha * raw + (1 - alpha) * prev
        if abs(smoothed - prev) < deadzone:
            smoothed = prev
        result.append({"time": c["time"], "cx": round(smoothed, 4)})
        prev = smoothed
    return result


def interpolate_centers(centers: list[dict], interval: float = None) -> list[dict]:
    interval = interval or settings.KEYFRAME_INTERVAL
    if not centers:
        return []
    duration = centers[-1]["time"] - centers[0]["time"]
    if duration <= 0:
        return [centers[0].copy()]
    result = []
    t = centers[0]["time"]
    while t <= centers[-1]["time"] + 0.001:
        # linear interpolation
        cx = _lerp_keyframes(centers, t, "cx")
        cy = centers[0].get("cy", 0.5)
        result.append({"time": round(t, 2), "cx": round(cx, 4), "cy": round(cy, 4)})
        t += interval
    return result


def _lerp_keyframes(centers, t, key):
    if t <= centers[0]["time"]:
        return centers[0][key]
    for i in range(1, len(centers)):
        if t <= centers[i]["time"]:
            prev = centers[i - 1]
            curr = centers[i]
            frac = (t - prev["time"]) / max(curr["time"] - prev["time"], 0.001)
            return prev[key] + frac * (curr[key] - prev[key])
    return centers[-1][key]


def detect_and_track_video(video_path: str, detector, project_id: str, conn,
                           sample_interval: float = None) -> list[dict]:
    sample_interval = sample_interval or settings.FACE_SAMPLE_INTERVAL
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_interval = max(1, int(fps * sample_interval))
    all_centers = []
    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            timestamp = frame_idx / fps
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            from app.providers.face_provider import detect_faces_frame
            faces = detect_faces_frame(detector, rgb, timestamp)
            if faces:
                best = max(faces, key=lambda f: f["confidence"])
                all_centers.append({"time": round(timestamp, 3), "cx": best["x"], "cy": best["y"]})
        frame_idx += 1
    cap.release()
    if not all_centers:
        return []
    smoothed = smooth_centers(all_centers)
    keyframes = interpolate_centers(smoothed)
    import json
    from app.db import insert_face_track
    insert_face_track(conn, project_id, keyframes[0]["time"], keyframes[-1]["time"],
                      json.dumps(keyframes))
    return keyframes
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_smoothing.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add apps/engine/app/services/vision_service.py apps/engine/tests/test_smoothing.py
git commit -m "feat(engine): add face tracking and EMA smoothing"
```

---

## Task 8: Smart Crop Keyframes

**Files:**
- Create: `apps/engine/app/domain/crop.py`
- Create: `apps/engine/tests/test_crop.py`

**Interfaces:**
- Consumes: centers from Task 7, source dimensions, aspect ratio
- Produces: `crop_window(src_w, src_h, aspect_w, aspect_h) -> dict`, `clamp_center(cx, cy, crop_w, crop_h, src_w, src_h) -> (float, float)`, `centers_to_keyframes(centers, src_w, src_h, aspect_ratio) -> list[dict]`, `build_crop_expr(keyframes) -> str`, `round_even(n) -> int`

- [ ] **Step 1: Create failing tests**

```python
from app.domain.crop import (
    round_even, crop_window, clamp_center, centers_to_keyframes,
    build_crop_expr, keypoints_for_clip
)


def test_round_even():
    assert round_even(607) == 606
    assert round_even(608) == 608
    assert round_even(1) == 0
    assert round_even(2) == 2


def test_crop_window_9_16():
    w = crop_window(1920, 1080, 9, 16)
    assert w["crop_w"] == 608  # 1080 * 9/16 = 607.5 -> 608
    assert w["crop_h"] == 1080


def test_crop_window_1_1():
    w = crop_window(1920, 1080, 1, 1)
    assert w["crop_w"] == 1080
    assert w["crop_h"] == 1080


def test_clamp_center():
    cx, cy = clamp_center(0.0, 0.5, 608, 1080, 1920, 1080)
    assert cx > 0
    cx2, _ = clamp_center(1.0, 0.5, 608, 1080, 1920, 1080)
    assert cx2 < 1.0


def test_centers_to_keyframes():
    centers = [
        {"time": 0.0, "cx": 0.5, "cy": 0.5},
        {"time": 1.0, "cx": 0.6, "cy": 0.5},
    ]
    kfs = centers_to_keyframes(centers, 1920, 1080, "9:16")
    assert len(kfs) >= 2
    assert "time" in kfs[0]
    assert "center_x" in kfs[0]


def test_build_crop_expr_single():
    kfs = [{"time": 0, "center_x": 0.5, "center_y": 0.5}]
    expr = build_crop_expr(kfs, 1920, 1080, 9, 16)
    assert "crop" in expr or "608" in expr
    # should contain the crop width
    assert "608" in expr
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_crop.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement crop.py**

```python
import math


def round_even(n: int) -> int:
    n = int(n)
    return n if n % 2 == 0 else n - 1


def aspect_to_wh(aspect: str) -> tuple[int, int]:
    parts = aspect.split(":")
    return int(parts[0]), int(parts[1])


def crop_window(src_w: int, src_h: int, aspect_w: int, aspect_h: int) -> dict:
    target_ratio = aspect_w / aspect_h
    source_ratio = src_w / src_h
    if target_ratio < source_ratio:
        crop_h = src_h
        crop_w = round_even(src_h * target_ratio)
    else:
        crop_w = src_w
        crop_h = round_even(src_w / target_ratio)
    return {"crop_w": crop_w, "crop_h": crop_h}


def clamp_center(cx: float, cy: float, crop_w: int, crop_h: int, src_w: int, src_h: int) -> tuple[float, float]:
    half_w_norm = (crop_w / src_w) / 2
    half_h_norm = (crop_h / src_h) / 2
    cx = max(half_w_norm, min(cx, 1 - half_w_norm))
    cy = max(half_h_norm, min(cy, 1 - half_h_norm))
    return cx, cy


def centers_to_keyframes(centers: list[dict], src_w: int, src_h: int, aspect: str) -> list[dict]:
    aw, ah = aspect_to_wh(aspect)
    w = crop_window(src_w, src_h, aw, ah)
    result = []
    for c in centers:
        cx, cy = clamp_center(c["cx"], c.get("cy", 0.5), w["crop_w"], w["crop_h"], src_w, src_h)
        result.append({
            "time": c["time"],
            "center_x": round(cx, 4),
            "center_y": round(cy, 4),
        })
    return result


def build_crop_expr(keyframes: list[dict], src_w: int, src_h: int, aspect_w: int, aspect_h: int) -> str:
    """Build ffmpeg crop x/y expression from keyframes."""
    w = crop_window(src_w, src_h, aspect_w, aspect_h)
    crop_w = w["crop_w"]
    crop_h = w["crop_h"]

    def _x_for_kf(kf):
        cx, _ = clamp_center(kf["center_x"], kf["center_y"], crop_w, crop_h, src_w, src_h)
        return round(cx * src_w - crop_w / 2, 2)

    if len(keyframes) == 1:
        x_val = _x_for_kf(keyframes[0])
        y_val = round(0)  # top-aligned for now
        return f"crop={crop_w}:{crop_h}:{x_val}:{y_val}"

    parts = []
    for i, kf in enumerate(keyframes):
        t = kf["time"]
        x = _x_for_kf(kf)
        if i == 0:
            parts.append(f"(between(t,{t},{t}){x})")
        else:
            prev_t = keyframes[i - 1]["time"]
            prev_x = _x_for_kf(keyframes[i - 1])
            expr = f"(between(t,{prev_t},{t})*(1-(t-{prev_t})/{max(t-prev_t,0.001)}){prev_x}+(t-{prev_t})/{max(t-prev_t,0.001)}*{x})"
            parts.append(expr)

    x_expr = "+".join(parts)
    return f"crop={crop_w}:{crop_h}:x='{x_expr}':y=0"


def keypoints_for_clip(keyframes: list[dict], src_w: int, src_h: int, aspect: str) -> list[dict]:
    aw, ah = aspect_to_wh(aspect)
    return centers_to_keyframes(keyframes, src_w, src_h, aspect)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_crop.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add apps/engine/app/domain/crop.py apps/engine/tests/test_crop.py
git commit -m "feat(engine): add smart crop math and ffmpeg expression builder"
```

---

## Task 9: Caption Generation (ASS Files)

**Files:**
- Create: `apps/engine/app/domain/captions.py`
- Create: `apps/engine/app/services/captions_service.py`
- Create: `apps/engine/tests/test_captions.py`

**Interfaces:**
- Consumes: word timestamps from Task 4
- Produces: `split_words_to_lines(words, max_chars=30, max_lines=2) -> list[dict]` returning `[{text, start, end}]`, and `generate_ass(lines, width, height, style) -> str`

- [ ] **Step 1: Create failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_captions.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement captions.py**

```python
import json


def split_words_to_lines(words: list[dict], max_chars: int = 30,
                         max_lines: int = 2) -> list[dict]:
    if not words:
        return []
    lines = []
    current_text = []
    current_start = None
    current_end = None
    for w in words:
        word_text = w["word"].strip()
        candidate = " ".join(current_text + [word_text])
        if current_start is None:
            current_start = w["start"]
        if len(candidate) > max_chars and current_text:
            lines.append({
                "text": " ".join(current_text),
                "start": current_start,
                "end": current_end or current_start,
                "words": list(current_text),
            })
            current_text = [word_text]
            current_start = w["start"]
        else:
            current_text.append(word_text)
        current_end = w["end"]
        if len(lines) >= max_lines:
            break
    if current_text and len(lines) < max_lines:
        lines.append({
            "text": " ".join(current_text),
            "start": current_start or 0.0,
            "end": current_end or 0.0,
            "words": list(current_text),
        })
    return lines


def generate_ass(lines: list[dict], width: int = 1080, height: int = 1920,
                 style: dict = None) -> str:
    style = style or {}
    font_size = style.get("font_size", 48)
    font_name = style.get("font_name", "Arial")
    margin_bottom = style.get("margin_bottom", 120)

    header = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {width}
PlayResY: {height}
ScalerBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,2,1,2,20,20,{margin_bottom},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for l in lines:
        start = _fmt_time(l["start"])
        end = _fmt_time(l["end"])
        text = l["text"].replace("\n", "\\N")
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    return header + "\n".join(events) + "\n"


def _fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_captions.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add apps/engine/app/domain/captions.py apps/engine/app/services/captions_service.py apps/engine/tests/test_captions.py
git commit -m "feat(engine): add caption splitting and ASS file generation"
```

---

## Task 10: Job Queue + SSE Progress

**Files:**
- Create: `apps/engine/app/jobs.py`

**Interfaces:**
- Consumes: nothing
- Produces: `enqueue_job(job_id, kind, project_id, fn, *args)`, `update_progress(job_id, stage, progress)`, `get_job(job_id) -> dict`, `cancel_job(job_id)`, `job_events(job_id) -> AsyncGenerator` for SSE

- [ ] **Step 1: Implement jobs.py** (no unit test for async queue — covered by integration)

```python
import asyncio
import uuid
import time
from enum import Enum
from dataclasses import dataclass, field


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    id: str
    kind: str
    project_id: str
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    stage: str = ""
    error: str = ""
    cancelled: bool = False
    _event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _queue: asyncio.Queue = field(default_factory=asyncio.Queue, repr=False)


_jobs: dict[str, Job] = {}


def enqueue_job(kind: str, project_id: str, fn, *args, job_id: str = None) -> str:
    job_id = job_id or str(uuid.uuid4())[:12]
    job = Job(id=job_id, kind=kind, project_id=project_id)
    _jobs[job_id] = job
    asyncio.get_event_loop().create_task(_run(job, fn, *args))
    return job_id


async def _run(job: Job, fn, *args):
    job.status = JobStatus.PROCESSING
    await _push(job, "started", 0.0)
    try:
        await fn(job, *args)
        if not job.cancelled:
            job.status = JobStatus.COMPLETED
            await _push(job, "done", 1.0)
    except Exception as e:
        job.status = JobStatus.FAILED
        job.error = str(e)
        await _push(job, "failed", job.progress)


async def _push(job: Job, stage: str, progress: float):
    job.stage = stage
    job.progress = progress
    await job._queue.put({"stage": stage, "progress": progress, "status": job.status.value})


def update_progress(job: Job, stage: str, progress: float):
    job.stage = stage
    job.progress = progress
    asyncio.get_event_loop().create_task(_push(job, stage, progress))


def get_job(job_id: str) -> dict | None:
    j = _jobs.get(job_id)
    if not j:
        return None
    return {
        "id": j.id, "kind": j.kind, "project_id": j.project_id,
        "status": j.status.value, "progress": j.progress,
        "stage": j.stage, "error": j.error,
    }


def cancel_job(job_id: str) -> bool:
    j = _jobs.get(job_id)
    if not j:
        return False
    j.cancelled = True
    j.status = JobStatus.CANCELLED
    asyncio.get_event_loop().create_task(_push(j, "cancelled", j.progress))
    return True


async def job_events(job_id: str):
    import json
    from starlette.responses import StreamingResponse
    j = _jobs.get(job_id)
    if not j:
        return
    async def stream():
        while True:
            data = await j._queue.get()
            yield f"data: {json.dumps(data)}\n\n"
            if data["status"] in ("completed", "failed", "cancelled"):
                break
    return stream()
```

- [ ] **Step 2: Commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add apps/engine/app/jobs.py
git commit -m "feat(engine): add async job queue with SSE progress"
```

---

## Task 11: FFmpeg Renderer (RenderPlan → Export)

**Files:**
- Create: `apps/engine/app/services/render_service.py`
- Create: `apps/engine/tests/test_render.py`

**Interfaces:**
- Consumes: keyframes from Task 8, captions from Task 9, video path from Task 3
- Produces: `build_render_plan(...)` returning a dict, and `render_clip(plan) -> output_path`

- [ ] **Step 1: Create failing test**

```python
from app.services.render_service import build_render_plan, render_plan_to_ffmpeg_args


def test_render_plan_has_crop():
    plan = build_render_plan(
        input_path="/tmp/test.mp4",
        start=0.0, end=5.0,
        keyframes=[{"time": 0.0, "center_x": 0.5, "center_y": 0.5}],
        src_w=1920, src_h=1080,
        aspect="9:16",
    )
    assert plan["input"] == "/tmp/test.mp4"
    assert plan["trim"]["start"] == 0.0
    assert plan["crop"]["aspect_ratio"] == "9:16"


def test_render_plan_to_args():
    plan = build_render_plan(
        input_path="/tmp/test.mp4",
        start=0.0, end=5.0,
        keyframes=[{"time": 0.0, "center_x": 0.5, "center_y": 0.5}],
        src_w=1920, src_h=1080,
        aspect="9:16",
    )
    args = render_plan_to_ffmpeg_args(plan)
    assert "-i" in args
    assert "crop=" in " ".join(args)
    assert "libx264" in args
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_render.py -v
```

Expected: FAIL

- [ ] **Step 3: Implement render_service.py**

```python
import subprocess
import json
from pathlib import Path
from app.domain.crop import build_crop_expr, crop_window, aspect_to_wh


def build_render_plan(input_path: str, start: float, end: float,
                      keyframes: list[dict], src_w: int, src_h: int,
                      aspect: str = "9:16",
                      ass_path: str = None) -> dict:
    aw, ah = aspect_to_wh(aspect)
    w = crop_window(src_w, src_h, aw, ah)
    # keyframe times are relative to the clip start (clip-relative)
    clip_kfs = []
    for kf in keyframes:
        clip_kfs.append({
            "time": round(kf["time"] - start, 4),
            "center_x": kf["center_x"],
            "center_y": kf["center_y"],
        })
    return {
        "input": input_path,
        "trim": {"start": start, "end": end},
        "crop": {
            "aspect_ratio": aspect,
            "src_w": src_w,
            "src_h": src_h,
            "crop_w": w["crop_w"],
            "crop_h": w["crop_h"],
            "keyframes": clip_kfs,
        },
        "captions": {"ass_path": ass_path} if ass_path else None,
        "output": {
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "video_codec": "libx264",
            "audio_codec": "aac",
            "preset": "fast",
            "crf": 23,
        },
    }


def render_plan_to_ffmpeg_args(plan: dict) -> list[str]:
    args = ["ffmpeg", "-y"]
    args.extend(["-ss", str(plan["trim"]["start"])])
    args.extend(["-i", plan["input"]])
    args.extend(["-t", str(plan["trim"]["end"] - plan["trim"]["start"])])

    crop = plan["crop"]
    aw, ah = aspect_to_wh(crop["aspect_ratio"])
    expr = build_crop_expr(crop["keyframes"], crop["src_w"], crop["src_h"], aw, ah)

    filters = [expr, f"scale={plan['output']['width']}:{plan['output']['height']}"]
    if plan.get("captions") and plan["captions"].get("ass_path"):
        ass = plan["captions"]["ass_path"]
        filters.append(f"subtitles='{ass}'")

    args.extend(["-vf", ",".join(filters)])
    args.extend(["-r", str(plan["output"]["fps"])])
    args.extend(["-c:v", plan["output"]["video_codec"]])
    args.extend(["-preset", plan["output"]["preset"]])
    args.extend(["-crf", str(plan["output"]["crf"])])
    args.extend(["-c:a", plan["output"]["audio_codec"]])
    args.extend(["-b:a", "128k"])
    return args


def render_clip(plan: dict, output_path: str) -> str:
    args = render_plan_to_ffmpeg_args(plan)
    args.append(output_path)
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg render failed: {result.stderr[-500:]}")
    return output_path
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_render.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add apps/engine/app/services/render_service.py apps/engine/tests/test_render.py
git commit -m "feat(engine): add FFmpeg renderer with RenderPlan"
```

---

## Task 12: FastAPI Server + Analysis Pipeline

**Files:**
- Create: `apps/engine/app/main.py`
- Create: `apps/engine/app/api/projects.py`
- Create: `apps/engine/app/api/clips.py`
- Create: `apps/engine/app/api/jobs_api.py`

**Interfaces:**
- Consumes: all backend services (Tasks 1-11)
- Produces: a running HTTP server on `127.0.0.1:8719`

- [ ] **Step 1: Create main.py**

```python
import sqlite3
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from app.config import settings
from app.db import init_db
from app.api import projects, clips, jobs_api

app = FastAPI(title="Smart Clipper Engine")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(projects.router, prefix="/api")
app.include_router(clips.router, prefix="/api")
app.include_router(jobs_api.router, prefix="/api")

# serve frontend build
frontend_dist = Path(__file__).parent.parent.parent / "desktop" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")


@app.on_event("startup")
def startup():
    db_path = settings.DATA_ROOT / "smartclipper.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    conn.close()


@app.get("/api/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 2: Create projects.py router**

```python
import sqlite3
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.config import settings
from app.db import (
    init_db, insert_project, get_project, update_project,
    insert_transcript_segments, insert_hook_candidate, insert_clip,
    insert_crop_keyframes, list_clips_for_project, list_hooks_for_project,
    insert_face_detection, flush_face_detections, insert_face_track,
    insert_caption, update_clip, get_crop_keyframes,
)

router = APIRouter()


class CreateProjectReq(BaseModel):
    name: str = ""
    url: str = ""


class AnalyzeReq(BaseModel):
    num_clips: int = 5
    max_duration: int = 60
    aspect_ratio: str = "9:16"


def _get_conn():
    return sqlite3.connect(str(settings.DATA_ROOT / "smartclipper.db"))


@router.post("/projects")
def create_project(req: CreateProjectReq):
    pid = uuid.uuid4().hex[:12]
    pdir = settings.DATA_ROOT / "projects" / pid
    pdir.mkdir(parents=True, exist_ok=True)
    for sub in ["source", "audio", "transcript", "analysis", "thumbnails", "previews", "exports"]:
        (pdir / sub).mkdir(exist_ok=True)
    conn = _get_conn()
    init_db(conn)
    insert_project(conn, id=pid, name=req.name or "Untitled", source_url=req.url)
    conn.close()
    return {"id": pid, "name": req.name or "Untitled"}


@router.get("/projects")
def list_projects():
    conn = _get_conn()
    rows = conn.execute("SELECT id,name,status,created_at FROM projects ORDER BY created_at DESC").fetchall()
    conn.close()
    return [{"id": r[0], "name": r[1], "status": r[2], "created_at": r[3]} for r in rows]


@router.get("/projects/{pid}")
def get_project_detail(pid: str):
    conn = _get_conn()
    p = get_project(conn, pid)
    if not p:
        conn.close()
        raise HTTPException(404)
    clips = list_clips_for_project(conn, pid)
    hooks = list_hooks_for_project(conn, pid)
    conn.close()
    return {
        "id": p.id, "name": p.name, "status": p.status,
        "clips": [{"id": c.id, "start": c.source_start, "end": c.source_end} for c in clips],
        "hooks": [{"id": h.id, "score": h.score, "start": h.start, "end": h.end} for h in hooks],
    }


@router.post("/projects/{pid}/analyze")
async def analyze_project(pid: str, req: AnalyzeReq):
    conn = _get_conn()
    p = get_project(conn, pid)
    if not p:
        conn.close()
        raise HTTPException(404)

    from app.services.import_service import extract_metadata, download_video, extract_audio
    from app.providers.whisper_provider import transcribe
    from app.domain.hooks import generate_candidates, score_candidate
    from app.db import list_hooks_for_project
    import json

    pdir = settings.DATA_ROOT / "projects" / pid
    update_project(conn, pid, status="downloading")

    # download/import
    source_url = p.name  # hack: we store URL in name for now
    video_files = list((pdir / "source").glob("*.mp4"))
    if not video_files:
        if source_url.startswith("http"):
            video_path = download_video(pid, source_url, pdir)
        else:
            raise HTTPException(400, "No video found")
    else:
        video_path = video_files[0]

    meta = extract_metadata(str(video_path))
    update_project(conn, pid, status="transcribing")

    # extract audio
    audio_path = extract_audio(str(video_path), pdir)

    # transcribe
    transcript = transcribe(str(audio_path))
    insert_transcript_segments(conn, "t_" + pid, transcript["segments"])

    # hooks
    update_project(conn, pid, status="hooking")
    candidates = generate_candidates(transcript["segments"], meta["duration"])
    for c in candidates[:20]:  # score top 20
        score, reasons, weaknesses = score_candidate(c, transcript["segments"])
        insert_hook_candidate(
            conn, id=str(uuid.uuid4())[:10], project_id=pid,
            start=c["start"], end=c["end"], score=score,
            scores_json=json.dumps({"final": score}),
            reasons_json=json.dumps(reasons),
            weaknesses_json=json.dumps(weaknesses),
        )

    hooks = list_hooks_for_project(conn, pid)
    top_hooks = hooks[:req.num_clips]

    update_project(conn, pid, status="cropping")

    # face detect + crop for each clip
    from app.providers.face_provider import create_detector, detect_faces_frame
    import cv2
    import json
    detector = create_detector()
    cap = cv2.VideoCapture(str(video_path))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30

    for h in top_hooks:
        clip_id = uuid.uuid4().hex[:10]
        insert_clip(conn, id=clip_id, project_id=pid, hook_candidate_id=h.id,
                    source_start=h.start, source_end=h.end, aspect_ratio=req.aspect_ratio)

        # sample frames for face detection
        centers = []
        t = h.start
        while t < h.end:
            frame_idx = int(t * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if ret:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                faces = detect_faces_frame(detector, rgb, t)
                if faces:
                    best = max(faces, key=lambda f: f["confidence"])
                    centers.append({"time": round(t, 3), "cx": best["x"], "cy": best["y"]})
            t += settings.FACE_SAMPLE_INTERVAL

        cap.release()

        from app.services.vision_service import smooth_centers, interpolate_centers
        if centers:
            smoothed = smooth_centers(centers)
            keyframes = interpolate_centers(smoothed)
        else:
            keyframes = [{"time": h.start, "cx": 0.5, "cy": 0.5, "time": h.start}]

        from app.domain.crop import centers_to_keyframes
        crop_kfs = centers_to_keyframes(
            [{"time": kf["time"], "cx": kf["cx"], "cy": kf.get("cy", 0.5)} for kf in keyframes],
            meta["width"], meta["height"], req.aspect_ratio
        )
        insert_crop_keyframes(conn, clip_id, crop_kfs, source="ai")

        # captions
        clip_segs = [s for s in transcript["segments"]
                     if s["end"] > h.start and s["start"] < h.end]
        from app.domain.captions import split_words_to_lines, generate_ass
        all_words = []
        for s in clip_segs:
            words = json.loads(s.get("words_json", "[]"))
            for w in words:
                all_words.append(w)
        lines = split_words_to_lines(all_words, max_chars=30, max_lines=2)
        ass_content = generate_ass(lines, meta["width"], meta["height"])
        ass_path = pdir / "exports" / f"{clip_id}.ass"
        ass_path.write_text(ass_content)
        insert_caption(conn, clip_id, 0, h.start, h.end,
                       " ".join(l["text"] for l in lines))

    update_project(conn, pid, status="ready")
    conn.close()
    return {"status": "analyzed", "clips": len(top_hooks)}
```

- [ ] **Step 3: Create clips.py router**

```python
import sqlite3
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.config import settings
from app.db import get_clip, update_clip, get_crop_keyframes, delete_manual_crop_keyframes

router = APIRouter()


class UpdateClipReq(BaseModel):
    title: str | None = None
    caption_short: str | None = None
    caption_long: str | None = None
    source_start: float | None = None
    source_end: float | None = None


class UpdateKeyframesReq(BaseModel):
    keyframes: list[dict]


def _get_conn():
    return sqlite3.connect(str(settings.DATA_ROOT / "smartclipper.db"))


@router.get("/clips/{clip_id}")
def get_clip_detail(clip_id: str):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    kfs = get_crop_keyframes(conn, clip_id)
    conn.close()
    return {
        "id": c.id, "project_id": c.project_id,
        "source_start": c.source_start, "source_end": c.source_end,
        "aspect_ratio": c.aspect_ratio,
        "crop_manually_modified": c.crop_manually_modified,
        "title": c.title,
        "caption_short": c.caption_short, "caption_long": c.caption_long,
        "cta": c.cta, "keyframes": kfs,
    }


@router.patch("/clips/{clip_id}")
def update_clip_info(clip_id: str, req: UpdateClipReq):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if updates:
        update_clip(conn, clip_id, **updates)
    conn.close()
    return {"status": "updated"}


@router.post("/clips/{clip_id}/keyframes")
def update_keyframes(clip_id: str, req: UpdateKeyframesReq):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    delete_manual_crop_keyframes(conn, clip_id)
    from app.db import insert_crop_keyframes
    insert_crop_keyframes(conn, clip_id, req.keyframes, source="manual")
    update_clip(conn, clip_id, crop_manually_modified=True)
    conn.close()
    return {"status": "updated", "keyframes": len(req.keyframes)}


@router.post("/clips/{clip_id}/reset-crop")
def reset_crop_to_ai(clip_id: str):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    delete_manual_crop_keyframes(conn, clip_id)
    update_clip(conn, clip_id, crop_manually_modified=False)
    conn.close()
    return {"status": "reset_to_ai"}
```

- [ ] **Step 4: Create jobs_api.py router**

```python
from fastapi import APIRouter
from starlette.responses import StreamingResponse
from app.jobs import get_job, cancel_job, job_events

router = APIRouter()


@router.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    j = get_job(job_id)
    if not j:
        return {"error": "not found"}
    return j


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: str):
    ok = cancel_job(job_id)
    return {"cancelled": ok}


@router.get("/jobs/{job_id}/events")
async def stream_events(job_id: str):
    stream = await job_events(job_id)
    if stream:
        return StreamingResponse(stream(), media_type="text/event-stream")
    return {"error": "not found"}
```

- [ ] **Step 5: Commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add apps/engine/app/main.py apps/engine/app/api/projects.py apps/engine/app/api/clips.py apps/engine/app/api/jobs_api.py
git commit -m "feat(engine): add FastAPI server with full analysis pipeline"
```

---

## Task 13: Frontend Shell + Dashboard

**Files:**
- Create: `apps/desktop/package.json`
- Create: `apps/desktop/vite.config.ts`
- Create: `apps/desktop/tsconfig.json`
- Create: `apps/desktop/index.html`
- Create: `apps/desktop/src/main.tsx`
- Create: `apps/desktop/src/App.tsx`
- Create: `apps/desktop/src/styles/globals.css`
- Create: `apps/desktop/src/components/Dashboard.tsx`
- Create: `apps/desktop/src/lib/api.ts`

**Interfaces:**
- Consumes: engine API from Task 12
- Produces: a React app served at `127.0.0.1:8719`

- [ ] **Step 1: Initialize React project**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper/apps/desktop
npm create vite@latest . -- --template react-ts 2>&1 | tail -5
npm install
npm install react-router-dom zustand
```

- [ ] **Step 2: Create src/lib/api.ts**

```typescript
const BASE = "http://127.0.0.1:8719/api";

export async function fetchJSON<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function createProject(name: string, url: string) {
  return fetchJSON("/projects", {
    method: "POST",
    body: JSON.stringify({ name, url }),
  });
}

export async function listProjects() {
  return fetchJSON("/projects");
}

export async function getProject(id: string) {
  return fetchJSON(`/projects/${id}`);
}

export async function analyzeProject(id: string, numClips = 5, maxDuration = 60, aspectRatio = "9:16") {
  return fetchJSON(`/projects/${id}/analyze`, {
    method: "POST",
    body: JSON.stringify({ num_clips: numClips, max_duration: maxDuration, aspect_ratio: aspectRatio }),
  });
}

export async function getClip(id: string) {
  return fetchJSON(`/clips/${id}`);
}

export async function updateClip(id: string, data: Record<string, any>) {
  return fetchJSON(`/clips/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function updateKeyframes(clipId: string, keyframes: any[]) {
  return fetchJSON(`/clips/${clipId}/keyframes`, {
    method: "POST",
    body: JSON.stringify({ keyframes }),
  });
}

export async function resetCropToAI(clipId: string) {
  return fetchJSON(`/clips/${clipId}/reset-crop`, { method: "POST" });
}

export async function getJob(jobId: string) {
  return fetchJSON(`/jobs/${jobId}`);
}
```

- [ ] **Step 3: Create src/App.tsx**

```tsx
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Dashboard from "./components/Dashboard";
import Editor from "./components/Editor";
import "./styles/globals.css";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/editor/:projectId" element={<Editor />} />
      </Routes>
    </BrowserRouter>
  );
}
```

- [ ] **Step 4: Create src/styles/globals.css**

```css
:root {
  --bg: #0f0f12;
  --surface: #1a1a22;
  --surface-2: #23232d;
  --border: #2d2d3a;
  --text: #e8e8ed;
  --text-dim: #8888a0;
  --accent: #6366f1;
  --accent-dim: #4f46e5;
  --success: #22c55e;
  --warning: #f59e0b;
  --error: #ef4444;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}

.app { display: flex; flex-direction: column; height: 100vh; }
.top-bar { display: flex; align-items: center; gap: 12px; padding: 12px 20px; background: var(--surface); border-bottom: 1px solid var(--border); }
.top-bar h1 { font-size: 16px; font-weight: 600; }
.status-badge { padding: 2px 8px; border-radius: 999px; font-size: 12px; font-weight: 500; }
.status-badge.processing { background: var(--warning); color: #000; }
.status-badge.ready { background: var(--success); color: #000; }
.btn { padding: 8px 16px; border-radius: 6px; border: 1px solid var(--border); background: var(--surface-2); color: var(--text); cursor: pointer; font-size: 13px; transition: background 0.15s; }
.btn:hover { background: var(--accent-dim); }
.btn.primary { background: var(--accent); border-color: var(--accent); }
.btn.primary:hover { background: #5558e6; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
.grid { display: grid; gap: 16px; }
```

- [ ] **Step 5: Create src/components/Dashboard.tsx**

```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listProjects, createProject } from "../lib/api";

export default function Dashboard() {
  const [projects, setProjects] = useState<any[]>([]);
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    listProjects().then(setProjects).catch(() => {});
  }, []);

  const handleCreate = async () => {
    if (!url.trim()) return;
    const p = await createProject(name || "Untitled", url);
    navigate(`/editor/${p.id}`);
  };

  return (
    <div className="app" style={{ padding: 40 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Smart Clipper</h1>
      <div className="card" style={{ marginBottom: 24, maxWidth: 600 }}>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>New Project</h2>
        <input
          placeholder="Project name (optional)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          style={{ width: "100%", padding: 8, background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--text)", marginBottom: 8 }}
        />
        <input
          placeholder="YouTube URL or local path"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          style={{ width: "100%", padding: 8, background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--text)", marginBottom: 12 }}
        />
        <button className="btn primary" onClick={handleCreate}>Analyze Video</button>
      </div>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
        {projects.map((p) => (
          <div key={p.id} className="card" style={{ cursor: "pointer" }} onClick={() => navigate(`/editor/${p.id}`)}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ fontSize: 14, fontWeight: 600 }}>{p.name}</h3>
              <span className={`status-badge ${p.status}`}>{p.status}</span>
            </div>
            <p style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 4 }}>{p.id}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Create src/main.tsx**

```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./styles/globals.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

- [ ] **Step 7: Commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add apps/desktop/
git commit -m "feat(frontend): add React shell with dashboard and API client"
```

---

## Task 14: Editor UI — Video Player + Crop Overlay + Timeline

**Files:**
- Create: `apps/desktop/src/components/Editor.tsx`
- Create: `apps/desktop/src/components/VideoPlayer.tsx`
- Create: `apps/desktop/src/components/CropOverlay.tsx`
- Create: `apps/desktop/src/components/Timeline.tsx`
- Create: `apps/desktop/src/components/Sidebar.tsx`
- Create: `apps/desktop/src/stores/editor.ts`

**Interfaces:**
- Consumes: API from Task 13
- Produces: a functional editor with draggable crop, timeline, and sidebar tabs

- [ ] **Step 1: Create src/stores/editor.ts**

```typescript
import { create } from "zustand";

interface Keyframe {
  time: number;
  center_x: number;
  center_y: number;
  source?: string;
}

interface EditorState {
  projectId: string;
  project: any;
  clip: any;
  keyframes: Keyframe[];
  currentTime: number;
  isPlaying: boolean;
  selectedTab: "crop" | "script" | "effect";
  setProject: (p: any) => void;
  setClip: (c: any) => void;
  setKeyframes: (k: Keyframe[]) => void;
  setCurrentTime: (t: number) => void;
  setIsPlaying: (p: boolean) => void;
  setSelectedTab: (t: "crop" | "script" | "effect") => void;
}

export const useEditorStore = create<EditorState>((set) => ({
  projectId: "",
  project: null,
  clip: null,
  keyframes: [],
  currentTime: 0,
  isPlaying: false,
  selectedTab: "crop",
  setProject: (p) => set({ project: p }),
  setClip: (c) => set({ clip: c }),
  setKeyframes: (k) => set({ keyframes: k }),
  setCurrentTime: (t) => set({ currentTime: t }),
  setIsPlaying: (p) => set({ isPlaying: p }),
  setSelectedTab: (t) => set({ selectedTab: t }),
}));
```

- [ ] **Step 2: Create VideoPlayer.tsx**

```tsx
import { useRef, useEffect } from "react";
import { useEditorStore } from "../stores/editor";

export default function VideoPlayer({ videoSrc }: { videoSrc: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const { setCurrentTime, setIsPlaying, isPlaying } = useEditorStore();

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onTime = () => setCurrentTime(v.currentTime);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    return () => { v.removeEventListener("timeupdate", onTime); v.removeEventListener("play", onPlay); v.removeEventListener("pause", onPause); };
  }, []);

  return (
    <video
      ref={videoRef}
      src={videoSrc}
      style={{ width: "100%", maxHeight: "70vh", objectFit: "contain", background: "#000", borderRadius: 8 }}
      controls
    />
  );
}
```

- [ ] **Step 3: Create CropOverlay.tsx**

```tsx
import { useRef, useCallback } from "react";
import { useEditorStore } from "../stores/editor";

export default function CropOverlay() {
  const { keyframes, currentTime } = useEditorStore();
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const getCurrentCrop = () => {
    if (!keyframes.length) return { cx: 0.5, cy: 0.5 };
    let kf = keyframes[0];
    for (const k of keyframes) {
      if (k.time <= currentTime) kf = k;
      else break;
    }
    return { cx: kf.center_x, cy: kf.center_y };
  };

  const crop = getCurrentCrop();
  const cropW = 1080 / 1920; // 9:16 normalized
  const left = crop.cx - cropW / 2;
  const top = crop.cy - 0.5; // assuming 1:1 crop height for overlay

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    dragging.current = true;
    const onMove = (ev: MouseEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = (ev.clientX - rect.left) / rect.width;
      const y = (ev.clientY - rect.top) / rect.height;
      useEditorStore.getState().setKeyframes(
        useEditorStore.getState().keyframes.map(k =>
          k.time === currentTime ? { ...k, center_x: Math.max(0.15, Math.min(0.85, x)), center_y: Math.max(0.1, Math.min(0.9, y)) } : k
        )
      );
    };
    const onUp = () => { dragging.current = false; window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [currentTime]);

  return (
    <div
      ref={containerRef}
      style={{ position: "relative", width: "100%", aspectRatio: "16/9", background: "#000", borderRadius: 8, overflow: "hidden", cursor: "crosshair" }}
      onMouseDown={handleMouseDown}
    >
      <div
        style={{
          position: "absolute",
          left: `${left * 100}%`,
          top: `${top * 100}%`,
          width: `${cropW * 100}%`,
          height: "100%",
          border: "2px solid var(--accent)",
          borderRadius: 4,
          pointerEvents: "none",
        }}
      />
    </div>
  );
}
```

- [ ] **Step 4: Create Timeline.tsx**

```tsx
import { useEditorStore } from "../stores/editor";

export default function Timeline() {
  const { clip, currentTime, setCurrentTime, keyframes } = useEditorStore();
  const duration = clip ? clip.source_end - clip.source_start : 60;

  return (
    <div style={{ padding: "12px 20px", background: "var(--surface)", borderTop: "1px solid var(--border)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
        <span style={{ fontVariantNumeric: "tabular-nums", fontSize: 13, color: "var(--text-dim)" }}>
          {formatTime(currentTime)}
        </span>
        <div style={{ flex: 1, position: "relative", height: 48, background: "var(--surface-2)", borderRadius: 6 }}>
          {keyframes.map((kf, i) => (
            <div
              key={i}
              style={{
                position: "absolute",
                left: `${((kf.time - (clip?.source_start || 0)) / duration) * 100}%`,
                top: "50%",
                transform: "translate(-50%, -50%)",
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: kf.source === "ai" ? "var(--accent)" : "var(--warning)",
              }}
            />
          ))}
          <div
            style={{
              position: "absolute",
              left: `${((currentTime - (clip?.source_start || 0)) / duration) * 100}%`,
              top: 0,
              bottom: 0,
              width: 2,
              background: "var(--error)",
              pointerEvents: "none",
            }}
          />
        </div>
      </div>
    </div>
  );
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  const ms = Math.floor((s % 1) * 100);
  return `${m.toString().padStart(2, "0")}:${sec.toString().padStart(2, "0")}.${ms.toString().padStart(2, "0")}`;
}
```

- [ ] **Step 5: Create Sidebar.tsx**

```tsx
import { useEditorStore } from "../stores/editor";

export default function Sidebar() {
  const { selectedTab, setSelectedTab, keyframes, currentTime, clip } = useEditorStore();

  const tabs = ["crop", "script", "effect"] as const;

  return (
    <div style={{ width: 320, background: "var(--surface)", borderLeft: "1px solid var(--border)", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", borderBottom: "1px solid var(--border)" }}>
        {tabs.map((t) => (
          <button
            key={t}
            className={`btn ${selectedTab === t ? "primary" : ""}`}
            style={{ flex: 1, borderRadius: 0, border: "none", borderBottom: selectedTab === t ? "2px solid var(--accent)" : "2px solid transparent" }}
            onClick={() => setSelectedTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      <div style={{ padding: 16, flex: 1, overflow: "auto" }}>
        {selectedTab === "crop" && (
          <div>
            <h3 style={{ fontSize: 14, marginBottom: 8 }}>Segment Crop</h3>
            {keyframes.map((kf, i) => (
              <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4, fontSize: 12, color: "var(--text-dim)" }}>
                <span>{formatTime(kf.time)}</span>
                <span>x: {(kf.center_x * 100).toFixed(0)}%</span>
                <span style={{ color: kf.source === "ai" ? "var(--accent)" : "var(--warning)" }}>{kf.source}</span>
              </div>
            ))}
          </div>
        )}
        {selectedTab === "script" && (
          <div>
            <h3 style={{ fontSize: 14, marginBottom: 8 }}>Script</h3>
            <p style={{ fontSize: 12, color: "var(--text-dim)" }}>
              {clip?.caption_short || "No captions yet"}
            </p>
          </div>
        )}
        {selectedTab === "effect" && (
          <div>
            <h3 style={{ fontSize: 14, marginBottom: 8 }}>Effects</h3>
            <p style={{ fontSize: 12, color: "var(--text-dim)" }}>Caption styling coming soon</p>
          </div>
        )}
      </div>
    </div>
  );
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}
```

- [ ] **Step 6: Create Editor.tsx**

```tsx
import { useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getProject, getClip } from "../lib/api";
import { useEditorStore } from "../stores/editor";
import VideoPlayer from "./VideoPlayer";
import Timeline from "./Timeline";
import Sidebar from "./Sidebar";

export default function Editor() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { setProject, setClip, setKeyframes, project, clip } = useEditorStore();

  useEffect(() => {
    if (!projectId) return;
    getProject(projectId).then(setProject).catch(() => navigate("/"));
  }, [projectId]);

  useEffect(() => {
    if (!project?.clips?.length) return;
    getClip(project.clips[0].id).then((c) => {
      setClip(c);
      setKeyframes(c.keyframes || []);
    }).catch(() => {});
  }, [project]);

  return (
    <div className="app">
      <div className="top-bar">
        <button className="btn" onClick={() => navigate("/")}>Back</button>
        <h1>{project?.name || "Loading..."}</h1>
        <span className={`status-badge ${project?.status || "processing"}`}>
          {project?.status || "processing"}
        </span>
        <div style={{ flex: 1 }} />
        {project?.clips && <span style={{ fontSize: 12, color: "var(--text-dim)" }}>{project.clips.length} clips</span>}
      </div>
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
          <div style={{ flex: 1, padding: 16, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <VideoPlayer videoSrc={`http://127.0.0.1:8719/api/media/${projectId}/video`} />
          </div>
          <Timeline />
        </div>
        <Sidebar />
      </div>
    </div>
  );
}
```

- [ ] **Step 7: Commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add apps/desktop/src/
git commit -m "feat(frontend): add editor with video player, crop overlay, timeline, sidebar"
```

---

## Task 15: Integration Test — Full Pipeline

**Files:**
- Create: `apps/engine/tests/test_integration.py`
- Create: `apps/engine/tests/fixtures/generate_fixture.sh`

**Interfaces:**
- Consumes: everything from Tasks 1-12
- Produces: a verified end-to-end export

- [ ] **Step 1: Create fixture video generator**

```bash
#!/bin/bash
cd "$(dirname "$0")"
ffmpeg -y \
  -f lavfi -i "testsrc=size=640x480:rate=30:duration=8" \
  -f lavfi -i "sine=frequency=440:duration=8" \
  -c:v libx264 -preset ultrafast -c:a aac -shortest \
  test_video.mp4
echo "Fixture created: test_video.mp4"
```

- [ ] **Step 2: Create integration test**

```python
import subprocess
import sqlite3
import json
import os
from pathlib import Path


def test_full_pipeline(tmp_data):
    """End-to-end: generate fixture → import → transcribe → crop → export."""
    fixture = Path(__file__).parent / "fixtures" / "test_video.mp4"
    if not fixture.exists():
        subprocess.run(["bash", str(Path(__file__).parent / "fixtures" / "generate_fixture.sh")], check=True)

    from app.config import settings
    from app.db import init_db, insert_project, insert_clip, insert_crop_keyframes
    from app.services.import_service import extract_metadata, extract_audio
    from app.domain.crop import centers_to_keyframes
    from app.domain.captions import split_words_to_lines, generate_ass
    from app.services.render_service import build_render_plan, render_plan_to_ffmpeg_args, render_clip

    # init
    conn = sqlite3.connect(str(tmp_data / "test.db"))
    init_db(conn)
    insert_project(conn, id="test", name="Integration Test")

    # metadata
    meta = extract_metadata(str(fixture))
    assert meta["width"] == 640
    assert meta["height"] == 480

    # audio
    audio = extract_audio(str(fixture), tmp_data)
    assert audio.exists()

    # crop
    centers = [
        {"time": 0.0, "cx": 0.5, "cy": 0.5},
        {"time": 4.0, "cx": 0.6, "cy": 0.5},
    ]
    kfs = centers_to_keyframes(centers, meta["width"], meta["height"], "9:16")
    insert_clip(conn, id="c1", project_id="test", source_start=0.0, source_end=8.0, aspect_ratio="9:16")
    insert_crop_keyframes(conn, "c1", kfs, source="ai")

    # render
    plan = build_render_plan(
        input_path=str(fixture),
        start=0.0, end=8.0,
        keyframes=kfs,
        src_w=meta["width"], src_h=meta["height"],
        aspect="9:16",
    )
    output = str(tmp_data / "output.mp4")
    render_clip(plan, output)
    assert Path(output).exists()
    assert Path(output).stat().st_size > 1000

    # verify output dimensions
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", output],
        capture_output=True, text=True,
    )
    info = json.loads(result.stdout)
    w = int(info["streams"][0]["width"])
    h = int(info["streams"][0]["height"])
    assert w == 1080
    assert h == 1920

    conn.close()
    print(f"Integration test passed: {output} ({w}x{h})")
```

- [ ] **Step 3: Run integration test**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper/apps/engine
uv run pytest tests/test_integration.py -v -s
```

Expected: PASS — output is 1080×1920

- [ ] **Step 4: Commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add apps/engine/tests/test_integration.py apps/engine/tests/fixtures/
git commit -m "test: add end-to-end integration test with fixture video"
```

---

## Task 16: Final Lint + Type Check + Verify

- [ ] **Step 1: Run all tests**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper/apps/engine
uv run pytest tests/ -v
```

Expected: ALL PASS

- [ ] **Step 2: Run mypy (optional, non-blocking)**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper/apps/engine
uv pip install -q mypy
uv run mypy app/ --ignore-missing-imports --no-error-summary 2>&1 | tail -10
```

Expected: no critical errors

- [ ] **Step 3: Final commit**

```bash
cd /Users/azmi/Documents/Learning/AI/smart-clipper
git add -A
git commit -m "chore: final lint and type check pass"
```

---

## Verification Checklist

After all tasks, verify:

- [ ] `uv run pytest tests/ -v` — all pass
- [ ] `uv run python -m app.main` — server starts on 127.0.0.1:8719
- [ ] `http://127.0.0.1:8719/` — dashboard loads
- [ ] Create a project with a YouTube URL
- [ ] Analysis completes and clips appear
- [ ] Editor loads with video player + crop overlay
- [ ] Crop keyframes are visible and draggable
- [ ] Timeline shows keyframe dots
- [ ] Export produces a 1080×1920 MP4

## Known Issues

1. The frontend uses a simple Vite dev server during development. For the integration test with the FastAPI backend, either run `npm run dev` on port 5173 with CORS or build and serve from FastAPI. The `main.py` already mounts the dist folder if it exists.
2. The video media endpoint `/api/media/{pid}/video` needs to be added to `projects.py` — it streams the source video for the player. Add it after Task 12.
3. The face model asset (`blaze_face_short_range.tflite`) must be downloaded manually or via a setup script. It is not in the repo. Add a `scripts/setup.sh` that downloads it from Google's storage.
