import { useRef, useState, useEffect, useCallback } from "react";
import { useEditorStore } from "../stores/editor";
import { updateKeyframes } from "../lib/api";

// ponytail: linear interp, cukup untuk follow wajah saat play
export function interpolateKeyframes(kfs: any[], t: number) {
  if (!kfs.length) return { cx: 0.5, cy: 0.5 };
  const sorted = [...kfs].sort((a, b) => a.time - b.time);
  if (t <= sorted[0].time) return { cx: sorted[0].center_x, cy: sorted[0].center_y };
  for (let i = 1; i < sorted.length; i++) {
    if (t <= sorted[i].time) {
      const p = sorted[i - 1], c = sorted[i];
      const span = Math.max(c.time - p.time, 0.001);
      const f = (t - p.time) / span;
      return { cx: p.center_x + f * (c.center_x - p.center_x), cy: p.center_y + f * (c.center_y - p.center_y) };
    }
  }
  const last = sorted[sorted.length - 1];
  return { cx: last.center_x, cy: last.center_y };
}

// speaker pada waktu t: keyframe terakhir <= t yang punya speaker
function speakerAt(kfs: any[], t: number): string | null {
  let spk: string | null = null;
  for (const k of [...kfs].sort((a, b) => a.time - b.time)) {
    if (k.time <= t + 0.001 && k.speaker) spk = k.speaker;
    else if (k.time > t) break;
  }
  return spk;
}

export function cropNormW(vw: number, vh: number, aspect: string) {
  const [aw, ah] = aspect.split(":").map(Number);
  if (!vw || !vh || !aw || !ah) return 606 / 1920; // fallback 9:16 @1080p
  const target = aw / ah, src = vw / vh;
  // ponytail: samakan dengan backend crop_window (round_even) agar preview == hasil FFmpeg
  if (target < src) return Math.floor((vh * target) / 2) * 2 / vw;
  return 1;
}

export default function CropOverlay() {
  const { keyframes, currentTime, clip, videoRef } = useEditorStore();
  const boxRef = useRef<HTMLDivElement>(null);
  const [vidSize, setVidSize] = useState({ w: 1280, h: 720 });
  const [saving, setSaving] = useState(false);
  const drag = useRef<{ startX: number; baseCx: number } | null>(null);

  useEffect(() => {
    const v = videoRef?.current;
    if (!v) return;
    const upd = () => v.videoWidth && setVidSize({ w: v.videoWidth, h: v.videoHeight });
    v.addEventListener("loadedmetadata", upd);
    upd();
    return () => v.removeEventListener("loadedmetadata", upd);
  }, [videoRef, clip?.id]);

  const aspect = clip?.aspect_ratio || "9:16";
  const crop = interpolateKeyframes(keyframes, currentTime);
  const spkNow = speakerAt(keyframes, currentTime);
  const spkPrev = speakerAt(keyframes, currentTime - 0.6);
  // ponytail: flash amber hanya jika pindah ORANG (posisi crop ikut loncat),
  // bukan ganti label di wajah yang sama
  const cxPrev = interpolateKeyframes(keyframes, currentTime - 0.6).cx;
  const justSwitched = !!(spkNow && spkPrev && spkNow !== spkPrev) && Math.abs(crop.cx - cxPrev) > 0.08;
  const nw = cropNormW(vidSize.w, vidSize.h, aspect);
  const half = nw / 2;
  const cx = Math.max(half, Math.min(1 - half, crop.cx));
  const left = (cx - half) * 100;

  const upsert = useCallback((nx: number) => {
    const st = useEditorStore.getState();
    const kfs = [...st.keyframes].sort((a, b) => a.time - b.time);
    const t = st.currentTime;
    const idx = kfs.findIndex((k) => Math.abs(k.time - t) < 0.15);
    let next;
    if (idx >= 0) next = kfs.map((k, i) => (i === idx ? { ...k, center_x: nx, source: "manual" } : k));
    else {
      next = [...kfs, { time: Math.round(t * 100) / 100, center_x: nx, center_y: 0.5, source: "manual" }].sort((a, b) => a.time - b.time);
    }
    st.setKeyframes(next);
    return next;
  }, []);

  const persist = useCallback(async (kfs: any[]) => {
    const clipId = useEditorStore.getState().clip?.id;
    if (!clipId) return;
    setSaving(true);
    try { await updateKeyframes(clipId, kfs); } catch {} finally { setSaving(false); }
  }, []);

  const onCropDown = (e: React.MouseEvent) => {
    e.stopPropagation();
    drag.current = { startX: e.clientX, baseCx: cx };
    const onMove = (ev: MouseEvent) => {
      if (!drag.current || !boxRef.current) return;
      const rect = boxRef.current.getBoundingClientRect();
      const dxN = (ev.clientX - drag.current.startX) / rect.width;
      upsert(Math.max(half, Math.min(1 - half, drag.current.baseCx + dxN)));
    };
    const onUp = () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
      if (drag.current) persist(useEditorStore.getState().keyframes);
      drag.current = null;
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };

  if (!clip) return null;

  return (
    <div ref={boxRef} data-testid="smart-crop" style={{ position: "absolute", inset: 0, overflow: "hidden", borderRadius: 8 }}>
      {/* dim 4 sisi agar lubang crop jernih */}
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${left}%`, background: "rgba(0,0,0,0.55)" }} />
      <div style={{ position: "absolute", top: 0, bottom: 0, left: `${left + nw * 100}%`, right: 0, background: "rgba(0,0,0,0.55)" }} />
      {/* rectangle ungu smart crop */}
      <div
        onMouseDown={onCropDown}
        data-testid="smart-crop-rect"
        style={{
          position: "absolute", left: `${left}%`, top: 0, width: `${nw * 100}%`, height: "100%",
          border: `2px solid ${justSwitched ? "#f59e0b" : "#8b5cf6"}`, borderRadius: 4, cursor: "ew-resize", touchAction: "none",
        }}
      >
        <div style={{ position: "absolute", top: 6, left: "50%", transform: "translateX(-50%)", background: justSwitched ? "#f59e0b" : "#6366f1", color: "#fff", fontSize: 10, fontWeight: 700, padding: "1px 8px", borderRadius: 4 }}>
          {aspect}{spkNow ? ` · ${spkNow}` : ""}{saving ? " •" : ""}
        </div>
      </div>
    </div>
  );
}
