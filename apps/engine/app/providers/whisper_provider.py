import json
import math
from app.config import settings


def transcribe(audio_path: str) -> dict:
    """Transcribe audio using mlx-whisper. Returns float timestamps."""
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
    return {
        "language": result.get("language", ""),
        "segments": segments,
    }
