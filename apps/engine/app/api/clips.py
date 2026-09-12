import sqlite3
import uuid
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.config import settings
from app.db import get_clip, update_clip, get_crop_keyframes, delete_manual_crop_keyframes

router = APIRouter()


class UpdateClipReq(BaseModel):
    title: str | None = None
    caption_short: str | None = None
    caption_long: str | None = None
    source_start: float | None = None
    source_end: float | None = None


class UpdateKeyframesReq(BaseModel):
    keyframes: list[dict]


def _get_conn():
    return sqlite3.connect(str(settings.DATA_ROOT / "smartclipper.db"))


@router.get("/clips/{clip_id}")
def get_clip_detail(clip_id: str):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    kfs = get_crop_keyframes(conn, clip_id)
    conn.close()
    return {
        "id": c.id, "project_id": c.project_id,
        "source_start": c.source_start, "source_end": c.source_end,
        "aspect_ratio": c.aspect_ratio,
        "crop_manually_modified": c.crop_manually_modified,
        "title": c.title,
        "caption_short": c.caption_short, "caption_long": c.caption_long,
        "cta": c.cta, "keyframes": kfs,
    }


@router.patch("/clips/{clip_id}")
def update_clip_info(clip_id: str, req: UpdateClipReq):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if updates:
        update_clip(conn, clip_id, **updates)
    conn.close()
    return {"status": "updated"}


@router.post("/clips/{clip_id}/keyframes")
def update_keyframes(clip_id: str, req: UpdateKeyframesReq):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    delete_manual_crop_keyframes(conn, clip_id)
    from app.db import insert_crop_keyframes
    insert_crop_keyframes(conn, clip_id, req.keyframes, source="manual")
    update_clip(conn, clip_id, crop_manually_modified=True)
    conn.close()
    return {"status": "updated", "keyframes": len(req.keyframes)}


@router.post("/clips/{clip_id}/reset-crop")
def reset_crop_to_ai(clip_id: str):
    conn = _get_conn()
    c = get_clip(conn, clip_id)
    if not c:
        conn.close()
        raise HTTPException(404)
    delete_manual_crop_keyframes(conn, clip_id)
    update_clip(conn, clip_id, crop_manually_modified=False)
    conn.close()
    return {"status": "reset_to_ai"}
