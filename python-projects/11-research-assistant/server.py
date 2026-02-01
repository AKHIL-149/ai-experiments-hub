#!/usr/bin/env python3
"""
Research Assistant Web Server

FastAPI server with:
- User authentication (session-based)
- Research query API
- WebSocket for real-time progress
- Static file serving
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Cookie, Response, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.database import DatabaseManager
from src.core.auth_manager import AuthManager
from src.core.web_search_client import WebSearchClient
from src.core.arxiv_client import ArXivClient
from src.core.llm_client import LLMClient
from src.core.research_orchestrator import ResearchOrchestrator
from src.services.cache_manager import CacheManager
from src.utils.report_generator import ReportGenerator

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Initialize FastAPI app
app = FastAPI(
    title="Research Assistant API",
    description="Multi-source AI research with citations",
    version="1.0.0"
)

# CORS configuration
allowed_origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:8000').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Initialize managers
database_url = os.getenv('DATABASE_URL', 'sqlite:///./data/database.db')
session_ttl = int(os.getenv('SESSION_TTL_DAYS', '30'))

db_manager = DatabaseManager(database_url)
auth_manager = AuthManager(session_ttl_days=session_ttl)

# Initialize research components
cache_dir = os.getenv('CACHE_DIR', './data/cache')
cache_enabled = os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
cache_manager = CacheManager(cache_dir=cache_dir, enable_cache=cache_enabled)

arxiv_cache_dir = os.getenv('ARXIV_CACHE_DIR', './data/papers')
output_dir = os.getenv('OUTPUT_DIR', './data/output')

# Global research orchestrator (will be initialized per request with user-specific settings)
llm_provider = os.getenv('LLM_PROVIDER', 'ollama').lower()
llm_model = os.getenv('LLM_MODEL')

# WebSocket connection registry
ws_connections: Dict[str, WebSocket] = {}


# Pydantic models
class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ResearchRequest(BaseModel):
    query: str
    search_web: bool = True
    search_arxiv: bool = True
    search_documents: bool = False
    max_sources: int = 20
    citation_style: str = 'APA'


# Helper functions
def get_current_user(session_token: Optional[str]):
    """Validate session and get current user."""
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    with db_manager.get_session() as db_session:
        valid, user, error = auth_manager.validate_session(db_session, session_token)

        if not valid:
            raise HTTPException(status_code=401, detail=error or "Invalid session")

        return user


def create_research_orchestrator(
    search_web: bool = True,
    search_arxiv: bool = True
) -> ResearchOrchestrator:
    """Create research orchestrator with configured clients."""
    # Initialize web search client
    web_client = None
    if search_web:
        web_client = WebSearchClient(
            provider='duckduckgo',
            cache_manager=cache_manager
        )

    # Initialize ArXiv client
    arxiv_client = None
    if search_arxiv:
        arxiv_client = ArXivClient(cache_dir=arxiv_cache_dir)

    # Initialize LLM client
    llm_api_key = (
        os.getenv('OPENAI_API_KEY') if llm_provider == 'openai'
        else os.getenv('ANTHROPIC_API_KEY')
    )

    llm_client = LLMClient(
        provider=llm_provider,
        model=llm_model,
        api_key=llm_api_key
    )

    # Initialize embedding model (optional)
    embedding_model = None
    try:
        from sentence_transformers import SentenceTransformer
        embedding_model_name = os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
        embedding_model = SentenceTransformer(embedding_model_name)
    except Exception as e:
        logging.warning(f"Failed to load embedding model: {e}")

    # Create orchestrator
    orchestrator = ResearchOrchestrator(
        db_path=database_url,
        web_search_client=web_client,
        arxiv_client=arxiv_client,
        llm_client=llm_client,
        embedding_model=embedding_model,
        cache_manager=cache_manager
    )

    return orchestrator


# Routes

@app.get("/")
async def index(request: Request):
    """Serve main page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "ok",
        "database": "connected",
        "cache_enabled": cache_enabled,
        "llm_provider": llm_provider
    }


# Authentication endpoints

@app.post("/api/auth/register")
async def register(req: RegisterRequest):
    """Register new user."""
    with db_manager.get_session() as db_session:
        success, user, error = auth_manager.register_user(
            db_session,
            username=req.username,
            email=req.email,
            password=req.password
        )

        if not success:
            raise HTTPException(status_code=400, detail=error)

        return {
            "user_id": user.id,
            "username": user.username,
            "email": user.email
        }


@app.post("/api/auth/login")
async def login(req: LoginRequest, response: Response):
    """Login and create session."""
    with db_manager.get_session() as db_session:
        # Authenticate user
        success, user, error = auth_manager.authenticate(
            db_session,
            username=req.username,
            password=req.password
        )

        if not success:
            raise HTTPException(status_code=401, detail=error)

        # Create session
        success, session, error = auth_manager.create_session(db_session, user)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to create session")

        # Set session cookie
        cookie_secure = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
        response.set_cookie(
            key="session_token",
            value=session.id,
            httponly=True,
            secure=cookie_secure,
            samesite="strict",
            max_age=session_ttl * 24 * 60 * 60  # Convert days to seconds
        )

        return {
            "user_id": user.id,
            "username": user.username,
            "email": user.email
        }


@app.post("/api/auth/logout")
async def logout(
    response: Response,
    session_token: Optional[str] = Cookie(None)
):
    """Logout and delete session."""
    if session_token:
        with db_manager.get_session() as db_session:
            auth_manager.delete_session(db_session, session_token)

    # Clear cookie
    response.delete_cookie("session_token")

    return {"success": True}


@app.get("/api/auth/me")
async def get_current_user_info(session_token: Optional[str] = Cookie(None)):
    """Get current user information."""
    user = get_current_user(session_token)

    return {
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "created_at": user.created_at.isoformat()
    }


# Research endpoints

@app.post("/api/research")
async def create_research(
    req: ResearchRequest,
    session_token: Optional[str] = Cookie(None)
):
    """Create new research query."""
    user = get_current_user(session_token)

    try:
        # Create orchestrator
        orchestrator = create_research_orchestrator(
            search_web=req.search_web,
            search_arxiv=req.search_arxiv
        )

        # Conduct research
        results = orchestrator.conduct_research(
            user_id=user.id,
            query=req.query,
            search_web=req.search_web,
            search_arxiv=req.search_arxiv,
            search_documents=req.search_documents,
            max_sources=req.max_sources,
            citation_style=req.citation_style
        )

        return results

    except Exception as e:
        logging.error(f"Research failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/research/{query_id}")
async def get_research(
    query_id: str,
    session_token: Optional[str] = Cookie(None)
):
    """Get research query results."""
    user = get_current_user(session_token)

    # Create minimal orchestrator without clients (not needed for retrieval)
    orchestrator = ResearchOrchestrator(
        db_path=database_url,
        web_search_client=None,
        arxiv_client=None,
        llm_client=None,
        embedding_model=None,
        cache_manager=None
    )

    results = orchestrator.get_research_query(query_id)

    if not results:
        raise HTTPException(status_code=404, detail="Research query not found")

    return results


@app.get("/api/research")
async def list_research(
    limit: int = 50,
    offset: int = 0,
    session_token: Optional[str] = Cookie(None)
):
    """List user's research queries."""
    user = get_current_user(session_token)

    # Create minimal orchestrator without web/arxiv clients (not needed for listing)
    orchestrator = ResearchOrchestrator(
        db_path=database_url,
        web_search_client=None,
        arxiv_client=None,
        llm_client=None,
        embedding_model=None,
        cache_manager=None
    )

    queries = orchestrator.list_user_queries(
        user_id=user.id,
        limit=limit,
        offset=offset
    )

    return {
        "queries": queries,
        "total": len(queries),
        "limit": limit,
        "offset": offset
    }


@app.delete("/api/research/{query_id}")
async def delete_research(
    query_id: str,
    session_token: Optional[str] = Cookie(None)
):
    """Delete research query."""
    user = get_current_user(session_token)

    with db_manager.get_session() as db_session:
        from src.core.database import ResearchQuery

        query = db_session.query(ResearchQuery).filter_by(
            id=query_id,
            user_id=user.id
        ).first()

        if not query:
            raise HTTPException(status_code=404, detail="Research query not found")

        db_session.delete(query)
        db_session.commit()

    return {"success": True}


@app.get("/api/research/{query_id}/download")
async def download_research(
    query_id: str,
    format: str = 'markdown',
    session_token: Optional[str] = Cookie(None)
):
    """Download research report."""
    user = get_current_user(session_token)

    # Get research results - create minimal orchestrator
    orchestrator = ResearchOrchestrator(
        db_path=database_url,
        web_search_client=None,
        arxiv_client=None,
        llm_client=None,
        embedding_model=None,
        cache_manager=None
    )

    results = orchestrator.get_research_query(query_id)

    if not results:
        raise HTTPException(status_code=404, detail="Research query not found")

    # Generate report
    gen = ReportGenerator(output_dir=output_dir)
    report_path = gen.generate_report(
        research_data=results,
        format=format,
        filename=f"research_{query_id}"
    )

    return FileResponse(
        path=str(report_path),
        filename=report_path.name,
        media_type='application/octet-stream'
    )


# WebSocket endpoint

@app.websocket("/ws/research/{query_id}")
async def websocket_research(websocket: WebSocket, query_id: str):
    """WebSocket for real-time research progress."""
    await websocket.accept()

    try:
        # Get session token from query params or headers
        session_token = websocket.query_params.get('session_token')

        if not session_token:
            await websocket.send_json({
                "type": "error",
                "error": "Authentication required"
            })
            await websocket.close()
            return

        # Validate session
        try:
            user = get_current_user(session_token)
        except HTTPException:
            await websocket.send_json({
                "type": "error",
                "error": "Invalid session"
            })
            await websocket.close()
            return

        # Register connection
        ws_connections[query_id] = websocket

        # Send initial message
        await websocket.send_json({
            "type": "connected",
            "query_id": query_id,
            "user_id": user.id
        })

        # Keep connection alive
        while True:
            try:
                data = await websocket.receive_text()
                # Echo back for keepalive
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                })
            except WebSocketDisconnect:
                break

    except Exception as e:
        logging.error(f"WebSocket error: {e}")
        await websocket.send_json({
            "type": "error",
            "error": str(e)
        })

    finally:
        # Unregister connection
        if query_id in ws_connections:
            del ws_connections[query_id]


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    logging.info("Starting Research Assistant API server")
    db_manager.create_tables()
    logging.info("Database tables initialized")


# Run server
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv('PORT', '8000'))
    host = os.getenv('HOST', '0.0.0.0')

    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )
