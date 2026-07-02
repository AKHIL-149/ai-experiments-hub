"""
Rate Limit Management API

Endpoints for viewing and managing rate limits.
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel

from src.core.rate_limiter import rate_limiter, RateLimitTier
from src.core.auth import get_current_user
from src.models.user import User, UserRole


router = APIRouter()


class RateLimitInfo(BaseModel):
    """Rate limit information response"""
    limit: int
    remaining: int
    reset: int
    used: int


class RateLimitReset(BaseModel):
    """Rate limit reset response"""
    success: bool
    message: str


@router.get("/rate-limits/me", response_model=RateLimitInfo)
async def get_my_rate_limit(
    endpoint: Optional[str] = Query(None, description="Specific endpoint to check"),
    current_user: User = Depends(get_current_user)
):
    """
    Get current user's rate limit status

    Args:
        endpoint: Optional endpoint to check
        current_user: Authenticated user

    Returns:
        RateLimitInfo: Rate limit information
    """
    identifier = f"user_{current_user.id}"

    # Determine rate limit config based on role
    if current_user.role == UserRole.VIEWER:
        config = RateLimitTier.VIEWER
    elif current_user.role == UserRole.USER:
        config = RateLimitTier.USER
    else:
        config = RateLimitTier.ADMIN

    info = rate_limiter.get_rate_limit_info(
        identifier=identifier,
        max_requests=config["max_requests"],
        window_seconds=config["window_seconds"],
        endpoint=endpoint
    )

    return RateLimitInfo(**info)


@router.get("/rate-limits/user/{user_id}", response_model=RateLimitInfo)
async def get_user_rate_limit(
    user_id: int,
    endpoint: Optional[str] = Query(None, description="Specific endpoint to check"),
    current_user: User = Depends(get_current_user)
):
    """
    Get rate limit status for a specific user (admin only)

    Args:
        user_id: User ID to check
        endpoint: Optional endpoint to check
        current_user: Authenticated user

    Returns:
        RateLimitInfo: Rate limit information

    Raises:
        HTTPException: If user is not admin
    """
    # Only admins can check other users' rate limits
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can view other users' rate limits"
        )

    identifier = f"user_{user_id}"

    # Use default USER tier for lookup
    config = RateLimitTier.USER

    info = rate_limiter.get_rate_limit_info(
        identifier=identifier,
        max_requests=config["max_requests"],
        window_seconds=config["window_seconds"],
        endpoint=endpoint
    )

    return RateLimitInfo(**info)


@router.post("/rate-limits/reset/me", response_model=RateLimitReset)
async def reset_my_rate_limit(
    endpoint: Optional[str] = Query(None, description="Specific endpoint to reset"),
    current_user: User = Depends(get_current_user)
):
    """
    Reset current user's rate limit

    Args:
        endpoint: Optional endpoint to reset
        current_user: Authenticated user

    Returns:
        RateLimitReset: Reset result
    """
    identifier = f"user_{current_user.id}"

    success = rate_limiter.reset_rate_limit(
        identifier=identifier,
        endpoint=endpoint
    )

    if success:
        message = f"Rate limit reset for user {current_user.id}"
        if endpoint:
            message += f" on endpoint {endpoint}"
    else:
        message = "Failed to reset rate limit"

    return RateLimitReset(success=success, message=message)


@router.post("/rate-limits/reset/user/{user_id}", response_model=RateLimitReset)
async def reset_user_rate_limit(
    user_id: int,
    endpoint: Optional[str] = Query(None, description="Specific endpoint to reset"),
    current_user: User = Depends(get_current_user)
):
    """
    Reset rate limit for a specific user (admin only)

    Args:
        user_id: User ID to reset
        endpoint: Optional endpoint to reset
        current_user: Authenticated user

    Returns:
        RateLimitReset: Reset result

    Raises:
        HTTPException: If user is not admin
    """
    # Only admins can reset other users' rate limits
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can reset other users' rate limits"
        )

    identifier = f"user_{user_id}"

    success = rate_limiter.reset_rate_limit(
        identifier=identifier,
        endpoint=endpoint
    )

    if success:
        message = f"Rate limit reset for user {user_id}"
        if endpoint:
            message += f" on endpoint {endpoint}"
    else:
        message = "Failed to reset rate limit"

    return RateLimitReset(success=success, message=message)


@router.get("/rate-limits/tiers")
async def get_rate_limit_tiers(
    current_user: User = Depends(get_current_user)
):
    """
    Get available rate limit tiers

    Args:
        current_user: Authenticated user

    Returns:
        dict: Rate limit tier information
    """
    return {
        "role_based": {
            "viewer": {
                "max_requests": RateLimitTier.VIEWER["max_requests"],
                "window_seconds": RateLimitTier.VIEWER["window_seconds"],
                "description": "60 requests per minute"
            },
            "user": {
                "max_requests": RateLimitTier.USER["max_requests"],
                "window_seconds": RateLimitTier.USER["window_seconds"],
                "description": "120 requests per minute"
            },
            "admin": {
                "max_requests": RateLimitTier.ADMIN["max_requests"],
                "window_seconds": RateLimitTier.ADMIN["window_seconds"],
                "description": "300 requests per minute"
            }
        },
        "endpoint_specific": {
            "task_create": {
                "max_requests": RateLimitTier.TASK_CREATE["max_requests"],
                "window_seconds": RateLimitTier.TASK_CREATE["window_seconds"],
                "description": "30 requests per minute"
            },
            "workflow_execute": {
                "max_requests": RateLimitTier.WORKFLOW_EXECUTE["max_requests"],
                "window_seconds": RateLimitTier.WORKFLOW_EXECUTE["window_seconds"],
                "description": "10 requests per minute"
            },
            "agent_create": {
                "max_requests": RateLimitTier.AGENT_CREATE["max_requests"],
                "window_seconds": RateLimitTier.AGENT_CREATE["window_seconds"],
                "description": "20 requests per minute"
            }
        },
        "current_user_tier": {
            "role": current_user.role.value,
            "max_requests": (
                RateLimitTier.VIEWER["max_requests"] if current_user.role == UserRole.VIEWER
                else RateLimitTier.USER["max_requests"] if current_user.role == UserRole.USER
                else RateLimitTier.ADMIN["max_requests"]
            ),
            "window_seconds": 60
        }
    }
