import { useEditorStore } from "../stores/editor";

export default function Sidebar() {
  const { selectedTab, setSelectedTab, keyframes, clip } = useEditorStore();

  const tabs = ["crop", "script", "effect"] as const;

  return (
    <div style={{ width: 320, background: "var(--surface)", borderLeft: "1px solid var(--border)", display: "flex", flexDirection: "column" }}>
      <div style={{ display: "flex", borderBottom: "1px solid var(--border)" }}>
        {tabs.map((t) => (
          <button
            key={t}
            className={`btn ${selectedTab === t ? "primary" : ""}`}
            style={{ flex: 1, borderRadius: 0, border: "none", borderBottom: selectedTab === t ? "2px solid var(--accent)" : "2px solid transparent" }}
            onClick={() => setSelectedTab(t)}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>
      <div style={{ padding: 16, flex: 1, overflow: "auto" }}>
        {selectedTab === "crop" && (
          <div>
            <h3 style={{ fontSize: 14, marginBottom: 8 }}>Segment Crop</h3>
            {keyframes.map((kf, i) => (
              <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 4, fontSize: 12, color: "var(--text-dim)" }}>
                <span>{formatTime(kf.time)}</span>
                <span>x: {(kf.center_x * 100).toFixed(0)}%</span>
                <span style={{ color: kf.source === "ai" ? "var(--accent)" : "var(--warning)" }}>{kf.source}</span>
              </div>
            ))}
          </div>
        )}
        {selectedTab === "script" && (
          <div>
            <h3 style={{ fontSize: 14, marginBottom: 8 }}>Script</h3>
            <p style={{ fontSize: 12, color: "var(--text-dim)" }}>
              {clip?.caption_short || "No captions yet"}
            </p>
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

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}
