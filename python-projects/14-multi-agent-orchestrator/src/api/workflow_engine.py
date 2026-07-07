"""
DAG Workflow Engine API endpoints
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.workflow_engine import WorkflowEngine, WorkflowStatus, StepStatus
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class WorkflowStep(BaseModel):
    """Workflow step definition"""
    step_id: str = Field(..., description="Unique step identifier")
    name: str = Field(..., description="Step name")
    agent_type: str = Field(..., description="Agent type to execute this step")
    task_description: str = Field(..., description="Task description")
    depends_on: List[str] = Field(default=[], description="Step IDs this step depends on")
    timeout_minutes: int = Field(30, ge=1, description="Step timeout in minutes")
    retry_count: int = Field(3, ge=0, description="Number of retry attempts")


class CreateWorkflowRequest(BaseModel):
    """Request model for creating workflow"""
    name: str = Field(..., description="Workflow name")
    description: Optional[str] = Field(None, description="Workflow description")
    steps: List[WorkflowStep] = Field(..., description="Workflow steps")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class UpdateStepStatusRequest(BaseModel):
    """Request model for updating step status"""
    step_id: str = Field(..., description="Step ID")
    status: str = Field(..., description="New step status")
    result: Optional[Any] = Field(None, description="Step result")
    error: Optional[str] = Field(None, description="Error message if failed")


class CancelWorkflowRequest(BaseModel):
    """Request model for cancelling workflow"""
    reason: Optional[str] = Field(None, description="Cancellation reason")


# Endpoints

@router.post("")
async def create_workflow(
    request: CreateWorkflowRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Create a new DAG workflow.

    Defines a workflow with multiple steps that can have dependencies.
    Steps are executed in dependency order with parallel execution where possible.

    Each step must have:
    - Unique step_id
    - Agent type to execute it
    - Task description
    - Optional dependencies (other step_ids)
    - Timeout and retry settings
    """
    try:
        # Convert Pydantic models to dicts
        steps_data = [step.dict() for step in request.steps]

        workflow = WorkflowEngine.create_workflow(
            session=db,
            name=request.name,
            description=request.description,
            steps=steps_data,
            metadata=request.metadata
        )

        return {
            "success": True,
            "workflow": workflow,
            "message": f"Workflow '{request.name}' created successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create workflow: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{workflow_id}/start")
async def start_workflow(
    workflow_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Start workflow execution.

    Begins executing the workflow by:
    1. Initializing step states
    2. Finding steps with no dependencies (ready to run)
    3. Creating tasks for ready steps
    4. Assigning tasks to appropriate agents

    Steps execute in parallel where dependencies allow.
    """
    try:
        result = WorkflowEngine.start_workflow(
            session=db,
            workflow_id=workflow_id
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to start workflow: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{workflow_id}/pause")
async def pause_workflow(
    workflow_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Pause workflow execution.

    Pauses the workflow, preventing new steps from starting.
    Currently running steps will complete.

    Can be resumed later with /resume endpoint.
    """
    try:
        result = WorkflowEngine.pause_workflow(
            session=db,
            workflow_id=workflow_id
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to pause workflow: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{workflow_id}/resume")
async def resume_workflow(
    workflow_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Resume paused workflow.

    Continues workflow execution from where it was paused.
    Executes any steps that are ready to run.
    """
    try:
        result = WorkflowEngine.resume_workflow(
            session=db,
            workflow_id=workflow_id
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to resume workflow: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{workflow_id}/cancel")
async def cancel_workflow(
    workflow_id: int,
    request: CancelWorkflowRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Cancel workflow execution.

    Cancels the workflow permanently. Cannot be resumed.
    Use pause/resume for temporary suspension.
    """
    try:
        result = WorkflowEngine.cancel_workflow(
            session=db,
            workflow_id=workflow_id,
            reason=request.reason
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to cancel workflow: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{workflow_id}/status")
async def get_workflow_status(
    workflow_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get detailed workflow status.

    Returns:
    - Overall workflow status
    - Progress (completed/total steps, percentage)
    - Timeline (created, started, completed times, duration)
    - Individual step statuses with results/errors
    - Task IDs associated with each step
    """
    try:
        status_info = WorkflowEngine.get_workflow_status(
            session=db,
            workflow_id=workflow_id
        )

        return {
            "success": True,
            **status_info
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get workflow status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{workflow_id}/steps/update")
async def update_step_status(
    workflow_id: int,
    request: UpdateStepStatusRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Update workflow step status.

    Called when a step completes, fails, or changes status.

    When a step completes:
    - Triggers execution of dependent steps
    - Checks if workflow is complete

    When a step fails:
    - Retries based on retry_count
    - Fails workflow if max retries exceeded
    """
    try:
        result = WorkflowEngine.update_step_status(
            session=db,
            workflow_id=workflow_id,
            step_id=request.step_id,
            status=request.status,
            result=request.result,
            error=request.error
        )

        return {
            "success": True,
            **result,
            "message": f"Step {request.step_id} status updated to {request.status}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update step status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("")
async def list_workflows(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum workflows to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    List workflows with optional filtering.

    Returns:
    - Workflow summaries
    - Pagination info
    - Total count

    Filter by status:
    - pending
    - running
    - paused
    - completed
    - failed
    - cancelled
    """
    try:
        result = WorkflowEngine.list_workflows(
            session=db,
            status=status,
            limit=limit,
            offset=offset
        )

        return {
            "success": True,
            **result,
            "message": f"Retrieved {len(result['workflows'])} workflows"
        }

    except Exception as e:
        logger.error(f"Failed to list workflows: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Delete a workflow.

    Can only delete workflows that are not running.
    Cancel running workflows before deleting.
    """
    try:
        result = WorkflowEngine.delete_workflow(
            session=db,
            workflow_id=workflow_id
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete workflow: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/statuses")
async def list_workflow_statuses() -> Dict[str, Any]:
    """
    List all workflow status types.

    Returns possible workflow statuses with descriptions.
    """
    statuses = [
        {
            "status": WorkflowStatus.PENDING,
            "description": "Workflow created but not started",
            "color": "gray"
        },
        {
            "status": WorkflowStatus.RUNNING,
            "description": "Workflow is currently executing",
            "color": "blue"
        },
        {
            "status": WorkflowStatus.PAUSED,
            "description": "Workflow execution is paused",
            "color": "yellow"
        },
        {
            "status": WorkflowStatus.COMPLETED,
            "description": "Workflow completed successfully",
            "color": "green"
        },
        {
            "status": WorkflowStatus.FAILED,
            "description": "Workflow failed",
            "color": "red"
        },
        {
            "status": WorkflowStatus.CANCELLED,
            "description": "Workflow was cancelled",
            "color": "orange"
        }
    ]

    return {
        "success": True,
        "total_statuses": len(statuses),
        "statuses": statuses,
        "message": "List of all workflow statuses"
    }


@router.get("/step-statuses")
async def list_step_statuses() -> Dict[str, Any]:
    """
    List all step status types.

    Returns possible step statuses with descriptions.
    """
    statuses = [
        {
            "status": StepStatus.PENDING,
            "description": "Step waiting for dependencies",
            "color": "gray"
        },
        {
            "status": StepStatus.READY,
            "description": "Step ready to execute",
            "color": "cyan"
        },
        {
            "status": StepStatus.RUNNING,
            "description": "Step is currently executing",
            "color": "blue"
        },
        {
            "status": StepStatus.COMPLETED,
            "description": "Step completed successfully",
            "color": "green"
        },
        {
            "status": StepStatus.FAILED,
            "description": "Step failed",
            "color": "red"
        },
        {
            "status": StepStatus.SKIPPED,
            "description": "Step was skipped",
            "color": "yellow"
        }
    ]

    return {
        "success": True,
        "total_statuses": len(statuses),
        "statuses": statuses,
        "message": "List of all step statuses"
    }
