You are a senior staff-level engineer specializing in desktop applications,
video processing, computer vision, local AI, and production-grade software
architecture.

Build a LOCAL-FIRST AI SMART VIDEO CLIPPER desktop application.

The application takes a YouTube video or local video file and automatically:

1. Download/import the video
2. Extract and transcribe the audio
3. Analyze the transcript
4. Detect potentially viral/high-retention hooks
5. Automatically generate clip candidates
6. Detect faces
7. Track faces throughout the clip
8. Automatically crop the video to vertical 9:16
9. Keep the active speaker/person centered
10. Smooth camera movement so the crop does not jitter
11. Generate viral captions
12. Generate title/hook suggestions
13. Allow the user to manually modify the automatic crop
14. Allow the user to modify clip start/end
15. Allow the user to edit captions
16. Preview everything before rendering
17. Export the final video using FFmpeg

The entire application must run locally.

DO NOT require cloud AI APIs for the core functionality.

The application should work offline after the required models and binaries
have been installed.

==================================================
PRODUCT VISION
==================================================

Think of the product as:

"CapCut-style editing UX + OpusClip-style AI clipping,
but local-first and developer-friendly."

The user should be able to:

Paste:

https://youtube.com/watch?v=...

Then click:

"Analyze Video"

The application should:

- download the video
- extract audio
- transcribe it
- identify speakers/faces
- analyze the transcript
- identify strong hook moments
- propose clips
- automatically crop them
- automatically generate captions

The user then reviews the generated clips.

==================================================
IMPORTANT UX REQUIREMENT
==================================================

The editing experience should be similar to the provided reference image.

The main editing screen should contain:

--------------------------------------------------
TOP BAR
--------------------------------------------------

Back

Campaign / Project Name

Video Name

Status:
● Processing
● Edited
● Ready

Metadata:

15 segments · 96s

Actions:

[Download]
[Save]

--------------------------------------------------
MAIN EDITOR
--------------------------------------------------

LEFT / CENTER:

Large video preview.

The video should display the actual 9:16 crop.

Show an editable crop rectangle.

Example:

+--------------------------------+
|                                |
|        SOURCE VIDEO            |
|                                |
|      ┌──────────────┐          |
|      │              │          |
|      │    PERSON    │          |
|      │              │          |
|      └──────────────┘          |
|                                |
+--------------------------------+

The crop rectangle must be draggable.

The user must be able to:

- drag crop
- resize crop if supported
- change aspect ratio
- select 9:16
- select 1:1
- select 16:9
- reset crop
- enable/disable smart crop

When Smart Crop is enabled:

The application automatically positions the crop around
the detected face/person.

==================================================
TIMELINE
==================================================

At the bottom create a professional editing timeline.

Example:

00:02:35

< previous        PLAY        next >

------------------------------------------------------------

| 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 |
|---|---|---|---|---|---|---|---|---|----|----|----|----|

Each segment should have:

- start timestamp
- end timestamp
- duration
- crop configuration
- face tracking information
- caption configuration

Clicking a segment should load that segment's configuration.

The timeline should visually distinguish:

- selected segment
- processed segments
- unprocessed segments
- AI-generated segments
- manually edited segments

==================================================
RIGHT SIDEBAR
==================================================

Create tabs:

[Crop] [Script] [Effect]

CROP TAB:

Segment and crop video

For each segment display:

1
────────●────────

2
────●────────────

3
────────────●────

etc.

This represents the crop position/keyframe timeline.

Each segment should have controls:

[<] [●] [>] [▶] [Reset]

Allow the user to manually override AI crop positions.

IMPORTANT:

The crop editing system must NOT simply change a CSS preview.

The crop configuration must be represented as actual timeline/keyframe
data that can later be translated into FFmpeg rendering instructions.

Example internal model:

{
  "segment_id": 1,
  "source_start": 123.5,
  "source_end": 127.2,
  "aspect_ratio": "9:16",
  "keyframes": [
    {
      "time": 123.5,
      "x": 0.42,
      "y": 0.50
    },
    {
      "time": 125.0,
      "x": 0.48,
      "y": 0.50
    },
    {
      "time": 127.2,
      "x": 0.51,
      "y": 0.50
    }
  ],
  "source": "ai",
  "manually_modified": false
}

==================================================
SCRIPT TAB
==================================================

Display transcript for the current clip.

Each transcript segment should contain:

- text
- start
- end
- confidence
- speaker if available

Example:

00:02:35.120
"Most developers make this mistake..."

00:02:37.200
"...when designing their backend."

The user must be able to edit the transcript/caption text.

==================================================
EFFECT TAB
==================================================

Initially support:

- captions
- caption style
- font
- font size
- position
- background
- animation
- highlight words
- emoji
- zoom effect

Architecture should allow adding more effects later.

==================================================
AI PIPELINE
==================================================

Implement the following pipeline:

VIDEO
  ↓
Download / Import
  ↓
Media Metadata
  ↓
Audio Extraction
  ↓
Whisper Transcription
  ↓
Transcript Segmentation
  ↓
Scene Detection
  ↓
Face Detection
  ↓
Face Tracking
  ↓
Speaker / Active Person Estimation
  ↓
Hook Detection
  ↓
Clip Candidate Generation
  ↓
Smart Crop
  ↓
Caption Generation
  ↓
User Editing
  ↓
FFmpeg Rendering
  ↓
Export

==================================================
YOUTUBE IMPORT
==================================================

Use yt-dlp.

Support:

- YouTube URL
- local MP4
- MOV
- MKV
- WebM

The system should extract:

- title
- channel
- duration
- resolution
- FPS
- audio information

Do not send video data to external servers.

Store imported media in:

data/
  projects/
  media/
  audio/
  transcripts/
  analysis/
  renders/
  thumbnails/

==================================================
TRANSCRIPTION
==================================================

Use mlx-whisper when running on Apple Silicon.

Prefer:

whisper-large-v3-turbo

if the machine can handle it.

Otherwise provide a lighter model option.

Architecture must allow:

Whisper implementation
to be replaced later.

Create:

TranscriptionProvider

with an interface similar to:

transcribe(audio_path) -> Transcript

Transcript model:

{
  "language": "id",
  "segments": [
    {
      "id": 0,
      "start": 0.0,
      "end": 3.4,
      "text": "...",
      "words": []
    }
  ]
}

If word-level timestamps are available, preserve them.

==================================================
HOOK DETECTION
==================================================

Do NOT claim that AI can mathematically determine whether a clip will go viral.

Instead implement:

"viral potential scoring"

based on measurable signals.

Analyze candidate sections using:

1. Curiosity
2. Emotional intensity
3. Strong claim
4. Contrarian statement
5. Surprise
6. Conflict
7. Story payoff
8. Educational value
9. Specificity
10. Question/open loop
11. Self-contained context
12. Fast payoff
13. Transcript confidence
14. Speech energy
15. Silence before/after hook

Generate a score:

0-100

Example:

Hook Score: 91

Reasons:

+ Strong opening statement
+ High curiosity
+ Contrarian claim
+ Self-contained
+ Strong payoff

Potential weaknesses:

- Context appears 2 seconds earlier

==================================================
HOOK DISCOVERY ALGORITHM
==================================================

First create candidate windows.

Example:

15 sec
30 sec
45 sec
60 sec

Then analyze every candidate.

Avoid simply asking the LLM:

"Find viral clips."

Instead:

STEP 1:
Use deterministic candidate generation.

STEP 2:
Use transcript heuristics.

STEP 3:
Use local LLM to evaluate candidates.

STEP 4:
Combine scores.

Example:

final_score =
    curiosity * 0.15 +
    emotional_intensity * 0.10 +
    specificity * 0.10 +
    novelty * 0.10 +
    conflict * 0.10 +
    payoff * 0.15 +
    self_contained * 0.10 +
    speech_energy * 0.05 +
    context_completeness * 0.10 +
    llm_score * 0.05

Make the scoring system configurable.

==================================================
LOCAL LLM
==================================================

Use Ollama.

Initial recommended model:

Qwen3 4B

because the application should run on machines with limited RAM.

Do NOT require a cloud LLM.

Create:

LLMProvider

with:

generate()
analyze_hook()
generate_caption()
generate_title()

The architecture must allow:

Ollama
llama.cpp
OpenAI-compatible local servers

to be swapped later.

==================================================
VIRAL CAPTION GENERATION
==================================================

For every selected clip automatically generate:

1. Short caption
2. Long caption
3. Hook/title
4. CTA
5. Hashtags

Example:

HOOK:

"This is why most backend systems fail."

CAPTION:

"Most backend developers focus on code before
thinking about failure modes..."

CTA:

"Would you design it differently?"

HASHTAGS:

#backend
#softwareengineering
#golang
#systemdesign

The user must be able to modify all generated text.

==================================================
FACE DETECTION
==================================================

Use MediaPipe Face Detection.

Detect:

- face bounding box
- confidence
- timestamp

Example:

{
  "timestamp": 10.25,
  "faces": [
    {
      "x": 0.32,
      "y": 0.24,
      "width": 0.21,
      "height": 0.32,
      "confidence": 0.98
    }
  ]
}

==================================================
FACE TRACKING
==================================================

Do not independently detect the face on every frame and immediately
move the crop.

That will cause jitter.

Implement:

Detection
+
Tracking
+
Temporal smoothing

Use:

- MediaPipe detection
- OpenCV tracking / optical flow where appropriate
- Kalman filtering or exponential smoothing

Generate a smooth center trajectory.

Example:

raw:

0.41
0.47
0.42
0.51
0.45

smoothed:

0.43
0.44
0.45
0.47
0.46

==================================================
ACTIVE SPEAKER
==================================================

GOAL:

For videos containing multiple people, the 9:16 crop must follow
the person who is CURRENTLY SPEAKING, not just the biggest face.
When the speaker changes, the crop glides to the new speaker.
When uncertain, framing stays stable (never rapid switching).

CONSTRAINTS (local-first, M1 8GB):

- No new model downloads for v1.
- Reuse: MediaPipe face boxes (already), audio WAV 16kHz (already),
  Whisper word timestamps (already).
- Face landmark / TalkNet-style neural models are v2 only.

V1 SIGNALS (all deterministic, computed per sample window ~0.5s):

1. face_tracks with stable IDs:
   Match detections across consecutive samples by IoU of boxes
   (threshold 0.3) + centroid distance fallback.
   Unmatched box -> new track id ("A", "B", ...).
   Store per track: id, boxes over time, total visible duration.

2. mouth_motion proxy (no landmarks):
   For each tracked face, take lower-third of the face box
   (mouth region heuristic) and compute mean absolute frame
   difference vs previous sample, normalized by box area.
   Speaking faces show bursty high variance; still faces ~flat.
   Smooth with EMA (alpha 0.4) per track.

3. speech_energy:
   RMS audio energy in the same 0.5s window from extracted WAV.
   Gate: if energy below silence threshold, nobody is speaking
   -> keep current framing.

4. transcript_timing:
   If a Whisper word/segment overlaps the window, speech is
   happening (supports step 3 when music/noise fools RMS).

5. previous speaker + face size/framing as tiebreakers.

V1 DECISION RULE (hysteresis = anti-jitter):

- Score each visible track:
  score = mouth_motion * 0.5 + size_score * 0.2 + center_score * 0.1
          + continuity_bonus(current speaker) * 0.2
- Switch speaker ONLY IF:
  challenger_score > current_score + SWITCH_MARGIN (0.15)
  AND challenger wins for MIN_DWELL_SEC (1.5s) sustained
  AND speech_energy above silence threshold.
  (dwell/hold dalam DETIK, bukan jumlah window, agar konsisten
  untuk sampling 0.1s maupun 0.5s)
- Face hilang sesaat (detection dropout, 1-2 sampel):
  TAHAN framing terakhir selama HOLD_SEC (1.0s), jangan loncat
  ke false-positive. Baru pindah jika wajah tak kembali.
- Otherwise keep current speaker, even if challenger leads slightly.
- Single face visible -> that face, no switching logic.

PIPELINE INTEGRATION:

Replace "pick max-confidence face" in clip analysis with:

  detect faces (all, not just best)
    -> update face_tracks (IoU matching)
    -> compute mouth_motion per track
    -> active speaker decision with hysteresis
    -> crop center = active speaker center
    -> smooth + clamp (existing)

Persist per crop keyframe:

  { "time": ..., "center_x": ..., "center_y": ...,
    "speaker": "A", "speaker_confidence": 0.82 }

Reuse existing crop_keyframes table + add nullable `speaker`
column (migration: ALTER TABLE, default NULL). face_tracks
centers_json extended with track_id per sample.

UI VISUALIZATION (editor follows ss.png layout):

- The purple 9:16 rectangle keeps following via existing
  interpolation + rAF playback loop (already implemented).
- Add speaker badge on the rectangle: "9:16 · A" (track id),
  dot turns amber for 0.5s right after a speaker switch.
- Timeline: small tick mark at each speaker-switch timestamp.
- Sidebar Crop tab: show "A/B" chip per segment row.
- Manual drag still creates manual keyframe (unchanged);
  "Reset AI" restores AI speaker trajectory.

TESTS (extend existing suite):

- IoU track matching: two boxes crossing -> ids stable.
- mouth_motion: synthetic still vs changing mouth region.
- hysteresis: flapping scores (A,B,A,B) -> no switch;
  sustained B lead > MIN_DWELL -> switch once.
- silence gate: zero energy -> keep framing.
- keyframe speaker field round-trips through DB + API.

PHASES:

- PHASE 4b (now): v1 heuristic above, works offline, no downloads.
- v2 (later): MediaPipe FaceLandmarker lip landmarks or
  lightweight audio-visual model behind SpeakerProvider
  interface. Architecture must allow the swap.

==================================================
SMART CROP
==================================================

For 9:16 output:

Calculate the crop based on:

source width
source height
target aspect ratio
face bounding box
safe margins

Do not crop directly to the face.

Use a margin around the face.

Example:

face center = 0.62

crop center target = 0.60

Use smoothing.

When there are no faces:

fall back to:

1. detected person
2. salient region
3. previous crop
4. center crop

==================================================
CROP KEYFRAMES
==================================================

Generate crop keyframes automatically.

Example:

[
  {
    "time": 0,
    "center_x": 0.50,
    "center_y": 0.50
  },
  {
    "time": 2.5,
    "center_x": 0.57,
    "center_y": 0.50
  },
  {
    "time": 5,
    "center_x": 0.61,
    "center_y": 0.49
  }
]

Interpolate between keyframes.

Support:

linear interpolation initially.

Architecture should allow:

ease-in
ease-out
smoothstep

later.

==================================================
IMPORTANT EDITOR BEHAVIOR
==================================================

When the user manually moves the crop:

Create/update a keyframe.

Mark:

manually_modified = true

Do not overwrite manual keyframes when AI analysis runs again.

Provide:

[Reset to AI]

which removes manual overrides and restores AI crop.

==================================================
CAPTIONS
==================================================

Generate captions from Whisper word timestamps.

Support:

- word-level highlighting
- sentence-level captions
- max characters per line
- max lines
- configurable caption position
- safe area

Example:

MOST DEVELOPERS

MAKE THIS

MISTAKE

The caption engine should split text intelligently rather than
randomly splitting every N characters.

==================================================
VIDEO RENDERING
==================================================

Use FFmpeg as the source of truth for final rendering.

Never rely on browser recording for production export.

Rendering pipeline:

source video
+
trim
+
crop
+
scale
+
captions
+
effects
+
audio
↓
FFmpeg
↓
H.264 / AAC
↓
MP4

Default:

1080x1920
30fps
H.264
AAC

Allow quality presets:

Fast
Balanced
High Quality

==================================================
FFMPEG CROP
==================================================

Build a rendering abstraction.

Do NOT scatter raw FFmpeg commands throughout the application.

Create:

VideoRenderer

with:

render_clip(project)
render_preview(project)
export_clip(project)

Create an intermediate representation:

RenderPlan

Example:

{
  "input": "...",
  "trim": {
    "start": 120.5,
    "end": 145.2
  },
  "crop": {
    "aspect_ratio": "9:16",
    "keyframes": [...]
  },
  "captions": {...},
  "effects": [...]
}

Then translate:

RenderPlan -> FFmpeg command/filter graph

This is important for maintainability.

==================================================
PREVIEW VS FINAL RENDER
==================================================

Do not render the entire video every time the user moves the crop.

Preview should use:

HTML5 video
+
CSS transform / canvas overlay

Final export uses:

FFmpeg

The preview and renderer must use the same coordinate system.

==================================================
PROJECT STORAGE
==================================================

Use SQLite.

Entities:

Project

Media

Transcript

TranscriptSegment

HookCandidate

Clip

FaceDetection

FaceTrack

CropKeyframe

Caption

RenderJob

Export

Example:

Project
  ├── Media
  ├── Transcript
  ├── HookCandidates
  ├── Clips
  │    ├── CropKeyframes
  │    └── Captions
  └── Exports

Do not store large video blobs in SQLite.

Store paths only.

==================================================
PROCESSING JOBS
==================================================

AI/video processing can take a long time.

Never block the UI.

Create job states:

queued
processing
completed
failed
cancelled

Example:

AnalysisJob

{
  "id": "...",
  "type": "transcription",
  "progress": 0.52,
  "status": "processing"
}

Expose progress to frontend.

Example:

Downloading video... 100%

Extracting audio... 100%

Transcribing... 64%

Detecting faces... 35%

Finding hooks... 80%

Generating clips... 100%

==================================================
CANCELLATION
==================================================

Every long-running process must support cancellation.

The user should be able to:

[Cancel]

without corrupting the project.

==================================================
LOCAL FILE SYSTEM
==================================================

Use a predictable project structure:

~/SmartClipper/

projects/
  project-id/
    project.db
    source/
    audio/
    transcript/
    analysis/
    thumbnails/
    previews/
    exports/

Do not expose arbitrary filesystem access to the frontend.

Use Tauri commands for filesystem operations.

==================================================
SECURITY
==================================================

This is a local application.

Still follow secure desktop architecture.

Frontend must not execute arbitrary shell commands.

Only backend/Tauri commands can invoke:

- FFmpeg
- yt-dlp
- Python
- Ollama

Validate every path.

Avoid shell injection.

Do not concatenate untrusted input directly into shell commands.

Use subprocess argument arrays.

==================================================
TAURI ARCHITECTURE
==================================================

Use:

Tauri 2
React
TypeScript

Frontend responsibilities:

- editor UI
- timeline
- player
- project management
- settings
- progress
- crop interaction

Tauri responsibilities:

- secure filesystem access
- process lifecycle
- launching local backend
- launching FFmpeg
- launching yt-dlp
- application packaging

Python responsibilities:

- transcription
- face detection
- tracking
- hook analysis
- local LLM orchestration
- video analysis

==================================================
PYTHON API
==================================================

Use FastAPI.

Suggested endpoints:

POST /projects

GET /projects

GET /projects/{id}

POST /projects/{id}/import

POST /projects/{id}/analyze

GET /projects/{id}/analysis

POST /projects/{id}/clips

GET /clips/{id}

PATCH /clips/{id}

POST /clips/{id}/smart-crop

POST /clips/{id}/generate-caption

POST /clips/{id}/preview

POST /clips/{id}/export

POST /jobs/{id}/cancel

GET /jobs/{id}

==================================================
REAL-TIME PROGRESS
==================================================

Use WebSocket or Server-Sent Events.

Example:

{
  "job_id": "...",
  "stage": "face_detection",
  "progress": 0.72
}

Frontend updates progress in real time.

==================================================
EDITOR STATE
==================================================

Use Zustand.

Do not put every video frame or huge analysis result into React state.

Keep:

UI state
editor state
project state
job state

separate.

==================================================
UI DESIGN
==================================================

Create a modern dark video-editor interface.

Visual direction:

- professional
- cinematic
- dark
- minimal
- high information density
- subtle borders
- purple/indigo accent
- rounded cards
- no excessive gradients
- no excessive glassmorphism

The UI should feel closer to:

professional video editor
+
AI workspace

rather than a generic SaaS dashboard.

==================================================
MAIN SCREENS
==================================================

1. Dashboard

Projects

[New Project]

Project cards:

thumbnail
title
duration
last edited
status

2. New Project

Paste YouTube URL

OR

[Import Video]

Then:

[Analyze Video]

3. AI Analysis

Show:

Video duration

Transcript

Detected faces

Potential hooks

Recommended clips

Example:

---------------------------------------
AI Recommended Clips
---------------------------------------

#1
Hook Score: 94
Duration: 32s

"Most developers make this mistake..."

[Preview]
[Edit]

#2
Hook Score: 89
Duration: 27s

"Nobody tells you this about Go..."

[Preview]
[Edit]

4. Clip Editor

Implement the UI shown in the reference image.

5. Export

Show:

Resolution
FPS
Format
Quality

[Export]

==================================================
AI RECOMMENDATION SCREEN
==================================================

The user should be able to select:

Auto-generate clips

or manually create clips.

Allow:

Number of clips:

3
5
10
15

Maximum duration:

30s
45s
60s
90s

Aspect ratio:

9:16
1:1
16:9

==================================================
PERFORMANCE
==================================================

The application must be optimized for Apple Silicon.

Target:

Mac M1
8GB RAM

Avoid loading multiple heavyweight AI models simultaneously.

Models should be loaded lazily.

Example:

Transcription model
  ↓
release when complete

Face detection
  ↓
release if not needed

LLM
  ↓
load only during hook analysis/caption generation

Do not keep unnecessary models resident in memory.

Use streaming/chunked processing where possible.

Avoid loading entire videos into RAM.

Use FFmpeg streaming/file-based processing.

==================================================
MODEL ABSTRACTION
==================================================

Create interfaces:

TranscriptionProvider
FaceDetectionProvider
LLMProvider
SceneDetectionProvider
EmbeddingProvider (future)

Do not hardcode the entire system around one model.

==================================================
FUTURE EXTENSIBILITY
==================================================

Design architecture so later we can add:

- speaker diarization
- automatic B-roll
- automatic zoom
- silence removal
- filler-word removal
- background music
- audio enhancement
- noise removal
- subtitle translation
- multi-language captions
- TikTok export
- Instagram Reels export
- YouTube Shorts export
- multiple aspect ratios
- multiple faces
- active speaker detection
- emotion detection
- semantic search
- project templates
- batch processing

==================================================
OBSERVABILITY
==================================================

Since this is a local application, keep observability lightweight.

Implement structured logs.

Example:

{
  "timestamp": "...",
  "level": "INFO",
  "component": "face_detector",
  "project_id": "...",
  "duration_ms": 142
}

Provide a developer log directory.

Do not introduce Kubernetes,
Kafka,
Redis,
microservices,
or cloud infrastructure.

This is intentionally a LOCAL MONOLITH / MODULAR DESKTOP APP.

==================================================
PROJECT ARCHITECTURE
==================================================

Use a modular architecture.

Suggested:

smart-clipper/
│
├── apps/
│   ├── desktop/
│   │   ├── src/
│   │   ├── src-tauri/
│   │   └── package.json
│   │
│   └── engine/
│       ├── app/
│       │   ├── api/
│       │   ├── domain/
│       │   ├── services/
│       │   ├── infrastructure/
│       │   └── workers/
│       │
│       ├── models/
│       ├── providers/
│       │   ├── whisper/
│       │   ├── ollama/
│       │   ├── face/
│       │   └── video/
│       │
│       └── main.py
│
├── packages/
│   ├── shared-types/
│   └── editor-model/
│
├── scripts/
│
├── models/
│
├── tests/
│
└── README.md

==================================================
IMPORTANT ENGINEERING RULE
==================================================

Do not build a fake prototype where buttons only change UI state.

Every important feature must have a real implementation.

For example:

"Smart Crop"

must actually:

1. Detect face
2. Track face
3. Generate crop trajectory
4. Save crop keyframes
5. Display crop in preview
6. Allow manual editing
7. Convert crop configuration into FFmpeg rendering instructions
8. Produce the correct exported video

Similarly:

"Find Viral Hooks"

must actually:

1. Use transcript
2. Generate candidates
3. Score candidates
4. Store candidates
5. Display timestamps
6. Allow preview
7. Create clip from selected candidate

==================================================
TESTING
==================================================

Implement tests for:

- crop calculations
- aspect ratio calculations
- crop boundaries
- keyframe interpolation
- face smoothing
- hook scoring
- transcript segmentation
- caption segmentation
- FFmpeg RenderPlan generation
- project persistence
- job lifecycle

Create fixture videos for integration tests.

==================================================
DEVELOPMENT PHASES
==================================================

Do NOT attempt to build everything simultaneously.

Implement in phases.

PHASE 1:

Desktop shell

React
Tauri
FastAPI

Video import

Video player

SQLite project

Basic timeline

==================================================

PHASE 2:

YouTube

yt-dlp

FFmpeg

Local video processing

==================================================

PHASE 3:

Whisper transcription

Transcript UI

Timestamp navigation

==================================================

PHASE 4:

Face detection

Face tracking

Smart crop

Crop preview

==================================================

PHASE 5:

Editable crop timeline

Keyframes

Manual override

Reset to AI

==================================================

PHASE 6:

Hook detection

Local Ollama

Qwen3

Candidate clips

Hook scoring

==================================================

PHASE 7:

Caption generation

Caption editor

Caption styling

==================================================

PHASE 8:

FFmpeg renderer

Preview rendering

Final export

==================================================

PHASE 9:

Performance optimization

Apple Silicon optimization

Model lifecycle

Caching

Parallel processing where safe

==================================================

PHASE 10:

Packaging

Tauri application bundle

Python sidecar

FFmpeg

yt-dlp

Model setup

First-run setup wizard

==================================================
FIRST RUN EXPERIENCE
==================================================

When the application starts for the first time:

Check:

FFmpeg
yt-dlp
Python runtime
Ollama
required models

Show:

System Ready

or:

Missing dependency

[Install / Setup]

The application should explain which models are installed.

Example:

AI Models

✓ Whisper
✓ Qwen3 4B
✓ MediaPipe Face Detection

==================================================
NO CLOUD DEPENDENCY
==================================================

Core functionality MUST work without:

OpenAI
Anthropic
Gemini
Replicate
AWS
GCP
Azure

Cloud integrations may be added later as optional providers.

==================================================
DELIVERABLE
==================================================

Build a working application, not just documentation.

Start by creating:

1. architecture
2. repository structure
3. database schema
4. domain models
5. Tauri shell
6. React editor UI
7. FastAPI engine
8. video import
9. FFmpeg integration

Then progressively implement the AI pipeline.

After each phase:

- run tests
- run lint
- run type checking
- verify the application manually
- fix errors before continuing

Do not leave TODO implementations for core features.

Prioritize working end-to-end functionality over visual polish.

The final application should allow this complete flow:

YouTube URL
    ↓
Download
    ↓
Analyze
    ↓
Transcript
    ↓
Find best hooks
    ↓
Generate clips
    ↓
Detect faces
    ↓
Smart 9:16 crop
    ↓
Generate captions
    ↓
User manually adjusts crop
    ↓
Preview
    ↓
Export MP4

The result should be a serious local AI video editor rather than
a simple CRUD dashboard.
