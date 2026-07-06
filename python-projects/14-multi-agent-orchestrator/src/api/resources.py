"""
Agent Resource Management API endpoints
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_resource import AgentResource, ResourceType
from src.models.agent import AgentStatus
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class SetResourceLimitsRequest(BaseModel):
    """Request model for setting resource limits"""
    agent_id: int = Field(..., description="Agent ID")
    cpu: Optional[float] = Field(None, ge=0.0, description="CPU cores limit")
    memory: Optional[float] = Field(None, ge=0.0, description="Memory in GB")
    gpu: Optional[int] = Field(None, ge=0, description="GPU units")
    disk: Optional[float] = Field(None, ge=0.0, description="Disk space in GB")
    network: Optional[float] = Field(None, ge=0.0, description="Network bandwidth in Mbps")


class SetResourceUsageRequest(BaseModel):
    """Request model for updating resource usage"""
    agent_id: int = Field(..., description="Agent ID")
    cpu: Optional[float] = Field(None, ge=0.0, description="Current CPU usage (cores)")
    memory: Optional[float] = Field(None, ge=0.0, description="Current memory usage (GB)")
    gpu: Optional[int] = Field(None, ge=0, description="Current GPU usage (units)")
    disk: Optional[float] = Field(None, ge=0.0, description="Current disk usage (GB)")
    network: Optional[float] = Field(None, ge=0.0, description="Current network usage (Mbps)")


class CheckAvailabilityRequest(BaseModel):
    """Request model for checking resource availability"""
    agent_id: int = Field(..., description="Agent ID")
    required_cpu: float = Field(default=0, ge=0.0, description="Required CPU cores")
    required_memory: float = Field(default=0, ge=0.0, description="Required memory (GB)")
    required_gpu: int = Field(default=0, ge=0, description="Required GPU units")
    required_disk: float = Field(default=0, ge=0.0, description="Required disk space (GB)")
    required_network: float = Field(default=0, ge=0.0, description="Required network bandwidth (Mbps)")


class FindAgentsRequest(BaseModel):
    """Request model for finding agents with resources"""
    required_cpu: float = Field(default=0, ge=0.0, description="Required CPU cores")
    required_memory: float = Field(default=0, ge=0.0, description="Required memory (GB)")
    required_gpu: int = Field(default=0, ge=0, description="Required GPU units")
    required_disk: float = Field(default=0, ge=0.0, description="Required disk space (GB)")
    required_network: float = Field(default=0, ge=0.0, description="Required network bandwidth (Mbps)")
    status: Optional[str] = Field(default=None, description="Filter by agent status")


class ReserveResourcesRequest(BaseModel):
    """Request model for reserving resources"""
    agent_id: int = Field(..., description="Agent ID")
    execution_id: int = Field(..., description="Execution ID")
    cpu: float = Field(default=0, ge=0.0, description="CPU cores to reserve")
    memory: float = Field(default=0, ge=0.0, description="Memory to reserve (GB)")
    gpu: int = Field(default=0, ge=0, description="GPU units to reserve")
    disk: float = Field(default=0, ge=0.0, description="Disk space to reserve (GB)")
    network: float = Field(default=0, ge=0.0, description="Network bandwidth to reserve (Mbps)")


class ReleaseResourcesRequest(BaseModel):
    """Request model for releasing resources"""
    agent_id: int = Field(..., description="Agent ID")
    execution_id: int = Field(..., description="Execution ID")


# Endpoints

@router.post("/limits/set")
async def set_resource_limits(
    request: SetResourceLimitsRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Set resource limits for an agent.

    Configures the maximum resources that can be allocated to an agent.
    At least one resource limit must be specified.
    """
    try:
        # Validate at least one limit is provided
        if all(v is None for v in [request.cpu, request.memory, request.gpu, request.disk, request.network]):
            raise ValueError("At least one resource limit must be specified")

        limits = AgentResource.set_resource_limits(
            session=db,
            agent_id=request.agent_id,
            cpu=request.cpu,
            memory=request.memory,
            gpu=request.gpu,
            disk=request.disk,
            network=request.network
        )

        return {
            "success": True,
            "agent_id": request.agent_id,
            "limits": limits,
            "message": f"Resource limits updated for agent {request.agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to set resource limits: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/limits/{agent_id}")
async def get_resource_limits(
    agent_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get resource limits for an agent.

    Returns the configured resource limits. If no limits are set,
    returns default limits.
    """
    try:
        limits = AgentResource.get_resource_limits(
            session=db,
            agent_id=agent_id
        )

        return {
            "success": True,
            "agent_id": agent_id,
            "limits": limits,
            "message": f"Resource limits for agent {agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get resource limits: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/usage/set")
async def set_resource_usage(
    request: SetResourceUsageRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Update current resource usage for an agent.

    Updates the current resource consumption metrics. This is typically
    called by monitoring systems or the agent itself to report usage.
    """
    try:
        # Validate at least one usage metric is provided
        if all(v is None for v in [request.cpu, request.memory, request.gpu, request.disk, request.network]):
            raise ValueError("At least one resource usage metric must be specified")

        usage = AgentResource.set_resource_usage(
            session=db,
            agent_id=request.agent_id,
            cpu=request.cpu,
            memory=request.memory,
            gpu=request.gpu,
            disk=request.disk,
            network=request.network
        )

        return {
            "success": True,
            "agent_id": request.agent_id,
            "usage": usage,
            "message": f"Resource usage updated for agent {request.agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to set resource usage: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/usage/{agent_id}")
async def get_resource_usage(
    agent_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get current resource usage for an agent.

    Returns current usage, limits, utilization percentages,
    and whether the agent is overloaded (>90% utilization).
    """
    try:
        usage_info = AgentResource.get_resource_usage(
            session=db,
            agent_id=agent_id
        )

        return {
            "success": True,
            "usage_info": usage_info,
            "message": f"Resource usage for agent {agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get resource usage: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/check-availability")
async def check_availability(
    request: CheckAvailabilityRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Check if an agent has sufficient resources available.

    Verifies whether the agent can accommodate the requested resources
    given its current usage and limits. Returns available amounts and
    any shortfalls.
    """
    try:
        availability = AgentResource.check_resource_availability(
            session=db,
            agent_id=request.agent_id,
            required_cpu=request.required_cpu,
            required_memory=request.required_memory,
            required_gpu=request.required_gpu,
            required_disk=request.required_disk,
            required_network=request.required_network
        )

        return {
            "success": True,
            "availability": availability,
            "message": (
                "Agent has sufficient resources"
                if availability["sufficient"]
                else "Insufficient resources"
            )
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to check availability: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/find-agents")
async def find_agents(
    request: FindAgentsRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Find agents with sufficient available resources.

    Searches for agents that can accommodate the requested resources.
    Results are sorted by lowest average utilization (prefer less loaded agents).

    Optionally filter by agent status (e.g., only ACTIVE agents).
    """
    try:
        # Convert status string to enum if provided
        agent_status = None
        if request.status:
            try:
                agent_status = AgentStatus(request.status)
            except ValueError:
                raise ValueError(f"Invalid agent status: {request.status}")

        suitable_agents = AgentResource.find_agents_with_resources(
            session=db,
            required_cpu=request.required_cpu,
            required_memory=request.required_memory,
            required_gpu=request.required_gpu,
            required_disk=request.required_disk,
            required_network=request.required_network,
            status=agent_status
        )

        return {
            "success": True,
            "total_agents": len(suitable_agents),
            "agents": suitable_agents,
            "message": f"Found {len(suitable_agents)} suitable agents"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to find agents: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/cluster")
async def get_cluster_resources(
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get cluster-wide resource statistics.

    Returns aggregate resource information across all agents:
    - Total limits (capacity)
    - Total usage (consumption)
    - Total available (capacity - consumption)
    - Utilization percentages
    - Average utilization across all resource types
    """
    try:
        cluster_stats = AgentResource.get_cluster_resources(session=db)

        return {
            "success": True,
            "cluster": cluster_stats,
            "message": f"Cluster resources for {cluster_stats['total_agents']} agents"
        }

    except Exception as e:
        logger.error(f"Failed to get cluster resources: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/reserve")
async def reserve_resources(
    request: ReserveResourcesRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Reserve resources for a task execution.

    Creates a reservation that allocates resources to a specific execution.
    The reservation is tracked and resources are marked as in-use.

    Fails if insufficient resources are available. Use check-availability
    endpoint first to verify resources before reserving.
    """
    try:
        reservation = AgentResource.reserve_resources(
            session=db,
            agent_id=request.agent_id,
            execution_id=request.execution_id,
            cpu=request.cpu,
            memory=request.memory,
            gpu=request.gpu,
            disk=request.disk,
            network=request.network
        )

        return {
            "success": True,
            "reservation": reservation,
            "message": f"Resources reserved for execution {request.execution_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to reserve resources: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/release")
async def release_resources(
    request: ReleaseResourcesRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Release reserved resources for a task execution.

    Removes the reservation and marks resources as available again.
    Should be called when task execution completes (success or failure).

    Returns success=false if the reservation was not found (already released
    or never existed).
    """
    try:
        released = AgentResource.release_resources(
            session=db,
            agent_id=request.agent_id,
            execution_id=request.execution_id
        )

        if not released:
            return {
                "success": False,
                "message": f"No reservation found for execution {request.execution_id} on agent {request.agent_id}"
            }

        return {
            "success": True,
            "message": f"Resources released for execution {request.execution_id}"
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to release resources: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/alerts")
async def get_resource_alerts(
    threshold: float = Query(90.0, ge=0.0, le=100.0, description="Utilization threshold percentage"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get agents with resource usage above threshold.

    Returns agents where any resource type has utilization >= threshold.
    Useful for monitoring and alerting on overloaded agents.

    Default threshold is 90%.
    """
    try:
        alerts = AgentResource.get_resource_alerts(
            session=db,
            threshold=threshold
        )

        return {
            "success": True,
            "threshold": threshold,
            "total_alerts": len(alerts),
            "alerts": alerts,
            "message": f"Found {len(alerts)} agents above {threshold}% utilization"
        }

    except Exception as e:
        logger.error(f"Failed to get resource alerts: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/types")
async def list_resource_types() -> Dict[str, Any]:
    """
    List all resource types with descriptions.

    Returns the available resource types that can be tracked
    and managed by the system.
    """
    types = [
        {
            "type": ResourceType.CPU,
            "unit": "cores",
            "description": "CPU processing capacity"
        },
        {
            "type": ResourceType.MEMORY,
            "unit": "GB",
            "description": "RAM memory capacity"
        },
        {
            "type": ResourceType.GPU,
            "unit": "units",
            "description": "GPU processing units"
        },
        {
            "type": ResourceType.DISK,
            "unit": "GB",
            "description": "Disk storage space"
        },
        {
            "type": ResourceType.NETWORK,
            "unit": "Mbps",
            "description": "Network bandwidth"
        }
    ]

    return {
        "success": True,
        "total_types": len(types),
        "types": types,
        "message": "List of all resource types"
    }
