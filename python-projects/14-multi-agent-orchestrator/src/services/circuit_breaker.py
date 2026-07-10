"""
Circuit Breaker and Fault Tolerance Service

Provides resilient service communication with circuit breaker pattern, retries, and fallbacks.
"""

from typing import Optional, Callable, Any, Dict, List
from datetime import datetime, timedelta
from collections import defaultdict
import uuid
import time
import asyncio
from functools import wraps


class CircuitState:
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit is open, failing fast
    HALF_OPEN = "half_open"  # Testing if service recovered


class RetryStrategy:
    """Retry strategy types"""
    NONE = "none"
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"


class FallbackStrategy:
    """Fallback strategy types"""
    NONE = "none"
    DEFAULT_VALUE = "default_value"
    CACHED_VALUE = "cached_value"
    ALTERNATIVE_SERVICE = "alternative_service"
    CUSTOM_HANDLER = "custom_handler"


class FailureType:
    """Types of failures"""
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    SERVICE_ERROR = "service_error"
    VALIDATION_ERROR = "validation_error"
    RATE_LIMIT = "rate_limit"
    UNKNOWN = "unknown"


class CircuitBreaker:
    """Circuit Breaker and Fault Tolerance service"""

    # In-memory storage
    _circuit_breakers = {}
    _retry_policies = {}
    _fallback_handlers = {}
    _execution_history = defaultdict(list)
    _circuit_metrics = defaultdict(lambda: {
        "total_calls": 0,
        "successful_calls": 0,
        "failed_calls": 0,
        "rejected_calls": 0,
        "fallback_calls": 0,
        "retry_attempts": 0,
        "total_latency_ms": 0
    })

    @staticmethod
    def create_circuit_breaker(
        session,
        name: str,
        service_name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout_seconds: float = 5.0,
        reset_timeout_seconds: int = 60,
        description: Optional[str] = None,
        enabled: bool = True,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create a circuit breaker.

        Args:
            session: Database session
            name: Circuit breaker name
            service_name: Name of the protected service
            failure_threshold: Number of failures before opening circuit
            success_threshold: Number of successes to close circuit from half-open
            timeout_seconds: Operation timeout
            reset_timeout_seconds: Time to wait before half-open attempt
            description: Circuit breaker description
            enabled: Whether circuit breaker is enabled
            metadata: Additional metadata

        Returns:
            Created circuit breaker
        """
        breaker_id = f"cb_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        breaker = {
            "id": breaker_id,
            "name": name,
            "service_name": service_name,
            "state": CircuitState.CLOSED,
            "failure_threshold": failure_threshold,
            "success_threshold": success_threshold,
            "timeout_seconds": timeout_seconds,
            "reset_timeout_seconds": reset_timeout_seconds,
            "description": description,
            "enabled": enabled,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "last_failure_at": None,
            "last_success_at": None,
            "opened_at": None,
            "half_opened_at": None,
            "consecutive_failures": 0,
            "consecutive_successes": 0,
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "rejected_calls": 0,
            "metadata": metadata or {}
        }

        CircuitBreaker._circuit_breakers[breaker_id] = breaker
        return breaker

    @staticmethod
    def create_retry_policy(
        session,
        name: str,
        strategy: str,
        max_attempts: int = 3,
        initial_delay_ms: int = 100,
        max_delay_ms: int = 5000,
        backoff_multiplier: float = 2.0,
        retryable_errors: Optional[List[str]] = None,
        description: Optional[str] = None,
        enabled: bool = True
    ) -> dict:
        """
        Create a retry policy.

        Args:
            session: Database session
            name: Policy name
            strategy: Retry strategy
            max_attempts: Maximum retry attempts
            initial_delay_ms: Initial delay in milliseconds
            max_delay_ms: Maximum delay in milliseconds
            backoff_multiplier: Multiplier for exponential backoff
            retryable_errors: List of retryable error types
            description: Policy description
            enabled: Whether policy is enabled

        Returns:
            Created retry policy
        """
        policy_id = f"retry_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        policy = {
            "id": policy_id,
            "name": name,
            "strategy": strategy,
            "max_attempts": max_attempts,
            "initial_delay_ms": initial_delay_ms,
            "max_delay_ms": max_delay_ms,
            "backoff_multiplier": backoff_multiplier,
            "retryable_errors": retryable_errors or [
                FailureType.TIMEOUT,
                FailureType.CONNECTION_ERROR,
                FailureType.SERVICE_ERROR
            ],
            "description": description,
            "enabled": enabled,
            "created_at": now.isoformat(),
            "total_retries": 0,
            "successful_retries": 0,
            "exhausted_retries": 0
        }

        CircuitBreaker._retry_policies[policy_id] = policy
        return policy

    @staticmethod
    def create_fallback_handler(
        session,
        name: str,
        strategy: str,
        fallback_data: Optional[dict] = None,
        alternative_service: Optional[str] = None,
        cache_ttl_seconds: Optional[int] = None,
        description: Optional[str] = None,
        enabled: bool = True
    ) -> dict:
        """
        Create a fallback handler.

        Args:
            session: Database session
            name: Handler name
            strategy: Fallback strategy
            fallback_data: Default fallback data
            alternative_service: Alternative service to call
            cache_ttl_seconds: Cache TTL for cached values
            description: Handler description
            enabled: Whether handler is enabled

        Returns:
            Created fallback handler
        """
        handler_id = f"fallback_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        handler = {
            "id": handler_id,
            "name": name,
            "strategy": strategy,
            "fallback_data": fallback_data,
            "alternative_service": alternative_service,
            "cache_ttl_seconds": cache_ttl_seconds,
            "description": description,
            "enabled": enabled,
            "created_at": now.isoformat(),
            "invocation_count": 0,
            "last_invoked_at": None
        }

        CircuitBreaker._fallback_handlers[handler_id] = handler
        return handler

    @staticmethod
    def execute_with_circuit_breaker(
        session,
        breaker_id: str,
        operation: Callable,
        retry_policy_id: Optional[str] = None,
        fallback_handler_id: Optional[str] = None,
        operation_metadata: Optional[dict] = None
    ) -> dict:
        """
        Execute operation with circuit breaker protection.

        Args:
            session: Database session
            breaker_id: Circuit breaker ID
            operation: Operation to execute
            retry_policy_id: Optional retry policy
            fallback_handler_id: Optional fallback handler
            operation_metadata: Operation metadata

        Returns:
            Execution result
        """
        breaker = CircuitBreaker._circuit_breakers.get(breaker_id)
        if not breaker:
            raise ValueError(f"Circuit breaker not found: {breaker_id}")

        if not breaker["enabled"]:
            # Circuit breaker disabled, execute directly
            return CircuitBreaker._execute_operation(operation)

        now = datetime.utcnow()
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"

        # Check circuit state
        state = CircuitBreaker._check_circuit_state(breaker, now)

        if state == CircuitState.OPEN:
            # Circuit is open, reject immediately
            breaker["rejected_calls"] += 1
            CircuitBreaker._circuit_metrics[breaker_id]["rejected_calls"] += 1

            result = {
                "execution_id": execution_id,
                "breaker_id": breaker_id,
                "success": False,
                "circuit_open": True,
                "executed_at": now.isoformat(),
                "error": "Circuit breaker is OPEN"
            }

            # Try fallback
            if fallback_handler_id:
                fallback_result = CircuitBreaker._execute_fallback(
                    fallback_handler_id, operation_metadata
                )
                result["fallback_used"] = True
                result["fallback_result"] = fallback_result

            return result

        # Execute with retry if policy specified
        if retry_policy_id:
            execution_result = CircuitBreaker._execute_with_retry(
                operation, retry_policy_id
            )
        else:
            execution_result = CircuitBreaker._execute_operation(operation)

        # Update circuit breaker based on result
        if execution_result["success"]:
            CircuitBreaker._record_success(breaker, now)
        else:
            CircuitBreaker._record_failure(breaker, now, execution_result.get("error_type"))

            # Try fallback on failure
            if fallback_handler_id:
                fallback_result = CircuitBreaker._execute_fallback(
                    fallback_handler_id, operation_metadata
                )
                execution_result["fallback_used"] = True
                execution_result["fallback_result"] = fallback_result

        # Record execution
        execution_record = {
            "execution_id": execution_id,
            "breaker_id": breaker_id,
            "executed_at": now.isoformat(),
            "circuit_state": state,
            **execution_result
        }

        CircuitBreaker._execution_history[breaker_id].append(execution_record)

        # Keep only last 100 executions per breaker
        if len(CircuitBreaker._execution_history[breaker_id]) > 100:
            CircuitBreaker._execution_history[breaker_id] = \
                CircuitBreaker._execution_history[breaker_id][-100:]

        return execution_record

    @staticmethod
    def get_circuit_status(session, breaker_id: str) -> dict:
        """Get current circuit breaker status"""
        breaker = CircuitBreaker._circuit_breakers.get(breaker_id)
        if not breaker:
            raise ValueError(f"Circuit breaker not found: {breaker_id}")

        now = datetime.utcnow()
        state = CircuitBreaker._check_circuit_state(breaker, now)

        return {
            "breaker_id": breaker_id,
            "name": breaker["name"],
            "service_name": breaker["service_name"],
            "current_state": state,
            "enabled": breaker["enabled"],
            "consecutive_failures": breaker["consecutive_failures"],
            "consecutive_successes": breaker["consecutive_successes"],
            "failure_threshold": breaker["failure_threshold"],
            "success_threshold": breaker["success_threshold"],
            "total_calls": breaker["total_calls"],
            "successful_calls": breaker["successful_calls"],
            "failed_calls": breaker["failed_calls"],
            "rejected_calls": breaker["rejected_calls"],
            "success_rate": breaker["successful_calls"] / breaker["total_calls"] if breaker["total_calls"] > 0 else 0,
            "last_failure_at": breaker["last_failure_at"],
            "last_success_at": breaker["last_success_at"]
        }

    @staticmethod
    def reset_circuit_breaker(session, breaker_id: str) -> dict:
        """Manually reset circuit breaker to closed state"""
        breaker = CircuitBreaker._circuit_breakers.get(breaker_id)
        if not breaker:
            raise ValueError(f"Circuit breaker not found: {breaker_id}")

        now = datetime.utcnow()
        breaker["state"] = CircuitState.CLOSED
        breaker["consecutive_failures"] = 0
        breaker["consecutive_successes"] = 0
        breaker["updated_at"] = now.isoformat()

        return {
            "breaker_id": breaker_id,
            "state": breaker["state"],
            "reset_at": now.isoformat()
        }

    @staticmethod
    def list_circuit_breakers(
        session,
        service_name: Optional[str] = None,
        state: Optional[str] = None,
        enabled: Optional[bool] = None,
        limit: int = 50
    ) -> dict:
        """List circuit breakers with filtering"""
        breakers = list(CircuitBreaker._circuit_breakers.values())
        now = datetime.utcnow()

        # Update states
        for breaker in breakers:
            breaker["current_state"] = CircuitBreaker._check_circuit_state(breaker, now)

        # Apply filters
        if service_name:
            breakers = [b for b in breakers if b["service_name"] == service_name]
        if state:
            breakers = [b for b in breakers if b["current_state"] == state]
        if enabled is not None:
            breakers = [b for b in breakers if b["enabled"] == enabled]

        # Sort by created_at descending
        breakers.sort(key=lambda x: x["created_at"], reverse=True)

        # Apply limit
        breakers = breakers[:limit]

        return {
            "circuit_breakers": breakers,
            "total_breakers": len(CircuitBreaker._circuit_breakers),
            "returned_count": len(breakers)
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get circuit breaker statistics"""
        breakers = list(CircuitBreaker._circuit_breakers.values())
        policies = list(CircuitBreaker._retry_policies.values())
        handlers = list(CircuitBreaker._fallback_handlers.values())
        now = datetime.utcnow()

        # State distribution
        state_dist = defaultdict(int)
        for breaker in breakers:
            state = CircuitBreaker._check_circuit_state(breaker, now)
            state_dist[state] += 1

        # Service distribution
        service_dist = defaultdict(int)
        for breaker in breakers:
            service_dist[breaker["service_name"]] += 1

        # Aggregate metrics
        total_calls = sum(b["total_calls"] for b in breakers)
        total_successful = sum(b["successful_calls"] for b in breakers)
        total_failed = sum(b["failed_calls"] for b in breakers)
        total_rejected = sum(b["rejected_calls"] for b in breakers)

        return {
            "total_circuit_breakers": len(breakers),
            "enabled_breakers": len([b for b in breakers if b["enabled"]]),
            "state_distribution": dict(state_dist),
            "service_distribution": dict(service_dist),
            "total_calls": total_calls,
            "successful_calls": total_successful,
            "failed_calls": total_failed,
            "rejected_calls": total_rejected,
            "overall_success_rate": total_successful / total_calls if total_calls > 0 else 0,
            "retry_policies": len(policies),
            "fallback_handlers": len(handlers),
            "total_retries": sum(p["total_retries"] for p in policies),
            "total_fallback_invocations": sum(h["invocation_count"] for h in handlers)
        }

    # Helper methods
    @staticmethod
    def _check_circuit_state(breaker: dict, now: datetime) -> str:
        """Check and update circuit state based on current conditions"""
        current_state = breaker["state"]

        if current_state == CircuitState.OPEN:
            # Check if should transition to half-open
            if breaker["opened_at"]:
                opened_time = datetime.fromisoformat(breaker["opened_at"])
                reset_timeout = timedelta(seconds=breaker["reset_timeout_seconds"])
                if now >= opened_time + reset_timeout:
                    breaker["state"] = CircuitState.HALF_OPEN
                    breaker["half_opened_at"] = now.isoformat()
                    breaker["consecutive_successes"] = 0
                    return CircuitState.HALF_OPEN

        return breaker["state"]

    @staticmethod
    def _record_success(breaker: dict, now: datetime):
        """Record successful execution"""
        breaker["total_calls"] += 1
        breaker["successful_calls"] += 1
        breaker["consecutive_successes"] += 1
        breaker["consecutive_failures"] = 0
        breaker["last_success_at"] = now.isoformat()
        breaker["updated_at"] = now.isoformat()

        CircuitBreaker._circuit_metrics[breaker["id"]]["total_calls"] += 1
        CircuitBreaker._circuit_metrics[breaker["id"]]["successful_calls"] += 1

        # Check if should close circuit from half-open
        if breaker["state"] == CircuitState.HALF_OPEN:
            if breaker["consecutive_successes"] >= breaker["success_threshold"]:
                breaker["state"] = CircuitState.CLOSED
                breaker["consecutive_successes"] = 0

    @staticmethod
    def _record_failure(breaker: dict, now: datetime, error_type: Optional[str] = None):
        """Record failed execution"""
        breaker["total_calls"] += 1
        breaker["failed_calls"] += 1
        breaker["consecutive_failures"] += 1
        breaker["consecutive_successes"] = 0
        breaker["last_failure_at"] = now.isoformat()
        breaker["updated_at"] = now.isoformat()

        CircuitBreaker._circuit_metrics[breaker["id"]]["total_calls"] += 1
        CircuitBreaker._circuit_metrics[breaker["id"]]["failed_calls"] += 1

        # Check if should open circuit
        if breaker["state"] == CircuitState.CLOSED:
            if breaker["consecutive_failures"] >= breaker["failure_threshold"]:
                breaker["state"] = CircuitState.OPEN
                breaker["opened_at"] = now.isoformat()
        elif breaker["state"] == CircuitState.HALF_OPEN:
            # Any failure in half-open state reopens circuit
            breaker["state"] = CircuitState.OPEN
            breaker["opened_at"] = now.isoformat()

    @staticmethod
    def _execute_operation(operation: Callable) -> dict:
        """Execute operation and return result"""
        start_time = time.time()
        try:
            result = operation()
            elapsed_ms = (time.time() - start_time) * 1000
            return {
                "success": True,
                "result": result,
                "latency_ms": elapsed_ms
            }
        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return {
                "success": False,
                "error": str(e),
                "error_type": CircuitBreaker._classify_error(e),
                "latency_ms": elapsed_ms
            }

    @staticmethod
    def _execute_with_retry(operation: Callable, policy_id: str) -> dict:
        """Execute operation with retry policy"""
        policy = CircuitBreaker._retry_policies.get(policy_id)
        if not policy or not policy["enabled"]:
            return CircuitBreaker._execute_operation(operation)

        attempts = 0
        last_result = None

        while attempts < policy["max_attempts"]:
            attempts += 1
            result = CircuitBreaker._execute_operation(operation)

            if result["success"]:
                if attempts > 1:
                    policy["total_retries"] += (attempts - 1)
                    policy["successful_retries"] += 1
                    CircuitBreaker._circuit_metrics["retry"]["retry_attempts"] += (attempts - 1)
                return result

            last_result = result

            # Check if error is retryable
            error_type = result.get("error_type")
            if error_type not in policy["retryable_errors"]:
                break

            # Calculate delay
            if attempts < policy["max_attempts"]:
                delay_ms = CircuitBreaker._calculate_retry_delay(
                    policy["strategy"],
                    attempts,
                    policy["initial_delay_ms"],
                    policy["max_delay_ms"],
                    policy["backoff_multiplier"]
                )
                time.sleep(delay_ms / 1000)

        # All retries exhausted
        policy["total_retries"] += attempts - 1
        policy["exhausted_retries"] += 1
        return last_result

    @staticmethod
    def _execute_fallback(handler_id: str, metadata: Optional[dict]) -> dict:
        """Execute fallback handler"""
        handler = CircuitBreaker._fallback_handlers.get(handler_id)
        if not handler or not handler["enabled"]:
            return {"fallback_available": False}

        now = datetime.utcnow()
        handler["invocation_count"] += 1
        handler["last_invoked_at"] = now.isoformat()

        CircuitBreaker._circuit_metrics["fallback"]["fallback_calls"] += 1

        strategy = handler["strategy"]

        if strategy == FallbackStrategy.DEFAULT_VALUE:
            return {
                "fallback_available": True,
                "strategy": strategy,
                "value": handler["fallback_data"]
            }
        elif strategy == FallbackStrategy.CACHED_VALUE:
            # Simplified - would fetch from cache in production
            return {
                "fallback_available": True,
                "strategy": strategy,
                "value": handler["fallback_data"],
                "cached": True
            }
        elif strategy == FallbackStrategy.ALTERNATIVE_SERVICE:
            return {
                "fallback_available": True,
                "strategy": strategy,
                "alternative_service": handler["alternative_service"]
            }
        else:
            return {"fallback_available": False}

    @staticmethod
    def _calculate_retry_delay(
        strategy: str,
        attempt: int,
        initial_delay: int,
        max_delay: int,
        multiplier: float
    ) -> int:
        """Calculate retry delay based on strategy"""
        if strategy == RetryStrategy.FIXED:
            return min(initial_delay, max_delay)
        elif strategy == RetryStrategy.EXPONENTIAL:
            delay = initial_delay * (multiplier ** (attempt - 1))
            return min(int(delay), max_delay)
        elif strategy == RetryStrategy.LINEAR:
            delay = initial_delay * attempt
            return min(delay, max_delay)
        else:
            return initial_delay

    @staticmethod
    def _classify_error(error: Exception) -> str:
        """Classify error type"""
        error_str = str(error).lower()
        if "timeout" in error_str:
            return FailureType.TIMEOUT
        elif "connection" in error_str:
            return FailureType.CONNECTION_ERROR
        elif "rate limit" in error_str:
            return FailureType.RATE_LIMIT
        else:
            return FailureType.SERVICE_ERROR
