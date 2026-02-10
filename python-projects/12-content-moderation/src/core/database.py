"""
Database models for Content Moderation System.

8 SQLAlchemy models:
- User: User accounts with role-based access
- Session: Authentication sessions
- ContentItem: Submitted content (text, image, video)
- ModerationJob: Celery task tracking
- Classification: AI classification results
- Review: Human moderation decisions
- Policy: Moderation policies and thresholds
- AuditLog: Complete audit trail

Pattern Source: Projects 10 & 11 database.py
"""

from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Boolean,
    Text, DateTime, JSON, Enum, ForeignKey, Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
import uuid
import enum

Base = declarative_base()


# Enums
class UserRole(str, enum.Enum):
    """User role for RBAC."""
    USER = 'user'
    MODERATOR = 'moderator'
    ADMIN = 'admin'


class ContentType(str, enum.Enum):
    """Type of content being moderated."""
    TEXT = 'text'
    IMAGE = 'image'
    VIDEO = 'video'


class ContentStatus(str, enum.Enum):
    """Content moderation status."""
    PENDING = 'pending'           # Awaiting moderation
    PROCESSING = 'processing'      # Being classified
    APPROVED = 'approved'          # Passed moderation
    REJECTED = 'rejected'          # Failed moderation
    FLAGGED = 'flagged'            # Needs human review
    APPEALED = 'appealed'          # User appealed rejection
    UNDER_REVIEW = 'under_review'  # Being reviewed by moderator


class JobStatus(str, enum.Enum):
    """Moderation job status."""
    QUEUED = 'queued'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'
    RETRYING = 'retrying'


class ActionType(str, enum.Enum):
    """Review action types."""
    AUTO_APPROVE = 'auto_approve'
    AUTO_REJECT = 'auto_reject'
    FLAG_REVIEW = 'flag_review'
    MANUAL_APPROVE = 'manual_approve'
    MANUAL_REJECT = 'manual_reject'


class ViolationCategory(str, enum.Enum):
    """Content violation categories."""
    SPAM = 'spam'
    NSFW = 'nsfw'
    HATE_SPEECH = 'hate_speech'
    VIOLENCE = 'violence'
    HARASSMENT = 'harassment'
    ILLEGAL_CONTENT = 'illegal_content'
    MISINFORMATION = 'misinformation'
    COPYRIGHT = 'copyright'
    SCAM = 'scam'
    CLEAN = 'clean'


# Models

class User(Base):
    """User account model with role-based access control."""
    __tablename__ = 'users'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)

    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    # Relationships
    sessions = relationship('Session', back_populates='user', cascade='all, delete-orphan')
    content_items = relationship('ContentItem', back_populates='user', cascade='all, delete-orphan')
    reviews = relationship('Review', back_populates='moderator')

    def to_dict(self) -> Dict:
        """Serialize user to dictionary."""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role.value,
            'is_active': self.is_active,
            'is_verified': self.is_verified,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
        }


class Session(Base):
    """Session model for authentication."""
    __tablename__ = 'sessions'

    id = Column(String, primary_key=True)  # Session token
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_accessed = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String(45), nullable=True)  # IPv6 max length
    user_agent = Column(String(500), nullable=True)

    # Relationships
    user = relationship('User', back_populates='sessions')

    def to_dict(self) -> Dict:
        """Serialize session to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'last_accessed': self.last_accessed.isoformat() if self.last_accessed else None,
        }


class ContentItem(Base):
    """Submitted content model."""
    __tablename__ = 'content_items'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)

    # Content details
    content_type = Column(Enum(ContentType), nullable=False)
    text_content = Column(Text, nullable=True)  # For text or captions
    file_path = Column(String(500), nullable=True)  # For images/videos
    file_size = Column(Integer, nullable=True)  # Bytes
    file_hash = Column(String(64), nullable=True, index=True)  # SHA256 for deduplication
    thumbnail_path = Column(String(500), nullable=True)

    # Metadata
    title = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    source_url = Column(String(1000), nullable=True)
    metadata_json = Column(JSON, nullable=True)  # Custom metadata

    # Moderation status
    status = Column(Enum(ContentStatus), default=ContentStatus.PENDING, index=True)
    priority = Column(Integer, default=0)  # Higher = more urgent

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    moderated_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship('User', back_populates='content_items')
    moderation_jobs = relationship('ModerationJob', back_populates='content', cascade='all, delete-orphan')
    classifications = relationship('Classification', back_populates='content', cascade='all, delete-orphan')
    reviews = relationship('Review', back_populates='content', cascade='all, delete-orphan')

    # Indexes
    __table_args__ = (
        Index('idx_status_priority', 'status', 'priority'),
        Index('idx_user_created', 'user_id', 'created_at'),
    )

    def to_dict(self, include_details: bool = False) -> Dict:
        """Serialize content item to dictionary."""
        result = {
            'id': self.id,
            'user_id': self.user_id,
            'content_type': self.content_type.value,
            'title': self.title,
            'status': self.status.value,
            'priority': self.priority,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'moderated_at': self.moderated_at.isoformat() if self.moderated_at else None,
        }

        if include_details:
            result.update({
                'text_content': self.text_content,
                'file_path': self.file_path,
                'thumbnail_path': self.thumbnail_path,
                'description': self.description,
                'metadata': self.metadata_json,
            })

        return result


class ModerationJob(Base):
    """Moderation job/task model."""
    __tablename__ = 'moderation_jobs'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content_id = Column(String, ForeignKey('content_items.id'), nullable=False, index=True)

    # Job details
    status = Column(Enum(JobStatus), default=JobStatus.QUEUED, index=True)
    queue_name = Column(String(50), default='default')  # critical, high, default, batch
    celery_task_id = Column(String(100), nullable=True, index=True)

    # Processing
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    processing_time_seconds = Column(Float, nullable=True)

    # Retry handling
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    last_error = Column(Text, nullable=True)

    # Results
    result_data = Column(JSON, nullable=True)  # Classification results

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    content = relationship('ContentItem', back_populates='moderation_jobs')

    # Indexes
    __table_args__ = (
        Index('idx_status_queue', 'status', 'queue_name'),
    )

    def to_dict(self) -> Dict:
        """Serialize job to dictionary."""
        return {
            'id': self.id,
            'content_id': self.content_id,
            'status': self.status.value,
            'queue_name': self.queue_name,
            'celery_task_id': self.celery_task_id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'processing_time_seconds': self.processing_time_seconds,
            'retry_count': self.retry_count,
            'result_data': self.result_data,
        }


class Classification(Base):
    """AI classification results model."""
    __tablename__ = 'classifications'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content_id = Column(String, ForeignKey('content_items.id'), nullable=False, index=True)
    job_id = Column(String, ForeignKey('moderation_jobs.id'), nullable=True)

    # Classification details
    category = Column(Enum(ViolationCategory), nullable=False, index=True)
    confidence = Column(Float, nullable=False)  # 0.0 - 1.0
    is_violation = Column(Boolean, nullable=False)

    # Model information
    provider = Column(String(50), nullable=False)  # ollama, openai, anthropic
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(50), nullable=True)

    # Detailed results
    reasoning = Column(Text, nullable=True)  # Why this classification
    sub_categories = Column(JSON, nullable=True)  # Detailed breakdown
    evidence = Column(JSON, nullable=True)  # Specific evidence (keywords, regions)

    # Metadata
    processing_time_ms = Column(Float, nullable=True)
    cost = Column(Float, nullable=True)  # API cost in USD
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    content = relationship('ContentItem', back_populates='classifications')

    def to_dict(self) -> Dict:
        """Serialize classification to dictionary."""
        return {
            'id': self.id,
            'content_id': self.content_id,
            'category': self.category.value,
            'confidence': self.confidence,
            'is_violation': self.is_violation,
            'provider': self.provider,
            'model_name': self.model_name,
            'reasoning': self.reasoning,
            'sub_categories': self.sub_categories,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Review(Base):
    """Human review model."""
    __tablename__ = 'reviews'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    content_id = Column(String, ForeignKey('content_items.id'), nullable=False, index=True)
    moderator_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)

    # Review decision
    action = Column(Enum(ActionType), nullable=False)
    approved = Column(Boolean, nullable=False)

    # Details
    category = Column(Enum(ViolationCategory), nullable=True)
    notes = Column(Text, nullable=True)
    tags = Column(JSON, nullable=True)  # Additional tags

    # Appeal handling
    is_appeal_review = Column(Boolean, default=False)
    original_review_id = Column(String, ForeignKey('reviews.id'), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    review_time_seconds = Column(Float, nullable=True)

    # Relationships
    content = relationship('ContentItem', back_populates='reviews')
    moderator = relationship('User', back_populates='reviews')
    appeals = relationship('Review', remote_side=[original_review_id])

    # Indexes
    __table_args__ = (
        Index('idx_moderator_created', 'moderator_id', 'created_at'),
    )

    def to_dict(self) -> Dict:
        """Serialize review to dictionary."""
        return {
            'id': self.id,
            'content_id': self.content_id,
            'moderator_id': self.moderator_id,
            'action': self.action.value,
            'approved': self.approved,
            'category': self.category.value if self.category else None,
            'notes': self.notes,
            'is_appeal_review': self.is_appeal_review,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Policy(Base):
    """Moderation policy model."""
    __tablename__ = 'policies'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Policy details
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    category = Column(Enum(ViolationCategory), nullable=False, index=True)

    # Thresholds
    auto_reject_threshold = Column(Float, default=0.9)  # Auto-reject if confidence >= this
    auto_approve_threshold = Column(Float, default=0.9)  # Auto-approve if confidence >= this (for clean)
    flag_review_threshold = Column(Float, default=0.5)  # Flag for review if confidence >= this

    # Actions
    enabled = Column(Boolean, default=True)
    severity = Column(Integer, default=5)  # 1 (low) - 10 (critical)

    # Metadata
    rules_json = Column(JSON, nullable=True)  # Custom rules
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String, ForeignKey('users.id'), nullable=True)

    def to_dict(self) -> Dict:
        """Serialize policy to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'category': self.category.value,
            'auto_reject_threshold': self.auto_reject_threshold,
            'auto_approve_threshold': self.auto_approve_threshold,
            'flag_review_threshold': self.flag_review_threshold,
            'enabled': self.enabled,
            'severity': self.severity,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(Base):
    """Audit trail model."""
    __tablename__ = 'audit_logs'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))

    # Event details
    event_type = Column(String(50), nullable=False, index=True)
    actor_id = Column(String, ForeignKey('users.id'), nullable=True, index=True)
    actor_username = Column(String(50), nullable=True)

    # Resource affected
    resource_type = Column(String(50), nullable=True)  # content, user, policy
    resource_id = Column(String, nullable=True, index=True)

    # Event data
    action = Column(String(100), nullable=False)
    details = Column(JSON, nullable=True)

    # Context
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    # Indexes
    __table_args__ = (
        Index('idx_event_created', 'event_type', 'created_at'),
        Index('idx_actor_created', 'actor_id', 'created_at'),
    )

    def to_dict(self) -> Dict:
        """Serialize audit log to dictionary."""
        return {
            'id': self.id,
            'event_type': self.event_type,
            'actor_username': self.actor_username,
            'resource_type': self.resource_type,
            'resource_id': self.resource_id,
            'action': self.action,
            'details': self.details,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class DatabaseManager:
    """Database connection and session management."""

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize database manager.

        Args:
            database_url: Database connection string (SQLite or PostgreSQL)
        """
        if database_url is None:
            # Default to SQLite in data directory
            db_dir = Path('./data')
            db_dir.mkdir(parents=True, exist_ok=True)
            database_url = f"sqlite:///{db_dir}/database.db"

        # Create engine
        if database_url.startswith('sqlite'):
            self.engine = create_engine(
                database_url,
                connect_args={'check_same_thread': False},
                echo=False
            )
        else:
            self.engine = create_engine(database_url, echo=False)

        self.SessionLocal = sessionmaker(bind=self.engine)

    def create_tables(self):
        """Create all tables in the database."""
        Base.metadata.create_all(self.engine)

    def drop_tables(self):
        """Drop all tables in the database."""
        Base.metadata.drop_all(self.engine)

    def get_session(self):
        """
        Get a new database session.

        Returns:
            SQLAlchemy session (use with context manager)
        """
        return self.SessionLocal()
