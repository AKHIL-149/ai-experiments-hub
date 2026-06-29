"""
Database models and connection management for AI Code Review Assistant.
"""

import os
import enum
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
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
    Index,
    CheckConstraint
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


class RefactoringStatus(str, enum.Enum):
    """Refactoring suggestion status enumeration."""
    SUGGESTED = 'suggested'
    ACCEPTED = 'accepted'
    REJECTED = 'rejected'
    APPLIED = 'applied'


class User(Base):
    """User accounts with role-based access control."""
    __tablename__ = 'users'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    github_token = Column(String(500), nullable=True)  # Personal access token for GitHub API
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
    team_id = Column(String(36), ForeignKey('teams.id'), index=True)  # Optional team ownership
    name = Column(String(255), nullable=False)
    github_url = Column(String(500), nullable=False)
    clone_path = Column(String(500))
    default_branch = Column(String(100), default='main')
    status = Column(Enum(RepositoryStatus), default=RepositoryStatus.PENDING, nullable=False)
    last_synced_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    settings_json = Column(JSON)  # Custom settings per repo

    # Composite indexes for common query patterns
    __table_args__ = (
        Index('idx_repo_user_created', 'user_id', 'created_at'),
        Index('idx_repo_user_status', 'user_id', 'status'),
        Index('idx_repo_team_created', 'team_id', 'created_at'),
    )

    # Relationships
    user = relationship('User', back_populates='repositories')
    pull_requests = relationship('PullRequest', back_populates='repository', cascade='all, delete-orphan')
    code_files = relationship('CodeFile', back_populates='repository', cascade='all, delete-orphan')

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
    author_avatar = Column(String(500))
    status = Column(Enum(PRStatus), default=PRStatus.OPEN, nullable=False)
    source_branch = Column(String(255), nullable=False)
    target_branch = Column(String(255), nullable=False)
    github_id = Column(String(100))  # GitHub PR ID
    github_url = Column(String(500))
    is_draft = Column(Boolean, default=False)
    is_merged = Column(Boolean, default=False)
    commits_count = Column(Integer, default=0)
    additions = Column(Integer, default=0)
    deletions = Column(Integer, default=0)
    changed_files = Column(Integer, default=0)
    mergeable = Column(Boolean)
    mergeable_state = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, index=True)
    reviewed_at = Column(DateTime)

    # Composite indexes for common query patterns
    __table_args__ = (
        Index('idx_pr_repo_status', 'repository_id', 'status'),
        Index('idx_pr_repo_created', 'repository_id', 'created_at'),
        Index('idx_pr_status_created', 'status', 'created_at'),
    )

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
            'author_avatar': self.author_avatar,
            'status': self.status.value,
            'source_branch': self.source_branch,
            'target_branch': self.target_branch,
            'github_id': self.github_id,
            'github_url': self.github_url,
            'is_draft': self.is_draft,
            'is_merged': self.is_merged,
            'commits_count': self.commits_count,
            'additions': self.additions,
            'deletions': self.deletions,
            'changed_files': self.changed_files,
            'mergeable': self.mergeable,
            'mergeable_state': self.mergeable_state,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None
        }

    def __repr__(self):
        return f"<PullRequest(id={self.id}, pr_number={self.pr_number}, status={self.status})>"


class CodeFile(Base):
    """Code files analyzed in pull requests or repositories."""
    __tablename__ = 'code_files'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pull_request_id = Column(String(36), ForeignKey('pull_requests.id'), nullable=True, index=True)  # Nullable for repository analysis
    repository_id = Column(String(36), ForeignKey('repositories.id'), nullable=True, index=True)  # For repository-level analysis
    file_path = Column(String(1000), nullable=False)
    file_hash = Column(String(64), index=True)  # SHA256 hash of content - indexed for deduplication
    language = Column(String(50), index=True)  # Indexed for language-specific queries
    lines_of_code = Column(Integer)
    parsed_data_json = Column(JSON)  # Cached ParsedModule from parser
    last_analyzed_at = Column(DateTime, index=True)  # Indexed for staleness checks

    # Composite indexes for common query patterns
    __table_args__ = (
        Index('idx_file_pr_language', 'pull_request_id', 'language'),
        Index('idx_file_repo_language', 'repository_id', 'language'),
        Index('idx_file_hash_language', 'file_hash', 'language'),
        CheckConstraint(
            '(pull_request_id IS NOT NULL) OR (repository_id IS NOT NULL)',
            name='chk_codefile_has_parent'
        ),
    )

    # Relationships
    pull_request = relationship('PullRequest', back_populates='code_files')
    repository = relationship('Repository', back_populates='code_files')
    issues = relationship('Issue', back_populates='code_file', cascade='all, delete-orphan')
    refactorings = relationship('Refactoring', back_populates='code_file', cascade='all, delete-orphan')

    def __init__(self, **kwargs):
        """Initialize CodeFile with validation."""
        super().__init__(**kwargs)
        # Validate that at least one parent reference is set
        if not self.pull_request_id and not self.repository_id:
            raise ValueError("CodeFile must have either pull_request_id or repository_id set")

    def to_dict(self) -> Dict:
        """Convert code file to dictionary."""
        return {
            'id': self.id,
            'pull_request_id': self.pull_request_id,
            'repository_id': self.repository_id,
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
    started_at = Column(DateTime, index=True)
    completed_at = Column(DateTime, index=True)
    result_json = Column(JSON)  # Job results summary

    # Composite indexes for common query patterns
    __table_args__ = (
        Index('idx_job_pr_status', 'pull_request_id', 'status'),
        Index('idx_job_status_started', 'status', 'started_at'),
    )

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

    # AI Enhancement fields
    ai_explanation = Column(Text)  # AI-generated explanation
    fix_suggestion = Column(Text)  # AI-generated fix suggestion
    fix_confidence = Column(Float)  # Confidence in the fix (0.0 to 1.0)
    can_auto_apply = Column(Boolean, default=False)  # Whether fix can be auto-applied

    # Issue fingerprinting and tracking
    fingerprint = Column(String(64), index=True)  # SHA256 hash for deduplication
    last_seen_at = Column(DateTime, nullable=True)  # Last time this issue was detected
    resolved = Column(Boolean, default=False, index=True)  # True if not seen in latest analysis
    resolved_at = Column(DateTime, nullable=True)  # When it was marked as resolved

    # Dismissal tracking
    dismissed = Column(Boolean, default=False, index=True)
    dismissed_at = Column(DateTime, nullable=True)
    dismissed_by = Column(String(36), ForeignKey('users.id'), nullable=True)
    dismissal_reason = Column(Text, nullable=True)

    # Reappearance tracking (for dismissed issues that keep showing up)
    reappeared_count = Column(Integer, default=0)  # How many times dismissed issue reappeared
    last_reappeared_at = Column(DateTime, nullable=True)  # Last time it reappeared after dismissal

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Composite indexes for common query patterns
    __table_args__ = (
        Index('idx_issue_category_severity', 'category', 'severity'),
        Index('idx_issue_file_severity', 'code_file_id', 'severity'),
        Index('idx_issue_created_severity', 'created_at', 'severity'),
        Index('idx_issue_fingerprint_file', 'fingerprint', 'code_file_id'),
        # Indexes for filtering active/dismissed/resolved issues
        Index('idx_issue_dismissed_resolved', 'dismissed', 'resolved'),
        Index('idx_issue_severity_dismissed', 'severity', 'dismissed', 'resolved'),
        # Index for dashboard queries (recent issues)
        Index('idx_issue_created_desc', 'created_at'),
    )

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
            'fingerprint': self.fingerprint,
            'last_seen_at': self.last_seen_at.isoformat() if self.last_seen_at else None,
            'resolved': self.resolved,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'dismissed': self.dismissed,
            'dismissed_at': self.dismissed_at.isoformat() if self.dismissed_at else None,
            'dismissed_by': self.dismissed_by,
            'dismissal_reason': self.dismissal_reason,
            'reappeared_count': self.reappeared_count,
            'last_reappeared_at': self.last_reappeared_at.isoformat() if self.last_reappeared_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f"<Issue(id={self.id}, category={self.category}, severity={self.severity})>"


class Refactoring(Base):
    """Refactoring suggestions for code improvements."""
    __tablename__ = 'refactorings'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    issue_id = Column(String(36), ForeignKey('issues.id'), nullable=False, index=True)
    code_file_id = Column(String(36), ForeignKey('code_files.id'), nullable=False, index=True)
    refactoring_type = Column(String(100), nullable=False)  # 'extract_method', 'rename', 'simplify'
    original_code = Column(Text)
    refactored_code = Column(Text)
    diff = Column(Text)  # Unified diff format
    explanation = Column(Text)
    benefits = Column(Text)
    confidence = Column(Float)  # 0.0 to 1.0
    status = Column(Enum(RefactoringStatus), default=RefactoringStatus.SUGGESTED, nullable=False)

    # Relationships
    issue = relationship('Issue', back_populates='refactorings')
    code_file = relationship('CodeFile', back_populates='refactorings')

    def to_dict(self) -> Dict:
        """Convert refactoring to dictionary."""
        return {
            'id': self.id,
            'issue_id': self.issue_id,
            'code_file_id': self.code_file_id,
            'refactoring_type': self.refactoring_type,
            'original_code': self.original_code,
            'refactored_code': self.refactored_code,
            'diff': self.diff,
            'explanation': self.explanation,
            'benefits': self.benefits,
            'confidence': self.confidence,
            'status': self.status.value
        }

    def __repr__(self):
        return f"<Refactoring(id={self.id}, type={self.refactoring_type}, status={self.status})>"


class Review(Base):
    """Pull request review results."""
    __tablename__ = 'reviews'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    pull_request_id = Column(String(36), ForeignKey('pull_requests.id'), nullable=False, index=True)
    reviewer_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    overall_score = Column(Integer)  # 0-100
    issues_count = Column(Integer, default=0)
    suggestions_count = Column(Integer, default=0)
    summary = Column(Text)
    approved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Composite indexes for common query patterns
    __table_args__ = (
        Index('idx_review_pr_created', 'pull_request_id', 'created_at'),
        Index('idx_review_reviewer_created', 'reviewer_id', 'created_at'),
    )

    # Relationships
    pull_request = relationship('PullRequest', back_populates='reviews')
    reviewer = relationship('User', back_populates='reviews')
    comments = relationship('ReviewComment', back_populates='review', cascade='all, delete-orphan')

    def to_dict(self) -> Dict:
        """Convert review to dictionary."""
        return {
            'id': self.id,
            'pull_request_id': self.pull_request_id,
            'reviewer_id': self.reviewer_id,
            'overall_score': self.overall_score,
            'issues_count': self.issues_count,
            'suggestions_count': self.suggestions_count,
            'summary': self.summary,
            'approved': self.approved,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f"<Review(id={self.id}, score={self.overall_score}, approved={self.approved})>"


class ReviewComment(Base):
    """Individual comments in a pull request review."""
    __tablename__ = 'review_comments'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    review_id = Column(String(36), ForeignKey('reviews.id'), nullable=False, index=True)
    file_path = Column(String(1000), nullable=False)
    line_number = Column(Integer)
    comment_text = Column(Text, nullable=False)
    severity = Column(Enum(IssueSeverity), default=IssueSeverity.INFO)
    github_comment_id = Column(String(100))  # GitHub comment ID for syncing
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    review = relationship('Review', back_populates='comments')

    def to_dict(self) -> Dict:
        """Convert review comment to dictionary."""
        return {
            'id': self.id,
            'review_id': self.review_id,
            'file_path': self.file_path,
            'line_number': self.line_number,
            'comment_text': self.comment_text,
            'severity': self.severity.value,
            'github_comment_id': self.github_comment_id,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f"<ReviewComment(id={self.id}, file={self.file_path}, line={self.line_number})>"


class SlackConfiguration(Base):
    """Slack webhook configuration and notification preferences."""
    __tablename__ = 'slack_configurations'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    repository_id = Column(String(36), ForeignKey('repositories.id'), index=True)  # Optional: per-repo config

    # Webhook configuration
    webhook_url = Column(String(500), nullable=False)
    channel = Column(String(100))  # Default channel (optional, can be in webhook URL)
    username = Column(String(100), default='Code Review Assistant')
    icon_emoji = Column(String(50), default=':robot_face:')

    # Notification preferences
    enabled = Column(Boolean, default=True)
    notify_pr_opened = Column(Boolean, default=True)
    notify_pr_analysis_complete = Column(Boolean, default=True)
    notify_critical_issues = Column(Boolean, default=True)
    notify_analysis_failed = Column(Boolean, default=True)

    # Threading
    use_threads = Column(Boolean, default=True)  # Reply in threads vs new messages
    thread_ts = Column(String(100))  # Last thread timestamp for this config

    # Filtering
    min_severity = Column(String(20), default='info')  # Minimum severity to notify
    only_failures = Column(Boolean, default=False)  # Only notify on failures

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship('User', backref='slack_configurations')
    repository = relationship('Repository', backref='slack_configurations')

    def to_dict(self) -> Dict:
        """Convert Slack configuration to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'repository_id': self.repository_id,
            'webhook_url': self.webhook_url[:50] + '...' if self.webhook_url else None,  # Redacted
            'channel': self.channel,
            'username': self.username,
            'icon_emoji': self.icon_emoji,
            'enabled': self.enabled,
            'notify_pr_opened': self.notify_pr_opened,
            'notify_pr_analysis_complete': self.notify_pr_analysis_complete,
            'notify_critical_issues': self.notify_critical_issues,
            'notify_analysis_failed': self.notify_analysis_failed,
            'use_threads': self.use_threads,
            'min_severity': self.min_severity,
            'only_failures': self.only_failures,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f"<SlackConfiguration(id={self.id}, user_id={self.user_id}, enabled={self.enabled})>"


class EmailConfiguration(Base):
    """Email SMTP configuration and notification preferences."""
    __tablename__ = 'email_configurations'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    repository_id = Column(String(36), ForeignKey('repositories.id'), index=True)  # Optional: per-repo config

    # SMTP configuration
    smtp_host = Column(String(200))
    smtp_port = Column(Integer, default=587)
    smtp_username = Column(String(200))
    smtp_password = Column(String(500))  # Should be encrypted
    smtp_use_tls = Column(Boolean, default=True)

    # Email settings
    from_email = Column(String(200), nullable=False)
    from_name = Column(String(100), default='Code Review Assistant')
    to_email = Column(String(200), nullable=False)  # Primary recipient
    reply_to = Column(String(200))

    # Notification preferences
    enabled = Column(Boolean, default=True)
    notify_pr_opened = Column(Boolean, default=True)
    notify_pr_analysis_complete = Column(Boolean, default=True)
    notify_critical_issues = Column(Boolean, default=True)
    notify_analysis_failed = Column(Boolean, default=True)

    # Digest mode
    enable_digest = Column(Boolean, default=False)
    digest_frequency = Column(String(20), default='daily')  # daily, weekly
    digest_time = Column(String(10), default='09:00')  # HH:MM
    last_digest_sent = Column(DateTime)

    # Filtering
    min_severity = Column(String(20), default='info')
    only_failures = Column(Boolean, default=False)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship('User', backref='email_configurations')
    repository = relationship('Repository', backref='email_configurations')

    def to_dict(self) -> Dict:
        """Convert Email configuration to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'repository_id': self.repository_id,
            'smtp_host': self.smtp_host,
            'smtp_port': self.smtp_port,
            'smtp_username': self.smtp_username,
            'smtp_use_tls': self.smtp_use_tls,
            'from_email': self.from_email,
            'from_name': self.from_name,
            'to_email': self.to_email,
            'reply_to': self.reply_to,
            'enabled': self.enabled,
            'notify_pr_opened': self.notify_pr_opened,
            'notify_pr_analysis_complete': self.notify_pr_analysis_complete,
            'notify_critical_issues': self.notify_critical_issues,
            'notify_analysis_failed': self.notify_analysis_failed,
            'enable_digest': self.enable_digest,
            'digest_frequency': self.digest_frequency,
            'digest_time': self.digest_time,
            'last_digest_sent': self.last_digest_sent.isoformat() if self.last_digest_sent else None,
            'min_severity': self.min_severity,
            'only_failures': self.only_failures,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f"<EmailConfiguration(id={self.id}, user_id={self.user_id}, to_email={self.to_email})>"


class DiscordConfiguration(Base):
    """Discord webhook configuration and notification preferences."""
    __tablename__ = 'discord_configurations'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    repository_id = Column(String(36), ForeignKey('repositories.id'), index=True)  # Optional: per-repo config

    # Webhook configuration
    webhook_url = Column(String(500), nullable=False)
    username = Column(String(100), default='Code Review Assistant')
    avatar_url = Column(String(500))

    # Notification preferences
    enabled = Column(Boolean, default=True)
    notify_pr_opened = Column(Boolean, default=True)
    notify_pr_analysis_complete = Column(Boolean, default=True)
    notify_critical_issues = Column(Boolean, default=True)
    notify_analysis_failed = Column(Boolean, default=True)

    # Filtering
    min_severity = Column(String(20), default='info')
    only_failures = Column(Boolean, default=False)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship('User', backref='discord_configurations')
    repository = relationship('Repository', backref='discord_configurations')

    def to_dict(self) -> Dict:
        """Convert Discord configuration to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'repository_id': self.repository_id,
            'webhook_url': self.webhook_url[:50] + '...' if self.webhook_url else None,  # Redacted
            'username': self.username,
            'avatar_url': self.avatar_url,
            'enabled': self.enabled,
            'notify_pr_opened': self.notify_pr_opened,
            'notify_pr_analysis_complete': self.notify_pr_analysis_complete,
            'notify_critical_issues': self.notify_critical_issues,
            'notify_analysis_failed': self.notify_analysis_failed,
            'min_severity': self.min_severity,
            'only_failures': self.only_failures,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f"<DiscordConfiguration(id={self.id}, user_id={self.user_id}, enabled={self.enabled})>"


class NotificationRule(Base):
    """Notification rules with conditions and actions."""
    __tablename__ = 'notification_rules'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    repository_id = Column(String(36), ForeignKey('repositories.id'), index=True)  # Optional: per-repo rule

    # Rule metadata
    name = Column(String(200), nullable=False)
    description = Column(Text)
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=100)  # Lower number = higher priority

    # Conditions (JSON-serialized)
    conditions = Column(JSON, nullable=False)  # {severity: [], category: [], file_patterns: [], pr_author: [], etc.}

    # Actions - which channels to notify
    notify_slack = Column(Boolean, default=False)
    notify_email = Column(Boolean, default=False)
    notify_discord = Column(Boolean, default=False)

    # Channel-specific configurations (references to config IDs)
    slack_config_id = Column(String(36), ForeignKey('slack_configurations.id'))
    email_config_id = Column(String(36), ForeignKey('email_configurations.id'))
    discord_config_id = Column(String(36), ForeignKey('discord_configurations.id'))

    # Quiet hours (JSON-serialized)
    quiet_hours_enabled = Column(Boolean, default=False)
    quiet_hours = Column(JSON)  # {start: "22:00", end: "08:00", timezone: "America/Chicago", days: [0,1,2,3,4,5,6]}

    # Batch/digest settings
    batch_notifications = Column(Boolean, default=False)
    batch_interval_minutes = Column(Integer, default=60)  # Wait N minutes before sending batch

    # Rate limiting
    rate_limit_enabled = Column(Boolean, default=False)
    max_notifications_per_hour = Column(Integer, default=10)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_triggered_at = Column(DateTime)
    trigger_count = Column(Integer, default=0)

    # Relationships
    user = relationship('User', backref='notification_rules')
    repository = relationship('Repository', backref='notification_rules')
    slack_config = relationship('SlackConfiguration')
    email_config = relationship('EmailConfiguration')
    discord_config = relationship('DiscordConfiguration')

    def to_dict(self) -> Dict:
        """Convert NotificationRule to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'repository_id': self.repository_id,
            'name': self.name,
            'description': self.description,
            'enabled': self.enabled,
            'priority': self.priority,
            'conditions': self.conditions,
            'notify_slack': self.notify_slack,
            'notify_email': self.notify_email,
            'notify_discord': self.notify_discord,
            'slack_config_id': self.slack_config_id,
            'email_config_id': self.email_config_id,
            'discord_config_id': self.discord_config_id,
            'quiet_hours_enabled': self.quiet_hours_enabled,
            'quiet_hours': self.quiet_hours,
            'batch_notifications': self.batch_notifications,
            'batch_interval_minutes': self.batch_interval_minutes,
            'rate_limit_enabled': self.rate_limit_enabled,
            'max_notifications_per_hour': self.max_notifications_per_hour,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_triggered_at': self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            'trigger_count': self.trigger_count
        }

    def __repr__(self):
        return f"<NotificationRule(id={self.id}, name={self.name}, enabled={self.enabled})>"


class CustomRule(Base):
    """Custom analysis rules created by users."""
    __tablename__ = 'custom_rules'

    id = Column(String(100), primary_key=True)  # User-defined rule ID (e.g., CUSTOM001)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    team_id = Column(String(36), ForeignKey('teams.id'), index=True)  # Optional team ownership

    # Rule metadata
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    category = Column(String(50), nullable=False)  # security, smell, complexity, etc.
    severity = Column(String(20), nullable=False)  # info, warning, error, critical
    languages = Column(String(200), nullable=False)  # Comma-separated list: python,javascript,java

    # Pattern matching
    pattern_type = Column(String(20), nullable=False)  # ast, regex, or both
    pattern_data = Column(JSON, nullable=False)  # {ast_patterns: [...], regex_pattern: {...}}

    # Action/Message
    message = Column(Text, nullable=False)  # Message to show when rule is triggered
    fix_suggestion = Column(Text)  # Suggestion for fixing the issue
    auto_fixable = Column(Boolean, default=False)

    # Status
    enabled = Column(Boolean, default=True)

    # Sharing and marketplace
    visibility = Column(String(20), default='private')  # private, public, unlisted
    is_featured = Column(Boolean, default=False)  # Featured in marketplace
    original_author = Column(String(200))  # Original author if forked
    forked_from = Column(String(100))  # Original rule ID if forked
    fork_count = Column(Integer, default=0)  # Number of times forked
    download_count = Column(Integer, default=0)  # Number of times downloaded
    tags = Column(String(500))  # Comma-separated tags for searching

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime)
    use_count = Column(Integer, default=0)

    # Relationships
    user = relationship('User', backref='custom_rules')
    ratings = relationship('RuleRating', back_populates='rule', cascade='all, delete-orphan')

    def to_dict(self) -> Dict:
        """Convert CustomRule to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'description': self.description,
            'category': self.category,
            'severity': self.severity,
            'languages': self.languages.split(',') if self.languages else [],
            'pattern_type': self.pattern_type,
            'ast_patterns': self.pattern_data.get('ast_patterns') if self.pattern_data else None,
            'regex_pattern': self.pattern_data.get('regex_pattern') if self.pattern_data else None,
            'message': self.message,
            'fix_suggestion': self.fix_suggestion,
            'auto_fixable': self.auto_fixable,
            'enabled': self.enabled,
            'visibility': self.visibility,
            'is_featured': self.is_featured,
            'original_author': self.original_author,
            'forked_from': self.forked_from,
            'fork_count': self.fork_count,
            'download_count': self.download_count,
            'tags': self.tags.split(',') if self.tags else [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None,
            'use_count': self.use_count
        }

    def __repr__(self):
        return f"<CustomRule(id={self.id}, name={self.name}, enabled={self.enabled})>"


class RuleRating(Base):
    """Ratings and reviews for custom rules in the marketplace."""
    __tablename__ = 'rule_ratings'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_id = Column(String(100), ForeignKey('custom_rules.id'), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)

    # Rating
    rating = Column(Integer, nullable=False)  # 1-5 stars
    review = Column(Text)  # Optional review text
    helpful_count = Column(Integer, default=0)  # Number of users who found this helpful

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Composite index for unique user+rule rating
    __table_args__ = (
        Index('idx_rule_user_rating', 'rule_id', 'user_id', unique=True),
    )

    # Relationships
    rule = relationship('CustomRule', back_populates='ratings')
    user = relationship('User', backref='rule_ratings')

    def to_dict(self) -> Dict:
        """Convert RuleRating to dictionary."""
        return {
            'id': self.id,
            'rule_id': self.rule_id,
            'user_id': self.user_id,
            'rating': self.rating,
            'review': self.review,
            'helpful_count': self.helpful_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f"<RuleRating(id={self.id}, rule_id={self.rule_id}, rating={self.rating})>"


class Plugin(Base):
    """Installed plugins."""
    __tablename__ = 'plugins'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)
    team_id = Column(String(36), ForeignKey('teams.id'), index=True)  # Optional team ownership

    # Plugin metadata
    name = Column(String(200), nullable=False, unique=True, index=True)
    version = Column(String(50), nullable=False)
    author = Column(String(200))
    description = Column(Text)
    plugin_type = Column(String(50), nullable=False)  # analyzer, formatter, reporter, integration, custom
    status = Column(String(50), default='inactive')  # active, inactive, error, disabled

    # Plugin source
    file_path = Column(String(1000), nullable=False)  # Path to plugin file
    homepage = Column(String(500))
    license = Column(String(100))
    supported_languages = Column(String(500))  # Comma-separated list

    # Configuration
    config_json = Column(JSON)  # Plugin-specific configuration

    # Status
    enabled = Column(Boolean, default=True)

    # Statistics
    load_count = Column(Integer, default=0)
    execution_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    last_error = Column(Text)

    # Metadata
    installed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime)

    # Relationships
    user = relationship('User', backref='plugins')

    def to_dict(self) -> Dict:
        """Convert Plugin to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'version': self.version,
            'author': self.author,
            'description': self.description,
            'plugin_type': self.plugin_type,
            'status': self.status,
            'file_path': self.file_path,
            'homepage': self.homepage,
            'license': self.license,
            'supported_languages': self.supported_languages.split(',') if self.supported_languages else [],
            'config': self.config_json,
            'enabled': self.enabled,
            'load_count': self.load_count,
            'execution_count': self.execution_count,
            'error_count': self.error_count,
            'last_error': self.last_error,
            'installed_at': self.installed_at.isoformat() if self.installed_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_used_at': self.last_used_at.isoformat() if self.last_used_at else None
        }

    def __repr__(self):
        return f"<Plugin(id={self.id}, name={self.name}, version={self.version}, status={self.status})>"


class Team(Base):
    """Teams/Organizations for collaborative code review."""
    __tablename__ = 'teams'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(200), nullable=False, index=True)
    slug = Column(String(200), unique=True, nullable=False, index=True)  # URL-friendly identifier
    description = Column(Text)

    # Settings
    visibility = Column(String(20), default='private')  # private, public
    allow_member_invites = Column(Boolean, default=False)  # Can members invite others

    # Billing/Plan (for future use)
    plan = Column(String(50), default='free')  # free, pro, enterprise

    # Statistics
    member_count = Column(Integer, default=0)
    repository_count = Column(Integer, default=0)
    rule_count = Column(Integer, default=0)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    members = relationship('TeamMember', back_populates='team', cascade='all, delete-orphan')
    invitations = relationship('TeamInvitation', back_populates='team', cascade='all, delete-orphan')

    def to_dict(self) -> Dict:
        """Convert Team to dictionary."""
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'description': self.description,
            'visibility': self.visibility,
            'allow_member_invites': self.allow_member_invites,
            'plan': self.plan,
            'member_count': self.member_count,
            'repository_count': self.repository_count,
            'rule_count': self.rule_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f"<Team(id={self.id}, name={self.name}, slug={self.slug})>"


class TeamMember(Base):
    """Team membership with role-based access control."""
    __tablename__ = 'team_members'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id = Column(String(36), ForeignKey('teams.id'), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey('users.id'), nullable=False, index=True)

    # Role: owner, admin, member, viewer
    # owner: full control (only one per team)
    # admin: manage members, settings, resources
    # member: create/edit own resources, view team resources
    # viewer: read-only access
    role = Column(String(20), nullable=False, default='member')

    # Permissions
    can_manage_members = Column(Boolean, default=False)
    can_manage_settings = Column(Boolean, default=False)
    can_create_rules = Column(Boolean, default=True)
    can_manage_plugins = Column(Boolean, default=False)

    # Status
    is_active = Column(Boolean, default=True)

    # Metadata
    joined_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    last_active_at = Column(DateTime)

    # Composite unique index
    __table_args__ = (
        Index('idx_team_user_membership', 'team_id', 'user_id', unique=True),
    )

    # Relationships
    team = relationship('Team', back_populates='members')
    user = relationship('User', backref='team_memberships')

    def to_dict(self) -> Dict:
        """Convert TeamMember to dictionary."""
        return {
            'id': self.id,
            'team_id': self.team_id,
            'user_id': self.user_id,
            'role': self.role,
            'can_manage_members': self.can_manage_members,
            'can_manage_settings': self.can_manage_settings,
            'can_create_rules': self.can_create_rules,
            'can_manage_plugins': self.can_manage_plugins,
            'is_active': self.is_active,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None,
            'last_active_at': self.last_active_at.isoformat() if self.last_active_at else None
        }

    def __repr__(self):
        return f"<TeamMember(id={self.id}, team_id={self.team_id}, user_id={self.user_id}, role={self.role})>"


class TeamInvitation(Base):
    """Pending invitations to join a team."""
    __tablename__ = 'team_invitations'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id = Column(String(36), ForeignKey('teams.id'), nullable=False, index=True)

    # Invitee (can be by email or user_id)
    email = Column(String(255), index=True)  # For users not yet registered
    user_id = Column(String(36), ForeignKey('users.id'), index=True)  # For existing users

    # Invitation details
    invited_by_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    role = Column(String(20), nullable=False, default='member')
    token = Column(String(100), unique=True, nullable=False, index=True)  # Unique invitation token

    # Status
    status = Column(String(20), default='pending')  # pending, accepted, declined, expired

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    expires_at = Column(DateTime, nullable=False)  # Invitation expiry
    responded_at = Column(DateTime)

    # Relationships
    team = relationship('Team', back_populates='invitations')
    invited_by = relationship('User', foreign_keys=[invited_by_id], backref='sent_invitations')
    user = relationship('User', foreign_keys=[user_id], backref='received_invitations')

    def to_dict(self) -> Dict:
        """Convert TeamInvitation to dictionary."""
        return {
            'id': self.id,
            'team_id': self.team_id,
            'email': self.email,
            'user_id': self.user_id,
            'invited_by_id': self.invited_by_id,
            'role': self.role,
            'token': self.token,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'responded_at': self.responded_at.isoformat() if self.responded_at else None
        }

    def __repr__(self):
        return f"<TeamInvitation(id={self.id}, team_id={self.team_id}, status={self.status})>"


class AnalysisSchedule(Base):
    """Scheduled recurring analysis for repositories."""
    __tablename__ = 'analysis_schedules'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    repository_id = Column(String(36), ForeignKey('repositories.id'), nullable=False, index=True)

    # Schedule configuration
    name = Column(String(200), nullable=False)
    description = Column(Text)
    schedule_type = Column(String(20), nullable=False, default='cron')  # cron, interval, daily, weekly
    cron_expression = Column(String(100))  # For cron type: "0 0 * * *" = daily at midnight
    interval_minutes = Column(Integer)  # For interval type: 60 = every hour

    # Analysis configuration
    analyze_all_files = Column(Boolean, default=True)
    file_patterns = Column(Text)  # JSON array of glob patterns
    enabled_rules = Column(Text)  # JSON array of rule IDs, null = all rules
    severity_threshold = Column(String(20), default='info')  # info, warning, error, critical

    # Notification settings
    notify_on_completion = Column(Boolean, default=False)
    notify_on_issues = Column(Boolean, default=True)
    notification_emails = Column(Text)  # JSON array of email addresses
    slack_webhook_url = Column(String(500))

    # Status
    enabled = Column(Boolean, default=True)
    last_run_at = Column(DateTime)
    next_run_at = Column(DateTime)
    run_count = Column(Integer, default=0)

    # Metadata
    created_by_id = Column(String(36), ForeignKey('users.id'), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    repository = relationship('Repository', backref='schedules')
    created_by = relationship('User', backref='created_schedules')
    runs = relationship('ScheduledRun', back_populates='schedule', cascade='all, delete-orphan')

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        import json
        return {
            'id': self.id,
            'repository_id': self.repository_id,
            'name': self.name,
            'description': self.description,
            'schedule_type': self.schedule_type,
            'cron_expression': self.cron_expression,
            'interval_minutes': self.interval_minutes,
            'analyze_all_files': self.analyze_all_files,
            'file_patterns': json.loads(self.file_patterns) if self.file_patterns else [],
            'enabled_rules': json.loads(self.enabled_rules) if self.enabled_rules else None,
            'severity_threshold': self.severity_threshold,
            'notify_on_completion': self.notify_on_completion,
            'notify_on_issues': self.notify_on_issues,
            'notification_emails': json.loads(self.notification_emails) if self.notification_emails else [],
            'slack_webhook_url': self.slack_webhook_url,
            'enabled': self.enabled,
            'last_run_at': self.last_run_at.isoformat() if self.last_run_at else None,
            'next_run_at': self.next_run_at.isoformat() if self.next_run_at else None,
            'run_count': self.run_count,
            'created_by_id': self.created_by_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

    def __repr__(self):
        return f"<AnalysisSchedule(id={self.id}, name={self.name}, enabled={self.enabled})>"


class ScheduledRun(Base):
    """Individual execution run of a scheduled analysis."""
    __tablename__ = 'scheduled_runs'

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    schedule_id = Column(String(36), ForeignKey('analysis_schedules.id'), nullable=False, index=True)

    # Execution details
    status = Column(String(20), default='pending')  # pending, running, completed, failed, cancelled
    celery_task_id = Column(String(100), index=True)

    # Results
    files_analyzed = Column(Integer, default=0)
    issues_found = Column(Integer, default=0)
    critical_issues = Column(Integer, default=0)
    error_issues = Column(Integer, default=0)
    warning_issues = Column(Integer, default=0)
    info_issues = Column(Integer, default=0)

    # Timing
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_seconds = Column(Float)

    # Output
    error_message = Column(Text)  # If status = failed
    result_summary = Column(Text)  # JSON with detailed results
    notification_sent = Column(Boolean, default=False)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    # Relationships
    schedule = relationship('AnalysisSchedule', back_populates='runs')

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        import json
        return {
            'id': self.id,
            'schedule_id': self.schedule_id,
            'status': self.status,
            'celery_task_id': self.celery_task_id,
            'files_analyzed': self.files_analyzed,
            'issues_found': self.issues_found,
            'critical_issues': self.critical_issues,
            'error_issues': self.error_issues,
            'warning_issues': self.warning_issues,
            'info_issues': self.info_issues,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_seconds': self.duration_seconds,
            'error_message': self.error_message,
            'result_summary': json.loads(self.result_summary) if self.result_summary else None,
            'notification_sent': self.notification_sent,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    def __repr__(self):
        return f"<ScheduledRun(id={self.id}, schedule_id={self.schedule_id}, status={self.status})>"


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
