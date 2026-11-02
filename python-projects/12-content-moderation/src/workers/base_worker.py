"""
Base Worker Class for Content Moderation Tasks.

Provides common functionality for all classification tasks including:
- Retry logic with exponential backoff
- Progress tracking
- Error handling
- State management
"""

import logging
from celery import Task
from typing import Dict, Any

from ..core.database import JobStatus
from .job_tracker import mark_job, flag_for_review

logging.basicConfig(level=logging.INFO)


class BaseClassificationTask(Task):
    """Base class for classification tasks with retry and progress tracking."""

    # Retry configuration
    autoretry_for = (ConnectionError, TimeoutError, Exception)
    retry_kwargs = {'max_retries': 3}
    retry_backoff = True  # Exponential backoff
    retry_backoff_max = 600  # 10 minutes max
    retry_jitter = True  # Add randomness

    def before_start(self, task_id, args, kwargs):
        """A worker picked the task up: the job is now being processed"""
        mark_job(task_id, JobStatus.PROCESSING)

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """
        Handler called when task is retried.

        Args:
            exc: Exception that caused retry
            task_id: Unique task ID
            args: Original task args
            kwargs: Original task kwargs
            einfo: Exception info
        """
        logging.warning(f"Task {task_id} retrying due to {exc.__class__.__name__}: {exc}")
        mark_job(task_id, JobStatus.RETRYING, error=str(exc), retry_count=self.request.retries + 1)

        # Update task state to show retry
        self.update_state(
            task_id=task_id,
            state='RETRY',
            meta={
                'exc_type': exc.__class__.__name__,
                'exc_message': str(exc),
                'retry_count': self.request.retries
            }
        )

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """
        Handler called when task fails after all retries.

        Args:
            exc: Exception that caused failure
            task_id: Unique task ID
            args: Original task args
            kwargs: Original task kwargs
            einfo: Exception info
        """
        logging.error(f"Task {task_id} failed after {self.request.retries} retries: {exc}")
        mark_job(task_id, JobStatus.FAILED, error=str(exc), retry_count=self.request.retries)
        # The content would stay "processing" for ever: hand it to the moderators
        if args:
            flag_for_review(args[0])

        # Update task state
        self.update_state(
            task_id=task_id,
            state='FAILURE',
            meta={
                'exc_type': exc.__class__.__name__,
                'exc_message': str(exc),
                'retry_count': self.request.retries
            }
        )

    def on_success(self, retval, task_id, args, kwargs):
        """
        Handler called when task completes successfully.

        Args:
            retval: Return value
            task_id: Unique task ID
            args: Original task args
            kwargs: Original task kwargs
        """
        logging.info(f"Task {task_id} completed successfully")
        mark_job(task_id, JobStatus.COMPLETED, result_data=retval if isinstance(retval, dict) else None)

    def update_progress(self, task_id: str, progress: int, message: str, **kwargs):
        """
        Update task progress.

        Args:
            task_id: Task ID
            progress: Progress percentage (0-100)
            message: Progress message
            **kwargs: Additional metadata
        """
        self.update_state(
            task_id=task_id,
            state='PROGRESS',
            meta={
                'progress': progress,
                'message': message,
                **kwargs
            }
        )

    def log_classification_start(self, task_id: str, content_type: str, content_id: str):
        """Log classification start."""
        logging.info(f"[{task_id}] Starting {content_type} classification for content {content_id}")

    def log_classification_complete(
        self,
        task_id: str,
        content_id: str,
        category: str,
        confidence: float,
        processing_time_ms: float
    ):
        """Log classification completion."""
        logging.info(
            f"[{task_id}] Classification complete for content {content_id}: "
            f"{category} (confidence: {confidence:.2f}, time: {processing_time_ms:.0f}ms)"
        )

    def log_classification_error(self, task_id: str, content_id: str, error: Exception):
        """Log classification error."""
        logging.error(f"[{task_id}] Classification failed for content {content_id}: {error}")
