"""
Monitoring service for collecting system metrics and dashboard data
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.models import (
    Task, TaskStatus, TaskPriority,
    Agent, AgentStatus,
    AgentExecution, ExecutionStatus,
    Workflow, WorkflowStatus
)


class MonitoringService:
    """Service for collecting monitoring metrics and dashboard data"""

    def get_dashboard_overview(self, db: Session) -> Dict[str, Any]:
        """
        Get high-level overview metrics for dashboard

        Returns:
            dict: Overview metrics including task counts, agent status, execution stats
        """
        now = datetime.utcnow()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)

        # Task metrics
        total_tasks = db.query(func.count(Task.id)).scalar()
        tasks_pending = db.query(func.count(Task.id)).filter(
            Task.status == TaskStatus.PENDING
        ).scalar()
        tasks_running = db.query(func.count(Task.id)).filter(
            Task.status == TaskStatus.IN_PROGRESS
        ).scalar()
        tasks_completed = db.query(func.count(Task.id)).filter(
            Task.status == TaskStatus.COMPLETED
        ).scalar()
        tasks_failed = db.query(func.count(Task.id)).filter(
            Task.status == TaskStatus.FAILED
        ).scalar()
        tasks_24h = db.query(func.count(Task.id)).filter(
            Task.created_at >= last_24h
        ).scalar()

        # Agent metrics
        total_agents = db.query(func.count(Agent.id)).scalar()
        agents_active = db.query(func.count(Agent.id)).filter(
            Agent.status.in_([AgentStatus.IDLE, AgentStatus.BUSY, AgentStatus.WAITING])
        ).scalar()
        agents_busy = db.query(func.count(Agent.id)).filter(
            Agent.status == AgentStatus.BUSY
        ).scalar()
        agents_idle = db.query(func.count(Agent.id)).filter(
            Agent.status == AgentStatus.IDLE
        ).scalar()
        agents_offline = db.query(func.count(Agent.id)).filter(
            Agent.status == AgentStatus.OFFLINE
        ).scalar()

        # Execution metrics
        total_executions = db.query(func.count(AgentExecution.id)).scalar()
        executions_running = db.query(func.count(AgentExecution.id)).filter(
            AgentExecution.status == ExecutionStatus.RUNNING
        ).scalar()
        executions_completed = db.query(func.count(AgentExecution.id)).filter(
            AgentExecution.status == ExecutionStatus.COMPLETED
        ).scalar()
        executions_failed = db.query(func.count(AgentExecution.id)).filter(
            AgentExecution.status == ExecutionStatus.FAILED
        ).scalar()

        # Workflow metrics
        total_workflows = db.query(func.count(Workflow.id)).scalar()
        workflows_running = db.query(func.count(Workflow.id)).filter(
            Workflow.status == WorkflowStatus.RUNNING
        ).scalar()
        workflows_completed = db.query(func.count(Workflow.id)).filter(
            Workflow.status == WorkflowStatus.COMPLETED
        ).scalar()

        # Success rates
        task_success_rate = 0
        if total_tasks > 0:
            task_success_rate = (tasks_completed / total_tasks) * 100

        execution_success_rate = 0
        if total_executions > 0:
            execution_success_rate = (executions_completed / total_executions) * 100

        return {
            "overview": {
                "total_tasks": total_tasks,
                "total_agents": total_agents,
                "total_executions": total_executions,
                "total_workflows": total_workflows,
                "tasks_24h": tasks_24h
            },
            "tasks": {
                "pending": tasks_pending,
                "running": tasks_running,
                "completed": tasks_completed,
                "failed": tasks_failed,
                "success_rate": round(task_success_rate, 2)
            },
            "agents": {
                "active": agents_active,
                "busy": agents_busy,
                "idle": agents_idle,
                "offline": agents_offline
            },
            "executions": {
                "running": executions_running,
                "completed": executions_completed,
                "failed": executions_failed,
                "success_rate": round(execution_success_rate, 2)
            },
            "workflows": {
                "total": total_workflows,
                "running": workflows_running,
                "completed": workflows_completed
            },
            "timestamp": now.isoformat()
        }

    def get_task_metrics(
        self,
        db: Session,
        time_range: str = "24h"
    ) -> Dict[str, Any]:
        """
        Get detailed task metrics over time

        Args:
            db: Database session
            time_range: Time range for metrics ("24h", "7d", "30d")

        Returns:
            dict: Task metrics including counts by status, priority, and time
        """
        now = datetime.utcnow()

        # Calculate time range
        if time_range == "24h":
            start_time = now - timedelta(hours=24)
        elif time_range == "7d":
            start_time = now - timedelta(days=7)
        elif time_range == "30d":
            start_time = now - timedelta(days=30)
        else:
            start_time = now - timedelta(hours=24)

        # Tasks by status in time range
        tasks_by_status = db.query(
            Task.status,
            func.count(Task.id).label('count')
        ).filter(
            Task.created_at >= start_time
        ).group_by(Task.status).all()

        # Tasks by priority in time range
        tasks_by_priority = db.query(
            Task.priority,
            func.count(Task.id).label('count')
        ).filter(
            Task.created_at >= start_time
        ).group_by(Task.priority).all()

        # Average task duration (completed tasks only)
        # Calculate from started_at to completed_at for accurate duration
        avg_duration_result = db.query(
            func.avg(
                func.extract('epoch', Task.completed_at - Task.started_at)
            ).label('avg_duration')
        ).filter(
            Task.status == TaskStatus.COMPLETED,
            Task.completed_at.isnot(None),
            Task.started_at.isnot(None),
            Task.created_at >= start_time
        ).scalar()

        # Ensure non-negative duration
        avg_duration = avg_duration_result if avg_duration_result and avg_duration_result > 0 else 0

        return {
            "time_range": time_range,
            "start_time": start_time.isoformat(),
            "end_time": now.isoformat(),
            "by_status": {
                str(status): count for status, count in tasks_by_status
            },
            "by_priority": {
                str(priority): count for priority, count in tasks_by_priority
            },
            "average_duration_seconds": round(avg_duration, 2),
            "timestamp": now.isoformat()
        }

    def get_agent_performance(self, db: Session) -> List[Dict[str, Any]]:
        """
        Get performance metrics for each agent

        Returns:
            list: Agent performance data including execution counts and success rates
        """
        agents = db.query(Agent).all()
        performance_data = []

        for agent in agents:
            # Count executions
            total_executions = db.query(func.count(AgentExecution.id)).filter(
                AgentExecution.agent_id == agent.id
            ).scalar()

            completed_executions = db.query(func.count(AgentExecution.id)).filter(
                AgentExecution.agent_id == agent.id,
                AgentExecution.status == ExecutionStatus.COMPLETED
            ).scalar()

            failed_executions = db.query(func.count(AgentExecution.id)).filter(
                AgentExecution.agent_id == agent.id,
                AgentExecution.status == ExecutionStatus.FAILED
            ).scalar()

            # Calculate success rate
            success_rate = 0
            if total_executions > 0:
                success_rate = (completed_executions / total_executions) * 100

            # Get average execution time
            avg_duration_result = db.query(
                func.avg(
                    func.extract('epoch', AgentExecution.completed_at - AgentExecution.started_at)
                ).label('avg_duration')
            ).filter(
                AgentExecution.agent_id == agent.id,
                AgentExecution.status == ExecutionStatus.COMPLETED,
                AgentExecution.completed_at.isnot(None)
            ).scalar()

            avg_duration = avg_duration_result if avg_duration_result else 0

            performance_data.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "agent_role": str(agent.role),
                "status": str(agent.status),
                "total_executions": total_executions,
                "completed_executions": completed_executions,
                "failed_executions": failed_executions,
                "success_rate": round(success_rate, 2),
                "average_duration_seconds": round(avg_duration, 2),
                "capabilities": agent.capabilities,
                "last_active": agent.last_active_at.isoformat() if agent.last_active_at else None
            })

        # Sort by total executions descending
        performance_data.sort(key=lambda x: x['total_executions'], reverse=True)

        return performance_data

    def get_workflow_metrics(self, db: Session) -> Dict[str, Any]:
        """
        Get workflow execution metrics

        Returns:
            dict: Workflow metrics including counts by status and type
        """
        now = datetime.utcnow()

        # Workflows by status
        workflows_by_status = db.query(
            Workflow.status,
            func.count(Workflow.id).label('count')
        ).group_by(Workflow.status).all()

        # Workflows by type
        workflows_by_type = db.query(
            Workflow.workflow_type,
            func.count(Workflow.id).label('count')
        ).group_by(Workflow.workflow_type).all()

        # Average workflow duration
        avg_duration_result = db.query(
            func.avg(
                func.extract('epoch', Workflow.completed_at - Workflow.started_at)
            ).label('avg_duration')
        ).filter(
            Workflow.status == WorkflowStatus.COMPLETED,
            Workflow.completed_at.isnot(None),
            Workflow.started_at.isnot(None)
        ).scalar()

        avg_duration = avg_duration_result if avg_duration_result else 0

        # Recent workflows (last 10)
        recent_workflows = db.query(Workflow).order_by(
            Workflow.created_at.desc()
        ).limit(10).all()

        return {
            "by_status": {
                str(status): count for status, count in workflows_by_status
            },
            "by_type": {
                str(wf_type): count for wf_type, count in workflows_by_type
            },
            "average_duration_seconds": round(avg_duration, 2),
            "recent_workflows": [
                {
                    "id": wf.id,
                    "name": wf.name,
                    "type": str(wf.workflow_type),
                    "status": str(wf.status),
                    "created_at": wf.created_at.isoformat(),
                    "completed_at": wf.completed_at.isoformat() if wf.completed_at else None
                }
                for wf in recent_workflows
            ],
            "timestamp": now.isoformat()
        }

    def get_system_health(self, db: Session) -> Dict[str, Any]:
        """
        Get overall system health status

        Returns:
            dict: System health indicators
        """
        now = datetime.utcnow()

        # Check for stuck tasks (running for > 1 hour)
        one_hour_ago = now - timedelta(hours=1)
        stuck_tasks = db.query(func.count(Task.id)).filter(
            Task.status == TaskStatus.IN_PROGRESS,
            Task.created_at < one_hour_ago
        ).scalar()

        # Check for failed tasks in last hour
        failed_tasks_recent = db.query(func.count(Task.id)).filter(
            Task.status == TaskStatus.FAILED,
            Task.created_at >= one_hour_ago
        ).scalar()

        # Check agent availability
        total_agents = db.query(func.count(Agent.id)).scalar()
        active_agents = db.query(func.count(Agent.id)).filter(
            Agent.status.in_([AgentStatus.IDLE, AgentStatus.BUSY, AgentStatus.WAITING])
        ).scalar()

        # Determine health status
        health_status = "healthy"
        health_issues = []

        if stuck_tasks > 0:
            health_status = "warning"
            health_issues.append(f"{stuck_tasks} tasks running for over 1 hour")

        if failed_tasks_recent > 5:
            health_status = "warning"
            health_issues.append(f"{failed_tasks_recent} tasks failed in last hour")

        if total_agents > 0 and (active_agents / total_agents) < 0.5:
            health_status = "critical"
            health_issues.append(f"Only {active_agents}/{total_agents} agents available")

        return {
            "status": health_status,
            "issues": health_issues,
            "metrics": {
                "stuck_tasks": stuck_tasks,
                "failed_tasks_1h": failed_tasks_recent,
                "total_agents": total_agents,
                "active_agents": active_agents,
                "agent_availability_percent": round((active_agents / total_agents * 100) if total_agents > 0 else 0, 2)
            },
            "timestamp": now.isoformat()
        }
