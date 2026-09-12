import { useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getProject, getClip } from "../lib/api";
import { useEditorStore } from "../stores/editor";
import VideoPlayer from "./VideoPlayer";
import CropOverlay from "./CropOverlay";
import Timeline from "./Timeline";
import Sidebar from "./Sidebar";

export default function Editor() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { setProject, setClip, setKeyframes, project, setVideoRef } = useEditorStore();
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (videoRef.current) setVideoRef(videoRef);
  }, []);

  useEffect(() => {
    if (!projectId) return;
    getProject(projectId).then(setProject).catch(() => navigate("/"));
  }, [projectId]);

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
            </div>
          </div>
          <Timeline />
        </div>
        <Sidebar />
      </div>
    </div>
  );
}
