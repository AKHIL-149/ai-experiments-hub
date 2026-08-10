"""
Summary model for storing generated video summaries
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column, Integer, String, DateTime, Enum, Text, JSON, ForeignKey
)
from sqlalchemy.orm import relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.video import Video


class SummaryType(enum.Enum):
    """Summary types"""
    OVERALL = "overall"  # Overall video summary
    SCENE = "scene"  # Scene-level summary
    CHAPTER = "chapter"  # Chapter/section summary
    HIGHLIGHT = "highlight"  # Highlight reel summary
    BRIEF = "brief"  # Brief/short summary
    DETAILED = "detailed"  # Detailed/long summary
    TECHNICAL = "technical"  # Technical summary


class Summary(Base):
    """
    Summary model for storing generated video summaries

    Attributes:
        id: Primary key
        video_id: Foreign key to parent video
        summary_type: Type of summary
        title: Summary title
        content: Summary text content
        timestamp_ranges: JSON array of timestamp ranges referenced
        metadata: Additional metadata (JSON)
        created_at: Timestamp when summary was created
        updated_at: Timestamp of last update
    """
    __tablename__ = "summaries"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Foreign key
    video_id = Column(
        Integer,
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Summary classification
    summary_type = Column(
        Enum(SummaryType),
        nullable=False,
        default=SummaryType.OVERALL,
        index=True
    )

    # Content
    title = Column(String(500), nullable=True)
    content = Column(Text, nullable=False)

    # Timestamp references
    # Format: [{"start": 10.5, "end": 20.3, "description": "..."}, ...]
    timestamp_ranges = Column(JSON, nullable=True, default=list)

    # Additional metadata
    # Can store: word_count, generation_time, model_used, key_points, etc.
    extra_metadata = Column("metadata", JSON, nullable=True, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    video = relationship("Video", back_populates="summaries")

    def __repr__(self):
        return f"<Summary(id={self.id}, video_id={self.video_id}, type={self.summary_type.value})>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "summary_type": self.summary_type.value,
            "title": self.title,
            "content": self.content,
            "timestamp_ranges": self.timestamp_ranges,
            "metadata": self.extra_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
