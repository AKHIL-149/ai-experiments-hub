"""
CLIP (Contrastive Language-Image Pre-training) integration
For semantic text-to-image search and multi-modal embeddings
"""

from src.services.clip.clip_model import CLIPModel, CLIPConfig
from src.services.clip.frame_embedder import (
    CLIPFrameEmbedder,
    FrameEmbedding,
    VideoEmbeddings,
    embed_video_frames,
)
from src.services.clip.text_embedder import (
    CLIPTextEmbedder,
    TextEmbedding,
    QueryResult,
    search_video_frames,
)

__all__ = [
    'CLIPModel',
    'CLIPConfig',
    'CLIPFrameEmbedder',
    'FrameEmbedding',
    'VideoEmbeddings',
    'embed_video_frames',
    'CLIPTextEmbedder',
    'TextEmbedding',
    'QueryResult',
    'search_video_frames',
]
