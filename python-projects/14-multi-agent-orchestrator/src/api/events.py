"""
Agent Event System API endpoints
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from datetime import datetime

from src.core.database import get_db_session
from src.services.agent_event_system import AgentEventSystem, EventSeverity
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class EmitEventRequest(BaseModel):
    """Request model for emitting an event"""
    event_type: str = Field(..., description="Event type")
    agent_id: Optional[int] = Field(None, description="Agent ID")
    task_id: Optional[int] = Field(None, description="Task ID")
    execution_id: Optional[int] = Field(None, description="Execution ID")
    severity: str = Field(EventSeverity.INFO, description="Event severity")
    message: str = Field(..., description="Event message")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class ClearEventsRequest(BaseModel):
    """Request model for clearing events"""
    agent_id: int = Field(..., description="Agent ID")
    older_than_hours: Optional[int] = Field(None, description="Clear events older than this many hours")


# Endpoints

@router.post("/emit")
async def emit_event(
    request: EmitEventRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Emit an event.

    Manually emit an event for testing or custom integrations.
    The event will be stored and listeners will be notified.
    """
    try:
        event = AgentEventSystem.emit_event(
            session=db,
            event_type=request.event_type,
            agent_id=request.agent_id,
            task_id=request.task_id,
            execution_id=request.execution_id,
            severity=request.severity,
            message=request.message,
            metadata=request.metadata
        )

        return {
            "success": True,
            "event": event,
            "message": "Event emitted successfully"
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to emit event: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/agent/{agent_id}")
async def get_agent_events(
    agent_id: int,
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    severities: Optional[str] = Query(None, description="Comma-separated severities"),
    start_time: Optional[datetime] = Query(None, description="Start time filter"),
    end_time: Optional[datetime] = Query(None, description="End time filter"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum events to return"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get events for a specific agent.

    Returns events with optional filtering by:
    - Event types
    - Severities
    - Time range
    - Limit

    Also includes event statistics.
    """
    try:
        # Parse comma-separated filters
        event_types_list = event_types.split(",") if event_types else None
        severities_list = severities.split(",") if severities else None

        result = AgentEventSystem.get_agent_events(
            session=db,
            agent_id=agent_id,
            event_types=event_types_list,
            severities=severities_list,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )

        return {
            "success": True,
            **result,
            "message": f"Retrieved {len(result['events'])} events for agent {agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get agent events: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/recent")
async def get_recent_events(
    minutes: int = Query(60, ge=1, le=1440, description="Minutes to look back"),
    event_types: Optional[str] = Query(None, description="Comma-separated event types"),
    severities: Optional[str] = Query(None, description="Comma-separated severities"),
    agent_ids: Optional[str] = Query(None, description="Comma-separated agent IDs"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum events to return"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get recent events across all agents.

    Returns recent events with optional filtering by:
    - Time window (minutes)
    - Event types
    - Severities
    - Agent IDs

    Useful for monitoring recent activity across the system.
    """
    try:
        # Parse comma-separated filters
        event_types_list = event_types.split(",") if event_types else None
        severities_list = severities.split(",") if severities else None
        agent_ids_list = [int(id) for id in agent_ids.split(",")] if agent_ids else None

        result = AgentEventSystem.get_recent_events(
            session=db,
            minutes=minutes,
            event_types=event_types_list,
            severities=severities_list,
            agent_ids=agent_ids_list,
            limit=limit
        )

        return {
            "success": True,
            **result,
            "message": f"Retrieved {len(result['events'])} recent events"
        }

    except Exception as e:
        logger.error(f"Failed to get recent events: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/timeline")
async def get_event_timeline(
    agent_id: Optional[int] = Query(None, description="Agent ID (None for all agents)"),
    hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
    granularity_minutes: int = Query(60, ge=5, le=1440, description="Time bucket size"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get event timeline with aggregation.

    Returns events aggregated into time buckets with statistics.

    Useful for:
    - Visualizing event trends over time
    - Identifying peak activity periods
    - Monitoring event patterns
    """
    try:
        result = AgentEventSystem.get_event_timeline(
            session=db,
            agent_id=agent_id,
            hours=hours,
            granularity_minutes=granularity_minutes
        )

        return {
            "success": True,
            **result,
            "message": f"Event timeline for last {hours} hours"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get event timeline: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/critical")
async def get_critical_events(
    hours: int = Query(24, ge=1, le=168, description="Hours to look back"),
    agent_ids: Optional[str] = Query(None, description="Comma-separated agent IDs"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get all critical and error events.

    Returns events with ERROR or CRITICAL severity.

    Useful for:
    - Quick identification of problems
    - Alerting and monitoring
    - Incident response
    """
    try:
        agent_ids_list = [int(id) for id in agent_ids.split(",")] if agent_ids else None

        result = AgentEventSystem.get_critical_events(
            session=db,
            hours=hours,
            agent_ids=agent_ids_list
        )

        return {
            "success": True,
            **result,
            "message": f"Retrieved {len(result['events'])} critical events"
        }

    except Exception as e:
        logger.error(f"Failed to get critical events: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/clear")
async def clear_agent_events(
    request: ClearEventsRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Clear events for an agent.

    Optionally clear only events older than a specified number of hours.

    Use with caution - this permanently deletes event data.
    """
    try:
        result = AgentEventSystem.clear_agent_events(
            session=db,
            agent_id=request.agent_id,
            older_than_hours=request.older_than_hours
        )

        return {
            "success": True,
            **result,
            "message": f"Cleared {result['events_cleared']} events for agent {request.agent_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to clear events: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/types")
async def list_event_types() -> Dict[str, Any]:
    """
    List all available event types.

    Returns event types organized by category:
    - Lifecycle events
    - Task events
    - Execution events
    - Health events
    - Resource events
    - Collaboration events
    - Load balancing events
    - Error events

    Useful for building event filters and understanding the event system.
    """
    try:
        types = AgentEventSystem.list_event_types()

        # Count total event types
        total_types = sum(len(events) for events in types.values())

        return {
            "success": True,
            "total_types": total_types,
            "types": types,
            "message": "List of all event types"
        }

    except Exception as e:
        logger.error(f"Failed to list event types: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/severities")
async def list_event_severities() -> Dict[str, Any]:
    """
    List all event severity levels.

    Returns:
    - Available severity levels
    - Descriptions
    - Usage recommendations
    """
    severities = [
        {
            "severity": EventSeverity.DEBUG,
            "description": "Detailed information for debugging",
            "color": "blue"
        },
        {
            "severity": EventSeverity.INFO,
            "description": "General informational events",
            "color": "green"
        },
        {
            "severity": EventSeverity.WARNING,
            "description": "Warning events that may need attention",
            "color": "yellow"
        },
        {
            "severity": EventSeverity.ERROR,
            "description": "Error events indicating failures",
            "color": "orange"
        },
        {
            "severity": EventSeverity.CRITICAL,
            "description": "Critical events requiring immediate attention",
            "color": "red"
        }
    ]

    return {
        "success": True,
        "total_severities": len(severities),
        "severities": severities,
        "message": "List of all event severities"
    }
