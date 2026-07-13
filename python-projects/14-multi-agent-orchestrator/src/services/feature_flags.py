"""
Feature Flags and A/B Testing Service

Provides feature flag management, A/B testing, gradual rollouts, and experiment tracking
for controlled feature releases and data-driven decision making.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from enum import Enum
import random
import hashlib
import statistics


class FlagStatus(str, Enum):
    """Feature flag status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


class RolloutStrategy(str, Enum):
    """Rollout strategy"""
    ALL_USERS = "all_users"
    PERCENTAGE = "percentage"
    USER_SEGMENTS = "user_segments"
    GRADUAL = "gradual"
    TARGETED = "targeted"


class ExperimentStatus(str, Enum):
    """A/B test experiment status"""
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class VariantType(str, Enum):
    """Experiment variant type"""
    CONTROL = "control"
    TREATMENT = "treatment"


class SegmentOperator(str, Enum):
    """Segment rule operator"""
    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    IN = "in"
    NOT_IN = "not_in"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    CONTAINS = "contains"
    MATCHES = "matches"


class FeatureFlags:
    """Feature Flags and A/B Testing management"""

    # In-memory storage
    _flags: Dict[str, Dict] = {}
    _experiments: Dict[str, Dict] = {}
    _user_assignments: Dict[str, Dict] = defaultdict(dict)
    _flag_evaluations: List[Dict] = []
    _experiment_events: List[Dict] = []
    _segments: Dict[str, Dict] = {}
    _metrics: Dict[str, Dict] = {}

    @staticmethod
    def create_flag(
        session,
        flag_id: str,
        name: str,
        description: Optional[str] = None,
        default_value: bool = False,
        rollout_strategy: RolloutStrategy = RolloutStrategy.ALL_USERS,
        rollout_percentage: int = 100,
        target_segments: Optional[List[str]] = None,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Create a feature flag."""
        if flag_id in FeatureFlags._flags:
            raise ValueError(f"Flag already exists: {flag_id}")

        flag = {
            "flag_id": flag_id,
            "name": name,
            "description": description or "",
            "default_value": default_value,
            "current_value": default_value,
            "status": FlagStatus.ACTIVE,
            "rollout_strategy": rollout_strategy,
            "rollout_percentage": rollout_percentage,
            "target_segments": target_segments or [],
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "total_evaluations": 0,
            "enabled_count": 0,
            "disabled_count": 0,
            "last_evaluated": None
        }

        FeatureFlags._flags[flag_id] = flag

        return flag

    @staticmethod
    def evaluate_flag(
        session,
        flag_id: str,
        user_id: str,
        context: Optional[Dict] = None
    ) -> dict:
        """Evaluate a feature flag for a user."""
        flag = FeatureFlags._flags.get(flag_id)
        if not flag:
            raise ValueError(f"Flag not found: {flag_id}")

        # Check if flag is active
        if flag["status"] != FlagStatus.ACTIVE:
            is_enabled = flag["default_value"]
            reason = "flag_inactive"
        else:
            # Evaluate based on rollout strategy
            is_enabled, reason = FeatureFlags._evaluate_rollout(
                flag, user_id, context or {}
            )

        # Record evaluation
        evaluation = {
            "evaluation_id": f"eval_{len(FeatureFlags._flag_evaluations)}_{datetime.utcnow().timestamp()}",
            "flag_id": flag_id,
            "user_id": user_id,
            "is_enabled": is_enabled,
            "reason": reason,
            "context": context or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        FeatureFlags._flag_evaluations.append(evaluation)

        # Update flag statistics
        flag["total_evaluations"] += 1
        flag["last_evaluated"] = datetime.utcnow().isoformat()
        if is_enabled:
            flag["enabled_count"] += 1
        else:
            flag["disabled_count"] += 1

        # Keep only last 10000 evaluations
        FeatureFlags._flag_evaluations = FeatureFlags._flag_evaluations[-10000:]

        return {
            "flag_id": flag_id,
            "is_enabled": is_enabled,
            "reason": reason,
            "evaluation_id": evaluation["evaluation_id"]
        }

    @staticmethod
    def _evaluate_rollout(flag: dict, user_id: str, context: Dict) -> tuple:
        """Evaluate rollout strategy for a flag."""
        strategy = flag["rollout_strategy"]

        if strategy == RolloutStrategy.ALL_USERS:
            return True, "all_users"

        elif strategy == RolloutStrategy.PERCENTAGE:
            # Use consistent hashing for stable rollout
            hash_value = int(hashlib.md5(f"{flag['flag_id']}:{user_id}".encode()).hexdigest(), 16)
            percentage = (hash_value % 100) + 1
            is_enabled = percentage <= flag["rollout_percentage"]
            return is_enabled, f"percentage_rollout_{flag['rollout_percentage']}"

        elif strategy == RolloutStrategy.USER_SEGMENTS:
            # Check if user belongs to target segments
            user_segments = context.get("segments", [])
            has_match = any(seg in flag["target_segments"] for seg in user_segments)
            return has_match, "segment_match" if has_match else "segment_no_match"

        elif strategy == RolloutStrategy.TARGETED:
            # Check specific user targeting
            targeted_users = flag.get("metadata", {}).get("targeted_users", [])
            is_targeted = user_id in targeted_users
            return is_targeted, "targeted_user" if is_targeted else "not_targeted"

        return flag["default_value"], "default"

    @staticmethod
    def update_flag(
        session,
        flag_id: str,
        current_value: Optional[bool] = None,
        rollout_percentage: Optional[int] = None,
        rollout_strategy: Optional[RolloutStrategy] = None,
        status: Optional[FlagStatus] = None,
        target_segments: Optional[List[str]] = None
    ) -> dict:
        """Update a feature flag."""
        flag = FeatureFlags._flags.get(flag_id)
        if not flag:
            raise ValueError(f"Flag not found: {flag_id}")

        # Update fields
        if current_value is not None:
            flag["current_value"] = current_value
        if rollout_percentage is not None:
            flag["rollout_percentage"] = rollout_percentage
        if rollout_strategy is not None:
            flag["rollout_strategy"] = rollout_strategy
        if status is not None:
            flag["status"] = status
        if target_segments is not None:
            flag["target_segments"] = target_segments

        flag["updated_at"] = datetime.utcnow().isoformat()

        return flag

    @staticmethod
    def create_experiment(
        session,
        experiment_id: str,
        name: str,
        description: Optional[str] = None,
        flag_id: str = None,
        variants: List[Dict] = None,
        traffic_allocation: int = 100,
        target_segments: Optional[List[str]] = None,
        metrics: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> dict:
        """Create an A/B test experiment."""
        if experiment_id in FeatureFlags._experiments:
            raise ValueError(f"Experiment already exists: {experiment_id}")

        # Validate variants
        if not variants or len(variants) < 2:
            raise ValueError("Experiment must have at least 2 variants")

        # Ensure traffic allocation adds up to 100
        total_allocation = sum(v.get("traffic_weight", 0) for v in variants)
        if total_allocation != 100:
            raise ValueError(f"Variant traffic weights must sum to 100, got {total_allocation}")

        experiment = {
            "experiment_id": experiment_id,
            "name": name,
            "description": description or "",
            "flag_id": flag_id,
            "variants": variants,
            "traffic_allocation": traffic_allocation,
            "target_segments": target_segments or [],
            "metrics": metrics or [],
            "status": ExperimentStatus.DRAFT,
            "start_date": start_date,
            "end_date": end_date,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "total_participants": 0,
            "variant_assignments": defaultdict(int)
        }

        FeatureFlags._experiments[experiment_id] = experiment

        return experiment

    @staticmethod
    def assign_variant(
        session,
        experiment_id: str,
        user_id: str,
        context: Optional[Dict] = None
    ) -> dict:
        """Assign a user to an experiment variant."""
        experiment = FeatureFlags._experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment not found: {experiment_id}")

        if experiment["status"] != ExperimentStatus.RUNNING:
            return {
                "experiment_id": experiment_id,
                "user_id": user_id,
                "variant": None,
                "reason": f"experiment_{experiment['status']}"
            }

        # Check if user already assigned
        assignment_key = f"{experiment_id}:{user_id}"
        if assignment_key in FeatureFlags._user_assignments:
            existing = FeatureFlags._user_assignments[assignment_key]
            return {
                "experiment_id": experiment_id,
                "user_id": user_id,
                "variant": existing["variant"],
                "reason": "existing_assignment"
            }

        # Check traffic allocation
        hash_value = int(hashlib.md5(f"{experiment_id}:{user_id}".encode()).hexdigest(), 16)
        if (hash_value % 100) + 1 > experiment["traffic_allocation"]:
            return {
                "experiment_id": experiment_id,
                "user_id": user_id,
                "variant": None,
                "reason": "traffic_allocation_excluded"
            }

        # Assign variant based on weights
        variant = FeatureFlags._assign_weighted_variant(experiment, user_id)

        # Record assignment
        assignment = {
            "assignment_id": f"assign_{len(FeatureFlags._user_assignments)}",
            "experiment_id": experiment_id,
            "user_id": user_id,
            "variant": variant,
            "assigned_at": datetime.utcnow().isoformat(),
            "context": context or {}
        }

        FeatureFlags._user_assignments[assignment_key] = assignment

        # Update experiment stats
        experiment["total_participants"] += 1
        experiment["variant_assignments"][variant] = experiment["variant_assignments"].get(variant, 0) + 1

        return {
            "experiment_id": experiment_id,
            "user_id": user_id,
            "variant": variant,
            "reason": "new_assignment"
        }

    @staticmethod
    def _assign_weighted_variant(experiment: dict, user_id: str) -> str:
        """Assign variant using consistent hashing and weights."""
        variants = experiment["variants"]

        # Use hash for consistent assignment
        hash_value = int(hashlib.md5(f"{experiment['experiment_id']}:{user_id}".encode()).hexdigest(), 16)
        position = hash_value % 100

        # Find variant based on cumulative weights
        cumulative = 0
        for variant in variants:
            cumulative += variant["traffic_weight"]
            if position < cumulative:
                return variant["variant_id"]

        # Fallback to first variant
        return variants[0]["variant_id"]

    @staticmethod
    def track_event(
        session,
        experiment_id: str,
        user_id: str,
        event_name: str,
        value: Optional[float] = None,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Track an event for experiment metrics."""
        experiment = FeatureFlags._experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment not found: {experiment_id}")

        # Get user's variant assignment
        assignment_key = f"{experiment_id}:{user_id}"
        assignment = FeatureFlags._user_assignments.get(assignment_key)

        variant = assignment["variant"] if assignment else None

        event = {
            "event_id": f"evt_{len(FeatureFlags._experiment_events)}_{datetime.utcnow().timestamp()}",
            "experiment_id": experiment_id,
            "user_id": user_id,
            "variant": variant,
            "event_name": event_name,
            "value": value,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        FeatureFlags._experiment_events.append(event)

        # Keep only last 100000 events
        FeatureFlags._experiment_events = FeatureFlags._experiment_events[-100000:]

        return event

    @staticmethod
    def get_experiment_results(session, experiment_id: str) -> dict:
        """Get experiment results and analysis."""
        experiment = FeatureFlags._experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment not found: {experiment_id}")

        # Get all events for this experiment
        events = [
            e for e in FeatureFlags._experiment_events
            if e["experiment_id"] == experiment_id
        ]

        # Calculate metrics per variant
        variant_results = {}
        for variant_info in experiment["variants"]:
            variant_id = variant_info["variant_id"]
            variant_events = [e for e in events if e["variant"] == variant_id]

            # Count events by type
            event_counts = defaultdict(int)
            event_values = defaultdict(list)

            for event in variant_events:
                event_counts[event["event_name"]] += 1
                if event["value"] is not None:
                    event_values[event["event_name"]].append(event["value"])

            # Calculate statistics
            metrics = {}
            for metric_name, values in event_values.items():
                if values:
                    metrics[metric_name] = {
                        "count": len(values),
                        "sum": sum(values),
                        "mean": statistics.mean(values),
                        "median": statistics.median(values),
                        "min": min(values),
                        "max": max(values),
                        "stddev": statistics.stdev(values) if len(values) > 1 else 0
                    }

            variant_results[variant_id] = {
                "variant_id": variant_id,
                "participants": experiment["variant_assignments"].get(variant_id, 0),
                "total_events": len(variant_events),
                "event_counts": dict(event_counts),
                "metrics": metrics
            }

        return {
            "experiment_id": experiment_id,
            "name": experiment["name"],
            "status": experiment["status"],
            "total_participants": experiment["total_participants"],
            "total_events": len(events),
            "variant_results": variant_results,
            "analyzed_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def start_experiment(session, experiment_id: str) -> dict:
        """Start an experiment."""
        experiment = FeatureFlags._experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment not found: {experiment_id}")

        if experiment["status"] != ExperimentStatus.DRAFT:
            raise ValueError(f"Can only start draft experiments")

        experiment["status"] = ExperimentStatus.RUNNING
        experiment["start_date"] = datetime.utcnow().isoformat()
        experiment["updated_at"] = datetime.utcnow().isoformat()

        return experiment

    @staticmethod
    def stop_experiment(session, experiment_id: str) -> dict:
        """Stop an experiment."""
        experiment = FeatureFlags._experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment not found: {experiment_id}")

        experiment["status"] = ExperimentStatus.COMPLETED
        experiment["end_date"] = datetime.utcnow().isoformat()
        experiment["updated_at"] = datetime.utcnow().isoformat()

        return experiment

    @staticmethod
    def create_segment(
        session,
        segment_id: str,
        name: str,
        description: Optional[str] = None,
        rules: List[Dict] = None
    ) -> dict:
        """Create a user segment."""
        if segment_id in FeatureFlags._segments:
            raise ValueError(f"Segment already exists: {segment_id}")

        segment = {
            "segment_id": segment_id,
            "name": name,
            "description": description or "",
            "rules": rules or [],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "total_evaluations": 0,
            "match_count": 0
        }

        FeatureFlags._segments[segment_id] = segment

        return segment

    @staticmethod
    def evaluate_segment(
        session,
        segment_id: str,
        user_attributes: Dict
    ) -> dict:
        """Evaluate if a user matches a segment."""
        segment = FeatureFlags._segments.get(segment_id)
        if not segment:
            raise ValueError(f"Segment not found: {segment_id}")

        # Evaluate all rules
        matches = True
        for rule in segment["rules"]:
            attribute = rule["attribute"]
            operator = rule["operator"]
            value = rule["value"]

            user_value = user_attributes.get(attribute)

            # Evaluate rule
            rule_matches = FeatureFlags._evaluate_rule(operator, user_value, value)

            if not rule_matches:
                matches = False
                break

        # Update statistics
        segment["total_evaluations"] += 1
        if matches:
            segment["match_count"] += 1

        return {
            "segment_id": segment_id,
            "matches": matches,
            "evaluated_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def _evaluate_rule(operator: str, user_value: Any, target_value: Any) -> bool:
        """Evaluate a segment rule."""
        if operator == SegmentOperator.EQUALS:
            return user_value == target_value
        elif operator == SegmentOperator.NOT_EQUALS:
            return user_value != target_value
        elif operator == SegmentOperator.IN:
            return user_value in target_value
        elif operator == SegmentOperator.NOT_IN:
            return user_value not in target_value
        elif operator == SegmentOperator.GREATER_THAN:
            return user_value > target_value
        elif operator == SegmentOperator.LESS_THAN:
            return user_value < target_value
        elif operator == SegmentOperator.CONTAINS:
            return target_value in str(user_value)
        elif operator == SegmentOperator.MATCHES:
            import re
            return bool(re.match(target_value, str(user_value)))
        return False

    @staticmethod
    def get_flag_analytics(session, flag_id: str) -> dict:
        """Get analytics for a feature flag."""
        flag = FeatureFlags._flags.get(flag_id)
        if not flag:
            raise ValueError(f"Flag not found: {flag_id}")

        # Get evaluations
        evaluations = [
            e for e in FeatureFlags._flag_evaluations
            if e["flag_id"] == flag_id
        ]

        # Calculate metrics
        total = len(evaluations)
        enabled = sum(1 for e in evaluations if e["is_enabled"])
        disabled = total - enabled

        # Reasons breakdown
        reasons = defaultdict(int)
        for eval in evaluations:
            reasons[eval["reason"]] += 1

        return {
            "flag_id": flag_id,
            "name": flag["name"],
            "status": flag["status"],
            "total_evaluations": total,
            "enabled_count": enabled,
            "disabled_count": disabled,
            "enabled_rate": (enabled / total * 100) if total > 0 else 0,
            "reasons": dict(reasons),
            "analyzed_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get comprehensive feature flags and A/B testing statistics."""
        total_flags = len(FeatureFlags._flags)
        active_flags = sum(1 for f in FeatureFlags._flags.values() if f["status"] == FlagStatus.ACTIVE)

        total_experiments = len(FeatureFlags._experiments)
        running_experiments = sum(
            1 for e in FeatureFlags._experiments.values()
            if e["status"] == ExperimentStatus.RUNNING
        )

        return {
            "flags": {
                "total": total_flags,
                "active": active_flags,
                "inactive": total_flags - active_flags
            },
            "experiments": {
                "total": total_experiments,
                "running": running_experiments,
                "completed": sum(
                    1 for e in FeatureFlags._experiments.values()
                    if e["status"] == ExperimentStatus.COMPLETED
                ),
                "draft": sum(
                    1 for e in FeatureFlags._experiments.values()
                    if e["status"] == ExperimentStatus.DRAFT
                )
            },
            "evaluations": {
                "total": len(FeatureFlags._flag_evaluations),
                "recent_24h": sum(
                    1 for e in FeatureFlags._flag_evaluations
                    if e["timestamp"] >= (datetime.utcnow() - timedelta(hours=24)).isoformat()
                )
            },
            "assignments": {
                "total": len(FeatureFlags._user_assignments)
            },
            "events": {
                "total": len(FeatureFlags._experiment_events)
            },
            "segments": {
                "total": len(FeatureFlags._segments)
            }
        }
