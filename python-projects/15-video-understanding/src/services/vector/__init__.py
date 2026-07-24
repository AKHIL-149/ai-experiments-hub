"""
Vector storage services for video embeddings
"""

from src.services.vector.frame_store import (
    FrameVectorStore,
    FrameSearchResult,
    add_frames_to_vector_store,
)

__all__ = [
    'FrameVectorStore',
    'FrameSearchResult',
    'add_frames_to_vector_store',
]
