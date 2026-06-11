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
