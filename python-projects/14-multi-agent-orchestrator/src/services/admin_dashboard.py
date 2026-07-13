"""
Admin Dashboard and System Management

Provides comprehensive administrative controls including user management, system configuration,
permissions, role-based access control, and platform administration.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from enum import Enum
import hashlib


class UserRole(str, Enum):
    """User roles"""
    ADMIN = "admin"
    MANAGER = "manager"
    USER = "user"
    VIEWER = "viewer"


class UserStatus(str, Enum):
    """User account status"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"
    PENDING = "pending"


class Permission(str, Enum):
    """System permissions"""
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    ADMIN = "admin"
    EXECUTE = "execute"


class SystemStatus(str, Enum):
    """System status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    MAINTENANCE = "maintenance"


class AdminDashboardService:
    """Admin Dashboard and System Management Service"""

    # In-memory storage
    _users: Dict[str, Dict] = {}
    _roles: Dict[str, Dict] = {}
    _permissions: Dict[str, List[str]] = defaultdict(list)
    _system_config: Dict[str, Any] = {}
    _audit_logs: List[Dict] = []
    _system_health: Dict[str, Any] = {}
    _maintenance_windows: List[Dict] = []
    _feature_toggles: Dict[str, bool] = {}

    @staticmethod
    def create_user(
        session,
        user_id: str,
        username: str,
        email: str,
        role: UserRole = UserRole.USER,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Create a new user."""
        if user_id in AdminDashboardService._users:
            raise ValueError(f"User already exists: {user_id}")

        user = {
            "user_id": user_id,
            "username": username,
            "email": email,
            "role": role,
            "status": UserStatus.ACTIVE,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "last_login_at": None,
            "login_count": 0,
            "permissions": []
        }

        # Assign default permissions based on role
        user["permissions"] = AdminDashboardService._get_default_permissions(role)

        AdminDashboardService._users[user_id] = user

        # Log audit event
        AdminDashboardService._log_audit_event(
            action="user_created",
            user_id=user_id,
            details={"username": username, "role": role}
        )

        return user

    @staticmethod
    def _get_default_permissions(role: UserRole) -> List[str]:
        """Get default permissions for a role."""
        if role == UserRole.ADMIN:
            return [Permission.READ, Permission.WRITE, Permission.DELETE, Permission.ADMIN, Permission.EXECUTE]
        elif role == UserRole.MANAGER:
            return [Permission.READ, Permission.WRITE, Permission.EXECUTE]
        elif role == UserRole.USER:
            return [Permission.READ, Permission.WRITE]
        else:  # VIEWER
            return [Permission.READ]

    @staticmethod
    def update_user_role(
        session,
        user_id: str,
        new_role: UserRole,
        updated_by: str
    ) -> dict:
        """Update a user's role."""
        user = AdminDashboardService._users.get(user_id)
        if not user:
            raise ValueError(f"User not found: {user_id}")

        old_role = user["role"]
        user["role"] = new_role
        user["permissions"] = AdminDashboardService._get_default_permissions(new_role)
        user["updated_at"] = datetime.utcnow().isoformat()

        # Log audit event
        AdminDashboardService._log_audit_event(
            action="user_role_updated",
            user_id=updated_by,
            details={
                "target_user_id": user_id,
                "old_role": old_role,
                "new_role": new_role
            }
        )

        return user

    @staticmethod
    def suspend_user(
        session,
        user_id: str,
        reason: str,
        suspended_by: str
    ) -> dict:
        """Suspend a user account."""
        user = AdminDashboardService._users.get(user_id)
        if not user:
            raise ValueError(f"User not found: {user_id}")

        user["status"] = UserStatus.SUSPENDED
        user["suspension_reason"] = reason
        user["suspended_at"] = datetime.utcnow().isoformat()
        user["suspended_by"] = suspended_by
        user["updated_at"] = datetime.utcnow().isoformat()

        # Log audit event
        AdminDashboardService._log_audit_event(
            action="user_suspended",
            user_id=suspended_by,
            details={"target_user_id": user_id, "reason": reason}
        )

        return user

    @staticmethod
    def reactivate_user(
        session,
        user_id: str,
        reactivated_by: str
    ) -> dict:
        """Reactivate a suspended user account."""
        user = AdminDashboardService._users.get(user_id)
        if not user:
            raise ValueError(f"User not found: {user_id}")

        user["status"] = UserStatus.ACTIVE
        user["suspension_reason"] = None
        user["suspended_at"] = None
        user["reactivated_at"] = datetime.utcnow().isoformat()
        user["updated_at"] = datetime.utcnow().isoformat()

        # Log audit event
        AdminDashboardService._log_audit_event(
            action="user_reactivated",
            user_id=reactivated_by,
            details={"target_user_id": user_id}
        )

        return user

    @staticmethod
    def list_users(
        session,
        role: Optional[UserRole] = None,
        status: Optional[UserStatus] = None,
        limit: int = 50
    ) -> List[dict]:
        """List users with optional filters."""
        users = list(AdminDashboardService._users.values())

        # Apply filters
        if role:
            users = [u for u in users if u["role"] == role]
        if status:
            users = [u for u in users if u["status"] == status]

        # Sort by created_at descending
        users.sort(key=lambda x: x["created_at"], reverse=True)

        return users[:limit]

    @staticmethod
    def update_system_config(
        session,
        config_key: str,
        config_value: Any,
        updated_by: str
    ) -> dict:
        """Update system configuration."""
        old_value = AdminDashboardService._system_config.get(config_key)

        AdminDashboardService._system_config[config_key] = config_value

        # Log audit event
        AdminDashboardService._log_audit_event(
            action="config_updated",
            user_id=updated_by,
            details={
                "config_key": config_key,
                "old_value": old_value,
                "new_value": config_value
            }
        )

        return {
            "config_key": config_key,
            "config_value": config_value,
            "updated_at": datetime.utcnow().isoformat(),
            "updated_by": updated_by
        }

    @staticmethod
    def get_system_config(session) -> dict:
        """Get all system configuration."""
        return dict(AdminDashboardService._system_config)

    @staticmethod
    def _log_audit_event(
        action: str,
        user_id: str,
        details: Optional[Dict] = None
    ):
        """Log an audit event."""
        event = {
            "event_id": f"audit_{len(AdminDashboardService._audit_logs)}_{datetime.utcnow().timestamp()}",
            "action": action,
            "user_id": user_id,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat(),
            "ip_address": "0.0.0.0",  # Would come from request in real implementation
            "user_agent": "Admin Dashboard"
        }

        AdminDashboardService._audit_logs.append(event)

        # Keep only last 100000 audit logs
        AdminDashboardService._audit_logs = AdminDashboardService._audit_logs[-100000:]

    @staticmethod
    def get_audit_logs(
        session,
        user_id: Optional[str] = None,
        action: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100
    ) -> List[dict]:
        """Get audit logs with filters."""
        logs = AdminDashboardService._audit_logs.copy()

        # Apply filters
        if user_id:
            logs = [l for l in logs if l["user_id"] == user_id]
        if action:
            logs = [l for l in logs if l["action"] == action]
        if start_time:
            logs = [l for l in logs if l["timestamp"] >= start_time]
        if end_time:
            logs = [l for l in logs if l["timestamp"] <= end_time]

        # Sort by timestamp descending
        logs.sort(key=lambda x: x["timestamp"], reverse=True)

        return logs[:limit]

    @staticmethod
    def get_system_health(session) -> dict:
        """Get system health status."""
        # Simulate system health check
        return {
            "status": SystemStatus.HEALTHY,
            "components": {
                "database": {"status": "healthy", "latency_ms": 5},
                "redis": {"status": "healthy", "latency_ms": 2},
                "celery": {"status": "healthy", "active_workers": 4},
                "api": {"status": "healthy", "response_time_ms": 50}
            },
            "metrics": {
                "cpu_usage_percent": 45.2,
                "memory_usage_percent": 62.8,
                "disk_usage_percent": 38.5,
                "network_io_mbps": 125.3
            },
            "uptime_seconds": 864000,  # 10 days
            "last_check_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def schedule_maintenance(
        session,
        maintenance_id: str,
        start_time: str,
        end_time: str,
        reason: str,
        scheduled_by: str
    ) -> dict:
        """Schedule a maintenance window."""
        maintenance = {
            "maintenance_id": maintenance_id,
            "start_time": start_time,
            "end_time": end_time,
            "reason": reason,
            "scheduled_by": scheduled_by,
            "status": "scheduled",
            "created_at": datetime.utcnow().isoformat(),
            "notifications_sent": False
        }

        AdminDashboardService._maintenance_windows.append(maintenance)

        # Log audit event
        AdminDashboardService._log_audit_event(
            action="maintenance_scheduled",
            user_id=scheduled_by,
            details={
                "maintenance_id": maintenance_id,
                "start_time": start_time,
                "end_time": end_time
            }
        )

        return maintenance

    @staticmethod
    def toggle_feature(
        session,
        feature_name: str,
        enabled: bool,
        toggled_by: str
    ) -> dict:
        """Toggle a feature flag."""
        old_value = AdminDashboardService._feature_toggles.get(feature_name)

        AdminDashboardService._feature_toggles[feature_name] = enabled

        # Log audit event
        AdminDashboardService._log_audit_event(
            action="feature_toggled",
            user_id=toggled_by,
            details={
                "feature_name": feature_name,
                "old_value": old_value,
                "new_value": enabled
            }
        )

        return {
            "feature_name": feature_name,
            "enabled": enabled,
            "toggled_at": datetime.utcnow().isoformat(),
            "toggled_by": toggled_by
        }

    @staticmethod
    def get_feature_flags(session) -> dict:
        """Get all feature flags."""
        return dict(AdminDashboardService._feature_toggles)

    @staticmethod
    def get_platform_statistics(session) -> dict:
        """Get comprehensive platform statistics."""
        total_users = len(AdminDashboardService._users)
        active_users = sum(1 for u in AdminDashboardService._users.values() if u["status"] == UserStatus.ACTIVE)

        # By role
        by_role = defaultdict(int)
        for user in AdminDashboardService._users.values():
            by_role[user["role"]] += 1

        # Recent activity (last 24 hours)
        one_day_ago = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        recent_audit_events = sum(
            1 for log in AdminDashboardService._audit_logs
            if log["timestamp"] >= one_day_ago
        )

        return {
            "users": {
                "total": total_users,
                "active": active_users,
                "suspended": sum(1 for u in AdminDashboardService._users.values() if u["status"] == UserStatus.SUSPENDED),
                "by_role": dict(by_role)
            },
            "system": {
                "config_entries": len(AdminDashboardService._system_config),
                "feature_flags": len(AdminDashboardService._feature_toggles),
                "enabled_features": sum(1 for v in AdminDashboardService._feature_toggles.values() if v)
            },
            "audit": {
                "total_events": len(AdminDashboardService._audit_logs),
                "recent_24h": recent_audit_events
            },
            "maintenance": {
                "scheduled_windows": len(AdminDashboardService._maintenance_windows),
                "upcoming": sum(
                    1 for m in AdminDashboardService._maintenance_windows
                    if m["status"] == "scheduled"
                )
            }
        }

    @staticmethod
    def bulk_update_users(
        session,
        user_ids: List[str],
        updates: Dict,
        updated_by: str
    ) -> dict:
        """Bulk update multiple users."""
        updated_count = 0
        failed_count = 0
        errors = []

        for user_id in user_ids:
            try:
                user = AdminDashboardService._users.get(user_id)
                if not user:
                    failed_count += 1
                    errors.append(f"User not found: {user_id}")
                    continue

                # Apply updates
                for key, value in updates.items():
                    if key in user and key not in ["user_id", "created_at"]:
                        user[key] = value

                user["updated_at"] = datetime.utcnow().isoformat()
                updated_count += 1

            except Exception as e:
                failed_count += 1
                errors.append(f"Error updating {user_id}: {str(e)}")

        # Log audit event
        AdminDashboardService._log_audit_event(
            action="bulk_user_update",
            user_id=updated_by,
            details={
                "user_count": len(user_ids),
                "updated_count": updated_count,
                "failed_count": failed_count
            }
        )

        return {
            "total": len(user_ids),
            "updated": updated_count,
            "failed": failed_count,
            "errors": errors
        }

    @staticmethod
    def export_audit_logs(
        session,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> dict:
        """Export audit logs for compliance."""
        logs = AdminDashboardService.get_audit_logs(
            session=session,
            start_time=start_time,
            end_time=end_time,
            limit=100000
        )

        export_id = f"export_{datetime.utcnow().timestamp()}"

        return {
            "export_id": export_id,
            "logs_count": len(logs),
            "logs": logs,
            "start_time": start_time,
            "end_time": end_time,
            "exported_at": datetime.utcnow().isoformat()
        }
