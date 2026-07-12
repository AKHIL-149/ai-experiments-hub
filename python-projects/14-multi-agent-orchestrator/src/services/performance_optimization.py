"""
Performance Optimization Service

Provides performance profiling, bottleneck detection, and optimization recommendations
for improving system performance and resource utilization.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from enum import Enum
import statistics


class OptimizationType(str, Enum):
    """Types of optimizations"""
    QUERY = "query"
    CACHE = "cache"
    MEMORY = "memory"
    CPU = "cpu"
    NETWORK = "network"
    ALGORITHM = "algorithm"


class Severity(str, Enum):
    """Optimization severity"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProfileType(str, Enum):
    """Profiling types"""
    CPU = "cpu"
    MEMORY = "memory"
    IO = "io"
    DATABASE = "database"
    API = "api"
    FULL = "full"


class PerformanceOptimization:
    """Performance optimization management"""

    # In-memory storage
    _profiles: Dict[str, Dict] = {}
    _bottlenecks: Dict[str, Dict] = {}
    _optimizations: Dict[str, Dict] = {}
    _benchmarks: Dict[str, Dict] = {}
    _resource_metrics: List[Dict] = []
    _query_analysis: Dict[str, Dict] = {}

    @staticmethod
    def create_profile(
        session,
        profile_id: str,
        name: str,
        profile_type: ProfileType,
        target: str,
        duration_seconds: int = 60,
        sample_rate: int = 100,
        enabled: bool = True
    ) -> dict:
        """Create a performance profiling session."""
        if profile_id in PerformanceOptimization._profiles:
            raise ValueError(f"Profile already exists: {profile_id}")

        profile = {
            "profile_id": profile_id,
            "name": name,
            "profile_type": profile_type,
            "target": target,
            "duration_seconds": duration_seconds,
            "sample_rate": sample_rate,
            "enabled": enabled,
            "created_at": datetime.utcnow().isoformat(),
            "status": "pending",
            "samples_collected": 0,
            "results": None,
            "started_at": None,
            "completed_at": None
        }

        PerformanceOptimization._profiles[profile_id] = profile
        return profile

    @staticmethod
    def start_profiling(
        session,
        profile_id: str
    ) -> dict:
        """Start a profiling session."""
        profile = PerformanceOptimization._profiles.get(profile_id)
        if not profile:
            raise ValueError(f"Profile not found: {profile_id}")

        if profile["status"] == "running":
            raise ValueError("Profile is already running")

        profile["status"] = "running"
        profile["started_at"] = datetime.utcnow().isoformat()

        return {
            "profile_id": profile_id,
            "status": "running",
            "started_at": profile["started_at"]
        }

    @staticmethod
    def stop_profiling(
        session,
        profile_id: str
    ) -> dict:
        """Stop a profiling session and generate results."""
        profile = PerformanceOptimization._profiles.get(profile_id)
        if not profile:
            raise ValueError(f"Profile not found: {profile_id}")

        if profile["status"] != "running":
            raise ValueError("Profile is not running")

        profile["status"] = "completed"
        profile["completed_at"] = datetime.utcnow().isoformat()

        # Generate mock profiling results
        if profile["profile_type"] == ProfileType.CPU:
            profile["results"] = {
                "cpu_usage": {
                    "avg": 45.2,
                    "max": 78.5,
                    "min": 12.3,
                    "p95": 68.4
                },
                "top_functions": [
                    {"function": "process_data", "cpu_time": 1234.5, "calls": 1500},
                    {"function": "parse_json", "cpu_time": 987.2, "calls": 3200},
                    {"function": "validate_input", "cpu_time": 654.1, "calls": 2100}
                ]
            }
        elif profile["profile_type"] == ProfileType.MEMORY:
            profile["results"] = {
                "memory_usage": {
                    "avg_mb": 512.4,
                    "max_mb": 1024.8,
                    "min_mb": 256.2,
                    "leaked_mb": 12.5
                },
                "allocations": 15234,
                "deallocations": 14987,
                "top_allocators": [
                    {"function": "create_cache", "allocated_mb": 256.5},
                    {"function": "load_data", "allocated_mb": 128.3},
                    {"function": "build_index", "allocated_mb": 95.7}
                ]
            }
        elif profile["profile_type"] == ProfileType.DATABASE:
            profile["results"] = {
                "query_count": 3458,
                "avg_query_time_ms": 45.2,
                "slow_queries": 42,
                "n_plus_one_detected": 5,
                "missing_indexes": 3,
                "top_slow_queries": [
                    {"query": "SELECT * FROM users WHERE...", "time_ms": 1245.3, "count": 156},
                    {"query": "SELECT * FROM orders JOIN...", "time_ms": 987.6, "count": 89}
                ]
            }

        # Detect bottlenecks
        PerformanceOptimization._detect_bottlenecks(profile)

        return {
            "profile_id": profile_id,
            "status": "completed",
            "completed_at": profile["completed_at"],
            "results": profile["results"]
        }

    @staticmethod
    def _detect_bottlenecks(profile: dict):
        """Detect performance bottlenecks from profiling results."""
        results = profile.get("results", {})

        if profile["profile_type"] == ProfileType.CPU:
            cpu_usage = results.get("cpu_usage", {})
            if cpu_usage.get("max", 0) > 80:
                PerformanceOptimization._create_bottleneck(
                    profile_id=profile["profile_id"],
                    bottleneck_type="cpu",
                    severity=Severity.HIGH,
                    description=f"High CPU usage detected: {cpu_usage['max']}%",
                    location=profile["target"],
                    metrics=cpu_usage
                )

        elif profile["profile_type"] == ProfileType.MEMORY:
            memory_usage = results.get("memory_usage", {})
            if memory_usage.get("leaked_mb", 0) > 10:
                PerformanceOptimization._create_bottleneck(
                    profile_id=profile["profile_id"],
                    bottleneck_type="memory_leak",
                    severity=Severity.CRITICAL,
                    description=f"Memory leak detected: {memory_usage['leaked_mb']} MB",
                    location=profile["target"],
                    metrics=memory_usage
                )

        elif profile["profile_type"] == ProfileType.DATABASE:
            if results.get("slow_queries", 0) > 20:
                PerformanceOptimization._create_bottleneck(
                    profile_id=profile["profile_id"],
                    bottleneck_type="slow_queries",
                    severity=Severity.HIGH,
                    description=f"{results['slow_queries']} slow database queries detected",
                    location=profile["target"],
                    metrics={"slow_query_count": results["slow_queries"]}
                )

            if results.get("n_plus_one_detected", 0) > 0:
                PerformanceOptimization._create_bottleneck(
                    profile_id=profile["profile_id"],
                    bottleneck_type="n_plus_one",
                    severity=Severity.HIGH,
                    description=f"N+1 query problem detected in {results['n_plus_one_detected']} locations",
                    location=profile["target"],
                    metrics={"n_plus_one_count": results["n_plus_one_detected"]}
                )

    @staticmethod
    def _create_bottleneck(
        profile_id: str,
        bottleneck_type: str,
        severity: Severity,
        description: str,
        location: str,
        metrics: Dict
    ):
        """Create a bottleneck entry."""
        bottleneck_id = f"bottleneck_{len(PerformanceOptimization._bottlenecks)}_{datetime.utcnow().timestamp()}"

        bottleneck = {
            "bottleneck_id": bottleneck_id,
            "profile_id": profile_id,
            "bottleneck_type": bottleneck_type,
            "severity": severity,
            "description": description,
            "location": location,
            "metrics": metrics,
            "detected_at": datetime.utcnow().isoformat(),
            "resolved": False,
            "optimization_id": None
        }

        PerformanceOptimization._bottlenecks[bottleneck_id] = bottleneck

        # Generate optimization recommendation
        PerformanceOptimization._generate_optimization(bottleneck)

    @staticmethod
    def _generate_optimization(bottleneck: dict):
        """Generate optimization recommendation for a bottleneck."""
        optimization_id = f"opt_{len(PerformanceOptimization._optimizations)}_{datetime.utcnow().timestamp()}"

        recommendations = {
            "cpu": {
                "type": OptimizationType.CPU,
                "recommendations": [
                    "Consider implementing caching for frequently accessed data",
                    "Review algorithm complexity in hot paths",
                    "Use async/await for I/O operations",
                    "Profile and optimize the most CPU-intensive functions"
                ],
                "expected_improvement": "30-50% reduction in CPU usage"
            },
            "memory_leak": {
                "type": OptimizationType.MEMORY,
                "recommendations": [
                    "Review object lifecycle and ensure proper cleanup",
                    "Check for circular references preventing garbage collection",
                    "Use weak references where appropriate",
                    "Implement connection pooling with proper resource cleanup"
                ],
                "expected_improvement": "Eliminate memory growth over time"
            },
            "slow_queries": {
                "type": OptimizationType.QUERY,
                "recommendations": [
                    "Add database indexes on frequently queried columns",
                    "Optimize JOIN operations and query structure",
                    "Implement query result caching",
                    "Use database query explain plans to identify inefficiencies"
                ],
                "expected_improvement": "50-80% reduction in query time"
            },
            "n_plus_one": {
                "type": OptimizationType.QUERY,
                "recommendations": [
                    "Use eager loading to fetch related data",
                    "Implement batch loading with DataLoader pattern",
                    "Add select_related() or prefetch_related() in ORM queries",
                    "Consider denormalization for frequently accessed data"
                ],
                "expected_improvement": "90%+ reduction in query count"
            }
        }

        bottleneck_type = bottleneck["bottleneck_type"]
        rec = recommendations.get(bottleneck_type, {
            "type": OptimizationType.ALGORITHM,
            "recommendations": ["Review implementation for optimization opportunities"],
            "expected_improvement": "Varies"
        })

        optimization = {
            "optimization_id": optimization_id,
            "bottleneck_id": bottleneck["bottleneck_id"],
            "optimization_type": rec["type"],
            "severity": bottleneck["severity"],
            "title": f"Optimize {bottleneck_type}",
            "description": bottleneck["description"],
            "recommendations": rec["recommendations"],
            "expected_improvement": rec["expected_improvement"],
            "location": bottleneck["location"],
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
            "applied_at": None,
            "impact": None
        }

        PerformanceOptimization._optimizations[optimization_id] = optimization
        bottleneck["optimization_id"] = optimization_id

    @staticmethod
    def get_bottlenecks(
        session,
        severity: Optional[Severity] = None,
        resolved: Optional[bool] = None
    ) -> List[dict]:
        """Get detected performance bottlenecks."""
        bottlenecks = list(PerformanceOptimization._bottlenecks.values())

        if severity:
            bottlenecks = [b for b in bottlenecks if b["severity"] == severity]

        if resolved is not None:
            bottlenecks = [b for b in bottlenecks if b["resolved"] == resolved]

        # Sort by severity and detection time
        severity_order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
        bottlenecks.sort(key=lambda x: (severity_order.get(x["severity"], 4), x["detected_at"]), reverse=True)

        return bottlenecks

    @staticmethod
    def get_optimizations(
        session,
        status: Optional[str] = None,
        optimization_type: Optional[OptimizationType] = None
    ) -> List[dict]:
        """Get optimization recommendations."""
        optimizations = list(PerformanceOptimization._optimizations.values())

        if status:
            optimizations = [o for o in optimizations if o["status"] == status]

        if optimization_type:
            optimizations = [o for o in optimizations if o["optimization_type"] == optimization_type]

        # Sort by severity
        severity_order = {Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2, Severity.LOW: 3}
        optimizations.sort(key=lambda x: (severity_order.get(x["severity"], 4), x["created_at"]), reverse=True)

        return optimizations

    @staticmethod
    def apply_optimization(
        session,
        optimization_id: str,
        impact_notes: Optional[str] = None
    ) -> dict:
        """Mark an optimization as applied."""
        optimization = PerformanceOptimization._optimizations.get(optimization_id)
        if not optimization:
            raise ValueError(f"Optimization not found: {optimization_id}")

        optimization["status"] = "applied"
        optimization["applied_at"] = datetime.utcnow().isoformat()
        optimization["impact"] = impact_notes

        # Mark bottleneck as resolved
        bottleneck = PerformanceOptimization._bottlenecks.get(optimization["bottleneck_id"])
        if bottleneck:
            bottleneck["resolved"] = True

        return {
            "optimization_id": optimization_id,
            "status": "applied",
            "applied_at": optimization["applied_at"]
        }

    @staticmethod
    def record_resource_metrics(
        session,
        cpu_percent: float,
        memory_mb: float,
        disk_io_mb: float,
        network_io_mb: float,
        active_connections: int,
        timestamp: Optional[str] = None
    ) -> dict:
        """Record resource utilization metrics."""
        metric = {
            "timestamp": timestamp or datetime.utcnow().isoformat(),
            "cpu_percent": cpu_percent,
            "memory_mb": memory_mb,
            "disk_io_mb": disk_io_mb,
            "network_io_mb": network_io_mb,
            "active_connections": active_connections
        }

        PerformanceOptimization._resource_metrics.append(metric)

        # Keep only last 24 hours
        cutoff = datetime.utcnow() - timedelta(hours=24)
        cutoff_iso = cutoff.isoformat()
        PerformanceOptimization._resource_metrics = [
            m for m in PerformanceOptimization._resource_metrics
            if m["timestamp"] >= cutoff_iso
        ]

        return metric

    @staticmethod
    def get_resource_utilization(
        session,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> dict:
        """Get resource utilization statistics."""
        metrics = PerformanceOptimization._resource_metrics.copy()

        if start_time:
            metrics = [m for m in metrics if m["timestamp"] >= start_time]
        if end_time:
            metrics = [m for m in metrics if m["timestamp"] <= end_time]

        if not metrics:
            return {
                "metrics_count": 0,
                "time_range": {"start": start_time, "end": end_time}
            }

        cpu_values = [m["cpu_percent"] for m in metrics]
        memory_values = [m["memory_mb"] for m in metrics]
        disk_values = [m["disk_io_mb"] for m in metrics]
        network_values = [m["network_io_mb"] for m in metrics]
        connection_values = [m["active_connections"] for m in metrics]

        return {
            "metrics_count": len(metrics),
            "time_range": {
                "start": metrics[0]["timestamp"],
                "end": metrics[-1]["timestamp"]
            },
            "cpu": {
                "avg": statistics.mean(cpu_values),
                "max": max(cpu_values),
                "min": min(cpu_values),
                "p95": statistics.quantiles(cpu_values, n=20)[18] if len(cpu_values) > 1 else cpu_values[0]
            },
            "memory_mb": {
                "avg": statistics.mean(memory_values),
                "max": max(memory_values),
                "min": min(memory_values),
                "p95": statistics.quantiles(memory_values, n=20)[18] if len(memory_values) > 1 else memory_values[0]
            },
            "disk_io_mb": {
                "total": sum(disk_values),
                "avg": statistics.mean(disk_values)
            },
            "network_io_mb": {
                "total": sum(network_values),
                "avg": statistics.mean(network_values)
            },
            "connections": {
                "avg": statistics.mean(connection_values),
                "max": max(connection_values)
            }
        }

    @staticmethod
    def analyze_query(
        session,
        query_id: str,
        query: str,
        execution_time_ms: float,
        rows_examined: int,
        rows_returned: int,
        index_used: bool
    ) -> dict:
        """Analyze a database query for optimization opportunities."""
        analysis = {
            "query_id": query_id,
            "query": query,
            "execution_time_ms": execution_time_ms,
            "rows_examined": rows_examined,
            "rows_returned": rows_returned,
            "index_used": index_used,
            "analyzed_at": datetime.utcnow().isoformat(),
            "issues": [],
            "recommendations": []
        }

        # Analyze query performance
        if execution_time_ms > 1000:
            analysis["issues"].append("Slow query execution (>1 second)")
            analysis["recommendations"].append("Consider adding indexes or optimizing query structure")

        if not index_used:
            analysis["issues"].append("No index used - full table scan")
            analysis["recommendations"].append("Add appropriate indexes for WHERE clause columns")

        if rows_examined > rows_returned * 10:
            analysis["issues"].append(f"Inefficient scan: examined {rows_examined} rows to return {rows_returned}")
            analysis["recommendations"].append("Improve query selectivity with better WHERE conditions")

        if "SELECT *" in query.upper():
            analysis["issues"].append("SELECT * detected - fetching unnecessary columns")
            analysis["recommendations"].append("Select only needed columns explicitly")

        if rows_returned > 1000:
            analysis["issues"].append(f"Large result set: {rows_returned} rows")
            analysis["recommendations"].append("Implement pagination to limit result set size")

        analysis["severity"] = "critical" if execution_time_ms > 5000 else "high" if execution_time_ms > 1000 else "medium"
        analysis["optimization_score"] = max(0, 100 - (len(analysis["issues"]) * 20))

        PerformanceOptimization._query_analysis[query_id] = analysis
        return analysis

    @staticmethod
    def create_benchmark(
        session,
        benchmark_id: str,
        name: str,
        target: str,
        operations: int,
        concurrency: int = 1
    ) -> dict:
        """Create a performance benchmark."""
        if benchmark_id in PerformanceOptimization._benchmarks:
            raise ValueError(f"Benchmark already exists: {benchmark_id}")

        benchmark = {
            "benchmark_id": benchmark_id,
            "name": name,
            "target": target,
            "operations": operations,
            "concurrency": concurrency,
            "created_at": datetime.utcnow().isoformat(),
            "status": "pending",
            "results": None,
            "completed_at": None
        }

        PerformanceOptimization._benchmarks[benchmark_id] = benchmark
        return benchmark

    @staticmethod
    def run_benchmark(
        session,
        benchmark_id: str
    ) -> dict:
        """Run a performance benchmark."""
        benchmark = PerformanceOptimization._benchmarks.get(benchmark_id)
        if not benchmark:
            raise ValueError(f"Benchmark not found: {benchmark_id}")

        benchmark["status"] = "running"

        # Simulate benchmark execution
        import random
        response_times = [random.uniform(10, 200) for _ in range(min(benchmark["operations"], 1000))]

        benchmark["results"] = {
            "total_operations": benchmark["operations"],
            "successful": benchmark["operations"] - random.randint(0, 5),
            "failed": random.randint(0, 5),
            "response_time_ms": {
                "avg": statistics.mean(response_times),
                "min": min(response_times),
                "max": max(response_times),
                "p50": statistics.median(response_times),
                "p95": statistics.quantiles(response_times, n=20)[18],
                "p99": statistics.quantiles(response_times, n=100)[98]
            },
            "throughput_ops_per_sec": benchmark["operations"] / random.uniform(5, 15),
            "concurrency": benchmark["concurrency"]
        }

        benchmark["status"] = "completed"
        benchmark["completed_at"] = datetime.utcnow().isoformat()

        return {
            "benchmark_id": benchmark_id,
            "status": "completed",
            "results": benchmark["results"]
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get performance optimization statistics."""
        bottlenecks_by_severity = defaultdict(int)
        for bottleneck in PerformanceOptimization._bottlenecks.values():
            bottlenecks_by_severity[bottleneck["severity"]] += 1

        optimizations_by_status = defaultdict(int)
        for optimization in PerformanceOptimization._optimizations.values():
            optimizations_by_status[optimization["status"]] += 1

        return {
            "profiles": {
                "total": len(PerformanceOptimization._profiles),
                "completed": sum(1 for p in PerformanceOptimization._profiles.values() if p["status"] == "completed")
            },
            "bottlenecks": {
                "total": len(PerformanceOptimization._bottlenecks),
                "unresolved": sum(1 for b in PerformanceOptimization._bottlenecks.values() if not b["resolved"]),
                "by_severity": dict(bottlenecks_by_severity)
            },
            "optimizations": {
                "total": len(PerformanceOptimization._optimizations),
                "by_status": dict(optimizations_by_status)
            },
            "resource_metrics": len(PerformanceOptimization._resource_metrics),
            "query_analyses": len(PerformanceOptimization._query_analysis),
            "benchmarks": len(PerformanceOptimization._benchmarks)
        }
