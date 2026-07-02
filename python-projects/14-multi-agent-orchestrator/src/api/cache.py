"""
Cache Management API

Endpoints for managing and monitoring the caching system.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from src.core.cache import cache_service
from src.core.auth import get_current_user
from src.models.user import User, UserRole


router = APIRouter()


class CacheStats(BaseModel):
    """Cache statistics response"""
    cache_keys: int
    total_keys: int
    hits: int
    misses: int
    hit_rate: float
    memory_used_mb: float
    memory_peak_mb: float


class CacheOperation(BaseModel):
    """Cache operation response"""
    success: bool
    message: str
    keys_affected: Optional[int] = None


@router.get("/cache/stats", response_model=CacheStats)
async def get_cache_stats(current_user: User = Depends(get_current_user)):
    """
    Get cache statistics

    Args:
        current_user: Authenticated user

    Returns:
        CacheStats: Cache statistics
    """
    stats = cache_service.get_stats()

    return CacheStats(**stats)


@router.post("/cache/clear", response_model=CacheOperation)
async def clear_cache(
    namespace: Optional[str] = Query(None, description="Namespace to clear (default: all)"),
    pattern: Optional[str] = Query(None, description="Pattern to match (supports wildcards)"),
    current_user: User = Depends(get_current_user)
):
    """
    Clear cache entries

    Args:
        namespace: Optional namespace to clear
        pattern: Optional pattern to match
        current_user: Authenticated user

    Returns:
        CacheOperation: Operation result

    Raises:
        HTTPException: If user is not admin
    """
    # Only admins can clear cache
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can clear cache"
        )

    try:
        if namespace and pattern:
            # Clear specific pattern in namespace
            keys_deleted = cache_service.delete_pattern(pattern, namespace)
            message = f"Cleared {keys_deleted} keys matching '{pattern}' in namespace '{namespace}'"

        elif namespace:
            # Clear entire namespace
            keys_deleted = cache_service.clear_namespace(namespace)
            message = f"Cleared namespace '{namespace}' ({keys_deleted} keys)"

        elif pattern:
            # Clear pattern across all namespaces
            keys_deleted = cache_service.delete_pattern(pattern)
            message = f"Cleared {keys_deleted} keys matching '{pattern}'"

        else:
            # Clear all cache
            cache_service.flush_all()
            keys_deleted = None
            message = "Cleared all cache"

        return CacheOperation(
            success=True,
            message=message,
            keys_affected=keys_deleted
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear cache: {str(e)}"
        )


@router.delete("/cache/key/{key}")
async def delete_cache_key(
    key: str,
    namespace: Optional[str] = Query(None, description="Namespace of the key"),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a specific cache key

    Args:
        key: Cache key to delete
        namespace: Optional namespace
        current_user: Authenticated user

    Returns:
        CacheOperation: Operation result

    Raises:
        HTTPException: If user is not admin
    """
    # Only admins can delete cache keys
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can delete cache keys"
        )

    success = cache_service.delete(key, namespace)

    if success:
        message = f"Deleted cache key '{key}'"
        if namespace:
            message += f" from namespace '{namespace}'"

        return CacheOperation(
            success=True,
            message=message,
            keys_affected=1
        )
    else:
        return CacheOperation(
            success=False,
            message=f"Failed to delete cache key '{key}'"
        )


@router.get("/cache/key/{key}")
async def get_cache_key(
    key: str,
    namespace: Optional[str] = Query(None, description="Namespace of the key"),
    current_user: User = Depends(get_current_user)
):
    """
    Get value of a specific cache key

    Args:
        key: Cache key to retrieve
        namespace: Optional namespace
        current_user: Authenticated user

    Returns:
        dict: Cache key value

    Raises:
        HTTPException: If key not found or user is not admin
    """
    # Only admins can view cache contents
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can view cache contents"
        )

    value = cache_service.get(key, namespace)

    if value is None:
        raise HTTPException(
            status_code=404,
            detail=f"Cache key '{key}' not found"
        )

    return {
        "key": key,
        "namespace": namespace,
        "value": value,
        "exists": True
    }


@router.post("/cache/invalidate/tasks")
async def invalidate_task_cache(current_user: User = Depends(get_current_user)):
    """
    Invalidate task-related cache

    Args:
        current_user: Authenticated user

    Returns:
        CacheOperation: Operation result
    """
    # Clear task-related caches
    keys_deleted = cache_service.clear_namespace("tasks")
    keys_deleted += cache_service.delete_pattern("*", "responses")  # Clear response cache

    return CacheOperation(
        success=True,
        message="Invalidated task cache",
        keys_affected=keys_deleted
    )


@router.post("/cache/invalidate/agents")
async def invalidate_agent_cache(current_user: User = Depends(get_current_user)):
    """
    Invalidate agent-related cache

    Args:
        current_user: Authenticated user

    Returns:
        CacheOperation: Operation result
    """
    # Clear agent-related caches
    keys_deleted = cache_service.clear_namespace("agents")
    keys_deleted += cache_service.delete_pattern("*", "responses")

    return CacheOperation(
        success=True,
        message="Invalidated agent cache",
        keys_affected=keys_deleted
    )


@router.post("/cache/warm")
async def warm_cache(
    current_user: User = Depends(get_current_user)
):
    """
    Warm up cache with frequently accessed data

    Args:
        current_user: Authenticated user

    Returns:
        CacheOperation: Operation result

    Raises:
        HTTPException: If user is not admin
    """
    # Only admins can warm cache
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=403,
            detail="Only administrators can warm cache"
        )

    # TODO: Implement cache warming logic
    # This would pre-load frequently accessed data into cache

    return CacheOperation(
        success=True,
        message="Cache warming initiated",
        keys_affected=0
    )
