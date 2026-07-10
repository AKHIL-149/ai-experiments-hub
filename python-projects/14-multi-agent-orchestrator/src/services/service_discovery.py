"""
Service Discovery and Registry

Provides dynamic service registration, discovery, and health monitoring for distributed agents.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import uuid
import random


class ServiceStatus:
    """Service health status"""
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPING = "stopping"
    UNKNOWN = "unknown"


class LoadBalancingStrategy:
    """Load balancing strategies"""
    ROUND_ROBIN = "round_robin"
    RANDOM = "random"
    LEAST_CONNECTIONS = "least_connections"
    WEIGHTED = "weighted"
    CONSISTENT_HASH = "consistent_hash"


class ServiceType:
    """Service types"""
    AGENT = "agent"
    API = "api"
    DATABASE = "database"
    CACHE = "cache"
    MESSAGE_QUEUE = "message_queue"
    STORAGE = "storage"
    CUSTOM = "custom"


class HealthCheckType:
    """Health check types"""
    HTTP = "http"
    TCP = "tcp"
    SCRIPT = "script"
    HEARTBEAT = "heartbeat"


class ServiceDiscovery:
    """Service Discovery and Registry"""

    # In-memory storage
    _services = {}
    _service_instances = {}
    _health_checks = {}
    _load_balancer_state = defaultdict(lambda: {"current_index": 0, "connection_counts": defaultdict(int)})
    _service_metrics = defaultdict(lambda: {
        "total_requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "average_latency_ms": 0
    })

    @staticmethod
    def register_service(
        session,
        service_name: str,
        service_type: str,
        host: str,
        port: int,
        version: str = "1.0.0",
        metadata: Optional[dict] = None,
        health_check_url: Optional[str] = None,
        health_check_interval_seconds: int = 30,
        tags: Optional[List[str]] = None,
        weight: int = 1
    ) -> dict:
        """
        Register a service instance.

        Args:
            session: Database session
            service_name: Service name
            service_type: Type of service
            host: Service host
            port: Service port
            version: Service version
            metadata: Additional metadata
            health_check_url: Health check endpoint
            health_check_interval_seconds: Health check interval
            tags: Service tags
            weight: Weight for load balancing

        Returns:
            Registered service instance
        """
        instance_id = f"instance_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # Create service definition if not exists
        if service_name not in ServiceDiscovery._services:
            service_id = f"service_{uuid.uuid4().hex[:12]}"
            ServiceDiscovery._services[service_name] = {
                "id": service_id,
                "name": service_name,
                "type": service_type,
                "created_at": now.isoformat(),
                "instance_count": 0,
                "healthy_instances": 0,
                "versions": set()
            }

        service = ServiceDiscovery._services[service_name]

        # Register instance
        instance = {
            "id": instance_id,
            "service_id": service["id"],
            "service_name": service_name,
            "service_type": service_type,
            "host": host,
            "port": port,
            "version": version,
            "status": ServiceStatus.STARTING,
            "metadata": metadata or {},
            "tags": tags or [],
            "weight": weight,
            "registered_at": now.isoformat(),
            "last_heartbeat_at": now.isoformat(),
            "health_check_url": health_check_url,
            "health_check_interval_seconds": health_check_interval_seconds,
            "consecutive_failures": 0,
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0
        }

        ServiceDiscovery._service_instances[instance_id] = instance

        # Update service counts
        service["instance_count"] += 1
        service["versions"].add(version)

        # Create health check if URL provided
        if health_check_url:
            ServiceDiscovery._create_health_check(instance_id, health_check_url, health_check_interval_seconds)

        # Mark as healthy after registration (would do actual health check in production)
        instance["status"] = ServiceStatus.HEALTHY
        service["healthy_instances"] += 1

        return instance

    @staticmethod
    def deregister_service(session, instance_id: str) -> dict:
        """
        Deregister a service instance.

        Args:
            session: Database session
            instance_id: Instance ID to deregister

        Returns:
            Deregistration result
        """
        instance = ServiceDiscovery._service_instances.get(instance_id)
        if not instance:
            raise ValueError(f"Service instance not found: {instance_id}")

        service_name = instance["service_name"]
        service = ServiceDiscovery._services.get(service_name)

        # Update service counts
        if service:
            service["instance_count"] -= 1
            if instance["status"] == ServiceStatus.HEALTHY:
                service["healthy_instances"] -= 1

        # Remove health check
        if instance_id in ServiceDiscovery._health_checks:
            del ServiceDiscovery._health_checks[instance_id]

        # Remove instance
        del ServiceDiscovery._service_instances[instance_id]

        return {
            "instance_id": instance_id,
            "service_name": service_name,
            "deregistered_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def discover_service(
        session,
        service_name: str,
        version: Optional[str] = None,
        tags: Optional[List[str]] = None,
        status: str = ServiceStatus.HEALTHY
    ) -> dict:
        """
        Discover service instances.

        Args:
            session: Database session
            service_name: Service name to discover
            version: Optional version filter
            tags: Optional tags filter
            status: Instance status filter

        Returns:
            Available service instances
        """
        service = ServiceDiscovery._services.get(service_name)
        if not service:
            raise ValueError(f"Service not found: {service_name}")

        # Find matching instances
        instances = [
            inst for inst in ServiceDiscovery._service_instances.values()
            if inst["service_name"] == service_name
        ]

        # Apply filters
        if version:
            instances = [inst for inst in instances if inst["version"] == version]
        if tags:
            instances = [inst for inst in instances if all(tag in inst["tags"] for tag in tags)]
        if status:
            instances = [inst for inst in instances if inst["status"] == status]

        return {
            "service_name": service_name,
            "instances": instances,
            "instance_count": len(instances),
            "discovered_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_service_instance(
        session,
        service_name: str,
        strategy: str = LoadBalancingStrategy.ROUND_ROBIN,
        version: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> dict:
        """
        Get a service instance using load balancing strategy.

        Args:
            session: Database session
            service_name: Service name
            strategy: Load balancing strategy
            version: Optional version filter
            tags: Optional tags filter

        Returns:
            Selected service instance
        """
        # Discover available instances
        discovery = ServiceDiscovery.discover_service(
            session=session,
            service_name=service_name,
            version=version,
            tags=tags,
            status=ServiceStatus.HEALTHY
        )

        instances = discovery["instances"]
        if not instances:
            raise ValueError(f"No healthy instances found for service: {service_name}")

        # Apply load balancing strategy
        selected = ServiceDiscovery._select_instance(service_name, instances, strategy)

        # Update metrics
        ServiceDiscovery._load_balancer_state[service_name]["connection_counts"][selected["id"]] += 1

        return {
            "service_name": service_name,
            "instance": selected,
            "strategy": strategy,
            "selected_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def heartbeat(session, instance_id: str) -> dict:
        """
        Send heartbeat for service instance.

        Args:
            session: Database session
            instance_id: Instance ID

        Returns:
            Heartbeat confirmation
        """
        instance = ServiceDiscovery._service_instances.get(instance_id)
        if not instance:
            raise ValueError(f"Service instance not found: {instance_id}")

        now = datetime.utcnow()
        instance["last_heartbeat_at"] = now.isoformat()
        instance["consecutive_failures"] = 0

        # Update status to healthy if it was starting
        if instance["status"] == ServiceStatus.STARTING:
            instance["status"] = ServiceStatus.HEALTHY
            service = ServiceDiscovery._services.get(instance["service_name"])
            if service:
                service["healthy_instances"] += 1

        return {
            "instance_id": instance_id,
            "status": instance["status"],
            "heartbeat_at": now.isoformat()
        }

    @staticmethod
    def update_instance_health(
        session,
        instance_id: str,
        status: str,
        health_data: Optional[dict] = None
    ) -> dict:
        """
        Update instance health status.

        Args:
            session: Database session
            instance_id: Instance ID
            status: New health status
            health_data: Health check data

        Returns:
            Updated instance
        """
        instance = ServiceDiscovery._service_instances.get(instance_id)
        if not instance:
            raise ValueError(f"Service instance not found: {instance_id}")

        old_status = instance["status"]
        instance["status"] = status
        instance["updated_at"] = datetime.utcnow().isoformat()

        service = ServiceDiscovery._services.get(instance["service_name"])

        # Update service healthy count
        if service:
            if old_status == ServiceStatus.HEALTHY and status != ServiceStatus.HEALTHY:
                service["healthy_instances"] -= 1
            elif old_status != ServiceStatus.HEALTHY and status == ServiceStatus.HEALTHY:
                service["healthy_instances"] += 1

        # Track failures
        if status == ServiceStatus.UNHEALTHY:
            instance["consecutive_failures"] += 1
        else:
            instance["consecutive_failures"] = 0

        if health_data:
            instance["last_health_data"] = health_data

        return instance

    @staticmethod
    def list_services(
        session,
        service_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> dict:
        """
        List registered services.

        Args:
            session: Database session
            service_type: Filter by service type
            status: Filter by status
            limit: Maximum services to return

        Returns:
            List of services
        """
        services = []

        for service in ServiceDiscovery._services.values():
            # Get instances for this service
            instances = [
                inst for inst in ServiceDiscovery._service_instances.values()
                if inst["service_name"] == service["name"]
            ]

            # Apply filters
            if service_type and service["type"] != service_type:
                continue

            if status:
                matching_instances = [inst for inst in instances if inst["status"] == status]
                if not matching_instances:
                    continue

            service_info = {
                **service,
                "versions": list(service["versions"]),
                "instances": instances
            }
            services.append(service_info)

        # Sort by name
        services.sort(key=lambda x: x["name"])

        # Apply limit
        services = services[:limit]

        return {
            "services": services,
            "total_services": len(ServiceDiscovery._services),
            "returned_count": len(services)
        }

    @staticmethod
    def get_service_health(session, service_name: str) -> dict:
        """
        Get service health information.

        Args:
            session: Database session
            service_name: Service name

        Returns:
            Service health information
        """
        service = ServiceDiscovery._services.get(service_name)
        if not service:
            raise ValueError(f"Service not found: {service_name}")

        instances = [
            inst for inst in ServiceDiscovery._service_instances.values()
            if inst["service_name"] == service_name
        ]

        # Calculate health metrics
        status_counts = defaultdict(int)
        for inst in instances:
            status_counts[inst["status"]] += 1

        total_instances = len(instances)
        healthy_instances = service["healthy_instances"]
        health_percentage = (healthy_instances / total_instances * 100) if total_instances > 0 else 0

        return {
            "service_name": service_name,
            "service_type": service["type"],
            "total_instances": total_instances,
            "healthy_instances": healthy_instances,
            "unhealthy_instances": status_counts[ServiceStatus.UNHEALTHY],
            "health_percentage": health_percentage,
            "status_distribution": dict(status_counts),
            "versions": list(service["versions"]),
            "checked_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get service discovery statistics"""
        services = list(ServiceDiscovery._services.values())
        instances = list(ServiceDiscovery._service_instances.values())

        # Type distribution
        type_dist = defaultdict(int)
        for service in services:
            type_dist[service["type"]] += 1

        # Status distribution
        status_dist = defaultdict(int)
        for instance in instances:
            status_dist[instance["status"]] += 1

        # Version distribution
        version_dist = defaultdict(int)
        for instance in instances:
            version_dist[instance["version"]] += 1

        # Calculate averages
        total_healthy = sum(s["healthy_instances"] for s in services)
        total_instances = len(instances)
        overall_health = (total_healthy / total_instances * 100) if total_instances > 0 else 0

        return {
            "total_services": len(services),
            "total_instances": total_instances,
            "healthy_instances": total_healthy,
            "overall_health_percentage": overall_health,
            "service_type_distribution": dict(type_dist),
            "instance_status_distribution": dict(status_dist),
            "version_distribution": dict(version_dist),
            "health_checks_configured": len(ServiceDiscovery._health_checks)
        }

    # Helper methods
    @staticmethod
    def _create_health_check(instance_id: str, url: str, interval_seconds: int):
        """Create health check for instance"""
        health_check = {
            "instance_id": instance_id,
            "url": url,
            "interval_seconds": interval_seconds,
            "type": HealthCheckType.HTTP,
            "created_at": datetime.utcnow().isoformat(),
            "last_check_at": None,
            "consecutive_failures": 0,
            "consecutive_successes": 0
        }
        ServiceDiscovery._health_checks[instance_id] = health_check

    @staticmethod
    def _select_instance(service_name: str, instances: List[dict], strategy: str) -> dict:
        """Select instance using load balancing strategy"""
        if not instances:
            raise ValueError("No instances available")

        if strategy == LoadBalancingStrategy.RANDOM:
            return random.choice(instances)

        elif strategy == LoadBalancingStrategy.ROUND_ROBIN:
            state = ServiceDiscovery._load_balancer_state[service_name]
            index = state["current_index"] % len(instances)
            state["current_index"] += 1
            return instances[index]

        elif strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
            state = ServiceDiscovery._load_balancer_state[service_name]
            connection_counts = state["connection_counts"]
            # Find instance with least connections
            min_connections = min(
                (connection_counts[inst["id"]], inst) for inst in instances
            )
            return min_connections[1]

        elif strategy == LoadBalancingStrategy.WEIGHTED:
            # Weighted random selection
            total_weight = sum(inst["weight"] for inst in instances)
            rand_val = random.uniform(0, total_weight)
            cumulative = 0
            for inst in instances:
                cumulative += inst["weight"]
                if cumulative >= rand_val:
                    return inst
            return instances[-1]

        elif strategy == LoadBalancingStrategy.CONSISTENT_HASH:
            # Simple consistent hashing (would use proper hash ring in production)
            return instances[hash(service_name) % len(instances)]

        else:
            return instances[0]
