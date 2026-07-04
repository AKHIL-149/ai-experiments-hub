"""
Agent Execution Manager for task queue and execution lifecycle management
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func

from src.models.agent import Agent, AgentStatus
from src.models.task import Task, TaskStatus
from src.models.agent_execution import AgentExecution, ExecutionStatus
from src.models.agent_message import AgentMessage, MessageType, MessagePriority
from src.services.agent_communication import AgentCommunicationService
from src.services.memory_service import MemoryService
from src.models.shared_memory import MemoryScope, MemoryType
from src.core.logging import logger


class ExecutionManager:
    """
    Manager for agent execution lifecycle, task queues, and error recovery.

    Handles:
    - Task queue management per agent
    - Execution lifecycle (start, pause, resume, cancel, retry)
    - Error recovery and retry logic
    - Execution monitoring and metrics
    - Resource cleanup
    """

    @staticmethod
    def enqueue_task(
        session: Session,
        agent_id: int,
        task_id: int,
        priority: int = 0,
        scheduled_at: Optional[datetime] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> AgentExecution:
        """
        Add a task to an agent's queue.

        Args:
            session: Database session
            agent_id: Agent ID
            task_id: Task ID to enqueue
            priority: Task priority (higher = more important)
            scheduled_at: When to execute (None = immediate)
            context: Additional context

        Returns:
            AgentExecution record
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # Create execution in queued state
        execution = AgentExecution(
            agent_id=agent_id,
            task_id=task_id,
            status=ExecutionStatus.QUEUED,
            input_data=context or {},
            priority=priority,
            scheduled_at=scheduled_at or datetime.utcnow()
        )

        session.add(execution)
        session.flush()

        logger.info(
            f"Enqueued task {task_id} for agent {agent_id} "
            f"(execution {execution.id}, priority {priority})"
        )

        return execution

    @staticmethod
    def get_next_task(
        session: Session,
        agent_id: int
    ) -> Optional[AgentExecution]:
        """
        Get the next task from an agent's queue.

        Prioritizes by:
        1. Priority (descending)
        2. Scheduled time (ascending)
        3. Creation time (ascending)

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Next execution to process, or None
        """
        now = datetime.utcnow()

        execution = session.query(AgentExecution).filter(
            and_(
                AgentExecution.agent_id == agent_id,
                AgentExecution.status == ExecutionStatus.QUEUED,
                or_(
                    AgentExecution.scheduled_at.is_(None),
                    AgentExecution.scheduled_at <= now
                )
            )
        ).order_by(
            AgentExecution.priority.desc(),
            AgentExecution.scheduled_at.asc(),
            AgentExecution.created_at.asc()
        ).first()

        return execution

    @staticmethod
    def start_execution(
        session: Session,
        execution_id: int
    ) -> AgentExecution:
        """
        Start an execution.

        Args:
            session: Database session
            execution_id: Execution ID

        Returns:
            Updated execution
        """
        execution = session.query(AgentExecution).filter(
            AgentExecution.id == execution_id
        ).first()

        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.status not in [ExecutionStatus.QUEUED, ExecutionStatus.PAUSED]:
            raise ValueError(
                f"Cannot start execution {execution_id} in status {execution.status}"
            )

        # Update execution
        execution.status = ExecutionStatus.RUNNING
        execution.started_at = datetime.utcnow()
        execution.attempts += 1

        # Update agent status
        agent = execution.agent
        agent.status = AgentStatus.BUSY
        agent.current_task_id = execution.task_id

        # Update task status
        task = execution.task
        task.status = TaskStatus.IN_PROGRESS
        task.assigned_agent_id = execution.agent_id

        session.flush()

        logger.info(
            f"Started execution {execution_id} "
            f"(agent {execution.agent_id}, task {execution.task_id}, attempt {execution.attempts})"
        )

        return execution

    @staticmethod
    def complete_execution(
        session: Session,
        execution_id: int,
        output_data: Optional[Dict[str, Any]] = None,
        metrics: Optional[Dict[str, Any]] = None
    ) -> AgentExecution:
        """
        Mark an execution as completed.

        Args:
            session: Database session
            execution_id: Execution ID
            output_data: Execution output
            metrics: Execution metrics

        Returns:
            Updated execution
        """
        execution = session.query(AgentExecution).filter(
            AgentExecution.id == execution_id
        ).first()

        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.status != ExecutionStatus.RUNNING:
            raise ValueError(
                f"Cannot complete execution {execution_id} in status {execution.status}"
            )

        # Update execution
        execution.status = ExecutionStatus.COMPLETED
        execution.completed_at = datetime.utcnow()
        execution.output_data = output_data or {}
        execution.metrics = metrics or {}

        # Calculate duration
        if execution.started_at:
            duration = (execution.completed_at - execution.started_at).total_seconds()
            execution.metrics["duration_seconds"] = duration

        # Update agent
        agent = execution.agent
        agent.status = AgentStatus.IDLE
        agent.current_task_id = None
        agent.successful_tasks += 1
        agent.last_active = datetime.utcnow()

        # Update average response time
        if agent.average_response_time is None:
            agent.average_response_time = execution.metrics.get("duration_seconds", 0)
        else:
            # Exponential moving average
            alpha = 0.3
            agent.average_response_time = (
                alpha * execution.metrics.get("duration_seconds", 0) +
                (1 - alpha) * agent.average_response_time
            )

        # Update task status
        task = execution.task
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.utcnow()

        session.flush()

        logger.info(
            f"Completed execution {execution_id} "
            f"(duration: {execution.metrics.get('duration_seconds', 0):.2f}s)"
        )

        return execution

    @staticmethod
    def fail_execution(
        session: Session,
        execution_id: int,
        error: str,
        error_details: Optional[Dict[str, Any]] = None,
        retry: bool = True
    ) -> Tuple[AgentExecution, Optional[AgentExecution]]:
        """
        Mark an execution as failed.

        Args:
            session: Database session
            execution_id: Execution ID
            error: Error message
            error_details: Additional error details
            retry: Whether to retry

        Returns:
            Tuple of (failed execution, retry execution or None)
        """
        execution = session.query(AgentExecution).filter(
            AgentExecution.id == execution_id
        ).first()

        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        # Update execution
        execution.status = ExecutionStatus.FAILED
        execution.completed_at = datetime.utcnow()
        execution.error_message = error
        execution.error_details = error_details or {}

        # Update agent
        agent = execution.agent
        agent.status = AgentStatus.IDLE
        agent.current_task_id = None
        agent.failed_tasks += 1
        agent.last_active = datetime.utcnow()

        # Update task status
        task = execution.task
        task.status = TaskStatus.FAILED
        task.error_message = error

        session.flush()

        logger.error(
            f"Failed execution {execution_id}: {error} "
            f"(attempt {execution.attempts})"
        )

        # Retry if needed
        retry_execution = None
        if retry and execution.attempts < 3:  # Max 3 attempts
            retry_execution = ExecutionManager.enqueue_task(
                session=session,
                agent_id=execution.agent_id,
                task_id=execution.task_id,
                priority=execution.priority,
                context={
                    **execution.input_data,
                    "retry_of_execution_id": execution.id,
                    "previous_error": error,
                    "attempt": execution.attempts + 1
                }
            )

            task.status = TaskStatus.PENDING
            task.error_message = f"Retrying after failure: {error}"

            logger.info(
                f"Created retry execution {retry_execution.id} "
                f"for failed execution {execution_id}"
            )

        return execution, retry_execution

    @staticmethod
    def pause_execution(
        session: Session,
        execution_id: int,
        reason: Optional[str] = None
    ) -> AgentExecution:
        """
        Pause a running execution.

        Args:
            session: Database session
            execution_id: Execution ID
            reason: Pause reason

        Returns:
            Updated execution
        """
        execution = session.query(AgentExecution).filter(
            AgentExecution.id == execution_id
        ).first()

        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.status != ExecutionStatus.RUNNING:
            raise ValueError(
                f"Cannot pause execution {execution_id} in status {execution.status}"
            )

        execution.status = ExecutionStatus.PAUSED
        execution.error_message = reason

        # Update agent
        agent = execution.agent
        agent.status = AgentStatus.IDLE
        agent.current_task_id = None

        session.flush()

        logger.info(f"Paused execution {execution_id}: {reason}")

        return execution

    @staticmethod
    def resume_execution(
        session: Session,
        execution_id: int
    ) -> AgentExecution:
        """
        Resume a paused execution.

        Args:
            session: Database session
            execution_id: Execution ID

        Returns:
            Updated execution
        """
        execution = session.query(AgentExecution).filter(
            AgentExecution.id == execution_id
        ).first()

        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.status != ExecutionStatus.PAUSED:
            raise ValueError(
                f"Cannot resume execution {execution_id} in status {execution.status}"
            )

        execution.status = ExecutionStatus.RUNNING

        # Update agent
        agent = execution.agent
        agent.status = AgentStatus.BUSY
        agent.current_task_id = execution.task_id

        session.flush()

        logger.info(f"Resumed execution {execution_id}")

        return execution

    @staticmethod
    def cancel_execution(
        session: Session,
        execution_id: int,
        reason: Optional[str] = None
    ) -> AgentExecution:
        """
        Cancel an execution.

        Args:
            session: Database session
            execution_id: Execution ID
            reason: Cancellation reason

        Returns:
            Updated execution
        """
        execution = session.query(AgentExecution).filter(
            AgentExecution.id == execution_id
        ).first()

        if not execution:
            raise ValueError(f"Execution {execution_id} not found")

        if execution.status in [ExecutionStatus.COMPLETED, ExecutionStatus.FAILED]:
            raise ValueError(
                f"Cannot cancel execution {execution_id} in status {execution.status}"
            )

        execution.status = ExecutionStatus.CANCELLED
        execution.completed_at = datetime.utcnow()
        execution.error_message = reason

        # Update agent if currently running
        if execution.status == ExecutionStatus.RUNNING:
            agent = execution.agent
            agent.status = AgentStatus.IDLE
            agent.current_task_id = None

        # Update task
        task = execution.task
        task.status = TaskStatus.CANCELLED
        task.error_message = reason

        session.flush()

        logger.info(f"Cancelled execution {execution_id}: {reason}")

        return execution

    @staticmethod
    def get_agent_queue(
        session: Session,
        agent_id: int,
        include_completed: bool = False,
        limit: int = 100
    ) -> List[AgentExecution]:
        """
        Get an agent's task queue.

        Args:
            session: Database session
            agent_id: Agent ID
            include_completed: Include completed/failed executions
            limit: Maximum results

        Returns:
            List of executions
        """
        query = session.query(AgentExecution).filter(
            AgentExecution.agent_id == agent_id
        )

        if not include_completed:
            query = query.filter(
                AgentExecution.status.in_([
                    ExecutionStatus.QUEUED,
                    ExecutionStatus.RUNNING,
                    ExecutionStatus.PAUSED,
                    ExecutionStatus.ASSIGNED
                ])
            )

        executions = query.order_by(
            AgentExecution.priority.desc(),
            AgentExecution.created_at.asc()
        ).limit(limit).all()

        return executions

    @staticmethod
    def get_execution_metrics(
        session: Session,
        agent_id: Optional[int] = None,
        task_id: Optional[int] = None,
        time_range_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get execution metrics.

        Args:
            session: Database session
            agent_id: Filter by agent
            task_id: Filter by task
            time_range_hours: Time range in hours

        Returns:
            Metrics dictionary
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=time_range_hours)

        query = session.query(AgentExecution).filter(
            AgentExecution.created_at >= cutoff_time
        )

        if agent_id:
            query = query.filter(AgentExecution.agent_id == agent_id)

        if task_id:
            query = query.filter(AgentExecution.task_id == task_id)

        executions = query.all()

        # Calculate metrics
        total = len(executions)
        by_status = {}
        for status in ExecutionStatus:
            count = len([e for e in executions if e.status == status])
            if count > 0:
                by_status[status.value] = count

        completed = [e for e in executions if e.status == ExecutionStatus.COMPLETED]
        failed = [e for e in executions if e.status == ExecutionStatus.FAILED]

        # Calculate durations
        durations = [
            e.metrics.get("duration_seconds", 0)
            for e in completed
            if e.metrics and "duration_seconds" in e.metrics
        ]

        metrics = {
            "total_executions": total,
            "by_status": by_status,
            "success_rate": len(completed) / total if total > 0 else 0,
            "failure_rate": len(failed) / total if total > 0 else 0,
            "time_range_hours": time_range_hours,
            "agent_id": agent_id,
            "task_id": task_id
        }

        if durations:
            metrics["average_duration_seconds"] = sum(durations) / len(durations)
            metrics["min_duration_seconds"] = min(durations)
            metrics["max_duration_seconds"] = max(durations)

        return metrics

    @staticmethod
    def cleanup_old_executions(
        session: Session,
        days_old: int = 30,
        keep_status: Optional[List[ExecutionStatus]] = None
    ) -> int:
        """
        Clean up old completed/failed executions.

        Args:
            session: Database session
            days_old: Delete executions older than this
            keep_status: Statuses to keep (don't delete)

        Returns:
            Number of executions deleted
        """
        cutoff_time = datetime.utcnow() - timedelta(days=days_old)

        keep_status = keep_status or [
            ExecutionStatus.QUEUED,
            ExecutionStatus.RUNNING,
            ExecutionStatus.PAUSED
        ]

        executions = session.query(AgentExecution).filter(
            and_(
                AgentExecution.created_at < cutoff_time,
                ~AgentExecution.status.in_(keep_status)
            )
        ).all()

        count = len(executions)

        for execution in executions:
            session.delete(execution)

        session.flush()

        if count > 0:
            logger.info(f"Cleaned up {count} old executions (>{days_old} days)")

        return count

    @staticmethod
    def get_stuck_executions(
        session: Session,
        timeout_hours: int = 1
    ) -> List[AgentExecution]:
        """
        Find executions that are stuck (running too long).

        Args:
            session: Database session
            timeout_hours: Consider stuck if running longer than this

        Returns:
            List of stuck executions
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=timeout_hours)

        executions = session.query(AgentExecution).filter(
            and_(
                AgentExecution.status == ExecutionStatus.RUNNING,
                AgentExecution.started_at < cutoff_time
            )
        ).all()

        if executions:
            logger.warning(f"Found {len(executions)} stuck executions")

        return executions

    @staticmethod
    def recover_stuck_executions(
        session: Session,
        timeout_hours: int = 1
    ) -> List[AgentExecution]:
        """
        Recover stuck executions by marking as failed and retrying.

        Args:
            session: Database session
            timeout_hours: Consider stuck if running longer than this

        Returns:
            List of recovered executions
        """
        stuck = ExecutionManager.get_stuck_executions(session, timeout_hours)

        recovered = []
        for execution in stuck:
            _, retry_execution = ExecutionManager.fail_execution(
                session=session,
                execution_id=execution.id,
                error=f"Execution timeout after {timeout_hours} hours",
                error_details={"timeout_hours": timeout_hours},
                retry=True
            )

            if retry_execution:
                recovered.append(retry_execution)

        if recovered:
            logger.info(f"Recovered {len(recovered)} stuck executions")

        return recovered
