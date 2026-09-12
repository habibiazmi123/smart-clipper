import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate, useSearchParams } from "react-router-dom";
import { getProject, getClip, getCaptions, scheduleAutoRender, exportCurrentClipWithProgress, cancelCurrentExport } from "../lib/api";
import { dominantSpeaker } from "../lib/speakers";
import { useEditorStore } from "../stores/editor";
import VideoPlayer from "./VideoPlayer";
import CropOverlay from "./CropOverlay";
import CaptionOverlay from "./CaptionOverlay";
import Timeline from "./Timeline";
import Sidebar from "./Sidebar";

export default function Editor() {
  const { projectId } = useParams();
  const [searchParams] = useSearchParams();
  const clipParam = searchParams.get("clip");
  const navigate = useNavigate();
  const { setProject, setClip, setKeyframes, setClipWords, setClipSegments, project, clip, captionStyle, setVideoRef, setClipSpeakers, setClipAvgX, exporting, exportProgress } = useEditorStore();
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
    const targetId = clipParam && project.clips.some((c: any) => c.id === clipParam) ? clipParam : project.clips[0].id;
    getClip(targetId).then((c) => {
      setClip(c);
      setKeyframes(c.keyframes || []);
      if (videoRef.current) videoRef.current.currentTime = c.source_start;
    }).catch(() => {});
  }, [project, clipParam]);

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
    <div className="app">
      <div className="top-bar">
        <button className="btn ghost sm" onClick={() => navigate("/")} aria-label="Back to projects">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M19 12H5" /><path d="m12 19-7-7 7-7" /></svg>
          Projects
        </button>
        <span aria-hidden style={{ width: 1, height: 20, background: "var(--border-strong)" }} />
        <h1>{project?.name || "Loading..."}</h1>
        <span className={`status-pill ${project?.status === "ready" ? "ready" : "processing"}`}>
          <span className="dot" aria-hidden />
          {project?.status === "ready" ? "Edited" : project?.status === "processing" ? "Processing" : project?.status || "…"}
        </span>
        <span className="top-meta tabular">{project?.clips?.length || 0} segments{typeof project?.duration === "number" ? ` · ${Math.round(project.duration)}s` : ""}</span>
        <div style={{ flex: 1 }} />
        {exporting && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 160 }}>
            <div className="progress-track" role="progressbar" aria-valuenow={Math.round((exportProgress ?? 0) * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Export progress">
              <div className="progress-fill" style={{ width: `${Math.round((exportProgress ?? 0) * 100)}%` }} />
            </div>
            <button className="btn sm" onClick={() => cancelCurrentExport()}>Cancel</button>
          </div>
        )}
        <button className="btn sm" disabled={!clip || exporting} onClick={() => exportCurrentClipWithProgress(true)}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" x2="12" y1="15" y2="3" /></svg>
          {exporting ? `Rendering ${exportProgress != null ? Math.round(exportProgress * 100) + "%" : ""}` : "Export"}</button>
        <button className="btn primary sm">Save</button>
      </div>
      <div className="editor-shell">
        <div className="preview-pane">
          <div style={{ padding: "10px 14px 0", display: "flex", alignItems: "center", gap: 8 }}>
            <span className="status-pill" style={{ fontSize: 11, color: "#fbbf24", borderColor: "rgba(245,158,11,.3)", background: "rgba(245,158,11,.08)" }}>
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden><circle cx="6" cy="6" r="3" /><circle cx="6" cy="18" r="3" /><line x1="20" x2="8.12" y1="4" y2="4" /><line x1="14.47" x2="20" y1="14.34" y2="20" /><line x1="14.47" x2="20" y1="9.66" y2="4" /></svg>
              Cut · 9:16 smart crop
            </span>
            <div style={{ flex: 1 }} />
            {clip && <span className="top-meta tabular" style={{ fontSize: 11 }}>clip {clip.id?.slice(0, 8)}</span>}
          </div>
          <div className="preview-stage">
            <div className="preview-frame">
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
