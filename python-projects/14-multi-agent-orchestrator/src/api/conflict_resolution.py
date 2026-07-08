"""
Conflict Resolution API

REST API endpoints for detecting and resolving agent conflicts.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.conflict_resolution import (
    ConflictResolution,
    ConflictType,
    ConflictSeverity,
    ConflictStatus,
    ResolutionStrategy
)


router = APIRouter()


# Request/Response Models
class DetectConflictRequest(BaseModel):
    conflict_type: str = Field(..., description="Type of conflict")
    involved_agents: List[int] = Field(..., description="Agent IDs involved")
    resource_id: Optional[str] = Field(None, description="Resource identifier")
    task_id: Optional[int] = Field(None, description="Task ID")
    description: str = Field("", description="Conflict description")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class ResolveConflictRequest(BaseModel):
    strategy: str = Field(ResolutionStrategy.AUTOMATIC, description="Resolution strategy")
    manual_decision: Optional[dict] = Field(None, description="Manual decision data")


class EscalateConflictRequest(BaseModel):
    reason: str = Field("", description="Escalation reason")


class BatchResolveRequest(BaseModel):
    conflict_ids: List[int] = Field(..., description="Conflict IDs to resolve")
    strategy: str = Field(ResolutionStrategy.AUTOMATIC, description="Resolution strategy")


class PreviewResolutionRequest(BaseModel):
    strategy: str = Field(..., description="Strategy to preview")


@router.post("/detect")
def detect_conflict(
    request: DetectConflictRequest,
    session: Session = Depends(get_db_session)
):
    """
    Detect and register a new conflict.

    Detects conflicts between agents including resource conflicts,
    decision conflicts, priority conflicts, and assignment conflicts.
    """
    try:
        conflict = ConflictResolution.detect_conflict(
            session=session,
            conflict_type=request.conflict_type,
            involved_agents=request.involved_agents,
            resource_id=request.resource_id,
            task_id=request.task_id,
            description=request.description,
            metadata=request.metadata
        )

        return {
            "success": True,
            "conflict": conflict,
            "message": f"Conflict detected with {conflict['severity']} severity"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{conflict_id}/resolve")
def resolve_conflict(
    conflict_id: int,
    request: ResolveConflictRequest,
    session: Session = Depends(get_db_session)
):
    """
    Resolve a detected conflict using a specified strategy.

    Strategies include:
    - priority_based: Use agent/task priority
    - voting: Democratic vote
    - arbitration: Third-party arbitrator
    - fcfs: First-come-first-served
    - round_robin: Fair distribution
    - automatic: System decides
    - manual: Human intervention
    """
    try:
        result = ConflictResolution.resolve_conflict(
            session=session,
            conflict_id=conflict_id,
            strategy=request.strategy,
            manual_decision=request.manual_decision
        )

        return {
            "success": True,
            "resolution": result,
            "message": f"Conflict resolved using {request.strategy} strategy"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{conflict_id}")
def get_conflict(
    conflict_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get details of a specific conflict.

    Returns conflict information including involved agents,
    status, severity, and resolution outcome if resolved.
    """
    try:
        conflict = ConflictResolution.get_conflict(
            session=session,
            conflict_id=conflict_id
        )

        return {
            "success": True,
            "conflict": conflict
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/")
def list_conflicts(
    status: Optional[str] = None,
    conflict_type: Optional[str] = None,
    severity: Optional[str] = None,
    agent_id: Optional[int] = None,
    limit: int = 100,
    session: Session = Depends(get_db_session)
):
    """
    List conflicts with optional filtering.

    Filter by status, conflict type, severity, or agent involvement.
    """
    try:
        result = ConflictResolution.list_conflicts(
            session=session,
            status=status,
            conflict_type=conflict_type,
            severity=severity,
            agent_id=agent_id,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}")
def get_agent_conflicts(
    agent_id: int,
    status: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get all conflicts involving a specific agent.

    Returns conflicts where the agent is involved, optionally filtered by status.
    """
    try:
        result = ConflictResolution.get_agent_conflicts(
            session=session,
            agent_id=agent_id,
            status=status
        )

        return {
            "success": True,
            "agent_id": agent_id,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{conflict_id}/escalate")
def escalate_conflict(
    conflict_id: int,
    request: EscalateConflictRequest,
    session: Session = Depends(get_db_session)
):
    """
    Escalate a conflict for manual intervention.

    Used when automatic resolution fails or when the conflict
    requires human judgment.
    """
    try:
        conflict = ConflictResolution.escalate_conflict(
            session=session,
            conflict_id=conflict_id,
            reason=request.reason
        )

        return {
            "success": True,
            "conflict": conflict,
            "message": "Conflict escalated for manual intervention"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get conflict resolution statistics.

    Returns statistics including total conflicts, resolution rates,
    average resolution time, and strategy effectiveness.
    """
    try:
        stats = ConflictResolution.get_conflict_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{conflict_id}/suggest-strategy")
def suggest_resolution_strategy(
    conflict_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get suggested resolution strategy for a conflict.

    Analyzes the conflict and recommends the best resolution strategy
    based on conflict type, severity, and number of involved agents.
    """
    try:
        suggestion = ConflictResolution.suggest_resolution_strategy(
            session=session,
            conflict_id=conflict_id
        )

        return {
            "success": True,
            **suggestion
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-resolve")
def batch_resolve_conflicts(
    request: BatchResolveRequest,
    session: Session = Depends(get_db_session)
):
    """
    Resolve multiple conflicts in batch.

    Applies the same resolution strategy to multiple conflicts
    for efficient bulk resolution.
    """
    try:
        result = ConflictResolution.batch_resolve_conflicts(
            session=session,
            conflict_ids=request.conflict_ids,
            strategy=request.strategy
        )

        return {
            "success": True,
            **result,
            "message": f"Resolved {result['successful']}/{result['total']} conflicts"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{conflict_id}/preview")
def preview_resolution(
    conflict_id: int,
    request: PreviewResolutionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Preview resolution outcome without applying it.

    Shows what would happen if a specific strategy is applied
    without actually resolving the conflict.
    """
    try:
        preview = ConflictResolution.preview_resolution(
            session=session,
            conflict_id=conflict_id,
            strategy=request.strategy
        )

        return {
            "success": True,
            **preview
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/types")
def list_conflict_types():
    """
    List all available conflict types.

    Returns all conflict types that can be detected and resolved.
    """
    return {
        "success": True,
        "conflict_types": [
            {"type": ConflictType.RESOURCE, "description": "Multiple agents need same resource"},
            {"type": ConflictType.DECISION, "description": "Agents disagree on a decision"},
            {"type": ConflictType.PRIORITY, "description": "Task priority conflicts"},
            {"type": ConflictType.ASSIGNMENT, "description": "Multiple agents assigned same task"},
            {"type": ConflictType.STATE, "description": "Inconsistent state between agents"},
            {"type": ConflictType.TIMING, "description": "Scheduling/timing conflicts"}
        ]
    }


@router.get("/strategies")
def list_resolution_strategies():
    """
    List all available resolution strategies.

    Returns all strategies that can be used to resolve conflicts.
    """
    return {
        "success": True,
        "strategies": [
            {"strategy": ResolutionStrategy.PRIORITY_BASED, "description": "Use agent/task priority"},
            {"strategy": ResolutionStrategy.VOTING, "description": "Democratic vote"},
            {"strategy": ResolutionStrategy.ARBITRATION, "description": "Third-party arbitrator"},
            {"strategy": ResolutionStrategy.FIRST_COME_FIRST_SERVED, "description": "Chronological order"},
            {"strategy": ResolutionStrategy.ROUND_ROBIN, "description": "Fair distribution"},
            {"strategy": ResolutionStrategy.AUTOMATIC, "description": "System decides"},
            {"strategy": ResolutionStrategy.MANUAL, "description": "Human intervention"}
        ]
    }


@router.get("/severities")
def list_severity_levels():
    """
    List all severity levels.

    Returns all possible conflict severity levels.
    """
    return {
        "success": True,
        "severities": [
            {"severity": ConflictSeverity.LOW, "description": "Minor conflict, low impact"},
            {"severity": ConflictSeverity.MEDIUM, "description": "Moderate conflict, requires attention"},
            {"severity": ConflictSeverity.HIGH, "description": "Significant conflict, priority resolution"},
            {"severity": ConflictSeverity.CRITICAL, "description": "Critical conflict, immediate action required"}
        ]
    }
