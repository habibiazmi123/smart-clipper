const BASE = "http://127.0.0.1:8719/api";

export async function fetchJSON<T = any>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function createProject(name: string, url: string) {
  return fetchJSON("/projects", {
    method: "POST",
    body: JSON.stringify({ name, url }),
  });
}

export async function listProjects() {
  return fetchJSON("/projects");
}

export async function getProject(id: string) {
  return fetchJSON(`/projects/${id}`);
}

export async function analyzeProject(id: string, numClips = 5, maxDuration = 60, aspectRatio = "9:16") {
  return fetchJSON(`/projects/${id}/analyze`, {
    method: "POST",
    body: JSON.stringify({ num_clips: numClips, max_duration: maxDuration, aspect_ratio: aspectRatio }),
  });
}

export async function getClip(id: string) {
  return fetchJSON(`/clips/${id}`);
}

export async function updateClip(id: string, data: Record<string, any>) {
  return fetchJSON(`/clips/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function updateKeyframes(clipId: string, keyframes: any[]) {
  return fetchJSON(`/clips/${clipId}/keyframes`, {
    method: "POST",
    body: JSON.stringify({ keyframes }),
  });
}

export async function resetCropToAI(clipId: string) {
  return fetchJSON(`/clips/${clipId}/reset-crop`, { method: "POST" });
}

export async function getJob(jobId: string) {
  return fetchJSON(`/jobs/${jobId}`);
}

export async function getCaptions(clipId: string) {
  return fetchJSON(`/clips/${clipId}/captions`);
}

export async function editSegment(segId: number, text: string) {
  return fetchJSON(`/transcript-segments/${segId}`, {
    method: "PATCH",
    body: JSON.stringify({ text }),
  });
}

export function hexToAss(hex: string): string {
  const h = hex.replace("#", "");
  const full = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
  const r = full.slice(0, 2), g = full.slice(2, 4), b = full.slice(4, 6);
  return `&H00${b}${g}${r}`.toUpperCase();
}

export async function exportClip(clipId: string, style: Record<string, any>): Promise<Blob> {
  const res = await fetch(`${BASE}/clips/${clipId}/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ style }),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.blob();
}

// ---- auto render: edit teks/gaya -> preview langsung, mp4 menyusul ----
import { useEditorStore } from "../stores/editor";

let autoTimer: any = null;

export function assStyleFromUi(cs: any): Record<string, any> {
  const pos = cs.position;
  return {
    font_size: cs.fontSize,
    primary: hexToAss(cs.active),
    secondary: hexToAss(cs.upcoming),
    alignment: pos === "top" ? 8 : pos === "middle" ? 5 : 2,
    margin_bottom: pos === "middle" ? 20 : 140,
  };
}

export async function refreshClipCaptions(clipId: string): Promise<void> {
  const d = await getCaptions(clipId);
  const st = useEditorStore.getState();
  if (st.clip?.id !== clipId) return;
  st.setClipWords(d.words || []);
  st.setClipSegments(d.segments || []);
}

export async function renderCurrentClip(): Promise<boolean> {
  const st = useEditorStore.getState();
  if (!st.clip || st.exporting) return false;
  st.setExporting(true);
  const cid = st.clip.id;
  try {
    const blob = await exportClip(cid, assStyleFromUi(st.captionStyle));
    // hasil disimpan per-segmen: tetap valid walau user sudah pindah segmen
    useEditorStore.getState().setRenderResult(
      URL.createObjectURL(blob), new Date().toLocaleTimeString(), cid);
    return true;
  } catch {
    return false;
  } finally {
    useEditorStore.getState().setExporting(false);
  }
}

export function scheduleAutoRender(delayMs = 5000): void {
  const st = useEditorStore.getState();
  if (!st.autoRender || !st.clip || st.exporting) return;
  clearTimeout(autoTimer);
  autoTimer = setTimeout(() => { renderCurrentClip(); }, delayMs);
}
