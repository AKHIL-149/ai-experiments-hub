"""Content Moderation System FastAPI Server"""

from fastapi import FastAPI, HTTPException, Depends, Cookie, Response, Request, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import uvicorn
import os
import hashlib
from pathlib import Path
from dotenv import load_dotenv

from src.core.database import (
    DatabaseManager, User, ContentItem, Classification,
    ContentType, ContentStatus, ViolationCategory
)
from src.core.auth_manager import AuthManager, UserRole

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
    Submit content for moderation

    Supports:
    - Text content (text_content field)
    - Image upload (file field)
    - Video upload (file field)
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

        # Validate input based on content type
        if content_type_enum == ContentType.TEXT:
            if not text_content or not text_content.strip():
                raise HTTPException(status_code=400, detail="text_content is required for text submissions")
            file_path = None
            file_hash = None

        elif content_type_enum in [ContentType.IMAGE, ContentType.VIDEO]:
            if not file:
                raise HTTPException(status_code=400, detail="file is required for image/video submissions")

            # Check file size
            file_size = 0
            file_data = bytearray()
            for chunk in file.file:
                chunk_data = chunk if isinstance(chunk, bytes) else chunk.encode()
                file_data.extend(chunk_data)
                file_size += len(chunk_data)

                if file_size > MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size: {MAX_UPLOAD_SIZE_MB}MB"
                    )

            # Save file
            file_ext = Path(file.filename).suffix if file.filename else '.bin'
            file_name = f"{user.id}_{ContentType(content_type).value}_{os.urandom(8).hex()}{file_ext}"
            file_path_obj = UPLOAD_DIR / file_name

            with open(file_path_obj, 'wb') as f:
                f.write(file_data)

            file_path = str(file_path_obj)
            file_hash = calculate_file_hash(file_path_obj)

            # Check for duplicate
            existing = db.query(ContentItem).filter(
                ContentItem.file_hash == file_hash
            ).first()

            if existing:
                # Delete uploaded file
                file_path_obj.unlink()
                return {
                    "success": True,
                    "content": existing.to_dict(),
                    "duplicate": True,
                    "message": "Duplicate content detected. Returning existing submission."
                }

        else:
            raise HTTPException(status_code=400, detail="Unsupported content type")

        # Create content item
        content_item = ContentItem(
            user_id=user.id,
            content_type=content_type_enum,
            text_content=text_content,
            file_path=file_path,
            file_hash=file_hash,
            status=ContentStatus.PENDING,
            priority=priority or 0
        )

        db.add(content_item)
        db.commit()
        db.refresh(content_item)

        # TODO: Enqueue moderation job (Phase 4)
        # For now, content is just stored as PENDING

        return {
            "success": True,
            "content": content_item.to_dict(),
            "message": "Content submitted for moderation"
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


if __name__ == "__main__":
    port = int(os.getenv('PORT', 8000))
    host = os.getenv('HOST', '0.0.0.0')
    uvicorn.run(app, host=host, port=port)
