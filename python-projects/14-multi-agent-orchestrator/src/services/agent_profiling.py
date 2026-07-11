"""
Agent Profiling and Benchmarking

Provides performance profiling, benchmarking, and resource usage tracking for agents.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import uuid
import time
import statistics


class ProfileMetricType:
    """Profile metric types"""
    EXECUTION_TIME = "execution_time"
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    IO_OPERATIONS = "io_operations"
    NETWORK_CALLS = "network_calls"
    DATABASE_QUERIES = "database_queries"
    CACHE_HITS = "cache_hits"
    ERROR_RATE = "error_rate"


class BenchmarkType:
    """Benchmark types"""
    THROUGHPUT = "throughput"
    LATENCY = "latency"
    CONCURRENCY = "concurrency"
    STRESS = "stress"
    ENDURANCE = "endurance"
    SPIKE = "spike"


class ProfileStatus:
    """Profile session status"""
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BottleneckSeverity:
    """Bottleneck severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentProfiling:
    """Agent Profiling and Benchmarking service"""

    # In-memory storage
    _profile_sessions = {}
    _profile_metrics = defaultdict(list)
    _benchmarks = {}
    _benchmark_results = defaultdict(list)
    _bottlenecks = defaultdict(list)
    _agent_baselines = {}
    _comparison_reports = {}
    _optimization_recommendations = defaultdict(list)

    @staticmethod
    def start_profile_session(
        session,
        agent_id: str,
        profile_name: str,
        metric_types: List[str],
        duration_seconds: Optional[int] = None,
        sample_interval_ms: int = 100,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Start profiling session for agent.

        Args:
            session: Database session
            agent_id: Agent ID to profile
            profile_name: Profile session name
            metric_types: Types of metrics to collect
            duration_seconds: Optional duration limit
            sample_interval_ms: Sampling interval in milliseconds
            metadata: Additional metadata

        Returns:
            Created profile session
        """
        profile_id = f"profile_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        profile_session = {
            "id": profile_id,
            "agent_id": agent_id,
            "name": profile_name,
            "status": ProfileStatus.ACTIVE,
            "metric_types": metric_types,
            "started_at": now.isoformat(),
            "ended_at": None,
            "duration_ms": None,
            "sample_interval_ms": sample_interval_ms,
            "duration_limit_seconds": duration_seconds,
            "samples_collected": 0,
            "metadata": metadata or {},
            "metrics_summary": {}
        }

        AgentProfiling._profile_sessions[profile_id] = profile_session
        return profile_session

    @staticmethod
    def record_metric(
        session,
        profile_id: str,
        metric_type: str,
        value: float,
        timestamp: Optional[datetime] = None,
        context: Optional[dict] = None
    ) -> dict:
        """
        Record performance metric during profiling.

        Args:
            session: Database session
            profile_id: Profile session ID
            metric_type: Type of metric
            value: Metric value
            timestamp: Optional custom timestamp
            context: Additional context

        Returns:
            Recorded metric
        """
        profile_session = AgentProfiling._profile_sessions.get(profile_id)
        if not profile_session:
            raise ValueError(f"Profile session not found: {profile_id}")

        if profile_session["status"] != ProfileStatus.ACTIVE:
            raise ValueError(f"Profile session is not active: {profile_id}")

        metric_id = f"metric_{uuid.uuid4().hex[:12]}"
        now = timestamp or datetime.utcnow()

        metric = {
            "id": metric_id,
            "profile_id": profile_id,
            "agent_id": profile_session["agent_id"],
            "metric_type": metric_type,
            "value": value,
            "timestamp": now.isoformat(),
            "context": context or {}
        }

        AgentProfiling._profile_metrics[profile_id].append(metric)
        profile_session["samples_collected"] += 1

        return metric

    @staticmethod
    def end_profile_session(
        session,
        profile_id: str,
        status: str = ProfileStatus.COMPLETED
    ) -> dict:
        """
        End profiling session and generate summary.

        Args:
            session: Database session
            profile_id: Profile session ID
            status: Final status

        Returns:
            Completed profile session with summary
        """
        profile_session = AgentProfiling._profile_sessions.get(profile_id)
        if not profile_session:
            raise ValueError(f"Profile session not found: {profile_id}")

        now = datetime.utcnow()
        started_at = datetime.fromisoformat(profile_session["started_at"])
        duration_ms = (now - started_at).total_seconds() * 1000

        profile_session["ended_at"] = now.isoformat()
        profile_session["duration_ms"] = duration_ms
        profile_session["status"] = status

        # Generate metrics summary
        metrics = AgentProfiling._profile_metrics[profile_id]
        summary = {}

        for metric_type in profile_session["metric_types"]:
            type_metrics = [m["value"] for m in metrics if m["metric_type"] == metric_type]
            if type_metrics:
                summary[metric_type] = {
                    "count": len(type_metrics),
                    "min": min(type_metrics),
                    "max": max(type_metrics),
                    "avg": statistics.mean(type_metrics),
                    "median": statistics.median(type_metrics),
                    "stddev": statistics.stdev(type_metrics) if len(type_metrics) > 1 else 0
                }

        profile_session["metrics_summary"] = summary

        # Detect bottlenecks
        AgentProfiling._detect_bottlenecks(profile_id, profile_session, metrics)

        return profile_session

    @staticmethod
    def create_benchmark(
        session,
        benchmark_name: str,
        benchmark_type: str,
        target_agents: List[str],
        test_duration_seconds: int = 60,
        target_throughput: Optional[int] = None,
        max_latency_ms: Optional[float] = None,
        concurrent_requests: int = 10,
        description: Optional[str] = None,
        test_data: Optional[dict] = None
    ) -> dict:
        """
        Create benchmark test.

        Args:
            session: Database session
            benchmark_name: Benchmark name
            benchmark_type: Type of benchmark
            target_agents: Agents to benchmark
            test_duration_seconds: Test duration
            target_throughput: Target requests per second
            max_latency_ms: Maximum acceptable latency
            concurrent_requests: Concurrent request count
            description: Benchmark description
            test_data: Test data configuration

        Returns:
            Created benchmark
        """
        benchmark_id = f"benchmark_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        benchmark = {
            "id": benchmark_id,
            "name": benchmark_name,
            "type": benchmark_type,
            "target_agents": target_agents,
            "test_duration_seconds": test_duration_seconds,
            "target_throughput": target_throughput,
            "max_latency_ms": max_latency_ms,
            "concurrent_requests": concurrent_requests,
            "description": description,
            "test_data": test_data or {},
            "created_at": now.isoformat(),
            "runs_count": 0,
            "last_run_at": None,
            "best_result": None,
            "worst_result": None
        }

        AgentProfiling._benchmarks[benchmark_id] = benchmark
        return benchmark

    @staticmethod
    def run_benchmark(
        session,
        benchmark_id: str,
        iterations: int = 1,
        warmup_iterations: int = 0
    ) -> dict:
        """
        Execute benchmark test.

        Args:
            session: Database session
            benchmark_id: Benchmark ID
            iterations: Number of test iterations
            warmup_iterations: Warmup iterations (not counted)

        Returns:
            Benchmark run results
        """
        benchmark = AgentProfiling._benchmarks.get(benchmark_id)
        if not benchmark:
            raise ValueError(f"Benchmark not found: {benchmark_id}")

        result_id = f"result_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # Simulate benchmark execution
        results = []
        for i in range(iterations):
            iteration_result = {
                "iteration": i + 1,
                "throughput": 100 + (i * 5),  # Simulated
                "avg_latency_ms": 50 + (i * 2),  # Simulated
                "p50_latency_ms": 45 + (i * 1.5),
                "p95_latency_ms": 75 + (i * 3),
                "p99_latency_ms": 95 + (i * 4),
                "error_rate": 0.01 * i,
                "success_count": 1000 - (i * 10),
                "error_count": i * 10
            }
            results.append(iteration_result)

        # Aggregate results
        avg_throughput = statistics.mean([r["throughput"] for r in results])
        avg_latency = statistics.mean([r["avg_latency_ms"] for r in results])
        avg_error_rate = statistics.mean([r["error_rate"] for r in results])

        result = {
            "id": result_id,
            "benchmark_id": benchmark_id,
            "benchmark_name": benchmark["name"],
            "benchmark_type": benchmark["type"],
            "executed_at": now.isoformat(),
            "iterations": iterations,
            "warmup_iterations": warmup_iterations,
            "target_agents": benchmark["target_agents"],
            "results": results,
            "aggregated_results": {
                "avg_throughput": avg_throughput,
                "avg_latency_ms": avg_latency,
                "min_latency_ms": min([r["avg_latency_ms"] for r in results]),
                "max_latency_ms": max([r["avg_latency_ms"] for r in results]),
                "avg_p95_latency_ms": statistics.mean([r["p95_latency_ms"] for r in results]),
                "avg_p99_latency_ms": statistics.mean([r["p99_latency_ms"] for r in results]),
                "avg_error_rate": avg_error_rate,
                "total_requests": sum([r["success_count"] + r["error_count"] for r in results])
            },
            "passed": avg_latency <= benchmark.get("max_latency_ms", float('inf')) if benchmark.get("max_latency_ms") else True
        }

        AgentProfiling._benchmark_results[benchmark_id].append(result)
        benchmark["runs_count"] += 1
        benchmark["last_run_at"] = now.isoformat()

        # Track best/worst results
        if not benchmark["best_result"] or avg_latency < benchmark["best_result"]["avg_latency_ms"]:
            benchmark["best_result"] = result["aggregated_results"]
        if not benchmark["worst_result"] or avg_latency > benchmark["worst_result"]["avg_latency_ms"]:
            benchmark["worst_result"] = result["aggregated_results"]

        return result

    @staticmethod
    def set_baseline(
        session,
        agent_id: str,
        baseline_name: str,
        metrics: dict,
        description: Optional[str] = None
    ) -> dict:
        """
        Set performance baseline for agent.

        Args:
            session: Database session
            agent_id: Agent ID
            baseline_name: Baseline name
            metrics: Baseline metrics
            description: Baseline description

        Returns:
            Created baseline
        """
        baseline_id = f"baseline_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        baseline = {
            "id": baseline_id,
            "agent_id": agent_id,
            "name": baseline_name,
            "metrics": metrics,
            "description": description,
            "created_at": now.isoformat(),
            "is_active": True
        }

        if agent_id not in AgentProfiling._agent_baselines:
            AgentProfiling._agent_baselines[agent_id] = []
        AgentProfiling._agent_baselines[agent_id].append(baseline)

        return baseline

    @staticmethod
    def compare_agents(
        session,
        agent_ids: List[str],
        metric_types: List[str],
        time_range_hours: int = 24
    ) -> dict:
        """
        Compare performance across multiple agents.

        Args:
            session: Database session
            agent_ids: Agents to compare
            metric_types: Metrics to compare
            time_range_hours: Time range for comparison

        Returns:
            Comparison report
        """
        comparison_id = f"comparison_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        cutoff_time = now - timedelta(hours=time_range_hours)

        agent_metrics = {}
        for agent_id in agent_ids:
            # Get profile sessions for agent
            sessions = [
                s for s in AgentProfiling._profile_sessions.values()
                if s["agent_id"] == agent_id and
                s["status"] == ProfileStatus.COMPLETED and
                datetime.fromisoformat(s["started_at"]) >= cutoff_time
            ]

            metrics_summary = {}
            for metric_type in metric_types:
                values = []
                for session_data in sessions:
                    if metric_type in session_data.get("metrics_summary", {}):
                        values.append(session_data["metrics_summary"][metric_type]["avg"])

                if values:
                    metrics_summary[metric_type] = {
                        "avg": statistics.mean(values),
                        "min": min(values),
                        "max": max(values),
                        "sample_count": len(values)
                    }

            agent_metrics[agent_id] = metrics_summary

        # Determine best and worst performers
        rankings = {}
        for metric_type in metric_types:
            agents_with_metric = {
                agent_id: data.get(metric_type, {}).get("avg")
                for agent_id, data in agent_metrics.items()
                if metric_type in data
            }
            if agents_with_metric:
                sorted_agents = sorted(agents_with_metric.items(), key=lambda x: x[1])
                rankings[metric_type] = {
                    "best": sorted_agents[0][0] if sorted_agents else None,
                    "worst": sorted_agents[-1][0] if sorted_agents else None,
                    "ranking": [agent_id for agent_id, _ in sorted_agents]
                }

        comparison = {
            "id": comparison_id,
            "agent_ids": agent_ids,
            "metric_types": metric_types,
            "time_range_hours": time_range_hours,
            "compared_at": now.isoformat(),
            "agent_metrics": agent_metrics,
            "rankings": rankings,
            "comparison_summary": {
                "total_agents": len(agent_ids),
                "metrics_compared": len(metric_types)
            }
        }

        AgentProfiling._comparison_reports[comparison_id] = comparison
        return comparison

    @staticmethod
    def get_bottlenecks(
        session,
        agent_id: Optional[str] = None,
        severity: Optional[str] = None,
        limit: int = 50
    ) -> dict:
        """
        Get identified performance bottlenecks.

        Args:
            session: Database session
            agent_id: Filter by agent
            severity: Filter by severity
            limit: Maximum bottlenecks to return

        Returns:
            Bottlenecks list
        """
        bottlenecks = []
        for aid, bottleneck_list in AgentProfiling._bottlenecks.items():
            if agent_id and aid != agent_id:
                continue

            for bottleneck in bottleneck_list:
                if severity and bottleneck["severity"] != severity:
                    continue
                bottlenecks.append(bottleneck)

        # Sort by severity
        severity_order = {
            BottleneckSeverity.CRITICAL: 0,
            BottleneckSeverity.HIGH: 1,
            BottleneckSeverity.MEDIUM: 2,
            BottleneckSeverity.LOW: 3
        }
        bottlenecks.sort(key=lambda x: (severity_order.get(x["severity"], 99), x["detected_at"]), reverse=True)

        # Apply limit
        bottlenecks = bottlenecks[:limit]

        return {
            "bottlenecks": bottlenecks,
            "total_count": len(bottlenecks),
            "severity_distribution": {
                "critical": len([b for b in bottlenecks if b["severity"] == BottleneckSeverity.CRITICAL]),
                "high": len([b for b in bottlenecks if b["severity"] == BottleneckSeverity.HIGH]),
                "medium": len([b for b in bottlenecks if b["severity"] == BottleneckSeverity.MEDIUM]),
                "low": len([b for b in bottlenecks if b["severity"] == BottleneckSeverity.LOW])
            }
        }

    @staticmethod
    def generate_optimization_recommendations(
        session,
        agent_id: str,
        profile_id: Optional[str] = None
    ) -> dict:
        """
        Generate optimization recommendations.

        Args:
            session: Database session
            agent_id: Agent ID
            profile_id: Optional specific profile session

        Returns:
            Optimization recommendations
        """
        recommendations = []

        # Get bottlenecks for agent
        bottlenecks_data = AgentProfiling.get_bottlenecks(
            session=session,
            agent_id=agent_id,
            limit=10
        )

        # Generate recommendations based on bottlenecks
        for bottleneck in bottlenecks_data["bottlenecks"]:
            recommendation = {
                "id": f"rec_{uuid.uuid4().hex[:12]}",
                "agent_id": agent_id,
                "category": bottleneck["component"],
                "priority": bottleneck["severity"],
                "issue": bottleneck["description"],
                "recommendation": AgentProfiling._generate_recommendation_text(bottleneck),
                "expected_impact": "high" if bottleneck["severity"] in [BottleneckSeverity.CRITICAL, BottleneckSeverity.HIGH] else "medium",
                "effort": "medium",
                "created_at": datetime.utcnow().isoformat()
            }
            recommendations.append(recommendation)

        # Store recommendations
        AgentProfiling._optimization_recommendations[agent_id].extend(recommendations)

        return {
            "agent_id": agent_id,
            "recommendations": recommendations,
            "total_recommendations": len(recommendations),
            "high_priority_count": len([r for r in recommendations if r["priority"] in [BottleneckSeverity.CRITICAL, BottleneckSeverity.HIGH]])
        }

    @staticmethod
    def get_profile_history(
        session,
        agent_id: str,
        status: Optional[str] = None,
        limit: int = 50
    ) -> dict:
        """
        Get profiling history for agent.

        Args:
            session: Database session
            agent_id: Agent ID
            status: Filter by status
            limit: Maximum sessions to return

        Returns:
            Profile history
        """
        sessions = [
            s for s in AgentProfiling._profile_sessions.values()
            if s["agent_id"] == agent_id
        ]

        # Apply filters
        if status:
            sessions = [s for s in sessions if s["status"] == status]

        # Sort by started_at descending
        sessions.sort(key=lambda x: x["started_at"], reverse=True)

        # Apply limit
        sessions = sessions[:limit]

        return {
            "agent_id": agent_id,
            "profile_sessions": sessions,
            "total_sessions": len(AgentProfiling._profile_sessions),
            "returned_count": len(sessions)
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get profiling statistics"""
        sessions = list(AgentProfiling._profile_sessions.values())
        benchmarks = list(AgentProfiling._benchmarks.values())

        # Status distribution
        status_dist = defaultdict(int)
        for sess in sessions:
            status_dist[sess["status"]] += 1

        # Benchmark type distribution
        benchmark_type_dist = defaultdict(int)
        for bench in benchmarks:
            benchmark_type_dist[bench["type"]] += 1

        # Total metrics
        total_metrics = sum(len(metrics) for metrics in AgentProfiling._profile_metrics.values())

        # Total bottlenecks by severity
        all_bottlenecks = []
        for bottleneck_list in AgentProfiling._bottlenecks.values():
            all_bottlenecks.extend(bottleneck_list)

        bottleneck_severity_dist = defaultdict(int)
        for bottleneck in all_bottlenecks:
            bottleneck_severity_dist[bottleneck["severity"]] += 1

        return {
            "total_profile_sessions": len(sessions),
            "active_sessions": len([s for s in sessions if s["status"] == ProfileStatus.ACTIVE]),
            "completed_sessions": len([s for s in sessions if s["status"] == ProfileStatus.COMPLETED]),
            "session_status_distribution": dict(status_dist),
            "total_benchmarks": len(benchmarks),
            "total_benchmark_runs": sum(b["runs_count"] for b in benchmarks),
            "benchmark_type_distribution": dict(benchmark_type_dist),
            "total_metrics_collected": total_metrics,
            "total_bottlenecks": len(all_bottlenecks),
            "bottleneck_severity_distribution": dict(bottleneck_severity_dist),
            "total_baselines": sum(len(baselines) for baselines in AgentProfiling._agent_baselines.values()),
            "total_comparisons": len(AgentProfiling._comparison_reports),
            "agents_profiled": len(set(s["agent_id"] for s in sessions))
        }

    # Helper methods
    @staticmethod
    def _detect_bottlenecks(profile_id: str, profile_session: dict, metrics: List[dict]):
        """Detect performance bottlenecks from metrics"""
        agent_id = profile_session["agent_id"]
        bottlenecks = []

        # Analyze metrics for bottlenecks
        for metric_type in profile_session["metric_types"]:
            type_metrics = [m["value"] for m in metrics if m["metric_type"] == metric_type]
            if not type_metrics:
                continue

            avg_value = statistics.mean(type_metrics)
            max_value = max(type_metrics)
            stddev = statistics.stdev(type_metrics) if len(type_metrics) > 1 else 0

            # High execution time
            if metric_type == ProfileMetricType.EXECUTION_TIME and avg_value > 1000:  # >1 second
                severity = BottleneckSeverity.CRITICAL if avg_value > 5000 else BottleneckSeverity.HIGH
                bottlenecks.append({
                    "id": f"bottleneck_{uuid.uuid4().hex[:12]}",
                    "agent_id": agent_id,
                    "profile_id": profile_id,
                    "component": metric_type,
                    "severity": severity,
                    "description": f"High execution time detected: {avg_value:.2f}ms average",
                    "metric_value": avg_value,
                    "threshold": 1000,
                    "detected_at": datetime.utcnow().isoformat()
                })

            # High memory usage
            elif metric_type == ProfileMetricType.MEMORY_USAGE and avg_value > 500:  # >500MB
                severity = BottleneckSeverity.HIGH if avg_value > 1000 else BottleneckSeverity.MEDIUM
                bottlenecks.append({
                    "id": f"bottleneck_{uuid.uuid4().hex[:12]}",
                    "agent_id": agent_id,
                    "profile_id": profile_id,
                    "component": metric_type,
                    "severity": severity,
                    "description": f"High memory usage: {avg_value:.2f}MB average",
                    "metric_value": avg_value,
                    "threshold": 500,
                    "detected_at": datetime.utcnow().isoformat()
                })

            # High error rate
            elif metric_type == ProfileMetricType.ERROR_RATE and avg_value > 0.05:  # >5%
                severity = BottleneckSeverity.CRITICAL if avg_value > 0.1 else BottleneckSeverity.HIGH
                bottlenecks.append({
                    "id": f"bottleneck_{uuid.uuid4().hex[:12]}",
                    "agent_id": agent_id,
                    "profile_id": profile_id,
                    "component": metric_type,
                    "severity": severity,
                    "description": f"High error rate: {avg_value*100:.2f}%",
                    "metric_value": avg_value,
                    "threshold": 0.05,
                    "detected_at": datetime.utcnow().isoformat()
                })

        AgentProfiling._bottlenecks[agent_id].extend(bottlenecks)

    @staticmethod
    def _generate_recommendation_text(bottleneck: dict) -> str:
        """Generate recommendation text based on bottleneck"""
        component = bottleneck["component"]

        recommendations = {
            ProfileMetricType.EXECUTION_TIME: "Consider optimizing algorithms, using caching, or implementing async processing",
            ProfileMetricType.MEMORY_USAGE: "Review memory allocation patterns, implement object pooling, or optimize data structures",
            ProfileMetricType.CPU_USAGE: "Profile CPU-intensive operations, consider parallel processing, or optimize computational algorithms",
            ProfileMetricType.IO_OPERATIONS: "Batch I/O operations, use async I/O, or implement buffering strategies",
            ProfileMetricType.NETWORK_CALLS: "Reduce network round trips, implement connection pooling, or use CDN for static resources",
            ProfileMetricType.DATABASE_QUERIES: "Optimize queries, add indexes, implement query caching, or use batch operations",
            ProfileMetricType.ERROR_RATE: "Implement better error handling, add input validation, or review error scenarios"
        }

        return recommendations.get(component, "Review and optimize this component")
