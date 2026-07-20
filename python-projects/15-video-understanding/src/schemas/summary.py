"""
Pydantic schemas for Summary model validation and serialization
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict

from src.models.summary import SummaryType


# Base schema with common fields
class SummaryBase(BaseModel):
    """Base schema for Summary"""
    content: str = Field(..., min_length=1, description="Summary text content")


# Schema for creating a summary
class SummaryCreate(SummaryBase):
    """Schema for creating a new summary"""
    video_id: int = Field(..., description="Parent video ID")
    summary_type: SummaryType = Field(default=SummaryType.OVERALL, description="Type of summary")
    title: Optional[str] = Field(None, max_length=500, description="Summary title")
    timestamp_ranges: Optional[List[Dict[str, Any]]] = Field(
        default_factory=list,
        description="Referenced timestamp ranges"
    )
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


# Schema for updating a summary
class SummaryUpdate(BaseModel):
    """Schema for updating an existing summary"""
    summary_type: Optional[SummaryType] = None
    title: Optional[str] = None
    content: Optional[str] = None
    timestamp_ranges: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


# Schema for summary response
class SummaryResponse(SummaryBase):
    """Schema for summary response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_id: int
    summary_type: str  # Enum converted to string
    title: Optional[str]
    timestamp_ranges: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


# Schema for summary list response (minimal fields)
class SummaryListResponse(BaseModel):
    """Schema for summary list response with minimal fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_id: int
    summary_type: str
    title: Optional[str]
    content_preview: str = Field(..., description="First 200 characters of content")
    created_at: datetime


# Schema for summary generation request
class SummaryGenerationRequest(BaseModel):
    """Schema for requesting summary generation"""
    video_id: int
    summary_type: SummaryType = Field(default=SummaryType.OVERALL, description="Type of summary to generate")
    max_length: Optional[int] = Field(None, ge=50, le=5000, description="Maximum summary length in words")
    include_timestamps: bool = Field(default=True, description="Include timestamp references")
    focus_areas: Optional[List[str]] = Field(None, description="Specific areas to focus on")


# Schema for summary with video info
class SummaryWithVideo(SummaryResponse):
    """Schema for summary with video information"""
    video_title: str
    video_duration: Optional[float]
    word_count: int = Field(..., description="Number of words in summary")


# Schema for chapter-based summary
class ChapterSummary(BaseModel):
    """Schema for chapter-based summary"""
    chapter_number: int
    title: str
    start_time: float
    end_time: float
    duration: float
    content: str
    key_points: List[str] = Field(default_factory=list, description="Key points from chapter")


# Schema for structured summary with chapters
class StructuredSummary(BaseModel):
    """Schema for structured summary with chapters"""
    video_id: int
    overall_summary: str
    chapters: List[ChapterSummary]
    key_takeaways: List[str] = Field(default_factory=list, description="Main takeaways")
    total_duration: float
    created_at: datetime
