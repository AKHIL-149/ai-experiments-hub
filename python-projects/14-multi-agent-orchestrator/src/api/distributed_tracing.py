"""
Distributed Tracing and Observability API

REST API endpoints for distributed tracing, span management, and observability.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.distributed_tracing import (
    DistributedTracing,
    SpanKind,
    SpanStatus,
    TraceState
)


router = APIRouter()


# Request/Response Models
class StartTraceRequest(BaseModel):
    trace_name: str = Field(..., description="Trace name")
    service_name: str = Field(..., description="Service initiating the trace")
    operation_name: str = Field(..., description="Operation being traced")
    attributes: Optional[dict] = Field(None, description="Optional trace attributes")
    trace_context: Optional[dict] = Field(None, description="Optional parent trace context")


class StartSpanRequest(BaseModel):
    span_name: str = Field(..., description="Span name")
    service_name: str = Field(..., description="Service executing the span")
    span_kind: str = Field(SpanKind.INTERNAL, description="Type of span")
    parent_span_id: Optional[str] = Field(None, description="Optional parent span")
    attributes: Optional[dict] = Field(None, description="Optional span attributes")


class EndSpanRequest(BaseModel):
    status: str = Field(SpanStatus.OK, description="Span status")
    error: Optional[str] = Field(None, description="Optional error message")
    stack_trace: Optional[str] = Field(None, description="Optional stack trace")


class AddSpanEventRequest(BaseModel):
    event_name: str = Field(..., description="Event name")
    attributes: Optional[dict] = Field(None, description="Optional event attributes")


class AddSpanLinkRequest(BaseModel):
    linked_trace_id: str = Field(..., description="Linked trace ID")
    linked_span_id: str = Field(..., description="Linked span ID")
    relationship: str = Field(..., description="Relationship type")
    attributes: Optional[dict] = Field(None, description="Optional link attributes")


@router.post("/traces")
def start_trace(
    request: StartTraceRequest,
    session: Session = Depends(get_db_session)
):
    """
    Start a new distributed trace.

    Initiates a new trace for tracking a request across multiple services.
    """
    try:
        trace = DistributedTracing.start_trace(
            session=session,
            trace_name=request.trace_name,
            service_name=request.service_name,
            operation_name=request.operation_name,
            attributes=request.attributes,
            trace_context=request.trace_context
        )

        return {
            "success": True,
            "trace": trace,
            "message": f"Trace started: {trace['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/traces/{trace_id}/spans")
def start_span(
    trace_id: str,
    request: StartSpanRequest,
    session: Session = Depends(get_db_session)
):
    """
    Start a span within a trace.

    Creates a new span representing an operation within the trace.
    """
    try:
        span = DistributedTracing.start_span(
            session=session,
            trace_id=trace_id,
            span_name=request.span_name,
            service_name=request.service_name,
            span_kind=request.span_kind,
            parent_span_id=request.parent_span_id,
            attributes=request.attributes
        )

        return {
            "success": True,
            "span": span,
            "message": f"Span started: {span['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spans/{span_id}/end")
def end_span(
    span_id: str,
    request: EndSpanRequest,
    session: Session = Depends(get_db_session)
):
    """
    End a span.

    Marks a span as completed with status and optional error information.
    """
    try:
        span = DistributedTracing.end_span(
            session=session,
            span_id=span_id,
            status=request.status,
            error=request.error,
            stack_trace=request.stack_trace
        )

        return {
            "success": True,
            "span": span,
            "message": f"Span ended: {span_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spans/{span_id}/events")
def add_span_event(
    span_id: str,
    request: AddSpanEventRequest,
    session: Session = Depends(get_db_session)
):
    """
    Add an event to a span.

    Records a timestamped event within a span for detailed tracking.
    """
    try:
        event = DistributedTracing.add_span_event(
            session=session,
            span_id=span_id,
            event_name=request.event_name,
            attributes=request.attributes
        )

        return {
            "success": True,
            "event": event,
            "message": "Event added to span"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/spans/{span_id}/links")
def add_span_link(
    span_id: str,
    request: AddSpanLinkRequest,
    session: Session = Depends(get_db_session)
):
    """
    Add a link to another span.

    Creates a relationship between spans for tracking correlations.
    """
    try:
        link = DistributedTracing.add_span_link(
            session=session,
            span_id=span_id,
            linked_trace_id=request.linked_trace_id,
            linked_span_id=request.linked_span_id,
            relationship=request.relationship,
            attributes=request.attributes
        )

        return {
            "success": True,
            "link": link,
            "message": "Link added to span"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/traces/{trace_id}")
def get_trace(
    trace_id: str,
    include_spans: bool = True,
    session: Session = Depends(get_db_session)
):
    """
    Get trace details.

    Returns detailed information about a trace including all spans
    and the span hierarchy.
    """
    try:
        trace = DistributedTracing.get_trace(
            session=session,
            trace_id=trace_id,
            include_spans=include_spans
        )

        return {
            "success": True,
            "trace": trace
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/traces/{trace_id}/timeline")
def get_trace_timeline(
    trace_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get trace timeline.

    Returns a chronological timeline of all spans in the trace
    for visualization.
    """
    try:
        timeline = DistributedTracing.get_trace_timeline(
            session=session,
            trace_id=trace_id
        )

        return {
            "success": True,
            "timeline": timeline
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/service-map")
def get_service_map(
    session: Session = Depends(get_db_session)
):
    """
    Get service dependency map.

    Returns the service dependency graph showing how services
    call each other.
    """
    try:
        service_map = DistributedTracing.get_service_map(session=session)

        return {
            "success": True,
            "service_map": service_map
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/traces")
def search_traces(
    service_name: Optional[str] = None,
    operation_name: Optional[str] = None,
    state: Optional[str] = None,
    min_duration_ms: Optional[int] = None,
    has_errors: Optional[bool] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    Search traces with filters.

    Returns traces matching the specified filters for analysis
    and debugging.
    """
    try:
        result = DistributedTracing.search_traces(
            session=session,
            service_name=service_name,
            operation_name=operation_name,
            state=state,
            min_duration_ms=min_duration_ms,
            has_errors=has_errors,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get distributed tracing statistics.

    Returns aggregate metrics including trace counts, error rates,
    and performance statistics.
    """
    try:
        stats = DistributedTracing.get_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/span-kinds")
def list_span_kinds():
    """
    List all span kinds.

    Returns all available span kind options.
    """
    return {
        "success": True,
        "span_kinds": [
            {"kind": SpanKind.INTERNAL, "description": "Internal operation"},
            {"kind": SpanKind.SERVER, "description": "Server-side operation"},
            {"kind": SpanKind.CLIENT, "description": "Client-side operation"},
            {"kind": SpanKind.PRODUCER, "description": "Message producer"},
            {"kind": SpanKind.CONSUMER, "description": "Message consumer"}
        ]
    }


@router.get("/span-statuses")
def list_span_statuses():
    """
    List all span statuses.

    Returns all possible span status values.
    """
    return {
        "success": True,
        "span_statuses": [
            {"status": SpanStatus.UNSET, "description": "Status not set"},
            {"status": SpanStatus.OK, "description": "Operation successful"},
            {"status": SpanStatus.ERROR, "description": "Operation failed"}
        ]
    }


@router.get("/trace-states")
def list_trace_states():
    """
    List all trace states.

    Returns all possible trace state values.
    """
    return {
        "success": True,
        "trace_states": [
            {"state": TraceState.ACTIVE, "description": "Trace is active"},
            {"state": TraceState.COMPLETED, "description": "Trace completed successfully"},
            {"state": TraceState.FAILED, "description": "Trace failed"}
        ]
    }
