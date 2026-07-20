"""
Pydantic schemas for Video model validation and serialization
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

from src.models.video import SourceType, VideoStatus


# Base schema with common fields
class VideoBase(BaseModel):
    """Base schema for Video"""
    title: str = Field(..., min_length=1, max_length=500, description="Video title")
    description: Optional[str] = Field(None, description="Video description")


# Schema for creating a video
class VideoCreate(VideoBase):
    """Schema for creating a new video"""
    source_type: SourceType = Field(..., description="Video source type")
    source_url: Optional[str] = Field(None, max_length=1000, description="Source URL for YouTube/streaming")
    file_path: Optional[str] = Field(None, max_length=1000, description="Local file path")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


# Schema for updating a video
class VideoUpdate(BaseModel):
    """Schema for updating an existing video"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    processing_status: Optional[VideoStatus] = None
    error_message: Optional[str] = None
    duration_seconds: Optional[float] = Field(None, gt=0)
    file_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# Schema for video response
class VideoResponse(VideoBase):
    """Schema for video response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_type: str  # Enum converted to string
    source_url: Optional[str]
    file_path: Optional[str]
    thumbnail_path: Optional[str]
    duration_seconds: Optional[float]
    processing_status: str  # Enum converted to string
    error_message: Optional[str]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    processed_at: Optional[datetime]


# Schema for video list response (minimal fields)
class VideoListResponse(BaseModel):
    """Schema for video list response with minimal fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    source_type: str
    duration_seconds: Optional[float]
    processing_status: str
    thumbnail_path: Optional[str]
    created_at: datetime


# Schema for video processing status
class VideoStatusResponse(BaseModel):
    """Schema for video processing status response"""
    video_id: int
    status: str
    progress: Optional[float] = Field(None, ge=0, le=100, description="Processing progress percentage")
    stage: Optional[str] = Field(None, description="Current processing stage")
    error_message: Optional[str] = None


# Schema for YouTube video upload
class YouTubeVideoCreate(BaseModel):
    """Schema for YouTube video creation"""
    url: str = Field(..., description="YouTube video URL")
    title: Optional[str] = Field(None, description="Override title (uses YouTube metadata if not provided)")
    description: Optional[str] = Field(None, description="Override description")


# Schema for streaming URL video upload
class StreamingVideoCreate(BaseModel):
    """Schema for streaming video creation"""
    url: str = Field(..., description="Streaming video URL")
    title: str = Field(..., description="Video title")
    description: Optional[str] = Field(None, description="Video description")


# Schema for video statistics
class VideoStatistics(BaseModel):
    """Schema for video statistics"""
    video_id: int
    total_scenes: int = 0
    total_frames: int = 0
    total_transcripts: int = 0
    total_highlights: int = 0
    processing_duration_seconds: Optional[float] = None
