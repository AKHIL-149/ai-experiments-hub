"""
Agent Collaboration API endpoints
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_collaboration import AgentCollaboration, CollaborationPattern, CollaborationRole
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class CreateCollaborationRequest(BaseModel):
    """Request model for creating a collaboration"""
    name: str = Field(..., description="Collaboration name")
    task_id: int = Field(..., description="Task ID")
    agent_ids: List[int] = Field(..., min_items=2, description="List of agent IDs")
    pattern: str = Field(
        default=CollaborationPattern.PARALLEL,
        description="Collaboration pattern (parallel/sequential/hierarchical/peer_to_peer)"
    )
    description: Optional[str] = Field(default=None, description="Optional description")


class AssignRoleRequest(BaseModel):
    """Request model for assigning a role"""
    task_id: int = Field(..., description="Task ID")
    collaboration_id: int = Field(..., description="Collaboration ID")
    agent_id: int = Field(..., description="Agent ID")
    role: str = Field(..., description="Role to assign (leader/contributor/reviewer/coordinator)")


class CreateHandoffRequest(BaseModel):
    """Request model for creating a handoff"""
    task_id: int = Field(..., description="Task ID")
    collaboration_id: int = Field(..., description="Collaboration ID")
    from_agent_id: int = Field(..., description="Source agent ID")
    to_agent_id: int = Field(..., description="Target agent ID")
    handoff_type: str = Field(..., description="Handoff type (work/review/approval)")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Optional context data")


class CompleteHandoffRequest(BaseModel):
    """Request model for completing a handoff"""
    task_id: int = Field(..., description="Task ID")
    collaboration_id: int = Field(..., description="Collaboration ID")
    from_agent_id: int = Field(..., description="Source agent ID")
    to_agent_id: int = Field(..., description="Target agent ID")


class UpdateCollaborationStatusRequest(BaseModel):
    """Request model for updating collaboration status"""
    task_id: int = Field(..., description="Task ID")
    collaboration_id: int = Field(..., description="Collaboration ID")
    status: str = Field(..., description="New status (active/paused/completed/cancelled)")


class FormTeamRequest(BaseModel):
    """Request model for forming a team"""
    task_id: int = Field(..., description="Task ID")
    required_roles: List[str] = Field(..., min_items=1, description="Required agent roles")
    max_agents: int = Field(default=5, ge=2, le=20, description="Maximum team size")


# Endpoints

@router.post("/create")
async def create_collaboration(
    request: CreateCollaborationRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Create a new collaboration session.

    Creates a collaboration between multiple agents working on a task.
    Supports different collaboration patterns:
    - **parallel**: Agents work simultaneously
    - **sequential**: Agents work in sequence
    - **hierarchical**: Leader-worker pattern
    - **peer_to_peer**: Equal collaboration
    """
    try:
        result = AgentCollaboration.create_collaboration(
            session=db,
            name=request.name,
            task_id=request.task_id,
            agent_ids=request.agent_ids,
            pattern=request.pattern,
            description=request.description
        )

        return {
            "success": True,
            "result": result,
            "message": f"Collaboration '{request.name}' created with {len(request.agent_ids)} agents"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create collaboration: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/assign-role")
async def assign_role(
    request: AssignRoleRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Assign a role to an agent in a collaboration.

    Roles define an agent's responsibilities:
    - **leader**: Coordinates and makes decisions
    - **contributor**: Does core work
    - **reviewer**: Reviews outputs
    - **coordinator**: Manages handoffs and communication
    """
    try:
        collaboration = AgentCollaboration.assign_role(
            session=db,
            task_id=request.task_id,
            collaboration_id=request.collaboration_id,
            agent_id=request.agent_id,
            role=request.role
        )

        return {
            "success": True,
            "collaboration": collaboration,
            "message": f"Assigned role '{request.role}' to agent {request.agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to assign role: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/handoff/create")
async def create_handoff(
    request: CreateHandoffRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Create a handoff between agents.

    A handoff transfers work or responsibility from one agent to another.
    Common handoff types:
    - **work**: Transfer task execution
    - **review**: Request review from another agent
    - **approval**: Request approval before proceeding
    """
    try:
        handoff = AgentCollaboration.create_handoff(
            session=db,
            task_id=request.task_id,
            collaboration_id=request.collaboration_id,
            from_agent_id=request.from_agent_id,
            to_agent_id=request.to_agent_id,
            handoff_type=request.handoff_type,
            context=request.context
        )

        return {
            "success": True,
            "handoff": handoff,
            "message": f"Handoff created from agent {request.from_agent_id} to {request.to_agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create handoff: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/handoff/complete")
async def complete_handoff(
    request: CompleteHandoffRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Mark a handoff as completed.

    Called by the receiving agent once they've accepted the handoff
    and are ready to proceed with the work.
    """
    try:
        handoff = AgentCollaboration.complete_handoff(
            session=db,
            task_id=request.task_id,
            collaboration_id=request.collaboration_id,
            from_agent_id=request.from_agent_id,
            to_agent_id=request.to_agent_id
        )

        return {
            "success": True,
            "handoff": handoff,
            "message": f"Handoff completed from agent {request.from_agent_id} to {request.to_agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to complete handoff: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/get/{task_id}/{collaboration_id}")
async def get_collaboration(
    task_id: int,
    collaboration_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get collaboration details.

    Returns full collaboration information including agents,
    roles, handoffs, and current status.
    """
    try:
        collaboration = AgentCollaboration.get_collaboration(
            session=db,
            task_id=task_id,
            collaboration_id=collaboration_id
        )

        return {
            "success": True,
            "collaboration": collaboration,
            "message": f"Collaboration {collaboration_id} for task {task_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get collaboration: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/list")
async def list_collaborations(
    task_id: Optional[int] = Query(None, description="Filter by task ID"),
    agent_id: Optional[int] = Query(None, description="Filter by agent ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    List collaborations with optional filters.

    Filters:
    - task_id: Show only collaborations for a specific task
    - agent_id: Show only collaborations involving a specific agent
    - status: Show only collaborations with a specific status
    """
    try:
        collaborations = AgentCollaboration.list_collaborations(
            session=db,
            task_id=task_id,
            agent_id=agent_id,
            status=status
        )

        return {
            "success": True,
            "total_collaborations": len(collaborations),
            "collaborations": collaborations,
            "message": f"Found {len(collaborations)} collaborations"
        }

    except Exception as e:
        logger.error(f"Failed to list collaborations: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/form-team")
async def form_team(
    request: FormTeamRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Automatically form a team for a task.

    Selects agents with the required roles and checks if all
    roles are covered. Returns team composition and any missing roles.
    """
    try:
        result = AgentCollaboration.form_team(
            session=db,
            task_id=request.task_id,
            required_roles=request.required_roles,
            max_agents=request.max_agents
        )

        return {
            "success": True,
            "team": result,
            "message": (
                f"Team formed with {result['team_size']} agents"
                if result["is_complete"]
                else f"Team incomplete - missing roles: {', '.join(result['missing_roles'])}"
            )
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to form team: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/agent/{agent_id}")
async def get_agent_collaborations(
    agent_id: int,
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get all collaborations for an agent.

    Returns all collaborations where the agent is a participant,
    optionally filtered by collaboration status.
    """
    try:
        collaborations = AgentCollaboration.get_agent_collaborations(
            session=db,
            agent_id=agent_id,
            status=status
        )

        return {
            "success": True,
            "agent_id": agent_id,
            "total_collaborations": len(collaborations),
            "collaborations": collaborations,
            "message": f"Found {len(collaborations)} collaborations for agent {agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get agent collaborations: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/update-status")
async def update_collaboration_status(
    request: UpdateCollaborationStatusRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Update collaboration status.

    Valid statuses:
    - **active**: Collaboration is ongoing
    - **paused**: Temporarily paused
    - **completed**: Successfully completed
    - **cancelled**: Cancelled before completion
    """
    try:
        collaboration = AgentCollaboration.update_collaboration_status(
            session=db,
            task_id=request.task_id,
            collaboration_id=request.collaboration_id,
            status=request.status
        )

        return {
            "success": True,
            "collaboration": collaboration,
            "message": f"Collaboration status updated to {request.status}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update collaboration status: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/metrics/{task_id}/{collaboration_id}")
async def get_collaboration_metrics(
    task_id: int,
    collaboration_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get collaboration performance metrics.

    Provides insights into:
    - Agent participation
    - Handoff success rates
    - Collaboration duration
    - Active agent count
    """
    try:
        metrics = AgentCollaboration.get_collaboration_metrics(
            session=db,
            task_id=task_id,
            collaboration_id=collaboration_id
        )

        return {
            "success": True,
            "metrics": metrics,
            "message": f"Collaboration metrics for {collaboration_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get collaboration metrics: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/handoffs/pending/{agent_id}")
async def get_pending_handoffs(
    agent_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get all pending handoffs for an agent.

    Returns handoffs where the agent is the recipient and
    the handoff hasn't been completed yet.
    """
    try:
        handoffs = AgentCollaboration.get_pending_handoffs(
            session=db,
            agent_id=agent_id
        )

        return {
            "success": True,
            "agent_id": agent_id,
            "total_pending": len(handoffs),
            "handoffs": handoffs,
            "message": f"Found {len(handoffs)} pending handoffs for agent {agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get pending handoffs: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/sync/{task_id}/{collaboration_id}")
async def sync_collaboration_state(
    task_id: int,
    collaboration_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Synchronize collaboration state with agent executions.

    Updates the collaboration's active agent count based on
    current execution status. Called periodically to keep
    collaboration state in sync.
    """
    try:
        collaboration = AgentCollaboration.sync_collaboration_state(
            session=db,
            task_id=task_id,
            collaboration_id=collaboration_id
        )

        return {
            "success": True,
            "collaboration": collaboration,
            "message": f"Collaboration {collaboration_id} state synchronized"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to sync collaboration state: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/patterns")
async def list_collaboration_patterns() -> Dict[str, Any]:
    """
    List all collaboration patterns.

    Returns available patterns for organizing multi-agent work.
    """
    patterns = [
        {
            "pattern": CollaborationPattern.PARALLEL,
            "description": "Agents work simultaneously on different parts",
            "use_case": "Independent subtasks that can run in parallel",
            "example": "Multiple agents analyzing different code modules"
        },
        {
            "pattern": CollaborationPattern.SEQUENTIAL,
            "description": "Agents work in sequence, passing work along",
            "use_case": "Pipeline where output of one agent feeds the next",
            "example": "Research → Code → Review → Test"
        },
        {
            "pattern": CollaborationPattern.HIERARCHICAL,
            "description": "Leader agent coordinates worker agents",
            "use_case": "Complex tasks requiring coordination and synthesis",
            "example": "Lead researcher delegates to specialized researchers"
        },
        {
            "pattern": CollaborationPattern.PEER_TO_PEER,
            "description": "Agents collaborate as equals without hierarchy",
            "use_case": "Brainstorming, design review, consensus building",
            "example": "Multiple reviewers providing feedback on code"
        }
    ]

    return {
        "success": True,
        "total_patterns": len(patterns),
        "patterns": patterns,
        "default_pattern": CollaborationPattern.PARALLEL,
        "message": "List of collaboration patterns"
    }


@router.get("/roles")
async def list_collaboration_roles() -> Dict[str, Any]:
    """
    List all collaboration roles.

    Returns available roles agents can play in a collaboration.
    """
    roles = [
        {
            "role": CollaborationRole.LEADER,
            "description": "Coordinates work, makes decisions, and synthesizes results",
            "responsibilities": ["Task coordination", "Decision making", "Result synthesis"]
        },
        {
            "role": CollaborationRole.CONTRIBUTOR,
            "description": "Performs core work on assigned tasks",
            "responsibilities": ["Execute assigned work", "Provide progress updates", "Deliver results"]
        },
        {
            "role": CollaborationRole.REVIEWER,
            "description": "Reviews outputs from other agents",
            "responsibilities": ["Quality review", "Provide feedback", "Approve/reject work"]
        },
        {
            "role": CollaborationRole.COORDINATOR,
            "description": "Manages handoffs and communication between agents",
            "responsibilities": ["Manage handoffs", "Facilitate communication", "Track progress"]
        }
    ]

    return {
        "success": True,
        "total_roles": len(roles),
        "roles": roles,
        "default_role": CollaborationRole.CONTRIBUTOR,
        "message": "List of collaboration roles"
    }
