"""
Distributed Tracing and Observability

Provides distributed tracing, span management, and request correlation across agents.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import uuid
import time


class SpanKind:
    """Span kinds"""
    INTERNAL = "internal"
    SERVER = "server"
    CLIENT = "client"
    PRODUCER = "producer"
    CONSUMER = "consumer"


class SpanStatus:
    """Span status"""
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"


class TraceState:
    """Trace state"""
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class DistributedTracing:
    """Distributed Tracing and Observability service"""

    # In-memory storage
    _traces = {}
    _spans = {}
    _trace_spans = defaultdict(list)
    _span_events = defaultdict(list)
    _span_links = defaultdict(list)
    _service_map = defaultdict(set)
    _trace_metrics = defaultdict(lambda: {
        "total_spans": 0,
        "error_spans": 0,
        "total_duration_ms": 0,
        "service_calls": defaultdict(int)
    })

    @staticmethod
    def start_trace(
        session,
        trace_name: str,
        service_name: str,
        operation_name: str,
        attributes: Optional[dict] = None,
        trace_context: Optional[dict] = None
    ) -> dict:
        """
        Start a new distributed trace.

        Args:
            session: Database session
            trace_name: Trace name
            service_name: Service initiating the trace
            operation_name: Operation being traced
            attributes: Optional trace attributes
            trace_context: Optional parent trace context

        Returns:
            Created trace
        """
        trace_id = trace_context.get("trace_id") if trace_context else f"trace_{uuid.uuid4().hex}"
        now = datetime.utcnow()

        trace = {
            "id": trace_id,
            "name": trace_name,
            "service_name": service_name,
            "operation_name": operation_name,
            "state": TraceState.ACTIVE,
            "started_at": now.isoformat(),
            "ended_at": None,
            "duration_ms": None,
            "root_span_id": None,
            "span_count": 0,
            "error_count": 0,
            "attributes": attributes or {},
            "services_involved": [service_name],
            "parent_trace_id": trace_context.get("parent_trace_id") if trace_context else None
        }

        DistributedTracing._traces[trace_id] = trace
        return trace

    @staticmethod
    def start_span(
        session,
        trace_id: str,
        span_name: str,
        service_name: str,
        span_kind: str = SpanKind.INTERNAL,
        parent_span_id: Optional[str] = None,
        attributes: Optional[dict] = None
    ) -> dict:
        """
        Start a span within a trace.

        Args:
            session: Database session
            trace_id: Trace ID
            span_name: Span name
            service_name: Service executing the span
            span_kind: Type of span
            parent_span_id: Optional parent span
            attributes: Optional span attributes

        Returns:
            Created span
        """
        trace = DistributedTracing._traces.get(trace_id)
        if not trace:
            raise ValueError(f"Trace not found: {trace_id}")

        span_id = f"span_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        span = {
            "id": span_id,
            "trace_id": trace_id,
            "parent_span_id": parent_span_id,
            "name": span_name,
            "service_name": service_name,
            "span_kind": span_kind,
            "status": SpanStatus.UNSET,
            "started_at": now.isoformat(),
            "ended_at": None,
            "duration_ms": None,
            "attributes": attributes or {},
            "events": [],
            "links": [],
            "error": None,
            "stack_trace": None
        }

        DistributedTracing._spans[span_id] = span
        DistributedTracing._trace_spans[trace_id].append(span_id)

        # Update trace
        trace["span_count"] += 1
        if not trace["root_span_id"] and not parent_span_id:
            trace["root_span_id"] = span_id
        if service_name not in trace["services_involved"]:
            trace["services_involved"].append(service_name)

        # Update service map
        if parent_span_id:
            parent_span = DistributedTracing._spans.get(parent_span_id)
            if parent_span:
                DistributedTracing._service_map[parent_span["service_name"]].add(service_name)

        # Update metrics
        DistributedTracing._trace_metrics[trace_id]["total_spans"] += 1
        DistributedTracing._trace_metrics[trace_id]["service_calls"][service_name] += 1

        return span

    @staticmethod
    def end_span(
        session,
        span_id: str,
        status: str = SpanStatus.OK,
        error: Optional[str] = None,
        stack_trace: Optional[str] = None
    ) -> dict:
        """
        End a span.

        Args:
            session: Database session
            span_id: Span ID
            status: Span status
            error: Optional error message
            stack_trace: Optional stack trace

        Returns:
            Ended span
        """
        span = DistributedTracing._spans.get(span_id)
        if not span:
            raise ValueError(f"Span not found: {span_id}")

        now = datetime.utcnow()
        started_at = datetime.fromisoformat(span["started_at"])
        duration_ms = (now - started_at).total_seconds() * 1000

        span["ended_at"] = now.isoformat()
        span["duration_ms"] = duration_ms
        span["status"] = status
        span["error"] = error
        span["stack_trace"] = stack_trace

        # Update trace
        trace_id = span["trace_id"]
        trace = DistributedTracing._traces.get(trace_id)
        if trace:
            if status == SpanStatus.ERROR:
                trace["error_count"] += 1
                DistributedTracing._trace_metrics[trace_id]["error_spans"] += 1

            DistributedTracing._trace_metrics[trace_id]["total_duration_ms"] += duration_ms

            # Check if all spans are complete
            all_complete = all(
                DistributedTracing._spans[sid].get("ended_at") is not None
                for sid in DistributedTracing._trace_spans[trace_id]
            )

            if all_complete:
                DistributedTracing._end_trace(trace_id)

        return span

    @staticmethod
    def add_span_event(
        session,
        span_id: str,
        event_name: str,
        attributes: Optional[dict] = None
    ) -> dict:
        """
        Add an event to a span.

        Args:
            session: Database session
            span_id: Span ID
            event_name: Event name
            attributes: Optional event attributes

        Returns:
            Created event
        """
        span = DistributedTracing._spans.get(span_id)
        if not span:
            raise ValueError(f"Span not found: {span_id}")

        event_id = f"event_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        event = {
            "id": event_id,
            "span_id": span_id,
            "name": event_name,
            "timestamp": now.isoformat(),
            "attributes": attributes or {}
        }

        DistributedTracing._span_events[span_id].append(event)
        span["events"].append(event)

        return event

    @staticmethod
    def add_span_link(
        session,
        span_id: str,
        linked_trace_id: str,
        linked_span_id: str,
        relationship: str,
        attributes: Optional[dict] = None
    ) -> dict:
        """
        Add a link to another span.

        Args:
            session: Database session
            span_id: Current span ID
            linked_trace_id: Linked trace ID
            linked_span_id: Linked span ID
            relationship: Relationship type
            attributes: Optional link attributes

        Returns:
            Created link
        """
        span = DistributedTracing._spans.get(span_id)
        if not span:
            raise ValueError(f"Span not found: {span_id}")

        link_id = f"link_{uuid.uuid4().hex[:12]}"

        link = {
            "id": link_id,
            "span_id": span_id,
            "linked_trace_id": linked_trace_id,
            "linked_span_id": linked_span_id,
            "relationship": relationship,
            "attributes": attributes or {},
            "created_at": datetime.utcnow().isoformat()
        }

        DistributedTracing._span_links[span_id].append(link)
        span["links"].append(link)

        return link

    @staticmethod
    def get_trace(session, trace_id: str, include_spans: bool = True) -> dict:
        """
        Get trace details.

        Args:
            session: Database session
            trace_id: Trace ID
            include_spans: Whether to include span details

        Returns:
            Trace details
        """
        trace = DistributedTracing._traces.get(trace_id)
        if not trace:
            raise ValueError(f"Trace not found: {trace_id}")

        result = {**trace}

        if include_spans:
            span_ids = DistributedTracing._trace_spans[trace_id]
            spans = [DistributedTracing._spans[sid] for sid in span_ids if sid in DistributedTracing._spans]
            result["spans"] = spans

            # Build span tree
            result["span_tree"] = DistributedTracing._build_span_tree(spans)

        return result

    @staticmethod
    def get_trace_timeline(session, trace_id: str) -> dict:
        """
        Get trace timeline visualization.

        Args:
            session: Database session
            trace_id: Trace ID

        Returns:
            Trace timeline
        """
        trace = DistributedTracing._traces.get(trace_id)
        if not trace:
            raise ValueError(f"Trace not found: {trace_id}")

        span_ids = DistributedTracing._trace_spans[trace_id]
        spans = [DistributedTracing._spans[sid] for sid in span_ids if sid in DistributedTracing._spans]

        # Calculate timeline
        timeline = []
        for span in sorted(spans, key=lambda x: x["started_at"]):
            if span.get("ended_at"):
                timeline.append({
                    "span_id": span["id"],
                    "span_name": span["name"],
                    "service_name": span["service_name"],
                    "started_at": span["started_at"],
                    "ended_at": span["ended_at"],
                    "duration_ms": span["duration_ms"],
                    "status": span["status"]
                })

        return {
            "trace_id": trace_id,
            "trace_name": trace["name"],
            "timeline": timeline,
            "total_duration_ms": trace.get("duration_ms"),
            "span_count": len(timeline)
        }

    @staticmethod
    def get_service_map(session) -> dict:
        """
        Get service dependency map.

        Returns:
            Service dependency map
        """
        dependencies = []
        for source, targets in DistributedTracing._service_map.items():
            for target in targets:
                dependencies.append({
                    "source": source,
                    "target": target,
                    "call_count": sum(
                        1 for trace_metrics in DistributedTracing._trace_metrics.values()
                        if target in trace_metrics["service_calls"]
                    )
                })

        return {
            "services": list(set(
                [d["source"] for d in dependencies] + [d["target"] for d in dependencies]
            )),
            "dependencies": dependencies,
            "dependency_count": len(dependencies)
        }

    @staticmethod
    def search_traces(
        session,
        service_name: Optional[str] = None,
        operation_name: Optional[str] = None,
        state: Optional[str] = None,
        min_duration_ms: Optional[int] = None,
        has_errors: Optional[bool] = None,
        limit: int = 50
    ) -> dict:
        """
        Search traces with filters.

        Args:
            session: Database session
            service_name: Filter by service
            operation_name: Filter by operation
            state: Filter by state
            min_duration_ms: Filter by minimum duration
            has_errors: Filter by error presence
            limit: Maximum traces to return

        Returns:
            Matching traces
        """
        traces = list(DistributedTracing._traces.values())

        # Apply filters
        if service_name:
            traces = [t for t in traces if service_name in t["services_involved"]]
        if operation_name:
            traces = [t for t in traces if t["operation_name"] == operation_name]
        if state:
            traces = [t for t in traces if t["state"] == state]
        if min_duration_ms is not None:
            traces = [t for t in traces if t.get("duration_ms", 0) >= min_duration_ms]
        if has_errors is not None:
            if has_errors:
                traces = [t for t in traces if t["error_count"] > 0]
            else:
                traces = [t for t in traces if t["error_count"] == 0]

        # Sort by started_at descending
        traces.sort(key=lambda x: x["started_at"], reverse=True)

        # Apply limit
        traces = traces[:limit]

        return {
            "traces": traces,
            "total_traces": len(DistributedTracing._traces),
            "returned_count": len(traces)
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get distributed tracing statistics"""
        traces = list(DistributedTracing._traces.values())
        spans = list(DistributedTracing._spans.values())

        # State distribution
        state_dist = defaultdict(int)
        for trace in traces:
            state_dist[trace["state"]] += 1

        # Service distribution
        service_dist = defaultdict(int)
        for span in spans:
            service_dist[span["service_name"]] += 1

        # Calculate averages
        completed_traces = [t for t in traces if t.get("duration_ms") is not None]
        avg_duration = sum(t["duration_ms"] for t in completed_traces) / len(completed_traces) if completed_traces else 0

        error_traces = [t for t in traces if t["error_count"] > 0]
        error_rate = len(error_traces) / len(traces) * 100 if traces else 0

        return {
            "total_traces": len(traces),
            "total_spans": len(spans),
            "active_traces": len([t for t in traces if t["state"] == TraceState.ACTIVE]),
            "completed_traces": len(completed_traces),
            "failed_traces": len([t for t in traces if t["state"] == TraceState.FAILED]),
            "trace_state_distribution": dict(state_dist),
            "service_distribution": dict(service_dist),
            "average_trace_duration_ms": avg_duration,
            "error_rate_percentage": error_rate,
            "total_errors": sum(t["error_count"] for t in traces),
            "services_count": len(service_dist)
        }

    # Helper methods
    @staticmethod
    def _end_trace(trace_id: str):
        """End a trace"""
        trace = DistributedTracing._traces.get(trace_id)
        if not trace:
            return

        now = datetime.utcnow()
        started_at = datetime.fromisoformat(trace["started_at"])
        duration_ms = (now - started_at).total_seconds() * 1000

        trace["ended_at"] = now.isoformat()
        trace["duration_ms"] = duration_ms

        # Set state based on errors
        if trace["error_count"] > 0:
            trace["state"] = TraceState.FAILED
        else:
            trace["state"] = TraceState.COMPLETED

    @staticmethod
    def _build_span_tree(spans: List[dict]) -> List[dict]:
        """Build hierarchical span tree"""
        span_map = {span["id"]: {**span, "children": []} for span in spans}

        root_spans = []
        for span in spans:
            parent_id = span.get("parent_span_id")
            if parent_id and parent_id in span_map:
                span_map[parent_id]["children"].append(span_map[span["id"]])
            else:
                root_spans.append(span_map[span["id"]])

        return root_spans
