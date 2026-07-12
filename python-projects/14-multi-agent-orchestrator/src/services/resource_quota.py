"""
Resource Quota Management Service

Provides resource allocation, quota enforcement, usage tracking, and
multi-tenant resource isolation for production environments.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from enum import Enum
import statistics


class ResourceType(str, Enum):
    """Types of resources"""
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"
    API_CALLS = "api_calls"
    TASKS = "tasks"
    AGENTS = "agents"
    WORKFLOWS = "workflows"


class QuotaStatus(str, Enum):
    """Quota status"""
    ACTIVE = "active"
    EXCEEDED = "exceeded"
    WARNING = "warning"
    SUSPENDED = "suspended"


class QuotaPeriod(str, Enum):
    """Quota reset period"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    NEVER = "never"


class EnforcementAction(str, Enum):
    """Action to take when quota exceeded"""
    BLOCK = "block"
    THROTTLE = "throttle"
    ALERT = "alert"
    NONE = "none"


class ResourceQuota:
    """Resource quota management and enforcement"""

    # In-memory storage
    _quotas: Dict[str, Dict] = {}
    _usage_records: List[Dict] = []
    _quota_violations: Dict[str, Dict] = {}
    _tenant_quotas: Dict[str, List[str]] = defaultdict(list)
    _allocation_history: List[Dict] = []
    _quota_overrides: Dict[str, Dict] = {}

    @staticmethod
    def create_quota(
        session,
        quota_id: str,
        name: str,
        tenant_id: str,
        resource_type: ResourceType,
        limit: float,
        warning_threshold: float = 80.0,
        reset_period: QuotaPeriod = QuotaPeriod.MONTHLY,
        enforcement_action: EnforcementAction = EnforcementAction.BLOCK,
        description: Optional[str] = None
    ) -> dict:
        """Create a resource quota."""
        if quota_id in ResourceQuota._quotas:
            raise ValueError(f"Quota already exists: {quota_id}")

        if warning_threshold < 0 or warning_threshold > 100:
            raise ValueError("Warning threshold must be between 0 and 100")

        if limit <= 0:
            raise ValueError("Limit must be greater than 0")

        quota = {
            "quota_id": quota_id,
            "name": name,
            "tenant_id": tenant_id,
            "resource_type": resource_type,
            "limit": limit,
            "warning_threshold": warning_threshold,
            "reset_period": reset_period,
            "enforcement_action": enforcement_action,
            "description": description or "",
            "status": QuotaStatus.ACTIVE,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "current_usage": 0.0,
            "usage_percent": 0.0,
            "last_reset": datetime.utcnow().isoformat(),
            "next_reset": ResourceQuota._calculate_next_reset(reset_period),
            "violation_count": 0,
            "last_violation": None,
            "is_enabled": True
        }

        ResourceQuota._quotas[quota_id] = quota
        ResourceQuota._tenant_quotas[tenant_id].append(quota_id)

        return quota

    @staticmethod
    def _calculate_next_reset(period: QuotaPeriod) -> str:
        """Calculate next quota reset time."""
        now = datetime.utcnow()

        if period == QuotaPeriod.HOURLY:
            next_reset = now + timedelta(hours=1)
        elif period == QuotaPeriod.DAILY:
            next_reset = now + timedelta(days=1)
        elif period == QuotaPeriod.WEEKLY:
            next_reset = now + timedelta(weeks=1)
        elif period == QuotaPeriod.MONTHLY:
            # Approximate month as 30 days
            next_reset = now + timedelta(days=30)
        else:  # NEVER
            next_reset = now + timedelta(days=365 * 100)  # Far future

        return next_reset.isoformat()

    @staticmethod
    def record_usage(
        session,
        quota_id: str,
        amount: float,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Record resource usage against a quota."""
        quota = ResourceQuota._quotas.get(quota_id)
        if not quota:
            raise ValueError(f"Quota not found: {quota_id}")

        if not quota["is_enabled"]:
            raise ValueError(f"Quota is disabled: {quota_id}")

        if quota["status"] == QuotaStatus.SUSPENDED:
            raise ValueError(f"Quota is suspended: {quota_id}")

        # Check if quota needs reset
        ResourceQuota._check_and_reset_quota(quota)

        # Check if usage would exceed quota
        new_usage = quota["current_usage"] + amount
        usage_percent = (new_usage / quota["limit"]) * 100

        # Determine if this is allowed
        can_proceed = True
        action_taken = None

        if usage_percent > 100:
            if quota["enforcement_action"] == EnforcementAction.BLOCK:
                can_proceed = False
                action_taken = "blocked"
            elif quota["enforcement_action"] == EnforcementAction.THROTTLE:
                # Allow but mark for throttling
                can_proceed = True
                action_taken = "throttled"
            elif quota["enforcement_action"] == EnforcementAction.ALERT:
                can_proceed = True
                action_taken = "alert_sent"
            else:  # NONE
                can_proceed = True
                action_taken = "allowed"

            # Record violation if blocked
            if not can_proceed:
                ResourceQuota._record_violation(quota, amount, new_usage)

        # Record usage
        usage_record = {
            "record_id": f"usage_{len(ResourceQuota._usage_records)}_{datetime.utcnow().timestamp()}",
            "quota_id": quota_id,
            "tenant_id": quota["tenant_id"],
            "resource_type": quota["resource_type"],
            "amount": amount,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
            "can_proceed": can_proceed,
            "action_taken": action_taken,
            "usage_before": quota["current_usage"],
            "usage_after": new_usage if can_proceed else quota["current_usage"]
        }

        ResourceQuota._usage_records.append(usage_record)

        # Update quota if allowed
        if can_proceed:
            quota["current_usage"] = new_usage
            quota["usage_percent"] = usage_percent
            quota["updated_at"] = datetime.utcnow().isoformat()

            # Update status based on usage
            if usage_percent >= 100:
                quota["status"] = QuotaStatus.EXCEEDED
            elif usage_percent >= quota["warning_threshold"]:
                quota["status"] = QuotaStatus.WARNING
            else:
                quota["status"] = QuotaStatus.ACTIVE

        # Keep only last 90 days of usage records
        cutoff = datetime.utcnow() - timedelta(days=90)
        cutoff_iso = cutoff.isoformat()
        ResourceQuota._usage_records = [
            r for r in ResourceQuota._usage_records
            if r["timestamp"] >= cutoff_iso
        ]

        return usage_record

    @staticmethod
    def _check_and_reset_quota(quota: dict):
        """Check if quota needs to be reset based on period."""
        if quota["reset_period"] == QuotaPeriod.NEVER:
            return

        now = datetime.utcnow()
        next_reset = datetime.fromisoformat(quota["next_reset"])

        if now >= next_reset:
            # Reset quota
            quota["current_usage"] = 0.0
            quota["usage_percent"] = 0.0
            quota["last_reset"] = now.isoformat()
            quota["next_reset"] = ResourceQuota._calculate_next_reset(quota["reset_period"])
            if quota["status"] != QuotaStatus.SUSPENDED:
                quota["status"] = QuotaStatus.ACTIVE

    @staticmethod
    def _record_violation(quota: dict, requested_amount: float, would_be_usage: float):
        """Record a quota violation."""
        violation_id = f"violation_{quota['quota_id']}_{datetime.utcnow().timestamp()}"

        violation = {
            "violation_id": violation_id,
            "quota_id": quota["quota_id"],
            "tenant_id": quota["tenant_id"],
            "resource_type": quota["resource_type"],
            "quota_limit": quota["limit"],
            "current_usage": quota["current_usage"],
            "requested_amount": requested_amount,
            "would_be_usage": would_be_usage,
            "overage": would_be_usage - quota["limit"],
            "overage_percent": ((would_be_usage - quota["limit"]) / quota["limit"]) * 100,
            "enforcement_action": quota["enforcement_action"],
            "occurred_at": datetime.utcnow().isoformat(),
            "resolved": False
        }

        ResourceQuota._quota_violations[violation_id] = violation

        # Update quota stats
        quota["violation_count"] += 1
        quota["last_violation"] = violation["occurred_at"]

    @staticmethod
    def check_quota(session, quota_id: str, amount: float) -> dict:
        """Check if quota allows a certain amount without recording usage."""
        quota = ResourceQuota._quotas.get(quota_id)
        if not quota:
            raise ValueError(f"Quota not found: {quota_id}")

        # Check if quota needs reset
        ResourceQuota._check_and_reset_quota(quota)

        new_usage = quota["current_usage"] + amount
        usage_percent = (new_usage / quota["limit"]) * 100

        is_allowed = usage_percent <= 100 or quota["enforcement_action"] in [
            EnforcementAction.THROTTLE,
            EnforcementAction.ALERT,
            EnforcementAction.NONE
        ]

        return {
            "quota_id": quota_id,
            "is_allowed": is_allowed,
            "current_usage": quota["current_usage"],
            "requested_amount": amount,
            "would_be_usage": new_usage,
            "limit": quota["limit"],
            "usage_percent": usage_percent,
            "remaining": max(0, quota["limit"] - quota["current_usage"]),
            "enforcement_action": quota["enforcement_action"],
            "checked_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_quota_status(session, quota_id: str) -> dict:
        """Get current quota status."""
        quota = ResourceQuota._quotas.get(quota_id)
        if not quota:
            raise ValueError(f"Quota not found: {quota_id}")

        # Check if quota needs reset
        ResourceQuota._check_and_reset_quota(quota)

        # Get recent usage trend
        recent_usage = [
            r for r in ResourceQuota._usage_records
            if r["quota_id"] == quota_id
            and r["timestamp"] >= (datetime.utcnow() - timedelta(hours=24)).isoformat()
        ]

        usage_trend = "stable"
        if len(recent_usage) >= 10:
            # Simple trend analysis
            first_half = recent_usage[:len(recent_usage)//2]
            second_half = recent_usage[len(recent_usage)//2:]

            avg_first = statistics.mean(r["amount"] for r in first_half)
            avg_second = statistics.mean(r["amount"] for r in second_half)

            if avg_second > avg_first * 1.2:
                usage_trend = "increasing"
            elif avg_second < avg_first * 0.8:
                usage_trend = "decreasing"

        return {
            "quota_id": quota_id,
            "name": quota["name"],
            "tenant_id": quota["tenant_id"],
            "resource_type": quota["resource_type"],
            "status": quota["status"],
            "current_usage": quota["current_usage"],
            "limit": quota["limit"],
            "usage_percent": quota["usage_percent"],
            "remaining": max(0, quota["limit"] - quota["current_usage"]),
            "warning_threshold": quota["warning_threshold"],
            "enforcement_action": quota["enforcement_action"],
            "reset_period": quota["reset_period"],
            "last_reset": quota["last_reset"],
            "next_reset": quota["next_reset"],
            "violation_count": quota["violation_count"],
            "last_violation": quota["last_violation"],
            "usage_trend": usage_trend,
            "recent_usage_count": len(recent_usage),
            "is_enabled": quota["is_enabled"],
            "checked_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_tenant_quotas(session, tenant_id: str) -> List[dict]:
        """Get all quotas for a tenant."""
        quota_ids = ResourceQuota._tenant_quotas.get(tenant_id, [])
        quotas = [ResourceQuota._quotas[qid] for qid in quota_ids if qid in ResourceQuota._quotas]

        # Check and reset all quotas
        for quota in quotas:
            ResourceQuota._check_and_reset_quota(quota)

        return quotas

    @staticmethod
    def update_quota(
        session,
        quota_id: str,
        limit: Optional[float] = None,
        warning_threshold: Optional[float] = None,
        enforcement_action: Optional[EnforcementAction] = None,
        is_enabled: Optional[bool] = None
    ) -> dict:
        """Update quota parameters."""
        quota = ResourceQuota._quotas.get(quota_id)
        if not quota:
            raise ValueError(f"Quota not found: {quota_id}")

        if limit is not None:
            if limit <= 0:
                raise ValueError("Limit must be greater than 0")
            quota["limit"] = limit
            quota["usage_percent"] = (quota["current_usage"] / limit) * 100

        if warning_threshold is not None:
            if warning_threshold < 0 or warning_threshold > 100:
                raise ValueError("Warning threshold must be between 0 and 100")
            quota["warning_threshold"] = warning_threshold

        if enforcement_action is not None:
            quota["enforcement_action"] = enforcement_action

        if is_enabled is not None:
            quota["is_enabled"] = is_enabled

        quota["updated_at"] = datetime.utcnow().isoformat()

        # Update status based on new limit
        if quota["usage_percent"] >= 100:
            quota["status"] = QuotaStatus.EXCEEDED
        elif quota["usage_percent"] >= quota["warning_threshold"]:
            quota["status"] = QuotaStatus.WARNING
        else:
            quota["status"] = QuotaStatus.ACTIVE

        return quota

    @staticmethod
    def reset_quota(session, quota_id: str) -> dict:
        """Manually reset a quota."""
        quota = ResourceQuota._quotas.get(quota_id)
        if not quota:
            raise ValueError(f"Quota not found: {quota_id}")

        old_usage = quota["current_usage"]

        quota["current_usage"] = 0.0
        quota["usage_percent"] = 0.0
        quota["last_reset"] = datetime.utcnow().isoformat()
        quota["next_reset"] = ResourceQuota._calculate_next_reset(quota["reset_period"])
        if quota["status"] != QuotaStatus.SUSPENDED:
            quota["status"] = QuotaStatus.ACTIVE
        quota["updated_at"] = datetime.utcnow().isoformat()

        return {
            "quota_id": quota_id,
            "reset": True,
            "previous_usage": old_usage,
            "reset_at": quota["last_reset"]
        }

    @staticmethod
    def create_quota_override(
        session,
        override_id: str,
        quota_id: str,
        temporary_limit: float,
        expires_at: str,
        reason: str
    ) -> dict:
        """Create a temporary quota override."""
        quota = ResourceQuota._quotas.get(quota_id)
        if not quota:
            raise ValueError(f"Quota not found: {quota_id}")

        if temporary_limit <= 0:
            raise ValueError("Temporary limit must be greater than 0")

        override = {
            "override_id": override_id,
            "quota_id": quota_id,
            "original_limit": quota["limit"],
            "temporary_limit": temporary_limit,
            "reason": reason,
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": expires_at,
            "is_active": True
        }

        ResourceQuota._quota_overrides[override_id] = override

        # Apply override
        quota["limit"] = temporary_limit
        quota["usage_percent"] = (quota["current_usage"] / temporary_limit) * 100

        return override

    @staticmethod
    def remove_quota_override(session, override_id: str) -> dict:
        """Remove a quota override."""
        override = ResourceQuota._quota_overrides.get(override_id)
        if not override:
            raise ValueError(f"Override not found: {override_id}")

        quota = ResourceQuota._quotas.get(override["quota_id"])
        if quota:
            # Restore original limit
            quota["limit"] = override["original_limit"]
            quota["usage_percent"] = (quota["current_usage"] / override["original_limit"]) * 100

        override["is_active"] = False

        return {
            "override_id": override_id,
            "removed": True,
            "quota_id": override["quota_id"],
            "restored_limit": override["original_limit"]
        }

    @staticmethod
    def get_violations(
        session,
        tenant_id: Optional[str] = None,
        quota_id: Optional[str] = None,
        resolved: Optional[bool] = None
    ) -> List[dict]:
        """Get quota violations."""
        violations = list(ResourceQuota._quota_violations.values())

        if tenant_id:
            violations = [v for v in violations if v["tenant_id"] == tenant_id]

        if quota_id:
            violations = [v for v in violations if v["quota_id"] == quota_id]

        if resolved is not None:
            violations = [v for v in violations if v["resolved"] == resolved]

        # Sort by occurrence time descending
        violations.sort(key=lambda x: x["occurred_at"], reverse=True)

        return violations

    @staticmethod
    def get_usage_history(
        session,
        quota_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        resource_type: Optional[ResourceType] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100
    ) -> List[dict]:
        """Get usage history."""
        records = ResourceQuota._usage_records.copy()

        if quota_id:
            records = [r for r in records if r["quota_id"] == quota_id]

        if tenant_id:
            records = [r for r in records if r["tenant_id"] == tenant_id]

        if resource_type:
            records = [r for r in records if r["resource_type"] == resource_type]

        if start_time:
            records = [r for r in records if r["timestamp"] >= start_time]

        if end_time:
            records = [r for r in records if r["timestamp"] <= end_time]

        # Sort by timestamp descending
        records.sort(key=lambda x: x["timestamp"], reverse=True)

        return records[:limit]

    @staticmethod
    def get_tenant_summary(session, tenant_id: str) -> dict:
        """Get quota summary for a tenant."""
        quotas = ResourceQuota.get_tenant_quotas(session, tenant_id)

        total_quotas = len(quotas)
        exceeded_quotas = sum(1 for q in quotas if q["status"] == QuotaStatus.EXCEEDED)
        warning_quotas = sum(1 for q in quotas if q["status"] == QuotaStatus.WARNING)

        # Get violations for this tenant
        violations = ResourceQuota.get_violations(session, tenant_id=tenant_id, resolved=False)

        # Calculate overall usage by resource type
        usage_by_type = defaultdict(lambda: {"usage": 0.0, "limit": 0.0})
        for quota in quotas:
            rt = quota["resource_type"]
            usage_by_type[rt]["usage"] += quota["current_usage"]
            usage_by_type[rt]["limit"] += quota["limit"]

        # Calculate percentages
        for rt in usage_by_type:
            if usage_by_type[rt]["limit"] > 0:
                usage_by_type[rt]["percent"] = (
                    usage_by_type[rt]["usage"] / usage_by_type[rt]["limit"]
                ) * 100
            else:
                usage_by_type[rt]["percent"] = 0.0

        return {
            "tenant_id": tenant_id,
            "total_quotas": total_quotas,
            "quota_status": {
                "active": sum(1 for q in quotas if q["status"] == QuotaStatus.ACTIVE),
                "warning": warning_quotas,
                "exceeded": exceeded_quotas,
                "suspended": sum(1 for q in quotas if q["status"] == QuotaStatus.SUSPENDED)
            },
            "active_violations": len(violations),
            "usage_by_resource": dict(usage_by_type),
            "checked_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get quota management statistics."""
        # Quota stats
        total_quotas = len(ResourceQuota._quotas)
        quotas_by_status = defaultdict(int)
        quotas_by_type = defaultdict(int)

        for quota in ResourceQuota._quotas.values():
            quotas_by_status[quota["status"]] += 1
            quotas_by_type[quota["resource_type"]] += 1

        # Usage stats
        total_usage_records = len(ResourceQuota._usage_records)
        blocked_requests = sum(1 for r in ResourceQuota._usage_records if not r["can_proceed"])

        # Violation stats
        total_violations = len(ResourceQuota._quota_violations)
        active_violations = sum(1 for v in ResourceQuota._quota_violations.values() if not v["resolved"])

        # Tenant stats
        total_tenants = len(ResourceQuota._tenant_quotas)

        # Override stats
        active_overrides = sum(1 for o in ResourceQuota._quota_overrides.values() if o["is_active"])

        return {
            "quotas": {
                "total": total_quotas,
                "by_status": dict(quotas_by_status),
                "by_type": dict(quotas_by_type)
            },
            "usage": {
                "total_records": total_usage_records,
                "blocked_requests": blocked_requests,
                "block_rate": (blocked_requests / total_usage_records * 100) if total_usage_records > 0 else 0
            },
            "violations": {
                "total": total_violations,
                "active": active_violations,
                "resolved": total_violations - active_violations
            },
            "tenants": {
                "total": total_tenants
            },
            "overrides": {
                "active": active_overrides,
                "total": len(ResourceQuota._quota_overrides)
            }
        }
