"""
Agent Profiling and Benchmarking API

REST API endpoints for agent profiling, performance benchmarking, and optimization.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_profiling import (
    AgentProfiling,
    ProfileMetricType,
    BenchmarkType,
    ProfileStatus,
    BottleneckSeverity
)


router = APIRouter()


# Request/Response Models
class StartProfileSessionRequest(BaseModel):
    agent_id: str = Field(..., description="Agent ID to profile")
    profile_name: str = Field(..., description="Profile session name")
    metric_types: List[str] = Field(..., description="Types of metrics to collect")
    duration_seconds: Optional[int] = Field(None, description="Optional duration limit")
    sample_interval_ms: int = Field(100, description="Sampling interval in milliseconds")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class RecordMetricRequest(BaseModel):
    metric_type: str = Field(..., description="Type of metric")
    value: float = Field(..., description="Metric value")
    context: Optional[dict] = Field(None, description="Additional context")


class CreateBenchmarkRequest(BaseModel):
    benchmark_name: str = Field(..., description="Benchmark name")
    benchmark_type: str = Field(..., description="Type of benchmark")
    target_agents: List[str] = Field(..., description="Agents to benchmark")
    test_duration_seconds: int = Field(60, description="Test duration")
    target_throughput: Optional[int] = Field(None, description="Target requests per second")
    max_latency_ms: Optional[float] = Field(None, description="Maximum acceptable latency")
    concurrent_requests: int = Field(10, description="Concurrent request count")
    description: Optional[str] = Field(None, description="Benchmark description")
    test_data: Optional[dict] = Field(None, description="Test data configuration")


class RunBenchmarkRequest(BaseModel):
    iterations: int = Field(1, description="Number of test iterations")
    warmup_iterations: int = Field(0, description="Warmup iterations (not counted)")


class SetBaselineRequest(BaseModel):
    baseline_name: str = Field(..., description="Baseline name")
    metrics: dict = Field(..., description="Baseline metrics")
    description: Optional[str] = Field(None, description="Baseline description")


class CompareAgentsRequest(BaseModel):
    agent_ids: List[str] = Field(..., description="Agents to compare")
    metric_types: List[str] = Field(..., description="Metrics to compare")
    time_range_hours: int = Field(24, description="Time range for comparison")


@router.post("/profile-sessions")
def start_profile_session(
    request: StartProfileSessionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Start profiling session.

    Initiates performance profiling for an agent with specified metrics.
    """
    try:
        profile_session = AgentProfiling.start_profile_session(
            session=session,
            agent_id=request.agent_id,
            profile_name=request.profile_name,
            metric_types=request.metric_types,
            duration_seconds=request.duration_seconds,
            sample_interval_ms=request.sample_interval_ms,
            metadata=request.metadata
        )

        return {
            "success": True,
            "profile_session": profile_session,
            "message": f"Profile session started: {profile_session['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profile-sessions/{profile_id}/metrics")
def record_metric(
    profile_id: str,
    request: RecordMetricRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record performance metric.

    Records a metric sample during an active profiling session.
    """
    try:
        metric = AgentProfiling.record_metric(
            session=session,
            profile_id=profile_id,
            metric_type=request.metric_type,
            value=request.value,
            context=request.context
        )

        return {
            "success": True,
            "metric": metric,
            "message": "Metric recorded"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/profile-sessions/{profile_id}/end")
def end_profile_session(
    profile_id: str,
    status: str = ProfileStatus.COMPLETED,
    session: Session = Depends(get_db_session)
):
    """
    End profiling session.

    Completes profiling session and generates summary with bottleneck detection.
    """
    try:
        profile_session = AgentProfiling.end_profile_session(
            session=session,
            profile_id=profile_id,
            status=status
        )

        return {
            "success": True,
            "profile_session": profile_session,
            "message": f"Profile session ended: {profile_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/profile-history")
def get_profile_history(
    agent_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    Get profiling history.

    Returns profiling session history for an agent.
    """
    try:
        result = AgentProfiling.get_profile_history(
            session=session,
            agent_id=agent_id,
            status=status,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/benchmarks")
def create_benchmark(
    request: CreateBenchmarkRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create benchmark test.

    Creates a benchmark configuration for performance testing.
    """
    try:
        benchmark = AgentProfiling.create_benchmark(
            session=session,
            benchmark_name=request.benchmark_name,
            benchmark_type=request.benchmark_type,
            target_agents=request.target_agents,
            test_duration_seconds=request.test_duration_seconds,
            target_throughput=request.target_throughput,
            max_latency_ms=request.max_latency_ms,
            concurrent_requests=request.concurrent_requests,
            description=request.description,
            test_data=request.test_data
        )

        return {
            "success": True,
            "benchmark": benchmark,
            "message": f"Benchmark created: {benchmark['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/benchmarks/{benchmark_id}/run")
def run_benchmark(
    benchmark_id: str,
    request: RunBenchmarkRequest,
    session: Session = Depends(get_db_session)
):
    """
    Run benchmark test.

    Executes benchmark test and returns performance results.
    """
    try:
        result = AgentProfiling.run_benchmark(
            session=session,
            benchmark_id=benchmark_id,
            iterations=request.iterations,
            warmup_iterations=request.warmup_iterations
        )

        return {
            "success": True,
            "result": result,
            "message": f"Benchmark completed: {result['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/benchmarks/{benchmark_id}/results")
def get_benchmark_results(
    benchmark_id: str,
    limit: int = 10,
    session: Session = Depends(get_db_session)
):
    """
    Get benchmark results.

    Returns historical results for a benchmark.
    """
    try:
        from src.services.agent_profiling import AgentProfiling as AP
        results = AP._benchmark_results.get(benchmark_id, [])
        results = sorted(results, key=lambda x: x["executed_at"], reverse=True)[:limit]

        return {
            "success": True,
            "benchmark_id": benchmark_id,
            "results": results,
            "total_runs": len(results)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/baseline")
def set_baseline(
    agent_id: str,
    request: SetBaselineRequest,
    session: Session = Depends(get_db_session)
):
    """
    Set performance baseline.

    Establishes performance baseline for agent comparison.
    """
    try:
        baseline = AgentProfiling.set_baseline(
            session=session,
            agent_id=agent_id,
            baseline_name=request.baseline_name,
            metrics=request.metrics,
            description=request.description
        )

        return {
            "success": True,
            "baseline": baseline,
            "message": f"Baseline set: {baseline['id']}"
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
    Compare agent performance.

    Compares performance metrics across multiple agents.
    """
    try:
        comparison = AgentProfiling.compare_agents(
            session=session,
            agent_ids=request.agent_ids,
            metric_types=request.metric_types,
            time_range_hours=request.time_range_hours
        )

        return {
            "success": True,
            "comparison": comparison,
            "message": "Comparison completed"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bottlenecks")
def get_bottlenecks(
    agent_id: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    Get performance bottlenecks.

    Returns identified bottlenecks with severity classification.
    """
    try:
        result = AgentProfiling.get_bottlenecks(
            session=session,
            agent_id=agent_id,
            severity=severity,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/recommendations")
def get_optimization_recommendations(
    agent_id: str,
    profile_id: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get optimization recommendations.

    Generates optimization recommendations based on profiling data.
    """
    try:
        result = AgentProfiling.generate_optimization_recommendations(
            session=session,
            agent_id=agent_id,
            profile_id=profile_id
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get profiling statistics.

    Returns aggregate metrics including session counts, benchmarks,
    and bottleneck distribution.
    """
    try:
        stats = AgentProfiling.get_statistics(session=session)

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

    Returns all available metric types for profiling.
    """
    return {
        "success": True,
        "metric_types": [
            {"type": ProfileMetricType.EXECUTION_TIME, "description": "Operation execution time"},
            {"type": ProfileMetricType.CPU_USAGE, "description": "CPU utilization"},
            {"type": ProfileMetricType.MEMORY_USAGE, "description": "Memory consumption"},
            {"type": ProfileMetricType.IO_OPERATIONS, "description": "I/O operations count"},
            {"type": ProfileMetricType.NETWORK_CALLS, "description": "Network calls count"},
            {"type": ProfileMetricType.DATABASE_QUERIES, "description": "Database query count"},
            {"type": ProfileMetricType.CACHE_HITS, "description": "Cache hit ratio"},
            {"type": ProfileMetricType.ERROR_RATE, "description": "Error occurrence rate"}
        ]
    }


@router.get("/benchmark-types")
def list_benchmark_types():
    """
    List all benchmark types.

    Returns all available benchmark types.
    """
    return {
        "success": True,
        "benchmark_types": [
            {"type": BenchmarkType.THROUGHPUT, "description": "Throughput testing"},
            {"type": BenchmarkType.LATENCY, "description": "Latency measurement"},
            {"type": BenchmarkType.CONCURRENCY, "description": "Concurrent load testing"},
            {"type": BenchmarkType.STRESS, "description": "Stress testing"},
            {"type": BenchmarkType.ENDURANCE, "description": "Endurance testing"},
            {"type": BenchmarkType.SPIKE, "description": "Spike testing"}
        ]
    }


@router.get("/profile-statuses")
def list_profile_statuses():
    """
    List all profile statuses.

    Returns all possible profile session status values.
    """
    return {
        "success": True,
        "profile_statuses": [
            {"status": ProfileStatus.ACTIVE, "description": "Profile session is active"},
            {"status": ProfileStatus.COMPLETED, "description": "Profile session completed"},
            {"status": ProfileStatus.FAILED, "description": "Profile session failed"},
            {"status": ProfileStatus.CANCELLED, "description": "Profile session cancelled"}
        ]
    }


@router.get("/bottleneck-severities")
def list_bottleneck_severities():
    """
    List all bottleneck severities.

    Returns all severity levels for bottleneck classification.
    """
    return {
        "success": True,
        "bottleneck_severities": [
            {"severity": BottleneckSeverity.CRITICAL, "description": "Critical impact - immediate attention required"},
            {"severity": BottleneckSeverity.HIGH, "description": "High impact - prioritize resolution"},
            {"severity": BottleneckSeverity.MEDIUM, "description": "Medium impact - address soon"},
            {"severity": BottleneckSeverity.LOW, "description": "Low impact - optimize when possible"}
        ]
    }
