import { useEffect, useState } from "react";
import { useEditorStore } from "../stores/editor";
import { interpolateKeyframes, cropNormW } from "./CropOverlay";

// Caption viral: frasa pendek mengikuti kata aktif, highlight + pop.
// Posisi di dalam band crop 9:16 (sama dengan hasil export).
export default function CaptionOverlay() {
  const { clipWords, currentTime, keyframes, clip, videoRef, captionStyle } = useEditorStore();
  const [vidSize, setVidSize] = useState({ w: 1920, h: 1080 });

  useEffect(() => {
    const v = videoRef?.current;
    if (!v) return;
    const upd = () => v.videoWidth && setVidSize({ w: v.videoWidth, h: v.videoHeight });
    v.addEventListener("loadedmetadata", upd);
    upd();
    return () => v.removeEventListener("loadedmetadata", upd);
  }, [videoRef, clip?.id]);

  if (!clip || !clipWords.length) return null;
  const t = currentTime;
  let ai = clipWords.findIndex((w) => t >= w.start && t < w.end);
  if (ai < 0) {
    // jeda: tampilkan frasa terakhir yang baru lewat (<0.8s), selain itu sembunyi
    const past = clipWords.filter((w) => w.end <= t).slice(-4);
    if (!past.length || t - past[past.length - 1].end > 0.8) return null;
    ai = clipWords.indexOf(past[past.length - 1]);
  }
  // kumpulkan frasa: mundur max 2 kata / gap >0.6s, maju max 2 kata
  let s = ai;
  while (s > 0 && ai - s < 2 && clipWords[s].start - clipWords[s - 1].end < 0.6) s--;
  let e = ai;
  while (e < clipWords.length - 1 && e - ai < 2 && clipWords[e + 1].start - clipWords[e].end < 0.6) e++;
  const phrase = clipWords.slice(s, e + 1);

  const aspect = clip?.aspect_ratio || "9:16";
  const crop = interpolateKeyframes(keyframes, t);
  const nw = cropNormW(vidSize.w, vidSize.h, aspect);
  const cx = Math.max(nw / 2, Math.min(1 - nw / 2, crop.cx));
  const left = (cx - nw / 2) * 100;
  const wPct = nw * 100;
  // skala font dari LEBAR TAMPILAN crop (bukan source px): 64px @ 606px crop
  const dispCropW = (videoRef?.current?.clientWidth || 800) * nw;
  const px = Math.max(11, (captionStyle.fontSize * dispCropW) / 606);
  const top = captionStyle.position === "top" ? "8%" : captionStyle.position === "middle" ? "42%" : undefined;
  const bottom = captionStyle.position === "bottom" ? "9%" : undefined;

  return (
    <div style={{ position: "absolute", inset: 0, pointerEvents: "none", overflow: "hidden" }}>
      <div style={{ position: "absolute", left: `${left}%`, width: `${wPct}%`, top, bottom, display: "flex", alignItems: "flex-start", justifyContent: "center", textAlign: "center", padding: "0 4px" }}>
        <div style={{ fontWeight: 800, lineHeight: 1.15, textTransform: "uppercase" }}>
          {phrase.map((w, i) => {
            const gi = s + i;
            const active = gi === ai;
            return (
              <span key={`${w.start}-${i}`} style={{
                display: "inline-block",
                fontSize: active ? px * 1.18 : px,
                color: active ? captionStyle.active : captionStyle.upcoming,
                margin: "0 0.18em",
                transform: active ? "scale(1.05)" : undefined,
                textShadow: captionStyle.stroke
                  ? "-2px -2px 0 #000,2px -2px 0 #000,-2px 2px 0 #000,2px 2px 0 #000,0 3px 6px rgba(0,0,0,.6)"
                  : "0 2px 8px rgba(0,0,0,.7)",
                transition: "font-size 90ms",
              }}>{w.w}</span>
            );
          })}
        </div>
      </div>
    </div>
  );
}
