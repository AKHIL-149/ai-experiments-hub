"""
Event Streaming and Message Bus

Provides real-time event distribution, pub/sub messaging, and stream processing.
"""

from typing import Optional, List, Dict, Any, Callable
from datetime import datetime, timedelta
from collections import defaultdict, deque
import uuid
import json


class MessageType:
    """Message types"""
    EVENT = "event"
    COMMAND = "command"
    QUERY = "query"
    RESPONSE = "response"
    NOTIFICATION = "notification"


class DeliveryGuarantee:
    """Delivery guarantees"""
    AT_MOST_ONCE = "at_most_once"
    AT_LEAST_ONCE = "at_least_once"
    EXACTLY_ONCE = "exactly_once"


class MessageStatus:
    """Message status"""
    PENDING = "pending"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class ConsumerGroupStrategy:
    """Consumer group strategies"""
    ROUND_ROBIN = "round_robin"
    STICKY = "sticky"
    RANGE = "range"


class EventStreaming:
    """Event Streaming and Message Bus service"""

    # In-memory storage
    _topics = {}
    _messages = {}
    _subscriptions = {}
    _consumer_groups = {}
    _message_queues = defaultdict(lambda: deque(maxlen=10000))
    _dead_letter_queue = deque(maxlen=1000)
    _offsets = defaultdict(lambda: defaultdict(int))
    _topic_metrics = defaultdict(lambda: {
        "total_messages": 0,
        "total_bytes": 0,
        "messages_per_second": 0,
        "consumers": 0,
        "producers": 0
    })

    @staticmethod
    def create_topic(
        session,
        name: str,
        partitions: int = 1,
        retention_hours: int = 168,  # 7 days
        max_message_size_bytes: int = 1048576,  # 1MB
        description: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create a message topic.

        Args:
            session: Database session
            name: Topic name
            partitions: Number of partitions
            retention_hours: Message retention period
            max_message_size_bytes: Maximum message size
            description: Topic description
            metadata: Additional metadata

        Returns:
            Created topic
        """
        if name in EventStreaming._topics:
            raise ValueError(f"Topic already exists: {name}")

        topic_id = f"topic_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        topic = {
            "id": topic_id,
            "name": name,
            "partitions": partitions,
            "retention_hours": retention_hours,
            "retention_bytes": None,
            "max_message_size_bytes": max_message_size_bytes,
            "description": description,
            "created_at": now.isoformat(),
            "message_count": 0,
            "total_bytes": 0,
            "subscriber_count": 0,
            "metadata": metadata or {}
        }

        EventStreaming._topics[name] = topic

        # Initialize partitions
        for i in range(partitions):
            partition_key = f"{name}:{i}"
            EventStreaming._message_queues[partition_key] = deque(maxlen=10000)

        return topic

    @staticmethod
    def publish_message(
        session,
        topic: str,
        message_type: str,
        payload: dict,
        key: Optional[str] = None,
        partition: Optional[int] = None,
        headers: Optional[dict] = None,
        ttl_seconds: Optional[int] = None
    ) -> dict:
        """
        Publish a message to a topic.

        Args:
            session: Database session
            topic: Topic name
            message_type: Type of message
            payload: Message payload
            key: Optional message key for partitioning
            partition: Optional specific partition
            headers: Optional message headers
            ttl_seconds: Optional time-to-live

        Returns:
            Published message
        """
        topic_obj = EventStreaming._topics.get(topic)
        if not topic_obj:
            raise ValueError(f"Topic not found: {topic}")

        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # Calculate partition
        if partition is None:
            if key:
                partition = hash(key) % topic_obj["partitions"]
            else:
                partition = hash(message_id) % topic_obj["partitions"]

        # Create message
        message_data = json.dumps(payload).encode()
        message_size = len(message_data)

        if message_size > topic_obj["max_message_size_bytes"]:
            raise ValueError(f"Message size {message_size} exceeds maximum {topic_obj['max_message_size_bytes']}")

        message = {
            "id": message_id,
            "topic": topic,
            "partition": partition,
            "message_type": message_type,
            "payload": payload,
            "key": key,
            "headers": headers or {},
            "size_bytes": message_size,
            "published_at": now.isoformat(),
            "expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat() if ttl_seconds else None,
            "status": MessageStatus.PENDING,
            "delivery_count": 0,
            "acknowledged_by": []
        }

        # Add to partition queue
        partition_key = f"{topic}:{partition}"
        EventStreaming._message_queues[partition_key].append(message)
        EventStreaming._messages[message_id] = message

        # Update topic metrics
        topic_obj["message_count"] += 1
        topic_obj["total_bytes"] += message_size
        EventStreaming._topic_metrics[topic]["total_messages"] += 1
        EventStreaming._topic_metrics[topic]["total_bytes"] += message_size

        # Deliver to subscribers
        EventStreaming._deliver_to_subscribers(topic, message)

        return message

    @staticmethod
    def subscribe(
        session,
        topic: str,
        subscriber_id: str,
        consumer_group: Optional[str] = None,
        auto_acknowledge: bool = True,
        filter_expression: Optional[str] = None
    ) -> dict:
        """
        Subscribe to a topic.

        Args:
            session: Database session
            topic: Topic name
            subscriber_id: Subscriber identifier
            consumer_group: Optional consumer group
            auto_acknowledge: Whether to auto-acknowledge messages
            filter_expression: Optional message filter

        Returns:
            Subscription
        """
        topic_obj = EventStreaming._topics.get(topic)
        if not topic_obj:
            raise ValueError(f"Topic not found: {topic}")

        subscription_id = f"sub_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        subscription = {
            "id": subscription_id,
            "topic": topic,
            "subscriber_id": subscriber_id,
            "consumer_group": consumer_group,
            "auto_acknowledge": auto_acknowledge,
            "filter_expression": filter_expression,
            "subscribed_at": now.isoformat(),
            "last_message_at": None,
            "messages_received": 0,
            "messages_acknowledged": 0,
            "offset": 0
        }

        EventStreaming._subscriptions[subscription_id] = subscription
        topic_obj["subscriber_count"] += 1
        EventStreaming._topic_metrics[topic]["consumers"] += 1

        # Add to consumer group if specified
        if consumer_group:
            if consumer_group not in EventStreaming._consumer_groups:
                EventStreaming._consumer_groups[consumer_group] = {
                    "group_id": consumer_group,
                    "topic": topic,
                    "strategy": ConsumerGroupStrategy.ROUND_ROBIN,
                    "members": [],
                    "created_at": now.isoformat()
                }
            EventStreaming._consumer_groups[consumer_group]["members"].append(subscription_id)

        return subscription

    @staticmethod
    def unsubscribe(session, subscription_id: str) -> dict:
        """
        Unsubscribe from a topic.

        Args:
            session: Database session
            subscription_id: Subscription ID

        Returns:
            Unsubscription result
        """
        subscription = EventStreaming._subscriptions.get(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription not found: {subscription_id}")

        topic = subscription["topic"]
        topic_obj = EventStreaming._topics.get(topic)

        # Remove from consumer group
        if subscription["consumer_group"]:
            group = EventStreaming._consumer_groups.get(subscription["consumer_group"])
            if group and subscription_id in group["members"]:
                group["members"].remove(subscription_id)

        # Update metrics
        if topic_obj:
            topic_obj["subscriber_count"] -= 1
            EventStreaming._topic_metrics[topic]["consumers"] -= 1

        # Remove subscription
        del EventStreaming._subscriptions[subscription_id]

        return {
            "subscription_id": subscription_id,
            "topic": topic,
            "unsubscribed_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def consume_messages(
        session,
        subscription_id: str,
        max_messages: int = 10,
        timeout_seconds: int = 30
    ) -> dict:
        """
        Consume messages from a subscription.

        Args:
            session: Database session
            subscription_id: Subscription ID
            max_messages: Maximum messages to return
            timeout_seconds: Timeout for waiting

        Returns:
            Consumed messages
        """
        subscription = EventStreaming._subscriptions.get(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription not found: {subscription_id}")

        topic = subscription["topic"]
        topic_obj = EventStreaming._topics.get(topic)
        if not topic_obj:
            raise ValueError(f"Topic not found: {topic}")

        messages = []
        now = datetime.utcnow()

        # Get messages from all partitions
        for partition in range(topic_obj["partitions"]):
            partition_key = f"{topic}:{partition}"
            queue = EventStreaming._message_queues[partition_key]
            offset = EventStreaming._offsets[subscription_id][partition]

            # Get messages starting from offset
            available = list(queue)[offset:]
            for msg in available[:max_messages - len(messages)]:
                # Apply filter if specified
                if subscription["filter_expression"]:
                    # Simplified filter (would use actual expression evaluation in production)
                    if not EventStreaming._matches_filter(msg, subscription["filter_expression"]):
                        continue

                # Check if expired
                if msg.get("expires_at"):
                    expires_at = datetime.fromisoformat(msg["expires_at"])
                    if now >= expires_at:
                        continue

                messages.append(msg)
                msg["delivery_count"] += 1

                # Auto-acknowledge if enabled
                if subscription["auto_acknowledge"]:
                    msg["status"] = MessageStatus.ACKNOWLEDGED
                    msg["acknowledged_by"].append(subscription_id)
                    subscription["messages_acknowledged"] += 1
                else:
                    msg["status"] = MessageStatus.DELIVERED

                # Update offset
                EventStreaming._offsets[subscription_id][partition] = offset + 1

            if len(messages) >= max_messages:
                break

        # Update subscription
        subscription["messages_received"] += len(messages)
        if messages:
            subscription["last_message_at"] = now.isoformat()

        return {
            "subscription_id": subscription_id,
            "topic": topic,
            "messages": messages,
            "message_count": len(messages),
            "consumed_at": now.isoformat()
        }

    @staticmethod
    def acknowledge_message(
        session,
        subscription_id: str,
        message_id: str
    ) -> dict:
        """
        Acknowledge a message.

        Args:
            session: Database session
            subscription_id: Subscription ID
            message_id: Message ID

        Returns:
            Acknowledgment result
        """
        subscription = EventStreaming._subscriptions.get(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription not found: {subscription_id}")

        message = EventStreaming._messages.get(message_id)
        if not message:
            raise ValueError(f"Message not found: {message_id}")

        now = datetime.utcnow()

        message["status"] = MessageStatus.ACKNOWLEDGED
        message["acknowledged_by"].append(subscription_id)
        message["acknowledged_at"] = now.isoformat()

        subscription["messages_acknowledged"] += 1

        return {
            "message_id": message_id,
            "subscription_id": subscription_id,
            "acknowledged_at": now.isoformat()
        }

    @staticmethod
    def move_to_dead_letter(
        session,
        message_id: str,
        reason: str
    ) -> dict:
        """
        Move message to dead letter queue.

        Args:
            session: Database session
            message_id: Message ID
            reason: Reason for moving to DLQ

        Returns:
            Dead letter record
        """
        message = EventStreaming._messages.get(message_id)
        if not message:
            raise ValueError(f"Message not found: {message_id}")

        now = datetime.utcnow()

        dead_letter = {
            "message_id": message_id,
            "original_message": message,
            "reason": reason,
            "moved_at": now.isoformat()
        }

        message["status"] = MessageStatus.DEAD_LETTER
        EventStreaming._dead_letter_queue.append(dead_letter)

        return dead_letter

    @staticmethod
    def list_topics(
        session,
        limit: int = 50
    ) -> dict:
        """List all topics"""
        topics = list(EventStreaming._topics.values())
        topics.sort(key=lambda x: x["created_at"], reverse=True)
        topics = topics[:limit]

        return {
            "topics": topics,
            "total_topics": len(EventStreaming._topics),
            "returned_count": len(topics)
        }

    @staticmethod
    def get_topic_statistics(session, topic: str) -> dict:
        """Get topic statistics"""
        topic_obj = EventStreaming._topics.get(topic)
        if not topic_obj:
            raise ValueError(f"Topic not found: {topic}")

        metrics = EventStreaming._topic_metrics[topic]

        # Calculate partition statistics
        partition_stats = []
        for i in range(topic_obj["partitions"]):
            partition_key = f"{topic}:{i}"
            queue = EventStreaming._message_queues[partition_key]
            partition_stats.append({
                "partition": i,
                "message_count": len(queue),
                "oldest_offset": 0,
                "newest_offset": len(queue) - 1 if queue else 0
            })

        return {
            "topic": topic,
            "message_count": topic_obj["message_count"],
            "total_bytes": topic_obj["total_bytes"],
            "subscriber_count": topic_obj["subscriber_count"],
            "partitions": topic_obj["partitions"],
            "partition_statistics": partition_stats,
            "total_messages": metrics["total_messages"],
            "consumers": metrics["consumers"],
            "producers": metrics["producers"]
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get event streaming statistics"""
        topics = list(EventStreaming._topics.values())
        subscriptions = list(EventStreaming._subscriptions.values())
        total_messages = sum(t["message_count"] for t in topics)
        total_bytes = sum(t["total_bytes"] for t in topics)

        # Consumer group stats
        active_groups = len(EventStreaming._consumer_groups)

        # Message status distribution
        status_dist = defaultdict(int)
        for msg in EventStreaming._messages.values():
            status_dist[msg["status"]] += 1

        return {
            "total_topics": len(topics),
            "total_subscriptions": len(subscriptions),
            "total_messages": total_messages,
            "total_bytes": total_bytes,
            "active_consumer_groups": active_groups,
            "dead_letter_queue_size": len(EventStreaming._dead_letter_queue),
            "message_status_distribution": dict(status_dist),
            "average_messages_per_topic": total_messages / len(topics) if topics else 0
        }

    # Helper methods
    @staticmethod
    def _deliver_to_subscribers(topic: str, message: dict):
        """Deliver message to topic subscribers"""
        for subscription in EventStreaming._subscriptions.values():
            if subscription["topic"] == topic:
                # Apply filter
                if subscription["filter_expression"]:
                    if not EventStreaming._matches_filter(message, subscription["filter_expression"]):
                        continue

                subscription["messages_received"] += 1

    @staticmethod
    def _matches_filter(message: dict, filter_expression: str) -> bool:
        """Check if message matches filter expression (simplified)"""
        # In production, would use actual expression parser
        return True
