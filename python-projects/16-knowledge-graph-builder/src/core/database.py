"""SQLAlchemy engine, session factory and table creation"""
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from src.core.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str, echo: bool = False):
    kwargs = {}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        if ":memory:" not in url:
            raw = url.split("///", 1)[-1]
            if raw:
                Path(raw).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, echo=echo, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):  # enforce ON DELETE CASCADE
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()
    return engine


_settings = get_settings()
engine = make_engine(_settings.database_url, _settings.db_echo)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    from src import models  # noqa: F401  (registers tables)
    Base.metadata.create_all(bind=engine)
