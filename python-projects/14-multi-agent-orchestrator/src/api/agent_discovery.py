"""
Agent Discovery API

REST API endpoints for agent registration, discovery, and service directory.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_discovery import (
    AgentDiscovery,
    DiscoveryStatus,
    CapabilityCategory
)


router = APIRouter()


# Request/Response Models
class RegisterAgentRequest(BaseModel):
    agent_name: str = Field(..., description="Agent name")
    capabilities: List[str] = Field(..., description="Agent capabilities")
    categories: Optional[List[str]] = Field(None, description="Capability categories")
    tags: Optional[List[str]] = Field(None, description="Searchable tags")
    endpoint: Optional[str] = Field(None, description="Agent endpoint URL")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class DiscoverAgentsRequest(BaseModel):
    required_capabilities: Optional[List[str]] = Field(None, description="Required capabilities")
    categories: Optional[List[str]] = Field(None, description="Category filters")
    tags: Optional[List[str]] = Field(None, description="Tag filters")
    status: Optional[str] = Field(None, description="Status filter")
    match_all_capabilities: bool = Field(False, description="Require all capabilities")
    limit: int = Field(10, description="Maximum results")


class UpdateStatusRequest(BaseModel):
    status: str = Field(..., description="New status")
    reason: Optional[str] = Field(None, description="Reason for change")


class HeartbeatRequest(BaseModel):
    metrics: Optional[dict] = Field(None, description="Current metrics")


class RegisterServiceRequest(BaseModel):
    service_name: str = Field(..., description="Service name")
    service_description: Optional[str] = Field(None, description="Service description")
    service_metadata: Optional[dict] = Field(None, description="Service metadata")


class AddCapabilityRequest(BaseModel):
    capability: str = Field(..., description="Capability to add")
    category: Optional[str] = Field(None, description="Capability category")


class RemoveCapabilityRequest(BaseModel):
    capability: str = Field(..., description="Capability to remove")


@router.post("/register")
def register_agent(
    agent_id: int,
    request: RegisterAgentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Register an agent in the discovery system.

    Makes the agent discoverable by other agents based on its capabilities,
    categories, and tags. Agents must register to participate in discovery.
    """
    try:
        registration = AgentDiscovery.register_agent(
            session=session,
            agent_id=agent_id,
            agent_name=request.agent_name,
            capabilities=request.capabilities,
            categories=request.categories,
            tags=request.tags,
            endpoint=request.endpoint,
            metadata=request.metadata
        )

        return {
            "success": True,
            "registration": registration,
            "message": f"Agent '{request.agent_name}' registered successfully"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/discover")
def discover_agents(
    request: DiscoverAgentsRequest,
    session: Session = Depends(get_db_session)
):
    """
    Discover agents based on requirements.

    Search for agents by capabilities, categories, tags, and status.
    Returns ranked results based on relevance to the query.
    """
    try:
        result = AgentDiscovery.discover_agents(
            session=session,
            required_capabilities=request.required_capabilities,
            categories=request.categories,
            tags=request.tags,
            status=request.status,
            match_all_capabilities=request.match_all_capabilities,
            limit=request.limit
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/agents/{agent_id}/status")
def update_status(
    agent_id: int,
    request: UpdateStatusRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update agent discovery status.

    Changes the agent's availability status (available, busy, unavailable, maintenance).
    Status affects whether the agent appears in discovery queries.
    """
    try:
        registration = AgentDiscovery.update_status(
            session=session,
            agent_id=agent_id,
            status=request.status,
            reason=request.reason
        )

        return {
            "success": True,
            "registration": registration,
            "message": f"Status updated to {request.status}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/heartbeat")
def heartbeat(
    agent_id: int,
    request: HeartbeatRequest = HeartbeatRequest(),
    session: Session = Depends(get_db_session)
):
    """
    Record agent heartbeat.

    Agents should send regular heartbeats to indicate they are alive and healthy.
    Heartbeats can include current metrics like load, memory usage, etc.
    """
    try:
        acknowledgment = AgentDiscovery.heartbeat(
            session=session,
            agent_id=agent_id,
            metrics=request.metrics
        )

        return {
            "success": True,
            **acknowledgment
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/services")
def register_service(
    agent_id: int,
    request: RegisterServiceRequest,
    session: Session = Depends(get_db_session)
):
    """
    Register a service provided by an agent.

    Adds the agent to the service directory for the specified service.
    Other agents can discover service providers using the service name.
    """
    try:
        service = AgentDiscovery.register_service(
            session=session,
            agent_id=agent_id,
            service_name=request.service_name,
            service_description=request.service_description,
            service_metadata=request.service_metadata
        )

        return {
            "success": True,
            "service": service,
            "message": f"Service '{request.service_name}' registered"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services/{service_name}")
def discover_service(
    service_name: str,
    only_available: bool = True,
    session: Session = Depends(get_db_session)
):
    """
    Discover agents providing a service.

    Finds all agents registered as providers of the specified service.
    Can optionally filter to only available agents.
    """
    try:
        result = AgentDiscovery.discover_service(
            session=session,
            service_name=service_name,
            only_available=only_available
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/capabilities")
def add_capability(
    agent_id: int,
    request: AddCapabilityRequest,
    session: Session = Depends(get_db_session)
):
    """
    Add a capability to an agent.

    Dynamically adds a new capability to the agent's profile.
    The agent becomes discoverable for this capability.
    """
    try:
        registration = AgentDiscovery.add_capability(
            session=session,
            agent_id=agent_id,
            capability=request.capability,
            category=request.category
        )

        return {
            "success": True,
            "registration": registration,
            "message": f"Capability '{request.capability}' added"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agents/{agent_id}/capabilities")
def remove_capability(
    agent_id: int,
    request: RemoveCapabilityRequest,
    session: Session = Depends(get_db_session)
):
    """
    Remove a capability from an agent.

    Removes a capability from the agent's profile.
    The agent will no longer be discoverable for this capability.
    """
    try:
        registration = AgentDiscovery.remove_capability(
            session=session,
            agent_id=agent_id,
            capability=request.capability
        )

        return {
            "success": True,
            "registration": registration,
            "message": f"Capability '{request.capability}' removed"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agents/{agent_id}/unregister")
def unregister_agent(
    agent_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Unregister an agent from discovery.

    Removes the agent from the discovery system and service directory.
    The agent will no longer be discoverable.
    """
    try:
        result = AgentDiscovery.unregister_agent(
            session=session,
            agent_id=agent_id
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}")
def get_agent_info(
    agent_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get agent registration information.

    Returns complete registration details including capabilities,
    status, uptime, and provided services.
    """
    try:
        info = AgentDiscovery.get_agent_info(
            session=session,
            agent_id=agent_id
        )

        return {
            "success": True,
            "agent": info
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents")
def list_all_agents(
    status: Optional[str] = None,
    category: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    List all registered agents.

    Returns all agents in the discovery system with optional filtering
    by status or category.
    """
    try:
        result = AgentDiscovery.list_all_agents(
            session=session,
            status=status,
            category=category
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/capabilities")
def get_capabilities_catalog(
    session: Session = Depends(get_db_session)
):
    """
    Get catalog of all capabilities.

    Returns all capabilities registered in the system with
    counts of total and available agents for each.
    """
    try:
        catalog = AgentDiscovery.get_capabilities_catalog(session=session)

        return {
            "success": True,
            **catalog
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services")
def get_service_directory(
    session: Session = Depends(get_db_session)
):
    """
    Get complete service directory.

    Returns all services registered in the system with
    their providers and availability status.
    """
    try:
        directory = AgentDiscovery.get_service_directory(session=session)

        return {
            "success": True,
            **directory
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health-check")
def check_agent_health(
    timeout_seconds: int = 300,
    session: Session = Depends(get_db_session)
):
    """
    Check health of all agents.

    Examines agent heartbeats to determine which agents are healthy
    (recent heartbeat) vs unhealthy (no recent heartbeat).
    """
    try:
        health = AgentDiscovery.check_agent_health(
            session=session,
            timeout_seconds=timeout_seconds
        )

        return {
            "success": True,
            **health
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get discovery system statistics.

    Returns aggregate data including agent counts, capability distribution,
    service counts, and top capabilities.
    """
    try:
        stats = AgentDiscovery.get_discovery_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/discovery-statuses")
def list_discovery_statuses():
    """
    List all discovery statuses.

    Returns all possible agent discovery statuses.
    """
    return {
        "success": True,
        "statuses": [
            {"status": DiscoveryStatus.AVAILABLE, "description": "Agent is available for tasks"},
            {"status": DiscoveryStatus.BUSY, "description": "Agent is busy with tasks"},
            {"status": DiscoveryStatus.UNAVAILABLE, "description": "Agent is unavailable"},
            {"status": DiscoveryStatus.MAINTENANCE, "description": "Agent is under maintenance"}
        ]
    }


@router.get("/capability-categories")
def list_capability_categories():
    """
    List all capability categories.

    Returns all predefined capability categories for organizing agent capabilities.
    """
    return {
        "success": True,
        "categories": [
            {"category": CapabilityCategory.COMPUTATION, "description": "Computational capabilities"},
            {"category": CapabilityCategory.STORAGE, "description": "Data storage capabilities"},
            {"category": CapabilityCategory.COMMUNICATION, "description": "Communication capabilities"},
            {"category": CapabilityCategory.ANALYSIS, "description": "Analysis and processing capabilities"},
            {"category": CapabilityCategory.GENERATION, "description": "Content generation capabilities"},
            {"category": CapabilityCategory.TRANSFORMATION, "description": "Data transformation capabilities"},
            {"category": CapabilityCategory.VALIDATION, "description": "Validation and verification capabilities"},
            {"category": CapabilityCategory.ORCHESTRATION, "description": "Orchestration and coordination capabilities"}
        ]
    }
