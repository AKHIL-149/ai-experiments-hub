"""
API Gateway and Service Mesh Management Service

Provides API routing, service mesh configuration, request transformation,
circuit breaking, and traffic management at the gateway level.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from enum import Enum
import statistics
import re


class RouteMethod(str, Enum):
    """HTTP methods"""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"


class LoadBalancingStrategy(str, Enum):
    """Load balancing strategies"""
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    RANDOM = "random"
    WEIGHTED = "weighted"


class CircuitState(str, Enum):
    """Circuit breaker states"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class RouteStatus(str, Enum):
    """Route status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"


class APIGateway:
    """API Gateway and Service Mesh management"""

    # In-memory storage
    _routes: Dict[str, Dict] = {}
    _services: Dict[str, Dict] = {}
    _circuit_breakers: Dict[str, Dict] = {}
    _request_logs: List[Dict] = []
    _transformations: Dict[str, Dict] = {}
    _middleware: Dict[str, Dict] = {}
    _service_instances: Dict[str, List[Dict]] = defaultdict(list)

    @staticmethod
    def register_service(
        session,
        service_id: str,
        name: str,
        version: str,
        base_url: str,
        health_check_path: str = "/health",
        timeout_ms: int = 5000,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Register a backend service."""
        if service_id in APIGateway._services:
            raise ValueError(f"Service already registered: {service_id}")

        service = {
            "service_id": service_id,
            "name": name,
            "version": version,
            "base_url": base_url,
            "health_check_path": health_check_path,
            "timeout_ms": timeout_ms,
            "metadata": metadata or {},
            "registered_at": datetime.utcnow().isoformat(),
            "is_healthy": True,
            "last_health_check": None,
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "average_response_time_ms": 0.0
        }

        APIGateway._services[service_id] = service

        return service

    @staticmethod
    def create_route(
        session,
        route_id: str,
        path: str,
        method: RouteMethod,
        service_id: str,
        upstream_path: Optional[str] = None,
        version: Optional[str] = None,
        load_balancing: LoadBalancingStrategy = LoadBalancingStrategy.ROUND_ROBIN,
        rate_limit_per_minute: int = 0,
        require_auth: bool = False,
        enable_circuit_breaker: bool = True,
        description: Optional[str] = None
    ) -> dict:
        """Create an API route."""
        if route_id in APIGateway._routes:
            raise ValueError(f"Route already exists: {route_id}")

        # Validate service exists
        if service_id not in APIGateway._services:
            raise ValueError(f"Service not found: {service_id}")

        route = {
            "route_id": route_id,
            "path": path,
            "method": method,
            "service_id": service_id,
            "upstream_path": upstream_path or path,
            "version": version,
            "load_balancing": load_balancing,
            "rate_limit_per_minute": rate_limit_per_minute,
            "require_auth": require_auth,
            "enable_circuit_breaker": enable_circuit_breaker,
            "description": description or "",
            "status": RouteStatus.ACTIVE,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "average_latency_ms": 0.0,
            "current_rate": 0
        }

        APIGateway._routes[route_id] = route

        # Create circuit breaker if enabled
        if enable_circuit_breaker:
            APIGateway._create_circuit_breaker(route_id, service_id)

        return route

    @staticmethod
    def _create_circuit_breaker(route_id: str, service_id: str):
        """Create circuit breaker for a route."""
        breaker = {
            "breaker_id": f"cb_{route_id}",
            "route_id": route_id,
            "service_id": service_id,
            "state": CircuitState.CLOSED,
            "failure_threshold": 5,
            "success_threshold": 2,
            "timeout_seconds": 60,
            "consecutive_failures": 0,
            "consecutive_successes": 0,
            "last_failure": None,
            "opened_at": None,
            "half_open_at": None,
            "total_opens": 0
        }

        APIGateway._circuit_breakers[route_id] = breaker

    @staticmethod
    def route_request(
        session,
        route_id: str,
        request_data: Dict,
        headers: Optional[Dict] = None
    ) -> dict:
        """Route a request through the gateway."""
        route = APIGateway._routes.get(route_id)
        if not route:
            raise ValueError(f"Route not found: {route_id}")

        if route["status"] != RouteStatus.ACTIVE:
            raise ValueError(f"Route is not active: {route_id}")

        # Check rate limit
        if route["rate_limit_per_minute"] > 0:
            if not APIGateway._check_rate_limit(route):
                return {
                    "success": False,
                    "status_code": 429,
                    "error": "Rate limit exceeded"
                }

        # Check circuit breaker
        if route["enable_circuit_breaker"]:
            breaker = APIGateway._circuit_breakers.get(route_id)
            if breaker and breaker["state"] == CircuitState.OPEN:
                # Check if timeout has passed
                if breaker["opened_at"]:
                    opened = datetime.fromisoformat(breaker["opened_at"])
                    if datetime.utcnow() < opened + timedelta(seconds=breaker["timeout_seconds"]):
                        return {
                            "success": False,
                            "status_code": 503,
                            "error": "Circuit breaker is open"
                        }
                    else:
                        # Move to half-open
                        breaker["state"] = CircuitState.HALF_OPEN
                        breaker["half_open_at"] = datetime.utcnow().isoformat()

        # Get service
        service = APIGateway._services[route["service_id"]]

        # Log request
        request_log = {
            "log_id": f"req_{len(APIGateway._request_logs)}_{datetime.utcnow().timestamp()}",
            "route_id": route_id,
            "service_id": route["service_id"],
            "method": route["method"],
            "path": route["path"],
            "timestamp": datetime.utcnow().isoformat(),
            "headers": headers or {},
            "request_data": request_data,
            "response_status": None,
            "response_time_ms": None,
            "success": None
        }

        # Simulate request processing
        import random
        response_time_ms = random.uniform(50, 500)
        success = random.random() > 0.1  # 90% success rate

        request_log["response_time_ms"] = response_time_ms
        request_log["success"] = success
        request_log["response_status"] = 200 if success else 500

        APIGateway._request_logs.append(request_log)

        # Update stats
        route["total_requests"] += 1
        service["total_requests"] += 1

        if success:
            route["successful_requests"] += 1
            service["successful_requests"] += 1

            # Update circuit breaker
            if route["enable_circuit_breaker"]:
                APIGateway._record_circuit_success(route_id)
        else:
            route["failed_requests"] += 1
            service["failed_requests"] += 1

            # Update circuit breaker
            if route["enable_circuit_breaker"]:
                APIGateway._record_circuit_failure(route_id)

        # Update average latency
        recent_logs = [
            log for log in APIGateway._request_logs
            if log["route_id"] == route_id and log["success"]
        ][-100:]

        if recent_logs:
            route["average_latency_ms"] = statistics.mean(
                log["response_time_ms"] for log in recent_logs
            )

        # Keep only last 10000 logs
        APIGateway._request_logs = APIGateway._request_logs[-10000:]

        return {
            "success": success,
            "status_code": 200 if success else 500,
            "response_time_ms": response_time_ms,
            "service": service["name"],
            "version": service["version"]
        }

    @staticmethod
    def _check_rate_limit(route: dict) -> bool:
        """Check if route is within rate limit."""
        # Get requests in last minute
        one_minute_ago = (datetime.utcnow() - timedelta(minutes=1)).isoformat()

        recent_requests = sum(
            1 for log in APIGateway._request_logs
            if log["route_id"] == route["route_id"]
            and log["timestamp"] >= one_minute_ago
        )

        route["current_rate"] = recent_requests

        return recent_requests < route["rate_limit_per_minute"]

    @staticmethod
    def _record_circuit_success(route_id: str):
        """Record successful request for circuit breaker."""
        breaker = APIGateway._circuit_breakers.get(route_id)
        if not breaker:
            return

        breaker["consecutive_failures"] = 0
        breaker["consecutive_successes"] += 1

        # If in half-open and enough successes, close circuit
        if breaker["state"] == CircuitState.HALF_OPEN:
            if breaker["consecutive_successes"] >= breaker["success_threshold"]:
                breaker["state"] = CircuitState.CLOSED
                breaker["consecutive_successes"] = 0

    @staticmethod
    def _record_circuit_failure(route_id: str):
        """Record failed request for circuit breaker."""
        breaker = APIGateway._circuit_breakers.get(route_id)
        if not breaker:
            return

        breaker["consecutive_successes"] = 0
        breaker["consecutive_failures"] += 1
        breaker["last_failure"] = datetime.utcnow().isoformat()

        # Open circuit if threshold reached
        if breaker["state"] in [CircuitState.CLOSED, CircuitState.HALF_OPEN]:
            if breaker["consecutive_failures"] >= breaker["failure_threshold"]:
                breaker["state"] = CircuitState.OPEN
                breaker["opened_at"] = datetime.utcnow().isoformat()
                breaker["total_opens"] += 1
                breaker["consecutive_failures"] = 0

    @staticmethod
    def create_transformation(
        session,
        transformation_id: str,
        route_id: str,
        transform_type: str,
        config: Dict
    ) -> dict:
        """Create request/response transformation."""
        transformation = {
            "transformation_id": transformation_id,
            "route_id": route_id,
            "transform_type": transform_type,
            "config": config,
            "created_at": datetime.utcnow().isoformat(),
            "enabled": True
        }

        APIGateway._transformations[transformation_id] = transformation

        return transformation

    @staticmethod
    def register_service_instance(
        session,
        service_id: str,
        instance_id: str,
        host: str,
        port: int,
        weight: int = 1,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Register a service instance for load balancing."""
        if service_id not in APIGateway._services:
            raise ValueError(f"Service not found: {service_id}")

        instance = {
            "instance_id": instance_id,
            "service_id": service_id,
            "host": host,
            "port": port,
            "weight": weight,
            "metadata": metadata or {},
            "registered_at": datetime.utcnow().isoformat(),
            "is_healthy": True,
            "last_health_check": None,
            "request_count": 0
        }

        APIGateway._service_instances[service_id].append(instance)

        return instance

    @staticmethod
    def get_route_stats(session, route_id: str) -> dict:
        """Get statistics for a route."""
        route = APIGateway._routes.get(route_id)
        if not route:
            raise ValueError(f"Route not found: {route_id}")

        # Get circuit breaker status
        circuit_breaker = APIGateway._circuit_breakers.get(route_id)

        # Get recent error rate
        recent_logs = [
            log for log in APIGateway._request_logs
            if log["route_id"] == route_id
        ][-100:]

        error_rate = 0.0
        if recent_logs:
            errors = sum(1 for log in recent_logs if not log["success"])
            error_rate = (errors / len(recent_logs)) * 100

        return {
            "route_id": route_id,
            "path": route["path"],
            "method": route["method"],
            "status": route["status"],
            "total_requests": route["total_requests"],
            "successful_requests": route["successful_requests"],
            "failed_requests": route["failed_requests"],
            "success_rate": (route["successful_requests"] / route["total_requests"] * 100) if route["total_requests"] > 0 else 0,
            "error_rate": error_rate,
            "average_latency_ms": route["average_latency_ms"],
            "current_rate_per_minute": route["current_rate"],
            "rate_limit": route["rate_limit_per_minute"],
            "circuit_breaker": circuit_breaker,
            "checked_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_service_health(session, service_id: str) -> dict:
        """Get health status of a service."""
        service = APIGateway._services.get(service_id)
        if not service:
            raise ValueError(f"Service not found: {service_id}")

        # Get instances
        instances = APIGateway._service_instances.get(service_id, [])
        healthy_instances = sum(1 for i in instances if i["is_healthy"])

        # Get routes for this service
        service_routes = [
            r for r in APIGateway._routes.values()
            if r["service_id"] == service_id
        ]

        return {
            "service_id": service_id,
            "name": service["name"],
            "version": service["version"],
            "is_healthy": service["is_healthy"],
            "total_instances": len(instances),
            "healthy_instances": healthy_instances,
            "total_requests": service["total_requests"],
            "successful_requests": service["successful_requests"],
            "failed_requests": service["failed_requests"],
            "success_rate": (service["successful_requests"] / service["total_requests"] * 100) if service["total_requests"] > 0 else 0,
            "average_response_time_ms": service["average_response_time_ms"],
            "routes_count": len(service_routes),
            "last_health_check": service["last_health_check"],
            "checked_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_gateway_stats(session) -> dict:
        """Get overall gateway statistics."""
        total_routes = len(APIGateway._routes)
        active_routes = sum(1 for r in APIGateway._routes.values() if r["status"] == RouteStatus.ACTIVE)

        total_services = len(APIGateway._services)
        healthy_services = sum(1 for s in APIGateway._services.values() if s["is_healthy"])

        # Circuit breaker stats
        open_circuits = sum(
            1 for cb in APIGateway._circuit_breakers.values()
            if cb["state"] == CircuitState.OPEN
        )

        # Request stats (last hour)
        one_hour_ago = (datetime.utcnow() - timedelta(hours=1)).isoformat()
        recent_requests = [
            log for log in APIGateway._request_logs
            if log["timestamp"] >= one_hour_ago
        ]

        total_requests = len(recent_requests)
        successful_requests = sum(1 for log in recent_requests if log["success"])
        failed_requests = total_requests - successful_requests

        # Calculate average response time
        avg_response_time = 0.0
        if recent_requests:
            avg_response_time = statistics.mean(
                log["response_time_ms"] for log in recent_requests
                if log["response_time_ms"] is not None
            )

        return {
            "routes": {
                "total": total_routes,
                "active": active_routes,
                "inactive": total_routes - active_routes
            },
            "services": {
                "total": total_services,
                "healthy": healthy_services,
                "unhealthy": total_services - healthy_services
            },
            "circuit_breakers": {
                "total": len(APIGateway._circuit_breakers),
                "open": open_circuits,
                "closed": len(APIGateway._circuit_breakers) - open_circuits
            },
            "requests_last_hour": {
                "total": total_requests,
                "successful": successful_requests,
                "failed": failed_requests,
                "success_rate": (successful_requests / total_requests * 100) if total_requests > 0 else 0,
                "average_response_time_ms": avg_response_time
            },
            "total_request_logs": len(APIGateway._request_logs),
            "transformations": len(APIGateway._transformations),
            "service_instances": sum(len(instances) for instances in APIGateway._service_instances.values())
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get comprehensive API gateway statistics."""
        return APIGateway.get_gateway_stats(session)
