"""
SLA Management and Tracking Service

Provides service level agreement definition, monitoring, violation tracking,
and compliance reporting for production services.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from enum import Enum
import statistics


class SLAMetricType(str, Enum):
    """Types of SLA metrics"""
    UPTIME = "uptime"
    RESPONSE_TIME = "response_time"
    ERROR_RATE = "error_rate"
    THROUGHPUT = "throughput"
    AVAILABILITY = "availability"


class SLASeverity(str, Enum):
    """SLA violation severity levels"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SLAStatus(str, Enum):
    """SLA status"""
    ACTIVE = "active"
    BREACHED = "breached"
    WARNING = "warning"
    SUSPENDED = "suspended"


class ComplianceStatus(str, Enum):
    """Compliance status"""
    COMPLIANT = "compliant"
    AT_RISK = "at_risk"
    NON_COMPLIANT = "non_compliant"


class SLAManagement:
    """SLA management and tracking"""

    # In-memory storage
    _slas: Dict[str, Dict] = {}
    _sla_metrics: List[Dict] = []
    _violations: Dict[str, Dict] = {}
    _compliance_reports: Dict[str, Dict] = {}
    _error_budgets: Dict[str, Dict] = {}
    _sla_versions: Dict[str, List[Dict]] = defaultdict(list)

    @staticmethod
    def create_sla(
        session,
        sla_id: str,
        name: str,
        service_name: str,
        metric_type: SLAMetricType,
        target_value: float,
        measurement_window_hours: int = 24,
        warning_threshold: float = 90.0,
        description: Optional[str] = None,
        penalty_per_violation: float = 0.0
    ) -> dict:
        """Create an SLA definition."""
        if sla_id in SLAManagement._slas:
            raise ValueError(f"SLA already exists: {sla_id}")

        if warning_threshold < 0 or warning_threshold > 100:
            raise ValueError("Warning threshold must be between 0 and 100")

        sla = {
            "sla_id": sla_id,
            "name": name,
            "service_name": service_name,
            "metric_type": metric_type,
            "target_value": target_value,
            "measurement_window_hours": measurement_window_hours,
            "warning_threshold": warning_threshold,
            "description": description or "",
            "penalty_per_violation": penalty_per_violation,
            "status": SLAStatus.ACTIVE,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "version": 1,
            "total_violations": 0,
            "total_penalties": 0.0,
            "current_compliance": 100.0,
            "last_measured": None
        }

        SLAManagement._slas[sla_id] = sla

        # Store version history
        SLAManagement._sla_versions[sla_id].append({
            "version": 1,
            "sla_data": sla.copy(),
            "created_at": sla["created_at"]
        })

        # Initialize error budget
        SLAManagement._initialize_error_budget(sla_id, metric_type, target_value)

        return sla

    @staticmethod
    def _initialize_error_budget(sla_id: str, metric_type: SLAMetricType, target_value: float):
        """Initialize error budget for an SLA."""
        # Calculate error budget based on metric type
        if metric_type == SLAMetricType.UPTIME:
            # e.g., 99.9% uptime = 0.1% error budget
            error_budget_percent = 100 - target_value
        elif metric_type == SLAMetricType.ERROR_RATE:
            # e.g., 1% error rate target = 1% error budget
            error_budget_percent = target_value
        else:
            # For response time and throughput, use 10% as default
            error_budget_percent = 10.0

        budget = {
            "budget_id": f"budget_{sla_id}",
            "sla_id": sla_id,
            "total_budget_percent": error_budget_percent,
            "remaining_budget_percent": error_budget_percent,
            "consumed_budget_percent": 0.0,
            "budget_window_start": datetime.utcnow().isoformat(),
            "budget_window_end": (datetime.utcnow() + timedelta(days=30)).isoformat(),
            "violation_count": 0,
            "last_reset": datetime.utcnow().isoformat()
        }

        SLAManagement._error_budgets[sla_id] = budget

    @staticmethod
    def record_metric(
        session,
        sla_id: str,
        measured_value: float,
        timestamp: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Record an SLA metric measurement."""
        sla = SLAManagement._slas.get(sla_id)
        if not sla:
            raise ValueError(f"SLA not found: {sla_id}")

        if sla["status"] == SLAStatus.SUSPENDED:
            raise ValueError(f"SLA is suspended: {sla_id}")

        metric = {
            "metric_id": f"metric_{len(SLAManagement._sla_metrics)}_{datetime.utcnow().timestamp()}",
            "sla_id": sla_id,
            "metric_type": sla["metric_type"],
            "measured_value": measured_value,
            "target_value": sla["target_value"],
            "timestamp": timestamp or datetime.utcnow().isoformat(),
            "metadata": metadata or {},
            "is_violation": False,
            "deviation_percent": 0.0
        }

        # Check if this is a violation
        is_violation = SLAManagement._check_violation(
            sla["metric_type"],
            measured_value,
            sla["target_value"]
        )

        metric["is_violation"] = is_violation

        # Calculate deviation
        if sla["target_value"] > 0:
            deviation = ((measured_value - sla["target_value"]) / sla["target_value"]) * 100
            metric["deviation_percent"] = deviation

        SLAManagement._sla_metrics.append(metric)

        # Update SLA status
        sla["last_measured"] = metric["timestamp"]

        # If violation, record it
        if is_violation:
            SLAManagement._record_violation(sla, metric)

        # Update compliance
        SLAManagement._update_compliance(sla_id)

        # Keep only recent metrics (last 30 days)
        cutoff = datetime.utcnow() - timedelta(days=30)
        cutoff_iso = cutoff.isoformat()
        SLAManagement._sla_metrics = [
            m for m in SLAManagement._sla_metrics
            if m["timestamp"] >= cutoff_iso
        ]

        return metric

    @staticmethod
    def _check_violation(metric_type: SLAMetricType, measured: float, target: float) -> bool:
        """Check if a measurement violates the SLA."""
        if metric_type == SLAMetricType.UPTIME:
            return measured < target
        elif metric_type == SLAMetricType.RESPONSE_TIME:
            return measured > target
        elif metric_type == SLAMetricType.ERROR_RATE:
            return measured > target
        elif metric_type == SLAMetricType.THROUGHPUT:
            return measured < target
        elif metric_type == SLAMetricType.AVAILABILITY:
            return measured < target
        return False

    @staticmethod
    def _record_violation(sla: dict, metric: dict):
        """Record an SLA violation."""
        violation_id = f"violation_{sla['sla_id']}_{datetime.utcnow().timestamp()}"

        # Determine severity based on deviation
        deviation = abs(metric["deviation_percent"])
        if deviation >= 50:
            severity = SLASeverity.CRITICAL
        elif deviation >= 25:
            severity = SLASeverity.HIGH
        elif deviation >= 10:
            severity = SLASeverity.MEDIUM
        else:
            severity = SLASeverity.LOW

        violation = {
            "violation_id": violation_id,
            "sla_id": sla["sla_id"],
            "service_name": sla["service_name"],
            "metric_type": sla["metric_type"],
            "measured_value": metric["measured_value"],
            "target_value": sla["target_value"],
            "deviation_percent": metric["deviation_percent"],
            "severity": severity,
            "penalty": sla["penalty_per_violation"],
            "detected_at": metric["timestamp"],
            "resolved_at": None,
            "resolution_notes": None,
            "acknowledged": False
        }

        SLAManagement._violations[violation_id] = violation

        # Update SLA stats
        sla["total_violations"] += 1
        sla["total_penalties"] += sla["penalty_per_violation"]
        sla["status"] = SLAStatus.BREACHED

        # Consume error budget
        budget = SLAManagement._error_budgets.get(sla["sla_id"])
        if budget:
            budget["violation_count"] += 1
            # Consume 1% of budget per violation (simplified)
            budget["consumed_budget_percent"] += 1.0
            budget["remaining_budget_percent"] = max(
                0,
                budget["total_budget_percent"] - budget["consumed_budget_percent"]
            )

    @staticmethod
    def _update_compliance(sla_id: str):
        """Update SLA compliance percentage."""
        sla = SLAManagement._slas.get(sla_id)
        if not sla:
            return

        # Get metrics in the measurement window
        window_start = datetime.utcnow() - timedelta(hours=sla["measurement_window_hours"])
        window_start_iso = window_start.isoformat()

        relevant_metrics = [
            m for m in SLAManagement._sla_metrics
            if m["sla_id"] == sla_id and m["timestamp"] >= window_start_iso
        ]

        if not relevant_metrics:
            sla["current_compliance"] = 100.0
            return

        violations = sum(1 for m in relevant_metrics if m["is_violation"])
        compliance = ((len(relevant_metrics) - violations) / len(relevant_metrics)) * 100

        sla["current_compliance"] = compliance

        # Update status based on compliance
        if compliance >= sla["warning_threshold"]:
            if sla["status"] != SLAStatus.SUSPENDED:
                sla["status"] = SLAStatus.ACTIVE
        elif compliance >= (sla["warning_threshold"] * 0.8):
            sla["status"] = SLAStatus.WARNING
        else:
            sla["status"] = SLAStatus.BREACHED

    @staticmethod
    def get_sla_status(session, sla_id: str) -> dict:
        """Get current SLA status and compliance."""
        sla = SLAManagement._slas.get(sla_id)
        if not sla:
            raise ValueError(f"SLA not found: {sla_id}")

        # Get recent violations
        recent_violations = [
            v for v in SLAManagement._violations.values()
            if v["sla_id"] == sla_id and not v["resolved_at"]
        ]

        # Get error budget
        budget = SLAManagement._error_budgets.get(sla_id, {})

        # Get recent metrics
        window_start = datetime.utcnow() - timedelta(hours=sla["measurement_window_hours"])
        window_start_iso = window_start.isoformat()
        recent_metrics = [
            m for m in SLAManagement._sla_metrics
            if m["sla_id"] == sla_id and m["timestamp"] >= window_start_iso
        ]

        # Calculate average measured value
        avg_measured = None
        if recent_metrics:
            avg_measured = statistics.mean(m["measured_value"] for m in recent_metrics)

        # Determine compliance status
        compliance_pct = sla["current_compliance"]
        if compliance_pct >= sla["warning_threshold"]:
            compliance_status = ComplianceStatus.COMPLIANT
        elif compliance_pct >= (sla["warning_threshold"] * 0.8):
            compliance_status = ComplianceStatus.AT_RISK
        else:
            compliance_status = ComplianceStatus.NON_COMPLIANT

        return {
            "sla_id": sla_id,
            "name": sla["name"],
            "service_name": sla["service_name"],
            "status": sla["status"],
            "compliance_status": compliance_status,
            "current_compliance": compliance_pct,
            "target_value": sla["target_value"],
            "average_measured": avg_measured,
            "active_violations": len(recent_violations),
            "total_violations": sla["total_violations"],
            "total_penalties": sla["total_penalties"],
            "error_budget": budget,
            "measurement_window_hours": sla["measurement_window_hours"],
            "last_measured": sla["last_measured"],
            "checked_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_violations(
        session,
        sla_id: Optional[str] = None,
        severity: Optional[SLASeverity] = None,
        resolved: Optional[bool] = None
    ) -> List[dict]:
        """Get SLA violations with optional filtering."""
        violations = list(SLAManagement._violations.values())

        if sla_id:
            violations = [v for v in violations if v["sla_id"] == sla_id]

        if severity:
            violations = [v for v in violations if v["severity"] == severity]

        if resolved is not None:
            if resolved:
                violations = [v for v in violations if v["resolved_at"] is not None]
            else:
                violations = [v for v in violations if v["resolved_at"] is None]

        # Sort by detected time descending
        violations.sort(key=lambda x: x["detected_at"], reverse=True)

        return violations

    @staticmethod
    def acknowledge_violation(
        session,
        violation_id: str,
        notes: Optional[str] = None
    ) -> dict:
        """Acknowledge an SLA violation."""
        violation = SLAManagement._violations.get(violation_id)
        if not violation:
            raise ValueError(f"Violation not found: {violation_id}")

        if violation["acknowledged"]:
            raise ValueError("Violation already acknowledged")

        violation["acknowledged"] = True
        violation["acknowledged_at"] = datetime.utcnow().isoformat()
        violation["acknowledgement_notes"] = notes

        return {
            "violation_id": violation_id,
            "acknowledged": True,
            "acknowledged_at": violation["acknowledged_at"]
        }

    @staticmethod
    def resolve_violation(
        session,
        violation_id: str,
        resolution_notes: str
    ) -> dict:
        """Resolve an SLA violation."""
        violation = SLAManagement._violations.get(violation_id)
        if not violation:
            raise ValueError(f"Violation not found: {violation_id}")

        if violation["resolved_at"]:
            raise ValueError("Violation already resolved")

        violation["resolved_at"] = datetime.utcnow().isoformat()
        violation["resolution_notes"] = resolution_notes

        # Update SLA status if no more active violations
        sla = SLAManagement._slas.get(violation["sla_id"])
        if sla:
            active_violations = [
                v for v in SLAManagement._violations.values()
                if v["sla_id"] == sla["sla_id"] and not v["resolved_at"]
            ]
            if not active_violations and sla["current_compliance"] >= sla["warning_threshold"]:
                sla["status"] = SLAStatus.ACTIVE

        return {
            "violation_id": violation_id,
            "resolved": True,
            "resolved_at": violation["resolved_at"]
        }

    @staticmethod
    def generate_compliance_report(
        session,
        sla_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None
    ) -> dict:
        """Generate compliance report for an SLA."""
        sla = SLAManagement._slas.get(sla_id)
        if not sla:
            raise ValueError(f"SLA not found: {sla_id}")

        # Default to last 30 days if not specified
        if not end_time:
            end_time = datetime.utcnow().isoformat()
        if not start_time:
            start_time = (datetime.utcnow() - timedelta(days=30)).isoformat()

        # Get metrics in time range
        metrics = [
            m for m in SLAManagement._sla_metrics
            if m["sla_id"] == sla_id
            and m["timestamp"] >= start_time
            and m["timestamp"] <= end_time
        ]

        # Get violations in time range
        violations = [
            v for v in SLAManagement._violations.values()
            if v["sla_id"] == sla_id
            and v["detected_at"] >= start_time
            and v["detected_at"] <= end_time
        ]

        # Calculate statistics
        total_measurements = len(metrics)
        total_violations = len(violations)
        compliance_rate = 0.0
        if total_measurements > 0:
            compliance_rate = ((total_measurements - total_violations) / total_measurements) * 100

        # Group violations by severity
        violations_by_severity = defaultdict(int)
        for v in violations:
            violations_by_severity[v["severity"]] += 1

        # Calculate average measured value
        avg_measured = None
        if metrics:
            avg_measured = statistics.mean(m["measured_value"] for m in metrics)

        # Calculate uptime percentage (if applicable)
        uptime_percent = None
        if sla["metric_type"] == SLAMetricType.UPTIME and metrics:
            uptime_percent = statistics.mean(m["measured_value"] for m in metrics)

        report_id = f"report_{sla_id}_{datetime.utcnow().timestamp()}"

        report = {
            "report_id": report_id,
            "sla_id": sla_id,
            "sla_name": sla["name"],
            "service_name": sla["service_name"],
            "report_period": {
                "start": start_time,
                "end": end_time
            },
            "compliance_rate": compliance_rate,
            "target_value": sla["target_value"],
            "average_measured": avg_measured,
            "uptime_percent": uptime_percent,
            "total_measurements": total_measurements,
            "total_violations": total_violations,
            "violations_by_severity": dict(violations_by_severity),
            "total_penalties": sum(v["penalty"] for v in violations),
            "generated_at": datetime.utcnow().isoformat()
        }

        SLAManagement._compliance_reports[report_id] = report

        return report

    @staticmethod
    def update_sla(
        session,
        sla_id: str,
        target_value: Optional[float] = None,
        warning_threshold: Optional[float] = None,
        penalty_per_violation: Optional[float] = None,
        status: Optional[SLAStatus] = None
    ) -> dict:
        """Update an SLA definition."""
        sla = SLAManagement._slas.get(sla_id)
        if not sla:
            raise ValueError(f"SLA not found: {sla_id}")

        # Update fields
        if target_value is not None:
            sla["target_value"] = target_value
        if warning_threshold is not None:
            if warning_threshold < 0 or warning_threshold > 100:
                raise ValueError("Warning threshold must be between 0 and 100")
            sla["warning_threshold"] = warning_threshold
        if penalty_per_violation is not None:
            sla["penalty_per_violation"] = penalty_per_violation
        if status is not None:
            sla["status"] = status

        sla["updated_at"] = datetime.utcnow().isoformat()
        sla["version"] += 1

        # Store version history
        SLAManagement._sla_versions[sla_id].append({
            "version": sla["version"],
            "sla_data": sla.copy(),
            "created_at": sla["updated_at"]
        })

        return sla

    @staticmethod
    def reset_error_budget(session, sla_id: str) -> dict:
        """Reset error budget for an SLA."""
        budget = SLAManagement._error_budgets.get(sla_id)
        if not budget:
            raise ValueError(f"Error budget not found for SLA: {sla_id}")

        budget["remaining_budget_percent"] = budget["total_budget_percent"]
        budget["consumed_budget_percent"] = 0.0
        budget["violation_count"] = 0
        budget["budget_window_start"] = datetime.utcnow().isoformat()
        budget["budget_window_end"] = (datetime.utcnow() + timedelta(days=30)).isoformat()
        budget["last_reset"] = datetime.utcnow().isoformat()

        return budget

    @staticmethod
    def get_sla_history(session, sla_id: str) -> List[dict]:
        """Get version history for an SLA."""
        history = SLAManagement._sla_versions.get(sla_id, [])
        return sorted(history, key=lambda x: x["version"], reverse=True)

    @staticmethod
    def get_statistics(session) -> dict:
        """Get SLA management statistics."""
        # SLA stats
        total_slas = len(SLAManagement._slas)
        active_slas = sum(1 for s in SLAManagement._slas.values() if s["status"] == SLAStatus.ACTIVE)
        breached_slas = sum(1 for s in SLAManagement._slas.values() if s["status"] == SLAStatus.BREACHED)

        # Violation stats
        total_violations = len(SLAManagement._violations)
        active_violations = sum(1 for v in SLAManagement._violations.values() if not v["resolved_at"])

        violations_by_severity = defaultdict(int)
        for v in SLAManagement._violations.values():
            violations_by_severity[v["severity"]] += 1

        # Compliance stats
        compliance_rates = [s["current_compliance"] for s in SLAManagement._slas.values()]
        avg_compliance = statistics.mean(compliance_rates) if compliance_rates else 0.0

        # Error budget stats
        budgets_depleted = sum(
            1 for b in SLAManagement._error_budgets.values()
            if b["remaining_budget_percent"] <= 0
        )

        return {
            "slas": {
                "total": total_slas,
                "active": active_slas,
                "breached": breached_slas,
                "warning": sum(1 for s in SLAManagement._slas.values() if s["status"] == SLAStatus.WARNING),
                "suspended": sum(1 for s in SLAManagement._slas.values() if s["status"] == SLAStatus.SUSPENDED)
            },
            "violations": {
                "total": total_violations,
                "active": active_violations,
                "resolved": total_violations - active_violations,
                "by_severity": dict(violations_by_severity)
            },
            "compliance": {
                "average_rate": avg_compliance,
                "compliant_slas": sum(1 for s in SLAManagement._slas.values() if s["current_compliance"] >= s["warning_threshold"]),
                "at_risk_slas": sum(1 for s in SLAManagement._slas.values() if s["warning_threshold"] * 0.8 <= s["current_compliance"] < s["warning_threshold"])
            },
            "error_budgets": {
                "total": len(SLAManagement._error_budgets),
                "depleted": budgets_depleted,
                "healthy": len(SLAManagement._error_budgets) - budgets_depleted
            },
            "metrics": {
                "total_recorded": len(SLAManagement._sla_metrics),
                "reports_generated": len(SLAManagement._compliance_reports)
            }
        }
