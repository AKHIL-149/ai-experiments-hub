"""
Database configuration and session management
"""

import os
from contextlib import contextmanager
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, sessionmaker

load_dotenv()

# Database URL from environment
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/multi_agent_orchestrator"
)

# Create SQLAlchemy engine
#
# SQLite-specific tuning: this app runs a FastAPI server and a multi-process
# (prefork) Celery worker pool against the same on-disk SQLite file. SQLite
# allows only one writer at a time; without a busy_timeout, a second writer
# that arrives while another connection's write transaction is still open
# gets "database is locked" immediately instead of waiting. Confirmed live -
# two Celery worker processes assigning two workflow tasks to the same
# agent within the same millisecond both crashed with
# sqlite3.OperationalError: database is locked on their very next
# UPDATE, leaving the tasks permanently stuck in an intermediate QUEUED
# state (their own failure-handling UPDATE hit the same lock and failed
# too). connect_args={"timeout": ...} makes the underlying sqlite3
# connection wait (and internally retry) for up to that many seconds
# before raising, which is enough for these sub-second write bursts to
# clear. WAL mode additionally lets readers proceed without blocking on a
# writer at all. Neither applies to Postgres, so both are gated on the URL.
_is_sqlite = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    echo=os.getenv("DB_ECHO", "false").lower() == "true",
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    connect_args={"timeout": 30} if _is_sqlite else {},
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

# Create SessionLocal class
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# Create Base class for models
Base = declarative_base()


@contextmanager
def get_db() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.

    Usage:
        with get_db() as db:
            db.query(Task).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db_session() -> Session:
    """
    Dependency for FastAPI endpoints.

    Usage:
        @app.get("/tasks")
        def get_tasks(db: Session = Depends(get_db_session)):
            return db.query(Task).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class DatabaseManager:
    """
    Database manager for direct session management.
    """

    def __init__(self):
        self.engine = engine
        self.SessionLocal = SessionLocal

    def get_session(self) -> Session:
        """Get a new database session"""
        return self.SessionLocal()

    @contextmanager
    def session_scope(self) -> Generator[Session, None, None]:
        """Provide a transactional scope around a series of operations"""
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_all(self):
        """Create all tables"""
        Base.metadata.create_all(bind=self.engine)

    def drop_all(self):
        """Drop all tables (use with caution!)"""
        Base.metadata.drop_all(bind=self.engine)


# Singleton instance
db_manager = DatabaseManager()
