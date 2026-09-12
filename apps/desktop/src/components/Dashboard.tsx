import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listProjects, createProject, analyzeProject } from "../lib/api";

export default function Dashboard() {
  const [projects, setProjects] = useState<any[]>([]);
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [numClips, setNumClips] = useState(3);
  const [maxDuration, setMaxDuration] = useState(60);
  const [aspectRatio, setAspectRatio] = useState("9:16");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    listProjects().then(setProjects).catch(() => {});
  }, []);

  const handleCreate = async () => {
    if (!url.trim() || busy) return;
    setBusy(true);
    try {
      const p = await createProject(name || "Untitled", url);
      analyzeProject(p.id, numClips, maxDuration, aspectRatio);
      navigate(`/editor/${p.id}`);
    } finally {
      setBusy(false);
    }
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
              <input
                className="field"
                placeholder="Project name (optional)"
                value={name}
                onChange={(e) => setName(e.target.value)}
                aria-label="Project name"
              />
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <input
                  className="field"
                  style={{ flex: "1 1 260px" }}
                  placeholder="YouTube URL or local video path"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                  aria-label="Video source"
                  inputMode="url"
                />
                <button className="btn primary" onClick={handleCreate} disabled={!url.trim() || busy} style={{ minHeight: 42 }}>
                  {busy ? "Creating…" : (
                    <>
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden><path d="M8 5v14l11-7z" /></svg>
                      Analyze Video
                    </>
                  )}
                </button>
              </div>
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
                onKeyDown={(e) => e.key === "Enter" && navigate(`/editor/${p.id}`)} aria-label={`Open ${p.name}`}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <h3 style={{ fontSize: 14, fontWeight: 650, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.name}</h3>
          <span className={`status-pill ${p.status === "ready" ? "ready" : "processing"}`}>
            <span className="dot" aria-hidden />{p.status === "cropping" ? "Potong clip…" : p.status}
          </span>
                </div>
                <p style={{ fontSize: 11.5, color: "var(--text-faint)", fontFamily: "ui-monospace,monospace", overflow: "hidden", textOverflow: "ellipsis" }}>{p.id}</p>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
