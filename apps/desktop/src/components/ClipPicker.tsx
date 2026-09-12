import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getProject } from "../lib/api";

function fmt(s: number) {
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m ? `${m}:${String(sec).padStart(2, "0")}` : `0:${String(sec).padStart(2, "0")}`;
}

function HookPreview({ src, start, end }: { src: string; start: number; end: number }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    const v = ref.current;
    if (!v) return;
    const onTime = () => { if (v.currentTime >= end - 0.15) { v.currentTime = start; v.play().catch(() => {}); } };
    v.addEventListener("timeupdate", onTime);
    return () => v.removeEventListener("timeupdate", onTime);
  }, [start, end]);
  const seek = () => { const v = ref.current; if (v) { v.currentTime = start; v.play().catch(() => {}); } };
  return (
    <div style={{ marginTop: 10, borderRadius: 10, overflow: "hidden", border: "1px solid var(--border)", background: "#000", position: "relative" }}>
      <video
        ref={ref}
        src={src}
        controls
        preload="metadata"
        onLoadedMetadata={seek}
        onClick={seek}
        style={{ width: "100%", display: "block", aspectRatio: "16/9", objectFit: "cover", cursor: "pointer" }}
      />
      <span style={{ position: "absolute", bottom: 6, left: 6, fontSize: 10, fontWeight: 700, background: "rgba(0,0,0,0.7)", color: "#fff", padding: "2px 6px", borderRadius: 6 }} className="tabular">
        {fmt(start)} → {fmt(end)} preview
      </span>
    </div>
  );
}

export default function ClipPicker() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const [hooks, setHooks] = useState<any[]>([]);
  const [clips, setClips] = useState<any[]>([]);
  const [status, setStatus] = useState("");
  const [downloadMb, setDownloadMb] = useState<number | null>(null);
  const [sel, setSel] = useState<string | null>(null);

  useEffect(() => {
    if (!projectId) return;
    let alive = true;
    const load = async () => {
      try {
        const p = await getProject(projectId);
        if (!alive) return;
        setHooks(p.hooks || []);
        setClips(p.clips || []);
        setStatus(p.status || "");
        setDownloadMb(p.download_mb ?? null);
        if (p.status !== "ready" || !p.clips?.length) {
          const poll = setInterval(async () => {
            try {
              const q = await getProject(projectId);
              if (!alive) return;
              setStatus(q.status);
              setDownloadMb(q.download_mb ?? null);
              if (q.hooks?.length) setHooks(q.hooks);
              if (q.clips?.length) setClips(q.clips);
              if (q.status === "ready") clearInterval(poll);
            } catch {}
          }, 1500);
          setTimeout(() => clearInterval(poll), 600000);
        }
      } catch { navigate("/"); }
    };
    load();
    return () => { alive = false; };
  }, [projectId]);

  const clipByHook = new Map(clips.map((c: any) => [c.hook_candidate_id || c.id, c]));
  const selectedClip = sel ? clipByHook.get(sel) : null;
  const canEdit = !!selectedClip;
  const videoSrc = `http://127.0.0.1:8719/api/media/${projectId}/video`;
  const hookCount = hooks.length;
  const clipCount = clips.length;
  const isHeu = hooks.some((h) => h.source === "heuristic");
  const analyzing = status !== "ready" && !hooks.length;
  const stageMap: Record<string, string> = {
    downloading: "Downloading video…",
    transcribing: "Transcribing audio…",
    hooking: "Mencari hook viral…",
    cropping: "Memotong clip & crop 9:16…",
  };
  const stage = (stageMap as any)[status] || (analyzing ? "Menganalisis…" : "");

  return (
    <div className="app" style={{ overflow: "auto" }}>
      <div style={{ maxWidth: 1120, margin: "0 auto", padding: 24 }}>
        <button className="btn ghost sm" onClick={() => navigate("/")} style={{ marginBottom: 14 }}>← Projects</button>

        <div style={{ display: "flex", alignItems: "end", justifyContent: "space-between", gap: 12, flexWrap: "wrap", marginBottom: 14 }}>
          <div>
            <h2 style={{ fontSize: 22, fontWeight: 800, letterSpacing: "-0.02em" }}>
              {analyzing ? stage : `Top ${hookCount} clips · pilih 1 untuk edit`}
            </h2>
            <p style={{ fontSize: 12.5, color: "var(--text-dim)", marginTop: 4 }}>
              Groq sudah potong {hookCount}×1 menit. Play di card — pilih 1 → Edit.
            </p>
          </div>
          {clipCount > 0 && <span className="status-pill ready"><span className="dot" />{clipCount} clips ready</span>}
        </div>

        {status === "downloading" && (
          <div className="card" style={{ marginBottom: 12, padding: 14 }}>
            <span className="status-pill processing"><span className="dot" />Downloading</span>
            <span style={{ marginLeft: 10, fontFamily: "ui-monospace,monospace", fontSize: 12 }}>{downloadMb != null ? `${downloadMb} MB` : "…"}</span>
            <p style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 6 }}>yt-dlp sedang menarik YouTube.</p>
          </div>
        )}
        {status && !analyzing && status !== "ready" && status !== "downloading" && (
          <div className="card" style={{ marginBottom: 12, padding: 14 }}>
            <span className="status-pill processing"><span className="dot" />{stage || status}</span>
            <p style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 6 }}>Polling tiap 1.5 detik…</p>
          </div>
        )}
        {isHeu && <p className="status-pill" style={{ marginBottom: 10, fontSize: 11 }}>LLM unavailable — skor lokal</p>}

        {!hooks.length && !analyzing ? (
          <div className="card" style={{ textAlign: "center", padding: 32, color: "var(--text-dim)" }}>
            <p style={{ fontSize: 13 }}>Belum ada clip. Coba buat project baru.</p>
          </div>
        ) : null}

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))", gap: 14 }}>
          {hooks.map((h: any, i: number) => {
            const clip = clipByHook.get(h.id);
            const hasClip = !!clip;
            const isSel = sel === h.id;
            const dur = Number(h.end) - Number(h.start);
            return (
              <article
                key={h.id}
                onClick={() => setSel(h.id)}
                style={{
                  padding: 0,
                  overflow: "hidden",
                  cursor: "pointer",
                  borderRadius: 14,
                  border: `1px solid ${isSel ? "#7c3aed" : hasClip ? "rgba(34,197,94,0.35)" : "rgba(255,255,255,0.08)"}`,
                  background: "var(--surface)",
                  boxShadow: isSel ? "0 0 0 2px rgba(139,92,246,0.35), 0 12px 32px rgba(0,0,0,.35)" : "0 1px 0 rgba(255,255,255,.04) inset, 0 12px 32px rgba(0,0,0,.25)",
                  transform: isSel ? "translateY(-1px)" : undefined,
                  transition: "border-color 180ms, box-shadow 180ms, transform 180ms",
                }}
              >
                <div style={{ height: 5, background: hasClip ? "linear-gradient(90deg,#22c55e,#16a34a)" : "linear-gradient(90deg,#7c3aed,#ec4899)", opacity: isSel ? 1 : 0.85 }} />
                <div style={{ padding: 14 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", marginBottom: 6 }}>
                    <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: 0.06, textTransform: "uppercase", color: isSel ? "#a78bfa" : "var(--text-dim)" }}>#{i + 1}</span>
                    <span className="status-pill" style={{ fontSize: 11, padding: "2px 8px" }}>
                      <span className="dot" style={{ background: hasClip ? "#22c55e" : "#f59e0b" }} />
                      {hasClip ? "Ready" : "Menyiapkan…"}
                    </span>
                    <span className="tabular" style={{ fontSize: 11, color: "var(--text-faint)" }}>{fmt(h.start)} → {fmt(h.end)} · {dur.toFixed(0)}s</span>
                    <span style={{ marginLeft: "auto", fontSize: 18, fontWeight: 800, color: h.score >= 80 ? "#22c55e" : h.score >= 50 ? "#f59e0b" : "#9ca3af" }}>{Math.round(h.score)}</span>
                  </div>
                  {h.source && (
                    <span style={{ fontSize: 10, letterSpacing: 0.06, textTransform: "uppercase", color: "var(--text-faint)", border: "1px solid var(--border)", borderRadius: 999, padding: "2px 7px" }}>{h.source}</span>
                  )}
                  {h.reasons?.length ? (
                    <ul style={{ margin: "8px 0 0", paddingLeft: 16, fontSize: 12, color: "var(--text-dim)", lineHeight: 1.45 }}>
                      {h.reasons.slice(0, 2).map((r: string, j: number) => <li key={j}>{r}</li>)}
                    </ul>
                  ) : null}
                  {h.weakness ? <p style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 6, fontStyle: "italic" }}>Kelemahan: {h.weakness}</p> : null}

                  {hasClip ? (
                    <HookPreview src={videoSrc} start={Number(h.start)} end={Number(h.end)} />
                  ) : (
                    <div style={{ marginTop: 10, borderRadius: 10, border: "1px dashed var(--border)", padding: 16, textAlign: "center", color: "var(--text-faint)", fontSize: 12 }}>
                      Clip belum ready — tunggu cropping selesai
                    </div>
                  )}

                  <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
                    <button
                      className="btn sm"
                      aria-pressed={isSel}
                      style={{
                        flex: 1, justifyContent: "center",
                        background: isSel ? "rgba(139,92,246,0.18)" : undefined,
                        borderColor: isSel ? "#7c3aed" : undefined,
                        color: isSel ? "#c4b5fd" : undefined,
                      }}
                      onClick={(e) => { e.stopPropagation(); setSel(h.id); }}
                    >
                      {isSel ? "✓ Selected" : "Select"}
                    </button>
                    <button
                      className="btn primary sm"
                      disabled={!hasClip}
                      onClick={(e) => { e.stopPropagation(); if (hasClip) setSel(h.id); }}
                      style={{ flex: 1, justifyContent: "center", opacity: hasClip ? 1 : 0.45 }}
                      title={hasClip ? "Pilih card ini untuk Edit" : "Tunggu clip ready"}
                    >
                      Preview
                    </button>
                  </div>
                  {hasClip && <p className="tabular" style={{ fontSize: 10, color: "var(--text-faint)", marginTop: 6, textAlign: "center" }}>clip {clip.id.slice(0, 8)} · {dur.toFixed(0)}s</p>}
                </div>
              </article>
            );
          })}
        </div>

        <div style={{ position: "sticky", bottom: 0, marginTop: 16, padding: "12px 0 4px", background: "linear-gradient(to top, var(--bg-deep), transparent)", display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <button
            className="btn primary"
            disabled={!canEdit}
            onClick={() => { if (selectedClip) navigate(`/editor/${projectId}?clip=${selectedClip.id}`); }}
            style={{ minWidth: 160, justifyContent: "center" }}
          >
            {canEdit ? `Edit selected →` : "Pilih 1 clip dulu"}
          </button>
          <span style={{ fontSize: 12, color: "var(--text-dim)" }}>
            {sel ? `1 terpilih · ${fmt(Number(hooks.find((h: any) => h.id === sel)?.start || 0))} → ${fmt(Number(hooks.find((h: any) => h.id === sel)?.end || 0))}` : "Belum ada yang dipilih"}
          </span>
          <span style={{ marginLeft: "auto", fontSize: 11, color: "var(--text-faint)" }}>Hanya 1 clip masuk editor (60s), bukan gabungan 3×60s</span>
        </div>
      </div>
    </div>
  );
}
