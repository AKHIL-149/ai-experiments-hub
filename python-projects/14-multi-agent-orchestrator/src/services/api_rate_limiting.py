"""
API Rate Limiting and Quota Management Service

Provides advanced rate limiting, quota management, and usage tracking.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import uuid


class QuotaTier:
    """Quota tier levels"""
    FREE = "free"
    BASIC = "basic"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"
    UNLIMITED = "unlimited"


class QuotaPeriod:
    """Quota reset period"""
    MINUTE = "minute"
    HOUR = "hour"
    DAY = "day"
    MONTH = "month"


class LimitStatus:
    """Rate limit status"""
    WITHIN_LIMIT = "within_limit"
    APPROACHING_LIMIT = "approaching_limit"
    EXCEEDED = "exceeded"
    BLOCKED = "blocked"


class APIRateLimiting:
    """API Rate Limiting and Quota Management service"""

    # In-memory storage
    _quota_plans = {}
    _user_quotas = {}
    _usage_records = defaultdict(list)
    _rate_limit_policies = {}
    _quota_overrides = {}
    _usage_windows = defaultdict(lambda: defaultdict(int))
    _blocked_users = {}

    # Default quota plans
    _default_plans = {
        QuotaTier.FREE: {
            "requests_per_minute": 10,
            "requests_per_hour": 100,
            "requests_per_day": 1000,
            "requests_per_month": 10000,
            "burst_allowance": 20,
            "concurrent_requests": 2
        },
        QuotaTier.BASIC: {
            "requests_per_minute": 60,
            "requests_per_hour": 1000,
            "requests_per_day": 10000,
            "requests_per_month": 100000,
            "burst_allowance": 100,
            "concurrent_requests": 5
        },
        QuotaTier.PREMIUM: {
            "requests_per_minute": 300,
            "requests_per_hour": 5000,
            "requests_per_day": 50000,
            "requests_per_month": 500000,
            "burst_allowance": 500,
            "concurrent_requests": 20
        },
        QuotaTier.ENTERPRISE: {
            "requests_per_minute": 1000,
            "requests_per_hour": 20000,
            "requests_per_day": 200000,
            "requests_per_month": 2000000,
            "burst_allowance": 2000,
            "concurrent_requests": 100
        }
    }

    @staticmethod
    def create_quota_plan(
        session,
        name: str,
        tier: str,
        limits: dict,
        description: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create a custom quota plan.

        Args:
            session: Database session
            name: Plan name
            tier: Quota tier
            limits: Rate limits configuration
            description: Plan description
            metadata: Additional metadata

        Returns:
            Created quota plan
        """
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        plan = {
            "id": plan_id,
            "name": name,
            "tier": tier,
            "limits": limits,
            "description": description,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "enabled": True,
            "users_count": 0,
            "metadata": metadata or {}
        }

        APIRateLimiting._quota_plans[plan_id] = plan
        return plan

    @staticmethod
    def assign_quota(
        session,
        user_id: str,
        tier: str,
        plan_id: Optional[str] = None,
        custom_limits: Optional[dict] = None
    ) -> dict:
        """
        Assign quota to a user.

        Args:
            session: Database session
            user_id: User identifier
            tier: Quota tier
            plan_id: Custom plan ID (optional)
            custom_limits: Custom limits override

        Returns:
            Assigned quota
        """
        quota_id = f"quota_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # Get base limits from tier or plan
        if plan_id:
            plan = APIRateLimiting._quota_plans.get(plan_id)
            if not plan:
                raise ValueError(f"Plan not found: {plan_id}")
            limits = plan["limits"]
        else:
            limits = APIRateLimiting._default_plans.get(tier, APIRateLimiting._default_plans[QuotaTier.FREE])

        # Apply custom limits if provided
        if custom_limits:
            limits = {**limits, **custom_limits}

        quota = {
            "id": quota_id,
            "user_id": user_id,
            "tier": tier,
            "plan_id": plan_id,
            "limits": limits,
            "assigned_at": now.isoformat(),
            "usage": {
                "minute": 0,
                "hour": 0,
                "day": 0,
                "month": 0,
                "total": 0
            },
            "last_reset": {
                "minute": now.isoformat(),
                "hour": now.isoformat(),
                "day": now.isoformat(),
                "month": now.isoformat()
            },
            "burst_used": 0,
            "status": LimitStatus.WITHIN_LIMIT
        }

        APIRateLimiting._user_quotas[user_id] = quota
        return quota

    @staticmethod
    def check_rate_limit(
        session,
        user_id: str,
        endpoint: Optional[str] = None
    ) -> dict:
        """
        Check if user is within rate limit.

        Args:
            session: Database session
            user_id: User identifier
            endpoint: Specific endpoint (optional)

        Returns:
            Rate limit check result
        """
        quota = APIRateLimiting._user_quotas.get(user_id)
        if not quota:
            # Assign default free tier
            quota = APIRateLimiting.assign_quota(
                session=session,
                user_id=user_id,
                tier=QuotaTier.FREE
            )

        now = datetime.utcnow()
        limits = quota["limits"]

        # Check if user is blocked
        if user_id in APIRateLimiting._blocked_users:
            block_info = APIRateLimiting._blocked_users[user_id]
            if datetime.fromisoformat(block_info["blocked_until"]) > now:
                return {
                    "allowed": False,
                    "status": LimitStatus.BLOCKED,
                    "reason": "User is temporarily blocked",
                    "blocked_until": block_info["blocked_until"],
                    "retry_after": (datetime.fromisoformat(block_info["blocked_until"]) - now).total_seconds()
                }
            else:
                # Block expired, remove it
                del APIRateLimiting._blocked_users[user_id]

        # Reset usage counters if needed
        APIRateLimiting._reset_usage_if_needed(quota, now)

        # Check each period
        for period in ["minute", "hour", "day", "month"]:
            limit_key = f"requests_per_{period}"
            if limit_key in limits:
                if quota["usage"][period] >= limits[limit_key]:
                    # Check burst allowance
                    if quota["burst_used"] < limits.get("burst_allowance", 0):
                        quota["burst_used"] += 1
                        return {
                            "allowed": True,
                            "status": LimitStatus.APPROACHING_LIMIT,
                            "reason": f"Using burst allowance ({quota['burst_used']}/{limits['burst_allowance']})",
                            "remaining": {p: max(0, limits.get(f"requests_per_{p}", float('inf')) - quota["usage"][p]) for p in ["minute", "hour", "day", "month"]},
                            "reset_at": quota["last_reset"]
                        }
                    else:
                        return {
                            "allowed": False,
                            "status": LimitStatus.EXCEEDED,
                            "reason": f"Rate limit exceeded for {period}",
                            "limit": limits[limit_key],
                            "current": quota["usage"][period],
                            "reset_at": quota["last_reset"][period],
                            "retry_after": APIRateLimiting._calculate_retry_after(period, now, datetime.fromisoformat(quota["last_reset"][period]))
                        }

        # Within limits
        return {
            "allowed": True,
            "status": LimitStatus.WITHIN_LIMIT,
            "remaining": {
                period: max(0, limits.get(f"requests_per_{period}", float('inf')) - quota["usage"][period])
                for period in ["minute", "hour", "day", "month"]
            },
            "reset_at": quota["last_reset"]
        }

    @staticmethod
    def record_request(
        session,
        user_id: str,
        endpoint: str,
        response_status: int,
        response_time_ms: Optional[float] = None
    ) -> dict:
        """
        Record an API request.

        Args:
            session: Database session
            user_id: User identifier
            endpoint: API endpoint
            response_status: HTTP response status
            response_time_ms: Response time in milliseconds

        Returns:
            Updated usage
        """
        quota = APIRateLimiting._user_quotas.get(user_id)
        if not quota:
            quota = APIRateLimiting.assign_quota(
                session=session,
                user_id=user_id,
                tier=QuotaTier.FREE
            )

        now = datetime.utcnow()

        # Update usage counters
        for period in ["minute", "hour", "day", "month"]:
            quota["usage"][period] += 1
        quota["usage"]["total"] += 1

        # Record usage for analytics
        record = {
            "timestamp": now.isoformat(),
            "user_id": user_id,
            "endpoint": endpoint,
            "response_status": response_status,
            "response_time_ms": response_time_ms,
            "tier": quota["tier"]
        }
        APIRateLimiting._usage_records[user_id].append(record)

        # Update status
        limits = quota["limits"]
        usage_percentage = max(
            quota["usage"]["minute"] / limits.get("requests_per_minute", float('inf')),
            quota["usage"]["hour"] / limits.get("requests_per_hour", float('inf')),
            quota["usage"]["day"] / limits.get("requests_per_day", float('inf')),
            quota["usage"]["month"] / limits.get("requests_per_month", float('inf'))
        )

        if usage_percentage >= 0.9:
            quota["status"] = LimitStatus.APPROACHING_LIMIT
        else:
            quota["status"] = LimitStatus.WITHIN_LIMIT

        return quota

    @staticmethod
    def get_usage_statistics(
        session,
        user_id: str,
        period: Optional[str] = None
    ) -> dict:
        """
        Get usage statistics for a user.

        Args:
            session: Database session
            user_id: User identifier
            period: Filter by period (optional)

        Returns:
            Usage statistics
        """
        quota = APIRateLimiting._user_quotas.get(user_id)
        if not quota:
            return {
                "user_id": user_id,
                "tier": QuotaTier.FREE,
                "usage": {"minute": 0, "hour": 0, "day": 0, "month": 0, "total": 0},
                "limits": APIRateLimiting._default_plans[QuotaTier.FREE],
                "status": LimitStatus.WITHIN_LIMIT
            }

        records = APIRateLimiting._usage_records.get(user_id, [])

        # Calculate statistics
        now = datetime.utcnow()
        stats = {
            "user_id": user_id,
            "tier": quota["tier"],
            "current_usage": quota["usage"],
            "limits": quota["limits"],
            "status": quota["status"],
            "burst_used": quota["burst_used"],
            "total_requests": len(records),
            "success_rate": 0,
            "avg_response_time_ms": 0,
            "endpoints": defaultdict(int)
        }

        if records:
            successful = sum(1 for r in records if 200 <= r["response_status"] < 300)
            stats["success_rate"] = successful / len(records)

            response_times = [r["response_time_ms"] for r in records if r.get("response_time_ms")]
            if response_times:
                stats["avg_response_time_ms"] = sum(response_times) / len(response_times)

            for record in records:
                stats["endpoints"][record["endpoint"]] += 1

        stats["endpoints"] = dict(stats["endpoints"])
        return stats

    @staticmethod
    def create_quota_override(
        session,
        user_id: str,
        custom_limits: dict,
        duration_hours: Optional[int] = None,
        reason: Optional[str] = None
    ) -> dict:
        """
        Create a temporary quota override.

        Args:
            session: Database session
            user_id: User identifier
            custom_limits: Custom limits to apply
            duration_hours: Override duration (None = permanent)
            reason: Override reason

        Returns:
            Created override
        """
        override_id = f"override_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        override = {
            "id": override_id,
            "user_id": user_id,
            "custom_limits": custom_limits,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(hours=duration_hours)).isoformat() if duration_hours else None,
            "reason": reason,
            "active": True
        }

        APIRateLimiting._quota_overrides[user_id] = override

        # Apply override to user's quota
        quota = APIRateLimiting._user_quotas.get(user_id)
        if quota:
            quota["limits"] = {**quota["limits"], **custom_limits}

        return override

    @staticmethod
    def block_user(
        session,
        user_id: str,
        duration_hours: int,
        reason: Optional[str] = None
    ) -> dict:
        """
        Temporarily block a user.

        Args:
            session: Database session
            user_id: User to block
            duration_hours: Block duration
            reason: Block reason

        Returns:
            Block information
        """
        now = datetime.utcnow()
        blocked_until = now + timedelta(hours=duration_hours)

        block = {
            "user_id": user_id,
            "blocked_at": now.isoformat(),
            "blocked_until": blocked_until.isoformat(),
            "reason": reason,
            "duration_hours": duration_hours
        }

        APIRateLimiting._blocked_users[user_id] = block
        return block

    @staticmethod
    def list_quotas(
        session,
        tier: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> dict:
        """
        List user quotas.

        Args:
            session: Database session
            tier: Filter by tier
            status: Filter by status
            limit: Maximum quotas to return

        Returns:
            Filtered quotas
        """
        quotas = list(APIRateLimiting._user_quotas.values())

        # Apply filters
        if tier:
            quotas = [q for q in quotas if q["tier"] == tier]
        if status:
            quotas = [q for q in quotas if q["status"] == status]

        # Sort by usage descending
        quotas.sort(key=lambda x: x["usage"]["total"], reverse=True)

        # Apply limit
        quotas = quotas[:limit]

        return {
            "quotas": quotas,
            "total_quotas": len(APIRateLimiting._user_quotas),
            "returned_count": len(quotas)
        }

    @staticmethod
    def get_global_statistics(session) -> dict:
        """Get global rate limiting statistics"""
        quotas = list(APIRateLimiting._user_quotas.values())
        all_records = [r for records in APIRateLimiting._usage_records.values() for r in records]

        # Tier distribution
        tier_dist = defaultdict(int)
        for quota in quotas:
            tier_dist[quota["tier"]] += 1

        # Status distribution
        status_dist = defaultdict(int)
        for quota in quotas:
            status_dist[quota["status"]] += 1

        # Total requests
        now = datetime.utcnow()
        last_hour = now - timedelta(hours=1)
        last_day = now - timedelta(days=1)

        requests_last_hour = sum(1 for r in all_records if datetime.fromisoformat(r["timestamp"]) > last_hour)
        requests_last_day = sum(1 for r in all_records if datetime.fromisoformat(r["timestamp"]) > last_day)

        return {
            "total_users": len(quotas),
            "total_requests": len(all_records),
            "requests_last_hour": requests_last_hour,
            "requests_last_day": requests_last_day,
            "tier_distribution": dict(tier_dist),
            "status_distribution": dict(status_dist),
            "blocked_users": len(APIRateLimiting._blocked_users),
            "active_overrides": len(APIRateLimiting._quota_overrides),
            "total_plans": len(APIRateLimiting._quota_plans)
        }

    @staticmethod
    def _reset_usage_if_needed(quota: dict, now: datetime):
        """Reset usage counters if period has elapsed"""
        for period in ["minute", "hour", "day", "month"]:
            last_reset = datetime.fromisoformat(quota["last_reset"][period])
            should_reset = False

            if period == "minute" and (now - last_reset).total_seconds() >= 60:
                should_reset = True
            elif period == "hour" and (now - last_reset).total_seconds() >= 3600:
                should_reset = True
            elif period == "day" and (now - last_reset).days >= 1:
                should_reset = True
            elif period == "month" and (now - last_reset).days >= 30:
                should_reset = True

            if should_reset:
                quota["usage"][period] = 0
                quota["last_reset"][period] = now.isoformat()
                if period == "minute":
                    quota["burst_used"] = 0

    @staticmethod
    def _calculate_retry_after(period: str, now: datetime, last_reset: datetime) -> float:
        """Calculate seconds until next reset"""
        if period == "minute":
            next_reset = last_reset + timedelta(minutes=1)
        elif period == "hour":
            next_reset = last_reset + timedelta(hours=1)
        elif period == "day":
            next_reset = last_reset + timedelta(days=1)
        else:  # month
            next_reset = last_reset + timedelta(days=30)

        return max(0, (next_reset - now).total_seconds())
