"""
Cost Tracking and Budget Management Service

Tracks and manages costs for agent operations including LLM API calls,
compute resources, storage, and external services.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict


class CostCategory:
    """Cost categories"""
    LLM_API = "llm_api"
    COMPUTE = "compute"
    STORAGE = "storage"
    EXTERNAL_API = "external_api"
    DATA_TRANSFER = "data_transfer"
    OTHER = "other"


class BudgetPeriod:
    """Budget time periods"""
    HOURLY = "hourly"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class AlertLevel:
    """Budget alert levels"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class CostTracking:
    """
    Cost Tracking and Budget Management Service

    Provides comprehensive cost tracking and budget management for
    agent operations with alerts and forecasting.
    """

    # In-memory storage
    _cost_entries = {}
    _entry_counter = 0
    _budgets = {}
    _budget_counter = 0
    _alerts = []
    _agent_costs = defaultdict(float)
    _workflow_costs = defaultdict(float)
    _category_costs = defaultdict(float)

    # Pricing configuration (defaults, can be updated)
    _pricing = {
        "llm_tokens_per_1k": {
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-3.5-turbo": {"input": 0.001, "output": 0.002},
            "claude-3-opus": {"input": 0.015, "output": 0.075},
            "claude-3-sonnet": {"input": 0.003, "output": 0.015},
            "claude-3-haiku": {"input": 0.00025, "output": 0.00125}
        },
        "compute_per_second": 0.0001,
        "storage_per_gb_month": 0.10,
        "data_transfer_per_gb": 0.09
    }

    @staticmethod
    def _generate_entry_id() -> str:
        """Generate unique cost entry ID"""
        CostTracking._entry_counter += 1
        return f"cost_{CostTracking._entry_counter}"

    @staticmethod
    def _generate_budget_id() -> str:
        """Generate unique budget ID"""
        CostTracking._budget_counter += 1
        return f"budget_{CostTracking._budget_counter}"

    @staticmethod
    def record_cost(
        session,
        category: str,
        amount: float,
        agent_id: Optional[int] = None,
        workflow_id: Optional[str] = None,
        task_id: Optional[str] = None,
        details: Optional[dict] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Record a cost entry.

        Tracks costs and updates budgets and alerts.
        """
        entry_id = CostTracking._generate_entry_id()

        cost_entry = {
            "id": entry_id,
            "category": category,
            "amount": amount,
            "agent_id": agent_id,
            "workflow_id": workflow_id,
            "task_id": task_id,
            "details": details or {},
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        CostTracking._cost_entries[entry_id] = cost_entry

        # Update aggregates
        CostTracking._category_costs[category] += amount
        if agent_id:
            CostTracking._agent_costs[agent_id] += amount
        if workflow_id:
            CostTracking._workflow_costs[workflow_id] += amount

        # Check budgets
        CostTracking._check_budgets(session, agent_id, workflow_id, category)

        return cost_entry

    @staticmethod
    def record_llm_cost(
        session,
        model: str,
        input_tokens: int,
        output_tokens: int,
        agent_id: Optional[int] = None,
        workflow_id: Optional[str] = None,
        task_id: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Record LLM API cost based on token usage.

        Automatically calculates cost based on model pricing.
        """
        pricing = CostTracking._pricing["llm_tokens_per_1k"].get(model, {"input": 0.01, "output": 0.02})

        input_cost = (input_tokens / 1000) * pricing["input"]
        output_cost = (output_tokens / 1000) * pricing["output"]
        total_cost = input_cost + output_cost

        return CostTracking.record_cost(
            session=session,
            category=CostCategory.LLM_API,
            amount=total_cost,
            agent_id=agent_id,
            workflow_id=workflow_id,
            task_id=task_id,
            details={
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "input_cost": input_cost,
                "output_cost": output_cost
            },
            metadata=metadata
        )

    @staticmethod
    def record_compute_cost(
        session,
        duration_seconds: float,
        agent_id: Optional[int] = None,
        workflow_id: Optional[str] = None,
        task_id: Optional[str] = None,
        cost_per_second: Optional[float] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Record compute cost based on execution time.
        """
        rate = cost_per_second or CostTracking._pricing["compute_per_second"]
        total_cost = duration_seconds * rate

        return CostTracking.record_cost(
            session=session,
            category=CostCategory.COMPUTE,
            amount=total_cost,
            agent_id=agent_id,
            workflow_id=workflow_id,
            task_id=task_id,
            details={
                "duration_seconds": duration_seconds,
                "cost_per_second": rate
            },
            metadata=metadata
        )

    @staticmethod
    def create_budget(
        session,
        name: str,
        amount: float,
        period: str,
        agent_id: Optional[int] = None,
        workflow_id: Optional[str] = None,
        category: Optional[str] = None,
        alert_thresholds: Optional[Dict[str, float]] = None,
        auto_disable_on_exceed: bool = False,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create budget limit.

        Sets spending limits with optional alerts and auto-disable.
        """
        budget_id = CostTracking._generate_budget_id()

        budget = {
            "id": budget_id,
            "name": name,
            "amount": amount,
            "period": period,
            "agent_id": agent_id,
            "workflow_id": workflow_id,
            "category": category,
            "alert_thresholds": alert_thresholds or {"warning": 0.8, "critical": 0.95},
            "auto_disable_on_exceed": auto_disable_on_exceed,
            "metadata": metadata or {},
            "current_spend": 0.0,
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "period_start": datetime.utcnow().isoformat(),
            "period_end": CostTracking._calculate_period_end(period).isoformat(),
            "alerts_triggered": []
        }

        CostTracking._budgets[budget_id] = budget

        return budget

    @staticmethod
    def _calculate_period_end(period: str) -> datetime:
        """Calculate budget period end time"""
        now = datetime.utcnow()

        if period == BudgetPeriod.HOURLY:
            return now + timedelta(hours=1)
        elif period == BudgetPeriod.DAILY:
            return now + timedelta(days=1)
        elif period == BudgetPeriod.WEEKLY:
            return now + timedelta(weeks=1)
        elif period == BudgetPeriod.MONTHLY:
            return now + timedelta(days=30)
        elif period == BudgetPeriod.YEARLY:
            return now + timedelta(days=365)
        else:
            return now + timedelta(days=30)

    @staticmethod
    def _check_budgets(
        session,
        agent_id: Optional[int],
        workflow_id: Optional[str],
        category: Optional[str]
    ):
        """Check if any budgets are exceeded and trigger alerts"""
        for budget_id, budget in CostTracking._budgets.items():
            if budget["status"] != "active":
                continue

            # Check if budget applies to this cost
            if budget["agent_id"] and budget["agent_id"] != agent_id:
                continue
            if budget["workflow_id"] and budget["workflow_id"] != workflow_id:
                continue
            if budget["category"] and budget["category"] != category:
                continue

            # Calculate current spend for this budget
            current_spend = CostTracking._get_budget_spend(budget)
            budget["current_spend"] = current_spend

            # Calculate percentage
            percentage = current_spend / budget["amount"] if budget["amount"] > 0 else 0

            # Check alert thresholds
            thresholds = budget["alert_thresholds"]

            if percentage >= thresholds.get("critical", 0.95):
                CostTracking._trigger_alert(budget, AlertLevel.CRITICAL, percentage)
            elif percentage >= thresholds.get("warning", 0.8):
                CostTracking._trigger_alert(budget, AlertLevel.WARNING, percentage)

            # Check if exceeded and auto-disable
            if percentage >= 1.0 and budget["auto_disable_on_exceed"]:
                budget["status"] = "exceeded"
                CostTracking._trigger_alert(budget, AlertLevel.CRITICAL, percentage, exceeded=True)

    @staticmethod
    def _get_budget_spend(budget: dict) -> float:
        """Calculate current spending for a budget"""
        period_start = datetime.fromisoformat(budget["period_start"])
        period_end = datetime.fromisoformat(budget["period_end"])

        total = 0.0
        for entry in CostTracking._cost_entries.values():
            entry_time = datetime.fromisoformat(entry["timestamp"])

            if entry_time < period_start or entry_time > period_end:
                continue

            # Check filters
            if budget["agent_id"] and entry["agent_id"] != budget["agent_id"]:
                continue
            if budget["workflow_id"] and entry["workflow_id"] != budget["workflow_id"]:
                continue
            if budget["category"] and entry["category"] != budget["category"]:
                continue

            total += entry["amount"]

        return total

    @staticmethod
    def _trigger_alert(budget: dict, level: str, percentage: float, exceeded: bool = False):
        """Trigger budget alert"""
        alert_key = f"{level}_{percentage:.0%}"

        # Don't duplicate alerts
        if alert_key in budget["alerts_triggered"]:
            return

        alert = {
            "budget_id": budget["id"],
            "budget_name": budget["name"],
            "level": level,
            "percentage": percentage,
            "current_spend": budget["current_spend"],
            "budget_amount": budget["amount"],
            "exceeded": exceeded,
            "message": f"Budget '{budget['name']}' at {percentage:.1%} ({budget['current_spend']:.2f}/{budget['amount']:.2f})",
            "timestamp": datetime.utcnow().isoformat()
        }

        CostTracking._alerts.append(alert)
        budget["alerts_triggered"].append(alert_key)

    @staticmethod
    def get_cost_summary(
        session,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        agent_id: Optional[int] = None,
        workflow_id: Optional[str] = None,
        category: Optional[str] = None
    ) -> dict:
        """
        Get cost summary with filtering.

        Returns aggregate costs and breakdowns.
        """
        entries = list(CostTracking._cost_entries.values())

        # Apply filters
        if start_date:
            start = datetime.fromisoformat(start_date)
            entries = [e for e in entries if datetime.fromisoformat(e["timestamp"]) >= start]

        if end_date:
            end = datetime.fromisoformat(end_date)
            entries = [e for e in entries if datetime.fromisoformat(e["timestamp"]) <= end]

        if agent_id:
            entries = [e for e in entries if e["agent_id"] == agent_id]

        if workflow_id:
            entries = [e for e in entries if e["workflow_id"] == workflow_id]

        if category:
            entries = [e for e in entries if e["category"] == category]

        # Calculate totals
        total_cost = sum(e["amount"] for e in entries)

        # Breakdown by category
        category_breakdown = defaultdict(float)
        for entry in entries:
            category_breakdown[entry["category"]] += entry["amount"]

        # Breakdown by agent
        agent_breakdown = defaultdict(float)
        for entry in entries:
            if entry["agent_id"]:
                agent_breakdown[entry["agent_id"]] += entry["amount"]

        # Breakdown by workflow
        workflow_breakdown = defaultdict(float)
        for entry in entries:
            if entry["workflow_id"]:
                workflow_breakdown[entry["workflow_id"]] += entry["amount"]

        return {
            "total_cost": total_cost,
            "entry_count": len(entries),
            "category_breakdown": dict(category_breakdown),
            "agent_breakdown": dict(agent_breakdown),
            "workflow_breakdown": dict(workflow_breakdown),
            "period": {
                "start": start_date,
                "end": end_date
            }
        }

    @staticmethod
    def get_budget_status(
        session,
        budget_id: str
    ) -> dict:
        """Get budget status with current spending"""
        if budget_id not in CostTracking._budgets:
            raise ValueError(f"Budget {budget_id} not found")

        budget = CostTracking._budgets[budget_id]

        # Update current spend
        current_spend = CostTracking._get_budget_spend(budget)
        budget["current_spend"] = current_spend

        # Calculate metrics
        percentage = current_spend / budget["amount"] if budget["amount"] > 0 else 0
        remaining = budget["amount"] - current_spend

        return {
            **budget,
            "percentage_used": percentage,
            "remaining": remaining,
            "is_exceeded": percentage >= 1.0
        }

    @staticmethod
    def list_budgets(
        session,
        status: Optional[str] = None,
        agent_id: Optional[int] = None,
        workflow_id: Optional[str] = None
    ) -> dict:
        """List budgets with filtering"""
        budgets = list(CostTracking._budgets.values())

        if status:
            budgets = [b for b in budgets if b["status"] == status]

        if agent_id:
            budgets = [b for b in budgets if b["agent_id"] == agent_id]

        if workflow_id:
            budgets = [b for b in budgets if b["workflow_id"] == workflow_id]

        # Update current spend for each
        for budget in budgets:
            budget["current_spend"] = CostTracking._get_budget_spend(budget)
            budget["percentage_used"] = budget["current_spend"] / budget["amount"] if budget["amount"] > 0 else 0

        return {
            "budgets": budgets,
            "total": len(budgets)
        }

    @staticmethod
    def get_alerts(
        session,
        level: Optional[str] = None,
        limit: int = 50
    ) -> dict:
        """Get budget alerts"""
        alerts = list(CostTracking._alerts)

        if level:
            alerts = [a for a in alerts if a["level"] == level]

        # Sort by timestamp descending
        alerts.sort(key=lambda a: a["timestamp"], reverse=True)

        return {
            "alerts": alerts[:limit],
            "total": len(alerts)
        }

    @staticmethod
    def get_cost_forecast(
        session,
        days_ahead: int = 30,
        agent_id: Optional[int] = None,
        workflow_id: Optional[str] = None
    ) -> dict:
        """
        Forecast future costs based on historical data.

        Uses simple linear projection from recent trends.
        """
        # Get last 7 days of costs
        end = datetime.utcnow()
        start = end - timedelta(days=7)

        entries = [
            e for e in CostTracking._cost_entries.values()
            if datetime.fromisoformat(e["timestamp"]) >= start
        ]

        if agent_id:
            entries = [e for e in entries if e["agent_id"] == agent_id]

        if workflow_id:
            entries = [e for e in entries if e["workflow_id"] == workflow_id]

        if not entries:
            return {
                "forecast_total": 0.0,
                "daily_average": 0.0,
                "confidence": "low",
                "message": "Insufficient data for forecast"
            }

        # Calculate daily average
        total_cost = sum(e["amount"] for e in entries)
        daily_average = total_cost / 7

        # Project forward
        forecast_total = daily_average * days_ahead

        return {
            "forecast_total": forecast_total,
            "daily_average": daily_average,
            "days_ahead": days_ahead,
            "confidence": "medium" if len(entries) > 20 else "low",
            "historical_period_days": 7,
            "historical_total": total_cost
        }

    @staticmethod
    def update_pricing(
        session,
        pricing_updates: dict
    ) -> dict:
        """Update pricing configuration"""
        CostTracking._pricing.update(pricing_updates)

        return {
            "success": True,
            "pricing": CostTracking._pricing
        }

    @staticmethod
    def get_pricing(session) -> dict:
        """Get current pricing configuration"""
        return CostTracking._pricing

    @staticmethod
    def get_cost_statistics(session) -> dict:
        """Get cost tracking statistics"""
        all_entries = list(CostTracking._cost_entries.values())

        total_cost = sum(e["amount"] for e in all_entries)

        # Category distribution
        category_totals = defaultdict(float)
        for entry in all_entries:
            category_totals[entry["category"]] += entry["amount"]

        # Top spending agents
        agent_totals = list(CostTracking._agent_costs.items())
        agent_totals.sort(key=lambda x: x[1], reverse=True)

        # Active budgets
        active_budgets = [b for b in CostTracking._budgets.values() if b["status"] == "active"]
        exceeded_budgets = [b for b in CostTracking._budgets.values() if b["status"] == "exceeded"]

        return {
            "total_cost": total_cost,
            "total_entries": len(all_entries),
            "category_distribution": dict(category_totals),
            "top_spending_agents": agent_totals[:10],
            "active_budgets": len(active_budgets),
            "exceeded_budgets": len(exceeded_budgets),
            "total_alerts": len(CostTracking._alerts),
            "unique_agents": len(CostTracking._agent_costs),
            "unique_workflows": len(CostTracking._workflow_costs)
        }
