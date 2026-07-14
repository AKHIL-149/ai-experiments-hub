"""
Capacity Planning and Auto-Scaling API

REST API endpoints for capacity planning, forecasting, and auto-scaling.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.capacity_planning import (
    CapacityPlanning,
    ResourceType,
    ScalingPolicy,
    ForecastPeriod
)


router = APIRouter()


# Request/Response Models
class CreateCapacityPlanRequest(BaseModel):
    """Request model for creating a capacity plan"""
    plan_id: str = Field(..., description="Unique plan identifier")
    name: str = Field(..., description="Plan name")
    resource_type: ResourceType = Field(..., description="Type of resource")
    current_capacity: float = Field(..., description="Current capacity", ge=0)
    target_utilization: float = Field(default=70.0, description="Target utilization %", ge=0, le=100)
    buffer_percentage: float = Field(default=20.0, description="Buffer %", ge=0, le=100)
    forecast_period: ForecastPeriod = Field(default=ForecastPeriod.MONTHLY, description="Forecast period")


class RecordResourceUsageRequest(BaseModel):
    """Request model for recording resource usage"""
    resource_type: ResourceType = Field(..., description="Type of resource")
    used: float = Field(..., description="Used amount", ge=0)
    total: float = Field(..., description="Total capacity", ge=0)
    timestamp: Optional[str] = Field(default=None, description="ISO timestamp")
    metadata: Optional[dict] = Field(default=None, description="Additional metadata")


class CreateScalingPolicyRequest(BaseModel):
    """Request model for creating a scaling policy"""
    policy_id: str = Field(..., description="Unique policy identifier")
    name: str = Field(..., description="Policy name")
    resource_type: ResourceType = Field(..., description="Type of resource")
    policy_type: ScalingPolicy = Field(..., description="Policy type")
    scale_up_threshold: float = Field(..., description="Scale up threshold %", ge=0, le=100)
    scale_down_threshold: float = Field(..., description="Scale down threshold %", ge=0, le=100)
    cooldown_minutes: int = Field(default=5, description="Cooldown period", ge=1)
    min_capacity: float = Field(default=1, description="Minimum capacity", ge=0)
    max_capacity: float = Field(default=100, description="Maximum capacity", ge=1)
    enabled: bool = Field(default=True, description="Whether policy is enabled")


class EvaluateScalingRequest(BaseModel):
    """Request model for evaluating scaling"""
    current_utilization: float = Field(..., description="Current utilization %", ge=0, le=100)
    current_capacity: float = Field(..., description="Current capacity", ge=0)


class EstimateCostsRequest(BaseModel):
    """Request model for cost estimation"""
    resource_type: ResourceType = Field(..., description="Type of resource")
    capacity: float = Field(..., description="Capacity amount", ge=0)
    unit_cost: float = Field(..., description="Cost per unit per hour", ge=0)
    duration_hours: int = Field(default=720, description="Duration in hours", ge=1)


class ApplyRecommendationRequest(BaseModel):
    """Request model for applying a recommendation"""
    notes: Optional[str] = Field(default=None, description="Implementation notes")


# API Endpoints
@router.post("/plans")
def create_capacity_plan(
    request: CreateCapacityPlanRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a capacity plan.
    Defines capacity planning parameters for a resource type.
    """
    try:
        result = CapacityPlanning.create_capacity_plan(
            session=session,
            plan_id=request.plan_id,
            name=request.name,
            resource_type=request.resource_type,
            current_capacity=request.current_capacity,
            target_utilization=request.target_utilization,
            buffer_percentage=request.buffer_percentage,
            forecast_period=request.forecast_period
        )
        return {
            "success": True,
            "plan": result,
            "message": f"Capacity plan created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating capacity plan: {str(e)}")


@router.get("/plans")
def list_capacity_plans(session: Session = Depends(get_db_session)):
    """
    List all capacity plans.
    Returns all capacity planning configurations.
    """
    try:
        plans = list(CapacityPlanning._capacity_plans.values())
        return {
            "success": True,
            "plans": plans,
            "count": len(plans)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing capacity plans: {str(e)}")


@router.post("/usage")
def record_resource_usage(
    request: RecordResourceUsageRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record resource usage.
    Stores resource utilization data for capacity planning and forecasting.
    """
    try:
        result = CapacityPlanning.record_resource_usage(
            session=session,
            resource_type=request.resource_type,
            used=request.used,
            total=request.total,
            timestamp=request.timestamp,
            metadata=request.metadata
        )
        return {
            "success": True,
            "usage": result,
            "message": f"Resource usage recorded: {result['utilization_percent']:.1f}%"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error recording usage: {str(e)}")


@router.post("/plans/{plan_id}/forecast")
def generate_forecast(
    plan_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Generate capacity forecast.
    Analyzes historical usage and predicts future capacity needs.
    Generates recommendations if scaling is required.
    """
    try:
        result = CapacityPlanning.generate_forecast(
            session=session,
            plan_id=plan_id
        )
        return {
            "success": True,
            "forecast": result,
            "message": "Forecast generated successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating forecast: {str(e)}")


@router.get("/forecasts")
def list_forecasts(session: Session = Depends(get_db_session)):
    """
    List all forecasts.
    Returns all capacity forecasts.
    """
    try:
        forecasts = list(CapacityPlanning._forecasts.values())
        return {
            "success": True,
            "forecasts": forecasts,
            "count": len(forecasts)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing forecasts: {str(e)}")


@router.post("/scaling-policies")
def create_scaling_policy(
    request: CreateScalingPolicyRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a scaling policy.
    Defines auto-scaling rules based on utilization thresholds.
    """
    try:
        result = CapacityPlanning.create_scaling_policy(
            session=session,
            policy_id=request.policy_id,
            name=request.name,
            resource_type=request.resource_type,
            policy_type=request.policy_type,
            scale_up_threshold=request.scale_up_threshold,
            scale_down_threshold=request.scale_down_threshold,
            cooldown_minutes=request.cooldown_minutes,
            min_capacity=request.min_capacity,
            max_capacity=request.max_capacity,
            enabled=request.enabled
        )
        return {
            "success": True,
            "policy": result,
            "message": f"Scaling policy created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating scaling policy: {str(e)}")


@router.get("/scaling-policies")
def list_scaling_policies(session: Session = Depends(get_db_session)):
    """
    List all scaling policies.
    Returns all auto-scaling configurations.
    """
    try:
        policies = list(CapacityPlanning._scaling_policies.values())
        return {
            "success": True,
            "policies": policies,
            "count": len(policies)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing scaling policies: {str(e)}")


@router.post("/scaling-policies/{policy_id}/evaluate")
def evaluate_scaling(
    policy_id: str,
    request: EvaluateScalingRequest,
    session: Session = Depends(get_db_session)
):
    """
    Evaluate scaling decision.
    Checks current utilization against policy thresholds.
    Executes scaling if needed and within cooldown period.
    """
    try:
        result = CapacityPlanning.evaluate_scaling(
            session=session,
            policy_id=policy_id,
            current_utilization=request.current_utilization,
            current_capacity=request.current_capacity
        )
        return {
            "success": True,
            "evaluation": result,
            "message": f"Scaling decision: {result['decision']}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error evaluating scaling: {str(e)}")


@router.get("/scaling-history")
def get_scaling_history(
    resource_type: Optional[ResourceType] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = 100,
    session: Session = Depends(get_db_session)
):
    """
    Get scaling history.
    Returns historical scaling events with optional filtering.
    """
    try:
        events = CapacityPlanning.get_scaling_history(
            session=session,
            resource_type=resource_type,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        return {
            "success": True,
            "events": events,
            "count": len(events)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting scaling history: {str(e)}")


@router.get("/recommendations")
def get_recommendations(
    applied: Optional[bool] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get capacity recommendations.
    Returns recommendations for capacity adjustments.
    """
    try:
        recommendations = CapacityPlanning.get_recommendations(
            session=session,
            applied=applied
        )
        return {
            "success": True,
            "recommendations": recommendations,
            "count": len(recommendations)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting recommendations: {str(e)}")


@router.post("/recommendations/{recommendation_id}/apply")
def apply_recommendation(
    recommendation_id: str,
    request: ApplyRecommendationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Apply a recommendation.
    Implements the recommended capacity change.
    """
    try:
        result = CapacityPlanning.apply_recommendation(
            session=session,
            recommendation_id=recommendation_id,
            notes=request.notes
        )
        return {
            "success": True,
            "application": result,
            "message": "Recommendation applied"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying recommendation: {str(e)}")


@router.post("/costs/estimate")
def estimate_costs(
    request: EstimateCostsRequest,
    session: Session = Depends(get_db_session)
):
    """
    Estimate costs.
    Calculates cost projections for a given capacity configuration.
    """
    try:
        result = CapacityPlanning.estimate_costs(
            session=session,
            resource_type=request.resource_type,
            capacity=request.capacity,
            unit_cost=request.unit_cost,
            duration_hours=request.duration_hours
        )
        return {
            "success": True,
            "estimate": result,
            "message": f"Estimated monthly cost: ${result['monthly_cost']:.2f}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error estimating costs: {str(e)}")


@router.get("/statistics")
def get_statistics(session: Session = Depends(get_db_session)):
    """
    Get statistics.
    Returns comprehensive capacity planning and auto-scaling statistics.
    """
    try:
        stats = CapacityPlanning.get_statistics(session)
        return {
            "success": True,
            "statistics": stats,
            "message": "Statistics retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")
