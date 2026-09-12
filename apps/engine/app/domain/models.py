from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Project:
    id: str
    name: str
    source_url: str = ""
    status: str = "importing"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class Media:
    id: str
    project_id: str
    source_url: str = ""
    path: str = ""
    title: str = ""
    channel: str = ""
    duration: float = 0.0
    width: int = 0
    height: int = 0
    fps: float = 0.0
    has_audio: bool = True


@dataclass
class Transcript:
    id: str
    project_id: str
    language: str = ""
    path: str = ""


@dataclass
class TranscriptSegment:
    id: int
    transcript_id: str
    idx: int
    start: float
    end: float
    text: str = ""
    confidence: float = 0.0
    speaker: Optional[str] = None
    words_json: str = "[]"


@dataclass
class HookCandidate:
    id: str
    project_id: str
    start: float
    end: float
    score: float
    scores_json: str = "{}"
    reasons_json: str = "[]"
    weaknesses_json: str = "[]"


@dataclass
class Clip:
    id: str
    project_id: str
    hook_candidate_id: str = ""
    source_start: float = 0.0
    source_end: float = 0.0
    aspect_ratio: str = "9:16"
    status: str = "draft"
    crop_manually_modified: bool = False
    title: str = ""
    caption_short: str = ""
    caption_long: str = ""
    cta: str = ""
    hashtags_json: str = "[]"


@dataclass
class FaceDetection:
    id: int
    project_id: str
    timestamp: float
    x: float
    y: float
    w: float
    h: float
    confidence: float


@dataclass
class FaceTrack:
    id: int
    project_id: str
    start: float
    end: float
    centers_json: str = "[]"


@dataclass
class CropKeyframe:
    id: int
    clip_id: str
    time: float
    center_x: float
    center_y: float
    source: str = "ai"


@dataclass
class Caption:
    id: int
    clip_id: str
    idx: int
    start: float
    end: float
    text: str = ""
    words_json: str = "[]"
    style_json: str = "{}"


@dataclass
class RenderJob:
    id: str
    clip_id: str
    kind: str = "export"
    status: str = "queued"
    progress: float = 0.0
    stage: str = ""
    error: str = ""
    output_path: str = ""
