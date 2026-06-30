"""
Health check endpoints
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Dict, Any

from src.core.database import get_db_session

router = APIRouter()


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint

    Returns:
        dict: Health status
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "multi-agent-orchestrator",
    }


@router.get("/health/db")
async def database_health(db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """
    Database health check

    Args:
        db: Database session

    Returns:
        dict: Database health status
    """
    try:
        # Simple query to check database connection
        db.execute("SELECT 1")

        return {
            "status": "healthy",
            "database": "connected",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


@router.get("/health/celery")
async def celery_health() -> Dict[str, Any]:
    """
    Celery health check

    Returns:
        dict: Celery health status
    """
    try:
        from celery_app import celery_app

        # Check if Celery workers are active
        inspect = celery_app.control.inspect()
        active_workers = inspect.active()

        worker_count = len(active_workers) if active_workers else 0

        return {
            "status": "healthy" if worker_count > 0 else "degraded",
            "workers": worker_count,
            "broker": "connected",
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "workers": 0,
            "broker": "disconnected",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat(),
        }


@router.get("/health/full")
async def full_health_check(db: Session = Depends(get_db_session)) -> Dict[str, Any]:
    """
    Comprehensive health check

    Args:
        db: Database session

    Returns:
        dict: Complete system health status
    """
    # Check database
    db_status = "healthy"
    try:
        db.execute("SELECT 1")
    except Exception:
        db_status = "unhealthy"

    # Check Celery
    celery_status = "healthy"
    worker_count = 0
    try:
        from celery_app import celery_app
        inspect = celery_app.control.inspect()
        active_workers = inspect.active()
        worker_count = len(active_workers) if active_workers else 0

        if worker_count == 0:
            celery_status = "degraded"
    except Exception:
        celery_status = "unhealthy"

    # Overall status
    overall_status = "healthy"
    if db_status == "unhealthy" or celery_status == "unhealthy":
        overall_status = "unhealthy"
    elif celery_status == "degraded":
        overall_status = "degraded"

    return {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "database": db_status,
            "celery": celery_status,
            "celery_workers": worker_count,
        }
    }
