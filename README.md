# Smart Clipper ✂️

Editor video AI yang jalan 100% lokal. Mirip OpusClip tapi tanpa cloud, tanpa upload, bisa offline.

Tempel link YouTube → otomatis jadi clip vertikal 9:16 lengkap dengan caption.

## Fitur

- Import YouTube (yt-dlp) + file lokal (MP4/MOV/MKV/WebM)
- Transkrip offline pakai mlx-whisper
- Deteksi hook + skor potensi viral 0-100
- Deteksi + tracking wajah (MediaPipe + OpenCV) dengan smoothing anti-jitter
- Active speaker v1: crop ngikutin yang lagi ngomong, bukan wajah paling gede
- Smart crop 9:16 / 1:1 / 16:9 dengan keyframe timeline
- Manual reframe (drag) yang tidak ketimpa AI + tombol Reset to AI
- Caption otomatis dari word timestamp + editor teks
- Preview pakai Remotion, export beneran pakai FFmpeg (H.264/AAC, 1080x1920)
- Progress realtime via SSE, semua job bisa di-cancel

## Tech Stack

| Layer | Teknologi |
|---|---|
| Frontend | React 19 + Vite + TypeScript + Zustand + Remotion Player |
| Backend | FastAPI (Python 3.12) + SQLite + SSE |
| AI / CV | mlx-whisper large-v3-turbo, MediaPipe, OpenCV, Ollama Qwen3 4B, Groq (enrich hook) |
| Video | FFmpeg, yt-dlp |

Target: Mac M1 8GB. Model di-load malas (lazy), tidak sekaligus, biar hemat RAM.

## Cara Jalan

Prasyarat: `uv`, `node 20+`, `ffmpeg`, `yt-dlp`, Ollama (opsional, untuk hook scoring).

```bash
make install
make dev
```

- Backend: http://127.0.0.1:8719
- Frontend: http://localhost:5173 (lihat output vite)

Perintah lain:

```bash
make be      # backend saja
make fe      # frontend saja
make test    # pytest backend
make lint    # oxlint frontend
make build   # build frontend ke apps/desktop/dist
make stop    # matikan backend + vite
```

## Alur Pakai

1. Buka frontend → New Project
2. Tempel URL YouTube atau import file lokal
3. Klik Analyze Video → tunggu transcript + hook + face tracking selesai
4. Pilih clip dari skor tertinggi → buka Editor
5. Geser crop manual kalau perlu, edit caption, atur gaya teks
6. Export → dapat MP4 vertikal siap upload ke Shorts/Reels/TikTok

## Arsitektur

```
apps/desktop/src/      # React editor (preview, timeline, crop overlay, stores zustand)
apps/engine/app/
  api/                 # FastAPI routes: projects, clips, jobs, from_hooks
  services/            # import, vision, speaker, render
  providers/           # whisper, face, llm (mudah ditukar)
  domain/              # crop math, smoothing, hooks scoring, captions
  db.py jobs.py        # SQLite + job lifecycle (queued/processing/completed/failed/cancelled)
data/                  # projects/, media/, audio/, transcripts/, renders/ (gitignored sebagian)
```

Pipeline AI:

```
Video → Download/Import → Audio → Whisper → Segmentasi →
Face Detect → Tracking + Smoothing → Active Speaker →
Hook Scoring → Kandidat Clip → Smart Crop → Caption →
User Edit → FFmpeg Render → Export
```

Catatan penting:

- Preview (Remotion/CSS) dan export (FFmpeg) pakai sistem koordinat yang sama.
- Crop disimpan sebagai keyframe beneran (`time, center_x, center_y, speaker`), bukan sekadar posisi CSS.
- `manually_modified = true` kalau user drag crop, jadi AI tidak menimpa editan.

## Testing

```bash
cd apps/engine && uv run pytest
```

Mencakup: crop math, keyframe interpolasi, smoothing, speaker hysteresis, hook scoring, caption segmentation, RenderPlan FFmpeg, persistensi project.

## Status

Aktif dikembangkan. Lihat `PRD.md` untuk spesifikasi penuh dan roadmap fase 1-10.
