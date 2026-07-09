"""
Performance Monitoring API

REST API endpoints for tracking and analyzing agent performance metrics.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.performance_monitoring import (
    PerformanceMonitoring,
    MetricType,
    PerformanceStatus
)


router = APIRouter()


# Request/Response Models
class RecordExecutionRequest(BaseModel):
    agent_id: Optional[int] = Field(None, description="Agent ID")
    workflow_id: Optional[str] = Field(None, description="Workflow ID")
    task_id: Optional[str] = Field(None, description="Task ID")
    execution_time_seconds: Optional[float] = Field(None, description="Execution time in seconds")
    success: bool = Field(True, description="Whether execution succeeded")
    error_type: Optional[str] = Field(None, description="Error type if failed")
    resource_usage: Optional[dict] = Field(None, description="Resource usage metrics")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class RecordResponseTimeRequest(BaseModel):
    agent_id: int = Field(..., description="Agent ID")
    response_time_ms: float = Field(..., description="Response time in milliseconds")
    endpoint: Optional[str] = Field(None, description="Endpoint or operation")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class RecordThroughputRequest(BaseModel):
    agent_id: Optional[int] = Field(None, description="Agent ID")
    workflow_id: Optional[str] = Field(None, description="Workflow ID")
    items_processed: int = Field(..., description="Number of items processed")
    time_window_seconds: float = Field(..., description="Time window in seconds")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class UpdateThresholdsRequest(BaseModel):
    thresholds: dict = Field(..., description="Performance thresholds")


@router.post("/executions")
def record_execution(
    request: RecordExecutionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record execution metrics.

    Tracks performance metrics for agent/workflow/task execution including
    execution time, success/failure, resource usage, and automatic anomaly detection.
    """
    try:
        metric = PerformanceMonitoring.record_execution(
            session=session,
            agent_id=request.agent_id,
            workflow_id=request.workflow_id,
            task_id=request.task_id,
            execution_time_seconds=request.execution_time_seconds,
            success=request.success,
            error_type=request.error_type,
            resource_usage=request.resource_usage,
            metadata=request.metadata
        )

        return {
            "success": True,
            "metric": metric,
            "message": "Execution metric recorded"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/response-times")
def record_response_time(
    request: RecordResponseTimeRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record response time metric.

    Tracks agent response times for monitoring latency and
    detecting slow responses.
    """
    try:
        metric = PerformanceMonitoring.record_response_time(
            session=session,
            agent_id=request.agent_id,
            response_time_ms=request.response_time_ms,
            endpoint=request.endpoint,
            metadata=request.metadata
        )

        return {
            "success": True,
            "metric": metric,
            "message": "Response time recorded"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/throughput")
def record_throughput(
    request: RecordThroughputRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record throughput metric.

    Tracks processing rates for agents/workflows to monitor
    performance and capacity.
    """
    try:
        metric = PerformanceMonitoring.record_throughput(
            session=session,
            agent_id=request.agent_id,
            workflow_id=request.workflow_id,
            items_processed=request.items_processed,
            time_window_seconds=request.time_window_seconds,
            metadata=request.metadata
        )

        return {
            "success": True,
            "metric": metric,
            "message": "Throughput recorded"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}")
def get_agent_performance(
    agent_id: int,
    time_window_hours: int = 24,
    session: Session = Depends(get_db_session)
):
    """
    Get agent performance metrics.

    Returns comprehensive performance analysis including success rates,
    execution times, throughput, anomalies, and performance status.
    """
    try:
        performance = PerformanceMonitoring.get_agent_performance(
            session=session,
            agent_id=agent_id,
            time_window_hours=time_window_hours
        )

        return {
            "success": True,
            "performance": performance
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/workflows/{workflow_id}")
def get_workflow_performance(
    workflow_id: str,
    time_window_hours: int = 24,
    session: Session = Depends(get_db_session)
):
    """
    Get workflow performance metrics.

    Returns workflow-level performance analysis including execution
    statistics, success rates, and performance trends.
    """
    try:
        performance = PerformanceMonitoring.get_workflow_performance(
            session=session,
            workflow_id=workflow_id,
            time_window_hours=time_window_hours
        )

        return {
            "success": True,
            "performance": performance
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system")
def get_system_performance(
    time_window_hours: int = 24,
    session: Session = Depends(get_db_session)
):
    """
    Get system-wide performance metrics.

    Returns aggregate performance metrics across all agents and workflows
    including overall health, capacity, and anomalies.
    """
    try:
        performance = PerformanceMonitoring.get_system_performance(
            session=session,
            time_window_hours=time_window_hours
        )

        return {
            "success": True,
            "performance": performance
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/anomalies")
def get_anomalies(
    agent_id: Optional[int] = None,
    workflow_id: Optional[str] = None,
    severity: Optional[str] = None,
    time_window_hours: int = 24,
    session: Session = Depends(get_db_session)
):
    """
    Get detected performance anomalies.

    Returns anomalies such as slow executions, high failure rates,
    and unusual performance patterns.
    """
    try:
        result = PerformanceMonitoring.get_anomalies(
            session=session,
            agent_id=agent_id,
            workflow_id=workflow_id,
            severity=severity,
            time_window_hours=time_window_hours
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trends")
def get_performance_trend(
    metric_type: str,
    agent_id: Optional[int] = None,
    workflow_id: Optional[str] = None,
    time_window_hours: int = 24,
    interval_minutes: int = 60,
    session: Session = Depends(get_db_session)
):
    """
    Get performance trend over time.

    Returns time-series data for a specific metric showing
    performance trends and patterns.
    """
    try:
        result = PerformanceMonitoring.get_performance_trend(
            session=session,
            metric_type=metric_type,
            agent_id=agent_id,
            workflow_id=workflow_id,
            time_window_hours=time_window_hours,
            interval_minutes=interval_minutes
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/compare")
def compare_agent_performance(
    agent_ids: str,
    time_window_hours: int = 24,
    session: Session = Depends(get_db_session)
):
    """
    Compare performance across agents.

    Returns comparative analysis of multiple agents showing
    relative performance, rankings, and differences.

    Parameters:
        agent_ids: Comma-separated agent IDs (e.g., "1,2,3")
    """
    try:
        # Parse comma-separated agent IDs
        agent_id_list = [int(id.strip()) for id in agent_ids.split(",")]

        result = PerformanceMonitoring.compare_agent_performance(
            session=session,
            agent_ids=agent_id_list,
            time_window_hours=time_window_hours
        )

        return {
            "success": True,
            **result
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
    Get performance monitoring statistics.

    Returns aggregate statistics about performance metrics including
    total executions, average performance, and metric distribution.
    """
    try:
        stats = PerformanceMonitoring.get_performance_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/thresholds")
def get_thresholds(
    session: Session = Depends(get_db_session)
):
    """
    Get performance thresholds.

    Returns current threshold configuration for determining
    performance status levels.
    """
    try:
        thresholds = PerformanceMonitoring.get_thresholds(session=session)

        return {
            "success": True,
            "thresholds": thresholds
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/thresholds")
def update_thresholds(
    request: UpdateThresholdsRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update performance thresholds.

    Configures thresholds for determining performance status
    (excellent, good, fair, poor, critical).
    """
    try:
        PerformanceMonitoring.update_thresholds(
            session=session,
            thresholds=request.thresholds
        )

        return {
            "success": True,
            "message": "Thresholds updated",
            "thresholds": request.thresholds
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metric-types")
def list_metric_types():
    """
    List all metric types.

    Returns all available performance metric types and their descriptions.
    """
    return {
        "success": True,
        "metric_types": [
            {"type": MetricType.EXECUTION_TIME, "description": "Time taken to execute a task"},
            {"type": MetricType.SUCCESS_RATE, "description": "Percentage of successful executions"},
            {"type": MetricType.THROUGHPUT, "description": "Items processed per unit time"},
            {"type": MetricType.ERROR_RATE, "description": "Percentage of failed executions"},
            {"type": MetricType.RESPONSE_TIME, "description": "Time to respond to requests"},
            {"type": MetricType.RESOURCE_UTILIZATION, "description": "CPU, memory, or other resource usage"},
            {"type": MetricType.QUEUE_LENGTH, "description": "Number of pending tasks"}
        ]
    }


@router.get("/statuses")
def list_performance_statuses():
    """
    List all performance statuses.

    Returns all possible performance health status levels.
    """
    return {
        "success": True,
        "statuses": [
            {"status": PerformanceStatus.EXCELLENT, "description": "Performance exceeds targets"},
            {"status": PerformanceStatus.GOOD, "description": "Performance meets targets"},
            {"status": PerformanceStatus.FAIR, "description": "Performance acceptable but below targets"},
            {"status": PerformanceStatus.POOR, "description": "Performance significantly below targets"},
            {"status": PerformanceStatus.CRITICAL, "description": "Performance critically degraded"}
        ]
    }
