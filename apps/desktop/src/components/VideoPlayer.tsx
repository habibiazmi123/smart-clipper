import { useRef, useEffect } from "react";
import { useEditorStore } from "../stores/editor";

export default function VideoPlayer({ videoSrc }: { videoSrc: string }) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const { setCurrentTime, setIsPlaying } = useEditorStore();

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onTime = () => setCurrentTime(v.currentTime);
    const onPlay = () => setIsPlaying(true);
    const onPause = () => setIsPlaying(false);
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    return () => { v.removeEventListener("timeupdate", onTime); v.removeEventListener("play", onPlay); v.removeEventListener("pause", onPause); };
  }, []);

  return (
    <video
      ref={videoRef}
      src={videoSrc}
      style={{ width: "100%", maxHeight: "70vh", objectFit: "contain", background: "#000", borderRadius: 8 }}
      controls
    />
  );
}
