"""Stored embeddings of passages and facts (so a question only has to embed itself)"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class Embedding(Base):
    """One vector (float32 bytes) for either a chunk or a fact, made by one model"""
    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint("chunk_id", "model", name="uq_embedding_chunk"),
        UniqueConstraint("fact_id", "model", name="uq_embedding_fact"),
        CheckConstraint("(chunk_id IS NULL) != (fact_id IS NULL)", name="ck_embedding_one_target"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), nullable=True, index=True)
    fact_id: Mapped[str | None] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"), nullable=True, index=True)
    model: Mapped[str] = mapped_column(String(120))
    dim: Mapped[int] = mapped_column(Integer)
    vector: Mapped[bytes] = mapped_column(LargeBinary)
    text_hash: Mapped[str] = mapped_column(String(16), default="")  # a fact's text changes when entities are renamed or merged
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
