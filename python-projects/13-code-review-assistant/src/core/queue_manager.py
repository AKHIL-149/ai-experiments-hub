"""
Queue management for async task processing with Celery
"""

from typing import Optional, Dict, Any, Tuple
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from celery.result import AsyncResult

from .database import AnalysisJob, JobStatus


class QueueManager:
    """Manage Celery task queue and job tracking"""

    def __init__(self, db_session: Session, celery_app):
        """
        Initialize queue manager

        Args:
            db_session: Database session
            celery_app: Celery application instance
        """
        self.db = db_session
        self.celery = celery_app

    def submit_analysis_job(
        self,
        pr_id: str,
        job_type: str = 'full_analysis'
    ) -> Tuple[bool, Optional[AnalysisJob], Optional[str]]:
        """
        Submit analysis job to queue

        Args:
            pr_id: Pull request ID
            job_type: Type of analysis job

        Returns:
            Tuple of (success, job, error_message)
        """
        try:
            # Create job record
            job = AnalysisJob(
                pull_request_id=pr_id,
                job_type=job_type,
                status=JobStatus.PENDING,
                started_at=datetime.now(timezone.utc)
            )

            self.db.add(job)
            self.db.commit()
            self.db.refresh(job)

            # Submit to Celery (will be implemented in workers)
            # task = self.celery.send_task(
            #     'src.workers.analysis_worker.analyze_pr',
            #     args=[job.id, pr_id]
            # )
            # job.celery_task_id = task.id
            # job.status = JobStatus.RUNNING
            # self.db.commit()

            return True, job, None

        except Exception as e:
            self.db.rollback()
            return False, None, str(e)

    def get_job_status(
        self,
        job_id: str
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Get job status and results

        Args:
            job_id: Analysis job ID

        Returns:
            Tuple of (success, status_info, error_message)
        """
        job = self.db.query(AnalysisJob).filter(
            AnalysisJob.id == job_id
        ).first()

        if not job:
            return False, None, "Job not found"

        status_info = {
            'job_id': job.id,
            'status': job.status.value,
            'job_type': job.job_type,
            'started_at': job.started_at.isoformat() if job.started_at else None,
            'completed_at': job.completed_at.isoformat() if job.completed_at else None,
            'result': job.result_json
        }

        # Check Celery task status if available
        if job.celery_task_id:
            task_result = AsyncResult(job.celery_task_id, app=self.celery)
            status_info['celery_state'] = task_result.state

        return True, status_info, None

    def cancel_job(self, job_id: str) -> Tuple[bool, Optional[str]]:
        """
        Cancel running job

        Args:
            job_id: Analysis job ID

        Returns:
            Tuple of (success, error_message)
        """
        job = self.db.query(AnalysisJob).filter(
            AnalysisJob.id == job_id
        ).first()

        if not job:
            return False, "Job not found"

        if job.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            return False, "Job already completed"

        # Revoke Celery task
        if job.celery_task_id:
            self.celery.control.revoke(job.celery_task_id, terminate=True)

        # Update job status
        job.status = JobStatus.FAILED
        job.completed_at = datetime.now(timezone.utc)
        job.result_json = {'error': 'Job cancelled by user'}
        self.db.commit()

        return True, None

    def cleanup_old_jobs(self, days: int = 30) -> int:
        """
        Remove old completed jobs

        Args:
            days: Remove jobs older than this many days

        Returns:
            Number of jobs deleted
        """
        from datetime import timedelta

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        count = self.db.query(AnalysisJob).filter(
            AnalysisJob.completed_at < cutoff_date,
            AnalysisJob.status.in_([JobStatus.COMPLETED, JobStatus.FAILED])
        ).delete()

        self.db.commit()
        return count

    def get_active_jobs(self) -> list:
        """
        Get all active (pending/running) jobs

        Returns:
            List of active jobs
        """
        return self.db.query(AnalysisJob).filter(
            AnalysisJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING])
        ).order_by(AnalysisJob.started_at.desc()).all()

    def get_job_stats(self) -> Dict[str, int]:
        """
        Get job statistics

        Returns:
            Dictionary with job counts by status
        """
        from sqlalchemy import func

        results = self.db.query(
            AnalysisJob.status,
            func.count(AnalysisJob.id)
        ).group_by(AnalysisJob.status).all()

        stats = {status.value: 0 for status in JobStatus}
        for status, count in results:
            stats[status.value] = count

        return stats

    def queue_pr_analysis(
        self,
        repository_id: int,
        pr_number: int,
        installation_id: Optional[int] = None,
        priority: str = 'normal'
    ) -> AnalysisJob:
        """
        Queue PR analysis job (webhook integration)

        Args:
            repository_id: Repository ID
            pr_number: Pull request number
            installation_id: GitHub installation ID
            priority: Job priority (high/normal/low)

        Returns:
            Created AnalysisJob
        """
        from ..core.database import PullRequest

        # Find or create PR
        pr = self.db.query(PullRequest).filter(
            PullRequest.repository_id == repository_id,
            PullRequest.pr_number == pr_number
        ).first()

        if not pr:
            # Create minimal PR record
            pr = PullRequest(
                repository_id=repository_id,
                pr_number=pr_number,
                title=f"PR #{pr_number}",
                author="unknown",
                status="open",
                source_branch="unknown",
                target_branch="unknown"
            )
            self.db.add(pr)
            self.db.commit()
            self.db.refresh(pr)

        # Create analysis job
        job = AnalysisJob(
            pull_request_id=pr.id,
            job_type='pr_analysis',
            status=JobStatus.PENDING,
            started_at=datetime.utcnow()
        )

        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)

        return job


# Global queue manager instance
_queue_manager: Optional[QueueManager] = None


def get_queue_manager() -> QueueManager:
    """
    Get the global queue manager instance.

    Note: This is a simplified version for webhook integration.
    In production, this should be properly initialized with db session and celery app.

    Returns:
        QueueManager instance
    """
    global _queue_manager

    if _queue_manager is None:
        from .database import DatabaseManager

        # Mock celery app for now (will be implemented later)
        class MockCeleryApp:
            pass

        db_manager = DatabaseManager()
        session = db_manager.get_session()
        _queue_manager = QueueManager(session, MockCeleryApp())

    return _queue_manager
