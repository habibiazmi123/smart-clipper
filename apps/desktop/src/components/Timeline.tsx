import { useEditorStore } from "../stores/editor";
import { getClip } from "../lib/api";
import { speakerColor } from "../lib/speakers";

export default function Timeline() {
  const { clip, project, currentTime, keyframes, videoRef, clipSpeakers } = useEditorStore();
  const clips = project?.clips || [];
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
    <div style={{ padding: "10px 16px 14px", background: "var(--surface)", borderTop: "1px solid var(--border)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ fontSize: 12, color: "var(--text-dim)", fontVariantNumeric: "tabular-nums" }}>◂ {fmt(currentTime)} ▸</span>
        <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
          <button className="btn" style={{ padding: "4px 10px" }} onClick={() => step(-2)}>⏮</button>
          <button className="btn primary" style={{ padding: "4px 14px" }} onClick={toggle}>⏯</button>
          <button className="btn" style={{ padding: "4px 10px" }} onClick={() => step(2)}>⏭</button>
        </div>
        {clip && <span style={{ fontSize: 12, color: "var(--success)", fontVariantNumeric: "tabular-nums" }}>{fmt(clip.source_start)} – {fmt(clip.source_end)} · {dur.toFixed(0)}d</span>}
      </div>
      {/* duration / segment strip seperti ss.png */}
      <div style={{ display: "flex", gap: 3, marginTop: 8, height: 34, background: "var(--surface-2)", borderRadius: 6, padding: 3, overflow: "hidden" }}>
        {(clips.length ? clips : clip ? [{ id: clip.id, start: clip.source_start, end: clip.source_end }] : []).map((c: any, i: number) => {
          const w = Math.max(24, ((c.end - c.start) / Math.max(total, 0.001)) * 100);
          const active = clip?.id === c.id;
          // blok sewarna speaker dominan segmen (= warna rectangle & dot sidebar)
          const base = speakerColor(c.id ? clipSpeakers[c.id] : null, i);
          return (
            <div
              key={c.id || i}
              onClick={() => c.id && selectClip(c.id)}
              title={`${fmt(c.start)} - ${fmt(c.end)}${c.id && clipSpeakers[c.id] ? ` · speaker ${clipSpeakers[c.id]}` : ""}`}
              style={{
                flex: `${w} 1 0%`, minWidth: 28, borderRadius: 4, cursor: "pointer",
                background: active ? base : base + "55",
                border: active ? "1px solid #fff3" : "1px solid transparent",
                color: "#fff", fontSize: 10, display: "flex", alignItems: "center", justifyContent: "center",
                position: "relative", overflow: "hidden",
              }}
            >
              {i + 1}
              {active && (
                <div style={{ position: "absolute", top: 0, bottom: 0, left: `${pos * 100}%`, width: 2, background: "#fff" }} />
              )}
            </div>
          );
        })}
      </div>
      {/* keyframe dots untuk clip aktif, max ~40 titik; tick putih = ganti speaker */}
      {clip && (() => {
        const step = Math.max(1, Math.ceil(keyframes.length / 40));
        const dots = keyframes.filter((_, i) => i % step === 0);
        return (
        <div style={{ position: "relative", height: 10, marginTop: 4 }}>
          {dots.map((kf, i) => {
            const prev = i > 0 ? dots[i - 1] : null;
            // tick putih hanya untuk pindah orang beneran (posisi loncat),
            // bukan ganti label di wajah yang sama
            const switched = kf.speaker && prev?.speaker && kf.speaker !== prev.speaker
              && Math.abs(kf.center_x - (prev?.center_x ?? kf.center_x)) > 0.05;
            return (
            <div key={i} title={`${fmt(kf.time)}${kf.speaker ? ` · ${kf.speaker}` : ""}`} style={{ position: "absolute", left: `${((kf.time - clip.source_start) / Math.max(dur, 0.001)) * 100}%`, top: switched ? 0 : 2, width: switched ? 3 : 6, height: switched ? 10 : 6, borderRadius: switched ? 2 : "50%", background: switched ? "#fff" : kf.speaker ? speakerColor(kf.speaker) : kf.source === "ai" ? "#8b5cf6" : "#f59e0b", transform: "translateX(-50%)" }} />
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

