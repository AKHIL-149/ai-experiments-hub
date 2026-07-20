"""
Pydantic schemas for Frame model validation and serialization
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict


# Base schema with common fields
class FrameBase(BaseModel):
    """Base schema for Frame"""
    timestamp: float = Field(..., ge=0, description="Frame timestamp in seconds")
    frame_number: int = Field(..., ge=0, description="Sequential frame number")


# Schema for creating a frame
class FrameCreate(FrameBase):
    """Schema for creating a new frame"""
    video_id: int = Field(..., description="Parent video ID")
    scene_id: Optional[int] = Field(None, description="Parent scene ID")
    file_path: Optional[str] = Field(None, max_length=1000, description="Path to frame image")
    is_keyframe: bool = Field(default=False, description="Whether this is a keyframe")
    frame_hash: Optional[str] = Field(None, max_length=64, description="Perceptual hash")
    visual_features: Optional[Dict[str, Any]] = Field(None, description="Visual feature vectors")
    ocr_text: Optional[str] = Field(None, description="Extracted text from frame")
    clip_embedding: Optional[List[float]] = Field(None, description="CLIP embedding vector")
    description: Optional[str] = Field(None, description="AI-generated description")
    objects_detected: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Detected objects")
    faces_detected: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="Detected faces")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


# Schema for updating a frame
class FrameUpdate(BaseModel):
    """Schema for updating an existing frame"""
    scene_id: Optional[int] = None
    is_keyframe: Optional[bool] = None
    frame_hash: Optional[str] = None
    visual_features: Optional[Dict[str, Any]] = None
    ocr_text: Optional[str] = None
    clip_embedding: Optional[List[float]] = None
    description: Optional[str] = None
    objects_detected: Optional[List[Dict[str, Any]]] = None
    faces_detected: Optional[List[Dict[str, Any]]] = None
    metadata: Optional[Dict[str, Any]] = None


# Schema for frame response
class FrameResponse(FrameBase):
    """Schema for frame response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_id: int
    scene_id: Optional[int]
    file_path: Optional[str]
    is_keyframe: bool
    frame_hash: Optional[str]
    ocr_text: Optional[str]
    description: Optional[str]
    objects_detected: List[Dict[str, Any]]
    faces_detected: List[Dict[str, Any]]
    metadata: Dict[str, Any]
    created_at: datetime


# Schema for frame list response (minimal fields)
class FrameListResponse(BaseModel):
    """Schema for frame list response with minimal fields"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    timestamp: float
    frame_number: int
    is_keyframe: bool
    file_path: Optional[str]
    has_ocr: bool = Field(default=False, description="Whether frame has OCR text")
    has_description: bool = Field(default=False, description="Whether frame has description")


# Schema for frame search request
class FrameSearchRequest(BaseModel):
    """Schema for searching frames"""
    query: str = Field(..., min_length=1, description="Search query (text or image)")
    video_id: Optional[int] = Field(None, description="Filter by video ID")
    scene_id: Optional[int] = Field(None, description="Filter by scene ID")
    keyframes_only: bool = Field(default=False, description="Search only keyframes")
    min_timestamp: Optional[float] = Field(None, ge=0, description="Minimum timestamp")
    max_timestamp: Optional[float] = Field(None, gt=0, description="Maximum timestamp")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")


# Schema for frame with embedding
class FrameWithEmbedding(FrameResponse):
    """Schema for frame response with embedding"""
    clip_embedding: Optional[List[float]]
    visual_features: Optional[Dict[str, Any]]


# Schema for frame analysis request
class FrameAnalysisRequest(BaseModel):
    """Schema for requesting frame analysis"""
    video_id: int
    frame_id: int
    analyze_objects: bool = Field(default=True, description="Detect objects")
    analyze_faces: bool = Field(default=True, description="Detect faces")
    extract_text: bool = Field(default=True, description="Extract text via OCR")
    generate_embedding: bool = Field(default=True, description="Generate CLIP embedding")
    generate_description: bool = Field(default=True, description="Generate AI description")


# Schema for OCR result
class OCRResult(BaseModel):
    """Schema for OCR extraction result"""
    frame_id: int
    text: str
    confidence: Optional[float] = Field(None, ge=0, le=1, description="OCR confidence")
    bounding_boxes: Optional[List[Dict[str, Any]]] = Field(None, description="Text bounding boxes")


# Schema for object detection result
class ObjectDetectionResult(BaseModel):
    """Schema for object detection result"""
    frame_id: int
    objects: List[Dict[str, Any]] = Field(..., description="Detected objects with bounding boxes")
    total_objects: int = Field(..., description="Total number of objects detected")
