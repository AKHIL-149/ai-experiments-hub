"""
FastAPI endpoints for video understanding platform
"""

from src.api.videos import router as videos_router
from src.api.processing import router as processing_router
from src.api.analysis import router as analysis_router
from src.api.search import router as search_router
from src.api.clips import router as clips_router
from src.api.websockets import router as websockets_router

__all__ = [
    'videos_router',
    'processing_router',
    'analysis_router',
    'search_router',
    'clips_router',
    'websockets_router',
]
