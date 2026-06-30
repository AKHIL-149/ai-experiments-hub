"""
Monitoring Worker - Health checks and metrics collection
"""

from celery import shared_task
from datetime import datetime, timedelta
from typing import Dict, Any

from src.core.database import DatabaseManager
from src.models import Task, TaskStatus, Agent, AgentStatus


@shared_task(name='src.workers.monitoring_worker.monitor_queue_health')
def monitor_queue_health() -> Dict[str, Any]:
    """
    Monitor Celery queue health and task distribution

    Returns:
        dict: Queue health metrics
    """
    from celery_app import celery_app

    try:
        inspect = celery_app.control.inspect()

        # Get active tasks
        active = inspect.active()
        scheduled = inspect.scheduled()
        reserved = inspect.reserved()

        return {
            'success': True,
            'timestamp': datetime.utcnow().isoformat(),
            'active_tasks': len(active) if active else 0,
            'scheduled_tasks': len(scheduled) if scheduled else 0,
            'reserved_tasks': len(reserved) if reserved else 0,
        }

    except Exception as e:
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
        with db_manager.session_scope() as session:
            # Find tasks in progress for more than 1 hour
            one_hour_ago = datetime.utcnow() - timedelta(hours=1)

            stalled_tasks = session.query(Task).filter(
                Task.status == TaskStatus.IN_PROGRESS,
                Task.started_at < one_hour_ago
            ).all()

            stalled_count = len(stalled_tasks)

            # Mark as failed
            for task in stalled_tasks:
                task.status = TaskStatus.FAILED
                task.error_message = 'Task stalled - exceeded timeout'
                task.completed_at = datetime.utcnow()

            return {
                'success': True,
                'stalled_tasks_count': stalled_count,
                'task_ids': [task.id for task in stalled_tasks]
            }

    except Exception as e:
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
        with db_manager.session_scope() as session:
            agents = session.query(Agent).all()

            metrics = {
                'total_agents': len(agents),
                'idle_agents': 0,
                'busy_agents': 0,
                'error_agents': 0,
            }

            for agent in agents:
                if agent.status == AgentStatus.IDLE:
                    metrics['idle_agents'] += 1
                elif agent.status == AgentStatus.BUSY:
                    metrics['busy_agents'] += 1
                elif agent.status == AgentStatus.ERROR:
                    metrics['error_agents'] += 1

            return {
                'success': True,
                'timestamp': datetime.utcnow().isoformat(),
                'metrics': metrics
            }

    except Exception as e:
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
        with db_manager.session_scope() as session:
            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)

            old_tasks = session.query(Task).filter(
                Task.status.in_([TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]),
                Task.completed_at < cutoff_date
            ).all()

            deleted_count = len(old_tasks)

            for task in old_tasks:
                session.delete(task)

            return {
                'success': True,
                'deleted_tasks': deleted_count,
                'cutoff_date': cutoff_date.isoformat()
            }

    except Exception as e:
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

            return {
                'success': True,
                'date': yesterday.date().isoformat(),
                'tasks': {
                    'total': total_tasks,
                    'completed': completed_tasks,
                    'failed': failed_tasks,
                    'success_rate': (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
                },
                'agents': {
                    'total': total_agents,
                    'active': active_agents
                }
            }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
