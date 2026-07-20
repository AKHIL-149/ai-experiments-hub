"""
Pydantic schemas for VideoEmbedding model validation and serialization
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict

from src.models.embedding import EmbeddingType


# Base schema with common fields
class EmbeddingBase(BaseModel):
    """Base schema for VideoEmbedding"""
    embedding_type: EmbeddingType = Field(..., description="Type of embedding")
    embedding_vector: List[float] = Field(..., description="Embedding vector")
    dimension: int = Field(..., gt=0, description="Vector dimension")


# Schema for creating an embedding
class EmbeddingCreate(EmbeddingBase):
    """Schema for creating a new embedding"""
    video_id: int = Field(..., description="Parent video ID")
    frame_id: Optional[int] = Field(None, description="Associated frame ID")
    scene_id: Optional[int] = Field(None, description="Associated scene ID")
    timestamp: Optional[float] = Field(None, ge=0, description="Associated timestamp")
    model_name: Optional[str] = Field(None, max_length=100, description="Model name")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


# Schema for updating an embedding
class EmbeddingUpdate(BaseModel):
    """Schema for updating an existing embedding"""
    embedding_vector: Optional[List[float]] = None
    timestamp: Optional[float] = None
    metadata: Optional[Dict[str, Any]] = None


# Schema for embedding response
class EmbeddingResponse(EmbeddingBase):
    """Schema for embedding response"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_id: int
    frame_id: Optional[int]
    scene_id: Optional[int]
    timestamp: Optional[float]
    embedding_type: str  # Enum converted to string
    model_name: Optional[str]
    metadata: Dict[str, Any]
    created_at: datetime


# Schema for embedding list response (minimal fields, no vector)
class EmbeddingListResponse(BaseModel):
    """Schema for embedding list response without vector data"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    video_id: int
    frame_id: Optional[int]
    scene_id: Optional[int]
    timestamp: Optional[float]
    embedding_type: str
    dimension: int
    model_name: Optional[str]
    created_at: datetime


# Schema for embedding generation request
class EmbeddingGenerationRequest(BaseModel):
    """Schema for requesting embedding generation"""
    video_id: int
    embedding_types: List[EmbeddingType] = Field(..., description="Types of embeddings to generate")
    frame_ids: Optional[List[int]] = Field(None, description="Specific frame IDs (if applicable)")
    scene_ids: Optional[List[int]] = Field(None, description="Specific scene IDs (if applicable)")
    batch_size: int = Field(default=32, ge=1, le=128, description="Batch size for processing")


# Schema for similarity search request
class SimilaritySearchRequest(BaseModel):
    """Schema for vector similarity search"""
    query_vector: Optional[List[float]] = Field(None, description="Query vector")
    query_text: Optional[str] = Field(None, description="Query text (will be embedded)")
    query_image_path: Optional[str] = Field(None, description="Query image path (will be embedded)")
    embedding_type: EmbeddingType = Field(..., description="Type of embedding to search")
    video_id: Optional[int] = Field(None, description="Filter by video ID")
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results")
    min_similarity: Optional[float] = Field(None, ge=0, le=1, description="Minimum similarity threshold")


# Schema for similarity search result
class SimilaritySearchResult(BaseModel):
    """Schema for similarity search result"""
    embedding_id: int
    video_id: int
    frame_id: Optional[int]
    scene_id: Optional[int]
    timestamp: Optional[float]
    similarity_score: float = Field(..., ge=0, le=1, description="Similarity score (0-1)")
    embedding_type: str
    metadata: Dict[str, Any]


# Schema for batch similarity search
class BatchSimilaritySearchRequest(BaseModel):
    """Schema for batch similarity search"""
    queries: List[SimilaritySearchRequest] = Field(..., description="Multiple search queries")
    aggregate_results: bool = Field(default=False, description="Aggregate and rank all results")


# Schema for embedding statistics
class EmbeddingStatistics(BaseModel):
    """Schema for embedding statistics"""
    video_id: int
    total_embeddings: int
    embeddings_by_type: Dict[str, int] = Field(..., description="Count by embedding type")
    total_dimension_size: int = Field(..., description="Total dimension size across all embeddings")
    models_used: List[str] = Field(..., description="List of models used")
    coverage: Dict[str, float] = Field(..., description="Coverage percentages")


# Schema for multi-modal embedding
class MultiModalEmbedding(BaseModel):
    """Schema for combined multi-modal embedding"""
    video_id: int
    timestamp: float
    visual_embedding: Optional[List[float]] = Field(None, description="Visual (CLIP) embedding")
    text_embedding: Optional[List[float]] = Field(None, description="Text embedding")
    audio_embedding: Optional[List[float]] = Field(None, description="Audio embedding")
    combined_embedding: List[float] = Field(..., description="Fused multi-modal embedding")
    fusion_method: str = Field(..., description="Method used for fusion (e.g., concat, weighted_avg)")
    weights: Optional[Dict[str, float]] = Field(None, description="Fusion weights by modality")


# Schema for embedding export
class EmbeddingExportRequest(BaseModel):
    """Schema for exporting embeddings"""
    video_id: int
    embedding_types: Optional[List[EmbeddingType]] = Field(None, description="Types to export (all if None)")
    format: str = Field(default="numpy", description="Export format: numpy, json, csv")
    include_metadata: bool = Field(default=True, description="Include metadata in export")
