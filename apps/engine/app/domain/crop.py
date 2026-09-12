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
            **({"speaker": c["speaker"]} if c.get("speaker") else {}),
        })
    return result


def build_crop_expr(keyframes: list[dict], src_w: int, src_h: int, aspect_w: int, aspect_h: int) -> str:
    """Build ffmpeg crop x/y expression from keyframes.

    Window half-open [Ti,Ti+1) + head/tail hold, sehingga nilainya
    PERSIS sama dengan interpolateKeyframes() di preview untuk semua t:
    sebelumnya suku interpolasi tidak ter-gate between() (operator `+`
    di luar kurung) -> x meledak lalu di-clamp ffmpeg ke area yang salah.
    """
    w = crop_window(src_w, src_h, aspect_w, aspect_h)
    crop_w = w["crop_w"]
    crop_h = w["crop_h"]

    def _x_for_kf(kf):
        cx, _ = clamp_center(kf["center_x"], kf["center_y"], crop_w, crop_h, src_w, src_h)
        return round(cx * src_w - crop_w / 2, 2)

    if not keyframes:
        return f"crop={crop_w}:{crop_h}:{(src_w - crop_w) / 2}:0"

    if len(keyframes) == 1:
        x_val = _x_for_kf(keyframes[0])
        return f"crop={crop_w}:{crop_h}:{x_val}:0"

    sk = sorted(keyframes, key=lambda k: k["time"])
    terms = [f"(lt(t,{sk[0]['time']})*{_x_for_kf(sk[0])})"]
    for i in range(len(sk) - 1):
        p, c = sk[i], sk[i + 1]
        xp = _x_for_kf(p)
        if _is_switch(p, c):
            # ganti orang = CUT: tahan posisi lama sampai batas, lalu loncat.
            # Glide hanya untuk mengikuti gerakan orang yang sama.
            terms.append(f"(gte(t,{p['time']})*lt(t,{c['time']})*{xp})")
            continue
        span = max(c["time"] - p["time"], 0.001)
        xc = _x_for_kf(c)
        terms.append(
            f"(gte(t,{p['time']})*lt(t,{c['time']})*"
            f"(({c['time']}-t)/{span}*{xp}+(t-{p['time']})/{span}*{xc}))"
        )
    terms.append(f"(gte(t,{sk[-1]['time']})*{_x_for_kf(sk[-1])})")
    return f"crop={crop_w}:{crop_h}:x='{'+'.join(terms)}':y=0"


def _is_switch(a: dict, b: dict) -> bool:
    """True jika dua keyframe berurutan beda pembicara (keduanya berlabel).

    Keyframe manual (tanpa label) = wildcard, tetap glide halus.
    """
    sa, sb = a.get("speaker"), b.get("speaker")
    return bool(sa and sb and sa != sb)


def keypoints_for_clip(keyframes: list[dict], src_w: int, src_h: int, aspect: str) -> list[dict]:
    aw, ah = aspect_to_wh(aspect)
    return centers_to_keyframes(keyframes, src_w, src_h, aspect)
