"""
Agent Lifecycle Management Service
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from src.models.agent import Agent, AgentStatus
from src.models.agent_execution import AgentExecution, ExecutionStatus
from src.core.logging import logger


class AgentLifecycleEvent:
    """Lifecycle event types"""
    REGISTERED = "registered"
    STARTED = "started"
    STOPPED = "stopped"
    PAUSED = "paused"
    RESUMED = "resumed"
    HEALTH_CHECK_PASSED = "health_check_passed"
    HEALTH_CHECK_FAILED = "health_check_failed"
    HEARTBEAT_MISSED = "heartbeat_missed"
    CRASHED = "crashed"
    RECOVERED = "recovered"
    DEREGISTERED = "deregistered"


class AgentLifecycle:
    """
    Service for managing agent lifecycle, health monitoring, and state transitions.

    Handles:
    - Agent registration and deregistration
    - Health checks and heartbeat monitoring
    - Lifecycle state transitions
    - Event logging
    - Automatic recovery
    """

    @staticmethod
    def register_agent(
        session: Session,
        name: str,
        role: str,
        capabilities: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Agent:
        """
        Register a new agent in the system.

        Args:
            session: Database session
            name: Agent name
            role: Agent role
            capabilities: List of agent capabilities
            config: Agent configuration
            metadata: Additional metadata

        Returns:
            Registered agent
        """
        from src.models.agent import AgentRole

        # Check if agent with same name exists
        existing = session.query(Agent).filter(Agent.name == name).first()
        if existing:
            raise ValueError(f"Agent with name '{name}' already exists")

        # Create new agent
        agent = Agent(
            name=name,
            role=AgentRole(role),
            status=AgentStatus.IDLE,
            capabilities=capabilities or [],
            config=config or {},
            metadata=metadata or {}
        )

        session.add(agent)
        session.flush()

        # Log lifecycle event
        AgentLifecycle._log_event(
            session=session,
            agent_id=agent.id,
            event_type=AgentLifecycleEvent.REGISTERED,
            details={"name": name, "role": role}
        )

        logger.info(f"Agent registered: {name} (ID: {agent.id}, role: {role})")

        return agent

    @staticmethod
    def deregister_agent(
        session: Session,
        agent_id: int,
        reason: Optional[str] = None
    ) -> bool:
        """
        Deregister an agent from the system.

        Args:
            session: Database session
            agent_id: Agent ID
            reason: Deregistration reason

        Returns:
            True if deregistered, False if not found
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            return False

        # Cancel running executions
        running_executions = session.query(AgentExecution).filter(
            and_(
                AgentExecution.agent_id == agent_id,
                AgentExecution.status == ExecutionStatus.RUNNING
            )
        ).all()

        for execution in running_executions:
            execution.status = ExecutionStatus.CANCELLED
            execution.completed_at = datetime.utcnow()
            execution.error_message = f"Agent deregistered: {reason or 'No reason provided'}"

        # Log lifecycle event
        AgentLifecycle._log_event(
            session=session,
            agent_id=agent_id,
            event_type=AgentLifecycleEvent.DEREGISTERED,
            details={"reason": reason, "cancelled_executions": len(running_executions)}
        )

        # Delete agent
        session.delete(agent)
        session.flush()

        logger.info(f"Agent deregistered: {agent.name} (ID: {agent_id})")

        return True

    @staticmethod
    def start_agent(
        session: Session,
        agent_id: int
    ) -> Agent:
        """
        Start an agent (set to IDLE status).

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Updated agent
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if agent.status == AgentStatus.IDLE:
            return agent

        agent.status = AgentStatus.IDLE
        agent.last_active = datetime.utcnow()

        AgentLifecycle._log_event(
            session=session,
            agent_id=agent_id,
            event_type=AgentLifecycleEvent.STARTED
        )

        session.flush()

        logger.info(f"Agent started: {agent.name} (ID: {agent_id})")

        return agent

    @staticmethod
    def stop_agent(
        session: Session,
        agent_id: int,
        reason: Optional[str] = None
    ) -> Agent:
        """
        Stop an agent (set to OFFLINE status).

        Args:
            session: Database session
            agent_id: Agent ID
            reason: Stop reason

        Returns:
            Updated agent
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Cancel current task if any
        if agent.current_task_id:
            executions = session.query(AgentExecution).filter(
                and_(
                    AgentExecution.agent_id == agent_id,
                    AgentExecution.task_id == agent.current_task_id,
                    AgentExecution.status == ExecutionStatus.RUNNING
                )
            ).all()

            for execution in executions:
                execution.status = ExecutionStatus.CANCELLED
                execution.completed_at = datetime.utcnow()
                execution.error_message = f"Agent stopped: {reason or 'Manual stop'}"

        agent.status = AgentStatus.OFFLINE
        agent.current_task_id = None

        AgentLifecycle._log_event(
            session=session,
            agent_id=agent_id,
            event_type=AgentLifecycleEvent.STOPPED,
            details={"reason": reason}
        )

        session.flush()

        logger.info(f"Agent stopped: {agent.name} (ID: {agent_id})")

        return agent

    @staticmethod
    def pause_agent(
        session: Session,
        agent_id: int,
        reason: Optional[str] = None
    ) -> Agent:
        """
        Pause an agent temporarily.

        Args:
            session: Database session
            agent_id: Agent ID
            reason: Pause reason

        Returns:
            Updated agent
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Pause current execution if any
        if agent.current_task_id:
            from src.services.execution_manager import ExecutionManager

            executions = session.query(AgentExecution).filter(
                and_(
                    AgentExecution.agent_id == agent_id,
                    AgentExecution.task_id == agent.current_task_id,
                    AgentExecution.status == ExecutionStatus.RUNNING
                )
            ).all()

            for execution in executions:
                ExecutionManager.pause_execution(
                    session=session,
                    execution_id=execution.id,
                    reason=f"Agent paused: {reason or 'Manual pause'}"
                )

        agent.status = AgentStatus.OFFLINE

        AgentLifecycle._log_event(
            session=session,
            agent_id=agent_id,
            event_type=AgentLifecycleEvent.PAUSED,
            details={"reason": reason}
        )

        session.flush()

        logger.info(f"Agent paused: {agent.name} (ID: {agent_id})")

        return agent

    @staticmethod
    def resume_agent(
        session: Session,
        agent_id: int
    ) -> Agent:
        """
        Resume a paused agent.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Updated agent
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        agent.status = AgentStatus.IDLE
        agent.last_active = datetime.utcnow()

        AgentLifecycle._log_event(
            session=session,
            agent_id=agent_id,
            event_type=AgentLifecycleEvent.RESUMED
        )

        session.flush()

        logger.info(f"Agent resumed: {agent.name} (ID: {agent_id})")

        return agent

    @staticmethod
    def heartbeat(
        session: Session,
        agent_id: int,
        status: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None
    ) -> Agent:
        """
        Update agent heartbeat.

        Args:
            session: Database session
            agent_id: Agent ID
            status: Optional status update
            metrics: Optional metrics data

        Returns:
            Updated agent
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        agent.last_active = datetime.utcnow()

        if status:
            from src.models.agent import AgentStatus as AS
            agent.status = AS(status)

        if metrics:
            # Update agent metadata with latest metrics
            if not agent.metadata:
                agent.metadata = {}
            agent.metadata["last_heartbeat_metrics"] = metrics
            agent.metadata["last_heartbeat_time"] = datetime.utcnow().isoformat()

        session.flush()

        return agent

    @staticmethod
    def health_check(
        session: Session,
        agent_id: int
    ) -> Dict[str, Any]:
        """
        Perform health check on an agent.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Health check result
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Calculate health metrics
        now = datetime.utcnow()
        last_active_delta = (now - agent.last_active).total_seconds() if agent.last_active else None

        # Health criteria
        is_healthy = True
        issues = []

        # Check 1: Last active within threshold (5 minutes)
        if last_active_delta is None or last_active_delta > 300:
            is_healthy = False
            issues.append(f"No activity for {last_active_delta or 'unknown'} seconds")

        # Check 2: Status is valid
        if agent.status == AgentStatus.OFFLINE:
            is_healthy = False
            issues.append("Agent is offline")

        # Check 3: Not stuck on a task
        if agent.current_task_id and agent.status == AgentStatus.BUSY:
            # Check if execution is stuck
            from src.services.execution_manager import ExecutionManager
            stuck = ExecutionManager.get_stuck_executions(session, timeout_hours=1)
            stuck_agent = [e for e in stuck if e.agent_id == agent_id]
            if stuck_agent:
                is_healthy = False
                issues.append(f"Stuck on task {agent.current_task_id}")

        # Log health check event
        event_type = AgentLifecycleEvent.HEALTH_CHECK_PASSED if is_healthy else AgentLifecycleEvent.HEALTH_CHECK_FAILED
        AgentLifecycle._log_event(
            session=session,
            agent_id=agent_id,
            event_type=event_type,
            details={"is_healthy": is_healthy, "issues": issues}
        )

        session.flush()

        result = {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "is_healthy": is_healthy,
            "status": agent.status.value,
            "last_active": agent.last_active.isoformat() if agent.last_active else None,
            "last_active_seconds_ago": last_active_delta,
            "current_task_id": agent.current_task_id,
            "issues": issues,
            "checked_at": now.isoformat()
        }

        return result

    @staticmethod
    def check_all_agents_health(
        session: Session
    ) -> Dict[str, Any]:
        """
        Check health of all agents.

        Args:
            session: Database session

        Returns:
            Health check summary
        """
        agents = session.query(Agent).all()

        results = []
        healthy_count = 0
        unhealthy_count = 0

        for agent in agents:
            try:
                health = AgentLifecycle.health_check(session, agent.id)
                results.append(health)

                if health["is_healthy"]:
                    healthy_count += 1
                else:
                    unhealthy_count += 1
            except Exception as e:
                logger.error(f"Health check failed for agent {agent.id}: {e}")
                unhealthy_count += 1
                results.append({
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "is_healthy": False,
                    "issues": [f"Health check error: {str(e)}"]
                })

        return {
            "total_agents": len(agents),
            "healthy": healthy_count,
            "unhealthy": unhealthy_count,
            "health_rate": healthy_count / len(agents) if agents else 0,
            "agents": results,
            "checked_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_inactive_agents(
        session: Session,
        inactive_threshold_minutes: int = 5
    ) -> List[Agent]:
        """
        Get agents that haven't been active recently.

        Args:
            session: Database session
            inactive_threshold_minutes: Inactivity threshold

        Returns:
            List of inactive agents
        """
        threshold = datetime.utcnow() - timedelta(minutes=inactive_threshold_minutes)

        agents = session.query(Agent).filter(
            or_(
                Agent.last_active < threshold,
                Agent.last_active.is_(None)
            )
        ).all()

        return agents

    @staticmethod
    def recover_agent(
        session: Session,
        agent_id: int
    ) -> Agent:
        """
        Attempt to recover an unhealthy agent.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Recovered agent
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Cancel stuck executions
        from src.services.execution_manager import ExecutionManager
        stuck = ExecutionManager.get_stuck_executions(session, timeout_hours=1)
        stuck_agent_executions = [e for e in stuck if e.agent_id == agent_id]

        for execution in stuck_agent_executions:
            ExecutionManager.fail_execution(
                session=session,
                execution_id=execution.id,
                error="Agent recovery - execution was stuck",
                retry=True
            )

        # Reset agent state
        agent.status = AgentStatus.IDLE
        agent.current_task_id = None
        agent.last_active = datetime.utcnow()

        AgentLifecycle._log_event(
            session=session,
            agent_id=agent_id,
            event_type=AgentLifecycleEvent.RECOVERED,
            details={"stuck_executions_cancelled": len(stuck_agent_executions)}
        )

        session.flush()

        logger.info(f"Agent recovered: {agent.name} (ID: {agent_id})")

        return agent

    @staticmethod
    def _log_event(
        session: Session,
        agent_id: int,
        event_type: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """
        Log a lifecycle event.

        Args:
            session: Database session
            agent_id: Agent ID
            event_type: Event type
            details: Event details
        """
        # Store in agent metadata for now
        # In production, you might want a separate lifecycle_events table
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if agent:
            if not agent.metadata:
                agent.metadata = {}

            if "lifecycle_events" not in agent.metadata:
                agent.metadata["lifecycle_events"] = []

            # Keep last 100 events
            events = agent.metadata["lifecycle_events"]
            if len(events) >= 100:
                events = events[-99:]

            events.append({
                "event_type": event_type,
                "timestamp": datetime.utcnow().isoformat(),
                "details": details or {}
            })

            agent.metadata["lifecycle_events"] = events
            session.flush()

    @staticmethod
    def get_lifecycle_events(
        session: Session,
        agent_id: int,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get lifecycle events for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            limit: Maximum events to return

        Returns:
            List of lifecycle events
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if not agent.metadata or "lifecycle_events" not in agent.metadata:
            return []

        events = agent.metadata["lifecycle_events"]
        return events[-limit:] if len(events) > limit else events
