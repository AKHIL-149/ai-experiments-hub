"""
Monitoring Worker - Health checks and metrics collection

Periodic tasks for system monitoring, maintenance, and health checks.
Runs via Celery Beat scheduler.
"""

from celery import shared_task
from datetime import datetime, timedelta
from typing import Dict, Any, List
import asyncio

from src.core.database import DatabaseManager
from src.models import Task, TaskStatus, Agent, AgentStatus
from src.core.logging import logger


@shared_task(name='src.workers.monitoring_worker.monitor_queue_health')
def monitor_queue_health() -> Dict[str, Any]:
    """
    Monitor Celery queue health and task distribution

    Returns:
        dict: Queue health metrics
    """
    from celery_app import celery_app

    try:
        logger.info("Monitoring queue health...")
        inspect = celery_app.control.inspect()

        # Get active tasks
        active = inspect.active()
        scheduled = inspect.scheduled()
        reserved = inspect.reserved()

        result = {
            'success': True,
            'timestamp': datetime.utcnow().isoformat(),
            'active_tasks': len(active) if active else 0,
            'scheduled_tasks': len(scheduled) if scheduled else 0,
            'reserved_tasks': len(reserved) if reserved else 0,
        }

        logger.info(
            f"Queue health: {result['active_tasks']} active, "
            f"{result['scheduled_tasks']} scheduled, "
            f"{result['reserved_tasks']} reserved"
        )

        return result

    except Exception as e:
        logger.error(f"Queue health check failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@shared_task(name='src.workers.monitoring_worker.check_stalled_tasks')
def check_stalled_tasks() -> Dict[str, Any]:
    """
    Check for tasks that have been in progress for too long

    Returns:
        dict: Stalled tasks information
    """
    db_manager = DatabaseManager()

    try:
        logger.info("Checking for stalled tasks...")
        with db_manager.session_scope() as session:
            # Find tasks in progress for more than 1 hour
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)

            stalled_tasks = session.query(Task).filter(
                Task.status == TaskStatus.IN_PROGRESS,
                Task.started_at < one_hour_ago
            ).all()

            stalled_count = len(stalled_tasks)

            # Mark as failed and send notifications
            for task in stalled_tasks:
                task.status = TaskStatus.FAILED
                task.error_message = 'Task stalled - exceeded timeout'
                task.completed_at = datetime.utcnow()

                # Send WebSocket notification
                try:
                    from src.core.websocket import notify_task_update

                    def run_async(coro):
                        try:
                            loop = asyncio.get_event_loop()
                        except RuntimeError:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                        if loop.is_running():
                            asyncio.create_task(coro)
                        else:
                            loop.run_until_complete(coro)

                    run_async(notify_task_update(
                        task_id=task.id,
                        event_type="status_changed",
                        data={
                            "status": "failed",
                            "error_message": task.error_message,
                            "reason": "stalled"
                        }
                    ))
                except Exception:
                    pass  # Don't fail if notification fails

            if stalled_count > 0:
                logger.warning(f"Found {stalled_count} stalled tasks: {[t.id for t in stalled_tasks]}")
            else:
                logger.info("No stalled tasks found")

            return {
                'success': True,
                'stalled_tasks_count': stalled_count,
                'task_ids': [task.id for task in stalled_tasks]
            }

    except Exception as e:
        logger.error(f"Stalled task check failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@shared_task(name='src.workers.monitoring_worker.update_agent_metrics')
def update_agent_metrics() -> Dict[str, Any]:
    """
    Update agent performance metrics

    Returns:
        dict: Updated metrics summary
    """
    db_manager = DatabaseManager()

    try:
        logger.info("Updating agent metrics...")
        with db_manager.session_scope() as session:
            agents = session.query(Agent).all()

            metrics = {
                'total_agents': len(agents),
                'idle_agents': 0,
                'busy_agents': 0,
                'error_agents': 0,
                'offline_agents': 0,
            }

            for agent in agents:
                if agent.status == AgentStatus.IDLE:
                    metrics['idle_agents'] += 1
                elif agent.status == AgentStatus.BUSY:
                    metrics['busy_agents'] += 1
                elif agent.status == AgentStatus.ERROR:
                    metrics['error_agents'] += 1
                elif agent.status == AgentStatus.OFFLINE:
                    metrics['offline_agents'] += 1

            logger.info(
                f"Agent metrics: {metrics['total_agents']} total, "
                f"{metrics['idle_agents']} idle, "
                f"{metrics['busy_agents']} busy, "
                f"{metrics['error_agents']} errors"
            )

            return {
                'success': True,
                'timestamp': datetime.utcnow().isoformat(),
                'metrics': metrics
            }

    except Exception as e:
        logger.error(f"Agent metrics update failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@shared_task(name='src.workers.monitoring_worker.cleanup_completed_tasks')
def cleanup_completed_tasks(days_to_keep: int = 30) -> Dict[str, Any]:
    """
    Clean up old completed tasks

    Args:
        days_to_keep: Number of days to keep completed tasks

    Returns:
        dict: Cleanup summary
    """
    db_manager = DatabaseManager()

    try:
        logger.info(f"Cleaning up tasks older than {days_to_keep} days...")
        with db_manager.session_scope() as session:
            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

            old_tasks = session.query(Task).filter(
                Task.status.in_([TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]),
                Task.completed_at < cutoff_date
            ).all()

            deleted_count = len(old_tasks)

            for task in old_tasks:
                session.delete(task)

            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} old tasks (older than {cutoff_date.date()})")
            else:
                logger.info("No old tasks to delete")

            return {
                'success': True,
                'deleted_tasks': deleted_count,
                'cutoff_date': cutoff_date.isoformat()
            }

    except Exception as e:
        logger.error(f"Task cleanup failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@shared_task(name='src.workers.monitoring_worker.generate_daily_report')
def generate_daily_report() -> Dict[str, Any]:
    """
    Generate daily performance report

    Returns:
        dict: Daily report data
    """
    db_manager = DatabaseManager()

    try:
        logger.info("Generating daily report...")
        with db_manager.session_scope() as session:
            yesterday = datetime.utcnow() - timedelta(days=1)

            # Task statistics
            total_tasks = session.query(Task).filter(Task.created_at >= yesterday).count()
            completed_tasks = session.query(Task).filter(
                Task.status == TaskStatus.COMPLETED,
                Task.completed_at >= yesterday
            ).count()
            failed_tasks = session.query(Task).filter(
                Task.status == TaskStatus.FAILED,
                Task.completed_at >= yesterday
            ).count()

            # Agent statistics
            total_agents = session.query(Agent).count()
            active_agents = session.query(Agent).filter(Agent.is_active == True).count()

            success_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0

            logger.info(
                f"Daily report: {total_tasks} tasks ({completed_tasks} completed, "
                f"{failed_tasks} failed, {success_rate:.1f}% success rate), "
                f"{active_agents}/{total_agents} agents active"
            )

            return {
                'success': True,
                'date': yesterday.date().isoformat(),
                'tasks': {
                    'total': total_tasks,
                    'completed': completed_tasks,
                    'failed': failed_tasks,
                    'success_rate': success_rate
                },
                'agents': {
                    'total': total_agents,
                    'active': active_agents
                }
            }

    except Exception as e:
        logger.error(f"Daily report generation failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@shared_task(name='src.workers.monitoring_worker.process_pending_tasks')
def process_pending_tasks() -> Dict[str, Any]:
    """
    Process pending tasks and auto-assign to available agents

    Returns:
        dict: Processing summary
    """
    db_manager = DatabaseManager()

    try:
        logger.info("Processing pending tasks...")
        with db_manager.session_scope() as session:
            from src.services import TaskService

            # Get ready tasks (no blocking dependencies)
            ready_tasks: List[Task] = TaskService.get_ready_tasks(session, limit=20)

            assigned_count = 0
            for task in ready_tasks:
                try:
                    # Auto-assign to best available agent
                    TaskService.auto_assign_task(session, task.id)
                    assigned_count += 1
                except Exception as e:
                    logger.warning(f"Failed to auto-assign task {task.id}: {e}")

            logger.info(f"Auto-assigned {assigned_count} pending tasks")

            return {
                'success': True,
                'ready_tasks': len(ready_tasks),
                'assigned_tasks': assigned_count
            }

    except Exception as e:
        logger.error(f"Pending task processing failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }


@shared_task(name='src.workers.monitoring_worker.check_agent_health')
def check_agent_health() -> Dict[str, Any]:
    """
    Check agent health and mark unresponsive agents as offline

    Returns:
        dict: Health check summary
    """
    db_manager = DatabaseManager()

    try:
        logger.info("Checking agent health...")
        with db_manager.session_scope() as session:
            # Find agents that haven't been active for more than 30 minutes
            inactive_threshold = datetime.utcnow() - timedelta(minutes=30)

            inactive_agents = session.query(Agent).filter(
                Agent.is_active == True,
                Agent.status.in_([AgentStatus.IDLE, AgentStatus.BUSY]),
                Agent.last_active_at < inactive_threshold
            ).all()

            inactive_count = len(inactive_agents)

            # Mark as offline
            for agent in inactive_agents:
                agent.status = AgentStatus.OFFLINE
                agent.current_task_id = None

            if inactive_count > 0:
                logger.warning(f"Marked {inactive_count} inactive agents as offline")
            else:
                logger.info("All agents are healthy")

            return {
                'success': True,
                'inactive_agents': inactive_count,
                'agent_ids': [agent.id for agent in inactive_agents]
            }

    except Exception as e:
        logger.error(f"Agent health check failed: {e}")
        return {
            'success': False,
            'error': str(e)
        }
