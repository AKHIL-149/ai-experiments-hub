"""
Video model for storing video metadata and processing status
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Enum, Text, JSON
)
from sqlalchemy.orm import relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.scene import Scene
    from src.models.frame import Frame
    from src.models.transcript import Transcript
    from src.models.summary import Summary
    from src.models.highlight import Highlight
    from src.models.embedding import VideoEmbedding


class SourceType(enum.Enum):
    """Video source types"""
    LOCAL = "local"
    YOUTUBE = "youtube"
    STREAM = "stream"


class VideoStatus(enum.Enum):
    """Video processing status"""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Video(Base):
    """
    Video model for storing video metadata and processing information

    Attributes:
        id: Primary key
        title: Video title
        description: Video description
        source_type: Type of video source (local, youtube, stream)
        source_url: Original URL (for youtube/stream sources)
        file_path: Local file path
        thumbnail_path: Path to thumbnail image
        duration_seconds: Video duration in seconds
        processing_status: Current processing status
        error_message: Error message if processing failed
        metadata: Additional metadata as JSON
        created_at: Timestamp when video was added
        updated_at: Timestamp of last update
        processed_at: Timestamp when processing completed
    """
    __tablename__ = "videos"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Public identifier used in API URLs and on-disk file names (UUID)
    external_id = Column(String(64), unique=True, nullable=True, index=True)

    # Basic information
    title = Column(String(500), nullable=False, index=True)
    description = Column(Text, nullable=True)

    # Source information
    source_type = Column(Enum(SourceType), nullable=False, index=True)
    source_url = Column(String(1000), nullable=True)  # For YouTube/streaming
    file_path = Column(String(1000), nullable=True)  # Local file path
    thumbnail_path = Column(String(1000), nullable=True)

    # Video properties
    duration_seconds = Column(Float, nullable=True)

    # Processing status
    processing_status = Column(
        Enum(VideoStatus),
        nullable=False,
        default=VideoStatus.PENDING,
        index=True
    )
    error_message = Column(Text, nullable=True)

    # Additional metadata (JSON)
    # Can store: codec, bitrate, resolution, fps, etc.
    extra_metadata = Column("metadata", JSON, nullable=True, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    processed_at = Column(DateTime, nullable=True)

    # Relationships
    scenes = relationship("Scene", back_populates="video", cascade="all, delete-orphan")
    frames = relationship("Frame", back_populates="video", cascade="all, delete-orphan")
    transcripts = relationship("Transcript", back_populates="video", cascade="all, delete-orphan")
    summaries = relationship("Summary", back_populates="video", cascade="all, delete-orphan")
    highlights = relationship("Highlight", back_populates="video", cascade="all, delete-orphan")
    embeddings = relationship("VideoEmbedding", back_populates="video", cascade="all, delete-orphan")
    chapters = relationship("Chapter", back_populates="video", cascade="all, delete-orphan")
    clips = relationship("Clip", back_populates="video", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Video(id={self.id}, title='{self.title}', status={self.processing_status.value})>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.external_id or str(self.id),
            "title": self.title,
            "description": self.description,
            "source_type": self.source_type.value,
            "source_url": self.source_url,
            "file_path": self.file_path,
            "thumbnail_path": self.thumbnail_path,
            "duration_seconds": self.duration_seconds,
            "processing_status": self.processing_status.value,
            "error_message": self.error_message,
            "metadata": self.extra_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }
