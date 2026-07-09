"""
Performance Monitoring Service

Tracks and analyzes agent and workflow performance metrics including
execution times, success rates, throughput, and resource utilization.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import statistics


class MetricType:
    """Performance metric types"""
    EXECUTION_TIME = "execution_time"
    SUCCESS_RATE = "success_rate"
    THROUGHPUT = "throughput"
    ERROR_RATE = "error_rate"
    RESPONSE_TIME = "response_time"
    RESOURCE_UTILIZATION = "resource_utilization"
    QUEUE_LENGTH = "queue_length"


class PerformanceStatus:
    """Performance health statuses"""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


class PerformanceMonitoring:
    """
    Performance Monitoring Service

    Tracks and analyzes performance metrics for agents, workflows,
    and the overall system with real-time monitoring and analytics.
    """

    # In-memory storage
    _metrics = defaultdict(list)
    _metric_counter = 0
    _agent_metrics = defaultdict(lambda: defaultdict(list))
    _workflow_metrics = defaultdict(lambda: defaultdict(list))
    _system_metrics = defaultdict(list)
    _anomalies = []
    _sla_violations = []

    # Performance thresholds
    _thresholds = {
        "execution_time_seconds": {"excellent": 1.0, "good": 5.0, "fair": 15.0, "poor": 30.0},
        "success_rate": {"excellent": 0.99, "good": 0.95, "fair": 0.90, "poor": 0.80},
        "response_time_seconds": {"excellent": 0.5, "good": 2.0, "fair": 5.0, "poor": 10.0},
        "error_rate": {"excellent": 0.01, "good": 0.05, "fair": 0.10, "poor": 0.20}
    }

    @staticmethod
    def _generate_metric_id() -> str:
        """Generate unique metric ID"""
        PerformanceMonitoring._metric_counter += 1
        return f"metric_{PerformanceMonitoring._metric_counter}"

    @staticmethod
    def record_execution(
        session,
        agent_id: Optional[int] = None,
        workflow_id: Optional[str] = None,
        task_id: Optional[str] = None,
        execution_time_seconds: Optional[float] = None,
        success: bool = True,
        error_type: Optional[str] = None,
        resource_usage: Optional[dict] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Record execution metrics.

        Tracks performance metrics for agent/workflow execution.
        """
        metric_id = PerformanceMonitoring._generate_metric_id()

        metric = {
            "id": metric_id,
            "agent_id": agent_id,
            "workflow_id": workflow_id,
            "task_id": task_id,
            "execution_time_seconds": execution_time_seconds,
            "success": success,
            "error_type": error_type,
            "resource_usage": resource_usage or {},
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        # Store in various indexes
        PerformanceMonitoring._metrics[metric_id] = metric

        if agent_id:
            PerformanceMonitoring._agent_metrics[agent_id]["executions"].append(metric)

        if workflow_id:
            PerformanceMonitoring._workflow_metrics[workflow_id]["executions"].append(metric)

        PerformanceMonitoring._system_metrics["executions"].append(metric)

        # Check for anomalies
        PerformanceMonitoring._detect_anomalies(metric)

        return metric

    @staticmethod
    def record_response_time(
        session,
        agent_id: int,
        response_time_seconds: float,
        operation: str,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Record response time metric.

        Tracks how long agents take to respond to requests.
        """
        metric_id = PerformanceMonitoring._generate_metric_id()

        metric = {
            "id": metric_id,
            "agent_id": agent_id,
            "metric_type": MetricType.RESPONSE_TIME,
            "response_time_seconds": response_time_seconds,
            "operation": operation,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        PerformanceMonitoring._metrics[metric_id] = metric
        PerformanceMonitoring._agent_metrics[agent_id]["response_times"].append(metric)

        return metric

    @staticmethod
    def record_throughput(
        session,
        agent_id: Optional[int] = None,
        workflow_id: Optional[str] = None,
        items_processed: int = 1,
        time_window_seconds: float = 60.0,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Record throughput metric.

        Tracks processing rate (items per second).
        """
        metric_id = PerformanceMonitoring._generate_metric_id()

        throughput = items_processed / time_window_seconds if time_window_seconds > 0 else 0

        metric = {
            "id": metric_id,
            "agent_id": agent_id,
            "workflow_id": workflow_id,
            "metric_type": MetricType.THROUGHPUT,
            "items_processed": items_processed,
            "time_window_seconds": time_window_seconds,
            "throughput_per_second": throughput,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        PerformanceMonitoring._metrics[metric_id] = metric

        if agent_id:
            PerformanceMonitoring._agent_metrics[agent_id]["throughput"].append(metric)

        if workflow_id:
            PerformanceMonitoring._workflow_metrics[workflow_id]["throughput"].append(metric)

        return metric

    @staticmethod
    def _detect_anomalies(metric: dict):
        """Detect performance anomalies"""
        # Check execution time anomaly
        if metric.get("execution_time_seconds"):
            exec_time = metric["execution_time_seconds"]
            threshold = PerformanceMonitoring._thresholds["execution_time_seconds"]["poor"]

            if exec_time > threshold:
                anomaly = {
                    "type": "slow_execution",
                    "severity": "high" if exec_time > threshold * 2 else "medium",
                    "metric_id": metric["id"],
                    "agent_id": metric.get("agent_id"),
                    "workflow_id": metric.get("workflow_id"),
                    "value": exec_time,
                    "threshold": threshold,
                    "timestamp": datetime.utcnow().isoformat(),
                    "message": f"Execution time {exec_time:.2f}s exceeds threshold {threshold:.2f}s"
                }
                PerformanceMonitoring._anomalies.append(anomaly)

        # Check for repeated failures
        if not metric.get("success") and metric.get("agent_id"):
            agent_id = metric["agent_id"]
            recent_executions = PerformanceMonitoring._agent_metrics[agent_id]["executions"][-10:]

            if len(recent_executions) >= 5:
                failures = sum(1 for e in recent_executions if not e.get("success"))
                failure_rate = failures / len(recent_executions)

                if failure_rate > 0.5:
                    anomaly = {
                        "type": "high_failure_rate",
                        "severity": "critical" if failure_rate > 0.8 else "high",
                        "agent_id": agent_id,
                        "value": failure_rate,
                        "threshold": 0.5,
                        "timestamp": datetime.utcnow().isoformat(),
                        "message": f"Agent {agent_id} failure rate {failure_rate:.1%} exceeds threshold"
                    }
                    PerformanceMonitoring._anomalies.append(anomaly)

    @staticmethod
    def get_agent_performance(
        session,
        agent_id: int,
        time_window_hours: int = 24
    ) -> dict:
        """
        Get agent performance metrics.

        Returns comprehensive performance analysis for an agent.
        """
        cutoff = datetime.utcnow() - timedelta(hours=time_window_hours)

        executions = [
            e for e in PerformanceMonitoring._agent_metrics[agent_id]["executions"]
            if datetime.fromisoformat(e["timestamp"]) >= cutoff
        ]

        response_times = [
            r for r in PerformanceMonitoring._agent_metrics[agent_id]["response_times"]
            if datetime.fromisoformat(r["timestamp"]) >= cutoff
        ]

        if not executions:
            return {
                "agent_id": agent_id,
                "time_window_hours": time_window_hours,
                "status": PerformanceStatus.GOOD,
                "message": "No data available"
            }

        # Calculate metrics
        total_executions = len(executions)
        successful = sum(1 for e in executions if e.get("success"))
        failed = total_executions - successful
        success_rate = successful / total_executions if total_executions > 0 else 0
        error_rate = failed / total_executions if total_executions > 0 else 0

        exec_times = [e["execution_time_seconds"] for e in executions if e.get("execution_time_seconds")]
        avg_exec_time = statistics.mean(exec_times) if exec_times else 0
        p50_exec_time = statistics.median(exec_times) if exec_times else 0
        p95_exec_time = statistics.quantiles(exec_times, n=20)[18] if len(exec_times) >= 20 else (max(exec_times) if exec_times else 0)

        resp_times = [r["response_time_seconds"] for r in response_times]
        avg_response_time = statistics.mean(resp_times) if resp_times else 0

        # Determine status
        status = PerformanceMonitoring._determine_status(success_rate, avg_exec_time, error_rate)

        return {
            "agent_id": agent_id,
            "time_window_hours": time_window_hours,
            "status": status,
            "total_executions": total_executions,
            "successful_executions": successful,
            "failed_executions": failed,
            "success_rate": success_rate,
            "error_rate": error_rate,
            "execution_times": {
                "average_seconds": avg_exec_time,
                "median_seconds": p50_exec_time,
                "p95_seconds": p95_exec_time
            },
            "average_response_time_seconds": avg_response_time,
            "total_response_time_samples": len(resp_times)
        }

    @staticmethod
    def _determine_status(success_rate: float, avg_exec_time: float, error_rate: float) -> str:
        """Determine overall performance status"""
        thresholds = PerformanceMonitoring._thresholds

        # Check success rate
        if success_rate >= thresholds["success_rate"]["excellent"] and \
           avg_exec_time <= thresholds["execution_time_seconds"]["excellent"]:
            return PerformanceStatus.EXCELLENT

        if success_rate >= thresholds["success_rate"]["good"] and \
           avg_exec_time <= thresholds["execution_time_seconds"]["good"]:
            return PerformanceStatus.GOOD

        if success_rate >= thresholds["success_rate"]["fair"] and \
           avg_exec_time <= thresholds["execution_time_seconds"]["fair"]:
            return PerformanceStatus.FAIR

        if success_rate >= thresholds["success_rate"]["poor"] or \
           avg_exec_time <= thresholds["execution_time_seconds"]["poor"]:
            return PerformanceStatus.POOR

        return PerformanceStatus.CRITICAL

    @staticmethod
    def get_workflow_performance(
        session,
        workflow_id: str,
        time_window_hours: int = 24
    ) -> dict:
        """
        Get workflow performance metrics.

        Returns comprehensive performance analysis for a workflow.
        """
        cutoff = datetime.utcnow() - timedelta(hours=time_window_hours)

        executions = [
            e for e in PerformanceMonitoring._workflow_metrics[workflow_id]["executions"]
            if datetime.fromisoformat(e["timestamp"]) >= cutoff
        ]

        if not executions:
            return {
                "workflow_id": workflow_id,
                "time_window_hours": time_window_hours,
                "status": PerformanceStatus.GOOD,
                "message": "No data available"
            }

        # Calculate metrics
        total_executions = len(executions)
        successful = sum(1 for e in executions if e.get("success"))
        success_rate = successful / total_executions if total_executions > 0 else 0

        exec_times = [e["execution_time_seconds"] for e in executions if e.get("execution_time_seconds")]
        avg_exec_time = statistics.mean(exec_times) if exec_times else 0
        total_exec_time = sum(exec_times) if exec_times else 0

        # Calculate throughput
        time_span = time_window_hours * 3600
        throughput = total_executions / time_span if time_span > 0 else 0

        status = PerformanceMonitoring._determine_status(success_rate, avg_exec_time, 1 - success_rate)

        return {
            "workflow_id": workflow_id,
            "time_window_hours": time_window_hours,
            "status": status,
            "total_executions": total_executions,
            "successful_executions": successful,
            "success_rate": success_rate,
            "average_execution_time_seconds": avg_exec_time,
            "total_execution_time_seconds": total_exec_time,
            "throughput_per_second": throughput
        }

    @staticmethod
    def get_system_performance(
        session,
        time_window_hours: int = 24
    ) -> dict:
        """
        Get system-wide performance metrics.

        Returns aggregate performance across all agents and workflows.
        """
        cutoff = datetime.utcnow() - timedelta(hours=time_window_hours)

        executions = [
            e for e in PerformanceMonitoring._system_metrics["executions"]
            if datetime.fromisoformat(e["timestamp"]) >= cutoff
        ]

        if not executions:
            return {
                "time_window_hours": time_window_hours,
                "status": PerformanceStatus.GOOD,
                "message": "No data available"
            }

        # Calculate metrics
        total = len(executions)
        successful = sum(1 for e in executions if e.get("success"))
        success_rate = successful / total if total > 0 else 0

        exec_times = [e["execution_time_seconds"] for e in executions if e.get("execution_time_seconds")]
        avg_exec_time = statistics.mean(exec_times) if exec_times else 0

        # Unique agents and workflows
        unique_agents = len(set(e["agent_id"] for e in executions if e.get("agent_id")))
        unique_workflows = len(set(e["workflow_id"] for e in executions if e.get("workflow_id")))

        # Error distribution
        errors = [e for e in executions if not e.get("success")]
        error_types = defaultdict(int)
        for error in errors:
            error_type = error.get("error_type", "unknown")
            error_types[error_type] += 1

        status = PerformanceMonitoring._determine_status(success_rate, avg_exec_time, 1 - success_rate)

        return {
            "time_window_hours": time_window_hours,
            "status": status,
            "total_executions": total,
            "successful_executions": successful,
            "failed_executions": len(errors),
            "success_rate": success_rate,
            "average_execution_time_seconds": avg_exec_time,
            "unique_agents": unique_agents,
            "unique_workflows": unique_workflows,
            "error_distribution": dict(error_types)
        }

    @staticmethod
    def get_anomalies(
        session,
        severity: Optional[str] = None,
        limit: int = 50
    ) -> dict:
        """
        Get detected performance anomalies.

        Returns anomalies sorted by timestamp descending.
        """
        anomalies = list(PerformanceMonitoring._anomalies)

        if severity:
            anomalies = [a for a in anomalies if a.get("severity") == severity]

        # Sort by timestamp descending
        anomalies.sort(key=lambda a: a["timestamp"], reverse=True)

        return {
            "anomalies": anomalies[:limit],
            "total": len(anomalies)
        }

    @staticmethod
    def get_performance_trend(
        session,
        agent_id: Optional[int] = None,
        workflow_id: Optional[str] = None,
        metric_type: str = MetricType.EXECUTION_TIME,
        days: int = 7
    ) -> dict:
        """
        Get performance trends over time.

        Returns time-series data for trend analysis.
        """
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Get relevant executions
        if agent_id:
            executions = [
                e for e in PerformanceMonitoring._agent_metrics[agent_id]["executions"]
                if datetime.fromisoformat(e["timestamp"]) >= cutoff
            ]
        elif workflow_id:
            executions = [
                e for e in PerformanceMonitoring._workflow_metrics[workflow_id]["executions"]
                if datetime.fromisoformat(e["timestamp"]) >= cutoff
            ]
        else:
            executions = [
                e for e in PerformanceMonitoring._system_metrics["executions"]
                if datetime.fromisoformat(e["timestamp"]) >= cutoff
            ]

        # Group by day
        daily_metrics = defaultdict(list)
        for execution in executions:
            timestamp = datetime.fromisoformat(execution["timestamp"])
            day_key = timestamp.date().isoformat()

            if metric_type == MetricType.EXECUTION_TIME and execution.get("execution_time_seconds"):
                daily_metrics[day_key].append(execution["execution_time_seconds"])
            elif metric_type == MetricType.SUCCESS_RATE:
                daily_metrics[day_key].append(1 if execution.get("success") else 0)

        # Calculate daily averages
        trend_data = []
        for day_key in sorted(daily_metrics.keys()):
            values = daily_metrics[day_key]
            avg_value = statistics.mean(values) if values else 0

            trend_data.append({
                "date": day_key,
                "value": avg_value,
                "sample_count": len(values)
            })

        return {
            "agent_id": agent_id,
            "workflow_id": workflow_id,
            "metric_type": metric_type,
            "days": days,
            "trend_data": trend_data
        }

    @staticmethod
    def compare_agent_performance(
        session,
        agent_ids: List[int],
        time_window_hours: int = 24
    ) -> dict:
        """
        Compare performance across multiple agents.

        Returns side-by-side performance comparison.
        """
        comparisons = []

        for agent_id in agent_ids:
            perf = PerformanceMonitoring.get_agent_performance(
                session=session,
                agent_id=agent_id,
                time_window_hours=time_window_hours
            )
            comparisons.append(perf)

        # Rank by success rate
        comparisons.sort(key=lambda p: p.get("success_rate", 0), reverse=True)

        return {
            "agent_count": len(agent_ids),
            "time_window_hours": time_window_hours,
            "comparisons": comparisons,
            "best_performer": comparisons[0]["agent_id"] if comparisons else None,
            "worst_performer": comparisons[-1]["agent_id"] if comparisons else None
        }

    @staticmethod
    def get_performance_statistics(session) -> dict:
        """
        Get performance monitoring statistics.

        Returns aggregate metrics about the monitoring system.
        """
        total_metrics = len(PerformanceMonitoring._metrics)
        total_anomalies = len(PerformanceMonitoring._anomalies)

        # Agent performance statuses
        agent_statuses = defaultdict(int)
        for agent_id in PerformanceMonitoring._agent_metrics.keys():
            perf = PerformanceMonitoring.get_agent_performance(session, agent_id, time_window_hours=1)
            agent_statuses[perf["status"]] += 1

        return {
            "total_metrics_recorded": total_metrics,
            "total_anomalies_detected": total_anomalies,
            "monitored_agents": len(PerformanceMonitoring._agent_metrics),
            "monitored_workflows": len(PerformanceMonitoring._workflow_metrics),
            "agent_status_distribution": dict(agent_statuses),
            "total_executions": len(PerformanceMonitoring._system_metrics["executions"])
        }

    @staticmethod
    def update_thresholds(
        session,
        threshold_updates: dict
    ) -> dict:
        """Update performance thresholds"""
        PerformanceMonitoring._thresholds.update(threshold_updates)

        return {
            "success": True,
            "thresholds": PerformanceMonitoring._thresholds
        }

    @staticmethod
    def get_thresholds(session) -> dict:
        """Get current performance thresholds"""
        return PerformanceMonitoring._thresholds
