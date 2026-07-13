"""
Multi-Region Deployment Management Service

Provides multi-region deployment orchestration, traffic routing, health monitoring,
and failover management for globally distributed systems.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from enum import Enum
import statistics


class RegionStatus(str, Enum):
    """Region status"""
    ACTIVE = "active"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class DeploymentStrategy(str, Enum):
    """Deployment strategy types"""
    ROLLING = "rolling"
    BLUE_GREEN = "blue_green"
    CANARY = "canary"
    RECREATE = "recreate"


class TrafficRoutingMode(str, Enum):
    """Traffic routing modes"""
    ROUND_ROBIN = "round_robin"
    WEIGHTED = "weighted"
    LATENCY_BASED = "latency_based"
    GEOLOCATION = "geolocation"


class DeploymentStatus(str, Enum):
    """Deployment status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class MultiRegion:
    """Multi-region deployment management"""

    # In-memory storage
    _regions: Dict[str, Dict] = {}
    _deployments: Dict[str, Dict] = {}
    _region_health: List[Dict] = []
    _traffic_routes: Dict[str, Dict] = {}
    _replication_status: Dict[str, Dict] = {}
    _deployment_history: List[Dict] = []
    _region_metrics: List[Dict] = []

    @staticmethod
    def register_region(
        session,
        region_id: str,
        name: str,
        location: str,
        endpoint: str,
        capacity: int = 100,
        priority: int = 1,
        enabled: bool = True,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Register a deployment region."""
        if region_id in MultiRegion._regions:
            raise ValueError(f"Region already registered: {region_id}")

        region = {
            "region_id": region_id,
            "name": name,
            "location": location,
            "endpoint": endpoint,
            "capacity": capacity,
            "priority": priority,
            "enabled": enabled,
            "metadata": metadata or {},
            "status": RegionStatus.ACTIVE,
            "registered_at": datetime.utcnow().isoformat(),
            "last_health_check": None,
            "current_load": 0,
            "total_deployments": 0,
            "successful_deployments": 0,
            "failed_deployments": 0,
            "average_latency_ms": 0.0
        }

        MultiRegion._regions[region_id] = region

        return region

    @staticmethod
    def create_deployment(
        session,
        deployment_id: str,
        name: str,
        service_name: str,
        version: str,
        target_regions: List[str],
        strategy: DeploymentStrategy = DeploymentStrategy.ROLLING,
        rollout_percentage: int = 100,
        description: Optional[str] = None
    ) -> dict:
        """Create a multi-region deployment."""
        if deployment_id in MultiRegion._deployments:
            raise ValueError(f"Deployment already exists: {deployment_id}")

        # Validate target regions
        for region_id in target_regions:
            if region_id not in MultiRegion._regions:
                raise ValueError(f"Invalid region: {region_id}")

        deployment = {
            "deployment_id": deployment_id,
            "name": name,
            "service_name": service_name,
            "version": version,
            "target_regions": target_regions,
            "strategy": strategy,
            "rollout_percentage": rollout_percentage,
            "description": description or "",
            "status": DeploymentStatus.PENDING,
            "created_at": datetime.utcnow().isoformat(),
            "started_at": None,
            "completed_at": None,
            "region_status": {region: "pending" for region in target_regions},
            "total_regions": len(target_regions),
            "completed_regions": 0,
            "failed_regions": 0,
            "current_region": None
        }

        MultiRegion._deployments[deployment_id] = deployment

        return deployment

    @staticmethod
    def execute_deployment(session, deployment_id: str) -> dict:
        """Execute a deployment across regions."""
        deployment = MultiRegion._deployments.get(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment not found: {deployment_id}")

        if deployment["status"] != DeploymentStatus.PENDING:
            raise ValueError(f"Deployment already started: {deployment_id}")

        deployment["status"] = DeploymentStatus.IN_PROGRESS
        deployment["started_at"] = datetime.utcnow().isoformat()

        # Execute deployment based on strategy
        if deployment["strategy"] == DeploymentStrategy.ROLLING:
            MultiRegion._execute_rolling_deployment(deployment)
        elif deployment["strategy"] == DeploymentStrategy.BLUE_GREEN:
            MultiRegion._execute_blue_green_deployment(deployment)
        elif deployment["strategy"] == DeploymentStrategy.CANARY:
            MultiRegion._execute_canary_deployment(deployment)
        else:  # RECREATE
            MultiRegion._execute_recreate_deployment(deployment)

        # Record deployment history
        history_entry = {
            "history_id": f"history_{len(MultiRegion._deployment_history)}_{datetime.utcnow().timestamp()}",
            "deployment_id": deployment_id,
            "service_name": deployment["service_name"],
            "version": deployment["version"],
            "strategy": deployment["strategy"],
            "target_regions": deployment["target_regions"],
            "status": deployment["status"],
            "started_at": deployment["started_at"],
            "completed_at": deployment["completed_at"],
            "duration_seconds": None
        }

        if deployment["completed_at"]:
            start = datetime.fromisoformat(deployment["started_at"])
            end = datetime.fromisoformat(deployment["completed_at"])
            history_entry["duration_seconds"] = (end - start).total_seconds()

        MultiRegion._deployment_history.append(history_entry)

        return deployment

    @staticmethod
    def _execute_rolling_deployment(deployment: dict):
        """Execute rolling deployment across regions."""
        for region_id in deployment["target_regions"]:
            region = MultiRegion._regions[region_id]

            if not region["enabled"] or region["status"] == RegionStatus.OFFLINE:
                deployment["region_status"][region_id] = "skipped"
                continue

            # Simulate deployment to region
            deployment["current_region"] = region_id
            deployment["region_status"][region_id] = "in_progress"

            # Mark as completed (simplified)
            deployment["region_status"][region_id] = "completed"
            deployment["completed_regions"] += 1

            # Update region stats
            region["total_deployments"] += 1
            region["successful_deployments"] += 1

        deployment["status"] = DeploymentStatus.COMPLETED
        deployment["completed_at"] = datetime.utcnow().isoformat()
        deployment["current_region"] = None

    @staticmethod
    def _execute_blue_green_deployment(deployment: dict):
        """Execute blue-green deployment across regions."""
        # Deploy to all regions simultaneously (green environment)
        for region_id in deployment["target_regions"]:
            region = MultiRegion._regions[region_id]

            if not region["enabled"] or region["status"] == RegionStatus.OFFLINE:
                deployment["region_status"][region_id] = "skipped"
                continue

            deployment["region_status"][region_id] = "completed"
            deployment["completed_regions"] += 1

            region["total_deployments"] += 1
            region["successful_deployments"] += 1

        deployment["status"] = DeploymentStatus.COMPLETED
        deployment["completed_at"] = datetime.utcnow().isoformat()

    @staticmethod
    def _execute_canary_deployment(deployment: dict):
        """Execute canary deployment across regions."""
        # Deploy to first region as canary
        if deployment["target_regions"]:
            canary_region = deployment["target_regions"][0]
            region = MultiRegion._regions[canary_region]

            if region["enabled"] and region["status"] != RegionStatus.OFFLINE:
                deployment["region_status"][canary_region] = "completed"
                deployment["completed_regions"] += 1
                region["total_deployments"] += 1
                region["successful_deployments"] += 1

            # If canary succeeds, deploy to remaining regions
            for region_id in deployment["target_regions"][1:]:
                region = MultiRegion._regions[region_id]

                if not region["enabled"] or region["status"] == RegionStatus.OFFLINE:
                    deployment["region_status"][region_id] = "skipped"
                    continue

                deployment["region_status"][region_id] = "completed"
                deployment["completed_regions"] += 1
                region["total_deployments"] += 1
                region["successful_deployments"] += 1

        deployment["status"] = DeploymentStatus.COMPLETED
        deployment["completed_at"] = datetime.utcnow().isoformat()

    @staticmethod
    def _execute_recreate_deployment(deployment: dict):
        """Execute recreate deployment across regions."""
        # Take down old version and deploy new version
        for region_id in deployment["target_regions"]:
            region = MultiRegion._regions[region_id]

            if not region["enabled"] or region["status"] == RegionStatus.OFFLINE:
                deployment["region_status"][region_id] = "skipped"
                continue

            deployment["region_status"][region_id] = "completed"
            deployment["completed_regions"] += 1
            region["total_deployments"] += 1
            region["successful_deployments"] += 1

        deployment["status"] = DeploymentStatus.COMPLETED
        deployment["completed_at"] = datetime.utcnow().isoformat()

    @staticmethod
    def record_health_check(
        session,
        region_id: str,
        is_healthy: bool,
        response_time_ms: float,
        error_message: Optional[str] = None
    ) -> dict:
        """Record region health check."""
        region = MultiRegion._regions.get(region_id)
        if not region:
            raise ValueError(f"Region not found: {region_id}")

        health_check = {
            "check_id": f"check_{len(MultiRegion._region_health)}_{datetime.utcnow().timestamp()}",
            "region_id": region_id,
            "is_healthy": is_healthy,
            "response_time_ms": response_time_ms,
            "error_message": error_message,
            "checked_at": datetime.utcnow().isoformat()
        }

        MultiRegion._region_health.append(health_check)

        # Update region status
        region["last_health_check"] = health_check["checked_at"]

        if not is_healthy:
            if region["status"] == RegionStatus.ACTIVE:
                region["status"] = RegionStatus.DEGRADED
        else:
            if region["status"] == RegionStatus.DEGRADED:
                region["status"] = RegionStatus.ACTIVE

        # Update average latency
        recent_checks = [
            c for c in MultiRegion._region_health
            if c["region_id"] == region_id and c["is_healthy"]
        ][-20:]

        if recent_checks:
            region["average_latency_ms"] = statistics.mean(
                c["response_time_ms"] for c in recent_checks
            )

        # Keep only last 1000 health checks
        MultiRegion._region_health = MultiRegion._region_health[-1000:]

        return health_check

    @staticmethod
    def configure_traffic_routing(
        session,
        route_id: str,
        service_name: str,
        routing_mode: TrafficRoutingMode,
        region_weights: Optional[Dict[str, float]] = None
    ) -> dict:
        """Configure traffic routing across regions."""
        if route_id in MultiRegion._traffic_routes:
            raise ValueError(f"Traffic route already exists: {route_id}")

        route = {
            "route_id": route_id,
            "service_name": service_name,
            "routing_mode": routing_mode,
            "region_weights": region_weights or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "enabled": True
        }

        # Validate weights if provided
        if region_weights:
            total_weight = sum(region_weights.values())
            if abs(total_weight - 100.0) > 0.01:
                raise ValueError("Region weights must sum to 100")

        MultiRegion._traffic_routes[route_id] = route

        return route

    @staticmethod
    def update_replication_status(
        session,
        replication_id: str,
        source_region: str,
        target_region: str,
        status: str,
        lag_seconds: float,
        bytes_pending: int = 0
    ) -> dict:
        """Update cross-region replication status."""
        replication = {
            "replication_id": replication_id,
            "source_region": source_region,
            "target_region": target_region,
            "status": status,
            "lag_seconds": lag_seconds,
            "bytes_pending": bytes_pending,
            "updated_at": datetime.utcnow().isoformat(),
            "is_healthy": lag_seconds < 60  # Consider healthy if lag < 1 minute
        }

        MultiRegion._replication_status[replication_id] = replication

        return replication

    @staticmethod
    def get_region_status(session, region_id: str) -> dict:
        """Get comprehensive region status."""
        region = MultiRegion._regions.get(region_id)
        if not region:
            raise ValueError(f"Region not found: {region_id}")

        # Get recent health checks
        recent_checks = [
            c for c in MultiRegion._region_health
            if c["region_id"] == region_id
        ][-10:]

        health_score = 0.0
        if recent_checks:
            healthy_count = sum(1 for c in recent_checks if c["is_healthy"])
            health_score = (healthy_count / len(recent_checks)) * 100

        # Get active deployments
        active_deployments = [
            d for d in MultiRegion._deployments.values()
            if region_id in d["target_regions"]
            and d["status"] == DeploymentStatus.IN_PROGRESS
        ]

        # Get replication status
        replications = [
            r for r in MultiRegion._replication_status.values()
            if r["source_region"] == region_id or r["target_region"] == region_id
        ]

        return {
            "region_id": region_id,
            "name": region["name"],
            "location": region["location"],
            "status": region["status"],
            "enabled": region["enabled"],
            "health_score": health_score,
            "average_latency_ms": region["average_latency_ms"],
            "current_load": region["current_load"],
            "capacity": region["capacity"],
            "load_percentage": (region["current_load"] / region["capacity"] * 100) if region["capacity"] > 0 else 0,
            "total_deployments": region["total_deployments"],
            "successful_deployments": region["successful_deployments"],
            "failed_deployments": region["failed_deployments"],
            "success_rate": (region["successful_deployments"] / region["total_deployments"] * 100) if region["total_deployments"] > 0 else 0,
            "active_deployments": len(active_deployments),
            "replications": replications,
            "last_health_check": region["last_health_check"],
            "checked_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def failover_region(
        session,
        source_region: str,
        target_region: str,
        reason: str
    ) -> dict:
        """Failover from one region to another."""
        source = MultiRegion._regions.get(source_region)
        target = MultiRegion._regions.get(target_region)

        if not source or not target:
            raise ValueError("Invalid source or target region")

        if target["status"] == RegionStatus.OFFLINE:
            raise ValueError(f"Target region is offline: {target_region}")

        # Mark source as maintenance
        old_status = source["status"]
        source["status"] = RegionStatus.MAINTENANCE

        # Transfer load to target
        target["current_load"] += source["current_load"]
        source["current_load"] = 0

        failover = {
            "failover_id": f"failover_{datetime.utcnow().timestamp()}",
            "source_region": source_region,
            "target_region": target_region,
            "reason": reason,
            "source_previous_status": old_status,
            "load_transferred": source["current_load"],
            "executed_at": datetime.utcnow().isoformat()
        }

        return failover

    @staticmethod
    def get_deployment_status(session, deployment_id: str) -> dict:
        """Get deployment status."""
        deployment = MultiRegion._deployments.get(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment not found: {deployment_id}")

        # Calculate progress
        progress = 0.0
        if deployment["total_regions"] > 0:
            progress = (deployment["completed_regions"] / deployment["total_regions"]) * 100

        # Calculate duration
        duration = None
        if deployment["started_at"]:
            if deployment["completed_at"]:
                start = datetime.fromisoformat(deployment["started_at"])
                end = datetime.fromisoformat(deployment["completed_at"])
                duration = (end - start).total_seconds()
            else:
                start = datetime.fromisoformat(deployment["started_at"])
                duration = (datetime.utcnow() - start).total_seconds()

        return {
            "deployment_id": deployment_id,
            "name": deployment["name"],
            "service_name": deployment["service_name"],
            "version": deployment["version"],
            "status": deployment["status"],
            "strategy": deployment["strategy"],
            "progress_percent": progress,
            "total_regions": deployment["total_regions"],
            "completed_regions": deployment["completed_regions"],
            "failed_regions": deployment["failed_regions"],
            "current_region": deployment["current_region"],
            "region_status": deployment["region_status"],
            "duration_seconds": duration,
            "started_at": deployment["started_at"],
            "completed_at": deployment["completed_at"]
        }

    @staticmethod
    def get_global_status(session) -> dict:
        """Get global multi-region status."""
        total_regions = len(MultiRegion._regions)
        active_regions = sum(1 for r in MultiRegion._regions.values() if r["status"] == RegionStatus.ACTIVE)
        degraded_regions = sum(1 for r in MultiRegion._regions.values() if r["status"] == RegionStatus.DEGRADED)
        offline_regions = sum(1 for r in MultiRegion._regions.values() if r["status"] == RegionStatus.OFFLINE)

        # Calculate global health
        global_health = 0.0
        if total_regions > 0:
            global_health = (active_regions / total_regions) * 100

        # Get active deployments
        active_deployments = sum(
            1 for d in MultiRegion._deployments.values()
            if d["status"] == DeploymentStatus.IN_PROGRESS
        )

        # Check replication health
        unhealthy_replications = sum(
            1 for r in MultiRegion._replication_status.values()
            if not r["is_healthy"]
        )

        return {
            "total_regions": total_regions,
            "active_regions": active_regions,
            "degraded_regions": degraded_regions,
            "offline_regions": offline_regions,
            "global_health": global_health,
            "active_deployments": active_deployments,
            "total_deployments": len(MultiRegion._deployments),
            "total_traffic_routes": len(MultiRegion._traffic_routes),
            "replication_pairs": len(MultiRegion._replication_status),
            "unhealthy_replications": unhealthy_replications,
            "checked_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get multi-region statistics."""
        # Region stats
        regions_by_status = defaultdict(int)
        for region in MultiRegion._regions.values():
            regions_by_status[region["status"]] += 1

        # Deployment stats
        deployments_by_status = defaultdict(int)
        deployments_by_strategy = defaultdict(int)
        for deployment in MultiRegion._deployments.values():
            deployments_by_status[deployment["status"]] += 1
            deployments_by_strategy[deployment["strategy"]] += 1

        # Health check stats
        total_checks = len(MultiRegion._region_health)
        healthy_checks = sum(1 for c in MultiRegion._region_health if c["is_healthy"])

        # Calculate average latency across all regions
        avg_latencies = [r["average_latency_ms"] for r in MultiRegion._regions.values() if r["average_latency_ms"] > 0]
        global_avg_latency = statistics.mean(avg_latencies) if avg_latencies else 0.0

        return {
            "regions": {
                "total": len(MultiRegion._regions),
                "by_status": dict(regions_by_status)
            },
            "deployments": {
                "total": len(MultiRegion._deployments),
                "by_status": dict(deployments_by_status),
                "by_strategy": dict(deployments_by_strategy),
                "history_count": len(MultiRegion._deployment_history)
            },
            "health_checks": {
                "total": total_checks,
                "healthy": healthy_checks,
                "unhealthy": total_checks - healthy_checks,
                "health_rate": (healthy_checks / total_checks * 100) if total_checks > 0 else 0
            },
            "traffic_routing": {
                "total_routes": len(MultiRegion._traffic_routes)
            },
            "replication": {
                "total_pairs": len(MultiRegion._replication_status),
                "healthy": sum(1 for r in MultiRegion._replication_status.values() if r["is_healthy"]),
                "unhealthy": sum(1 for r in MultiRegion._replication_status.values() if not r["is_healthy"])
            },
            "performance": {
                "global_avg_latency_ms": global_avg_latency
            }
        }
