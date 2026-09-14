import json
import logging
import subprocess
import shutil
from pathlib import Path

log = logging.getLogger(__name__)


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


def fetch_youtube_title(url: str) -> str | None:
    try:
        result = subprocess.run(
            ["yt-dlp", "--no-download", "--print", "%(title)s", url],
            capture_output=True, text=True, timeout=15,
        )
        title = result.stdout.strip()
        if title and result.returncode == 0:
            return title
    except Exception:
        pass
    return None


def download_video(project_id: str, url: str, project_dir: Path, on_progress=None) -> Path:
    import uuid
    log.info("[download] pid=%s starting url=%s", project_id, url)
    out_dir = project_dir / "source"
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / f"{uuid.uuid4().hex[:12]}.%(ext)s"
    cmd = [
        "yt-dlp",
        "--newline",
        "--progress",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "--merge-output-format", "mp4",
        "-o", str(tmp),
        url,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    last_pct = -1
    for line in proc.stdout:
        line = line.strip()
        if "%" in line and "of" in line:
            try:
                pct_str = line.split("%")[0].split()[-1]
                pct = float(pct_str) / 100.0
                pct_i = int(pct * 100)
                if pct_i != last_pct and pct_i % 5 == 0:
                    log.info("[download] pid=%s %.0f%% %s", project_id, pct * 100, line[:120])
                    last_pct = pct_i
                if on_progress:
                    on_progress(min(max(pct, 0.0), 1.0))
            except Exception:
                pass
        elif line:
            log.debug("[download] pid=%s %s", project_id, line[:300])
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"yt-dlp failed (code {proc.returncode})")
    for f in out_dir.iterdir():
        if f.suffix == ".mp4":
            sz = f.stat().st_size / 1024 / 1024
            log.info("[download] pid=%s done -> %s (%.1f MB)", project_id, f.name, sz)
            return f
    raise FileNotFoundError("No output from yt-dlp")


def extract_audio(video_path: str, project_dir: Path) -> Path:
    log.info("[audio] extracting %s", video_path)
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
    log.info("[audio] done -> %s (%.1f MB)", out, out.stat().st_size / 1024 / 1024)
    return out
