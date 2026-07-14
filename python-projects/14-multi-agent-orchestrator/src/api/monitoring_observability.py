"""
Monitoring and Observability API

REST API endpoints for monitoring, metrics collection, and observability.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.monitoring_observability import (
    MonitoringObservability,
    MetricType,
    AlertSeverity,
    AlertStatus,
    HealthStatus
)


router = APIRouter()


# Request/Response Models
class CreateMetricRequest(BaseModel):
    """Request model for creating a metric"""
    metric_id: str = Field(..., description="Unique metric identifier")
    name: str = Field(..., description="Metric name")
    metric_type: MetricType = Field(..., description="Type of metric")
    description: str = Field(default="", description="Metric description")
    unit: str = Field(default="", description="Unit of measurement")
    labels: Optional[Dict[str, str]] = Field(default=None, description="Metric labels")
    retention_days: int = Field(default=30, description="Data retention in days", ge=1, le=365)


class RecordMetricRequest(BaseModel):
    """Request model for recording a metric"""
    value: float = Field(..., description="Metric value")
    timestamp: Optional[str] = Field(default=None, description="ISO timestamp")
    labels: Optional[Dict[str, str]] = Field(default=None, description="Additional labels")


class QueryMetricsRequest(BaseModel):
    """Request model for querying metrics"""
    start_time: Optional[str] = Field(default=None, description="Start time (ISO)")
    end_time: Optional[str] = Field(default=None, description="End time (ISO)")
    aggregation: Optional[str] = Field(default=None, description="Aggregation function")
    interval: Optional[str] = Field(default=None, description="Time interval")


class CreateAlertRuleRequest(BaseModel):
    """Request model for creating an alert rule"""
    rule_id: str = Field(..., description="Unique rule identifier")
    name: str = Field(..., description="Rule name")
    metric_id: str = Field(..., description="Metric to monitor")
    condition: str = Field(..., description="Condition (gt, gte, lt, lte, eq, ne)")
    threshold: float = Field(..., description="Threshold value")
    severity: AlertSeverity = Field(..., description="Alert severity")
    duration: Optional[int] = Field(default=None, description="Duration in seconds")
    notification_channels: Optional[List[str]] = Field(default=None, description="Notification channels")
    enabled: bool = Field(default=True, description="Whether rule is enabled")


class UpdateAlertStatusRequest(BaseModel):
    """Request model for updating alert status"""
    status: AlertStatus = Field(..., description="New alert status")
    notes: Optional[str] = Field(default=None, description="Additional notes")


class RegisterServiceRequest(BaseModel):
    """Request model for registering a service"""
    service_id: str = Field(..., description="Unique service identifier")
    name: str = Field(..., description="Service name")
    service_type: str = Field(..., description="Service type")
    endpoints: Optional[List[str]] = Field(default=None, description="Service endpoints")
    dependencies: Optional[List[str]] = Field(default=None, description="Service dependencies")
    health_check_url: Optional[str] = Field(default=None, description="Health check URL")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")


class UpdateServiceHealthRequest(BaseModel):
    """Request model for updating service health"""
    status: HealthStatus = Field(..., description="Health status")
    response_time_ms: Optional[float] = Field(default=None, description="Response time in ms")
    error_message: Optional[str] = Field(default=None, description="Error message if unhealthy")


class CreateDashboardRequest(BaseModel):
    """Request model for creating a dashboard"""
    dashboard_id: str = Field(..., description="Unique dashboard identifier")
    name: str = Field(..., description="Dashboard name")
    description: str = Field(default="", description="Dashboard description")
    widgets: Optional[List[Dict]] = Field(default=None, description="Dashboard widgets")
    refresh_interval: int = Field(default=60, description="Refresh interval in seconds", ge=5)


class ConfigureSLARequest(BaseModel):
    """Request model for configuring SLA"""
    sla_id: str = Field(..., description="Unique SLA identifier")
    name: str = Field(..., description="SLA name")
    metric_id: str = Field(..., description="Metric to track")
    target_value: float = Field(..., description="Target value")
    comparison: str = Field(..., description="Comparison operator (gte, lte, etc.)")
    time_window: int = Field(..., description="Time window in days", ge=1)
    compliance_threshold: float = Field(default=99.0, description="Compliance threshold percentage", ge=0, le=100)


# API Endpoints
@router.post("/metrics")
def create_metric(
    request: CreateMetricRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a new metric definition.
    Defines a metric for collecting time-series data.
    """
    try:
        result = MonitoringObservability.create_metric(
            session=session,
            metric_id=request.metric_id,
            name=request.name,
            metric_type=request.metric_type,
            description=request.description,
            unit=request.unit,
            labels=request.labels,
            retention_days=request.retention_days
        )
        return {
            "success": True,
            "metric": result,
            "message": f"Metric created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating metric: {str(e)}")


@router.post("/metrics/{metric_id}/record")
def record_metric(
    metric_id: str,
    request: RecordMetricRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record a metric data point.
    Stores a value for the specified metric.
    Automatically checks alert rules.
    """
    try:
        result = MonitoringObservability.record_metric(
            session=session,
            metric_id=metric_id,
            value=request.value,
            timestamp=request.timestamp,
            labels=request.labels
        )
        return {
            "success": True,
            "recording": result,
            "message": f"Metric recorded: {metric_id}={request.value}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error recording metric: {str(e)}")


@router.post("/metrics/{metric_id}/query")
def query_metrics(
    metric_id: str,
    request: QueryMetricsRequest,
    session: Session = Depends(get_db_session)
):
    """
    Query metric data.
    Retrieves time-series data with optional aggregation.
    Supports avg, sum, min, max, count, p50, p95, p99.
    """
    try:
        result = MonitoringObservability.query_metrics(
            session=session,
            metric_id=metric_id,
            start_time=request.start_time,
            end_time=request.end_time,
            aggregation=request.aggregation,
            interval=request.interval
        )
        return {
            "success": True,
            "query_result": result,
            "message": "Metrics queried successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error querying metrics: {str(e)}")


@router.get("/metrics")
def list_metrics(session: Session = Depends(get_db_session)):
    """
    List all metrics.
    Returns all metric definitions.
    """
    try:
        metrics = list(MonitoringObservability._metrics.values())
        return {
            "success": True,
            "metrics": metrics,
            "count": len(metrics)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing metrics: {str(e)}")


@router.post("/alert-rules")
def create_alert_rule(
    request: CreateAlertRuleRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create an alert rule.
    Defines conditions for triggering alerts based on metric values.
    """
    try:
        result = MonitoringObservability.create_alert_rule(
            session=session,
            rule_id=request.rule_id,
            name=request.name,
            metric_id=request.metric_id,
            condition=request.condition,
            threshold=request.threshold,
            severity=request.severity,
            duration=request.duration,
            notification_channels=request.notification_channels,
            enabled=request.enabled
        )
        return {
            "success": True,
            "alert_rule": result,
            "message": f"Alert rule created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating alert rule: {str(e)}")


@router.get("/alert-rules")
def list_alert_rules(session: Session = Depends(get_db_session)):
    """
    List all alert rules.
    Returns all configured alert rules.
    """
    try:
        rules = list(MonitoringObservability._alert_rules.values())
        return {
            "success": True,
            "alert_rules": rules,
            "count": len(rules)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing alert rules: {str(e)}")


@router.get("/alerts")
def get_alerts(
    status: Optional[AlertStatus] = None,
    severity: Optional[AlertSeverity] = None,
    metric_id: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get alerts.
    Retrieves alerts with optional filtering by status, severity, or metric.
    """
    try:
        alerts = MonitoringObservability.get_alerts(
            session=session,
            status=status,
            severity=severity,
            metric_id=metric_id
        )
        return {
            "success": True,
            "alerts": alerts,
            "count": len(alerts)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting alerts: {str(e)}")


@router.put("/alerts/{alert_id}/status")
def update_alert_status(
    alert_id: str,
    request: UpdateAlertStatusRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update alert status.
    Acknowledge, resolve, or silence an alert.
    """
    try:
        result = MonitoringObservability.update_alert_status(
            session=session,
            alert_id=alert_id,
            status=request.status,
            notes=request.notes
        )
        return {
            "success": True,
            "update": result,
            "message": f"Alert status updated to: {request.status}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating alert status: {str(e)}")


@router.post("/services")
def register_service(
    request: RegisterServiceRequest,
    session: Session = Depends(get_db_session)
):
    """
    Register a service for monitoring.
    Adds a service to the monitoring system.
    """
    try:
        result = MonitoringObservability.register_service(
            session=session,
            service_id=request.service_id,
            name=request.name,
            service_type=request.service_type,
            endpoints=request.endpoints,
            dependencies=request.dependencies,
            health_check_url=request.health_check_url,
            metadata=request.metadata
        )
        return {
            "success": True,
            "service": result,
            "message": f"Service registered: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error registering service: {str(e)}")


@router.put("/services/{service_id}/health")
def update_service_health(
    service_id: str,
    request: UpdateServiceHealthRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update service health status.
    Records health check result for a service.
    """
    try:
        result = MonitoringObservability.update_service_health(
            session=session,
            service_id=service_id,
            status=request.status,
            response_time_ms=request.response_time_ms,
            error_message=request.error_message
        )
        return {
            "success": True,
            "health_check": result,
            "message": f"Service health updated: {request.status}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating service health: {str(e)}")


@router.get("/services/health")
def get_service_health(
    service_id: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get service health status.
    Returns health information for one or all services.
    """
    try:
        result = MonitoringObservability.get_service_health(
            session=session,
            service_id=service_id
        )
        return {
            "success": True,
            "health": result,
            "message": "Service health retrieved"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting service health: {str(e)}")


@router.post("/dashboards")
def create_dashboard(
    request: CreateDashboardRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a monitoring dashboard.
    Defines a dashboard for visualizing metrics and alerts.
    """
    try:
        result = MonitoringObservability.create_dashboard(
            session=session,
            dashboard_id=request.dashboard_id,
            name=request.name,
            description=request.description,
            widgets=request.widgets,
            refresh_interval=request.refresh_interval
        )
        return {
            "success": True,
            "dashboard": result,
            "message": f"Dashboard created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating dashboard: {str(e)}")


@router.get("/dashboards/{dashboard_id}")
def get_dashboard_data(
    dashboard_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get dashboard with data.
    Returns dashboard definition with populated widget data.
    """
    try:
        result = MonitoringObservability.get_dashboard_data(
            session=session,
            dashboard_id=dashboard_id
        )
        return {
            "success": True,
            "dashboard": result,
            "message": "Dashboard data retrieved"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting dashboard data: {str(e)}")


@router.post("/sla")
def configure_sla(
    request: ConfigureSLARequest,
    session: Session = Depends(get_db_session)
):
    """
    Configure SLA monitoring.
    Sets up service level agreement tracking for a metric.
    """
    try:
        result = MonitoringObservability.configure_sla(
            session=session,
            sla_id=request.sla_id,
            name=request.name,
            metric_id=request.metric_id,
            target_value=request.target_value,
            comparison=request.comparison,
            time_window=request.time_window,
            compliance_threshold=request.compliance_threshold
        )
        return {
            "success": True,
            "sla": result,
            "message": f"SLA configured: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error configuring SLA: {str(e)}")


@router.get("/sla/{sla_id}/compliance")
def get_sla_compliance(
    sla_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get SLA compliance.
    Calculates compliance percentage for the configured time window.
    """
    try:
        result = MonitoringObservability.get_sla_compliance(
            session=session,
            sla_id=sla_id
        )
        return {
            "success": True,
            "compliance": result,
            "message": f"SLA compliance calculated: {result.get('status')}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting SLA compliance: {str(e)}")


@router.get("/statistics")
def get_statistics(session: Session = Depends(get_db_session)):
    """
    Get monitoring statistics.
    Returns comprehensive statistics about all monitoring components.
    """
    try:
        stats = MonitoringObservability.get_statistics(session)
        return {
            "success": True,
            "statistics": stats,
            "message": "Statistics retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")
