"""
VideoEmbedding model for storing embedding vectors for semantic search
"""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Enum, JSON, ForeignKey
)
from sqlalchemy.orm import relationship

from src.core.database import Base

if TYPE_CHECKING:
    from src.models.video import Video
    from src.models.frame import Frame
    from src.models.scene import Scene


class EmbeddingType(enum.Enum):
    """Embedding vector types"""
    CLIP_VISUAL = "clip_visual"  # CLIP visual embedding
    CLIP_TEXT = "clip_text"  # CLIP text embedding
    TEXT_SEMANTIC = "text_semantic"  # Text semantic embedding (e.g., sentence-transformers)
    AUDIO_FEATURE = "audio_feature"  # Audio feature embedding
    MULTIMODAL = "multimodal"  # Combined multi-modal embedding
    CUSTOM = "custom"  # Custom embedding type


class VideoEmbedding(Base):
    """
    VideoEmbedding model for storing embedding vectors for semantic search

    Attributes:
        id: Primary key
        video_id: Foreign key to parent video
        frame_id: Foreign key to frame (nullable)
        scene_id: Foreign key to scene (nullable)
        embedding_type: Type of embedding
        embedding_vector: The embedding vector (JSON array)
        timestamp: Associated timestamp (nullable)
        dimension: Vector dimension
        model_name: Name of the model used
        metadata: Additional metadata (JSON)
        created_at: Timestamp when embedding was created
    """
    __tablename__ = "video_embeddings"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Foreign keys
    video_id = Column(
        Integer,
        ForeignKey("videos.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    frame_id = Column(
        Integer,
        ForeignKey("frames.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    scene_id = Column(
        Integer,
        ForeignKey("scenes.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    # Embedding classification
    embedding_type = Column(
        Enum(EmbeddingType),
        nullable=False,
        index=True
    )

    # Embedding data
    embedding_vector = Column(JSON, nullable=False)  # Array of floats
    timestamp = Column(Float, nullable=True, index=True)  # Associated timestamp if applicable
    dimension = Column(Integer, nullable=False)  # Vector dimension (e.g., 512, 768)

    # Model information
    model_name = Column(String(100), nullable=True)  # e.g., "ViT-B/32", "all-MiniLM-L6-v2"

    # Additional metadata
    # Can store: normalization_method, extraction_params, confidence, etc.
    extra_metadata = Column("metadata", JSON, nullable=True, default=dict)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    video = relationship("Video", back_populates="embeddings")

    def __repr__(self):
        ref = f"frame={self.frame_id}" if self.frame_id else f"scene={self.scene_id}" if self.scene_id else "video"
        return f"<VideoEmbedding(id={self.id}, video_id={self.video_id}, {ref}, type={self.embedding_type.value}, dim={self.dimension})>"

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "frame_id": self.frame_id,
            "scene_id": self.scene_id,
            "embedding_type": self.embedding_type.value,
            "embedding_vector": self.embedding_vector,
            "timestamp": self.timestamp,
            "dimension": self.dimension,
            "model_name": self.model_name,
            "metadata": self.extra_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
