"""
Production Readiness and Deployment Validation API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.core.database import get_db_session
from src.services.production_readiness import (
    ProductionReadinessService,
    DeploymentEnvironment,
    CheckStatus
)


router = APIRouter()


# Request Models
class RunReadinessCheckRequest(BaseModel):
    """Request to run readiness check"""
    check_id: str
    environment: DeploymentEnvironment = DeploymentEnvironment.PRODUCTION


class ValidateDeploymentRequest(BaseModel):
    """Request to validate deployment"""
    validation_id: str
    environment: DeploymentEnvironment
    version: str


class RecordDeploymentRequest(BaseModel):
    """Request to record deployment"""
    deployment_id: str
    environment: DeploymentEnvironment
    version: str
    deployed_by: str
    metadata: Optional[Dict] = None


# Endpoints
@router.post("/production/readiness-check")
async def run_readiness_check(
    request: RunReadinessCheckRequest,
    session: Session = Depends(get_db_session)
):
    """
    Run comprehensive production readiness check.

    Validates infrastructure, database, security, performance, configuration,
    API endpoints, and dependencies for deployment readiness.
    """
    try:
        result = ProductionReadinessService.run_readiness_check(
            session=session,
            check_id=request.check_id,
            environment=request.environment
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/production/validate-deployment")
async def validate_deployment(
    request: ValidateDeploymentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Validate a deployment.

    Performs post-deployment validation including system health checks,
    API availability, database status, and smoke tests.
    """
    try:
        result = ProductionReadinessService.validate_deployment(
            session=session,
            validation_id=request.validation_id,
            environment=request.environment,
            version=request.version
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/production/deployment-checklist")
async def get_deployment_checklist(
    environment: DeploymentEnvironment = DeploymentEnvironment.PRODUCTION,
    session: Session = Depends(get_db_session)
):
    """
    Get deployment checklist.

    Returns pre-deployment, deployment, and post-deployment tasks
    with completion status for systematic deployment process.
    """
    try:
        result = ProductionReadinessService.get_deployment_checklist(
            session=session,
            environment=environment
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/production/record-deployment")
async def record_deployment(
    request: RecordDeploymentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record a deployment.

    Logs deployment information including version, environment,
    deployer, and deployment metadata for audit trail.
    """
    try:
        result = ProductionReadinessService.record_deployment(
            session=session,
            deployment_id=request.deployment_id,
            environment=request.environment,
            version=request.version,
            deployed_by=request.deployed_by,
            metadata=request.metadata
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/production/system-overview")
async def get_system_overview(
    session: Session = Depends(get_db_session)
):
    """
    Get comprehensive system overview.

    Returns platform information, implementation statistics,
    architecture details, API metrics, and feature flags.

    This endpoint provides a complete snapshot of the system's
    current state and capabilities.
    """
    try:
        result = ProductionReadinessService.get_system_overview(session=session)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/production/statistics")
async def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get production readiness statistics.

    Returns:
    - Readiness check metrics
    - Deployment history
    - Validation results
    - Platform status
    """
    try:
        result = ProductionReadinessService.get_statistics(session=session)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
