import math


def round_even(n: int) -> int:
    n = int(n)
    return n if n % 2 == 0 else n - 1


def aspect_to_wh(aspect: str) -> tuple[int, int]:
    parts = aspect.split(":")
    return int(parts[0]), int(parts[1])


def crop_window(src_w: int, src_h: int, aspect_w: int, aspect_h: int) -> dict:
    target_ratio = aspect_w / aspect_h
    source_ratio = src_w / src_h
    if target_ratio < source_ratio:
        crop_h = src_h
        crop_w = round_even(src_h * target_ratio)
    else:
        crop_w = src_w
        crop_h = round_even(src_w / target_ratio)
    return {"crop_w": crop_w, "crop_h": crop_h}


def clamp_center(cx: float, cy: float, crop_w: int, crop_h: int, src_w: int, src_h: int) -> tuple[float, float]:
    half_w_norm = (crop_w / src_w) / 2
    half_h_norm = (crop_h / src_h) / 2
    cx = max(half_w_norm, min(cx, 1 - half_w_norm))
    cy = max(half_h_norm, min(cy, 1 - half_h_norm))
    return cx, cy


def centers_to_keyframes(centers: list[dict], src_w: int, src_h: int, aspect: str) -> list[dict]:
    aw, ah = aspect_to_wh(aspect)
    w = crop_window(src_w, src_h, aw, ah)
    result = []
    for c in centers:
        cx, cy = clamp_center(c["cx"], c.get("cy", 0.5), w["crop_w"], w["crop_h"], src_w, src_h)
        result.append({
            "time": c["time"],
            "center_x": round(cx, 4),
            "center_y": round(cy, 4),
        })
    return result


def build_crop_expr(keyframes: list[dict], src_w: int, src_h: int, aspect_w: int, aspect_h: int) -> str:
    """Build ffmpeg crop x/y expression from keyframes."""
    w = crop_window(src_w, src_h, aspect_w, aspect_h)
    crop_w = w["crop_w"]
    crop_h = w["crop_h"]

    def _x_for_kf(kf):
        cx, _ = clamp_center(kf["center_x"], kf["center_y"], crop_w, crop_h, src_w, src_h)
        return round(cx * src_w - crop_w / 2, 2)

    if len(keyframes) == 1:
        x_val = _x_for_kf(keyframes[0])
        return f"crop={crop_w}:{crop_h}:{x_val}:0"

    parts = []
    for i, kf in enumerate(keyframes):
        t = kf["time"]
        x = _x_for_kf(kf)
        if i == 0:
            parts.append(f"(between(t,{t},{t})*{x})")
        else:
            prev_t = keyframes[i - 1]["time"]
            prev_x = _x_for_kf(keyframes[i - 1])
            expr = f"(between(t,{prev_t},{t})*(1-(t-{prev_t})/{max(t-prev_t,0.001)})*{prev_x}+(t-{prev_t})/{max(t-prev_t,0.001)}*{x})"
            parts.append(expr)

    x_expr = "+".join(parts)
    return f"crop={crop_w}:{crop_h}:x='{x_expr}':y=0"


def keypoints_for_clip(keyframes: list[dict], src_w: int, src_h: int, aspect: str) -> list[dict]:
    aw, ah = aspect_to_wh(aspect)
    return centers_to_keyframes(keyframes, src_w, src_h, aspect)
