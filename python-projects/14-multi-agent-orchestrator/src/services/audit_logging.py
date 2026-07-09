"""
Audit Logging Service

Provides comprehensive audit logging for compliance, security, and debugging.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import uuid
import hashlib
import json


class AuditEventType:
    """Audit event types"""
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    ACCESS = "access"
    EXECUTE = "execute"
    AUTHENTICATE = "authenticate"
    AUTHORIZE = "authorize"
    EXPORT = "export"
    IMPORT = "import"
    CONFIGURE = "configure"


class AuditCategory:
    """Audit log categories"""
    USER = "user"
    AGENT = "agent"
    WORKFLOW = "workflow"
    TASK = "task"
    SYSTEM = "system"
    SECURITY = "security"
    DATA = "data"
    CONFIG = "config"
    COST = "cost"
    APPROVAL = "approval"


class AuditSeverity:
    """Audit event severity"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditLogging:
    """Audit Logging service for comprehensive activity tracking"""

    # In-memory storage
    _audit_logs = {}
    _log_index = defaultdict(list)  # For fast querying
    _retention_policies = {}
    _log_sequence = 0
    _previous_hash = "0" * 64  # Genesis hash

    @staticmethod
    def log_event(
        session,
        event_type: str,
        category: str,
        actor: str,
        action: str,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        details: Optional[dict] = None,
        changes: Optional[dict] = None,
        severity: str = AuditSeverity.INFO,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Log an audit event.

        Args:
            session: Database session
            event_type: Type of event (create, update, delete, etc.)
            category: Event category
            actor: User/system performing action
            action: Description of action
            resource_type: Type of resource affected
            resource_id: ID of resource affected
            details: Event details
            changes: Before/after changes
            severity: Event severity
            ip_address: IP address of actor
            user_agent: User agent string
            metadata: Additional metadata

        Returns:
            Created audit log entry
        """
        log_id = f"audit_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        AuditLogging._log_sequence += 1

        # Create audit log entry
        audit_log = {
            "id": log_id,
            "sequence": AuditLogging._log_sequence,
            "event_type": event_type,
            "category": category,
            "actor": actor,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": details or {},
            "changes": changes or {},
            "severity": severity,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "metadata": metadata or {},
            "timestamp": now.isoformat(),
            "success": True
        }

        # Calculate hash for tamper detection
        audit_log["hash"] = AuditLogging._calculate_hash(audit_log)
        audit_log["previous_hash"] = AuditLogging._previous_hash
        AuditLogging._previous_hash = audit_log["hash"]

        # Store audit log
        AuditLogging._audit_logs[log_id] = audit_log

        # Update indexes for fast querying
        AuditLogging._log_index["category:" + category].append(log_id)
        AuditLogging._log_index["event_type:" + event_type].append(log_id)
        AuditLogging._log_index["actor:" + actor].append(log_id)
        if resource_type:
            AuditLogging._log_index["resource_type:" + resource_type].append(log_id)
        if resource_id:
            AuditLogging._log_index["resource_id:" + resource_id].append(log_id)

        # Check retention policies
        AuditLogging._apply_retention_policies(session)

        return audit_log

    @staticmethod
    def log_authentication(
        session,
        actor: str,
        success: bool,
        method: str,
        ip_address: Optional[str] = None,
        failure_reason: Optional[str] = None
    ) -> dict:
        """Log authentication event"""
        return AuditLogging.log_event(
            session=session,
            event_type=AuditEventType.AUTHENTICATE,
            category=AuditCategory.SECURITY,
            actor=actor,
            action=f"Authentication {'successful' if success else 'failed'}",
            details={
                "method": method,
                "success": success,
                "failure_reason": failure_reason
            },
            severity=AuditSeverity.INFO if success else AuditSeverity.WARNING,
            ip_address=ip_address
        )

    @staticmethod
    def log_data_access(
        session,
        actor: str,
        resource_type: str,
        resource_id: str,
        operation: str,
        ip_address: Optional[str] = None
    ) -> dict:
        """Log data access event"""
        return AuditLogging.log_event(
            session=session,
            event_type=AuditEventType.ACCESS,
            category=AuditCategory.DATA,
            actor=actor,
            action=f"Accessed {resource_type}",
            resource_type=resource_type,
            resource_id=resource_id,
            details={"operation": operation},
            severity=AuditSeverity.INFO,
            ip_address=ip_address
        )

    @staticmethod
    def log_configuration_change(
        session,
        actor: str,
        config_key: str,
        old_value: Any,
        new_value: Any,
        ip_address: Optional[str] = None
    ) -> dict:
        """Log configuration change"""
        return AuditLogging.log_event(
            session=session,
            event_type=AuditEventType.CONFIGURE,
            category=AuditCategory.CONFIG,
            actor=actor,
            action=f"Changed configuration: {config_key}",
            resource_type="configuration",
            resource_id=config_key,
            changes={
                "before": old_value,
                "after": new_value
            },
            severity=AuditSeverity.WARNING,
            ip_address=ip_address
        )

    @staticmethod
    def query_logs(
        session,
        event_type: Optional[str] = None,
        category: Optional[str] = None,
        actor: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        severity: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100
    ) -> dict:
        """
        Query audit logs with filtering.

        Args:
            session: Database session
            event_type: Filter by event type
            category: Filter by category
            actor: Filter by actor
            resource_type: Filter by resource type
            resource_id: Filter by resource ID
            severity: Filter by severity
            start_date: Start date filter
            end_date: End date filter
            limit: Maximum logs to return

        Returns:
            Filtered audit logs and statistics
        """
        # Start with all logs
        log_ids = set(AuditLogging._audit_logs.keys())

        # Apply index filters for performance
        if category:
            log_ids &= set(AuditLogging._log_index.get("category:" + category, []))
        if event_type:
            log_ids &= set(AuditLogging._log_index.get("event_type:" + event_type, []))
        if actor:
            log_ids &= set(AuditLogging._log_index.get("actor:" + actor, []))
        if resource_type:
            log_ids &= set(AuditLogging._log_index.get("resource_type:" + resource_type, []))
        if resource_id:
            log_ids &= set(AuditLogging._log_index.get("resource_id:" + resource_id, []))

        # Get logs
        logs = [AuditLogging._audit_logs[log_id] for log_id in log_ids]

        # Apply additional filters
        if severity:
            logs = [log for log in logs if log["severity"] == severity]

        if start_date:
            start_dt = datetime.fromisoformat(start_date)
            logs = [log for log in logs if datetime.fromisoformat(log["timestamp"]) >= start_dt]

        if end_date:
            end_dt = datetime.fromisoformat(end_date)
            logs = [log for log in logs if datetime.fromisoformat(log["timestamp"]) <= end_dt]

        # Sort by timestamp descending
        logs.sort(key=lambda x: x["timestamp"], reverse=True)

        # Apply limit
        logs = logs[:limit]

        return {
            "logs": logs,
            "total_logs": len(AuditLogging._audit_logs),
            "returned_count": len(logs)
        }

    @staticmethod
    def get_actor_activity(
        session,
        actor: str,
        time_window_hours: int = 24,
        limit: int = 50
    ) -> dict:
        """
        Get activity for a specific actor.

        Args:
            session: Database session
            actor: Actor identifier
            time_window_hours: Time window in hours
            limit: Maximum logs to return

        Returns:
            Actor activity and statistics
        """
        now = datetime.utcnow()
        start_date = (now - timedelta(hours=time_window_hours)).isoformat()

        result = AuditLogging.query_logs(
            session=session,
            actor=actor,
            start_date=start_date,
            limit=limit
        )

        # Calculate statistics
        logs = result["logs"]
        event_types = defaultdict(int)
        categories = defaultdict(int)

        for log in logs:
            event_types[log["event_type"]] += 1
            categories[log["category"]] += 1

        return {
            "actor": actor,
            "time_window_hours": time_window_hours,
            "activity_count": len(logs),
            "recent_activity": logs,
            "event_type_breakdown": dict(event_types),
            "category_breakdown": dict(categories)
        }

    @staticmethod
    def get_resource_history(
        session,
        resource_type: str,
        resource_id: str,
        limit: int = 50
    ) -> dict:
        """
        Get complete history for a resource.

        Args:
            session: Database session
            resource_type: Type of resource
            resource_id: Resource ID
            limit: Maximum logs to return

        Returns:
            Resource history
        """
        result = AuditLogging.query_logs(
            session=session,
            resource_type=resource_type,
            resource_id=resource_id,
            limit=limit
        )

        logs = result["logs"]

        # Extract timeline of changes
        timeline = []
        for log in logs:
            timeline.append({
                "timestamp": log["timestamp"],
                "event_type": log["event_type"],
                "actor": log["actor"],
                "action": log["action"],
                "changes": log.get("changes", {})
            })

        return {
            "resource_type": resource_type,
            "resource_id": resource_id,
            "history_count": len(logs),
            "timeline": timeline,
            "full_logs": logs
        }

    @staticmethod
    def create_retention_policy(
        session,
        name: str,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        retention_days: int = 90,
        enabled: bool = True
    ) -> dict:
        """
        Create a retention policy.

        Args:
            session: Database session
            name: Policy name
            category: Category to apply to
            severity: Severity to apply to
            retention_days: Days to retain logs
            enabled: Whether policy is enabled

        Returns:
            Created retention policy
        """
        policy_id = f"policy_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        policy = {
            "id": policy_id,
            "name": name,
            "category": category,
            "severity": severity,
            "retention_days": retention_days,
            "enabled": enabled,
            "created_at": now.isoformat(),
            "logs_deleted": 0
        }

        AuditLogging._retention_policies[policy_id] = policy
        return policy

    @staticmethod
    def export_logs(
        session,
        format: str = "json",
        event_type: Optional[str] = None,
        category: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> dict:
        """
        Export audit logs.

        Args:
            session: Database session
            format: Export format (json, csv)
            event_type: Filter by event type
            category: Filter by category
            start_date: Start date filter
            end_date: End date filter

        Returns:
            Export data
        """
        result = AuditLogging.query_logs(
            session=session,
            event_type=event_type,
            category=category,
            start_date=start_date,
            end_date=end_date,
            limit=10000
        )

        logs = result["logs"]

        export_id = f"export_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        export = {
            "id": export_id,
            "format": format,
            "log_count": len(logs),
            "exported_at": now.isoformat(),
            "data": logs if format == "json" else AuditLogging._convert_to_csv(logs)
        }

        # Log the export action
        AuditLogging.log_event(
            session=session,
            event_type=AuditEventType.EXPORT,
            category=AuditCategory.SYSTEM,
            actor="system",
            action=f"Exported {len(logs)} audit logs",
            details={"format": format, "log_count": len(logs)}
        )

        return export

    @staticmethod
    def verify_integrity(session) -> dict:
        """
        Verify audit log integrity.

        Returns:
            Integrity verification results
        """
        logs = sorted(AuditLogging._audit_logs.values(), key=lambda x: x["sequence"])

        verified_count = 0
        tampered_count = 0
        tampered_logs = []
        previous_hash = "0" * 64

        for log in logs:
            # Verify hash chain
            if log["previous_hash"] != previous_hash:
                tampered_count += 1
                tampered_logs.append({
                    "log_id": log["id"],
                    "sequence": log["sequence"],
                    "reason": "Hash chain broken"
                })

            # Verify hash calculation
            calculated_hash = AuditLogging._calculate_hash(log)
            if calculated_hash != log["hash"]:
                tampered_count += 1
                tampered_logs.append({
                    "log_id": log["id"],
                    "sequence": log["sequence"],
                    "reason": "Hash mismatch"
                })
            else:
                verified_count += 1

            previous_hash = log["hash"]

        return {
            "total_logs": len(logs),
            "verified_count": verified_count,
            "tampered_count": tampered_count,
            "integrity_valid": tampered_count == 0,
            "tampered_logs": tampered_logs
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get audit logging statistics"""
        logs = list(AuditLogging._audit_logs.values())

        # Event type distribution
        event_type_dist = defaultdict(int)
        for log in logs:
            event_type_dist[log["event_type"]] += 1

        # Category distribution
        category_dist = defaultdict(int)
        for log in logs:
            category_dist[log["category"]] += 1

        # Severity distribution
        severity_dist = defaultdict(int)
        for log in logs:
            severity_dist[log["severity"]] += 1

        # Recent activity (last 24 hours)
        now = datetime.utcnow()
        recent_cutoff = now - timedelta(hours=24)
        recent_logs = [
            log for log in logs
            if datetime.fromisoformat(log["timestamp"]) > recent_cutoff
        ]

        # Top actors
        actor_counts = defaultdict(int)
        for log in logs:
            actor_counts[log["actor"]] += 1
        top_actors = sorted(actor_counts.items(), key=lambda x: x[1], reverse=True)[:10]

        return {
            "total_logs": len(logs),
            "event_type_distribution": dict(event_type_dist),
            "category_distribution": dict(category_dist),
            "severity_distribution": dict(severity_dist),
            "recent_logs_24h": len(recent_logs),
            "top_actors": [{"actor": actor, "event_count": count} for actor, count in top_actors],
            "total_retention_policies": len(AuditLogging._retention_policies),
            "current_sequence": AuditLogging._log_sequence
        }

    @staticmethod
    def _calculate_hash(log: dict) -> str:
        """Calculate hash for audit log entry"""
        # Create hash from critical fields
        hash_data = {
            "sequence": log["sequence"],
            "event_type": log["event_type"],
            "category": log["category"],
            "actor": log["actor"],
            "action": log["action"],
            "timestamp": log["timestamp"],
            "previous_hash": log.get("previous_hash", "")
        }

        hash_string = json.dumps(hash_data, sort_keys=True)
        return hashlib.sha256(hash_string.encode()).hexdigest()

    @staticmethod
    def _apply_retention_policies(session):
        """Apply retention policies to delete old logs"""
        now = datetime.utcnow()

        for policy in AuditLogging._retention_policies.values():
            if not policy["enabled"]:
                continue

            cutoff_date = now - timedelta(days=policy["retention_days"])

            # Find logs to delete
            logs_to_delete = []
            for log_id, log in AuditLogging._audit_logs.items():
                log_date = datetime.fromisoformat(log["timestamp"])

                # Check if log matches policy criteria
                if policy["category"] and log["category"] != policy["category"]:
                    continue
                if policy["severity"] and log["severity"] != policy["severity"]:
                    continue

                # Check if log is older than retention period
                if log_date < cutoff_date:
                    logs_to_delete.append(log_id)

            # Delete logs (in production, archive instead)
            for log_id in logs_to_delete:
                del AuditLogging._audit_logs[log_id]
                policy["logs_deleted"] += 1

    @staticmethod
    def _convert_to_csv(logs: List[dict]) -> str:
        """Convert logs to CSV format"""
        if not logs:
            return ""

        # CSV header
        headers = ["id", "timestamp", "event_type", "category", "actor", "action", "resource_type", "resource_id", "severity"]
        csv_lines = [",".join(headers)]

        # CSV rows
        for log in logs:
            row = [
                log.get("id", ""),
                log.get("timestamp", ""),
                log.get("event_type", ""),
                log.get("category", ""),
                log.get("actor", ""),
                log.get("action", ""),
                log.get("resource_type", ""),
                log.get("resource_id", ""),
                log.get("severity", "")
            ]
            csv_lines.append(",".join(str(v) for v in row))

        return "\n".join(csv_lines)
