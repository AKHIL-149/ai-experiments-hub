"""
Task Worker - Handles task execution and management
"""

from celery import shared_task
from datetime import datetime
from typing import Dict, Any

from src.core.database import DatabaseManager
from src.models import Task, TaskStatus


@shared_task(name='task_worker.execute_task', bind=True, max_retries=3)
def execute_task(self, task_id: int) -> Dict[str, Any]:
    """
    Execute a task by delegating to appropriate agent

    Args:
        task_id: ID of task to execute

    Returns:
        dict: Execution result with status and output
    """
    db_manager = DatabaseManager()

    try:
        with db_manager.session_scope() as session:
            task = session.query(Task).filter(Task.id == task_id).first()

            if not task:
                return {
                    'success': False,
                    'error': f'Task {task_id} not found',
                    'task_id': task_id
                }

            # Update task status
            task.status = TaskStatus.IN_PROGRESS
            task.started_at = datetime.utcnow()
            session.commit()

            # Task execution logic will be implemented in later commits
            # For now, return placeholder
            return {
                'success': True,
                'task_id': task_id,
                'message': 'Task execution stub - will be implemented with agents'
            }

    except Exception as e:
        # Update task status to failed
        with db_manager.session_scope() as session:
            task = session.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = TaskStatus.FAILED
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()

        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=2 ** self.request.retries)


@shared_task(name='task_worker.create_task')
def create_task(
    title: str,
    description: str,
    task_type: str,
    priority: int = 5,
    input_data: Dict[str, Any] = None,
    parent_task_id: int = None
) -> Dict[str, Any]:
    """
    Create a new task in the database

    Args:
        title: Task title
        description: Task description
        task_type: Type of task
        priority: Priority (1-10, lower is higher priority)
        input_data: Input parameters for the task
        parent_task_id: Optional parent task for subtasks

    Returns:
        dict: Created task information
    """
    db_manager = DatabaseManager()

    try:
        with db_manager.session_scope() as session:
            task = Task(
                title=title,
                description=description,
                task_type=task_type,
                priority=priority,
                status=TaskStatus.PENDING,
                input_data=input_data or {},
                parent_task_id=parent_task_id
            )
            session.add(task)
            session.flush()

            task_id = task.id

            return {
                'success': True,
                'task_id': task_id,
                'title': title,
                'status': TaskStatus.PENDING.value
            }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


@shared_task(name='task_worker.update_task_status')
def update_task_status(task_id: int, status: str, output_data: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Update task status and output

    Args:
        task_id: Task ID
        status: New status
        output_data: Optional output data

    Returns:
        dict: Update result
    """
    db_manager = DatabaseManager()

    try:
        with db_manager.session_scope() as session:
            task = session.query(Task).filter(Task.id == task_id).first()

            if not task:
                return {
                    'success': False,
                    'error': f'Task {task_id} not found'
                }

            task.status = TaskStatus(status)

            if output_data:
                task.output_data = output_data

            if status in [TaskStatus.COMPLETED.value, TaskStatus.FAILED.value, TaskStatus.CANCELLED.value]:
                task.completed_at = datetime.utcnow()

                # Calculate actual duration
                if task.started_at:
                    duration = (task.completed_at - task.started_at).total_seconds()
                    task.actual_duration_seconds = int(duration)

            return {
                'success': True,
                'task_id': task_id,
                'status': status
            }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
