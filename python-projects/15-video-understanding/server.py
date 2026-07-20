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

from src.core.config import settings
from src.core.database import Base, engine
from src.core.logging import setup_logging
from src.core.middleware import (
    LoggingMiddleware,
    RateLimitMiddleware,
    ErrorHandlingMiddleware,
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
    logger.info(f"Environment: {settings.app_env}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"Database URL: {settings.database_url.split('@')[-1] if '@' in settings.database_url else settings.database_url}")

    # Create database tables (if not using migrations)
    # Note: In production, use Alembic migrations instead
    if settings.debug:
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=engine)

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
        "transcription, visual understanding, and semantic search"
    ),
    version="15.1.8",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)


# ============================================================================
# Middleware Configuration
# ============================================================================

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
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
        "version": "15.1.8",
        "status": "operational",
        "docs": "/docs",
        "redoc": "/redoc",
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "environment": settings.app_env,
        "database": "connected",
    }


@app.get("/version")
async def version():
    """Version information"""
    return {
        "version": "15.1.8",
        "api_version": "v1",
        "environment": settings.app_env,
    }


# ============================================================================
# API Routes (to be added in later commits)
# ============================================================================

# TODO: Add API routers in future commits:
# - /api/videos
# - /api/scenes
# - /api/frames
# - /api/transcripts
# - /api/summaries
# - /api/highlights
# - /api/search
# - /api/clips
# - /ws/process


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
