"""Content Moderation System FastAPI Server"""

from fastapi import FastAPI, HTTPException, Depends, Cookie, Response, Request, UploadFile, File, Form, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
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
from src.utils.file_handler import get_file_handler

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

# Database
db_manager = DatabaseManager(os.getenv('DATABASE_URL'))
db_manager.create_tables()

# Templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Session configuration
SESSION_TTL_DAYS = int(os.getenv('SESSION_TTL_DAYS', '30'))
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
MAX_UPLOAD_SIZE_MB = int(os.getenv('MAX_UPLOAD_SIZE_MB', '100'))
UPLOAD_DIR = Path(os.getenv('UPLOAD_DIR', './data/uploads'))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# Pydantic models

class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ContentSubmitText(BaseModel):
    text_content: str
    priority: Optional[int] = 0


class ContentStatusUpdate(BaseModel):
    status: ContentStatus


class UserRoleUpdate(BaseModel):
    role: UserRole


class ReviewSubmitRequest(BaseModel):
    content_id: str
    approved: bool
    category: Optional[str] = None
    notes: Optional[str] = None


class AppealCreateRequest(BaseModel):
    content_id: str
    reason: str


class AppealReviewRequest(BaseModel):
    approved: bool
    notes: Optional[str] = None


class PolicyCreateRequest(BaseModel):
    name: str
    category: str
    auto_reject_threshold: float = 0.9
    flag_review_threshold: float = 0.5
    severity: int = 5
    enabled: bool = True


class PolicyUpdateRequest(BaseModel):
    auto_reject_threshold: Optional[float] = None
    flag_review_threshold: Optional[float] = None
    severity: Optional[int] = None
    enabled: Optional[bool] = None


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
    """Extract client IP address from request"""
    # Check for forwarded IP (behind proxy)
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()

    # Check for real IP (behind proxy)
    real_ip = request.headers.get('X-Real-IP')
    if real_ip:
        return real_ip

    # Fall back to client host
    return request.client.host if request.client else 'unknown'


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
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/admin/dashboard")
async def admin_dashboard(request: Request):
    """Serve admin dashboard page"""
    return templates.TemplateResponse("admin/dashboard.html", {"request": request})


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

    return {
        "status": "ok",
        "database": "connected",
        "version": "1.0.0",
        "stats": {
            "users": user_count,
            "content_items": content_count
        }
    }


# Authentication endpoints

@app.post("/api/auth/register")
async def register(data: RegisterRequest, response: Response, request: Request):
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


@app.post("/api/auth/login")
async def login(data: LoginRequest, response: Response, request: Request):
    """Login user"""
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        success, user, error = auth_manager.authenticate(data.username, data.password)

        if not success:
            raise HTTPException(status_code=401, detail=error or "Invalid credentials")

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
    with db_manager.get_session() as db:
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

        elif content_type_enum in [ContentType.IMAGE, ContentType.VIDEO]:
            if not file:
                raise HTTPException(status_code=400, detail="file is required for image/video submissions")

            # Read file data
            file_data = await file.read()

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

            # Check for duplicate
            existing = db.query(ContentItem).filter(
                ContentItem.file_hash == file_hash
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
            priority=priority or 0
        )

        db.add(content_item)
        db.commit()
        db.refresh(content_item)

        # Phase 4: Asynchronous classification with Celery
        try:
            # Create moderation job based on content type
            if content_type_enum == ContentType.TEXT:
                job = queue_manager.create_text_job(
                    content_id=content_item.id,
                    text_content=text_content,
                    priority=priority or 0
                )
            elif content_type_enum == ContentType.IMAGE:
                job = queue_manager.create_image_job(
                    content_id=content_item.id,
                    file_path=file_path,
                    use_vision=True,
                    priority=priority or 0
                )
            elif content_type_enum == ContentType.VIDEO:
                job = queue_manager.create_video_job(
                    content_id=content_item.id,
                    file_path=file_path,
                    max_frames=10,
                    use_vision=False,  # Faster processing
                    priority=priority or 0
                )
            else:
                raise ValueError(f"Unsupported content type: {content_type_enum}")

            # Update content status to processing
            content_item.status = ContentStatus.PROCESSING
            db.commit()
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


@app.get("/api/content")
async def list_user_content(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
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
            "content": [item.to_dict() for item in items],
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
    limit: int = 50,
    offset: int = 0,
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
    limit: int = 50,
    offset: int = 0,
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
            item_dict = item.to_dict()
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

@app.websocket("/ws/jobs/{job_id}")
async def websocket_job_updates(websocket: WebSocket, job_id: str):
    """
    WebSocket endpoint for real-time job progress updates.

    Client connects with job_id and receives progress updates every 1 second.
    """
    await websocket.accept()

    try:
        from src.core.queue_manager import get_queue_manager
        from src.core.database import ModerationJob

        queue_manager = get_queue_manager()

        # Verify job exists
        with db_manager.get_session() as db:
            job = db.query(ModerationJob).filter(ModerationJob.id == job_id).first()

            if not job:
                await websocket.send_json({
                    "error": "Job not found"
                })
                await websocket.close()
                return

        # Send updates until task completes
        while True:
            status = queue_manager.get_job_status(job_id)

            # Send status update
            await websocket.send_json(status)

            # Check if task is done
            celery_state = status.get('celery_state')
            if celery_state in ['SUCCESS', 'FAILURE', 'REVOKED']:
                # Send final update and close
                await asyncio.sleep(1)
                await websocket.send_json({
                    **status,
                    'done': True
                })
                break

            # Wait 1 second before next update
            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logging.info(f"WebSocket disconnected for job {job_id}")
    except Exception as e:
        logging.error(f"WebSocket error for job {job_id}: {e}")
        try:
            await websocket.send_json({
                "error": str(e)
            })
        except:
            pass
    finally:
        try:
            await websocket.close()
        except:
            pass


if __name__ == "__main__":
    port = int(os.getenv('PORT', 7000))
    host = os.getenv('HOST', '0.0.0.0')
    uvicorn.run(app, host=host, port=port)
