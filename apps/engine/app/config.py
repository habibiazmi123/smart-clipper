from pathlib import Path
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    DATA_ROOT: Path = Path("./data")
    WHISPER_MODEL: str = "mlx-community/whisper-small-mlx"
    FACE_MODEL: str = "apps/engine/assets/blaze_face_short_range.tflite"
    LLM_MODEL: str = "llama3.2:latest"
    OLLAMA_URL: str = "http://127.0.0.1:11434"
    HOST: str = "127.0.0.1"
    PORT: int = 8719
    CHUNK_SIZE: int = 16000  # whisper expects 16kHz mono
    VIDEO_EXTENSIONS: tuple = (".mp4", ".mov", ".mkv", ".webm")
    HOOK_SCORE_WEIGHTS: dict = field(default_factory=lambda: {
        "curiosity": 0.15,
        "emotional_intensity": 0.10,
        "specificity": 0.10,
        "novelty": 0.10,
        "conflict": 0.10,
        "payoff": 0.15,
        "self_contained": 0.10,
        "speech_energy": 0.05,
        "context_completeness": 0.10,
        "llm_score": 0.05,
    })
    SMOOTHING_ALPHA: float = 0.15
    SMOOTHING_DEADZONE: float = 0.02
    KEYFRAME_INTERVAL: float = 0.5
    FACE_SAMPLE_INTERVAL: float = 0.1  # every ~3rd frame at 30fps


settings = Settings()
