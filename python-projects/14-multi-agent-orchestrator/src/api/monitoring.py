"""
Monitoring API endpoints
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional

from src.core.database import get_db_session
from src.core.login_gate import Caller, get_caller
from src.services.monitoring_service import MonitoringService

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


@router.get("/dashboard", response_model=Dict[str, Any])
async def get_dashboard_overview(
    db: Session = Depends(get_db_session),
    caller: Optional[Caller] = Depends(get_caller),
):
    """
    Get high-level overview metrics for monitoring dashboard

    Returns comprehensive metrics including:
    - Task counts by status
    - Agent availability
    - Execution statistics
    - Workflow status
    - Success rates
    """
    service = MonitoringService()
    return service.get_dashboard_overview(db, owner_id=None if caller is None or caller.is_admin else caller.user_id)


@router.get("/tasks", response_model=Dict[str, Any])
async def get_task_metrics(
    time_range: str = Query("24h", regex="^(24h|7d|30d)$"),
    db: Session = Depends(get_db_session),
    caller: Optional[Caller] = Depends(get_caller),
):
    """
    Get detailed task metrics over specified time range

    Args:
        time_range: Time range for metrics ("24h", "7d", or "30d")

    Returns:
        Task metrics including counts by status, priority, and average duration
    """
    service = MonitoringService()
    return service.get_task_metrics(db, time_range, owner_id=None if caller is None or caller.is_admin else caller.user_id)


@router.get("/agents", response_model=List[Dict[str, Any]])
async def get_agent_performance(
    db: Session = Depends(get_db_session)
):
    """
    Get performance metrics for all agents

    Returns:
        List of agent performance data including:
        - Execution counts
        - Success rates
        - Average duration
        - Current status
    """
    service = MonitoringService()
    return service.get_agent_performance(db)


@router.get("/workflows", response_model=Dict[str, Any])
async def get_workflow_metrics(
    db: Session = Depends(get_db_session),
    caller: Optional[Caller] = Depends(get_caller),
):
    """
    Get workflow execution metrics

    Returns:
        Workflow metrics including:
        - Counts by status and type
        - Average duration
        - Recent workflow executions
    """
    service = MonitoringService()
    return service.get_workflow_metrics(
        db, owner_id=None if caller is None or caller.is_admin else caller.user_id
    )


@router.get("/health", response_model=Dict[str, Any])
async def get_system_health(
    db: Session = Depends(get_db_session)
):
    """
    Get overall system health status

    Returns:
        System health indicators including:
        - Health status (healthy/warning/critical)
        - Detected issues
        - Agent availability
        - Stuck or failed tasks
    """
    service = MonitoringService()
    return service.get_system_health(db)
