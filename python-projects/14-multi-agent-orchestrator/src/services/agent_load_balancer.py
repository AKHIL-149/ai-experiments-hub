"""
Agent Load Balancing Service
Handles intelligent task distribution across agents using various load balancing strategies
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
import random

from src.models.agent import Agent, AgentStatus
from src.models.task import Task, TaskStatus
from src.models.agent_execution import AgentExecution, ExecutionStatus
from src.services.agent_resource import AgentResource
from src.core.logging import logger


class LoadBalancingStrategy:
    """Load balancing strategy constants"""
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    WEIGHTED = "weighted"
    RANDOM = "random"
    CAPABILITY_BASED = "capability_based"
    PERFORMANCE_BASED = "performance_based"


class AgentLoadBalancer:
    """
    Agent Load Balancing Service

    Intelligently distributes tasks across agents using various strategies.
    """

    def __init__(self):
        self._round_robin_index = {}

    @staticmethod
    def select_agent(
        session: Session,
        task_id: int,
        strategy: str = LoadBalancingStrategy.LEAST_LOADED,
        required_role: Optional[str] = None,
        required_capabilities: Optional[List[str]] = None,
        required_resources: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Select the best agent for a task using the specified strategy.

        Args:
            session: Database session
            task_id: Task ID
            strategy: Load balancing strategy
            required_role: Optional required agent role
            required_capabilities: Optional required capabilities
            required_resources: Optional required resources

        Returns:
            Selected agent information
        """
        task = session.query(Task).filter(Task.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        # Get available agents
        available_agents = AgentLoadBalancer._get_available_agents(
            session=session,
            required_role=required_role,
            required_capabilities=required_capabilities,
            required_resources=required_resources
        )

        if not available_agents:
            raise ValueError("No available agents matching requirements")

        # Select agent based on strategy
        if strategy == LoadBalancingStrategy.ROUND_ROBIN:
            selected = AgentLoadBalancer._round_robin_select(available_agents)
        elif strategy == LoadBalancingStrategy.LEAST_LOADED:
            selected = AgentLoadBalancer._least_loaded_select(session, available_agents)
        elif strategy == LoadBalancingStrategy.WEIGHTED:
            selected = AgentLoadBalancer._weighted_select(session, available_agents)
        elif strategy == LoadBalancingStrategy.RANDOM:
            selected = AgentLoadBalancer._random_select(available_agents)
        elif strategy == LoadBalancingStrategy.CAPABILITY_BASED:
            selected = AgentLoadBalancer._capability_select(session, available_agents, required_capabilities or [])
        elif strategy == LoadBalancingStrategy.PERFORMANCE_BASED:
            selected = AgentLoadBalancer._performance_select(session, available_agents)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")

        logger.info(f"Selected agent {selected['agent_id']} for task {task_id} using {strategy} strategy")

        return selected

    @staticmethod
    def _get_available_agents(
        session: Session,
        required_role: Optional[str] = None,
        required_capabilities: Optional[List[str]] = None,
        required_resources: Optional[Dict[str, float]] = None
    ) -> List[Agent]:
        """Get list of available agents matching requirements."""
        query = session.query(Agent).filter(
            Agent.status.in_([AgentStatus.ACTIVE, AgentStatus.IDLE])
        )

        if required_role:
            query = query.filter(Agent.role == required_role)

        agents = query.all()

        # Filter by capabilities if required
        if required_capabilities:
            agents = [
                agent for agent in agents
                if agent.metadata and "capabilities" in agent.metadata
                and all(cap in agent.metadata["capabilities"] for cap in required_capabilities)
            ]

        # Filter by resource availability if required
        if required_resources:
            filtered_agents = []
            for agent in agents:
                availability = AgentResource.check_resource_availability(
                    session=session,
                    agent_id=agent.id,
                    required_cpu=required_resources.get("cpu", 0),
                    required_memory=required_resources.get("memory", 0),
                    required_gpu=required_resources.get("gpu", 0),
                    required_disk=required_resources.get("disk", 0),
                    required_network=required_resources.get("network", 0)
                )
                if availability["sufficient"]:
                    filtered_agents.append(agent)
            agents = filtered_agents

        return agents

    @staticmethod
    def _round_robin_select(agents: List[Agent]) -> Dict[str, Any]:
        """Select agent using round-robin strategy."""
        if not hasattr(AgentLoadBalancer, '_rr_counter'):
            AgentLoadBalancer._rr_counter = 0

        selected_agent = agents[AgentLoadBalancer._rr_counter % len(agents)]
        AgentLoadBalancer._rr_counter += 1

        return {
            "agent_id": selected_agent.id,
            "agent_name": selected_agent.name,
            "agent_role": selected_agent.role.value,
            "selection_reason": "round_robin"
        }

    @staticmethod
    def _least_loaded_select(session: Session, agents: List[Agent]) -> Dict[str, Any]:
        """Select agent with least current load."""
        agent_loads = []

        for agent in agents:
            # Count running executions
            running_count = session.query(AgentExecution).filter(
                and_(
                    AgentExecution.agent_id == agent.id,
                    AgentExecution.status == ExecutionStatus.RUNNING
                )
            ).count()

            # Get resource utilization
            usage_info = AgentResource.get_resource_usage(session, agent.id)
            avg_utilization = sum(usage_info["utilization_percentage"].values()) / len(usage_info["utilization_percentage"])

            # Combined load score (lower is better)
            load_score = running_count * 10 + avg_utilization

            agent_loads.append({
                "agent": agent,
                "load_score": load_score,
                "running_tasks": running_count,
                "utilization": avg_utilization
            })

        # Select agent with lowest load
        selected = min(agent_loads, key=lambda x: x["load_score"])

        return {
            "agent_id": selected["agent"].id,
            "agent_name": selected["agent"].name,
            "agent_role": selected["agent"].role.value,
            "selection_reason": "least_loaded",
            "load_score": selected["load_score"],
            "running_tasks": selected["running_tasks"],
            "utilization_percentage": selected["utilization"]
        }

    @staticmethod
    def _weighted_select(session: Session, agents: List[Agent]) -> Dict[str, Any]:
        """Select agent using weighted random selection based on capacity."""
        agent_weights = []

        for agent in agents:
            # Get resource limits as capacity indicator
            limits = AgentResource.get_resource_limits(session, agent.id)
            usage_info = AgentResource.get_resource_usage(session, agent.id)

            # Calculate available capacity (higher is better)
            total_capacity = limits.get("cpu", 0) + limits.get("memory", 0)
            avg_utilization = sum(usage_info["utilization_percentage"].values()) / len(usage_info["utilization_percentage"])
            available_capacity = total_capacity * (100 - avg_utilization) / 100

            weight = max(available_capacity, 1)  # Ensure positive weight

            agent_weights.append({
                "agent": agent,
                "weight": weight,
                "capacity": total_capacity,
                "utilization": avg_utilization
            })

        # Weighted random selection
        total_weight = sum(aw["weight"] for aw in agent_weights)
        rand_value = random.uniform(0, total_weight)

        cumulative = 0
        selected = agent_weights[0]
        for aw in agent_weights:
            cumulative += aw["weight"]
            if rand_value <= cumulative:
                selected = aw
                break

        return {
            "agent_id": selected["agent"].id,
            "agent_name": selected["agent"].name,
            "agent_role": selected["agent"].role.value,
            "selection_reason": "weighted",
            "weight": selected["weight"],
            "capacity": selected["capacity"],
            "utilization_percentage": selected["utilization"]
        }

    @staticmethod
    def _random_select(agents: List[Agent]) -> Dict[str, Any]:
        """Select random agent."""
        selected_agent = random.choice(agents)

        return {
            "agent_id": selected_agent.id,
            "agent_name": selected_agent.name,
            "agent_role": selected_agent.role.value,
            "selection_reason": "random"
        }

    @staticmethod
    def _capability_select(session: Session, agents: List[Agent], required_capabilities: List[str]) -> Dict[str, Any]:
        """Select agent with best capability match."""
        agent_scores = []

        for agent in agents:
            if not agent.metadata or "capabilities" not in agent.metadata:
                continue

            agent_capabilities = agent.metadata["capabilities"]

            # Calculate capability score
            matched_caps = sum(1 for cap in required_capabilities if cap in agent_capabilities)
            extra_caps = len(agent_capabilities) - matched_caps
            score = matched_caps * 100 - extra_caps  # Prefer exact matches

            agent_scores.append({
                "agent": agent,
                "score": score,
                "matched_capabilities": matched_caps,
                "total_capabilities": len(agent_capabilities)
            })

        if not agent_scores:
            # Fallback to least loaded if no capabilities metadata
            return AgentLoadBalancer._least_loaded_select(session, agents)

        # Select agent with highest score
        selected = max(agent_scores, key=lambda x: x["score"])

        return {
            "agent_id": selected["agent"].id,
            "agent_name": selected["agent"].name,
            "agent_role": selected["agent"].role.value,
            "selection_reason": "capability_based",
            "capability_score": selected["score"],
            "matched_capabilities": selected["matched_capabilities"]
        }

    @staticmethod
    def _performance_select(session: Session, agents: List[Agent]) -> Dict[str, Any]:
        """Select agent based on historical performance."""
        agent_performance = []

        for agent in agents:
            # Get recent completed executions
            recent_executions = session.query(AgentExecution).filter(
                and_(
                    AgentExecution.agent_id == agent.id,
                    AgentExecution.status == ExecutionStatus.COMPLETED,
                    AgentExecution.completed_at >= datetime.utcnow() - timedelta(hours=24)
                )
            ).all()

            if not recent_executions:
                # No history, assign neutral score
                performance_score = 50
                avg_duration = None
                success_rate = None
            else:
                # Calculate success rate
                total = len(recent_executions)
                successful = sum(1 for exec in recent_executions if exec.result and exec.result.get("success"))
                success_rate = (successful / total * 100) if total > 0 else 0

                # Calculate average duration
                durations = []
                for exec in recent_executions:
                    if exec.started_at and exec.completed_at:
                        duration = (exec.completed_at - exec.started_at).total_seconds()
                        durations.append(duration)

                avg_duration = sum(durations) / len(durations) if durations else None

                # Performance score (higher is better)
                # Success rate contributes 70%, speed contributes 30%
                speed_score = 100 - min((avg_duration or 0) / 60, 100) if avg_duration else 50
                performance_score = success_rate * 0.7 + speed_score * 0.3

            agent_performance.append({
                "agent": agent,
                "performance_score": performance_score,
                "success_rate": success_rate,
                "avg_duration": avg_duration,
                "recent_executions": len(recent_executions) if recent_executions else 0
            })

        # Select agent with highest performance score
        selected = max(agent_performance, key=lambda x: x["performance_score"])

        return {
            "agent_id": selected["agent"].id,
            "agent_name": selected["agent"].name,
            "agent_role": selected["agent"].role.value,
            "selection_reason": "performance_based",
            "performance_score": selected["performance_score"],
            "success_rate": selected["success_rate"],
            "avg_duration_seconds": selected["avg_duration"],
            "recent_executions": selected["recent_executions"]
        }

    @staticmethod
    def get_load_distribution(
        session: Session,
        agent_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Get load distribution across agents.

        Args:
            session: Database session
            agent_ids: Optional list of agent IDs to analyze

        Returns:
            Load distribution information
        """
        query = session.query(Agent)
        if agent_ids:
            query = query.filter(Agent.id.in_(agent_ids))

        agents = query.all()
        distribution = []

        for agent in agents:
            # Count tasks by status
            running = session.query(AgentExecution).filter(
                and_(
                    AgentExecution.agent_id == agent.id,
                    AgentExecution.status == ExecutionStatus.RUNNING
                )
            ).count()

            queued = session.query(AgentExecution).filter(
                and_(
                    AgentExecution.agent_id == agent.id,
                    AgentExecution.status == ExecutionStatus.QUEUED
                )
            ).count()

            # Get resource utilization
            usage_info = AgentResource.get_resource_usage(session, agent.id)

            distribution.append({
                "agent_id": agent.id,
                "agent_name": agent.name,
                "agent_role": agent.role.value,
                "agent_status": agent.status.value,
                "running_tasks": running,
                "queued_tasks": queued,
                "total_tasks": running + queued,
                "resource_utilization": usage_info["utilization_percentage"],
                "is_overloaded": usage_info["is_overloaded"]
            })

        # Calculate cluster statistics
        total_running = sum(d["running_tasks"] for d in distribution)
        total_queued = sum(d["queued_tasks"] for d in distribution)
        avg_load = total_running / len(distribution) if distribution else 0

        # Calculate load balance (standard deviation)
        if distribution:
            loads = [d["running_tasks"] for d in distribution]
            variance = sum((x - avg_load) ** 2 for x in loads) / len(loads)
            std_dev = variance ** 0.5
            balance_score = 100 - min(std_dev / avg_load * 100 if avg_load > 0 else 0, 100)
        else:
            balance_score = 100

        return {
            "total_agents": len(distribution),
            "total_running_tasks": total_running,
            "total_queued_tasks": total_queued,
            "average_load": avg_load,
            "balance_score": balance_score,
            "distribution": distribution
        }

    @staticmethod
    def rebalance_tasks(
        session: Session,
        strategy: str = LoadBalancingStrategy.LEAST_LOADED,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Rebalance tasks across agents.

        Args:
            session: Database session
            strategy: Strategy to use for rebalancing
            dry_run: If True, only simulate rebalancing

        Returns:
            Rebalancing results
        """
        # Get current distribution
        distribution = AgentLoadBalancer.get_load_distribution(session)

        if distribution["balance_score"] >= 80:
            return {
                "needed": False,
                "balance_score": distribution["balance_score"],
                "message": "System is already well balanced"
            }

        # Find overloaded and underloaded agents
        avg_load = distribution["average_load"]
        overloaded = [d for d in distribution["distribution"] if d["running_tasks"] > avg_load * 1.5]
        underloaded = [d for d in distribution["distribution"] if d["running_tasks"] < avg_load * 0.5]

        if not overloaded or not underloaded:
            return {
                "needed": False,
                "balance_score": distribution["balance_score"],
                "message": "No clear rebalancing opportunity"
            }

        # Identify tasks to move
        migrations = []
        for overloaded_agent in overloaded:
            # Get queued tasks for this agent
            queued_executions = session.query(AgentExecution).filter(
                and_(
                    AgentExecution.agent_id == overloaded_agent["agent_id"],
                    AgentExecution.status == ExecutionStatus.QUEUED
                )
            ).limit(3).all()  # Limit migrations per agent

            for execution in queued_executions:
                if not underloaded:
                    break

                # Select target agent
                target = underloaded[0]

                migrations.append({
                    "execution_id": execution.id,
                    "task_id": execution.task_id,
                    "from_agent_id": overloaded_agent["agent_id"],
                    "from_agent_name": overloaded_agent["agent_name"],
                    "to_agent_id": target["agent_id"],
                    "to_agent_name": target["agent_name"]
                })

                # Update target load
                target["queued_tasks"] += 1
                if target["queued_tasks"] >= avg_load * 0.8:
                    underloaded.pop(0)

        # Apply migrations if not dry run
        if not dry_run:
            for migration in migrations:
                execution = session.query(AgentExecution).filter(
                    AgentExecution.id == migration["execution_id"]
                ).first()
                if execution:
                    execution.agent_id = migration["to_agent_id"]

            session.commit()
            logger.info(f"Rebalanced {len(migrations)} tasks")

        return {
            "needed": True,
            "balance_score_before": distribution["balance_score"],
            "migrations": migrations,
            "total_migrations": len(migrations),
            "applied": not dry_run,
            "message": f"{'Would migrate' if dry_run else 'Migrated'} {len(migrations)} tasks"
        }

    @staticmethod
    def get_agent_capacity(
        session: Session,
        agent_id: int
    ) -> Dict[str, Any]:
        """
        Get agent capacity information.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Capacity information
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Get current load
        running = session.query(AgentExecution).filter(
            and_(
                AgentExecution.agent_id == agent_id,
                AgentExecution.status == ExecutionStatus.RUNNING
            )
        ).count()

        queued = session.query(AgentExecution).filter(
            and_(
                AgentExecution.agent_id == agent_id,
                AgentExecution.status == ExecutionStatus.QUEUED
            )
        ).count()

        # Get resource info
        usage_info = AgentResource.get_resource_usage(session, agent_id)

        # Calculate capacity
        max_concurrent = agent.metadata.get("max_concurrent_tasks", 5) if agent.metadata else 5
        task_capacity_used = (running / max_concurrent * 100) if max_concurrent > 0 else 0

        avg_resource_util = sum(usage_info["utilization_percentage"].values()) / len(usage_info["utilization_percentage"])

        # Overall capacity (combination of task and resource capacity)
        overall_capacity_used = max(task_capacity_used, avg_resource_util)

        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "agent_status": agent.status.value,
            "running_tasks": running,
            "queued_tasks": queued,
            "max_concurrent_tasks": max_concurrent,
            "task_capacity_used_percentage": task_capacity_used,
            "resource_utilization": usage_info["utilization_percentage"],
            "avg_resource_utilization_percentage": avg_resource_util,
            "overall_capacity_used_percentage": overall_capacity_used,
            "available_capacity_percentage": 100 - overall_capacity_used,
            "can_accept_tasks": overall_capacity_used < 90 and agent.status in [AgentStatus.ACTIVE, AgentStatus.IDLE]
        }
