"""
API Gateway and Service Mesh API

REST API endpoints for API gateway and service mesh management.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.api_gateway import (
    APIGateway,
    RouteMethod,
    LoadBalancingStrategy
)


router = APIRouter()


# Request/Response Models
class RegisterServiceRequest(BaseModel):
    """Request model for registering a service"""
    service_id: str = Field(..., description="Unique service identifier")
    name: str = Field(..., description="Service name")
    version: str = Field(..., description="Service version")
    base_url: str = Field(..., description="Base URL of the service")
    health_check_path: str = Field(default="/health", description="Health check endpoint path")
    timeout_ms: int = Field(default=5000, description="Request timeout in milliseconds", ge=100)
    metadata: Optional[Dict] = Field(default=None, description="Additional metadata")


class CreateRouteRequest(BaseModel):
    """Request model for creating a route"""
    route_id: str = Field(..., description="Unique route identifier")
    path: str = Field(..., description="API path pattern")
    method: RouteMethod = Field(..., description="HTTP method")
    service_id: str = Field(..., description="Target service ID")
    upstream_path: Optional[str] = Field(default=None, description="Upstream path (defaults to path)")
    version: Optional[str] = Field(default=None, description="API version")
    load_balancing: LoadBalancingStrategy = Field(default=LoadBalancingStrategy.ROUND_ROBIN, description="Load balancing strategy")
    rate_limit_per_minute: int = Field(default=0, description="Rate limit per minute (0 = unlimited)", ge=0)
    require_auth: bool = Field(default=False, description="Whether authentication is required")
    enable_circuit_breaker: bool = Field(default=True, description="Enable circuit breaker")
    description: Optional[str] = Field(default=None, description="Route description")


class RouteRequestRequest(BaseModel):
    """Request model for routing a request"""
    request_data: Dict = Field(..., description="Request payload")
    headers: Optional[Dict] = Field(default=None, description="Request headers")


class CreateTransformationRequest(BaseModel):
    """Request model for creating a transformation"""
    transformation_id: str = Field(..., description="Unique transformation identifier")
    route_id: str = Field(..., description="Route ID")
    transform_type: str = Field(..., description="Transformation type")
    config: Dict = Field(..., description="Transformation configuration")


class RegisterInstanceRequest(BaseModel):
    """Request model for registering a service instance"""
    instance_id: str = Field(..., description="Unique instance identifier")
    host: str = Field(..., description="Instance host")
    port: int = Field(..., description="Instance port", ge=1, le=65535)
    weight: int = Field(default=1, description="Load balancing weight", ge=1)
    metadata: Optional[Dict] = Field(default=None, description="Additional metadata")


# API Endpoints
@router.post("/services")
def register_service(
    request: RegisterServiceRequest,
    session: Session = Depends(get_db_session)
):
    """
    Register service.
    Registers a backend service for API gateway routing.
    """
    try:
        result = APIGateway.register_service(
            session=session,
            service_id=request.service_id,
            name=request.name,
            version=request.version,
            base_url=request.base_url,
            health_check_path=request.health_check_path,
            timeout_ms=request.timeout_ms,
            metadata=request.metadata
        )
        return {
            "success": True,
            "service": result,
            "message": f"Service registered: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error registering service: {str(e)}")


@router.get("/services")
def list_services(session: Session = Depends(get_db_session)):
    """
    List services.
    Returns all registered backend services.
    """
    try:
        services = list(APIGateway._services.values())
        return {
            "success": True,
            "services": services,
            "count": len(services)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing services: {str(e)}")


@router.get("/services/{service_id}/health")
def get_service_health(
    service_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get service health.
    Returns health status and metrics for a service.
    """
    try:
        health = APIGateway.get_service_health(
            session=session,
            service_id=service_id
        )
        return {
            "success": True,
            "health": health
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting service health: {str(e)}")


@router.post("/routes")
def create_route(
    request: CreateRouteRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create route.
    Creates a new API route with traffic management configuration.
    """
    try:
        result = APIGateway.create_route(
            session=session,
            route_id=request.route_id,
            path=request.path,
            method=request.method,
            service_id=request.service_id,
            upstream_path=request.upstream_path,
            version=request.version,
            load_balancing=request.load_balancing,
            rate_limit_per_minute=request.rate_limit_per_minute,
            require_auth=request.require_auth,
            enable_circuit_breaker=request.enable_circuit_breaker,
            description=request.description
        )
        return {
            "success": True,
            "route": result,
            "message": f"Route created: {request.path}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating route: {str(e)}")


@router.get("/routes")
def list_routes(session: Session = Depends(get_db_session)):
    """
    List routes.
    Returns all configured API routes.
    """
    try:
        routes = list(APIGateway._routes.values())
        return {
            "success": True,
            "routes": routes,
            "count": len(routes)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing routes: {str(e)}")


@router.get("/routes/{route_id}/stats")
def get_route_stats(
    route_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get route statistics.
    Returns metrics and performance statistics for a route.
    """
    try:
        stats = APIGateway.get_route_stats(
            session=session,
            route_id=route_id
        )
        return {
            "success": True,
            "stats": stats
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting route stats: {str(e)}")


@router.post("/routes/{route_id}/request")
def route_request(
    route_id: str,
    request: RouteRequestRequest,
    session: Session = Depends(get_db_session)
):
    """
    Route request.
    Routes a request through the API gateway to the backend service.
    """
    try:
        result = APIGateway.route_request(
            session=session,
            route_id=route_id,
            request_data=request.request_data,
            headers=request.headers
        )
        return {
            "success": result["success"],
            "response": result,
            "message": "Request routed successfully" if result["success"] else "Request failed"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error routing request: {str(e)}")


@router.post("/transformations")
def create_transformation(
    request: CreateTransformationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create transformation.
    Creates a request/response transformation rule for a route.
    """
    try:
        result = APIGateway.create_transformation(
            session=session,
            transformation_id=request.transformation_id,
            route_id=request.route_id,
            transform_type=request.transform_type,
            config=request.config
        )
        return {
            "success": True,
            "transformation": result,
            "message": "Transformation created"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating transformation: {str(e)}")


@router.get("/transformations")
def list_transformations(session: Session = Depends(get_db_session)):
    """
    List transformations.
    Returns all configured request/response transformations.
    """
    try:
        transformations = list(APIGateway._transformations.values())
        return {
            "success": True,
            "transformations": transformations,
            "count": len(transformations)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing transformations: {str(e)}")


@router.post("/services/{service_id}/instances")
def register_instance(
    service_id: str,
    request: RegisterInstanceRequest,
    session: Session = Depends(get_db_session)
):
    """
    Register service instance.
    Registers a new instance of a service for load balancing.
    """
    try:
        result = APIGateway.register_service_instance(
            session=session,
            service_id=service_id,
            instance_id=request.instance_id,
            host=request.host,
            port=request.port,
            weight=request.weight,
            metadata=request.metadata
        )
        return {
            "success": True,
            "instance": result,
            "message": f"Instance registered: {request.instance_id}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error registering instance: {str(e)}")


@router.get("/services/{service_id}/instances")
def list_instances(
    service_id: str,
    session: Session = Depends(get_db_session)
):
    """
    List service instances.
    Returns all registered instances for a service.
    """
    try:
        instances = APIGateway._service_instances.get(service_id, [])
        return {
            "success": True,
            "instances": instances,
            "count": len(instances)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing instances: {str(e)}")


@router.get("/circuit-breakers")
def list_circuit_breakers(session: Session = Depends(get_db_session)):
    """
    List circuit breakers.
    Returns all circuit breaker states.
    """
    try:
        breakers = list(APIGateway._circuit_breakers.values())
        return {
            "success": True,
            "circuit_breakers": breakers,
            "count": len(breakers)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing circuit breakers: {str(e)}")


@router.get("/gateway-stats")
def get_gateway_stats(session: Session = Depends(get_db_session)):
    """
    Get gateway statistics.
    Returns overall API gateway statistics and metrics.
    """
    try:
        stats = APIGateway.get_gateway_stats(session)
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting gateway stats: {str(e)}")


@router.get("/statistics")
def get_statistics(session: Session = Depends(get_db_session)):
    """
    Get statistics.
    Returns comprehensive API gateway statistics.
    """
    try:
        stats = APIGateway.get_statistics(session)
        return {
            "success": True,
            "statistics": stats,
            "message": "Statistics retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")
