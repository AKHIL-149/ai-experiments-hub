"""Content Moderation System FastAPI Server"""

from fastapi import FastAPI, HTTPException, Depends, Cookie, Response, Request, UploadFile, File, Form, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List
from urllib.parse import urlparse
import uvicorn
import os
import hashlib
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

from src.core.database import (
    DatabaseManager, User, ContentItem, Classification, Review, Policy,
    ContentType, ContentStatus, ViolationCategory
)
from src.core.auth_manager import AuthManager, UserRole
from src.services.classification_service import get_classification_service
from src.services.admin_service import get_admin_service
from src.services.analytics_service import get_analytics_service
from src.utils.file_handler import get_file_handler
from src.utils.cost_tracker import get_cost_tracker
from src.utils.rate_limit import FailureThrottle
from src.middleware.rate_limiter import client_ip

# Load environment
load_dotenv()

# Initialize FastAPI
app = FastAPI(
    title="Content Moderation System",
    version="1.0.0",
    description="AI-powered multi-modal content moderation platform"
)

# CORS middleware
allowed_origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:8000').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting - nothing else in this app enforced any limits on auth
# endpoints, so a client could hammer /api/auth/register, /api/auth/login,
# or /api/auth/guest indefinitely (unlimited account creation, unlimited
# credential-stuffing attempts). Redis-backed with an in-memory fallback
# if Redis is unreachable.
from src.middleware.rate_limiter import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# Database
db_manager = DatabaseManager(os.getenv('DATABASE_URL'))
db_manager.create_tables()

# Templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


def static_version(rel_path: str) -> str:
    """
    Short cache-busting token for a static asset, derived from its mtime.

    StaticFiles serves no explicit Cache-Control header, so browsers fall
    back to heuristic caching (RFC 7234) off Last-Modified alone - which
    can and does serve a stale script/stylesheet indefinitely across
    deploys without ever revalidating. Confirmed live: after editing
    dashboard.js, a brand new browser tab/profile kept executing the
    pre-edit function body - `fetch(url, {cache:'no-store'})` got the
    new content, but the real `<script src>` tag load did not.
    Appending ?v=<mtime-hash> changes the URL itself whenever the file
    changes, which bypasses heuristic caching without needing
    Cache-Control changes to the StaticFiles mount.
    """
    try:
        mtime = os.path.getmtime(Path("static") / rel_path)
        return hashlib.md5(str(mtime).encode()).hexdigest()[:8]
    except OSError:
        return "0"


templates.env.globals["static_version"] = static_version

# Session configuration
SESSION_TTL_DAYS = int(os.getenv('SESSION_TTL_DAYS', '30'))
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
MAX_UPLOAD_SIZE_MB = int(os.getenv('MAX_UPLOAD_SIZE_MB', '100'))
UPLOAD_DIR = Path(os.getenv('UPLOAD_DIR', './data/uploads'))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Limits
MAX_TEXT_CHARS = int(os.getenv('MAX_TEXT_CHARS', 10000))
# Priorities a regular user may pick: 0 normal, 5 high. 10 (the critical queue) is for moderators:
# the form offered it to everyone, so any user could put their submissions ahead of everyone else's.
USER_MAX_PRIORITY = 5
MAX_PRIORITY = 10

# Failed logins allowed per username and client before further attempts get a 429. The per-IP
# limit in the middleware is separate; this one follows the username across addresses.
login_throttle = FailureThrottle(
    max_failures=int(os.getenv('LOGIN_MAX_FAILURES', 10)),
    window_seconds=int(os.getenv('LOGIN_WINDOW_SECONDS', 300)),
)


# Pydantic models

class RegisterRequest(BaseModel):
    username: str = Field(max_length=200)
    email: str = Field(max_length=200)
    password: str = Field(max_length=1000)


class LoginRequest(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=1000)


class ContentSubmitText(BaseModel):
    text_content: str
    priority: Optional[int] = 0


class ContentStatusUpdate(BaseModel):
    status: ContentStatus


class UserRoleUpdate(BaseModel):
    role: UserRole


class ReviewSubmitRequest(BaseModel):
    content_id: str = Field(max_length=100)
    approved: bool
    category: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = Field(None, max_length=5000)


class AppealCreateRequest(BaseModel):
    content_id: str = Field(max_length=100)
    reason: str = Field(max_length=5000)


class AppealReviewRequest(BaseModel):
    approved: bool
    notes: Optional[str] = Field(None, max_length=5000)


class PolicyCreateRequest(BaseModel):
    name: str = Field(max_length=200)
    category: str = Field(max_length=50)
    auto_reject_threshold: float = 0.9
    auto_approve_threshold: float = 0.95
    flag_review_threshold: float = 0.5
    severity: int = 5
    enabled: bool = True


class PolicyUpdateRequest(BaseModel):
    auto_reject_threshold: Optional[float] = None
    auto_approve_threshold: Optional[float] = None
    flag_review_threshold: Optional[float] = None
    severity: Optional[int] = None
    enabled: Optional[bool] = None


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """`detail` as one sentence: the page shows it, and FastAPI's list of objects displayed as [object Object]"""
    problems = []
    for err in exc.errors():
        loc = list(err.get("loc", ()))
        if loc and loc[0] in ("body", "query", "path", "form"):
            loc = loc[1:]
        field = ".".join(str(part) for part in loc)
        message = str(err.get("msg", "Invalid value")).removeprefix("Value error, ")
        problems.append(f"{field}: {message}" if field else message)
    return JSONResponse(status_code=422, content={"detail": "; ".join(problems) or "Invalid request"})


# Dependency: Get current user from session cookie
async def get_current_user(
    request: Request,
    session_token: Optional[str] = Cookie(None)
) -> User:
    """Validate session and return current user"""
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        success, user, error = auth_manager.validate_session(session_token)

        if not success:
            raise HTTPException(status_code=401, detail=error or "Invalid session")

        return user


# Dependency: Get current user with admin role
async def get_current_admin(
    current_user: User = Depends(get_current_user)
) -> User:
    """Require admin role"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


# Dependency: Get current user with moderator or admin role
async def get_current_moderator(
    current_user: User = Depends(get_current_user)
) -> User:
    """Require moderator or admin role"""
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        if not auth_manager.is_moderator(current_user):
            raise HTTPException(status_code=403, detail="Moderator access required")
    return current_user


# Helper functions

def get_client_ip(request: Request) -> str:
    """The caller's address (forwarding headers only when TRUST_PROXY=true, see client_ip)"""
    return client_ip(request)


def calculate_file_hash(file_path: Path) -> str:
    """Calculate SHA256 hash of file for deduplication"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


# Routes

@app.get("/")
async def index(request: Request):
    """Serve main HTML page"""
    return templates.TemplateResponse(request, "index.html", {"request": request})


@app.get("/admin/dashboard")
async def admin_dashboard(request: Request):
    """Serve admin dashboard page"""
    return templates.TemplateResponse(request, "admin/dashboard.html", {"request": request})


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    with db_manager.get_session() as db:
        # Test database connection
        try:
            user_count = db.query(User).count()
            content_count = db.query(ContentItem).count()
        except Exception as e:
            return {
                "status": "error",
                "database": "disconnected",
                "error": str(e)
            }

    # Without a worker every submission stays "processing" for ever, so say whether one is running
    try:
        from src.core.queue_manager import get_queue_manager
        worker = get_queue_manager().worker_status()
    except Exception as e:
        worker = {"available": False, "workers": 0, "error": str(e)[:200]}

    return {
        "status": "ok",
        "database": "connected",
        "version": "1.0.0",
        "worker": worker,
        "stats": {
            "users": user_count,
            "content_items": content_count
        }
    }


# Authentication endpoints. register, guest_login and login are plain `def` on purpose: FastAPI
# runs those in a worker thread, and bcrypt (~0.25 s of CPU per hash) froze every other request
# when they were `async def`.

@app.post("/api/auth/register")
def register(data: RegisterRequest, response: Response, request: Request):
    """Register new user"""
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        success, user, error = auth_manager.register_user(
            data.username, data.email, data.password
        )

        if not success:
            raise HTTPException(status_code=400, detail=error)

        # Create session with IP tracking
        ip_address = get_client_ip(request)
        session_token = auth_manager.create_session(user, ip_address)

        # Set HTTPOnly cookie
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite='strict',
            max_age=SESSION_TTL_DAYS * 24 * 60 * 60
        )

        return {
            "success": True,
            "user": user.to_dict()
        }


@app.post("/api/auth/guest")
def guest_login(response: Response, request: Request):
    """Create a temporary guest account and log in as it - no signup
    form required. Mirrors /api/auth/register's session/cookie setup."""
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        success, user, error = auth_manager.create_guest_user()

        if not success:
            raise HTTPException(status_code=400, detail=error)

        ip_address = get_client_ip(request)
        session_token = auth_manager.create_session(user, ip_address)

        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite='strict',
            max_age=SESSION_TTL_DAYS * 24 * 60 * 60
        )

        return {
            "success": True,
            "user": user.to_dict()
        }


@app.post("/api/auth/login")
def login(data: LoginRequest, response: Response, request: Request):
    """Login user"""
    throttle_key = f"{get_client_ip(request)}|{data.username.strip().lower()}"
    wait = login_throttle.retry_after(throttle_key)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed logins. Try again in {wait} seconds.",
            headers={"Retry-After": str(wait)},
        )

    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        success, user, error = auth_manager.authenticate(data.username, data.password)

        if not success:
            login_throttle.record_failure(throttle_key)
            raise HTTPException(status_code=401, detail=error or "Invalid credentials")

        login_throttle.reset(throttle_key)

        # Create session with IP tracking
        ip_address = get_client_ip(request)
        session_token = auth_manager.create_session(user, ip_address)

        # Set HTTPOnly cookie
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite='strict',
            max_age=SESSION_TTL_DAYS * 24 * 60 * 60
        )

        return {
            "success": True,
            "user": user.to_dict()
        }


@app.post("/api/auth/logout")
async def logout(response: Response, session_token: Optional[str] = Cookie(None)):
    """Logout user"""
    if session_token:
        with db_manager.get_session() as db:
            auth_manager = AuthManager(db, SESSION_TTL_DAYS)
            auth_manager.delete_session(session_token)

    response.delete_cookie("session_token")
    return {"success": True}


@app.get("/api/auth/me")
async def get_current_user_info(user: User = Depends(get_current_user)):
    """Get current user info"""
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)

        # Get active sessions
        active_sessions = auth_manager.get_active_sessions(user)

        user_data = user.to_dict()
        user_data['active_sessions'] = len(active_sessions)

        return user_data


# Content submission endpoints

@app.post("/api/content")
async def submit_content(
    content_type: str = Form(...),
    text_content: Optional[str] = Form(None),
    priority: Optional[int] = Form(0),
    file: Optional[UploadFile] = File(None),
    user: User = Depends(get_current_user)
):
    """
    Submit content for moderation (Phase 4: Asynchronous queue processing)

    Supports:
    - Text content (text_content field) - LLM classification (async)
    - Image upload (file field) - NSFW detection + Vision classification (async)
    - Video upload (file field) - Frame extraction + NSFW detection + aggregated classification (async)

    Returns immediately with job ID for status tracking.
    """
    # Priority: 0-5 for users, up to 10 for moderators
    priority = priority or 0
    if priority < 0 or priority > MAX_PRIORITY:
        raise HTTPException(status_code=400, detail=f"priority must be between 0 and {MAX_PRIORITY}")

    with db_manager.get_session() as db:
        if priority > USER_MAX_PRIORITY and not AuthManager(db, SESSION_TTL_DAYS).is_moderator(user):
            raise HTTPException(status_code=403, detail="Critical priority is reserved for moderators")

        # Validate content type
        try:
            content_type_enum = ContentType(content_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid content_type. Must be: {', '.join([ct.value for ct in ContentType])}"
            )

        # Initialize services
        file_handler = get_file_handler()
        from src.core.queue_manager import get_queue_manager
        queue_manager = get_queue_manager()

        file_path = None
        file_hash = None
        thumbnail_path = None

        # Validate input based on content type
        if content_type_enum == ContentType.TEXT:
            if not text_content or not text_content.strip():
                raise HTTPException(status_code=400, detail="text_content is required for text submissions")
            if len(text_content) > MAX_TEXT_CHARS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Text is too long ({len(text_content)} characters, the limit is {MAX_TEXT_CHARS})"
                )

        elif content_type_enum in [ContentType.IMAGE, ContentType.VIDEO]:
            if not file:
                raise HTTPException(status_code=400, detail="file is required for image/video submissions")

            # Read the file in pieces and stop at the limit: the whole upload (any size) was read
            # into memory before its size was looked at
            file_data = bytearray()
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                file_data += chunk
                if len(file_data) > file_handler.max_upload_size:
                    raise HTTPException(
                        status_code=400,
                        detail=f"File too large. Maximum size: {file_handler.max_upload_size // (1024 * 1024)}MB"
                    )
            file_data = bytes(file_data)

            # Save file using file handler
            success, saved_path, saved_hash, error = file_handler.save_upload(
                file_data=file_data,
                filename=file.filename or 'unknown',
                user_id=user.id,
                content_type=content_type
            )

            if not success:
                raise HTTPException(status_code=400, detail=error)

            file_path = saved_path
            file_hash = saved_hash

            # Check for duplicate - among this user's own submissions. It looked at everyone's: a user
            # uploading a file somebody else had submitted was handed that person's content record
            # (owner id, status, path) instead of getting their own file moderated.
            existing = db.query(ContentItem).filter(
                ContentItem.file_hash == file_hash,
                ContentItem.user_id == user.id
            ).first()

            if existing:
                # Delete uploaded file
                file_handler.delete_file(file_path)
                return {
                    "success": True,
                    "content": existing.to_dict(),
                    "duplicate": True,
                    "message": "Duplicate content detected. Returning existing submission."
                }

            # Generate thumbnail for images
            if content_type_enum == ContentType.IMAGE:
                success, thumb_path, error = file_handler.generate_thumbnail(file_path)
                if success:
                    thumbnail_path = thumb_path

            # Generate thumbnail for videos (Phase 3)
            elif content_type_enum == ContentType.VIDEO:
                from src.services.video_processor import get_video_processor
                video_processor = get_video_processor()
                success, thumb_path, error = video_processor.generate_video_thumbnail(file_path)
                if success:
                    thumbnail_path = thumb_path
                else:
                    logging.warning(f"Video thumbnail generation failed: {error}")

        else:
            raise HTTPException(status_code=400, detail="Unsupported content type")

        # Create content item
        content_item = ContentItem(
            user_id=user.id,
            content_type=content_type_enum,
            text_content=text_content,
            file_path=file_path,
            file_hash=file_hash,
            status=ContentStatus.PENDING,  # Pending until job is queued
            priority=priority
        )

        db.add(content_item)
        db.commit()
        db.refresh(content_item)

        # Processing before the job is sent. It was set afterwards, so a worker that finished first
        # had its decision overwritten and the item stayed "processing" for ever.
        content_item.status = ContentStatus.PROCESSING
        db.commit()

        # Phase 4: Asynchronous classification with Celery
        try:
            # Create moderation job based on content type
            if content_type_enum == ContentType.TEXT:
                job = queue_manager.create_text_job(
                    content_id=content_item.id,
                    text_content=text_content,
                    priority=priority
                )
            elif content_type_enum == ContentType.IMAGE:
                job = queue_manager.create_image_job(
                    content_id=content_item.id,
                    file_path=file_path,
                    use_vision=True,
                    priority=priority
                )
            elif content_type_enum == ContentType.VIDEO:
                job = queue_manager.create_video_job(
                    content_id=content_item.id,
                    file_path=file_path,
                    max_frames=10,
                    use_vision=True,
                    priority=priority
                )
            else:
                raise ValueError(f"Unsupported content type: {content_type_enum}")

            db.refresh(content_item)

            # Prepare response with job information
            content_dict = content_item.to_dict()
            content_dict['thumbnail_path'] = thumbnail_path
            content_dict['job_id'] = job.id
            content_dict['celery_task_id'] = job.celery_task_id
            content_dict['queue_name'] = job.queue_name

            return {
                "success": True,
                "content": content_dict,
                "job": {
                    "id": job.id,
                    "celery_task_id": job.celery_task_id,
                    "queue_name": job.queue_name,
                    "status": job.status.value
                },
                "message": f"Content submitted for {content_type} classification. Use job_id to check status."
            }

        except Exception as e:
            # Job creation failed, mark as flagged for manual review
            logging.error(f"Job creation failed for content {content_item.id}: {e}")
            content_item.status = ContentStatus.FLAGGED
            db.commit()
            db.refresh(content_item)

            return {
                "success": True,
                "content": content_item.to_dict(),
                "message": "Content submitted but job creation failed. Flagged for manual review.",
                "error": str(e)
            }


@app.get("/api/content/{content_id}")
async def get_content(
    content_id: str,
    user: User = Depends(get_current_user)
):
    """Get content item by ID"""
    with db_manager.get_session() as db:
        content = db.query(ContentItem).filter(
            ContentItem.id == content_id
        ).first()

        if not content:
            raise HTTPException(status_code=404, detail="Content not found")

        # Only allow owner or moderators to view
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        if content.user_id != user.id and not auth_manager.is_moderator(user):
            raise HTTPException(status_code=403, detail="Access denied")

        # Include classifications if moderator
        content_dict = content.to_dict()
        if auth_manager.is_moderator(user):
            classifications = db.query(Classification).filter(
                Classification.content_id == content_id
            ).all()
            content_dict['classifications'] = [c.to_dict() for c in classifications]

        return content_dict


MEDIA_TYPES = {
    '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.gif': 'image/gif', '.webp': 'image/webp',
    '.mp4': 'video/mp4', '.mov': 'video/quicktime', '.avi': 'video/x-msvideo', '.webm': 'video/webm',
}


@app.get("/api/content/{content_id}/file")
async def get_content_file(
    content_id: str,
    user: User = Depends(get_current_user)
):
    """
    The uploaded image or video, for its owner and for moderators.

    Nothing served the upload directory, so the review queue's <img src="data/uploads/..."> was a 404:
    moderators could not see the picture or video they were asked to judge.
    """
    with db_manager.get_session() as db:
        content = db.query(ContentItem).filter(ContentItem.id == content_id).first()

        if not content or not content.file_path:
            raise HTTPException(status_code=404, detail="File not found")

        if content.user_id != user.id and not AuthManager(db, SESSION_TTL_DAYS).is_moderator(user):
            # the same answer as for a missing file: no probing for ids
            raise HTTPException(status_code=404, detail="File not found")

        file_path = Path(content.file_path).resolve()

    # Only ever from the upload directory, whatever the database row says
    if UPLOAD_DIR.resolve() not in file_path.parents or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        str(file_path),
        media_type=MEDIA_TYPES.get(file_path.suffix.lower(), 'application/octet-stream'),
        headers={'X-Content-Type-Options': 'nosniff', 'Content-Disposition': 'inline'}
    )


@app.get("/api/content")
async def list_user_content(
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user)
):
    """List user's submitted content"""
    with db_manager.get_session() as db:
        query = db.query(ContentItem).filter(ContentItem.user_id == user.id)

        # Filter by status
        if status:
            try:
                status_enum = ContentStatus(status)
                query = query.filter(ContentItem.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid status")

        # Order and paginate
        query = query.order_by(ContentItem.created_at.desc())
        total = query.count()
        items = query.limit(limit).offset(offset).all()

        return {
            "content": [item.to_dict(include_details=True) for item in items],
            "total": total,
            "has_more": offset + limit < total
        }


@app.delete("/api/content/{content_id}")
async def delete_content(
    content_id: str,
    user: User = Depends(get_current_user)
):
    """Delete content (only if pending)"""
    with db_manager.get_session() as db:
        content = db.query(ContentItem).filter(
            ContentItem.id == content_id,
            ContentItem.user_id == user.id
        ).first()

        if not content:
            raise HTTPException(status_code=404, detail="Content not found")

        # Only allow deletion of pending content
        if content.status != ContentStatus.PENDING:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete content that has been moderated"
            )

        # Delete file if exists
        if content.file_path and Path(content.file_path).exists():
            Path(content.file_path).unlink()

        db.delete(content)
        db.commit()

        return {"success": True}


# Admin endpoints

@app.get("/api/admin/users")
async def list_users(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(get_current_admin)
):
    """List all users (admin only)"""
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        success, users, error = auth_manager.list_users(admin, offset, limit)

        if not success:
            raise HTTPException(status_code=403, detail=error)

        total = db.query(User).count()

        return {
            "users": [u.to_dict() for u in users],
            "total": total,
            "has_more": offset + limit < total
        }


@app.patch("/api/admin/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    data: UserRoleUpdate,
    admin: User = Depends(get_current_admin)
):
    """Update user role (admin only)"""
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        success, updated_user, error = auth_manager.update_user_role(
            admin, user_id, data.role
        )

        if not success:
            raise HTTPException(status_code=400, detail=error)

        return {
            "success": True,
            "user": updated_user.to_dict()
        }


@app.post("/api/admin/users/{user_id}/deactivate")
async def deactivate_user(
    user_id: str,
    admin: User = Depends(get_current_admin)
):
    """Deactivate user (admin only)"""
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        success, updated_user, error = auth_manager.deactivate_user(admin, user_id)

        if not success:
            raise HTTPException(status_code=400, detail=error)

        return {
            "success": True,
            "user": updated_user.to_dict()
        }


@app.post("/api/admin/users/{user_id}/reactivate")
async def reactivate_user(
    user_id: str,
    admin: User = Depends(get_current_admin)
):
    """Reactivate user (admin only)"""
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        success, updated_user, error = auth_manager.reactivate_user(admin, user_id)

        if not success:
            raise HTTPException(status_code=400, detail=error)

        return {
            "success": True,
            "user": updated_user.to_dict()
        }


# Moderation queue endpoints (moderator only)

@app.get("/api/moderation/queue")
async def get_moderation_queue(
    status: Optional[str] = None,
    priority: Optional[int] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    moderator: User = Depends(get_current_moderator)
):
    """Get moderation queue (moderator only)"""
    with db_manager.get_session() as db:
        query = db.query(ContentItem)

        # Filter by status (default: flagged items)
        if status:
            try:
                status_enum = ContentStatus(status)
                query = query.filter(ContentItem.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid status")
        else:
            # Default: show flagged items
            query = query.filter(ContentItem.status == ContentStatus.FLAGGED)

        # Filter by priority
        if priority is not None:
            query = query.filter(ContentItem.priority >= priority)

        # Order by priority (high first), then created date
        query = query.order_by(
            ContentItem.priority.desc(),
            ContentItem.created_at.asc()
        )

        total = query.count()
        items = query.limit(limit).offset(offset).all()

        # Include classifications for each item
        results = []
        for item in items:
            item_dict = item.to_dict(include_details=True)
            classifications = db.query(Classification).filter(
                Classification.content_id == item.id
            ).all()
            item_dict['classifications'] = [c.to_dict() for c in classifications]
            results.append(item_dict)

        return {
            "queue": results,
            "total": total,
            "has_more": offset + limit < total
        }


@app.get("/api/moderation/stats")
async def get_moderation_stats(
    moderator: User = Depends(get_current_moderator)
):
    """Get moderation statistics (moderator only)"""
    with db_manager.get_session() as db:
        stats = {
            "pending": db.query(ContentItem).filter(
                ContentItem.status == ContentStatus.PENDING
            ).count(),
            "processing": db.query(ContentItem).filter(
                ContentItem.status == ContentStatus.PROCESSING
            ).count(),
            "flagged": db.query(ContentItem).filter(
                ContentItem.status == ContentStatus.FLAGGED
            ).count(),
            "approved": db.query(ContentItem).filter(
                ContentItem.status == ContentStatus.APPROVED
            ).count(),
            "rejected": db.query(ContentItem).filter(
                ContentItem.status == ContentStatus.REJECTED
            ).count(),
            "total": db.query(ContentItem).count()
        }

        return stats


# Phase 5: Review and Appeal endpoints

@app.post("/api/moderation/review")
async def submit_review(
    request: ReviewSubmitRequest,
    moderator: User = Depends(get_current_moderator)
):
    """Submit manual review decision (moderator only)"""
    admin_service = get_admin_service()

    success, review, error = admin_service.submit_review(
        moderator=moderator,
        content_id=request.content_id,
        approved=request.approved,
        category=request.category,
        notes=request.notes
    )

    if not success:
        raise HTTPException(status_code=400, detail=error)

    return {
        "success": True,
        "review": review.to_dict(),
        "message": f"Content {'approved' if request.approved else 'rejected'}"
    }


@app.post("/api/appeals")
async def create_appeal(
    request: AppealCreateRequest,
    user: User = Depends(get_current_user)
):
    """Create appeal for rejected content"""
    admin_service = get_admin_service()

    success, appeal_id, error = admin_service.create_appeal(
        user=user,
        content_id=request.content_id,
        reason=request.reason
    )

    if not success:
        raise HTTPException(status_code=400, detail=error)

    return {
        "success": True,
        "appeal_id": appeal_id,
        "message": "Appeal submitted successfully"
    }


@app.get("/api/appeals")
async def list_appeals(
    moderator: User = Depends(get_current_moderator)
):
    """List all appeals (moderator only)"""
    with db_manager.get_session() as db:
        appeals = db.query(Review).filter(
            Review.is_appeal_review == True
        ).order_by(Review.created_at.desc()).all()

        results = []
        for appeal in appeals:
            appeal_dict = appeal.to_dict()

            # Add content information
            content = db.query(ContentItem).filter(
                ContentItem.id == appeal.content_id
            ).first()

            if content:
                appeal_dict['content'] = content.to_dict()

            results.append(appeal_dict)

        return {
            "success": True,
            "appeals": results,
            "total": len(results)
        }


@app.post("/api/appeals/{appeal_id}/review")
async def review_appeal(
    appeal_id: str,
    request: AppealReviewRequest,
    moderator: User = Depends(get_current_moderator)
):
    """Review an appeal (moderator only)"""
    admin_service = get_admin_service()

    success, review, error = admin_service.review_appeal(
        moderator=moderator,
        appeal_id=appeal_id,
        approved=request.approved,
        notes=request.notes
    )

    if not success:
        raise HTTPException(status_code=400, detail=error)

    return {
        "success": True,
        "review": review.to_dict(),
        "message": f"Appeal {'approved' if request.approved else 'rejected'}"
    }


# Phase 5: Policy Management endpoints

@app.get("/api/admin/policies")
async def list_policies(
    enabled_only: bool = False,
    moderator: User = Depends(get_current_moderator)
):
    """List moderation policies (moderator only)"""
    admin_service = get_admin_service()

    success, policies, error = admin_service.list_policies(enabled_only=enabled_only)

    if not success:
        raise HTTPException(status_code=500, detail=error)

    return {
        "success": True,
        "policies": [p.to_dict() for p in policies],
        "total": len(policies)
    }


@app.post("/api/admin/policies")
async def create_policy(
    request: PolicyCreateRequest,
    admin: User = Depends(get_current_admin)
):
    """Create moderation policy (admin only)"""
    admin_service = get_admin_service()

    success, policy, error = admin_service.create_policy(
        admin=admin,
        name=request.name,
        category=request.category,
        auto_reject_threshold=request.auto_reject_threshold,
        auto_approve_threshold=request.auto_approve_threshold,
        flag_review_threshold=request.flag_review_threshold,
        severity=request.severity,
        enabled=request.enabled
    )

    if not success:
        raise HTTPException(status_code=400, detail=error)

    return {
        "success": True,
        "policy": policy.to_dict(),
        "message": f"Policy '{request.name}' created successfully"
    }


@app.patch("/api/admin/policies/{policy_id}")
async def update_policy(
    policy_id: str,
    request: PolicyUpdateRequest,
    admin: User = Depends(get_current_admin)
):
    """Update moderation policy (admin only)"""
    admin_service = get_admin_service()

    success, policy, error = admin_service.update_policy(
        admin=admin,
        policy_id=policy_id,
        auto_reject_threshold=request.auto_reject_threshold,
        auto_approve_threshold=request.auto_approve_threshold,
        flag_review_threshold=request.flag_review_threshold,
        severity=request.severity,
        enabled=request.enabled
    )

    if not success:
        raise HTTPException(status_code=400, detail=error)

    return {
        "success": True,
        "policy": policy.to_dict(),
        "message": f"Policy updated successfully"
    }


@app.get("/api/admin/stats")
async def get_admin_stats(
    moderator: User = Depends(get_current_moderator)
):
    """Get admin dashboard statistics (moderator only)"""
    admin_service = get_admin_service()
    stats = admin_service.get_admin_stats()

    return {
        "success": True,
        "stats": stats
    }


# Phase 6: Analytics endpoints

@app.get("/api/analytics/overview")
async def get_analytics_overview(
    moderator: User = Depends(get_current_moderator)
):
    """Get analytics overview metrics (moderator only)"""
    analytics_service = get_analytics_service()
    metrics = analytics_service.get_overview_metrics()

    return {
        "success": True,
        "metrics": metrics
    }


@app.get("/api/analytics/trends")
async def get_analytics_trends(
    days: int = Query(30, ge=1, le=365),
    moderator: User = Depends(get_current_moderator)
):
    """Get time-series trends (moderator only)"""
    analytics_service = get_analytics_service()
    trends = analytics_service.get_time_series(days=days)

    return {
        "success": True,
        "trends": trends
    }


@app.get("/api/analytics/categories")
async def get_category_breakdown(
    moderator: User = Depends(get_current_moderator)
):
    """Get violation category breakdown (moderator only)"""
    analytics_service = get_analytics_service()
    breakdown = analytics_service.get_category_breakdown()

    return {
        "success": True,
        "breakdown": breakdown
    }


@app.get("/api/analytics/content-types")
async def get_content_type_stats(
    moderator: User = Depends(get_current_moderator)
):
    """Get content type statistics (moderator only)"""
    analytics_service = get_analytics_service()
    stats = analytics_service.get_content_type_stats()

    return {
        "success": True,
        "stats": stats
    }


@app.get("/api/analytics/moderators")
async def get_moderator_performance(
    admin: User = Depends(get_current_admin)
):
    """Get moderator performance metrics (admin only)"""
    analytics_service = get_analytics_service()
    performance = analytics_service.get_moderator_performance()

    return {
        "success": True,
        "moderators": performance
    }


@app.get("/api/analytics/costs")
async def get_cost_analysis(
    moderator: User = Depends(get_current_moderator)
):
    """Get cost analysis (moderator only)"""
    analytics_service = get_analytics_service()
    costs = analytics_service.get_cost_analysis()

    return {
        "success": True,
        "costs": costs
    }


@app.get("/api/analytics/performance")
async def get_performance_metrics(
    moderator: User = Depends(get_current_moderator)
):
    """Get system performance metrics (moderator only)"""
    analytics_service = get_analytics_service()
    metrics = analytics_service.get_performance_metrics()

    return {
        "success": True,
        "metrics": metrics
    }


@app.get("/api/analytics/export")
async def export_analytics(
    days: int = Query(30, ge=1, le=365),
    format: str = 'json',
    moderator: User = Depends(get_current_moderator)
):
    """Export analytics data (moderator only)"""
    from fastapi.responses import JSONResponse
    import json

    analytics_service = get_analytics_service()
    success, data, error = analytics_service.export_analytics_data(format=format, days=days)

    if not success:
        raise HTTPException(status_code=500, detail=error)

    if format == 'json':
        return JSONResponse(content=data)
    else:
        # CSV export would go here
        return {
            "success": True,
            "message": "CSV export not yet implemented",
            "data": data
        }


# Job status endpoints (Phase 4)

@app.get("/api/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    user: User = Depends(get_current_user)
):
    """Get moderation job status"""
    from src.core.queue_manager import get_queue_manager
    from src.core.database import ModerationJob

    queue_manager = get_queue_manager()

    # Verify user owns the content
    with db_manager.get_session() as db:
        job = db.query(ModerationJob).filter(ModerationJob.id == job_id).first()

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        content = db.query(ContentItem).filter(ContentItem.id == job.content_id).first()

        if not content:
            raise HTTPException(status_code=404, detail="Content not found")

        # Check ownership or moderator status
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        if content.user_id != user.id and not auth_manager.is_moderator(user):
            raise HTTPException(status_code=403, detail="Access denied")

    # Get job status
    status = queue_manager.get_job_status(job_id)

    return status


@app.get("/api/jobs/queue/stats")
async def get_queue_stats(
    moderator: User = Depends(get_current_moderator)
):
    """Get queue statistics (moderator only)"""
    from src.core.queue_manager import get_queue_manager

    queue_manager = get_queue_manager()
    stats = queue_manager.get_queue_stats()

    return {
        "success": True,
        "stats": stats
    }


# WebSocket endpoint for real-time job updates

def origin_allowed(origin: Optional[str], host: Optional[str]) -> bool:
    """
    Browsers send no CORS preflight for a WebSocket, and SameSite=Strict is "same site", not "same
    origin": another port of localhost is the same site, so the session cookie went along. Accept
    the page's own origin (Origin host == Host header) and ALLOWED_ORIGINS; clients that send no
    Origin are not browsers and cannot ride a cookie.
    """
    if not origin:
        return True
    if origin in [o.strip() for o in os.getenv('ALLOWED_ORIGINS', 'http://localhost:8000').split(',')]:
        return True
    return bool(host) and urlparse(origin).netloc == host


@app.websocket("/ws/jobs/{job_id}")
async def websocket_job_updates(
    websocket: WebSocket,
    job_id: str,
    session_token: Optional[str] = Cookie(None)
):
    """
    WebSocket endpoint for real-time job progress updates.

    Client connects with job_id and receives progress updates every 1 second. Only the person who
    submitted the content (or a moderator) may watch a job: the socket used to accept anyone and
    answer with the job's classification, reasoning included.
    """
    if not origin_allowed(websocket.headers.get('origin'), websocket.headers.get('host')):
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    from src.core.database import ModerationJob

    with db_manager.get_session() as db:
        success, user, _ = AuthManager(db, SESSION_TTL_DAYS).validate_session(session_token or '')
        if not success:
            await websocket.close(code=1008, reason="Not authenticated")
            return

        job = db.query(ModerationJob).filter(ModerationJob.id == job_id).first()
        content = db.query(ContentItem).filter(ContentItem.id == job.content_id).first() if job else None
        # The same answer for "no such job" and "not yours": no probing for job ids
        if not job or not content or (
            content.user_id != user.id and not AuthManager(db, SESSION_TTL_DAYS).is_moderator(user)
        ):
            await websocket.close(code=1008, reason="Job not found")
            return

    await websocket.accept()

    try:
        from src.core.queue_manager import get_queue_manager
        queue_manager = get_queue_manager()

        # Send updates until the job is over
        while True:
            status = queue_manager.get_job_status(job_id)

            await websocket.send_json(status)

            # Done: the task finished, or the job row says so (a job can be over without Celery
            # reporting it, e.g. when its result has expired from Redis)
            celery_state = status.get('celery_state')
            if celery_state in ['SUCCESS', 'FAILURE', 'REVOKED'] or status.get('status') in ('completed', 'failed'):
                await asyncio.sleep(1)
                await websocket.send_json({
                    **status,
                    'done': True
                })
                break

            # Wait 1 second before next update
            await asyncio.sleep(1)

    except (WebSocketDisconnect, RuntimeError):
        logging.info(f"WebSocket disconnected for job {job_id}")
    except Exception as e:
        logging.error(f"WebSocket error for job {job_id}: {e}")
        try:
            await websocket.send_json({
                "error": "Could not read the job status"
            })
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@app.on_event("startup")
async def startup_event():
    """Close jobs left open by workers that never reported, and drop expired sessions"""
    try:
        from src.workers.job_tracker import reconcile_jobs
        closed = reconcile_jobs(db_manager)
        if closed:
            logging.info(f"Closed {closed} moderation job(s) whose content was already moderated")
    except Exception as e:
        logging.warning(f"Could not reconcile moderation jobs: {e}")

    with db_manager.get_session() as db:
        AuthManager(db, SESSION_TTL_DAYS).cleanup_expired_sessions()


if __name__ == "__main__":
    port = int(os.getenv('PORT', 7000))
    # Loopback unless HOST says otherwise: the app holds sign-ins and moderation decisions
    # (it listened on every interface whatever HOST said elsewhere)
    host = os.getenv('HOST', '127.0.0.1')
    # uvicorn itself rewrites the client address from X-Forwarded-For when the request comes from
    # 127.0.0.1 (its default), which let a local client choose its own address for every rate limit.
    # Only behind a reverse proxy you run (TRUST_PROXY=true) are those headers believed.
    trust_proxy = os.getenv('TRUST_PROXY', 'false').lower() == 'true'
    uvicorn.run(app, host=host, port=port, proxy_headers=trust_proxy)
