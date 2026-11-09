"""
The job queue as the person sees it: what is waiting, what is running, and a way to cancel or retry.

Every account sees and controls its own jobs only (404 for another account's, like a video); administrators
see all of them.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.core import database
from src.core.auth import current_caller
from src.models.job import ACTIVE_STATUSES, Job, JobKind, JobStatus
from src.models.video import Video
from src.services import job_queue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobResponse(BaseModel):
    job_id: str
    kind: str
    status: str
    video_id: Optional[str] = None
    video_title: Optional[str] = None
    queue_position: Optional[int] = None  # while queued: 1 = starts next
    attempts: int
    max_attempts: int
    error: Optional[str] = None
    cancel_requested: bool = False
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class QueueSummary(BaseModel):
    queued: int          # waiting, your jobs (everyone's for an administrator)
    running: int
    analysis_workers: int
    download_workers: int


class JobListResponse(BaseModel):
    jobs: List[JobResponse]
    total: int
    queue: QueueSummary


def _visible(query):
    caller = current_caller()
    if caller is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    if caller.is_admin:
        return query
    return query.filter(Job.user_id == caller.user_id)


def _to_response(db, job: Job, positions: dict) -> JobResponse:
    video = db.query(Video.external_id, Video.title).filter(Video.id == job.video_id).first()
    return JobResponse(
        job_id=job.id, kind=job.kind, status=job.status,
        video_id=video[0] if video else None, video_title=video[1] if video else None,
        queue_position=positions.get(job.id) if job.status == JobStatus.QUEUED.value else None,
        attempts=job.attempts, max_attempts=job.max_attempts, error=job.error,
        cancel_requested=bool(job.cancel_requested),
        created_at=job.created_at, started_at=job.started_at, finished_at=job.finished_at,
    )


def _get(db, job_id: str) -> Job:
    job = _visible(db.query(Job).filter(Job.id == job_id)).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: Optional[str] = Query(None, description="queued, running, completed, failed or cancelled"),
    kind: Optional[str] = Query(None, description="download or process"),
    limit: int = Query(50, ge=1, le=200),
):
    """Your jobs, active ones first, newest first"""
    if status is not None and status not in {s.value for s in JobStatus}:
        raise HTTPException(status_code=400, detail=f"status must be one of {[s.value for s in JobStatus]}")
    if kind is not None and kind not in {k.value for k in JobKind}:
        raise HTTPException(status_code=400, detail=f"kind must be one of {[k.value for k in JobKind]}")

    from src.core.config import settings
    with database.get_db() as db:
        query = _visible(db.query(Job))
        if status:
            query = query.filter(Job.status == status)
        if kind:
            query = query.filter(Job.kind == kind)
        total = query.count()
        rows = query.order_by(Job.created_at.desc()).limit(limit).all()
        rows.sort(key=lambda j: 0 if j.status in ACTIVE_STATUSES else 1)  # stable: still newest first inside each group

        positions = job_queue.queue_positions(db)
        counts = _visible(db.query(Job)).filter(Job.status.in_(ACTIVE_STATUSES))
        queued = counts.filter(Job.status == JobStatus.QUEUED.value).count()
        running = counts.filter(Job.status == JobStatus.RUNNING.value).count()
        return JobListResponse(
            jobs=[_to_response(db, j, positions) for j in rows],
            total=total,
            queue=QueueSummary(
                queued=queued, running=running,
                analysis_workers=max(1, settings.max_concurrent_videos),
                download_workers=max(1, settings.max_concurrent_downloads),
            ),
        )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: str):
    with database.get_db() as db:
        job = _get(db, job_id)
        return _to_response(db, job, job_queue.queue_positions(db))


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: str):
    """
    Cancel a job. One that is still waiting is cancelled at once; a running one stops at its next checkpoint
    (between pipeline stages and after each scene; a transcription already under way finishes first).
    """
    with database.get_db() as db:
        job = _get(db, job_id)
        if job.status not in ACTIVE_STATUSES:
            raise HTTPException(status_code=409, detail=f"The job is already {job.status}")
        job_queue.request_cancel(db, job)
        db.flush()
        return _to_response(db, job, job_queue.queue_positions(db))


@router.post("/{job_id}/retry", response_model=JobResponse)
async def retry_job(job_id: str):
    """Queue a failed or cancelled job again"""
    with database.get_db() as db:
        job = _get(db, job_id)
        try:
            job_queue.retry(db, job)
        except job_queue.QueueFull as e:
            raise HTTPException(status_code=429, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e))
        db.flush()
        response = _to_response(db, job, job_queue.queue_positions(db))
    job_queue.notify()
    return response
