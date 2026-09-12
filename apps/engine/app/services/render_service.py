import subprocess
import json
from pathlib import Path
from app.domain.crop import build_crop_expr, crop_window, aspect_to_wh


def build_render_plan(input_path: str, start: float, end: float,
                      keyframes: list[dict], src_w: int, src_h: int,
                      aspect: str = "9:16",
                      ass_path: str = None) -> dict:
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
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "video_codec": "libx264",
            "audio_codec": "aac",
            "preset": "fast",
            "crf": 23,
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
