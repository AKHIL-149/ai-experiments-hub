"""
Data Retention and Archival Service

Provides automated data lifecycle management, retention policies, and archival.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import uuid
import json


class RetentionPeriod:
    """Retention period constants"""
    DAYS_7 = "7_days"
    DAYS_30 = "30_days"
    DAYS_90 = "90_days"
    DAYS_180 = "180_days"
    YEAR_1 = "1_year"
    YEAR_3 = "3_years"
    YEAR_7 = "7_years"
    PERMANENT = "permanent"


class DataLifecycleStage:
    """Data lifecycle stages"""
    ACTIVE = "active"
    WARM = "warm"
    COLD = "cold"
    ARCHIVED = "archived"
    DELETED = "deleted"


class RetentionAction:
    """Retention policy actions"""
    ARCHIVE = "archive"
    DELETE = "delete"
    COMPRESS = "compress"
    ENCRYPT = "encrypt"
    MOVE_TO_COLD = "move_to_cold"


class ComplianceType:
    """Compliance regulation types"""
    GDPR = "gdpr"
    HIPAA = "hipaa"
    SOC2 = "soc2"
    PCI_DSS = "pci_dss"
    CCPA = "ccpa"
    CUSTOM = "custom"


class DataRetention:
    """Data Retention and Archival service"""

    # In-memory storage
    _retention_policies = {}
    _archived_data = {}
    _lifecycle_rules = {}
    _retention_jobs = {}
    _archived_items = defaultdict(list)
    _deletion_queue = []
    _compliance_requirements = {}

    @staticmethod
    def create_retention_policy(
        session,
        name: str,
        data_type: str,
        retention_period: str,
        action: str,
        description: Optional[str] = None,
        compliance_type: Optional[str] = None,
        enabled: bool = True,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create a retention policy.

        Args:
            session: Database session
            name: Policy name
            data_type: Type of data (workflows, tasks, logs, etc.)
            retention_period: How long to retain data
            action: Action to take after period
            description: Policy description
            compliance_type: Compliance regulation
            enabled: Whether policy is enabled
            metadata: Additional metadata

        Returns:
            Created retention policy
        """
        policy_id = f"policy_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # Convert retention period to days
        retention_days = DataRetention._period_to_days(retention_period)

        policy = {
            "id": policy_id,
            "name": name,
            "data_type": data_type,
            "retention_period": retention_period,
            "retention_days": retention_days,
            "action": action,
            "description": description,
            "compliance_type": compliance_type,
            "enabled": enabled,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "last_run_at": None,
            "next_run_at": (now + timedelta(days=1)).isoformat(),
            "items_processed": 0,
            "items_archived": 0,
            "items_deleted": 0,
            "metadata": metadata or {}
        }

        DataRetention._retention_policies[policy_id] = policy
        return policy

    @staticmethod
    def create_lifecycle_rule(
        session,
        name: str,
        data_type: str,
        stages: List[dict],
        description: Optional[str] = None,
        enabled: bool = True
    ) -> dict:
        """
        Create a data lifecycle rule.

        Args:
            session: Database session
            name: Rule name
            data_type: Type of data
            stages: List of lifecycle stages with transitions
            description: Rule description
            enabled: Whether rule is enabled

        Returns:
            Created lifecycle rule
        """
        rule_id = f"rule_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        rule = {
            "id": rule_id,
            "name": name,
            "data_type": data_type,
            "stages": stages,
            "description": description,
            "enabled": enabled,
            "created_at": now.isoformat(),
            "items_in_lifecycle": 0,
            "current_stage_distribution": defaultdict(int)
        }

        DataRetention._lifecycle_rules[rule_id] = rule
        return rule

    @staticmethod
    def archive_data(
        session,
        data_type: str,
        data_id: str,
        data: dict,
        retention_policy_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Archive data.

        Args:
            session: Database session
            data_type: Type of data
            data_id: Data identifier
            data: Data to archive
            retention_policy_id: Associated retention policy
            metadata: Additional metadata

        Returns:
            Archive record
        """
        archive_id = f"archive_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # Compress data (simplified - in production use actual compression)
        compressed_size = len(json.dumps(data).encode()) * 0.3  # Simulate 70% compression

        archive = {
            "id": archive_id,
            "data_type": data_type,
            "data_id": data_id,
            "archived_data": data,
            "archived_at": now.isoformat(),
            "original_size_bytes": len(json.dumps(data).encode()),
            "compressed_size_bytes": int(compressed_size),
            "compression_ratio": 0.7,
            "retention_policy_id": retention_policy_id,
            "lifecycle_stage": DataLifecycleStage.ARCHIVED,
            "retrieval_count": 0,
            "last_accessed_at": None,
            "expires_at": None,
            "metadata": metadata or {}
        }

        # Set expiration if policy specified
        if retention_policy_id:
            policy = DataRetention._retention_policies.get(retention_policy_id)
            if policy and policy["retention_days"]:
                expires_at = now + timedelta(days=policy["retention_days"])
                archive["expires_at"] = expires_at.isoformat()

        DataRetention._archived_data[archive_id] = archive
        DataRetention._archived_items[data_type].append(archive)

        return archive

    @staticmethod
    def retrieve_archived_data(
        session,
        archive_id: str
    ) -> dict:
        """
        Retrieve archived data.

        Args:
            session: Database session
            archive_id: Archive identifier

        Returns:
            Retrieved archived data
        """
        archive = DataRetention._archived_data.get(archive_id)
        if not archive:
            raise ValueError(f"Archive not found: {archive_id}")

        now = datetime.utcnow()

        # Update access tracking
        archive["retrieval_count"] += 1
        archive["last_accessed_at"] = now.isoformat()

        return {
            "archive_id": archive_id,
            "data_type": archive["data_type"],
            "data_id": archive["data_id"],
            "data": archive["archived_data"],
            "archived_at": archive["archived_at"],
            "retrieval_count": archive["retrieval_count"]
        }

    @staticmethod
    def apply_retention_policy(
        session,
        policy_id: str,
        dry_run: bool = False
    ) -> dict:
        """
        Apply a retention policy.

        Args:
            session: Database session
            policy_id: Policy to apply
            dry_run: If True, don't actually modify data

        Returns:
            Policy application results
        """
        policy = DataRetention._retention_policies.get(policy_id)
        if not policy:
            raise ValueError(f"Policy not found: {policy_id}")

        if not policy["enabled"]:
            raise ValueError(f"Policy is disabled: {policy_id}")

        now = datetime.utcnow()
        cutoff_date = now - timedelta(days=policy["retention_days"])

        # Simulate finding items to process
        # In production, this would query the actual database
        items_to_process = DataRetention._find_items_for_retention(
            data_type=policy["data_type"],
            cutoff_date=cutoff_date
        )

        results = {
            "policy_id": policy_id,
            "policy_name": policy["name"],
            "action": policy["action"],
            "items_found": len(items_to_process),
            "items_processed": 0,
            "items_archived": 0,
            "items_deleted": 0,
            "items_failed": 0,
            "dry_run": dry_run,
            "executed_at": now.isoformat()
        }

        if not dry_run:
            for item in items_to_process:
                try:
                    if policy["action"] == RetentionAction.ARCHIVE:
                        DataRetention.archive_data(
                            session=session,
                            data_type=policy["data_type"],
                            data_id=item["id"],
                            data=item,
                            retention_policy_id=policy_id
                        )
                        results["items_archived"] += 1
                    elif policy["action"] == RetentionAction.DELETE:
                        DataRetention._deletion_queue.append({
                            "data_type": policy["data_type"],
                            "data_id": item["id"],
                            "deleted_at": now.isoformat(),
                            "policy_id": policy_id
                        })
                        results["items_deleted"] += 1

                    results["items_processed"] += 1
                except Exception as e:
                    results["items_failed"] += 1

            # Update policy stats
            policy["last_run_at"] = now.isoformat()
            policy["next_run_at"] = (now + timedelta(days=1)).isoformat()
            policy["items_processed"] += results["items_processed"]
            policy["items_archived"] += results["items_archived"]
            policy["items_deleted"] += results["items_deleted"]

        return results

    @staticmethod
    def transition_lifecycle_stage(
        session,
        data_type: str,
        data_id: str,
        to_stage: str,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Transition data to a different lifecycle stage.

        Args:
            session: Database session
            data_type: Type of data
            data_id: Data identifier
            to_stage: Target lifecycle stage
            metadata: Additional metadata

        Returns:
            Transition record
        """
        transition_id = f"transition_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        transition = {
            "id": transition_id,
            "data_type": data_type,
            "data_id": data_id,
            "to_stage": to_stage,
            "transitioned_at": now.isoformat(),
            "metadata": metadata or {}
        }

        return transition

    @staticmethod
    def schedule_retention_job(
        session,
        name: str,
        policy_ids: List[str],
        schedule_cron: str,
        enabled: bool = True
    ) -> dict:
        """
        Schedule a retention job.

        Args:
            session: Database session
            name: Job name
            policy_ids: Policies to apply
            schedule_cron: Cron schedule
            enabled: Whether job is enabled

        Returns:
            Scheduled job
        """
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        job = {
            "id": job_id,
            "name": name,
            "policy_ids": policy_ids,
            "schedule_cron": schedule_cron,
            "enabled": enabled,
            "created_at": now.isoformat(),
            "last_run_at": None,
            "next_run_at": DataRetention._calculate_next_run(schedule_cron),
            "successful_runs": 0,
            "failed_runs": 0,
            "total_items_processed": 0
        }

        DataRetention._retention_jobs[job_id] = job
        return job

    @staticmethod
    def create_compliance_requirement(
        session,
        name: str,
        compliance_type: str,
        data_types: List[str],
        minimum_retention_days: int,
        maximum_retention_days: Optional[int] = None,
        required_actions: Optional[List[str]] = None,
        description: Optional[str] = None
    ) -> dict:
        """
        Create a compliance requirement.

        Args:
            session: Database session
            name: Requirement name
            compliance_type: Type of compliance
            data_types: Data types covered
            minimum_retention_days: Minimum retention period
            maximum_retention_days: Maximum retention period
            required_actions: Required actions
            description: Requirement description

        Returns:
            Compliance requirement
        """
        requirement_id = f"compliance_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        requirement = {
            "id": requirement_id,
            "name": name,
            "compliance_type": compliance_type,
            "data_types": data_types,
            "minimum_retention_days": minimum_retention_days,
            "maximum_retention_days": maximum_retention_days,
            "required_actions": required_actions or [],
            "description": description,
            "created_at": now.isoformat(),
            "policies_count": 0,
            "compliant": True
        }

        DataRetention._compliance_requirements[requirement_id] = requirement
        return requirement

    @staticmethod
    def list_retention_policies(
        session,
        data_type: Optional[str] = None,
        compliance_type: Optional[str] = None,
        enabled: Optional[bool] = None,
        limit: int = 50
    ) -> dict:
        """
        List retention policies.

        Args:
            session: Database session
            data_type: Filter by data type
            compliance_type: Filter by compliance
            enabled: Filter by enabled status
            limit: Maximum policies to return

        Returns:
            Filtered retention policies
        """
        policies = list(DataRetention._retention_policies.values())

        # Apply filters
        if data_type:
            policies = [p for p in policies if p["data_type"] == data_type]
        if compliance_type:
            policies = [p for p in policies if p.get("compliance_type") == compliance_type]
        if enabled is not None:
            policies = [p for p in policies if p["enabled"] == enabled]

        # Sort by created_at descending
        policies.sort(key=lambda x: x["created_at"], reverse=True)

        # Apply limit
        policies = policies[:limit]

        return {
            "policies": policies,
            "total_policies": len(DataRetention._retention_policies),
            "returned_count": len(policies)
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get data retention statistics"""
        policies = list(DataRetention._retention_policies.values())
        archives = list(DataRetention._archived_data.values())
        jobs = list(DataRetention._retention_jobs.values())

        # Archive statistics
        total_archived_size = sum(a.get("original_size_bytes", 0) for a in archives)
        total_compressed_size = sum(a.get("compressed_size_bytes", 0) for a in archives)

        # Data type distribution
        type_dist = defaultdict(int)
        for archive in archives:
            type_dist[archive["data_type"]] += 1

        # Lifecycle stage distribution
        stage_dist = defaultdict(int)
        for archive in archives:
            stage_dist[archive["lifecycle_stage"]] += 1

        return {
            "total_policies": len(policies),
            "enabled_policies": len([p for p in policies if p["enabled"]]),
            "total_archived_items": len(archives),
            "total_archived_size_bytes": total_archived_size,
            "total_compressed_size_bytes": total_compressed_size,
            "compression_savings_bytes": total_archived_size - total_compressed_size,
            "data_type_distribution": dict(type_dist),
            "lifecycle_stage_distribution": dict(stage_dist),
            "scheduled_jobs": len(jobs),
            "active_jobs": len([j for j in jobs if j["enabled"]]),
            "items_in_deletion_queue": len(DataRetention._deletion_queue),
            "compliance_requirements": len(DataRetention._compliance_requirements)
        }

    @staticmethod
    def _period_to_days(period: str) -> int:
        """Convert retention period to days"""
        period_map = {
            RetentionPeriod.DAYS_7: 7,
            RetentionPeriod.DAYS_30: 30,
            RetentionPeriod.DAYS_90: 90,
            RetentionPeriod.DAYS_180: 180,
            RetentionPeriod.YEAR_1: 365,
            RetentionPeriod.YEAR_3: 1095,
            RetentionPeriod.YEAR_7: 2555,
            RetentionPeriod.PERMANENT: None
        }
        return period_map.get(period, 30)

    @staticmethod
    def _find_items_for_retention(data_type: str, cutoff_date: datetime) -> List[dict]:
        """Find items that need retention processing (simulated)"""
        # In production, this would query the actual database
        # Simulating finding 10 items
        import random
        return [
            {
                "id": f"{data_type}_{i}",
                "created_at": (cutoff_date - timedelta(days=random.randint(1, 100))).isoformat(),
                "data": {"sample": "data"}
            }
            for i in range(10)
        ]

    @staticmethod
    def _calculate_next_run(cron_expression: str) -> str:
        """Calculate next run time from cron (simplified)"""
        now = datetime.utcnow()
        next_run = now + timedelta(days=1)  # Simplified - daily
        return next_run.isoformat()
