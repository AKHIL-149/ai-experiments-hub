"""
Error tracking API endpoints
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.core.error_tracker import error_tracker
from src.core.logging import logger


router = APIRouter()


class ErrorSummaryResponse(BaseModel):
    """Error summary response model"""
    time_period_hours: int
    total_errors: int
    unique_errors: int
    severity_breakdown: dict
    category_breakdown: dict
    top_errors: list
    generated_at: str


@router.get("/summary")
async def get_error_summary(
    hours: int = Query(24, ge=1, le=168, description="Hours to look back (1-168)"),
    min_occurrences: int = Query(1, ge=1, description="Minimum occurrence count")
):
    """
    Get error summary for specified time period

    Args:
        hours: Number of hours to look back (default: 24, max: 168/7 days)
        min_occurrences: Minimum occurrence count to include (default: 1)

    Returns:
        ErrorSummaryResponse: Error statistics and top errors
    """
    try:
        summary = error_tracker.get_error_summary(
            hours=hours,
            min_occurrences=min_occurrences
        )

        logger.info(
            f"Error summary requested: {summary['total_errors']} errors "
            f"({summary['unique_errors']} unique) in last {hours} hours"
        )

        return summary

    except Exception as e:
        logger.error(f"Failed to get error summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/details/{fingerprint}")
async def get_error_details(fingerprint: str):
    """
    Get detailed information about a specific error

    Args:
        fingerprint: Error fingerprint

    Returns:
        dict: Detailed error information including occurrences and traceback
    """
    try:
        details = error_tracker.get_error_details(fingerprint)

        if not details:
            raise HTTPException(
                status_code=404,
                detail=f"Error with fingerprint '{fingerprint}' not found"
            )

        return details

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get error details: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/suggestions/{fingerprint}")
async def get_recovery_suggestions(fingerprint: str):
    """
    Get recovery suggestions for a specific error

    Args:
        fingerprint: Error fingerprint

    Returns:
        dict: Recovery suggestions
    """
    try:
        suggestions = error_tracker.get_recovery_suggestions(fingerprint)

        return {
            "fingerprint": fingerprint,
            "suggestions": suggestions
        }

    except Exception as e:
        logger.error(f"Failed to get recovery suggestions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear")
async def clear_old_errors(hours: int = Query(168, ge=1, description="Keep errors newer than this")):
    """
    Clear errors older than specified hours

    Args:
        hours: Keep errors newer than this many hours (default: 168/7 days)

    Returns:
        dict: Number of errors cleared
    """
    try:
        cleared_count = error_tracker.clear_old_errors(hours=hours)

        logger.info(f"Cleared {cleared_count} errors older than {hours} hours")

        return {
            "success": True,
            "cleared_count": cleared_count,
            "kept_hours": hours
        }

    except Exception as e:
        logger.error(f"Failed to clear old errors: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/categories")
async def get_error_categories():
    """
    Get list of error categories

    Returns:
        dict: Available error categories and severities
    """
    from src.core.error_tracker import ErrorCategory, ErrorSeverity

    return {
        "categories": [cat.value for cat in ErrorCategory],
        "severities": [sev.value for sev in ErrorSeverity]
    }


@router.get("/stats")
async def get_error_stats():
    """
    Get overall error tracking statistics

    Returns:
        dict: Error tracker statistics
    """
    try:
        total_tracked = len(error_tracker.errors)
        unique_fingerprints = len(error_tracker.error_counts)

        # Get errors in last 24 hours
        summary_24h = error_tracker.get_error_summary(hours=24)

        # Get errors in last hour
        summary_1h = error_tracker.get_error_summary(hours=1)

        return {
            "total_errors_tracked": total_tracked,
            "unique_error_types": unique_fingerprints,
            "errors_last_24h": summary_24h["total_errors"],
            "errors_last_hour": summary_1h["total_errors"],
            "max_errors_capacity": error_tracker.max_errors,
            "memory_usage_percent": round(
                (total_tracked / error_tracker.max_errors) * 100, 2
            )
        }

    except Exception as e:
        logger.error(f"Failed to get error stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
