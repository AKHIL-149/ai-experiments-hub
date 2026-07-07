"""
Agent Communication Protocol API endpoints
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_communication_protocol import (
    AgentCommunicationProtocol,
    MessageType,
    MessagePriority,
    CommunicationProtocol
)
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class SendMessageRequest(BaseModel):
    """Request model for sending message"""
    from_agent_id: int = Field(..., description="Sender agent ID")
    to_agent_id: Optional[int] = Field(None, description="Recipient agent ID (None for broadcast)")
    message_type: str = Field(MessageType.NOTIFICATION, description="Message type")
    protocol: str = Field(CommunicationProtocol.DIRECT, description="Communication protocol")
    content: str = Field(..., description="Message content")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")
    priority: str = Field(MessagePriority.NORMAL, description="Message priority")
    requires_ack: bool = Field(False, description="Whether acknowledgment is required")
    topic: Optional[str] = Field(None, description="Optional topic for pub/sub")


class MarkReadRequest(BaseModel):
    """Request model for marking message read"""
    message_id: int = Field(..., description="Message ID")
    agent_id: int = Field(..., description="Agent ID")


class SendAckRequest(BaseModel):
    """Request model for sending acknowledgment"""
    original_message_id: int = Field(..., description="Original message ID")
    agent_id: int = Field(..., description="Agent ID sending ACK")
    ack_content: str = Field("Acknowledged", description="ACK content")


class SendRequestRequest(BaseModel):
    """Request model for sending request"""
    from_agent_id: int = Field(..., description="Requesting agent ID")
    to_agent_id: int = Field(..., description="Target agent ID")
    request_content: str = Field(..., description="Request content")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")
    timeout_seconds: int = Field(300, ge=1, description="Request timeout in seconds")


class SendReplyRequest(BaseModel):
    """Request model for sending reply"""
    request_message_id: int = Field(..., description="Original request message ID")
    from_agent_id: int = Field(..., description="Replying agent ID")
    reply_content: str = Field(..., description="Reply content")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Optional metadata")


class SubscribeRequest(BaseModel):
    """Request model for topic subscription"""
    agent_id: int = Field(..., description="Agent ID")
    topic: str = Field(..., description="Topic to subscribe to")


class UnsubscribeRequest(BaseModel):
    """Request model for topic unsubscription"""
    agent_id: int = Field(..., description="Agent ID")
    topic: str = Field(..., description="Topic to unsubscribe from")


# Endpoints

@router.post("/send")
async def send_message(
    request: SendMessageRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Send a message using specified protocol.

    Protocols:
    - **direct**: One-to-one message
    - **broadcast**: To all active agents
    - **multicast**: To specific group (specify recipient_ids in metadata)
    - **pubsub**: To topic subscribers
    - **request_reply**: Request expecting a reply

    Message types:
    - **request**: Request for action/information
    - **response**: Reply to a request
    - **broadcast**: General announcement
    - **notification**: Event notification
    - **command**: Command to execute
    - **query**: Query for information
    - **acknowledgment**: Acknowledgment of receipt
    """
    try:
        result = AgentCommunicationProtocol.send_message(
            session=db,
            from_agent_id=request.from_agent_id,
            to_agent_id=request.to_agent_id,
            message_type=request.message_type,
            protocol=request.protocol,
            content=request.content,
            metadata=request.metadata,
            priority=request.priority,
            requires_ack=request.requires_ack,
            topic=request.topic
        )

        return {
            "success": True,
            **result,
            "message": f"Message sent via {request.protocol} to {len(result['delivered_to'])} recipients"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to send message: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/{agent_id}/messages")
async def get_messages(
    agent_id: int,
    message_type: Optional[str] = Query(None, description="Filter by message type"),
    status: Optional[str] = Query(None, description="Filter by status"),
    from_agent_id: Optional[int] = Query(None, description="Filter by sender"),
    unread_only: bool = Query(False, description="Only unread messages"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum messages"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get messages for an agent.

    Returns messages from database and in-memory queue.
    Includes filtering by type, status, sender, and read status.
    """
    try:
        result = AgentCommunicationProtocol.get_messages(
            session=db,
            agent_id=agent_id,
            message_type=message_type,
            status=status,
            from_agent_id=from_agent_id,
            unread_only=unread_only,
            limit=limit
        )

        return {
            "success": True,
            **result,
            "message": f"Retrieved {result['total_messages']} messages"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get messages: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/mark-read")
async def mark_message_read(
    request: MarkReadRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Mark a message as read.

    Updates message status to 'read' and records read timestamp.
    """
    try:
        result = AgentCommunicationProtocol.mark_message_read(
            session=db,
            message_id=request.message_id,
            agent_id=request.agent_id
        )

        return {
            "success": True,
            **result,
            "message": "Message marked as read"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to mark message read: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/acknowledge")
async def send_acknowledgment(
    request: SendAckRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Send acknowledgment for a message.

    Sends an ACK message back to the original sender.
    Used for confirming message receipt.
    """
    try:
        result = AgentCommunicationProtocol.send_acknowledgment(
            session=db,
            original_message_id=request.original_message_id,
            agent_id=request.agent_id,
            ack_content=request.ack_content
        )

        return {
            "success": True,
            **result,
            "message": "Acknowledgment sent"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to send acknowledgment: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/request")
async def send_request(
    request: SendRequestRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Send a request and track it for reply.

    Uses request-reply protocol.
    Request is tracked until reply is received or timeout expires.
    """
    try:
        result = AgentCommunicationProtocol.send_request(
            session=db,
            from_agent_id=request.from_agent_id,
            to_agent_id=request.to_agent_id,
            request_content=request.request_content,
            metadata=request.metadata,
            timeout_seconds=request.timeout_seconds
        )

        return {
            "success": True,
            **result,
            "message": "Request sent and tracked"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to send request: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/reply")
async def send_reply(
    request: SendReplyRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Send a reply to a request.

    Replies are linked to the original request message.
    Marks the request as replied in the tracking system.
    """
    try:
        result = AgentCommunicationProtocol.send_reply(
            session=db,
            request_message_id=request.request_message_id,
            from_agent_id=request.from_agent_id,
            reply_content=request.reply_content,
            metadata=request.metadata
        )

        return {
            "success": True,
            **result,
            "message": "Reply sent"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to send reply: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/subscribe")
async def subscribe_to_topic(
    request: SubscribeRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Subscribe an agent to a topic.

    Agent will receive all messages published to this topic.
    Uses pub/sub protocol for message distribution.
    """
    try:
        result = AgentCommunicationProtocol.subscribe_to_topic(
            session=db,
            agent_id=request.agent_id,
            topic=request.topic
        )

        return {
            "success": True,
            **result
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to subscribe: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/unsubscribe")
async def unsubscribe_from_topic(
    request: UnsubscribeRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Unsubscribe an agent from a topic.

    Agent will no longer receive messages published to this topic.
    """
    try:
        result = AgentCommunicationProtocol.unsubscribe_from_topic(
            session=db,
            agent_id=request.agent_id,
            topic=request.topic
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        logger.error(f"Failed to unsubscribe: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/topics/{topic}/subscribers")
async def get_topic_subscribers(
    topic: str,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get subscribers for a topic.

    Returns list of agent IDs subscribed to the topic.
    """
    try:
        result = AgentCommunicationProtocol.get_topic_subscribers(
            session=db,
            topic=topic
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        logger.error(f"Failed to get subscribers: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/topics")
async def list_topics(
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    List all active topics.

    Returns topics with subscriber counts.
    Only includes topics with at least one subscriber.
    """
    try:
        result = AgentCommunicationProtocol.list_topics(session=db)

        return {
            "success": True,
            **result,
            "message": f"Found {result['total_topics']} active topics"
        }

    except Exception as e:
        logger.error(f"Failed to list topics: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/conversation/{agent1_id}/{agent2_id}")
async def get_conversation(
    agent1_id: int,
    agent2_id: int,
    limit: int = Query(50, ge=1, le=500, description="Maximum messages"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get conversation history between two agents.

    Returns messages exchanged between the two agents in chronological order.
    """
    try:
        result = AgentCommunicationProtocol.get_conversation(
            session=db,
            agent1_id=agent1_id,
            agent2_id=agent2_id,
            limit=limit
        )

        return {
            "success": True,
            **result,
            "message": f"Retrieved {result['message_count']} messages"
        }

    except Exception as e:
        logger.error(f"Failed to get conversation: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/stats")
async def get_communication_stats(
    agent_id: Optional[int] = Query(None, description="Optional agent ID filter"),
    hours: int = Query(24, ge=1, le=168, description="Time window in hours"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get communication statistics.

    Returns statistics on message volume, types, protocols, priorities, and statuses.
    Can be filtered by agent ID for agent-specific stats.
    """
    try:
        stats = AgentCommunicationProtocol.get_communication_stats(
            session=db,
            agent_id=agent_id,
            hours=hours
        )

        return {
            "success": True,
            "stats": stats,
            "message": f"Communication stats for last {hours} hours"
        }

    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/{agent_id}/clear-queue")
async def clear_message_queue(
    agent_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Clear message queue for an agent.

    Removes all queued messages from in-memory queue.
    Does not affect messages already in database.
    """
    try:
        result = AgentCommunicationProtocol.clear_message_queue(
            session=db,
            agent_id=agent_id
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        logger.error(f"Failed to clear queue: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/pending-requests")
async def get_pending_requests(
    agent_id: Optional[int] = Query(None, description="Optional agent ID filter"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get pending requests awaiting replies.

    Returns requests that haven't been replied to and haven't expired.
    Can be filtered by agent ID to show only that agent's pending requests.
    """
    try:
        result = AgentCommunicationProtocol.get_pending_requests(
            session=db,
            agent_id=agent_id
        )

        return {
            "success": True,
            **result,
            "message": f"Found {result['pending_count']} pending requests"
        }

    except Exception as e:
        logger.error(f"Failed to get pending requests: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/protocols")
async def list_protocols() -> Dict[str, Any]:
    """
    List all communication protocol types.

    Returns available protocols with descriptions.
    """
    protocols = [
        {
            "protocol": CommunicationProtocol.DIRECT,
            "description": "One-to-one direct messaging"
        },
        {
            "protocol": CommunicationProtocol.BROADCAST,
            "description": "Message to all active agents"
        },
        {
            "protocol": CommunicationProtocol.MULTICAST,
            "description": "Message to specific group of agents"
        },
        {
            "protocol": CommunicationProtocol.PUBSUB,
            "description": "Publish-subscribe topic-based messaging"
        },
        {
            "protocol": CommunicationProtocol.REQUEST_REPLY,
            "description": "Request-reply pattern with tracking"
        }
    ]

    return {
        "success": True,
        "total_protocols": len(protocols),
        "protocols": protocols,
        "message": "List of all communication protocols"
    }


@router.get("/message-types")
async def list_message_types() -> Dict[str, Any]:
    """
    List all message type constants.

    Returns available message types with descriptions.
    """
    types = [
        {
            "type": MessageType.REQUEST,
            "description": "Request for action or information"
        },
        {
            "type": MessageType.RESPONSE,
            "description": "Reply to a request"
        },
        {
            "type": MessageType.BROADCAST,
            "description": "General announcement to all"
        },
        {
            "type": MessageType.NOTIFICATION,
            "description": "Event notification"
        },
        {
            "type": MessageType.COMMAND,
            "description": "Command to execute"
        },
        {
            "type": MessageType.QUERY,
            "description": "Query for information"
        },
        {
            "type": MessageType.ACK,
            "description": "Acknowledgment of receipt"
        }
    ]

    return {
        "success": True,
        "total_types": len(types),
        "types": types,
        "message": "List of all message types"
    }
