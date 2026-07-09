"""
Cost Tracking and Budget Management API

REST API endpoints for tracking costs and managing budgets.
"""

from typing import Optional, Dict
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.cost_tracking import (
    CostTracking,
    CostCategory,
    BudgetPeriod,
    AlertLevel
)


router = APIRouter()


# Request/Response Models
class RecordCostRequest(BaseModel):
    category: str = Field(..., description="Cost category")
    amount: float = Field(..., description="Cost amount")
    agent_id: Optional[int] = Field(None, description="Agent ID")
    workflow_id: Optional[str] = Field(None, description="Workflow ID")
    task_id: Optional[str] = Field(None, description="Task ID")
    details: Optional[dict] = Field(None, description="Additional details")
    metadata: Optional[dict] = Field(None, description="Metadata")


class RecordLLMCostRequest(BaseModel):
    model: str = Field(..., description="LLM model name")
    input_tokens: int = Field(..., description="Input token count")
    output_tokens: int = Field(..., description="Output token count")
    agent_id: Optional[int] = Field(None, description="Agent ID")
    workflow_id: Optional[str] = Field(None, description="Workflow ID")
    task_id: Optional[str] = Field(None, description="Task ID")
    metadata: Optional[dict] = Field(None, description="Metadata")


class RecordComputeCostRequest(BaseModel):
    duration_seconds: float = Field(..., description="Execution duration in seconds")
    agent_id: Optional[int] = Field(None, description="Agent ID")
    workflow_id: Optional[str] = Field(None, description="Workflow ID")
    task_id: Optional[str] = Field(None, description="Task ID")
    cost_per_second: Optional[float] = Field(None, description="Custom cost per second")
    metadata: Optional[dict] = Field(None, description="Metadata")


class CreateBudgetRequest(BaseModel):
    name: str = Field(..., description="Budget name")
    amount: float = Field(..., description="Budget amount")
    period: str = Field(..., description="Budget period")
    agent_id: Optional[int] = Field(None, description="Agent ID filter")
    workflow_id: Optional[str] = Field(None, description="Workflow ID filter")
    category: Optional[str] = Field(None, description="Category filter")
    alert_thresholds: Optional[Dict[str, float]] = Field(None, description="Alert thresholds")
    auto_disable_on_exceed: bool = Field(False, description="Auto-disable when exceeded")
    metadata: Optional[dict] = Field(None, description="Metadata")


class UpdatePricingRequest(BaseModel):
    pricing_updates: dict = Field(..., description="Pricing configuration updates")


@router.post("/costs")
def record_cost(
    request: RecordCostRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record cost entry.

    Tracks a cost and updates budgets and alerts.
    """
    try:
        cost_entry = CostTracking.record_cost(
            session=session,
            category=request.category,
            amount=request.amount,
            agent_id=request.agent_id,
            workflow_id=request.workflow_id,
            task_id=request.task_id,
            details=request.details,
            metadata=request.metadata
        )

        return {
            "success": True,
            "cost_entry": cost_entry,
            "message": f"Cost recorded: ${cost_entry['amount']:.4f}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/costs/llm")
def record_llm_cost(
    request: RecordLLMCostRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record LLM API cost.

    Automatically calculates cost based on model pricing and token usage.
    """
    try:
        cost_entry = CostTracking.record_llm_cost(
            session=session,
            model=request.model,
            input_tokens=request.input_tokens,
            output_tokens=request.output_tokens,
            agent_id=request.agent_id,
            workflow_id=request.workflow_id,
            task_id=request.task_id,
            metadata=request.metadata
        )

        return {
            "success": True,
            "cost_entry": cost_entry,
            "message": f"LLM cost recorded: ${cost_entry['amount']:.4f}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/costs/compute")
def record_compute_cost(
    request: RecordComputeCostRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record compute cost.

    Tracks cost based on execution time.
    """
    try:
        cost_entry = CostTracking.record_compute_cost(
            session=session,
            duration_seconds=request.duration_seconds,
            agent_id=request.agent_id,
            workflow_id=request.workflow_id,
            task_id=request.task_id,
            cost_per_second=request.cost_per_second,
            metadata=request.metadata
        )

        return {
            "success": True,
            "cost_entry": cost_entry,
            "message": f"Compute cost recorded: ${cost_entry['amount']:.4f}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/budgets")
def create_budget(
    request: CreateBudgetRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create budget.

    Sets spending limits with optional alerts and auto-disable.
    """
    try:
        budget = CostTracking.create_budget(
            session=session,
            name=request.name,
            amount=request.amount,
            period=request.period,
            agent_id=request.agent_id,
            workflow_id=request.workflow_id,
            category=request.category,
            alert_thresholds=request.alert_thresholds,
            auto_disable_on_exceed=request.auto_disable_on_exceed,
            metadata=request.metadata
        )

        return {
            "success": True,
            "budget": budget,
            "message": f"Budget '{request.name}' created"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/budgets/{budget_id}")
def get_budget_status(
    budget_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get budget status.

    Returns budget details with current spending and usage percentage.
    """
    try:
        budget_status = CostTracking.get_budget_status(
            session=session,
            budget_id=budget_id
        )

        return {
            "success": True,
            "budget": budget_status
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/budgets")
def list_budgets(
    status: Optional[str] = None,
    agent_id: Optional[int] = None,
    workflow_id: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    List budgets.

    Returns budgets with optional filtering by status, agent, or workflow.
    """
    try:
        result = CostTracking.list_budgets(
            session=session,
            status=status,
            agent_id=agent_id,
            workflow_id=workflow_id
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
def get_cost_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    agent_id: Optional[int] = None,
    workflow_id: Optional[str] = None,
    category: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get cost summary.

    Returns aggregate costs with breakdowns by category, agent, and workflow.
    """
    try:
        summary = CostTracking.get_cost_summary(
            session=session,
            start_date=start_date,
            end_date=end_date,
            agent_id=agent_id,
            workflow_id=workflow_id,
            category=category
        )

        return {
            "success": True,
            **summary
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/alerts")
def get_alerts(
    level: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    Get budget alerts.

    Returns alerts triggered when budgets reach warning or critical thresholds.
    """
    try:
        result = CostTracking.get_alerts(
            session=session,
            level=level,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/forecast")
def get_cost_forecast(
    days_ahead: int = 30,
    agent_id: Optional[int] = None,
    workflow_id: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get cost forecast.

    Projects future costs based on historical spending patterns.
    """
    try:
        forecast = CostTracking.get_cost_forecast(
            session=session,
            days_ahead=days_ahead,
            agent_id=agent_id,
            workflow_id=workflow_id
        )

        return {
            "success": True,
            "forecast": forecast
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pricing")
def update_pricing(
    request: UpdatePricingRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update pricing configuration.

    Updates pricing rates for LLM models, compute, storage, etc.
    """
    try:
        result = CostTracking.update_pricing(
            session=session,
            pricing_updates=request.pricing_updates
        )

        return {
            "success": True,
            **result,
            "message": "Pricing updated"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pricing")
def get_pricing(
    session: Session = Depends(get_db_session)
):
    """
    Get pricing configuration.

    Returns current pricing rates for all cost categories.
    """
    try:
        pricing = CostTracking.get_pricing(session=session)

        return {
            "success": True,
            "pricing": pricing
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get cost tracking statistics.

    Returns aggregate metrics including total costs, category distribution,
    top spending agents, and budget information.
    """
    try:
        stats = CostTracking.get_cost_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
def list_cost_categories():
    """
    List cost categories.

    Returns all available cost categories.
    """
    return {
        "success": True,
        "categories": [
            {"category": CostCategory.LLM_API, "description": "LLM API token costs"},
            {"category": CostCategory.COMPUTE, "description": "Compute execution costs"},
            {"category": CostCategory.STORAGE, "description": "Data storage costs"},
            {"category": CostCategory.EXTERNAL_API, "description": "External API call costs"},
            {"category": CostCategory.DATA_TRANSFER, "description": "Data transfer costs"},
            {"category": CostCategory.OTHER, "description": "Other miscellaneous costs"}
        ]
    }


@router.get("/budget-periods")
def list_budget_periods():
    """
    List budget periods.

    Returns all available budget time periods.
    """
    return {
        "success": True,
        "periods": [
            {"period": BudgetPeriod.HOURLY, "description": "Hourly budget"},
            {"period": BudgetPeriod.DAILY, "description": "Daily budget"},
            {"period": BudgetPeriod.WEEKLY, "description": "Weekly budget"},
            {"period": BudgetPeriod.MONTHLY, "description": "Monthly budget"},
            {"period": BudgetPeriod.YEARLY, "description": "Yearly budget"}
        ]
    }


@router.get("/alert-levels")
def list_alert_levels():
    """
    List alert levels.

    Returns all alert severity levels.
    """
    return {
        "success": True,
        "levels": [
            {"level": AlertLevel.INFO, "description": "Informational alert"},
            {"level": AlertLevel.WARNING, "description": "Warning - approaching budget limit"},
            {"level": AlertLevel.CRITICAL, "description": "Critical - budget nearly or fully exceeded"}
        ]
    }
