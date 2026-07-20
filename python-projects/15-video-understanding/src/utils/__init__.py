"""
Utility functions and helpers for video processing
"""

from src.utils.video_validator import VideoValidator, validate_video_file
from src.utils.thumbnail_generator import ThumbnailGenerator, generate_thumbnail
from src.utils.metadata_extractor import (
    VideoMetadataExtractor,
    extract_video_metadata,
)
from src.utils.frame_hasher import (
    FrameHasher,
    FrameHash,
    HashAlgorithm,
    compute_frame_hash,
    deduplicate_frame_list,
)

__all__ = [
    'VideoValidator',
    'validate_video_file',
    'ThumbnailGenerator',
    'generate_thumbnail',
    'VideoMetadataExtractor',
    'extract_video_metadata',
    'FrameHasher',
    'FrameHash',
    'HashAlgorithm',
    'compute_frame_hash',
    'deduplicate_frame_list',
]
