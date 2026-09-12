import { useEffect, useRef } from "react";
import { useEditorStore } from "../stores/editor";
import { getClip } from "../lib/api";

export default function VideoPlayer({ videoSrc, videoRef }: { videoSrc: string; videoRef: { current: HTMLVideoElement | null } }) {
  const { setCurrentTime, setIsPlaying, clip } = useEditorStore();
  const pendingRef = useRef<string | null>(null);

  // auto-follow: seleksi segmen mengikuti waktu play/seek, tanpa seek ulang
  const followSegment = () => {
    const v = videoRef.current;
    const st = useEditorStore.getState();
    const clips = st.project?.clips;
    if (!v || !clips?.length) return;
    const t = v.currentTime;
    const cur = st.clip;
    if (cur && t >= cur.source_start - 0.25 && t < cur.source_end) return;
    const last = clips[clips.length - 1];
    const next = clips.find((c: any) => t >= c.start - 0.25 && t < c.end)
      || (t >= last.end ? last : null);
    if (!next || next.id === cur?.id || pendingRef.current === next.id) return;
    pendingRef.current = next.id;
    getClip(next.id).then((c) => {
      pendingRef.current = null;
      const s2 = useEditorStore.getState();
      if (s2.clip?.id === c.id) return;
      const tt = videoRef.current?.currentTime ?? t;
      if (tt < c.source_start - 0.5 || tt >= c.source_end) return; // sudah keburu pindah
      s2.setSeekOnSelect(false);
      s2.setClip(c);
      s2.setKeyframes(c.keyframes || []);
    }).catch(() => { pendingRef.current = null; });
  };

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    let raf = 0;
    const loop = () => {
      const cur = useEditorStore.getState().clip;
      if (cur && v.currentTime >= cur.source_end - 0.12) {
        v.pause();
        v.currentTime = cur.source_end;
        setCurrentTime(v.currentTime);
        return;
      }
      setCurrentTime(v.currentTime);
      followSegment();
      if (!v.paused) raf = requestAnimationFrame(loop);
    };
    const onTime = () => {
      const cur = useEditorStore.getState().clip;
      if (cur && videoRef.current && videoRef.current.currentTime >= cur.source_end - 0.12) {
        videoRef.current.pause();
        videoRef.current.currentTime = cur.source_end;
      }
      setCurrentTime(v.currentTime);
    };
    const onPlay = () => { setIsPlaying(true); raf = requestAnimationFrame(loop); };
    const onPause = () => { setIsPlaying(false); cancelAnimationFrame(raf); setCurrentTime(v.currentTime); };
    const onSeek = () => {
      const cur = useEditorStore.getState().clip;
      const t = v.currentTime;
      if (cur && (t < cur.source_start - 0.5 || t > cur.source_end + 0.5)) {
        v.currentTime = cur.source_start;
      }
      setCurrentTime(v.currentTime);
      followSegment();
    };
    v.addEventListener("timeupdate", onTime);
    v.addEventListener("play", onPlay);
    v.addEventListener("pause", onPause);
    v.addEventListener("seeked", onSeek);
    return () => { cancelAnimationFrame(raf); v.removeEventListener("timeupdate", onTime); v.removeEventListener("play", onPlay); v.removeEventListener("pause", onPause); v.removeEventListener("seeked", onSeek); };
  }, []);

  useEffect(() => {
    // hanya seek saat klik user; auto-follow saat play jalan terus tanpa lompat
    const st = useEditorStore.getState();
    if (clip && st.seekOnSelect && videoRef.current) {
      const v = videoRef.current;
      if (Math.abs(v.currentTime - clip.source_start) > 1) v.currentTime = clip.source_start;
      st.setSeekOnSelect(false);
    }
  }, [clip?.id]);

  return (
    <video
      ref={videoRef}
      src={videoSrc}
      style={{ width: "100%", height: "100%", objectFit: "contain", background: "#000", display: "block" }}
      controls
    />
  );
}
