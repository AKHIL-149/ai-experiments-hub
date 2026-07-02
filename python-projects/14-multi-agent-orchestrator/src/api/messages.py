"""
Agent messaging API endpoints
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_communication import AgentCommunicationService
from src.models.agent_message import MessageType, MessagePriority, MessageStatus
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class SendMessageRequest(BaseModel):
    """Request model for sending a message"""
    receiver_agent_id: Optional[int] = None  # None for broadcast
    content: str
    message_type: str = "notification"
    priority: str = "normal"
    subject: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    workflow_id: Optional[str] = None
    task_id: Optional[int] = None
    thread_id: Optional[str] = None
    requires_response: bool = False
    response_timeout_seconds: Optional[int] = None
    expires_in_seconds: Optional[int] = None

    class Config:
        schema_extra = {
            "example": {
                "receiver_agent_id": 2,
                "content": "Please analyze the user authentication requirements",
                "message_type": "request",
                "priority": "high",
                "subject": "Auth requirements analysis",
                "requires_response": True,
                "response_timeout_seconds": 300
            }
        }


class SendResponseRequest(BaseModel):
    """Request model for sending a response"""
    content: str
    payload: Optional[Dict[str, Any]] = None

    class Config:
        schema_extra = {
            "example": {
                "content": "Analysis complete. Recommending JWT with refresh tokens.",
                "payload": {
                    "recommendation": "JWT",
                    "reasoning": "Industry standard, stateless, scalable"
                }
            }
        }


class MessageResponse(BaseModel):
    """Response model for message"""
    id: int
    sender_agent_id: int
    receiver_agent_id: Optional[int]
    message_type: str
    priority: str
    status: str
    subject: Optional[str]
    content: str
    payload: Optional[Dict[str, Any]]
    workflow_id: Optional[str]
    task_id: Optional[int]
    thread_id: Optional[str]
    requires_response: bool
    response_received: bool
    created_at: str
    delivered_at: Optional[str]
    read_at: Optional[str]


# Endpoints

@router.post("/send")
async def send_message(
    sender_agent_id: int,
    request: SendMessageRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Send a message from an agent to another agent or broadcast.

    Args:
        sender_agent_id: ID of sending agent
        request: Message request data
        db: Database session

    Returns:
        dict: Created message
    """
    try:
        message = AgentCommunicationService.send_message(
            session=db,
            sender_agent_id=sender_agent_id,
            receiver_agent_id=request.receiver_agent_id,
            content=request.content,
            message_type=MessageType(request.message_type),
            priority=MessagePriority(request.priority),
            subject=request.subject,
            payload=request.payload,
            workflow_id=request.workflow_id,
            task_id=request.task_id,
            thread_id=request.thread_id,
            requires_response=request.requires_response,
            response_timeout_seconds=request.response_timeout_seconds,
            expires_in_seconds=request.expires_in_seconds
        )

        db.commit()

        return message.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to send message: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/respond/{message_id}")
async def send_response(
    message_id: int,
    sender_agent_id: int,
    request: SendResponseRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Send a response to a message.

    Args:
        message_id: ID of message being responded to
        sender_agent_id: ID of responding agent
        request: Response data
        db: Database session

    Returns:
        dict: Response message
    """
    try:
        response = AgentCommunicationService.send_response(
            session=db,
            sender_agent_id=sender_agent_id,
            original_message_id=message_id,
            content=request.content,
            payload=request.payload
        )

        db.commit()

        return response.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to send response: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/broadcast")
async def broadcast_message(
    sender_agent_id: int,
    content: str,
    subject: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    workflow_id: Optional[str] = None,
    priority: str = "normal",
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Broadcast a message to all agents.

    Args:
        sender_agent_id: ID of broadcasting agent
        content: Broadcast content
        subject: Broadcast subject
        payload: Broadcast data
        workflow_id: Associated workflow ID
        priority: Message priority
        db: Database session

    Returns:
        dict: Broadcast message
    """
    try:
        message = AgentCommunicationService.broadcast_message(
            session=db,
            sender_agent_id=sender_agent_id,
            content=content,
            subject=subject,
            payload=payload,
            workflow_id=workflow_id,
            priority=MessagePriority(priority)
        )

        db.commit()

        return message.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to broadcast message: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/inbox/{agent_id}")
async def get_inbox(
    agent_id: int,
    unread_only: bool = False,
    limit: int = 50,
    db: Session = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    """
    Get inbox messages for an agent.

    Args:
        agent_id: Agent ID
        unread_only: Only return unread messages
        limit: Result limit
        db: Database session

    Returns:
        list: Inbox messages
    """
    messages = AgentCommunicationService.get_inbox(
        session=db,
        agent_id=agent_id,
        unread_only=unread_only,
        limit=limit
    )

    return [msg.to_dict() for msg in messages]


@router.get("/sent/{agent_id}")
async def get_sent_messages(
    agent_id: int,
    limit: int = 50,
    db: Session = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    """
    Get sent messages for an agent.

    Args:
        agent_id: Agent ID
        limit: Result limit
        db: Database session

    Returns:
        list: Sent messages
    """
    messages = AgentCommunicationService.get_sent_messages(
        session=db,
        agent_id=agent_id,
        limit=limit
    )

    return [msg.to_dict() for msg in messages]


@router.get("/thread/{thread_id}")
async def get_thread(
    thread_id: str,
    db: Session = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    """
    Get all messages in a thread.

    Args:
        thread_id: Thread ID
        db: Database session

    Returns:
        list: Thread messages
    """
    messages = AgentCommunicationService.get_thread(
        session=db,
        thread_id=thread_id
    )

    return [msg.to_dict() for msg in messages]


@router.patch("/{message_id}/read")
async def mark_as_read(
    message_id: int,
    agent_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Mark message as read.

    Args:
        message_id: Message ID
        agent_id: Agent ID (for validation)
        db: Database session

    Returns:
        dict: Updated message
    """
    try:
        message = AgentCommunicationService.mark_as_read(
            session=db,
            message_id=message_id,
            agent_id=agent_id
        )

        db.commit()

        return message.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.patch("/{message_id}/processed")
async def mark_as_processed(
    message_id: int,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Mark message as processed.

    Args:
        message_id: Message ID
        db: Database session

    Returns:
        dict: Updated message
    """
    try:
        message = AgentCommunicationService.mark_as_processed(
            session=db,
            message_id=message_id
        )

        db.commit()

        return message.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/statistics")
async def get_statistics(
    agent_id: Optional[int] = None,
    workflow_id: Optional[str] = None,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get message statistics.

    Args:
        agent_id: Optional agent filter
        workflow_id: Optional workflow filter
        db: Database session

    Returns:
        dict: Message statistics
    """
    return AgentCommunicationService.get_statistics(
        session=db,
        agent_id=agent_id,
        workflow_id=workflow_id
    )


@router.delete("/expired")
async def delete_expired_messages(
    db: Session = Depends(get_db_session)
) -> Dict[str, int]:
    """
    Delete expired messages.

    Args:
        db: Database session

    Returns:
        dict: Number of messages deleted
    """
    count = AgentCommunicationService.delete_expired_messages(session=db)
    db.commit()

    return {"deleted": count}
