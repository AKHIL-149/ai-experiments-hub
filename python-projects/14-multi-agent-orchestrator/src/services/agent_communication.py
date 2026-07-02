"""
Agent Communication Service

Handles inter-agent communication, message routing, and coordination.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from src.models.agent_message import AgentMessage, MessageType, MessagePriority, MessageStatus
from src.models.agent import Agent
from src.core.logging import logger


class AgentCommunicationService:
    """
    Service for managing agent-to-agent communication.

    Provides message passing, broadcasting, thread management,
    and message history tracking.
    """

    @staticmethod
    def send_message(
        session: Session,
        sender_agent_id: int,
        receiver_agent_id: Optional[int],
        content: str,
        message_type: MessageType = MessageType.NOTIFICATION,
        priority: MessagePriority = MessagePriority.NORMAL,
        subject: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        workflow_id: Optional[str] = None,
        task_id: Optional[int] = None,
        execution_id: Optional[int] = None,
        thread_id: Optional[str] = None,
        parent_message_id: Optional[int] = None,
        requires_response: bool = False,
        response_timeout_seconds: Optional[int] = None,
        expires_in_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentMessage:
        """
        Send a message from one agent to another (or broadcast).

        Args:
            session: Database session
            sender_agent_id: ID of sending agent
            receiver_agent_id: ID of receiving agent (None for broadcast)
            content: Message content
            message_type: Type of message
            priority: Message priority
            subject: Message subject
            payload: Structured data payload
            workflow_id: Associated workflow ID
            task_id: Associated task ID
            execution_id: Associated execution ID
            thread_id: Thread ID for grouping messages
            parent_message_id: Parent message for threading
            requires_response: Whether response is required
            response_timeout_seconds: Timeout for response
            expires_in_seconds: Message expiration time
            metadata: Additional metadata

        Returns:
            AgentMessage: Created message
        """
        # Calculate expiration
        expires_at = None
        if expires_in_seconds:
            expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)

        # Create message
        message = AgentMessage(
            sender_agent_id=sender_agent_id,
            receiver_agent_id=receiver_agent_id,
            message_type=message_type,
            priority=priority,
            status=MessageStatus.PENDING,
            subject=subject,
            content=content,
            payload=payload,
            workflow_id=workflow_id,
            task_id=task_id,
            execution_id=execution_id,
            thread_id=thread_id,
            parent_message_id=parent_message_id,
            requires_response=requires_response,
            response_timeout_seconds=response_timeout_seconds,
            expires_at=expires_at,
            metadata=metadata
        )

        session.add(message)
        session.flush()

        logger.info(
            f"Message {message.id} sent: "
            f"from agent {sender_agent_id} to {receiver_agent_id or 'broadcast'}, "
            f"type={message_type.value}, priority={priority.value}"
        )

        # Auto-deliver if not requiring confirmation
        if message_type in [MessageType.NOTIFICATION, MessageType.BROADCAST]:
            message.mark_as_delivered()
            session.flush()

        return message

    @staticmethod
    def send_response(
        session: Session,
        sender_agent_id: int,
        original_message_id: int,
        content: str,
        payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentMessage:
        """
        Send a response to a message.

        Args:
            session: Database session
            sender_agent_id: ID of responding agent
            original_message_id: ID of message being responded to
            content: Response content
            payload: Response data
            metadata: Additional metadata

        Returns:
            AgentMessage: Response message
        """
        # Get original message
        original_message = session.query(AgentMessage).filter(
            AgentMessage.id == original_message_id
        ).first()

        if not original_message:
            raise ValueError(f"Original message {original_message_id} not found")

        # Create response
        response = AgentCommunicationService.send_message(
            session=session,
            sender_agent_id=sender_agent_id,
            receiver_agent_id=original_message.sender_agent_id,
            content=content,
            message_type=MessageType.RESPONSE,
            priority=original_message.priority,
            subject=f"Re: {original_message.subject}" if original_message.subject else None,
            payload=payload,
            workflow_id=original_message.workflow_id,
            task_id=original_message.task_id,
            execution_id=original_message.execution_id,
            thread_id=original_message.thread_id,
            parent_message_id=original_message_id,
            metadata=metadata
        )

        # Mark original message as having received response
        original_message.response_received = True
        session.flush()

        return response

    @staticmethod
    def broadcast_message(
        session: Session,
        sender_agent_id: int,
        content: str,
        subject: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        workflow_id: Optional[str] = None,
        priority: MessagePriority = MessagePriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AgentMessage:
        """
        Broadcast a message to all agents.

        Args:
            session: Database session
            sender_agent_id: ID of broadcasting agent
            content: Broadcast content
            subject: Broadcast subject
            payload: Broadcast data
            workflow_id: Associated workflow ID
            priority: Message priority
            metadata: Additional metadata

        Returns:
            AgentMessage: Broadcast message
        """
        return AgentCommunicationService.send_message(
            session=session,
            sender_agent_id=sender_agent_id,
            receiver_agent_id=None,  # None indicates broadcast
            content=content,
            message_type=MessageType.BROADCAST,
            priority=priority,
            subject=subject,
            payload=payload,
            workflow_id=workflow_id,
            metadata=metadata
        )

    @staticmethod
    def get_messages(
        session: Session,
        agent_id: Optional[int] = None,
        sender_id: Optional[int] = None,
        receiver_id: Optional[int] = None,
        message_type: Optional[MessageType] = None,
        status: Optional[MessageStatus] = None,
        workflow_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        priority: Optional[MessagePriority] = None,
        unread_only: bool = False,
        limit: int = 100,
        offset: int = 0
    ) -> List[AgentMessage]:
        """
        Get messages with filters.

        Args:
            session: Database session
            agent_id: Filter by agent (sent or received)
            sender_id: Filter by sender
            receiver_id: Filter by receiver
            message_type: Filter by type
            status: Filter by status
            workflow_id: Filter by workflow
            thread_id: Filter by thread
            priority: Filter by priority
            unread_only: Only return unread messages
            limit: Result limit
            offset: Result offset

        Returns:
            List of messages
        """
        query = session.query(AgentMessage)

        # Agent filter (sent or received)
        if agent_id:
            query = query.filter(
                or_(
                    AgentMessage.sender_agent_id == agent_id,
                    AgentMessage.receiver_agent_id == agent_id,
                    AgentMessage.receiver_agent_id.is_(None)  # Include broadcasts
                )
            )

        if sender_id:
            query = query.filter(AgentMessage.sender_agent_id == sender_id)

        if receiver_id:
            query = query.filter(AgentMessage.receiver_agent_id == receiver_id)

        if message_type:
            query = query.filter(AgentMessage.message_type == message_type)

        if status:
            query = query.filter(AgentMessage.status == status)

        if workflow_id:
            query = query.filter(AgentMessage.workflow_id == workflow_id)

        if thread_id:
            query = query.filter(AgentMessage.thread_id == thread_id)

        if priority:
            query = query.filter(AgentMessage.priority == priority)

        if unread_only:
            query = query.filter(AgentMessage.status.in_([MessageStatus.PENDING, MessageStatus.DELIVERED]))

        return query.order_by(AgentMessage.created_at.desc()).limit(limit).offset(offset).all()

    @staticmethod
    def get_inbox(
        session: Session,
        agent_id: int,
        unread_only: bool = False,
        limit: int = 50
    ) -> List[AgentMessage]:
        """
        Get inbox messages for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            unread_only: Only return unread messages
            limit: Result limit

        Returns:
            List of inbox messages
        """
        return AgentCommunicationService.get_messages(
            session=session,
            receiver_id=agent_id,
            unread_only=unread_only,
            limit=limit
        )

    @staticmethod
    def get_sent_messages(
        session: Session,
        agent_id: int,
        limit: int = 50
    ) -> List[AgentMessage]:
        """
        Get sent messages for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            limit: Result limit

        Returns:
            List of sent messages
        """
        return AgentCommunicationService.get_messages(
            session=session,
            sender_id=agent_id,
            limit=limit
        )

    @staticmethod
    def get_thread(
        session: Session,
        thread_id: str
    ) -> List[AgentMessage]:
        """
        Get all messages in a thread.

        Args:
            session: Database session
            thread_id: Thread ID

        Returns:
            List of messages in thread
        """
        return session.query(AgentMessage).filter(
            AgentMessage.thread_id == thread_id
        ).order_by(AgentMessage.created_at.asc()).all()

    @staticmethod
    def mark_as_read(
        session: Session,
        message_id: int,
        agent_id: Optional[int] = None
    ) -> AgentMessage:
        """
        Mark message as read.

        Args:
            session: Database session
            message_id: Message ID
            agent_id: Optional agent ID for validation

        Returns:
            Updated message
        """
        message = session.query(AgentMessage).filter(
            AgentMessage.id == message_id
        ).first()

        if not message:
            raise ValueError(f"Message {message_id} not found")

        # Validate recipient
        if agent_id and message.receiver_agent_id != agent_id:
            raise ValueError(f"Agent {agent_id} is not the recipient of message {message_id}")

        message.mark_as_read()
        session.flush()

        return message

    @staticmethod
    def mark_as_processed(
        session: Session,
        message_id: int
    ) -> AgentMessage:
        """
        Mark message as processed.

        Args:
            session: Database session
            message_id: Message ID

        Returns:
            Updated message
        """
        message = session.query(AgentMessage).filter(
            AgentMessage.id == message_id
        ).first()

        if not message:
            raise ValueError(f"Message {message_id} not found")

        message.mark_as_processed()
        session.flush()

        return message

    @staticmethod
    def delete_expired_messages(session: Session) -> int:
        """
        Delete expired messages.

        Args:
            session: Database session

        Returns:
            Number of messages deleted
        """
        expired = session.query(AgentMessage).filter(
            and_(
                AgentMessage.expires_at.isnot(None),
                AgentMessage.expires_at < datetime.utcnow()
            )
        ).all()

        count = len(expired)

        for message in expired:
            session.delete(message)

        session.flush()

        if count > 0:
            logger.info(f"Deleted {count} expired messages")

        return count

    @staticmethod
    def get_statistics(
        session: Session,
        agent_id: Optional[int] = None,
        workflow_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get message statistics.

        Args:
            session: Database session
            agent_id: Optional agent filter
            workflow_id: Optional workflow filter

        Returns:
            Statistics dictionary
        """
        query = session.query(AgentMessage)

        if agent_id:
            query = query.filter(
                or_(
                    AgentMessage.sender_agent_id == agent_id,
                    AgentMessage.receiver_agent_id == agent_id
                )
            )

        if workflow_id:
            query = query.filter(AgentMessage.workflow_id == workflow_id)

        total_messages = query.count()

        return {
            "total_messages": total_messages,
            "by_type": {
                message_type.value: query.filter(AgentMessage.message_type == message_type).count()
                for message_type in MessageType
            },
            "by_status": {
                status.value: query.filter(AgentMessage.status == status).count()
                for status in MessageStatus
            },
            "by_priority": {
                priority.value: query.filter(AgentMessage.priority == priority).count()
                for priority in MessagePriority
            },
            "pending_responses": query.filter(
                and_(
                    AgentMessage.requires_response == True,
                    AgentMessage.response_received == False
                )
            ).count(),
            "agent_id": agent_id,
            "workflow_id": workflow_id
        }
