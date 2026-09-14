import { useState, useRef, useCallback } from "react";
import { useEditorStore } from "../stores/editor";
import { getClip } from "../lib/api";
import { speakerColor } from "../lib/speakers";

function parseSeekInput(v: string): number | null {
  v = v.trim();
  if (!v) return null;
  if (/^\d+(\.\d+)?$/.test(v)) return Number(v);
  const parts = v.split(":").map(Number);
  if (parts.some(isNaN)) return null;
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  return null;
}

export default function Timeline() {
  const { clip, project, currentTime, keyframes, videoRef, clipSpeakers } = useEditorStore();
  const [seekInput, setSeekInput] = useState("");
  const [seekErr, setSeekErr] = useState(false);
  const scrubRef = useRef<HTMLDivElement>(null);

  const doSeek = useCallback((t: number) => {
    const v = videoRef?.current;
    if (!v) return;
    const target = clip ? Math.max(clip.source_start, Math.min(clip.source_end, t)) : Math.max(0, t);
    v.currentTime = target;
  }, [clip, videoRef]);

  const onScrub = useCallback((e: React.MouseEvent<HTMLDivElement>) => {
    if (!clip || !scrubRef.current) return;
    const rect = scrubRef.current.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    doSeek(clip.source_start + frac * Math.max(clip.source_end - clip.source_start, 0.001));
  }, [clip, doSeek]);
  const clips = project?.clips || [];
  const hookMap = Object.fromEntries((project?.hooks || []).map((h: any) => [h.id, h]));
  const total = clips.length
    ? clips[clips.length - 1].end - clips[0].start
    : clip ? clip.source_end - clip.source_start : 1;

  const selectClip = async (id: string) => {
    try {
      const c = await getClip(id);
      const st = useEditorStore.getState();
      st.setSeekOnSelect(true);
      st.setClip(c);
      st.setKeyframes(c.keyframes || []);
      if (st.videoRef?.current) st.videoRef.current.currentTime = c.source_start;
    } catch {}
  };

  const step = (d: number) => {
    const v = videoRef?.current;
    if (v) v.currentTime = Math.max(0, v.currentTime + d);
  };
  const toggle = () => {
    const v = videoRef?.current;
    if (!v) return;
    if (v.paused) v.play(); else v.pause();
  };

  const dur = clip ? clip.source_end - clip.source_start : 0;
  const pos = clip ? Math.max(0, Math.min(1, (currentTime - clip.source_start) / Math.max(dur, 0.001))) : 0;

  return (
    <div className="timeline-bar">
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
          <input
            value={seekInput}
            onChange={(e) => { setSeekInput(e.target.value); setSeekErr(false); }}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                const t = parseSeekInput(seekInput);
                if (t != null) { doSeek(t); setSeekInput(""); setSeekErr(false); }
                else setSeekErr(true);
              }
            }}
            placeholder="seek mm:ss"
            title="Ketik waktu (mm:ss atau detik) lalu Enter"
            style={{ width: 72, fontSize: 12, background: seekErr ? "#451a03" : "#111320",
              color: seekErr ? "#fbbf24" : "var(--text-dim)", border: `1px solid ${seekErr ? "#f59e0b" : "#2a2f4a"}`,
              borderRadius: 4, padding: "4px 6px", outline: "none" }}
          />
          <span className="tabular" style={{ fontSize: 12, color: "var(--text-dim)", minWidth: 52 }}>{fmt(currentTime)}</span>
        </div>
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
          <button className="btn icon sm" style={{ width: 34, height: 32 }} onClick={() => step(-2)} aria-label="Back 2 seconds">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M11 18V6l-8.5 6L11 18zm.5-6l8.5 6V6l-8.5 6z" /></svg>
          </button>
          <button className="btn primary sm" style={{ padding: "6px 18px" }} onClick={toggle} aria-label="Play or pause">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M8 5v14l11-7z" /></svg>
          </button>
          <button className="btn icon sm" style={{ width: 34, height: 32 }} onClick={() => step(2)} aria-label="Forward 2 seconds">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M13 6v12l8.5-6L13 6zM4 18l8.5-6L4 6v12z" /></svg>
          </button>
        </div>
        {clip && <span className="tabular" style={{ fontSize: 11.5, color: "var(--text-dim)" }}>{fmt(clip.source_start)} – {fmt(clip.source_end)} · {dur.toFixed(0)}s</span>}
      </div>
      {/* duration / segment strip seperti ss.png */}
      <div className="seg-strip">
        {(clips.length ? clips : clip ? [{ id: clip.id, start: clip.source_start, end: clip.source_end }] : []).map((c: any, i: number) => {
          const w = Math.max(24, ((c.end - c.start) / Math.max(total, 0.001)) * 100);
          const active = clip?.id === c.id;
          // blok sewarna speaker dominan segmen (= warna rectangle & dot sidebar)
          const base = speakerColor(c.id ? clipSpeakers[c.id] : null, i);
          const hook = c.hook_candidate_id ? hookMap[c.hook_candidate_id] : null;
          return (
            <div
              key={c.id || i}
              onClick={() => c.id && selectClip(c.id)}
              title={`${fmt(c.start)} - ${fmt(c.end)}${hook ? ` · score ${Math.round(hook.score)}` : ""}${c.id && clipSpeakers[c.id] ? ` · speaker ${clipSpeakers[c.id]}` : ""}${hook?.reasons?.[0] ? ` · ${hook.reasons[0]}` : ""}`}
              className="seg-block"
              style={{
                flex: `${w} 1 0%`,
                background: active ? base : base + "55",
                border: active ? "1px solid #fff3" : "1px solid transparent",
              }}
            >
              {hook ? `${i + 1} · ${Math.round(hook.score)}` : i + 1}
            </div>
          );
        })}
      </div>
      {/* scrub bar: drag/click untuk seek */}
      {clip && (
        <div ref={scrubRef} onClick={onScrub}
          style={{ position: "relative", height: 18, marginTop: 6, background: "#111320", borderRadius: 4, cursor: "pointer", border: "1px solid #2a2f4a" }}>
          <div style={{ position: "absolute", top: 0, bottom: 0, left: `${pos * 100}%`, width: 2, background: "#fff", pointerEvents: "none" }} />
          <div style={{ position: "absolute", top: 0, bottom: 0, left: 0, width: `${pos * 100}%`, background: "rgba(139,92,246,0.25)", borderRadius: 4, pointerEvents: "none" }} />
          <div
            onMouseDown={(e) => {
              e.preventDefault();
              const onMove = (ev: MouseEvent) => {
                if (!scrubRef.current || !clip) return;
                const rect = scrubRef.current.getBoundingClientRect();
                const frac = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
                doSeek(clip.source_start + frac * Math.max(clip.source_end - clip.source_start, 0.001));
              };
              const onUp = () => {
                window.removeEventListener("mousemove", onMove);
                window.removeEventListener("mouseup", onUp);
              };
              window.addEventListener("mousemove", onMove);
              window.addEventListener("mouseup", onUp);
            }}
            style={{ position: "absolute", top: "50%", left: `${pos * 100}%`, width: 14, height: 14, borderRadius: "50%", background: "#fff", border: "2px solid #8b5cf6", transform: "translate(-50%, -50%)", cursor: "grab" }} />
        </div>
      )}
      {/* keyframe dots untuk clip aktif, max ~40 titik; tick putih = ganti speaker */}
      {clip && (() => {
        const step = Math.max(1, Math.ceil(keyframes.length / 40));
        const dots = keyframes.filter((_, i) => i % step === 0);
        return (
        <div style={{ position: "relative", height: 10, marginTop: 4 }}>
          {dots.map((kf, i) => {
            const prev = i > 0 ? dots[i - 1] : null;
            // tick putih = CUT beneran. Mirror _is_switch backend.
            const switched = !!prev && (() => {
              const dx = Math.abs(kf.center_x - prev.center_x);
              if (prev.source === "manual" || kf.source === "manual") return dx > 0.08;
              return kf.speaker == null || prev.speaker == null || kf.speaker !== prev.speaker || dx > 0.08;
            })();
            return (
            <div key={i} title={`${fmt(kf.time)}${kf.speaker ? ` · ${kf.speaker}` : " · center (tanpa wajah)"}`} style={{ position: "absolute", left: `${((kf.time - clip.source_start) / Math.max(dur, 0.001)) * 100}%`, top: switched ? 0 : 2, width: switched ? 3 : 6, height: switched ? 10 : 6, borderRadius: switched ? 2 : "50%", background: switched ? "#fff" : kf.speaker ? speakerColor(kf.speaker) : kf.source === "manual" ? "#f59e0b" : "#6b7280", transform: "translateX(-50%)" }} />
            );
          })}
        </div>
        );
      })()}
    </div>
  );
}

function fmt(s: number): string {
  s = Math.max(0, s || 0);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
  const p = (n: number) => n.toString().padStart(2, "0");
  return h ? `${p(h)}:${p(m)}:${p(sec)}` : `${p(m)}:${p(sec)}`;
}

