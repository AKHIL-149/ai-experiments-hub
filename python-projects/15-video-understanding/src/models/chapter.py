"""
Chapter model for storing detected video chapter boundaries
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, JSON, ForeignKey
)
from sqlalchemy.orm import relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.video import Video


class Chapter(Base):
    """
    Chapter model for storing detected chapter boundaries in videos

    Attributes:
        id: Primary key
        video_id: Foreign key to parent video
        chapter_number: Sequential chapter number in video
        title: Chapter title
        description: Chapter description
        start_time: Start time in seconds
        end_time: End time in seconds
        keyframe_path: Path to representative frame
        importance_score: Chapter importance score (0.0 to 1.0)
        metadata: Additional metadata (JSON)
        created_at: Timestamp when chapter was created
    """
    __tablename__ = "chapters"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Foreign key
    video_id = Column(
        Integer,
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Basic information
    chapter_number = Column(Integer, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)

    # Temporal information
    start_time = Column(Float, nullable=False, index=True)
    end_time = Column(Float, nullable=False, index=True)

    # File paths
    keyframe_path = Column(String(1000), nullable=True)

    # Importance scoring
    importance_score = Column(Float, nullable=False, default=0.5)

    # Additional metadata
    extra_metadata = Column("metadata", JSON, nullable=True, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    video = relationship("Video", back_populates="chapters")

    def __repr__(self):
        return f"<Chapter(id={self.id}, video_id={self.video_id}, number={self.chapter_number}, time={self.start_time:.1f}-{self.end_time:.1f}s)>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "chapter_number": self.chapter_number,
            "title": self.title,
            "description": self.description,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.end_time - self.start_time,
            "keyframe_path": self.keyframe_path,
            "importance_score": self.importance_score,
            "metadata": self.extra_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
