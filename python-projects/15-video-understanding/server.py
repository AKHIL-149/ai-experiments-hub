"""
FastAPI server for Video Understanding & Summarization Platform
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, FileResponse
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
    auth_router,
    jobs_router,
)
from src.core.login_gate import LoginGateMiddleware
from src.services.video_cleanup import (
    ensure_account_schema, purge_dead_sessions, purge_expired_guests,
)

# The page files are found next to this file, not relative to wherever the server was started from
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
FRONTEND_INDEX = os.path.join(FRONTEND_DIR, "index.html")
FRONTEND_LOGIN = os.path.join(FRONTEND_DIR, "login.html")

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)


def _cleanup_once() -> None:
    from src.core.database import SessionLocal
    db = SessionLocal()
    try:
        purge_expired_guests(db)
        purge_dead_sessions(db)
        from src.services.job_queue import purge_old_jobs
        purge_old_jobs(db)
    finally:
        db.close()


async def _cleanup_loop() -> None:
    """Remove expired guests (and what they uploaded) and dead sign-ins, now and then every hour"""
    while True:
        try:
            await asyncio.to_thread(_cleanup_once)
        except Exception as e:
            logger.warning(f"Cleanup failed: {e}")
        await asyncio.sleep(3600)


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

    # Accounts: the tables are created above in debug mode; a database that already existed also needs
    # videos.user_id (the Alembic migration adds it as well)
    try:
        import src.models  # noqa: F401  (registers every table, users included)
        Base.metadata.create_all(bind=engine)
        ensure_account_schema(engine)
    except Exception as e:
        logger.warning(f"Could not prepare the account tables: {e}")

    cleanup_task = asyncio.create_task(_cleanup_loop())

    # The job queue: downloads and analysis run here, a few at a time, and survive restarts
    if settings.job_workers_enabled:
        from src.api.videos import QUEUE_RUNNERS
        from src.services import job_queue
        await job_queue.start(QUEUE_RUNNERS)

    logger.info("✅ Application startup complete")

    yield

    # Shutdown
    cleanup_task.cancel()
    if settings.job_workers_enabled:
        from src.services import job_queue
        await job_queue.stop()
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

# Sign-in gate: added first = innermost, so CORS headers, the rate limiter and logging also cover the
# 401s it answers
app.add_middleware(LoginGateMiddleware)

# CORS middleware - Allow frontend access
app.add_middleware(
    CORSMiddleware,
    # Only the origins in CORS_ORIGINS (plus the dev frontend on loopback).
    # "*" with credentials made the server answer any website that asked, so a
    # page open in the same browser could read and delete videos here.
    allow_origins=sorted({
        *settings.cors_origins,
        "http://localhost:3001",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:8000",
    }),
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
async def root(request: Request):
    """Root endpoint - Serve frontend or API info"""
    # Check if client accepts HTML (browser request)
    accept_header = request.headers.get("accept", "")
    if "text/html" in accept_header and os.path.exists(FRONTEND_INDEX):
        return FileResponse(FRONTEND_INDEX, headers={"Cache-Control": "no-cache"})

    # Return JSON for API clients
    return {
        "name": "Video Understanding & Summarization Platform",
        "version": __version__,
        "status": "operational",
        "docs": "/docs",
        "redoc": "/redoc",
        "frontend": "/static/index.html",
        "endpoints": {
            "videos": "/api/videos",
            "search": "/api/search",
            "clips": "/api/clips",
            "websocket": "/api/ws",
        }
    }


@app.get("/login")
async def login_page():
    return FileResponse(FRONTEND_LOGIN, headers={"Cache-Control": "no-cache"})


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
app.include_router(auth_router)
app.include_router(videos_router)
app.include_router(processing_router)
app.include_router(analysis_router)
app.include_router(search_router)
app.include_router(clips_router)
app.include_router(jobs_router)
app.include_router(websockets_router)

# ============================================================================
# Static Files
# ============================================================================

# /uploads, /clips and /thumbnails used to be mounted here: anyone could fetch any file by name without
# signing in. Files now only leave through the endpoints that check who owns them
# (/api/clips/{id}/download, /api/videos/{id}/frames/..., highlight thumbnails).

class RevalidatingStaticFiles(StaticFiles):
    """
    Frontend files the browser must re-check on every load. Sent with no
    Cache-Control at all, a browser kept running its old app.js after a fix
    (a page that had the XSS fix on disk still ran the vulnerable copy). The
    files keep their ETag, so an unchanged file is a cheap 304.
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Serve frontend files (fixes tracking prevention by using same origin)
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", RevalidatingStaticFiles(directory=FRONTEND_DIR), name="frontend")


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(404)
async def not_found_handler(request, exc):
    """Handle 404 errors - serve frontend for SPA routes"""
    # If the request is for an API endpoint, return JSON error
    if request.url.path.startswith("/api/") or request.url.path.startswith("/docs") or request.url.path.startswith("/redoc"):
        return JSONResponse(
            status_code=404,
            content={
                "error": "Not Found",
                "message": f"The requested resource '{request.url.path}' was not found",
            }
        )

    # For frontend routes, serve index.html (SPA handling)
    if os.path.exists(FRONTEND_INDEX):
        return FileResponse(FRONTEND_INDEX, headers={"Cache-Control": "no-cache"})

    # Fallback to JSON error if no frontend
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
