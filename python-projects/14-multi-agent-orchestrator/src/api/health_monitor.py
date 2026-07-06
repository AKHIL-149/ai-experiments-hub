"""
Agent Health Monitoring API endpoints
"""

from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_health_monitor import AgentHealthMonitor, HealthStatus
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class RecordHeartbeatRequest(BaseModel):
    """Request model for recording heartbeat"""
    agent_id: int = Field(..., description="Agent ID")


class SetHealthThresholdRequest(BaseModel):
    """Request model for setting health threshold"""
    agent_id: int = Field(..., description="Agent ID")
    check_type: str = Field(..., description="Check type (error_rate/response_time/resource_usage)")
    threshold_value: float = Field(..., ge=0.0, description="Threshold value")


# Endpoints

@router.get("/check/{agent_id}")
async def check_agent_health(
    agent_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Perform comprehensive health check on an agent.

    Checks:
    - Agent status
    - Heartbeat (last activity)
    - Resource utilization
    - Error rate
    - Execution performance

    Returns overall health status and detailed check results.
    """
    try:
        health = AgentHealthMonitor.check_agent_health(
            session=db,
            agent_id=agent_id
        )

        return {
            "success": True,
            "health": health,
            "message": f"Health check completed for agent {agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to check agent health: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/heartbeat")
async def record_heartbeat(
    request: RecordHeartbeatRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Record a heartbeat for an agent.

    Heartbeats indicate the agent is alive and responsive.
    Should be called periodically by agents.
    """
    try:
        result = AgentHealthMonitor.record_heartbeat(
            session=db,
            agent_id=request.agent_id
        )

        return {
            "success": True,
            "heartbeat": result,
            "message": "Heartbeat recorded"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to record heartbeat: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/uptime/{agent_id}")
async def get_uptime_stats(
    agent_id: int,
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get uptime statistics for an agent.

    Returns:
    - Uptime percentage
    - Total executions (successful/failed)
    - Total active hours
    - Failure reasons breakdown
    """
    try:
        stats = AgentHealthMonitor.get_uptime_stats(
            session=db,
            agent_id=agent_id,
            days=days
        )

        return {
            "success": True,
            "uptime": stats,
            "message": f"Uptime statistics for last {days} days"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get uptime stats: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/cluster")
async def get_cluster_health(
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get overall cluster health status.

    Returns aggregate health across all agents:
    - Cluster health status
    - Healthy/degraded/unhealthy agent counts
    - Healthy percentage
    - Individual agent health summary
    """
    try:
        cluster_health = AgentHealthMonitor.get_cluster_health(session=db)

        return {
            "success": True,
            "cluster": cluster_health,
            "message": f"Cluster health: {cluster_health['cluster_status']}"
        }

    except Exception as e:
        logger.error(f"Failed to get cluster health: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/anomalies/{agent_id}")
async def detect_anomalies(
    agent_id: int,
    threshold_std_dev: float = Query(2.0, ge=1.0, le=5.0, description="Standard deviations threshold"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Detect anomalies in agent behavior.

    Analyzes execution times and flags executions that deviate
    significantly from the norm (based on standard deviations).

    Higher threshold = fewer anomalies detected.
    """
    try:
        anomalies = AgentHealthMonitor.detect_anomalies(
            session=db,
            agent_id=agent_id,
            threshold_std_dev=threshold_std_dev
        )

        return {
            "success": True,
            "anomalies": anomalies,
            "message": (
                f"Detected {anomalies['total_anomalies']} anomalies"
                if anomalies.get("anomalies_detected")
                else "No anomalies detected"
            )
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to detect anomalies: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/failures/{agent_id}")
async def get_failure_analysis(
    agent_id: int,
    days: int = Query(7, ge=1, le=90, description="Number of days to analyze"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Analyze failures for an agent.

    Returns:
    - Total failures
    - Failure categories (timeout/resource/error/unknown)
    - Failure timeline with details
    """
    try:
        analysis = AgentHealthMonitor.get_failure_analysis(
            session=db,
            agent_id=agent_id,
            days=days
        )

        return {
            "success": True,
            "analysis": analysis,
            "message": f"Failure analysis for last {days} days"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get failure analysis: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/threshold")
async def set_health_threshold(
    request: SetHealthThresholdRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Set custom health check threshold for an agent.

    Allows customizing health check thresholds:
    - **error_rate**: Error rate percentage threshold
    - **response_time**: Maximum acceptable response time
    - **resource_usage**: Resource utilization threshold
    """
    try:
        result = AgentHealthMonitor.set_health_threshold(
            session=db,
            agent_id=request.agent_id,
            check_type=request.check_type,
            threshold_value=request.threshold_value
        )

        return {
            "success": True,
            "threshold": result,
            "message": f"Health threshold updated for agent {request.agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to set health threshold: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/status-types")
async def list_health_statuses() -> Dict[str, Any]:
    """
    List all health status types.

    Returns the possible health statuses with descriptions.
    """
    statuses = [
        {
            "status": HealthStatus.HEALTHY,
            "description": "Agent is operating normally with no issues",
            "color": "green"
        },
        {
            "status": HealthStatus.DEGRADED,
            "description": "Agent has warnings but is still functional",
            "color": "yellow"
        },
        {
            "status": HealthStatus.UNHEALTHY,
            "description": "Agent has critical issues affecting functionality",
            "color": "red"
        },
        {
            "status": HealthStatus.UNKNOWN,
            "description": "Agent health cannot be determined",
            "color": "gray"
        }
    ]

    return {
        "success": True,
        "total_statuses": len(statuses),
        "statuses": statuses,
        "message": "List of all health statuses"
    }
