"""
Agent Analytics Service for performance tracking and analysis
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc

from src.models.agent import Agent, AgentRole, AgentStatus
from src.models.task import Task, TaskStatus
from src.models.agent_execution import AgentExecution, ExecutionStatus
from src.core.logging import logger


class AgentAnalytics:
    """
    Service for analyzing agent performance, tracking metrics,
    and providing insights into agent effectiveness.

    Provides:
    - Performance metrics per agent
    - Agent ranking and comparison
    - Success rate analysis
    - Response time analytics
    - Task completion trends
    - Cost analysis (if enabled)
    """

    @staticmethod
    def get_agent_performance(
        session: Session,
        agent_id: int,
        time_range_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get comprehensive performance metrics for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            time_range_hours: Time range for metrics

        Returns:
            Performance metrics dictionary
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        cutoff_time = datetime.utcnow() - timedelta(hours=time_range_hours)

        # Get executions in time range
        executions = session.query(AgentExecution).filter(
            and_(
                AgentExecution.agent_id == agent_id,
                AgentExecution.created_at >= cutoff_time
            )
        ).all()

        # Count by status
        status_counts = {}
        for status in ExecutionStatus:
            count = len([e for e in executions if e.status == status])
            if count > 0:
                status_counts[status.value] = count

        # Calculate success metrics
        completed = [e for e in executions if e.status == ExecutionStatus.COMPLETED]
        failed = [e for e in executions if e.status == ExecutionStatus.FAILED]
        total = len(executions)

        success_rate = len(completed) / total if total > 0 else 0
        failure_rate = len(failed) / total if total > 0 else 0

        # Calculate duration metrics
        durations = [
            (e.completed_at - e.started_at).total_seconds()
            for e in completed
            if e.started_at and e.completed_at
        ]

        duration_metrics = {}
        if durations:
            duration_metrics = {
                "average_duration_seconds": sum(durations) / len(durations),
                "min_duration_seconds": min(durations),
                "max_duration_seconds": max(durations),
                "median_duration_seconds": sorted(durations)[len(durations) // 2]
            }

        # Calculate retry metrics
        retry_count = sum(e.attempts - 1 for e in executions if e.attempts > 1)
        avg_attempts = sum(e.attempts for e in executions) / total if total > 0 else 0

        # Get task distribution by status
        tasks_completed = agent.successful_tasks
        tasks_failed = agent.failed_tasks
        total_lifetime_tasks = tasks_completed + tasks_failed

        performance = {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "agent_role": agent.role.value,
            "agent_status": agent.status.value,
            "time_range_hours": time_range_hours,

            # Execution counts
            "total_executions": total,
            "executions_by_status": status_counts,

            # Success metrics
            "success_rate": success_rate,
            "failure_rate": failure_rate,
            "completed_count": len(completed),
            "failed_count": len(failed),

            # Duration metrics
            "duration_metrics": duration_metrics,

            # Retry metrics
            "total_retries": retry_count,
            "average_attempts": avg_attempts,

            # Lifetime metrics
            "lifetime_successful_tasks": tasks_completed,
            "lifetime_failed_tasks": tasks_failed,
            "lifetime_total_tasks": total_lifetime_tasks,
            "lifetime_success_rate": tasks_completed / total_lifetime_tasks if total_lifetime_tasks > 0 else 0,

            # Agent info
            "average_response_time": agent.average_response_time,
            "current_task_id": agent.current_task_id,
            "last_active": agent.last_active.isoformat() if agent.last_active else None,
            "created_at": agent.created_at.isoformat() if agent.created_at else None
        }

        return performance

    @staticmethod
    def get_agent_ranking(
        session: Session,
        role: Optional[AgentRole] = None,
        metric: str = "success_rate",
        time_range_hours: int = 24,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Rank agents by specified metric.

        Args:
            session: Database session
            role: Filter by agent role
            metric: Ranking metric (success_rate, speed, total_tasks, etc.)
            time_range_hours: Time range for metrics
            limit: Maximum results

        Returns:
            Ranked list of agent performance
        """
        query = session.query(Agent)

        if role:
            query = query.filter(Agent.role == role)

        agents = query.all()

        # Calculate metrics for each agent
        agent_metrics = []
        for agent in agents:
            try:
                perf = AgentAnalytics.get_agent_performance(
                    session=session,
                    agent_id=agent.id,
                    time_range_hours=time_range_hours
                )
                agent_metrics.append(perf)
            except Exception as e:
                logger.warning(f"Failed to get performance for agent {agent.id}: {e}")
                continue

        # Sort by metric
        if metric == "success_rate":
            agent_metrics.sort(key=lambda x: x["success_rate"], reverse=True)
        elif metric == "speed":
            agent_metrics.sort(
                key=lambda x: x["duration_metrics"].get("average_duration_seconds", float('inf'))
            )
        elif metric == "total_tasks":
            agent_metrics.sort(key=lambda x: x["total_executions"], reverse=True)
        elif metric == "lifetime_success_rate":
            agent_metrics.sort(key=lambda x: x["lifetime_success_rate"], reverse=True)
        elif metric == "reliability":
            # Reliability = success_rate * (1 - retry_rate)
            agent_metrics.sort(
                key=lambda x: x["success_rate"] * (1 - (x["total_retries"] / max(x["total_executions"], 1))),
                reverse=True
            )

        # Add rank
        for i, metrics in enumerate(agent_metrics[:limit]):
            metrics["rank"] = i + 1

        return agent_metrics[:limit]

    @staticmethod
    def compare_agents(
        session: Session,
        agent_ids: List[int],
        time_range_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Compare performance of multiple agents.

        Args:
            session: Database session
            agent_ids: List of agent IDs to compare
            time_range_hours: Time range for metrics

        Returns:
            Comparison data
        """
        comparisons = []
        for agent_id in agent_ids:
            try:
                perf = AgentAnalytics.get_agent_performance(
                    session=session,
                    agent_id=agent_id,
                    time_range_hours=time_range_hours
                )
                comparisons.append(perf)
            except Exception as e:
                logger.warning(f"Failed to get performance for agent {agent_id}: {e}")
                continue

        # Calculate best performers
        best_success_rate = max(comparisons, key=lambda x: x["success_rate"]) if comparisons else None
        best_speed = min(
            [c for c in comparisons if c["duration_metrics"]],
            key=lambda x: x["duration_metrics"]["average_duration_seconds"]
        ) if any(c["duration_metrics"] for c in comparisons) else None
        most_active = max(comparisons, key=lambda x: x["total_executions"]) if comparisons else None

        return {
            "time_range_hours": time_range_hours,
            "agent_count": len(comparisons),
            "comparisons": comparisons,
            "best_success_rate": {
                "agent_id": best_success_rate["agent_id"],
                "agent_name": best_success_rate["agent_name"],
                "success_rate": best_success_rate["success_rate"]
            } if best_success_rate else None,
            "best_speed": {
                "agent_id": best_speed["agent_id"],
                "agent_name": best_speed["agent_name"],
                "average_duration_seconds": best_speed["duration_metrics"]["average_duration_seconds"]
            } if best_speed else None,
            "most_active": {
                "agent_id": most_active["agent_id"],
                "agent_name": most_active["agent_name"],
                "total_executions": most_active["total_executions"]
            } if most_active else None
        }

    @staticmethod
    def get_execution_trends(
        session: Session,
        agent_id: Optional[int] = None,
        role: Optional[AgentRole] = None,
        time_range_hours: int = 168,  # 7 days
        interval_hours: int = 24  # Daily buckets
    ) -> Dict[str, Any]:
        """
        Get execution trends over time.

        Args:
            session: Database session
            agent_id: Filter by agent
            role: Filter by role
            time_range_hours: Total time range
            interval_hours: Bucket interval

        Returns:
            Trend data
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=time_range_hours)

        query = session.query(AgentExecution).filter(
            AgentExecution.created_at >= cutoff_time
        )

        if agent_id:
            query = query.filter(AgentExecution.agent_id == agent_id)
        elif role:
            query = query.join(Agent).filter(Agent.role == role)

        executions = query.all()

        # Create time buckets
        num_buckets = time_range_hours // interval_hours
        buckets = []

        for i in range(num_buckets):
            bucket_start = cutoff_time + timedelta(hours=i * interval_hours)
            bucket_end = bucket_start + timedelta(hours=interval_hours)

            bucket_executions = [
                e for e in executions
                if bucket_start <= e.created_at < bucket_end
            ]

            completed = len([e for e in bucket_executions if e.status == ExecutionStatus.COMPLETED])
            failed = len([e for e in bucket_executions if e.status == ExecutionStatus.FAILED])
            total = len(bucket_executions)

            buckets.append({
                "period_start": bucket_start.isoformat(),
                "period_end": bucket_end.isoformat(),
                "total_executions": total,
                "completed": completed,
                "failed": failed,
                "success_rate": completed / total if total > 0 else 0
            })

        return {
            "time_range_hours": time_range_hours,
            "interval_hours": interval_hours,
            "bucket_count": num_buckets,
            "agent_id": agent_id,
            "role": role.value if role else None,
            "trends": buckets
        }

    @staticmethod
    def get_task_distribution(
        session: Session,
        agent_id: Optional[int] = None,
        time_range_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get distribution of tasks by various dimensions.

        Args:
            session: Database session
            agent_id: Filter by agent
            time_range_hours: Time range

        Returns:
            Distribution data
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=time_range_hours)

        query = session.query(AgentExecution).filter(
            AgentExecution.created_at >= cutoff_time
        )

        if agent_id:
            query = query.filter(AgentExecution.agent_id == agent_id)

        executions = query.all()

        # Distribution by status
        by_status = {}
        for status in ExecutionStatus:
            count = len([e for e in executions if e.status == status])
            if count > 0:
                by_status[status.value] = count

        # Distribution by priority
        priorities = [e.priority for e in executions if e.priority is not None]
        by_priority = {}
        if priorities:
            for priority in set(priorities):
                by_priority[str(priority)] = priorities.count(priority)

        # Distribution by agent (if not filtered by agent_id)
        by_agent = {}
        if not agent_id:
            for execution in executions:
                agent_name = execution.agent.name if execution.agent else "Unknown"
                by_agent[agent_name] = by_agent.get(agent_name, 0) + 1

        # Distribution by attempts
        by_attempts = {}
        for execution in executions:
            attempts_key = f"{execution.attempts}_attempts"
            by_attempts[attempts_key] = by_attempts.get(attempts_key, 0) + 1

        return {
            "time_range_hours": time_range_hours,
            "total_executions": len(executions),
            "by_status": by_status,
            "by_priority": by_priority,
            "by_agent": by_agent if by_agent else None,
            "by_attempts": by_attempts
        }

    @staticmethod
    def get_error_analysis(
        session: Session,
        agent_id: Optional[int] = None,
        time_range_hours: int = 168
    ) -> Dict[str, Any]:
        """
        Analyze errors and failure patterns.

        Args:
            session: Database session
            agent_id: Filter by agent
            time_range_hours: Time range

        Returns:
            Error analysis data
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=time_range_hours)

        query = session.query(AgentExecution).filter(
            and_(
                AgentExecution.created_at >= cutoff_time,
                AgentExecution.status == ExecutionStatus.FAILED
            )
        )

        if agent_id:
            query = query.filter(AgentExecution.agent_id == agent_id)

        failed_executions = query.all()

        # Group by error message
        error_groups = {}
        for execution in failed_executions:
            error_msg = execution.error_message or "Unknown error"
            if error_msg not in error_groups:
                error_groups[error_msg] = {
                    "count": 0,
                    "error_message": error_msg,
                    "execution_ids": [],
                    "agent_ids": set()
                }
            error_groups[error_msg]["count"] += 1
            error_groups[error_msg]["execution_ids"].append(execution.id)
            error_groups[error_msg]["agent_ids"].add(execution.agent_id)

        # Convert to list and sort by count
        error_list = list(error_groups.values())
        for error in error_list:
            error["agent_ids"] = list(error["agent_ids"])
            error["execution_ids"] = error["execution_ids"][:10]  # Limit to first 10

        error_list.sort(key=lambda x: x["count"], reverse=True)

        # Calculate retry success rate
        retried = [e for e in failed_executions if e.attempts > 1]
        retry_rate = len(retried) / len(failed_executions) if failed_executions else 0

        return {
            "time_range_hours": time_range_hours,
            "total_failures": len(failed_executions),
            "unique_error_types": len(error_groups),
            "retry_rate": retry_rate,
            "top_errors": error_list[:10],
            "agent_id": agent_id
        }

    @staticmethod
    def get_agent_utilization(
        session: Session,
        time_range_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get agent utilization metrics.

        Args:
            session: Database session
            time_range_hours: Time range

        Returns:
            Utilization metrics
        """
        agents = session.query(Agent).all()

        utilization_data = []
        for agent in agents:
            cutoff_time = datetime.utcnow() - timedelta(hours=time_range_hours)

            # Get executions
            executions = session.query(AgentExecution).filter(
                and_(
                    AgentExecution.agent_id == agent.id,
                    AgentExecution.created_at >= cutoff_time
                )
            ).all()

            # Calculate busy time
            busy_time_seconds = 0
            for execution in executions:
                if execution.started_at and execution.completed_at:
                    duration = (execution.completed_at - execution.started_at).total_seconds()
                    busy_time_seconds += duration

            total_time_seconds = time_range_hours * 3600
            utilization_rate = busy_time_seconds / total_time_seconds if total_time_seconds > 0 else 0

            utilization_data.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "agent_role": agent.role.value,
                "agent_status": agent.status.value,
                "busy_time_hours": busy_time_seconds / 3600,
                "utilization_rate": utilization_rate,
                "executions_count": len(executions)
            })

        # Sort by utilization rate
        utilization_data.sort(key=lambda x: x["utilization_rate"], reverse=True)

        avg_utilization = sum(u["utilization_rate"] for u in utilization_data) / len(utilization_data) if utilization_data else 0

        return {
            "time_range_hours": time_range_hours,
            "total_agents": len(agents),
            "average_utilization_rate": avg_utilization,
            "agents": utilization_data
        }

    @staticmethod
    def get_performance_summary(
        session: Session,
        time_range_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get overall system performance summary.

        Args:
            session: Database session
            time_range_hours: Time range

        Returns:
            Performance summary
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=time_range_hours)

        # Get all executions
        executions = session.query(AgentExecution).filter(
            AgentExecution.created_at >= cutoff_time
        ).all()

        # Get all agents
        agents = session.query(Agent).all()
        active_agents = [a for a in agents if a.status in [AgentStatus.BUSY, AgentStatus.IDLE]]
        busy_agents = [a for a in agents if a.status == AgentStatus.BUSY]

        # Calculate metrics
        total_executions = len(executions)
        completed = len([e for e in executions if e.status == ExecutionStatus.COMPLETED])
        failed = len([e for e in executions if e.status == ExecutionStatus.FAILED])
        running = len([e for e in executions if e.status == ExecutionStatus.RUNNING])
        queued = len([e for e in executions if e.status == ExecutionStatus.QUEUED])

        success_rate = completed / total_executions if total_executions > 0 else 0

        # Calculate average response time
        durations = [
            (e.completed_at - e.started_at).total_seconds()
            for e in executions
            if e.started_at and e.completed_at and e.status == ExecutionStatus.COMPLETED
        ]

        avg_duration = sum(durations) / len(durations) if durations else 0

        return {
            "time_range_hours": time_range_hours,
            "timestamp": datetime.utcnow().isoformat(),

            # Agent metrics
            "total_agents": len(agents),
            "active_agents": len(active_agents),
            "busy_agents": len(busy_agents),
            "idle_agents": len(active_agents) - len(busy_agents),

            # Execution metrics
            "total_executions": total_executions,
            "completed_executions": completed,
            "failed_executions": failed,
            "running_executions": running,
            "queued_executions": queued,

            # Performance metrics
            "success_rate": success_rate,
            "failure_rate": failed / total_executions if total_executions > 0 else 0,
            "average_response_time_seconds": avg_duration,

            # Throughput
            "executions_per_hour": total_executions / time_range_hours if time_range_hours > 0 else 0,
            "completions_per_hour": completed / time_range_hours if time_range_hours > 0 else 0
        }
