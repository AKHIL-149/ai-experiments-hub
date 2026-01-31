"""
Database models and management for Research Assistant.

Implements 6 tables:
- User: User accounts with authentication
- Session: User sessions for authentication
- ResearchQuery: Research queries/jobs
- Source: Individual sources (web, arxiv, documents)
- Finding: Key findings extracted from sources
- Citation: Citation tracking for proper attribution
"""

import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    create_engine,
    Column,
    String,
    Text,
    Integer,
    Float,
    Boolean,
    DateTime,
    JSON,
    ForeignKey,
    Index,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session, sessionmaker
from sqlalchemy.pool import StaticPool

Base = declarative_base()


class User(Base):
    """User account model."""

    __tablename__ = 'users'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sessions = relationship('UserSession', back_populates='user', cascade='all, delete-orphan')
    research_queries = relationship('ResearchQuery', back_populates='user', cascade='all, delete-orphan')

    def to_dict(self) -> Dict[str, Any]:
        """Convert user to dictionary (exclude password_hash)."""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class UserSession(Base):
    """Session model for authentication."""

    __tablename__ = 'sessions'

    id = Column(String, primary_key=True)  # Session token
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_accessed = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship('User', back_populates='sessions')

    def is_expired(self) -> bool:
        """Check if session has expired."""
        return datetime.utcnow() > self.expires_at

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary."""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'last_accessed': self.last_accessed.isoformat() if self.last_accessed else None,
        }


class ResearchQuery(Base):
    """Research query/job model."""

    __tablename__ = 'research_queries'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    query_text = Column(Text, nullable=False)
    status = Column(String(20), default='pending', index=True)  # pending, processing, completed, failed

    # Configuration
    search_web = Column(Boolean, default=True)
    search_arxiv = Column(Boolean, default=True)
    search_documents = Column(Boolean, default=True)
    max_sources = Column(Integer, default=20)
    verification_level = Column(String(20), default='strict')  # strict, standard, lenient
    citation_style = Column(String(20), default='APA')  # APA, MLA, Chicago, IEEE

    # Results
    summary = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    processing_time_seconds = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    metadata_json = Column(JSON, nullable=True)

    # Relationships
    user = relationship('User', back_populates='research_queries')
    sources = relationship('Source', back_populates='query', cascade='all, delete-orphan')
    findings = relationship('Finding', back_populates='query', cascade='all, delete-orphan')
    citations = relationship('Citation', back_populates='query', cascade='all, delete-orphan')

    # Indexes
    __table_args__ = (
        Index('idx_user_created', 'user_id', 'created_at'),
        Index('idx_status_created', 'status', 'created_at'),
    )

    def to_dict(self, include_sources=False, include_findings=False, include_citations=False) -> Dict[str, Any]:
        """Convert research query to dictionary."""
        result = {
            'id': self.id,
            'user_id': self.user_id,
            'query_text': self.query_text,
            'status': self.status,
            'search_web': self.search_web,
            'search_arxiv': self.search_arxiv,
            'search_documents': self.search_documents,
            'max_sources': self.max_sources,
            'verification_level': self.verification_level,
            'citation_style': self.citation_style,
            'summary': self.summary,
            'confidence_score': self.confidence_score,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'processing_time_seconds': self.processing_time_seconds,
            'error_message': self.error_message,
            'metadata': self.metadata_json,
        }

        if include_sources and self.sources:
            result['sources'] = [s.to_dict() for s in self.sources]

        if include_findings and self.findings:
            result['findings'] = [f.to_dict() for f in self.findings]

        if include_citations and self.citations:
            result['citations'] = [c.to_dict() for c in self.citations]

        return result

    def mark_processing(self) -> None:
        """Mark query as processing."""
        self.status = 'processing'
        self.started_at = datetime.utcnow()

    def mark_completed(self, summary: str, confidence: float) -> None:
        """Mark query as completed."""
        self.status = 'completed'
        self.completed_at = datetime.utcnow()
        self.summary = summary
        self.confidence_score = confidence
        if self.started_at:
            self.processing_time_seconds = (self.completed_at - self.started_at).total_seconds()

    def mark_failed(self, error: str) -> None:
        """Mark query as failed."""
        self.status = 'failed'
        self.completed_at = datetime.utcnow()
        self.error_message = error


class Source(Base):
    """Source model for individual sources."""

    __tablename__ = 'sources'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    query_id = Column(String, ForeignKey('research_queries.id'), nullable=False, index=True)

    # Source identification
    source_type = Column(String(20), nullable=False)  # web, arxiv, document
    title = Column(String(500), nullable=False)
    url = Column(String(1000), nullable=True)
    authors = Column(JSON, nullable=True)  # List of author names
    published_date = Column(DateTime, nullable=True)

    # Content
    content = Column(Text, nullable=False)
    content_hash = Column(String(64), nullable=False, index=True)  # SHA256

    # Retrieval metadata
    relevance_score = Column(Float, nullable=False)  # 0-1 similarity score
    authority_score = Column(Float, nullable=True)  # 0-1 authority score
    retrieval_rank = Column(Integer, nullable=False)  # Order retrieved
    fetch_timestamp = Column(DateTime, default=datetime.utcnow)

    # Additional metadata
    metadata_json = Column(JSON, nullable=True)

    # Relationships
    query = relationship('ResearchQuery', back_populates='sources')
    citations = relationship('Citation', back_populates='source')

    # Indexes
    __table_args__ = (
        Index('idx_query_relevance', 'query_id', 'relevance_score'),
        Index('idx_content_hash', 'content_hash'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert source to dictionary."""
        return {
            'id': self.id,
            'query_id': self.query_id,
            'source_type': self.source_type,
            'title': self.title,
            'url': self.url,
            'authors': self.authors,
            'published_date': self.published_date.isoformat() if self.published_date else None,
            'content': self.content[:500] + '...' if len(self.content) > 500 else self.content,  # Truncate long content
            'content_hash': self.content_hash,
            'relevance_score': self.relevance_score,
            'authority_score': self.authority_score,
            'retrieval_rank': self.retrieval_rank,
            'fetch_timestamp': self.fetch_timestamp.isoformat() if self.fetch_timestamp else None,
            'metadata': self.metadata_json,
        }


class Finding(Base):
    """Finding model for extracted key findings."""

    __tablename__ = 'findings'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    query_id = Column(String, ForeignKey('research_queries.id'), nullable=False, index=True)

    # Finding content
    finding_text = Column(Text, nullable=False)
    finding_type = Column(String(50), nullable=True)  # fact, argument, statistic, definition, etc.
    confidence = Column(Float, nullable=False)  # 0-1 confidence score

    # Source tracking
    source_ids = Column(JSON, nullable=False)  # List of source IDs supporting this finding

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    metadata_json = Column(JSON, nullable=True)

    # Relationships
    query = relationship('ResearchQuery', back_populates='findings')

    # Indexes
    __table_args__ = (
        Index('idx_query_confidence', 'query_id', 'confidence'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert finding to dictionary."""
        return {
            'id': self.id,
            'query_id': self.query_id,
            'finding_text': self.finding_text,
            'finding_type': self.finding_type,
            'confidence': self.confidence,
            'source_ids': self.source_ids,
            'source_count': len(self.source_ids) if self.source_ids else 0,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'metadata': self.metadata_json,
        }


class Citation(Base):
    """Citation model for source attribution."""

    __tablename__ = 'citations'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    query_id = Column(String, ForeignKey('research_queries.id'), nullable=False, index=True)
    source_id = Column(String, ForeignKey('sources.id'), nullable=False, index=True)

    # Citation details
    citation_text = Column(Text, nullable=True)  # Quoted text from source
    context = Column(Text, nullable=True)  # Surrounding context
    citation_style = Column(String(20), nullable=False)  # APA, MLA, Chicago, IEEE
    formatted_citation = Column(Text, nullable=False)  # Fully formatted citation

    # Position in report
    section = Column(String(100), nullable=True)  # Which section of report
    citation_number = Column(Integer, nullable=True)  # Sequential number in report

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    metadata_json = Column(JSON, nullable=True)

    # Relationships
    query = relationship('ResearchQuery', back_populates='citations')
    source = relationship('Source', back_populates='citations')

    # Indexes
    __table_args__ = (
        Index('idx_query_source', 'query_id', 'source_id'),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert citation to dictionary."""
        return {
            'id': self.id,
            'query_id': self.query_id,
            'source_id': self.source_id,
            'citation_text': self.citation_text,
            'context': self.context,
            'citation_style': self.citation_style,
            'formatted_citation': self.formatted_citation,
            'section': self.section,
            'citation_number': self.citation_number,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'metadata': self.metadata_json,
        }


class DatabaseManager:
    """Database connection and session management."""

    def __init__(self, database_url: str = 'sqlite:///./data/database.db', echo: bool = False):
        """
        Initialize database manager.

        Args:
            database_url: SQLAlchemy database URL
            echo: Whether to echo SQL statements (for debugging)
        """
        # Use StaticPool for SQLite to avoid threading issues
        if database_url.startswith('sqlite'):
            self.engine = create_engine(
                database_url,
                connect_args={'check_same_thread': False},
                poolclass=StaticPool,
                echo=echo
            )
        else:
            self.engine = create_engine(database_url, echo=echo)

        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def create_tables(self) -> None:
        """Create all database tables."""
        Base.metadata.create_all(bind=self.engine)

    def drop_tables(self) -> None:
        """Drop all database tables (use with caution!)."""
        Base.metadata.drop_all(bind=self.engine)

    def get_session(self) -> Session:
        """Get a new database session."""
        return self.SessionLocal()

    def cleanup_expired_sessions(self, session: Session) -> int:
        """
        Remove expired sessions from database.

        Args:
            session: Database session

        Returns:
            Number of sessions deleted
        """
        now = datetime.utcnow()
        expired = session.query(UserSession).filter(UserSession.expires_at < now).all()
        count = len(expired)

        for s in expired:
            session.delete(s)

        session.commit()
        return count

    def get_user_by_username(self, session: Session, username: str) -> Optional[User]:
        """Get user by username."""
        return session.query(User).filter(User.username == username).first()

    def get_user_by_email(self, session: Session, email: str) -> Optional[User]:
        """Get user by email."""
        return session.query(User).filter(User.email == email).first()

    def get_user_by_id(self, session: Session, user_id: str) -> Optional[User]:
        """Get user by ID."""
        return session.query(User).filter(User.id == user_id).first()

    def get_session_by_token(self, session: Session, token: str) -> Optional[UserSession]:
        """Get session by token."""
        return session.query(UserSession).filter(UserSession.id == token).first()

    def get_research_queries_by_user(
        self,
        session: Session,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None
    ) -> List[ResearchQuery]:
        """Get research queries for a user."""
        query = session.query(ResearchQuery).filter(ResearchQuery.user_id == user_id)

        if status:
            query = query.filter(ResearchQuery.status == status)

        query = query.order_by(ResearchQuery.created_at.desc())
        query = query.limit(limit).offset(offset)

        return query.all()

    def get_research_query_by_id(
        self,
        session: Session,
        query_id: str,
        user_id: Optional[str] = None
    ) -> Optional[ResearchQuery]:
        """Get research query by ID, optionally filtering by user."""
        query = session.query(ResearchQuery).filter(ResearchQuery.id == query_id)

        if user_id:
            query = query.filter(ResearchQuery.user_id == user_id)

        return query.first()
