import { useRef, useState, useEffect, useCallback } from "react";
import { useEditorStore } from "../stores/editor";
import { updateKeyframes, deleteKeyframe } from "../lib/api";
import { speakerColor } from "../lib/speakers";

// ponytail: linear interp, cukup untuk follow wajah saat play.
// Ganti orang = CUT (tahan posisi lama sampai batas keyframe), glide
// hanya untuk gerakan orang yang sama. Mirror build_crop_expr backend.
function isSwitch(a: any, b: any): boolean {
  if (a?.source === "manual" || b?.source === "manual") return false;
  if (a?.speaker == null || b?.speaker == null) return true;
  return a.speaker !== b.speaker;
}

export function interpolateKeyframes(kfs: any[], t: number) {
  if (!kfs.length) return { cx: 0.5, cy: 0.5 };
  const sorted = [...kfs].sort((a, b) => a.time - b.time);
  if (t < sorted[0].time) return { cx: sorted[0].center_x, cy: sorted[0].center_y };
  for (let i = 1; i < sorted.length; i++) {
    if (t < sorted[i].time) {
      const p = sorted[i - 1], c = sorted[i];
      if (isSwitch(p, c)) return { cx: p.center_x, cy: p.center_y };
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
  const { keyframes, currentTime, clip, videoRef, setKeyframes } = useEditorStore();
  const boxRef = useRef<HTMLDivElement>(null);
  const [vidSize, setVidSize] = useState({ w: 1280, h: 720 });
  const [saving, setSaving] = useState(false);
  const drag = useRef<{ startX: number; baseCx: number } | null>(null);

  const hasManualAtCurrentTime = (() => {
    const t = Math.round(currentTime * 100) / 100;
    return keyframes.some((k: any) => Math.abs(Math.round(k.time * 100) / 100 - t) < 0.08 && k.source === "manual");
  })();

  const handleDeleteKeyframe = async () => {
    if (!clip?.id) return;
    const t = Math.round(currentTime * 100) / 100;
    try {
      const res = await deleteKeyframe(clip.id, t);
      setKeyframes(res.keyframes || []);
    } catch {}
  };



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
  // rectangle sewarna speaker (= warna blok timeline & dot sidebar segmen ini)
  const rectColor = justSwitched ? "#f59e0b" : speakerColor(spkNow);
  const nw = cropNormW(vidSize.w, vidSize.h, aspect);
  const half = nw / 2;
  const cx = Math.max(half, Math.min(1 - half, crop.cx));
  const left = (cx - half) * 100;

  const upsert = useCallback((nx: number) => {
    const st = useEditorStore.getState();
    const t = Math.round(st.currentTime * 100) / 100;
    const HALF = cropNormW(1280, 720, st.clip?.aspect_ratio || "9:16") / 2;
    const clamped = Math.max(HALF, Math.min(1 - HALF, nx));
    let kfs = [...st.keyframes].sort((a, b) => a.time - b.time);
    // cari keyframe terdekat (bukan first match) dengan threshold lebar
    // agar drag di antara dua titik mengupdate yang paling dekat, bukan bikin baru
    let bestIdx = -1, bestDist = 0.35;
    for (let i = 0; i < kfs.length; i++) {
      const dist = Math.abs(Math.round(kfs[i].time * 100) / 100 - t);
      if (dist < bestDist) { bestDist = dist; bestIdx = i; }
    }
    if (bestIdx >= 0) kfs[bestIdx] = { ...kfs[bestIdx], center_x: clamped, source: "manual" };
    else kfs.push({ time: t, center_x: clamped, center_y: 0.5, source: "manual" });
    kfs = kfs.sort((a, b) => a.time - b.time).reduce((acc: any[], cur) => {
      const last = acc[acc.length - 1];
      if (last && Math.round(last.time * 100) / 100 === Math.round(cur.time * 100) / 100) acc[acc.length - 1] = cur;
      else acc.push(cur);
      return acc;
    }, []);
    st.setKeyframes(kfs);
    return kfs;
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

  const onStageDown = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('[data-testid="smart-crop-rect"]')) return;
    e.preventDefault();
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
    <div ref={boxRef} data-testid="smart-crop" onMouseDown={onStageDown} style={{ position: "absolute", inset: 0, overflow: "hidden", borderRadius: 8, cursor: "grab" }}>
      {/* dim 4 sisi agar lubang crop jernih */}
      <div style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${left}%`, background: "rgba(0,0,0,0.55)" }} />
      <div style={{ position: "absolute", top: 0, bottom: 0, left: `${left + nw * 100}%`, right: 0, background: "rgba(0,0,0,0.55)" }} />
      {/* rectangle ungu smart crop */}
      <div
        onMouseDown={onCropDown}
        data-testid="smart-crop-rect"
        style={{
          position: "absolute", left: `${left}%`, top: 0, width: `${nw * 100}%`, height: "100%",
          border: `2px solid ${rectColor}`, borderRadius: 4, cursor: "ew-resize", touchAction: "none",
        }}
      >
        <div style={{ position: "absolute", top: 6, left: "50%", transform: "translateX(-50%)", background: rectColor, color: "#fff", fontSize: 10, fontWeight: 700, padding: "1px 8px", borderRadius: 4 }}>
          {aspect}{spkNow ? ` · ${spkNow}` : ""}{saving ? " •" : ""}
        </div>
      </div>
      {hasManualAtCurrentTime && (
        <button
          onClick={(e) => { e.stopPropagation(); handleDeleteKeyframe(); }}
          title="Hapus koreksi di waktu ini (kembalikan ke interpolasi AI)"
          style={{ position: "absolute", bottom: 8, left: "50%", transform: "translateX(-50%)", zIndex: 6,
            background: "#ef4444", color: "#fff", border: "none", borderRadius: 6, padding: "4px 10px",
            fontSize: 11, fontWeight: 600, cursor: "pointer" }}
        >✕ Hapus keyframe manual</button>
      )}
    </div>
  );
}
