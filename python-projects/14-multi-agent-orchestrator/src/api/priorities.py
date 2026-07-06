"""
Agent Priority API endpoints
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_priority import AgentPriority, PriorityLevel, EscalationPolicy
from src.models.agent_execution import ExecutionStatus
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class SetPriorityRequest(BaseModel):
    """Request model for setting task priority"""
    task_id: int = Field(..., description="Task ID")
    priority: str = Field(..., description="Priority level (critical/high/normal/low)")
    reason: Optional[str] = Field(default=None, description="Reason for priority change")


class SetSLARequest(BaseModel):
    """Request model for setting task SLA"""
    task_id: int = Field(..., description="Task ID")
    sla_minutes: int = Field(..., ge=1, description="SLA in minutes")
    auto_escalate: bool = Field(default=True, description="Auto-escalate if SLA at risk")


class EscalatePrioritiesRequest(BaseModel):
    """Request model for priority escalation"""
    policy: str = Field(
        default=EscalationPolicy.MODERATE,
        description="Escalation policy (aggressive/moderate/conservative)"
    )
    dry_run: bool = Field(
        default=False,
        description="Preview escalations without applying"
    )


class ReorderQueueRequest(BaseModel):
    """Request model for reordering agent queue"""
    agent_id: int = Field(..., description="Agent ID")
    use_dynamic_priority: bool = Field(
        default=True,
        description="Use dynamic priority (age + SLA) vs static"
    )


# Endpoints

@router.post("/set-priority")
async def set_priority(
    request: SetPriorityRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Set or update task priority.

    Changes the priority level of a task and logs the change
    in the task's metadata for audit purposes.
    """
    try:
        result = AgentPriority.set_task_priority(
            session=db,
            task_id=request.task_id,
            priority=request.priority,
            reason=request.reason
        )

        return {
            "success": True,
            "result": result,
            "message": f"Priority set to {request.priority} for task {request.task_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to set priority: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/queue")
async def get_priority_queue(
    agent_id: Optional[int] = Query(None, description="Filter by agent ID"),
    status_filter: Optional[str] = Query(None, description="Filter by execution status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum tasks to return"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get tasks ordered by static priority.

    Returns tasks sorted by priority level (critical > high > normal > low)
    and then by creation time (older first).
    """
    try:
        # Convert status string to enum if provided
        exec_status = None
        if status_filter:
            try:
                exec_status = ExecutionStatus(status_filter)
            except ValueError:
                raise ValueError(f"Invalid status: {status_filter}")

        queue = AgentPriority.get_priority_queue(
            session=db,
            agent_id=agent_id,
            status=exec_status,
            limit=limit
        )

        return {
            "success": True,
            "total_tasks": len(queue),
            "agent_id_filter": agent_id,
            "status_filter": status_filter,
            "queue": queue,
            "message": f"Retrieved {len(queue)} tasks from priority queue"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get priority queue: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/queue/dynamic")
async def get_dynamic_priority_queue(
    agent_id: Optional[int] = Query(None, description="Filter by agent ID"),
    include_sla: bool = Query(True, description="Include SLA calculations"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum tasks to return"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get tasks ordered by dynamic priority.

    Dynamic priority considers:
    - Base priority level (critical/high/normal/low)
    - Task age (older tasks get priority boost)
    - SLA deadlines (tasks near SLA breach get priority boost)
    """
    try:
        queue = AgentPriority.get_priority_queue_dynamic(
            session=db,
            agent_id=agent_id,
            include_sla=include_sla,
            limit=limit
        )

        return {
            "success": True,
            "total_tasks": len(queue),
            "agent_id_filter": agent_id,
            "include_sla": include_sla,
            "queue": queue,
            "message": f"Retrieved {len(queue)} tasks from dynamic priority queue"
        }

    except Exception as e:
        logger.error(f"Failed to get dynamic priority queue: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/escalate")
async def escalate_priorities(
    request: EscalatePrioritiesRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Escalate priorities for aging tasks.

    Automatically increases priority for tasks that have been
    waiting too long based on the selected escalation policy:

    - **aggressive**: Escalate after 30 minutes
    - **moderate**: Escalate low/normal after 2h, high after 1h
    - **conservative**: Escalate low/normal after 6h, high after 3h

    Set dry_run=true to preview changes without applying them.
    """
    try:
        result = AgentPriority.escalate_priorities(
            session=db,
            policy=request.policy,
            dry_run=request.dry_run
        )

        if not request.dry_run:
            db.commit()

        return {
            "success": True,
            "result": result,
            "message": (
                f"Would escalate {result['escalated_count']} tasks"
                if request.dry_run
                else f"Escalated {result['escalated_count']} tasks"
            )
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to escalate priorities: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/statistics")
async def get_priority_statistics(
    time_range_hours: int = Query(24, ge=1, le=720, description="Time range in hours"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get priority statistics and metrics.

    Provides insights into:
    - Task distribution by priority level
    - Average completion times by priority
    - Currently queued tasks by priority
    - SLA breach metrics
    """
    try:
        stats = AgentPriority.get_priority_statistics(
            session=db,
            time_range_hours=time_range_hours
        )

        return {
            "success": True,
            "statistics": stats,
            "message": f"Priority statistics for last {time_range_hours} hours"
        }

    except Exception as e:
        logger.error(f"Failed to get priority statistics: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/sla/set")
async def set_sla(
    request: SetSLARequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Set SLA (Service Level Agreement) for a task.

    Defines a deadline for task completion. The system will:
    - Track time remaining until SLA breach
    - Boost priority for tasks approaching their SLA
    - Report SLA violations
    - Optionally auto-escalate priority as deadline approaches
    """
    try:
        result = AgentPriority.set_task_sla(
            session=db,
            task_id=request.task_id,
            sla_minutes=request.sla_minutes,
            auto_escalate=request.auto_escalate
        )

        return {
            "success": True,
            "sla": result,
            "message": f"SLA set for task {request.task_id}: {request.sla_minutes} minutes"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to set SLA: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/sla/violations")
async def check_sla_violations(
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Check for SLA violations and at-risk tasks.

    Returns:
    - **Violations**: Tasks that have exceeded their SLA
    - **At Risk**: Tasks with less than 25% of SLA time remaining
    """
    try:
        violations = AgentPriority.check_sla_violations(session=db)

        return {
            "success": True,
            "violations": violations,
            "message": f"Found {violations['violations_count']} violations, {violations['at_risk_count']} at risk"
        }

    except Exception as e:
        logger.error(f"Failed to check SLA violations: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/reorder-queue")
async def reorder_queue(
    request: ReorderQueueRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Reorder an agent's task queue based on priority.

    Reorders the agent's queue using either:
    - **Static priority**: Based only on priority level
    - **Dynamic priority**: Considers age, SLA, and base priority

    Returns the reordered queue.
    """
    try:
        result = AgentPriority.reorder_agent_queue(
            session=db,
            agent_id=request.agent_id,
            use_dynamic_priority=request.use_dynamic_priority
        )

        return {
            "success": True,
            "result": result,
            "message": f"Reordered queue for agent {request.agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to reorder queue: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/levels")
async def list_priority_levels() -> Dict[str, Any]:
    """
    List all priority levels with their weights.

    Priority levels are used to determine task urgency and
    execution order. Higher weights indicate higher priority.
    """
    levels = [
        {
            "level": PriorityLevel.CRITICAL,
            "weight": PriorityLevel.get_weight(PriorityLevel.CRITICAL),
            "description": "Urgent, system-critical tasks requiring immediate attention"
        },
        {
            "level": PriorityLevel.HIGH,
            "weight": PriorityLevel.get_weight(PriorityLevel.HIGH),
            "description": "Important tasks that should be completed soon"
        },
        {
            "level": PriorityLevel.NORMAL,
            "weight": PriorityLevel.get_weight(PriorityLevel.NORMAL),
            "description": "Standard tasks with normal urgency (default)"
        },
        {
            "level": PriorityLevel.LOW,
            "weight": PriorityLevel.get_weight(PriorityLevel.LOW),
            "description": "Low-urgency tasks that can wait if needed"
        }
    ]

    return {
        "success": True,
        "total_levels": len(levels),
        "levels": levels,
        "default_level": PriorityLevel.NORMAL,
        "message": "List of all priority levels"
    }


@router.get("/policies")
async def list_escalation_policies() -> Dict[str, Any]:
    """
    List all escalation policies with their thresholds.

    Escalation policies determine how quickly task priorities
    are automatically increased as tasks age.
    """
    policies = [
        {
            "policy": EscalationPolicy.AGGRESSIVE,
            "description": "Fast escalation for time-sensitive environments",
            "thresholds": {
                "low_to_normal": "30 minutes",
                "normal_to_high": "30 minutes",
                "high_to_critical": "30 minutes"
            },
            "use_case": "Production incidents, real-time systems"
        },
        {
            "policy": EscalationPolicy.MODERATE,
            "description": "Balanced escalation for typical workloads",
            "thresholds": {
                "low_to_normal": "2 hours",
                "normal_to_high": "2 hours",
                "high_to_critical": "1 hour"
            },
            "use_case": "Standard business operations, mixed workloads"
        },
        {
            "policy": EscalationPolicy.CONSERVATIVE,
            "description": "Slow escalation for long-running tasks",
            "thresholds": {
                "low_to_normal": "6 hours",
                "normal_to_high": "6 hours",
                "high_to_critical": "3 hours"
            },
            "use_case": "Research tasks, batch processing"
        },
        {
            "policy": EscalationPolicy.NONE,
            "description": "No automatic escalation",
            "thresholds": {},
            "use_case": "When manual priority management is preferred"
        }
    ]

    return {
        "success": True,
        "total_policies": len(policies),
        "policies": policies,
        "default_policy": EscalationPolicy.MODERATE,
        "message": "List of all escalation policies"
    }


@router.get("/task/{task_id}/priority-history")
async def get_priority_history(
    task_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get priority change history for a task.

    Returns a complete audit trail of all priority changes
    including timestamps and reasons.
    """
    try:
        from src.models.task import Task

        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task {task_id} not found"
            )

        history = []
        if task.metadata and "priority_history" in task.metadata:
            history = task.metadata["priority_history"]

        return {
            "success": True,
            "task_id": task_id,
            "current_priority": task.priority.value,
            "history_count": len(history),
            "history": history,
            "message": f"Priority history for task {task_id}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get priority history: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
