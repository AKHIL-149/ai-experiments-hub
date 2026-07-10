"""
API Rate Limiting and Quota Management API

REST API endpoints for rate limiting and quota management.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.api_rate_limiting import (
    APIRateLimiting,
    QuotaTier,
    QuotaPeriod,
    LimitStatus
)


router = APIRouter()


# Request/Response Models
class CreateQuotaPlanRequest(BaseModel):
    name: str = Field(..., description="Plan name")
    tier: str = Field(..., description="Quota tier")
    limits: dict = Field(..., description="Rate limits configuration")
    description: Optional[str] = Field(None, description="Plan description")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class AssignQuotaRequest(BaseModel):
    tier: str = Field(..., description="Quota tier")
    plan_id: Optional[str] = Field(None, description="Custom plan ID")
    custom_limits: Optional[dict] = Field(None, description="Custom limits override")


class RecordRequestRequest(BaseModel):
    endpoint: str = Field(..., description="API endpoint")
    response_status: int = Field(..., description="HTTP response status")
    response_time_ms: Optional[float] = Field(None, description="Response time in milliseconds")


class CreateQuotaOverrideRequest(BaseModel):
    custom_limits: dict = Field(..., description="Custom limits to apply")
    duration_hours: Optional[int] = Field(None, description="Override duration (None = permanent)")
    reason: Optional[str] = Field(None, description="Override reason")


class BlockUserRequest(BaseModel):
    duration_hours: int = Field(..., description="Block duration in hours")
    reason: Optional[str] = Field(None, description="Block reason")


@router.post("/plans")
def create_quota_plan(
    request: CreateQuotaPlanRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a custom quota plan.

    Defines a reusable quota plan with specific rate limits
    that can be assigned to multiple users.
    """
    try:
        plan = APIRateLimiting.create_quota_plan(
            session=session,
            name=request.name,
            tier=request.tier,
            limits=request.limits,
            description=request.description,
            metadata=request.metadata
        )

        return {
            "success": True,
            "plan": plan,
            "message": f"Quota plan created: {plan['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quotas/{user_id}")
def assign_quota(
    user_id: str,
    request: AssignQuotaRequest,
    session: Session = Depends(get_db_session)
):
    """
    Assign quota to a user.

    Assigns a quota tier and limits to a specific user,
    optionally using a custom plan or custom limits.
    """
    try:
        quota = APIRateLimiting.assign_quota(
            session=session,
            user_id=user_id,
            tier=request.tier,
            plan_id=request.plan_id,
            custom_limits=request.custom_limits
        )

        return {
            "success": True,
            "quota": quota,
            "message": f"Quota assigned to user {user_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quotas/{user_id}/check")
def check_rate_limit(
    user_id: str,
    endpoint: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Check rate limit for a user.

    Returns whether the user is within their rate limits,
    including remaining quota and reset times.
    """
    try:
        result = APIRateLimiting.check_rate_limit(
            session=session,
            user_id=user_id,
            endpoint=endpoint
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quotas/{user_id}/record")
def record_request(
    user_id: str,
    request: RecordRequestRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record an API request.

    Tracks API usage for rate limiting and analytics purposes.
    """
    try:
        quota = APIRateLimiting.record_request(
            session=session,
            user_id=user_id,
            endpoint=request.endpoint,
            response_status=request.response_status,
            response_time_ms=request.response_time_ms
        )

        return {
            "success": True,
            "quota": quota,
            "message": "Request recorded"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quotas/{user_id}/usage")
def get_usage_statistics(
    user_id: str,
    period: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get usage statistics for a user.

    Returns detailed usage metrics including request counts,
    success rates, and endpoint usage.
    """
    try:
        stats = APIRateLimiting.get_usage_statistics(
            session=session,
            user_id=user_id,
            period=period
        )

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quotas/{user_id}/override")
def create_quota_override(
    user_id: str,
    request: CreateQuotaOverrideRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a quota override.

    Temporarily or permanently overrides a user's quota limits
    with custom values.
    """
    try:
        override = APIRateLimiting.create_quota_override(
            session=session,
            user_id=user_id,
            custom_limits=request.custom_limits,
            duration_hours=request.duration_hours,
            reason=request.reason
        )

        return {
            "success": True,
            "override": override,
            "message": f"Quota override created for user {user_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/quotas/{user_id}/block")
def block_user(
    user_id: str,
    request: BlockUserRequest,
    session: Session = Depends(get_db_session)
):
    """
    Block a user.

    Temporarily blocks a user from making API requests
    for a specified duration.
    """
    try:
        block = APIRateLimiting.block_user(
            session=session,
            user_id=user_id,
            duration_hours=request.duration_hours,
            reason=request.reason
        )

        return {
            "success": True,
            "block": block,
            "message": f"User {user_id} blocked for {request.duration_hours} hours"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/quotas")
def list_quotas(
    tier: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    List user quotas.

    Returns quotas with optional filtering by tier and status.
    """
    try:
        result = APIRateLimiting.list_quotas(
            session=session,
            tier=tier,
            status=status,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_global_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get global rate limiting statistics.

    Returns aggregate metrics including total users, requests,
    tier distribution, and status distribution.
    """
    try:
        stats = APIRateLimiting.get_global_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tiers")
def list_quota_tiers():
    """
    List all quota tiers.

    Returns all available quota tiers and their default limits.
    """
    return {
        "success": True,
        "tiers": [
            {
                "tier": QuotaTier.FREE,
                "description": "Free tier with basic limits",
                "limits": APIRateLimiting._default_plans[QuotaTier.FREE]
            },
            {
                "tier": QuotaTier.BASIC,
                "description": "Basic tier with moderate limits",
                "limits": APIRateLimiting._default_plans[QuotaTier.BASIC]
            },
            {
                "tier": QuotaTier.PREMIUM,
                "description": "Premium tier with high limits",
                "limits": APIRateLimiting._default_plans[QuotaTier.PREMIUM]
            },
            {
                "tier": QuotaTier.ENTERPRISE,
                "description": "Enterprise tier with very high limits",
                "limits": APIRateLimiting._default_plans[QuotaTier.ENTERPRISE]
            },
            {
                "tier": QuotaTier.UNLIMITED,
                "description": "Unlimited tier (no limits)"
            }
        ]
    }


@router.get("/periods")
def list_quota_periods():
    """
    List all quota reset periods.

    Returns all supported quota reset period types.
    """
    return {
        "success": True,
        "periods": [
            {"period": QuotaPeriod.MINUTE, "description": "Per-minute quota"},
            {"period": QuotaPeriod.HOUR, "description": "Per-hour quota"},
            {"period": QuotaPeriod.DAY, "description": "Per-day quota"},
            {"period": QuotaPeriod.MONTH, "description": "Per-month quota"}
        ]
    }


@router.get("/statuses")
def list_limit_statuses():
    """
    List all rate limit statuses.

    Returns all possible rate limit status values.
    """
    return {
        "success": True,
        "statuses": [
            {"status": LimitStatus.WITHIN_LIMIT, "description": "Within quota limits"},
            {"status": LimitStatus.APPROACHING_LIMIT, "description": "Approaching quota limit (>90%)"},
            {"status": LimitStatus.EXCEEDED, "description": "Quota limit exceeded"},
            {"status": LimitStatus.BLOCKED, "description": "User is blocked"}
        ]
    }
