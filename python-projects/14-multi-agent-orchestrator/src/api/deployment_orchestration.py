"""
Deployment and Container Orchestration API

REST API endpoints for deployment management and container orchestration.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.deployment_orchestration import (
    DeploymentOrchestration,
    DeploymentStrategy,
    DeploymentStatus,
    Environment,
    ContainerStatus,
    InfrastructureProvider
)


router = APIRouter()


# Request/Response Models
class CreateDeploymentRequest(BaseModel):
    deployment_name: str = Field(..., description="Deployment name")
    environment: str = Field(..., description="Target environment")
    version: str = Field(..., description="Application version")
    strategy: str = Field(DeploymentStrategy.ROLLING, description="Deployment strategy")
    image: Optional[str] = Field(None, description="Container image")
    replicas: int = Field(3, description="Number of replicas", ge=1, le=100)
    configuration: Optional[dict] = Field(None, description="Deployment configuration")


class ExecuteDeploymentRequest(BaseModel):
    auto_rollback_on_failure: bool = Field(True, description="Enable automatic rollback on failure")


class CreateContainerRequest(BaseModel):
    container_name: str = Field(..., description="Container name")
    image: str = Field(..., description="Container image")
    port_mappings: Optional[List[dict]] = Field(None, description="Port mappings")
    environment_vars: Optional[dict] = Field(None, description="Environment variables")
    resource_limits: Optional[dict] = Field(None, description="Resource limits")


class ScaleDeploymentRequest(BaseModel):
    target_replicas: int = Field(..., description="Target number of replicas", ge=0, le=100)


class RollbackRequest(BaseModel):
    target_version: Optional[str] = Field(None, description="Target version (defaults to previous)")


class CreateInfrastructureRequest(BaseModel):
    environment: str = Field(..., description="Target environment")
    provider: str = Field(..., description="Cloud provider")
    region: str = Field(..., description="Geographic region")
    configuration: dict = Field(..., description="Infrastructure configuration")


@router.post("/deployments")
def create_deployment(
    request: CreateDeploymentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a new deployment.

    Initializes a new deployment configuration for the specified environment
    with the chosen deployment strategy.
    """
    try:
        deployment = DeploymentOrchestration.create_deployment(
            session=session,
            deployment_name=request.deployment_name,
            environment=request.environment,
            version=request.version,
            strategy=request.strategy,
            image=request.image,
            replicas=request.replicas,
            configuration=request.configuration
        )

        return {
            "success": True,
            "deployment": deployment,
            "message": f"Deployment created: {deployment['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deployments/{deployment_id}/execute")
def execute_deployment(
    deployment_id: str,
    request: ExecuteDeploymentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Execute a deployment.

    Starts the deployment process using the configured strategy
    with optional automatic rollback on failure.
    """
    try:
        result = DeploymentOrchestration.execute_deployment(
            session=session,
            deployment_id=deployment_id,
            auto_rollback_on_failure=request.auto_rollback_on_failure
        )

        return {
            "success": True,
            "deployment": result,
            "message": f"Deployment executed: {result['status']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deployments/{deployment_id}/containers")
def create_container(
    deployment_id: str,
    request: CreateContainerRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a container instance.

    Launches a new container as part of the deployment with
    specified resource limits and configuration.
    """
    try:
        container = DeploymentOrchestration.create_container(
            session=session,
            deployment_id=deployment_id,
            container_name=request.container_name,
            image=request.image,
            port_mappings=request.port_mappings,
            environment_vars=request.environment_vars,
            resource_limits=request.resource_limits
        )

        return {
            "success": True,
            "container": container,
            "message": f"Container created: {container['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deployments/{deployment_id}/scale")
def scale_deployment(
    deployment_id: str,
    request: ScaleDeploymentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Scale deployment replicas.

    Scales the number of running replicas up or down
    to match the target count.
    """
    try:
        result = DeploymentOrchestration.scale_deployment(
            session=session,
            deployment_id=deployment_id,
            target_replicas=request.target_replicas
        )

        return {
            "success": True,
            "scaling": result,
            "message": f"Scaled from {result['from_replicas']} to {result['to_replicas']} replicas"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deployments/{deployment_id}/rollback")
def rollback_deployment(
    deployment_id: str,
    request: RollbackRequest,
    session: Session = Depends(get_db_session)
):
    """
    Rollback deployment to previous version.

    Reverts the deployment to the specified version or
    the previous stable version if not specified.
    """
    try:
        result = DeploymentOrchestration.rollback_deployment(
            session=session,
            deployment_id=deployment_id,
            target_version=request.target_version
        )

        return {
            "success": True,
            "rollback": result,
            "message": f"Rolled back from {result['from_version']} to {result['to_version']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/infrastructure")
def create_infrastructure(
    request: CreateInfrastructureRequest,
    session: Session = Depends(get_db_session)
):
    """
    Provision infrastructure.

    Provisions cloud infrastructure resources for the
    specified environment using Infrastructure as Code.
    """
    try:
        infrastructure = DeploymentOrchestration.create_infrastructure(
            session=session,
            environment=request.environment,
            provider=request.provider,
            region=request.region,
            configuration=request.configuration
        )

        return {
            "success": True,
            "infrastructure": infrastructure,
            "message": f"Infrastructure provisioned: {infrastructure['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deployments/{deployment_id}/health")
def perform_health_check(
    deployment_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Perform deployment health check.

    Runs comprehensive health checks on the deployment
    including replica availability, response time, and error rates.
    """
    try:
        health = DeploymentOrchestration.perform_health_check(
            session=session,
            deployment_id=deployment_id
        )

        return {
            "success": True,
            "health_check": health
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deployments/{deployment_id}/logs")
def get_deployment_logs(
    deployment_id: str,
    limit: int = 100,
    level: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get deployment logs.

    Retrieves logs from all containers in the deployment
    with optional filtering by log level.
    """
    try:
        logs = DeploymentOrchestration.get_deployment_logs(
            session=session,
            deployment_id=deployment_id,
            limit=limit,
            level=level
        )

        return {
            "success": True,
            **logs
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deployments/{deployment_id}/metrics")
def get_deployment_metrics(
    deployment_id: str,
    time_range_minutes: int = 60,
    session: Session = Depends(get_db_session)
):
    """
    Get deployment metrics.

    Returns time-series metrics for CPU, memory, request rate,
    and error rate over the specified time range.
    """
    try:
        metrics = DeploymentOrchestration.get_deployment_metrics(
            session=session,
            deployment_id=deployment_id,
            time_range_minutes=time_range_minutes
        )

        return {
            "success": True,
            **metrics
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deployments/{deployment_name}/history")
def get_deployment_history(
    deployment_name: str,
    limit: int = 10,
    session: Session = Depends(get_db_session)
):
    """
    Get deployment history.

    Returns the deployment history for a specific application
    showing all versions deployed over time.
    """
    try:
        history = DeploymentOrchestration.get_deployment_history(
            session=session,
            deployment_name=deployment_name,
            limit=limit
        )

        return {
            "success": True,
            **history
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get deployment orchestration statistics.

    Returns aggregate statistics including deployment counts,
    success rates, and resource utilization.
    """
    try:
        stats = DeploymentOrchestration.get_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies")
def list_deployment_strategies():
    """
    List all deployment strategies.

    Returns all available deployment strategy options.
    """
    return {
        "success": True,
        "strategies": [
            {"strategy": DeploymentStrategy.ROLLING, "description": "Rolling update with gradual replica replacement"},
            {"strategy": DeploymentStrategy.BLUE_GREEN, "description": "Deploy to parallel environment then switch"},
            {"strategy": DeploymentStrategy.CANARY, "description": "Deploy to small subset before full rollout"},
            {"strategy": DeploymentStrategy.RECREATE, "description": "Stop all replicas then deploy new version"},
            {"strategy": DeploymentStrategy.A_B_TESTING, "description": "Split traffic between versions"}
        ]
    }


@router.get("/environments")
def list_environments():
    """
    List all environments.

    Returns all available deployment environments.
    """
    return {
        "success": True,
        "environments": [
            {"environment": Environment.DEVELOPMENT, "description": "Development environment"},
            {"environment": Environment.STAGING, "description": "Staging environment"},
            {"environment": Environment.PRODUCTION, "description": "Production environment"},
            {"environment": Environment.QA, "description": "QA testing environment"},
            {"environment": Environment.UAT, "description": "User acceptance testing environment"}
        ]
    }


@router.get("/providers")
def list_infrastructure_providers():
    """
    List all infrastructure providers.

    Returns all supported cloud infrastructure providers.
    """
    return {
        "success": True,
        "providers": [
            {"provider": InfrastructureProvider.AWS, "description": "Amazon Web Services"},
            {"provider": InfrastructureProvider.GCP, "description": "Google Cloud Platform"},
            {"provider": InfrastructureProvider.AZURE, "description": "Microsoft Azure"},
            {"provider": InfrastructureProvider.KUBERNETES, "description": "Kubernetes clusters"},
            {"provider": InfrastructureProvider.DOCKER, "description": "Docker containers"},
            {"provider": InfrastructureProvider.DIGITAL_OCEAN, "description": "DigitalOcean"}
        ]
    }
