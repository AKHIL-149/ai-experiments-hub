"""
Service Discovery and Registry API

REST API endpoints for service registration, discovery, and health monitoring.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.service_discovery import (
    ServiceDiscovery,
    ServiceStatus,
    LoadBalancingStrategy,
    ServiceType,
    HealthCheckType
)


router = APIRouter()


# Request/Response Models
class RegisterServiceRequest(BaseModel):
    service_name: str = Field(..., description="Service name")
    service_type: str = Field(..., description="Type of service")
    host: str = Field(..., description="Service host")
    port: int = Field(..., description="Service port")
    version: str = Field("1.0.0", description="Service version")
    metadata: Optional[dict] = Field(None, description="Additional metadata")
    health_check_url: Optional[str] = Field(None, description="Health check endpoint")
    health_check_interval_seconds: int = Field(30, description="Health check interval")
    tags: Optional[List[str]] = Field(None, description="Service tags")
    weight: int = Field(1, description="Weight for load balancing")


class DiscoverServiceRequest(BaseModel):
    version: Optional[str] = Field(None, description="Version filter")
    tags: Optional[List[str]] = Field(None, description="Tags filter")
    status: str = Field(ServiceStatus.HEALTHY, description="Status filter")


class GetServiceInstanceRequest(BaseModel):
    strategy: str = Field(LoadBalancingStrategy.ROUND_ROBIN, description="Load balancing strategy")
    version: Optional[str] = Field(None, description="Version filter")
    tags: Optional[List[str]] = Field(None, description="Tags filter")


class UpdateHealthRequest(BaseModel):
    status: str = Field(..., description="Health status")
    health_data: Optional[dict] = Field(None, description="Health check data")


@router.post("/register")
def register_service(
    request: RegisterServiceRequest,
    session: Session = Depends(get_db_session)
):
    """
    Register a service instance.

    Registers a new service instance with the discovery service,
    making it available for discovery and load balancing.
    """
    try:
        instance = ServiceDiscovery.register_service(
            session=session,
            service_name=request.service_name,
            service_type=request.service_type,
            host=request.host,
            port=request.port,
            version=request.version,
            metadata=request.metadata,
            health_check_url=request.health_check_url,
            health_check_interval_seconds=request.health_check_interval_seconds,
            tags=request.tags,
            weight=request.weight
        )

        return {
            "success": True,
            "instance": instance,
            "message": f"Service registered: {instance['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/instances/{instance_id}")
def deregister_service(
    instance_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Deregister a service instance.

    Removes a service instance from the registry,
    making it unavailable for discovery.
    """
    try:
        result = ServiceDiscovery.deregister_service(
            session=session,
            instance_id=instance_id
        )

        return {
            "success": True,
            **result,
            "message": f"Service deregistered: {instance_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/discover/{service_name}")
def discover_service(
    service_name: str,
    request: DiscoverServiceRequest,
    session: Session = Depends(get_db_session)
):
    """
    Discover service instances.

    Returns all instances of a service matching the specified filters.
    """
    try:
        result = ServiceDiscovery.discover_service(
            session=session,
            service_name=service_name,
            version=request.version,
            tags=request.tags,
            status=request.status
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/instance/{service_name}")
def get_service_instance(
    service_name: str,
    request: GetServiceInstanceRequest,
    session: Session = Depends(get_db_session)
):
    """
    Get a service instance.

    Returns a single service instance using the specified
    load balancing strategy.
    """
    try:
        result = ServiceDiscovery.get_service_instance(
            session=session,
            service_name=service_name,
            strategy=request.strategy,
            version=request.version,
            tags=request.tags
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/heartbeat/{instance_id}")
def send_heartbeat(
    instance_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Send heartbeat for service instance.

    Updates the last heartbeat time for an instance,
    indicating it is still alive.
    """
    try:
        result = ServiceDiscovery.heartbeat(
            session=session,
            instance_id=instance_id
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/instances/{instance_id}/health")
def update_instance_health(
    instance_id: str,
    request: UpdateHealthRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update instance health status.

    Updates the health status of a service instance based
    on health check results.
    """
    try:
        instance = ServiceDiscovery.update_instance_health(
            session=session,
            instance_id=instance_id,
            status=request.status,
            health_data=request.health_data
        )

        return {
            "success": True,
            "instance": instance,
            "message": f"Health status updated to {request.status}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services")
def list_services(
    service_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    List registered services.

    Returns all registered services with optional filtering
    by type and status.
    """
    try:
        result = ServiceDiscovery.list_services(
            session=session,
            service_type=service_type,
            status=status,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services/{service_name}/health")
def get_service_health(
    service_name: str,
    session: Session = Depends(get_db_session)
):
    """
    Get service health information.

    Returns detailed health information for a service including
    instance counts and health percentages.
    """
    try:
        health = ServiceDiscovery.get_service_health(
            session=session,
            service_name=service_name
        )

        return {
            "success": True,
            "health": health
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
    Get service discovery statistics.

    Returns aggregate metrics including total services,
    instances, and health percentages.
    """
    try:
        stats = ServiceDiscovery.get_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/service-types")
def list_service_types():
    """
    List all service types.

    Returns all available service type options.
    """
    return {
        "success": True,
        "service_types": [
            {"type": ServiceType.AGENT, "description": "Agent service"},
            {"type": ServiceType.API, "description": "API service"},
            {"type": ServiceType.DATABASE, "description": "Database service"},
            {"type": ServiceType.CACHE, "description": "Cache service"},
            {"type": ServiceType.MESSAGE_QUEUE, "description": "Message queue service"},
            {"type": ServiceType.STORAGE, "description": "Storage service"},
            {"type": ServiceType.CUSTOM, "description": "Custom service"}
        ]
    }


@router.get("/service-statuses")
def list_service_statuses():
    """
    List all service statuses.

    Returns all possible service health statuses.
    """
    return {
        "success": True,
        "service_statuses": [
            {"status": ServiceStatus.HEALTHY, "description": "Service is healthy"},
            {"status": ServiceStatus.UNHEALTHY, "description": "Service is unhealthy"},
            {"status": ServiceStatus.STARTING, "description": "Service is starting"},
            {"status": ServiceStatus.STOPPING, "description": "Service is stopping"},
            {"status": ServiceStatus.UNKNOWN, "description": "Service status unknown"}
        ]
    }


@router.get("/load-balancing-strategies")
def list_load_balancing_strategies():
    """
    List all load balancing strategies.

    Returns all available load balancing strategies.
    """
    return {
        "success": True,
        "load_balancing_strategies": [
            {"strategy": LoadBalancingStrategy.ROUND_ROBIN, "description": "Round-robin selection"},
            {"strategy": LoadBalancingStrategy.RANDOM, "description": "Random selection"},
            {"strategy": LoadBalancingStrategy.LEAST_CONNECTIONS, "description": "Least connections"},
            {"strategy": LoadBalancingStrategy.WEIGHTED, "description": "Weighted selection"},
            {"strategy": LoadBalancingStrategy.CONSISTENT_HASH, "description": "Consistent hashing"}
        ]
    }


@router.get("/health-check-types")
def list_health_check_types():
    """
    List all health check types.

    Returns all available health check types.
    """
    return {
        "success": True,
        "health_check_types": [
            {"type": HealthCheckType.HTTP, "description": "HTTP health check"},
            {"type": HealthCheckType.TCP, "description": "TCP health check"},
            {"type": HealthCheckType.SCRIPT, "description": "Script-based health check"},
            {"type": HealthCheckType.HEARTBEAT, "description": "Heartbeat health check"}
        ]
    }
