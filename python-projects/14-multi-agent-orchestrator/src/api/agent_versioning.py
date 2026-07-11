"""
Agent Versioning and Rollback API

REST API endpoints for agent version control, deployment, and rollback management.
"""

from typing import Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_versioning import (
    AgentVersioning,
    VersionStatus,
    DeploymentStrategy,
    DeploymentStatus,
    RollbackReason
)


router = APIRouter()


# Request/Response Models
class CreateVersionRequest(BaseModel):
    agent_id: str = Field(..., description="Agent ID")
    version_number: str = Field(..., description="Version number (e.g., '1.2.3')")
    code_hash: str = Field(..., description="Hash of agent code")
    configuration: dict = Field(..., description="Version configuration")
    dependencies: Optional[list] = Field(None, description="List of dependencies")
    description: Optional[str] = Field(None, description="Version description")
    changelog: Optional[str] = Field(None, description="Change log")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class DeployVersionRequest(BaseModel):
    strategy: str = Field(DeploymentStrategy.IMMEDIATE, description="Deployment strategy")
    target_percentage: Optional[int] = Field(None, description="Target traffic percentage (for canary)")
    schedule_at: Optional[str] = Field(None, description="Schedule deployment time (ISO format)")
    validation_checks: Optional[list] = Field(None, description="Pre-deployment validation checks")
    rollback_on_error: bool = Field(True, description="Auto-rollback on error")


class RollbackVersionRequest(BaseModel):
    target_version_id: Optional[str] = Field(None, description="Optional specific version to rollback to")
    reason: str = Field(RollbackReason.USER_REQUEST, description="Rollback reason")
    description: Optional[str] = Field(None, description="Rollback description")


class PromoteCanaryRequest(BaseModel):
    target_percentage: int = Field(100, description="Target traffic percentage")


class DeprecateVersionRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Deprecation reason")


@router.post("/versions")
def create_version(
    request: CreateVersionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create agent version.

    Creates a new version of an agent with code, configuration, and dependencies.
    """
    try:
        version = AgentVersioning.create_version(
            session=session,
            agent_id=request.agent_id,
            version_number=request.version_number,
            code_hash=request.code_hash,
            configuration=request.configuration,
            dependencies=request.dependencies,
            description=request.description,
            changelog=request.changelog,
            metadata=request.metadata
        )

        return {
            "success": True,
            "version": version,
            "message": f"Version created: {version['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/versions/{version_id}/deploy")
def deploy_version(
    version_id: str,
    request: DeployVersionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Deploy version.

    Deploys an agent version using specified strategy (immediate, canary, blue-green, etc.).
    """
    try:
        # Parse schedule_at if provided
        schedule_at = None
        if request.schedule_at:
            schedule_at = datetime.fromisoformat(request.schedule_at)

        deployment = AgentVersioning.deploy_version(
            session=session,
            version_id=version_id,
            strategy=request.strategy,
            target_percentage=request.target_percentage,
            schedule_at=schedule_at,
            validation_checks=request.validation_checks,
            rollback_on_error=request.rollback_on_error
        )

        return {
            "success": True,
            "deployment": deployment,
            "message": f"Deployment initiated: {deployment['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/rollback")
def rollback_version(
    agent_id: str,
    request: RollbackVersionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Rollback version.

    Rolls back to a previous version or a specific target version.
    """
    try:
        rollback = AgentVersioning.rollback_version(
            session=session,
            agent_id=agent_id,
            target_version_id=request.target_version_id,
            reason=request.reason,
            description=request.description
        )

        return {
            "success": True,
            "rollback": rollback,
            "message": f"Rolled back to version {rollback['to_version_number']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/versions")
def get_version_history(
    agent_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    Get version history.

    Returns version history for an agent with optional status filter.
    """
    try:
        result = AgentVersioning.get_version_history(
            session=session,
            agent_id=agent_id,
            status=status,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/deployments/{deployment_id}")
def get_deployment_status(
    deployment_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get deployment status.

    Returns detailed status of a deployment including progress and metrics.
    """
    try:
        deployment = AgentVersioning.get_deployment_status(
            session=session,
            deployment_id=deployment_id
        )

        return {
            "success": True,
            "deployment": deployment
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deployments/{deployment_id}/promote")
def promote_canary(
    deployment_id: str,
    request: PromoteCanaryRequest,
    session: Session = Depends(get_db_session)
):
    """
    Promote canary deployment.

    Increases traffic percentage for canary deployment or completes it.
    """
    try:
        deployment = AgentVersioning.promote_canary(
            session=session,
            deployment_id=deployment_id,
            target_percentage=request.target_percentage
        )

        return {
            "success": True,
            "deployment": deployment,
            "message": f"Canary promoted to {deployment['current_percentage']}%"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/versions/{version_id}/compare/{other_version_id}")
def compare_versions(
    version_id: str,
    other_version_id: str,
    include_diff: bool = True,
    session: Session = Depends(get_db_session)
):
    """
    Compare versions.

    Compares two versions and returns differences in code, configuration, and dependencies.
    """
    try:
        comparison = AgentVersioning.compare_versions(
            session=session,
            version_id_1=version_id,
            version_id_2=other_version_id,
            include_diff=include_diff
        )

        return {
            "success": True,
            "comparison": comparison
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/versions/{version_id}/deprecate")
def deprecate_version(
    version_id: str,
    request: DeprecateVersionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Deprecate version.

    Marks a version as deprecated (cannot deprecate current active version).
    """
    try:
        version = AgentVersioning.deprecate_version(
            session=session,
            version_id=version_id,
            reason=request.reason
        )

        return {
            "success": True,
            "version": version,
            "message": f"Version deprecated: {version_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rollbacks")
def list_rollbacks(
    agent_id: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    List rollbacks.

    Returns rollback history with optional agent filter.
    """
    try:
        result = AgentVersioning.list_rollbacks(
            session=session,
            agent_id=agent_id,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get versioning statistics.

    Returns aggregate metrics including version counts, deployment stats,
    and rollback history.
    """
    try:
        stats = AgentVersioning.get_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/version-statuses")
def list_version_statuses():
    """
    List all version statuses.

    Returns all possible version status values.
    """
    return {
        "success": True,
        "version_statuses": [
            {"status": VersionStatus.DRAFT, "description": "Version is in draft state"},
            {"status": VersionStatus.ACTIVE, "description": "Version is currently active"},
            {"status": VersionStatus.DEPRECATED, "description": "Version is deprecated"},
            {"status": VersionStatus.RETIRED, "description": "Version is retired"}
        ]
    }


@router.get("/deployment-strategies")
def list_deployment_strategies():
    """
    List all deployment strategies.

    Returns all available deployment strategies.
    """
    return {
        "success": True,
        "deployment_strategies": [
            {"strategy": DeploymentStrategy.IMMEDIATE, "description": "Immediate full deployment"},
            {"strategy": DeploymentStrategy.CANARY, "description": "Gradual canary deployment with traffic splitting"},
            {"strategy": DeploymentStrategy.BLUE_GREEN, "description": "Blue-green deployment with instant switchover"},
            {"strategy": DeploymentStrategy.ROLLING, "description": "Rolling deployment across instances"},
            {"strategy": DeploymentStrategy.SCHEDULED, "description": "Scheduled deployment at specific time"}
        ]
    }


@router.get("/deployment-statuses")
def list_deployment_statuses():
    """
    List all deployment statuses.

    Returns all possible deployment status values.
    """
    return {
        "success": True,
        "deployment_statuses": [
            {"status": DeploymentStatus.PENDING, "description": "Deployment is pending"},
            {"status": DeploymentStatus.IN_PROGRESS, "description": "Deployment in progress"},
            {"status": DeploymentStatus.COMPLETED, "description": "Deployment completed successfully"},
            {"status": DeploymentStatus.FAILED, "description": "Deployment failed"},
            {"status": DeploymentStatus.ROLLED_BACK, "description": "Deployment rolled back"}
        ]
    }


@router.get("/rollback-reasons")
def list_rollback_reasons():
    """
    List all rollback reasons.

    Returns common rollback reason categories.
    """
    return {
        "success": True,
        "rollback_reasons": [
            {"reason": RollbackReason.ERRORS, "description": "Errors detected after deployment"},
            {"reason": RollbackReason.PERFORMANCE_DEGRADATION, "description": "Performance degradation observed"},
            {"reason": RollbackReason.USER_REQUEST, "description": "Manual user request"},
            {"reason": RollbackReason.VALIDATION_FAILURE, "description": "Validation checks failed"},
            {"reason": RollbackReason.EMERGENCY, "description": "Emergency rollback"}
        ]
    }
