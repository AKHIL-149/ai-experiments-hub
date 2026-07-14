"""
Agent Conflict Resolution Service

Detects and resolves conflicts between agents in multi-agent systems.
Handles resource conflicts, decision conflicts, priority conflicts, and task assignment conflicts.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from src.models import Agent, Task
from src.core.logging import logger


class ConflictType:
    """Conflict type constants"""
    RESOURCE = "resource"  # Multiple agents need same resource
    DECISION = "decision"  # Agents disagree on a decision
    PRIORITY = "priority"  # Task priority conflicts
    ASSIGNMENT = "assignment"  # Multiple agents assigned same task
    STATE = "state"  # Inconsistent state between agents
    TIMING = "timing"  # Scheduling/timing conflicts


class ConflictSeverity:
    """Conflict severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConflictStatus:
    """Conflict status constants"""
    DETECTED = "detected"
    ANALYZING = "analyzing"
    RESOLVING = "resolving"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class ResolutionStrategy:
    """Resolution strategy constants"""
    PRIORITY_BASED = "priority_based"  # Use agent/task priority
    VOTING = "voting"  # Democratic vote
    ARBITRATION = "arbitration"  # Third-party arbitrator
    FIRST_COME_FIRST_SERVED = "fcfs"  # Chronological order
    ROUND_ROBIN = "round_robin"  # Fair distribution
    AUTOMATIC = "automatic"  # System decides
    MANUAL = "manual"  # Human intervention required


class ConflictResolution:
    """Service for detecting and resolving agent conflicts"""

    # In-memory storage for conflicts
    _conflicts: Dict[int, Dict[str, Any]] = {}
    _resolution_history: List[Dict[str, Any]] = []
    _conflict_counter = 0

    @staticmethod
    def detect_conflict(
        session: Session,
        conflict_type: str,
        involved_agents: List[int],
        resource_id: Optional[str] = None,
        task_id: Optional[int] = None,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Detect and register a new conflict.

        Args:
            session: Database session
            conflict_type: Type of conflict
            involved_agents: List of agent IDs involved
            resource_id: Optional resource identifier
            task_id: Optional task ID
            description: Conflict description
            metadata: Optional metadata

        Returns:
            Conflict details
        """
        # Validate agents exist
        agents = session.query(Agent).filter(Agent.id.in_(involved_agents)).all()
        if len(agents) != len(involved_agents):
            raise ValueError("One or more agents not found")

        # Validate task if provided
        if task_id:
            task = session.query(Task).filter(Task.id == task_id).first()
            if not task:
                raise ValueError(f"Task {task_id} not found")

        ConflictResolution._conflict_counter += 1
        conflict_id = ConflictResolution._conflict_counter

        # Determine severity based on conflict type and number of agents
        severity = ConflictResolution._calculate_severity(
            conflict_type,
            len(involved_agents),
            task_id
        )

        conflict = {
            "conflict_id": conflict_id,
            "conflict_type": conflict_type,
            "involved_agents": involved_agents,
            "resource_id": resource_id,
            "task_id": task_id,
            "description": description,
            "severity": severity,
            "status": ConflictStatus.DETECTED,
            "detected_at": datetime.utcnow().isoformat(),
            "resolved_at": None,
            "resolution_strategy": None,
            "resolution_outcome": None,
            "attempts": 0,
            "metadata": metadata or {}
        }

        ConflictResolution._conflicts[conflict_id] = conflict

        logger.warning(
            f"Conflict detected: {conflict_type} involving {len(involved_agents)} agents (ID: {conflict_id})"
        )

        return conflict

    @staticmethod
    def _calculate_severity(
        conflict_type: str,
        agent_count: int,
        task_id: Optional[int]
    ) -> str:
        """Calculate conflict severity"""
        # Critical conflicts
        if conflict_type == ConflictType.STATE:
            return ConflictSeverity.CRITICAL
        if agent_count > 5:
            return ConflictSeverity.CRITICAL

        # High severity
        if conflict_type in [ConflictType.RESOURCE, ConflictType.ASSIGNMENT]:
            return ConflictSeverity.HIGH
        if agent_count > 3:
            return ConflictSeverity.HIGH

        # Medium severity
        if conflict_type == ConflictType.PRIORITY:
            return ConflictSeverity.MEDIUM

        # Low severity
        return ConflictSeverity.LOW

    @staticmethod
    def resolve_conflict(
        session: Session,
        conflict_id: int,
        strategy: str = ResolutionStrategy.AUTOMATIC,
        manual_decision: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Resolve a detected conflict.

        Args:
            session: Database session
            conflict_id: Conflict ID
            strategy: Resolution strategy
            manual_decision: Manual decision data (for manual strategy)

        Returns:
            Resolution result
        """
        if conflict_id not in ConflictResolution._conflicts:
            raise ValueError(f"Conflict {conflict_id} not found")

        conflict = ConflictResolution._conflicts[conflict_id]

        if conflict["status"] == ConflictStatus.RESOLVED:
            raise ValueError(f"Conflict {conflict_id} already resolved")

        conflict["status"] = ConflictStatus.RESOLVING
        conflict["resolution_strategy"] = strategy
        conflict["attempts"] += 1

        try:
            # Apply resolution strategy
            if strategy == ResolutionStrategy.PRIORITY_BASED:
                outcome = ConflictResolution._resolve_by_priority(session, conflict)
            elif strategy == ResolutionStrategy.VOTING:
                outcome = ConflictResolution._resolve_by_voting(session, conflict)
            elif strategy == ResolutionStrategy.ARBITRATION:
                outcome = ConflictResolution._resolve_by_arbitration(session, conflict)
            elif strategy == ResolutionStrategy.FIRST_COME_FIRST_SERVED:
                outcome = ConflictResolution._resolve_fcfs(session, conflict)
            elif strategy == ResolutionStrategy.ROUND_ROBIN:
                outcome = ConflictResolution._resolve_round_robin(session, conflict)
            elif strategy == ResolutionStrategy.MANUAL:
                if not manual_decision:
                    raise ValueError("Manual decision required for manual strategy")
                outcome = manual_decision
            else:  # AUTOMATIC
                outcome = ConflictResolution._resolve_automatically(session, conflict)

            conflict["status"] = ConflictStatus.RESOLVED
            conflict["resolved_at"] = datetime.utcnow().isoformat()
            conflict["resolution_outcome"] = outcome

            # Record in history
            ConflictResolution._resolution_history.append({
                "conflict_id": conflict_id,
                "conflict_type": conflict["conflict_type"],
                "strategy": strategy,
                "outcome": outcome,
                "resolved_at": conflict["resolved_at"],
                "duration_seconds": (
                    datetime.fromisoformat(conflict["resolved_at"]) -
                    datetime.fromisoformat(conflict["detected_at"])
                ).total_seconds()
            })

            # Keep only last 1000 history entries
            if len(ConflictResolution._resolution_history) > 1000:
                ConflictResolution._resolution_history = ConflictResolution._resolution_history[-1000:]

            logger.info(
                f"Conflict {conflict_id} resolved using {strategy} strategy"
            )

            return {
                "conflict_id": conflict_id,
                "status": conflict["status"],
                "strategy": strategy,
                "outcome": outcome,
                "attempts": conflict["attempts"]
            }

        except Exception as e:
            conflict["status"] = ConflictStatus.ESCALATED
            logger.error(f"Failed to resolve conflict {conflict_id}: {e}")
            raise

    @staticmethod
    def _resolve_by_priority(session: Session, conflict: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve conflict based on agent priority"""
        agents = session.query(Agent).filter(
            Agent.id.in_(conflict["involved_agents"])
        ).all()

        # Sort by priority (assuming higher priority value = higher priority)
        # Get priority from metadata if available
        agent_priorities = []
        for agent in agents:
            priority = agent.metadata.get("priority", 0) if agent.metadata else 0
            agent_priorities.append({"agent_id": agent.id, "priority": priority})

        agent_priorities.sort(key=lambda x: x["priority"], reverse=True)

        return {
            "winner_agent_id": agent_priorities[0]["agent_id"],
            "method": "priority_based",
            "priority_order": agent_priorities
        }

    @staticmethod
    def _resolve_by_voting(session: Session, conflict: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve conflict using voting mechanism"""
        # Simulate voting - in real implementation, would collect votes
        involved_agents = conflict["involved_agents"]

        # Simple majority: first agent gets vote from half
        winner_agent_id = involved_agents[0]

        return {
            "winner_agent_id": winner_agent_id,
            "method": "voting",
            "vote_count": len(involved_agents) // 2 + 1
        }

    @staticmethod
    def _resolve_by_arbitration(session: Session, conflict: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve conflict using third-party arbitration"""
        # Find an agent not involved in the conflict to arbitrate
        excluded_ids = conflict["involved_agents"]
        arbitrator = session.query(Agent).filter(
            ~Agent.id.in_(excluded_ids)
        ).first()

        if not arbitrator:
            # Fallback to automatic resolution
            return ConflictResolution._resolve_automatically(session, conflict)

        # Arbitrator picks first agent (simplified logic)
        return {
            "winner_agent_id": conflict["involved_agents"][0],
            "method": "arbitration",
            "arbitrator_id": arbitrator.id,
            "arbitrator_name": arbitrator.name
        }

    @staticmethod
    def _resolve_fcfs(session: Session, conflict: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve using first-come-first-served"""
        # First agent in the list gets priority
        return {
            "winner_agent_id": conflict["involved_agents"][0],
            "method": "first_come_first_served"
        }

    @staticmethod
    def _resolve_round_robin(session: Session, conflict: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve using round-robin distribution"""
        # Use conflict_id to determine which agent's turn it is
        index = conflict["conflict_id"] % len(conflict["involved_agents"])
        return {
            "winner_agent_id": conflict["involved_agents"][index],
            "method": "round_robin",
            "round_robin_index": index
        }

    @staticmethod
    def _resolve_automatically(session: Session, conflict: Dict[str, Any]) -> Dict[str, Any]:
        """Automatic resolution based on conflict type"""
        conflict_type = conflict["conflict_type"]

        if conflict_type == ConflictType.RESOURCE:
            return ConflictResolution._resolve_by_priority(session, conflict)
        elif conflict_type == ConflictType.ASSIGNMENT:
            return ConflictResolution._resolve_round_robin(session, conflict)
        elif conflict_type == ConflictType.PRIORITY:
            return ConflictResolution._resolve_by_voting(session, conflict)
        else:
            return ConflictResolution._resolve_fcfs(session, conflict)

    @staticmethod
    def get_conflict(session: Session, conflict_id: int) -> Dict[str, Any]:
        """Get conflict details"""
        if conflict_id not in ConflictResolution._conflicts:
            raise ValueError(f"Conflict {conflict_id} not found")

        conflict = ConflictResolution._conflicts[conflict_id]

        # Enrich with agent details
        agents = session.query(Agent).filter(
            Agent.id.in_(conflict["involved_agents"])
        ).all()

        enriched_conflict = {
            **conflict,
            "agents": [
                {
                    "agent_id": agent.id,
                    "agent_name": agent.name,
                    "agent_type": agent.type
                }
                for agent in agents
            ]
        }

        return enriched_conflict

    @staticmethod
    def list_conflicts(
        session: Session,
        status: Optional[str] = None,
        conflict_type: Optional[str] = None,
        severity: Optional[str] = None,
        agent_id: Optional[int] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        List conflicts with optional filtering.

        Args:
            session: Database session
            status: Optional status filter
            conflict_type: Optional conflict type filter
            severity: Optional severity filter
            agent_id: Optional agent ID filter
            limit: Maximum conflicts to return

        Returns:
            List of conflicts
        """
        filtered_conflicts = []

        for conflict in ConflictResolution._conflicts.values():
            # Filter by status
            if status and conflict["status"] != status:
                continue

            # Filter by conflict type
            if conflict_type and conflict["conflict_type"] != conflict_type:
                continue

            # Filter by severity
            if severity and conflict["severity"] != severity:
                continue

            # Filter by agent involvement
            if agent_id and agent_id not in conflict["involved_agents"]:
                continue

            filtered_conflicts.append(conflict)

            if len(filtered_conflicts) >= limit:
                break

        return {
            "total": len(filtered_conflicts),
            "conflicts": filtered_conflicts
        }

    @staticmethod
    def get_agent_conflicts(
        session: Session,
        agent_id: int,
        status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get all conflicts involving a specific agent.

        Args:
            session: Database session
            agent_id: Agent ID
            status: Optional status filter

        Returns:
            Agent's conflicts
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        return ConflictResolution.list_conflicts(
            session=session,
            agent_id=agent_id,
            status=status
        )

    @staticmethod
    def escalate_conflict(
        session: Session,
        conflict_id: int,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Escalate a conflict for manual intervention.

        Args:
            session: Database session
            conflict_id: Conflict ID
            reason: Escalation reason

        Returns:
            Updated conflict
        """
        if conflict_id not in ConflictResolution._conflicts:
            raise ValueError(f"Conflict {conflict_id} not found")

        conflict = ConflictResolution._conflicts[conflict_id]

        conflict["status"] = ConflictStatus.ESCALATED
        conflict["escalation_reason"] = reason
        conflict["escalated_at"] = datetime.utcnow().isoformat()

        logger.warning(f"Conflict {conflict_id} escalated: {reason}")

        return conflict

    @staticmethod
    def get_conflict_statistics(session: Session) -> Dict[str, Any]:
        """
        Get conflict resolution statistics.

        Args:
            session: Database session

        Returns:
            Conflict statistics
        """
        total_conflicts = len(ConflictResolution._conflicts)

        # Count by status
        status_counts = {}
        for conflict in ConflictResolution._conflicts.values():
            status = conflict["status"]
            status_counts[status] = status_counts.get(status, 0) + 1

        # Count by type
        type_counts = {}
        for conflict in ConflictResolution._conflicts.values():
            conflict_type = conflict["conflict_type"]
            type_counts[conflict_type] = type_counts.get(conflict_type, 0) + 1

        # Count by severity
        severity_counts = {}
        for conflict in ConflictResolution._conflicts.values():
            severity = conflict["severity"]
            severity_counts[severity] = severity_counts.get(severity, 0) + 1

        # Calculate resolution rates
        resolved_count = status_counts.get(ConflictStatus.RESOLVED, 0)
        resolution_rate = (resolved_count / total_conflicts * 100) if total_conflicts > 0 else 0

        # Calculate average resolution time
        resolution_times = []
        for conflict in ConflictResolution._conflicts.values():
            if conflict["status"] == ConflictStatus.RESOLVED and conflict["resolved_at"]:
                detected = datetime.fromisoformat(conflict["detected_at"])
                resolved = datetime.fromisoformat(conflict["resolved_at"])
                resolution_times.append((resolved - detected).total_seconds())

        avg_resolution_time = sum(resolution_times) / len(resolution_times) if resolution_times else 0

        # Strategy effectiveness
        strategy_stats = {}
        for entry in ConflictResolution._resolution_history:
            strategy = entry["strategy"]
            if strategy not in strategy_stats:
                strategy_stats[strategy] = {
                    "count": 0,
                    "total_duration": 0
                }
            strategy_stats[strategy]["count"] += 1
            strategy_stats[strategy]["total_duration"] += entry["duration_seconds"]

        # Calculate average duration per strategy
        for strategy, stats in strategy_stats.items():
            stats["avg_duration"] = stats["total_duration"] / stats["count"]

        return {
            "total_conflicts": total_conflicts,
            "by_status": status_counts,
            "by_type": type_counts,
            "by_severity": severity_counts,
            "resolution_rate_percent": resolution_rate,
            "avg_resolution_time_seconds": avg_resolution_time,
            "strategy_effectiveness": strategy_stats,
            "total_resolved": resolved_count
        }

    @staticmethod
    def suggest_resolution_strategy(
        session: Session,
        conflict_id: int
    ) -> Dict[str, Any]:
        """
        Suggest best resolution strategy for a conflict.

        Args:
            session: Database session
            conflict_id: Conflict ID

        Returns:
            Strategy suggestion
        """
        if conflict_id not in ConflictResolution._conflicts:
            raise ValueError(f"Conflict {conflict_id} not found")

        conflict = ConflictResolution._conflicts[conflict_id]
        conflict_type = conflict["conflict_type"]
        severity = conflict["severity"]
        agent_count = len(conflict["involved_agents"])

        # Strategy selection logic
        if severity == ConflictSeverity.CRITICAL:
            suggested_strategy = ResolutionStrategy.MANUAL
            reasoning = "Critical severity requires manual intervention"

        elif conflict_type == ConflictType.RESOURCE:
            suggested_strategy = ResolutionStrategy.PRIORITY_BASED
            reasoning = "Resource conflicts best resolved by priority"

        elif conflict_type == ConflictType.DECISION and agent_count <= 5:
            suggested_strategy = ResolutionStrategy.VOTING
            reasoning = "Decision conflicts benefit from voting with small groups"

        elif conflict_type == ConflictType.ASSIGNMENT:
            suggested_strategy = ResolutionStrategy.ROUND_ROBIN
            reasoning = "Task assignment conflicts benefit from fair distribution"

        elif agent_count > 10:
            suggested_strategy = ResolutionStrategy.ARBITRATION
            reasoning = "Large groups benefit from arbitration"

        else:
            suggested_strategy = ResolutionStrategy.AUTOMATIC
            reasoning = "Standard conflict suitable for automatic resolution"

        return {
            "conflict_id": conflict_id,
            "suggested_strategy": suggested_strategy,
            "reasoning": reasoning,
            "alternative_strategies": [
                ResolutionStrategy.PRIORITY_BASED,
                ResolutionStrategy.VOTING,
                ResolutionStrategy.FCFS
            ]
        }

    @staticmethod
    def batch_resolve_conflicts(
        session: Session,
        conflict_ids: List[int],
        strategy: str = ResolutionStrategy.AUTOMATIC
    ) -> Dict[str, Any]:
        """
        Resolve multiple conflicts in batch.

        Args:
            session: Database session
            conflict_ids: List of conflict IDs
            strategy: Resolution strategy to use

        Returns:
            Batch resolution results
        """
        results = {
            "total": len(conflict_ids),
            "successful": 0,
            "failed": 0,
            "results": []
        }

        for conflict_id in conflict_ids:
            try:
                result = ConflictResolution.resolve_conflict(
                    session=session,
                    conflict_id=conflict_id,
                    strategy=strategy
                )
                results["successful"] += 1
                results["results"].append({
                    "conflict_id": conflict_id,
                    "status": "success",
                    "outcome": result
                })
            except Exception as e:
                results["failed"] += 1
                results["results"].append({
                    "conflict_id": conflict_id,
                    "status": "failed",
                    "error": str(e)
                })

        logger.info(
            f"Batch resolved {results['successful']}/{results['total']} conflicts"
        )

        return results

    @staticmethod
    def preview_resolution(
        session: Session,
        conflict_id: int,
        strategy: str
    ) -> Dict[str, Any]:
        """
        Preview resolution outcome without applying it.

        Args:
            session: Database session
            conflict_id: Conflict ID
            strategy: Resolution strategy to preview

        Returns:
            Preview of resolution outcome
        """
        if conflict_id not in ConflictResolution._conflicts:
            raise ValueError(f"Conflict {conflict_id} not found")

        conflict = ConflictResolution._conflicts[conflict_id].copy()

        # Simulate resolution without changing actual conflict
        if strategy == ResolutionStrategy.PRIORITY_BASED:
            outcome = ConflictResolution._resolve_by_priority(session, conflict)
        elif strategy == ResolutionStrategy.VOTING:
            outcome = ConflictResolution._resolve_by_voting(session, conflict)
        elif strategy == ResolutionStrategy.FCFS:
            outcome = ConflictResolution._resolve_fcfs(session, conflict)
        elif strategy == ResolutionStrategy.ROUND_ROBIN:
            outcome = ConflictResolution._resolve_round_robin(session, conflict)
        else:
            outcome = ConflictResolution._resolve_automatically(session, conflict)

        return {
            "conflict_id": conflict_id,
            "strategy": strategy,
            "preview_outcome": outcome,
            "note": "This is a preview. Use resolve_conflict to apply."
        }
