"""
Task Worker - Handles task execution and management
"""

import asyncio
from celery import shared_task
from datetime import datetime
from typing import Dict, Any

from src.core.database import DatabaseManager
from src.core.logging import logger
from src.models import Task, TaskStatus


@shared_task(name='src.workers.task_worker.execute_task', bind=True, max_retries=3)
def execute_task(self, task_id: int) -> Dict[str, Any]:
    """
    Execute a task by delegating to the appropriate agent

    Auto-assigns an agent by task_type if none is assigned yet, then runs
    the real agent execution pipeline (AgentService.execute_agent - creates
    the configured LLM provider, resolves the specialized agent from the
    registry, and actually calls the LLM) and persists the real result onto
    the task. Agent-level failures (bad LLM response, connection error) are
    recorded as a normal FAILED task rather than retried, since
    AgentService.execute_agent already handles those internally - only
    unexpected errors (e.g. DB issues) trigger a Celery retry.

    Args:
        task_id: ID of task to execute

    Returns:
        dict: Execution result with status and output
    """
    from src.services.task_service import TaskService
    from src.services.agent_service import AgentService
    from src.core.exceptions import ValidationException

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

            # Agent assignment requires the task still be PENDING/QUEUED, so
            # it must happen before the IN_PROGRESS transition below.
            if not task.assigned_agent_id:
                try:
                    task = TaskService.auto_assign_task(session, task_id)
                except ValidationException as e:
                    task.status = TaskStatus.FAILED
                    task.error_message = str(e)
                    task.completed_at = datetime.utcnow()
                    return {'success': False, 'error': str(e), 'task_id': task_id}

            task.status = TaskStatus.IN_PROGRESS
            task.started_at = datetime.utcnow()
            session.flush()

            # Each specialized agent reads a different key for its "main
            # content" field (research/writer: topic, code: requirements,
            # data_analyst: data/questions, planner: goal) - there's no
            # single universal field name. Seed all of them from the task's
            # own title/description so whichever agent gets assigned finds
            # something meaningful, then let any explicit input_data the
            # caller provided override those defaults.
            # "topic" (research/writer agents) is the actual subject to
            # research/write about - task.description, not task.title.
            # Using title here made every research/writer task answer a
            # question about its own short label instead of what was
            # actually asked - confirmed live: "Summarize REST vs GraphQL"
            # produced a report titled "Test: DataAnalyst Agent" describing
            # a hypothetical data analyst, because title was "Test:
            # DataAnalyst agent".
            agent_input = {
                "topic": task.description,
                "requirements": task.description,
                "goal": task.description,
                "data": {},
                "questions": [task.description],
                "context": task.description,
            }
            agent_input.update(task.input_data or {})

            execution = asyncio.run(AgentService.execute_agent(
                session=session,
                agent_id=task.assigned_agent_id,
                input_data=agent_input,
                task_id=task_id,
            ))

            if execution.is_successful:
                task.status = TaskStatus.COMPLETED
                task.output_data = execution.output_data
            else:
                task.status = TaskStatus.FAILED
                task.error_message = execution.error_message

            task.completed_at = datetime.utcnow()
            task.actual_cost = execution.cost or 0.0
            if task.started_at:
                task.actual_duration_seconds = int((task.completed_at - task.started_at).total_seconds())

            return {
                'success': execution.is_successful,
                'task_id': task_id,
                'execution_id': execution.id,
                'agent_id': task.assigned_agent_id,
                'output': execution.output_data,
                'error': execution.error_message,
            }

    except Exception as e:
        logger.error(f"Unexpected error executing task {task_id}: {e}")
        # Update task status to failed
        with db_manager.session_scope() as session:
            task = session.query(Task).filter(Task.id == task_id).first()
            if task:
                task.status = TaskStatus.FAILED
                task.error_message = str(e)
                task.completed_at = datetime.utcnow()

        # Retry with exponential backoff
        raise self.retry(exc=e, countdown=2 ** self.request.retries)


@shared_task(name='src.workers.task_worker.create_task')
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


@shared_task(name='src.workers.task_worker.update_task_status')
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
