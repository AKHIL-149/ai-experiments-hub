"""
Agent Discovery Service

Provides agent registration, discovery, and service directory functionality.
Enables agents to find each other based on capabilities and availability.
"""

from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
from collections import defaultdict
import re


class DiscoveryStatus:
    """Agent discovery statuses"""
    AVAILABLE = "available"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"
    MAINTENANCE = "maintenance"


class CapabilityCategory:
    """Capability categories"""
    COMPUTATION = "computation"
    STORAGE = "storage"
    COMMUNICATION = "communication"
    ANALYSIS = "analysis"
    GENERATION = "generation"
    TRANSFORMATION = "transformation"
    VALIDATION = "validation"
    ORCHESTRATION = "orchestration"


class AgentDiscovery:
    """
    Agent Discovery System

    Manages agent registration, capability-based discovery, and service directory.
    Provides matchmaking between agents seeking capabilities and agents offering them.
    """

    # In-memory storage
    _registry = {}  # agent_id -> registration
    _registry_counter = 0

    _capabilities_index = defaultdict(set)  # capability -> {agent_ids}
    _category_index = defaultdict(set)  # category -> {agent_ids}
    _tag_index = defaultdict(set)  # tag -> {agent_ids}

    _heartbeats = {}  # agent_id -> last_heartbeat_time
    _service_directory = defaultdict(list)  # service_name -> [agent_ids]

    _discovery_queries = []  # Query history

    @staticmethod
    def register_agent(
        session,
        agent_id: int,
        agent_name: str,
        capabilities: List[str],
        categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        endpoint: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Register an agent in the discovery system.

        Args:
            session: Database session
            agent_id: Agent ID
            agent_name: Agent name
            capabilities: List of capabilities
            categories: Capability categories
            tags: Tags for searchability
            endpoint: Agent's network endpoint
            metadata: Additional metadata

        Returns:
            Registration record
        """
        AgentDiscovery._registry_counter += 1
        registration_id = f"reg_{AgentDiscovery._registry_counter}"

        registration = {
            "id": registration_id,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "capabilities": capabilities,
            "categories": categories or [],
            "tags": tags or [],
            "endpoint": endpoint,
            "metadata": metadata or {},
            "status": DiscoveryStatus.AVAILABLE,
            "registered_at": datetime.utcnow().isoformat(),
            "last_seen": datetime.utcnow().isoformat(),
            "query_count": 0,
            "match_count": 0
        }

        AgentDiscovery._registry[agent_id] = registration

        # Index by capabilities
        for capability in capabilities:
            AgentDiscovery._capabilities_index[capability.lower()].add(agent_id)

        # Index by categories
        for category in (categories or []):
            AgentDiscovery._category_index[category].add(agent_id)

        # Index by tags
        for tag in (tags or []):
            AgentDiscovery._tag_index[tag.lower()].add(agent_id)

        # Record heartbeat
        AgentDiscovery._heartbeats[agent_id] = datetime.utcnow()

        return registration

    @staticmethod
    def discover_agents(
        session,
        required_capabilities: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        status: Optional[str] = None,
        match_all_capabilities: bool = False,
        limit: int = 10
    ) -> dict:
        """
        Discover agents based on requirements.

        Args:
            session: Database session
            required_capabilities: Capabilities needed
            categories: Category filters
            tags: Tag filters
            status: Status filter
            match_all_capabilities: Whether all capabilities must match
            limit: Maximum results

        Returns:
            Matching agents ranked by relevance
        """
        # Record query
        query_record = {
            "query_id": f"query_{len(AgentDiscovery._discovery_queries) + 1}",
            "required_capabilities": required_capabilities,
            "categories": categories,
            "tags": tags,
            "timestamp": datetime.utcnow().isoformat()
        }
        AgentDiscovery._discovery_queries.append(query_record)

        matches = set()

        # Find by capabilities
        if required_capabilities:
            capability_matches = set()
            for capability in required_capabilities:
                agents_with_capability = AgentDiscovery._capabilities_index.get(
                    capability.lower(), set()
                )
                if not capability_matches:
                    capability_matches = agents_with_capability.copy()
                elif match_all_capabilities:
                    capability_matches &= agents_with_capability
                else:
                    capability_matches |= agents_with_capability

            matches = capability_matches
        else:
            # No capability filter, start with all agents
            matches = set(AgentDiscovery._registry.keys())

        # Filter by categories
        if categories:
            category_matches = set()
            for category in categories:
                category_matches |= AgentDiscovery._category_index.get(category, set())
            matches &= category_matches

        # Filter by tags
        if tags:
            tag_matches = set()
            for tag in tags:
                tag_matches |= AgentDiscovery._tag_index.get(tag.lower(), set())
            matches &= tag_matches

        # Filter by status
        if status:
            matches = {
                agent_id for agent_id in matches
                if AgentDiscovery._registry[agent_id]["status"] == status
            }

        # Convert to list and rank
        results = []
        for agent_id in matches:
            registration = AgentDiscovery._registry[agent_id]

            # Calculate relevance score
            relevance_score = 0.0

            if required_capabilities:
                matching_caps = set(required_capabilities) & set(
                    cap.lower() for cap in registration["capabilities"]
                )
                relevance_score = len(matching_caps) / len(required_capabilities)

            results.append({
                **registration,
                "relevance_score": relevance_score
            })

            # Update match count
            registration["match_count"] += 1

        # Sort by relevance
        results.sort(key=lambda x: x["relevance_score"], reverse=True)

        return {
            "query_id": query_record["query_id"],
            "total_matches": len(results),
            "matches": results[:limit]
        }

    @staticmethod
    def update_status(
        session,
        agent_id: int,
        status: str,
        reason: Optional[str] = None
    ) -> dict:
        """
        Update agent discovery status.

        Args:
            session: Database session
            agent_id: Agent ID
            status: New status
            reason: Reason for status change

        Returns:
            Updated registration
        """
        if agent_id not in AgentDiscovery._registry:
            raise ValueError(f"Agent {agent_id} not registered")

        registration = AgentDiscovery._registry[agent_id]
        old_status = registration["status"]

        registration["status"] = status
        registration["last_seen"] = datetime.utcnow().isoformat()

        if reason:
            if "status_history" not in registration["metadata"]:
                registration["metadata"]["status_history"] = []

            registration["metadata"]["status_history"].append({
                "timestamp": datetime.utcnow().isoformat(),
                "old_status": old_status,
                "new_status": status,
                "reason": reason
            })

        return registration

    @staticmethod
    def heartbeat(
        session,
        agent_id: int,
        metrics: Optional[dict] = None
    ) -> dict:
        """
        Record agent heartbeat.

        Args:
            session: Database session
            agent_id: Agent ID
            metrics: Current agent metrics

        Returns:
            Heartbeat acknowledgment
        """
        if agent_id not in AgentDiscovery._registry:
            raise ValueError(f"Agent {agent_id} not registered")

        AgentDiscovery._heartbeats[agent_id] = datetime.utcnow()
        registration = AgentDiscovery._registry[agent_id]
        registration["last_seen"] = datetime.utcnow().isoformat()

        if metrics:
            registration["metadata"]["last_metrics"] = metrics

        # Auto-update status based on metrics
        if metrics and "load" in metrics:
            if metrics["load"] > 0.9:
                registration["status"] = DiscoveryStatus.BUSY
            elif registration["status"] == DiscoveryStatus.BUSY and metrics["load"] < 0.5:
                registration["status"] = DiscoveryStatus.AVAILABLE

        return {
            "agent_id": agent_id,
            "acknowledged_at": datetime.utcnow().isoformat(),
            "current_status": registration["status"]
        }

    @staticmethod
    def register_service(
        session,
        agent_id: int,
        service_name: str,
        service_description: Optional[str] = None,
        service_metadata: Optional[dict] = None
    ) -> dict:
        """
        Register a service provided by an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            service_name: Service name
            service_description: Service description
            service_metadata: Service metadata

        Returns:
            Service registration
        """
        if agent_id not in AgentDiscovery._registry:
            raise ValueError(f"Agent {agent_id} not registered")

        service_record = {
            "agent_id": agent_id,
            "service_name": service_name,
            "description": service_description,
            "metadata": service_metadata or {},
            "registered_at": datetime.utcnow().isoformat()
        }

        AgentDiscovery._service_directory[service_name].append(service_record)

        return service_record

    @staticmethod
    def discover_service(
        session,
        service_name: str,
        only_available: bool = True
    ) -> dict:
        """
        Discover agents providing a service.

        Args:
            session: Database session
            service_name: Service name to find
            only_available: Only return available agents

        Returns:
            Service providers
        """
        providers = AgentDiscovery._service_directory.get(service_name, [])

        if only_available:
            providers = [
                p for p in providers
                if AgentDiscovery._registry[p["agent_id"]]["status"] == DiscoveryStatus.AVAILABLE
            ]

        return {
            "service_name": service_name,
            "total_providers": len(providers),
            "providers": providers
        }

    @staticmethod
    def add_capability(
        session,
        agent_id: int,
        capability: str,
        category: Optional[str] = None
    ) -> dict:
        """
        Add a capability to an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            capability: Capability to add
            category: Capability category

        Returns:
            Updated registration
        """
        if agent_id not in AgentDiscovery._registry:
            raise ValueError(f"Agent {agent_id} not registered")

        registration = AgentDiscovery._registry[agent_id]

        if capability not in registration["capabilities"]:
            registration["capabilities"].append(capability)
            AgentDiscovery._capabilities_index[capability.lower()].add(agent_id)

        if category and category not in registration["categories"]:
            registration["categories"].append(category)
            AgentDiscovery._category_index[category].add(agent_id)

        return registration

    @staticmethod
    def remove_capability(
        session,
        agent_id: int,
        capability: str
    ) -> dict:
        """
        Remove a capability from an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            capability: Capability to remove

        Returns:
            Updated registration
        """
        if agent_id not in AgentDiscovery._registry:
            raise ValueError(f"Agent {agent_id} not registered")

        registration = AgentDiscovery._registry[agent_id]

        if capability in registration["capabilities"]:
            registration["capabilities"].remove(capability)
            AgentDiscovery._capabilities_index[capability.lower()].discard(agent_id)

        return registration

    @staticmethod
    def unregister_agent(
        session,
        agent_id: int
    ) -> dict:
        """
        Unregister an agent.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Unregistration confirmation
        """
        if agent_id not in AgentDiscovery._registry:
            raise ValueError(f"Agent {agent_id} not registered")

        registration = AgentDiscovery._registry[agent_id]

        # Remove from indices
        for capability in registration["capabilities"]:
            AgentDiscovery._capabilities_index[capability.lower()].discard(agent_id)

        for category in registration["categories"]:
            AgentDiscovery._category_index[category].discard(agent_id)

        for tag in registration["tags"]:
            AgentDiscovery._tag_index[tag.lower()].discard(agent_id)

        # Remove from registry
        del AgentDiscovery._registry[agent_id]
        AgentDiscovery._heartbeats.pop(agent_id, None)

        # Remove from service directory
        for service_name, providers in AgentDiscovery._service_directory.items():
            AgentDiscovery._service_directory[service_name] = [
                p for p in providers if p["agent_id"] != agent_id
            ]

        return {
            "agent_id": agent_id,
            "unregistered_at": datetime.utcnow().isoformat(),
            "message": f"Agent {registration['agent_name']} unregistered"
        }

    @staticmethod
    def get_agent_info(
        session,
        agent_id: int
    ) -> dict:
        """
        Get agent registration info.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Agent registration details
        """
        if agent_id not in AgentDiscovery._registry:
            raise ValueError(f"Agent {agent_id} not registered")

        registration = AgentDiscovery._registry[agent_id]

        # Calculate uptime
        registered_time = datetime.fromisoformat(registration["registered_at"])
        uptime_seconds = (datetime.utcnow() - registered_time).total_seconds()

        # Get services
        provided_services = []
        for service_name, providers in AgentDiscovery._service_directory.items():
            if any(p["agent_id"] == agent_id for p in providers):
                provided_services.append(service_name)

        return {
            **registration,
            "uptime_seconds": uptime_seconds,
            "provided_services": provided_services
        }

    @staticmethod
    def list_all_agents(
        session,
        status: Optional[str] = None,
        category: Optional[str] = None
    ) -> dict:
        """
        List all registered agents.

        Args:
            session: Database session
            status: Filter by status
            category: Filter by category

        Returns:
            List of registered agents
        """
        agents = list(AgentDiscovery._registry.values())

        if status:
            agents = [a for a in agents if a["status"] == status]

        if category:
            agents = [a for a in agents if category in a["categories"]]

        # Sort by registration time
        agents.sort(key=lambda a: a["registered_at"], reverse=True)

        return {
            "total": len(agents),
            "agents": agents
        }

    @staticmethod
    def get_capabilities_catalog(session) -> dict:
        """
        Get catalog of all available capabilities.

        Args:
            session: Database session

        Returns:
            Capabilities catalog with agent counts
        """
        catalog = {}

        for capability, agent_ids in AgentDiscovery._capabilities_index.items():
            available_count = sum(
                1 for agent_id in agent_ids
                if AgentDiscovery._registry[agent_id]["status"] == DiscoveryStatus.AVAILABLE
            )

            catalog[capability] = {
                "total_agents": len(agent_ids),
                "available_agents": available_count,
                "agents": list(agent_ids)
            }

        return {
            "total_capabilities": len(catalog),
            "capabilities": catalog
        }

    @staticmethod
    def get_service_directory(session) -> dict:
        """
        Get complete service directory.

        Args:
            session: Database session

        Returns:
            Service directory with providers
        """
        directory = {}

        for service_name, providers in AgentDiscovery._service_directory.items():
            available_providers = [
                p for p in providers
                if AgentDiscovery._registry[p["agent_id"]]["status"] == DiscoveryStatus.AVAILABLE
            ]

            directory[service_name] = {
                "total_providers": len(providers),
                "available_providers": len(available_providers),
                "providers": providers
            }

        return {
            "total_services": len(directory),
            "services": directory
        }

    @staticmethod
    def check_agent_health(
        session,
        timeout_seconds: int = 300
    ) -> dict:
        """
        Check health of all agents based on heartbeats.

        Args:
            session: Database session
            timeout_seconds: Heartbeat timeout

        Returns:
            Health status of all agents
        """
        now = datetime.utcnow()
        timeout_delta = timedelta(seconds=timeout_seconds)

        healthy = []
        unhealthy = []

        for agent_id, last_heartbeat in AgentDiscovery._heartbeats.items():
            if (now - last_heartbeat) <= timeout_delta:
                healthy.append(agent_id)
            else:
                unhealthy.append(agent_id)

                # Auto-update status to unavailable
                if agent_id in AgentDiscovery._registry:
                    AgentDiscovery._registry[agent_id]["status"] = DiscoveryStatus.UNAVAILABLE

        return {
            "checked_at": now.isoformat(),
            "timeout_seconds": timeout_seconds,
            "total_agents": len(AgentDiscovery._heartbeats),
            "healthy_count": len(healthy),
            "unhealthy_count": len(unhealthy),
            "healthy_agents": healthy,
            "unhealthy_agents": unhealthy
        }

    @staticmethod
    def get_discovery_statistics(session) -> dict:
        """
        Get discovery system statistics.

        Args:
            session: Database session

        Returns:
            System statistics
        """
        total_agents = len(AgentDiscovery._registry)

        # Count by status
        by_status = defaultdict(int)
        for registration in AgentDiscovery._registry.values():
            by_status[registration["status"]] += 1

        # Count by category
        by_category = defaultdict(int)
        for registration in AgentDiscovery._registry.values():
            for category in registration["categories"]:
                by_category[category] += 1

        # Top capabilities
        top_capabilities = sorted(
            AgentDiscovery._capabilities_index.items(),
            key=lambda x: len(x[1]),
            reverse=True
        )[:10]

        return {
            "total_agents": total_agents,
            "total_capabilities": len(AgentDiscovery._capabilities_index),
            "total_services": len(AgentDiscovery._service_directory),
            "total_queries": len(AgentDiscovery._discovery_queries),
            "agents_by_status": dict(by_status),
            "agents_by_category": dict(by_category),
            "top_capabilities": [
                {"capability": cap, "agent_count": len(agents)}
                for cap, agents in top_capabilities
            ]
        }
