import json


def split_words_to_lines(words: list[dict], max_chars: int = 30,
                         max_lines: int = 2) -> list[dict]:
    if not words:
        return []
    lines = []
    current_text = []
    current_start = None
    current_end = None
    for w in words:
        word_text = w["word"].strip()
        candidate = " ".join(current_text + [word_text])
        if current_start is None:
            current_start = w["start"]
        if len(candidate) > max_chars and current_text:
            lines.append({
                "text": " ".join(current_text),
                "start": current_start,
                "end": current_end or current_start,
                "words": list(current_text),
            })
            current_text = [word_text]
            current_start = w["start"]
        else:
            current_text.append(word_text)
        current_end = w["end"]
        if len(lines) >= max_lines:
            break
    if current_text and len(lines) < max_lines:
        lines.append({
            "text": " ".join(current_text),
            "start": current_start or 0.0,
            "end": current_end or 0.0,
            "words": list(current_text),
        })
    return lines


def generate_ass(lines: list[dict], width: int = 1080, height: int = 1920,
                 style: dict = None) -> str:
    style = style or {}
    font_size = style.get("font_size", 48)
    font_name = style.get("font_name", "Arial")
    margin_bottom = style.get("margin_bottom", 120)

    header = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {width}
PlayResY: {height}
ScalerBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,1,0,0,0,100,100,0,0,1,2,1,2,20,20,{margin_bottom},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for l in lines:
        start = _fmt_time(l["start"])
        end = _fmt_time(l["end"])
        text = l["text"].replace("\n", "\\N")
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

    return header + "\n".join(events) + "\n"


def _fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"
