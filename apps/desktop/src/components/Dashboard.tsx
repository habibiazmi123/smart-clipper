import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listProjects, createProject, uploadProjectFile, analyzeProject, deleteProject } from "../lib/api";

export default function Dashboard() {
  const [projects, setProjects] = useState<any[]>([]);
  const [mode, setMode] = useState<"url" | "file">("url");
  const [url, setUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [numClips, setNumClips] = useState(3);
  const [maxDuration, setMaxDuration] = useState(60);
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    listProjects().then(setProjects).catch(() => {});
  }, []);

  useEffect(() => {
    if (!projects.some((p) => p.status !== "ready" && p.status !== "failed")) return;
    const iv = setInterval(() => listProjects().then(setProjects).catch(() => {}), 2000);
    return () => clearInterval(iv);
  }, [projects]);

  const handleCreate = async () => {
    if (busy) return;
    setBusy(true);
    try {
      if (mode === "file") {
        if (!file) return;
        const p = await createProject("", file.name);
        await uploadProjectFile(p.id, file);
        analyzeProject(p.id, numClips, maxDuration, aspectRatio);
        navigate(`/editor/${p.id}`);
      } else {
        if (!url.trim()) return;
        const p = await createProject("", url);
        analyzeProject(p.id, numClips, maxDuration, aspectRatio);
        navigate(`/editor/${p.id}`);
      }
    } finally {
      setBusy(false);
    }
  };
  const canSubmit = mode === "file" ? !!file : !!url.trim();

  const handleDelete = async (e: React.MouseEvent, pid: string) => {
    e.stopPropagation();
    if (!confirm("Hapus project ini beserta semua data?")) return;
    await deleteProject(pid).catch(() => {});
    setProjects((prev) => prev.filter((p) => p.id !== pid));
  };

  return (
    <div className="app" style={{ overflow: "auto" }}>
      <div style={{ maxWidth: 1080, width: "100%", margin: "0 auto", padding: "36px 24px 48px" }}>
        <header style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 22 }}>
          <span aria-hidden style={{ width: 34, height: 34, borderRadius: 10, background: "linear-gradient(135deg,#7c3aed,#ec4899)", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 16 }}>S</span>
          <div>
            <h1 style={{ fontSize: 20, fontWeight: 750, letterSpacing: "-0.02em", lineHeight: 1.1 }}>Smart Clipper</h1>
            <p style={{ fontSize: 12.5, color: "var(--text-dim)" }}>Local-first AI video editor · CapCut UX + OpusClip AI</p>
          </div>
          <div style={{ flex: 1 }} />
          <span className="status-pill" style={{ fontSize: 11 }}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2.4"><rect x="3" y="11" width="18" height="10" rx="2" /><path d="M7 11V7a5 5 0 0 1 10 0v4" /></svg>
            100% local · offline ready
          </span>
        </header>

        <section className="dash-hero" aria-label="Create project">
          <div style={{ position: "relative", zIndex: 1, maxWidth: 640 }}>
            <p className="lbl" style={{ marginBottom: 8 }}>New project</p>
            <h2 style={{ fontSize: 26, fontWeight: 780, letterSpacing: "-0.025em", lineHeight: 1.15, marginBottom: 8 }}>
              Paste link. Get viral clips.
            </h2>
            <p style={{ fontSize: 13.5, color: "var(--text-dim)", marginBottom: 16 }}>
              Download → transcribe → detect hooks → smart 9:16 crop → captions. All on-device.
            </p>
            <div style={{ display: "grid", gap: 10 }}>
              <div style={{ display: "flex", gap: 8 }}>
                {(["url", "file"] as const).map((m) => (
                  <button
                    key={m}
                    className="btn"
                    onClick={() => setMode(m)}
                    aria-pressed={mode === m}
                    style={mode === m ? {} : { opacity: 0.55 }}
                  >
                    {m === "url" ? "YouTube URL" : "Upload file"}
                  </button>
                ))}
              </div>
              {mode === "url" ? (
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <input
                  className="field"
                  style={{ flex: "1 1 260px" }}
                  placeholder="YouTube URL"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  aria-label="Video source"
                  inputMode="url"
                />
                <button className="btn primary" onClick={handleCreate} disabled={!canSubmit || busy} style={{ minHeight: 42 }}>
                  {busy ? "Creating…" : (
                    <>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M8 5v14l11-7z" /></svg>
                      Analyze Video
                    </>
                  )}
                </button>
              </div>
              ) : (
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                <label className="field" style={{ flex: "1 1 260px", cursor: "pointer", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {file ? file.name : "Pilih file video…"}
                  <input
                    type="file"
                    accept="video/*,.mp4,.mov,.mkv,.webm"
                    hidden
                    onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                    aria-label="Video file"
                  />
                </label>
                <button className="btn primary" onClick={handleCreate} disabled={!canSubmit || busy} style={{ minHeight: 42 }}>
                  {busy ? "Uploading…" : (
                    <>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M8 5v14l11-7z" /></svg>
                      Upload & Analyze
                    </>
                  )}
                </button>
              </div>
              )}
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12 }}>
                  <span style={{ color: "var(--text-dim)" }}>Clips</span>
                  <select className="field" value={numClips} onChange={(e) => setNumClips(Number(e.target.value))}>
                    {[3, 5, 10, 15].map((n) => <option key={n} value={n}>{n}</option>)}
                  </select>
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12 }}>
                  <span style={{ color: "var(--text-dim)" }}>Max duration</span>
                  <select className="field" value={maxDuration} onChange={(e) => setMaxDuration(Number(e.target.value))}>
                    {[30, 45, 60, 90].map((n) => <option key={n} value={n}>{n}s</option>)}
                  </select>
                </label>
                <label style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12 }}>
                  <span style={{ color: "var(--text-dim)" }}>Ratio</span>
                  <select className="field" value={aspectRatio} onChange={(e) => setAspectRatio(e.target.value)}>
                    {["9:16", "1:1", "16:9"].map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </label>
              </div>
              <p style={{ fontSize: 11.5, color: "var(--text-faint)" }}>Supports YouTube · MP4 · MOV · MKV · WebM via yt-dlp + FFmpeg</p>
            </div>
          </div>
        </section>

        <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "26px 2px 14px" }}>
          <h2 style={{ fontSize: 14, fontWeight: 700 }}>Projects</h2>
          <span style={{ fontSize: 12, color: "var(--text-faint)" }} className="tabular">{projects.length} total</span>
        </div>
        {!projects.length ? (
          <div className="card" style={{ textAlign: "center", padding: 32, color: "var(--text-dim)" }}>
            <p style={{ fontSize: 13 }}>No projects yet. Paste a URL above to start your first clip.</p>
          </div>
        ) : (
          <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
            {projects.map((p) => (
              <article key={p.id} className="card hoverable" onClick={() => navigate(`/editor/${p.id}`)} tabIndex={0}
                onKeyDown={(e) => e.key === "Enter" && navigate(`/editor/${p.id}`)} aria-label={`Open ${p.name}`}
                style={{ position: "relative" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <h3 style={{ fontSize: 14, fontWeight: 650, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</h3>
                  <span className={`status-pill ${p.status === "ready" ? "ready" : "processing"}`}>
                    <span className="dot" aria-hidden />{p.status === "cropping" ? "Potong clip…" : (p as any).stage || p.status}
                  </span>
                </div>
                {(p as any).progress > 0 && p.status !== "ready" && (
                  <div style={{ height: 4, background: "#1a1d2e", borderRadius: 2, overflow: "hidden", marginBottom: 6, border: "1px solid #2a2f4a" }}>
                    <div style={{ height: "100%", width: `${Math.round(((p as any).progress ?? 0) * 100)}%`, background: "#8b5cf6", transition: "width 0.6s" }} />
                  </div>
                )}
                <p style={{ fontSize: 11.5, color: "var(--text-faint)", fontFamily: "ui-monospace,monospace", overflow: "hidden", textOverflow: "ellipsis" }}>{p.id}</p>
                <button
                  onClick={(e) => handleDelete(e, p.id)}
                  title="Hapus project"
                  aria-label={`Delete ${p.name}`}
                  style={{ position: "absolute", top: 8, right: 8, width: 26, height: 26, borderRadius: 6, border: "1px solid #3a2a2a", background: "rgba(239,68,68,.12)", color: "#f87171", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center" }}
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" /><line x1="10" y1="11" x2="10" y2="17" /><line x1="14" y1="11" x2="14" y2="17" /></svg>
                </button>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
