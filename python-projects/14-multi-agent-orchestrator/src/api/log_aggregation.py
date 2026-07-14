"""
Log Aggregation and Analysis API

REST API endpoints for centralized log collection, search, and analysis.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.log_aggregation import (
    LogAggregation,
    LogLevel,
    LogSource,
    AggregationType
)


router = APIRouter()


# Request/Response Models
class IngestLogRequest(BaseModel):
    """Request model for ingesting a log"""
    message: str = Field(..., description="Log message")
    level: LogLevel = Field(..., description="Log level")
    source: str = Field(..., description="Log source identifier")
    source_type: LogSource = Field(..., description="Type of log source")
    timestamp: Optional[str] = Field(default=None, description="ISO timestamp")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")
    tags: Optional[List[str]] = Field(default=None, description="Tags for categorization")


class IngestBulkRequest(BaseModel):
    """Request model for bulk log ingestion"""
    logs: List[Dict] = Field(..., description="List of log entries")


class SearchLogsRequest(BaseModel):
    """Request model for searching logs"""
    query: Optional[str] = Field(default=None, description="Search query")
    level: Optional[LogLevel] = Field(default=None, description="Filter by log level")
    source: Optional[str] = Field(default=None, description="Filter by source")
    source_type: Optional[LogSource] = Field(default=None, description="Filter by source type")
    start_time: Optional[str] = Field(default=None, description="Start time (ISO)")
    end_time: Optional[str] = Field(default=None, description="End time (ISO)")
    tags: Optional[List[str]] = Field(default=None, description="Filter by tags")
    limit: int = Field(default=100, description="Max results", ge=1, le=10000)
    offset: int = Field(default=0, description="Offset for pagination", ge=0)


class AggregateLogsRequest(BaseModel):
    """Request model for log aggregation"""
    aggregation_type: AggregationType = Field(..., description="Type of aggregation")
    field: str = Field(..., description="Field to aggregate on")
    query: Optional[str] = Field(default=None, description="Filter query")
    level: Optional[LogLevel] = Field(default=None, description="Filter by level")
    start_time: Optional[str] = Field(default=None, description="Start time (ISO)")
    end_time: Optional[str] = Field(default=None, description="End time (ISO)")
    interval: Optional[str] = Field(default=None, description="Time interval for timeline")


class CreateParserRequest(BaseModel):
    """Request model for creating a parser"""
    parser_id: str = Field(..., description="Unique parser identifier")
    name: str = Field(..., description="Parser name")
    patterns: Dict[str, str] = Field(..., description="Regex patterns for field extraction")
    source_filter: Optional[List[str]] = Field(default=None, description="Sources to apply parser to")
    description: str = Field(default="", description="Parser description")
    enabled: bool = Field(default=True, description="Whether parser is enabled")


class CreatePatternRequest(BaseModel):
    """Request model for creating a pattern"""
    pattern_id: str = Field(..., description="Unique pattern identifier")
    name: str = Field(..., description="Pattern name")
    regex: str = Field(..., description="Regex pattern to match")
    description: str = Field(default="", description="Pattern description")
    level_filter: Optional[List[LogLevel]] = Field(default=None, description="Log levels to match")
    alert_on_match: bool = Field(default=False, description="Create alert on match")
    alert_severity: str = Field(default="warning", description="Alert severity")
    enabled: bool = Field(default=True, description="Whether pattern is enabled")


class CreateRetentionPolicyRequest(BaseModel):
    """Request model for creating a retention policy"""
    policy_id: str = Field(..., description="Unique policy identifier")
    name: str = Field(..., description="Policy name")
    retention_days: int = Field(..., description="Days to retain logs", ge=1)
    source_filter: Optional[List[str]] = Field(default=None, description="Sources to apply policy to")
    level_filter: Optional[List[LogLevel]] = Field(default=None, description="Levels to apply policy to")
    enabled: bool = Field(default=True, description="Whether policy is enabled")


class CreateLogStreamRequest(BaseModel):
    """Request model for creating a log stream"""
    stream_id: str = Field(..., description="Unique stream identifier")
    name: str = Field(..., description="Stream name")
    source: str = Field(..., description="Source to stream from")
    filters: Optional[Dict] = Field(default=None, description="Stream filters")
    enabled: bool = Field(default=True, description="Whether stream is enabled")


class ExportLogsRequest(BaseModel):
    """Request model for exporting logs"""
    format: str = Field(..., description="Export format (json, csv, text)")
    query: Optional[str] = Field(default=None, description="Filter query")
    start_time: Optional[str] = Field(default=None, description="Start time (ISO)")
    end_time: Optional[str] = Field(default=None, description="End time (ISO)")
    limit: int = Field(default=10000, description="Max logs to export", ge=1, le=100000)


# API Endpoints
@router.post("/ingest")
def ingest_log(
    request: IngestLogRequest,
    session: Session = Depends(get_db_session)
):
    """
    Ingest a single log entry.
    Stores the log and applies parsers and pattern matching.
    """
    try:
        result = LogAggregation.ingest_log(
            session=session,
            message=request.message,
            level=request.level,
            source=request.source,
            source_type=request.source_type,
            timestamp=request.timestamp,
            metadata=request.metadata,
            tags=request.tags
        )
        return {
            "success": True,
            "ingestion": result,
            "message": f"Log ingested: {result['log_id']}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error ingesting log: {str(e)}")


@router.post("/ingest/bulk")
def ingest_bulk(
    request: IngestBulkRequest,
    session: Session = Depends(get_db_session)
):
    """
    Ingest multiple log entries in bulk.
    Efficiently processes large batches of logs.
    """
    try:
        result = LogAggregation.ingest_bulk(
            session=session,
            logs=request.logs
        )
        return {
            "success": True,
            "bulk_ingestion": result,
            "message": f"Bulk ingestion: {result['ingested_count']} succeeded, {result['failed_count']} failed"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in bulk ingestion: {str(e)}")


@router.post("/search")
def search_logs(
    request: SearchLogsRequest,
    session: Session = Depends(get_db_session)
):
    """
    Search logs with filters.
    Supports full-text search, filtering by level/source/time, and pagination.
    """
    try:
        result = LogAggregation.search_logs(
            session=session,
            query=request.query,
            level=request.level,
            source=request.source,
            source_type=request.source_type,
            start_time=request.start_time,
            end_time=request.end_time,
            tags=request.tags,
            limit=request.limit,
            offset=request.offset
        )
        return {
            "success": True,
            "search_results": result,
            "message": f"Found {result['total']} logs"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching logs: {str(e)}")


@router.post("/aggregate")
def aggregate_logs(
    request: AggregateLogsRequest,
    session: Session = Depends(get_db_session)
):
    """
    Aggregate logs for analysis.
    Supports count, unique values, term frequency, timeline, and stats aggregations.
    """
    try:
        result = LogAggregation.aggregate_logs(
            session=session,
            aggregation_type=request.aggregation_type,
            field=request.field,
            query=request.query,
            level=request.level,
            start_time=request.start_time,
            end_time=request.end_time,
            interval=request.interval
        )
        return {
            "success": True,
            "aggregation": result,
            "message": f"Aggregation completed: {request.aggregation_type}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error aggregating logs: {str(e)}")


@router.post("/parsers")
def create_parser(
    request: CreateParserRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a log parser.
    Defines regex patterns to extract structured fields from log messages.
    """
    try:
        result = LogAggregation.create_parser(
            session=session,
            parser_id=request.parser_id,
            name=request.name,
            patterns=request.patterns,
            source_filter=request.source_filter,
            description=request.description,
            enabled=request.enabled
        )
        return {
            "success": True,
            "parser": result,
            "message": f"Parser created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating parser: {str(e)}")


@router.get("/parsers")
def list_parsers(session: Session = Depends(get_db_session)):
    """
    List all log parsers.
    Returns all registered parsers for extracting structured fields.
    """
    try:
        parsers = list(LogAggregation._parsers.values())
        return {
            "success": True,
            "parsers": parsers,
            "count": len(parsers)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing parsers: {str(e)}")


@router.post("/patterns")
def create_pattern(
    request: CreatePatternRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a log pattern.
    Defines a regex pattern for detecting specific log entries.
    Can trigger alerts when matched.
    """
    try:
        result = LogAggregation.create_pattern(
            session=session,
            pattern_id=request.pattern_id,
            name=request.name,
            regex=request.regex,
            description=request.description,
            level_filter=request.level_filter,
            alert_on_match=request.alert_on_match,
            alert_severity=request.alert_severity,
            enabled=request.enabled
        )
        return {
            "success": True,
            "pattern": result,
            "message": f"Pattern created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating pattern: {str(e)}")


@router.get("/patterns")
def get_patterns(session: Session = Depends(get_db_session)):
    """
    Get all log patterns.
    Returns all registered patterns for log detection.
    """
    try:
        patterns = LogAggregation.get_patterns(session)
        return {
            "success": True,
            "patterns": patterns,
            "count": len(patterns)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting patterns: {str(e)}")


@router.get("/patterns/{pattern_id}/matches")
def get_pattern_matches(
    pattern_id: str,
    limit: int = 100,
    session: Session = Depends(get_db_session)
):
    """
    Get logs matching a pattern.
    Returns logs that match the specified pattern.
    """
    try:
        result = LogAggregation.get_pattern_matches(
            session=session,
            pattern_id=pattern_id,
            limit=limit
        )
        return {
            "success": True,
            "matches": result,
            "message": f"Found {result['count']} matching logs"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting pattern matches: {str(e)}")


@router.post("/retention-policies")
def create_retention_policy(
    request: CreateRetentionPolicyRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a retention policy.
    Defines how long logs are retained based on source and level.
    """
    try:
        result = LogAggregation.create_retention_policy(
            session=session,
            policy_id=request.policy_id,
            name=request.name,
            retention_days=request.retention_days,
            source_filter=request.source_filter,
            level_filter=request.level_filter,
            enabled=request.enabled
        )
        return {
            "success": True,
            "policy": result,
            "message": f"Retention policy created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating retention policy: {str(e)}")


@router.get("/retention-policies")
def list_retention_policies(session: Session = Depends(get_db_session)):
    """
    List all retention policies.
    Returns all configured retention policies.
    """
    try:
        policies = list(LogAggregation._retention_policies.values())
        return {
            "success": True,
            "policies": policies,
            "count": len(policies)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing retention policies: {str(e)}")


@router.post("/streams")
def create_log_stream(
    request: CreateLogStreamRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a log stream.
    Defines a stream for real-time log monitoring.
    """
    try:
        result = LogAggregation.create_log_stream(
            session=session,
            stream_id=request.stream_id,
            name=request.name,
            source=request.source,
            filters=request.filters,
            enabled=request.enabled
        )
        return {
            "success": True,
            "stream": result,
            "message": f"Log stream created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating log stream: {str(e)}")


@router.get("/streams/{stream_id}")
def get_log_stream(
    stream_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get a log stream.
    Returns stream configuration and status.
    """
    try:
        result = LogAggregation.get_log_stream(
            session=session,
            stream_id=stream_id
        )
        return {
            "success": True,
            "stream": result,
            "message": "Log stream retrieved"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting log stream: {str(e)}")


@router.post("/export")
def export_logs(
    request: ExportLogsRequest,
    session: Session = Depends(get_db_session)
):
    """
    Export logs.
    Exports logs in JSON, CSV, or text format.
    """
    try:
        result = LogAggregation.export_logs(
            session=session,
            format=request.format,
            query=request.query,
            start_time=request.start_time,
            end_time=request.end_time,
            limit=request.limit
        )
        return {
            "success": True,
            "export": result,
            "message": f"Exported {result['log_count']} logs as {request.format}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error exporting logs: {str(e)}")


@router.get("/statistics")
def get_statistics(session: Session = Depends(get_db_session)):
    """
    Get log statistics.
    Returns comprehensive statistics about logs, parsers, patterns, and policies.
    """
    try:
        stats = LogAggregation.get_statistics(session)
        return {
            "success": True,
            "statistics": stats,
            "message": "Statistics retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")
