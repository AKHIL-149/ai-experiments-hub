"""
Agent Role Management API

REST API endpoints for managing agent roles, assignments, and hierarchies.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_role import (
    AgentRole,
    RoleType,
    RoleLevel,
    AssignmentStatus
)


router = APIRouter()


# Request/Response Models
class DefineRoleRequest(BaseModel):
    role_type: str = Field(..., description="Type of role")
    role_name: str = Field(..., description="Name of role")
    role_level: str = Field(..., description="Hierarchy level")
    description: str = Field(..., description="Role description")
    responsibilities: List[str] = Field(..., description="List of responsibilities")
    required_capabilities: List[str] = Field(..., description="Required capabilities")
    optional_capabilities: Optional[List[str]] = Field(None, description="Optional capabilities")
    min_experience_hours: float = Field(0, description="Minimum experience required")
    permissions: Optional[List[str]] = Field(None, description="Role permissions")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class AssignRoleRequest(BaseModel):
    role_id: str = Field(..., description="Role ID")
    assigned_by: Optional[int] = Field(None, description="Agent who assigned")
    start_date: Optional[str] = Field(None, description="Start date")
    end_date: Optional[str] = Field(None, description="End date")
    assignment_reason: str = Field("", description="Reason for assignment")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class RevokeRoleRequest(BaseModel):
    revoked_by: Optional[int] = Field(None, description="Agent who revoked")
    revocation_reason: str = Field("", description="Reason for revocation")


class UpdateAssignmentRequest(BaseModel):
    status: Optional[str] = Field(None, description="New status")
    end_date: Optional[str] = Field(None, description="New end date")
    metadata: Optional[dict] = Field(None, description="Updated metadata")


class RecordPerformanceRequest(BaseModel):
    task_id: int = Field(..., description="Task ID")
    performance_score: float = Field(..., description="Performance score (0-1)")
    quality_score: float = Field(..., description="Quality score (0-1)")
    completion_time: float = Field(..., description="Time taken")
    notes: str = Field("", description="Additional notes")


class PromoteAgentRequest(BaseModel):
    current_assignment_id: str = Field(..., description="Current assignment ID")
    new_role_level: str = Field(..., description="New role level")
    promoted_by: Optional[int] = Field(None, description="Agent who promoted")
    promotion_reason: str = Field("", description="Reason for promotion")


class SuggestRoleRequest(BaseModel):
    task_requirements: dict = Field(..., description="Task requirements")
    required_level: Optional[str] = Field(None, description="Minimum role level")


@router.post("/roles")
def define_role(
    request: DefineRoleRequest,
    session: Session = Depends(get_db_session)
):
    """
    Define a new role.

    Creates a role definition with responsibilities, capabilities,
    level, and permissions.
    """
    try:
        role = AgentRole.define_role(
            session=session,
            role_type=request.role_type,
            role_name=request.role_name,
            role_level=request.role_level,
            description=request.description,
            responsibilities=request.responsibilities,
            required_capabilities=request.required_capabilities,
            optional_capabilities=request.optional_capabilities,
            min_experience_hours=request.min_experience_hours,
            permissions=request.permissions,
            metadata=request.metadata
        )

        return {
            "success": True,
            "role": role,
            "message": f"Role '{request.role_name}' defined"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/assign")
def assign_role(
    agent_id: int,
    request: AssignRoleRequest,
    session: Session = Depends(get_db_session)
):
    """
    Assign role to an agent.

    Creates a role assignment with start/end dates and tracking.
    Validates that agent doesn't already have active assignment.
    """
    try:
        assignment = AgentRole.assign_role(
            session=session,
            agent_id=agent_id,
            role_id=request.role_id,
            assigned_by=request.assigned_by,
            start_date=request.start_date,
            end_date=request.end_date,
            assignment_reason=request.assignment_reason,
            metadata=request.metadata
        )

        return {
            "success": True,
            "assignment": assignment,
            "message": f"Role assigned to agent {agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assignments/{assignment_id}/revoke")
def revoke_role(
    assignment_id: str,
    request: RevokeRoleRequest,
    session: Session = Depends(get_db_session)
):
    """
    Revoke a role assignment.

    Sets assignment status to revoked and records reason.
    """
    try:
        assignment = AgentRole.revoke_role(
            session=session,
            assignment_id=assignment_id,
            revoked_by=request.revoked_by,
            revocation_reason=request.revocation_reason
        )

        return {
            "success": True,
            "assignment": assignment,
            "message": "Role revoked"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/assignments/{assignment_id}")
def update_assignment(
    assignment_id: str,
    request: UpdateAssignmentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update role assignment.

    Modify assignment status, end date, or metadata.
    """
    try:
        assignment = AgentRole.update_role_assignment(
            session=session,
            assignment_id=assignment_id,
            status=request.status,
            end_date=request.end_date,
            metadata=request.metadata
        )

        return {
            "success": True,
            "assignment": assignment,
            "message": "Assignment updated"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/assignments/{assignment_id}/performance")
def record_performance(
    assignment_id: str,
    request: RecordPerformanceRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record performance in a role.

    Tracks task completion, performance, and quality scores.
    Updates assignment statistics.
    """
    try:
        performance = AgentRole.record_role_performance(
            session=session,
            assignment_id=assignment_id,
            task_id=request.task_id,
            performance_score=request.performance_score,
            quality_score=request.quality_score,
            completion_time=request.completion_time,
            notes=request.notes
        )

        return {
            "success": True,
            "performance": performance,
            "message": "Performance recorded"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/promote")
def promote_agent(
    agent_id: int,
    request: PromoteAgentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Promote agent to higher role level.

    Completes current assignment and creates new one at higher level.
    Validates that new level is higher than current.
    """
    try:
        promotion = AgentRole.promote_agent(
            session=session,
            agent_id=agent_id,
            current_assignment_id=request.current_assignment_id,
            new_role_level=request.new_role_level,
            promoted_by=request.promoted_by,
            promotion_reason=request.promotion_reason
        )

        return {
            "success": True,
            "promotion": promotion,
            "message": f"Agent promoted to {request.new_role_level}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/roles")
def get_agent_roles(
    agent_id: int,
    active_only: bool = True,
    session: Session = Depends(get_db_session)
):
    """
    Get agent's role assignments.

    Returns all roles assigned to agent with optional filtering.
    """
    try:
        roles = AgentRole.get_agent_roles(
            session=session,
            agent_id=agent_id,
            active_only=active_only
        )

        return {
            "success": True,
            **roles
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/roles/{role_id}/agents")
def get_agents_by_role(
    role_id: str,
    active_only: bool = True,
    session: Session = Depends(get_db_session)
):
    """
    Get all agents with a specific role.

    Returns agents who have been assigned this role.
    """
    try:
        result = AgentRole.get_agents_by_role(
            session=session,
            role_id=role_id,
            active_only=active_only
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/suggest")
def suggest_role_for_task(
    request: SuggestRoleRequest,
    session: Session = Depends(get_db_session)
):
    """
    Suggest best role for a task.

    Analyzes task requirements and suggests suitable roles
    ranked by capability match and level.
    """
    try:
        suggestions = AgentRole.suggest_role_for_task(
            session=session,
            task_requirements=request.task_requirements,
            required_level=request.required_level
        )

        return {
            "success": True,
            **suggestions
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/hierarchy")
def get_role_hierarchy(
    session: Session = Depends(get_db_session)
):
    """
    Get role hierarchy visualization.

    Returns roles organized by type and level.
    """
    try:
        hierarchy = AgentRole.get_role_hierarchy(session=session)

        return {
            "success": True,
            **hierarchy
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get role system statistics.

    Returns aggregate data on roles, assignments, and distribution.
    """
    try:
        stats = AgentRole.get_role_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/role-types")
def list_role_types():
    """
    List all role types.

    Returns predefined role types available.
    """
    return {
        "success": True,
        "role_types": [
            {"type": RoleType.LEADER, "description": "Team leader and decision maker"},
            {"type": RoleType.COORDINATOR, "description": "Coordinates tasks and agents"},
            {"type": RoleType.SPECIALIST, "description": "Domain specialist"},
            {"type": RoleType.EXECUTOR, "description": "Task executor"},
            {"type": RoleType.ANALYST, "description": "Data and information analyst"},
            {"type": RoleType.REVIEWER, "description": "Quality reviewer"},
            {"type": RoleType.RESEARCHER, "description": "Information researcher"},
            {"type": RoleType.DEVELOPER, "description": "Development specialist"},
            {"type": RoleType.TESTER, "description": "Quality assurance tester"},
            {"type": RoleType.SUPPORT, "description": "Support and assistance"}
        ]
    }


@router.get("/role-levels")
def list_role_levels():
    """
    List all role levels.

    Returns hierarchy levels from entry to executive.
    """
    return {
        "success": True,
        "role_levels": [
            {"level": RoleLevel.EXECUTIVE, "rank": 5, "description": "Executive level - highest authority"},
            {"level": RoleLevel.SENIOR, "rank": 4, "description": "Senior level - experienced leader"},
            {"level": RoleLevel.INTERMEDIATE, "rank": 3, "description": "Intermediate level - skilled practitioner"},
            {"level": RoleLevel.JUNIOR, "rank": 2, "description": "Junior level - developing skills"},
            {"level": RoleLevel.ENTRY, "rank": 1, "description": "Entry level - beginner"}
        ]
    }


@router.get("/assignment-statuses")
def list_assignment_statuses():
    """
    List all assignment statuses.

    Returns possible statuses for role assignments.
    """
    return {
        "success": True,
        "assignment_statuses": [
            {"status": AssignmentStatus.ACTIVE, "description": "Currently active"},
            {"status": AssignmentStatus.SUSPENDED, "description": "Temporarily suspended"},
            {"status": AssignmentStatus.COMPLETED, "description": "Successfully completed"},
            {"status": AssignmentStatus.REVOKED, "description": "Revoked/terminated"}
        ]
    }
