"""Database models and manager for Chat Application"""

from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, JSON, ForeignKey, Boolean, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime, timedelta
import uuid
from pathlib import Path
from typing import Optional, List, Dict

Base = declarative_base()


class User(Base):
    """User model for authentication"""
    __tablename__ = 'users'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    is_guest = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    sessions = relationship('Session', back_populates='user', cascade='all, delete-orphan')
    conversations = relationship('Conversation', back_populates='user', cascade='all, delete-orphan')

    def to_dict(self) -> Dict:
        """Convert user model to dictionary"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'is_guest': self.is_guest,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Session(Base):
    """Session model for authentication tokens"""
    __tablename__ = 'sessions'

    id = Column(String, primary_key=True)  # Session token
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    last_accessed = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship('User', back_populates='sessions')


class Conversation(Base):
    """Conversation model for chat threads"""
    __tablename__ = 'conversations'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey('users.id'), nullable=False, index=True)
    title = Column(String(200), nullable=True)
    llm_provider = Column(String(50), default='ollama')  # ollama, openai, anthropic
    llm_model = Column(String(100), nullable=True)
    system_prompt = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    metadata_json = Column(JSON, nullable=True)

    # Relationships
    user = relationship('User', back_populates='conversations')
    messages = relationship(
        'Message',
        back_populates='conversation',
        cascade='all, delete-orphan',
        order_by='Message.created_at'
    )

    def to_dict(self, include_messages: bool = False) -> Dict:
        """Convert conversation model to dictionary"""
        result = {
            'id': self.id,
            'title': self.title,
            'llm_provider': self.llm_provider,
            'llm_model': self.llm_model,
            'system_prompt': self.system_prompt,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'metadata': self.metadata_json
        }
        if include_messages:
            result['messages'] = [m.to_dict() for m in self.messages]
        return result


class Message(Base):
    """Message model for chat messages"""
    __tablename__ = 'messages'

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id = Column(String, ForeignKey('conversations.id'), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    metadata_json = Column(JSON, nullable=True)

    # Relationships
    conversation = relationship('Conversation', back_populates='messages')

    def to_dict(self) -> Dict:
        """Convert message model to dictionary"""
        return {
            'id': self.id,
            'role': self.role,
            'content': self.content,
            'tokens': self.tokens,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'metadata': self.metadata_json
        }


class DatabaseManager:
    """Manage database connections and operations"""

    def __init__(self, db_url: Optional[str] = None):
        """
        Initialize database manager

        Args:
            db_url: Database URL (defaults to SQLite in ./data/database.db)
        """
        if db_url is None:
            db_dir = Path('./data')
            db_dir.mkdir(parents=True, exist_ok=True)
            db_url = f"sqlite:///{db_dir}/database.db"

        self.engine = create_engine(db_url, echo=False)
        Base.metadata.create_all(self.engine)
        self._migrate_schema()
        self.SessionLocal = sessionmaker(bind=self.engine)

    def _migrate_schema(self):
        """
        Add columns that create_all() can't add on its own.

        create_all() only creates missing TABLES - it never alters an
        existing table's columns. is_guest was added to the User model
        after this app already had a live users table (and a live
        database.db) without it, so on an existing DB this fills the
        gap with a plain ALTER TABLE. A no-op on a brand new DB, since
        create_all() above already created the column there.
        """
        inspector = inspect(self.engine)
        if 'users' not in inspector.get_table_names():
            return

        columns = {col['name'] for col in inspector.get_columns('users')}
        if 'is_guest' not in columns:
            with self.engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE users ADD COLUMN is_guest BOOLEAN NOT NULL DEFAULT 0"
                ))
                conn.commit()

    def get_session(self):
        """
        Get database session (use with context manager)

        Returns:
            Database session
        """
        return self.SessionLocal()
