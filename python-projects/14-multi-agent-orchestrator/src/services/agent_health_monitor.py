"""
Agent Health Monitoring Service
Tracks agent health, uptime, failures, and provides health checks
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from src.models.agent import Agent, AgentStatus
from src.models.agent_execution import AgentExecution, ExecutionStatus
from src.services.agent_resource import AgentResource
from src.core.logging import logger


class HealthStatus:
    """Health status constants"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class AgentHealthMonitor:
    """
    Agent Health Monitoring Service

    Tracks agent health, performs health checks, and monitors uptime/failures.
    """

    @staticmethod
    def check_agent_health(
        session: Session,
        agent_id: int
    ) -> Dict[str, Any]:
        """
        Perform comprehensive health check on an agent.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Health check results
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        health_checks = {}
        issues = []
        warnings = []

        # Check 1: Agent status
        if agent.status == AgentStatus.ACTIVE:
            health_checks["status"] = "pass"
        elif agent.status == AgentStatus.IDLE:
            health_checks["status"] = "pass"
            warnings.append("Agent is idle")
        elif agent.status == AgentStatus.BUSY:
            health_checks["status"] = "pass"
        else:
            health_checks["status"] = "fail"
            issues.append(f"Agent status is {agent.status.value}")

        # Check 2: Heartbeat (last activity)
        last_heartbeat = AgentHealthMonitor._get_last_heartbeat(session, agent_id)
        if last_heartbeat:
            age_minutes = (datetime.utcnow() - last_heartbeat).total_seconds() / 60
            if age_minutes < 5:
                health_checks["heartbeat"] = "pass"
            elif age_minutes < 15:
                health_checks["heartbeat"] = "warn"
                warnings.append(f"No heartbeat for {age_minutes:.1f} minutes")
            else:
                health_checks["heartbeat"] = "fail"
                issues.append(f"No heartbeat for {age_minutes:.1f} minutes")
        else:
            health_checks["heartbeat"] = "unknown"
            warnings.append("No heartbeat data available")

        # Check 3: Resource utilization
        usage_info = AgentResource.get_resource_usage(session, agent_id)
        if usage_info["is_overloaded"]:
            health_checks["resources"] = "fail"
            issues.append("Agent is overloaded (>90% utilization)")
        else:
            avg_util = sum(usage_info["utilization_percentage"].values()) / len(usage_info["utilization_percentage"])
            if avg_util < 80:
                health_checks["resources"] = "pass"
            else:
                health_checks["resources"] = "warn"
                warnings.append(f"High resource utilization ({avg_util:.1f}%)")

        # Check 4: Error rate
        error_rate = AgentHealthMonitor._calculate_error_rate(session, agent_id)
        if error_rate < 5:
            health_checks["error_rate"] = "pass"
        elif error_rate < 15:
            health_checks["error_rate"] = "warn"
            warnings.append(f"Elevated error rate ({error_rate:.1f}%)")
        else:
            health_checks["error_rate"] = "fail"
            issues.append(f"High error rate ({error_rate:.1f}%)")

        # Check 5: Execution performance
        avg_duration = AgentHealthMonitor._get_average_execution_time(session, agent_id)
        if avg_duration is not None:
            if avg_duration < 300:  # Less than 5 minutes
                health_checks["performance"] = "pass"
            elif avg_duration < 600:  # Less than 10 minutes
                health_checks["performance"] = "warn"
                warnings.append(f"Slow execution time ({avg_duration:.1f}s avg)")
            else:
                health_checks["performance"] = "fail"
                issues.append(f"Very slow execution time ({avg_duration:.1f}s avg)")
        else:
            health_checks["performance"] = "unknown"

        # Determine overall health status
        if any(check == "fail" for check in health_checks.values()):
            overall_status = HealthStatus.UNHEALTHY
        elif any(check == "warn" for check in health_checks.values()):
            overall_status = HealthStatus.DEGRADED
        elif all(check in ["pass", "unknown"] for check in health_checks.values()):
            overall_status = HealthStatus.HEALTHY
        else:
            overall_status = HealthStatus.UNKNOWN

        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "overall_status": overall_status,
            "checks": health_checks,
            "issues": issues,
            "warnings": warnings,
            "checked_at": datetime.utcnow().isoformat(),
            "last_heartbeat": last_heartbeat.isoformat() if last_heartbeat else None,
            "error_rate_percentage": error_rate,
            "avg_execution_time_seconds": avg_duration
        }

    @staticmethod
    def _get_last_heartbeat(session: Session, agent_id: int) -> Optional[datetime]:
        """Get the last heartbeat timestamp for an agent."""
        agent = session.query(Agent).filter(Agent.id == agent_id).first()

        # Try to get from agent metadata
        if agent.metadata and "last_heartbeat" in agent.metadata:
            return datetime.fromisoformat(agent.metadata["last_heartbeat"])

        # Fallback: use last execution start time
        last_execution = session.query(AgentExecution).filter(
            AgentExecution.agent_id == agent_id
        ).order_by(AgentExecution.started_at.desc()).first()

        if last_execution and last_execution.started_at:
            return last_execution.started_at

        return None

    @staticmethod
    def _calculate_error_rate(session: Session, agent_id: int, hours: int = 24) -> float:
        """Calculate error rate for an agent over the specified time period."""
        since = datetime.utcnow() - timedelta(hours=hours)

        executions = session.query(AgentExecution).filter(
            and_(
                AgentExecution.agent_id == agent_id,
                AgentExecution.started_at >= since,
                AgentExecution.status.in_([ExecutionStatus.COMPLETED, ExecutionStatus.FAILED])
            )
        ).all()

        if not executions:
            return 0.0

        failed_count = sum(1 for exec in executions if exec.status == ExecutionStatus.FAILED)
        return (failed_count / len(executions)) * 100

    @staticmethod
    def _get_average_execution_time(session: Session, agent_id: int, hours: int = 24) -> Optional[float]:
        """Get average execution time for completed tasks."""
        since = datetime.utcnow() - timedelta(hours=hours)

        executions = session.query(AgentExecution).filter(
            and_(
                AgentExecution.agent_id == agent_id,
                AgentExecution.status == ExecutionStatus.COMPLETED,
                AgentExecution.started_at >= since,
                AgentExecution.completed_at.isnot(None)
            )
        ).all()

        if not executions:
            return None

        durations = []
        for exec in executions:
            duration = (exec.completed_at - exec.started_at).total_seconds()
            durations.append(duration)

        return sum(durations) / len(durations)

    @staticmethod
    def record_heartbeat(
        session: Session,
        agent_id: int
    ) -> Dict[str, Any]:
        """
        Record a heartbeat for an agent.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Heartbeat confirmation
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if not agent.metadata:
            agent.metadata = {}

        agent.metadata["last_heartbeat"] = datetime.utcnow().isoformat()

        # Initialize heartbeat history if not exists
        if "heartbeat_history" not in agent.metadata:
            agent.metadata["heartbeat_history"] = []

        # Keep last 100 heartbeats
        agent.metadata["heartbeat_history"].append(datetime.utcnow().isoformat())
        if len(agent.metadata["heartbeat_history"]) > 100:
            agent.metadata["heartbeat_history"] = agent.metadata["heartbeat_history"][-100:]

        session.commit()

        logger.info(f"Recorded heartbeat for agent {agent_id}")

        return {
            "agent_id": agent_id,
            "heartbeat_at": agent.metadata["last_heartbeat"],
            "message": "Heartbeat recorded"
        }

    @staticmethod
    def get_uptime_stats(
        session: Session,
        agent_id: int,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get uptime statistics for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            days: Number of days to analyze

        Returns:
            Uptime statistics
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        since = datetime.utcnow() - timedelta(days=days)

        # Get all executions in period
        executions = session.query(AgentExecution).filter(
            and_(
                AgentExecution.agent_id == agent_id,
                AgentExecution.started_at >= since
            )
        ).all()

        total_executions = len(executions)
        successful = sum(1 for exec in executions if exec.status == ExecutionStatus.COMPLETED)
        failed = sum(1 for exec in executions if exec.status == ExecutionStatus.FAILED)

        # Calculate uptime percentage
        if total_executions > 0:
            uptime_percentage = (successful / total_executions) * 100
        else:
            uptime_percentage = 100.0  # No failures if no executions

        # Calculate total active time
        total_active_seconds = 0
        for exec in executions:
            if exec.started_at and exec.completed_at:
                duration = (exec.completed_at - exec.started_at).total_seconds()
                total_active_seconds += duration

        # Get failure breakdown
        failure_reasons = {}
        for exec in executions:
            if exec.status == ExecutionStatus.FAILED:
                reason = "Unknown"
                if exec.result and "error" in exec.result:
                    reason = exec.result["error"][:50]  # First 50 chars
                failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "period_days": days,
            "total_executions": total_executions,
            "successful_executions": successful,
            "failed_executions": failed,
            "uptime_percentage": uptime_percentage,
            "total_active_hours": total_active_seconds / 3600,
            "failure_reasons": failure_reasons,
            "analyzed_from": since.isoformat(),
            "analyzed_to": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_cluster_health(
        session: Session
    ) -> Dict[str, Any]:
        """
        Get overall cluster health status.

        Args:
            session: Database session

        Returns:
            Cluster health information
        """
        agents = session.query(Agent).all()

        health_summary = {
            HealthStatus.HEALTHY: 0,
            HealthStatus.DEGRADED: 0,
            HealthStatus.UNHEALTHY: 0,
            HealthStatus.UNKNOWN: 0
        }

        agent_health_list = []

        for agent in agents:
            health = AgentHealthMonitor.check_agent_health(session, agent.id)
            health_summary[health["overall_status"]] += 1

            agent_health_list.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "status": health["overall_status"],
                "issue_count": len(health["issues"]),
                "warning_count": len(health["warnings"])
            })

        total_agents = len(agents)
        healthy_percentage = (health_summary[HealthStatus.HEALTHY] / total_agents * 100) if total_agents > 0 else 0

        # Determine overall cluster health
        if healthy_percentage >= 90:
            cluster_status = HealthStatus.HEALTHY
        elif healthy_percentage >= 70:
            cluster_status = HealthStatus.DEGRADED
        else:
            cluster_status = HealthStatus.UNHEALTHY

        return {
            "cluster_status": cluster_status,
            "total_agents": total_agents,
            "healthy_agents": health_summary[HealthStatus.HEALTHY],
            "degraded_agents": health_summary[HealthStatus.DEGRADED],
            "unhealthy_agents": health_summary[HealthStatus.UNHEALTHY],
            "unknown_agents": health_summary[HealthStatus.UNKNOWN],
            "healthy_percentage": healthy_percentage,
            "agents": agent_health_list,
            "checked_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def detect_anomalies(
        session: Session,
        agent_id: int,
        threshold_std_dev: float = 2.0
    ) -> Dict[str, Any]:
        """
        Detect anomalies in agent behavior.

        Args:
            session: Database session
            agent_id: Agent ID
            threshold_std_dev: Standard deviations from mean to consider anomaly

        Returns:
            Detected anomalies
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        since = datetime.utcnow() - timedelta(days=7)

        executions = session.query(AgentExecution).filter(
            and_(
                AgentExecution.agent_id == agent_id,
                AgentExecution.started_at >= since,
                AgentExecution.status == ExecutionStatus.COMPLETED,
                AgentExecution.completed_at.isnot(None)
            )
        ).all()

        if len(executions) < 10:
            return {
                "agent_id": agent_id,
                "anomalies_detected": False,
                "message": "Insufficient data for anomaly detection (need at least 10 executions)"
            }

        # Calculate execution time statistics
        durations = [(exec.completed_at - exec.started_at).total_seconds() for exec in executions]
        mean_duration = sum(durations) / len(durations)
        variance = sum((d - mean_duration) ** 2 for d in durations) / len(durations)
        std_dev = variance ** 0.5

        # Detect anomalies
        anomalies = []
        for i, exec in enumerate(executions):
            duration = durations[i]
            z_score = (duration - mean_duration) / std_dev if std_dev > 0 else 0

            if abs(z_score) > threshold_std_dev:
                anomalies.append({
                    "execution_id": exec.id,
                    "task_id": exec.task_id,
                    "duration_seconds": duration,
                    "z_score": z_score,
                    "deviation_type": "slow" if z_score > 0 else "fast",
                    "timestamp": exec.started_at.isoformat()
                })

        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "anomalies_detected": len(anomalies) > 0,
            "total_anomalies": len(anomalies),
            "anomalies": anomalies,
            "statistics": {
                "mean_duration_seconds": mean_duration,
                "std_dev_seconds": std_dev,
                "min_duration_seconds": min(durations),
                "max_duration_seconds": max(durations),
                "total_executions_analyzed": len(executions)
            },
            "threshold_std_dev": threshold_std_dev
        }

    @staticmethod
    def get_failure_analysis(
        session: Session,
        agent_id: int,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Analyze failures for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            days: Number of days to analyze

        Returns:
            Failure analysis
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        since = datetime.utcnow() - timedelta(days=days)

        failed_executions = session.query(AgentExecution).filter(
            and_(
                AgentExecution.agent_id == agent_id,
                AgentExecution.status == ExecutionStatus.FAILED,
                AgentExecution.started_at >= since
            )
        ).all()

        # Categorize failures
        failure_categories = {
            "timeout": 0,
            "resource_exhaustion": 0,
            "execution_error": 0,
            "unknown": 0
        }

        failure_timeline = []

        for exec in failed_executions:
            error_msg = ""
            if exec.result and "error" in exec.result:
                error_msg = exec.result["error"].lower()

            # Categorize
            if "timeout" in error_msg:
                failure_categories["timeout"] += 1
                category = "timeout"
            elif "memory" in error_msg or "resource" in error_msg:
                failure_categories["resource_exhaustion"] += 1
                category = "resource_exhaustion"
            elif error_msg:
                failure_categories["execution_error"] += 1
                category = "execution_error"
            else:
                failure_categories["unknown"] += 1
                category = "unknown"

            failure_timeline.append({
                "execution_id": exec.id,
                "task_id": exec.task_id,
                "category": category,
                "error_message": exec.result.get("error") if exec.result else "No error message",
                "failed_at": exec.updated_at.isoformat() if exec.updated_at else None
            })

        total_failures = len(failed_executions)

        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "period_days": days,
            "total_failures": total_failures,
            "failure_categories": failure_categories,
            "failure_timeline": failure_timeline[-20:],  # Last 20 failures
            "analyzed_from": since.isoformat(),
            "analyzed_to": datetime.utcnow().isoformat()
        }

    @staticmethod
    def set_health_threshold(
        session: Session,
        agent_id: int,
        check_type: str,
        threshold_value: float
    ) -> Dict[str, Any]:
        """
        Set custom health check threshold for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            check_type: Type of check (error_rate/response_time/resource_usage)
            threshold_value: Threshold value

        Returns:
            Updated threshold configuration
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if not agent.metadata:
            agent.metadata = {}

        if "health_thresholds" not in agent.metadata:
            agent.metadata["health_thresholds"] = {}

        agent.metadata["health_thresholds"][check_type] = threshold_value
        session.commit()

        logger.info(f"Set {check_type} threshold to {threshold_value} for agent {agent_id}")

        return {
            "agent_id": agent_id,
            "check_type": check_type,
            "threshold_value": threshold_value,
            "thresholds": agent.metadata["health_thresholds"]
        }
