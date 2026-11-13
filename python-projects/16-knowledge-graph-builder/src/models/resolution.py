"""Entity resolution records: other names an entity is known by, merge suggestions, and the merge history (for undo)"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SuggestionStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"  # a person said these are different; never suggested again


class EntityAlias(Base):
    """Another way an entity's name was written. A later document using it lands on the same entity."""
    __tablename__ = "entity_aliases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    entity_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(300), unique=True)
    name: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MergeSuggestion(Base):
    __tablename__ = "merge_suggestions"
    __table_args__ = (UniqueConstraint("entity_a_id", "entity_b_id", name="uq_merge_pair"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    entity_a_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    entity_b_id: Mapped[str] = mapped_column(ForeignKey("entities.id", ondelete="CASCADE"), index=True)
    score: Mapped[float] = mapped_column(Float)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    llm_verdict: Mapped[str | None] = mapped_column(String(10), nullable=True)  # yes | no | None (not asked / failed)
    status: Mapped[SuggestionStatus] = mapped_column(Enum(SuggestionStatus), default=SuggestionStatus.PENDING, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MergeRecord(Base):
    """What a merge changed, enough to undo it. No foreign keys on purpose: the history outlives the rows."""
    __tablename__ = "merge_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    keep_id: Mapped[str] = mapped_column(String(32), index=True)
    absorbed_id: Mapped[str] = mapped_column(String(32))
    keep_name: Mapped[str] = mapped_column(String(300))
    absorbed_name: Mapped[str] = mapped_column(String(300))
    how: Mapped[str] = mapped_column(String(30))  # auto | suggestion | manual
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
