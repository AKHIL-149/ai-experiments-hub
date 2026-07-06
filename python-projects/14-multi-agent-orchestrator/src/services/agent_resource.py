"""
Agent Resource Management Service
Handles resource allocation, monitoring, and limits for agents
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from src.models.agent import Agent, AgentStatus
from src.models.agent_execution import AgentExecution, ExecutionStatus
from src.core.logging import logger


class ResourceType:
    """Resource type constants"""
    CPU = "cpu"              # CPU cores
    MEMORY = "memory"        # RAM in GB
    GPU = "gpu"              # GPU units
    DISK = "disk"            # Disk space in GB
    NETWORK = "network"      # Network bandwidth in Mbps


class AgentResource:
    """
    Agent Resource Management Service

    Manages resource allocation, limits, and monitoring for agents.
    """

    @staticmethod
    def set_resource_limits(
        session: Session,
        agent_id: int,
        cpu: Optional[float] = None,
        memory: Optional[float] = None,
        gpu: Optional[int] = None,
        disk: Optional[float] = None,
        network: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Set resource limits for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            cpu: CPU cores limit
            memory: Memory in GB
            gpu: GPU units
            disk: Disk space in GB
            network: Network bandwidth in Mbps

        Returns:
            Updated resource limits
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Initialize metadata if needed
        if not agent.metadata:
            agent.metadata = {}

        if "resource_limits" not in agent.metadata:
            agent.metadata["resource_limits"] = {}

        # Update limits
        if cpu is not None:
            agent.metadata["resource_limits"]["cpu"] = cpu
        if memory is not None:
            agent.metadata["resource_limits"]["memory"] = memory
        if gpu is not None:
            agent.metadata["resource_limits"]["gpu"] = gpu
        if disk is not None:
            agent.metadata["resource_limits"]["disk"] = disk
        if network is not None:
            agent.metadata["resource_limits"]["network"] = network

        session.commit()

        logger.info(f"Updated resource limits for agent {agent_id}")

        return agent.metadata["resource_limits"]

    @staticmethod
    def get_resource_limits(
        session: Session,
        agent_id: int
    ) -> Dict[str, float]:
        """
        Get resource limits for an agent.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Resource limits
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if not agent.metadata or "resource_limits" not in agent.metadata:
            # Default limits
            return {
                "cpu": 2.0,
                "memory": 4.0,
                "gpu": 0,
                "disk": 100.0,
                "network": 100.0
            }

        return agent.metadata["resource_limits"]

    @staticmethod
    def set_resource_usage(
        session: Session,
        agent_id: int,
        cpu: Optional[float] = None,
        memory: Optional[float] = None,
        gpu: Optional[int] = None,
        disk: Optional[float] = None,
        network: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Update current resource usage for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            cpu: Current CPU usage (cores)
            memory: Current memory usage (GB)
            gpu: Current GPU usage (units)
            disk: Current disk usage (GB)
            network: Current network usage (Mbps)

        Returns:
            Updated resource usage
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if not agent.metadata:
            agent.metadata = {}

        if "resource_usage" not in agent.metadata:
            agent.metadata["resource_usage"] = {}

        # Update usage
        if cpu is not None:
            agent.metadata["resource_usage"]["cpu"] = cpu
        if memory is not None:
            agent.metadata["resource_usage"]["memory"] = memory
        if gpu is not None:
            agent.metadata["resource_usage"]["gpu"] = gpu
        if disk is not None:
            agent.metadata["resource_usage"]["disk"] = disk
        if network is not None:
            agent.metadata["resource_usage"]["network"] = network

        agent.metadata["resource_usage"]["last_updated"] = datetime.utcnow().isoformat()

        session.commit()

        return agent.metadata["resource_usage"]

    @staticmethod
    def get_resource_usage(
        session: Session,
        agent_id: int
    ) -> Dict[str, Any]:
        """
        Get current resource usage for an agent.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Resource usage information
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        limits = AgentResource.get_resource_limits(session, agent_id)

        usage = {
            "cpu": 0.0,
            "memory": 0.0,
            "gpu": 0,
            "disk": 0.0,
            "network": 0.0,
            "last_updated": None
        }

        if agent.metadata and "resource_usage" in agent.metadata:
            usage.update(agent.metadata["resource_usage"])

        # Calculate utilization percentages
        utilization = {}
        for resource_type in [ResourceType.CPU, ResourceType.MEMORY, ResourceType.GPU,
                             ResourceType.DISK, ResourceType.NETWORK]:
            limit = limits.get(resource_type, 1.0)
            current = usage.get(resource_type, 0.0)
            utilization[resource_type] = (current / limit * 100) if limit > 0 else 0

        return {
            "agent_id": agent_id,
            "usage": usage,
            "limits": limits,
            "utilization_percentage": utilization,
            "is_overloaded": any(u > 90 for u in utilization.values())
        }

    @staticmethod
    def check_resource_availability(
        session: Session,
        agent_id: int,
        required_cpu: float = 0,
        required_memory: float = 0,
        required_gpu: int = 0,
        required_disk: float = 0,
        required_network: float = 0
    ) -> Dict[str, Any]:
        """
        Check if agent has sufficient resources available.

        Args:
            session: Database session
            agent_id: Agent ID
            required_cpu: Required CPU cores
            required_memory: Required memory (GB)
            required_gpu: Required GPU units
            required_disk: Required disk space (GB)
            required_network: Required network bandwidth (Mbps)

        Returns:
            Availability information
        """
        usage_info = AgentResource.get_resource_usage(session, agent_id)
        limits = usage_info["limits"]
        usage = usage_info["usage"]

        available = {}
        sufficient = {}
        shortfall = {}

        resources = {
            ResourceType.CPU: (required_cpu, usage.get("cpu", 0), limits.get("cpu", 0)),
            ResourceType.MEMORY: (required_memory, usage.get("memory", 0), limits.get("memory", 0)),
            ResourceType.GPU: (required_gpu, usage.get("gpu", 0), limits.get("gpu", 0)),
            ResourceType.DISK: (required_disk, usage.get("disk", 0), limits.get("disk", 0)),
            ResourceType.NETWORK: (required_network, usage.get("network", 0), limits.get("network", 0))
        }

        for resource_type, (required, current, limit) in resources.items():
            available[resource_type] = limit - current
            sufficient[resource_type] = available[resource_type] >= required

            if not sufficient[resource_type]:
                shortfall[resource_type] = required - available[resource_type]

        return {
            "agent_id": agent_id,
            "available": available,
            "required": {
                "cpu": required_cpu,
                "memory": required_memory,
                "gpu": required_gpu,
                "disk": required_disk,
                "network": required_network
            },
            "sufficient": all(sufficient.values()),
            "shortfall": shortfall if shortfall else None
        }

    @staticmethod
    def find_agents_with_resources(
        session: Session,
        required_cpu: float = 0,
        required_memory: float = 0,
        required_gpu: int = 0,
        required_disk: float = 0,
        required_network: float = 0,
        status: Optional[AgentStatus] = None
    ) -> List[Dict[str, Any]]:
        """
        Find agents with sufficient available resources.

        Args:
            session: Database session
            required_cpu: Required CPU cores
            required_memory: Required memory (GB)
            required_gpu: Required GPU units
            required_disk: Required disk space (GB)
            required_network: Required network bandwidth (Mbps)
            status: Optional status filter

        Returns:
            List of agents with sufficient resources
        """
        query = session.query(Agent)

        if status:
            query = query.filter(Agent.status == status)

        agents = query.all()
        suitable_agents = []

        for agent in agents:
            availability = AgentResource.check_resource_availability(
                session=session,
                agent_id=agent.id,
                required_cpu=required_cpu,
                required_memory=required_memory,
                required_gpu=required_gpu,
                required_disk=required_disk,
                required_network=required_network
            )

            if availability["sufficient"]:
                usage_info = AgentResource.get_resource_usage(session, agent.id)
                suitable_agents.append({
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "agent_role": agent.role.value,
                    "agent_status": agent.status.value,
                    "available_resources": availability["available"],
                    "utilization": usage_info["utilization_percentage"]
                })

        # Sort by lowest average utilization
        suitable_agents.sort(
            key=lambda x: sum(x["utilization"].values()) / len(x["utilization"])
        )

        return suitable_agents

    @staticmethod
    def get_cluster_resources(
        session: Session
    ) -> Dict[str, Any]:
        """
        Get cluster-wide resource statistics.

        Args:
            session: Database session

        Returns:
            Cluster resource information
        """
        agents = session.query(Agent).all()

        total_limits = {
            ResourceType.CPU: 0.0,
            ResourceType.MEMORY: 0.0,
            ResourceType.GPU: 0,
            ResourceType.DISK: 0.0,
            ResourceType.NETWORK: 0.0
        }

        total_usage = {
            ResourceType.CPU: 0.0,
            ResourceType.MEMORY: 0.0,
            ResourceType.GPU: 0,
            ResourceType.DISK: 0.0,
            ResourceType.NETWORK: 0.0
        }

        agent_count = len(agents)

        for agent in agents:
            limits = AgentResource.get_resource_limits(session, agent.id)
            for resource_type in total_limits.keys():
                total_limits[resource_type] += limits.get(resource_type, 0)

            if agent.metadata and "resource_usage" in agent.metadata:
                usage = agent.metadata["resource_usage"]
                for resource_type in total_usage.keys():
                    total_usage[resource_type] += usage.get(resource_type, 0)

        total_available = {}
        cluster_utilization = {}

        for resource_type in total_limits.keys():
            total_available[resource_type] = total_limits[resource_type] - total_usage[resource_type]
            cluster_utilization[resource_type] = (
                (total_usage[resource_type] / total_limits[resource_type] * 100)
                if total_limits[resource_type] > 0
                else 0
            )

        return {
            "total_agents": agent_count,
            "total_limits": total_limits,
            "total_usage": total_usage,
            "total_available": total_available,
            "cluster_utilization_percentage": cluster_utilization,
            "average_utilization": sum(cluster_utilization.values()) / len(cluster_utilization) if cluster_utilization else 0
        }

    @staticmethod
    def reserve_resources(
        session: Session,
        agent_id: int,
        execution_id: int,
        cpu: float = 0,
        memory: float = 0,
        gpu: int = 0,
        disk: float = 0,
        network: float = 0
    ) -> Dict[str, Any]:
        """
        Reserve resources for a task execution.

        Args:
            session: Database session
            agent_id: Agent ID
            execution_id: Execution ID
            cpu: CPU cores to reserve
            memory: Memory to reserve (GB)
            gpu: GPU units to reserve
            disk: Disk space to reserve (GB)
            network: Network bandwidth to reserve (Mbps)

        Returns:
            Reservation information
        """
        # Check availability first
        availability = AgentResource.check_resource_availability(
            session=session,
            agent_id=agent_id,
            required_cpu=cpu,
            required_memory=memory,
            required_gpu=gpu,
            required_disk=disk,
            required_network=network
        )

        if not availability["sufficient"]:
            raise ValueError(f"Insufficient resources. Shortfall: {availability['shortfall']}")

        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent.metadata:
            agent.metadata = {}

        if "resource_reservations" not in agent.metadata:
            agent.metadata["resource_reservations"] = []

        reservation = {
            "execution_id": execution_id,
            "cpu": cpu,
            "memory": memory,
            "gpu": gpu,
            "disk": disk,
            "network": network,
            "reserved_at": datetime.utcnow().isoformat()
        }

        agent.metadata["resource_reservations"].append(reservation)

        # Update usage to include reservation
        current_usage = agent.metadata.get("resource_usage", {})
        current_usage["cpu"] = current_usage.get("cpu", 0) + cpu
        current_usage["memory"] = current_usage.get("memory", 0) + memory
        current_usage["gpu"] = current_usage.get("gpu", 0) + gpu
        current_usage["disk"] = current_usage.get("disk", 0) + disk
        current_usage["network"] = current_usage.get("network", 0) + network
        agent.metadata["resource_usage"] = current_usage

        session.commit()

        logger.info(f"Reserved resources for execution {execution_id} on agent {agent_id}")

        return reservation

    @staticmethod
    def release_resources(
        session: Session,
        agent_id: int,
        execution_id: int
    ) -> bool:
        """
        Release reserved resources for a task execution.

        Args:
            session: Database session
            agent_id: Agent ID
            execution_id: Execution ID

        Returns:
            True if released, False if not found
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent or not agent.metadata or "resource_reservations" not in agent.metadata:
            return False

        # Find and remove reservation
        reservation = None
        for res in agent.metadata["resource_reservations"]:
            if res.get("execution_id") == execution_id:
                reservation = res
                break

        if not reservation:
            return False

        agent.metadata["resource_reservations"].remove(reservation)

        # Update usage to remove reservation
        current_usage = agent.metadata.get("resource_usage", {})
        current_usage["cpu"] = max(0, current_usage.get("cpu", 0) - reservation.get("cpu", 0))
        current_usage["memory"] = max(0, current_usage.get("memory", 0) - reservation.get("memory", 0))
        current_usage["gpu"] = max(0, current_usage.get("gpu", 0) - reservation.get("gpu", 0))
        current_usage["disk"] = max(0, current_usage.get("disk", 0) - reservation.get("disk", 0))
        current_usage["network"] = max(0, current_usage.get("network", 0) - reservation.get("network", 0))
        agent.metadata["resource_usage"] = current_usage

        session.commit()

        logger.info(f"Released resources for execution {execution_id} on agent {agent_id}")

        return True

    @staticmethod
    def get_resource_alerts(
        session: Session,
        threshold: float = 90.0
    ) -> List[Dict[str, Any]]:
        """
        Get agents with resource usage above threshold.

        Args:
            session: Database session
            threshold: Utilization threshold percentage

        Returns:
            List of agents with high resource usage
        """
        agents = session.query(Agent).all()
        alerts = []

        for agent in agents:
            usage_info = AgentResource.get_resource_usage(session, agent.id)
            utilization = usage_info["utilization_percentage"]

            overloaded_resources = {}
            for resource_type, util in utilization.items():
                if util >= threshold:
                    overloaded_resources[resource_type] = util

            if overloaded_resources:
                alerts.append({
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "agent_status": agent.status.value,
                    "overloaded_resources": overloaded_resources,
                    "usage": usage_info["usage"],
                    "limits": usage_info["limits"]
                })

        return alerts
