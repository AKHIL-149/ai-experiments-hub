"""
Clip model for storing extracted video clips
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


class ClipStatus(enum.Enum):
    """Clip processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Clip(Base):
    """
    Clip model for storing extracted video clips

    Attributes:
        id: Primary key
        external_id: Public identifier used in API URLs
        video_id: Foreign key to parent video
        title: Clip title
        description: Clip description
        start_time: Start time in seconds
        end_time: End time in seconds
        file_path: Path to extracted clip file
        file_size: File size in bytes
        format: Output format (mp4, webm, gif)
        resolution: Output resolution
        status: Processing status
        error_message: Error message if processing failed
        thumbnail_path: Path to thumbnail image
        metadata: Additional metadata (JSON)
        created_at: Timestamp when clip was requested
        completed_at: Timestamp when clip finished processing
    """
    __tablename__ = "clips"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Public identifier used in API URLs
    external_id = Column(String(64), unique=True, nullable=False, index=True)

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

    # File information
    file_path = Column(String(1000), nullable=True)
    file_size = Column(Integer, nullable=True)
    format = Column(String(20), nullable=False, default="mp4")
    resolution = Column(String(20), nullable=False, default="original")
    thumbnail_path = Column(String(1000), nullable=True)

    # Processing status
    status = Column(Enum(ClipStatus), nullable=False, default=ClipStatus.PENDING, index=True)
    error_message = Column(Text, nullable=True)

    # Additional metadata
    extra_metadata = Column("metadata", JSON, nullable=True, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    video = relationship("Video", back_populates="clips")

    def __repr__(self):
        return f"<Clip(id={self.id}, video_id={self.video_id}, time={self.start_time:.1f}-{self.end_time:.1f}s, status={self.status.value})>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "clip_id": self.external_id,
            "video_id": self.video_id,
            "title": self.title,
            "description": self.description,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.end_time - self.start_time,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "format": self.format,
            "resolution": self.resolution,
            "status": self.status.value,
            "error_message": self.error_message,
            "thumbnail_path": self.thumbnail_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
