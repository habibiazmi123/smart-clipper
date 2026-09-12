import json
import logging
import math
import time
from app.config import settings

log = logging.getLogger(__name__)


def transcribe(audio_path: str) -> dict:
    """Transcribe audio using mlx-whisper. Returns float timestamps."""
    log.info("[transcribe] start %s", audio_path)
    t0 = time.time()
    import mlx_whisper
    result = mlx_whisper.transcribe(
        audio_path,
        path_or_hf_repo=settings.WHISPER_MODEL,
        word_timestamps=True,
    )
    segments = []
    for s in result.get("segments", []):
        words = []
        for w in s.get("words", []):
            words.append({
                "word": str(w["word"]),
                "start": float(w["start"]),
                "end": float(w["end"]),
                "probability": float(w["probability"]),
            })
        avg_logprob = s.get("avg_logprob", -1.0)
        segments.append({
            "idx": int(s.get("id", len(segments))),
            "start": float(s["start"]),
            "end": float(s["end"]),
            "text": str(s.get("text", "")),
            "confidence": float(math.exp(avg_logprob)) if avg_logprob is not None else 0.0,
            "words_json": json.dumps(words),
        })
    dur = segments[-1]["end"] if segments else 0
    log.info("[transcribe] done lang=%s segs=%d words=%d dur=%.1fs took=%.1fs",
             result.get("language", ""), len(segments),
             sum(len(json.loads(s["words_json"])) for s in segments), dur, time.time() - t0)
    return {
        "language": result.get("language", ""),
        "segments": segments,
    }
