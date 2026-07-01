"""
Task service for managing task operations and lifecycle
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from src.models.task import Task, TaskStatus, TaskDependency
from src.models.agent import AgentRole
from src.services.agent_service import AgentService
from src.services.workflow_service import workflow_service
from src.core.logging import logger
from src.core.exceptions import (
    TaskNotFoundError,
    ValidationError,
    WorkflowExecutionError,
    AgentNotFoundError
)


class TaskService:
    """Service for task management and orchestration"""

    @staticmethod
    def create_task(
        session: Session,
        title: str,
        description: str,
        task_type: str,
        priority: int = 5,
        input_data: Optional[Dict[str, Any]] = None,
        parent_task_id: Optional[int] = None,
        requires_approval: bool = False
    ) -> Task:
        """
        Create a new task

        Args:
            session: Database session
            title: Task title
            description: Task description
            task_type: Task type
            priority: Task priority (1-10)
            input_data: Input parameters
            parent_task_id: Parent task ID for subtasks
            requires_approval: Whether task requires approval

        Returns:
            Task: Created task

        Raises:
            ValidationError: If validation fails
        """
        try:
            # Validate priority
            if not 1 <= priority <= 10:
                raise ValidationError("Priority must be between 1 and 10")

            # Create task
            task = Task(
                title=title,
                description=description,
                task_type=task_type,
                priority=priority,
                input_data=input_data or {},
                parent_task_id=parent_task_id,
                requires_approval=requires_approval,
                status=TaskStatus.PENDING,
                progress_percentage=0.0
            )

            session.add(task)
            session.commit()
            session.refresh(task)

            logger.info(f"Created task {task.id}: {title}")

            return task

        except ValidationError:
            raise
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create task: {e}")
            raise

    @staticmethod
    def get_task_by_id(session: Session, task_id: int) -> Task:
        """
        Get task by ID

        Args:
            session: Database session
            task_id: Task ID

        Returns:
            Task: Task instance

        Raises:
            TaskNotFoundError: If task not found
        """
        task = session.query(Task).filter(Task.id == task_id).first()

        if not task:
            raise TaskNotFoundError(task_id)

        return task

    @staticmethod
    def update_task_status(
        session: Session,
        task_id: int,
        status: TaskStatus,
        output_data: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None
    ) -> Task:
        """
        Update task status

        Args:
            session: Database session
            task_id: Task ID
            status: New status
            output_data: Task output data
            error_message: Error message if failed

        Returns:
            Task: Updated task

        Raises:
            TaskNotFoundError: If task not found
        """
        task = TaskService.get_task_by_id(session, task_id)

        task.status = status

        if output_data:
            task.output_data = output_data

        if error_message:
            task.error_message = error_message

        # Update timestamps
        if status == TaskStatus.IN_PROGRESS and not task.started_at:
            task.started_at = datetime.utcnow()

        if status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            task.completed_at = datetime.utcnow()

            # Calculate actual duration
            if task.started_at:
                duration = (task.completed_at - task.started_at).total_seconds()
                task.actual_duration_seconds = int(duration)

        session.commit()
        session.refresh(task)

        logger.info(f"Updated task {task_id} status to {status}")

        return task

    @staticmethod
    def update_task_progress(
        session: Session,
        task_id: int,
        progress_percentage: float
    ) -> Task:
        """
        Update task progress

        Args:
            session: Database session
            task_id: Task ID
            progress_percentage: Progress percentage (0-100)

        Returns:
            Task: Updated task

        Raises:
            TaskNotFoundError: If task not found
            ValidationError: If progress is invalid
        """
        if not 0 <= progress_percentage <= 100:
            raise ValidationError("Progress must be between 0 and 100")

        task = TaskService.get_task_by_id(session, task_id)
        task.progress_percentage = progress_percentage

        session.commit()
        session.refresh(task)

        return task

    @staticmethod
    def assign_task_to_agent(
        session: Session,
        task_id: int,
        agent_id: int
    ) -> Task:
        """
        Assign task to an agent

        Args:
            session: Database session
            task_id: Task ID
            agent_id: Agent ID

        Returns:
            Task: Updated task

        Raises:
            TaskNotFoundError: If task not found
            AgentNotFoundError: If agent not found
            ValidationError: If assignment is invalid
        """
        task = TaskService.get_task_by_id(session, task_id)
        agent = AgentService.get_agent_by_id(session, agent_id)

        # Validate task can be assigned
        if task.status not in [TaskStatus.PENDING, TaskStatus.QUEUED]:
            raise ValidationError(f"Cannot assign task with status {task.status}")

        # Validate agent is available
        if not agent.is_available():
            raise ValidationError(f"Agent {agent_id} is not available")

        # Assign task to agent
        task.assigned_agent_id = agent_id
        task.status = TaskStatus.QUEUED

        # Update agent
        AgentService.assign_agent_to_task(session, agent_id, task_id)

        session.commit()
        session.refresh(task)

        logger.info(f"Assigned task {task_id} to agent {agent_id}")

        return task

    @staticmethod
    def auto_assign_task(
        session: Session,
        task_id: int,
        required_role: Optional[AgentRole] = None
    ) -> Task:
        """
        Automatically assign task to best available agent

        Args:
            session: Database session
            task_id: Task ID
            required_role: Required agent role (optional)

        Returns:
            Task: Updated task

        Raises:
            TaskNotFoundError: If task not found
            ValidationError: If no suitable agent available
        """
        task = TaskService.get_task_by_id(session, task_id)

        # Determine required role from task type if not provided
        if not required_role:
            role_mapping = {
                "research": AgentRole.RESEARCHER,
                "coding": AgentRole.CODER,
                "review": AgentRole.REVIEWER,
                "testing": AgentRole.TESTER,
                "documentation": AgentRole.WRITER,
                "general": AgentRole.COORDINATOR
            }
            required_role = role_mapping.get(task.task_type, AgentRole.COORDINATOR)

        # Find best available agent
        agent = AgentService.find_best_agent_for_role(session, required_role)

        if not agent:
            raise ValidationError(f"No available agent found for role {required_role}")

        # Assign task
        return TaskService.assign_task_to_agent(session, task_id, agent.id)

    @staticmethod
    def add_task_dependency(
        session: Session,
        task_id: int,
        depends_on_task_id: int,
        dependency_type: str = "completion",
        is_blocking: bool = True
    ) -> TaskDependency:
        """
        Add a dependency between tasks

        Args:
            session: Database session
            task_id: Task that has the dependency
            depends_on_task_id: Task that must complete first
            dependency_type: Type of dependency
            is_blocking: Whether dependency is blocking

        Returns:
            TaskDependency: Created dependency

        Raises:
            TaskNotFoundError: If either task not found
            ValidationError: If dependency is invalid
        """
        # Validate both tasks exist
        task = TaskService.get_task_by_id(session, task_id)
        depends_on_task = TaskService.get_task_by_id(session, depends_on_task_id)

        # Check for circular dependency
        if TaskService._would_create_cycle(session, task_id, depends_on_task_id):
            raise ValidationError("Dependency would create a circular dependency")

        # Create dependency
        dependency = TaskDependency(
            task_id=task_id,
            depends_on_task_id=depends_on_task_id,
            dependency_type=dependency_type,
            is_blocking=is_blocking
        )

        session.add(dependency)
        session.commit()
        session.refresh(dependency)

        logger.info(f"Added dependency: task {task_id} depends on task {depends_on_task_id}")

        return dependency

    @staticmethod
    def _would_create_cycle(
        session: Session,
        task_id: int,
        depends_on_task_id: int,
        visited: Optional[set] = None
    ) -> bool:
        """
        Check if adding a dependency would create a cycle

        Args:
            session: Database session
            task_id: Task ID
            depends_on_task_id: Dependency task ID
            visited: Set of visited task IDs (for recursion)

        Returns:
            bool: True if cycle would be created
        """
        if visited is None:
            visited = set()

        if depends_on_task_id == task_id:
            return True

        if depends_on_task_id in visited:
            return False

        visited.add(depends_on_task_id)

        # Get all tasks that depends_on_task depends on
        dependencies = session.query(TaskDependency).filter(
            TaskDependency.task_id == depends_on_task_id
        ).all()

        for dep in dependencies:
            if TaskService._would_create_cycle(session, task_id, dep.depends_on_task_id, visited):
                return True

        return False

    @staticmethod
    def get_ready_tasks(session: Session, limit: int = 10) -> List[Task]:
        """
        Get tasks that are ready to execute

        Args:
            session: Database session
            limit: Maximum number of tasks to return

        Returns:
            list: Tasks ready for execution
        """
        # Get pending/queued tasks
        tasks = session.query(Task).filter(
            or_(
                Task.status == TaskStatus.PENDING,
                Task.status == TaskStatus.QUEUED
            )
        ).order_by(Task.priority.asc(), Task.created_at.asc()).limit(limit).all()

        # Filter to only tasks with satisfied dependencies
        ready_tasks = [task for task in tasks if task.is_ready_to_execute()]

        return ready_tasks

    @staticmethod
    def execute_task_with_workflow(
        session: Session,
        task_id: int,
        workflow_type: str = "simple"
    ) -> Dict[str, Any]:
        """
        Execute a task using the workflow engine

        Args:
            session: Database session
            task_id: Task ID
            workflow_type: Type of workflow to use

        Returns:
            dict: Workflow execution result

        Raises:
            TaskNotFoundError: If task not found
            WorkflowExecutionError: If workflow execution fails
        """
        task = TaskService.get_task_by_id(session, task_id)

        # Update task status
        TaskService.update_task_status(session, task_id, TaskStatus.IN_PROGRESS)

        try:
            # Execute workflow
            final_state = workflow_service.execute_workflow(
                task_id=task.id,
                task_title=task.title,
                task_description=task.description,
                task_type=task.task_type,
                priority=task.priority,
                input_data=task.input_data,
                workflow_type=workflow_type
            )

            # Update task with results
            task.output_data = {
                "research": final_state.get("research_output"),
                "code": final_state.get("code_output"),
                "review": final_state.get("review_output"),
                "test": final_state.get("test_output"),
                "document": final_state.get("document_output")
            }

            task.progress_percentage = final_state.get("progress", 100)
            task.actual_cost = final_state.get("total_cost", 0.0)

            # Update status based on workflow result
            workflow_status = final_state.get("status", "completed")
            if workflow_status == "completed":
                TaskService.update_task_status(
                    session,
                    task_id,
                    TaskStatus.COMPLETED,
                    output_data=task.output_data
                )
            elif workflow_status == "failed":
                TaskService.update_task_status(
                    session,
                    task_id,
                    TaskStatus.FAILED,
                    error_message=final_state.get("error", "Workflow execution failed")
                )

            # Update agent metrics if assigned
            if task.assigned_agent_id:
                execution_time = final_state.get("execution_time", 0)
                success = workflow_status == "completed"
                cost = final_state.get("total_cost", 0.0)
                tokens = final_state.get("total_tokens", 0)

                AgentService.update_agent_metrics(
                    session,
                    task.assigned_agent_id,
                    int(execution_time),
                    success,
                    cost,
                    tokens
                )

                # Release agent
                AgentService.update_agent_status(
                    session,
                    task.assigned_agent_id,
                    AgentStatus.IDLE
                )

            logger.info(
                f"Workflow execution completed for task {task_id}: "
                f"status={workflow_status}, cost=${final_state.get('total_cost', 0):.4f}"
            )

            return {
                "task_id": task.id,
                "status": task.status.value,
                "workflow_result": final_state
            }

        except Exception as e:
            # Update task as failed
            TaskService.update_task_status(
                session,
                task_id,
                TaskStatus.FAILED,
                error_message=str(e)
            )

            # Release agent if assigned
            if task.assigned_agent_id:
                try:
                    AgentService.update_agent_status(
                        session,
                        task.assigned_agent_id,
                        AgentStatus.IDLE
                    )
                    AgentService.update_agent_metrics(
                        session,
                        task.assigned_agent_id,
                        0,
                        False,
                        0.0,
                        0
                    )
                except Exception as agent_error:
                    logger.error(f"Failed to update agent after task failure: {agent_error}")

            logger.error(f"Task {task_id} execution failed: {e}")
            raise WorkflowExecutionError(workflow_id=workflow_type, error=str(e))

    @staticmethod
    def cancel_task(session: Session, task_id: int, reason: Optional[str] = None) -> Task:
        """
        Cancel a task

        Args:
            session: Database session
            task_id: Task ID
            reason: Cancellation reason

        Returns:
            Task: Cancelled task

        Raises:
            TaskNotFoundError: If task not found
            ValidationError: If task cannot be cancelled
        """
        task = TaskService.get_task_by_id(session, task_id)

        # Can only cancel pending, queued, or waiting tasks
        if task.status not in [TaskStatus.PENDING, TaskStatus.QUEUED, TaskStatus.WAITING_APPROVAL]:
            raise ValidationError(f"Cannot cancel task with status {task.status}")

        # Release agent if assigned
        if task.assigned_agent_id:
            try:
                AgentService.update_agent_status(
                    session,
                    task.assigned_agent_id,
                    AgentStatus.IDLE
                )
            except Exception as e:
                logger.warning(f"Failed to release agent during task cancellation: {e}")

        # Update task
        TaskService.update_task_status(
            session,
            task_id,
            TaskStatus.CANCELLED,
            error_message=reason or "Task cancelled"
        )

        logger.info(f"Cancelled task {task_id}: {reason}")

        return task
