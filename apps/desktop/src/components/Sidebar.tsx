import { useEffect, useState } from "react";
import { useEditorStore } from "../stores/editor";
import { getClip, updateKeyframes, resetCropToAI } from "../lib/api";

const DOT = ["#6366f1", "#22c55e", "#f59e0b", "#a855f7", "#ec4899", "#06b6d4"];

export default function Sidebar() {
  const { selectedTab, setSelectedTab, keyframes, clip, project, setClip, setKeyframes, currentTime } = useEditorStore();
  const [avgs, setAvgs] = useState<Record<string, number>>({});

  const tabs = ["crop", "script", "effect"] as const;

  useEffect(() => {
    if (!project?.clips) return;
    let alive = true;
    (async () => {
      const m: Record<string, number> = {};
      await Promise.all(project.clips.slice(0, 15).map(async (c: any) => {
        try {
          const d = await getClip(c.id);
          const kfs = d.keyframes || [];
          if (kfs.length) m[c.id] = kfs.reduce((s: number, k: any) => s + k.center_x, 0) / kfs.length;
        } catch {}
      }));
      if (alive) setAvgs(m);
    })();
    return () => { alive = false; };
  }, [project?.id]);

  const selectClip = async (clipId: string, autoplay = false) => {
    try {
      const c = await getClip(clipId);
      useEditorStore.getState().setSeekOnSelect(true);
      setClip(c);
      setKeyframes(c.keyframes || []);
      const v = useEditorStore.getState().videoRef?.current;
      if (v) { v.currentTime = c.source_start; if (autoplay) v.play(); }
    } catch {}
  };

  // slider geser seluruh trajectory clip (clamped 9:16)
  const shiftClip = async (clipId: string, nx: number) => {
    const HALF = 0.158;
    const clamped = Math.max(HALF, Math.min(1 - HALF, nx));
    if (clip?.id === clipId) {
      const cur = avgs[clipId] ?? 0.5;
      const d = clamped - cur;
      const next = keyframes.map((k) => ({ ...k, center_x: Math.max(HALF, Math.min(1 - HALF, k.center_x + d)), source: "manual" }));
      setKeyframes(next);
      setAvgs((m) => ({ ...m, [clipId]: clamped }));
      try { await updateKeyframes(clipId, next); } catch {}
    } else {
      await selectClip(clipId);
      const kfs = useEditorStore.getState().keyframes;
      const avg = kfs.length ? kfs.reduce((s, k: any) => s + k.center_x, 0) / kfs.length : 0.5;
      const d = clamped - avg;
      const next = kfs.map((k: any) => ({ ...k, center_x: Math.max(HALF, Math.min(1 - HALF, k.center_x + d)), source: "manual" }));
      setKeyframes(next);
      setAvgs((m) => ({ ...m, [clipId]: clamped }));
      try { await updateKeyframes(clipId, next); } catch {}
    }
  };

  const reset = async () => {
    if (!clip) return;
    try {
      await resetCropToAI(clip.id);
      const c = await getClip(clip.id);
      setKeyframes(c.keyframes || []);
    } catch {}
  };

  return (
    <div style={{ width: 330, background: "#12162a", border: "1px solid #2a2f4a", borderRadius: 10, display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <div style={{ display: "flex", borderBottom: "1px solid #2a2f4a" }}>
        {tabs.map((t) => (
          <button key={t} className="btn" onClick={() => setSelectedTab(t)}
            style={{ flex: 1, border: "none", borderRadius: 0, background: "transparent", borderBottom: selectedTab === t ? "2px solid #8b5cf6" : "2px solid transparent", color: selectedTab === t ? "#fff" : "var(--text-dim)" }}>
            {t === "crop" ? "▦ Crop" : t === "script" ? "T Script" : "✨ Effect"}
          </button>
        ))}
      </div>
      <div style={{ padding: 12, flex: 1, overflow: "auto" }}>
        {selectedTab === "crop" && (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <h3 style={{ fontSize: 12, color: "var(--text-dim)" }}>Segmen dan crop video</h3>
              <button className="btn" style={{ fontSize: 11, padding: "2px 8px" }} onClick={reset}>Reset AI</button>
            </div>
            {(project?.clips || []).map((c: any, i: number) => {
              const val = c.id === clip?.id
                ? (() => { const kfs = keyframes; if (!kfs.length) return avgs[c.id] ?? 0.5;
                    // interpolasi saat play agar slider ikut gerak
                    const s = [...kfs].sort((a: any, b: any) => a.time - b.time);
                    if (currentTime <= s[0].time) return s[0].center_x;
                    for (let j = 1; j < s.length; j++) if (currentTime <= s[j].time) {
                      const p = s[j-1], q = s[j], f = (currentTime - p.time) / Math.max(q.time - p.time, 0.001);
                      return p.center_x + f * (q.center_x - p.center_x);
                    }
                    return s[s.length-1].center_x; })()
                : avgs[c.id] ?? 0.5;
              const active = c.id === clip?.id;
              return (
                <div key={c.id} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 8px", borderRadius: 6, marginBottom: 4, background: active ? "#8b5cf622" : "transparent", border: active ? "1px solid #8b5cf655" : "1px solid transparent" }}>
                  <span style={{ width: 20, height: 20, borderRadius: "50%", background: DOT[i % DOT.length], color: "#fff", fontSize: 11, fontWeight: 700, display: "flex", alignItems: "center", justifyContent: "center" }}>{i + 1}</span>
                  <input type="range" min={16} max={84} value={Math.round(val * 100)}
                    onChange={(e) => shiftClip(c.id, Number(e.target.value) / 100)}
                    style={{ flex: 1, accentColor: "#8b5cf6" }} />
                  <button className="btn" style={{ padding: "2px 7px", fontSize: 11 }} onClick={() => selectClip(c.id, true)} title="Preview">▷</button>
                </div>
              );
            })}
            {!project?.clips?.length && <p style={{ fontSize: 12, color: "var(--text-dim)" }}>Belum ada segmen.</p>}
          </div>
        )}
        {selectedTab === "script" && (
          <div>
            <h3 style={{ fontSize: 14, marginBottom: 8 }}>Script</h3>
            <p style={{ fontSize: 12, color: "var(--text-dim)" }}>{clip?.caption_short || "No captions yet"}</p>
          </div>
        )}
        {selectedTab === "effect" && (
          <div>
            <h3 style={{ fontSize: 14, marginBottom: 8 }}>Effects</h3>
            <p style={{ fontSize: 12, color: "var(--text-dim)" }}>Caption styling coming soon</p>
          </div>
        )}
      </div>
    </div>
  );
}

