# Smart Clipper — Vertical Slice Design

Date: 2026-09-12
Status: Approved
Source requirements: `PRD.md`

## 1. Goal

Deliver a working local-first AI video clipper covering the complete flow end to end:

```
YouTube URL → download → transcribe → score hooks → generate clips
→ detect/track faces → smart 9:16 crop keyframes → captions
→ manual crop adjustment in editor → preview → export MP4
```

Every stage is really implemented. No stage is a stub, a mock, or a button that
only mutates UI state. Breadth is achieved by keeping each stage minimal, not by
faking it.

## 2. Scope decisions

Four decisions were made before design, and they constrain everything below.

| Decision | Choice | Reason |
|---|---|---|
| Build scope | Thin end-to-end vertical slice | De-risks the whole pipeline before thickening any layer |
| Desktop shell | Defer Tauri; FastAPI serves the React build | Tauri adds a Rust toolchain, sidecar packaging, and an IPC layer to a pipeline that is 95% Python + React. Its PRD duties (spawn ffmpeg/yt-dlp, filesystem access) are already Python's job |
| Models | `whisper small` + `llama3.2:latest` | Both already present locally; zero new downloads. The LLM is only 5% of the hook score by the PRD's own formula, so model size mostly buys caption polish |
| Animated crop | ffmpeg `crop` filter with a `t`-expression | Single pass, no intermediate files, no per-frame Python decode |

### Explicitly out of scope for this slice

- Tauri shell and packaging (Phase 10)
- Active-speaker switching via mouth movement + audio correlation. The slice
  picks the most prominent stable face track. The PRD itself directs preferring
  stable framing when attribution is uncertain.
- Scene detection
- Effect tab: the slice implements caption text, font size, position, and
  highlight colour, and these values reach the renderer. Animation presets,
  emoji injection, background boxes, and the zoom effect are not implemented.
  The effects field on `RenderPlan` is a list, so adding them later does not
  change its shape.
- 1:1 and 16:9 presets in the UI. The crop math is ratio-generic and tested at
  all three ratios; only 9:16 is wired into the interface.

## 3. Verified environment

These were confirmed by execution, not assumption. They are facts about the
target machine, and the implementation depends on them.

- Hardware: arm64, 8GB RAM — the PRD's stated target.
- Python: system default is 3.14.7, which **cannot** run this project.
  `mediapipe` and `mlx-whisper` have no 3.14 wheels. Python **3.12** resolves
  all critical dependencies: `mlx-whisper 0.4.3`, `opencv-python 5.0.0.93`,
  `fastapi 0.141.1`. `uv` is installed and pins 3.12 at no cost.
- **`mediapipe` must be pinned to `==0.10.35`.** This is not a preference. The
  latest version, 1.0.1, is what `uv` resolves to by default and it **crashes
  hard** on this machine: `TensorsToDetectionsCalculator::Open()` aborts with
  `graph_service.h:139] Check failed: service_ Service is unavailable` inside
  `DrishtiMetalHelper`. Passing `delegate=CPU` does not avoid it — the Metal
  service is requested regardless. Both 1.0.1 and 0.10.35 have removed the
  legacy `mp.solutions.face_detection` API entirely, so the Tasks API is the
  only option, and it only functions on 0.10.35. Verified working there:
  1 face at 0.92 confidence, correct bounding box, and `RunningMode.VIDEO`
  accepting OpenCV BGR→RGB frames via `detect_for_video`.
- The face model is a separate ~224KB `.task`/`.tflite` asset
  (`blaze_face_short_range.tflite`) that must be downloaded; it is not bundled
  in the wheel.
- Binaries present: `ffmpeg`, `yt-dlp`, `ollama`, `node`, `cargo`.
- ffmpeg is built with `--enable-libass`, `--enable-libfreetype`,
  `--enable-libharfbuzz`. The `ass` and `subtitles` filters are both available,
  so captions burn in from a generated ASS file rather than from long chains of
  `drawtext` filters.
- Ollama models present: `llama3.2:latest`, `bge-m3`, `nomic-embed-text`.
  No `qwen3`. A scoring prompt against `llama3.2` returned a clean numeric
  answer in 98ms of eval time.
- **Animated crop verified.** A moving `crop` x-expression was confirmed to be
  evaluated per frame, not once at filter init: with the crop window sliding
  across a white box, mean luma jumped 16 → 88 at the predicted crossing time
  (t≈2.3s). This is the single riskiest assumption in the export path and it
  holds on this exact build.

## 4. Architecture

Two processes, one language boundary.

```
React (Vite)  ──HTTP + SSE──>  FastAPI engine  ──subprocess──>  yt-dlp, ffmpeg, ffprobe
    │                              │
 browser                     in-process: mlx-whisper, mediapipe, opencv
                             HTTP: ollama (127.0.0.1:11434)
```

The engine owns everything privileged: subprocess spawning, filesystem access,
and SQLite. The frontend sends IDs and receives data; it never supplies a
filesystem path. This keeps the PRD's security posture intact even without
Tauri, and means adding Tauri later is a window wrapper rather than a rewrite.

### Repository layout

```
smart-clipper/
├── apps/
│   ├── engine/
│   │   ├── app/
│   │   │   ├── api/           # routers: projects, clips, jobs
│   │   │   ├── domain/        # dataclasses + pure logic (crop, hooks, captions)
│   │   │   ├── services/      # import, transcribe, vision, hooks, captions, render
│   │   │   ├── providers/     # whisper, ollama, face — swappable behind protocols
│   │   │   ├── jobs.py        # queue, progress, cancellation
│   │   │   ├── db.py          # SQLite schema + access
│   │   │   └── config.py      # paths, model ids, scoring weights
│   │   ├── tests/
│   │   └── pyproject.toml     # requires-python = "==3.12.*"
│   └── desktop/               # React + TS + Vite
└── docs/superpowers/specs/
```

### Storage

The PRD names both `data/` and `~/SmartClipper/`. Resolution: a single
configurable `DATA_ROOT`, defaulting to `./data` in development. Per-project
layout follows the PRD:

```
data/projects/<project-id>/
    source/  audio/  transcript/  analysis/  thumbnails/  previews/  exports/
```

One SQLite database at `data/smartclipper.db` holds all projects. Only paths are
stored, never blobs. Every path the engine resolves is verified to remain inside
`DATA_ROOT` before use, so a crafted ID cannot escape the project tree.

## 5. Database schema

```
projects(id, name, status, created_at, updated_at)
media(id, project_id, source_url, path, title, channel, duration,
      width, height, fps, has_audio)
transcripts(id, project_id, language, path)
transcript_segments(id, transcript_id, idx, start, end, text, confidence,
                    speaker, words_json)
hook_candidates(id, project_id, start, end, score, scores_json,
                reasons_json, weaknesses_json)
clips(id, project_id, hook_candidate_id, source_start, source_end,
      aspect_ratio, status, crop_manually_modified,
      title, caption_short, caption_long, cta, hashtags_json)
face_detections(id, project_id, timestamp, x, y, w, h, confidence)
face_tracks(id, project_id, start, end, centers_json)
crop_keyframes(id, clip_id, time, center_x, center_y, source)
captions(id, clip_id, idx, start, end, text, words_json, style_json)
render_jobs(id, clip_id, kind, status, progress, stage, error, output_path)
```

`source` on `crop_keyframes` is `ai` or `manual`. Re-running analysis replaces
`ai` rows and leaves `manual` rows untouched, which is what makes "do not
overwrite manual keyframes" real rather than aspirational. **Reset to AI**
deletes the `manual` rows for a clip and regenerates, clearing
`crop_manually_modified`.

Two clarifications on columns whose meaning would otherwise be guessed:

- `transcript_segments.confidence` is derived from Whisper's `avg_logprob` as
  `exp(avg_logprob)`, giving a 0..1 value. Whisper does not emit a confidence
  figure directly, and the hook scorer consumes this normalized form. Verified
  against real output: `avg_logprob=-0.276` → `0.759`.
- Verified `mlx_whisper.transcribe` output schema, which the parser depends on.
  Segments carry `id, seek, start, end, text, tokens, temperature, avg_logprob,
  compression_ratio, no_speech_prob, words`; words carry
  `word, start, end, probability`. Word `start`/`end` arrive as `np.float64`
  and **must be cast to `float`** before JSON serialization or persistence
  fails. The model id is `mlx-community/whisper-small-mlx`.
- `face_detections` rows are keyed to the project and timestamped in **source**
  time, not clip time. Clips reference them by time range. This means detection
  runs once per source video and is reused by every clip drawn from it, rather
  than being recomputed per clip.

## 6. Crop coordinate system

This is the contract that makes preview and export agree, so it is stated
precisely.

A keyframe is `{time, center_x, center_y}` where `center_x` and `center_y` are
**normalized source coordinates in 0..1**. Never pixels. Both consumers scale
from the same normalized values:

- Preview: multiplied by the displayed video element's size.
- Renderer: multiplied by the source pixel dimensions.

Crop window size for a target aspect ratio:

```
target  = aspect_w / aspect_h
source  = src_w / src_h

if target < source:   # vertical target from a wider source — the usual case
    crop_h = src_h
    crop_w = round_even(src_h * target)
else:
    crop_w = src_w
    crop_h = round_even(src_w / target)
```

Dimensions are rounded to even numbers because H.264 with yuv420p requires it.

The centre is clamped so the window never leaves the frame:

```
half_w = (crop_w / src_w) / 2
cx     = clamp(center_x, half_w, 1 - half_w)     # same form for y
x_px   = round(cx * src_w - crop_w / 2)
```

Clamping at the normalized level, before conversion to pixels, keeps preview and
renderer from disagreeing at the edges of the frame.

## 7. Smart crop pipeline

1. **Detect.** MediaPipe face detection on frames sampled every 3rd frame
   (~10Hz at 30fps). Sufficient for head motion and three times cheaper than
   every frame.
2. **Track.** Associate detections into tracks by IoU plus centre distance. A
   track survives a short gap of missed detections before being closed.
3. **Select.** Choose the track with the greatest presence × mean area across
   the clip. One subject for the whole clip, so framing stays stable.
4. **Smooth.** Exponential moving average, `alpha = 0.15`, with a small
   deadzone (0.02 normalized) so sub-pixel noise produces no movement at all.
   This is what removes jitter; raw per-frame centres would shake.
5. **Keyframe.** Emit one keyframe per ~0.5s of clip, plus the boundaries, so
   the generated ffmpeg expression stays a manageable length.
6. **Fallback** when no face is present, in order: hold the previous crop, then
   centre crop.

Interpolation between keyframes is linear for the slice. The interpolator takes
an easing function parameter, so smoothstep and ease-in/out drop in later without
touching callers.

## 8. Hook scoring

Deterministic candidates first, LLM last, exactly as the PRD instructs. Windows
of 15/30/45/60s are generated at sentence boundaries and each is scored on
measurable signals:

- curiosity — question forms, open-loop and curiosity-gap openers
- emotional intensity — intensity lexicon, exclamation, emphatic repetition
- specificity — numerals, proper nouns, concrete technical terms
- novelty — contrarian and myth-breaking phrasing
- conflict — negation, opposition, disagreement markers
- payoff — whether a claim made early is resolved inside the window
- self-containment — penalty for unresolved referents ("this", "that") in the
  opening sentence
- speech energy — audio RMS over the window relative to the clip
- context completeness — whether the window opens mid-reference
- transcript confidence — mean Whisper segment confidence
- silence padding — quiet immediately before the start and after the end

Weights live in a single config dict and sum to 1.0, with the LLM at 0.05 as
specified. Scores, reasons, and weaknesses are all persisted, so the UI can show
why a clip scored as it did rather than just asserting a number.

The system reports this as **viral potential scoring** based on measurable
signals. It does not claim to predict virality.

## 9. Captions

Built from Whisper word timestamps. Line splitting respects a max characters per
line and a max lines per screen, and breaks at clause boundaries, never mid-word
and never leaving a single orphan word on a line.

Rendering goes through a generated ASS file consumed by ffmpeg's `ass` filter.
libass is compiled into the local ffmpeg, so word-level highlighting uses native
karaoke timing tags rather than one `drawtext` filter per word.

## 10. Rendering

`RenderPlan` is a plain dataclass — input path, trim, crop with keyframes,
captions, effects, and output settings. Exactly one translator converts a
`RenderPlan` into an ffmpeg argument array. No other module builds ffmpeg
arguments, which is the PRD's maintainability requirement.

The crop expression is piecewise-linear over the keyframes, built as nested
`if(between(t,...))` clauses.

**Timebase detail that matters:** `-ss` before `-i` resets presentation
timestamps to zero, so keyframe times are converted to clip-relative before the
expression is generated. Getting this wrong yields a crop that animates at the
wrong moment — correct-looking output that is subtly wrong, so it is tested.

Filter chain:

```
crop=w:h:x='<expr>':y='<expr>'  →  scale=1080:1920  →  ass=<file>
```

Output defaults are 1080×1920, 30fps, H.264 + AAC, with Fast / Balanced /
High Quality presets mapping to x264 preset and CRF.

Preview never invokes ffmpeg for crop changes. The React player draws the crop
overlay from the same normalized keyframes, so moving a crop is instant. ffmpeg
is the source of truth for final output only.

The PRD lists `POST /clips/{id}/preview`. It is deliberately **not** implemented
in the slice: rendering a preview file on every crop adjustment is exactly the
behaviour the PRD's own "Preview vs Final Render" section forbids. Live preview
is handled client-side from the shared keyframes. The endpoint becomes useful
only for effects that cannot be reproduced in the browser, and none are in scope
here.

## 11. Jobs and progress

A single-worker background queue inside the engine process. States: `queued`,
`processing`, `completed`, `failed`, `cancelled`.

Analysis is staged, and each stage reports fractional progress:

```
download → metadata → audio → transcribe → hooks → clips
→ faces → crop → captions → done
```

Progress streams to the frontend over SSE at `GET /jobs/{id}/events`. SSE rather
than WebSocket because the traffic is one-directional.

Cancellation is cooperative: each stage checks a per-job cancel flag at loop
boundaries, and subprocesses are terminated. A cancelled job leaves the project
in its last consistent state, with partial outputs discarded rather than
half-written rows committed.

Models load lazily and are released as soon as a stage finishes, so Whisper and
the LLM are never co-resident. Peak memory stays near 2GB, inside the 8GB target.

## 12. API

```
POST   /projects                    create, optionally with a URL
GET    /projects                    list
GET    /projects/{id}               detail with media + counts
POST   /projects/{id}/import        import from URL or local file
POST   /projects/{id}/analyze       run the pipeline
GET    /projects/{id}/analysis      transcript, hooks, faces
POST   /projects/{id}/clips         create a clip, manually or from a candidate
GET    /clips/{id}                  clip with keyframes and captions
PATCH  /clips/{id}                  trim, aspect, captions, manual keyframes
POST   /clips/{id}/smart-crop       regenerate AI keyframes
POST   /clips/{id}/reset-crop       drop manual keyframes, restore AI
POST   /clips/{id}/generate-caption LLM caption/title/CTA/hashtags
POST   /clips/{id}/export           enqueue export
GET    /jobs/{id}                   job state
GET    /jobs/{id}/events            SSE progress
POST   /jobs/{id}/cancel            cancel
GET    /media/{media_id}            range-capable video streaming for the player
```

## 13. Frontend

React + TypeScript + Vite, Zustand for state, split into UI / editor / project /
job stores as the PRD requires. Analysis results are fetched and held outside
component state; no frame data or large analysis blobs go into React state.

Screens: Dashboard, New Project, Analysis (hooks with scores and reasons), Clip
Editor, Export.

The editor follows the PRD reference layout — top bar with status and metadata,
large preview with a draggable crop rectangle, segment timeline at the bottom,
and a right sidebar with Crop / Script / Effect tabs. Dragging the crop writes a
keyframe at the playhead and marks the clip manually modified.

Visual direction is dark, dense, and minimal with an indigo accent — a
professional editor, not a SaaS dashboard.

## 14. Testing

Real tests for the pure logic, where a silent bug produces a subtly wrong video:

- crop window sizing at 9:16, 1:1, 16:9
- centre clamping at and beyond frame edges
- keyframe interpolation, including before-first and after-last keyframe
- EMA smoothing reduces variance and respects the deadzone
- hook scoring — signal extraction and weight combination
- transcript and caption segmentation, including the orphan-word rule
- RenderPlan → ffmpeg argument array, including clip-relative keyframe times
- project persistence and the manual-vs-AI keyframe merge rule
- job lifecycle, including cancellation

Integration coverage uses a small ffmpeg-generated fixture video rather than
mocks, and asserts that an export produces a 1080×1920 file of the expected
duration.

## 15. Risks

| Risk | Handling |
|---|---|
| Python 3.14 default breaks install | Pin 3.12 via `uv`; verified to resolve all deps |
| **mediapipe 1.0.1 crashes on Metal** | **Pin `==0.10.35`; verified working. Default resolution picks the broken version, so the pin is load-bearing** |
| Crop expression not evaluated per frame | Verified by luma measurement before design |
| `-ss` timebase shifts crop animation | Keyframes converted to clip-relative; covered by a test |
| Whisper word times are `np.float64` | Cast to `float` at the parser boundary; verified schema |
| Memory pressure on 8GB | Sequential model load/release; never co-resident |
| ffmpeg lacking libass | Verified compiled in |
| yt-dlp breakage from YouTube changes | Isolated in one provider; local file import is an unaffected path |
