"""
Agent Communication Protocol Service

Manages advanced communication protocols and messaging patterns between agents.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
from collections import defaultdict
import json

from src.models import Agent, AgentMessage
from src.core.logging import logger


class MessageType:
    """Message type constants"""
    REQUEST = "request"
    RESPONSE = "response"
    BROADCAST = "broadcast"
    NOTIFICATION = "notification"
    COMMAND = "command"
    QUERY = "query"
    ACK = "acknowledgment"


class MessagePriority:
    """Message priority constants"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class MessageStatus:
    """Message status constants"""
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    READ = "read"
    FAILED = "failed"


class CommunicationProtocol:
    """Communication protocol constants"""
    DIRECT = "direct"
    BROADCAST = "broadcast"
    MULTICAST = "multicast"
    PUBSUB = "pubsub"
    REQUEST_REPLY = "request_reply"


class AgentCommunicationProtocol:
    """Service for advanced agent-to-agent communication protocols"""

    # In-memory message queue for fast delivery
    _message_queue: Dict[int, List[Dict[str, Any]]] = defaultdict(list)

    # Message subscribers for pub/sub
    _subscribers: Dict[str, List[int]] = defaultdict(list)

    # Pending requests awaiting replies
    _pending_requests: Dict[int, Dict[str, Any]] = {}

    @staticmethod
    def send_message(
        session: Session,
        from_agent_id: int,
        to_agent_id: Optional[int] = None,
        message_type: str = MessageType.NOTIFICATION,
        protocol: str = CommunicationProtocol.DIRECT,
        content: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        priority: str = MessagePriority.NORMAL,
        requires_ack: bool = False,
        topic: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send a message from one agent to another (or broadcast).

        Args:
            session: Database session
            from_agent_id: Sender agent ID
            to_agent_id: Recipient agent ID (None for broadcast)
            message_type: Type of message
            protocol: Communication protocol
            content: Message content
            metadata: Optional metadata
            priority: Message priority
            requires_ack: Whether acknowledgment is required
            topic: Optional topic for pub/sub

        Returns:
            Message details with delivery info
        """
        # Validate sender exists
        sender = session.query(Agent).filter(Agent.id == from_agent_id).first()
        if not sender:
            raise ValueError(f"Sender agent {from_agent_id} not found")

        # For direct messages, validate recipient
        if protocol == CommunicationProtocol.DIRECT and to_agent_id:
            recipient = session.query(Agent).filter(Agent.id == to_agent_id).first()
            if not recipient:
                raise ValueError(f"Recipient agent {to_agent_id} not found")

        # Create message record
        message = AgentMessage(
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            message_type=message_type,
            content=content,
            status=MessageStatus.SENT,
            metadata=metadata or {}
        )

        # Add protocol and priority to metadata
        message.metadata.update({
            "protocol": protocol,
            "priority": priority,
            "requires_ack": requires_ack,
            "topic": topic,
            "sent_at": datetime.utcnow().isoformat()
        })

        session.add(message)
        session.flush()

        # Handle delivery based on protocol
        delivered_to = []

        if protocol == CommunicationProtocol.DIRECT:
            # Direct message to specific agent
            if to_agent_id:
                AgentCommunicationProtocol._queue_message(to_agent_id, message.id, message.to_dict())
                delivered_to.append(to_agent_id)

        elif protocol == CommunicationProtocol.BROADCAST:
            # Broadcast to all active agents
            active_agents = session.query(Agent).filter(Agent.status == "active").all()
            for agent in active_agents:
                if agent.id != from_agent_id:  # Don't send to self
                    AgentCommunicationProtocol._queue_message(agent.id, message.id, message.to_dict())
                    delivered_to.append(agent.id)

        elif protocol == CommunicationProtocol.MULTICAST:
            # Send to specific group (from metadata)
            recipient_ids = metadata.get("recipient_ids", []) if metadata else []
            for recipient_id in recipient_ids:
                AgentCommunicationProtocol._queue_message(recipient_id, message.id, message.to_dict())
                delivered_to.append(recipient_id)

        elif protocol == CommunicationProtocol.PUBSUB:
            # Send to topic subscribers
            if topic:
                subscribers = AgentCommunicationProtocol._subscribers.get(topic, [])
                for subscriber_id in subscribers:
                    if subscriber_id != from_agent_id:  # Don't send to self
                        AgentCommunicationProtocol._queue_message(subscriber_id, message.id, message.to_dict())
                        delivered_to.append(subscriber_id)

        message.metadata["delivered_to"] = delivered_to
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(message, "metadata")

        session.commit()
        session.refresh(message)

        logger.info(f"Message {message.id} sent from agent {from_agent_id} via {protocol} to {len(delivered_to)} recipients")

        return {
            "message_id": message.id,
            "from_agent_id": from_agent_id,
            "to_agent_id": to_agent_id,
            "protocol": protocol,
            "status": message.status,
            "delivered_to": delivered_to,
            "sent_at": message.created_at.isoformat()
        }

    @staticmethod
    def _queue_message(agent_id: int, message_id: int, message_data: Dict[str, Any]) -> None:
        """Queue a message for an agent"""
        AgentCommunicationProtocol._message_queue[agent_id].append({
            "message_id": message_id,
            "queued_at": datetime.utcnow().isoformat(),
            **message_data
        })

    @staticmethod
    def get_messages(
        session: Session,
        agent_id: int,
        message_type: Optional[str] = None,
        status: Optional[str] = None,
        from_agent_id: Optional[int] = None,
        unread_only: bool = False,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get messages for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            message_type: Optional filter by message type
            status: Optional filter by status
            from_agent_id: Optional filter by sender
            unread_only: Only return unread messages
            limit: Maximum messages to return

        Returns:
            Dictionary with messages
        """
        # Check agent exists
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Query messages
        query = session.query(AgentMessage).filter(
            or_(
                AgentMessage.to_agent_id == agent_id,
                AgentMessage.to_agent_id.is_(None)  # Broadcast messages
            )
        )

        if message_type:
            query = query.filter(AgentMessage.message_type == message_type)

        if status:
            query = query.filter(AgentMessage.status == status)

        if from_agent_id:
            query = query.filter(AgentMessage.from_agent_id == from_agent_id)

        if unread_only:
            query = query.filter(AgentMessage.status != MessageStatus.READ)

        messages = query.order_by(desc(AgentMessage.created_at)).limit(limit).all()

        # Also check in-memory queue
        queued_messages = AgentCommunicationProtocol._message_queue.get(agent_id, [])

        return {
            "agent_id": agent_id,
            "total_messages": len(messages),
            "queued_messages": len(queued_messages),
            "messages": [msg.to_dict() for msg in messages],
            "queue": queued_messages[:limit]
        }

    @staticmethod
    def mark_message_read(
        session: Session,
        message_id: int,
        agent_id: int
    ) -> Dict[str, Any]:
        """
        Mark a message as read.

        Args:
            session: Database session
            message_id: Message ID
            agent_id: Agent ID marking as read

        Returns:
            Updated message details
        """
        message = session.query(AgentMessage).filter(AgentMessage.id == message_id).first()
        if not message:
            raise ValueError(f"Message {message_id} not found")

        # Verify agent is recipient
        if message.to_agent_id and message.to_agent_id != agent_id:
            raise ValueError(f"Agent {agent_id} is not the recipient of message {message_id}")

        message.status = MessageStatus.READ
        message.metadata["read_at"] = datetime.utcnow().isoformat()
        message.metadata["read_by"] = agent_id

        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(message, "metadata")

        session.commit()

        return {
            "message_id": message_id,
            "status": message.status,
            "read_at": message.metadata.get("read_at")
        }

    @staticmethod
    def send_acknowledgment(
        session: Session,
        original_message_id: int,
        agent_id: int,
        ack_content: str = "Acknowledged"
    ) -> Dict[str, Any]:
        """
        Send acknowledgment for a message.

        Args:
            session: Database session
            original_message_id: ID of message being acknowledged
            agent_id: Agent ID sending acknowledgment
            ack_content: Acknowledgment content

        Returns:
            Acknowledgment message details
        """
        original_message = session.query(AgentMessage).filter(
            AgentMessage.id == original_message_id
        ).first()

        if not original_message:
            raise ValueError(f"Message {original_message_id} not found")

        # Send ACK back to original sender
        ack_message = AgentCommunicationProtocol.send_message(
            session=session,
            from_agent_id=agent_id,
            to_agent_id=original_message.from_agent_id,
            message_type=MessageType.ACK,
            protocol=CommunicationProtocol.DIRECT,
            content=ack_content,
            metadata={
                "original_message_id": original_message_id,
                "ack_for": original_message.message_type
            }
        )

        return ack_message

    @staticmethod
    def send_request(
        session: Session,
        from_agent_id: int,
        to_agent_id: int,
        request_content: str,
        metadata: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 300
    ) -> Dict[str, Any]:
        """
        Send a request and track it for reply.

        Args:
            session: Database session
            from_agent_id: Requesting agent ID
            to_agent_id: Target agent ID
            request_content: Request content
            metadata: Optional metadata
            timeout_seconds: Request timeout

        Returns:
            Request details with tracking info
        """
        message = AgentCommunicationProtocol.send_message(
            session=session,
            from_agent_id=from_agent_id,
            to_agent_id=to_agent_id,
            message_type=MessageType.REQUEST,
            protocol=CommunicationProtocol.REQUEST_REPLY,
            content=request_content,
            metadata=metadata,
            requires_ack=True
        )

        # Track pending request
        AgentCommunicationProtocol._pending_requests[message["message_id"]] = {
            "from_agent_id": from_agent_id,
            "to_agent_id": to_agent_id,
            "sent_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(seconds=timeout_seconds)).isoformat(),
            "reply_received": False
        }

        return message

    @staticmethod
    def send_reply(
        session: Session,
        request_message_id: int,
        from_agent_id: int,
        reply_content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send a reply to a request.

        Args:
            session: Database session
            request_message_id: Original request message ID
            from_agent_id: Replying agent ID
            reply_content: Reply content
            metadata: Optional metadata

        Returns:
            Reply message details
        """
        request_message = session.query(AgentMessage).filter(
            AgentMessage.id == request_message_id
        ).first()

        if not request_message:
            raise ValueError(f"Request message {request_message_id} not found")

        # Send reply back to requester
        reply_metadata = metadata or {}
        reply_metadata["request_message_id"] = request_message_id

        reply_message = AgentCommunicationProtocol.send_message(
            session=session,
            from_agent_id=from_agent_id,
            to_agent_id=request_message.from_agent_id,
            message_type=MessageType.RESPONSE,
            protocol=CommunicationProtocol.DIRECT,
            content=reply_content,
            metadata=reply_metadata
        )

        # Mark request as replied
        if request_message_id in AgentCommunicationProtocol._pending_requests:
            AgentCommunicationProtocol._pending_requests[request_message_id]["reply_received"] = True
            AgentCommunicationProtocol._pending_requests[request_message_id]["replied_at"] = datetime.utcnow().isoformat()

        return reply_message

    @staticmethod
    def subscribe_to_topic(
        session: Session,
        agent_id: int,
        topic: str
    ) -> Dict[str, Any]:
        """
        Subscribe an agent to a topic for pub/sub messaging.

        Args:
            session: Database session
            agent_id: Agent ID
            topic: Topic to subscribe to

        Returns:
            Subscription details
        """
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if agent_id not in AgentCommunicationProtocol._subscribers[topic]:
            AgentCommunicationProtocol._subscribers[topic].append(agent_id)
            logger.info(f"Agent {agent_id} subscribed to topic '{topic}'")

        return {
            "agent_id": agent_id,
            "topic": topic,
            "subscriber_count": len(AgentCommunicationProtocol._subscribers[topic]),
            "message": f"Subscribed to topic '{topic}'"
        }

    @staticmethod
    def unsubscribe_from_topic(
        session: Session,
        agent_id: int,
        topic: str
    ) -> Dict[str, Any]:
        """
        Unsubscribe an agent from a topic.

        Args:
            session: Database session
            agent_id: Agent ID
            topic: Topic to unsubscribe from

        Returns:
            Unsubscription details
        """
        if agent_id in AgentCommunicationProtocol._subscribers.get(topic, []):
            AgentCommunicationProtocol._subscribers[topic].remove(agent_id)
            logger.info(f"Agent {agent_id} unsubscribed from topic '{topic}'")

        return {
            "agent_id": agent_id,
            "topic": topic,
            "message": f"Unsubscribed from topic '{topic}'"
        }

    @staticmethod
    def get_topic_subscribers(
        session: Session,
        topic: str
    ) -> Dict[str, Any]:
        """
        Get subscribers for a topic.

        Args:
            session: Database session
            topic: Topic name

        Returns:
            List of subscriber agent IDs
        """
        subscribers = AgentCommunicationProtocol._subscribers.get(topic, [])

        return {
            "topic": topic,
            "subscriber_count": len(subscribers),
            "subscribers": subscribers
        }

    @staticmethod
    def list_topics(session: Session) -> Dict[str, Any]:
        """
        List all active topics.

        Args:
            session: Database session

        Returns:
            List of topics with subscriber counts
        """
        topics = [
            {
                "topic": topic,
                "subscriber_count": len(subscribers),
                "subscribers": subscribers
            }
            for topic, subscribers in AgentCommunicationProtocol._subscribers.items()
            if subscribers  # Only include topics with subscribers
        ]

        return {
            "total_topics": len(topics),
            "topics": topics
        }

    @staticmethod
    def get_conversation(
        session: Session,
        agent1_id: int,
        agent2_id: int,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get conversation history between two agents.

        Args:
            session: Database session
            agent1_id: First agent ID
            agent2_id: Second agent ID
            limit: Maximum messages to return

        Returns:
            Conversation history
        """
        messages = session.query(AgentMessage).filter(
            or_(
                and_(
                    AgentMessage.from_agent_id == agent1_id,
                    AgentMessage.to_agent_id == agent2_id
                ),
                and_(
                    AgentMessage.from_agent_id == agent2_id,
                    AgentMessage.to_agent_id == agent1_id
                )
            )
        ).order_by(AgentMessage.created_at).limit(limit).all()

        return {
            "agent1_id": agent1_id,
            "agent2_id": agent2_id,
            "message_count": len(messages),
            "messages": [msg.to_dict() for msg in messages]
        }

    @staticmethod
    def get_communication_stats(
        session: Session,
        agent_id: Optional[int] = None,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get communication statistics.

        Args:
            session: Database session
            agent_id: Optional agent ID for agent-specific stats
            hours: Number of hours to analyze

        Returns:
            Communication statistics
        """
        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        query = session.query(AgentMessage).filter(
            AgentMessage.created_at >= cutoff_time
        )

        if agent_id:
            query = query.filter(
                or_(
                    AgentMessage.from_agent_id == agent_id,
                    AgentMessage.to_agent_id == agent_id
                )
            )

        messages = query.all()

        stats = {
            "time_window_hours": hours,
            "total_messages": len(messages),
            "by_type": {},
            "by_protocol": {},
            "by_priority": {},
            "by_status": {}
        }

        if agent_id:
            stats["agent_id"] = agent_id
            stats["messages_sent"] = sum(1 for m in messages if m.from_agent_id == agent_id)
            stats["messages_received"] = sum(1 for m in messages if m.to_agent_id == agent_id)

        for message in messages:
            msg_type = message.message_type
            protocol = message.metadata.get("protocol", "unknown")
            priority = message.metadata.get("priority", "normal")
            status = message.status

            stats["by_type"][msg_type] = stats["by_type"].get(msg_type, 0) + 1
            stats["by_protocol"][protocol] = stats["by_protocol"].get(protocol, 0) + 1
            stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

        return stats

    @staticmethod
    def clear_message_queue(
        session: Session,
        agent_id: int
    ) -> Dict[str, Any]:
        """
        Clear message queue for an agent.

        Args:
            session: Database session
            agent_id: Agent ID

        Returns:
            Cleared count
        """
        cleared_count = len(AgentCommunicationProtocol._message_queue.get(agent_id, []))
        AgentCommunicationProtocol._message_queue[agent_id] = []

        return {
            "agent_id": agent_id,
            "messages_cleared": cleared_count,
            "message": f"Cleared {cleared_count} messages from queue"
        }

    @staticmethod
    def get_pending_requests(
        session: Session,
        agent_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get pending requests (awaiting replies).

        Args:
            session: Database session
            agent_id: Optional filter by agent ID

        Returns:
            Pending requests
        """
        now = datetime.utcnow()
        pending = []

        for request_id, request_info in AgentCommunicationProtocol._pending_requests.items():
            # Check if expired
            expires_at = datetime.fromisoformat(request_info["expires_at"])
            if now > expires_at:
                continue

            # Filter by agent if specified
            if agent_id and request_info["from_agent_id"] != agent_id:
                continue

            if not request_info["reply_received"]:
                pending.append({
                    "request_id": request_id,
                    **request_info
                })

        return {
            "agent_id": agent_id,
            "pending_count": len(pending),
            "pending_requests": pending
        }
