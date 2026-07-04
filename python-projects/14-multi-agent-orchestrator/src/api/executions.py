"""
Agent Execution Management API endpoints
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.execution_manager import ExecutionManager
from src.models.agent_execution import ExecutionStatus
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class ExecutionEnqueueRequest(BaseModel):
    """Request model for enqueuing a task"""
    agent_id: int
    task_id: int
    priority: int = 0
    scheduled_at: Optional[str] = None  # ISO format datetime
    context: Optional[Dict[str, Any]] = None


class ExecutionCompleteRequest(BaseModel):
    """Request model for completing an execution"""
    execution_id: int
    output_data: Optional[Dict[str, Any]] = None
    metrics: Optional[Dict[str, Any]] = None


class ExecutionFailRequest(BaseModel):
    """Request model for failing an execution"""
    execution_id: int
    error: str
    error_details: Optional[Dict[str, Any]] = None
    retry: bool = True


class ExecutionCancelRequest(BaseModel):
    """Request model for cancelling an execution"""
    execution_id: int
    reason: Optional[str] = None


# Endpoints

@router.post("/enqueue")
async def enqueue_task(
    request: ExecutionEnqueueRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Enqueue a task for an agent"""
    try:
        # Parse scheduled_at if provided
        scheduled_at = None
        if request.scheduled_at:
            scheduled_at = datetime.fromisoformat(request.scheduled_at.replace('Z', '+00:00'))

        execution = ExecutionManager.enqueue_task(
            session=db,
            agent_id=request.agent_id,
            task_id=request.task_id,
            priority=request.priority,
            scheduled_at=scheduled_at,
            context=request.context
        )

        db.commit()

        return {
            "id": execution.id,
            "agent_id": execution.agent_id,
            "task_id": execution.task_id,
            "status": execution.status.value,
            "priority": execution.priority,
            "scheduled_at": execution.scheduled_at.isoformat() if execution.scheduled_at else None,
            "created_at": execution.created_at.isoformat() if execution.created_at else None
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to enqueue task: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/next/{agent_id}")
async def get_next_task(
    agent_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get the next task from an agent's queue"""
    try:
        execution = ExecutionManager.get_next_task(
            session=db,
            agent_id=agent_id
        )

        if not execution:
            return {"execution": None, "message": "No tasks in queue"}

        return {
            "execution": {
                "id": execution.id,
                "agent_id": execution.agent_id,
                "task_id": execution.task_id,
                "status": execution.status.value,
                "priority": execution.priority,
                "scheduled_at": execution.scheduled_at.isoformat() if execution.scheduled_at else None,
                "created_at": execution.created_at.isoformat() if execution.created_at else None,
                "task": {
                    "id": execution.task.id,
                    "title": execution.task.title,
                    "description": execution.task.description
                }
            }
        }

    except Exception as e:
        logger.error(f"Failed to get next task: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/start/{execution_id}")
async def start_execution(
    execution_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Start an execution"""
    try:
        execution = ExecutionManager.start_execution(
            session=db,
            execution_id=execution_id
        )

        db.commit()

        return {
            "id": execution.id,
            "agent_id": execution.agent_id,
            "task_id": execution.task_id,
            "status": execution.status.value,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "attempts": execution.attempts
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to start execution: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/complete")
async def complete_execution(
    request: ExecutionCompleteRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Mark an execution as completed"""
    try:
        execution = ExecutionManager.complete_execution(
            session=db,
            execution_id=request.execution_id,
            output_data=request.output_data,
            metrics=request.metrics
        )

        db.commit()

        return {
            "id": execution.id,
            "status": execution.status.value,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "metrics": execution.metrics,
            "output_data": execution.output_data
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to complete execution: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/fail")
async def fail_execution(
    request: ExecutionFailRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Mark an execution as failed"""
    try:
        execution, retry_execution = ExecutionManager.fail_execution(
            session=db,
            execution_id=request.execution_id,
            error=request.error,
            error_details=request.error_details,
            retry=request.retry
        )

        db.commit()

        result = {
            "id": execution.id,
            "status": execution.status.value,
            "error_message": execution.error_message,
            "error_details": execution.error_details,
            "retry_created": retry_execution is not None
        }

        if retry_execution:
            result["retry_execution"] = {
                "id": retry_execution.id,
                "status": retry_execution.status.value,
                "scheduled_at": retry_execution.scheduled_at.isoformat() if retry_execution.scheduled_at else None
            }

        return result

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to fail execution: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/pause/{execution_id}")
async def pause_execution(
    execution_id: int,
    reason: Optional[str] = None,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Pause a running execution"""
    try:
        execution = ExecutionManager.pause_execution(
            session=db,
            execution_id=execution_id,
            reason=reason
        )

        db.commit()

        return {
            "id": execution.id,
            "status": execution.status.value,
            "reason": execution.error_message
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to pause execution: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/resume/{execution_id}")
async def resume_execution(
    execution_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Resume a paused execution"""
    try:
        execution = ExecutionManager.resume_execution(
            session=db,
            execution_id=execution_id
        )

        db.commit()

        return {
            "id": execution.id,
            "status": execution.status.value
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to resume execution: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/cancel")
async def cancel_execution(
    request: ExecutionCancelRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Cancel an execution"""
    try:
        execution = ExecutionManager.cancel_execution(
            session=db,
            execution_id=request.execution_id,
            reason=request.reason
        )

        db.commit()

        return {
            "id": execution.id,
            "status": execution.status.value,
            "reason": execution.error_message
        }

    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to cancel execution: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/queue/{agent_id}")
async def get_agent_queue(
    agent_id: int,
    include_completed: bool = Query(False),
    limit: int = Query(100, le=1000),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get an agent's task queue"""
    try:
        executions = ExecutionManager.get_agent_queue(
            session=db,
            agent_id=agent_id,
            include_completed=include_completed,
            limit=limit
        )

        return {
            "agent_id": agent_id,
            "count": len(executions),
            "executions": [
                {
                    "id": e.id,
                    "task_id": e.task_id,
                    "status": e.status.value,
                    "priority": e.priority,
                    "attempts": e.attempts,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                    "started_at": e.started_at.isoformat() if e.started_at else None,
                    "task_title": e.task.title if e.task else None
                }
                for e in executions
            ]
        }

    except Exception as e:
        logger.error(f"Failed to get agent queue: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/metrics")
async def get_execution_metrics(
    agent_id: Optional[int] = Query(None),
    task_id: Optional[int] = Query(None),
    time_range_hours: int = Query(24, le=720),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get execution metrics"""
    try:
        metrics = ExecutionManager.get_execution_metrics(
            session=db,
            agent_id=agent_id,
            task_id=task_id,
            time_range_hours=time_range_hours
        )

        return metrics

    except Exception as e:
        logger.error(f"Failed to get execution metrics: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/cleanup")
async def cleanup_old_executions(
    days_old: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db_session)
) -> Dict[str, int]:
    """Clean up old completed/failed executions"""
    try:
        count = ExecutionManager.cleanup_old_executions(
            session=db,
            days_old=days_old
        )

        db.commit()

        return {"deleted": count}

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to cleanup executions: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/stuck")
async def get_stuck_executions(
    timeout_hours: int = Query(1, ge=1, le=24),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Find stuck executions"""
    try:
        executions = ExecutionManager.get_stuck_executions(
            session=db,
            timeout_hours=timeout_hours
        )

        return {
            "count": len(executions),
            "executions": [
                {
                    "id": e.id,
                    "agent_id": e.agent_id,
                    "task_id": e.task_id,
                    "started_at": e.started_at.isoformat() if e.started_at else None,
                    "attempts": e.attempts
                }
                for e in executions
            ]
        }

    except Exception as e:
        logger.error(f"Failed to get stuck executions: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/recover-stuck")
async def recover_stuck_executions(
    timeout_hours: int = Query(1, ge=1, le=24),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Recover stuck executions"""
    try:
        recovered = ExecutionManager.recover_stuck_executions(
            session=db,
            timeout_hours=timeout_hours
        )

        db.commit()

        return {
            "recovered_count": len(recovered),
            "retry_executions": [
                {
                    "id": e.id,
                    "agent_id": e.agent_id,
                    "task_id": e.task_id,
                    "status": e.status.value
                }
                for e in recovered
            ]
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to recover stuck executions: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{execution_id}")
async def get_execution(
    execution_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get execution details"""
    try:
        from src.models.agent_execution import AgentExecution

        execution = db.query(AgentExecution).filter(
            AgentExecution.id == execution_id
        ).first()

        if not execution:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

        return {
            "id": execution.id,
            "agent_id": execution.agent_id,
            "task_id": execution.task_id,
            "status": execution.status.value,
            "priority": execution.priority,
            "attempts": execution.attempts,
            "input_data": execution.input_data,
            "output_data": execution.output_data,
            "metrics": execution.metrics,
            "error_message": execution.error_message,
            "error_details": execution.error_details,
            "created_at": execution.created_at.isoformat() if execution.created_at else None,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "scheduled_at": execution.scheduled_at.isoformat() if execution.scheduled_at else None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get execution: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
