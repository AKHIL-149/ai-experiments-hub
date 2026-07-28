"""
FastAPI endpoints for video understanding platform
"""

from src.api.videos import router as videos_router
from src.api.processing import router as processing_router

__all__ = [
    'videos_router',
    'processing_router',
]
