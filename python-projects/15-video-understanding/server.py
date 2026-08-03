"""
FastAPI server for Video Understanding & Summarization Platform
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import os

from src import __version__
from src.core.config import settings
from src.core.database import Base, engine
from src.core.logging import setup_logging
from src.core.middleware import (
    LoggingMiddleware,
    RateLimitMiddleware,
    ErrorHandlingMiddleware,
)

# Import API routers
from src.api import (
    videos_router,
    processing_router,
    analysis_router,
    search_router,
    clips_router,
    websockets_router,
)

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """
    Application lifespan manager - handles startup and shutdown events
    """
    # Startup
    logger.info("🚀 Starting Video Understanding Platform...")
    logger.info(f"Version: {__version__}")
    logger.info(f"Environment: {settings.app_env}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Database URL: {settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url}")

    # Create required directories
    directories = [
        "data/uploads",
        "data/videos",
        "data/frames",
        "data/clips",
        "data/thumbnails",
        "data/vector_stores",
    ]
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        logger.info(f"Ensured directory exists: {directory}")

    # Create database tables (if not using migrations)
    # Note: In production, use Alembic migrations instead
    if settings.debug:
        try:
            logger.info("Creating database tables...")
            Base.metadata.create_all(bind=engine)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.warning(f"Could not create database tables: {e}")
            logger.warning("Server will run without database (API endpoints will return errors)")

    logger.info("✅ Application startup complete")

    yield

    # Shutdown
    logger.info("🛑 Shutting down Video Understanding Platform...")
    logger.info("✅ Application shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Video Understanding & Summarization Platform",
    description=(
        "Multi-modal video analysis platform with scene detection, "
        "transcription, visual understanding, semantic search, and AI-powered video analysis.\n\n"
        "## Features\n"
        "* **Video Upload & Management** - Upload local files, YouTube videos, or streaming URLs\n"
        "* **Scene Detection** - Automatic scene boundary detection\n"
        "* **Audio Transcription** - Speech-to-text with speaker diarization\n"
        "* **Visual Analysis** - Object detection, OCR, and action recognition\n"
        "* **Semantic Search** - Multi-modal search across video content\n"
        "* **Summary Generation** - AI-powered video summaries and chapters\n"
        "* **Highlight Detection** - Automatic highlight moment extraction\n"
        "* **Clip Creation** - Generate clips and highlight reels\n"
        "* **Real-time Updates** - WebSocket support for processing progress"
    ),
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# ============================================================================
# Middleware Configuration
# ============================================================================

# CORS middleware - Allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "*",  # Allow all origins in development
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GZip compression
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Custom middleware (in order of execution)
app.add_middleware(ErrorHandlingMiddleware)
if settings.rate_limit_enabled:
    app.add_middleware(RateLimitMiddleware)
app.add_middleware(LoggingMiddleware)


# ============================================================================
# Health Check Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": "Video Understanding & Summarization Platform",
        "version": __version__,
        "status": "operational",
        "docs": "/docs",
        "redoc": "/redoc",
        "endpoints": {
            "videos": "/api/videos",
            "search": "/api/search",
            "clips": "/api/clips",
            "websocket": "/api/ws",
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": __version__,
        "environment": settings.app_env,
        "database": "connected",
    }


@app.get("/version")
async def version():
    """Version information"""
    return {
        "version": __version__,
        "api_version": "v1",
        "environment": settings.app_env,
    }


@app.get("/api/info")
async def api_info():
    """Detailed API information"""
    return {
        "version": __version__,
        "capabilities": {
            "video_sources": ["local_upload", "youtube", "streaming_url"],
            "processing": {
                "frame_extraction": True,
                "scene_detection": True,
                "audio_transcription": True,
                "visual_analysis": True,
                "embeddings": True,
                "summarization": True,
                "highlights": True,
            },
            "search": {
                "semantic_search": True,
                "frame_search": True,
                "transcript_search": True,
                "video_qa": True,
            },
            "features": {
                "clip_creation": True,
                "highlight_reels": True,
                "real_time_updates": True,
                "multi_modal_fusion": True,
            }
        }
    }


# ============================================================================
# API Routes
# ============================================================================

# Include all API routers
app.include_router(videos_router)
app.include_router(processing_router)
app.include_router(analysis_router)
app.include_router(search_router)
app.include_router(clips_router)
app.include_router(websockets_router)

# ============================================================================
# Static Files
# ============================================================================

# Serve uploaded files and generated content
if os.path.exists("data/uploads"):
    app.mount("/uploads", StaticFiles(directory="data/uploads"), name="uploads")

if os.path.exists("data/clips"):
    app.mount("/clips", StaticFiles(directory="data/clips"), name="clips")

if os.path.exists("data/thumbnails"):
    app.mount("/thumbnails", StaticFiles(directory="data/thumbnails"), name="thumbnails")


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 errors"""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": f"The requested resource '{request.url.path}' was not found",
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    """Handle 500 errors"""
    logger.error(f"Internal server error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred. Please try again later.",
        }
    )


# ============================================================================
# Application Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    logger.info("🚀 Starting server with uvicorn...")
    uvicorn.run(
        "server:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
