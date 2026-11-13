"""Documents, chunks, entities and facts (with the quotes that support them)"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


ENTITY_TYPES = ("person", "organization", "place", "product", "event", "concept")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    title: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str | None] = mapped_column(String(300), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus), default=DocumentStatus.PENDING, index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    chunks_done: Mapped[int] = mapped_column(Integer, default=0)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)  # candidates / accepted / rejected by reason
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan", passive_deletes=True)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    index: Mapped[int] = mapped_column(Integer)
    start: Mapped[int] = mapped_column(Integer)  # character offsets in Document.text
    end: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)

    document = relationship("Document", back_populates="chunks")


class Entity(Base):
    __tablename__ = "entities"
    __table_args__ = (UniqueConstraint("key", name="uq_entity_key"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(300))  # display name (first form seen)
    key: Mapped[str] = mapped_column(String(300))  # normalised name used for exact matching (step 2 adds smarter matching)
    type: Mapped[str] = mapped_column(String(30), default="concept", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Fact(Base):
    """One statement: subject --predicate--> object (an entity or a plain value), optionally valid for a period"""
    __tablename__ = "facts"
    __table_args__ = (
        UniqueConstraint("subject_id", "predicate", "object_id", "object_value", "valid_from", "valid_to", name="uq_fact"),
        Index("ix_fact_subject", "subject_id"),
        Index("ix_fact_object", "object_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    subject_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"))
    predicate: Mapped[str] = mapped_column(String(80))
    object_id: Mapped[str] = mapped_column(String(32), ForeignKey("entities.id", ondelete="CASCADE"), nullable=True)
    object_value: Mapped[str] = mapped_column(String(300), default="")  # "" when the object is an entity
    valid_from: Mapped[str] = mapped_column(String(10), default="")  # YYYY, YYYY-MM or YYYY-MM-DD; "" = not stated
    valid_to: Mapped[str] = mapped_column(String(10), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    subject = relationship("Entity", foreign_keys=[subject_id])
    object = relationship("Entity", foreign_keys=[object_id])
    sources = relationship("FactSource", back_populates="fact", cascade="all, delete-orphan", passive_deletes=True)


class FactSource(Base):
    """Where a fact was read: the exact quote, the chunk and the document"""
    __tablename__ = "fact_sources"
    __table_args__ = (UniqueConstraint("fact_id", "chunk_id", "evidence", name="uq_fact_source"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    fact_id: Mapped[str] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    chunk_id: Mapped[str] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), index=True)
    evidence: Mapped[str] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(default=False)  # True when the double-check pass confirmed it
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    fact = relationship("Fact", back_populates="sources")
