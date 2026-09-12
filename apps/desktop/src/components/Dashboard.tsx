import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { listProjects, createProject } from "../lib/api";

export default function Dashboard() {
  const [projects, setProjects] = useState<any[]>([]);
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    listProjects().then(setProjects).catch(() => {});
  }, []);

  const handleCreate = async () => {
    if (!url.trim()) return;
    const p = await createProject(name || "Untitled", url);
    navigate(`/editor/${p.id}`);
  };

  return (
    <div className="app" style={{ padding: 40 }}>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 24 }}>Smart Clipper</h1>
      <div className="card" style={{ marginBottom: 24, maxWidth: 600 }}>
        <h2 style={{ fontSize: 16, marginBottom: 12 }}>New Project</h2>
        <input
          placeholder="Project name (optional)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          style={{ width: "100%", padding: 8, background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--text)", marginBottom: 8 }}
        />
        <input
          placeholder="YouTube URL or local path"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          style={{ width: "100%", padding: 8, background: "var(--surface-2)", border: "1px solid var(--border)", borderRadius: 6, color: "var(--text)", marginBottom: 12 }}
        />
        <button className="btn primary" onClick={handleCreate}>Analyze Video</button>
      </div>
      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
        {projects.map((p) => (
          <div key={p.id} className="card" style={{ cursor: "pointer" }} onClick={() => navigate(`/editor/${p.id}`)}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ fontSize: 14, fontWeight: 600 }}>{p.name}</h3>
              <span className={`status-badge ${p.status}`}>{p.status}</span>
            </div>
            <p style={{ fontSize: 12, color: "var(--text-dim)", marginTop: 4 }}>{p.id}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
