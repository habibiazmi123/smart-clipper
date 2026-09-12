from fastapi import APIRouter
from starlette.responses import StreamingResponse
from app.jobs import get_job, cancel_job, job_events

router = APIRouter()


@router.get("/jobs/{job_id}")
def get_job_status(job_id: str):
    j = get_job(job_id)
    if not j:
        return {"error": "not found"}
    return j


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: str):
    ok = cancel_job(job_id)
    return {"cancelled": ok}


@router.get("/jobs/{job_id}/events")
async def stream_events(job_id: str):
    stream = await job_events(job_id)
    if stream:
        return StreamingResponse(stream(), media_type="text/event-stream")
    return {"error": "not found"}
