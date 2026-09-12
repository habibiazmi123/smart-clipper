import asyncio
import uuid
import time
from enum import Enum
from dataclasses import dataclass, field


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Job:
    id: str
    kind: str
    project_id: str
    status: JobStatus = JobStatus.QUEUED
    progress: float = 0.0
    stage: str = ""
    error: str = ""
    cancelled: bool = False
    _event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    _queue: asyncio.Queue = field(default_factory=asyncio.Queue, repr=False)


_jobs: dict[str, Job] = {}


def enqueue_job(kind: str, project_id: str, fn, *args, job_id: str = None) -> str:
    job_id = job_id or str(uuid.uuid4())[:12]
    job = Job(id=job_id, kind=kind, project_id=project_id)
    _jobs[job_id] = job
    asyncio.get_event_loop().create_task(_run(job, fn, *args))
    return job_id


async def _run(job: Job, fn, *args):
    job.status = JobStatus.PROCESSING
    await _push(job, "started", 0.0)
    try:
        await fn(job, *args)
        if not job.cancelled:
            job.status = JobStatus.COMPLETED
            await _push(job, "done", 1.0)
    except Exception as e:
        job.status = JobStatus.FAILED
        job.error = str(e)
        await _push(job, "failed", job.progress)


async def _push(job: Job, stage: str, progress: float):
    job.stage = stage
    job.progress = progress
    await job._queue.put({"stage": stage, "progress": progress, "status": job.status.value})


def update_progress(job: Job, stage: str, progress: float):
    job.stage = stage
    job.progress = progress
    asyncio.get_event_loop().create_task(_push(job, stage, progress))


def get_job(job_id: str) -> dict | None:
    j = _jobs.get(job_id)
    if not j:
        return None
    return {
        "id": j.id, "kind": j.kind, "project_id": j.project_id,
        "status": j.status.value, "progress": j.progress,
        "stage": j.stage, "error": j.error,
    }


def cancel_job(job_id: str) -> bool:
    j = _jobs.get(job_id)
    if not j:
        return False
    j.cancelled = True
    j.status = JobStatus.CANCELLED
    asyncio.get_event_loop().create_task(_push(j, "cancelled", j.progress))
    return True


async def job_events(job_id: str):
    import json
    j = _jobs.get(job_id)
    if not j:
        return None
    async def stream():
        while True:
            data = await j._queue.get()
            yield f"data: {json.dumps(data)}\n\n"
            if data["status"] in ("completed", "failed", "cancelled"):
                break
    return stream()
