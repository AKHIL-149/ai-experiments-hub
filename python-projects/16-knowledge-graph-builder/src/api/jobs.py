"""Your background jobs: see them, cancel them"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_owner
from src.api.documents import job_to_dict
from src.core.database import get_db
from src.models.graph import Document
from src.models.job import ACTIVE, Job, JobStatus
from src.services import job_queue

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _mine(db: Session, job_id: str, owner: int | None) -> Job:
    job = db.get(Job, job_id)
    if job is None or job.owner_id != owner:   # someone else's job answers exactly like one that does not exist
        raise HTTPException(404, "Job not found")
    return job


def _out(db: Session, job: Job, positions: dict) -> dict:
    doc = db.get(Document, job.document_id)
    return {**job_to_dict(job, positions), "document_id": job.document_id, "document_title": doc.title if doc else None, "kind": job.kind}


@router.get("")
def list_jobs(status: str | None = None, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    q = select(Job).where(Job.owner_id == owner).order_by(Job.created_at.desc()).limit(200)
    if status == "active":
        q = q.where(Job.status.in_(ACTIVE))
    elif status:
        if status not in {s.value for s in JobStatus}:
            raise HTTPException(422, f"status must be active or one of: {', '.join(s.value for s in JobStatus)}")
        q = q.where(Job.status == status)
    positions = job_queue.queue_positions(db)
    return {"jobs": [_out(db, j, positions) for j in db.execute(q).scalars()]}


@router.get("/{job_id}")
def get_job(job_id: str, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    return _out(db, _mine(db, job_id, owner), job_queue.queue_positions(db))


@router.post("/{job_id}/cancel")
def cancel_job(job_id: str, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    """A waiting job is cancelled at once. A running one stops at its next checkpoint (before the next passage) and leaves nothing behind."""
    job = _mine(db, job_id, owner)
    if job.status not in ACTIVE:
        raise HTTPException(409, f"The job is already {job.status}")
    job_queue.request_cancel(db, job)
    db.commit()
    return _out(db, job, job_queue.queue_positions(db))
