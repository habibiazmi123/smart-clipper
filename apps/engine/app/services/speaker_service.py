"""Active-speaker detection v1 (PRD ACTIVE SPEAKER).

Heuristic, local, no extra models:
- stable face track IDs via IoU matching
- mouth-motion proxy: mean abs frame-diff in lower-third of face box
- speech gate: WAV RMS energy and/or Whisper word timing
- hysteresis: brief interjections ("hmm", "oh") must NOT steal the crop

Single visible face -> that face, no switching logic.
Uncertain -> keep current framing (never rapid switching).
"""

import logging
import wave
import time

import cv2
import numpy as np

from app.config import settings

log = logging.getLogger(__name__)


def _box_iou(a: dict, b: dict) -> float:
    ax1, ay1 = a["x"] - a["w"] / 2, a["y"] - a["h"] / 2
    ax2, ay2 = a["x"] + a["w"] / 2, a["y"] + a["h"] / 2
    bx1, by1 = b["x"] - b["w"] / 2, b["y"] - b["h"] / 2
    bx2, by2 = b["x"] + b["w"] / 2, b["y"] + b["h"] / 2
    ix = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    iy = max(0.0, min(ay2, by2) - max(ay1, by1))
    union = a["w"] * a["h"] + b["w"] * b["h"] - ix * iy
    return (ix * iy / union) if union > 0 else 0.0


def _next_id(used: set) -> str:
    for i in range(26):
        c = chr(ord("A") + i)
        if c not in used:
            return c
    n = 2
    while f"A{n}" in used:
        n += 1
    return f"A{n}"


def mouth_energy(gray1: np.ndarray, gray2: np.ndarray, box: dict, baseline: float = 0.0) -> float:
    """Mean abs diff in lower-third of face box (mouth region heuristic),
    minus global-frame motion baseline. Tanpa baseline, anggukan pendengar
    / goyangan kamera ikut terbaca sebagai 'berbicara' dan nyuri crop."""
    H, W = gray1.shape
    # ponytail: box x/y = TITIK TENGAH wajah (face_provider). Dulu dipakai
    # langsung sebagai pojok kiri-atas -> ROI mulut geser setengah wajah
    # ke kanan-bawah (sampel pipi/background, bukan mulut).
    x, y = int((box["x"] - box["w"] / 2) * W), int((box["y"] - box["h"] / 2) * H)
    w, h = int(box["w"] * W), int(box["h"] * H)
    y0, y1 = max(y + 2 * h // 3, 0), y + h
    x0, x1 = max(x, 0), x + w
    r1, r2 = gray1[y0:y1, x0:x1], gray2[y0:y1, x0:x1]
    if r1.size == 0:
        return 0.0
    raw = float(np.abs(r1.astype(np.int16) - r2.astype(np.int16)).mean())
    return max(0.0, raw - baseline)


def load_wav_mono(path: str) -> tuple[np.ndarray, int]:
    """Load 16-bit mono WAV as float32 -1..1. Returns (samples, rate)."""
    with wave.open(path, "rb") as w:
        n, rate, ch = w.getnframes(), w.getframerate(), w.getnchannels()
        raw = w.readframes(n)
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return a, rate


def window_rms(samples: np.ndarray, rate: int, t0: float, t1: float) -> float:
    s = samples[int(t0 * rate):int(t1 * rate)]
    return float(np.sqrt((s ** 2).mean())) if len(s) else 0.0


class SpeakerTracker:
    """Stateful per-clip tracker. Call update() once per sample, in time order."""

    def __init__(self, switch_margin=None, min_dwell_sec=None, hold_sec=None,
                 silence_rms=None, mouth_alpha=None, iou_threshold=None,
                 sample_interval=0.5):
        import math
        self.margin = switch_margin if switch_margin is not None else settings.SPEAKER_SWITCH_MARGIN
        dwell_s = min_dwell_sec if min_dwell_sec is not None else settings.SPEAKER_MIN_DWELL_SEC
        hold_s = hold_sec if hold_sec is not None else settings.SPEAKER_HOLD_SEC
        # ponytail: dwell/hold dalam DETIK bukan window, agar konsisten
        # untuk sampling 0.1s (pipeline) maupun 0.5s (preview)
        self.dwell = max(2, math.ceil(dwell_s / sample_interval))
        self.hold = max(1, round(hold_s / sample_interval))
        self.silence = silence_rms if silence_rms is not None else settings.SPEAKER_SILENCE_RMS
        self.alpha = mouth_alpha if mouth_alpha is not None else settings.SPEAKER_MOUTH_ALPHA
        self.iou_thr = iou_threshold if iou_threshold is not None else settings.SPEAKER_IOU_THRESHOLD
        self.tracks: dict[str, dict] = {}
        self.used_ids: set[str] = set()  # huruf tidak dipakai ulang: A tetap orang yang sama
        self.current: str | None = None
        self.last_pos: dict = {"cx": 0.5, "cy": 0.5}
        self.misses = 0
        self.challenger: str | None = None
        self.wins = 0

    def update(self, faces: list[dict], mouth: dict[int, float],
               speaking: bool, t: float) -> dict | None:
        """faces: [{x,y,w,h,confidence}] normalized. mouth: face_idx -> energy."""
        if not faces:
            # bingkai kosong = pembicara hilang: tahan dulu, lalu lepas
            self.misses += 1
            if self.misses <= self.hold and self.current is not None:
                return {"speaker": self.current, "cx": self.last_pos["cx"],
                        "cy": self.last_pos["cy"], "confidence": 0.5,
                        "time": round(t, 3)}
            return None
        # umur track SEBELUM update sampel ini (untuk takeover stale)
        prev_seen = {tid: tr.get("last_seen", t) for tid, tr in self.tracks.items()}
        stale_after = settings.SPEAKER_STALE_TAKEOVER_SEC
        # track basi dibuang; ingat cukup lama agar orang yang kembali = ID sama
        mem = settings.SPEAKER_TRACK_MEMORY_SEC
        for tid in [k for k, tr in self.tracks.items() if t - tr.get("last_seen", t) > mem]:
            del self.tracks[tid]
            if self.challenger == tid:
                self.challenger, self.wins = None, 0
        # 1. IoU match -> stable ids, centroid fallback untuk lompatan cepat
        assigned: dict[int, str] = {}
        for i, f in enumerate(faces):
            best_id, best_iou = None, self.iou_thr
            for tid, tr in self.tracks.items():
                iou = _box_iou(f, tr)
                if iou >= best_iou:
                    best_id, best_iou = tid, iou
            if best_id is None:
                # wajah sama yang bergeser cepat: centroid dekat -> id sama.
                # 0.15 = ayunan kepala cepat; wajah beda orang umumnya >=0.3.
                best_dist, best_tid = 0.15, None
                for tid, tr in self.tracks.items():
                    d = abs(f["x"] - tr["x"]) + abs(f["y"] - tr["y"])
                    if d < best_dist:
                        best_dist, best_tid = d, tid
                best_id = best_tid
            # ponytail: POST-MATCH CUT DETECTION. Centroid fallback bisa
            # salah match wajah B ke track A (jarak < 0.15) saat A dropout
            # dan B muncul di posisi mirip. Kalau wajah yang match berpindah
            # jauh dari posisi terakhir track-nya, itu CUT → buat ID baru.
            if best_id is not None:
                prev_tr = self.tracks[best_id]
                jump = abs(f["x"] - prev_tr["x"]) + abs(f["y"] - prev_tr["y"])
                if jump > 0.18:
                    best_id = None  # force buat ID baru
            if best_id is None:
                best_id = _next_id(self.used_ids)
                self.used_ids.add(best_id)
                self.tracks[best_id] = {"mouth_ema": 0.0}
            assigned[i] = best_id
            tr = self.tracks[best_id]
            tr.update({k: f[k] for k in ("x", "y", "w", "h", "confidence")})
            tr["last_seen"] = t
            e = mouth.get(i, 0.0)
            tr["mouth_ema"] = self.alpha * e + (1 - self.alpha) * tr.get("mouth_ema", 0.0)

        visible = [assigned[i] for i in range(len(faces))]
        visible = list(dict.fromkeys(visible))  # duplikat deteksi -> satu id

        # ponytail: INSTANT SWITCH untuk camera cut.
        # Podcast/ interview punya cut cepat (1-2 detik). Tanpa ini,
        # dwell 1.5s tidak pernah selesai → crop stuck di posisi lama
        # sampai 1.2 detik setelah wajah baru muncul (glitch terlihat).
        # Aturan: wajah baru yang TIDAK match ke track manapun (= orang baru)
        # muncul di posisi jauh dari current speaker = CUT langsung.
        # Kalau match ke existing track = dropout biasa, tahan.
        pre_existing = set(self.tracks.keys())
        if len(visible) == 1 and self.current is not None:
            solo = visible[0]
            solo_tr = self.tracks[solo]
            if solo not in pre_existing:
                cur_tr = self.tracks.get(self.current)
                if cur_tr:
                    jump = abs(solo_tr["x"] - cur_tr["x"]) + abs(solo_tr["y"] - cur_tr["y"])
                else:
                    jump = abs(solo_tr["x"] - self.last_pos["cx"]) + abs(solo_tr["y"] - self.last_pos["cy"])
                if jump > 0.15:
                    self.current = solo
                    self.last_pos = {"cx": solo_tr["x"], "cy": solo_tr["y"]}
                    self.misses = 0
                    self.challenger, self.wins = None, 0
                    return {"speaker": self.current, "cx": solo_tr["x"], "cy": solo_tr["y"],
                            "confidence": 0.9, "time": round(t, 3)}

        # 2. score (mouth relative antar wajah yang terlihat)
        peak = max(self.tracks[tid]["mouth_ema"] for tid in visible)
        scores = {}
        for i, tid in enumerate(visible):
            tr = self.tracks[tid]
            mouth_s = (tr["mouth_ema"] / peak) if peak > 0.5 else 0.0
            size_s = min(tr["w"] * tr["h"] / 0.06, 1.0)
            center_s = max(0.0, 1 - abs(tr["x"] - 0.5) * 2)
            cont = 1.0 if tid == self.current else 0.0
            scores[tid] = mouth_s * 0.5 + size_s * 0.2 + center_s * 0.1 + cont * 0.2

        # 3. hysteresis: tanggapan singkat tidak boleh switch,
        # wajah hilang sesaat (dropout) -> tahan dulu, jangan loncat
        if self.current not in visible:
            self.misses += 1
            # ponytail: INSTANT SWITCH saat current hilang + wajah lain jauh.
            # Camera cut sering diikuti blackout (detector kehilangan semua wajah
            # 0.5-1.5 detik). Saat wajah baru muncul, dwell tidak pernah selesai
            # karena kita sudah melewati 'hold' window → crop stuck 1+ detik.
            # Fix: kalau ada wajah terlihat DAN posisinya jauh dari posisi terakhir
            # (= camera cut, bukan dropout sesaat), switch langsung.
            # HANYA untuk wajah baru (bukan match existing track = dropout biasa).
            if self.misses > self.hold and visible:
                best = max(visible, key=lambda tid: scores[tid])
                if best not in pre_existing:
                    solo_tr = self.tracks[best]
                    jump = abs(solo_tr["x"] - self.last_pos["cx"]) + abs(solo_tr["y"] - self.last_pos["cy"])
                    if jump > 0.15:
                        self.current = best
                        self.last_pos = {"cx": solo_tr["x"], "cy": solo_tr["y"]}
                        self.misses = 0
                        self.challenger, self.wins = None, 0
                        return {"speaker": self.current, "cx": solo_tr["x"], "cy": solo_tr["y"],
                                "confidence": 0.9, "time": round(t, 3)}
            if self.misses <= self.hold and self.current is not None:
                return {"speaker": self.current, "cx": self.last_pos["cx"],
                        "cy": self.last_pos["cy"], "confidence": 0.5,
                        "time": round(t, 3)}
            best = max(visible, key=lambda tid: scores[tid])
            if t - prev_seen.get(best, t) > stale_after:
                # wajah muncul setelah jeda (shot cut / orang baru):
                # ID baru, jangan warisi identitas basi
                nid = _next_id(self.used_ids)
                self.used_ids.add(nid)
                btr = self.tracks[best]
                self.tracks[nid] = {k: btr[k] for k in ("x", "y", "w", "h", "confidence")
                                    if k in btr}
                self.tracks[nid].update(mouth_ema=0.0, last_seen=t)
                scores[nid] = scores[best_id]
                best = nid
            self.current = best
            self.misses = 0
            self.challenger, self.wins = None, 0
        elif len(visible) == 1:
            self.current = visible[0]
            self.misses = 0
            self.challenger, self.wins = None, 0
        elif speaking:
            self.misses = 0
            others = [tid for tid in visible if tid != self.current]
            chal = max(others, key=lambda tid: scores[tid])
            if scores[chal] > scores[self.current] + self.margin:
                if self.challenger == chal:
                    self.wins += 1
                else:
                    self.challenger, self.wins = chal, 1
                if self.wins >= self.dwell:
                    self.current = chal
                    self.challenger, self.wins = None, 0
            else:
                self.challenger, self.wins = None, 0
        else:
            self.misses = 0

        tr = self.tracks[self.current]
        self.last_pos = {"cx": tr["x"], "cy": tr["y"]}
        runner = max((scores[tid] for tid in visible if tid != self.current), default=0.0)
        conf = round(min(0.99, 0.5 + max(0.0, scores[self.current] - runner)), 2)
        return {"speaker": self.current, "cx": tr["x"], "cy": tr["y"],
                "confidence": conf, "time": round(t, 3)}


def analyze_clip_speakers(video_path: str, detector, start: float, end: float,
                           wav: tuple | None = None, transcript_segs: list | None = None,
                           sample_interval: float | None = None,
                           tracker: "SpeakerTracker | None" = None) -> list[dict]:
    """Per-clip pass. Berbagi satu tracker lintas clip = ID konsisten
    (orang sama = huruf sama) selama framing kontinu. Returns
    [{time, cx, cy, speaker, sconf}]."""
    log.info("[crop] clip [%.1f-%.1f] analyze start", start, end)
    t0 = time.time()
    interval = sample_interval or settings.FACE_SAMPLE_INTERVAL
    mouth_dt = settings.SPEAKER_MOUTH_DT
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    if tracker is None:
        tracker = SpeakerTracker(sample_interval=interval)
    from app.providers.face_provider import detect_faces_frame
    # ponytail: SATU seek ke awal + baca berurutan. Sebelumnya 2x seek per
    # sampel (t dan t+dt): lambat (decode-ulang dari keyframe tiap sampel)
    # dan rapuh di file corrupt (seek mendarat di frame salah -> pasangan
    # mouth ngaco -> speaker salah). Buffer kecil menyimpan gray terakhir
    # untuk pasangan mouth (t vs t-dt, setara t vs t+dt untuk gerak mulut).
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, int(start * fps)))
    frame_idx = max(0, int(start * fps))
    buf: list[tuple[float, np.ndarray]] = []  # (waktu_frame, gray)
    keep = mouth_dt + interval + 1.0 / max(fps, 1.0)
    out = []
    t = start
    while t < end:
        target = int(t * fps)
        f1 = None
        while True:
            if frame_idx >= target:
                ret, frm = cap.read()
                if not ret:
                    break
                frame_idx += 1
                g = cv2.cvtColor(frm, cv2.COLOR_BGR2GRAY)
                buf.append((frame_idx / fps, g))
                while len(buf) > 2 and buf[0][0] < t - keep:
                    buf.pop(0)
                f1 = frm
                gray1 = g
                break
            ret, frm = cap.read()
            if not ret:
                break
            frame_idx += 1
            g = cv2.cvtColor(frm, cv2.COLOR_BGR2GRAY)
            buf.append((frame_idx / fps, g))
            while len(buf) > 2 and buf[0][0] < t - keep:
                buf.pop(0)
        if f1 is None:
            break
        # pasangan mouth: gray terdekat dengan t-dt dari buffer
        gray2 = min(buf, key=lambda bg: abs(bg[0] - (t - mouth_dt)))[1] if buf else gray1
        faces = detect_faces_frame(detector, cv2.cvtColor(f1, cv2.COLOR_BGR2RGB), t)
        # ponytail: baseline gerak global sekali per sampel; yang dihitung
        # sebagai mulut hanya gerak RELATIF terhadap goyangan kamera/kepala
        baseline = float(np.abs(gray1.astype(np.int16) - gray2.astype(np.int16)).mean())
        mouth = {i: mouth_energy(gray1, gray2, b, baseline) for i, b in enumerate(faces)}
        speaking = True
        if wav is not None:
            speaking = window_rms(wav[0], wav[1], t, t + interval) > settings.SPEAKER_SILENCE_RMS
        if transcript_segs:
            speaking = speaking or any(s["start"] < t + interval and s["end"] > t for s in transcript_segs)
        r = tracker.update(faces, mouth, speaking, t)
        if r:
            out.append({"time": r["time"], "cx": r["cx"], "cy": r["cy"],
                        "speaker": r["speaker"], "sconf": r["confidence"]})
        else:
            # ponytail: PRD fallback = previous crop sebelum center crop;
            # tengah frame shot lebar dua orang = ruang kosong, tahan posisi
            # terakhir agar tidak loncat ke tengah saat wajah hilang lama
            out.append({"time": round(t, 3), "cx": tracker.last_pos["cx"], "cy": tracker.last_pos["cy"],
                        "speaker": None, "sconf": 0.0})
        t += interval
    cap.release()
    log.info("[crop] clip [%.1f-%.1f] done samples=%d speakers=%s took=%.1fs",
             start, end, len(out),
             sorted(s for s in set(x["speaker"] for x in out) if s is not None),
             time.time() - t0)
    return out
