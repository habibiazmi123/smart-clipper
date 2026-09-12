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
      // seek video to clip start
      if (videoRef.current) {
        videoRef.current.currentTime = c.source_start;
      }
    }).catch(() => {});
  }, [project]);

  return (
    <div className="app">
      <div className="top-bar">
        <button className="btn" onClick={() => navigate("/")}>Back</button>
        <h1>{project?.name || "Loading..."}</h1>
        <span className={`status-badge ${project?.status || "processing"}`}>
          {project?.status || "processing"}
        </span>
        <div style={{ flex: 1 }} />
        {project?.clips && <span style={{ fontSize: 12, color: "var(--text-dim)" }}>{project.clips.length} clips</span>}
      </div>
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
          <div style={{ flex: 1, padding: 16, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <VideoPlayer videoSrc={`http://127.0.0.1:8719/api/media/${projectId}/video`} videoRef={videoRef} />
          </div>
          <CropOverlay />
          <Timeline />
        </div>
        <Sidebar />
      </div>
    </div>
  );
}
