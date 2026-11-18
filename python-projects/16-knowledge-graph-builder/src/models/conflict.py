"""Facts that cannot both be true, and what a person decided about them"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ConflictStatus(str, enum.Enum):
    OPEN = "open"
    RESOLVED = "resolved"       # a person chose one fact (the other is then left out) or ended one of them at the other's start
    DISMISSED = "dismissed"     # a person said both are true (they are not in conflict)


class Conflict(Base):
    """Two facts that look like they contradict each other. Facts are never deleted: a resolved conflict only
    records which one a person trusts, and can be reopened."""
    __tablename__ = "conflicts"
    __table_args__ = (UniqueConstraint("fact_a_id", "fact_b_id", name="uq_conflict_pair"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(30))                    # different_object | different_value | different_holder | reversed
    severity: Mapped[str] = mapped_column(String(10))                # certain | possible (see conflicts.py)
    fact_a_id: Mapped[str] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"), index=True)
    fact_b_id: Mapped[str] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"), index=True)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    llm_verdict: Mapped[str | None] = mapped_column(String(10), nullable=True)   # yes | no | unsure | None (not asked)
    status: Mapped[ConflictStatus] = mapped_column(Enum(ConflictStatus), default=ConflictStatus.OPEN, index=True)
    resolution: Mapped[str | None] = mapped_column(String(20), nullable=True)    # keep_a | keep_b | both | succession
    data: Mapped[dict] = mapped_column(JSON, default=dict)           # what a resolution changed, to undo it
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PredicateKind(Base):
    """How a relation word behaves ("headquartered in": one object at a time; "CEO of": one holder at a time), as the
    model judged it for words the built-in list does not know. Not personal data, so it is shared."""
    __tablename__ = "predicate_kinds"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))                    # one_object | one_subject | many
    model: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
