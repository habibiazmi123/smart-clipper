import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getProject, getClip, getCaptions, scheduleAutoRender } from "../lib/api";
import { dominantSpeaker } from "../lib/speakers";
import { useEditorStore } from "../stores/editor";
import VideoPlayer from "./VideoPlayer";
import CropOverlay from "./CropOverlay";
import CaptionOverlay from "./CaptionOverlay";
import Timeline from "./Timeline";
import Sidebar from "./Sidebar";

export default function Editor() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { setProject, setClip, setKeyframes, setClipWords, setClipSegments, project, clip, captionStyle, setVideoRef, setClipSpeakers, setClipAvgX } = useEditorStore();
  const videoRef = useRef<HTMLVideoElement>(null);
  const lastStyleKey = useRef<string | null>(null);

  useEffect(() => {
    if (videoRef.current) setVideoRef(videoRef);
  }, []);

  useEffect(() => {
    if (!projectId) return;
    getProject(projectId).then(setProject).catch(() => navigate("/"));
  }, [projectId]);

  // meta per-segmen (avg crop + speaker dominan) untuk warna timeline/sidebar
  useEffect(() => {
    if (!project?.clips?.length) return;
    let alive = true;
    (async () => {
      const spk: Record<string, string | null> = {};
      const avg: Record<string, number> = {};
      await Promise.all(project.clips.slice(0, 15).map(async (c: any) => {
        try {
          const d = await getClip(c.id);
          const kfs = d.keyframes || [];
          if (kfs.length) {
            avg[c.id] = kfs.reduce((s: number, k: any) => s + k.center_x, 0) / kfs.length;
            spk[c.id] = dominantSpeaker(kfs);
          }
        } catch {}
      }));
      if (alive) { setClipSpeakers(spk); setClipAvgX(avg); }
    })();
    return () => { alive = false; };
  }, [project?.id]);

  useEffect(() => {
    if (!project?.clips?.length) return;
    getClip(project.clips[0].id).then((c) => {
      setClip(c);
      setKeyframes(c.keyframes || []);
      if (videoRef.current) {
        videoRef.current.currentTime = c.source_start;
      }
    }).catch(() => {});
  }, [project]);

  // gaya caption diubah -> ikut auto-render (debounced; mount pertama skip)
  useEffect(() => {
    const key = JSON.stringify(captionStyle);
    if (lastStyleKey.current === null) { lastStyleKey.current = key; return; }
    if (lastStyleKey.current !== key) { lastStyleKey.current = key; scheduleAutoRender(); }
  }, [captionStyle]);
  useEffect(() => {
    if (!clip?.id) return;
    let alive = true;
    getCaptions(clip.id).then((d) => {
      if (!alive) return;
      setClipWords(d.words || []);
      setClipSegments(d.segments || []);
    }).catch(() => {});
    return () => { alive = false; };
  }, [clip?.id]);

  return (
    <div className="app" style={{ background: "#0b0e1a" }}>
      <div className="top-bar">
        <button className="btn" onClick={() => navigate("/")}>← Campaign Detail</button>
        <h1 style={{ fontSize: 13 }}>{project?.name || "Loading..."} <span style={{ color: "var(--text-dim)", fontWeight: 400 }}>/ {project?.status === "ready" ? "🟢 Edited" : project?.status || ""} / {project?.clips?.length || 0} segment</span></h1>
        <div style={{ flex: 1 }} />
        <button className="btn">⭳ Download</button>
        <button className="btn primary">💾 Simpan</button>
      </div>
      <div style={{ display: "flex", flex: 1, overflow: "hidden", gap: 12, padding: 12 }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", background: "#151929", borderRadius: 10, border: "1px solid #2a2f4a", overflow: "hidden" }}>
          <div style={{ padding: "8px 12px", fontSize: 11, color: "var(--text-dim)", display: "flex", justifyContent: "flex-end" }}>
            <span style={{ background: "#f59e0b33", color: "#fbbf24", padding: "2px 10px", borderRadius: 6, fontWeight: 700 }}>✂ Cut</span>
          </div>
          <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: "0 16px", minHeight: 0 }}>
            <div style={{ position: "relative", width: "100%", maxWidth: 860, aspectRatio: "16/9", background: "#000", borderRadius: 8, overflow: "hidden" }}>
              <VideoPlayer videoSrc={`http://127.0.0.1:8719/api/media/${projectId}/video`} videoRef={videoRef} />
              <CropOverlay />
              <CaptionOverlay />
              <MuteButton />
            </div>
          </div>
          <Timeline />
        </div>
        <Sidebar />
      </div>
    </div>
  );
}

function MuteButton() {
  const { videoRef } = useEditorStore();
  const [muted, setMuted] = useState(false);
  useEffect(() => {
    const v = videoRef?.current;
    if (!v) return;
    const upd = () => setMuted(v.muted);
    v.addEventListener("volumechange", upd);
    upd();
    return () => v.removeEventListener("volumechange", upd);
  }, [videoRef]);
  return (
    <button
      onClick={() => { const v = videoRef?.current; if (v) v.muted = !v.muted; }}
      title={muted ? "Unmute (suara nyala)" : "Mute (bisukan)"}
      style={{ position: "absolute", top: 10, right: 10, zIndex: 5, width: 34, height: 34, borderRadius: "50%",
        background: "rgba(0,0,0,0.6)", border: "1px solid #ffffff33", cursor: "pointer",
        display: "flex", alignItems: "center", justifyContent: "center" }}
    >
      {muted ? (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#f87171" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" fill="#f87171" stroke="none" />
          <line x1="23" y1="9" x2="17" y2="15" /><line x1="17" y1="9" x2="23" y2="15" />
        </svg>
      ) : (
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" fill="#fff" stroke="none" />
          <path d="M15.54 8.46a5 5 0 0 1 0 7.07" /><path d="M19.07 4.93a10 10 0 0 1 0 14.14" />
        </svg>
      )}
    </button>
  );
}
