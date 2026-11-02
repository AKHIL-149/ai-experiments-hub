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
import re
import sys
import time
import uuid
import hashlib
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Cookie, Response, WebSocket, WebSocketDisconnect, Request, UploadFile, File, Query
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator, model_validator
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.database import DatabaseManager, Document
from src.core.auth_manager import AuthManager
from src.core.web_search_client import WebSearchClient
from src.core.arxiv_client import ArXivClient
from src.core.llm_client import LLMClient
from src.core.research_orchestrator import ResearchOrchestrator
from src.services.cache_manager import CacheManager
from src.services.document_processor import extract_text, chunk_text, DocumentProcessingError, SUPPORTED_TYPES
from src.services.vector_store import get_vector_store
from src.services.embedding_service import get_embedding_service
from src.utils.report_generator import ReportGenerator
from src.utils.usage_analytics import UsageAnalytics
from src.utils.cost_tracker import CostTracker
from src.utils.rate_limit import FailureThrottle

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Limits
MAX_QUERY_CHARS = int(os.getenv('MAX_QUERY_CHARS', 2000))
MAX_SOURCES_LIMIT = int(os.getenv('MAX_SOURCES_LIMIT', 50))
PROGRESS_TTL_SECONDS = 600

# Failed logins allowed per username and client before further attempts get a 429
login_throttle = FailureThrottle(
    max_failures=int(os.getenv('LOGIN_MAX_FAILURES', 10)),
    window_seconds=int(os.getenv('LOGIN_WINDOW_SECONDS', 300)),
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


def static_version(rel_path: str) -> str:
    """
    Short cache-busting token for a static asset, derived from its mtime.

    StaticFiles serves no explicit Cache-Control header, so browsers fall
    back to heuristic caching (RFC 7234) off Last-Modified alone - which
    can and does serve a stale script/stylesheet indefinitely across
    edits without ever revalidating. Confirmed live here: after fixing a
    real bug in app.js, a brand new browser tab kept executing the
    pre-fix function body - fetch(url, {cache:'no-store'}) got the new
    content, but the real <script src> tag load did not. Appending
    ?v=<mtime-hash> changes the URL itself whenever the file changes,
    bypassing heuristic caching without touching the StaticFiles mount.
    Same fix already applied in project 12 (AKHIL-238).
    """
    try:
        mtime = os.path.getmtime(Path("static") / rel_path)
        return hashlib.md5(str(mtime).encode()).hexdigest()[:8]
    except OSError:
        return "0"


templates.env.globals["static_version"] = static_version

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

# My Documents (RAG) - vector store and embedding model are process-wide
# singletons, not created per-request like create_research_orchestrator()
# does for its other clients. Both are expensive to construct
# (SentenceTransformer loads model weights; PersistentClient opens the
# on-disk index) and, unlike the web/arxiv/llm clients, have no reason
# to vary per-request or per-user - loading them fresh on every request
# would make every research query and every upload noticeably slower
# for no benefit.
documents_dir = Path(os.getenv('DOCUMENTS_DIR', './data/documents'))
documents_dir.mkdir(parents=True, exist_ok=True)
chroma_dir = os.getenv('CHROMA_DIR', './data/chroma')
max_upload_bytes = int(os.getenv('MAX_UPLOAD_MB', '20')) * 1024 * 1024

vector_store = None
embedding_service = None
try:
    vector_store = get_vector_store(persist_dir=chroma_dir)
    embedding_service = get_embedding_service()
except Exception as e:
    # Document upload/search degrades to "unavailable" rather than
    # taking the whole server down - the rest of the app (web/arxiv
    # research) doesn't depend on this.
    logging.warning(f"Document RAG unavailable (vector_store/embedding_service failed to init): {e}")

# Initialize analytics and cost tracking (Phase 5)
usage_analytics = UsageAnalytics(db_manager)
cost_tracker = CostTracker(log_file=os.getenv('COST_LOG_FILE', './data/costs.jsonl'))

# WebSocket connection registry
ws_connections: Dict[str, WebSocket] = {}


# Pydantic models
class RegisterRequest(BaseModel):
    username: str = Field(max_length=200)
    email: str = Field(max_length=200)
    password: str = Field(max_length=1000)


class LoginRequest(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=1000)


CITATION_STYLES = {'APA': 'APA', 'MLA': 'MLA', 'CHICAGO': 'Chicago', 'IEEE': 'IEEE'}


class ResearchRequest(BaseModel):
    query: str = Field(max_length=MAX_QUERY_CHARS)
    search_web: bool = True
    search_arxiv: bool = True
    search_documents: bool = False
    max_sources: int = Field(20, ge=1, le=MAX_SOURCES_LIMIT)
    citation_style: str = 'APA'
    # Chosen by the page so it can ask how far this research has got while the request is open
    request_id: Optional[str] = Field(None, pattern=r'^[A-Za-z0-9\-]{8,64}$')

    @field_validator('query')
    @classmethod
    def query_has_text(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError('Enter a research question (at least 3 characters)')
        return value

    @field_validator('citation_style')
    @classmethod
    def known_style(cls, value: str) -> str:
        style = CITATION_STYLES.get(value.strip().upper())
        if not style:
            raise ValueError(f"Unknown citation style. Use one of: {', '.join(CITATION_STYLES.values())}")
        return style

    @model_validator(mode='after')
    def some_source(self):
        # With nothing ticked the run used to go through every stage and answer "No sources found"
        if not (self.search_web or self.search_arxiv or self.search_documents):
            raise ValueError('Choose at least one source to search')
        return self


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """`detail` as one readable sentence: the page shows it to the user, and FastAPI's own list of
    objects displayed as "[object Object]"."""
    problems = []
    for err in exc.errors():
        loc = list(err.get("loc", ()))
        if loc and loc[0] in ("body", "query", "path"):  # where it was found, not which field (a field can be called "query")
            loc = loc[1:]
        field = ".".join(str(part) for part in loc)
        message = str(err.get("msg", "Invalid value")).removeprefix("Value error, ")
        problems.append(f"{field}: {message}" if field else message)
    return JSONResponse(status_code=422, content={"detail": "; ".join(problems) or "Invalid request"})


# Research progress, so the page can show how far a run has got. Kept in memory: it only matters
# while the request is open.
research_progress: Dict[str, Dict[str, Any]] = {}
progress_lock = threading.Lock()
# One research at a time per user (a second tab or a double click would start a second one)
running_research: set = set()


def set_progress(request_id: Optional[str], user_id: str, **fields):
    if not request_id:
        return
    now = time.time()
    with progress_lock:
        for key in [k for k, v in research_progress.items() if now - v['updated'] > PROGRESS_TTL_SECONDS]:
            del research_progress[key]
        entry = research_progress.setdefault(request_id, {'user_id': user_id, 'step': 0, 'total': 6,
                                                          'message': 'Starting', 'status': 'running'})
        entry.update(fields)
        entry['updated'] = now


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
        api_key=llm_api_key,
        # Without it nothing was ever recorded, and the cost and usage figures stayed empty
        cost_tracker=cost_tracker
    )

    # The model that ranks and de-duplicates sources is the one already loaded for documents. A
    # fresh SentenceTransformer per request loaded the weights again (and asked HuggingFace about
    # every file) before each research.
    embedding_model = embedding_service.model if embedding_service else None

    # Create orchestrator
    orchestrator = ResearchOrchestrator(
        db_path=database_url,
        web_search_client=web_client,
        arxiv_client=arxiv_client,
        llm_client=llm_client,
        embedding_model=embedding_model,
        cache_manager=cache_manager,
        vector_store=vector_store,
        embedding_service=embedding_service
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

def client_key(request: Request) -> str:
    return request.client.host if request.client else 'unknown'


# The auth handlers are plain `def` on purpose: FastAPI runs those in a worker thread. bcrypt takes
# ~0.25 s of CPU per hash, and as `async def` each login or guest sign-in froze the whole server.

@app.post("/api/auth/register")
def register(req: RegisterRequest):
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
            "email": user.email,
            "is_guest": user.is_guest
        }


@app.post("/api/auth/login")
def login(req: LoginRequest, request: Request, response: Response):
    """Login and create session."""
    throttle_key = f"{client_key(request)}|{req.username.lower()}"
    wait = login_throttle.retry_after(throttle_key)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed logins. Try again in {wait} seconds.",
            headers={"Retry-After": str(wait)},
        )

    with db_manager.get_session() as db_session:
        # Authenticate user
        success, user, error = auth_manager.authenticate(
            db_session,
            username=req.username,
            password=req.password
        )

        if not success:
            login_throttle.record_failure(throttle_key)
            raise HTTPException(status_code=401, detail=error)

        login_throttle.reset(throttle_key)

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
            "email": user.email,
            "is_guest": user.is_guest
        }


@app.post("/api/auth/guest")
def guest_login(response: Response):
    """Create a temporary guest account and log in as it - no signup
    form required. Mirrors /api/auth/login's session/cookie setup."""
    with db_manager.get_session() as db_session:
        success, user, error = auth_manager.create_guest_user(db_session)

        if not success:
            raise HTTPException(status_code=400, detail=error)

        success, session, error = auth_manager.create_session(db_session, user)

        if not success:
            raise HTTPException(status_code=500, detail="Failed to create session")

        cookie_secure = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
        response.set_cookie(
            key="session_token",
            value=session.id,
            httponly=True,
            secure=cookie_secure,
            samesite="strict",
            max_age=session_ttl * 24 * 60 * 60
        )

        return {
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "is_guest": user.is_guest
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
        "is_guest": user.is_guest,
        "created_at": user.created_at.isoformat()
    }


# Document endpoints (My Documents / RAG)

@app.post("/api/documents")
def upload_document(
    file: UploadFile = File(...),
    session_token: Optional[str] = Cookie(None)
):
    """
    Upload a document for 'My Documents' research search.

    Synchronous, like /api/research: extracts text, chunks it, embeds
    each chunk, and stores the embeddings before responding - by the
    time this returns 200, the document is already searchable. No
    background job/polling, matching how the rest of this app works.
    """
    user = get_current_user(session_token)

    if not vector_store or not embedding_service:
        raise HTTPException(
            status_code=503,
            detail="Document upload is unavailable (embedding/vector store failed to initialize)"
        )

    # A bare file name: browsers send just the name, other clients can send "../../x.pdf" or text
    # with control characters, and it is stored, listed and shown back
    filename = os.path.basename((file.filename or "upload").replace('\\', '/'))
    filename = ''.join(ch for ch in filename if ch.isprintable())[:200].strip() or "upload"
    file_type = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if file_type not in SUPPORTED_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{file_type}'. Supported: {', '.join(sorted(SUPPORTED_TYPES))}"
        )

    # Never more than the limit plus one byte: the whole body was read before it was compared
    content = file.file.read(max_upload_bytes + 1)
    if len(content) > max_upload_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"File too large (the limit is {max_upload_bytes / 1024 / 1024:.0f}MB)"
        )
    if not content:
        raise HTTPException(status_code=400, detail="File is empty")

    document_id = str(uuid.uuid4())
    user_dir = documents_dir / user.id
    user_dir.mkdir(parents=True, exist_ok=True)
    dest_path = user_dir / f"{document_id}.{file_type}"
    dest_path.write_bytes(content)

    with db_manager.get_session() as db_session:
        doc = Document(
            id=document_id,
            user_id=user.id,
            filename=filename,
            file_type=file_type,
            file_size_bytes=len(content),
            file_path=str(dest_path),
            status='processing'
        )
        db_session.add(doc)
        db_session.commit()

    try:
        text = extract_text(str(dest_path), file_type)
        chunks = chunk_text(text)

        if not chunks:
            raise DocumentProcessingError("Document produced no usable text chunks")

        embeddings = embedding_service.embed_texts(chunks)
        chunk_count = vector_store.add_chunks(
            document_id=document_id,
            user_id=user.id,
            chunks=chunks,
            embeddings=embeddings,
            filename=filename
        )

        with db_manager.get_session() as db_session:
            doc = db_session.query(Document).filter_by(id=document_id).first()
            doc.status = 'ready'
            doc.chunk_count = chunk_count
            doc.processed_at = datetime.utcnow()
            db_session.commit()
            result = doc.to_dict()

        return result

    except Exception as e:
        logging.error(f"Document processing failed for {document_id}: {e}", exc_info=True)
        with db_manager.get_session() as db_session:
            doc = db_session.query(Document).filter_by(id=document_id).first()
            if doc:
                doc.status = 'failed'
                doc.error_message = str(e)
                db_session.commit()
        # 200, not 500 - the upload itself succeeded and is now tracked
        # (visible in GET /api/documents as status='failed'); only text
        # extraction/embedding failed, e.g. a scanned/image-only PDF.
        return JSONResponse(status_code=200, content={
            "id": document_id,
            "filename": filename,
            "status": "failed",
            "error_message": str(e)
        })


@app.get("/api/documents")
def list_documents(session_token: Optional[str] = Cookie(None)):
    """List the current user's uploaded documents."""
    user = get_current_user(session_token)

    with db_manager.get_session() as db_session:
        docs = (
            db_session.query(Document)
            .filter_by(user_id=user.id)
            .order_by(Document.uploaded_at.desc())
            .all()
        )
        return {"documents": [d.to_dict() for d in docs]}


@app.delete("/api/documents/{document_id}")
def delete_document(
    document_id: str,
    session_token: Optional[str] = Cookie(None)
):
    """Delete an uploaded document (DB row, file on disk, and vector chunks)."""
    user = get_current_user(session_token)

    with db_manager.get_session() as db_session:
        doc = db_session.query(Document).filter_by(id=document_id, user_id=user.id).first()

        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")

        file_path = Path(doc.file_path)

        db_session.delete(doc)
        db_session.commit()

    if vector_store:
        vector_store.delete_document(document_id)

    try:
        file_path.unlink(missing_ok=True)
    except OSError as e:
        logging.warning(f"Failed to delete file for document {document_id}: {e}")

    return {"success": True}


# Research endpoints

def research_reader() -> ResearchOrchestrator:
    """An orchestrator that only reads saved research (no search, LLM or embedding clients)"""
    return ResearchOrchestrator(
        db_path=database_url,
        web_search_client=None,
        arxiv_client=None,
        llm_client=None,
        embedding_model=None,
        cache_manager=None
    )


# `def`, not `async def`: a research takes a minute of blocking work (searching, reading pages, the
# model), and on the event loop it froze every other request, the health check and the progress
# polling included.
@app.post("/api/research")
def create_research(
    req: ResearchRequest,
    session_token: Optional[str] = Cookie(None)
):
    """Create new research query."""
    user = get_current_user(session_token)

    with progress_lock:
        if user.id in running_research:
            raise HTTPException(status_code=429, detail="A research is already running. Wait for it to finish.")
        running_research.add(user.id)

    set_progress(req.request_id, user.id, step=0, message="Starting", status='running')

    def on_progress(step: int, total: int, message: str):
        set_progress(req.request_id, user.id, step=step, total=total, message=message)

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
            citation_style=req.citation_style,
            progress=on_progress
        )

        set_progress(req.request_id, user.id, step=6, message="Done", status='done')
        return results

    except Exception as e:
        logging.error(f"Research failed: {e}", exc_info=True)
        set_progress(req.request_id, user.id, message=str(e), status='failed')
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        with progress_lock:
            running_research.discard(user.id)


@app.get("/api/research/progress/{request_id}")
def get_research_progress(
    request_id: str,
    session_token: Optional[str] = Cookie(None)
):
    """How far a running research has got (step 1-6 of 6 and what it is doing)."""
    user = get_current_user(session_token)

    with progress_lock:
        entry = research_progress.get(request_id)
        if not entry or entry['user_id'] != user.id:
            raise HTTPException(status_code=404, detail="No such research in progress")
        return {key: entry[key] for key in ('step', 'total', 'message', 'status')}


@app.get("/api/research/{query_id}")
def get_research(
    query_id: str,
    session_token: Optional[str] = Cookie(None)
):
    """Get research query results."""
    user = get_current_user(session_token)

    # Only the owner's: any signed-in user could read any other user's research by its id
    results = research_reader().get_research_query(query_id, user_id=user.id)

    if not results:
        raise HTTPException(status_code=404, detail="Research query not found")

    return results


@app.get("/api/research")
def list_research(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session_token: Optional[str] = Cookie(None)
):
    """List user's research queries."""
    user = get_current_user(session_token)

    reader = research_reader()
    queries = reader.list_user_queries(
        user_id=user.id,
        limit=limit,
        offset=offset
    )

    return {
        "queries": queries,
        # The number of queries the user has: it was the number on this page
        "total": reader.count_user_queries(user.id),
        "limit": limit,
        "offset": offset
    }


@app.delete("/api/research/{query_id}")
def delete_research(
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


REPORT_MEDIA_TYPES = {
    'markdown': 'text/markdown', 'html': 'text/html', 'json': 'application/json',
    'pdf': 'application/pdf',
    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}
REPORT_EXTENSIONS = {'markdown': 'md', 'html': 'html', 'json': 'json', 'pdf': 'pdf', 'docx': 'docx'}


@app.get("/api/export-formats")
def export_formats(session_token: Optional[str] = Cookie(None)):
    """The report formats this server can really produce (PDF needs the pango library)"""
    get_current_user(session_token)
    return {"formats": ReportGenerator(output_dir=output_dir).get_info()['supported_formats']}


@app.get("/api/research/{query_id}/download")
def download_research(
    query_id: str,
    format: str = 'markdown',
    session_token: Optional[str] = Cookie(None)
):
    """Download research report."""
    user = get_current_user(session_token)

    kind = ReportGenerator.FORMAT_ALIASES.get((format or '').lower())
    if not kind:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{format}'. Use one of: {', '.join(sorted(REPORT_MEDIA_TYPES))}"
        )

    # Get research results - only the owner's
    results = research_reader().get_research_query(query_id, user_id=user.id)

    if not results:
        raise HTTPException(status_code=404, detail="Research query not found")

    # Generate report
    gen = ReportGenerator(output_dir=output_dir)
    try:
        report_path = gen.generate_report(
            research_data=results,
            format=kind,
            filename=f"research_{query_id}"
        )
    except ValueError as e:
        # e.g. PDF without the pango library: the server cannot do it, which is not a server bug
        raise HTTPException(status_code=501, detail=str(e))

    return FileResponse(
        path=str(report_path),
        filename=f"research_{query_id}.{REPORT_EXTENSIONS[kind]}",
        media_type=REPORT_MEDIA_TYPES[kind]
    )


# Analytics endpoints (Phase 5)

@app.get("/api/analytics/usage")
async def get_usage_stats(
    days: int = Query(30, ge=1, le=365),
    session_token: Optional[str] = Cookie(None)
):
    """Get usage statistics for current user."""
    user = get_current_user(session_token)

    try:
        stats = usage_analytics.get_user_stats(user.id, days=days)
        return stats
    except Exception as e:
        logging.error(f"Failed to get usage stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analytics/costs")
async def get_cost_analysis(
    days: int = Query(30, ge=1, le=365),
    session_token: Optional[str] = Cookie(None)
):
    """Get cost analysis for current user."""
    user = get_current_user(session_token)

    try:
        costs = usage_analytics.get_cost_analysis(user.id, days=days)
        return costs
    except Exception as e:
        logging.error(f"Failed to get cost analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analytics/sources")
async def get_source_effectiveness(
    days: int = Query(30, ge=1, le=365),
    session_token: Optional[str] = Cookie(None)
):
    """Get source effectiveness analysis."""
    user = get_current_user(session_token)

    try:
        effectiveness = usage_analytics.get_source_effectiveness(user.id, days=days)
        return effectiveness
    except Exception as e:
        logging.error(f"Failed to get source effectiveness: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analytics/performance")
async def get_performance_metrics(
    days: int = Query(30, ge=1, le=365),
    session_token: Optional[str] = Cookie(None)
):
    """Get system-wide performance metrics (admin only for now)."""
    user = get_current_user(session_token)

    try:
        metrics = usage_analytics.get_performance_metrics(days=days)
        return metrics
    except Exception as e:
        logging.error(f"Failed to get performance metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analytics/session-costs")
async def get_session_costs(
    session_token: Optional[str] = Cookie(None)
):
    """Get current session cost breakdown."""
    user = get_current_user(session_token)

    try:
        breakdown = cost_tracker.get_session_breakdown()
        return breakdown
    except Exception as e:
        logging.error(f"Failed to get session costs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# WebSocket endpoint

def origin_allowed(origin: Optional[str], host: Optional[str]) -> bool:
    """
    Browsers send no CORS preflight for a WebSocket, and SameSite=Strict is "same site", not "same
    origin": a page on another port of localhost is same-site, so the browser attached the session
    cookie to its connection. Accept the page's own origin (Origin host == Host header) and
    ALLOWED_ORIGINS; clients that send no Origin are not browsers and cannot ride a cookie.
    """
    if not origin:
        return True
    if origin in [o.strip() for o in os.getenv('ALLOWED_ORIGINS', 'http://localhost:8000').split(',')]:
        return True
    return bool(host) and urlparse(origin).netloc == host


@app.websocket("/ws/research/{query_id}")
async def websocket_research(
    websocket: WebSocket,
    query_id: str,
    session_token: Optional[str] = Cookie(None)
):
    """
    Keep-alive socket. Research progress is read from GET /api/research/progress/{request_id}.

    The session comes from the cookie. It used to be a `?session_token=` query parameter, which
    puts the token in server logs and browser history.
    """
    if not origin_allowed(websocket.headers.get('origin'), websocket.headers.get('host')):
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    try:
        user = get_current_user(session_token)
    except HTTPException:
        await websocket.close(code=1008, reason="Not authenticated")
        return

    await websocket.accept()
    ws_connections[query_id] = websocket

    try:
        await websocket.send_json({
            "type": "connected",
            "query_id": query_id,
            "user_id": user.id
        })

        while True:
            await websocket.receive_text()
            await websocket.send_json({
                "type": "pong",
                "timestamp": datetime.now().isoformat()
            })

    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        if ws_connections.get(query_id) is websocket:
            del ws_connections[query_id]


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup."""
    logging.info("Starting Research Assistant API server")
    db_manager.create_tables()
    logging.info("Database tables initialized")

    # Research left 'processing' by a server that stopped mid-run
    interrupted = research_reader().fail_interrupted_queries()
    if interrupted:
        logging.warning(f"Marked {interrupted} interrupted research(es) as failed")
    with db_manager.get_session() as db_session:
        auth_manager.cleanup_expired_sessions(db_session)


# Run server
if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv('PORT', '8000'))
    # Loopback unless HOST says otherwise (the app holds sign-ins and runs your model for anyone who
    # can reach it); it listened on every interface whatever HOST was set to elsewhere.
    host = os.getenv('HOST', '127.0.0.1')
    # Auto-reload restarts the server (and kills a research in progress) whenever a source file
    # changes: for development only
    reload = os.getenv('RELOAD', 'false').lower() == 'true'

    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info"
    )
