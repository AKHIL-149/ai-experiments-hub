"""
Pydantic schemas for Highlight model validation and serialization
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict

from src.models.highlight import HighlightType


# Base schema with common fields
class HighlightBase(BaseModel):
    """Base schema for Highlight"""
    title: str = Field(..., min_length=1, max_length=500, description="Highlight title")
    start_time: float = Field(..., ge=0, description="Start time in seconds")
    end_time: float = Field(..., gt=0, description="End time in seconds")


# Schema for creating a highlight
class HighlightCreate(HighlightBase):
    """Schema for creating a new highlight"""
    video_id: int = Field(..., description="Parent video ID")
    description: Optional[str] = Field(None, description="Highlight description")
    importance_score: float = Field(default=0.5, ge=0, le=1, description="Importance score (0-1)")
    highlight_type: HighlightType = Field(default=HighlightType.UNKNOWN, description="Type of highlight")
    clip_path: Optional[str] = Field(None, max_length=1000, description="Path to clip file")
    thumbnail_path: Optional[str] = Field(None, max_length=1000, description="Path to thumbnail")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


# Schema for updating a highlight
class HighlightUpdate(BaseModel):
    """Schema for updating an existing highlight"""
    title: Optional[str] = None
    description: Optional[str] = None
    importance_score: Optional[float] = Field(None, ge=0, le=1)
    highlight_type: Optional[HighlightType] = None
    clip_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# Schema for highlight response
class HighlightResponse(HighlightBase):
    """Schema for highlight response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_id: int
    description: Optional[str]
    importance_score: float
    highlight_type: str  # Enum converted to string
    clip_path: Optional[str]
    thumbnail_path: Optional[str]
    duration: float = Field(..., description="Duration in seconds")
    metadata: Dict[str, Any]
    created_at: datetime


# Schema for highlight list response (minimal fields)
class HighlightListResponse(BaseModel):
    """Schema for highlight list response with minimal fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    start_time: float
    end_time: float
    duration: float
    importance_score: float
    highlight_type: str
    thumbnail_path: Optional[str]


# Schema for highlight generation request
class HighlightGenerationRequest(BaseModel):
    """Schema for requesting highlight generation"""
    video_id: int
    max_highlights: int = Field(default=5, ge=1, le=20, description="Maximum number of highlights")
    min_importance: float = Field(default=0.5, ge=0, le=1, description="Minimum importance threshold")
    min_duration: float = Field(default=5.0, ge=1, description="Minimum highlight duration in seconds")
    max_duration: float = Field(default=60.0, gt=0, description="Maximum highlight duration in seconds")
    highlight_types: Optional[List[HighlightType]] = Field(None, description="Filter by highlight types")
    create_clips: bool = Field(default=True, description="Create video clips for highlights")


# Schema for highlight with video info
class HighlightWithVideo(HighlightResponse):
    """Schema for highlight with video information"""
    video_title: str
    video_duration: Optional[float]
    timestamp_formatted: str = Field(..., description="Formatted timestamp (MM:SS)")


# Schema for highlight reel
class HighlightReel(BaseModel):
    """Schema for a highlight reel compilation"""
    video_id: int
    highlights: List[HighlightResponse]
    total_duration: float = Field(..., description="Total duration of all highlights")
    reel_path: Optional[str] = Field(None, description="Path to compiled reel video")
    created_at: datetime


# Schema for highlight importance breakdown
class HighlightImportanceBreakdown(BaseModel):
    """Schema for highlight importance scoring breakdown"""
    highlight_id: int
    importance_score: float
    visual_score: Optional[float] = Field(None, description="Visual activity score")
    audio_score: Optional[float] = Field(None, description="Audio energy score")
    text_score: Optional[float] = Field(None, description="Text/dialogue importance score")
    object_score: Optional[float] = Field(None, description="Object detection score")
    face_score: Optional[float] = Field(None, description="Face detection score")
    factors: Dict[str, Any] = Field(default_factory=dict, description="Detailed scoring factors")


# Schema for highlight search
class HighlightSearchRequest(BaseModel):
    """Schema for searching highlights"""
    query: Optional[str] = Field(None, description="Search query")
    video_id: Optional[int] = Field(None, description="Filter by video ID")
    highlight_type: Optional[HighlightType] = Field(None, description="Filter by type")
    min_importance: Optional[float] = Field(None, ge=0, le=1, description="Minimum importance")
    min_duration: Optional[float] = Field(None, ge=0, description="Minimum duration")
    max_duration: Optional[float] = Field(None, gt=0, description="Maximum duration")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results")
