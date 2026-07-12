"""
Log Aggregation and Analysis Service

Provides centralized log collection, search, analysis, and pattern detection
for distributed systems monitoring and debugging.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from enum import Enum
import re
import json


class LogLevel(str, Enum):
    """Log severity levels"""
    TRACE = "trace"
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    FATAL = "fatal"


class LogSource(str, Enum):
    """Log source types"""
    APPLICATION = "application"
    DATABASE = "database"
    WEBSERVER = "webserver"
    CONTAINER = "container"
    SYSTEM = "system"
    SECURITY = "security"


class AggregationType(str, Enum):
    """Log aggregation types"""
    COUNT = "count"
    UNIQUE = "unique"
    TERMS = "terms"
    TIMELINE = "timeline"
    STATS = "stats"


class LogAggregation:
    """Log aggregation and analysis management"""

    # In-memory storage
    _logs: List[Dict] = []
    _log_streams: Dict[str, Dict] = {}
    _parsers: Dict[str, Dict] = {}
    _patterns: Dict[str, Dict] = {}
    _alerts: Dict[str, Dict] = {}
    _retention_policies: Dict[str, Dict] = {}

    @staticmethod
    def ingest_log(
        session,
        message: str,
        level: LogLevel,
        source: str,
        source_type: LogSource,
        timestamp: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> dict:
        """Ingest a log entry."""
        log_entry = {
            "log_id": f"log_{len(LogAggregation._logs)}_{datetime.utcnow().timestamp()}",
            "message": message,
            "level": level,
            "source": source,
            "source_type": source_type,
            "timestamp": timestamp or datetime.utcnow().isoformat(),
            "metadata": metadata or {},
            "tags": tags or [],
            "parsed_fields": {},
            "indexed_at": datetime.utcnow().isoformat()
        }

        # Apply parsers
        LogAggregation._apply_parsers(log_entry)

        # Store log
        LogAggregation._logs.append(log_entry)

        # Check for pattern matches
        matched_patterns = LogAggregation._check_patterns(log_entry)

        # Apply retention policies
        LogAggregation._apply_retention()

        return {
            "log_id": log_entry["log_id"],
            "ingested_at": log_entry["indexed_at"],
            "matched_patterns": matched_patterns
        }

    @staticmethod
    def ingest_bulk(
        session,
        logs: List[Dict]
    ) -> dict:
        """Ingest multiple log entries in bulk."""
        ingested = []
        failed = []

        for log_data in logs:
            try:
                result = LogAggregation.ingest_log(
                    session=session,
                    message=log_data["message"],
                    level=log_data["level"],
                    source=log_data["source"],
                    source_type=log_data["source_type"],
                    timestamp=log_data.get("timestamp"),
                    metadata=log_data.get("metadata"),
                    tags=log_data.get("tags")
                )
                ingested.append(result)
            except Exception as e:
                failed.append({
                    "log": log_data,
                    "error": str(e)
                })

        return {
            "ingested_count": len(ingested),
            "failed_count": len(failed),
            "ingested": ingested,
            "failed": failed
        }

    @staticmethod
    def _apply_parsers(log_entry: dict):
        """Apply registered parsers to extract structured fields."""
        for parser_id, parser in LogAggregation._parsers.items():
            if not parser["enabled"]:
                continue

            # Check if parser applies to this source
            if parser["source_filter"] and log_entry["source"] not in parser["source_filter"]:
                continue

            # Apply regex patterns
            for field_name, pattern in parser["patterns"].items():
                match = re.search(pattern, log_entry["message"])
                if match:
                    log_entry["parsed_fields"][field_name] = match.group(1) if match.groups() else match.group(0)

    @staticmethod
    def _check_patterns(log_entry: dict) -> List[str]:
        """Check if log matches any registered patterns."""
        matched = []

        for pattern_id, pattern in LogAggregation._patterns.items():
            if not pattern["enabled"]:
                continue

            # Check level filter
            if pattern["level_filter"] and log_entry["level"] not in pattern["level_filter"]:
                continue

            # Check regex match
            if re.search(pattern["regex"], log_entry["message"]):
                pattern["match_count"] += 1
                pattern["last_matched"] = datetime.utcnow().isoformat()
                matched.append(pattern_id)

                # Trigger alert if configured
                if pattern.get("alert_on_match"):
                    LogAggregation._create_pattern_alert(pattern_id, log_entry)

        return matched

    @staticmethod
    def _create_pattern_alert(pattern_id: str, log_entry: dict):
        """Create an alert for a pattern match."""
        pattern = LogAggregation._patterns[pattern_id]
        alert_id = f"alert_{pattern_id}_{datetime.utcnow().timestamp()}"

        alert = {
            "alert_id": alert_id,
            "pattern_id": pattern_id,
            "pattern_name": pattern["name"],
            "log_id": log_entry["log_id"],
            "message": log_entry["message"],
            "severity": pattern.get("alert_severity", "warning"),
            "created_at": datetime.utcnow().isoformat()
        }

        LogAggregation._alerts[alert_id] = alert

    @staticmethod
    def _apply_retention():
        """Apply retention policies to remove old logs."""
        for policy_id, policy in LogAggregation._retention_policies.items():
            cutoff = datetime.utcnow() - timedelta(days=policy["retention_days"])
            cutoff_iso = cutoff.isoformat()

            # Filter logs
            LogAggregation._logs = [
                log for log in LogAggregation._logs
                if not (
                    (not policy["source_filter"] or log["source"] in policy["source_filter"]) and
                    (not policy["level_filter"] or log["level"] in policy["level_filter"]) and
                    log["timestamp"] < cutoff_iso
                )
            ]

    @staticmethod
    def search_logs(
        session,
        query: Optional[str] = None,
        level: Optional[LogLevel] = None,
        source: Optional[str] = None,
        source_type: Optional[LogSource] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> dict:
        """Search logs with filters."""
        filtered_logs = LogAggregation._logs.copy()

        # Apply filters
        if query:
            filtered_logs = [
                log for log in filtered_logs
                if query.lower() in log["message"].lower() or
                   query.lower() in json.dumps(log["metadata"]).lower()
            ]

        if level:
            filtered_logs = [log for log in filtered_logs if log["level"] == level]

        if source:
            filtered_logs = [log for log in filtered_logs if log["source"] == source]

        if source_type:
            filtered_logs = [log for log in filtered_logs if log["source_type"] == source_type]

        if start_time:
            filtered_logs = [log for log in filtered_logs if log["timestamp"] >= start_time]

        if end_time:
            filtered_logs = [log for log in filtered_logs if log["timestamp"] <= end_time]

        if tags:
            filtered_logs = [
                log for log in filtered_logs
                if any(tag in log["tags"] for tag in tags)
            ]

        # Sort by timestamp descending
        filtered_logs.sort(key=lambda x: x["timestamp"], reverse=True)

        # Pagination
        total = len(filtered_logs)
        paginated_logs = filtered_logs[offset:offset + limit]

        return {
            "logs": paginated_logs,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total
        }

    @staticmethod
    def aggregate_logs(
        session,
        aggregation_type: AggregationType,
        field: str,
        query: Optional[str] = None,
        level: Optional[LogLevel] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        interval: Optional[str] = None
    ) -> dict:
        """Aggregate logs for analysis."""
        # Get filtered logs
        search_result = LogAggregation.search_logs(
            session=session,
            query=query,
            level=level,
            start_time=start_time,
            end_time=end_time,
            limit=10000
        )
        logs = search_result["logs"]

        if aggregation_type == AggregationType.COUNT:
            return {
                "aggregation_type": "count",
                "count": len(logs),
                "field": field
            }

        elif aggregation_type == AggregationType.UNIQUE:
            values = set()
            for log in logs:
                value = log.get(field) or log.get("metadata", {}).get(field) or log.get("parsed_fields", {}).get(field)
                if value:
                    values.add(str(value))

            return {
                "aggregation_type": "unique",
                "unique_count": len(values),
                "values": list(values),
                "field": field
            }

        elif aggregation_type == AggregationType.TERMS:
            term_counts = defaultdict(int)
            for log in logs:
                value = log.get(field) or log.get("metadata", {}).get(field) or log.get("parsed_fields", {}).get(field)
                if value:
                    term_counts[str(value)] += 1

            sorted_terms = sorted(term_counts.items(), key=lambda x: x[1], reverse=True)

            return {
                "aggregation_type": "terms",
                "terms": [{"term": term, "count": count} for term, count in sorted_terms],
                "field": field,
                "total_terms": len(sorted_terms)
            }

        elif aggregation_type == AggregationType.TIMELINE:
            # Group by time interval (simplified - using hours)
            timeline = defaultdict(int)
            for log in logs:
                timestamp = datetime.fromisoformat(log["timestamp"].replace('Z', '+00:00'))
                hour_key = timestamp.replace(minute=0, second=0, microsecond=0).isoformat()
                timeline[hour_key] += 1

            sorted_timeline = sorted(timeline.items())

            return {
                "aggregation_type": "timeline",
                "timeline": [{"timestamp": ts, "count": count} for ts, count in sorted_timeline],
                "field": field,
                "intervals": len(sorted_timeline)
            }

        elif aggregation_type == AggregationType.STATS:
            level_stats = defaultdict(int)
            source_stats = defaultdict(int)
            source_type_stats = defaultdict(int)

            for log in logs:
                level_stats[log["level"]] += 1
                source_stats[log["source"]] += 1
                source_type_stats[log["source_type"]] += 1

            return {
                "aggregation_type": "stats",
                "total_logs": len(logs),
                "by_level": dict(level_stats),
                "by_source": dict(source_stats),
                "by_source_type": dict(source_type_stats),
                "field": field
            }

        return {}

    @staticmethod
    def create_parser(
        session,
        parser_id: str,
        name: str,
        patterns: Dict[str, str],
        source_filter: Optional[List[str]] = None,
        description: str = "",
        enabled: bool = True
    ) -> dict:
        """Create a log parser for extracting structured fields."""
        if parser_id in LogAggregation._parsers:
            raise ValueError(f"Parser already exists: {parser_id}")

        parser = {
            "parser_id": parser_id,
            "name": name,
            "description": description,
            "patterns": patterns,
            "source_filter": source_filter,
            "enabled": enabled,
            "created_at": datetime.utcnow().isoformat(),
            "logs_parsed": 0
        }

        LogAggregation._parsers[parser_id] = parser
        return parser

    @staticmethod
    def create_pattern(
        session,
        pattern_id: str,
        name: str,
        regex: str,
        description: str = "",
        level_filter: Optional[List[LogLevel]] = None,
        alert_on_match: bool = False,
        alert_severity: str = "warning",
        enabled: bool = True
    ) -> dict:
        """Create a pattern for detecting specific log entries."""
        if pattern_id in LogAggregation._patterns:
            raise ValueError(f"Pattern already exists: {pattern_id}")

        # Validate regex
        try:
            re.compile(regex)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {str(e)}")

        pattern = {
            "pattern_id": pattern_id,
            "name": name,
            "description": description,
            "regex": regex,
            "level_filter": level_filter,
            "alert_on_match": alert_on_match,
            "alert_severity": alert_severity,
            "enabled": enabled,
            "created_at": datetime.utcnow().isoformat(),
            "match_count": 0,
            "last_matched": None
        }

        LogAggregation._patterns[pattern_id] = pattern
        return pattern

    @staticmethod
    def get_patterns(session) -> List[dict]:
        """Get all registered patterns."""
        return list(LogAggregation._patterns.values())

    @staticmethod
    def get_pattern_matches(
        session,
        pattern_id: str,
        limit: int = 100
    ) -> dict:
        """Get logs that match a specific pattern."""
        pattern = LogAggregation._patterns.get(pattern_id)
        if not pattern:
            raise ValueError(f"Pattern not found: {pattern_id}")

        matched_logs = []
        for log in reversed(LogAggregation._logs):
            if re.search(pattern["regex"], log["message"]):
                matched_logs.append(log)
                if len(matched_logs) >= limit:
                    break

        return {
            "pattern_id": pattern_id,
            "pattern_name": pattern["name"],
            "matched_logs": matched_logs,
            "count": len(matched_logs),
            "total_matches": pattern["match_count"]
        }

    @staticmethod
    def create_retention_policy(
        session,
        policy_id: str,
        name: str,
        retention_days: int,
        source_filter: Optional[List[str]] = None,
        level_filter: Optional[List[LogLevel]] = None,
        enabled: bool = True
    ) -> dict:
        """Create a log retention policy."""
        if policy_id in LogAggregation._retention_policies:
            raise ValueError(f"Retention policy already exists: {policy_id}")

        if retention_days < 1:
            raise ValueError("Retention days must be at least 1")

        policy = {
            "policy_id": policy_id,
            "name": name,
            "retention_days": retention_days,
            "source_filter": source_filter,
            "level_filter": level_filter,
            "enabled": enabled,
            "created_at": datetime.utcnow().isoformat()
        }

        LogAggregation._retention_policies[policy_id] = policy
        return policy

    @staticmethod
    def get_log_stream(
        session,
        stream_id: str
    ) -> dict:
        """Get a log stream configuration."""
        stream = LogAggregation._log_streams.get(stream_id)
        if not stream:
            raise ValueError(f"Log stream not found: {stream_id}")
        return stream

    @staticmethod
    def create_log_stream(
        session,
        stream_id: str,
        name: str,
        source: str,
        filters: Optional[Dict] = None,
        enabled: bool = True
    ) -> dict:
        """Create a log stream for real-time log monitoring."""
        if stream_id in LogAggregation._log_streams:
            raise ValueError(f"Log stream already exists: {stream_id}")

        stream = {
            "stream_id": stream_id,
            "name": name,
            "source": source,
            "filters": filters or {},
            "enabled": enabled,
            "created_at": datetime.utcnow().isoformat(),
            "logs_streamed": 0
        }

        LogAggregation._log_streams[stream_id] = stream
        return stream

    @staticmethod
    def export_logs(
        session,
        format: str,
        query: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 10000
    ) -> dict:
        """Export logs in various formats."""
        # Get filtered logs
        search_result = LogAggregation.search_logs(
            session=session,
            query=query,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        logs = search_result["logs"]

        if format == "json":
            exported_data = json.dumps(logs, indent=2)
        elif format == "csv":
            # Simplified CSV export
            headers = ["timestamp", "level", "source", "message"]
            rows = [",".join(headers)]
            for log in logs:
                row = [
                    log["timestamp"],
                    log["level"],
                    log["source"],
                    log["message"].replace(",", ";")  # Simple escape
                ]
                rows.append(",".join(row))
            exported_data = "\n".join(rows)
        elif format == "text":
            lines = []
            for log in logs:
                lines.append(f"[{log['timestamp']}] {log['level'].upper()} [{log['source']}] {log['message']}")
            exported_data = "\n".join(lines)
        else:
            raise ValueError(f"Unsupported export format: {format}")

        return {
            "format": format,
            "log_count": len(logs),
            "exported_at": datetime.utcnow().isoformat(),
            "data": exported_data
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get log aggregation statistics."""
        level_counts = defaultdict(int)
        source_counts = defaultdict(int)
        source_type_counts = defaultdict(int)

        for log in LogAggregation._logs:
            level_counts[log["level"]] += 1
            source_counts[log["source"]] += 1
            source_type_counts[log["source_type"]] += 1

        return {
            "total_logs": len(LogAggregation._logs),
            "by_level": dict(level_counts),
            "by_source": dict(source_counts),
            "by_source_type": dict(source_type_counts),
            "parsers": len(LogAggregation._parsers),
            "patterns": len(LogAggregation._patterns),
            "pattern_alerts": len(LogAggregation._alerts),
            "retention_policies": len(LogAggregation._retention_policies),
            "log_streams": len(LogAggregation._log_streams)
        }
