"""
Service for managing scheduled analysis and automated scanning.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any
from pathlib import Path
from sqlalchemy.orm import Session
from croniter import croniter

from src.core.database import (
    AnalysisSchedule,
    ScheduledRun,
    Repository,
    User
)


class ScheduleService:
    """Service for managing analysis schedules and runs."""

    def __init__(self, session: Session):
        """
        Initialize schedule service.

        Args:
            session: Database session
        """
        self.session = session

    def create_schedule(
        self,
        repository_id: str,
        user_id: str,
        name: str,
        schedule_type: str,
        cron_expression: Optional[str] = None,
        interval_minutes: Optional[int] = None,
        description: Optional[str] = None,
        analyze_all_files: bool = True,
        file_patterns: Optional[List[str]] = None,
        enabled_rules: Optional[List[str]] = None,
        severity_threshold: str = 'info',
        notify_on_completion: bool = False,
        notify_on_issues: bool = True,
        notification_emails: Optional[List[str]] = None,
        slack_webhook_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new analysis schedule.

        Args:
            repository_id: Repository to analyze
            user_id: User creating the schedule
            name: Schedule name
            schedule_type: Type (cron, interval, daily, weekly)
            cron_expression: Cron expression for cron type
            interval_minutes: Minutes for interval type
            description: Optional description
            analyze_all_files: Whether to analyze all files
            file_patterns: Glob patterns for files to analyze
            enabled_rules: List of rule IDs to use
            severity_threshold: Minimum severity to report
            notify_on_completion: Send notification when complete
            notify_on_issues: Send notification when issues found
            notification_emails: Email addresses for notifications
            slack_webhook_url: Slack webhook URL for notifications

        Returns:
            Created schedule data

        Raises:
            ValueError: If validation fails
        """
        # Validate repository exists and user has access
        repository = self.session.query(Repository).filter_by(id=repository_id).first()
        if not repository:
            raise ValueError(f"Repository not found: {repository_id}")

        if repository.user_id != user_id:
            raise ValueError("You don't have permission to schedule analysis for this repository")

        # Validate schedule type and configuration
        if schedule_type == 'cron':
            if not cron_expression:
                raise ValueError("Cron expression required for cron schedule type")
            # Validate cron expression
            try:
                croniter(cron_expression)
            except Exception as e:
                raise ValueError(f"Invalid cron expression: {e}")
        elif schedule_type == 'interval':
            if not interval_minutes or interval_minutes < 1:
                raise ValueError("Interval minutes must be >= 1 for interval schedule type")
        elif schedule_type == 'daily':
            # Daily at midnight
            cron_expression = "0 0 * * *"
        elif schedule_type == 'weekly':
            # Weekly on Sunday at midnight
            cron_expression = "0 0 * * 0"
        else:
            raise ValueError(f"Invalid schedule type: {schedule_type}. Must be cron, interval, daily, or weekly")

        # Calculate next run time
        next_run_at = self._calculate_next_run(schedule_type, cron_expression, interval_minutes)

        # Create schedule
        schedule = AnalysisSchedule(
            repository_id=repository_id,
            name=name,
            description=description,
            schedule_type=schedule_type,
            cron_expression=cron_expression,
            interval_minutes=interval_minutes,
            analyze_all_files=analyze_all_files,
            file_patterns=json.dumps(file_patterns) if file_patterns else None,
            enabled_rules=json.dumps(enabled_rules) if enabled_rules else None,
            severity_threshold=severity_threshold,
            notify_on_completion=notify_on_completion,
            notify_on_issues=notify_on_issues,
            notification_emails=json.dumps(notification_emails) if notification_emails else None,
            slack_webhook_url=slack_webhook_url,
            enabled=True,
            next_run_at=next_run_at,
            created_by_id=user_id
        )

        self.session.add(schedule)
        self.session.commit()
        self.session.refresh(schedule)

        return self._enrich_schedule(schedule)

    def get_schedule(self, schedule_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get schedule by ID.

        Args:
            schedule_id: Schedule ID
            user_id: Optional user ID for permission check

        Returns:
            Schedule data or None
        """
        query = self.session.query(AnalysisSchedule).filter_by(id=schedule_id)

        if user_id:
            # Join with repository to check ownership
            query = query.join(Repository).filter(Repository.user_id == user_id)

        schedule = query.first()
        if not schedule:
            return None

        return self._enrich_schedule(schedule)

    def list_schedules(
        self,
        user_id: Optional[str] = None,
        repository_id: Optional[str] = None,
        enabled_only: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List schedules with optional filters.

        Args:
            user_id: Filter by user
            repository_id: Filter by repository
            enabled_only: Only return enabled schedules

        Returns:
            List of schedules
        """
        query = self.session.query(AnalysisSchedule)

        if user_id:
            query = query.join(Repository).filter(Repository.user_id == user_id)

        if repository_id:
            query = query.filter(AnalysisSchedule.repository_id == repository_id)

        if enabled_only:
            query = query.filter(AnalysisSchedule.enabled == True)

        schedules = query.order_by(AnalysisSchedule.created_at.desc()).all()
        return [self._enrich_schedule(s) for s in schedules]

    def update_schedule(
        self,
        schedule_id: str,
        user_id: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Update schedule settings.

        Args:
            schedule_id: Schedule ID
            user_id: User making the update
            **kwargs: Fields to update

        Returns:
            Updated schedule data

        Raises:
            ValueError: If schedule not found or user lacks permission
        """
        schedule = self.session.query(AnalysisSchedule).filter_by(id=schedule_id).first()
        if not schedule:
            raise ValueError(f"Schedule not found: {schedule_id}")

        # Check permission
        repository = self.session.query(Repository).filter_by(id=schedule.repository_id).first()
        if repository.user_id != user_id:
            raise ValueError("You don't have permission to update this schedule")

        # Update allowed fields
        allowed_fields = [
            'name', 'description', 'schedule_type', 'cron_expression', 'interval_minutes',
            'analyze_all_files', 'file_patterns', 'enabled_rules', 'severity_threshold',
            'notify_on_completion', 'notify_on_issues', 'notification_emails',
            'slack_webhook_url', 'enabled'
        ]

        schedule_changed = False
        for field, value in kwargs.items():
            if field in allowed_fields and hasattr(schedule, field):
                # Convert lists to JSON for storage
                if field in ['file_patterns', 'enabled_rules', 'notification_emails']:
                    if value is not None:
                        value = json.dumps(value)

                setattr(schedule, field, value)

                # If schedule type or timing changed, recalculate next run
                if field in ['schedule_type', 'cron_expression', 'interval_minutes']:
                    schedule_changed = True

        if schedule_changed:
            # Recalculate next run time
            schedule.next_run_at = self._calculate_next_run(
                schedule.schedule_type,
                schedule.cron_expression,
                schedule.interval_minutes,
                base_time=schedule.last_run_at
            )

        schedule.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        self.session.refresh(schedule)

        return self._enrich_schedule(schedule)

    def delete_schedule(self, schedule_id: str, user_id: str) -> Dict[str, Any]:
        """
        Delete a schedule.

        Args:
            schedule_id: Schedule ID
            user_id: User deleting the schedule

        Returns:
            Success message

        Raises:
            ValueError: If schedule not found or user lacks permission
        """
        schedule = self.session.query(AnalysisSchedule).filter_by(id=schedule_id).first()
        if not schedule:
            raise ValueError(f"Schedule not found: {schedule_id}")

        # Check permission
        repository = self.session.query(Repository).filter_by(id=schedule.repository_id).first()
        if repository.user_id != user_id:
            raise ValueError("You don't have permission to delete this schedule")

        self.session.delete(schedule)
        self.session.commit()

        return {'message': 'Schedule deleted successfully'}

    def toggle_schedule(self, schedule_id: str, user_id: str, enabled: bool) -> Dict[str, Any]:
        """
        Enable or disable a schedule.

        Args:
            schedule_id: Schedule ID
            user_id: User toggling the schedule
            enabled: Enable or disable

        Returns:
            Updated schedule data
        """
        return self.update_schedule(schedule_id, user_id, enabled=enabled)

    def trigger_schedule(self, schedule_id: str, user_id: str) -> Dict[str, Any]:
        """
        Manually trigger a schedule to run immediately.

        Args:
            schedule_id: Schedule ID
            user_id: User triggering the schedule

        Returns:
            Created run data
        """
        schedule = self.session.query(AnalysisSchedule).filter_by(id=schedule_id).first()
        if not schedule:
            raise ValueError(f"Schedule not found: {schedule_id}")

        # Check permission
        repository = self.session.query(Repository).filter_by(id=schedule.repository_id).first()
        if repository.user_id != user_id:
            raise ValueError("You don't have permission to trigger this schedule")

        # Create a run
        run = ScheduledRun(
            schedule_id=schedule_id,
            status='pending'
        )
        self.session.add(run)
        self.session.commit()
        self.session.refresh(run)

        # Trigger Celery task
        from src.workers.schedule_worker import run_scheduled_analysis
        task = run_scheduled_analysis.delay(run.id)
        run.celery_task_id = task.id
        self.session.commit()

        return run.to_dict()

    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        """
        Get run by ID.

        Args:
            run_id: Run ID

        Returns:
            Run data or None
        """
        run = self.session.query(ScheduledRun).filter_by(id=run_id).first()
        if not run:
            return None

        return self._enrich_run(run)

    def list_runs(
        self,
        schedule_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        List runs with optional filters.

        Args:
            schedule_id: Filter by schedule
            status: Filter by status
            limit: Maximum number of runs to return

        Returns:
            List of runs
        """
        query = self.session.query(ScheduledRun)

        if schedule_id:
            query = query.filter(ScheduledRun.schedule_id == schedule_id)

        if status:
            query = query.filter(ScheduledRun.status == status)

        runs = query.order_by(ScheduledRun.created_at.desc()).limit(limit).all()
        return [self._enrich_run(r) for r in runs]

    def update_run_status(
        self,
        run_id: str,
        status: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Update run status and results.

        Args:
            run_id: Run ID
            status: New status
            **kwargs: Additional fields to update

        Returns:
            Updated run data
        """
        run = self.session.query(ScheduledRun).filter_by(id=run_id).first()
        if not run:
            raise ValueError(f"Run not found: {run_id}")

        run.status = status

        # Update additional fields
        for field, value in kwargs.items():
            if hasattr(run, field):
                setattr(run, field, value)

        # Calculate duration if completed
        if status in ['completed', 'failed', 'cancelled'] and run.started_at:
            run.completed_at = datetime.now(timezone.utc)
            run.duration_seconds = (run.completed_at - run.started_at).total_seconds()

        # Update schedule's last run time
        if status in ['completed', 'failed']:
            schedule = self.session.query(AnalysisSchedule).filter_by(id=run.schedule_id).first()
            if schedule:
                schedule.last_run_at = datetime.now(timezone.utc)
                schedule.run_count += 1
                schedule.next_run_at = self._calculate_next_run(
                    schedule.schedule_type,
                    schedule.cron_expression,
                    schedule.interval_minutes,
                    base_time=schedule.last_run_at
                )

        self.session.commit()
        self.session.refresh(run)

        return self._enrich_run(run)

    def get_due_schedules(self) -> List[Dict[str, Any]]:
        """
        Get all enabled schedules that are due to run.

        Returns:
            List of due schedules
        """
        now = datetime.now(timezone.utc)
        schedules = self.session.query(AnalysisSchedule).filter(
            AnalysisSchedule.enabled == True,
            AnalysisSchedule.next_run_at <= now
        ).all()

        return [self._enrich_schedule(s) for s in schedules]

    def _calculate_next_run(
        self,
        schedule_type: str,
        cron_expression: Optional[str],
        interval_minutes: Optional[int],
        base_time: Optional[datetime] = None
    ) -> datetime:
        """
        Calculate next run time for a schedule.

        Args:
            schedule_type: Schedule type (cron, interval, daily, weekly)
            cron_expression: Cron expression
            interval_minutes: Interval in minutes
            base_time: Base time (defaults to now)

        Returns:
            Next run datetime
        """
        if base_time is None:
            base_time = datetime.now(timezone.utc)

        if schedule_type in ['cron', 'daily', 'weekly']:
            # Use croniter to calculate next run
            cron = croniter(cron_expression, base_time)
            next_run = cron.get_next(datetime)
            # Ensure timezone-aware
            if next_run.tzinfo is None:
                next_run = next_run.replace(tzinfo=timezone.utc)
            return next_run
        elif schedule_type == 'interval':
            return base_time + timedelta(minutes=interval_minutes)
        else:
            raise ValueError(f"Invalid schedule type: {schedule_type}")

    def _enrich_schedule(self, schedule: AnalysisSchedule) -> Dict[str, Any]:
        """
        Enrich schedule with related data.

        Args:
            schedule: Schedule model

        Returns:
            Enriched schedule dict
        """
        data = schedule.to_dict()

        # Add repository info
        if schedule.repository:
            data['repository'] = {
                'id': schedule.repository.id,
                'name': schedule.repository.name,
                'github_url': schedule.repository.github_url
            }

        # Add creator info
        if schedule.created_by:
            data['created_by'] = {
                'id': schedule.created_by.id,
                'username': schedule.created_by.username
            }

        # Add recent runs count
        recent_runs = self.session.query(ScheduledRun).filter(
            ScheduledRun.schedule_id == schedule.id
        ).count()
        data['total_runs'] = recent_runs

        # Add last run info
        last_run = self.session.query(ScheduledRun).filter(
            ScheduledRun.schedule_id == schedule.id,
            ScheduledRun.status.in_(['completed', 'failed'])
        ).order_by(ScheduledRun.completed_at.desc()).first()

        if last_run:
            data['last_run'] = {
                'id': last_run.id,
                'status': last_run.status,
                'issues_found': last_run.issues_found,
                'completed_at': last_run.completed_at.isoformat() if last_run.completed_at else None
            }

        return data

    def _enrich_run(self, run: ScheduledRun) -> Dict[str, Any]:
        """
        Enrich run with related data.

        Args:
            run: Run model

        Returns:
            Enriched run dict
        """
        data = run.to_dict()

        # Add schedule info
        if run.schedule:
            data['schedule'] = {
                'id': run.schedule.id,
                'name': run.schedule.name,
                'repository_id': run.schedule.repository_id
            }

        return data
