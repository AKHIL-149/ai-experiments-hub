"""
Circuit Breaker and Fault Tolerance API

REST API endpoints for managing circuit breakers, retry policies, and fault tolerance.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
    RetryStrategy,
    FallbackStrategy,
    FailureType
)


router = APIRouter()


# Request/Response Models
class CreateCircuitBreakerRequest(BaseModel):
    name: str = Field(..., description="Circuit breaker name")
    service_name: str = Field(..., description="Name of the protected service")
    failure_threshold: int = Field(5, description="Failures before opening circuit")
    success_threshold: int = Field(2, description="Successes to close from half-open")
    timeout_seconds: float = Field(5.0, description="Operation timeout")
    reset_timeout_seconds: int = Field(60, description="Time before half-open attempt")
    description: Optional[str] = Field(None, description="Circuit breaker description")
    enabled: bool = Field(True, description="Whether circuit breaker is enabled")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class CreateRetryPolicyRequest(BaseModel):
    name: str = Field(..., description="Policy name")
    strategy: str = Field(..., description="Retry strategy")
    max_attempts: int = Field(3, description="Maximum retry attempts")
    initial_delay_ms: int = Field(100, description="Initial delay in milliseconds")
    max_delay_ms: int = Field(5000, description="Maximum delay in milliseconds")
    backoff_multiplier: float = Field(2.0, description="Multiplier for exponential backoff")
    retryable_errors: Optional[List[str]] = Field(None, description="List of retryable error types")
    description: Optional[str] = Field(None, description="Policy description")
    enabled: bool = Field(True, description="Whether policy is enabled")


class CreateFallbackHandlerRequest(BaseModel):
    name: str = Field(..., description="Handler name")
    strategy: str = Field(..., description="Fallback strategy")
    fallback_data: Optional[dict] = Field(None, description="Default fallback data")
    alternative_service: Optional[str] = Field(None, description="Alternative service to call")
    cache_ttl_seconds: Optional[int] = Field(None, description="Cache TTL for cached values")
    description: Optional[str] = Field(None, description="Handler description")
    enabled: bool = Field(True, description="Whether handler is enabled")


class ExecuteWithCircuitBreakerRequest(BaseModel):
    retry_policy_id: Optional[str] = Field(None, description="Optional retry policy")
    fallback_handler_id: Optional[str] = Field(None, description="Optional fallback handler")
    operation_metadata: Optional[dict] = Field(None, description="Operation metadata")


@router.post("/circuit-breakers")
def create_circuit_breaker(
    request: CreateCircuitBreakerRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a circuit breaker.

    Creates a circuit breaker to protect a service with automatic
    failure detection and recovery.
    """
    try:
        breaker = CircuitBreaker.create_circuit_breaker(
            session=session,
            name=request.name,
            service_name=request.service_name,
            failure_threshold=request.failure_threshold,
            success_threshold=request.success_threshold,
            timeout_seconds=request.timeout_seconds,
            reset_timeout_seconds=request.reset_timeout_seconds,
            description=request.description,
            enabled=request.enabled,
            metadata=request.metadata
        )

        return {
            "success": True,
            "circuit_breaker": breaker,
            "message": f"Circuit breaker created: {breaker['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retry-policies")
def create_retry_policy(
    request: CreateRetryPolicyRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a retry policy.

    Creates a retry policy with configurable strategy and backoff.
    """
    try:
        policy = CircuitBreaker.create_retry_policy(
            session=session,
            name=request.name,
            strategy=request.strategy,
            max_attempts=request.max_attempts,
            initial_delay_ms=request.initial_delay_ms,
            max_delay_ms=request.max_delay_ms,
            backoff_multiplier=request.backoff_multiplier,
            retryable_errors=request.retryable_errors,
            description=request.description,
            enabled=request.enabled
        )

        return {
            "success": True,
            "retry_policy": policy,
            "message": f"Retry policy created: {policy['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fallback-handlers")
def create_fallback_handler(
    request: CreateFallbackHandlerRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a fallback handler.

    Creates a fallback handler for graceful degradation when
    primary service fails.
    """
    try:
        handler = CircuitBreaker.create_fallback_handler(
            session=session,
            name=request.name,
            strategy=request.strategy,
            fallback_data=request.fallback_data,
            alternative_service=request.alternative_service,
            cache_ttl_seconds=request.cache_ttl_seconds,
            description=request.description,
            enabled=request.enabled
        )

        return {
            "success": True,
            "fallback_handler": handler,
            "message": f"Fallback handler created: {handler['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/circuit-breakers")
def list_circuit_breakers(
    service_name: Optional[str] = None,
    state: Optional[str] = None,
    enabled: Optional[bool] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    List circuit breakers.

    Returns circuit breakers with optional filtering by service,
    state, and enabled status.
    """
    try:
        result = CircuitBreaker.list_circuit_breakers(
            session=session,
            service_name=service_name,
            state=state,
            enabled=enabled,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/circuit-breakers/{breaker_id}")
def get_circuit_breaker(
    breaker_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get circuit breaker by ID.

    Returns detailed information about a specific circuit breaker
    including current status and metrics.
    """
    try:
        breaker = CircuitBreaker.get_circuit_status(
            session=session,
            breaker_id=breaker_id
        )

        return {
            "success": True,
            "circuit_breaker": breaker
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/circuit-breakers/{breaker_id}/reset")
def reset_circuit_breaker(
    breaker_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Reset circuit breaker.

    Manually resets the circuit breaker to closed state,
    clearing failure counters.
    """
    try:
        result = CircuitBreaker.reset_circuit_breaker(
            session=session,
            breaker_id=breaker_id
        )

        return {
            "success": True,
            **result,
            "message": "Circuit breaker reset to CLOSED state"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get circuit breaker statistics.

    Returns aggregate metrics including state distribution,
    success rates, and retry statistics.
    """
    try:
        stats = CircuitBreaker.get_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/circuit-states")
def list_circuit_states():
    """
    List all circuit states.

    Returns all possible circuit breaker states.
    """
    return {
        "success": True,
        "circuit_states": [
            {"state": CircuitState.CLOSED, "description": "Normal operation - requests pass through"},
            {"state": CircuitState.OPEN, "description": "Circuit is open - requests are rejected"},
            {"state": CircuitState.HALF_OPEN, "description": "Testing recovery - limited requests allowed"}
        ]
    }


@router.get("/retry-strategies")
def list_retry_strategies():
    """
    List all retry strategies.

    Returns all available retry strategies and their descriptions.
    """
    return {
        "success": True,
        "retry_strategies": [
            {"strategy": RetryStrategy.NONE, "description": "No retries"},
            {"strategy": RetryStrategy.FIXED, "description": "Fixed delay between retries"},
            {"strategy": RetryStrategy.EXPONENTIAL, "description": "Exponential backoff"},
            {"strategy": RetryStrategy.LINEAR, "description": "Linear increase in delay"}
        ]
    }


@router.get("/fallback-strategies")
def list_fallback_strategies():
    """
    List all fallback strategies.

    Returns all available fallback strategies.
    """
    return {
        "success": True,
        "fallback_strategies": [
            {"strategy": FallbackStrategy.NONE, "description": "No fallback"},
            {"strategy": FallbackStrategy.DEFAULT_VALUE, "description": "Return default value"},
            {"strategy": FallbackStrategy.CACHED_VALUE, "description": "Return cached value"},
            {"strategy": FallbackStrategy.ALTERNATIVE_SERVICE, "description": "Call alternative service"},
            {"strategy": FallbackStrategy.CUSTOM_HANDLER, "description": "Custom fallback handler"}
        ]
    }


@router.get("/failure-types")
def list_failure_types():
    """
    List all failure types.

    Returns all recognized failure types for error classification.
    """
    return {
        "success": True,
        "failure_types": [
            {"type": FailureType.TIMEOUT, "description": "Request timeout"},
            {"type": FailureType.CONNECTION_ERROR, "description": "Connection failure"},
            {"type": FailureType.SERVICE_ERROR, "description": "Service error"},
            {"type": FailureType.VALIDATION_ERROR, "description": "Validation failure"},
            {"type": FailureType.RATE_LIMIT, "description": "Rate limit exceeded"},
            {"type": FailureType.UNKNOWN, "description": "Unknown error"}
        ]
    }
