"""
Keeps the moderation_jobs table in step with what the workers really do.

QueueManager.update_job_status() existed but nothing called it, so every job stayed 'queued' for
ever: the job API, the analytics ("0 completed, 0% success") and the queue statistics (13 queued
while Redis was empty) all described a system that never did anything.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from ..core.database import (
    ContentItem, ContentStatus, DatabaseManager, JobStatus, ModerationJob
)

TERMINAL = (JobStatus.COMPLETED, JobStatus.FAILED)


def _json_safe(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if data is None:
        return None
    return {k: v for k, v in data.items() if isinstance(v, (str, int, float, bool, type(None)))}


def mark_job(
    celery_task_id: str,
    status: JobStatus,
    result_data: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    retry_count: Optional[int] = None,
    db_manager: Optional[DatabaseManager] = None,
) -> bool:
    """Move the job of a Celery task to `status`. False when there is no such job (yet)."""
    try:
        with (db_manager or DatabaseManager()).get_session() as db:
            job = db.query(ModerationJob).filter(ModerationJob.celery_task_id == celery_task_id).first()
            if not job:
                return False
            if job.status in TERMINAL and status not in TERMINAL:
                return True  # a late "started" must not undo "completed"

            now = datetime.utcnow()
            job.status = status
            if status == JobStatus.PROCESSING and not job.started_at:
                job.started_at = now
            if status in TERMINAL:
                job.completed_at = now
                if job.started_at:
                    job.processing_time_seconds = (now - job.started_at).total_seconds()
            if result_data is not None:
                job.result_data = _json_safe(result_data)
            if error is not None:
                job.last_error = error[:2000]
            if retry_count is not None:
                job.retry_count = retry_count
            db.commit()
            return True
    except Exception as e:  # tracking must never fail the classification itself
        logging.error(f"Could not update the job of task {celery_task_id}: {e}")
        return False


def flag_for_review(content_id: str, db_manager: Optional[DatabaseManager] = None) -> None:
    """
    A job that failed for good leaves its content PROCESSING for ever. Send it to the moderators.
    Content a person has already decided on is left alone.
    """
    try:
        with (db_manager or DatabaseManager()).get_session() as db:
            content = db.query(ContentItem).filter(ContentItem.id == content_id).first()
            if content and content.status in (ContentStatus.PENDING, ContentStatus.PROCESSING):
                content.status = ContentStatus.FLAGGED
                db.commit()
    except Exception as e:
        logging.error(f"Could not flag content {content_id} after a failed job: {e}")


def reconcile_jobs(db_manager: Optional[DatabaseManager] = None) -> int:
    """
    Close jobs whose content has already been moderated but which are still marked queued or
    processing (all the jobs created before workers reported their progress). Idempotent.
    """
    closed = 0
    with (db_manager or DatabaseManager()).get_session() as db:
        open_jobs = db.query(ModerationJob).filter(
            ModerationJob.status.in_([JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.RETRYING])
        ).all()
        for job in open_jobs:
            content = db.query(ContentItem).filter(ContentItem.id == job.content_id).first()
            if content is None:
                job.status = JobStatus.FAILED
                job.last_error = 'Content was deleted'
            elif content.moderated_at is not None and content.status in (
                ContentStatus.APPROVED, ContentStatus.REJECTED, ContentStatus.FLAGGED
            ):
                job.status = JobStatus.COMPLETED
                job.completed_at = content.moderated_at
            else:
                continue
            closed += 1
        if closed:
            db.commit()
    return closed
