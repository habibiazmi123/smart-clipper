import json
import subprocess
import shutil
from pathlib import Path


def extract_metadata(video_path: str) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", video_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    data = json.loads(result.stdout)
    vstream = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    astream = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    duration = float(data["format"].get("duration", 0))
    fps_str = vstream.get("r_frame_rate", "30/1") if vstream else "30/1"
    num, den = [int(x) for x in fps_str.split("/")]
    fps = num / den if den else 30.0
    return {
        "duration": duration,
        "width": int(vstream["width"]) if vstream else 0,
        "height": int(vstream["height"]) if vstream else 0,
        "fps": fps,
        "has_audio": astream is not None,
        "title": Path(video_path).stem,
        "channel": "",
    }


def download_video(project_id: str, url: str, project_dir: Path) -> Path:
    import uuid
    out_dir = project_dir / "source"
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / f"{uuid.uuid4().hex[:12]}.%(ext)s"
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(tmp),
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr}")
    for f in out_dir.iterdir():
        if f.suffix == ".mp4":
            return f
    raise FileNotFoundError("No output from yt-dlp")


def extract_audio(video_path: str, project_dir: Path) -> Path:
    audio_dir = project_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    out = audio_dir / "audio.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn",
         "-ar", "16000", "-ac", "1", "-acodec", "pcm_s16le", str(out)],
        capture_output=True,
    )
    if not out.exists():
        raise RuntimeError("Audio extraction failed")
    return out
