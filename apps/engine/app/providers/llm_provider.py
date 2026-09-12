"""Transcript-text -> viral hooks. Groq primary, heuristic fallback. Stdlib only."""
import json
import logging
import os
import re
import time
import urllib.request

log = logging.getLogger(__name__)

PROMPT = ("You are a short-form video editor. Given transcript lines as "
          "[start-end] text, return JSON array of top hooks: "
          '[{"start":float,"end":float,"score":0-100,"hook_text":str,"reasons":[str],"weakness":str}]. '
          "Each clip <= MAX_DUR seconds. Prefer curiosity, contrarian claims, payoff, specificity.")


def chunk_transcript(segments, max_chars=60000):
    chunks, cur, cur_len = [], [], 0
    for s in segments:
        line = f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}\n"
        if cur and cur_len + len(line) > max_chars:
            chunks.append(cur)
            cur, cur_len = [], 0
        cur.append(s)
        cur_len += len(line)
    if cur:
        chunks.append(cur)
    return chunks


def _word_bounds(segments):
    starts, ends = [], []
    for s in segments:
        try:
            ws = json.loads(s.get("words_json") or "[]")
        except Exception:
            ws = []
        for w in ws:
            starts.append(float(w["start"]))
            ends.append(float(w["end"]))
    return sorted(starts), sorted(ends)


def validate_and_snap_hooks(raw, segments, max_duration):
    starts, ends = _word_bounds(segments)

    def snap_start(t):
        if not starts:
            return round(max(t, 0.0), 3)
        return round(min(starts, key=lambda b: abs(b - t)), 3)

    def snap_end(t):
        if not ends:
            return round(max(t, 0.0), 3)
        return round(min(ends, key=lambda b: abs(b - t)), 3)

    dur = segments[-1]["end"] if segments else 0.0
    ends_sorted = sorted(ends)
    out = []
    for h in raw:
        try:
            s, e = float(h["start"]), float(h["end"])
        except Exception:
            continue
        s, e = max(0.0, s), min(dur or e, e)
        if e - s > max_duration:
            e = s + max_duration
        # Groq sering kasih hook 2-10s; expand ke max_duration agar klip ~60s
        # hook di awal window, sisanya konteks
        if e - s < max_duration * 0.6:
            target_end = min(dur, s + max_duration)
            # snap target_end ke word end terdekat agar tidak potong kata
            if ends_sorted:
                target_end = min(ends_sorted, key=lambda b: abs(b - target_end))
                # jangan mundur di bawah e asli
                if target_end < e:
                    target_end = e
            e = target_end
        if e <= s:
            continue
        out.append({"start": snap_start(s), "end": snap_end(e),
                    "score": max(0.0, min(100.0, float(h.get("score", 50)))),
                    "hook_text": str(h.get("hook_text", ""))[:300],
                    "reasons": list(h.get("reasons", []))[:6],
                    "weakness": str(h.get("weakness", ""))[:300],
                    "source": h.get("source", "groq")})
    return sorted(out, key=lambda h: h["score"], reverse=True)


def dedupe_hooks(hooks, iou_thresh=0.5):
    kept = []
    for h in sorted(hooks, key=lambda x: x["score"], reverse=True):
        overlap = False
        for k in kept:
            inter = max(0.0, min(h["end"], k["end"]) - max(h["start"], k["start"]))
            union = max(h["end"], k["end"]) - min(h["start"], k["start"])
            if union > 0 and inter / union > iou_thresh:
                overlap = True
                break
        if not overlap:
            kept.append(h)
    return kept


def _groq_call(transcript_text, n, max_duration, model, api_key, url):
    body = json.dumps({"model": model, "temperature": 0.3, "max_tokens": 4000,
                       "messages": [{"role": "system", "content": PROMPT + f" MAX_DUR={max_duration} TOP_N={n}."},
                                    {"role": "user", "content": transcript_text[:90000]}]}).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json",
                                          "Authorization": f"Bearer {api_key}",
                                          "User-Agent": "SmartClipper/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read().decode())
    content = data["choices"][0]["message"]["content"]
    m = re.search(r"\[.*\]", content, re.S)
    return json.loads(m.group(0) if m else content)


def _heuristic_fallback(segments, n, max_duration):
    import random
    from app.domain.hooks import generate_candidates, score_candidate
    dur = segments[-1]["end"] if segments else 0.0
    cands = [c for c in generate_candidates(segments, dur) if c["end"] - c["start"] <= max_duration]
    scored = []
    for c in cands:
        s, reasons, weak = score_candidate(c, segments)
        scored.append({"start": c["start"], "end": c["end"], "score": s,
                       "hook_text": "", "reasons": reasons,
                       "weakness": "; ".join(weak), "source": "heuristic"})
    scored.sort(key=lambda h: h["score"], reverse=True)
    deduped = dedupe_hooks(scored, iou_thresh=0.35)
    if len(deduped) < n and scored:
        random.seed(42)
        pool = [h for h in scored if h not in deduped]
        random.shuffle(pool)
        for h in pool:
            if len(deduped) >= n:
                break
            deduped.append(h)
    return deduped[:n]


def find_hooks(segments, n=3, max_duration=60):
    from app.config import settings
    api_key = os.environ.get("GROQ_API_KEY", "") or getattr(settings, "GROQ_API_KEY", "")
    if not segments:
        return []
    if not api_key:
        log.info("[hooks] no GROQ_API_KEY -> heuristic fallback")
        return _heuristic_fallback(segments, n, max_duration)
    model = os.environ.get("GROQ_MODEL", "") or getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
    url = getattr(settings, "GROQ_URL", "https://api.groq.com/openai/v1/chat/completions")
    t0 = time.time()
    all_hooks = []
    chunks = chunk_transcript(segments)
    log.info("[hooks] start model=%s chunks=%d top_n=%d max_dur=%ds", model, len(chunks), n, max_duration)
    for i, chunk in enumerate(chunks):
        text = "\n".join(f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in chunk)
        try:
            raw = _groq_call(text, n, max_duration, model, api_key, url)
            for h in validate_and_snap_hooks(raw, chunk, max_duration):
                h["source"] = "groq"
                all_hooks.append(h)
            log.info("[hooks] chunk %d/%d -> %d raw hooks", i + 1, len(chunks), len(raw))
        except Exception as e:
            log.warning("[hooks] chunk %d/%d failed: %s", i + 1, len(chunks), e)
            continue
    if not all_hooks:
        log.info("[hooks] no LLM results -> heuristic fallback")
        return _heuristic_fallback(segments, n, max_duration)
    deduped = dedupe_hooks(all_hooks)
    if len(deduped) < n:
        fill = _heuristic_fallback(segments, n * 2, max_duration)
        for h in fill:
            if len(deduped) >= n:
                break
            if not any((max(0, min(h["end"], k["end"]) - max(h["start"], k["start"])) / max(h["end"] - h["start"], k["end"] - k["start"], 1)) > 0.35 for k in deduped):
                deduped.append(h)
    deduped = deduped[:n]
    log.info("[hooks] done total=%d deduped=%d took=%.1fs", len(all_hooks), len(deduped), time.time() - t0)
    return deduped
