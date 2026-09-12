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


# ponytail: warna ASS &HAABBGGRR; karaoke \k mengisi Primary saat dinyanyikan
VIRAL_PRESETS = {
    "hormozi": {"font_name": "Arial", "font_size": 64, "bold": True,
                "primary": "&H0000FFFF", "secondary": "&H00FFFFFF",
                "outline": "&H00000000", "outline_w": 3},
    "beast": {"font_name": "Arial", "font_size": 72, "bold": True,
              "primary": "&H00FFFFFF", "secondary": "&H0000FFFF",
              "outline": "&H00000000", "outline_w": 3},
    "minimal": {"font_name": "Arial", "font_size": 52, "bold": False,
                "primary": "&H00FFFFFF", "secondary": "&H99FFFFFF",
                "outline": "&H00000000", "outline_w": 2},
}


def generate_karaoke_ass(words: list[dict], width: int = 1920, height: int = 1080,
                         style: dict = None, max_words: int = 8,
                         max_dur: float = 3.0) -> str:
    """Word-by-word highlighted ASS (viral style). words: [{w,start,end}]."""
    style = {"alignment": 2, "margin_bottom": 140, **VIRAL_PRESETS["hormozi"], **(style or {})}
    align = int(style.get("alignment", 2))
    header = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 0
PlayResX: {width}
PlayResY: {height}
ScalerBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style['font_name']},{style['font_size']},{style['primary']},{style['secondary']},{style['outline']},&H80000000,{-1 if style.get('bold', True) else 0},0,0,0,100,100,0,0,1,{style['outline_w']},1,{align},20,20,{style['margin_bottom']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    group: list[dict] = []

    def flush():
        if not group:
            return
        parts = []
        for w in group:
            cs = max(1, int(round((w["end"] - w["start"]) * 100)))
            safe = w["w"].replace("{", "(").replace("}", ")")
            parts.append(f"{{\\k{cs}}}{safe} ")
        text = "".join(parts).rstrip().replace("\n", "")
        events.append(f"Dialogue: 0,{_fmt_time(group[0]['start'])},{_fmt_time(group[-1]['end'])},Default,,0,0,0,,{text}")
        group.clear()

    for w in words:
        if group and (len(group) >= max_words or w["start"] - group[0]["start"] > max_dur):
            flush()
        group.append(w)
    flush()
    return header + "\n".join(events) + "\n"
