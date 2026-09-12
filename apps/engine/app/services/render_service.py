import asyncio
import subprocess
import json
from pathlib import Path
from app.domain.crop import build_crop_expr, crop_window, aspect_to_wh


QUALITY_PRESETS = {
    "fast": {"preset": "veryfast", "crf": 28},
    "balanced": {"preset": "fast", "crf": 23},
    "high": {"preset": "slow", "crf": 18},
}

# dimensi output tetap; filter subtitles jalan SETELAH scale,
# jadi ASS PlayRes harus pakai angka ini (bukan dimensi source)
OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920


def build_render_plan(input_path: str, start: float, end: float,
                      keyframes: list[dict], src_w: int, src_h: int,
                      aspect: str = "9:16",
                      ass_path: str = None,
                      quality: str = "balanced") -> dict:
    q = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["balanced"])
    aw, ah = aspect_to_wh(aspect)
    w = crop_window(src_w, src_h, aw, ah)
    # keyframe times are relative to the clip start (clip-relative)
    clip_kfs = []
    for kf in keyframes:
        clip_kfs.append({
            "time": round(kf["time"] - start, 4),
            "center_x": kf["center_x"],
            "center_y": kf["center_y"],
        })
    return {
        "input": input_path,
        "trim": {"start": start, "end": end},
        "crop": {
            "aspect_ratio": aspect,
            "src_w": src_w,
            "src_h": src_h,
            "crop_w": w["crop_w"],
            "crop_h": w["crop_h"],
            "keyframes": clip_kfs,
        },
        "captions": {"ass_path": ass_path} if ass_path else None,
        "output": {
            "width": OUTPUT_WIDTH,
            "height": OUTPUT_HEIGHT,
            "fps": 30,
            "video_codec": "libx264",
            "audio_codec": "aac",
            "preset": q["preset"],
            "crf": q["crf"],
            "quality": quality if quality in QUALITY_PRESETS else "balanced",
        },
    }


def render_plan_to_ffmpeg_args(plan: dict) -> list[str]:
    args = ["ffmpeg", "-y"]
    args.extend(["-ss", str(plan["trim"]["start"])])
    args.extend(["-i", plan["input"]])
    args.extend(["-t", str(plan["trim"]["end"] - plan["trim"]["start"])])

    crop = plan["crop"]
    aw, ah = aspect_to_wh(crop["aspect_ratio"])
    expr = build_crop_expr(crop["keyframes"], crop["src_w"], crop["src_h"], aw, ah)

    filters = [expr, f"scale={plan['output']['width']}:{plan['output']['height']}"]
    if plan.get("captions") and plan["captions"].get("ass_path"):
        ass = plan["captions"]["ass_path"]
        filters.append(f"subtitles='{ass}'")

    args.extend(["-vf", ",".join(filters)])
    args.extend(["-r", str(plan["output"]["fps"])])
    # ponytail: map eksplisit agar audio tidak pernah hilang diam-diam;
    # 0:a:0? = ikutkan audio bila ada (sumber tanpa audio tetap lolos)
    args.extend(["-map", "0:v:0", "-map", "0:a:0?"])
    args.extend(["-c:v", plan["output"]["video_codec"]])
    args.extend(["-preset", plan["output"]["preset"]])
    args.extend(["-crf", str(plan["output"]["crf"])])
    args.extend(["-c:a", plan["output"]["audio_codec"]])
    args.extend(["-b:a", "128k"])
    return args


def render_clip(plan: dict, output_path: str) -> str:
    args = render_plan_to_ffmpeg_args(plan)
    args.append(output_path)
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg render failed: {result.stderr[-500:]}")
    return output_path


def render_clip_with_progress(plan: dict, output_path: str,
                              on_progress=None, should_cancel=None) -> str:
    """Render sambil lapor progress 0..1 via ffmpeg -progress pipe.

    on_progress(frac) dipanggil dari thread worker; cukup set atribut
    job (polling GET /jobs aman). should_cancel() -> bool; jika True,
    ffmpeg di-terminate dan asyncio.CancelledError dilempar.
    """
    args = render_plan_to_ffmpeg_args(plan)
    args.extend(["-progress", "pipe:1", "-nostats", output_path])
    duration = max(plan["trim"]["end"] - plan["trim"]["start"], 0.01)
    proc = subprocess.Popen(args, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    try:
        for line in proc.stdout:
            if should_cancel and should_cancel():
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                raise asyncio.CancelledError()
            line = line.strip()
            if line.startswith("out_time_ms="):
                try:
                    ms = int(line.split("=", 1)[1] or 0)
                except ValueError:
                    continue
                if on_progress:
                    on_progress(min(max((ms / 1_000_000) / duration, 0.0), 1.0))
            elif line == "progress=end" and on_progress:
                on_progress(1.0)
        _, stderr = proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg render failed: {(stderr or '')[-500:]}")
    finally:
        if proc.poll() is None:
            proc.kill()
    return output_path
