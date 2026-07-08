"""
Agent Performance Tracking Service

Tracks and analyzes agent performance metrics including task completion, efficiency,
quality, resource usage, and trends over time.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import statistics


class MetricType:
    """Types of performance metrics"""
    TASK_COMPLETION = "task_completion"
    EFFICIENCY = "efficiency"
    QUALITY = "quality"
    RESOURCE_USAGE = "resource_usage"
    RESPONSE_TIME = "response_time"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"


class PerformanceLevel:
    """Performance level classifications"""
    EXCELLENT = "excellent"  # Top 10%
    GOOD = "good"  # Top 25%
    AVERAGE = "average"  # Middle 50%
    BELOW_AVERAGE = "below_average"  # Bottom 25%
    POOR = "poor"  # Bottom 10%


class TrendDirection:
    """Performance trend directions"""
    IMPROVING = "improving"
    STABLE = "stable"
    DECLINING = "declining"


class AgentPerformance:
    """
    Agent Performance Tracking System

    Tracks comprehensive performance metrics and provides analytics,
    benchmarking, and trend analysis.
    """

    # In-memory storage
    _performance_records = defaultdict(list)  # agent_id -> [records]
    _task_metrics = {}
    _task_counter = 0

    _efficiency_metrics = defaultdict(list)  # agent_id -> [metrics]
    _quality_metrics = defaultdict(list)  # agent_id -> [metrics]
    _resource_metrics = defaultdict(list)  # agent_id -> [metrics]

    _benchmarks = {}
    _performance_alerts = defaultdict(list)  # agent_id -> [alerts]

    @staticmethod
    def record_task_completion(
        session,
        agent_id: int,
        task_id: int,
        success: bool,
        completion_time_seconds: float,
        quality_score: float = 1.0,
        error_count: int = 0,
        retry_count: int = 0,
        resource_usage: Optional[dict] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Record task completion metrics.

        Args:
            session: Database session
            agent_id: Agent ID
            task_id: Task ID
            success: Whether task succeeded
            completion_time_seconds: Time taken to complete
            quality_score: Quality rating (0-1)
            error_count: Number of errors encountered
            retry_count: Number of retries needed
            resource_usage: Resource consumption metrics
            metadata: Additional metadata

        Returns:
            Task performance record
        """
        AgentPerformance._task_counter += 1
        record_id = f"task_perf_{AgentPerformance._task_counter}"

        record = {
            "id": record_id,
            "agent_id": agent_id,
            "task_id": task_id,
            "success": success,
            "completion_time_seconds": completion_time_seconds,
            "quality_score": quality_score,
            "error_count": error_count,
            "retry_count": retry_count,
            "resource_usage": resource_usage or {},
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        AgentPerformance._performance_records[agent_id].append(record)
        AgentPerformance._task_metrics[task_id] = record

        # Check for performance alerts
        AgentPerformance._check_performance_alerts(agent_id, record)

        return record

    @staticmethod
    def record_efficiency_metric(
        session,
        agent_id: int,
        throughput: float,
        utilization: float,
        average_response_time: float,
        idle_time_seconds: float = 0,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Record efficiency metrics.

        Args:
            session: Database session
            agent_id: Agent ID
            throughput: Tasks completed per hour
            utilization: Agent utilization percentage (0-100)
            average_response_time: Average response time in seconds
            idle_time_seconds: Idle time in seconds
            metadata: Additional metadata

        Returns:
            Efficiency metric record
        """
        metric = {
            "agent_id": agent_id,
            "throughput": throughput,
            "utilization": utilization,
            "average_response_time": average_response_time,
            "idle_time_seconds": idle_time_seconds,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        AgentPerformance._efficiency_metrics[agent_id].append(metric)

        return metric

    @staticmethod
    def record_quality_metric(
        session,
        agent_id: int,
        accuracy: float,
        consistency: float,
        error_rate: float,
        defect_rate: float = 0.0,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Record quality metrics.

        Args:
            session: Database session
            agent_id: Agent ID
            accuracy: Accuracy score (0-1)
            consistency: Consistency score (0-1)
            error_rate: Error rate (0-1)
            defect_rate: Defect rate (0-1)
            metadata: Additional metadata

        Returns:
            Quality metric record
        """
        metric = {
            "agent_id": agent_id,
            "accuracy": accuracy,
            "consistency": consistency,
            "error_rate": error_rate,
            "defect_rate": defect_rate,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        AgentPerformance._quality_metrics[agent_id].append(metric)

        return metric

    @staticmethod
    def record_resource_usage(
        session,
        agent_id: int,
        cpu_usage: float,
        memory_usage_mb: float,
        api_calls: int,
        tokens_used: int = 0,
        cost: float = 0.0,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Record resource usage metrics.

        Args:
            session: Database session
            agent_id: Agent ID
            cpu_usage: CPU usage percentage (0-100)
            memory_usage_mb: Memory usage in MB
            api_calls: Number of API calls made
            tokens_used: Number of LLM tokens used
            cost: Cost in dollars
            metadata: Additional metadata

        Returns:
            Resource usage record
        """
        metric = {
            "agent_id": agent_id,
            "cpu_usage": cpu_usage,
            "memory_usage_mb": memory_usage_mb,
            "api_calls": api_calls,
            "tokens_used": tokens_used,
            "cost": cost,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        AgentPerformance._resource_metrics[agent_id].append(metric)

        return metric

    @staticmethod
    def get_performance_summary(
        session,
        agent_id: int,
        timeframe_hours: int = 24
    ) -> dict:
        """
        Get performance summary for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            timeframe_hours: Time window for metrics

        Returns:
            Performance summary with all metrics
        """
        cutoff = datetime.utcnow() - timedelta(hours=timeframe_hours)
        cutoff_iso = cutoff.isoformat()

        # Filter records by timeframe
        task_records = [
            r for r in AgentPerformance._performance_records.get(agent_id, [])
            if r["timestamp"] > cutoff_iso
        ]

        if not task_records:
            return {
                "agent_id": agent_id,
                "timeframe_hours": timeframe_hours,
                "task_count": 0,
                "message": "No performance data available"
            }

        # Task completion metrics
        total_tasks = len(task_records)
        successful_tasks = sum(1 for r in task_records if r["success"])
        success_rate = successful_tasks / total_tasks if total_tasks > 0 else 0

        completion_times = [r["completion_time_seconds"] for r in task_records]
        average_time = statistics.mean(completion_times)
        median_time = statistics.median(completion_times)

        quality_scores = [r["quality_score"] for r in task_records]
        average_quality = statistics.mean(quality_scores)

        total_errors = sum(r["error_count"] for r in task_records)
        total_retries = sum(r["retry_count"] for r in task_records)

        # Efficiency metrics
        efficiency_records = [
            m for m in AgentPerformance._efficiency_metrics.get(agent_id, [])
            if m["timestamp"] > cutoff_iso
        ]

        if efficiency_records:
            avg_throughput = statistics.mean([m["throughput"] for m in efficiency_records])
            avg_utilization = statistics.mean([m["utilization"] for m in efficiency_records])
            avg_response_time = statistics.mean([m["average_response_time"] for m in efficiency_records])
        else:
            avg_throughput = 0
            avg_utilization = 0
            avg_response_time = 0

        # Quality metrics
        quality_records = [
            m for m in AgentPerformance._quality_metrics.get(agent_id, [])
            if m["timestamp"] > cutoff_iso
        ]

        if quality_records:
            avg_accuracy = statistics.mean([m["accuracy"] for m in quality_records])
            avg_consistency = statistics.mean([m["consistency"] for m in quality_records])
            avg_error_rate = statistics.mean([m["error_rate"] for m in quality_records])
        else:
            avg_accuracy = 0
            avg_consistency = 0
            avg_error_rate = 0

        # Resource usage
        resource_records = [
            m for m in AgentPerformance._resource_metrics.get(agent_id, [])
            if m["timestamp"] > cutoff_iso
        ]

        if resource_records:
            total_cost = sum(m["cost"] for m in resource_records)
            total_api_calls = sum(m["api_calls"] for m in resource_records)
            total_tokens = sum(m["tokens_used"] for m in resource_records)
            avg_cpu = statistics.mean([m["cpu_usage"] for m in resource_records])
            avg_memory = statistics.mean([m["memory_usage_mb"] for m in resource_records])
        else:
            total_cost = 0
            total_api_calls = 0
            total_tokens = 0
            avg_cpu = 0
            avg_memory = 0

        # Performance level
        performance_score = (
            success_rate * 0.3 +
            average_quality * 0.3 +
            (1 - avg_error_rate) * 0.2 +
            avg_accuracy * 0.2
        )
        performance_level = AgentPerformance._calculate_performance_level(performance_score)

        return {
            "agent_id": agent_id,
            "timeframe_hours": timeframe_hours,
            "task_metrics": {
                "total_tasks": total_tasks,
                "successful_tasks": successful_tasks,
                "failed_tasks": total_tasks - successful_tasks,
                "success_rate": success_rate,
                "average_completion_time": average_time,
                "median_completion_time": median_time,
                "average_quality": average_quality,
                "total_errors": total_errors,
                "total_retries": total_retries
            },
            "efficiency_metrics": {
                "average_throughput": avg_throughput,
                "average_utilization": avg_utilization,
                "average_response_time": avg_response_time
            },
            "quality_metrics": {
                "average_accuracy": avg_accuracy,
                "average_consistency": avg_consistency,
                "average_error_rate": avg_error_rate
            },
            "resource_metrics": {
                "total_cost": total_cost,
                "total_api_calls": total_api_calls,
                "total_tokens": total_tokens,
                "average_cpu_usage": avg_cpu,
                "average_memory_usage_mb": avg_memory
            },
            "performance_score": performance_score,
            "performance_level": performance_level
        }

    @staticmethod
    def get_performance_trend(
        session,
        agent_id: int,
        metric_type: str,
        timeframe_hours: int = 168  # 1 week
    ) -> dict:
        """
        Get performance trend analysis.

        Args:
            session: Database session
            agent_id: Agent ID
            metric_type: Type of metric to analyze
            timeframe_hours: Time window for analysis

        Returns:
            Trend analysis with direction and statistics
        """
        cutoff = datetime.utcnow() - timedelta(hours=timeframe_hours)
        cutoff_iso = cutoff.isoformat()

        # Get relevant records
        if metric_type == MetricType.TASK_COMPLETION:
            records = [
                r for r in AgentPerformance._performance_records.get(agent_id, [])
                if r["timestamp"] > cutoff_iso
            ]
            values = [1 if r["success"] else 0 for r in records]
        elif metric_type == MetricType.EFFICIENCY:
            records = [
                m for m in AgentPerformance._efficiency_metrics.get(agent_id, [])
                if m["timestamp"] > cutoff_iso
            ]
            values = [m["throughput"] for m in records]
        elif metric_type == MetricType.QUALITY:
            records = [
                m for m in AgentPerformance._quality_metrics.get(agent_id, [])
                if m["timestamp"] > cutoff_iso
            ]
            values = [m["accuracy"] for m in records]
        else:
            records = []
            values = []

        if len(values) < 2:
            return {
                "agent_id": agent_id,
                "metric_type": metric_type,
                "trend": TrendDirection.STABLE,
                "message": "Insufficient data for trend analysis"
            }

        # Calculate trend
        first_half = values[:len(values)//2]
        second_half = values[len(values)//2:]

        avg_first = statistics.mean(first_half)
        avg_second = statistics.mean(second_half)

        change_percent = ((avg_second - avg_first) / avg_first * 100) if avg_first > 0 else 0

        if change_percent > 5:
            trend = TrendDirection.IMPROVING
        elif change_percent < -5:
            trend = TrendDirection.DECLINING
        else:
            trend = TrendDirection.STABLE

        return {
            "agent_id": agent_id,
            "metric_type": metric_type,
            "timeframe_hours": timeframe_hours,
            "trend": trend,
            "change_percent": change_percent,
            "first_period_average": avg_first,
            "second_period_average": avg_second,
            "current_value": values[-1] if values else 0,
            "min_value": min(values),
            "max_value": max(values),
            "average_value": statistics.mean(values),
            "data_points": len(values)
        }

    @staticmethod
    def compare_agents(
        session,
        agent_ids: List[int],
        metric_type: str,
        timeframe_hours: int = 24
    ) -> dict:
        """
        Compare performance across multiple agents.

        Args:
            session: Database session
            agent_ids: List of agent IDs to compare
            metric_type: Metric to compare
            timeframe_hours: Time window

        Returns:
            Comparison results with rankings
        """
        results = []

        for agent_id in agent_ids:
            summary = AgentPerformance.get_performance_summary(
                session=session,
                agent_id=agent_id,
                timeframe_hours=timeframe_hours
            )

            if summary.get("task_count", 0) > 0:
                if metric_type == MetricType.TASK_COMPLETION:
                    value = summary["task_metrics"]["success_rate"]
                elif metric_type == MetricType.EFFICIENCY:
                    value = summary["efficiency_metrics"]["average_throughput"]
                elif metric_type == MetricType.QUALITY:
                    value = summary["quality_metrics"]["average_accuracy"]
                else:
                    value = 0

                results.append({
                    "agent_id": agent_id,
                    "value": value,
                    "performance_level": summary["performance_level"]
                })

        # Sort by value descending
        results.sort(key=lambda x: x["value"], reverse=True)

        # Add rankings
        for i, result in enumerate(results):
            result["rank"] = i + 1

        return {
            "metric_type": metric_type,
            "timeframe_hours": timeframe_hours,
            "agents_compared": len(results),
            "rankings": results,
            "best_performer": results[0] if results else None,
            "worst_performer": results[-1] if results else None
        }

    @staticmethod
    def get_performance_alerts(
        session,
        agent_id: int
    ) -> dict:
        """
        Get performance alerts for an agent.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Performance alerts
        """
        alerts = AgentPerformance._performance_alerts.get(agent_id, [])

        # Sort by timestamp descending
        alerts.sort(key=lambda x: x["timestamp"], reverse=True)

        return {
            "agent_id": agent_id,
            "total_alerts": len(alerts),
            "alerts": alerts
        }

    @staticmethod
    def set_benchmark(
        session,
        metric_type: str,
        target_value: float,
        threshold_warning: float,
        threshold_critical: float,
        description: str = ""
    ) -> dict:
        """
        Set performance benchmark.

        Args:
            session: Database session
            metric_type: Type of metric
            target_value: Target/ideal value
            threshold_warning: Warning threshold
            threshold_critical: Critical threshold
            description: Benchmark description

        Returns:
            Benchmark record
        """
        benchmark = {
            "metric_type": metric_type,
            "target_value": target_value,
            "threshold_warning": threshold_warning,
            "threshold_critical": threshold_critical,
            "description": description,
            "created_at": datetime.utcnow().isoformat()
        }

        AgentPerformance._benchmarks[metric_type] = benchmark

        return benchmark

    @staticmethod
    def get_performance_statistics(session) -> dict:
        """
        Get system-wide performance statistics.

        Args:
            session: Database session

        Returns:
            Aggregate performance statistics
        """
        total_agents = len(AgentPerformance._performance_records)
        total_tasks = sum(len(records) for records in AgentPerformance._performance_records.values())

        all_task_records = [
            r for records in AgentPerformance._performance_records.values()
            for r in records
        ]

        if all_task_records:
            overall_success_rate = sum(1 for r in all_task_records if r["success"]) / len(all_task_records)
            avg_completion_time = statistics.mean([r["completion_time_seconds"] for r in all_task_records])
            avg_quality = statistics.mean([r["quality_score"] for r in all_task_records])
        else:
            overall_success_rate = 0
            avg_completion_time = 0
            avg_quality = 0

        return {
            "total_agents_tracked": total_agents,
            "total_tasks_recorded": total_tasks,
            "overall_success_rate": overall_success_rate,
            "average_completion_time": avg_completion_time,
            "average_quality_score": avg_quality,
            "total_benchmarks": len(AgentPerformance._benchmarks),
            "total_alerts": sum(len(alerts) for alerts in AgentPerformance._performance_alerts.values())
        }

    # Helper methods

    @staticmethod
    def _calculate_performance_level(score: float) -> str:
        """Calculate performance level from score"""
        if score >= 0.9:
            return PerformanceLevel.EXCELLENT
        elif score >= 0.75:
            return PerformanceLevel.GOOD
        elif score >= 0.5:
            return PerformanceLevel.AVERAGE
        elif score >= 0.25:
            return PerformanceLevel.BELOW_AVERAGE
        else:
            return PerformanceLevel.POOR

    @staticmethod
    def _check_performance_alerts(agent_id: int, record: dict):
        """Check if performance triggers any alerts"""
        # Check success rate
        recent_records = AgentPerformance._performance_records[agent_id][-10:]
        if len(recent_records) >= 5:
            success_rate = sum(1 for r in recent_records if r["success"]) / len(recent_records)
            if success_rate < 0.5:
                alert = {
                    "alert_type": "low_success_rate",
                    "severity": "critical",
                    "message": f"Success rate below 50%: {success_rate*100:.1f}%",
                    "timestamp": datetime.utcnow().isoformat()
                }
                AgentPerformance._performance_alerts[agent_id].append(alert)

        # Check error rate
        if record["error_count"] > 3:
            alert = {
                "alert_type": "high_error_count",
                "severity": "warning",
                "message": f"Task had {record['error_count']} errors",
                "timestamp": datetime.utcnow().isoformat()
            }
            AgentPerformance._performance_alerts[agent_id].append(alert)

        # Check quality score
        if record["quality_score"] < 0.5:
            alert = {
                "alert_type": "low_quality",
                "severity": "warning",
                "message": f"Quality score below 50%: {record['quality_score']*100:.1f}%",
                "timestamp": datetime.utcnow().isoformat()
            }
            AgentPerformance._performance_alerts[agent_id].append(alert)
