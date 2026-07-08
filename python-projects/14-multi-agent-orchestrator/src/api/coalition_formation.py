"""
Coalition Formation API

REST API endpoints for agent coalition formation and management.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.coalition_formation import (
    CoalitionFormation,
    CoalitionStatus,
    MemberRole,
    FormationStrategy
)


router = APIRouter()


# Request/Response Models
class CreateCoalitionRequest(BaseModel):
    name: str = Field(..., description="Coalition name")
    goal: str = Field(..., description="Coalition goal/objective")
    required_capabilities: List[str] = Field(..., description="Required capabilities")
    leader_agent_id: Optional[int] = Field(None, description="Leader agent ID")
    initial_members: Optional[List[int]] = Field(None, description="Initial member IDs")
    max_members: int = Field(10, description="Maximum coalition size")
    duration_hours: Optional[int] = Field(None, description="Coalition duration in hours")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class AddMemberRequest(BaseModel):
    agent_id: int = Field(..., description="Agent ID to add")
    role: str = Field(MemberRole.CONTRIBUTOR, description="Member role")


class RemoveMemberRequest(BaseModel):
    agent_id: int = Field(..., description="Agent ID to remove")
    reason: str = Field("", description="Removal reason")


class AssignTaskRequest(BaseModel):
    task_id: int = Field(..., description="Task ID to assign")


class PoolResourceRequest(BaseModel):
    agent_id: int = Field(..., description="Agent contributing resource")
    resource_type: str = Field(..., description="Type of resource")
    amount: float = Field(..., description="Amount to contribute")


class UpdateContributionRequest(BaseModel):
    agent_id: int = Field(..., description="Agent ID")
    score_delta: float = Field(..., description="Score change")


class RecordAchievementRequest(BaseModel):
    title: str = Field(..., description="Achievement title")
    description: str = Field(..., description="Achievement description")
    value: float = Field(1.0, description="Achievement value/importance")


class DissolveCoalitionRequest(BaseModel):
    reason: str = Field("", description="Dissolution reason")


class CompleteCoalitionRequest(BaseModel):
    outcome: str = Field("", description="Completion outcome")


class SuggestCoalitionRequest(BaseModel):
    task_id: int = Field(..., description="Task ID")
    strategy: str = Field(FormationStrategy.CAPABILITY_BASED, description="Formation strategy")
    max_members: int = Field(5, description="Maximum coalition size")


@router.post("/coalitions")
def create_coalition(
    request: CreateCoalitionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a new coalition.

    Creates a temporary team of agents to collaborate on complex tasks.
    Supports setting goals, required capabilities, and initial members.
    """
    try:
        coalition = CoalitionFormation.create_coalition(
            session=session,
            name=request.name,
            goal=request.goal,
            required_capabilities=request.required_capabilities,
            leader_agent_id=request.leader_agent_id,
            initial_members=request.initial_members,
            max_members=request.max_members,
            duration_hours=request.duration_hours,
            metadata=request.metadata
        )

        return {
            "success": True,
            "coalition": coalition,
            "message": f"Coalition created with {len(coalition['members'])} members"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/coalitions/{coalition_id}/members")
def add_member(
    coalition_id: int,
    request: AddMemberRequest,
    session: Session = Depends(get_db_session)
):
    """
    Add a member to coalition.

    Adds an agent to an existing coalition with a specified role.
    Coalition must be in forming or active status.
    """
    try:
        coalition = CoalitionFormation.add_member(
            session=session,
            coalition_id=coalition_id,
            agent_id=request.agent_id,
            role=request.role
        )

        return {
            "success": True,
            "coalition": coalition,
            "message": f"Agent {request.agent_id} added as {request.role}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/coalitions/{coalition_id}/members")
def remove_member(
    coalition_id: int,
    request: RemoveMemberRequest,
    session: Session = Depends(get_db_session)
):
    """
    Remove a member from coalition.

    Removes an agent from the coalition. If the leader leaves,
    leadership is automatically reassigned to another member.
    """
    try:
        coalition = CoalitionFormation.remove_member(
            session=session,
            coalition_id=coalition_id,
            agent_id=request.agent_id,
            reason=request.reason
        )

        return {
            "success": True,
            "coalition": coalition,
            "message": f"Agent {request.agent_id} removed from coalition"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/coalitions/{coalition_id}/tasks")
def assign_task(
    coalition_id: int,
    request: AssignTaskRequest,
    session: Session = Depends(get_db_session)
):
    """
    Assign a task to coalition.

    Assigns a task to the coalition for collaborative completion.
    Coalition must be in active status.
    """
    try:
        coalition = CoalitionFormation.assign_task(
            session=session,
            coalition_id=coalition_id,
            task_id=request.task_id
        )

        return {
            "success": True,
            "coalition": coalition,
            "message": f"Task {request.task_id} assigned to coalition"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/coalitions/{coalition_id}/resources")
def pool_resource(
    coalition_id: int,
    request: PoolResourceRequest,
    session: Session = Depends(get_db_session)
):
    """
    Pool a resource to coalition.

    Allows coalition members to contribute resources to a shared pool.
    Tracks individual contributions for transparency.
    """
    try:
        coalition = CoalitionFormation.pool_resource(
            session=session,
            coalition_id=coalition_id,
            agent_id=request.agent_id,
            resource_type=request.resource_type,
            amount=request.amount
        )

        return {
            "success": True,
            "coalition": coalition,
            "message": f"Resource pooled: {request.amount} {request.resource_type}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/coalitions/{coalition_id}/contributions")
def update_contribution(
    coalition_id: int,
    request: UpdateContributionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update agent contribution score.

    Updates an agent's contribution score in the coalition.
    Positive values reward contributions, negative values penalize.
    """
    try:
        coalition = CoalitionFormation.update_contribution_score(
            session=session,
            coalition_id=coalition_id,
            agent_id=request.agent_id,
            score_delta=request.score_delta
        )

        return {
            "success": True,
            "coalition": coalition,
            "message": "Contribution score updated"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/coalitions/{coalition_id}/achievements")
def record_achievement(
    coalition_id: int,
    request: RecordAchievementRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record a coalition achievement.

    Records a significant accomplishment or milestone reached
    by the coalition.
    """
    try:
        coalition = CoalitionFormation.record_achievement(
            session=session,
            coalition_id=coalition_id,
            title=request.title,
            description=request.description,
            value=request.value
        )

        return {
            "success": True,
            "coalition": coalition,
            "message": f"Achievement recorded: {request.title}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/coalitions/{coalition_id}/dissolve")
def dissolve_coalition(
    coalition_id: int,
    request: DissolveCoalitionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Dissolve a coalition.

    Permanently dissolves the coalition, marking all members
    as inactive. Use for premature termination.
    """
    try:
        coalition = CoalitionFormation.dissolve_coalition(
            session=session,
            coalition_id=coalition_id,
            reason=request.reason
        )

        return {
            "success": True,
            "coalition": coalition,
            "message": "Coalition dissolved"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/coalitions/{coalition_id}/complete")
def complete_coalition(
    coalition_id: int,
    request: CompleteCoalitionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Mark coalition as completed.

    Marks the coalition as successfully completed after
    achieving its goal. Use for normal termination.
    """
    try:
        coalition = CoalitionFormation.complete_coalition(
            session=session,
            coalition_id=coalition_id,
            outcome=request.outcome
        )

        return {
            "success": True,
            "coalition": coalition,
            "message": "Coalition completed successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/coalitions/{coalition_id}")
def get_coalition(
    coalition_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get coalition details.

    Returns complete coalition information including members,
    tasks, resources, and achievements.
    """
    try:
        coalition = CoalitionFormation.get_coalition(
            session=session,
            coalition_id=coalition_id
        )

        return {
            "success": True,
            "coalition": coalition
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/coalitions")
def list_coalitions(
    status: Optional[str] = None,
    agent_id: Optional[int] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    List coalitions with optional filtering.

    Filter by status or agent membership. Returns coalitions
    matching the specified criteria.
    """
    try:
        result = CoalitionFormation.list_coalitions(
            session=session,
            status=status,
            agent_id=agent_id,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/coalitions/suggest")
def suggest_coalition(
    request: SuggestCoalitionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Suggest optimal coalition for a task.

    Uses AI to suggest the best team composition for a task
    based on capabilities, workload, or hybrid strategy.
    """
    try:
        suggestion = CoalitionFormation.suggest_coalition(
            session=session,
            task_id=request.task_id,
            strategy=request.strategy,
            max_members=request.max_members
        )

        return {
            "success": True,
            **suggestion
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get coalition statistics.

    Returns statistics including total coalitions, average size,
    total tasks assigned, and breakdown by status.
    """
    try:
        stats = CoalitionFormation.get_coalition_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statuses")
def list_statuses():
    """
    List all coalition statuses.

    Returns all possible statuses a coalition can have.
    """
    return {
        "success": True,
        "statuses": [
            {"status": CoalitionStatus.FORMING, "description": "Coalition being assembled"},
            {"status": CoalitionStatus.ACTIVE, "description": "Coalition actively working"},
            {"status": CoalitionStatus.COMPLETED, "description": "Coalition successfully completed goal"},
            {"status": CoalitionStatus.DISSOLVED, "description": "Coalition dissolved prematurely"}
        ]
    }


@router.get("/roles")
def list_roles():
    """
    List all member roles.

    Returns all possible roles a member can have in a coalition.
    """
    return {
        "success": True,
        "roles": [
            {"role": MemberRole.LEADER, "description": "Coalition leader, makes final decisions"},
            {"role": MemberRole.COORDINATOR, "description": "Coordinates activities and communication"},
            {"role": MemberRole.SPECIALIST, "description": "Domain expert with specific skills"},
            {"role": MemberRole.CONTRIBUTOR, "description": "General contributor to coalition work"},
            {"role": MemberRole.ADVISOR, "description": "Provides guidance and advice"}
        ]
    }


@router.get("/strategies")
def list_strategies():
    """
    List all formation strategies.

    Returns all available strategies for suggesting coalitions.
    """
    return {
        "success": True,
        "strategies": [
            {
                "strategy": FormationStrategy.CAPABILITY_BASED,
                "description": "Form based on required capabilities"
            },
            {
                "strategy": FormationStrategy.REPUTATION_BASED,
                "description": "Form based on agent reputation scores"
            },
            {
                "strategy": FormationStrategy.WORKLOAD_BASED,
                "description": "Form based on current workload availability"
            },
            {
                "strategy": FormationStrategy.PROXIMITY_BASED,
                "description": "Form based on agent similarity/compatibility"
            },
            {
                "strategy": FormationStrategy.HYBRID,
                "description": "Combination of multiple factors"
            }
        ]
    }
