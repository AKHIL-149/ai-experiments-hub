"""
Disaster Recovery and Failover API

REST API endpoints for disaster recovery planning and automated failover.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.disaster_recovery import (
    DisasterRecovery,
    FailoverStrategy,
    ReplicaStatus
)


router = APIRouter()


# Request/Response Models
class CreateDRPlanRequest(BaseModel):
    """Request model for creating a DR plan"""
    plan_id: str = Field(..., description="Unique plan identifier")
    name: str = Field(..., description="Plan name")
    strategy: FailoverStrategy = Field(..., description="Failover strategy")
    primary_region: str = Field(..., description="Primary region")
    secondary_region: str = Field(..., description="Secondary/DR region")
    rpo_minutes: int = Field(..., description="Recovery Point Objective (minutes)", ge=0)
    rto_minutes: int = Field(..., description="Recovery Time Objective (minutes)", ge=0)
    critical_services: List[str] = Field(..., description="List of critical services")
    enabled: bool = Field(default=True, description="Whether plan is enabled")


class CreateFailoverConfigRequest(BaseModel):
    """Request model for creating a failover config"""
    config_id: str = Field(..., description="Unique config identifier")
    plan_id: str = Field(..., description="DR plan ID")
    service_name: str = Field(..., description="Service name")
    primary_endpoint: str = Field(..., description="Primary endpoint URL")
    failover_endpoint: str = Field(..., description="Failover endpoint URL")
    health_check_interval: int = Field(default=30, description="Health check interval (seconds)", ge=1)
    failure_threshold: int = Field(default=3, description="Consecutive failures before failover", ge=1)
    auto_failover: bool = Field(default=True, description="Enable automatic failover")


class PerformHealthCheckRequest(BaseModel):
    """Request model for health check"""
    is_healthy: bool = Field(..., description="Whether service is healthy")
    response_time_ms: Optional[float] = Field(default=None, description="Response time in ms")
    error_message: Optional[str] = Field(default=None, description="Error message if unhealthy")


class TriggerFailoverRequest(BaseModel):
    """Request model for manual failover"""
    reason: str = Field(..., description="Reason for failover")


class CreateDRDrillRequest(BaseModel):
    """Request model for creating a DR drill"""
    drill_id: str = Field(..., description="Unique drill identifier")
    plan_id: str = Field(..., description="DR plan ID")
    name: str = Field(..., description="Drill name")
    scheduled_at: str = Field(..., description="ISO timestamp for scheduled execution")
    duration_minutes: int = Field(default=60, description="Expected duration (minutes)", ge=1)
    test_failover: bool = Field(default=True, description="Whether to test actual failover")


class CreateReplicaRequest(BaseModel):
    """Request model for creating a replica"""
    replica_id: str = Field(..., description="Unique replica identifier")
    plan_id: str = Field(..., description="DR plan ID")
    source_region: str = Field(..., description="Source region")
    target_region: str = Field(..., description="Target region")
    data_type: str = Field(..., description="Type of data being replicated")
    replication_lag_seconds: int = Field(default=0, description="Current replication lag", ge=0)


class UpdateReplicaStatusRequest(BaseModel):
    """Request model for updating replica status"""
    status: ReplicaStatus = Field(..., description="Replica status")
    replication_lag_seconds: int = Field(..., description="Current replication lag (seconds)", ge=0)
    bytes_replicated: int = Field(..., description="Total bytes replicated", ge=0)


# API Endpoints
@router.post("/plans")
def create_dr_plan(
    request: CreateDRPlanRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a DR plan.
    Defines disaster recovery strategy, RPO/RTO objectives, and critical services.
    """
    try:
        result = DisasterRecovery.create_dr_plan(
            session=session,
            plan_id=request.plan_id,
            name=request.name,
            strategy=request.strategy,
            primary_region=request.primary_region,
            secondary_region=request.secondary_region,
            rpo_minutes=request.rpo_minutes,
            rto_minutes=request.rto_minutes,
            critical_services=request.critical_services,
            enabled=request.enabled
        )
        return {
            "success": True,
            "plan": result,
            "message": f"DR plan created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating DR plan: {str(e)}")


@router.get("/plans")
def list_dr_plans(session: Session = Depends(get_db_session)):
    """
    List all DR plans.
    Returns all disaster recovery plans.
    """
    try:
        plans = list(DisasterRecovery._dr_plans.values())
        return {
            "success": True,
            "plans": plans,
            "count": len(plans)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing DR plans: {str(e)}")


@router.post("/failover-configs")
def create_failover_config(
    request: CreateFailoverConfigRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a failover configuration.
    Defines failover endpoints and health check parameters for a service.
    """
    try:
        result = DisasterRecovery.create_failover_config(
            session=session,
            config_id=request.config_id,
            plan_id=request.plan_id,
            service_name=request.service_name,
            primary_endpoint=request.primary_endpoint,
            failover_endpoint=request.failover_endpoint,
            health_check_interval=request.health_check_interval,
            failure_threshold=request.failure_threshold,
            auto_failover=request.auto_failover
        )
        return {
            "success": True,
            "config": result,
            "message": f"Failover config created for: {request.service_name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating failover config: {str(e)}")


@router.get("/failover-configs")
def list_failover_configs(session: Session = Depends(get_db_session)):
    """
    List all failover configurations.
    Returns all service failover configurations.
    """
    try:
        configs = list(DisasterRecovery._failover_configs.values())
        return {
            "success": True,
            "configs": configs,
            "count": len(configs)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing failover configs: {str(e)}")


@router.post("/health-check/{config_id}")
def perform_health_check(
    config_id: str,
    request: PerformHealthCheckRequest,
    session: Session = Depends(get_db_session)
):
    """
    Perform health check.
    Records health check result and triggers automatic failover if threshold exceeded.
    """
    try:
        result = DisasterRecovery.perform_health_check(
            session=session,
            config_id=config_id,
            is_healthy=request.is_healthy,
            response_time_ms=request.response_time_ms,
            error_message=request.error_message
        )
        return {
            "success": True,
            "health_check": result,
            "message": f"Health check recorded: {'healthy' if request.is_healthy else 'unhealthy'}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error performing health check: {str(e)}")


@router.post("/failover/{config_id}/trigger")
def trigger_manual_failover(
    config_id: str,
    request: TriggerFailoverRequest,
    session: Session = Depends(get_db_session)
):
    """
    Trigger manual failover.
    Manually initiates failover to secondary endpoint.
    """
    try:
        result = DisasterRecovery.trigger_manual_failover(
            session=session,
            config_id=config_id,
            reason=request.reason
        )
        return {
            "success": True,
            "failover": result,
            "message": "Failover initiated successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error triggering failover: {str(e)}")


@router.post("/failover/{config_id}/rollback")
def rollback_failover(
    config_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Rollback failover.
    Returns service to primary endpoint after failover.
    """
    try:
        result = DisasterRecovery.rollback_failover(
            session=session,
            config_id=config_id
        )
        return {
            "success": True,
            "rollback": result,
            "message": "Rollback completed successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error rolling back failover: {str(e)}")


@router.get("/failover-history")
def get_failover_history(
    plan_id: Optional[str] = None,
    limit: int = 100,
    session: Session = Depends(get_db_session)
):
    """
    Get failover history.
    Returns historical failover events.
    """
    try:
        events = DisasterRecovery.get_failover_history(
            session=session,
            plan_id=plan_id,
            limit=limit
        )
        return {
            "success": True,
            "events": events,
            "count": len(events)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting failover history: {str(e)}")


@router.post("/drills")
def create_dr_drill(
    request: CreateDRDrillRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a DR drill.
    Schedules a disaster recovery drill to test failover procedures.
    """
    try:
        result = DisasterRecovery.create_dr_drill(
            session=session,
            drill_id=request.drill_id,
            plan_id=request.plan_id,
            name=request.name,
            scheduled_at=request.scheduled_at,
            duration_minutes=request.duration_minutes,
            test_failover=request.test_failover
        )
        return {
            "success": True,
            "drill": result,
            "message": f"DR drill scheduled: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating DR drill: {str(e)}")


@router.post("/drills/{drill_id}/execute")
def execute_drill(
    drill_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Execute a DR drill.
    Runs the disaster recovery drill and validates RPO/RTO objectives.
    """
    try:
        result = DisasterRecovery.execute_drill(
            session=session,
            drill_id=drill_id
        )
        return {
            "success": True,
            "execution": result,
            "message": "DR drill executed successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing drill: {str(e)}")


@router.get("/drills")
def list_drills(session: Session = Depends(get_db_session)):
    """
    List all DR drills.
    Returns all disaster recovery drills.
    """
    try:
        drills = list(DisasterRecovery._drills.values())
        return {
            "success": True,
            "drills": drills,
            "count": len(drills)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing drills: {str(e)}")


@router.post("/replicas")
def create_replica(
    request: CreateReplicaRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a replica.
    Configures data replication between regions.
    """
    try:
        result = DisasterRecovery.create_replica(
            session=session,
            replica_id=request.replica_id,
            plan_id=request.plan_id,
            source_region=request.source_region,
            target_region=request.target_region,
            data_type=request.data_type,
            replication_lag_seconds=request.replication_lag_seconds
        )
        return {
            "success": True,
            "replica": result,
            "message": f"Replica created: {request.source_region} → {request.target_region}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating replica: {str(e)}")


@router.put("/replicas/{replica_id}/status")
def update_replica_status(
    replica_id: str,
    request: UpdateReplicaStatusRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update replica status.
    Updates replication status and lag information.
    """
    try:
        result = DisasterRecovery.update_replica_status(
            session=session,
            replica_id=replica_id,
            status=request.status,
            replication_lag_seconds=request.replication_lag_seconds,
            bytes_replicated=request.bytes_replicated
        )
        return {
            "success": True,
            "update": result,
            "message": f"Replica status updated: {request.status}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating replica status: {str(e)}")


@router.get("/replicas")
def list_replicas(session: Session = Depends(get_db_session)):
    """
    List all replicas.
    Returns all data replication configurations.
    """
    try:
        replicas = list(DisasterRecovery._replicas.values())
        return {
            "success": True,
            "replicas": replicas,
            "count": len(replicas)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing replicas: {str(e)}")


@router.get("/plans/{plan_id}/status")
def get_dr_status(
    plan_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get DR status.
    Returns comprehensive disaster recovery status for a plan.
    """
    try:
        status = DisasterRecovery.get_dr_status(
            session=session,
            plan_id=plan_id
        )
        return {
            "success": True,
            "status": status,
            "message": "DR status retrieved"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting DR status: {str(e)}")


@router.get("/statistics")
def get_statistics(session: Session = Depends(get_db_session)):
    """
    Get statistics.
    Returns comprehensive disaster recovery and failover statistics.
    """
    try:
        stats = DisasterRecovery.get_statistics(session)
        return {
            "success": True,
            "statistics": stats,
            "message": "Statistics retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")
