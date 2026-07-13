"""
Feature Flags and A/B Testing API

REST API endpoints for feature flag management, A/B testing experiments,
and gradual rollout control.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from src.database import get_db_session
from src.services.feature_flags import (
    FeatureFlags,
    FlagStatus,
    RolloutStrategy,
    ExperimentStatus,
    SegmentOperator
)


router = APIRouter()


# Request/Response Models
class CreateFlagRequest(BaseModel):
    """Request model for creating a feature flag"""
    flag_id: str = Field(..., description="Unique flag identifier")
    name: str = Field(..., description="Flag name")
    description: Optional[str] = Field(default=None, description="Flag description")
    default_value: bool = Field(default=False, description="Default flag value")
    rollout_strategy: RolloutStrategy = Field(default=RolloutStrategy.ALL_USERS, description="Rollout strategy")
    rollout_percentage: int = Field(default=100, description="Rollout percentage", ge=0, le=100)
    target_segments: Optional[List[str]] = Field(default=None, description="Target user segments")
    metadata: Optional[Dict] = Field(default=None, description="Additional metadata")


class EvaluateFlagRequest(BaseModel):
    """Request model for evaluating a flag"""
    user_id: str = Field(..., description="User identifier")
    context: Optional[Dict] = Field(default=None, description="Evaluation context")


class UpdateFlagRequest(BaseModel):
    """Request model for updating a flag"""
    current_value: Optional[bool] = Field(default=None, description="New flag value")
    rollout_percentage: Optional[int] = Field(default=None, description="New rollout percentage", ge=0, le=100)
    rollout_strategy: Optional[RolloutStrategy] = Field(default=None, description="New rollout strategy")
    status: Optional[FlagStatus] = Field(default=None, description="New status")
    target_segments: Optional[List[str]] = Field(default=None, description="New target segments")


class VariantDefinition(BaseModel):
    """Variant definition for experiments"""
    variant_id: str = Field(..., description="Variant identifier")
    name: str = Field(..., description="Variant name")
    traffic_weight: int = Field(..., description="Traffic weight (0-100)", ge=0, le=100)
    config: Optional[Dict] = Field(default=None, description="Variant configuration")


class CreateExperimentRequest(BaseModel):
    """Request model for creating an experiment"""
    experiment_id: str = Field(..., description="Unique experiment identifier")
    name: str = Field(..., description="Experiment name")
    description: Optional[str] = Field(default=None, description="Experiment description")
    flag_id: Optional[str] = Field(default=None, description="Associated flag ID")
    variants: List[VariantDefinition] = Field(..., description="Experiment variants", min_items=2)
    traffic_allocation: int = Field(default=100, description="Percentage of traffic to include", ge=0, le=100)
    target_segments: Optional[List[str]] = Field(default=None, description="Target segments")
    metrics: Optional[List[str]] = Field(default=None, description="Metrics to track")
    start_date: Optional[str] = Field(default=None, description="Start date (ISO)")
    end_date: Optional[str] = Field(default=None, description="End date (ISO)")


class AssignVariantRequest(BaseModel):
    """Request model for variant assignment"""
    user_id: str = Field(..., description="User identifier")
    context: Optional[Dict] = Field(default=None, description="Assignment context")


class TrackEventRequest(BaseModel):
    """Request model for tracking events"""
    user_id: str = Field(..., description="User identifier")
    event_name: str = Field(..., description="Event name")
    value: Optional[float] = Field(default=None, description="Event value")
    metadata: Optional[Dict] = Field(default=None, description="Event metadata")


class SegmentRuleDefinition(BaseModel):
    """Segment rule definition"""
    attribute: str = Field(..., description="User attribute to check")
    operator: SegmentOperator = Field(..., description="Comparison operator")
    value: str = Field(..., description="Target value")


class CreateSegmentRequest(BaseModel):
    """Request model for creating a segment"""
    segment_id: str = Field(..., description="Unique segment identifier")
    name: str = Field(..., description="Segment name")
    description: Optional[str] = Field(default=None, description="Segment description")
    rules: List[SegmentRuleDefinition] = Field(..., description="Segment rules")


class EvaluateSegmentRequest(BaseModel):
    """Request model for evaluating a segment"""
    user_attributes: Dict = Field(..., description="User attributes")


# API Endpoints
@router.post("/flags")
def create_flag(
    request: CreateFlagRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a feature flag.
    Defines a feature flag with rollout strategy and targeting rules.
    """
    try:
        result = FeatureFlags.create_flag(
            session=session,
            flag_id=request.flag_id,
            name=request.name,
            description=request.description,
            default_value=request.default_value,
            rollout_strategy=request.rollout_strategy,
            rollout_percentage=request.rollout_percentage,
            target_segments=request.target_segments,
            metadata=request.metadata
        )
        return {
            "success": True,
            "flag": result,
            "message": f"Feature flag created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating flag: {str(e)}")


@router.get("/flags")
def list_flags(session: Session = Depends(get_db_session)):
    """
    List all feature flags.
    Returns all defined feature flags with their current status.
    """
    try:
        flags = list(FeatureFlags._flags.values())
        return {
            "success": True,
            "flags": flags,
            "count": len(flags)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing flags: {str(e)}")


@router.get("/flags/{flag_id}")
def get_flag(
    flag_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get flag details.
    Returns detailed information about a specific feature flag.
    """
    try:
        flag = FeatureFlags._flags.get(flag_id)
        if not flag:
            raise HTTPException(status_code=404, detail=f"Flag not found: {flag_id}")

        return {
            "success": True,
            "flag": flag
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting flag: {str(e)}")


@router.put("/flags/{flag_id}")
def update_flag(
    flag_id: str,
    request: UpdateFlagRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update a feature flag.
    Modifies flag configuration including rollout percentage and strategy.
    """
    try:
        result = FeatureFlags.update_flag(
            session=session,
            flag_id=flag_id,
            current_value=request.current_value,
            rollout_percentage=request.rollout_percentage,
            rollout_strategy=request.rollout_strategy,
            status=request.status,
            target_segments=request.target_segments
        )
        return {
            "success": True,
            "flag": result,
            "message": "Flag updated successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating flag: {str(e)}")


@router.post("/flags/{flag_id}/evaluate")
def evaluate_flag(
    flag_id: str,
    request: EvaluateFlagRequest,
    session: Session = Depends(get_db_session)
):
    """
    Evaluate a feature flag.
    Determines if flag is enabled for a specific user based on rollout rules.
    """
    try:
        result = FeatureFlags.evaluate_flag(
            session=session,
            flag_id=flag_id,
            user_id=request.user_id,
            context=request.context
        )
        return {
            "success": True,
            "evaluation": result,
            "message": "Enabled" if result["is_enabled"] else "Disabled"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error evaluating flag: {str(e)}")


@router.get("/flags/{flag_id}/analytics")
def get_flag_analytics(
    flag_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get flag analytics.
    Returns evaluation statistics and performance metrics for a flag.
    """
    try:
        analytics = FeatureFlags.get_flag_analytics(
            session=session,
            flag_id=flag_id
        )
        return {
            "success": True,
            "analytics": analytics
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting analytics: {str(e)}")


@router.post("/experiments")
def create_experiment(
    request: CreateExperimentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create an A/B test experiment.
    Defines an experiment with multiple variants for testing.
    """
    try:
        # Convert Pydantic models to dicts
        variants = [v.dict() for v in request.variants]

        result = FeatureFlags.create_experiment(
            session=session,
            experiment_id=request.experiment_id,
            name=request.name,
            description=request.description,
            flag_id=request.flag_id,
            variants=variants,
            traffic_allocation=request.traffic_allocation,
            target_segments=request.target_segments,
            metrics=request.metrics,
            start_date=request.start_date,
            end_date=request.end_date
        )
        return {
            "success": True,
            "experiment": result,
            "message": f"Experiment created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating experiment: {str(e)}")


@router.get("/experiments")
def list_experiments(session: Session = Depends(get_db_session)):
    """
    List all experiments.
    Returns all A/B test experiments with their status.
    """
    try:
        experiments = list(FeatureFlags._experiments.values())
        return {
            "success": True,
            "experiments": experiments,
            "count": len(experiments)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing experiments: {str(e)}")


@router.get("/experiments/{experiment_id}")
def get_experiment(
    experiment_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get experiment details.
    Returns detailed information about an experiment.
    """
    try:
        experiment = FeatureFlags._experiments.get(experiment_id)
        if not experiment:
            raise HTTPException(status_code=404, detail=f"Experiment not found: {experiment_id}")

        return {
            "success": True,
            "experiment": experiment
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting experiment: {str(e)}")


@router.post("/experiments/{experiment_id}/start")
def start_experiment(
    experiment_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Start an experiment.
    Activates an experiment to begin collecting data.
    """
    try:
        result = FeatureFlags.start_experiment(
            session=session,
            experiment_id=experiment_id
        )
        return {
            "success": True,
            "experiment": result,
            "message": "Experiment started"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error starting experiment: {str(e)}")


@router.post("/experiments/{experiment_id}/stop")
def stop_experiment(
    experiment_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Stop an experiment.
    Completes an experiment and stops collecting new data.
    """
    try:
        result = FeatureFlags.stop_experiment(
            session=session,
            experiment_id=experiment_id
        )
        return {
            "success": True,
            "experiment": result,
            "message": "Experiment stopped"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error stopping experiment: {str(e)}")


@router.post("/experiments/{experiment_id}/assign")
def assign_variant(
    experiment_id: str,
    request: AssignVariantRequest,
    session: Session = Depends(get_db_session)
):
    """
    Assign user to variant.
    Assigns a user to an experiment variant for consistent experience.
    """
    try:
        result = FeatureFlags.assign_variant(
            session=session,
            experiment_id=experiment_id,
            user_id=request.user_id,
            context=request.context
        )
        return {
            "success": True,
            "assignment": result,
            "message": f"Assigned to variant: {result['variant']}" if result['variant'] else "Not assigned"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error assigning variant: {str(e)}")


@router.post("/experiments/{experiment_id}/events")
def track_event(
    experiment_id: str,
    request: TrackEventRequest,
    session: Session = Depends(get_db_session)
):
    """
    Track experiment event.
    Records an event for experiment metric tracking.
    """
    try:
        result = FeatureFlags.track_event(
            session=session,
            experiment_id=experiment_id,
            user_id=request.user_id,
            event_name=request.event_name,
            value=request.value,
            metadata=request.metadata
        )
        return {
            "success": True,
            "event": result,
            "message": "Event tracked"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error tracking event: {str(e)}")


@router.get("/experiments/{experiment_id}/results")
def get_experiment_results(
    experiment_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get experiment results.
    Returns analysis and metrics for all experiment variants.
    """
    try:
        results = FeatureFlags.get_experiment_results(
            session=session,
            experiment_id=experiment_id
        )
        return {
            "success": True,
            "results": results,
            "message": "Results retrieved successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting results: {str(e)}")


@router.post("/segments")
def create_segment(
    request: CreateSegmentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a user segment.
    Defines a user segment with targeting rules for flag rollouts.
    """
    try:
        # Convert Pydantic models to dicts
        rules = [r.dict() for r in request.rules]

        result = FeatureFlags.create_segment(
            session=session,
            segment_id=request.segment_id,
            name=request.name,
            description=request.description,
            rules=rules
        )
        return {
            "success": True,
            "segment": result,
            "message": f"Segment created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating segment: {str(e)}")


@router.get("/segments")
def list_segments(session: Session = Depends(get_db_session)):
    """
    List all segments.
    Returns all defined user segments.
    """
    try:
        segments = list(FeatureFlags._segments.values())
        return {
            "success": True,
            "segments": segments,
            "count": len(segments)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing segments: {str(e)}")


@router.post("/segments/{segment_id}/evaluate")
def evaluate_segment(
    segment_id: str,
    request: EvaluateSegmentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Evaluate a segment.
    Checks if user attributes match segment rules.
    """
    try:
        result = FeatureFlags.evaluate_segment(
            session=session,
            segment_id=segment_id,
            user_attributes=request.user_attributes
        )
        return {
            "success": True,
            "evaluation": result,
            "message": "Match" if result["matches"] else "No match"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error evaluating segment: {str(e)}")


@router.get("/statistics")
def get_statistics(session: Session = Depends(get_db_session)):
    """
    Get statistics.
    Returns comprehensive feature flag and A/B testing statistics.
    """
    try:
        stats = FeatureFlags.get_statistics(session)
        return {
            "success": True,
            "statistics": stats,
            "message": "Statistics retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")
