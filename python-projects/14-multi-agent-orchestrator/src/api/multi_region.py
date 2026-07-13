"""
Multi-Region Deployment API

REST API endpoints for multi-region deployment orchestration and management.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from src.database import get_db_session
from src.services.multi_region import (
    MultiRegion,
    DeploymentStrategy,
    TrafficRoutingMode
)


router = APIRouter()


# Request/Response Models
class RegisterRegionRequest(BaseModel):
    """Request model for registering a region"""
    region_id: str = Field(..., description="Unique region identifier")
    name: str = Field(..., description="Region name")
    location: str = Field(..., description="Geographic location")
    endpoint: str = Field(..., description="Region endpoint URL")
    capacity: int = Field(default=100, description="Region capacity", ge=1)
    priority: int = Field(default=1, description="Region priority", ge=1)
    enabled: bool = Field(default=True, description="Whether region is enabled")
    metadata: Optional[Dict] = Field(default=None, description="Additional metadata")


class CreateDeploymentRequest(BaseModel):
    """Request model for creating a deployment"""
    deployment_id: str = Field(..., description="Unique deployment identifier")
    name: str = Field(..., description="Deployment name")
    service_name: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    target_regions: List[str] = Field(..., description="Target region IDs", min_items=1)
    strategy: DeploymentStrategy = Field(default=DeploymentStrategy.ROLLING, description="Deployment strategy")
    rollout_percentage: int = Field(default=100, description="Rollout percentage", ge=1, le=100)
    description: Optional[str] = Field(default=None, description="Deployment description")


class RecordHealthCheckRequest(BaseModel):
    """Request model for recording health check"""
    is_healthy: bool = Field(..., description="Whether region is healthy")
    response_time_ms: float = Field(..., description="Response time in milliseconds", ge=0)
    error_message: Optional[str] = Field(default=None, description="Error message if unhealthy")


class ConfigureTrafficRoutingRequest(BaseModel):
    """Request model for configuring traffic routing"""
    route_id: str = Field(..., description="Unique route identifier")
    service_name: str = Field(..., description="Service name")
    routing_mode: TrafficRoutingMode = Field(..., description="Routing mode")
    region_weights: Optional[Dict[str, float]] = Field(default=None, description="Region weights (must sum to 100)")


class UpdateReplicationRequest(BaseModel):
    """Request model for updating replication status"""
    replication_id: str = Field(..., description="Unique replication identifier")
    source_region: str = Field(..., description="Source region ID")
    target_region: str = Field(..., description="Target region ID")
    status: str = Field(..., description="Replication status")
    lag_seconds: float = Field(..., description="Replication lag in seconds", ge=0)
    bytes_pending: int = Field(default=0, description="Bytes pending replication", ge=0)


class FailoverRequest(BaseModel):
    """Request model for region failover"""
    target_region: str = Field(..., description="Target region ID for failover")
    reason: str = Field(..., description="Reason for failover")


# API Endpoints
@router.post("/regions")
def register_region(
    request: RegisterRegionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Register a deployment region.
    Registers a new region for multi-region deployments.
    """
    try:
        result = MultiRegion.register_region(
            session=session,
            region_id=request.region_id,
            name=request.name,
            location=request.location,
            endpoint=request.endpoint,
            capacity=request.capacity,
            priority=request.priority,
            enabled=request.enabled,
            metadata=request.metadata
        )
        return {
            "success": True,
            "region": result,
            "message": f"Region registered: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error registering region: {str(e)}")


@router.get("/regions")
def list_regions(session: Session = Depends(get_db_session)):
    """
    List all regions.
    Returns all registered deployment regions.
    """
    try:
        regions = list(MultiRegion._regions.values())
        return {
            "success": True,
            "regions": regions,
            "count": len(regions)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing regions: {str(e)}")


@router.get("/regions/{region_id}")
def get_region_status(
    region_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get region status.
    Returns comprehensive status information for a region.
    """
    try:
        status = MultiRegion.get_region_status(
            session=session,
            region_id=region_id
        )
        return {
            "success": True,
            "status": status
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting region status: {str(e)}")


@router.post("/regions/{region_id}/health")
def record_health_check(
    region_id: str,
    request: RecordHealthCheckRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record health check.
    Records a health check result for a region.
    """
    try:
        result = MultiRegion.record_health_check(
            session=session,
            region_id=region_id,
            is_healthy=request.is_healthy,
            response_time_ms=request.response_time_ms,
            error_message=request.error_message
        )
        return {
            "success": True,
            "health_check": result,
            "message": "Healthy" if request.is_healthy else "Unhealthy"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error recording health check: {str(e)}")


@router.post("/deployments")
def create_deployment(
    request: CreateDeploymentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create deployment.
    Creates a new multi-region deployment.
    """
    try:
        result = MultiRegion.create_deployment(
            session=session,
            deployment_id=request.deployment_id,
            name=request.name,
            service_name=request.service_name,
            version=request.version,
            target_regions=request.target_regions,
            strategy=request.strategy,
            rollout_percentage=request.rollout_percentage,
            description=request.description
        )
        return {
            "success": True,
            "deployment": result,
            "message": f"Deployment created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating deployment: {str(e)}")


@router.post("/deployments/{deployment_id}/execute")
def execute_deployment(
    deployment_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Execute deployment.
    Executes a deployment across target regions.
    """
    try:
        result = MultiRegion.execute_deployment(
            session=session,
            deployment_id=deployment_id
        )
        return {
            "success": True,
            "deployment": result,
            "message": "Deployment executed"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing deployment: {str(e)}")


@router.get("/deployments/{deployment_id}")
def get_deployment_status(
    deployment_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get deployment status.
    Returns current status and progress of a deployment.
    """
    try:
        status = MultiRegion.get_deployment_status(
            session=session,
            deployment_id=deployment_id
        )
        return {
            "success": True,
            "status": status
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting deployment status: {str(e)}")


@router.get("/deployments")
def list_deployments(session: Session = Depends(get_db_session)):
    """
    List all deployments.
    Returns all multi-region deployments.
    """
    try:
        deployments = list(MultiRegion._deployments.values())
        return {
            "success": True,
            "deployments": deployments,
            "count": len(deployments)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing deployments: {str(e)}")


@router.post("/traffic-routing")
def configure_traffic_routing(
    request: ConfigureTrafficRoutingRequest,
    session: Session = Depends(get_db_session)
):
    """
    Configure traffic routing.
    Sets up traffic routing rules across regions.
    """
    try:
        result = MultiRegion.configure_traffic_routing(
            session=session,
            route_id=request.route_id,
            service_name=request.service_name,
            routing_mode=request.routing_mode,
            region_weights=request.region_weights
        )
        return {
            "success": True,
            "route": result,
            "message": "Traffic routing configured"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error configuring traffic routing: {str(e)}")


@router.get("/traffic-routing")
def list_traffic_routes(session: Session = Depends(get_db_session)):
    """
    List traffic routes.
    Returns all configured traffic routing rules.
    """
    try:
        routes = list(MultiRegion._traffic_routes.values())
        return {
            "success": True,
            "routes": routes,
            "count": len(routes)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing traffic routes: {str(e)}")


@router.post("/replication")
def update_replication_status(
    request: UpdateReplicationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update replication status.
    Updates cross-region replication status.
    """
    try:
        result = MultiRegion.update_replication_status(
            session=session,
            replication_id=request.replication_id,
            source_region=request.source_region,
            target_region=request.target_region,
            status=request.status,
            lag_seconds=request.lag_seconds,
            bytes_pending=request.bytes_pending
        )
        return {
            "success": True,
            "replication": result,
            "message": "Replication status updated"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating replication status: {str(e)}")


@router.get("/replication")
def list_replication_status(session: Session = Depends(get_db_session)):
    """
    List replication status.
    Returns all cross-region replication pairs.
    """
    try:
        replications = list(MultiRegion._replication_status.values())
        return {
            "success": True,
            "replications": replications,
            "count": len(replications)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing replication status: {str(e)}")


@router.post("/regions/{region_id}/failover")
def failover_region(
    region_id: str,
    request: FailoverRequest,
    session: Session = Depends(get_db_session)
):
    """
    Failover region.
    Initiates failover from one region to another.
    """
    try:
        result = MultiRegion.failover_region(
            session=session,
            source_region=region_id,
            target_region=request.target_region,
            reason=request.reason
        )
        return {
            "success": True,
            "failover": result,
            "message": f"Failover completed: {region_id} → {request.target_region}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during failover: {str(e)}")


@router.get("/global-status")
def get_global_status(session: Session = Depends(get_db_session)):
    """
    Get global status.
    Returns overall multi-region deployment status.
    """
    try:
        status = MultiRegion.get_global_status(session)
        return {
            "success": True,
            "global_status": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting global status: {str(e)}")


@router.get("/statistics")
def get_statistics(session: Session = Depends(get_db_session)):
    """
    Get statistics.
    Returns comprehensive multi-region statistics.
    """
    try:
        stats = MultiRegion.get_statistics(session)
        return {
            "success": True,
            "statistics": stats,
            "message": "Statistics retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")
