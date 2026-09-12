import os
from pathlib import Path
from dataclasses import dataclass, field

def _load_env():
    vals: dict[str, str] = {}
    _env = Path(__file__).parent.parent / ".env"
    if _env.exists():
        for _line in _env.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _k, _v = _k.strip(), _v.strip()
                vals[_k] = _v
                os.environ.setdefault(_k, _v)
    return vals

_ENV = _load_env()


@dataclass(frozen=True)
class Settings:
    DATA_ROOT: Path = Path("./data")
    WHISPER_MODEL: str = "mlx-community/whisper-small-mlx"
    FACE_MODEL: str = str(Path(__file__).parent.parent / "assets" / "blaze_face_short_range.tflite")
    LLM_MODEL: str = "llama3.2:latest"
    OLLAMA_URL: str = "http://127.0.0.1:11434"
    GROQ_API_KEY: str = _ENV.get("GROQ_API_KEY", "")  # type: ignore[name-defined]
    GROQ_MODEL: str = _ENV.get("GROQ_MODEL", "openai/gpt-oss-120b")  # type: ignore[name-defined]
    GROQ_URL: str = "https://api.groq.com/openai/v1/chat/completions"
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
    SMOOTHING_ALPHA: float = 0.35
    # ponytail: 0.15 butuh ~10 sampel untuk konvergen (rect ketinggalan wajah);
    # 0.35 konvergen ~4 sampel, detector cukup stabil sehingga tetap halus.
    # deadzone 0.02 membekukan pan pelan (0.50->0.62 tidak gerak); 0.005 cukup lawan jitter
    SMOOTHING_DEADZONE: float = 0.005
    KEYFRAME_INTERVAL: float = 0.5
    FACE_SAMPLE_INTERVAL: float = 0.1  # every ~3rd frame at 30fps
    # active speaker v1 (PRD): hysteresis agar tanggapan singkat tidak switch
    SPEAKER_SWITCH_MARGIN: float = 0.15
    SPEAKER_MIN_DWELL_SEC: float = 1.5  # challenger unggul selama ini baru switch
    SPEAKER_HOLD_SEC: float = 1.0  # wajah hilang sesaat -> tahan framing
    # takeover karena pembicara pergi: wajah yang cocok ke track basi
    # (>2s tak terlihat, biasanya shot cut) dapat ID BARU, bukan warisi ID lama
    SPEAKER_STALE_TAKEOVER_SEC: float = 2.0
    SPEAKER_SILENCE_RMS: float = 0.03  # kalibrasi: speech 0.09-0.18, sunyi 0.0
    SPEAKER_MOUTH_ALPHA: float = 0.4
    SPEAKER_IOU_THRESHOLD: float = 0.3
    SPEAKER_TRACK_MEMORY_SEC: float = 30.0  # ingat wajah lama: kembali = ID sama
    SPEAKER_MOUTH_DT: float = 0.12  # pasang frame pembanding untuk mouth-motion


settings = Settings()
