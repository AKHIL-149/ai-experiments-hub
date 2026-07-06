"""
Agent Capability API endpoints
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_capability import AgentCapability, CapabilityLevel, CapabilityCategory
from src.models.agent import AgentRole
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class RegisterCapabilityRequest(BaseModel):
    """Request model for registering a capability"""
    agent_id: int = Field(..., description="Agent ID")
    capability: str = Field(..., description="Capability name")
    level: str = Field(
        default=CapabilityLevel.INTERMEDIATE,
        description="Proficiency level"
    )
    category: Optional[str] = Field(
        default=None,
        description="Capability category"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Additional metadata"
    )


class BatchRegisterRequest(BaseModel):
    """Request model for batch capability registration"""
    agent_id: int = Field(..., description="Agent ID")
    capabilities: List[Dict[str, Any]] = Field(
        ...,
        description="List of capabilities to register"
    )


class RemoveCapabilityRequest(BaseModel):
    """Request model for removing a capability"""
    agent_id: int = Field(..., description="Agent ID")
    capability: str = Field(..., description="Capability name to remove")


class MatchCapabilitiesRequest(BaseModel):
    """Request model for capability matching"""
    required_capabilities: List[str] = Field(
        ...,
        description="List of required capability names"
    )
    min_level: str = Field(
        default=CapabilityLevel.BASIC,
        description="Minimum proficiency level"
    )
    role: Optional[str] = Field(
        default=None,
        description="Optional role filter"
    )
    status: Optional[str] = Field(
        default=None,
        description="Optional status filter"
    )


class FindBestAgentRequest(BaseModel):
    """Request model for finding best agent"""
    required_capabilities: List[str] = Field(
        ...,
        description="Required capabilities"
    )
    min_level: str = Field(
        default=CapabilityLevel.INTERMEDIATE,
        description="Minimum proficiency level"
    )
    role: Optional[str] = Field(
        default=None,
        description="Optional role filter"
    )
    prefer_available: bool = Field(
        default=True,
        description="Prefer idle/available agents"
    )


class ValidateCapabilityRequest(BaseModel):
    """Request model for capability validation"""
    capability: str = Field(..., description="Capability name")
    level: str = Field(..., description="Proficiency level")
    category: Optional[str] = Field(default=None, description="Category")


# Endpoints

@router.post("/register")
async def register_capability(
    request: RegisterCapabilityRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Register a capability for an agent.

    Capabilities define what an agent can do and at what proficiency level.
    Use this to track agent skills for intelligent task routing.
    """
    try:
        capability = AgentCapability.register_capability(
            session=db,
            agent_id=request.agent_id,
            capability=request.capability,
            level=request.level,
            category=request.category,
            metadata=request.metadata
        )

        return {
            "success": True,
            "capability": capability,
            "message": f"Capability '{request.capability}' registered for agent {request.agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to register capability: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/batch-register")
async def batch_register_capabilities(
    request: BatchRegisterRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Register multiple capabilities for an agent in batch.

    More efficient than individual registration when setting up
    a new agent or updating multiple capabilities at once.
    """
    try:
        if not request.capabilities:
            raise ValueError("Capabilities list cannot be empty")

        if len(request.capabilities) > 100:
            raise ValueError("Maximum 100 capabilities allowed per batch")

        capabilities = AgentCapability.batch_register_capabilities(
            session=db,
            agent_id=request.agent_id,
            capabilities=request.capabilities
        )

        return {
            "success": True,
            "registered_count": len(capabilities),
            "capabilities": capabilities,
            "message": f"Registered {len(capabilities)} capabilities for agent {request.agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to batch register capabilities: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/remove")
async def remove_capability(
    request: RemoveCapabilityRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Remove a capability from an agent.

    Use this when an agent no longer possesses a capability
    or when the capability is deprecated.
    """
    try:
        removed = AgentCapability.remove_capability(
            session=db,
            agent_id=request.agent_id,
            capability=request.capability
        )

        if not removed:
            return {
                "success": False,
                "message": f"Capability '{request.capability}' not found for agent {request.agent_id}"
            }

        return {
            "success": True,
            "message": f"Capability '{request.capability}' removed from agent {request.agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to remove capability: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/agent/{agent_id}")
async def get_agent_capabilities(
    agent_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get all capabilities for a specific agent.

    Returns detailed information about each capability including
    proficiency level, category, and registration date.
    """
    try:
        capabilities = AgentCapability.get_agent_capabilities(
            session=db,
            agent_id=agent_id
        )

        return {
            "success": True,
            "agent_id": agent_id,
            "total_capabilities": len(capabilities),
            "capabilities": capabilities,
            "message": f"Retrieved {len(capabilities)} capabilities for agent {agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get agent capabilities: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/match")
async def match_capabilities(
    request: MatchCapabilitiesRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Find agents that match required capabilities.

    Returns a ranked list of agents sorted by match score.
    Higher scores indicate better capability matches.
    """
    try:
        if not request.required_capabilities:
            raise ValueError("Required capabilities list cannot be empty")

        # Convert role string to enum if provided
        role = None
        if request.role:
            try:
                role = AgentRole(request.role)
            except ValueError:
                raise ValueError(f"Invalid role: {request.role}")

        # Convert status string to enum if provided
        from src.models.agent import AgentStatus
        agent_status = None
        if request.status:
            try:
                agent_status = AgentStatus(request.status)
            except ValueError:
                raise ValueError(f"Invalid status: {request.status}")

        matches = AgentCapability.match_capabilities(
            session=db,
            required_capabilities=request.required_capabilities,
            min_level=request.min_level,
            role=role,
            status=agent_status
        )

        return {
            "success": True,
            "required_capabilities": request.required_capabilities,
            "min_level": request.min_level,
            "total_matches": len(matches),
            "matches": matches,
            "message": f"Found {len(matches)} agents matching capabilities"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to match capabilities: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/find-best-agent")
async def find_best_agent(
    request: FindBestAgentRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Find the single best agent for given capabilities.

    Returns the top-ranked agent or null if no suitable agent found.
    Prefers idle agents when prefer_available is true.
    """
    try:
        if not request.required_capabilities:
            raise ValueError("Required capabilities list cannot be empty")

        # Convert role string to enum if provided
        role = None
        if request.role:
            try:
                role = AgentRole(request.role)
            except ValueError:
                raise ValueError(f"Invalid role: {request.role}")

        best_agent = AgentCapability.find_best_agent(
            session=db,
            required_capabilities=request.required_capabilities,
            min_level=request.min_level,
            role=role,
            prefer_available=request.prefer_available
        )

        if not best_agent:
            return {
                "success": False,
                "agent": None,
                "message": "No suitable agent found for required capabilities"
            }

        return {
            "success": True,
            "agent": best_agent,
            "message": f"Found best agent: {best_agent['agent_name']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to find best agent: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/coverage")
async def get_capability_coverage(
    capabilities: List[str],
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Analyze capability coverage across all agents.

    Shows how many agents have each capability and at what levels.
    Useful for identifying gaps in your agent fleet.
    """
    try:
        if not capabilities:
            raise ValueError("Capabilities list cannot be empty")

        coverage = AgentCapability.get_capability_coverage(
            session=db,
            capabilities=capabilities
        )

        return {
            "success": True,
            "analysis": coverage,
            "message": f"Coverage analysis for {len(capabilities)} capabilities"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get capability coverage: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/all")
async def get_all_capabilities(
    category: Optional[str] = Query(None, description="Filter by category"),
    min_agents: int = Query(1, ge=1, description="Minimum number of agents"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get all unique capabilities across all agents.

    Returns statistics about each capability including how many
    agents possess it and at what proficiency levels.
    """
    try:
        capabilities = AgentCapability.get_all_capabilities(
            session=db,
            category=category,
            min_agents=min_agents
        )

        return {
            "success": True,
            "total_capabilities": len(capabilities),
            "category_filter": category,
            "min_agents": min_agents,
            "capabilities": capabilities,
            "message": f"Retrieved {len(capabilities)} capabilities"
        }

    except Exception as e:
        logger.error(f"Failed to get all capabilities: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/suggest/{agent_id}")
async def suggest_capabilities(
    agent_id: int,
    based_on_role: bool = Query(True, description="Base suggestions on agent role"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Suggest capabilities for an agent based on role and peer analysis.

    Recommends capabilities that:
    1. Are typical for the agent's role
    2. Are commonly possessed by similar agents
    3. The agent doesn't already have
    """
    try:
        suggestions = AgentCapability.suggest_capabilities_for_agent(
            session=db,
            agent_id=agent_id,
            based_on_role=based_on_role
        )

        return {
            "success": True,
            "agent_id": agent_id,
            "total_suggestions": len(suggestions),
            "suggestions": suggestions,
            "message": f"Generated {len(suggestions)} capability suggestions for agent {agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to suggest capabilities: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/validate")
async def validate_capability(
    request: ValidateCapabilityRequest
) -> Dict[str, Any]:
    """
    Validate a capability definition.

    Checks that:
    - Capability name is valid
    - Proficiency level is valid
    - Category is recognized (warning if not)
    """
    try:
        validation = AgentCapability.validate_capability(
            capability=request.capability,
            level=request.level,
            category=request.category
        )

        return {
            "success": True,
            "validation": validation,
            "message": "Valid capability" if validation["valid"] else "Invalid capability"
        }

    except Exception as e:
        logger.error(f"Failed to validate capability: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/levels")
async def list_capability_levels() -> Dict[str, Any]:
    """
    List all valid capability proficiency levels.

    Returns the hierarchy of proficiency levels from basic to expert.
    """
    levels = [
        {
            "level": CapabilityLevel.BASIC,
            "weight": 1.0,
            "description": "Fundamental understanding and basic usage"
        },
        {
            "level": CapabilityLevel.INTERMEDIATE,
            "weight": 2.0,
            "description": "Comfortable with common use cases and patterns"
        },
        {
            "level": CapabilityLevel.ADVANCED,
            "weight": 3.0,
            "description": "Deep knowledge and ability to handle complex scenarios"
        },
        {
            "level": CapabilityLevel.EXPERT,
            "weight": 4.0,
            "description": "Mastery with ability to teach and innovate"
        }
    ]

    return {
        "success": True,
        "total_levels": len(levels),
        "levels": levels,
        "default_level": CapabilityLevel.INTERMEDIATE,
        "message": "List of all capability proficiency levels"
    }


@router.get("/categories")
async def list_capability_categories() -> Dict[str, Any]:
    """
    List all valid capability categories.

    Categories help organize capabilities into logical groups
    for easier management and discovery.
    """
    categories = [
        {"name": CapabilityCategory.PROGRAMMING, "description": "Programming languages and paradigms"},
        {"name": CapabilityCategory.TESTING, "description": "Testing frameworks and methodologies"},
        {"name": CapabilityCategory.DOCUMENTATION, "description": "Documentation tools and writing"},
        {"name": CapabilityCategory.ANALYSIS, "description": "Data analysis and research"},
        {"name": CapabilityCategory.DESIGN, "description": "UI/UX and system design"},
        {"name": CapabilityCategory.DEPLOYMENT, "description": "Deployment and release management"},
        {"name": CapabilityCategory.MONITORING, "description": "Monitoring and observability"},
        {"name": CapabilityCategory.SECURITY, "description": "Security and vulnerability assessment"},
        {"name": CapabilityCategory.DATABASE, "description": "Database systems and query languages"},
        {"name": CapabilityCategory.API, "description": "API design and integration"},
        {"name": CapabilityCategory.UI_UX, "description": "User interface and experience"},
        {"name": CapabilityCategory.MACHINE_LEARNING, "description": "ML frameworks and models"},
        {"name": CapabilityCategory.DATA_PROCESSING, "description": "Data processing and ETL"},
        {"name": CapabilityCategory.CLOUD, "description": "Cloud platforms and services"},
        {"name": CapabilityCategory.DEVOPS, "description": "DevOps tools and practices"}
    ]

    return {
        "success": True,
        "total_categories": len(categories),
        "categories": categories,
        "message": "List of all capability categories"
    }
