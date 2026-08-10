"""
Highlight model for storing detected important moments in videos
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Enum, Text, JSON, ForeignKey
)
from sqlalchemy.orm import relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.video import Video


class HighlightType(enum.Enum):
    """Highlight types"""
    ACTION = "action"  # Action-packed moment
    DIALOGUE = "dialogue"  # Important dialogue
    KEY_MOMENT = "key_moment"  # Key moment
    EMOTIONAL = "emotional"  # Emotional moment
    VISUAL = "visual"  # Visually interesting
    INFORMATIVE = "informative"  # Information-dense
    TRANSITION = "transition"  # Important transition
    UNKNOWN = "unknown"


class Highlight(Base):
    """
    Highlight model for storing detected important moments in videos

    Attributes:
        id: Primary key
        video_id: Foreign key to parent video
        title: Highlight title
        description: Highlight description
        start_time: Start time in seconds
        end_time: End time in seconds
        importance_score: Importance score (0.0 to 1.0)
        highlight_type: Type of highlight
        clip_path: Path to extracted clip file
        thumbnail_path: Path to thumbnail image
        metadata: Additional metadata (JSON)
        created_at: Timestamp when highlight was created
    """
    __tablename__ = "highlights"

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
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)

    # Temporal information
    start_time = Column(Float, nullable=False, index=True)
    end_time = Column(Float, nullable=False, index=True)

    # Importance scoring
    importance_score = Column(Float, nullable=False, default=0.5, index=True)

    # Classification
    highlight_type = Column(
        Enum(HighlightType),
        nullable=False,
        default=HighlightType.UNKNOWN,
        index=True
    )

    # File paths
    clip_path = Column(String(1000), nullable=True)
    thumbnail_path = Column(String(1000), nullable=True)

    # Additional metadata
    # Can store: visual_score, audio_score, text_score, detected_objects,
    # detected_actions, speaker_info, etc.
    extra_metadata = Column("metadata", JSON, nullable=True, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    video = relationship("Video", back_populates="highlights")

    def __repr__(self):
        return f"<Highlight(id={self.id}, video_id={self.video_id}, score={self.importance_score:.2f}, time={self.start_time:.1f}-{self.end_time:.1f}s)>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "title": self.title,
            "description": self.description,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.end_time - self.start_time,
            "importance_score": self.importance_score,
            "highlight_type": self.highlight_type.value,
            "clip_path": self.clip_path,
            "thumbnail_path": self.thumbnail_path,
            "metadata": self.extra_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
