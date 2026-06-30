"""
FastAPI server for Multi-Agent Task Orchestrator
"""

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.core.config import settings
from src.api import tasks, agents, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan event handler for startup and shutdown
    """
    # Startup
    print(f"🚀 Starting {settings.APP_NAME}")
    print(f"📊 Database: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'configured'}")
    print(f"🔴 Redis: {settings.REDIS_URL}")
    print(f"🤖 Default LLM: {settings.DEFAULT_LLM_PROVIDER}/{settings.DEFAULT_MODEL}")

    yield

    # Shutdown
    print(f"🛑 Shutting down {settings.APP_NAME}")


# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered multi-agent task orchestration system using LangGraph",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

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
