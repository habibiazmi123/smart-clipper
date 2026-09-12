import { create } from "zustand";

interface Keyframe {
  time: number;
  center_x: number;
  center_y: number;
  source?: string;
  speaker?: string | null;
}

export interface CaptionStyle {
  preset: "hormozi" | "beast" | "minimal";
  fontSize: number; // px pada 1080p, preview diskala dari lebar crop
  active: string; // warna kata aktif (hex)
  upcoming: string; // warna kata lain (hex)
  position: "bottom" | "middle" | "top";
  stroke: boolean;
}

const storedStyle = (): CaptionStyle => {
  try {
    const s = JSON.parse(localStorage.getItem("sc_caption_style") || "");
    if (s && typeof s.fontSize === "number") return s;
  } catch {}
  return { preset: "hormozi", fontSize: 64, active: "#FFFF00", upcoming: "#FFFFFF", position: "bottom", stroke: true };
};

interface EditorState {
  projectId: string;
  project: any;
  clip: any;
  keyframes: Keyframe[];
  currentTime: number;
  isPlaying: boolean;
  selectedTab: "crop" | "script" | "effect";
  videoRef: { current: HTMLVideoElement | null } | null;
  // true = klik user (lompat ke awal segmen), false = auto-follow saat play (jangan seek)
  seekOnSelect: boolean;
  clipWords: { w: string; start: number; end: number }[];
  clipSegments: { id: number; start: number; end: number; text: string }[];
  captionStyle: CaptionStyle;
  exporting: boolean;
  autoRender: boolean;
  renderResults: Record<string, { url: string; time: string }>;
  setProject: (p: any) => void;
  setClip: (c: any) => void;
  setKeyframes: (k: Keyframe[]) => void;
  setCurrentTime: (t: number) => void;
  setIsPlaying: (p: boolean) => void;
  setSelectedTab: (t: "crop" | "script" | "effect") => void;
  setVideoRef: (r: { current: HTMLVideoElement | null }) => void;
  setSeekOnSelect: (v: boolean) => void;
  setClipWords: (w: EditorState["clipWords"]) => void;
  setClipSegments: (s: EditorState["clipSegments"]) => void;
  setCaptionStyle: (s: Partial<CaptionStyle>) => void;
  setExporting: (v: boolean) => void;
  setAutoRender: (v: boolean) => void;
  setRenderResult: (url: string, time: string, clipId: string) => void;
}

export const useEditorStore = create<EditorState>((set) => ({
  projectId: "",
  project: null,
  clip: null,
  keyframes: [],
  currentTime: 0,
  isPlaying: false,
  selectedTab: "crop",
  videoRef: null,
  seekOnSelect: true,
  clipWords: [],
  clipSegments: [],
  captionStyle: storedStyle(),
  exporting: false,
  autoRender: true,
  renderResults: {},
  setProject: (p) => set({ project: p }),
  setClip: (c) => set({ clip: c }),
  setKeyframes: (k) => set({ keyframes: k }),
  setCurrentTime: (t) => set({ currentTime: t }),
  setIsPlaying: (p) => set({ isPlaying: p }),
  setSelectedTab: (t) => set({ selectedTab: t }),
  setVideoRef: (r) => set({ videoRef: r }),
  setSeekOnSelect: (v) => set({ seekOnSelect: v }),
  setClipWords: (w) => set({ clipWords: w }),
  setClipSegments: (s) => set({ clipSegments: s }),
  setCaptionStyle: (s) => set((st) => {
    const next = { ...st.captionStyle, ...s };
    try { localStorage.setItem("sc_caption_style", JSON.stringify(next)); } catch {}
    return { captionStyle: next };
  }),
  setExporting: (v) => set({ exporting: v }),
  setAutoRender: (v) => set({ autoRender: v }),
  setRenderResult: (url, time, clipId) => set((st) => {
    const prev = st.renderResults[clipId];
    if (prev) { try { URL.revokeObjectURL(prev.url); } catch {} }
    return { renderResults: { ...st.renderResults, [clipId]: { url, time } } };
  }),
}));
