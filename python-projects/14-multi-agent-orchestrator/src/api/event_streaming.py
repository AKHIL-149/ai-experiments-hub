"""
Event Streaming and Message Bus API

REST API endpoints for event streaming, pub/sub messaging, and message queuing.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.event_streaming import (
    EventStreaming,
    MessageType,
    DeliveryGuarantee,
    MessageStatus,
    ConsumerGroupStrategy
)


router = APIRouter()


# Request/Response Models
class CreateTopicRequest(BaseModel):
    name: str = Field(..., description="Topic name")
    partitions: int = Field(1, description="Number of partitions")
    retention_hours: int = Field(168, description="Message retention period in hours")
    max_message_size_bytes: int = Field(1048576, description="Maximum message size in bytes")
    description: Optional[str] = Field(None, description="Topic description")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class PublishMessageRequest(BaseModel):
    message_type: str = Field(..., description="Type of message")
    payload: dict = Field(..., description="Message payload")
    key: Optional[str] = Field(None, description="Optional message key for partitioning")
    partition: Optional[int] = Field(None, description="Optional specific partition")
    headers: Optional[dict] = Field(None, description="Optional message headers")
    ttl_seconds: Optional[int] = Field(None, description="Optional time-to-live")


class SubscribeRequest(BaseModel):
    subscriber_id: str = Field(..., description="Subscriber identifier")
    consumer_group: Optional[str] = Field(None, description="Optional consumer group")
    auto_acknowledge: bool = Field(True, description="Whether to auto-acknowledge messages")
    filter_expression: Optional[str] = Field(None, description="Optional message filter")


class ConsumeMessagesRequest(BaseModel):
    max_messages: int = Field(10, description="Maximum messages to return")
    timeout_seconds: int = Field(30, description="Timeout for waiting")


class AcknowledgeMessageRequest(BaseModel):
    subscription_id: str = Field(..., description="Subscription ID")


class MoveToDeadLetterRequest(BaseModel):
    reason: str = Field(..., description="Reason for moving to DLQ")


@router.post("/topics")
def create_topic(
    request: CreateTopicRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a message topic.

    Creates a new topic for publishing and subscribing to messages
    with configurable partitions and retention.
    """
    try:
        topic = EventStreaming.create_topic(
            session=session,
            name=request.name,
            partitions=request.partitions,
            retention_hours=request.retention_hours,
            max_message_size_bytes=request.max_message_size_bytes,
            description=request.description,
            metadata=request.metadata
        )

        return {
            "success": True,
            "topic": topic,
            "message": f"Topic created: {topic['name']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/topics/{topic}/publish")
def publish_message(
    topic: str,
    request: PublishMessageRequest,
    session: Session = Depends(get_db_session)
):
    """
    Publish a message to a topic.

    Publishes a message to the specified topic with optional
    partitioning and headers.
    """
    try:
        message = EventStreaming.publish_message(
            session=session,
            topic=topic,
            message_type=request.message_type,
            payload=request.payload,
            key=request.key,
            partition=request.partition,
            headers=request.headers,
            ttl_seconds=request.ttl_seconds
        )

        return {
            "success": True,
            "message": message,
            "message_text": f"Message published: {message['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/topics/{topic}/subscribe")
def subscribe_to_topic(
    topic: str,
    request: SubscribeRequest,
    session: Session = Depends(get_db_session)
):
    """
    Subscribe to a topic.

    Creates a subscription to receive messages from the topic
    with optional consumer group and filtering.
    """
    try:
        subscription = EventStreaming.subscribe(
            session=session,
            topic=topic,
            subscriber_id=request.subscriber_id,
            consumer_group=request.consumer_group,
            auto_acknowledge=request.auto_acknowledge,
            filter_expression=request.filter_expression
        )

        return {
            "success": True,
            "subscription": subscription,
            "message": f"Subscribed to topic: {topic}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/subscriptions/{subscription_id}")
def unsubscribe(
    subscription_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Unsubscribe from a topic.

    Removes a subscription and stops receiving messages.
    """
    try:
        result = EventStreaming.unsubscribe(
            session=session,
            subscription_id=subscription_id
        )

        return {
            "success": True,
            **result,
            "message": f"Unsubscribed: {subscription_id}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subscriptions/{subscription_id}/consume")
def consume_messages(
    subscription_id: str,
    request: ConsumeMessagesRequest,
    session: Session = Depends(get_db_session)
):
    """
    Consume messages from a subscription.

    Retrieves messages from the subscription with optional
    batching and timeout.
    """
    try:
        result = EventStreaming.consume_messages(
            session=session,
            subscription_id=subscription_id,
            max_messages=request.max_messages,
            timeout_seconds=request.timeout_seconds
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/messages/{message_id}/acknowledge")
def acknowledge_message(
    message_id: str,
    request: AcknowledgeMessageRequest,
    session: Session = Depends(get_db_session)
):
    """
    Acknowledge a message.

    Marks a message as successfully processed by a subscriber.
    """
    try:
        result = EventStreaming.acknowledge_message(
            session=session,
            subscription_id=request.subscription_id,
            message_id=message_id
        )

        return {
            "success": True,
            **result,
            "message": "Message acknowledged"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/messages/{message_id}/dead-letter")
def move_to_dead_letter(
    message_id: str,
    request: MoveToDeadLetterRequest,
    session: Session = Depends(get_db_session)
):
    """
    Move message to dead letter queue.

    Moves a failed message to the dead letter queue for
    manual inspection or reprocessing.
    """
    try:
        result = EventStreaming.move_to_dead_letter(
            session=session,
            message_id=message_id,
            reason=request.reason
        )

        return {
            "success": True,
            "dead_letter": result,
            "message": "Message moved to dead letter queue"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/topics")
def list_topics(
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    List all topics.

    Returns all message topics with their configurations
    and statistics.
    """
    try:
        result = EventStreaming.list_topics(
            session=session,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/topics/{topic}/statistics")
def get_topic_statistics(
    topic: str,
    session: Session = Depends(get_db_session)
):
    """
    Get topic statistics.

    Returns detailed statistics for a topic including
    message counts, partition info, and subscriber counts.
    """
    try:
        stats = EventStreaming.get_topic_statistics(
            session=session,
            topic=topic
        )

        return {
            "success": True,
            "statistics": stats
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
    Get event streaming statistics.

    Returns aggregate metrics including total topics,
    subscriptions, messages, and consumer groups.
    """
    try:
        stats = EventStreaming.get_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/message-types")
def list_message_types():
    """
    List all message types.

    Returns all available message type options.
    """
    return {
        "success": True,
        "message_types": [
            {"type": MessageType.EVENT, "description": "Event message"},
            {"type": MessageType.COMMAND, "description": "Command message"},
            {"type": MessageType.QUERY, "description": "Query message"},
            {"type": MessageType.RESPONSE, "description": "Response message"},
            {"type": MessageType.NOTIFICATION, "description": "Notification message"}
        ]
    }


@router.get("/delivery-guarantees")
def list_delivery_guarantees():
    """
    List all delivery guarantees.

    Returns all available delivery guarantee options.
    """
    return {
        "success": True,
        "delivery_guarantees": [
            {"guarantee": DeliveryGuarantee.AT_MOST_ONCE, "description": "At most once delivery"},
            {"guarantee": DeliveryGuarantee.AT_LEAST_ONCE, "description": "At least once delivery"},
            {"guarantee": DeliveryGuarantee.EXACTLY_ONCE, "description": "Exactly once delivery"}
        ]
    }


@router.get("/message-statuses")
def list_message_statuses():
    """
    List all message statuses.

    Returns all possible message status values.
    """
    return {
        "success": True,
        "message_statuses": [
            {"status": MessageStatus.PENDING, "description": "Message pending delivery"},
            {"status": MessageStatus.DELIVERED, "description": "Message delivered"},
            {"status": MessageStatus.ACKNOWLEDGED, "description": "Message acknowledged"},
            {"status": MessageStatus.FAILED, "description": "Message delivery failed"},
            {"status": MessageStatus.DEAD_LETTER, "description": "Message in dead letter queue"}
        ]
    }


@router.get("/consumer-group-strategies")
def list_consumer_group_strategies():
    """
    List all consumer group strategies.

    Returns all available consumer group distribution strategies.
    """
    return {
        "success": True,
        "consumer_group_strategies": [
            {"strategy": ConsumerGroupStrategy.ROUND_ROBIN, "description": "Round-robin distribution"},
            {"strategy": ConsumerGroupStrategy.STICKY, "description": "Sticky assignment"},
            {"strategy": ConsumerGroupStrategy.RANGE, "description": "Range-based assignment"}
        ]
    }
