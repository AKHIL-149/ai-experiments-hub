"""
Agent Versioning and Rollback

Provides version control, deployment strategies, and rollback capabilities for agents.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import uuid
import hashlib


class VersionStatus:
    """Version status"""
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    RETIRED = "retired"


class DeploymentStrategy:
    """Deployment strategies"""
    IMMEDIATE = "immediate"
    CANARY = "canary"
    BLUE_GREEN = "blue_green"
    ROLLING = "rolling"
    SCHEDULED = "scheduled"


class DeploymentStatus:
    """Deployment status"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class RollbackReason:
    """Rollback reasons"""
    ERRORS = "errors"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    USER_REQUEST = "user_request"
    VALIDATION_FAILURE = "validation_failure"
    EMERGENCY = "emergency"


class AgentVersioning:
    """Agent Versioning and Rollback service"""

    # In-memory storage
    _versions = {}
    _agent_versions = defaultdict(list)
    _deployments = {}
    _rollbacks = defaultdict(list)
    _version_comparisons = {}
    _canary_deployments = {}
    _traffic_splits = defaultdict(dict)

    @staticmethod
    def create_version(
        session,
        agent_id: str,
        version_number: str,
        code_hash: str,
        configuration: dict,
        dependencies: Optional[List[str]] = None,
        description: Optional[str] = None,
        changelog: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create new agent version.

        Args:
            session: Database session
            agent_id: Agent ID
            version_number: Version number (e.g., "1.2.3")
            code_hash: Hash of agent code
            configuration: Version configuration
            dependencies: List of dependencies
            description: Version description
            changelog: Change log
            metadata: Additional metadata

        Returns:
            Created version
        """
        version_id = f"version_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        version = {
            "id": version_id,
            "agent_id": agent_id,
            "version_number": version_number,
            "code_hash": code_hash,
            "configuration": configuration,
            "dependencies": dependencies or [],
            "status": VersionStatus.DRAFT,
            "description": description,
            "changelog": changelog,
            "metadata": metadata or {},
            "created_at": now.isoformat(),
            "created_by": metadata.get("created_by") if metadata else None,
            "activated_at": None,
            "deprecated_at": None,
            "retired_at": None,
            "deployment_count": 0,
            "active_deployments": 0,
            "rollback_count": 0,
            "is_current": False
        }

        AgentVersioning._versions[version_id] = version
        AgentVersioning._agent_versions[agent_id].append(version_id)

        return version

    @staticmethod
    def deploy_version(
        session,
        version_id: str,
        strategy: str = DeploymentStrategy.IMMEDIATE,
        target_percentage: Optional[int] = None,
        schedule_at: Optional[datetime] = None,
        validation_checks: Optional[List[str]] = None,
        rollback_on_error: bool = True
    ) -> dict:
        """
        Deploy agent version.

        Args:
            session: Database session
            version_id: Version ID to deploy
            strategy: Deployment strategy
            target_percentage: Target traffic percentage (for canary)
            schedule_at: Schedule deployment time
            validation_checks: Pre-deployment validation checks
            rollback_on_error: Auto-rollback on error

        Returns:
            Deployment record
        """
        version = AgentVersioning._versions.get(version_id)
        if not version:
            raise ValueError(f"Version not found: {version_id}")

        deployment_id = f"deploy_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # Determine status based on strategy
        if schedule_at and schedule_at > now:
            status = DeploymentStatus.PENDING
        else:
            status = DeploymentStatus.IN_PROGRESS

        deployment = {
            "id": deployment_id,
            "version_id": version_id,
            "agent_id": version["agent_id"],
            "version_number": version["version_number"],
            "strategy": strategy,
            "status": status,
            "target_percentage": target_percentage,
            "current_percentage": 0 if strategy == DeploymentStrategy.CANARY else 100,
            "schedule_at": schedule_at.isoformat() if schedule_at else None,
            "started_at": now.isoformat() if status == DeploymentStatus.IN_PROGRESS else None,
            "completed_at": None,
            "validation_checks": validation_checks or [],
            "validation_results": {},
            "rollback_on_error": rollback_on_error,
            "error_count": 0,
            "errors": [],
            "previous_version_id": AgentVersioning._get_current_version(version["agent_id"])
        }

        AgentVersioning._deployments[deployment_id] = deployment

        # Handle immediate deployment
        if status == DeploymentStatus.IN_PROGRESS:
            if strategy == DeploymentStrategy.IMMEDIATE:
                AgentVersioning._complete_deployment(deployment_id)
            elif strategy == DeploymentStrategy.CANARY:
                AgentVersioning._setup_canary_deployment(deployment_id, target_percentage or 10)

        # Update version stats
        version["deployment_count"] += 1
        version["active_deployments"] += 1

        return deployment

    @staticmethod
    def rollback_version(
        session,
        agent_id: str,
        target_version_id: Optional[str] = None,
        reason: str = RollbackReason.USER_REQUEST,
        description: Optional[str] = None
    ) -> dict:
        """
        Rollback to previous version.

        Args:
            session: Database session
            agent_id: Agent ID
            target_version_id: Optional specific version to rollback to
            reason: Rollback reason
            description: Rollback description

        Returns:
            Rollback record
        """
        current_version_id = AgentVersioning._get_current_version(agent_id)
        if not current_version_id:
            raise ValueError(f"No current version found for agent: {agent_id}")

        # Determine target version
        if target_version_id:
            target_version = AgentVersioning._versions.get(target_version_id)
            if not target_version or target_version["agent_id"] != agent_id:
                raise ValueError(f"Invalid target version: {target_version_id}")
        else:
            # Get previous version
            target_version_id = AgentVersioning._get_previous_version(agent_id, current_version_id)
            if not target_version_id:
                raise ValueError(f"No previous version found for agent: {agent_id}")
            target_version = AgentVersioning._versions[target_version_id]

        rollback_id = f"rollback_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        rollback = {
            "id": rollback_id,
            "agent_id": agent_id,
            "from_version_id": current_version_id,
            "from_version_number": AgentVersioning._versions[current_version_id]["version_number"],
            "to_version_id": target_version_id,
            "to_version_number": target_version["version_number"],
            "reason": reason,
            "description": description,
            "initiated_at": now.isoformat(),
            "completed_at": None,
            "status": DeploymentStatus.IN_PROGRESS,
            "success": False
        }

        # Perform rollback
        AgentVersioning._activate_version(target_version_id)
        AgentVersioning._deactivate_version(current_version_id)

        rollback["completed_at"] = datetime.utcnow().isoformat()
        rollback["status"] = DeploymentStatus.COMPLETED
        rollback["success"] = True

        AgentVersioning._rollbacks[agent_id].append(rollback)

        # Update version stats
        AgentVersioning._versions[current_version_id]["rollback_count"] += 1

        return rollback

    @staticmethod
    def compare_versions(
        session,
        version_id_1: str,
        version_id_2: str,
        include_diff: bool = True
    ) -> dict:
        """
        Compare two versions.

        Args:
            session: Database session
            version_id_1: First version ID
            version_id_2: Second version ID
            include_diff: Include configuration diff

        Returns:
            Comparison result
        """
        version1 = AgentVersioning._versions.get(version_id_1)
        version2 = AgentVersioning._versions.get(version_id_2)

        if not version1 or not version2:
            raise ValueError("One or both versions not found")

        if version1["agent_id"] != version2["agent_id"]:
            raise ValueError("Versions belong to different agents")

        comparison_id = f"comparison_{uuid.uuid4().hex[:12]}"

        comparison = {
            "id": comparison_id,
            "agent_id": version1["agent_id"],
            "version_1": {
                "id": version_id_1,
                "version_number": version1["version_number"],
                "code_hash": version1["code_hash"],
                "status": version1["status"],
                "created_at": version1["created_at"]
            },
            "version_2": {
                "id": version_id_2,
                "version_number": version2["version_number"],
                "code_hash": version2["code_hash"],
                "status": version2["status"],
                "created_at": version2["created_at"]
            },
            "code_changed": version1["code_hash"] != version2["code_hash"],
            "dependencies_changed": version1["dependencies"] != version2["dependencies"],
            "compared_at": datetime.utcnow().isoformat()
        }

        if include_diff:
            comparison["configuration_diff"] = AgentVersioning._compute_config_diff(
                version1["configuration"],
                version2["configuration"]
            )
            comparison["dependencies_diff"] = AgentVersioning._compute_list_diff(
                version1["dependencies"],
                version2["dependencies"]
            )

        AgentVersioning._version_comparisons[comparison_id] = comparison
        return comparison

    @staticmethod
    def get_version_history(
        session,
        agent_id: str,
        status: Optional[str] = None,
        limit: int = 50
    ) -> dict:
        """
        Get version history for agent.

        Args:
            session: Database session
            agent_id: Agent ID
            status: Filter by status
            limit: Maximum versions to return

        Returns:
            Version history
        """
        version_ids = AgentVersioning._agent_versions.get(agent_id, [])
        versions = [AgentVersioning._versions[vid] for vid in version_ids if vid in AgentVersioning._versions]

        # Apply filters
        if status:
            versions = [v for v in versions if v["status"] == status]

        # Sort by created_at descending
        versions.sort(key=lambda x: x["created_at"], reverse=True)

        # Apply limit
        versions = versions[:limit]

        # Get current version
        current_version_id = AgentVersioning._get_current_version(agent_id)

        return {
            "agent_id": agent_id,
            "versions": versions,
            "total_versions": len(AgentVersioning._agent_versions.get(agent_id, [])),
            "returned_count": len(versions),
            "current_version_id": current_version_id
        }

    @staticmethod
    def get_deployment_status(
        session,
        deployment_id: str
    ) -> dict:
        """
        Get deployment status.

        Args:
            session: Database session
            deployment_id: Deployment ID

        Returns:
            Deployment status
        """
        deployment = AgentVersioning._deployments.get(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment not found: {deployment_id}")

        # Get canary deployment info if applicable
        if deployment["strategy"] == DeploymentStrategy.CANARY:
            canary_info = AgentVersioning._canary_deployments.get(deployment_id, {})
            deployment["canary_info"] = canary_info

        return deployment

    @staticmethod
    def promote_canary(
        session,
        deployment_id: str,
        target_percentage: int = 100
    ) -> dict:
        """
        Promote canary deployment.

        Args:
            session: Database session
            deployment_id: Deployment ID
            target_percentage: Target traffic percentage

        Returns:
            Updated deployment
        """
        deployment = AgentVersioning._deployments.get(deployment_id)
        if not deployment:
            raise ValueError(f"Deployment not found: {deployment_id}")

        if deployment["strategy"] != DeploymentStrategy.CANARY:
            raise ValueError("Not a canary deployment")

        deployment["current_percentage"] = target_percentage

        if target_percentage >= 100:
            AgentVersioning._complete_deployment(deployment_id)

        return deployment

    @staticmethod
    def list_rollbacks(
        session,
        agent_id: Optional[str] = None,
        limit: int = 50
    ) -> dict:
        """
        List rollback history.

        Args:
            session: Database session
            agent_id: Filter by agent
            limit: Maximum rollbacks to return

        Returns:
            Rollback list
        """
        rollbacks = []
        for aid, rollback_list in AgentVersioning._rollbacks.items():
            if agent_id and aid != agent_id:
                continue
            rollbacks.extend(rollback_list)

        # Sort by initiated_at descending
        rollbacks.sort(key=lambda x: x["initiated_at"], reverse=True)

        # Apply limit
        rollbacks = rollbacks[:limit]

        return {
            "rollbacks": rollbacks,
            "total_rollbacks": sum(len(r) for r in AgentVersioning._rollbacks.values()),
            "returned_count": len(rollbacks)
        }

    @staticmethod
    def deprecate_version(
        session,
        version_id: str,
        reason: Optional[str] = None
    ) -> dict:
        """
        Deprecate version.

        Args:
            session: Database session
            version_id: Version ID
            reason: Deprecation reason

        Returns:
            Updated version
        """
        version = AgentVersioning._versions.get(version_id)
        if not version:
            raise ValueError(f"Version not found: {version_id}")

        if version["is_current"]:
            raise ValueError("Cannot deprecate current active version")

        version["status"] = VersionStatus.DEPRECATED
        version["deprecated_at"] = datetime.utcnow().isoformat()
        if reason:
            version["metadata"]["deprecation_reason"] = reason

        return version

    @staticmethod
    def get_statistics(session) -> dict:
        """Get versioning statistics"""
        versions = list(AgentVersioning._versions.values())
        deployments = list(AgentVersioning._deployments.values())

        # Status distribution
        status_dist = defaultdict(int)
        for v in versions:
            status_dist[v["status"]] += 1

        # Strategy distribution
        strategy_dist = defaultdict(int)
        for d in deployments:
            strategy_dist[d["strategy"]] += 1

        # Deployment status distribution
        deploy_status_dist = defaultdict(int)
        for d in deployments:
            deploy_status_dist[d["status"]] += 1

        # Total rollbacks
        total_rollbacks = sum(len(r) for r in AgentVersioning._rollbacks.values())

        # Agents with versions
        agents_with_versions = len(AgentVersioning._agent_versions)

        # Active versions
        active_versions = len([v for v in versions if v["status"] == VersionStatus.ACTIVE])

        return {
            "total_versions": len(versions),
            "active_versions": active_versions,
            "deprecated_versions": len([v for v in versions if v["status"] == VersionStatus.DEPRECATED]),
            "version_status_distribution": dict(status_dist),
            "total_deployments": len(deployments),
            "active_deployments": len([d for d in deployments if d["status"] == DeploymentStatus.IN_PROGRESS]),
            "completed_deployments": len([d for d in deployments if d["status"] == DeploymentStatus.COMPLETED]),
            "failed_deployments": len([d for d in deployments if d["status"] == DeploymentStatus.FAILED]),
            "deployment_status_distribution": dict(deploy_status_dist),
            "deployment_strategy_distribution": dict(strategy_dist),
            "total_rollbacks": total_rollbacks,
            "agents_with_versions": agents_with_versions,
            "total_comparisons": len(AgentVersioning._version_comparisons)
        }

    # Helper methods
    @staticmethod
    def _get_current_version(agent_id: str) -> Optional[str]:
        """Get current active version for agent"""
        version_ids = AgentVersioning._agent_versions.get(agent_id, [])
        for vid in version_ids:
            version = AgentVersioning._versions.get(vid)
            if version and version["is_current"]:
                return vid
        return None

    @staticmethod
    def _get_previous_version(agent_id: str, current_version_id: str) -> Optional[str]:
        """Get previous version before current"""
        version_ids = AgentVersioning._agent_versions.get(agent_id, [])
        versions = [(vid, AgentVersioning._versions[vid]) for vid in version_ids if vid in AgentVersioning._versions]
        versions.sort(key=lambda x: x[1]["created_at"], reverse=True)

        # Find current version index
        for i, (vid, _) in enumerate(versions):
            if vid == current_version_id:
                # Return next version (previous in time)
                if i + 1 < len(versions):
                    return versions[i + 1][0]
                break
        return None

    @staticmethod
    def _activate_version(version_id: str):
        """Activate version"""
        version = AgentVersioning._versions.get(version_id)
        if not version:
            return

        # Deactivate other versions for this agent
        for vid in AgentVersioning._agent_versions[version["agent_id"]]:
            if vid != version_id:
                other_version = AgentVersioning._versions.get(vid)
                if other_version and other_version["is_current"]:
                    other_version["is_current"] = False

        version["status"] = VersionStatus.ACTIVE
        version["is_current"] = True
        version["activated_at"] = datetime.utcnow().isoformat()

    @staticmethod
    def _deactivate_version(version_id: str):
        """Deactivate version"""
        version = AgentVersioning._versions.get(version_id)
        if not version:
            return

        version["is_current"] = False

    @staticmethod
    def _complete_deployment(deployment_id: str):
        """Complete deployment"""
        deployment = AgentVersioning._deployments.get(deployment_id)
        if not deployment:
            return

        deployment["status"] = DeploymentStatus.COMPLETED
        deployment["completed_at"] = datetime.utcnow().isoformat()
        deployment["current_percentage"] = 100

        # Activate version
        AgentVersioning._activate_version(deployment["version_id"])

        # Deactivate previous version
        if deployment["previous_version_id"]:
            AgentVersioning._deactivate_version(deployment["previous_version_id"])

    @staticmethod
    def _setup_canary_deployment(deployment_id: str, initial_percentage: int):
        """Setup canary deployment"""
        deployment = AgentVersioning._deployments.get(deployment_id)
        if not deployment:
            return

        canary_info = {
            "deployment_id": deployment_id,
            "initial_percentage": initial_percentage,
            "current_percentage": initial_percentage,
            "target_percentage": deployment.get("target_percentage", 100),
            "started_at": datetime.utcnow().isoformat(),
            "phase": "initial",
            "metrics": {
                "requests": 0,
                "errors": 0,
                "avg_latency_ms": 0
            }
        }

        AgentVersioning._canary_deployments[deployment_id] = canary_info
        deployment["current_percentage"] = initial_percentage

    @staticmethod
    def _compute_config_diff(config1: dict, config2: dict) -> dict:
        """Compute configuration differences"""
        added = {}
        removed = {}
        changed = {}

        all_keys = set(config1.keys()) | set(config2.keys())

        for key in all_keys:
            if key not in config1:
                added[key] = config2[key]
            elif key not in config2:
                removed[key] = config1[key]
            elif config1[key] != config2[key]:
                changed[key] = {
                    "old": config1[key],
                    "new": config2[key]
                }

        return {
            "added": added,
            "removed": removed,
            "changed": changed
        }

    @staticmethod
    def _compute_list_diff(list1: List, list2: List) -> dict:
        """Compute list differences"""
        set1 = set(list1)
        set2 = set(list2)

        return {
            "added": list(set2 - set1),
            "removed": list(set1 - set2),
            "common": list(set1 & set2)
        }
