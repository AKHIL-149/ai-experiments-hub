"""
Queue Manager for Content Moderation.

Manages job creation, status tracking, and queue routing for classification tasks.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from celery.result import AsyncResult

from .database import DatabaseManager, ModerationJob, ContentItem, JobStatus
from ..workers.text_worker import classify_text_task
from ..workers.image_worker import classify_image_task
from ..workers.video_worker import classify_video_task

logging.basicConfig(level=logging.INFO)


class QueueManager:
    """Manages asynchronous classification jobs and queue routing."""

    # Queue names by priority
    QUEUE_CRITICAL = 'critical'
    QUEUE_HIGH = 'high'
    QUEUE_DEFAULT = 'default'
    QUEUE_BATCH = 'batch'

    def __init__(self):
        """Initialize queue manager."""
        self.db_manager = DatabaseManager()
        logging.info("QueueManager initialized")

    def create_text_job(
        self,
        content_id: str,
        text_content: str,
        priority: int = 0,
        queue_name: Optional[str] = None
    ) -> ModerationJob:
        """
        Create and enqueue text classification job.

        Args:
            content_id: Content item ID
            text_content: Text to classify
            priority: Priority level (0=normal, 5=high, 10=critical)
            queue_name: Override queue name

        Returns:
            ModerationJob instance
        """
        # Determine queue based on priority
        if queue_name is None:
            queue_name = self._get_queue_by_priority(priority)

        # Submit Celery task
        task = classify_text_task.apply_async(
            args=[content_id, text_content, priority],
            queue=queue_name,
            priority=priority
        )

        # Create moderation job record
        with self.db_manager.get_session() as db:
            job = ModerationJob(
                content_id=content_id,
                status=JobStatus.QUEUED,
                queue_name=queue_name,
                celery_task_id=task.id,
                retry_count=0
            )

            db.add(job)
            db.commit()
            db.refresh(job)

            logging.info(f"Created text job {job.id} for content {content_id} (queue: {queue_name}, task: {task.id})")
            return job

    def create_image_job(
        self,
        content_id: str,
        file_path: str,
        use_vision: bool = True,
        priority: int = 0,
        queue_name: Optional[str] = None
    ) -> ModerationJob:
        """
        Create and enqueue image classification job.

        Args:
            content_id: Content item ID
            file_path: Path to image file
            use_vision: Whether to use vision models
            priority: Priority level
            queue_name: Override queue name

        Returns:
            ModerationJob instance
        """
        # Determine queue based on priority
        if queue_name is None:
            queue_name = self._get_queue_by_priority(priority, default_high=True)

        # Submit Celery task
        task = classify_image_task.apply_async(
            args=[content_id, file_path, use_vision, priority],
            queue=queue_name,
            priority=priority
        )

        # Create moderation job record
        with self.db_manager.get_session() as db:
            job = ModerationJob(
                content_id=content_id,
                status=JobStatus.QUEUED,
                queue_name=queue_name,
                celery_task_id=task.id,
                retry_count=0
            )

            db.add(job)
            db.commit()
            db.refresh(job)

            logging.info(f"Created image job {job.id} for content {content_id} (queue: {queue_name}, task: {task.id})")
            return job

    def create_video_job(
        self,
        content_id: str,
        file_path: str,
        max_frames: int = 10,
        use_vision: bool = False,
        priority: int = 0,
        queue_name: Optional[str] = None
    ) -> ModerationJob:
        """
        Create and enqueue video classification job.

        Args:
            content_id: Content item ID
            file_path: Path to video file
            max_frames: Maximum frames to analyze
            use_vision: Whether to use vision models
            priority: Priority level
            queue_name: Override queue name

        Returns:
            ModerationJob instance
        """
        # Determine queue based on priority
        if queue_name is None:
            queue_name = self._get_queue_by_priority(priority, default_high=True)

        # Submit Celery task
        task = classify_video_task.apply_async(
            args=[content_id, file_path, max_frames, use_vision, priority],
            queue=queue_name,
            priority=priority
        )

        # Create moderation job record
        with self.db_manager.get_session() as db:
            job = ModerationJob(
                content_id=content_id,
                status=JobStatus.QUEUED,
                queue_name=queue_name,
                celery_task_id=task.id,
                retry_count=0
            )

            db.add(job)
            db.commit()
            db.refresh(job)

            logging.info(f"Created video job {job.id} for content {content_id} (queue: {queue_name}, task: {task.id})")
            return job

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """
        Get job status including Celery task state.

        Args:
            job_id: Moderation job ID

        Returns:
            Job status dictionary
        """
        with self.db_manager.get_session() as db:
            job = db.query(ModerationJob).filter(ModerationJob.id == job_id).first()

            if not job:
                return {'error': 'Job not found'}

            # Get Celery task status
            task_result = AsyncResult(job.celery_task_id)

            status_dict = {
                'job_id': job.id,
                'content_id': job.content_id,
                'status': job.status.value,
                'queue_name': job.queue_name,
                'celery_task_id': job.celery_task_id,
                'celery_state': task_result.state,
                'retry_count': job.retry_count,
                'started_at': job.started_at.isoformat() if job.started_at else None,
                'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                'processing_time_seconds': job.processing_time_seconds
            }

            # Add task info if available
            if task_result.state == 'PROGRESS':
                status_dict['progress'] = task_result.info.get('progress', 0)
                status_dict['message'] = task_result.info.get('message', '')
            elif task_result.state == 'SUCCESS':
                status_dict['result'] = task_result.result
            elif task_result.state == 'FAILURE':
                status_dict['error'] = str(task_result.info)

            return status_dict

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        result_data: Optional[Dict] = None
    ):
        """
        Update job status in database.

        Args:
            job_id: Moderation job ID
            status: New status
            result_data: Optional result data
        """
        with self.db_manager.get_session() as db:
            job = db.query(ModerationJob).filter(ModerationJob.id == job_id).first()

            if not job:
                logging.error(f"Job {job_id} not found")
                return

            job.status = status

            if status == JobStatus.PROCESSING and not job.started_at:
                job.started_at = datetime.utcnow()

            elif status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                job.completed_at = datetime.utcnow()

                if job.started_at:
                    job.processing_time_seconds = (
                        job.completed_at - job.started_at
                    ).total_seconds()

                if result_data:
                    job.result_data = result_data

            db.commit()
            logging.info(f"Updated job {job_id} status to {status.value}")

    def get_queue_stats(self) -> Dict[str, Any]:
        """
        Get queue statistics.

        Returns:
            Queue statistics dictionary
        """
        with self.db_manager.get_session() as db:
            stats = {}

            for queue_name in [self.QUEUE_CRITICAL, self.QUEUE_HIGH, self.QUEUE_DEFAULT, self.QUEUE_BATCH]:
                queued = db.query(ModerationJob).filter(
                    ModerationJob.queue_name == queue_name,
                    ModerationJob.status == JobStatus.QUEUED
                ).count()

                processing = db.query(ModerationJob).filter(
                    ModerationJob.queue_name == queue_name,
                    ModerationJob.status == JobStatus.PROCESSING
                ).count()

                stats[queue_name] = {
                    'queued': queued,
                    'processing': processing
                }

            return stats

    def _get_queue_by_priority(
        self,
        priority: int,
        default_high: bool = False
    ) -> str:
        """
        Determine queue name based on priority.

        Args:
            priority: Priority level
            default_high: Use high queue as default (for images/videos)

        Returns:
            Queue name
        """
        if priority >= 10:
            return self.QUEUE_CRITICAL
        elif priority >= 5:
            return self.QUEUE_HIGH
        elif priority < 0:
            return self.QUEUE_BATCH
        else:
            return self.QUEUE_HIGH if default_high else self.QUEUE_DEFAULT


# Global queue manager instance
_queue_manager_instance = None


def get_queue_manager() -> QueueManager:
    """
    Get global QueueManager instance.

    Returns:
        QueueManager singleton
    """
    global _queue_manager_instance
    if _queue_manager_instance is None:
        _queue_manager_instance = QueueManager()
    return _queue_manager_instance
