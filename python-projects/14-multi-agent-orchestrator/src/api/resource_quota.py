"""
Resource Quota Management API

REST API endpoints for resource allocation, quota enforcement, and usage tracking.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from src.database import get_db_session
from src.services.resource_quota import (
    ResourceQuota,
    ResourceType,
    QuotaPeriod,
    EnforcementAction
)


router = APIRouter()


# Request/Response Models
class CreateQuotaRequest(BaseModel):
    """Request model for creating a quota"""
    quota_id: str = Field(..., description="Unique quota identifier")
    name: str = Field(..., description="Quota name")
    tenant_id: str = Field(..., description="Tenant identifier")
    resource_type: ResourceType = Field(..., description="Type of resource")
    limit: float = Field(..., description="Quota limit", gt=0)
    warning_threshold: float = Field(default=80.0, description="Warning threshold percentage", ge=0, le=100)
    reset_period: QuotaPeriod = Field(default=QuotaPeriod.MONTHLY, description="Reset period")
    enforcement_action: EnforcementAction = Field(default=EnforcementAction.BLOCK, description="Enforcement action")
    description: Optional[str] = Field(default=None, description="Quota description")


class RecordUsageRequest(BaseModel):
    """Request model for recording usage"""
    amount: float = Field(..., description="Amount of resource used", gt=0)
    metadata: Optional[Dict] = Field(default=None, description="Additional metadata")


class CheckQuotaRequest(BaseModel):
    """Request model for checking quota"""
    amount: float = Field(..., description="Amount to check", gt=0)


class UpdateQuotaRequest(BaseModel):
    """Request model for updating a quota"""
    limit: Optional[float] = Field(default=None, description="New limit", gt=0)
    warning_threshold: Optional[float] = Field(default=None, description="New warning threshold", ge=0, le=100)
    enforcement_action: Optional[EnforcementAction] = Field(default=None, description="New enforcement action")
    is_enabled: Optional[bool] = Field(default=None, description="Enable/disable quota")


class CreateOverrideRequest(BaseModel):
    """Request model for creating quota override"""
    override_id: str = Field(..., description="Unique override identifier")
    temporary_limit: float = Field(..., description="Temporary limit", gt=0)
    expires_at: str = Field(..., description="Expiration time (ISO)")
    reason: str = Field(..., description="Reason for override")


# API Endpoints
@router.post("/quotas")
def create_quota(
    request: CreateQuotaRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a resource quota.
    Defines limits for resource usage per tenant with automatic enforcement.
    """
    try:
        result = ResourceQuota.create_quota(
            session=session,
            quota_id=request.quota_id,
            name=request.name,
            tenant_id=request.tenant_id,
            resource_type=request.resource_type,
            limit=request.limit,
            warning_threshold=request.warning_threshold,
            reset_period=request.reset_period,
            enforcement_action=request.enforcement_action,
            description=request.description
        )
        return {
            "success": True,
            "quota": result,
            "message": f"Quota created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating quota: {str(e)}")


@router.get("/quotas")
def list_quotas(session: Session = Depends(get_db_session)):
    """
    List all quotas.
    Returns all defined resource quotas across all tenants.
    """
    try:
        quotas = list(ResourceQuota._quotas.values())
        return {
            "success": True,
            "quotas": quotas,
            "count": len(quotas)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing quotas: {str(e)}")


@router.get("/quotas/{quota_id}")
def get_quota(
    quota_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get quota details.
    Returns detailed information about a specific quota.
    """
    try:
        quota = ResourceQuota._quotas.get(quota_id)
        if not quota:
            raise HTTPException(status_code=404, detail=f"Quota not found: {quota_id}")

        return {
            "success": True,
            "quota": quota
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting quota: {str(e)}")


@router.put("/quotas/{quota_id}")
def update_quota(
    quota_id: str,
    request: UpdateQuotaRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update quota parameters.
    Modifies quota limits, thresholds, or enforcement actions.
    """
    try:
        result = ResourceQuota.update_quota(
            session=session,
            quota_id=quota_id,
            limit=request.limit,
            warning_threshold=request.warning_threshold,
            enforcement_action=request.enforcement_action,
            is_enabled=request.is_enabled
        )
        return {
            "success": True,
            "quota": result,
            "message": "Quota updated successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating quota: {str(e)}")


@router.get("/quotas/{quota_id}/status")
def get_quota_status(
    quota_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get quota status.
    Returns current usage, remaining capacity, and trend analysis.
    """
    try:
        status = ResourceQuota.get_quota_status(
            session=session,
            quota_id=quota_id
        )
        return {
            "success": True,
            "status": status
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting quota status: {str(e)}")


@router.post("/quotas/{quota_id}/usage")
def record_usage(
    quota_id: str,
    request: RecordUsageRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record resource usage.
    Records usage against a quota and enforces limits.
    """
    try:
        result = ResourceQuota.record_usage(
            session=session,
            quota_id=quota_id,
            amount=request.amount,
            metadata=request.metadata
        )

        message = "Usage recorded"
        if not result["can_proceed"]:
            message = f"Usage blocked - quota exceeded (action: {result['action_taken']})"
        elif result["action_taken"]:
            message = f"Usage recorded with action: {result['action_taken']}"

        return {
            "success": result["can_proceed"],
            "usage_record": result,
            "message": message
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error recording usage: {str(e)}")


@router.post("/quotas/{quota_id}/check")
def check_quota(
    quota_id: str,
    request: CheckQuotaRequest,
    session: Session = Depends(get_db_session)
):
    """
    Check quota availability.
    Checks if a quota allows a certain amount without recording usage.
    """
    try:
        result = ResourceQuota.check_quota(
            session=session,
            quota_id=quota_id,
            amount=request.amount
        )
        return {
            "success": True,
            "check_result": result,
            "message": "Allowed" if result["is_allowed"] else "Would exceed quota"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking quota: {str(e)}")


@router.post("/quotas/{quota_id}/reset")
def reset_quota(
    quota_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Reset quota usage.
    Manually resets quota usage to zero.
    """
    try:
        result = ResourceQuota.reset_quota(
            session=session,
            quota_id=quota_id
        )
        return {
            "success": True,
            "reset": result,
            "message": "Quota reset successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error resetting quota: {str(e)}")


@router.get("/tenants/{tenant_id}/quotas")
def get_tenant_quotas(
    tenant_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get tenant quotas.
    Returns all quotas for a specific tenant.
    """
    try:
        quotas = ResourceQuota.get_tenant_quotas(
            session=session,
            tenant_id=tenant_id
        )
        return {
            "success": True,
            "quotas": quotas,
            "count": len(quotas)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting tenant quotas: {str(e)}")


@router.get("/tenants/{tenant_id}/summary")
def get_tenant_summary(
    tenant_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get tenant summary.
    Returns quota summary and resource usage overview for a tenant.
    """
    try:
        summary = ResourceQuota.get_tenant_summary(
            session=session,
            tenant_id=tenant_id
        )
        return {
            "success": True,
            "summary": summary
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting tenant summary: {str(e)}")


@router.post("/quotas/{quota_id}/overrides")
def create_override(
    quota_id: str,
    request: CreateOverrideRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create quota override.
    Creates a temporary quota limit increase with expiration.
    """
    try:
        result = ResourceQuota.create_quota_override(
            session=session,
            override_id=request.override_id,
            quota_id=quota_id,
            temporary_limit=request.temporary_limit,
            expires_at=request.expires_at,
            reason=request.reason
        )
        return {
            "success": True,
            "override": result,
            "message": "Quota override created"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating override: {str(e)}")


@router.delete("/overrides/{override_id}")
def remove_override(
    override_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Remove quota override.
    Removes a temporary quota override and restores original limit.
    """
    try:
        result = ResourceQuota.remove_quota_override(
            session=session,
            override_id=override_id
        )
        return {
            "success": True,
            "removal": result,
            "message": "Override removed successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error removing override: {str(e)}")


@router.get("/violations")
def get_violations(
    tenant_id: Optional[str] = None,
    quota_id: Optional[str] = None,
    resolved: Optional[bool] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get quota violations.
    Returns quota violations with optional filtering.
    """
    try:
        violations = ResourceQuota.get_violations(
            session=session,
            tenant_id=tenant_id,
            quota_id=quota_id,
            resolved=resolved
        )
        return {
            "success": True,
            "violations": violations,
            "count": len(violations)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting violations: {str(e)}")


@router.get("/usage-history")
def get_usage_history(
    quota_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
    resource_type: Optional[ResourceType] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    session: Session = Depends(get_db_session)
):
    """
    Get usage history.
    Returns historical resource usage records with optional filtering.
    """
    try:
        history = ResourceQuota.get_usage_history(
            session=session,
            quota_id=quota_id,
            tenant_id=tenant_id,
            resource_type=resource_type,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        return {
            "success": True,
            "usage_history": history,
            "count": len(history)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting usage history: {str(e)}")


@router.get("/statistics")
def get_statistics(session: Session = Depends(get_db_session)):
    """
    Get statistics.
    Returns comprehensive quota management statistics.
    """
    try:
        stats = ResourceQuota.get_statistics(session)
        return {
            "success": True,
            "statistics": stats,
            "message": "Statistics retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")
