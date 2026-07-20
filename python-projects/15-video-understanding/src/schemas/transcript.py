"""
Pydantic schemas for Transcript model validation and serialization
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict

from src.models.transcript import SegmentType


# Base schema with common fields
class TranscriptBase(BaseModel):
    """Base schema for Transcript"""
    start_time: float = Field(..., ge=0, description="Segment start time in seconds")
    end_time: float = Field(..., gt=0, description="Segment end time in seconds")
    text: str = Field(..., min_length=1, description="Transcribed text")


# Schema for creating a transcript
class TranscriptCreate(TranscriptBase):
    """Schema for creating a new transcript segment"""
    video_id: int = Field(..., description="Parent video ID")
    scene_id: Optional[int] = Field(None, description="Parent scene ID")
    speaker_id: Optional[str] = Field(None, max_length=50, description="Speaker identifier")
    confidence: Optional[float] = Field(None, ge=0, le=1, description="Transcription confidence")
    language: Optional[str] = Field(default="en", max_length=10, description="Language code")
    segment_type: Optional[SegmentType] = Field(None, description="Segment type")
    embedding: Optional[List[float]] = Field(None, description="Text embedding vector")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


# Schema for updating a transcript
class TranscriptUpdate(BaseModel):
    """Schema for updating an existing transcript"""
    text: Optional[str] = None
    speaker_id: Optional[str] = None
    confidence: Optional[float] = None
    language: Optional[str] = None
    segment_type: Optional[SegmentType] = None
    embedding: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None


# Schema for transcript response
class TranscriptResponse(TranscriptBase):
    """Schema for transcript response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_id: int
    scene_id: Optional[int]
    speaker_id: Optional[str]
    confidence: Optional[float]
    language: Optional[str]
    segment_type: Optional[str]  # Enum converted to string
    metadata: Dict[str, Any]
    created_at: datetime


# Schema for transcript list response (minimal fields)
class TranscriptListResponse(BaseModel):
    """Schema for transcript list response with minimal fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    start_time: float
    end_time: float
    text: str
    speaker_id: Optional[str]
    confidence: Optional[float]


# Schema for full transcript response with speaker info
class TranscriptWithSpeaker(TranscriptResponse):
    """Schema for transcript with speaker information"""
    speaker_name: Optional[str] = Field(None, description="Speaker display name")
    duration: float = Field(..., description="Duration in seconds")
    word_count: int = Field(..., description="Number of words")


# Schema for transcript search request
class TranscriptSearchRequest(BaseModel):
    """Schema for searching transcripts"""
    query: str = Field(..., min_length=1, description="Search query")
    video_id: Optional[int] = Field(None, description="Filter by video ID")
    scene_id: Optional[int] = Field(None, description="Filter by scene ID")
    speaker_id: Optional[str] = Field(None, description="Filter by speaker")
    language: Optional[str] = Field(None, description="Filter by language")
    min_confidence: Optional[float] = Field(None, ge=0, le=1, description="Minimum confidence")
    min_timestamp: Optional[float] = Field(None, ge=0, description="Minimum timestamp")
    max_timestamp: Optional[float] = Field(None, gt=0, description="Maximum timestamp")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")


# Schema for transcript aggregation
class TranscriptAggregation(BaseModel):
    """Schema for aggregated transcript data"""
    video_id: int
    total_segments: int
    total_duration: float = Field(..., description="Total duration in seconds")
    unique_speakers: int
    languages: List[str]
    avg_confidence: Optional[float] = Field(None, ge=0, le=1)
    word_count: int


# Schema for speaker statistics
class SpeakerStatistics(BaseModel):
    """Schema for speaker statistics"""
    speaker_id: str
    total_segments: int
    total_duration: float
    word_count: int
    avg_confidence: Optional[float]
    first_appearance: float = Field(..., description="First appearance timestamp")
    last_appearance: float = Field(..., description="Last appearance timestamp")


# Schema for transcription request
class TranscriptionRequest(BaseModel):
    """Schema for requesting transcription"""
    video_id: int
    use_api: bool = Field(default=False, description="Use API instead of local model")
    language: Optional[str] = Field(None, description="Force specific language")
    enable_diarization: bool = Field(default=True, description="Enable speaker diarization")
    min_segment_duration: float = Field(default=0.5, ge=0, description="Minimum segment duration")


# Schema for transcription status
class TranscriptionStatus(BaseModel):
    """Schema for transcription status"""
    video_id: int
    status: str = Field(..., description="Status: pending, processing, completed, failed")
    progress: Optional[float] = Field(None, ge=0, le=100, description="Progress percentage")
    segments_processed: int = Field(default=0, description="Number of segments processed")
    total_segments: Optional[int] = Field(None, description="Total segments to process")
    error_message: Optional[str] = None


# Schema for full video transcript
class FullVideoTranscript(BaseModel):
    """Schema for complete video transcript"""
    video_id: int
    title: str
    duration: float
    segments: List[TranscriptWithSpeaker]
    speakers: List[SpeakerStatistics]
    languages: List[str]
    total_words: int
    avg_confidence: Optional[float]
