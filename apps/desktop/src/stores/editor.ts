import { create } from "zustand";

interface Keyframe {
  time: number;
  center_x: number;
  center_y: number;
  source?: string;
}

interface EditorState {
  projectId: string;
  project: any;
  clip: any;
  keyframes: Keyframe[];
  currentTime: number;
  isPlaying: boolean;
  selectedTab: "crop" | "script" | "effect";
  setProject: (p: any) => void;
  setClip: (c: any) => void;
  setKeyframes: (k: Keyframe[]) => void;
  setCurrentTime: (t: number) => void;
  setIsPlaying: (p: boolean) => void;
  setSelectedTab: (t: "crop" | "script" | "effect") => void;
}

export const useEditorStore = create<EditorState>((set) => ({
  projectId: "",
  project: null,
  clip: null,
  keyframes: [],
  currentTime: 0,
  isPlaying: false,
  selectedTab: "crop",
  setProject: (p) => set({ project: p }),
  setClip: (c) => set({ clip: c }),
  setKeyframes: (k) => set({ keyframes: k }),
  setCurrentTime: (t) => set({ currentTime: t }),
  setIsPlaying: (p) => set({ isPlaying: p }),
  setSelectedTab: (t) => set({ selectedTab: t }),
}));
