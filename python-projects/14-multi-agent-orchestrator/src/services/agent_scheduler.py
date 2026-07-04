"""
Agent Scheduler and Load Balancer Service
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import and_

from src.models.agent import Agent, AgentRole, AgentStatus
from src.models.task import Task
from src.models.agent_execution import AgentExecution, ExecutionStatus
from src.services.orchestration_service import AgentOrchestrationService
from src.core.logging import logger


class SchedulingStrategy:
    """Scheduling strategy types"""
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    CAPABILITY_BASED = "capability_based"
    PERFORMANCE_BASED = "performance_based"
    RANDOM = "random"
    PRIORITY_QUEUE = "priority_queue"


class AgentScheduler:
    """
    Service for scheduling tasks to agents using various load balancing strategies.

    Provides:
    - Multiple scheduling strategies
    - Load-aware task assignment
    - Capability matching
    - Performance-based scheduling
    - Queue management
    """

    # Class-level counter for round-robin
    _round_robin_counter = 0

    @staticmethod
    def schedule_task(
        session: Session,
        task_id: int,
        strategy: str = SchedulingStrategy.LEAST_LOADED,
        required_capabilities: Optional[List[str]] = None,
        preferred_role: Optional[AgentRole] = None
    ) -> Optional[Agent]:
        """
        Schedule a task to an appropriate agent.

        Args:
            session: Database session
            task_id: Task ID to schedule
            strategy: Scheduling strategy to use
            required_capabilities: Required agent capabilities
            preferred_role: Preferred agent role

        Returns:
            Selected agent or None if no suitable agent found
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # Get available agents
        available_agents = AgentScheduler._get_available_agents(
            session=session,
            required_capabilities=required_capabilities,
            preferred_role=preferred_role
        )

        if not available_agents:
            logger.warning(f"No available agents for task {task_id}")
            return None

        # Select agent based on strategy
        if strategy == SchedulingStrategy.ROUND_ROBIN:
            agent = AgentScheduler._round_robin_schedule(available_agents)
        elif strategy == SchedulingStrategy.LEAST_LOADED:
            agent = AgentScheduler._least_loaded_schedule(session, available_agents)
        elif strategy == SchedulingStrategy.CAPABILITY_BASED:
            agent = AgentScheduler._capability_based_schedule(
                available_agents,
                required_capabilities or []
            )
        elif strategy == SchedulingStrategy.PERFORMANCE_BASED:
            agent = AgentScheduler._performance_based_schedule(available_agents)
        elif strategy == SchedulingStrategy.RANDOM:
            agent = AgentScheduler._random_schedule(available_agents)
        else:
            # Default to least loaded
            agent = AgentScheduler._least_loaded_schedule(session, available_agents)

        if agent:
            logger.info(
                f"Scheduled task {task_id} to agent {agent.id} ({agent.name}) "
                f"using {strategy} strategy"
            )

        return agent

    @staticmethod
    def batch_schedule(
        session: Session,
        task_ids: List[int],
        strategy: str = SchedulingStrategy.LEAST_LOADED,
        balance_load: bool = True
    ) -> Dict[int, Optional[int]]:
        """
        Schedule multiple tasks to agents.

        Args:
            session: Database session
            task_ids: List of task IDs to schedule
            strategy: Scheduling strategy
            balance_load: Whether to balance load across agents

        Returns:
            Dictionary mapping task_id to agent_id (or None)
        """
        assignments = {}

        if balance_load and strategy == SchedulingStrategy.LEAST_LOADED:
            # For load balancing, track assignments in this batch
            agent_loads = {}

            for task_id in task_ids:
                available_agents = AgentScheduler._get_available_agents(session)

                if not available_agents:
                    assignments[task_id] = None
                    continue

                # Calculate current load including this batch
                agent_scores = []
                for agent in available_agents:
                    current_load = AgentScheduler._get_agent_load(session, agent.id)
                    batch_load = agent_loads.get(agent.id, 0)
                    total_load = current_load + batch_load

                    agent_scores.append((agent, total_load))

                # Select agent with lowest total load
                agent_scores.sort(key=lambda x: x[1])
                selected_agent = agent_scores[0][0]

                # Track assignment
                agent_loads[selected_agent.id] = agent_loads.get(selected_agent.id, 0) + 1
                assignments[task_id] = selected_agent.id

        else:
            # Schedule each task independently
            for task_id in task_ids:
                agent = AgentScheduler.schedule_task(
                    session=session,
                    task_id=task_id,
                    strategy=strategy
                )
                assignments[task_id] = agent.id if agent else None

        logger.info(
            f"Batch scheduled {len(task_ids)} tasks: "
            f"{sum(1 for a in assignments.values() if a is not None)} assigned, "
            f"{sum(1 for a in assignments.values() if a is None)} unassigned"
        )

        return assignments

    @staticmethod
    def get_load_distribution(
        session: Session
    ) -> Dict[str, Any]:
        """
        Get current load distribution across agents.

        Args:
            session: Database session

        Returns:
            Load distribution data
        """
        agents = session.query(Agent).all()

        distribution = []
        total_load = 0

        for agent in agents:
            load = AgentScheduler._get_agent_load(session, agent.id)
            total_load += load

            distribution.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "role": agent.role.value,
                "status": agent.status.value,
                "current_load": load,
                "queued_tasks": AgentScheduler._get_queued_count(session, agent.id)
            })

        # Sort by load descending
        distribution.sort(key=lambda x: x["current_load"], reverse=True)

        avg_load = total_load / len(agents) if agents else 0

        # Calculate load balance metric (coefficient of variation)
        if agents and avg_load > 0:
            loads = [d["current_load"] for d in distribution]
            variance = sum((l - avg_load) ** 2 for l in loads) / len(loads)
            std_dev = variance ** 0.5
            balance_score = 1 - (std_dev / avg_load)  # Higher is better
        else:
            balance_score = 1.0

        return {
            "total_agents": len(agents),
            "total_load": total_load,
            "average_load": avg_load,
            "balance_score": max(0, min(1, balance_score)),
            "agents": distribution
        }

    @staticmethod
    def rebalance_load(
        session: Session,
        threshold: float = 0.3
    ) -> Dict[str, Any]:
        """
        Rebalance load by moving queued tasks from overloaded to underloaded agents.

        Args:
            session: Database session
            threshold: Rebalance if load difference exceeds this factor

        Returns:
            Rebalancing result
        """
        distribution = AgentScheduler.get_load_distribution(session)

        if distribution["balance_score"] > (1 - threshold):
            logger.info("Load is already balanced, no rebalancing needed")
            return {
                "rebalanced": False,
                "reason": "Load already balanced",
                "balance_score": distribution["balance_score"]
            }

        # Find overloaded and underloaded agents
        avg_load = distribution["average_load"]
        overloaded = [
            a for a in distribution["agents"]
            if a["current_load"] > avg_load * (1 + threshold)
            and a["queued_tasks"] > 0
        ]
        underloaded = [
            a for a in distribution["agents"]
            if a["current_load"] < avg_load * (1 - threshold)
            and a["status"] == "idle"
        ]

        if not overloaded or not underloaded:
            logger.info("Cannot rebalance: no suitable source/target agents")
            return {
                "rebalanced": False,
                "reason": "No suitable agents for rebalancing"
            }

        # Move queued tasks from overloaded to underloaded agents
        moved_count = 0

        for overloaded_agent in overloaded:
            # Get queued executions
            queued = session.query(AgentExecution).filter(
                and_(
                    AgentExecution.agent_id == overloaded_agent["agent_id"],
                    AgentExecution.status == ExecutionStatus.QUEUED
                )
            ).order_by(AgentExecution.priority.desc()).all()

            for execution in queued:
                if not underloaded:
                    break

                # Move to underloaded agent
                target_agent = underloaded[0]
                execution.agent_id = target_agent["agent_id"]

                # Update target agent load
                target_agent["current_load"] += 1
                target_agent["queued_tasks"] += 1

                # Check if target is still underloaded
                if target_agent["current_load"] >= avg_load:
                    underloaded.pop(0)

                moved_count += 1

                logger.info(
                    f"Moved execution {execution.id} from agent {overloaded_agent['agent_id']} "
                    f"to agent {target_agent['agent_id']}"
                )

        session.flush()

        # Get new balance score
        new_distribution = AgentScheduler.get_load_distribution(session)

        return {
            "rebalanced": True,
            "tasks_moved": moved_count,
            "old_balance_score": distribution["balance_score"],
            "new_balance_score": new_distribution["balance_score"],
            "improvement": new_distribution["balance_score"] - distribution["balance_score"]
        }

    @staticmethod
    def _get_available_agents(
        session: Session,
        required_capabilities: Optional[List[str]] = None,
        preferred_role: Optional[AgentRole] = None
    ) -> List[Agent]:
        """Get available agents matching criteria."""
        query = session.query(Agent).filter(Agent.status == AgentStatus.IDLE)

        if preferred_role:
            query = query.filter(Agent.role == preferred_role)

        agents = query.all()

        # Filter by capabilities if specified
        if required_capabilities:
            agents = [
                agent for agent in agents
                if agent.capabilities and all(
                    cap in agent.capabilities for cap in required_capabilities
                )
            ]

        return agents

    @staticmethod
    def _get_agent_load(session: Session, agent_id: int) -> int:
        """Get current load (running + queued tasks) for an agent."""
        count = session.query(AgentExecution).filter(
            and_(
                AgentExecution.agent_id == agent_id,
                AgentExecution.status.in_([
                    ExecutionStatus.RUNNING,
                    ExecutionStatus.QUEUED,
                    ExecutionStatus.ASSIGNED
                ])
            )
        ).count()

        return count

    @staticmethod
    def _get_queued_count(session: Session, agent_id: int) -> int:
        """Get number of queued tasks for an agent."""
        count = session.query(AgentExecution).filter(
            and_(
                AgentExecution.agent_id == agent_id,
                AgentExecution.status == ExecutionStatus.QUEUED
            )
        ).count()

        return count

    @staticmethod
    def _round_robin_schedule(agents: List[Agent]) -> Agent:
        """Round-robin scheduling strategy."""
        selected = agents[AgentScheduler._round_robin_counter % len(agents)]
        AgentScheduler._round_robin_counter += 1
        return selected

    @staticmethod
    def _least_loaded_schedule(session: Session, agents: List[Agent]) -> Agent:
        """Least-loaded scheduling strategy."""
        agent_loads = [
            (agent, AgentScheduler._get_agent_load(session, agent.id))
            for agent in agents
        ]

        # Sort by load (ascending)
        agent_loads.sort(key=lambda x: x[1])

        return agent_loads[0][0]

    @staticmethod
    def _capability_based_schedule(
        agents: List[Agent],
        required_capabilities: List[str]
    ) -> Agent:
        """Capability-based scheduling strategy."""
        if not required_capabilities:
            return agents[0]

        # Score agents by capability match
        agent_scores = []
        for agent in agents:
            if not agent.capabilities:
                score = 0
            else:
                # Count matching capabilities
                matches = sum(1 for cap in required_capabilities if cap in agent.capabilities)
                # Bonus for having exactly the required capabilities
                exact_match = set(required_capabilities) == set(agent.capabilities)
                score = matches + (10 if exact_match else 0)

            agent_scores.append((agent, score))

        # Sort by score (descending)
        agent_scores.sort(key=lambda x: x[1], reverse=True)

        return agent_scores[0][0]

    @staticmethod
    def _performance_based_schedule(agents: List[Agent]) -> Agent:
        """Performance-based scheduling strategy."""
        agent_scores = []

        for agent in agents:
            # Calculate performance score
            success_rate = (
                agent.successful_tasks / (agent.successful_tasks + agent.failed_tasks)
                if (agent.successful_tasks + agent.failed_tasks) > 0
                else 0.5
            )

            # Lower response time is better
            response_time_score = (
                1 / (1 + (agent.average_response_time or 300) / 100)
                if agent.average_response_time
                else 0.5
            )

            # Combined score (weighted)
            score = (success_rate * 0.7) + (response_time_score * 0.3)

            agent_scores.append((agent, score))

        # Sort by score (descending)
        agent_scores.sort(key=lambda x: x[1], reverse=True)

        return agent_scores[0][0]

    @staticmethod
    def _random_schedule(agents: List[Agent]) -> Agent:
        """Random scheduling strategy."""
        import random
        return random.choice(agents)
