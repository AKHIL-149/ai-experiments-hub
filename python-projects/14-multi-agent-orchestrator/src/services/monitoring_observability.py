"""
Monitoring and Observability Service

Provides comprehensive monitoring, metrics collection, and observability features
for tracking system health, performance, and SLA compliance.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from enum import Enum
import statistics


class MetricType(str, Enum):
    """Types of metrics"""
    COUNTER = "counter"  # Monotonically increasing
    GAUGE = "gauge"  # Point-in-time value
    HISTOGRAM = "histogram"  # Distribution of values
    SUMMARY = "summary"  # Statistical summary


class AlertSeverity(str, Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Alert status"""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SILENCED = "silenced"


class HealthStatus(str, Enum):
    """Service health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class MonitoringObservability:
    """Monitoring and observability management"""

    # In-memory storage
    _metrics: Dict[str, Dict] = {}
    _metric_data: Dict[str, List[Dict]] = defaultdict(list)
    _alerts: Dict[str, Dict] = {}
    _alert_rules: Dict[str, Dict] = {}
    _services: Dict[str, Dict] = {}
    _dashboards: Dict[str, Dict] = {}
    _sla_configs: Dict[str, Dict] = {}

    @staticmethod
    def create_metric(
        session,
        metric_id: str,
        name: str,
        metric_type: MetricType,
        description: str = "",
        unit: str = "",
        labels: Optional[Dict[str, str]] = None,
        retention_days: int = 30
    ) -> dict:
        """Create a new metric definition."""
        if metric_id in MonitoringObservability._metrics:
            raise ValueError(f"Metric already exists: {metric_id}")

        metric = {
            "metric_id": metric_id,
            "name": name,
            "metric_type": metric_type,
            "description": description,
            "unit": unit,
            "labels": labels or {},
            "retention_days": retention_days,
            "created_at": datetime.utcnow().isoformat(),
            "data_points": 0,
            "last_value": None,
            "last_updated": None
        }

        MonitoringObservability._metrics[metric_id] = metric
        return metric

    @staticmethod
    def record_metric(
        session,
        metric_id: str,
        value: float,
        timestamp: Optional[str] = None,
        labels: Optional[Dict[str, str]] = None
    ) -> dict:
        """Record a metric data point."""
        metric = MonitoringObservability._metrics.get(metric_id)
        if not metric:
            raise ValueError(f"Metric not found: {metric_id}")

        data_point = {
            "value": value,
            "timestamp": timestamp or datetime.utcnow().isoformat(),
            "labels": labels or {},
            "metric_type": metric["metric_type"]
        }

        # Store data point
        MonitoringObservability._metric_data[metric_id].append(data_point)

        # Update metric metadata
        metric["data_points"] += 1
        metric["last_value"] = value
        metric["last_updated"] = data_point["timestamp"]

        # Apply retention policy
        MonitoringObservability._apply_retention(metric_id, metric["retention_days"])

        # Check alert rules
        triggered_alerts = MonitoringObservability._check_alert_rules(metric_id, value)

        return {
            "metric_id": metric_id,
            "data_point": data_point,
            "triggered_alerts": triggered_alerts
        }

    @staticmethod
    def _apply_retention(metric_id: str, retention_days: int):
        """Apply retention policy to metric data."""
        cutoff = datetime.utcnow() - timedelta(days=retention_days)
        cutoff_iso = cutoff.isoformat()

        data_points = MonitoringObservability._metric_data[metric_id]
        MonitoringObservability._metric_data[metric_id] = [
            dp for dp in data_points
            if dp["timestamp"] >= cutoff_iso
        ]

    @staticmethod
    def query_metrics(
        session,
        metric_id: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        aggregation: Optional[str] = None,
        interval: Optional[str] = None
    ) -> dict:
        """Query metric data with optional aggregation."""
        metric = MonitoringObservability._metrics.get(metric_id)
        if not metric:
            raise ValueError(f"Metric not found: {metric_id}")

        # Filter by time range
        data_points = MonitoringObservability._metric_data[metric_id]

        if start_time:
            data_points = [dp for dp in data_points if dp["timestamp"] >= start_time]
        if end_time:
            data_points = [dp for dp in data_points if dp["timestamp"] <= end_time]

        # Apply aggregation
        if aggregation:
            values = [dp["value"] for dp in data_points]
            if not values:
                aggregated_value = None
            elif aggregation == "avg":
                aggregated_value = statistics.mean(values)
            elif aggregation == "sum":
                aggregated_value = sum(values)
            elif aggregation == "min":
                aggregated_value = min(values)
            elif aggregation == "max":
                aggregated_value = max(values)
            elif aggregation == "count":
                aggregated_value = len(values)
            elif aggregation == "p50":
                aggregated_value = statistics.median(values)
            elif aggregation == "p95":
                aggregated_value = statistics.quantiles(values, n=20)[18] if len(values) > 1 else values[0]
            elif aggregation == "p99":
                aggregated_value = statistics.quantiles(values, n=100)[98] if len(values) > 1 else values[0]
            else:
                aggregated_value = None

            return {
                "metric_id": metric_id,
                "aggregation": aggregation,
                "value": aggregated_value,
                "data_points_count": len(data_points),
                "time_range": {
                    "start": start_time,
                    "end": end_time
                }
            }

        return {
            "metric_id": metric_id,
            "data_points": data_points,
            "count": len(data_points)
        }

    @staticmethod
    def create_alert_rule(
        session,
        rule_id: str,
        name: str,
        metric_id: str,
        condition: str,
        threshold: float,
        severity: AlertSeverity,
        duration: Optional[int] = None,
        notification_channels: Optional[List[str]] = None,
        enabled: bool = True
    ) -> dict:
        """Create an alert rule for a metric."""
        if rule_id in MonitoringObservability._alert_rules:
            raise ValueError(f"Alert rule already exists: {rule_id}")

        if metric_id not in MonitoringObservability._metrics:
            raise ValueError(f"Metric not found: {metric_id}")

        # Validate condition
        valid_conditions = ["gt", "gte", "lt", "lte", "eq", "ne"]
        if condition not in valid_conditions:
            raise ValueError(f"Invalid condition. Must be one of: {valid_conditions}")

        rule = {
            "rule_id": rule_id,
            "name": name,
            "metric_id": metric_id,
            "condition": condition,
            "threshold": threshold,
            "severity": severity,
            "duration": duration,  # Seconds condition must be true
            "notification_channels": notification_channels or [],
            "enabled": enabled,
            "created_at": datetime.utcnow().isoformat(),
            "triggered_count": 0,
            "last_triggered": None
        }

        MonitoringObservability._alert_rules[rule_id] = rule
        return rule

    @staticmethod
    def _check_alert_rules(metric_id: str, value: float) -> List[str]:
        """Check if any alert rules are triggered by this value."""
        triggered = []

        for rule_id, rule in MonitoringObservability._alert_rules.items():
            if rule["metric_id"] != metric_id or not rule["enabled"]:
                continue

            condition = rule["condition"]
            threshold = rule["threshold"]

            is_triggered = False
            if condition == "gt" and value > threshold:
                is_triggered = True
            elif condition == "gte" and value >= threshold:
                is_triggered = True
            elif condition == "lt" and value < threshold:
                is_triggered = True
            elif condition == "lte" and value <= threshold:
                is_triggered = True
            elif condition == "eq" and value == threshold:
                is_triggered = True
            elif condition == "ne" and value != threshold:
                is_triggered = True

            if is_triggered:
                # Create alert
                alert_id = f"alert_{rule_id}_{datetime.utcnow().timestamp()}"
                alert = {
                    "alert_id": alert_id,
                    "rule_id": rule_id,
                    "metric_id": metric_id,
                    "value": value,
                    "threshold": threshold,
                    "severity": rule["severity"],
                    "status": AlertStatus.ACTIVE,
                    "created_at": datetime.utcnow().isoformat(),
                    "acknowledged_at": None,
                    "resolved_at": None,
                    "message": f"{rule['name']}: {value} {condition} {threshold}"
                }

                MonitoringObservability._alerts[alert_id] = alert
                rule["triggered_count"] += 1
                rule["last_triggered"] = alert["created_at"]
                triggered.append(alert_id)

        return triggered

    @staticmethod
    def get_alerts(
        session,
        status: Optional[AlertStatus] = None,
        severity: Optional[AlertSeverity] = None,
        metric_id: Optional[str] = None
    ) -> List[dict]:
        """Get alerts with optional filtering."""
        alerts = list(MonitoringObservability._alerts.values())

        if status:
            alerts = [a for a in alerts if a["status"] == status]
        if severity:
            alerts = [a for a in alerts if a["severity"] == severity]
        if metric_id:
            alerts = [a for a in alerts if a["metric_id"] == metric_id]

        # Sort by created_at descending
        alerts.sort(key=lambda x: x["created_at"], reverse=True)
        return alerts

    @staticmethod
    def update_alert_status(
        session,
        alert_id: str,
        status: AlertStatus,
        notes: Optional[str] = None
    ) -> dict:
        """Update alert status (acknowledge, resolve, silence)."""
        alert = MonitoringObservability._alerts.get(alert_id)
        if not alert:
            raise ValueError(f"Alert not found: {alert_id}")

        old_status = alert["status"]
        alert["status"] = status

        if status == AlertStatus.ACKNOWLEDGED:
            alert["acknowledged_at"] = datetime.utcnow().isoformat()
        elif status == AlertStatus.RESOLVED:
            alert["resolved_at"] = datetime.utcnow().isoformat()

        if notes:
            alert["notes"] = notes

        return {
            "alert_id": alert_id,
            "old_status": old_status,
            "new_status": status,
            "updated_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def register_service(
        session,
        service_id: str,
        name: str,
        service_type: str,
        endpoints: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        health_check_url: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> dict:
        """Register a service for monitoring."""
        if service_id in MonitoringObservability._services:
            raise ValueError(f"Service already registered: {service_id}")

        service = {
            "service_id": service_id,
            "name": name,
            "service_type": service_type,
            "endpoints": endpoints or [],
            "dependencies": dependencies or [],
            "health_check_url": health_check_url,
            "metadata": metadata or {},
            "status": HealthStatus.UNKNOWN,
            "registered_at": datetime.utcnow().isoformat(),
            "last_health_check": None,
            "uptime_percentage": 100.0,
            "health_checks_total": 0,
            "health_checks_failed": 0
        }

        MonitoringObservability._services[service_id] = service
        return service

    @staticmethod
    def update_service_health(
        session,
        service_id: str,
        status: HealthStatus,
        response_time_ms: Optional[float] = None,
        error_message: Optional[str] = None
    ) -> dict:
        """Update service health status."""
        service = MonitoringObservability._services.get(service_id)
        if not service:
            raise ValueError(f"Service not found: {service_id}")

        old_status = service["status"]
        service["status"] = status
        service["last_health_check"] = datetime.utcnow().isoformat()
        service["health_checks_total"] += 1

        if status != HealthStatus.HEALTHY:
            service["health_checks_failed"] += 1

        # Update uptime percentage
        service["uptime_percentage"] = (
            (service["health_checks_total"] - service["health_checks_failed"]) /
            service["health_checks_total"] * 100
        )

        health_check = {
            "service_id": service_id,
            "old_status": old_status,
            "new_status": status,
            "response_time_ms": response_time_ms,
            "error_message": error_message,
            "timestamp": service["last_health_check"]
        }

        return health_check

    @staticmethod
    def get_service_health(
        session,
        service_id: Optional[str] = None
    ) -> dict:
        """Get health status of services."""
        if service_id:
            service = MonitoringObservability._services.get(service_id)
            if not service:
                raise ValueError(f"Service not found: {service_id}")
            return service

        # Return all services with health summary
        services = list(MonitoringObservability._services.values())

        summary = {
            "total": len(services),
            "healthy": sum(1 for s in services if s["status"] == HealthStatus.HEALTHY),
            "degraded": sum(1 for s in services if s["status"] == HealthStatus.DEGRADED),
            "unhealthy": sum(1 for s in services if s["status"] == HealthStatus.UNHEALTHY),
            "unknown": sum(1 for s in services if s["status"] == HealthStatus.UNKNOWN)
        }

        return {
            "services": services,
            "summary": summary
        }

    @staticmethod
    def create_dashboard(
        session,
        dashboard_id: str,
        name: str,
        description: str = "",
        widgets: Optional[List[Dict]] = None,
        refresh_interval: int = 60
    ) -> dict:
        """Create a monitoring dashboard."""
        if dashboard_id in MonitoringObservability._dashboards:
            raise ValueError(f"Dashboard already exists: {dashboard_id}")

        dashboard = {
            "dashboard_id": dashboard_id,
            "name": name,
            "description": description,
            "widgets": widgets or [],
            "refresh_interval": refresh_interval,
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": None,
            "views": 0
        }

        MonitoringObservability._dashboards[dashboard_id] = dashboard
        return dashboard

    @staticmethod
    def get_dashboard_data(
        session,
        dashboard_id: str
    ) -> dict:
        """Get dashboard with populated widget data."""
        dashboard = MonitoringObservability._dashboards.get(dashboard_id)
        if not dashboard:
            raise ValueError(f"Dashboard not found: {dashboard_id}")

        dashboard["views"] += 1

        # Populate widget data
        widgets_with_data = []
        for widget in dashboard["widgets"]:
            widget_data = widget.copy()

            if widget["type"] == "metric":
                metric_id = widget.get("metric_id")
                if metric_id:
                    result = MonitoringObservability.query_metrics(
                        session,
                        metric_id=metric_id,
                        aggregation=widget.get("aggregation", "avg")
                    )
                    widget_data["data"] = result

            elif widget["type"] == "service_health":
                health_data = MonitoringObservability.get_service_health(session)
                widget_data["data"] = health_data

            elif widget["type"] == "alerts":
                alerts = MonitoringObservability.get_alerts(
                    session,
                    status=AlertStatus.ACTIVE
                )
                widget_data["data"] = alerts

            widgets_with_data.append(widget_data)

        dashboard_copy = dashboard.copy()
        dashboard_copy["widgets"] = widgets_with_data
        dashboard_copy["generated_at"] = datetime.utcnow().isoformat()

        return dashboard_copy

    @staticmethod
    def configure_sla(
        session,
        sla_id: str,
        name: str,
        metric_id: str,
        target_value: float,
        comparison: str,  # "gte", "lte", etc.
        time_window: int,  # Days
        compliance_threshold: float = 99.0
    ) -> dict:
        """Configure SLA monitoring."""
        if sla_id in MonitoringObservability._sla_configs:
            raise ValueError(f"SLA already exists: {sla_id}")

        if metric_id not in MonitoringObservability._metrics:
            raise ValueError(f"Metric not found: {metric_id}")

        sla = {
            "sla_id": sla_id,
            "name": name,
            "metric_id": metric_id,
            "target_value": target_value,
            "comparison": comparison,
            "time_window": time_window,
            "compliance_threshold": compliance_threshold,
            "created_at": datetime.utcnow().isoformat(),
            "current_compliance": None,
            "violations": []
        }

        MonitoringObservability._sla_configs[sla_id] = sla
        return sla

    @staticmethod
    def get_sla_compliance(
        session,
        sla_id: str
    ) -> dict:
        """Calculate SLA compliance."""
        sla = MonitoringObservability._sla_configs.get(sla_id)
        if not sla:
            raise ValueError(f"SLA not found: {sla_id}")

        # Get metric data for time window
        start_time = (datetime.utcnow() - timedelta(days=sla["time_window"])).isoformat()

        data_points = MonitoringObservability._metric_data[sla["metric_id"]]
        window_data = [dp for dp in data_points if dp["timestamp"] >= start_time]

        if not window_data:
            return {
                "sla_id": sla_id,
                "compliance": None,
                "status": "insufficient_data",
                "data_points": 0
            }

        # Calculate compliance
        target = sla["target_value"]
        comparison = sla["comparison"]

        compliant_count = 0
        for dp in window_data:
            value = dp["value"]

            is_compliant = False
            if comparison == "gte" and value >= target:
                is_compliant = True
            elif comparison == "lte" and value <= target:
                is_compliant = True
            elif comparison == "gt" and value > target:
                is_compliant = True
            elif comparison == "lt" and value < target:
                is_compliant = True
            elif comparison == "eq" and value == target:
                is_compliant = True

            if is_compliant:
                compliant_count += 1

        compliance_percentage = (compliant_count / len(window_data)) * 100

        sla["current_compliance"] = compliance_percentage

        status = "met" if compliance_percentage >= sla["compliance_threshold"] else "violated"

        return {
            "sla_id": sla_id,
            "name": sla["name"],
            "compliance": compliance_percentage,
            "status": status,
            "target": target,
            "threshold": sla["compliance_threshold"],
            "data_points": len(window_data),
            "compliant_points": compliant_count,
            "time_window_days": sla["time_window"]
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get monitoring statistics."""
        return {
            "metrics": {
                "total": len(MonitoringObservability._metrics),
                "by_type": {
                    mt.value: sum(1 for m in MonitoringObservability._metrics.values() if m["metric_type"] == mt)
                    for mt in MetricType
                },
                "total_data_points": sum(len(data) for data in MonitoringObservability._metric_data.values())
            },
            "alerts": {
                "total": len(MonitoringObservability._alerts),
                "by_status": {
                    status.value: sum(1 for a in MonitoringObservability._alerts.values() if a["status"] == status)
                    for status in AlertStatus
                },
                "by_severity": {
                    sev.value: sum(1 for a in MonitoringObservability._alerts.values() if a["severity"] == sev)
                    for sev in AlertSeverity
                }
            },
            "alert_rules": {
                "total": len(MonitoringObservability._alert_rules),
                "enabled": sum(1 for r in MonitoringObservability._alert_rules.values() if r["enabled"])
            },
            "services": {
                "total": len(MonitoringObservability._services),
                "by_status": {
                    status.value: sum(1 for s in MonitoringObservability._services.values() if s["status"] == status)
                    for status in HealthStatus
                }
            },
            "dashboards": len(MonitoringObservability._dashboards),
            "slas": len(MonitoringObservability._sla_configs)
        }
