"""
Agent Priority Management Service
Handles task prioritization, queue management, and priority escalation
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from src.models.task import Task, TaskStatus, TaskPriority
from src.models.agent_execution import AgentExecution, ExecutionStatus
from src.models.agent import Agent, AgentStatus
from src.core.logging import logger


class PriorityLevel:
    """Priority level constants with numeric weights"""
    CRITICAL = "critical"  # Weight: 4
    HIGH = "high"          # Weight: 3
    NORMAL = "normal"      # Weight: 2
    LOW = "low"            # Weight: 1

    @staticmethod
    def get_weight(priority: str) -> int:
        """Get numeric weight for priority level"""
        weights = {
            PriorityLevel.CRITICAL: 4,
            PriorityLevel.HIGH: 3,
            PriorityLevel.NORMAL: 2,
            PriorityLevel.LOW: 1
        }
        return weights.get(priority, 2)


class EscalationPolicy:
    """Priority escalation policies"""
    AGGRESSIVE = "aggressive"    # Escalate every 30 minutes
    MODERATE = "moderate"        # Escalate every 2 hours
    CONSERVATIVE = "conservative"  # Escalate every 6 hours
    NONE = "none"               # No automatic escalation


class AgentPriority:
    """
    Agent Priority Management Service

    Manages task priorities, queue ordering, priority escalation,
    and SLA tracking.
    """

    @staticmethod
    def set_task_priority(
        session: Session,
        task_id: int,
        priority: str,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Set or update task priority.

        Args:
            session: Database session
            task_id: Task ID
            priority: Priority level (critical, high, normal, low)
            reason: Optional reason for priority change

        Returns:
            Updated task information
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        old_priority = task.priority.value if task.priority else None

        # Convert string to enum
        try:
            priority_enum = TaskPriority(priority)
        except ValueError:
            raise ValueError(f"Invalid priority '{priority}'. Valid: critical, high, normal, low")

        task.priority = priority_enum
        task.updated_at = datetime.utcnow()

        # Log priority change in metadata
        if not task.metadata:
            task.metadata = {}

        if "priority_history" not in task.metadata:
            task.metadata["priority_history"] = []

        task.metadata["priority_history"].append({
            "from": old_priority,
            "to": priority,
            "changed_at": datetime.utcnow().isoformat(),
            "reason": reason
        })

        session.commit()

        logger.info(f"Task {task_id} priority changed from {old_priority} to {priority}")

        return {
            "task_id": task_id,
            "old_priority": old_priority,
            "new_priority": priority,
            "reason": reason,
            "changed_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_priority_queue(
        session: Session,
        agent_id: Optional[int] = None,
        status: Optional[ExecutionStatus] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get tasks ordered by priority.

        Args:
            session: Database session
            agent_id: Optional agent ID filter
            status: Optional execution status filter
            limit: Maximum tasks to return

        Returns:
            List of tasks ordered by priority
        """
        query = session.query(AgentExecution).join(Task)

        if agent_id:
            query = query.filter(AgentExecution.agent_id == agent_id)

        if status:
            query = query.filter(AgentExecution.status == status)

        # Order by priority weight (critical first) then creation time
        executions = query.order_by(
            Task.priority.desc(),
            AgentExecution.created_at.asc()
        ).limit(limit).all()

        result = []
        for execution in executions:
            task = execution.task
            result.append({
                "execution_id": execution.id,
                "task_id": task.id,
                "task_title": task.title,
                "priority": task.priority.value,
                "priority_weight": PriorityLevel.get_weight(task.priority.value),
                "status": execution.status.value,
                "agent_id": execution.agent_id,
                "created_at": execution.created_at.isoformat(),
                "age_minutes": (datetime.utcnow() - execution.created_at).total_seconds() / 60
            })

        return result

    @staticmethod
    def calculate_dynamic_priority(
        task: Task,
        age_minutes: float,
        base_priority: str
    ) -> int:
        """
        Calculate dynamic priority score considering age and base priority.

        Args:
            task: Task object
            age_minutes: Task age in minutes
            base_priority: Base priority level

        Returns:
            Dynamic priority score (higher = more urgent)
        """
        base_weight = PriorityLevel.get_weight(base_priority)

        # Age factor: increase priority as task ages
        # Every 30 minutes adds 0.1 to the weight
        age_factor = (age_minutes / 30) * 0.1

        # SLA factor: if task has SLA in metadata, increase urgency as deadline approaches
        sla_factor = 0.0
        if task.metadata and "sla_minutes" in task.metadata:
            sla_minutes = task.metadata["sla_minutes"]
            remaining = sla_minutes - age_minutes
            if remaining <= 0:
                sla_factor = 2.0  # SLA breached - critical
            elif remaining <= sla_minutes * 0.25:
                sla_factor = 1.0  # 25% time left - urgent
            elif remaining <= sla_minutes * 0.50:
                sla_factor = 0.5  # 50% time left - elevated

        # Calculate final score
        dynamic_score = (base_weight + age_factor + sla_factor) * 100

        return int(dynamic_score)

    @staticmethod
    def get_priority_queue_dynamic(
        session: Session,
        agent_id: Optional[int] = None,
        include_sla: bool = True,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get tasks ordered by dynamic priority (considering age and SLA).

        Args:
            session: Database session
            agent_id: Optional agent ID filter
            include_sla: Include SLA calculations
            limit: Maximum tasks to return

        Returns:
            List of tasks ordered by dynamic priority
        """
        query = session.query(AgentExecution).join(Task)

        if agent_id:
            query = query.filter(AgentExecution.agent_id == agent_id)

        # Only queued or pending executions
        query = query.filter(
            AgentExecution.status.in_([ExecutionStatus.QUEUED, ExecutionStatus.PENDING])
        )

        executions = query.all()

        result = []
        for execution in executions:
            task = execution.task
            age_minutes = (datetime.utcnow() - execution.created_at).total_seconds() / 60

            dynamic_score = AgentPriority.calculate_dynamic_priority(
                task=task,
                age_minutes=age_minutes,
                base_priority=task.priority.value
            )

            result.append({
                "execution_id": execution.id,
                "task_id": task.id,
                "task_title": task.title,
                "base_priority": task.priority.value,
                "dynamic_score": dynamic_score,
                "age_minutes": age_minutes,
                "status": execution.status.value,
                "agent_id": execution.agent_id,
                "sla_status": AgentPriority._get_sla_status(task, age_minutes) if include_sla else None
            })

        # Sort by dynamic score (descending)
        result.sort(key=lambda x: x["dynamic_score"], reverse=True)

        return result[:limit]

    @staticmethod
    def _get_sla_status(task: Task, age_minutes: float) -> Optional[Dict[str, Any]]:
        """Get SLA status for a task"""
        if not task.metadata or "sla_minutes" not in task.metadata:
            return None

        sla_minutes = task.metadata["sla_minutes"]
        remaining = sla_minutes - age_minutes

        return {
            "sla_minutes": sla_minutes,
            "age_minutes": age_minutes,
            "remaining_minutes": max(0, remaining),
            "breached": remaining <= 0,
            "at_risk": 0 < remaining <= sla_minutes * 0.25,
            "percentage_used": (age_minutes / sla_minutes * 100) if sla_minutes > 0 else 0
        }

    @staticmethod
    def escalate_priorities(
        session: Session,
        policy: str = EscalationPolicy.MODERATE,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Escalate priorities for aging tasks.

        Args:
            session: Database session
            policy: Escalation policy (aggressive, moderate, conservative)
            dry_run: If True, only return what would be escalated

        Returns:
            Escalation results
        """
        # Define age thresholds based on policy
        thresholds = {
            EscalationPolicy.AGGRESSIVE: {"low": 30, "normal": 30, "high": 30},
            EscalationPolicy.MODERATE: {"low": 120, "normal": 120, "high": 60},
            EscalationPolicy.CONSERVATIVE: {"low": 360, "normal": 360, "high": 180}
        }

        if policy not in thresholds:
            raise ValueError(f"Invalid policy '{policy}'")

        policy_thresholds = thresholds[policy]
        now = datetime.utcnow()

        # Find tasks eligible for escalation
        escalations = []

        for current_priority in [PriorityLevel.LOW, PriorityLevel.NORMAL, PriorityLevel.HIGH]:
            threshold_minutes = policy_thresholds[current_priority]
            time_threshold = now - timedelta(minutes=threshold_minutes)

            # Query tasks with current priority that are old enough
            query = session.query(Task).join(AgentExecution).filter(
                and_(
                    Task.priority == TaskPriority(current_priority),
                    AgentExecution.status.in_([ExecutionStatus.QUEUED, ExecutionStatus.PENDING]),
                    AgentExecution.created_at <= time_threshold
                )
            )

            tasks = query.all()

            for task in tasks:
                # Determine new priority
                if current_priority == PriorityLevel.LOW:
                    new_priority = PriorityLevel.NORMAL
                elif current_priority == PriorityLevel.NORMAL:
                    new_priority = PriorityLevel.HIGH
                elif current_priority == PriorityLevel.HIGH:
                    new_priority = PriorityLevel.CRITICAL

                escalations.append({
                    "task_id": task.id,
                    "task_title": task.title,
                    "from_priority": current_priority,
                    "to_priority": new_priority,
                    "age_minutes": (now - task.created_at).total_seconds() / 60
                })

                # Apply escalation if not dry run
                if not dry_run:
                    AgentPriority.set_task_priority(
                        session=session,
                        task_id=task.id,
                        priority=new_priority,
                        reason=f"Auto-escalated by {policy} policy after {threshold_minutes} minutes"
                    )

        return {
            "policy": policy,
            "dry_run": dry_run,
            "escalated_count": len(escalations),
            "escalations": escalations,
            "timestamp": now.isoformat()
        }

    @staticmethod
    def get_priority_statistics(
        session: Session,
        time_range_hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get priority statistics and metrics.

        Args:
            session: Database session
            time_range_hours: Time range for statistics

        Returns:
            Priority statistics
        """
        time_threshold = datetime.utcnow() - timedelta(hours=time_range_hours)

        # Count tasks by priority
        priority_counts = {}
        for priority in [PriorityLevel.CRITICAL, PriorityLevel.HIGH, PriorityLevel.NORMAL, PriorityLevel.LOW]:
            count = session.query(Task).filter(
                and_(
                    Task.priority == TaskPriority(priority),
                    Task.created_at >= time_threshold
                )
            ).count()
            priority_counts[priority] = count

        # Average completion time by priority
        completion_times = {}
        for priority in [PriorityLevel.CRITICAL, PriorityLevel.HIGH, PriorityLevel.NORMAL, PriorityLevel.LOW]:
            executions = session.query(AgentExecution).join(Task).filter(
                and_(
                    Task.priority == TaskPriority(priority),
                    AgentExecution.status == ExecutionStatus.COMPLETED,
                    AgentExecution.created_at >= time_threshold,
                    AgentExecution.completed_at.isnot(None)
                )
            ).all()

            if executions:
                total_time = sum(
                    (e.completed_at - e.created_at).total_seconds()
                    for e in executions
                )
                avg_time = total_time / len(executions)
                completion_times[priority] = {
                    "average_seconds": avg_time,
                    "sample_size": len(executions)
                }
            else:
                completion_times[priority] = {
                    "average_seconds": 0,
                    "sample_size": 0
                }

        # Count currently queued by priority
        queued_counts = {}
        for priority in [PriorityLevel.CRITICAL, PriorityLevel.HIGH, PriorityLevel.NORMAL, PriorityLevel.LOW]:
            count = session.query(AgentExecution).join(Task).filter(
                and_(
                    Task.priority == TaskPriority(priority),
                    AgentExecution.status == ExecutionStatus.QUEUED
                )
            ).count()
            queued_counts[priority] = count

        # SLA breach analysis
        sla_breaches = 0
        sla_at_risk = 0
        tasks_with_sla = session.query(Task).filter(
            Task.metadata.isnot(None),
            Task.created_at >= time_threshold
        ).all()

        for task in tasks_with_sla:
            if task.metadata and "sla_minutes" in task.metadata:
                age_minutes = (datetime.utcnow() - task.created_at).total_seconds() / 60
                sla_minutes = task.metadata["sla_minutes"]

                if age_minutes > sla_minutes:
                    sla_breaches += 1
                elif age_minutes > sla_minutes * 0.75:
                    sla_at_risk += 1

        return {
            "time_range_hours": time_range_hours,
            "priority_distribution": priority_counts,
            "completion_times": completion_times,
            "currently_queued": queued_counts,
            "sla_metrics": {
                "breaches": sla_breaches,
                "at_risk": sla_at_risk,
                "total_with_sla": len([t for t in tasks_with_sla if t.metadata and "sla_minutes" in t.metadata])
            },
            "total_tasks": sum(priority_counts.values()),
            "timestamp": datetime.utcnow().isoformat()
        }

    @staticmethod
    def set_task_sla(
        session: Session,
        task_id: int,
        sla_minutes: int,
        auto_escalate: bool = True
    ) -> Dict[str, Any]:
        """
        Set SLA for a task.

        Args:
            session: Database session
            task_id: Task ID
            sla_minutes: SLA in minutes
            auto_escalate: Automatically escalate if SLA at risk

        Returns:
            SLA configuration
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if not task.metadata:
            task.metadata = {}

        task.metadata["sla_minutes"] = sla_minutes
        task.metadata["sla_set_at"] = datetime.utcnow().isoformat()
        task.metadata["auto_escalate_on_sla"] = auto_escalate

        session.commit()

        logger.info(f"SLA set for task {task_id}: {sla_minutes} minutes")

        return {
            "task_id": task_id,
            "sla_minutes": sla_minutes,
            "deadline": (datetime.utcnow() + timedelta(minutes=sla_minutes)).isoformat(),
            "auto_escalate": auto_escalate
        }

    @staticmethod
    def check_sla_violations(
        session: Session
    ) -> Dict[str, Any]:
        """
        Check for SLA violations and at-risk tasks.

        Returns:
            SLA violation report
        """
        tasks = session.query(Task).filter(
            Task.metadata.isnot(None),
            Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS])
        ).all()

        violations = []
        at_risk = []

        for task in tasks:
            if not task.metadata or "sla_minutes" not in task.metadata:
                continue

            age_minutes = (datetime.utcnow() - task.created_at).total_seconds() / 60
            sla_minutes = task.metadata["sla_minutes"]
            remaining = sla_minutes - age_minutes

            task_info = {
                "task_id": task.id,
                "task_title": task.title,
                "priority": task.priority.value,
                "sla_minutes": sla_minutes,
                "age_minutes": age_minutes,
                "remaining_minutes": remaining
            }

            if remaining <= 0:
                violations.append({
                    **task_info,
                    "breached_by_minutes": abs(remaining)
                })
            elif remaining <= sla_minutes * 0.25:
                at_risk.append({
                    **task_info,
                    "percentage_remaining": (remaining / sla_minutes) * 100
                })

        return {
            "violations": violations,
            "violations_count": len(violations),
            "at_risk": at_risk,
            "at_risk_count": len(at_risk),
            "total_checked": len([t for t in tasks if t.metadata and "sla_minutes" in t.metadata]),
            "timestamp": datetime.utcnow().isoformat()
        }

    @staticmethod
    def reorder_agent_queue(
        session: Session,
        agent_id: int,
        use_dynamic_priority: bool = True
    ) -> Dict[str, Any]:
        """
        Reorder agent's queue based on priority.

        Args:
            session: Database session
            agent_id: Agent ID
            use_dynamic_priority: Use dynamic priority vs static

        Returns:
            Reordered queue information
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if use_dynamic_priority:
            queue = AgentPriority.get_priority_queue_dynamic(
                session=session,
                agent_id=agent_id,
                include_sla=True
            )
        else:
            queue = AgentPriority.get_priority_queue(
                session=session,
                agent_id=agent_id,
                status=ExecutionStatus.QUEUED
            )

        # Update queue order in database (if we add a queue_order field)
        # For now, just return the ordered list

        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "queue_length": len(queue),
            "use_dynamic_priority": use_dynamic_priority,
            "queue": queue,
            "reordered_at": datetime.utcnow().isoformat()
        }
