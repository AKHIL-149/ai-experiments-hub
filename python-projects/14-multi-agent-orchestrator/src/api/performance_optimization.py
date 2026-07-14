"""
Performance Optimization API

REST API endpoints for performance profiling, bottleneck detection, and optimization.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.performance_optimization import (
    PerformanceOptimization,
    OptimizationType,
    Severity,
    ProfileType
)


router = APIRouter()


# Request/Response Models
class CreateProfileRequest(BaseModel):
    """Request model for creating a profile"""
    profile_id: str = Field(..., description="Unique profile identifier")
    name: str = Field(..., description="Profile name")
    profile_type: ProfileType = Field(..., description="Type of profiling")
    target: str = Field(..., description="Target to profile")
    duration_seconds: int = Field(default=60, description="Profile duration", ge=1, le=3600)
    sample_rate: int = Field(default=100, description="Sample rate", ge=1, le=1000)
    enabled: bool = Field(default=True, description="Whether profile is enabled")


class ApplyOptimizationRequest(BaseModel):
    """Request model for applying an optimization"""
    impact_notes: Optional[str] = Field(default=None, description="Notes about impact")


class RecordResourceMetricsRequest(BaseModel):
    """Request model for recording resource metrics"""
    cpu_percent: float = Field(..., description="CPU usage percentage", ge=0, le=100)
    memory_mb: float = Field(..., description="Memory usage in MB", ge=0)
    disk_io_mb: float = Field(..., description="Disk I/O in MB", ge=0)
    network_io_mb: float = Field(..., description="Network I/O in MB", ge=0)
    active_connections: int = Field(..., description="Active connections", ge=0)
    timestamp: Optional[str] = Field(default=None, description="ISO timestamp")


class AnalyzeQueryRequest(BaseModel):
    """Request model for analyzing a query"""
    query_id: str = Field(..., description="Unique query identifier")
    query: str = Field(..., description="SQL query")
    execution_time_ms: float = Field(..., description="Execution time in ms", ge=0)
    rows_examined: int = Field(..., description="Rows examined", ge=0)
    rows_returned: int = Field(..., description="Rows returned", ge=0)
    index_used: bool = Field(..., description="Whether an index was used")


class CreateBenchmarkRequest(BaseModel):
    """Request model for creating a benchmark"""
    benchmark_id: str = Field(..., description="Unique benchmark identifier")
    name: str = Field(..., description="Benchmark name")
    target: str = Field(..., description="Target to benchmark")
    operations: int = Field(..., description="Number of operations", ge=1)
    concurrency: int = Field(default=1, description="Concurrency level", ge=1, le=1000)


# API Endpoints
@router.post("/profiles")
def create_profile(
    request: CreateProfileRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a performance profile.
    Defines a profiling session for CPU, memory, I/O, or database performance.
    """
    try:
        result = PerformanceOptimization.create_profile(
            session=session,
            profile_id=request.profile_id,
            name=request.name,
            profile_type=request.profile_type,
            target=request.target,
            duration_seconds=request.duration_seconds,
            sample_rate=request.sample_rate,
            enabled=request.enabled
        )
        return {
            "success": True,
            "profile": result,
            "message": f"Profile created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating profile: {str(e)}")


@router.post("/profiles/{profile_id}/start")
def start_profiling(
    profile_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Start profiling.
    Begins collecting performance data for the specified profile.
    """
    try:
        result = PerformanceOptimization.start_profiling(
            session=session,
            profile_id=profile_id
        )
        return {
            "success": True,
            "profiling": result,
            "message": "Profiling started"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting profiling: {str(e)}")


@router.post("/profiles/{profile_id}/stop")
def stop_profiling(
    profile_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Stop profiling.
    Stops data collection and generates profiling results.
    Automatically detects bottlenecks and generates optimization recommendations.
    """
    try:
        result = PerformanceOptimization.stop_profiling(
            session=session,
            profile_id=profile_id
        )
        return {
            "success": True,
            "profiling": result,
            "message": "Profiling completed and results generated"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error stopping profiling: {str(e)}")


@router.get("/profiles")
def list_profiles(session: Session = Depends(get_db_session)):
    """
    List all profiles.
    Returns all performance profiling sessions.
    """
    try:
        profiles = list(PerformanceOptimization._profiles.values())
        return {
            "success": True,
            "profiles": profiles,
            "count": len(profiles)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing profiles: {str(e)}")


@router.get("/bottlenecks")
def get_bottlenecks(
    severity: Optional[Severity] = None,
    resolved: Optional[bool] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get performance bottlenecks.
    Returns detected bottlenecks with optional filtering.
    """
    try:
        bottlenecks = PerformanceOptimization.get_bottlenecks(
            session=session,
            severity=severity,
            resolved=resolved
        )
        return {
            "success": True,
            "bottlenecks": bottlenecks,
            "count": len(bottlenecks)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting bottlenecks: {str(e)}")


@router.get("/optimizations")
def get_optimizations(
    status: Optional[str] = None,
    optimization_type: Optional[OptimizationType] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get optimization recommendations.
    Returns optimization suggestions with optional filtering.
    """
    try:
        optimizations = PerformanceOptimization.get_optimizations(
            session=session,
            status=status,
            optimization_type=optimization_type
        )
        return {
            "success": True,
            "optimizations": optimizations,
            "count": len(optimizations)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting optimizations: {str(e)}")


@router.post("/optimizations/{optimization_id}/apply")
def apply_optimization(
    optimization_id: str,
    request: ApplyOptimizationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Apply an optimization.
    Marks an optimization as applied and resolves the associated bottleneck.
    """
    try:
        result = PerformanceOptimization.apply_optimization(
            session=session,
            optimization_id=optimization_id,
            impact_notes=request.impact_notes
        )
        return {
            "success": True,
            "application": result,
            "message": "Optimization applied"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying optimization: {str(e)}")


@router.post("/resource-metrics")
def record_resource_metrics(
    request: RecordResourceMetricsRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record resource metrics.
    Stores CPU, memory, disk, network, and connection metrics.
    """
    try:
        result = PerformanceOptimization.record_resource_metrics(
            session=session,
            cpu_percent=request.cpu_percent,
            memory_mb=request.memory_mb,
            disk_io_mb=request.disk_io_mb,
            network_io_mb=request.network_io_mb,
            active_connections=request.active_connections,
            timestamp=request.timestamp
        )
        return {
            "success": True,
            "metric": result,
            "message": "Resource metrics recorded"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error recording metrics: {str(e)}")


@router.get("/resource-utilization")
def get_resource_utilization(
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get resource utilization.
    Returns aggregated resource usage statistics.
    """
    try:
        result = PerformanceOptimization.get_resource_utilization(
            session=session,
            start_time=start_time,
            end_time=end_time
        )
        return {
            "success": True,
            "utilization": result,
            "message": "Resource utilization retrieved"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting resource utilization: {str(e)}")


@router.post("/query-analysis")
def analyze_query(
    request: AnalyzeQueryRequest,
    session: Session = Depends(get_db_session)
):
    """
    Analyze a query.
    Analyzes database query performance and provides optimization recommendations.
    """
    try:
        result = PerformanceOptimization.analyze_query(
            session=session,
            query_id=request.query_id,
            query=request.query,
            execution_time_ms=request.execution_time_ms,
            rows_examined=request.rows_examined,
            rows_returned=request.rows_returned,
            index_used=request.index_used
        )
        return {
            "success": True,
            "analysis": result,
            "message": f"Query analyzed - optimization score: {result['optimization_score']}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing query: {str(e)}")


@router.get("/query-analysis")
def list_query_analyses(session: Session = Depends(get_db_session)):
    """
    List query analyses.
    Returns all query performance analyses.
    """
    try:
        analyses = list(PerformanceOptimization._query_analysis.values())
        return {
            "success": True,
            "analyses": analyses,
            "count": len(analyses)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing query analyses: {str(e)}")


@router.post("/benchmarks")
def create_benchmark(
    request: CreateBenchmarkRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a benchmark.
    Defines a performance benchmark test.
    """
    try:
        result = PerformanceOptimization.create_benchmark(
            session=session,
            benchmark_id=request.benchmark_id,
            name=request.name,
            target=request.target,
            operations=request.operations,
            concurrency=request.concurrency
        )
        return {
            "success": True,
            "benchmark": result,
            "message": f"Benchmark created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating benchmark: {str(e)}")


@router.post("/benchmarks/{benchmark_id}/run")
def run_benchmark(
    benchmark_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Run a benchmark.
    Executes the benchmark and generates performance metrics.
    """
    try:
        result = PerformanceOptimization.run_benchmark(
            session=session,
            benchmark_id=benchmark_id
        )
        return {
            "success": True,
            "benchmark": result,
            "message": "Benchmark completed"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error running benchmark: {str(e)}")


@router.get("/benchmarks")
def list_benchmarks(session: Session = Depends(get_db_session)):
    """
    List all benchmarks.
    Returns all performance benchmarks.
    """
    try:
        benchmarks = list(PerformanceOptimization._benchmarks.values())
        return {
            "success": True,
            "benchmarks": benchmarks,
            "count": len(benchmarks)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing benchmarks: {str(e)}")


@router.get("/statistics")
def get_statistics(session: Session = Depends(get_db_session)):
    """
    Get statistics.
    Returns comprehensive performance optimization statistics.
    """
    try:
        stats = PerformanceOptimization.get_statistics(session)
        return {
            "success": True,
            "statistics": stats,
            "message": "Statistics retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")
