"""
Metrics API endpoints
"""

from fastapi import APIRouter, Response
from typing import Dict, Any

from src.core.metrics import metrics_collector
from src.core.database import DatabaseManager
from src.models import Task, TaskStatus, Agent, AgentStatus

router = APIRouter()


@router.get("/metrics")
async def get_prometheus_metrics():
    """
    Prometheus metrics endpoint

    Returns:
        Response: Prometheus formatted metrics
    """
    # Update metrics before returning
    _update_metrics()

    return Response(
        content=metrics_collector.get_metrics(),
        media_type=metrics_collector.get_content_type()
    )


@router.get("/metrics/summary")
async def get_metrics_summary() -> Dict[str, Any]:
    """
    Get human-readable metrics summary

    Returns:
        dict: Metrics summary
    """
    db_manager = DatabaseManager()

    with db_manager.session_scope() as session:
        # Task metrics
        total_tasks = session.query(Task).count()
        pending_tasks = session.query(Task).filter(Task.status == TaskStatus.PENDING).count()
        in_progress_tasks = session.query(Task).filter(Task.status == TaskStatus.IN_PROGRESS).count()
        completed_tasks = session.query(Task).filter(Task.status == TaskStatus.COMPLETED).count()
        failed_tasks = session.query(Task).filter(Task.status == TaskStatus.FAILED).count()

        # Agent metrics
        total_agents = session.query(Agent).count()
        idle_agents = session.query(Agent).filter(Agent.status == AgentStatus.IDLE).count()
        busy_agents = session.query(Agent).filter(Agent.status == AgentStatus.BUSY).count()
        error_agents = session.query(Agent).filter(Agent.status == AgentStatus.ERROR).count()

        # Calculate success rate
        total_completed = completed_tasks + failed_tasks
        success_rate = (completed_tasks / total_completed * 100) if total_completed > 0 else 0

        # Agent utilization
        utilization_rate = (busy_agents / total_agents * 100) if total_agents > 0 else 0

    return {
        "tasks": {
            "total": total_tasks,
            "pending": pending_tasks,
            "in_progress": in_progress_tasks,
            "completed": completed_tasks,
            "failed": failed_tasks,
            "success_rate": round(success_rate, 2)
        },
        "agents": {
            "total": total_agents,
            "idle": idle_agents,
            "busy": busy_agents,
            "error": error_agents,
            "utilization_rate": round(utilization_rate, 2)
        }
    }


def _update_metrics():
    """
    Update Prometheus metrics with current database state
    """
    db_manager = DatabaseManager()

    try:
        with db_manager.session_scope() as session:
            # Update task queue sizes
            for status in TaskStatus:
                count = session.query(Task).filter(Task.status == status).count()
                metrics_collector.update_task_queue_size(status.value, count)

            # Update agent counts by role
            from src.models import AgentRole
            for role in AgentRole:
                count = session.query(Agent).filter(
                    Agent.role == role,
                    Agent.is_active == True
                ).count()
                metrics_collector.update_agent_count(role.value, count)

            # Update database connections (approximate)
            # In production, this would query the actual connection pool
            metrics_collector.update_database_connections(10)

        # Update Celery workers
        try:
            from celery_app import celery_app
            inspect = celery_app.control.inspect()
            active_workers = inspect.active()
            worker_count = len(active_workers) if active_workers else 0
            metrics_collector.update_celery_workers(worker_count)
        except Exception:
            metrics_collector.update_celery_workers(0)

    except Exception as e:
        # Log error but don't fail the metrics endpoint
        print(f"Error updating metrics: {e}")
