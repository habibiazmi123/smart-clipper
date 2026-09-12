import { useEditorStore } from "../stores/editor";

export default function Timeline() {
  const { clip, currentTime, keyframes } = useEditorStore();
  const duration = clip ? clip.source_end - clip.source_start : 60;

  return (
    <div style={{ padding: "12px 20px", background: "var(--surface)", borderTop: "1px solid var(--border)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 8 }}>
        <span style={{ fontVariantNumeric: "tabular-nums", fontSize: 13, color: "var(--text-dim)" }}>
          {formatTime(currentTime)}
        </span>
        <div style={{ flex: 1, position: "relative", height: 48, background: "var(--surface-2)", borderRadius: 6 }}>
          {keyframes.map((kf, i) => (
            <div
              key={i}
              style={{
                position: "absolute",
                left: `${((kf.time - (clip?.source_start || 0)) / duration) * 100}%`,
                top: "50%",
                transform: "translate(-50%, -50%)",
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: kf.source === "ai" ? "var(--accent)" : "var(--warning)",
              }}
            />
          ))}
          <div
            style={{
              position: "absolute",
              left: `${((currentTime - (clip?.source_start || 0)) / duration) * 100}%`,
              top: 0,
              bottom: 0,
              width: 2,
              background: "var(--error)",
              pointerEvents: "none",
            }}
          />
        </div>
      </div>
    </div>
  );
}

function formatTime(s: number): string {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  const ms = Math.floor((s % 1) * 100);
  return `${m.toString().padStart(2, "0")}:${sec.toString().padStart(2, "0")}.${ms.toString().padStart(2, "0")}`;
}
