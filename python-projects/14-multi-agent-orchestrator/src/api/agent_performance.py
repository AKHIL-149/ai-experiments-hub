"""
Agent Performance Tracking API

REST API endpoints for tracking and analyzing agent performance metrics.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_performance import (
    AgentPerformance,
    MetricType,
    PerformanceLevel,
    TrendDirection
)


router = APIRouter()


# Request/Response Models
class RecordTaskCompletionRequest(BaseModel):
    task_id: int = Field(..., description="Task ID")
    success: bool = Field(..., description="Whether task succeeded")
    completion_time_seconds: float = Field(..., description="Time taken to complete")
    quality_score: float = Field(1.0, description="Quality rating (0-1)")
    error_count: int = Field(0, description="Number of errors")
    retry_count: int = Field(0, description="Number of retries")
    resource_usage: Optional[dict] = Field(None, description="Resource consumption")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class RecordEfficiencyRequest(BaseModel):
    throughput: float = Field(..., description="Tasks per hour")
    utilization: float = Field(..., description="Utilization percentage (0-100)")
    average_response_time: float = Field(..., description="Average response time (seconds)")
    idle_time_seconds: float = Field(0, description="Idle time")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class RecordQualityRequest(BaseModel):
    accuracy: float = Field(..., description="Accuracy score (0-1)")
    consistency: float = Field(..., description="Consistency score (0-1)")
    error_rate: float = Field(..., description="Error rate (0-1)")
    defect_rate: float = Field(0.0, description="Defect rate (0-1)")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class RecordResourceUsageRequest(BaseModel):
    cpu_usage: float = Field(..., description="CPU usage percentage (0-100)")
    memory_usage_mb: float = Field(..., description="Memory usage in MB")
    api_calls: int = Field(..., description="Number of API calls")
    tokens_used: int = Field(0, description="LLM tokens used")
    cost: float = Field(0.0, description="Cost in dollars")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class CompareAgentsRequest(BaseModel):
    agent_ids: List[int] = Field(..., description="List of agent IDs to compare")
    metric_type: str = Field(..., description="Metric to compare")
    timeframe_hours: int = Field(24, description="Time window")


class SetBenchmarkRequest(BaseModel):
    metric_type: str = Field(..., description="Type of metric")
    target_value: float = Field(..., description="Target/ideal value")
    threshold_warning: float = Field(..., description="Warning threshold")
    threshold_critical: float = Field(..., description="Critical threshold")
    description: str = Field("", description="Benchmark description")


@router.post("/agents/{agent_id}/task-completion")
def record_task_completion(
    agent_id: int,
    request: RecordTaskCompletionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record task completion metrics.

    Tracks task success, completion time, quality, errors, and retries.
    Automatically checks for performance alerts.
    """
    try:
        record = AgentPerformance.record_task_completion(
            session=session,
            agent_id=agent_id,
            task_id=request.task_id,
            success=request.success,
            completion_time_seconds=request.completion_time_seconds,
            quality_score=request.quality_score,
            error_count=request.error_count,
            retry_count=request.retry_count,
            resource_usage=request.resource_usage,
            metadata=request.metadata
        )

        return {
            "success": True,
            "record": record,
            "message": f"Task completion recorded: {'success' if request.success else 'failure'}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/efficiency")
def record_efficiency_metric(
    agent_id: int,
    request: RecordEfficiencyRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record efficiency metrics.

    Tracks throughput, utilization, response time, and idle time.
    """
    try:
        metric = AgentPerformance.record_efficiency_metric(
            session=session,
            agent_id=agent_id,
            throughput=request.throughput,
            utilization=request.utilization,
            average_response_time=request.average_response_time,
            idle_time_seconds=request.idle_time_seconds,
            metadata=request.metadata
        )

        return {
            "success": True,
            "metric": metric,
            "message": "Efficiency metric recorded"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/quality")
def record_quality_metric(
    agent_id: int,
    request: RecordQualityRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record quality metrics.

    Tracks accuracy, consistency, error rate, and defect rate.
    """
    try:
        metric = AgentPerformance.record_quality_metric(
            session=session,
            agent_id=agent_id,
            accuracy=request.accuracy,
            consistency=request.consistency,
            error_rate=request.error_rate,
            defect_rate=request.defect_rate,
            metadata=request.metadata
        )

        return {
            "success": True,
            "metric": metric,
            "message": "Quality metric recorded"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/resource-usage")
def record_resource_usage(
    agent_id: int,
    request: RecordResourceUsageRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record resource usage metrics.

    Tracks CPU, memory, API calls, LLM tokens, and cost.
    """
    try:
        metric = AgentPerformance.record_resource_usage(
            session=session,
            agent_id=agent_id,
            cpu_usage=request.cpu_usage,
            memory_usage_mb=request.memory_usage_mb,
            api_calls=request.api_calls,
            tokens_used=request.tokens_used,
            cost=request.cost,
            metadata=request.metadata
        )

        return {
            "success": True,
            "metric": metric,
            "message": "Resource usage recorded"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/summary")
def get_performance_summary(
    agent_id: int,
    timeframe_hours: int = 24,
    session: Session = Depends(get_db_session)
):
    """
    Get comprehensive performance summary.

    Returns task, efficiency, quality, and resource metrics
    along with performance score and level.
    """
    try:
        summary = AgentPerformance.get_performance_summary(
            session=session,
            agent_id=agent_id,
            timeframe_hours=timeframe_hours
        )

        return {
            "success": True,
            **summary
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/trend")
def get_performance_trend(
    agent_id: int,
    metric_type: str,
    timeframe_hours: int = 168,
    session: Session = Depends(get_db_session)
):
    """
    Get performance trend analysis.

    Analyzes trends over time and calculates change percentage.
    Returns improving, stable, or declining trend.
    """
    try:
        trend = AgentPerformance.get_performance_trend(
            session=session,
            agent_id=agent_id,
            metric_type=metric_type,
            timeframe_hours=timeframe_hours
        )

        return {
            "success": True,
            **trend
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare")
def compare_agents(
    request: CompareAgentsRequest,
    session: Session = Depends(get_db_session)
):
    """
    Compare performance across multiple agents.

    Ranks agents by specified metric and identifies
    best and worst performers.
    """
    try:
        comparison = AgentPerformance.compare_agents(
            session=session,
            agent_ids=request.agent_ids,
            metric_type=request.metric_type,
            timeframe_hours=request.timeframe_hours
        )

        return {
            "success": True,
            **comparison
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/alerts")
def get_performance_alerts(
    agent_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Get performance alerts for an agent.

    Returns alerts for low success rate, high errors,
    low quality, and other performance issues.
    """
    try:
        alerts = AgentPerformance.get_performance_alerts(
            session=session,
            agent_id=agent_id
        )

        return {
            "success": True,
            **alerts
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/benchmarks")
def set_benchmark(
    request: SetBenchmarkRequest,
    session: Session = Depends(get_db_session)
):
    """
    Set performance benchmark.

    Establishes target values and thresholds for performance metrics.
    Used for alerting and performance evaluation.
    """
    try:
        benchmark = AgentPerformance.set_benchmark(
            session=session,
            metric_type=request.metric_type,
            target_value=request.target_value,
            threshold_warning=request.threshold_warning,
            threshold_critical=request.threshold_critical,
            description=request.description
        )

        return {
            "success": True,
            "benchmark": benchmark,
            "message": f"Benchmark set for {request.metric_type}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get system-wide performance statistics.

    Returns aggregate metrics across all agents including
    overall success rate, average times, and quality scores.
    """
    try:
        stats = AgentPerformance.get_performance_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metric-types")
def list_metric_types():
    """
    List all metric types.

    Returns all types of metrics that can be tracked.
    """
    return {
        "success": True,
        "metric_types": [
            {"type": MetricType.TASK_COMPLETION, "description": "Task completion metrics"},
            {"type": MetricType.EFFICIENCY, "description": "Efficiency and throughput metrics"},
            {"type": MetricType.QUALITY, "description": "Quality and accuracy metrics"},
            {"type": MetricType.RESOURCE_USAGE, "description": "Resource consumption metrics"},
            {"type": MetricType.RESPONSE_TIME, "description": "Response time metrics"},
            {"type": MetricType.THROUGHPUT, "description": "Throughput metrics"},
            {"type": MetricType.ERROR_RATE, "description": "Error rate metrics"}
        ]
    }


@router.get("/performance-levels")
def list_performance_levels():
    """
    List all performance levels.

    Returns performance level classifications.
    """
    return {
        "success": True,
        "performance_levels": [
            {"level": PerformanceLevel.EXCELLENT, "description": "Top 10% performers", "score_range": "0.9-1.0"},
            {"level": PerformanceLevel.GOOD, "description": "Top 25% performers", "score_range": "0.75-0.89"},
            {"level": PerformanceLevel.AVERAGE, "description": "Middle 50%", "score_range": "0.5-0.74"},
            {"level": PerformanceLevel.BELOW_AVERAGE, "description": "Bottom 25%", "score_range": "0.25-0.49"},
            {"level": PerformanceLevel.POOR, "description": "Bottom 10%", "score_range": "0-0.24"}
        ]
    }


@router.get("/trend-directions")
def list_trend_directions():
    """
    List all trend directions.

    Returns possible trend directions for performance analysis.
    """
    return {
        "success": True,
        "trend_directions": [
            {"direction": TrendDirection.IMPROVING, "description": "Performance improving over time (>5% increase)"},
            {"direction": TrendDirection.STABLE, "description": "Performance stable (±5%)"},
            {"direction": TrendDirection.DECLINING, "description": "Performance declining over time (>5% decrease)"}
        ]
    }
