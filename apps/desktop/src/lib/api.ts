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
