"""
Shared Memory model for agent context sharing
"""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Enum,
    ForeignKey, JSON, Boolean, Index
)
from sqlalchemy.orm import relationship

from src.core.database import Base


class MemoryScope(str, enum.Enum):
    """Scope of shared memory"""
    GLOBAL = "global"          # Shared across all workflows
    WORKFLOW = "workflow"      # Shared within a workflow
    TASK = "task"             # Shared within a task
    AGENT = "agent"           # Specific to an agent


class MemoryType(str, enum.Enum):
    """Type of memory content"""
    CONTEXT = "context"        # General context information
    RESULT = "result"          # Execution results
    CONFIGURATION = "configuration"  # Configuration data
    STATE = "state"           # State information
    METADATA = "metadata"     # Metadata
    CACHE = "cache"           # Cached data


class SharedMemory(Base):
    """
    Shared Memory model for inter-agent context sharing.

    Enables agents to share context, results, and state information
    during workflow execution across different scopes.
    """
    __tablename__ = "shared_memory"

    # Primary Key
    id = Column(Integer, primary_key=True, index=True)

    # Memory Key (unique within scope)
    key = Column(String(255), nullable=False, index=True)

    # Scope
    scope = Column(Enum(MemoryScope), default=MemoryScope.WORKFLOW, nullable=False, index=True)
    scope_id = Column(String(100), nullable=True, index=True)  # workflow_id, task_id, agent_id

    # Memory Type
    memory_type = Column(Enum(MemoryType), default=MemoryType.CONTEXT, nullable=False, index=True)

    # Content
    value = Column(JSON, nullable=False)  # Actual data stored
    description = Column(Text, nullable=True)  # Description of what this memory contains

    # Ownership
    created_by_agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True, index=True)
    created_by_agent = relationship("Agent", foreign_keys=[created_by_agent_id])

    # Access Control
    is_public = Column(Boolean, default=True)  # Whether all agents can access
    allowed_agent_ids = Column(JSON, nullable=True)  # List of agent IDs with access

    # Versioning
    version = Column(Integer, default=1)  # Version number for updates
    previous_version_id = Column(Integer, ForeignKey("shared_memory.id"), nullable=True)

    # TTL and Expiration
    ttl_seconds = Column(Integer, nullable=True)  # Time to live in seconds
    expires_at = Column(DateTime, nullable=True, index=True)  # Expiration timestamp

    # Metadata
    extra_metadata = Column(JSON, nullable=True)  # Additional metadata
    tags = Column(JSON, nullable=True)  # Tags for categorization

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    accessed_at = Column(DateTime, default=datetime.utcnow, index=True)  # Last access time
    access_count = Column(Integer, default=0)  # Number of times accessed

    # Composite indexes for efficient queries
    __table_args__ = (
        Index('idx_scope_key', 'scope', 'scope_id', 'key'),
        Index('idx_scope_type', 'scope', 'memory_type'),
        Index('idx_workflow_memory', 'scope', 'scope_id', 'created_at'),
    )

    def __repr__(self):
        return (
            f"<SharedMemory(id={self.id}, key='{self.key}', "
            f"scope={self.scope}, scope_id='{self.scope_id}')>"
        )

    def is_expired(self) -> bool:
        """Check if memory has expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False

    def is_accessible_by(self, agent_id: int) -> bool:
        """Check if an agent can access this memory"""
        if self.is_public:
            return True

        if self.created_by_agent_id == agent_id:
            return True

        if self.allowed_agent_ids and agent_id in self.allowed_agent_ids:
            return True

        return False

    def update_access(self):
        """Update access tracking"""
        self.accessed_at = datetime.utcnow()
        self.access_count += 1

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "key": self.key,
            "scope": self.scope.value,
            "scope_id": self.scope_id,
            "memory_type": self.memory_type.value,
            "value": self.value,
            "description": self.description,
            "created_by_agent_id": self.created_by_agent_id,
            "is_public": self.is_public,
            "allowed_agent_ids": self.allowed_agent_ids,
            "version": self.version,
            "previous_version_id": self.previous_version_id,
            "ttl_seconds": self.ttl_seconds,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "metadata": self.metadata,
            "tags": self.tags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "accessed_at": self.accessed_at.isoformat() if self.accessed_at else None,
            "access_count": self.access_count
        }
