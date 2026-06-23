"""
Celery worker for scheduled analysis tasks.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any
from pathlib import Path

from celery import Task
from sqlalchemy.orm import Session

from celery_app import celery_app
from src.core.database import DatabaseManager, AnalysisSchedule, ScheduledRun, Repository
from src.services.schedule_service import ScheduleService
from src.services.code_analyzer_service import CodeAnalyzerService
from src.workers.notification_worker import send_notification

logger = logging.getLogger(__name__)


class ScheduledAnalysisTask(Task):
    """Custom task class with database session management."""

    def __init__(self):
        self._db = None

    @property
    def db(self):
        if self._db is None:
            self._db = DatabaseManager()
        return self._db


@celery_app.task(base=ScheduledAnalysisTask, bind=True, name='schedule_worker.run_scheduled_analysis')
def run_scheduled_analysis(self, run_id: str) -> Dict[str, Any]:
    """
    Execute a scheduled analysis run.

    Args:
        run_id: ScheduledRun ID

    Returns:
        Analysis results
    """
    logger.info(f"Starting scheduled analysis run: {run_id}")

    with self.db.get_session() as session:
        schedule_service = ScheduleService(session)

        # Get the run
        run = session.query(ScheduledRun).filter_by(id=run_id).first()
        if not run:
            logger.error(f"Run not found: {run_id}")
            return {'error': 'Run not found'}

        # Get the schedule
        schedule = session.query(AnalysisSchedule).filter_by(id=run.schedule_id).first()
        if not schedule:
            logger.error(f"Schedule not found: {run.schedule_id}")
            schedule_service.update_run_status(
                run_id,
                'failed',
                error_message='Schedule not found'
            )
            return {'error': 'Schedule not found'}

        # Get the repository
        repository = session.query(Repository).filter_by(id=schedule.repository_id).first()
        if not repository:
            logger.error(f"Repository not found: {schedule.repository_id}")
            schedule_service.update_run_status(
                run_id,
                'failed',
                error_message='Repository not found'
            )
            return {'error': 'Repository not found'}

        try:
            # Update run status to running
            schedule_service.update_run_status(
                run_id,
                'running',
                started_at=datetime.now(timezone.utc),
                celery_task_id=self.request.id
            )

            # Prepare analysis configuration
            file_patterns = json.loads(schedule.file_patterns) if schedule.file_patterns else None
            enabled_rules = json.loads(schedule.enabled_rules) if schedule.enabled_rules else None

            # Initialize analyzer
            analyzer_service = CodeAnalyzerService(session)

            # Analyze repository
            logger.info(f"Analyzing repository: {repository.name}")

            if schedule.analyze_all_files:
                # Analyze all Python files in repository
                repo_path = Path(repository.clone_path)
                if not repo_path.exists():
                    raise ValueError(f"Repository path not found: {repository.clone_path}")

                # Find Python files
                python_files = list(repo_path.rglob('*.py'))
                logger.info(f"Found {len(python_files)} Python files to analyze")

                all_issues = []
                files_analyzed = 0

                for file_path in python_files:
                    # Check if file matches patterns (if specified)
                    if file_patterns:
                        relative_path = file_path.relative_to(repo_path)
                        if not any(relative_path.match(pattern) for pattern in file_patterns):
                            continue

                    try:
                        # Analyze file
                        with open(file_path, 'r', encoding='utf-8') as f:
                            code = f.read()

                        # Use analyzer service
                        result = analyzer_service.analyze_code(
                            code=code,
                            language='python',
                            file_path=str(file_path.relative_to(repo_path)),
                            enabled_rules=enabled_rules
                        )

                        if result.get('issues'):
                            all_issues.extend(result['issues'])

                        files_analyzed += 1

                    except Exception as e:
                        logger.warning(f"Error analyzing file {file_path}: {e}")
                        continue

            else:
                # Analyze specific files based on patterns
                if not file_patterns:
                    raise ValueError("file_patterns required when analyze_all_files is False")

                repo_path = Path(repository.clone_path)
                all_issues = []
                files_analyzed = 0

                for pattern in file_patterns:
                    for file_path in repo_path.rglob(pattern):
                        if file_path.is_file() and file_path.suffix == '.py':
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    code = f.read()

                                result = analyzer_service.analyze_code(
                                    code=code,
                                    language='python',
                                    file_path=str(file_path.relative_to(repo_path)),
                                    enabled_rules=enabled_rules
                                )

                                if result.get('issues'):
                                    all_issues.extend(result['issues'])

                                files_analyzed += 1

                            except Exception as e:
                                logger.warning(f"Error analyzing file {file_path}: {e}")
                                continue

            # Filter issues by severity threshold
            severity_order = {'info': 0, 'warning': 1, 'error': 2, 'critical': 3}
            threshold_level = severity_order.get(schedule.severity_threshold, 0)

            filtered_issues = [
                issue for issue in all_issues
                if severity_order.get(issue.get('severity', 'info'), 0) >= threshold_level
            ]

            # Count issues by severity
            critical_count = sum(1 for i in filtered_issues if i.get('severity') == 'critical')
            error_count = sum(1 for i in filtered_issues if i.get('severity') == 'error')
            warning_count = sum(1 for i in filtered_issues if i.get('severity') == 'warning')
            info_count = sum(1 for i in filtered_issues if i.get('severity') == 'info')

            # Prepare result summary
            result_summary = {
                'files_analyzed': files_analyzed,
                'total_issues': len(filtered_issues),
                'issues_by_severity': {
                    'critical': critical_count,
                    'error': error_count,
                    'warning': warning_count,
                    'info': info_count
                },
                'issues_by_category': {},
                'top_issues': filtered_issues[:10]  # Top 10 issues
            }

            # Count by category
            for issue in filtered_issues:
                category = issue.get('category', 'unknown')
                result_summary['issues_by_category'][category] = \
                    result_summary['issues_by_category'].get(category, 0) + 1

            # Update run with results
            schedule_service.update_run_status(
                run_id,
                'completed',
                files_analyzed=files_analyzed,
                issues_found=len(filtered_issues),
                critical_issues=critical_count,
                error_issues=error_count,
                warning_issues=warning_count,
                info_issues=info_count,
                result_summary=json.dumps(result_summary)
            )

            logger.info(f"Scheduled analysis completed: {run_id} - {len(filtered_issues)} issues found")

            # Send notifications if configured
            if schedule.notify_on_completion or (schedule.notify_on_issues and len(filtered_issues) > 0):
                send_scheduled_analysis_notification.delay(run_id)

            return {
                'success': True,
                'run_id': run_id,
                'files_analyzed': files_analyzed,
                'issues_found': len(filtered_issues),
                'result_summary': result_summary
            }

        except Exception as e:
            logger.error(f"Error in scheduled analysis: {e}", exc_info=True)

            # Update run status to failed
            schedule_service.update_run_status(
                run_id,
                'failed',
                error_message=str(e)
            )

            return {
                'success': False,
                'error': str(e)
            }


@celery_app.task(base=ScheduledAnalysisTask, bind=True, name='schedule_worker.send_scheduled_analysis_notification')
def send_scheduled_analysis_notification(self, run_id: str) -> Dict[str, Any]:
    """
    Send notification for a completed scheduled analysis.

    Args:
        run_id: ScheduledRun ID

    Returns:
        Notification result
    """
    logger.info(f"Sending notification for run: {run_id}")

    with self.db.get_session() as session:
        schedule_service = ScheduleService(session)

        # Get the run
        run_data = schedule_service.get_run(run_id)
        if not run_data:
            logger.error(f"Run not found: {run_id}")
            return {'error': 'Run not found'}

        # Get the schedule
        schedule_data = schedule_service.get_schedule(run_data['schedule_id'])
        if not schedule_data:
            logger.error(f"Schedule not found: {run_data['schedule_id']}")
            return {'error': 'Schedule not found'}

        # Check if notification should be sent
        if not schedule_data.get('notify_on_completion') and \
           not (schedule_data.get('notify_on_issues') and run_data.get('issues_found', 0) > 0):
            logger.info("Notification not required for this run")
            return {'message': 'Notification not required'}

        # Prepare notification message
        repository_name = schedule_data.get('repository', {}).get('name', 'Unknown')
        status = run_data.get('status', 'completed')
        issues_found = run_data.get('issues_found', 0)
        critical_issues = run_data.get('critical_issues', 0)
        error_issues = run_data.get('error_issues', 0)
        warning_issues = run_data.get('warning_issues', 0)

        if status == 'completed':
            if issues_found > 0:
                subject = f"⚠️ Scheduled Analysis: {issues_found} issues found in {repository_name}"
                message = f"""
Scheduled analysis completed for repository: {repository_name}

**Schedule:** {schedule_data.get('name')}
**Files Analyzed:** {run_data.get('files_analyzed', 0)}
**Total Issues:** {issues_found}

**Issues by Severity:**
- Critical: {critical_issues}
- Error: {error_issues}
- Warning: {warning_issues}
- Info: {run_data.get('info_issues', 0)}

**Duration:** {run_data.get('duration_seconds', 0):.2f} seconds
**Completed:** {run_data.get('completed_at', 'N/A')}
"""
            else:
                subject = f"✅ Scheduled Analysis: No issues found in {repository_name}"
                message = f"""
Scheduled analysis completed successfully for repository: {repository_name}

**Schedule:** {schedule_data.get('name')}
**Files Analyzed:** {run_data.get('files_analyzed', 0)}
**Issues Found:** 0

All files passed analysis without issues!

**Duration:** {run_data.get('duration_seconds', 0):.2f} seconds
**Completed:** {run_data.get('completed_at', 'N/A')}
"""
        else:
            subject = f"❌ Scheduled Analysis Failed: {repository_name}"
            message = f"""
Scheduled analysis failed for repository: {repository_name}

**Schedule:** {schedule_data.get('name')}
**Error:** {run_data.get('error_message', 'Unknown error')}
**Completed:** {run_data.get('completed_at', 'N/A')}
"""

        # Send email notifications
        notification_emails = schedule_data.get('notification_emails', [])
        if notification_emails:
            for email in notification_emails:
                try:
                    send_notification.delay(
                        notification_type='email',
                        recipient=email,
                        subject=subject,
                        message=message
                    )
                except Exception as e:
                    logger.error(f"Error sending email to {email}: {e}")

        # Send Slack notification
        slack_webhook_url = schedule_data.get('slack_webhook_url')
        if slack_webhook_url:
            try:
                send_notification.delay(
                    notification_type='slack',
                    recipient=slack_webhook_url,
                    message=message
                )
            except Exception as e:
                logger.error(f"Error sending Slack notification: {e}")

        # Mark notification as sent
        run = session.query(ScheduledRun).filter_by(id=run_id).first()
        if run:
            run.notification_sent = True
            session.commit()

        logger.info(f"Notifications sent for run: {run_id}")
        return {'success': True, 'message': 'Notifications sent'}


@celery_app.task(base=ScheduledAnalysisTask, bind=True, name='schedule_worker.check_due_schedules')
def check_due_schedules(self) -> Dict[str, Any]:
    """
    Check for due schedules and trigger them.
    This task should be run periodically (e.g., every minute).

    Returns:
        Summary of triggered schedules
    """
    logger.info("Checking for due schedules")

    with self.db.get_session() as session:
        schedule_service = ScheduleService(session)

        # Get due schedules
        due_schedules = schedule_service.get_due_schedules()

        triggered_count = 0
        triggered_schedules = []

        for schedule in due_schedules:
            try:
                # Create a run
                run = ScheduledRun(
                    schedule_id=schedule['id'],
                    status='pending'
                )
                session.add(run)
                session.commit()
                session.refresh(run)

                # Trigger analysis
                task = run_scheduled_analysis.delay(run.id)

                # Update run with task ID
                run.celery_task_id = task.id
                session.commit()

                triggered_count += 1
                triggered_schedules.append({
                    'schedule_id': schedule['id'],
                    'schedule_name': schedule['name'],
                    'run_id': run.id,
                    'task_id': task.id
                })

                logger.info(f"Triggered schedule: {schedule['name']} (run_id: {run.id})")

            except Exception as e:
                logger.error(f"Error triggering schedule {schedule['id']}: {e}", exc_info=True)

        logger.info(f"Triggered {triggered_count} schedules")

        return {
            'success': True,
            'triggered_count': triggered_count,
            'triggered_schedules': triggered_schedules
        }
