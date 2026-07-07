"""
Agent Event System Service

Tracks and manages agent-related events for monitoring, auditing, and real-time updates.
"""

from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
from collections import defaultdict
import json

from src.models.database import Agent, AgentExecution, Task
from src.core.logging import logger


class EventType:
    """Event type constants"""
    # Agent lifecycle events
    AGENT_CREATED = "agent.created"
    AGENT_UPDATED = "agent.updated"
    AGENT_ACTIVATED = "agent.activated"
    AGENT_DEACTIVATED = "agent.deactivated"
    AGENT_DELETED = "agent.deleted"

    # Task events
    TASK_ASSIGNED = "task.assigned"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    TASK_CANCELLED = "task.cancelled"

    # Execution events
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"
    EXECUTION_TIMEOUT = "execution.timeout"

    # Health events
    HEALTH_DEGRADED = "health.degraded"
    HEALTH_UNHEALTHY = "health.unhealthy"
    HEALTH_RECOVERED = "health.recovered"
    HEARTBEAT_MISSED = "heartbeat.missed"

    # Resource events
    RESOURCE_ALLOCATED = "resource.allocated"
    RESOURCE_RELEASED = "resource.released"
    RESOURCE_EXHAUSTED = "resource.exhausted"
    RESOURCE_WARNING = "resource.warning"

    # Collaboration events
    COLLABORATION_STARTED = "collaboration.started"
    COLLABORATION_ENDED = "collaboration.ended"
    HANDOFF_INITIATED = "handoff.initiated"
    HANDOFF_COMPLETED = "handoff.completed"

    # Load balancing events
    TASK_REBALANCED = "task.rebalanced"
    AGENT_OVERLOADED = "agent.overloaded"
    AGENT_UNDERUTILIZED = "agent.underutilized"

    # Error events
    ERROR_OCCURRED = "error.occurred"
    ANOMALY_DETECTED = "anomaly.detected"
    SLA_BREACH = "sla.breach"
    PRIORITY_ESCALATED = "priority.escalated"


class EventSeverity:
    """Event severity levels"""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AgentEventSystem:
    """Service for managing agent events"""

    # In-memory event listeners
    _listeners: Dict[str, List[Callable]] = defaultdict(list)

    @staticmethod
    def emit_event(
        session: Session,
        event_type: str,
        agent_id: Optional[int] = None,
        task_id: Optional[int] = None,
        execution_id: Optional[int] = None,
        severity: str = EventSeverity.INFO,
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Emit an event and notify listeners.

        Args:
            session: Database session
            event_type: Type of event
            agent_id: Optional agent ID
            task_id: Optional task ID
            execution_id: Optional execution ID
            severity: Event severity level
            message: Event message
            metadata: Additional event metadata

        Returns:
            Event data dictionary
        """
        event_data = {
            "event_type": event_type,
            "agent_id": agent_id,
            "task_id": task_id,
            "execution_id": execution_id,
            "severity": severity,
            "message": message,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        # Store event in agent's metadata for persistence
        if agent_id:
            agent = session.query(Agent).filter(Agent.id == agent_id).first()
            if agent:
                if not agent.metadata:
                    agent.metadata = {}

                if "events" not in agent.metadata:
                    agent.metadata["events"] = []

                # Keep last 100 events per agent to avoid unbounded growth
                agent.metadata["events"].append(event_data)
                if len(agent.metadata["events"]) > 100:
                    agent.metadata["events"] = agent.metadata["events"][-100:]

                # Mark as modified for SQLAlchemy
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(agent, "metadata")
                session.commit()

        # Notify listeners
        AgentEventSystem._notify_listeners(event_type, event_data)

        logger.debug(f"Event emitted: {event_type} - {message}")

        return event_data

    @staticmethod
    def _notify_listeners(event_type: str, event_data: Dict[str, Any]) -> None:
        """Notify all registered listeners for an event type"""
        # Notify specific event type listeners
        for listener in AgentEventSystem._listeners.get(event_type, []):
            try:
                listener(event_data)
            except Exception as e:
                logger.error(f"Error in event listener for {event_type}: {e}")

        # Notify wildcard listeners (listening to all events)
        for listener in AgentEventSystem._listeners.get("*", []):
            try:
                listener(event_data)
            except Exception as e:
                logger.error(f"Error in wildcard event listener: {e}")

    @staticmethod
    def register_listener(
        event_type: str,
        callback: Callable[[Dict[str, Any]], None]
    ) -> None:
        """
        Register a listener for an event type.

        Args:
            event_type: Event type to listen to (use "*" for all events)
            callback: Callback function that receives event data
        """
        AgentEventSystem._listeners[event_type].append(callback)
        logger.info(f"Registered listener for event type: {event_type}")

    @staticmethod
    def unregister_listener(
        event_type: str,
        callback: Callable[[Dict[str, Any]], None]
    ) -> bool:
        """
        Unregister a listener.

        Args:
            event_type: Event type
            callback: Callback function to remove

        Returns:
            True if listener was found and removed
        """
        if event_type in AgentEventSystem._listeners:
            try:
                AgentEventSystem._listeners[event_type].remove(callback)
                logger.info(f"Unregistered listener for event type: {event_type}")
                return True
            except ValueError:
                return False
        return False

    @staticmethod
    def get_agent_events(
        session: Session,
        agent_id: int,
        event_types: Optional[List[str]] = None,
        severities: Optional[List[str]] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get events for a specific agent.

        Args:
            session: Database session
            agent_id: Agent ID
            event_types: Optional filter by event types
            severities: Optional filter by severities
            start_time: Optional filter by start time
            end_time: Optional filter by end time
            limit: Maximum number of events to return

        Returns:
            Dictionary with events and statistics
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        events = agent.metadata.get("events", []) if agent.metadata else []

        # Apply filters
        filtered_events = []
        for event in events:
            # Filter by event type
            if event_types and event["event_type"] not in event_types:
                continue

            # Filter by severity
            if severities and event["severity"] not in severities:
                continue

            # Filter by time
            event_time = datetime.fromisoformat(event["timestamp"])
            if start_time and event_time < start_time:
                continue
            if end_time and event_time > end_time:
                continue

            filtered_events.append(event)

        # Sort by timestamp (most recent first)
        filtered_events.sort(key=lambda x: x["timestamp"], reverse=True)

        # Apply limit
        filtered_events = filtered_events[:limit]

        # Calculate statistics
        stats = {
            "total_events": len(events),
            "filtered_events": len(filtered_events),
            "events_by_type": {},
            "events_by_severity": {}
        }

        for event in filtered_events:
            event_type = event["event_type"]
            severity = event["severity"]

            stats["events_by_type"][event_type] = stats["events_by_type"].get(event_type, 0) + 1
            stats["events_by_severity"][severity] = stats["events_by_severity"].get(severity, 0) + 1

        return {
            "agent_id": agent_id,
            "events": filtered_events,
            "statistics": stats
        }

    @staticmethod
    def get_recent_events(
        session: Session,
        minutes: int = 60,
        event_types: Optional[List[str]] = None,
        severities: Optional[List[str]] = None,
        agent_ids: Optional[List[int]] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get recent events across all agents.

        Args:
            session: Database session
            minutes: Number of minutes to look back
            event_types: Optional filter by event types
            severities: Optional filter by severities
            agent_ids: Optional filter by agent IDs
            limit: Maximum number of events to return

        Returns:
            Dictionary with events and statistics
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes)

        # Query all agents
        query = session.query(Agent)
        if agent_ids:
            query = query.filter(Agent.id.in_(agent_ids))

        agents = query.all()

        all_events = []
        for agent in agents:
            events = agent.metadata.get("events", []) if agent.metadata else []

            for event in events:
                # Filter by time
                event_time = datetime.fromisoformat(event["timestamp"])
                if event_time < cutoff_time:
                    continue

                # Filter by event type
                if event_types and event["event_type"] not in event_types:
                    continue

                # Filter by severity
                if severities and event["severity"] not in severities:
                    continue

                all_events.append(event)

        # Sort by timestamp (most recent first)
        all_events.sort(key=lambda x: x["timestamp"], reverse=True)

        # Apply limit
        all_events = all_events[:limit]

        # Calculate statistics
        stats = {
            "total_events": len(all_events),
            "time_window_minutes": minutes,
            "events_by_type": {},
            "events_by_severity": {},
            "events_by_agent": {}
        }

        for event in all_events:
            event_type = event["event_type"]
            severity = event["severity"]
            agent_id = event.get("agent_id")

            stats["events_by_type"][event_type] = stats["events_by_type"].get(event_type, 0) + 1
            stats["events_by_severity"][severity] = stats["events_by_severity"].get(severity, 0) + 1
            if agent_id:
                stats["events_by_agent"][agent_id] = stats["events_by_agent"].get(agent_id, 0) + 1

        return {
            "events": all_events,
            "statistics": stats
        }

    @staticmethod
    def get_event_timeline(
        session: Session,
        agent_id: Optional[int] = None,
        hours: int = 24,
        granularity_minutes: int = 60
    ) -> Dict[str, Any]:
        """
        Get event timeline with aggregation.

        Args:
            session: Database session
            agent_id: Optional agent ID (None for all agents)
            hours: Number of hours to look back
            granularity_minutes: Time bucket size in minutes

        Returns:
            Dictionary with timeline data
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        # Get events
        if agent_id:
            agent = session.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                raise ValueError(f"Agent {agent_id} not found")

            events = agent.metadata.get("events", []) if agent.metadata else []
        else:
            events = []
            agents = session.query(Agent).all()
            for agent in agents:
                agent_events = agent.metadata.get("events", []) if agent.metadata else []
                events.extend(agent_events)

        # Filter by time
        filtered_events = [
            event for event in events
            if datetime.fromisoformat(event["timestamp"]) >= cutoff_time
        ]

        # Create time buckets
        num_buckets = (hours * 60) // granularity_minutes
        buckets = []

        for i in range(num_buckets):
            bucket_start = datetime.utcnow() - timedelta(minutes=granularity_minutes * (num_buckets - i))
            bucket_end = bucket_start + timedelta(minutes=granularity_minutes)

            bucket_events = [
                event for event in filtered_events
                if bucket_start <= datetime.fromisoformat(event["timestamp"]) < bucket_end
            ]

            buckets.append({
                "start_time": bucket_start.isoformat(),
                "end_time": bucket_end.isoformat(),
                "event_count": len(bucket_events),
                "events_by_severity": {
                    EventSeverity.DEBUG: sum(1 for e in bucket_events if e["severity"] == EventSeverity.DEBUG),
                    EventSeverity.INFO: sum(1 for e in bucket_events if e["severity"] == EventSeverity.INFO),
                    EventSeverity.WARNING: sum(1 for e in bucket_events if e["severity"] == EventSeverity.WARNING),
                    EventSeverity.ERROR: sum(1 for e in bucket_events if e["severity"] == EventSeverity.ERROR),
                    EventSeverity.CRITICAL: sum(1 for e in bucket_events if e["severity"] == EventSeverity.CRITICAL)
                }
            })

        return {
            "agent_id": agent_id,
            "hours": hours,
            "granularity_minutes": granularity_minutes,
            "total_events": len(filtered_events),
            "timeline": buckets
        }

    @staticmethod
    def clear_agent_events(
        session: Session,
        agent_id: int,
        older_than_hours: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Clear events for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            older_than_hours: Optional - only clear events older than this

        Returns:
            Dictionary with deletion statistics
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if not agent.metadata or "events" not in agent.metadata:
            return {
                "agent_id": agent_id,
                "events_cleared": 0,
                "events_remaining": 0
            }

        events = agent.metadata["events"]
        original_count = len(events)

        if older_than_hours is not None:
            cutoff_time = datetime.utcnow() - timedelta(hours=older_than_hours)
            agent.metadata["events"] = [
                event for event in events
                if datetime.fromisoformat(event["timestamp"]) >= cutoff_time
            ]
        else:
            agent.metadata["events"] = []

        # Mark as modified for SQLAlchemy
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(agent, "metadata")
        session.commit()

        events_cleared = original_count - len(agent.metadata["events"])

        return {
            "agent_id": agent_id,
            "events_cleared": events_cleared,
            "events_remaining": len(agent.metadata["events"])
        }

    @staticmethod
    def get_critical_events(
        session: Session,
        hours: int = 24,
        agent_ids: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Get all critical/error events.

        Args:
            session: Database session
            hours: Number of hours to look back
            agent_ids: Optional filter by agent IDs

        Returns:
            Dictionary with critical events
        """
        return AgentEventSystem.get_recent_events(
            session=session,
            minutes=hours * 60,
            severities=[EventSeverity.ERROR, EventSeverity.CRITICAL],
            agent_ids=agent_ids,
            limit=1000
        )

    @staticmethod
    def list_event_types() -> Dict[str, Any]:
        """
        List all available event types.

        Returns:
            Dictionary with event types categorized
        """
        return {
            "lifecycle": [
                EventType.AGENT_CREATED,
                EventType.AGENT_UPDATED,
                EventType.AGENT_ACTIVATED,
                EventType.AGENT_DEACTIVATED,
                EventType.AGENT_DELETED
            ],
            "task": [
                EventType.TASK_ASSIGNED,
                EventType.TASK_STARTED,
                EventType.TASK_COMPLETED,
                EventType.TASK_FAILED,
                EventType.TASK_CANCELLED
            ],
            "execution": [
                EventType.EXECUTION_STARTED,
                EventType.EXECUTION_COMPLETED,
                EventType.EXECUTION_FAILED,
                EventType.EXECUTION_TIMEOUT
            ],
            "health": [
                EventType.HEALTH_DEGRADED,
                EventType.HEALTH_UNHEALTHY,
                EventType.HEALTH_RECOVERED,
                EventType.HEARTBEAT_MISSED
            ],
            "resource": [
                EventType.RESOURCE_ALLOCATED,
                EventType.RESOURCE_RELEASED,
                EventType.RESOURCE_EXHAUSTED,
                EventType.RESOURCE_WARNING
            ],
            "collaboration": [
                EventType.COLLABORATION_STARTED,
                EventType.COLLABORATION_ENDED,
                EventType.HANDOFF_INITIATED,
                EventType.HANDOFF_COMPLETED
            ],
            "load_balancing": [
                EventType.TASK_REBALANCED,
                EventType.AGENT_OVERLOADED,
                EventType.AGENT_UNDERUTILIZED
            ],
            "error": [
                EventType.ERROR_OCCURRED,
                EventType.ANOMALY_DETECTED,
                EventType.SLA_BREACH,
                EventType.PRIORITY_ESCALATED
            ]
        }
