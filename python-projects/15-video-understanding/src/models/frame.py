"""
Frame model for storing individual video frames and their analysis
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, Text, JSON, ForeignKey
)
from sqlalchemy.orm import relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.video import Video
    from src.models.scene import Scene


class Frame(Base):
    """
    Frame model for storing individual video frames and their analysis

    Attributes:
        id: Primary key
        video_id: Foreign key to parent video
        scene_id: Foreign key to parent scene (nullable)
        timestamp: Frame timestamp in seconds
        frame_number: Sequential frame number
        file_path: Path to saved frame image
        is_keyframe: Whether this is a keyframe
        frame_hash: Perceptual hash for deduplication
        visual_features: Visual feature vectors (JSON)
        ocr_text: Text extracted from frame
        clip_embedding: CLIP embedding vector (JSON array)
        description: AI-generated frame description
        objects_detected: Detected objects (JSON)
        faces_detected: Detected faces (JSON)
        metadata: Additional metadata (JSON)
        created_at: Timestamp when frame was created
    """
    __tablename__ = "frames"

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
    timestamp = Column(Float, nullable=False, index=True)
    frame_number = Column(Integer, nullable=False, index=True)

    # File information
    file_path = Column(String(1000), nullable=True)
    is_keyframe = Column(Boolean, default=False, index=True)
    frame_hash = Column(String(64), nullable=True, index=True)  # Perceptual hash

    # Visual analysis
    visual_features = Column(JSON, nullable=True)  # Generic visual features
    ocr_text = Column(Text, nullable=True)  # Extracted text
    clip_embedding = Column(JSON, nullable=True)  # CLIP embedding vector
    description = Column(Text, nullable=True)  # AI-generated description

    # Detected entities
    objects_detected = Column(JSON, nullable=True, default=list)
    faces_detected = Column(JSON, nullable=True, default=list)

    # Additional metadata
    extra_metadata = Column("metadata", JSON, nullable=True, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    video = relationship("Video", back_populates="frames")
    scene = relationship("Scene", back_populates="frames")

    def __repr__(self):
        return f"<Frame(id={self.id}, video_id={self.video_id}, timestamp={self.timestamp:.2f}s)>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "scene_id": self.scene_id,
            "timestamp": self.timestamp,
            "frame_number": self.frame_number,
            "file_path": self.file_path,
            "is_keyframe": self.is_keyframe,
            "frame_hash": self.frame_hash,
            "visual_features": self.visual_features,
            "ocr_text": self.ocr_text,
            "clip_embedding": self.clip_embedding,
            "description": self.description,
            "objects_detected": self.objects_detected,
            "faces_detected": self.faces_detected,
            "metadata": self.extra_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
