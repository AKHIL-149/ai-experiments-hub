"""
Database models and connection management for AI Code Review Assistant.
"""

import os
import enum
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List
import uuid

from sqlalchemy import (
    create_engine,
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    Text,
    JSON,
    ForeignKey,
    Enum,
    Index
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, Session

Base = declarative_base()


class UserRole(str, enum.Enum):
    """User role enumeration for RBAC."""
    USER = 'user'
    ADMIN = 'admin'


class RepositoryStatus(str, enum.Enum):
    """Repository status enumeration."""
    PENDING = 'pending'
    CLONING = 'cloning'
    READY = 'ready'
    ERROR = 'error'


class PRStatus(str, enum.Enum):
    """Pull request status enumeration."""
    OPEN = 'open'
    CLOSED = 'closed'
    MERGED = 'merged'
    ANALYZING = 'analyzing'
    REVIEWED = 'reviewed'


class JobStatus(str, enum.Enum):
    """Analysis job status enumeration."""
    QUEUED = 'queued'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'


class IssueCategory(str, enum.Enum):
    """Issue category enumeration."""
    SECURITY = 'security'
    SMELL = 'smell'
    COMPLEXITY = 'complexity'
    STYLE = 'style'
    PATTERN = 'pattern'


class IssueSeverity(str, enum.Enum):
    """Issue severity enumeration."""
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'


class User(Base):
    """User accounts with role-based access control."""
    __tablename__ = 'users'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login = Column(DateTime)

    # Relationships
    sessions = relationship('UserSession', back_populates='user', cascade='all, delete-orphan')
    repositories = relationship('Repository', back_populates='user', cascade='all, delete-orphan')
    reviews = relationship('Review', back_populates='reviewer', cascade='all, delete-orphan')

    def to_dict(self) -> Dict:
        """Convert user to dictionary (exclude password_hash)."""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'role': self.role.value,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None
        }

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"


class UserSession(Base):
    """User authentication sessions."""
    __tablename__ = 'sessions'

    id = Column(String(64), primary_key=True)  # Session token
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    last_accessed = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip_address = Column(String(45))  # IPv6 compatible

    # Relationships
    user = relationship('User', back_populates='sessions')

    def to_dict(self) -> Dict:
        """Convert session to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'last_accessed': self.last_accessed.isoformat() if self.last_accessed else None,
            'ip_address': self.ip_address
        }

    def __repr__(self):
        return f"<UserSession(id={self.id}, user_id={self.user_id})>"


class Repository(Base):
    """GitHub repositories tracked for code review."""
    __tablename__ = 'repositories'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    github_url = Column(String(500), nullable=False)
    clone_path = Column(String(500))
    default_branch = Column(String(100), default='main')
    status = Column(Enum(RepositoryStatus), default=RepositoryStatus.PENDING, nullable=False)
    last_synced_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    settings_json = Column(JSON)  # Custom settings per repo

    # Relationships
    user = relationship('User', back_populates='repositories')
    pull_requests = relationship('PullRequest', back_populates='repository', cascade='all, delete-orphan')

    def to_dict(self) -> Dict:
        """Convert repository to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'github_url': self.github_url,
            'clone_path': self.clone_path,
            'default_branch': self.default_branch,
            'status': self.status.value,
            'last_synced_at': self.last_synced_at.isoformat() if self.last_synced_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'settings': self.settings_json
        }

    def __repr__(self):
        return f"<Repository(id={self.id}, name={self.name}, status={self.status})>"


class PullRequest(Base):
    """GitHub pull requests for code review."""
    __tablename__ = 'pull_requests'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    repository_id = Column(String(36), ForeignKey('repositories.id'), nullable=False, index=True)
    pr_number = Column(Integer, nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    author = Column(String(255))
    status = Column(Enum(PRStatus), default=PRStatus.OPEN, nullable=False)
    source_branch = Column(String(255), nullable=False)
    target_branch = Column(String(255), nullable=False)
    github_id = Column(String(100))  # GitHub PR ID
    github_url = Column(String(500))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    reviewed_at = Column(DateTime)

    # Relationships
    repository = relationship('Repository', back_populates='pull_requests')
    code_files = relationship('CodeFile', back_populates='pull_request', cascade='all, delete-orphan')
    analysis_jobs = relationship('AnalysisJob', back_populates='pull_request', cascade='all, delete-orphan')
    reviews = relationship('Review', back_populates='pull_request', cascade='all, delete-orphan')

    def to_dict(self) -> Dict:
        """Convert pull request to dictionary."""
        return {
            'id': self.id,
            'repository_id': self.repository_id,
            'pr_number': self.pr_number,
            'title': self.title,
            'description': self.description,
            'author': self.author,
            'status': self.status.value,
            'source_branch': self.source_branch,
            'target_branch': self.target_branch,
            'github_id': self.github_id,
            'github_url': self.github_url,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None
        }

    def __repr__(self):
        return f"<PullRequest(id={self.id}, pr_number={self.pr_number}, status={self.status})>"


class CodeFile(Base):
    """Code files analyzed in pull requests."""
    __tablename__ = 'code_files'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pull_request_id = Column(String(36), ForeignKey('pull_requests.id'), nullable=False, index=True)
    file_path = Column(String(1000), nullable=False)
    file_hash = Column(String(64))  # SHA256 hash of content
    language = Column(String(50))
    lines_of_code = Column(Integer)
    parsed_data_json = Column(JSON)  # Cached ParsedModule from parser
    last_analyzed_at = Column(DateTime)

    # Relationships
    pull_request = relationship('PullRequest', back_populates='code_files')
    issues = relationship('Issue', back_populates='code_file', cascade='all, delete-orphan')
    refactorings = relationship('Refactoring', back_populates='code_file', cascade='all, delete-orphan')

    def to_dict(self) -> Dict:
        """Convert code file to dictionary."""
        return {
            'id': self.id,
            'pull_request_id': self.pull_request_id,
            'file_path': self.file_path,
            'file_hash': self.file_hash,
            'language': self.language,
            'lines_of_code': self.lines_of_code,
            'last_analyzed_at': self.last_analyzed_at.isoformat() if self.last_analyzed_at else None,
            'parsed_data': self.parsed_data_json
        }

    def __repr__(self):
        return f"<CodeFile(id={self.id}, file_path={self.file_path}, language={self.language})>"


class AnalysisJob(Base):
    """Asynchronous analysis jobs tracked via Celery."""
    __tablename__ = 'analysis_jobs'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pull_request_id = Column(String(36), ForeignKey('pull_requests.id'), nullable=False, index=True)
    job_type = Column(String(50), nullable=False)  # 'file', 'pr', 'repo'
    status = Column(Enum(JobStatus), default=JobStatus.QUEUED, nullable=False)
    celery_task_id = Column(String(100), index=True)  # Celery task ID
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    result_json = Column(JSON)  # Job results summary

    # Relationships
    pull_request = relationship('PullRequest', back_populates='analysis_jobs')

    def to_dict(self) -> Dict:
        """Convert analysis job to dictionary."""
        return {
            'id': self.id,
            'pull_request_id': self.pull_request_id,
            'job_type': self.job_type,
            'status': self.status.value,
            'celery_task_id': self.celery_task_id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'result': self.result_json
        }

    def __repr__(self):
        return f"<AnalysisJob(id={self.id}, job_type={self.job_type}, status={self.status})>"


class Issue(Base):
    """Code issues detected during analysis."""
    __tablename__ = 'issues'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    code_file_id = Column(String(36), ForeignKey('code_files.id'), nullable=False, index=True)
    category = Column(Enum(IssueCategory), nullable=False, index=True)
    severity = Column(Enum(IssueSeverity), nullable=False, index=True)
    rule_id = Column(String(100), nullable=False)  # e.g., 'SEC001', 'SMELL002'
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    line_number = Column(Integer)
    column_number = Column(Integer)
    code_snippet = Column(Text)
    confidence = Column(Float)  # 0.0 to 1.0
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    code_file = relationship('CodeFile', back_populates='issues')
    refactorings = relationship('Refactoring', back_populates='issue', cascade='all, delete-orphan')

    def to_dict(self) -> Dict:
        """Convert issue to dictionary."""
        return {
            'id': self.id,
            'code_file_id': self.code_file_id,
            'category': self.category.value,
            'severity': self.severity.value,
            'rule_id': self.rule_id,
            'title': self.title,
            'description': self.description,
            'line_number': self.line_number,
            'column_number': self.column_number,
            'code_snippet': self.code_snippet,
            'confidence': self.confidence,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f"<Issue(id={self.id}, category={self.category}, severity={self.severity})>"


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(self, db_url: Optional[str] = None):
        """
        Initialize database manager.

        Args:
            db_url: Database URL. If None, uses SQLite in ./data/database.db
        """
        if db_url is None:
            db_dir = Path('./data')
            db_dir.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{db_dir}/database.db"

        self.engine = create_engine(
            db_url,
            echo=False,
            pool_pre_ping=True
        )

        # Create all tables
        Base.metadata.create_all(self.engine)

        # Session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

    def get_session(self) -> Session:
        """
        Get a new database session.

        Returns:
            SQLAlchemy Session object

        Usage:
            with db_manager.get_session() as session:
                # Use session
                session.query(User).all()
        """
        return self.SessionLocal()

    def close(self):
        """Close database connection."""
        self.engine.dispose()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
