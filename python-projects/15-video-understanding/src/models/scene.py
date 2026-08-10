"""
Scene model for storing detected scenes and their properties
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
    from src.models.frame import Frame
    from src.models.transcript import Transcript


class SceneType(enum.Enum):
    """Scene classification types"""
    STATIC = "static"  # Little to no motion
    MOTION = "motion"  # Significant motion/action
    DIALOGUE = "dialogue"  # Conversation/talking heads
    TRANSITION = "transition"  # Transitional scene
    ACTION = "action"  # High activity scene
    UNKNOWN = "unknown"  # Type not yet determined


class TransitionType(enum.Enum):
    """Scene transition types"""
    CUT = "cut"  # Hard cut between scenes
    FADE = "fade"  # Fade in/out transition
    DISSOLVE = "dissolve"  # Dissolve/cross-fade
    WIPE = "wipe"  # Wipe transition
    UNKNOWN = "unknown"  # Transition type not determined


class Scene(Base):
    """
    Scene model for storing detected scenes within videos

    A scene is a continuous segment of video with consistent visual content,
    typically bounded by shot changes or transitions.

    Attributes:
        id: Primary key
        video_id: Foreign key to parent video
        scene_number: Sequential scene number within the video
        start_time: Scene start time in seconds
        end_time: Scene end time in seconds
        duration: Scene duration in seconds
        frame_count: Number of frames in this scene
        keyframe_path: Path to representative keyframe image
        scene_type: Classification of scene content
        transition_type: Type of transition into this scene
        visual_embedding: Vector embedding for visual similarity (stored as JSON array)
        description: Natural language description of scene
        metadata: Additional metadata as JSON
        created_at: Timestamp when scene was created
    """
    __tablename__ = "scenes"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # Foreign key to video
    video_id = Column(Integer, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)

    # Scene identification
    scene_number = Column(Integer, nullable=False, index=True)  # Sequential number in video

    # Temporal information
    start_time = Column(Float, nullable=False, index=True)  # Start time in seconds
    end_time = Column(Float, nullable=False, index=True)  # End time in seconds
    duration = Column(Float, nullable=False)  # Duration in seconds

    # Scene properties
    frame_count = Column(Integer, nullable=True, default=0)
    keyframe_path = Column(String(1000), nullable=True)  # Path to representative frame

    # Scene classification
    scene_type = Column(Enum(SceneType), nullable=True, default=SceneType.UNKNOWN)
    transition_type = Column(Enum(TransitionType), nullable=True, default=TransitionType.UNKNOWN)

    # Visual embedding (stored as JSON array of floats)
    # This will be populated by CLIP or other vision models
    visual_embedding = Column(JSON, nullable=True)

    # Scene description
    description = Column(Text, nullable=True)

    # Additional metadata (JSON)
    # Can store: motion_score, color_palette, dominant_objects, etc.
    extra_metadata = Column("metadata", JSON, nullable=True, default=dict)

    # Timestamp
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    video = relationship("Video", back_populates="scenes")
    frames = relationship("Frame", back_populates="scene", cascade="all, delete-orphan")
    transcripts = relationship("Transcript", back_populates="scene", cascade="all, delete-orphan")

    def __repr__(self):
        return (
            f"<Scene(id={self.id}, video_id={self.video_id}, "
            f"scene_number={self.scene_number}, duration={self.duration:.2f}s)>"
        )

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": self.id,
            "video_id": self.video_id,
            "scene_number": self.scene_number,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration": self.duration,
            "frame_count": self.frame_count,
            "keyframe_path": self.keyframe_path,
            "scene_type": self.scene_type.value if self.scene_type else None,
            "transition_type": self.transition_type.value if self.transition_type else None,
            "description": self.description,
            "metadata": self.extra_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @property
    def timestamp_range(self) -> str:
        """Get formatted timestamp range (e.g., '00:01:30 - 00:02:15')"""
        def format_time(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"

        return f"{format_time(self.start_time)} - {format_time(self.end_time)}"
