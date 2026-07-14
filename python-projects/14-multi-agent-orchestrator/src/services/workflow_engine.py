"""
DAG Workflow Engine Service

Manages and executes DAG-based workflows with parallel execution support.
"""

from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
from collections import defaultdict, deque
import json

from src.models import Workflow, Task, Agent, AgentExecution
from src.core.logging import logger


class WorkflowStatus:
    """Workflow status constants"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus:
    """Workflow step status constants"""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowEngine:
    """Service for managing DAG workflow execution"""

    @staticmethod
    def create_workflow(
        session: Session,
        name: str,
        description: Optional[str] = None,
        steps: List[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create a new workflow definition.

        Args:
            session: Database session
            name: Workflow name
            description: Optional description
            steps: List of workflow steps with dependencies
            metadata: Optional metadata

        Returns:
            Dictionary with workflow details

        Step format:
        {
            "step_id": "unique_id",
            "name": "Step name",
            "agent_type": "coder",
            "task_description": "Task to perform",
            "depends_on": ["other_step_id"],  # Dependencies
            "timeout_minutes": 30,
            "retry_count": 3
        }
        """
        # Validate steps form a valid DAG
        if steps:
            WorkflowEngine._validate_workflow_dag(steps)

        workflow_data = {
            "name": name,
            "description": description,
            "status": WorkflowStatus.PENDING,
            "metadata": metadata or {}
        }

        # Store workflow definition in metadata
        workflow_data["metadata"]["steps"] = steps or []
        workflow_data["metadata"]["created_at"] = datetime.utcnow().isoformat()

        workflow = Workflow(**workflow_data)
        session.add(workflow)
        session.commit()
        session.refresh(workflow)

        return {
            "id": workflow.id,
            "name": workflow.name,
            "description": workflow.description,
            "status": workflow.status,
            "steps": steps or [],
            "created_at": workflow.created_at,
            "metadata": workflow.metadata
        }

    @staticmethod
    def _validate_workflow_dag(steps: List[Dict[str, Any]]) -> None:
        """
        Validate that workflow steps form a valid DAG.

        Raises ValueError if:
        - Circular dependencies exist
        - Referenced dependencies don't exist
        """
        step_ids = {step["step_id"] for step in steps}

        # Check all dependencies exist
        for step in steps:
            for dep in step.get("depends_on", []):
                if dep not in step_ids:
                    raise ValueError(f"Step {step['step_id']} depends on non-existent step {dep}")

        # Check for cycles using DFS
        def has_cycle(step_id: str, visited: Set[str], rec_stack: Set[str]) -> bool:
            visited.add(step_id)
            rec_stack.add(step_id)

            # Find step
            step = next((s for s in steps if s["step_id"] == step_id), None)
            if not step:
                return False

            for dep in step.get("depends_on", []):
                if dep not in visited:
                    if has_cycle(dep, visited, rec_stack):
                        return True
                elif dep in rec_stack:
                    return True

            rec_stack.remove(step_id)
            return False

        visited = set()
        for step in steps:
            if step["step_id"] not in visited:
                if has_cycle(step["step_id"], visited, set()):
                    raise ValueError("Workflow contains circular dependencies")

    @staticmethod
    def start_workflow(
        session: Session,
        workflow_id: int
    ) -> Dict[str, Any]:
        """
        Start workflow execution.

        Args:
            session: Database session
            workflow_id: Workflow ID

        Returns:
            Dictionary with workflow execution details
        """
        workflow = session.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        if workflow.status not in [WorkflowStatus.PENDING, WorkflowStatus.PAUSED]:
            raise ValueError(f"Cannot start workflow in status {workflow.status}")

        # Initialize workflow execution state
        workflow.status = WorkflowStatus.RUNNING
        workflow.metadata["started_at"] = datetime.utcnow().isoformat()
        workflow.metadata["step_states"] = {}

        steps = workflow.metadata.get("steps", [])
        for step in steps:
            workflow.metadata["step_states"][step["step_id"]] = {
                "status": StepStatus.PENDING,
                "attempts": 0,
                "task_id": None,
                "result": None,
                "error": None
            }

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(workflow, "metadata")
        session.commit()

        # Execute ready steps
        WorkflowEngine._execute_ready_steps(session, workflow)

        session.refresh(workflow)

        return {
            "id": workflow.id,
            "name": workflow.name,
            "status": workflow.status,
            "started_at": workflow.metadata.get("started_at"),
            "message": "Workflow execution started"
        }

    @staticmethod
    def _execute_ready_steps(session: Session, workflow: Workflow) -> None:
        """Execute all steps that are ready to run"""
        steps = workflow.metadata.get("steps", [])
        step_states = workflow.metadata.get("step_states", {})

        # Find ready steps (dependencies completed, not yet started)
        for step in steps:
            step_id = step["step_id"]
            state = step_states.get(step_id, {})

            if state.get("status") != StepStatus.PENDING:
                continue

            # Check if all dependencies are completed
            dependencies = step.get("depends_on", [])
            dependencies_met = all(
                step_states.get(dep, {}).get("status") == StepStatus.COMPLETED
                for dep in dependencies
            )

            if dependencies_met:
                # Mark as ready and create task
                step_states[step_id]["status"] = StepStatus.READY
                WorkflowEngine._create_step_task(session, workflow, step)

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(workflow, "metadata")
        session.commit()

    @staticmethod
    def _create_step_task(
        session: Session,
        workflow: Workflow,
        step: Dict[str, Any]
    ) -> None:
        """Create a task for a workflow step"""
        task = Task(
            title=f"{workflow.name} - {step['name']}",
            description=step.get("task_description", ""),
            type=step.get("agent_type", "general"),
            status="pending",
            metadata={
                "workflow_id": workflow.id,
                "step_id": step["step_id"],
                "timeout_minutes": step.get("timeout_minutes", 30),
                "retry_count": step.get("retry_count", 3)
            }
        )
        session.add(task)
        session.flush()

        # Update step state
        step_states = workflow.metadata.get("step_states", {})
        step_states[step["step_id"]]["status"] = StepStatus.RUNNING
        step_states[step["step_id"]]["task_id"] = task.id
        step_states[step["step_id"]]["started_at"] = datetime.utcnow().isoformat()

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(workflow, "metadata")

    @staticmethod
    def update_step_status(
        session: Session,
        workflow_id: int,
        step_id: str,
        status: str,
        result: Optional[Any] = None,
        error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update workflow step status.

        Args:
            session: Database session
            workflow_id: Workflow ID
            step_id: Step ID
            status: New status
            result: Optional step result
            error: Optional error message

        Returns:
            Updated workflow state
        """
        workflow = session.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        step_states = workflow.metadata.get("step_states", {})
        if step_id not in step_states:
            raise ValueError(f"Step {step_id} not found in workflow")

        # Update step state
        step_states[step_id]["status"] = status
        step_states[step_id]["completed_at"] = datetime.utcnow().isoformat()

        if result:
            step_states[step_id]["result"] = result

        if error:
            step_states[step_id]["error"] = error

        if status == StepStatus.FAILED:
            step_states[step_id]["attempts"] += 1

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(workflow, "metadata")
        session.commit()

        # Check if workflow should continue
        if status == StepStatus.COMPLETED:
            # Execute next ready steps
            WorkflowEngine._execute_ready_steps(session, workflow)
            # Check if workflow is complete
            WorkflowEngine._check_workflow_completion(session, workflow)
        elif status == StepStatus.FAILED:
            # Handle failure
            WorkflowEngine._handle_step_failure(session, workflow, step_id)

        session.refresh(workflow)

        return {
            "workflow_id": workflow.id,
            "step_id": step_id,
            "status": status,
            "workflow_status": workflow.status
        }

    @staticmethod
    def _check_workflow_completion(session: Session, workflow: Workflow) -> None:
        """Check if workflow is complete"""
        step_states = workflow.metadata.get("step_states", {})

        all_completed = all(
            state.get("status") == StepStatus.COMPLETED
            for state in step_states.values()
        )

        if all_completed:
            workflow.status = WorkflowStatus.COMPLETED
            workflow.metadata["completed_at"] = datetime.utcnow().isoformat()

            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(workflow, "metadata")
            session.commit()

            logger.info(f"Workflow {workflow.id} completed successfully")

    @staticmethod
    def _handle_step_failure(
        session: Session,
        workflow: Workflow,
        step_id: str
    ) -> None:
        """Handle step failure with retry logic"""
        steps = workflow.metadata.get("steps", [])
        step_states = workflow.metadata.get("step_states", {})

        step = next((s for s in steps if s["step_id"] == step_id), None)
        if not step:
            return

        state = step_states[step_id]
        max_retries = step.get("retry_count", 3)

        if state["attempts"] < max_retries:
            # Retry the step
            logger.info(f"Retrying step {step_id} (attempt {state['attempts']} of {max_retries})")
            state["status"] = StepStatus.PENDING
            WorkflowEngine._execute_ready_steps(session, workflow)
        else:
            # Max retries exceeded, fail workflow
            logger.error(f"Step {step_id} failed after {max_retries} attempts, failing workflow")
            workflow.status = WorkflowStatus.FAILED
            workflow.metadata["failed_at"] = datetime.utcnow().isoformat()
            workflow.metadata["failure_reason"] = f"Step {step_id} failed after {max_retries} attempts"

            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(workflow, "metadata")
            session.commit()

    @staticmethod
    def pause_workflow(
        session: Session,
        workflow_id: int
    ) -> Dict[str, Any]:
        """
        Pause workflow execution.

        Args:
            session: Database session
            workflow_id: Workflow ID

        Returns:
            Updated workflow state
        """
        workflow = session.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        if workflow.status != WorkflowStatus.RUNNING:
            raise ValueError(f"Cannot pause workflow in status {workflow.status}")

        workflow.status = WorkflowStatus.PAUSED
        workflow.metadata["paused_at"] = datetime.utcnow().isoformat()

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(workflow, "metadata")
        session.commit()

        return {
            "id": workflow.id,
            "status": workflow.status,
            "message": "Workflow paused"
        }

    @staticmethod
    def resume_workflow(
        session: Session,
        workflow_id: int
    ) -> Dict[str, Any]:
        """
        Resume paused workflow.

        Args:
            session: Database session
            workflow_id: Workflow ID

        Returns:
            Updated workflow state
        """
        workflow = session.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        if workflow.status != WorkflowStatus.PAUSED:
            raise ValueError(f"Cannot resume workflow in status {workflow.status}")

        workflow.status = WorkflowStatus.RUNNING
        workflow.metadata["resumed_at"] = datetime.utcnow().isoformat()

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(workflow, "metadata")
        session.commit()

        # Continue execution
        WorkflowEngine._execute_ready_steps(session, workflow)

        return {
            "id": workflow.id,
            "status": workflow.status,
            "message": "Workflow resumed"
        }

    @staticmethod
    def cancel_workflow(
        session: Session,
        workflow_id: int,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel workflow execution.

        Args:
            session: Database session
            workflow_id: Workflow ID
            reason: Optional cancellation reason

        Returns:
            Updated workflow state
        """
        workflow = session.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        if workflow.status in [WorkflowStatus.COMPLETED, WorkflowStatus.CANCELLED]:
            raise ValueError(f"Cannot cancel workflow in status {workflow.status}")

        workflow.status = WorkflowStatus.CANCELLED
        workflow.metadata["cancelled_at"] = datetime.utcnow().isoformat()
        if reason:
            workflow.metadata["cancellation_reason"] = reason

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(workflow, "metadata")
        session.commit()

        return {
            "id": workflow.id,
            "status": workflow.status,
            "message": "Workflow cancelled"
        }

    @staticmethod
    def get_workflow_status(
        session: Session,
        workflow_id: int
    ) -> Dict[str, Any]:
        """
        Get detailed workflow status.

        Args:
            session: Database session
            workflow_id: Workflow ID

        Returns:
            Detailed workflow status with step progress
        """
        workflow = session.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        steps = workflow.metadata.get("steps", [])
        step_states = workflow.metadata.get("step_states", {})

        # Calculate progress
        total_steps = len(steps)
        completed_steps = sum(1 for state in step_states.values() if state.get("status") == StepStatus.COMPLETED)
        failed_steps = sum(1 for state in step_states.values() if state.get("status") == StepStatus.FAILED)
        running_steps = sum(1 for state in step_states.values() if state.get("status") == StepStatus.RUNNING)

        progress_percentage = (completed_steps / total_steps * 100) if total_steps > 0 else 0

        # Get execution timeline
        started_at = workflow.metadata.get("started_at")
        completed_at = workflow.metadata.get("completed_at")
        duration_seconds = None

        if started_at:
            start_time = datetime.fromisoformat(started_at)
            end_time = datetime.fromisoformat(completed_at) if completed_at else datetime.utcnow()
            duration_seconds = (end_time - start_time).total_seconds()

        return {
            "id": workflow.id,
            "name": workflow.name,
            "description": workflow.description,
            "status": workflow.status,
            "progress": {
                "total_steps": total_steps,
                "completed_steps": completed_steps,
                "failed_steps": failed_steps,
                "running_steps": running_steps,
                "percentage": round(progress_percentage, 2)
            },
            "timeline": {
                "created_at": workflow.created_at.isoformat(),
                "started_at": started_at,
                "completed_at": completed_at,
                "duration_seconds": duration_seconds
            },
            "steps": [
                {
                    "step_id": step["step_id"],
                    "name": step["name"],
                    "status": step_states.get(step["step_id"], {}).get("status", StepStatus.PENDING),
                    "task_id": step_states.get(step["step_id"], {}).get("task_id"),
                    "result": step_states.get(step["step_id"], {}).get("result"),
                    "error": step_states.get(step["step_id"], {}).get("error")
                }
                for step in steps
            ]
        }

    @staticmethod
    def list_workflows(
        session: Session,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        List workflows with optional filtering.

        Args:
            session: Database session
            status: Optional status filter
            limit: Maximum workflows to return
            offset: Pagination offset

        Returns:
            Dictionary with workflows and pagination info
        """
        query = session.query(Workflow)

        if status:
            query = query.filter(Workflow.status == status)

        total = query.count()

        workflows = query.order_by(desc(Workflow.created_at)).limit(limit).offset(offset).all()

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "workflows": [
                {
                    "id": w.id,
                    "name": w.name,
                    "description": w.description,
                    "status": w.status,
                    "created_at": w.created_at.isoformat(),
                    "step_count": len(w.metadata.get("steps", []))
                }
                for w in workflows
            ]
        }

    @staticmethod
    def delete_workflow(
        session: Session,
        workflow_id: int
    ) -> Dict[str, Any]:
        """
        Delete a workflow.

        Args:
            session: Database session
            workflow_id: Workflow ID

        Returns:
            Deletion confirmation
        """
        workflow = session.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not workflow:
            raise ValueError(f"Workflow {workflow_id} not found")

        if workflow.status == WorkflowStatus.RUNNING:
            raise ValueError("Cannot delete running workflow. Cancel it first.")

        session.delete(workflow)
        session.commit()

        return {
            "id": workflow_id,
            "message": "Workflow deleted successfully"
        }
