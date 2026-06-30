"""
FastAPI server for Multi-Agent Task Orchestrator
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.core.config import settings
from src.core.logging import setup_logging, logger
from src.core.middleware import RequestLoggingMiddleware, ErrorTrackingMiddleware
from src.api import tasks, agents, health, metrics


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler for startup and shutdown
    """
    # Startup
    logger.info(f"🚀 Starting {settings.APP_NAME}")
    logger.info(f"📊 Database: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'configured'}")
    logger.info(f"🔴 Redis: {settings.REDIS_URL}")
    logger.info(f"🤖 Default LLM: {settings.DEFAULT_LLM_PROVIDER}/{settings.DEFAULT_MODEL}")
    logger.info(f"📝 Log Level: {settings.LOG_LEVEL}")

    yield

    # Shutdown
    logger.info(f"🛑 Shutting down {settings.APP_NAME}")


# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered multi-agent task orchestration system using LangGraph",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add custom middleware
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(ErrorTrackingMiddleware)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api", tags=["Health"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(agents.router, prefix="/api/agents", tags=["Agents"])
app.include_router(metrics.router, prefix="/api", tags=["Metrics"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": "0.1.0",
        "status": "running",
        "docs": "/docs",
    }


if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )
