"""
Agent Message model for inter-agent communication
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Enum,
    ForeignKey, JSON, Boolean
)
from sqlalchemy.orm import relationship

from src.core.database import Base


class MessageType(str, enum.Enum):
    """Message types for agent communication"""
    REQUEST = "request"           # Request for action/information
    RESPONSE = "response"          # Response to a request
    BROADCAST = "broadcast"        # Broadcast to all agents
    NOTIFICATION = "notification"  # One-way notification
    ERROR = "error"               # Error message
    TASK_ASSIGNMENT = "task_assignment"  # Task delegation


class MessagePriority(str, enum.Enum):
    """Message priority levels"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class MessageStatus(str, enum.Enum):
    """Message delivery status"""
    PENDING = "pending"
    DELIVERED = "delivered"
    READ = "read"
    PROCESSED = "processed"
    FAILED = "failed"


class AgentMessage(Base):
    """
    Agent Message model for inter-agent communication.

    Enables agents to communicate with each other during workflow execution,
    share context, delegate tasks, and coordinate activities.
    """
    __tablename__ = "agent_messages"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)

    # Sender and Receiver
    sender_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False, index=True)
    receiver_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True, index=True)  # Null for broadcast

    # Relationships
    sender_agent = relationship("Agent", foreign_keys=[sender_agent_id])
    receiver_agent = relationship("Agent", foreign_keys=[receiver_agent_id])

    # Message Metadata
    message_type = Column(Enum(MessageType), default=MessageType.NOTIFICATION, nullable=False, index=True)
    priority = Column(Enum(MessagePriority), default=MessagePriority.NORMAL, nullable=False, index=True)
    status = Column(Enum(MessageStatus), default=MessageStatus.PENDING, nullable=False, index=True)

    # Message Content
    subject = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    payload = Column(JSON, nullable=True)  # Structured data payload

    # Context
    workflow_id = Column(String(100), nullable=True, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=True, index=True)
    execution_id = Column(Integer, ForeignKey("agent_executions.id"), nullable=True, index=True)

    # Thread Management
    thread_id = Column(String(100), nullable=True, index=True)  # Group related messages
    parent_message_id = Column(Integer, ForeignKey("agent_messages.id"), nullable=True)

    # Request-Response Tracking
    requires_response = Column(Boolean, default=False)
    response_received = Column(Boolean, default=False)
    response_timeout_seconds = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    delivered_at = Column(DateTime, nullable=True)
    read_at = Column(DateTime, nullable=True)
    processed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    # Metadata
    metadata = Column(JSON, nullable=True)  # Additional metadata
    error_message = Column(Text, nullable=True)  # Error details if failed

    def __repr__(self):
        return (
            f"<AgentMessage(id={self.id}, "
            f"from={self.sender_agent_id}, to={self.receiver_agent_id}, "
            f"type={self.message_type}, status={self.status})>"
        )

    def mark_as_delivered(self):
        """Mark message as delivered"""
        if self.status == MessageStatus.PENDING:
            self.status = MessageStatus.DELIVERED
            self.delivered_at = datetime.utcnow()

    def mark_as_read(self):
        """Mark message as read"""
        if self.status in [MessageStatus.PENDING, MessageStatus.DELIVERED]:
            self.status = MessageStatus.READ
            self.read_at = datetime.utcnow()

    def mark_as_processed(self):
        """Mark message as processed"""
        self.status = MessageStatus.PROCESSED
        self.processed_at = datetime.utcnow()

    def mark_as_failed(self, error: str):
        """Mark message as failed"""
        self.status = MessageStatus.FAILED
        self.error_message = error

    def is_expired(self) -> bool:
        """Check if message has expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "sender_agent_id": self.sender_agent_id,
            "receiver_agent_id": self.receiver_agent_id,
            "message_type": self.message_type.value,
            "priority": self.priority.value,
            "status": self.status.value,
            "subject": self.subject,
            "content": self.content,
            "payload": self.payload,
            "workflow_id": self.workflow_id,
            "task_id": self.task_id,
            "execution_id": self.execution_id,
            "thread_id": self.thread_id,
            "parent_message_id": self.parent_message_id,
            "requires_response": self.requires_response,
            "response_received": self.response_received,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
            "error_message": self.error_message
        }
