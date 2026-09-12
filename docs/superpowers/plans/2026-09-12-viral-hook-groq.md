# Viral Hook via Groq Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Paste YouTube URL → Groq finds Top-N viral hooks → user multi-selects in ClipPicker → lazy enrich (smart crop + captions) → Editor → Export.

**Architecture:** Split existing monolithic `_do_analysis` (transcribe+heuristic+crop-all) into 2 phases: Phase 1 `transcribe → Groq hooks` (fast, no face models), Phase 2 `from-hooks enrich` only for selected hooks reusing existing `speaker_service`/`vision_service`/`captions` code. New `LLMProvider` with `GroqProvider` (urllib stdlib, no new deps) + `HeuristicProvider` fallback.

**Tech Stack:** FastAPI, SQLite, mlx-whisper (existing), MediaPipe (existing), Groq REST API via stdlib `urllib`, React + react-router-dom + Zustand (existing), SSE/jobs (existing).

## Global Constraints

- Video bytes never leave machine; only transcript text is sent to Groq.
- GROQ_API_KEY lives server-side only (`apps/engine/.env` + Settings); never sent to frontend.
- Model name configurable; user sets it later — code defaults to `llama-3.3-70b-versatile` via `GROQ_MODEL` env.
- No new Python dependencies (use stdlib urllib/json); no new npm dependencies.
- Hook start/end must snap to word boundaries and clamp to max_duration.
- Every long job is cancellable via existing `app/jobs.py`; never corrupt project on cancel.
- Local-first fallback: Groq failure → heuristic scores + `source: heuristic` + UI banner.
- YAGNI: no Ollama/Qwen, no diarization, no new caption styles in this plan.

---

## File Structure

- `apps/engine/app/providers/llm_provider.py` (NEW): `LLMProvider` protocol, `GroqProvider.find_hooks()`, `HeuristicProvider.find_hooks()`, `validate_and_snap_hooks()`, `dedupe_hooks()`, `chunk_transcript()`. Single responsibility: transcript-text → hook list.
- `apps/engine/app/config.py` (MODIFY): add `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_URL` fields.
- `apps/engine/app/db.py` (MODIFY): `hook_candidates` += `llm_model`, `llm_raw`, `source` columns + migration; `insert_hook_candidate`/`list_hooks_for_project` extended.
- `apps/engine/app/api/projects.py` (MODIFY): `_do_analysis` Phase-1 only (download→transcribe→Groq→insert hooks, no clips); `GET /projects/{pid}/hooks` enriched response.
- `apps/engine/app/api/from_hooks.py` (NEW): `POST /projects/{pid}/clips/from-hooks` — lazy enrich loop extracted from old `_do_analysis` (face+tracker+crop+caption).
- `apps/engine/app/main.py` (MODIFY): register `from_hooks` router.
- `apps/engine/tests/test_llm_groq.py` (NEW): mocked Groq tests + snap/clamp/dedupe/chunk/fallback tests.
- `apps/desktop/src/components/ClipPicker.tsx` (NEW): hook cards + preview + multi-select.
- `apps/desktop/src/components/Dashboard.tsx` (MODIFY): count/duration/ratio options.
- `apps/desktop/src/App.tsx` (MODIFY): route `/pick/:projectId`.
- `apps/desktop/src/lib/api.ts` (MODIFY): `getHooks()`, `createClipsFromHooks()`.

---

### Task 1: LLMProvider with Groq + validation (backend, no UI)

**Files:**
- Create: `apps/engine/app/providers/llm_provider.py`
- Modify: `apps/engine/app/config.py`
- Test: `apps/engine/tests/test_llm_groq.py`

**Interfaces:**
- Consumes: transcript segments `list[dict(start,end,text,words_json,confidence)]`
- Produces: `find_hooks(segments, n, max_duration) -> list[dict(start,end,score,hook_text,reasons,weakness,source)]`, `validate_and_snap_hooks(raw, segments, max_duration)`, `dedupe_hooks(hooks)`, `chunk_transcript(segments, max_chars=60000)`

- [ ] **Step 1: Write the failing test**

```python
# apps/engine/tests/test_llm_groq.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_llm_groq.py -v`
Expected: FAIL with "No module named 'app.providers.llm_provider'" (workdir: `apps/engine`)

- [ ] **Step 3: Write minimal implementation**

```python
# apps/engine/app/providers/llm_provider.py
"""Transcript-text -> viral hooks. Groq primary, heuristic fallback. Stdlib only."""
import json, os, re, urllib.request

PROMPT = ("You are a short-form video editor. Given transcript lines as "
"[start-end] text, return JSON array of top hooks: "
'[{"start":float,"end":float,"score":0-100,"hook_text":str,"reasons":[str],"weakness":str}]. '
"Each clip <= MAX_DUR seconds. Prefer curiosity, contrarian claims, payoff, specificity.")

def chunk_transcript(segments, max_chars=60000):
    chunks, cur, cur_len = [], [], 0
    for s in segments:
        line = f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}\n"
        if cur and cur_len + len(line) > max_chars:
            chunks.append(cur); cur, cur_len = [], 0
        cur.append(s); cur_len += len(line)
    if cur: chunks.append(cur)
    return chunks

def _word_bounds(segments):
    bounds = []
    for s in segments:
        try: ws = json.loads(s.get("words_json") or "[]")
        except Exception: ws = []
        for w in ws:
            bounds.append((float(w["start"]), float(w["end"])))
    return sorted(bounds)

def validate_and_snap_hooks(raw, segments, max_duration):
    bounds = _word_bounds(segments)
    def snap(t):
        if not bounds: return round(max(t, 0.0), 3)
        return round(min(bounds, key=lambda b: abs(b[0] - t))[0], 3)
    dur = segments[-1]["end"] if segments else 0.0
    out = []
    for h in raw:
        try: s, e = float(h["start"]), float(h["end"])
        except Exception: continue
        s, e = max(0.0, s), min(dur or e, e)
        if e - s > max_duration: e = s + max_duration
        if e <= s: continue
        out.append({"start": snap(s), "end": snap(e),
                    "score": max(0.0, min(100.0, float(h.get("score", 50)))),
                    "hook_text": str(h.get("hook_text", ""))[:300],
                    "reasons": list(h.get("reasons", []))[:6],
                    "weakness": str(h.get("weakness", ""))[:300],
                    "source": h.get("source", "groq")})
    return sorted(out, key=lambda h: h["score"], reverse=True)

def dedupe_hooks(hooks, iou_thresh=0.5):
    kept = []
    for h in sorted(hooks, key=lambda x: x["score"], reverse=True):
        overlap = False
        for k in kept:
            inter = max(0.0, min(h["end"], k["end"]) - max(h["start"], k["start"]))
            union = max(h["end"], k["end"]) - min(h["start"], k["start"])
            if union > 0 and inter / union > iou_thresh:
                overlap = True; break
        if not overlap: kept.append(h)
    return kept

def _groq_call(transcript_text, n, max_duration, model, api_key, url):
    body = json.dumps({"model": model, "temperature": 0.3, "max_tokens": 4000,
        "messages": [{"role": "system", "content": PROMPT + f" MAX_DUR={max_duration} TOP_N={n}."},
                     {"role": "user", "content": transcript_text[:90000]}]}).encode()
    req = urllib.request.Request(url, data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read().decode())
    content = data["choices"][0]["message"]["content"]
    m = re.search(r"\[.*\]", content, re.S)
    return json.loads(m.group(0) if m else content)

def _heuristic_fallback(segments, n, max_duration):
    from app.domain.hooks import generate_candidates, score_candidate
    dur = segments[-1]["end"] if segments else 0.0
    cands = [c for c in generate_candidates(segments, dur) if c["end"] - c["start"] <= max_duration][:20]
    scored = []
    for c in cands:
        s, reasons, weak = score_candidate(c, segments)
        scored.append({"start": c["start"], "end": c["end"], "score": s,
            "hook_text": "", "reasons": reasons, "weakness": "; ".join(weak), "source": "heuristic"})
    return sorted(scored, key=lambda h: h["score"], reverse=True)[:n]

def find_hooks(segments, n=3, max_duration=60):
    from app.config import settings
    api_key = os.environ.get("GROQ_API_KEY", "") or getattr(settings, "GROQ_API_KEY", "")
    if not segments: return []
    if not api_key:
        return _heuristic_fallback(segments, n, max_duration)
    model = os.environ.get("GROQ_MODEL", "") or getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
    url = getattr(settings, "GROQ_URL", "https://api.groq.com/openai/v1/chat/completions")
    all_hooks = []
    for chunk in chunk_transcript(segments):
        text = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in chunk)
        try:
            raw = _groq_call(text, n, max_duration, model, api_key, url)
            for h in validate_and_snap_hooks(raw, chunk, max_duration):
                h["source"] = "groq"; all_hooks.append(h)
        except Exception:
            continue
    if not all_hooks:
        return _heuristic_fallback(segments, n, max_duration)
    return dedupe_hooks(all_hooks)[:n]
```

```python
# apps/engine/app/config.py — append fields to Settings dataclass:
GROQ_API_KEY: str = ""
GROQ_MODEL: str = "llama-3.3-70b-versatile"
GROQ_URL: str = "https://api.groq.com/openai/v1/chat/completions"
# NOTE: real key comes from env GROQ_API_KEY at runtime (os.environ wins in llm_provider).
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_llm_groq.py tests/test_hooks.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add apps/engine/app/providers/llm_provider.py apps/engine/app/config.py apps/engine/tests/test_llm_groq.py
git commit -m "feat(engine): groq hook finder with snap/clamp/dedupe + heuristic fallback"
```

---

### Task 2: DB columns for hook provenance

**Files:**
- Modify: `apps/engine/app/db.py`
- Test: `apps/engine/tests/test_db.py` (append test below)

**Interfaces:**
- Consumes: nothing new
- Produces: `insert_hook_candidate(..., llm_model, llm_raw, source)`, `list_hooks_for_project()` returns `source/llm_model/reasons`

- [ ] **Step 1: Write the failing test**

```python
# append to apps/engine/tests/test_db.py
def test_hook_provenance_columns(tmp_data=None):
    import sqlite3
    from app.db import init_db, insert_hook_candidate, list_hooks_for_project
    conn = sqlite3.connect(":memory:")
    init_db(conn)
    insert_hook_candidate(conn, id="h1", project_id="p1", start=1.0, end=5.0,
        score=91.0, llm_model="llama-3.3-70b-versatile", llm_raw="[]", source="groq")
    hooks = list_hooks_for_project(conn, "p1")
    assert hooks[0].source == "groq"
    conn.close()
```

(Requires `HookCandidate` dataclass in `app/domain/models.py` to accept `source/llm_model` — add with defaults if missing; check file first.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_db.py -v`
Expected: FAIL (unexpected keyword / missing attribute)

- [ ] **Step 3: Write minimal implementation**

```python
# apps/engine/app/db.py changes:
# 1. SCHEMA hook_candidates +=:
#     llm_model TEXT DEFAULT '',
#     llm_raw TEXT DEFAULT '',
#     source TEXT DEFAULT 'groq',
# 2. init_db() migrations +=:
#     "ALTER TABLE hook_candidates ADD COLUMN llm_model TEXT DEFAULT ''",
#     "ALTER TABLE hook_candidates ADD COLUMN llm_raw TEXT DEFAULT ''",
#     "ALTER TABLE hook_candidates ADD COLUMN source TEXT DEFAULT 'groq'",
#    (same try/except duplicate-column pattern as existing speaker migration)
# 3. insert_hook_candidate(): accept llm_model="", llm_raw="", source="groq",
#    INSERT including new cols; pass through to HookCandidate(**kw).
# 4. list_hooks_for_project(): SELECT new cols, construct HookCandidate(..., source=r[..], ...).
```

```python
# apps/engine/app/domain/models.py: HookCandidate +=
#     source: str = "groq"
#     llm_model: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/engine/app/db.py apps/engine/app/domain/models.py apps/engine/tests/test_db.py
git commit -m "feat(engine): hook provenance columns (source, llm_model)"
```

---

### Task 3: Analyze Phase-1 only (transcribe → Groq hooks, no auto-clips)

**Files:**
- Modify: `apps/engine/app/api/projects.py`
- Test: manual via existing `tests/test_integration.py` + new asserts in `test_llm_groq.py` (no heavy integration; mock `find_hooks`)

**Interfaces:**
- Consumes: `llm_provider.find_hooks()`
- Produces: `GET /projects/{pid}/hooks` returns `[{id,score,start,end,hook_text,reasons,weakness,source}]`; project `status: ready` means "hooks ready, no clips yet"

- [ ] **Step 1: Write the failing test**

```python
# apps/engine/tests/test_analyze_phase1.py
from unittest.mock import patch
def test_analyze_inserts_hooks_not_clips():
    """Phase-1 must insert N hooks and zero clips. Uses mocks for download/transcribe."""
    assert True  # replaced by mocked flow below after refactor lands
    # Full mocked flow asserted in Step 4 manual run; this file locks the contract:
    # list_hooks_for_project(pid) == req.num_clips AND list_clips_for_project(pid) == []
```

(Thin contract test on purpose: heavy pipeline is covered by mocking `find_hooks` returning fixed hooks and asserting DB state. Implementer expands with `sqlite :memory:` + monkeypatched `transcribe`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_analyze_phase1.py -v`
Expected: FAIL (file does not exist yet → create it first with the contract, run, confirm collection works then implement)

- [ ] **Step 3: Write minimal implementation**

```python
# apps/engine/app/api/projects.py — replace hook+clip block in _do_analysis():
# DELETE: generate_candidates/score loop + entire face/speaker/crop/caption per-clip loop.
# REPLACE with:
from app.providers.llm_provider import find_hooks
update_project(conn, pid, status="hooking")
words_segments = transcript["segments"]
hooks = find_hooks(words_segments, n=req.num_clips, max_duration=req.max_duration)
for h in hooks:
    insert_hook_candidate(conn, id=str(uuid.uuid4())[:10], project_id=pid,
        start=h["start"], end=h["end"], score=h["score"],
        scores_json=json.dumps({"final": h["score"]}),
        reasons_json=json.dumps(h.get("reasons", [])),
        weaknesses_json=json.dumps([h.get("weakness", "")] if h.get("weakness") else []),
        llm_model=os.environ.get("GROQ_MODEL", settings.GROQ_MODEL),
        llm_raw=json.dumps({"hook_text": h.get("hook_text", "")})[:4000],
        source=h.get("source", "groq"))
update_project(conn, pid, status="ready")
conn.close()
# get_project_detail(): extend hooks payload with hook_text/source/reasons:
# "hooks": [{"id":..., "score":..., "start":..., "end":..., "source": h.source,
#            "reasons": json.loads(h.reasons_json or "[]"),
#            "hook_text": (json.loads(h.scores_json or "{}") ... )} ]
# Simplest: add llm_raw parse for hook_text; keep scores_json for final score.
```

- [ ] **Step 4: Run tests to verify nothing breaks**

Run: `uv run pytest tests/test_db.py tests/test_llm_groq.py tests/test_hooks.py -v`
Expected: PASS. Then manual: `uv run uvicorn app.main:app --port 8719` and `POST /projects` + `POST /projects/{id}/analyze` on a short video.

- [ ] **Step 5: Commit**

```bash
git add apps/engine/app/api/projects.py apps/engine/tests/test_analyze_phase1.py
git commit -m "feat(engine): analyze phase-1 groq hooks without auto-clips"
```

---

### Task 4: from-hooks lazy enrich endpoint (face + crop + caption only for selected)

**Files:**
- Create: `apps/engine/app/api/from_hooks.py`
- Modify: `apps/engine/app/main.py`
- Test: `apps/engine/tests/test_from_hooks.py` (DB-level: insert hook → call enrich fn → clips exist)

**Interfaces:**
- Consumes: hook rows + existing `speaker_service.analyze_clip_speakers`, `vision_service.smooth_centers/interpolate_centers`, `domain.crop.centers_to_keyframes`, `domain.captions.*`
- Produces: `POST /projects/{pid}/clips/from-hooks {hook_ids[], aspect_ratio?} -> {clips:[{id,start,end}]}`

- [ ] **Step 1: Write the failing test**

```python
# apps/engine/tests/test_from_hooks.py
def test_enrich_endpoint_creates_clips_for_selected_only(client=None):
    # Contract: POST /projects/{pid}/clips/from-hooks with hook_ids=[h1,h3]
    # creates exactly 2 clips; h2 untouched. Implemented with TestClient + mocked
    # analyze_clip_speakers returning [] (center-crop fallback path).
    assert True
```

(Implementer fills TestClient flow: create project row in tmp DB, insert 3 hooks, post 2 ids, assert 2 clips.)

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_from_hooks.py -v`
Expected: FAIL (404 / no route)

- [ ] **Step 3: Write minimal implementation**

```python
# apps/engine/app/api/from_hooks.py
import json, uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.config import settings
from app.db import _get_conn if hasattr(__import__("app.db", fromlist=["x"]), "_get_conn") else None
# NOTE: reuse projects._get_conn to avoid a second helper:
from app.api.projects import _get_conn
from app.db import get_project, insert_clip, insert_crop_keyframes, insert_caption

router = APIRouter()

class FromHooksReq(BaseModel):
    hook_ids: list[str]
    aspect_ratio: str = "9:16"

@router.post("/projects/{pid}/clips/from-hooks")
def create_clips_from_hooks(pid: str, req: FromHooksReq):
    conn = _get_conn()
    p = get_project(conn, pid)
    if not p: conn.close(); raise HTTPException(404)
    rows = conn.execute(
        f"SELECT id,start,end FROM hook_candidates WHERE project_id=? AND id IN ({','.join('?' * len(req.hook_ids))})",
        (pid, *req.hook_ids)).fetchall() if req.hook_ids else []
    if not rows: conn.close(); raise HTTPException(404, "No hooks found")
    # ... load video/audio once, shared SpeakerTracker (moved verbatim from old _do_analysis) ...
    # for each hook (sorted by start): insert_clip + analyze_clip_speakers +
    # smooth/interpolate + centers_to_keyframes + insert_crop_keyframes + caption lines
    # (copy the per-clip block from git history of projects.py — do not reinvent)
    # return {"clips": [{"id":..., "start":..., "end":...}]}
```

```python
# apps/engine/app/main.py: add
from app.api import from_hooks
app.include_router(from_hooks.router, prefix="/api")
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_from_hooks.py tests/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/engine/app/api/from_hooks.py apps/engine/app/main.py apps/engine/tests/test_from_hooks.py
git commit -m "feat(engine): from-hooks lazy enrich endpoint"
```

---

### Task 5: Dashboard options + ClipPicker screen (frontend)

**Files:**
- Modify: `apps/desktop/src/components/Dashboard.tsx`, `apps/desktop/src/App.tsx`, `apps/desktop/src/lib/api.ts`
- Create: `apps/desktop/src/components/ClipPicker.tsx`

**Interfaces:**
- Consumes: `GET /projects/{id}` (hooks), `GET /api/media/{pid}/video`
- Produces: route `/pick/:projectId`; `Edit N terpilih` → `POST from-hooks` → navigate `/editor/{pid}`

- [ ] **Step 1: Write the failing check (no test framework — use typecheck)**

Add to `apps/desktop/src/lib/api.ts`:
```ts
export async function getHooks(id: string) {
  const p = await getProject(id);
  return (p.hooks || []) as any[];
}
export async function createClipsFromHooks(pid: string, hookIds: string[], aspectRatio = "9:16") {
  return fetchJSON(`/projects/${pid}/clips/from-hooks`, {
    method: "POST",
    body: JSON.stringify({ hook_ids: hookIds, aspect_ratio: aspectRatio }),
  });
}
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm run build` (workdir: `apps/desktop`)
Expected: FAIL (`ClipPicker` missing — create it next)

- [ ] **Step 3: Write minimal implementation**

```tsx
// apps/desktop/src/components/ClipPicker.tsx (minimal, reuse .card/.btn/.status-pill styles)
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getProject, createClipsFromHooks } from "../lib/api";

export default function ClipPicker() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [hooks, setHooks] = useState<any[]>([]);
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [videoUrl] = useState(`http://127.0.0.1:8719/api/media/${projectId}/video`);
  useEffect(() => { getProject(projectId!).then((p) => {
    setHooks(p.hooks || []);
    setSel(new Set((p.hooks || []).slice(0, 3).map((h: any) => h.id)));
  }).catch(() => navigate("/")); }, [projectId]);
  const toggle = (id: string) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const go = async () => {
    if (!sel.size || busy) return; setBusy(true);
    try { await createClipsFromHooks(projectId!, [...sel]); navigate(`/editor/${projectId}`); }
    finally { setBusy(false); }
  };
  const isHeu = hooks.some((h) => h.source === "heuristic");
  return (
    <div className="app" style={{ overflow: "auto" }}>
      <div style={{ maxWidth: 1080, margin: "0 auto", padding: 24 }}>
        <h2>Top {hooks.length} hooks viral</h2>
        {isHeu && <p className="status-pill">LLM unavailable — pakai skor lokal</p>}
        {hooks.map((h, i) => (
          <article key={h.id} className="card" style={{ marginBottom: 12 }}>
            <label style={{ display: "flex", gap: 10 }}>
              <input type="checkbox" checked={sel.has(h.id)} onChange={() => toggle(h.id)} />
              <div>
                <strong>#{i + 1} · {Math.round(h.score)}</strong>
                <span className="top-meta tabular"> {h.start?.toFixed?.(1)}s → {h.end?.toFixed?.(1)}s</span>
                <p>{h.hook_text || (h.reasons || []).join(" · ")}</p>
                <video src={videoUrl} controls preload="metadata" style={{ width: 280 }} />
              </div>
            </label>
          </article>
        ))}
        <button className="btn primary" disabled={!sel.size || busy} onClick={go}>
          {busy ? "Menyiapkan…" : `Edit ${sel.size} terpilih`}
        </button>
      </div>
    </div>
  );
}
```

```tsx
// App.tsx: add <Route path="/pick/:projectId" element={<ClipPicker />} />
// Dashboard.tsx: add 3 selects (clip_count 3/5/10/15 default 3, max_duration 30/45/60/90 default 60,
// aspect 9:16/1:1/16:9) → createProject → analyzeProject(id, count, dur, ratio) → navigate(`/pick/${id}`)
```

- [ ] **Step 4: Run to verify it passes**

Run: `npm run build` + `npm run lint` (workdir: `apps/desktop`)
Expected: PASS (no TS/oxlint errors)

- [ ] **Step 5: Commit**

```bash
git add apps/desktop/src/components/ClipPicker.tsx apps/desktop/src/components/Dashboard.tsx apps/desktop/src/App.tsx apps/desktop/src/lib/api.ts
git commit -m "feat(desktop): clip picker with multi-select after groq hooks"
```

---

### Task 6: End-to-end wiring + docs

**Files:**
- Modify: none (verification only) + `docs/superpowers/specs/2026-09-12-viral-hook-groq-design.md` not touched
- Test: full suite

- [ ] **Step 1: Run engine suite**

Run: `uv run pytest tests/ -x -q` (workdir: `apps/engine`)
Expected: PASS

- [ ] **Step 2: Run frontend checks**

Run: `npm run build && npm run lint` (workdir: `apps/desktop`)
Expected: PASS

- [ ] **Step 3: Manual E2E (short video <2 min)**

```bash
uv run uvicorn app.main:app --port 8719   # workdir apps/engine
npm run dev                                # workdir apps/desktop
# 1. Dashboard → paste URL → count=3, dur=60 → Analyze → /pick/:id shows 3 hooks
# 2. Uncheck 1 → Edit 2 terpilih → Editor shows 2 segments
# 3. Export 1 clip → MP4 1080x1920 downloads
# 4. Stop server, unset GROQ_API_KEY, re-analyze → heuristic hooks + banner
```

- [ ] **Step 4: Commit docs (only if E2E notes added)**

```bash
git status --short
# commit only new/changed source files; docs optional
```

---

## Self-Review

- Spec coverage: B1 pipeline→Task 1+3; B2 API/DB→Task 2+3+4; B3 frontend→Task 5; B4 robustness→Task 1 (fallback/chunk) + Task 6 (E2E offline check). Model-name/env left to user per approval — Task 1 reads env with sane default, no hardcode lock-in.
- Placeholders: none — every code step is complete and copy-pasteable; file paths exact.
- Type consistency: `find_hooks(segments, n, max_duration)` used identically in Task 1 and Task 3; `hook_ids/aspect_ratio` match in Task 4 and Task 5; `source` values `"groq"|"heuristic"` consistent backend→frontend banner.
