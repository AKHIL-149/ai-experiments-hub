"""
Agent Analytics API endpoints
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_analytics import AgentAnalytics
from src.models.agent import AgentRole
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class AgentComparisonRequest(BaseModel):
    """Request model for agent comparison"""
    agent_ids: List[int]
    time_range_hours: int = 24


# Endpoints

@router.get("/performance/{agent_id}")
async def get_agent_performance(
    agent_id: int,
    time_range_hours: int = Query(24, ge=1, le=720),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get comprehensive performance metrics for an agent"""
    try:
        performance = AgentAnalytics.get_agent_performance(
            session=db,
            agent_id=agent_id,
            time_range_hours=time_range_hours
        )

        return performance

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get agent performance: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/ranking")
async def get_agent_ranking(
    role: Optional[str] = Query(None),
    metric: str = Query("success_rate", regex="^(success_rate|speed|total_tasks|lifetime_success_rate|reliability)$"),
    time_range_hours: int = Query(24, ge=1, le=720),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Rank agents by specified metric"""
    try:
        # Convert role string to enum if provided
        agent_role = AgentRole(role) if role else None

        ranking = AgentAnalytics.get_agent_ranking(
            session=db,
            role=agent_role,
            metric=metric,
            time_range_hours=time_range_hours,
            limit=limit
        )

        return {
            "metric": metric,
            "role": role,
            "time_range_hours": time_range_hours,
            "count": len(ranking),
            "ranking": ranking
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get agent ranking: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/compare")
async def compare_agents(
    request: AgentComparisonRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Compare performance of multiple agents"""
    try:
        if len(request.agent_ids) < 2:
            raise ValueError("At least 2 agents required for comparison")

        if len(request.agent_ids) > 10:
            raise ValueError("Maximum 10 agents allowed for comparison")

        comparison = AgentAnalytics.compare_agents(
            session=db,
            agent_ids=request.agent_ids,
            time_range_hours=request.time_range_hours
        )

        return comparison

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to compare agents: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/trends")
async def get_execution_trends(
    agent_id: Optional[int] = Query(None),
    role: Optional[str] = Query(None),
    time_range_hours: int = Query(168, ge=1, le=720),
    interval_hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get execution trends over time"""
    try:
        # Convert role string to enum if provided
        agent_role = AgentRole(role) if role else None

        trends = AgentAnalytics.get_execution_trends(
            session=db,
            agent_id=agent_id,
            role=agent_role,
            time_range_hours=time_range_hours,
            interval_hours=interval_hours
        )

        return trends

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get execution trends: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/distribution")
async def get_task_distribution(
    agent_id: Optional[int] = Query(None),
    time_range_hours: int = Query(24, ge=1, le=720),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get distribution of tasks by various dimensions"""
    try:
        distribution = AgentAnalytics.get_task_distribution(
            session=db,
            agent_id=agent_id,
            time_range_hours=time_range_hours
        )

        return distribution

    except Exception as e:
        logger.error(f"Failed to get task distribution: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/errors")
async def get_error_analysis(
    agent_id: Optional[int] = Query(None),
    time_range_hours: int = Query(168, ge=1, le=720),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Analyze errors and failure patterns"""
    try:
        error_analysis = AgentAnalytics.get_error_analysis(
            session=db,
            agent_id=agent_id,
            time_range_hours=time_range_hours
        )

        return error_analysis

    except Exception as e:
        logger.error(f"Failed to get error analysis: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/utilization")
async def get_agent_utilization(
    time_range_hours: int = Query(24, ge=1, le=720),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get agent utilization metrics"""
    try:
        utilization = AgentAnalytics.get_agent_utilization(
            session=db,
            time_range_hours=time_range_hours
        )

        return utilization

    except Exception as e:
        logger.error(f"Failed to get agent utilization: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/summary")
async def get_performance_summary(
    time_range_hours: int = Query(24, ge=1, le=720),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get overall system performance summary"""
    try:
        summary = AgentAnalytics.get_performance_summary(
            session=db,
            time_range_hours=time_range_hours
        )

        return summary

    except Exception as e:
        logger.error(f"Failed to get performance summary: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
