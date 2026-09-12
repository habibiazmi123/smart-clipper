import { useRef, useCallback } from "react";
import { useEditorStore } from "../stores/editor";

export default function CropOverlay() {
  const { keyframes, currentTime } = useEditorStore();
  const containerRef = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  const getCurrentCrop = () => {
    if (!keyframes.length) return { cx: 0.5, cy: 0.5 };
    let kf = keyframes[0];
    for (const k of keyframes) {
      if (k.time <= currentTime) kf = k;
      else break;
    }
    return { cx: kf.center_x, cy: kf.center_y };
  };

  const crop = getCurrentCrop();
  const cropW = 1080 / 1920; // 9:16 normalized
  const left = crop.cx - cropW / 2;
  const top = crop.cy - 0.5;

  const handleMouseDown = useCallback((_e: React.MouseEvent) => {
    dragging.current = true;
    const onMove = (ev: MouseEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const rect = containerRef.current.getBoundingClientRect();
      const x = (ev.clientX - rect.left) / rect.width;
      const y = (ev.clientY - rect.top) / rect.height;
      useEditorStore.getState().setKeyframes(
        useEditorStore.getState().keyframes.map(k =>
          k.time === currentTime ? { ...k, center_x: Math.max(0.15, Math.min(0.85, x)), center_y: Math.max(0.1, Math.min(0.9, y)) } : k
        )
      );
    };
    const onUp = () => { dragging.current = false; window.removeEventListener("mousemove", onMove); window.removeEventListener("mouseup", onUp); };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [currentTime]);

  return (
    <div
      ref={containerRef}
      style={{ position: "absolute", inset: 16, pointerEvents: "none", cursor: "crosshair" }}
      onMouseDown={handleMouseDown}
    >
      {/* Dimmed area outside crop */}
      <div style={{ position: "absolute", inset: 0, background: "rgba(0,0,0,0.4)" }} />
      {/* Crop window - clear area */}
      <div
        style={{
          position: "absolute",
          left: `${left * 100}%`,
          top: `${top * 100}%`,
          width: `${cropW * 100}%`,
          height: "100%",
          border: "2px solid var(--accent)",
          borderRadius: 4,
          background: "transparent",
          pointerEvents: "auto",
          cursor: "move",
        }}
      />
    </div>
  );
}
