"""
Webhook Management and Event Notifications Service

Provides webhook registration, event delivery, retry logic, signature verification,
and comprehensive delivery tracking for external integrations.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict
from enum import Enum
import hashlib
import hmac
import random
import json


class WebhookStatus(str, Enum):
    """Webhook status"""
    ACTIVE = "active"
    PAUSED = "paused"
    FAILED = "failed"
    DISABLED = "disabled"


class EventType(str, Enum):
    """Event types"""
    TASK_CREATED = "task.created"
    TASK_UPDATED = "task.updated"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    AGENT_ASSIGNED = "agent.assigned"
    AGENT_COMPLETED = "agent.completed"
    APPROVAL_REQUESTED = "approval.requested"
    APPROVAL_GRANTED = "approval.granted"
    ERROR_OCCURRED = "error.occurred"
    CUSTOM = "custom"


class DeliveryStatus(str, Enum):
    """Delivery status"""
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class RetryStrategy(str, Enum):
    """Retry strategy"""
    EXPONENTIAL = "exponential"
    LINEAR = "linear"
    FIXED = "fixed"


class WebhookManagement:
    """Webhook Management and Event Notifications"""

    # In-memory storage
    _webhooks: Dict[str, Dict] = {}
    _deliveries: Dict[str, Dict] = {}
    _events: List[Dict] = []
    _subscriptions: Dict[str, List[str]] = defaultdict(list)  # event_type -> webhook_ids
    _delivery_logs: List[Dict] = []

    @staticmethod
    def register_webhook(
        session,
        webhook_id: str,
        url: str,
        event_types: List[EventType],
        description: Optional[str] = None,
        secret: Optional[str] = None,
        headers: Optional[Dict] = None,
        retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        max_retries: int = 3,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Register a webhook endpoint."""
        if webhook_id in WebhookManagement._webhooks:
            raise ValueError(f"Webhook already exists: {webhook_id}")

        # Generate secret if not provided
        if not secret:
            secret = hashlib.sha256(f"{webhook_id}{datetime.utcnow().timestamp()}".encode()).hexdigest()

        webhook = {
            "webhook_id": webhook_id,
            "url": url,
            "event_types": event_types,
            "description": description or "",
            "secret": secret,
            "headers": headers or {},
            "retry_strategy": retry_strategy,
            "max_retries": max_retries,
            "metadata": metadata or {},
            "status": WebhookStatus.ACTIVE,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "last_triggered": None,
            "total_deliveries": 0,
            "successful_deliveries": 0,
            "failed_deliveries": 0,
            "failure_count": 0,
            "last_failure": None
        }

        WebhookManagement._webhooks[webhook_id] = webhook

        # Register subscriptions
        for event_type in event_types:
            WebhookManagement._subscriptions[event_type].append(webhook_id)

        return webhook

    @staticmethod
    def trigger_event(
        session,
        event_type: EventType,
        payload: Dict,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Trigger an event and deliver to subscribed webhooks."""
        event = {
            "event_id": f"evt_{len(WebhookManagement._events)}_{datetime.utcnow().timestamp()}",
            "event_type": event_type,
            "payload": payload,
            "metadata": metadata or {},
            "timestamp": datetime.utcnow().isoformat(),
            "delivered_to": []
        }

        WebhookManagement._events.append(event)

        # Find subscribed webhooks
        subscribed_webhooks = WebhookManagement._subscriptions.get(event_type, [])

        # Deliver to each webhook
        delivery_results = []
        for webhook_id in subscribed_webhooks:
            webhook = WebhookManagement._webhooks.get(webhook_id)
            if webhook and webhook["status"] == WebhookStatus.ACTIVE:
                delivery = WebhookManagement._deliver_to_webhook(webhook, event)
                delivery_results.append(delivery)
                event["delivered_to"].append(webhook_id)

        # Keep only last 100000 events
        WebhookManagement._events = WebhookManagement._events[-100000:]

        return {
            "event": event,
            "deliveries": delivery_results,
            "webhook_count": len(delivery_results)
        }

    @staticmethod
    def _deliver_to_webhook(webhook: dict, event: dict) -> dict:
        """Deliver event to a webhook endpoint."""
        delivery_id = f"del_{len(WebhookManagement._deliveries)}_{datetime.utcnow().timestamp()}"

        # Prepare payload
        delivery_payload = {
            "event_id": event["event_id"],
            "event_type": event["event_type"],
            "timestamp": event["timestamp"],
            "data": event["payload"]
        }

        # Generate signature
        signature = WebhookManagement._generate_signature(
            webhook["secret"],
            json.dumps(delivery_payload)
        )

        # Simulate HTTP delivery
        success = random.random() > 0.05  # 95% success rate

        delivery = {
            "delivery_id": delivery_id,
            "webhook_id": webhook["webhook_id"],
            "event_id": event["event_id"],
            "url": webhook["url"],
            "payload": delivery_payload,
            "signature": signature,
            "status": DeliveryStatus.SUCCESS if success else DeliveryStatus.FAILED,
            "status_code": 200 if success else 500,
            "response_time_ms": random.uniform(50, 500),
            "attempt": 1,
            "max_attempts": webhook["max_retries"] + 1,
            "created_at": datetime.utcnow().isoformat(),
            "delivered_at": datetime.utcnow().isoformat() if success else None,
            "next_retry_at": None,
            "error_message": None if success else "Internal Server Error"
        }

        WebhookManagement._deliveries[delivery_id] = delivery

        # Update webhook stats
        webhook["total_deliveries"] += 1
        webhook["last_triggered"] = datetime.utcnow().isoformat()

        if success:
            webhook["successful_deliveries"] += 1
            webhook["failure_count"] = 0
        else:
            webhook["failed_deliveries"] += 1
            webhook["failure_count"] += 1
            webhook["last_failure"] = datetime.utcnow().isoformat()

            # Schedule retry if needed
            if delivery["attempt"] < delivery["max_attempts"]:
                delivery["status"] = DeliveryStatus.RETRYING
                delivery["next_retry_at"] = WebhookManagement._calculate_next_retry(
                    webhook["retry_strategy"],
                    delivery["attempt"]
                )

            # Pause webhook if too many failures
            if webhook["failure_count"] >= 10:
                webhook["status"] = WebhookStatus.FAILED

        # Log delivery
        WebhookManagement._log_delivery(delivery)

        return delivery

    @staticmethod
    def _generate_signature(secret: str, payload: str) -> str:
        """Generate HMAC signature for webhook payload."""
        return hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

    @staticmethod
    def verify_signature(webhook_id: str, payload: str, signature: str) -> bool:
        """Verify webhook signature."""
        webhook = WebhookManagement._webhooks.get(webhook_id)
        if not webhook:
            return False

        expected_signature = WebhookManagement._generate_signature(
            webhook["secret"],
            payload
        )

        return hmac.compare_digest(signature, expected_signature)

    @staticmethod
    def _calculate_next_retry(strategy: RetryStrategy, attempt: int) -> str:
        """Calculate next retry time based on strategy."""
        if strategy == RetryStrategy.EXPONENTIAL:
            delay_seconds = (2 ** attempt) * 60  # 2min, 4min, 8min, etc.
        elif strategy == RetryStrategy.LINEAR:
            delay_seconds = attempt * 300  # 5min, 10min, 15min, etc.
        else:  # FIXED
            delay_seconds = 300  # 5 minutes

        next_retry = datetime.utcnow() + timedelta(seconds=delay_seconds)
        return next_retry.isoformat()

    @staticmethod
    def retry_delivery(session, delivery_id: str) -> dict:
        """Retry a failed webhook delivery."""
        delivery = WebhookManagement._deliveries.get(delivery_id)
        if not delivery:
            raise ValueError(f"Delivery not found: {delivery_id}")

        if delivery["status"] == DeliveryStatus.SUCCESS:
            raise ValueError("Cannot retry successful delivery")

        webhook = WebhookManagement._webhooks[delivery["webhook_id"]]

        # Increment attempt
        delivery["attempt"] += 1

        # Simulate retry
        success = random.random() > 0.05

        delivery["status"] = DeliveryStatus.SUCCESS if success else DeliveryStatus.FAILED
        delivery["status_code"] = 200 if success else 500
        delivery["response_time_ms"] = random.uniform(50, 500)

        if success:
            delivery["delivered_at"] = datetime.utcnow().isoformat()
            delivery["next_retry_at"] = None
            webhook["successful_deliveries"] += 1
            webhook["failure_count"] = 0
        else:
            delivery["error_message"] = "Internal Server Error"
            webhook["failed_deliveries"] += 1

            # Schedule next retry if attempts remain
            if delivery["attempt"] < delivery["max_attempts"]:
                delivery["status"] = DeliveryStatus.RETRYING
                delivery["next_retry_at"] = WebhookManagement._calculate_next_retry(
                    webhook["retry_strategy"],
                    delivery["attempt"]
                )

        # Log retry
        WebhookManagement._log_delivery(delivery)

        return delivery

    @staticmethod
    def update_webhook(
        session,
        webhook_id: str,
        url: Optional[str] = None,
        event_types: Optional[List[EventType]] = None,
        status: Optional[WebhookStatus] = None,
        retry_strategy: Optional[RetryStrategy] = None,
        max_retries: Optional[int] = None
    ) -> dict:
        """Update webhook configuration."""
        webhook = WebhookManagement._webhooks.get(webhook_id)
        if not webhook:
            raise ValueError(f"Webhook not found: {webhook_id}")

        # Update fields
        if url is not None:
            webhook["url"] = url
        if event_types is not None:
            # Remove old subscriptions
            for event_type in webhook["event_types"]:
                if webhook_id in WebhookManagement._subscriptions[event_type]:
                    WebhookManagement._subscriptions[event_type].remove(webhook_id)

            # Add new subscriptions
            for event_type in event_types:
                WebhookManagement._subscriptions[event_type].append(webhook_id)

            webhook["event_types"] = event_types
        if status is not None:
            webhook["status"] = status
        if retry_strategy is not None:
            webhook["retry_strategy"] = retry_strategy
        if max_retries is not None:
            webhook["max_retries"] = max_retries

        webhook["updated_at"] = datetime.utcnow().isoformat()

        return webhook

    @staticmethod
    def test_webhook(session, webhook_id: str) -> dict:
        """Send a test event to a webhook."""
        webhook = WebhookManagement._webhooks.get(webhook_id)
        if not webhook:
            raise ValueError(f"Webhook not found: {webhook_id}")

        # Create test event
        test_event = {
            "event_id": f"test_{datetime.utcnow().timestamp()}",
            "event_type": "test.ping",
            "payload": {
                "message": "This is a test webhook delivery",
                "timestamp": datetime.utcnow().isoformat()
            },
            "metadata": {"test": True},
            "timestamp": datetime.utcnow().isoformat(),
            "delivered_to": [webhook_id]
        }

        # Deliver test event
        delivery = WebhookManagement._deliver_to_webhook(webhook, test_event)

        return {
            "test_event": test_event,
            "delivery": delivery,
            "message": "Test delivery sent"
        }

    @staticmethod
    def _log_delivery(delivery: dict):
        """Log webhook delivery."""
        log_entry = {
            "log_id": f"log_{len(WebhookManagement._delivery_logs)}",
            "delivery_id": delivery["delivery_id"],
            "webhook_id": delivery["webhook_id"],
            "event_id": delivery["event_id"],
            "status": delivery["status"],
            "status_code": delivery["status_code"],
            "attempt": delivery["attempt"],
            "response_time_ms": delivery["response_time_ms"],
            "timestamp": datetime.utcnow().isoformat()
        }

        WebhookManagement._delivery_logs.append(log_entry)

        # Keep only last 100000 logs
        WebhookManagement._delivery_logs = WebhookManagement._delivery_logs[-100000:]

    @staticmethod
    def get_webhook_stats(session, webhook_id: str) -> dict:
        """Get statistics for a webhook."""
        webhook = WebhookManagement._webhooks.get(webhook_id)
        if not webhook:
            raise ValueError(f"Webhook not found: {webhook_id}")

        # Get recent deliveries
        webhook_deliveries = [
            d for d in WebhookManagement._deliveries.values()
            if d["webhook_id"] == webhook_id
        ]

        # Calculate success rate
        total = len(webhook_deliveries)
        successful = sum(1 for d in webhook_deliveries if d["status"] == DeliveryStatus.SUCCESS)

        # Get response time stats
        response_times = [d["response_time_ms"] for d in webhook_deliveries if d["status"] == DeliveryStatus.SUCCESS]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0

        return {
            "webhook_id": webhook_id,
            "url": webhook["url"],
            "status": webhook["status"],
            "event_types": webhook["event_types"],
            "total_deliveries": total,
            "successful_deliveries": successful,
            "failed_deliveries": total - successful,
            "success_rate": (successful / total * 100) if total > 0 else 0,
            "average_response_time_ms": avg_response_time,
            "last_triggered": webhook["last_triggered"],
            "last_failure": webhook["last_failure"],
            "current_failure_count": webhook["failure_count"],
            "analyzed_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_delivery_history(
        session,
        webhook_id: Optional[str] = None,
        event_type: Optional[EventType] = None,
        status: Optional[DeliveryStatus] = None,
        limit: int = 100
    ) -> List[dict]:
        """Get delivery history with optional filters."""
        deliveries = list(WebhookManagement._deliveries.values())

        # Apply filters
        if webhook_id:
            deliveries = [d for d in deliveries if d["webhook_id"] == webhook_id]
        if event_type:
            # Get event IDs for this event type
            event_ids = [
                e["event_id"] for e in WebhookManagement._events
                if e["event_type"] == event_type
            ]
            deliveries = [d for d in deliveries if d["event_id"] in event_ids]
        if status:
            deliveries = [d for d in deliveries if d["status"] == status]

        # Sort by created_at descending
        deliveries.sort(key=lambda x: x["created_at"], reverse=True)

        return deliveries[:limit]

    @staticmethod
    def get_statistics(session) -> dict:
        """Get comprehensive webhook management statistics."""
        total_webhooks = len(WebhookManagement._webhooks)
        active_webhooks = sum(
            1 for w in WebhookManagement._webhooks.values()
            if w["status"] == WebhookStatus.ACTIVE
        )

        total_deliveries = len(WebhookManagement._deliveries)
        successful_deliveries = sum(
            1 for d in WebhookManagement._deliveries.values()
            if d["status"] == DeliveryStatus.SUCCESS
        )
        failed_deliveries = sum(
            1 for d in WebhookManagement._deliveries.values()
            if d["status"] == DeliveryStatus.FAILED
        )

        # Recent activity (last 24 hours)
        one_day_ago = (datetime.utcnow() - timedelta(hours=24)).isoformat()
        recent_events = sum(
            1 for e in WebhookManagement._events
            if e["timestamp"] >= one_day_ago
        )
        recent_deliveries = sum(
            1 for d in WebhookManagement._deliveries.values()
            if d["created_at"] >= one_day_ago
        )

        return {
            "webhooks": {
                "total": total_webhooks,
                "active": active_webhooks,
                "paused": sum(1 for w in WebhookManagement._webhooks.values() if w["status"] == WebhookStatus.PAUSED),
                "failed": sum(1 for w in WebhookManagement._webhooks.values() if w["status"] == WebhookStatus.FAILED)
            },
            "events": {
                "total": len(WebhookManagement._events),
                "recent_24h": recent_events
            },
            "deliveries": {
                "total": total_deliveries,
                "successful": successful_deliveries,
                "failed": failed_deliveries,
                "success_rate": (successful_deliveries / total_deliveries * 100) if total_deliveries > 0 else 0,
                "recent_24h": recent_deliveries
            },
            "subscriptions": {
                "total": sum(len(subs) for subs in WebhookManagement._subscriptions.values())
            }
        }
