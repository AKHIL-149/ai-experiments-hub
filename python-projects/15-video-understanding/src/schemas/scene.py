"""
Pydantic schemas for Scene model validation and serialization
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict

from src.models.scene import SceneType, TransitionType


# Base schema with common fields
class SceneBase(BaseModel):
    """Base schema for Scene"""
    scene_number: int = Field(..., ge=0, description="Sequential scene number")
    start_time: float = Field(..., ge=0, description="Start time in seconds")
    end_time: float = Field(..., gt=0, description="End time in seconds")


# Schema for creating a scene
class SceneCreate(SceneBase):
    """Schema for creating a new scene"""
    video_id: int = Field(..., description="Parent video ID")
    duration: Optional[float] = Field(None, gt=0, description="Duration in seconds")
    frame_count: Optional[int] = Field(None, ge=0, description="Number of frames")
    keyframe_path: Optional[str] = Field(None, max_length=1000, description="Path to keyframe image")
    scene_type: Optional[SceneType] = Field(None, description="Scene classification")
    transition_type: Optional[TransitionType] = Field(None, description="Transition type")
    description: Optional[str] = Field(None, description="Scene description")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


# Schema for updating a scene
class SceneUpdate(BaseModel):
    """Schema for updating an existing scene"""
    scene_type: Optional[SceneType] = None
    transition_type: Optional[TransitionType] = None
    keyframe_path: Optional[str] = None
    description: Optional[str] = None
    visual_embedding: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None


# Schema for scene response
class SceneResponse(SceneBase):
    """Schema for scene response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_id: int
    duration: float
    frame_count: int
    keyframe_path: Optional[str]
    scene_type: Optional[str]  # Enum converted to string
    transition_type: Optional[str]  # Enum converted to string
    description: Optional[str]
    metadata: Dict[str, Any]
    created_at: datetime


# Schema for scene list response (minimal fields)
class SceneListResponse(BaseModel):
    """Schema for scene list response with minimal fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    scene_number: int
    start_time: float
    end_time: float
    duration: float
    scene_type: Optional[str]
    keyframe_path: Optional[str]


# Schema for scene with frames and transcripts
class SceneDetailResponse(SceneResponse):
    """Schema for detailed scene response with related data"""
    frame_count: int
    transcript_count: int = Field(default=0, description="Number of transcript segments")
    timestamp_range: str = Field(..., description="Formatted timestamp range")


# Schema for scene analysis request
class SceneAnalysisRequest(BaseModel):
    """Schema for requesting scene analysis"""
    video_id: int
    scene_id: int
    analyze_visual: bool = Field(default=True, description="Perform visual analysis")
    analyze_audio: bool = Field(default=True, description="Perform audio analysis")
    generate_description: bool = Field(default=True, description="Generate natural language description")


# Schema for scene search
class SceneSearchRequest(BaseModel):
    """Schema for searching scenes"""
    query: str = Field(..., min_length=1, description="Search query")
    video_id: Optional[int] = Field(None, description="Filter by video ID")
    scene_type: Optional[SceneType] = Field(None, description="Filter by scene type")
    min_duration: Optional[float] = Field(None, ge=0, description="Minimum scene duration")
    max_duration: Optional[float] = Field(None, gt=0, description="Maximum scene duration")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")


# Schema for scene statistics
class SceneStatistics(BaseModel):
    """Schema for scene statistics"""
    video_id: int
    total_scenes: int
    avg_scene_duration: float
    min_scene_duration: float
    max_scene_duration: float
    scene_type_distribution: Dict[str, int] = Field(default_factory=dict)
    transition_type_distribution: Dict[str, int] = Field(default_factory=dict)
