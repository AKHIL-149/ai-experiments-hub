"""
Transcript model for storing audio transcription segments
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
    from src.models.scene import Scene


class SegmentType(enum.Enum):
    """Transcript segment types"""
    WORD = "word"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    SPEAKER_TURN = "speaker_turn"


class Transcript(Base):
    """
    Transcript model for storing audio transcription segments

    Attributes:
        id: Primary key
        video_id: Foreign key to parent video
        scene_id: Foreign key to parent scene (nullable)
        start_time: Segment start time in seconds
        end_time: Segment end time in seconds
        text: Transcribed text content
        speaker_id: Speaker identifier from diarization
        confidence: Transcription confidence score (0-1)
        language: Detected language code (e.g., 'en', 'es')
        segment_type: Type of segment
        embedding: Text embedding vector (JSON array)
        metadata: Additional metadata (JSON)
        created_at: Timestamp when transcript was created
    """
    __tablename__ = "transcripts"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Foreign keys
    video_id = Column(
        Integer,
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    scene_id = Column(
        Integer,
        ForeignKey("scenes.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    # Temporal information
    start_time = Column(Float, nullable=False, index=True)
    end_time = Column(Float, nullable=False, index=True)

    # Transcript content
    text = Column(Text, nullable=False)

    # Speaker diarization
    speaker_id = Column(String(50), nullable=True, index=True)
    confidence = Column(Float, nullable=True)  # 0.0 to 1.0

    # Language information
    language = Column(String(10), nullable=True, default="en")

    # Segment classification
    segment_type = Column(
        Enum(SegmentType),
        nullable=True,
        default=SegmentType.SENTENCE
    )

    # Embedding for semantic search
    embedding = Column(JSON, nullable=True)  # Text embedding vector

    # Additional metadata
    extra_metadata = Column("metadata", JSON, nullable=True, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    video = relationship("Video", back_populates="transcripts")
    scene = relationship("Scene", back_populates="transcripts")

    def __repr__(self):
        speaker_info = f", speaker={self.speaker_id}" if self.speaker_id else ""
        return f"<Transcript(id={self.id}, video_id={self.video_id}, time={self.start_time:.2f}-{self.end_time:.2f}s{speaker_info})>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "scene_id": self.scene_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "text": self.text,
            "speaker_id": self.speaker_id,
            "confidence": self.confidence,
            "language": self.language,
            "segment_type": self.segment_type.value if self.segment_type else None,
            "embedding": self.embedding,
            "metadata": self.extra_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
