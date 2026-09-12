// Satu map warna speaker untuk seluruh UI: blok timeline, rectangle crop,
// badge, dan dot sidebar selalu merujuk orang yang sama.
export const SPEAKER_COLORS = [
  "#8b5cf6", // A - ungu
  "#22c55e", // B - hijau
  "#f59e0b", // C - amber
  "#06b6d4", // D - cyan
  "#ec4899", // E - pink
  "#a855f7", // F - ungu tua
];

export function speakerColor(speaker: string | null | undefined, fallbackIndex = 0): string {
  if (!speaker) return SPEAKER_COLORS[fallbackIndex % SPEAKER_COLORS.length];
  const i = speaker.toUpperCase().charCodeAt(0) - 65;
  if (i >= 0 && i < 26) return SPEAKER_COLORS[i % SPEAKER_COLORS.length];
  return SPEAKER_COLORS[fallbackIndex % SPEAKER_COLORS.length];
}

export function dominantSpeaker(keyframes: { speaker?: string | null }[]): string | null {
  const counts: Record<string, number> = {};
  for (const k of keyframes) if (k.speaker) counts[k.speaker] = (counts[k.speaker] || 0) + 1;
  let best: string | null = null, n = 0;
  for (const [s, c] of Object.entries(counts)) if (c > n) { best = s; n = c; }
  return best;
}
