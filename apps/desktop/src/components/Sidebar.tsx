import { useState } from "react";
import { useEditorStore } from "../stores/editor";
import { getClip, updateKeyframes, resetCropToAI, editSegment, refreshClipCaptions, exportCurrentClipWithProgress, cancelCurrentExport, scheduleAutoRender } from "../lib/api";
import { speakerColor } from "../lib/speakers";

const PRESETS = [
  { id: "hormozi", label: "Hormozi", active: "#FFFF00", upcoming: "#FFFFFF" },
  { id: "beast", label: "Beast", active: "#FFFFFF", upcoming: "#FFFF00" },
  { id: "minimal", label: "Minimal", active: "#FFFFFF", upcoming: "#CCCCCC" },
] as const;

export default function Sidebar() {
  const { selectedTab, setSelectedTab, keyframes, clip, project, setClip, setKeyframes, currentTime,
    clipSegments, captionStyle, setCaptionStyle, exporting, exportProgress, exportQuality, setExportQuality, autoRender, setAutoRender, renderResults, clipSpeakers, clipAvgX, setClipAvgX } = useEditorStore();
  const renderRes = clip ? renderResults[clip.id] : undefined;
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editText, setEditText] = useState("");

  const tabs = ["crop", "script", "effect"] as const;

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
      const cur = clipAvgX[clipId] ?? 0.5;
      const d = clamped - cur;
      const next = keyframes.map((k) => ({ ...k, center_x: Math.max(HALF, Math.min(1 - HALF, k.center_x + d)), source: "manual" }));
      setKeyframes(next);
      setClipAvgX({ ...clipAvgX, [clipId]: clamped });
      try { await updateKeyframes(clipId, next); } catch {}
    } else {
      await selectClip(clipId);
      const kfs = useEditorStore.getState().keyframes;
      const avg = kfs.length ? kfs.reduce((s, k: any) => s + k.center_x, 0) / kfs.length : 0.5;
      const d = clamped - avg;
      const next = kfs.map((k: any) => ({ ...k, center_x: Math.max(HALF, Math.min(1 - HALF, k.center_x + d)), source: "manual" }));
      setKeyframes(next);
      setClipAvgX({ ...useEditorStore.getState().clipAvgX, [clipId]: clamped });
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
    <aside className="side-pane" aria-label="Clip controls">
      <div className="side-tabs" role="tablist">
        {tabs.map((t) => (
          <button key={t} role="tab" aria-selected={selectedTab === t} className="side-tab" onClick={() => setSelectedTab(t)}>
            {t === "crop" ? (
              <><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M6 2v14a2 2 0 0 0 2 2h14" /><path d="M18 22V8a2 2 0 0 0-2-2H2" /></svg> Crop</>
            ) : t === "script" ? (
              <><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" /><polyline points="14 2 14 8 20 8" /></svg> Script</>
            ) : (
              <><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><path d="M12 3l1.9 5.8H20l-4.9 3.5 1.9 5.7-5-3.6-5 3.6 1.9-5.7L4 8.8h6.1z" /></svg> Effect</>
            )}
          </button>
        ))}
      </div>
      <div className="side-body">
        {selectedTab === "crop" && (
          <div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <h3 className="lbl">Segments · drag to reframe</h3>
              <button className="btn sm" onClick={reset}>Reset AI</button>
            </div>
            {(project?.clips || []).map((c: any, i: number) => {
              const val = c.id === clip?.id
                ? (() => { const kfs = keyframes; if (!kfs.length) return clipAvgX[c.id] ?? 0.5;
                    // interpolasi saat play agar slider ikut gerak
                    const s = [...kfs].sort((a: any, b: any) => a.time - b.time);
                    if (currentTime <= s[0].time) return s[0].center_x;
                    for (let j = 1; j < s.length; j++) if (currentTime <= s[j].time) {
                      const p = s[j-1], q = s[j], f = (currentTime - p.time) / Math.max(q.time - p.time, 0.001);
                      return p.center_x + f * (q.center_x - p.center_x);
                    }
                    return s[s.length-1].center_x; })()
                : clipAvgX[c.id] ?? 0.5;
              const active = c.id === clip?.id;
              // dot + slider sewarna speaker segmen (= warna rectangle & blok timeline)
              const spkColor = speakerColor(clipSpeakers[c.id], i);
              return (
                <div key={c.id} className={`seg-row ${active ? "active" : ""}`}>
                  <span className="seg-num" style={{ background: spkColor }}>{i + 1}</span>
                  <input type="range" min={16} max={84} value={Math.round(val * 100)} aria-label={`Reframe segment ${i + 1}`}
                    onChange={(e) => shiftClip(c.id, Number(e.target.value) / 100)}
                    style={{ flex: 1, accentColor: spkColor }} />
                  <button className="btn sm icon" style={{ width: 30, height: 30 }} onClick={() => selectClip(c.id, true)} title="Preview" aria-label={`Preview segment ${i + 1}`}>▷</button>
                </div>
              );
            })}
            {!project?.clips?.length && <p style={{ fontSize: 12, color: "var(--text-dim)" }}>Belum ada segmen.</p>}
          </div>
        )}
        {selectedTab === "script" && (
          <div>
            <h3 className="lbl" style={{ marginBottom: 10 }}>Transcript · click to jump</h3>
            {!clipSegments.length && <p style={{ fontSize: 12, color: "var(--text-dim)" }}>Belum ada transkrip.</p>}
            {clipSegments.map((s) => {
              const active = currentTime >= s.start && currentTime < s.end;
              const v = useEditorStore.getState().videoRef?.current;
              return (
                <div key={s.id} onClick={() => v && (v.currentTime = s.start + 0.01)}
                  className={`script-row ${active ? "active" : ""}`}>
                  <div className="script-time tabular">{fmtT(s.start)}</div>
                  {editingId === s.id ? (
                    <input autoFocus value={editText} onChange={(e) => setEditText(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      onBlur={async () => { setEditingId(null); if (editText.trim() && editText !== s.text && clip) { await editSegment(s.id, editText.trim()).catch(() => {}); await refreshClipCaptions(clip.id).catch(() => {}); scheduleAutoRender(); } }}
                      onKeyDown={async (e) => { if (e.key === "Enter") (e.target as HTMLInputElement).blur(); if (e.key === "Escape") setEditingId(null); }}
                      style={{ width: "100%", background: "#000", color: "#fff", border: "1px solid #8b5cf6", borderRadius: 4, fontSize: 12, padding: 4 }} />
                  ) : (
                    <div onDoubleClick={(e) => { e.stopPropagation(); setEditingId(s.id); setEditText(s.text); }} title="Double-click untuk edit">{s.text}</div>
                  )}
                </div>
              );
            })}
          </div>
        )}
        {selectedTab === "effect" && (
          <div>
            <h3 className="lbl" style={{ marginBottom: 10 }}>Viral caption style</h3>
            <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
              {PRESETS.map((p) => (
                <button key={p.id} className="btn" onClick={() => setCaptionStyle({ preset: p.id, active: p.active, upcoming: p.upcoming })}
                  style={{ flex: 1, fontSize: 11, padding: "6px 4px", borderColor: captionStyle.preset === p.id ? "#8b5cf6" : undefined, background: captionStyle.preset === p.id ? "#8b5cf633" : undefined }}>{p.label}</button>
              ))}
            </div>
            <label style={{ fontSize: 11, color: "var(--text-dim)" }}>Ukuran font ({captionStyle.fontSize})</label>
            <input type="range" min={40} max={110} value={captionStyle.fontSize} onChange={(e) => setCaptionStyle({ fontSize: Number(e.target.value) })} style={{ width: "100%", accentColor: "#8b5cf6", marginBottom: 8 }} />
            <label style={{ fontSize: 11, color: "var(--text-dim)" }}>Posisi</label>
            <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
              {(["top", "middle", "bottom"] as const).map((p) => (
                <button key={p} className="btn" onClick={() => setCaptionStyle({ position: p })}
                  style={{ flex: 1, fontSize: 11, padding: "4px", borderColor: captionStyle.position === p ? "#8b5cf6" : undefined }}>{p}</button>
              ))}
            </div>
            <div style={{ display: "flex", gap: 12, marginBottom: 8, fontSize: 11 }}>
              <label style={{ display: "flex", gap: 4, alignItems: "center" }}>Aktif <input type="color" value={captionStyle.active} onChange={(e) => setCaptionStyle({ active: e.target.value })} /></label>
              <label style={{ display: "flex", gap: 4, alignItems: "center" }}>Lainnya <input type="color" value={captionStyle.upcoming} onChange={(e) => setCaptionStyle({ upcoming: e.target.value })} /></label>
              <label style={{ display: "flex", gap: 4, alignItems: "center" }}><input type="checkbox" checked={captionStyle.stroke} onChange={(e) => setCaptionStyle({ stroke: e.target.checked })} /> Outline</label>
            </div>
            <label style={{ fontSize: 11, color: "var(--text-dim)" }}>Kualitas export</label>
            <div style={{ display: "flex", gap: 6, marginBottom: 8 }}>
              {(["fast", "balanced", "high"] as const).map((q) => (
                <button key={q} className="btn" onClick={() => setExportQuality(q)}
                  title={q === "fast" ? "Cepat, file kecil (veryfast crf28)" : q === "balanced" ? "Seimbang (fast crf23)" : "Lambat, tajam (slow crf18)"}
                  style={{ flex: 1, fontSize: 11, padding: "4px", borderColor: exportQuality === q ? "#8b5cf6" : undefined, background: exportQuality === q ? "#8b5cf633" : undefined }}>
                  {q === "fast" ? "⚡ Cepat" : q === "balanced" ? "⚖ Seimbang" : "💎 Tinggi"}
                </button>
              ))}
            </div>
            <button className="btn primary" disabled={!clip || exporting} onClick={() => exportCurrentClipWithProgress(true)}
              style={{ width: "100%", marginBottom: 8 }}>{exporting ? `Rendering… ${exportProgress != null ? Math.round(exportProgress * 100) + "%" : ""}` : "⭳ Export 9:16 + caption"}</button>
            {exporting && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ height: 8, background: "#0b0e1a", borderRadius: 4, overflow: "hidden", border: "1px solid #2a2f4a" }}>
                  <div style={{ height: "100%", width: `${Math.round((exportProgress ?? 0) * 100)}%`, background: "#8b5cf6", transition: "width 0.4s" }} />
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 4 }}>
                  <span style={{ fontSize: 11, color: "var(--text-dim)" }}>{Math.round((exportProgress ?? 0) * 100)}% · {exportQuality}</span>
                  <button className="btn" style={{ fontSize: 11, padding: "2px 8px" }} onClick={() => cancelCurrentExport()}>Batal</button>
                </div>
              </div>
            )}
            <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12, marginBottom: 6 }}>
              <input type="checkbox" checked={autoRender} onChange={(e) => setAutoRender(e.target.checked)} />
              Auto-render setiap edit teks/gaya
            </label>
            {renderRes ? (
              <a href={renderRes.url} download={`${clip?.id}_9x16.mp4`} style={{ fontSize: 12, color: "#22c55e" }}>
                ✓ Render terbaru siap · {renderRes.time} — klik untuk download
              </a>
            ) : exporting ? (
              <p style={{ fontSize: 12, color: "#f59e0b" }}>Rendering… hasil otomatis muncul di sini.</p>
            ) : (
              <p style={{ fontSize: 11, color: "var(--text-dim)" }}>Edit teks/gaya → mp4 fresh ter-render otomatis.</p>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}

function fmtT(s: number): string {
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

