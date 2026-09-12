# Viral Hook via Groq — Design (Approach B, hook-cepat + enrich lazy)

Tanggal: 2026-09-12. Status: disetujui user per bagian (B1–B4).

## 1. Tujuan & alur
Paste YouTube URL → AI cari Top-N hook viral (default 3, max durasi default 60s) → user preview + multi-select → masuk Editor → Export.
Opsi fleksibel PRD: jumlah 3/5/10/15, durasi 30/45/60/90s, rasio 9:16/1:1/16:9.

## 2. Pipeline 2 tahap (B1, revisi: Groq, tanpa Qwen lokal)
Tahap 1 HOOK-FAST:
1. yt-dlp download → FFmpeg ekstrak audio 16kHz mono WAV.
2. Whisper lokal (mlx-whisper, prefer large-v3-turbo) → Transcript + word timestamps. Model di-release setelah selesai (hemat RAM).
3. Transcript utuh (teks + timestamps kata) dikirim ke Groq via `LLMProvider/GroqProvider` (default model `llama-3.3-70b-versatile`, API key dari server `.env`/Settings; hanya teks yang keluar, video tetap lokal).
4. Prompt terstruktur meminta Top-N momen: `start/end` presisi detik, `score` 0–100, `hook_text`, `reasons[]`, `weakness`. Kriteria: curiosity, emotional intensity, strong/contrarian claim, surprise, conflict, payoff, educational value, specificity, question/open-loop, self-contained, fast payoff.
5. Validasi server-side: clamp durasi ≤ max_duration, snap start/end ke word boundary terdekat, dedupe overlap (IoU > 0.5 → ambil skor tertinggi), sort desc.
6. Fallback: Groq error (no key, offline, rate-limit, invalid JSON) → skor heuristik murni lokal + flag `source: heuristic` + banner UI.

Tahap 2 ENRICH-LAZY (hanya hook yang dicentang user):
face detect MediaPipe → IoU tracking + EMA smoothing + active-speaker hysteresis (ikut spec PRD §ACTIVE SPEAKER) → smart crop keyframes → caption dari word timestamps → Clip siap editor.
Tanpa model LLM lokal; Whisper dan face tidak pernah resident barengan.

Non-goals: Qwen3 4B / Ollama lokal (dicoret user), diarization, auto-zoom, B-roll.

## 3. Backend API + DB (B2)
Reuse FastAPI + SQLite existing. Tambahan:
- `POST /projects` body += `clip_count`, `max_duration`, `aspect_ratio`.
- `POST /projects/{id}/analyze` → job cancellable 2 fase (`transcribe` → `groq-hooks`), progress via SSE yang sudah ada (`stage`, `progress`), `POST /jobs/{id}/cancel` reuse.
- `GET /projects/{id}/hooks` → daftar HookCandidate.
- `POST /projects/{id}/clips/from-hooks {hook_ids[]}` → enrich lazy → create Clips + CropKeyframes + Captions.
- `HookCandidate` += `llm_model TEXT NULL`, `llm_raw TEXT NULL` (debug), `source TEXT DEFAULT 'groq'`.
- `LLMProvider` interface: `find_hooks(transcript, n, max_dur)`. Implementasi: `GroqProvider` (urllib, tanpa dep baru bila bisa; retry 2x + JSON-repair) dan `HeuristicProvider` (fallback). API key tidak pernah dikirim ke frontend.

## 4. Frontend (B3)
- Dashboard form += opsi count/duration/ratio → `Analyze Video` → layar progress (tahap + % + Cancel).
- Screen baru `ClipPicker` (`/pick/:projectId`): kartu per hook (rank, score, durasi, hook text, reasons, weakness), preview video asli (`GET /api/media/{pid}/video`, seek ke start), checkbox multi-select, tombol `Edit N terpilih`.
- Editor existing tidak diubah kecuali menerima N clips; Export per klip via FFmpeg/RenderPlan existing.

## 5. Robustness & testing (B4)
- Groq gagal → fallback heuristik + banner "LLM unavailable, pakai skor lokal".
- Long video: transcript di-chunk per ~15 menit kata, 1 request per chunk (atau gabung bila muat), merge + dedupe global.
- Semua job cancellable tanpa korup project; path tervalidasi (tanpa shell injection, arg array).
- Tests: clamp/snap/dedupe hook; fallback saat LLM mati; from-hooks hanya enrich terpilih; RenderPlan FFmpeg tak berubah; GroqProvider di-mock.

## 6. Self-review
- Placeholder: tidak ada; model default eksplisit, fallback eksplisit.
- Konsistensi: video lokal-only kecuali teks transcript ke Groq — dinyatakan di §2 dan §3.
- Scope: satu spek (picker + groq hooks + lazy enrich); tidak merambah efek/caption styling baru.
- Ambiguitas diputuskan: default 3 × 60s 9:16; multi-select; Export tetap di Editor.
