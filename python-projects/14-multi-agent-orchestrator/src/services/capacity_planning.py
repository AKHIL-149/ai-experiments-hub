"""
Capacity Planning and Auto-Scaling Service

Provides capacity forecasting, resource planning, and automatic scaling
based on demand and usage patterns.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from enum import Enum
import statistics


class ResourceType(str, Enum):
    """Types of resources"""
    COMPUTE = "compute"
    MEMORY = "memory"
    STORAGE = "storage"
    NETWORK = "network"
    DATABASE = "database"


class ScalingDirection(str, Enum):
    """Scaling direction"""
    UP = "up"
    DOWN = "down"
    NONE = "none"


class ScalingPolicy(str, Enum):
    """Scaling policy types"""
    TARGET_TRACKING = "target_tracking"
    STEP_SCALING = "step_scaling"
    SCHEDULED = "scheduled"
    PREDICTIVE = "predictive"


class ForecastPeriod(str, Enum):
    """Forecast time periods"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class CapacityPlanning:
    """Capacity planning and auto-scaling management"""

    # In-memory storage
    _capacity_plans: Dict[str, Dict] = {}
    _scaling_policies: Dict[str, Dict] = {}
    _scaling_events: List[Dict] = []
    _resource_usage: List[Dict] = []
    _forecasts: Dict[str, Dict] = {}
    _recommendations: Dict[str, Dict] = {}

    @staticmethod
    def create_capacity_plan(
        session,
        plan_id: str,
        name: str,
        resource_type: ResourceType,
        current_capacity: float,
        target_utilization: float = 70.0,
        buffer_percentage: float = 20.0,
        forecast_period: ForecastPeriod = ForecastPeriod.MONTHLY
    ) -> dict:
        """Create a capacity plan."""
        if plan_id in CapacityPlanning._capacity_plans:
            raise ValueError(f"Capacity plan already exists: {plan_id}")

        if target_utilization < 0 or target_utilization > 100:
            raise ValueError("Target utilization must be between 0 and 100")

        plan = {
            "plan_id": plan_id,
            "name": name,
            "resource_type": resource_type,
            "current_capacity": current_capacity,
            "target_utilization": target_utilization,
            "buffer_percentage": buffer_percentage,
            "forecast_period": forecast_period,
            "created_at": datetime.utcnow().isoformat(),
            "last_updated": None,
            "forecasted_demand": None,
            "recommended_capacity": None,
            "scaling_events_count": 0
        }

        CapacityPlanning._capacity_plans[plan_id] = plan
        return plan

    @staticmethod
    def record_resource_usage(
        session,
        resource_type: ResourceType,
        used: float,
        total: float,
        timestamp: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Record resource usage for capacity planning."""
        usage = {
            "resource_type": resource_type,
            "used": used,
            "total": total,
            "utilization_percent": (used / total * 100) if total > 0 else 0,
            "timestamp": timestamp or datetime.utcnow().isoformat(),
            "metadata": metadata or {}
        }

        CapacityPlanning._resource_usage.append(usage)

        # Keep only last 90 days
        cutoff = datetime.utcnow() - timedelta(days=90)
        cutoff_iso = cutoff.isoformat()
        CapacityPlanning._resource_usage = [
            u for u in CapacityPlanning._resource_usage
            if u["timestamp"] >= cutoff_iso
        ]

        return usage

    @staticmethod
    def generate_forecast(
        session,
        plan_id: str
    ) -> dict:
        """Generate capacity forecast based on historical usage."""
        plan = CapacityPlanning._capacity_plans.get(plan_id)
        if not plan:
            raise ValueError(f"Capacity plan not found: {plan_id}")

        # Get historical data for this resource type
        usage_data = [
            u for u in CapacityPlanning._resource_usage
            if u["resource_type"] == plan["resource_type"]
        ]

        if not usage_data:
            return {
                "plan_id": plan_id,
                "status": "insufficient_data",
                "message": "Not enough historical data to generate forecast"
            }

        # Calculate trends
        utilizations = [u["utilization_percent"] for u in usage_data[-100:]]

        current_avg = statistics.mean(utilizations[-30:]) if len(utilizations) >= 30 else statistics.mean(utilizations)
        historical_avg = statistics.mean(utilizations)

        # Simple linear projection
        growth_rate = (current_avg - historical_avg) / historical_avg if historical_avg > 0 else 0

        # Forecast based on period
        periods = {
            ForecastPeriod.DAILY: 1,
            ForecastPeriod.WEEKLY: 7,
            ForecastPeriod.MONTHLY: 30,
            ForecastPeriod.QUARTERLY: 90
        }

        days = periods[plan["forecast_period"]]
        projected_utilization = current_avg * (1 + growth_rate * (days / 30))
        projected_utilization = min(100, max(0, projected_utilization))

        # Calculate forecasted demand
        forecasted_demand = (projected_utilization / 100) * plan["current_capacity"]

        # Calculate recommended capacity with buffer
        buffer_multiplier = 1 + (plan["buffer_percentage"] / 100)
        recommended_capacity = (forecasted_demand / (plan["target_utilization"] / 100)) * buffer_multiplier

        forecast = {
            "forecast_id": f"forecast_{plan_id}_{datetime.utcnow().timestamp()}",
            "plan_id": plan_id,
            "forecast_period": plan["forecast_period"],
            "generated_at": datetime.utcnow().isoformat(),
            "historical_data_points": len(usage_data),
            "current_utilization": current_avg,
            "projected_utilization": projected_utilization,
            "growth_rate": growth_rate * 100,
            "current_capacity": plan["current_capacity"],
            "forecasted_demand": forecasted_demand,
            "recommended_capacity": recommended_capacity,
            "capacity_gap": recommended_capacity - plan["current_capacity"],
            "requires_scaling": recommended_capacity > plan["current_capacity"]
        }

        # Update plan
        plan["forecasted_demand"] = forecasted_demand
        plan["recommended_capacity"] = recommended_capacity
        plan["last_updated"] = datetime.utcnow().isoformat()

        # Store forecast
        CapacityPlanning._forecasts[forecast["forecast_id"]] = forecast

        # Generate recommendation if needed
        if forecast["requires_scaling"]:
            CapacityPlanning._generate_recommendation(plan, forecast)

        return forecast

    @staticmethod
    def _generate_recommendation(plan: dict, forecast: dict):
        """Generate capacity recommendation."""
        recommendation_id = f"rec_{plan['plan_id']}_{datetime.utcnow().timestamp()}"

        recommendation = {
            "recommendation_id": recommendation_id,
            "plan_id": plan["plan_id"],
            "forecast_id": forecast["forecast_id"],
            "resource_type": plan["resource_type"],
            "current_capacity": plan["current_capacity"],
            "recommended_capacity": forecast["recommended_capacity"],
            "increase_amount": forecast["capacity_gap"],
            "increase_percentage": (forecast["capacity_gap"] / plan["current_capacity"] * 100) if plan["current_capacity"] > 0 else 0,
            "justification": f"Projected utilization of {forecast['projected_utilization']:.1f}% exceeds target of {plan['target_utilization']}%",
            "timeline": plan["forecast_period"],
            "priority": "high" if forecast["projected_utilization"] > 90 else "medium",
            "created_at": datetime.utcnow().isoformat(),
            "applied": False
        }

        CapacityPlanning._recommendations[recommendation_id] = recommendation

    @staticmethod
    def create_scaling_policy(
        session,
        policy_id: str,
        name: str,
        resource_type: ResourceType,
        policy_type: ScalingPolicy,
        scale_up_threshold: float,
        scale_down_threshold: float,
        cooldown_minutes: int = 5,
        min_capacity: float = 1,
        max_capacity: float = 100,
        enabled: bool = True
    ) -> dict:
        """Create an auto-scaling policy."""
        if policy_id in CapacityPlanning._scaling_policies:
            raise ValueError(f"Scaling policy already exists: {policy_id}")

        policy = {
            "policy_id": policy_id,
            "name": name,
            "resource_type": resource_type,
            "policy_type": policy_type,
            "scale_up_threshold": scale_up_threshold,
            "scale_down_threshold": scale_down_threshold,
            "cooldown_minutes": cooldown_minutes,
            "min_capacity": min_capacity,
            "max_capacity": max_capacity,
            "enabled": enabled,
            "created_at": datetime.utcnow().isoformat(),
            "last_triggered": None,
            "scale_up_count": 0,
            "scale_down_count": 0
        }

        CapacityPlanning._scaling_policies[policy_id] = policy
        return policy

    @staticmethod
    def evaluate_scaling(
        session,
        policy_id: str,
        current_utilization: float,
        current_capacity: float
    ) -> dict:
        """Evaluate if scaling is needed based on policy."""
        policy = CapacityPlanning._scaling_policies.get(policy_id)
        if not policy:
            raise ValueError(f"Scaling policy not found: {policy_id}")

        if not policy["enabled"]:
            return {
                "policy_id": policy_id,
                "decision": ScalingDirection.NONE,
                "reason": "Policy is disabled"
            }

        # Check cooldown
        if policy["last_triggered"]:
            last_triggered = datetime.fromisoformat(policy["last_triggered"])
            cooldown_end = last_triggered + timedelta(minutes=policy["cooldown_minutes"])
            if datetime.utcnow() < cooldown_end:
                return {
                    "policy_id": policy_id,
                    "decision": ScalingDirection.NONE,
                    "reason": f"Cooldown period active until {cooldown_end.isoformat()}"
                }

        # Evaluate scaling decision
        decision = ScalingDirection.NONE
        reason = "Current utilization within thresholds"
        new_capacity = current_capacity

        if current_utilization >= policy["scale_up_threshold"]:
            if current_capacity < policy["max_capacity"]:
                decision = ScalingDirection.UP
                # Scale up by 50% or to max capacity
                new_capacity = min(current_capacity * 1.5, policy["max_capacity"])
                reason = f"Utilization {current_utilization:.1f}% exceeds scale-up threshold {policy['scale_up_threshold']:.1f}%"
            else:
                reason = "At maximum capacity"

        elif current_utilization <= policy["scale_down_threshold"]:
            if current_capacity > policy["min_capacity"]:
                decision = ScalingDirection.DOWN
                # Scale down by 25% or to min capacity
                new_capacity = max(current_capacity * 0.75, policy["min_capacity"])
                reason = f"Utilization {current_utilization:.1f}% below scale-down threshold {policy['scale_down_threshold']:.1f}%"
            else:
                reason = "At minimum capacity"

        result = {
            "policy_id": policy_id,
            "decision": decision,
            "reason": reason,
            "current_capacity": current_capacity,
            "new_capacity": new_capacity,
            "capacity_change": new_capacity - current_capacity,
            "evaluated_at": datetime.utcnow().isoformat()
        }

        # Execute scaling if needed
        if decision != ScalingDirection.NONE:
            CapacityPlanning._execute_scaling(policy, decision, current_capacity, new_capacity, reason)

        return result

    @staticmethod
    def _execute_scaling(
        policy: dict,
        direction: ScalingDirection,
        old_capacity: float,
        new_capacity: float,
        reason: str
    ):
        """Execute a scaling action."""
        event = {
            "event_id": f"event_{len(CapacityPlanning._scaling_events)}_{datetime.utcnow().timestamp()}",
            "policy_id": policy["policy_id"],
            "resource_type": policy["resource_type"],
            "direction": direction,
            "old_capacity": old_capacity,
            "new_capacity": new_capacity,
            "capacity_change": new_capacity - old_capacity,
            "reason": reason,
            "executed_at": datetime.utcnow().isoformat(),
            "status": "completed"
        }

        CapacityPlanning._scaling_events.append(event)

        # Update policy stats
        policy["last_triggered"] = event["executed_at"]
        if direction == ScalingDirection.UP:
            policy["scale_up_count"] += 1
        else:
            policy["scale_down_count"] += 1

        # Update related capacity plans
        for plan in CapacityPlanning._capacity_plans.values():
            if plan["resource_type"] == policy["resource_type"]:
                plan["current_capacity"] = new_capacity
                plan["scaling_events_count"] += 1

    @staticmethod
    def get_scaling_history(
        session,
        resource_type: Optional[ResourceType] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100
    ) -> List[dict]:
        """Get scaling event history."""
        events = CapacityPlanning._scaling_events.copy()

        if resource_type:
            events = [e for e in events if e["resource_type"] == resource_type]

        if start_time:
            events = [e for e in events if e["executed_at"] >= start_time]

        if end_time:
            events = [e for e in events if e["executed_at"] <= end_time]

        # Sort by execution time descending
        events.sort(key=lambda x: x["executed_at"], reverse=True)

        return events[:limit]

    @staticmethod
    def get_recommendations(
        session,
        applied: Optional[bool] = None
    ) -> List[dict]:
        """Get capacity recommendations."""
        recommendations = list(CapacityPlanning._recommendations.values())

        if applied is not None:
            recommendations = [r for r in recommendations if r["applied"] == applied]

        # Sort by priority and creation time
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(
            key=lambda x: (priority_order.get(x["priority"], 3), x["created_at"]),
            reverse=True
        )

        return recommendations

    @staticmethod
    def apply_recommendation(
        session,
        recommendation_id: str,
        notes: Optional[str] = None
    ) -> dict:
        """Apply a capacity recommendation."""
        recommendation = CapacityPlanning._recommendations.get(recommendation_id)
        if not recommendation:
            raise ValueError(f"Recommendation not found: {recommendation_id}")

        if recommendation["applied"]:
            raise ValueError("Recommendation already applied")

        # Update plan capacity
        plan = CapacityPlanning._capacity_plans.get(recommendation["plan_id"])
        if plan:
            plan["current_capacity"] = recommendation["recommended_capacity"]

        recommendation["applied"] = True
        recommendation["applied_at"] = datetime.utcnow().isoformat()
        recommendation["notes"] = notes

        return {
            "recommendation_id": recommendation_id,
            "status": "applied",
            "applied_at": recommendation["applied_at"],
            "new_capacity": recommendation["recommended_capacity"]
        }

    @staticmethod
    def estimate_costs(
        session,
        resource_type: ResourceType,
        capacity: float,
        unit_cost: float,
        duration_hours: int = 720  # Default 30 days
    ) -> dict:
        """Estimate costs for a given capacity."""
        total_cost = capacity * unit_cost * duration_hours

        return {
            "resource_type": resource_type,
            "capacity": capacity,
            "unit_cost": unit_cost,
            "duration_hours": duration_hours,
            "total_cost": total_cost,
            "monthly_cost": total_cost if duration_hours == 720 else (total_cost / duration_hours * 720),
            "daily_cost": total_cost / (duration_hours / 24),
            "calculated_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get capacity planning statistics."""
        # Scaling event stats
        scale_up_events = sum(1 for e in CapacityPlanning._scaling_events if e["direction"] == ScalingDirection.UP)
        scale_down_events = sum(1 for e in CapacityPlanning._scaling_events if e["direction"] == ScalingDirection.DOWN)

        # Resource usage stats
        usage_by_type = defaultdict(list)
        for usage in CapacityPlanning._resource_usage[-1000:]:
            usage_by_type[usage["resource_type"]].append(usage["utilization_percent"])

        avg_utilization = {}
        for resource_type, utilizations in usage_by_type.items():
            avg_utilization[resource_type] = {
                "avg": statistics.mean(utilizations),
                "max": max(utilizations),
                "min": min(utilizations)
            }

        return {
            "capacity_plans": len(CapacityPlanning._capacity_plans),
            "scaling_policies": {
                "total": len(CapacityPlanning._scaling_policies),
                "enabled": sum(1 for p in CapacityPlanning._scaling_policies.values() if p["enabled"])
            },
            "scaling_events": {
                "total": len(CapacityPlanning._scaling_events),
                "scale_up": scale_up_events,
                "scale_down": scale_down_events
            },
            "resource_usage_records": len(CapacityPlanning._resource_usage),
            "forecasts": len(CapacityPlanning._forecasts),
            "recommendations": {
                "total": len(CapacityPlanning._recommendations),
                "pending": sum(1 for r in CapacityPlanning._recommendations.values() if not r["applied"]),
                "applied": sum(1 for r in CapacityPlanning._recommendations.values() if r["applied"])
            },
            "average_utilization": avg_utilization
        }
