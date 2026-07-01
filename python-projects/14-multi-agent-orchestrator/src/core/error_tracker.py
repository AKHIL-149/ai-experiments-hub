"""
Error tracking and reporting system

Centralized error tracking for monitoring system health and debugging.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from enum import Enum
import traceback
import hashlib
from collections import defaultdict

from src.core.logging import logger


class ErrorSeverity(str, Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(str, Enum):
    """Error categories for classification"""
    TASK_EXECUTION = "task_execution"
    AGENT_ERROR = "agent_error"
    WORKFLOW_ERROR = "workflow_error"
    DATABASE_ERROR = "database_error"
    API_ERROR = "api_error"
    VALIDATION_ERROR = "validation_error"
    NETWORK_ERROR = "network_error"
    SYSTEM_ERROR = "system_error"


class ErrorTracker:
    """
    Centralized error tracking system

    Features:
    - Error aggregation and deduplication
    - Error severity classification
    - Error frequency tracking
    - Error recovery suggestions
    """

    def __init__(self):
        """Initialize error tracker"""
        # Store errors in memory (in production, use database or external service)
        self.errors: List[Dict[str, Any]] = []

        # Error frequency tracking
        self.error_counts: Dict[str, int] = defaultdict(int)

        # Last occurrence tracking
        self.last_occurrence: Dict[str, datetime] = {}

        # Maximum errors to keep in memory
        self.max_errors = 1000

    def track_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        category: ErrorCategory = ErrorCategory.SYSTEM_ERROR,
        task_id: Optional[int] = None,
        agent_id: Optional[int] = None
    ) -> str:
        """
        Track an error with context

        Args:
            error: The exception that occurred
            context: Additional context information
            severity: Error severity level
            category: Error category
            task_id: Related task ID (if applicable)
            agent_id: Related agent ID (if applicable)

        Returns:
            str: Error fingerprint (unique identifier)
        """
        # Generate error fingerprint for deduplication
        fingerprint = self._generate_fingerprint(error, category)

        # Update frequency tracking
        self.error_counts[fingerprint] += 1
        self.last_occurrence[fingerprint] = datetime.utcnow()

        # Create error record
        error_record = {
            "fingerprint": fingerprint,
            "timestamp": datetime.utcnow(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "traceback": traceback.format_exc(),
            "severity": severity.value,
            "category": category.value,
            "context": context or {},
            "task_id": task_id,
            "agent_id": agent_id,
            "occurrence_count": self.error_counts[fingerprint],
        }

        # Add to errors list
        self.errors.append(error_record)

        # Trim errors if exceeding max
        if len(self.errors) > self.max_errors:
            self.errors = self.errors[-self.max_errors:]

        # Log error
        self._log_error(error_record)

        # Send notification for high/critical errors
        if severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            self._send_error_notification(error_record)

        return fingerprint

    def _generate_fingerprint(
        self,
        error: Exception,
        category: ErrorCategory
    ) -> str:
        """
        Generate unique fingerprint for error deduplication

        Args:
            error: The exception
            category: Error category

        Returns:
            str: Error fingerprint
        """
        # Use error type, message, and category for fingerprint
        fingerprint_data = f"{type(error).__name__}:{str(error)}:{category.value}"
        return hashlib.md5(fingerprint_data.encode()).hexdigest()[:16]

    def _log_error(self, error_record: Dict[str, Any]) -> None:
        """
        Log error to logging system

        Args:
            error_record: Error record dictionary
        """
        severity = error_record["severity"]

        log_message = (
            f"[{error_record['category']}] "
            f"{error_record['error_type']}: {error_record['error_message']} "
            f"(fingerprint: {error_record['fingerprint']}, "
            f"occurrences: {error_record['occurrence_count']})"
        )

        if severity == ErrorSeverity.CRITICAL.value:
            logger.critical(log_message)
        elif severity == ErrorSeverity.HIGH.value:
            logger.error(log_message)
        elif severity == ErrorSeverity.MEDIUM.value:
            logger.warning(log_message)
        else:
            logger.info(log_message)

    def _send_error_notification(self, error_record: Dict[str, Any]) -> None:
        """
        Send notification for critical errors

        Args:
            error_record: Error record dictionary
        """
        try:
            from src.core.websocket import notify_system_event
            import asyncio

            def run_async(coro):
                try:
                    loop = asyncio.get_event_loop()
                except RuntimeError:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                if loop.is_running():
                    asyncio.create_task(coro)
                else:
                    loop.run_until_complete(coro)

            run_async(notify_system_event(
                event_type="error",
                data={
                    "severity": error_record["severity"],
                    "category": error_record["category"],
                    "error_type": error_record["error_type"],
                    "error_message": error_record["error_message"],
                    "fingerprint": error_record["fingerprint"],
                    "task_id": error_record.get("task_id"),
                    "agent_id": error_record.get("agent_id"),
                }
            ))
        except Exception as e:
            logger.warning(f"Failed to send error notification: {e}")

    def get_error_summary(
        self,
        hours: int = 24,
        min_occurrences: int = 1
    ) -> Dict[str, Any]:
        """
        Get error summary for specified time period

        Args:
            hours: Number of hours to look back
            min_occurrences: Minimum occurrence count to include

        Returns:
            dict: Error summary statistics
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        # Filter recent errors
        recent_errors = [
            error for error in self.errors
            if error["timestamp"] >= cutoff_time
        ]

        # Aggregate by fingerprint
        error_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for error in recent_errors:
            error_groups[error["fingerprint"]].append(error)

        # Filter by occurrence count
        error_groups = {
            fp: errors for fp, errors in error_groups.items()
            if len(errors) >= min_occurrences
        }

        # Calculate statistics
        total_errors = len(recent_errors)
        unique_errors = len(error_groups)

        # Group by severity
        severity_counts = defaultdict(int)
        for error in recent_errors:
            severity_counts[error["severity"]] += 1

        # Group by category
        category_counts = defaultdict(int)
        for error in recent_errors:
            category_counts[error["category"]] += 1

        # Top errors by frequency
        top_errors = sorted(
            [
                {
                    "fingerprint": fp,
                    "count": len(errors),
                    "last_occurrence": max(e["timestamp"] for e in errors),
                    "error_type": errors[0]["error_type"],
                    "error_message": errors[0]["error_message"],
                    "severity": errors[0]["severity"],
                    "category": errors[0]["category"],
                }
                for fp, errors in error_groups.items()
            ],
            key=lambda x: x["count"],
            reverse=True
        )[:10]

        return {
            "time_period_hours": hours,
            "total_errors": total_errors,
            "unique_errors": unique_errors,
            "severity_breakdown": dict(severity_counts),
            "category_breakdown": dict(category_counts),
            "top_errors": top_errors,
            "generated_at": datetime.utcnow().isoformat()
        }

    def get_error_details(self, fingerprint: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific error

        Args:
            fingerprint: Error fingerprint

        Returns:
            dict: Error details or None if not found
        """
        matching_errors = [
            error for error in self.errors
            if error["fingerprint"] == fingerprint
        ]

        if not matching_errors:
            return None

        # Get latest occurrence
        latest = max(matching_errors, key=lambda x: x["timestamp"])

        return {
            "fingerprint": fingerprint,
            "total_occurrences": len(matching_errors),
            "first_occurrence": min(e["timestamp"] for e in matching_errors).isoformat(),
            "last_occurrence": latest["timestamp"].isoformat(),
            "error_type": latest["error_type"],
            "error_message": latest["error_message"],
            "severity": latest["severity"],
            "category": latest["category"],
            "recent_occurrences": [
                {
                    "timestamp": e["timestamp"].isoformat(),
                    "task_id": e.get("task_id"),
                    "agent_id": e.get("agent_id"),
                    "context": e.get("context"),
                }
                for e in sorted(matching_errors, key=lambda x: x["timestamp"], reverse=True)[:5]
            ],
            "sample_traceback": latest["traceback"]
        }

    def clear_old_errors(self, hours: int = 168) -> int:
        """
        Clear errors older than specified hours (default 7 days)

        Args:
            hours: Number of hours to keep

        Returns:
            int: Number of errors cleared
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        initial_count = len(self.errors)
        self.errors = [
            error for error in self.errors
            if error["timestamp"] >= cutoff_time
        ]
        cleared_count = initial_count - len(self.errors)

        if cleared_count > 0:
            logger.info(f"Cleared {cleared_count} old errors (older than {hours} hours)")

        return cleared_count

    def get_recovery_suggestions(
        self,
        fingerprint: str
    ) -> List[str]:
        """
        Get recovery suggestions for a specific error

        Args:
            fingerprint: Error fingerprint

        Returns:
            list: Recovery suggestions
        """
        error_details = self.get_error_details(fingerprint)
        if not error_details:
            return ["Error not found in tracker"]

        suggestions = []
        category = error_details["category"]
        error_type = error_details["error_type"]

        # Category-specific suggestions
        if category == ErrorCategory.DATABASE_ERROR.value:
            suggestions.extend([
                "Check database connection and credentials",
                "Verify database migrations are up to date",
                "Check for database locks or deadlocks",
                "Review database query performance"
            ])
        elif category == ErrorCategory.NETWORK_ERROR.value:
            suggestions.extend([
                "Check network connectivity",
                "Verify external service availability",
                "Review timeout settings",
                "Check firewall rules"
            ])
        elif category == ErrorCategory.TASK_EXECUTION.value:
            suggestions.extend([
                "Review task input data and dependencies",
                "Check agent availability and status",
                "Verify workflow configuration",
                "Review task timeout settings"
            ])
        elif category == ErrorCategory.AGENT_ERROR.value:
            suggestions.extend([
                "Check agent configuration and status",
                "Verify LLM API credentials and quota",
                "Review agent system prompts",
                "Check agent resource limits"
            ])

        # Error type specific suggestions
        if "Timeout" in error_type:
            suggestions.append("Consider increasing timeout limits")
        elif "Connection" in error_type:
            suggestions.append("Check service availability and network connectivity")
        elif "Validation" in error_type:
            suggestions.append("Review input data format and validation rules")

        # Frequency-based suggestions
        if error_details["total_occurrences"] > 10:
            suggestions.append("High occurrence count - consider investigating root cause")

        return suggestions if suggestions else ["No specific suggestions available"]


# Global error tracker instance
error_tracker = ErrorTracker()
