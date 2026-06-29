"""
FastAPI server for AI Code Review Assistant
"""

import os
import tempfile
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Response, Cookie, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from src.core.database import (
    DatabaseManager, Repository, RepositoryStatus, User, PullRequest, PRStatus,
    CodeFile, Issue, Refactoring, RefactoringStatus, Plugin
)
from src.core.auth_manager import AuthManager, UserRole
from src.services.code_analyzer_service import CodeAnalyzerService
from src.services.pr_service import PullRequestService
from src.services.schedule_service import ScheduleService
from src.workers.analysis_worker import (
    analyze_file_task,
    analyze_repository_task,
    get_analysis_results,
    get_all_cached_analyses
)
from src.workers.repository_worker import (
    clone_repository_task,
    sync_repository_task,
    delete_repository_task
)
from src.workers.pr_worker import (
    analyze_pr_task,
    sync_pr_task
)
from celery.result import AsyncResult
from celery_app import celery_app

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(
    title="AI Code Review Assistant",
    version="0.1.0",
    description="Intelligent code review system with GitHub integration"
)

# Request ID Middleware (first - needed by other middleware)
from src.middleware.request_id import RequestIDMiddleware
app.add_middleware(RequestIDMiddleware)

# CORS configuration
allowed_origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:8000').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiting Middleware
from src.middleware.rate_limiter import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# Security Headers Middleware
from src.middleware.security_headers import SecurityHeadersMiddleware
app.add_middleware(SecurityHeadersMiddleware)


# ============================================================================
# Startup Event - Initialize Cache
# ============================================================================

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    from src.services.cache_service import init_cache_from_env
    init_cache_from_env()
    print("✅ Cache service initialized")


# ============================================================================
# Error Handling Middleware
# ============================================================================

@app.middleware("http")
async def error_handling_middleware(request: Request, call_next):
    """
    Global error handling middleware with correlation ID tracking
    and structured logging
    """
    from src.services.logging_service import logging_service

    # Generate correlation ID for this request
    correlation_id = request.headers.get('X-Correlation-ID', logging_service.generate_correlation_id())

    with logging_service.correlation_context(correlation_id):
        try:
            # Log request
            logging_service.info(
                f"{request.method} {request.url.path}",
                metadata={
                    'method': request.method,
                    'path': request.url.path,
                    'query_params': dict(request.query_params),
                    'client_host': request.client.host if request.client else None
                }
            )

            # Process request
            response = await call_next(request)

            # Add correlation ID to response headers
            response.headers['X-Correlation-ID'] = correlation_id

            # Log response
            logging_service.info(
                f"Response {response.status_code}",
                metadata={'status_code': response.status_code}
            )

            return response

        except Exception as e:
            # Log error
            logging_service.error(
                f"Request failed: {str(e)}",
                metadata={
                    'method': request.method,
                    'path': request.url.path,
                    'error_type': type(e).__name__
                },
                exception=e
            )

            # Return error response
            return JSONResponse(
                status_code=500,
                content={
                    'error': 'Internal server error',
                    'correlation_id': correlation_id,
                    'message': str(e)
                },
                headers={'X-Correlation-ID': correlation_id}
            )


# Initialize database
db_url = os.getenv('DATABASE_URL')
db_manager = DatabaseManager(db_url)

# Session configuration
SESSION_TTL_DAYS = int(os.getenv('SESSION_TTL_DAYS', '30'))
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# Pydantic models for requests
class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class PasswordChangeRequest(BaseModel):
    old_password: str
    new_password: str


class CreateRepositoryRequest(BaseModel):
    """Request model for creating a repository"""
    name: str
    github_url: str
    github_token: Optional[str] = None


class UpdateRepositoryRequest(BaseModel):
    """Request model for updating a repository"""
    name: Optional[str] = None
    default_branch: Optional[str] = None
    settings: Optional[dict] = None


# Dependency: Get current user from session
async def get_current_user(session_token: Optional[str] = Cookie(None)):
    """Dependency to get current authenticated user"""
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        success, user, error = auth_manager.validate_session(session_token)

        if not success:
            raise HTTPException(status_code=401, detail=error or "Invalid session")

        return user


# Dependency: Require admin role
async def require_admin(user = Depends(get_current_user)):
    """Dependency to require admin role"""
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


# ============================================================================
# Health Check Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """
    Comprehensive health check endpoint for Docker/monitoring with system metrics
    Returns overall health status and detailed component checks
    """
    import psutil
    from datetime import datetime

    # Check all components
    components = {}
    overall_healthy = True

    # Database check
    try:
        with db_manager.get_session() as db:
            db.execute("SELECT 1")
            components["database"] = {"status": "healthy", "latency_ms": 0}
    except Exception as e:
        components["database"] = {"status": "unhealthy", "error": str(e)}
        overall_healthy = False

    # Celery check
    try:
        inspect = celery_app.control.inspect()
        active_workers = inspect.active()
        if active_workers:
            components["celery"] = {
                "status": "healthy",
                "workers": len(active_workers)
            }
        else:
            components["celery"] = {"status": "degraded", "workers": 0}
    except Exception as e:
        components["celery"] = {"status": "unhealthy", "error": str(e)}
        overall_healthy = False

    # Redis/Cache check
    try:
        from src.services.cache_service import cache_service
        test_key = "health_check_test"
        cache_service.set(test_key, "ok", ttl=10)
        result = cache_service.get(test_key)
        components["cache"] = {
            "status": "healthy" if result == "ok" else "degraded",
            "backend": "redis" if cache_service.use_redis else "memory"
        }
    except Exception as e:
        components["cache"] = {"status": "degraded", "error": str(e)}

    # System metrics
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        metrics = {
            "cpu_percent": round(cpu_percent, 2),
            "memory_percent": round(memory.percent, 2),
            "memory_available_mb": round(memory.available / (1024 * 1024), 2),
            "disk_percent": round(disk.percent, 2),
            "disk_free_gb": round(disk.free / (1024 * 1024 * 1024), 2)
        }
    except Exception as e:
        metrics = {"error": str(e)}

    # Build response
    response = {
        "status": "healthy" if overall_healthy else "unhealthy",
        "service": "code-review-assistant",
        "version": "0.1.0",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "uptime_seconds": int((datetime.utcnow() - datetime.utcfromtimestamp(psutil.boot_time())).total_seconds()),
        "components": components,
        "metrics": metrics
    }

    # Return 503 if unhealthy
    if not overall_healthy:
        return JSONResponse(status_code=503, content=response)

    return response


@app.get("/api/health/db")
async def database_health():
    """Database connectivity health check"""
    try:
        with db_manager.get_session() as db:
            # Simple query to verify database is accessible
            db.execute("SELECT 1")
            return {
                "status": "healthy",
                "component": "database",
                "database_url": db_url.split('@')[-1] if db_url else "sqlite"
            }
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "component": "database",
                "error": str(e)
            }
        )


@app.get("/api/health/celery")
async def celery_health():
    """Celery worker health check"""
    try:
        # Check if Celery workers are available
        inspect = celery_app.control.inspect()
        active_workers = inspect.active()

        if active_workers:
            return {
                "status": "healthy",
                "component": "celery",
                "workers": list(active_workers.keys()),
                "worker_count": len(active_workers)
            }
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "component": "celery",
                    "error": "No active workers found"
                }
            )
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "component": "celery",
                "error": str(e)
            }
        )


@app.get("/api/health/redis")
async def redis_health():
    """Redis connectivity health check"""
    try:
        from src.services.cache_service import cache_service

        # Try to set and get a test value
        test_key = "health_check_test"
        test_value = "ok"
        cache_service.set(test_key, test_value, ttl=10)
        result = cache_service.get(test_key)

        if result == test_value:
            return {
                "status": "healthy",
                "component": "redis",
                "backend": "redis" if cache_service.use_redis else "memory"
            }
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unhealthy",
                    "component": "redis",
                    "error": "Cache read/write test failed"
                }
            )
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "component": "redis",
                "error": str(e)
            }
        )


# ============================================================================
# Authentication Endpoints
# ============================================================================

@app.post("/api/auth/register")
async def register(data: RegisterRequest, response: Response):
    """Register a new user"""
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        success, user, error = auth_manager.register_user(
            username=data.username,
            email=data.email,
            password=data.password
        )

        if not success:
            raise HTTPException(status_code=400, detail=error)

        # Auto-login: create session
        session_token = auth_manager.create_session(user)

        # Set session cookie
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="strict",
            max_age=SESSION_TTL_DAYS * 24 * 60 * 60
        )

        return {
            "success": True,
            "user": user.to_dict(),
            "message": "Registration successful"
        }


@app.post("/api/auth/login")
async def login(data: LoginRequest, response: Response):
    """Login with username and password"""
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        success, user, error = auth_manager.authenticate(
            username=data.username,
            password=data.password
        )

        if not success:
            raise HTTPException(status_code=401, detail=error)

        # Create session
        session_token = auth_manager.create_session(user)

        # Set session cookie
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=COOKIE_SECURE,
            samesite="strict",
            max_age=SESSION_TTL_DAYS * 24 * 60 * 60
        )

        return {
            "success": True,
            "user": user.to_dict(),
            "message": "Login successful"
        }


@app.post("/api/auth/logout")
async def logout(
    response: Response,
    session_token: Optional[str] = Cookie(None)
):
    """Logout and delete session"""
    if session_token:
        with db_manager.get_session() as db:
            auth_manager = AuthManager(db, SESSION_TTL_DAYS)
            auth_manager.delete_session(session_token)

    # Clear session cookie
    response.delete_cookie(key="session_token")

    return {"success": True, "message": "Logout successful"}


@app.get("/api/auth/me")
async def get_me(user = Depends(get_current_user)):
    """Get current authenticated user"""
    return {
        "success": True,
        "user": user.to_dict()
    }


@app.post("/api/auth/change-password")
async def change_password(
    data: PasswordChangeRequest,
    user = Depends(get_current_user)
):
    """Change user password"""
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db, SESSION_TTL_DAYS)
        success, error = auth_manager.change_password(
            user=user,
            old_password=data.old_password,
            new_password=data.new_password
        )

        if not success:
            raise HTTPException(status_code=400, detail=error)

        return {
            "success": True,
            "message": "Password changed successfully"
        }


# ============================================================================
# GitHub Integration Routes
# ============================================================================

@app.post("/api/github/token")
async def set_github_token(
    data: Dict[str, str],
    user = Depends(get_current_user)
):
    """Set or update GitHub personal access token"""
    token = data.get('token')

    if not token:
        raise HTTPException(status_code=400, detail="Token is required")

    # Validate token by trying to use it
    try:
        from src.services.github_service import GitHubService
        github_service = GitHubService(github_token=token)
        user_info = github_service.get_authenticated_user()
        github_service.close()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid GitHub token: {str(e)}")

    # Save token to user
    with db_manager.get_session() as db:
        db_user = db.query(User).filter(User.id == user.id).first()
        db_user.github_token = token
        db.commit()

    return {
        "success": True,
        "message": "GitHub token saved successfully",
        "github_user": user_info.get('login')
    }


@app.get("/api/github/status")
async def get_github_status(user = Depends(get_current_user)):
    """Get GitHub authentication status"""
    with db_manager.get_session() as db:
        db_user = db.query(User).filter(User.id == user.id).first()

        if not db_user.github_token:
            return {
                "authenticated": False,
                "github_user": None
            }

        # Validate token is still working
        try:
            from src.services.github_service import GitHubService
            github_service = GitHubService(github_token=db_user.github_token)
            user_info = github_service.get_authenticated_user()
            github_service.close()

            return {
                "authenticated": True,
                "github_user": user_info.get('login'),
                "github_email": user_info.get('email'),
                "github_avatar": user_info.get('avatar_url')
            }
        except Exception as e:
            return {
                "authenticated": False,
                "github_user": None,
                "error": "Token is invalid or expired"
            }


@app.delete("/api/github/token")
async def remove_github_token(user = Depends(get_current_user)):
    """Remove GitHub token"""
    with db_manager.get_session() as db:
        db_user = db.query(User).filter(User.id == user.id).first()
        db_user.github_token = None
        db.commit()

    return {
        "success": True,
        "message": "GitHub token removed"
    }


@app.post("/api/github/webhook")
async def github_webhook(request: Request):
    """
    GitHub webhook endpoint for receiving events.

    Handles:
    - Pull request events (opened, synchronized, reopened)
    - Push events
    - Installation events
    - Review events
    """
    from src.core.webhook_handler import get_webhook_handler
    from src.services.webhook_service import get_webhook_service

    # Get raw body for signature verification
    body = await request.body()

    # Get headers
    signature = request.headers.get('X-Hub-Signature-256', '')
    event_type = request.headers.get('X-GitHub-Event', '')
    delivery_id = request.headers.get('X-GitHub-Delivery', '')

    # Verify signature
    webhook_handler = get_webhook_handler()
    if not webhook_handler.verify_signature(body, signature):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature"
        )

    # Parse JSON payload
    import json
    try:
        payload = json.loads(body.decode('utf-8'))
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload"
        )

    # Log webhook receipt
    from src.services.logging_service import logging_service
    logging_service.info(
        f"Received GitHub webhook: {event_type}",
        extra={
            'event_type': event_type,
            'delivery_id': delivery_id,
            'action': payload.get('action')
        }
    )

    # Handle event asynchronously
    webhook_service = get_webhook_service()
    result = await webhook_handler.handle_event(event_type, payload)

    # Return success response
    return {
        "success": True,
        "event": event_type,
        "delivery_id": delivery_id,
        "result": result
    }


# ============================================================================
# GitHub App Configuration Routes
# ============================================================================

@app.get("/api/github/app/status")
async def get_github_app_status(user = Depends(get_current_user)):
    """Get GitHub App configuration status"""
    from src.core.github_app import get_github_app

    github_app = get_github_app()

    # Check if GitHub App is configured
    is_configured = github_app.is_configured()

    if not is_configured:
        return {
            "configured": False,
            "app_id": None,
            "private_key_set": False,
            "installations": []
        }

    # Get app info
    try:
        # Get list of installations (requires admin permission)
        installations = []

        return {
            "configured": True,
            "app_id": github_app.app_id,
            "private_key_set": github_app.private_key is not None,
            "installations": installations,
            "webhook_url": f"{os.getenv('HOST', 'http://localhost:8000')}/api/github/webhook"
        }
    except Exception as e:
        return {
            "configured": True,
            "app_id": github_app.app_id,
            "private_key_set": github_app.private_key is not None,
            "error": str(e),
            "installations": []
        }


@app.post("/api/github/app/config")
async def update_github_app_config(
    data: Dict[str, Any],
    user = Depends(require_admin)
):
    """Update GitHub App configuration (admin only)"""
    app_id = data.get('app_id')
    private_key = data.get('private_key')

    if not app_id or not private_key:
        raise HTTPException(
            status_code=400,
            detail="app_id and private_key are required"
        )

    # Validate configuration
    try:
        from src.core.github_app import GitHubApp

        # Test the configuration
        test_app = GitHubApp(app_id=app_id, private_key=private_key)

        # Try to generate a JWT token to validate
        token = test_app.generate_jwt()
        if not token:
            raise ValueError("Failed to generate JWT token")

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid GitHub App configuration: {str(e)}"
        )

    # Save to environment file (or database)
    # Note: In production, you'd want to save this securely
    env_path = os.path.join(os.getcwd(), '.env')

    # Read current .env
    env_content = ""
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            env_content = f.read()

    # Update or add app_id and private_key
    lines = env_content.split('\n')
    app_id_found = False
    private_key_found = False

    for i, line in enumerate(lines):
        if line.startswith('GITHUB_APP_ID='):
            lines[i] = f'GITHUB_APP_ID={app_id}'
            app_id_found = True
        elif line.startswith('GITHUB_PRIVATE_KEY='):
            # Escape newlines in private key
            escaped_key = private_key.replace('\n', '\\n')
            lines[i] = f'GITHUB_PRIVATE_KEY="{escaped_key}"'
            private_key_found = True

    if not app_id_found:
        lines.append(f'GITHUB_APP_ID={app_id}')
    if not private_key_found:
        escaped_key = private_key.replace('\n', '\\n')
        lines.append(f'GITHUB_PRIVATE_KEY="{escaped_key}"')

    # Write back to .env
    with open(env_path, 'w') as f:
        f.write('\n'.join(lines))

    # Reload environment
    load_dotenv(override=True)

    return {
        "success": True,
        "message": "GitHub App configuration updated successfully",
        "restart_required": True
    }


@app.get("/api/github/app/installations")
async def get_github_app_installations(user = Depends(get_current_user)):
    """Get list of GitHub App installations"""
    from src.core.github_app import get_github_app
    import requests

    github_app = get_github_app()

    if not github_app.is_configured():
        raise HTTPException(
            status_code=400,
            detail="GitHub App is not configured"
        )

    try:
        # Generate JWT token
        jwt_token = github_app.generate_jwt()

        # Get installations
        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28'
        }

        response = requests.get(
            f'{github_app.github_api_url}/app/installations',
            headers=headers,
            timeout=10
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to fetch installations: {response.text}"
            )

        installations = response.json()

        # Format installation data
        formatted_installations = []
        for installation in installations:
            formatted_installations.append({
                'id': installation['id'],
                'account': {
                    'login': installation['account']['login'],
                    'type': installation['account']['type'],
                    'avatar_url': installation['account']['avatar_url']
                },
                'repository_selection': installation.get('repository_selection'),
                'created_at': installation.get('created_at'),
                'updated_at': installation.get('updated_at')
            })

        return {
            "success": True,
            "installations": formatted_installations,
            "count": len(formatted_installations)
        }

    except requests.RequestException as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch installations: {str(e)}"
        )


@app.post("/api/github/app/test")
async def test_github_app_connection(user = Depends(require_admin)):
    """Test GitHub App connectivity (admin only)"""
    from src.core.github_app import get_github_app
    import requests

    github_app = get_github_app()

    if not github_app.is_configured():
        return {
            "success": False,
            "configured": False,
            "error": "GitHub App is not configured"
        }

    try:
        # Test JWT generation
        jwt_token = github_app.generate_jwt()
        if not jwt_token:
            return {
                "success": False,
                "configured": True,
                "jwt_generation": False,
                "error": "Failed to generate JWT token"
            }

        # Test API connectivity
        headers = {
            'Authorization': f'Bearer {jwt_token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28'
        }

        response = requests.get(
            f'{github_app.github_api_url}/app',
            headers=headers,
            timeout=10
        )

        if response.status_code != 200:
            return {
                "success": False,
                "configured": True,
                "jwt_generation": True,
                "api_connectivity": False,
                "error": f"API returned {response.status_code}: {response.text}"
            }

        app_info = response.json()

        return {
            "success": True,
            "configured": True,
            "jwt_generation": True,
            "api_connectivity": True,
            "app_info": {
                "id": app_info.get('id'),
                "name": app_info.get('name'),
                "owner": app_info.get('owner', {}).get('login'),
                "html_url": app_info.get('html_url')
            }
        }

    except requests.RequestException as e:
        return {
            "success": False,
            "configured": True,
            "jwt_generation": True,
            "api_connectivity": False,
            "error": f"Network error: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "configured": True,
            "error": str(e)
        }


# ============================================================================
# Slack Integration Routes
# ============================================================================

@app.get("/api/slack/config")
async def get_slack_config(
    repository_id: Optional[str] = None,
    user = Depends(get_current_user)
):
    """Get Slack configuration for user/repository"""
    from src.core.database import SlackConfiguration

    with db_manager.get_session() as db:
        query = db.query(SlackConfiguration).filter(
            SlackConfiguration.user_id == user.id
        )

        if repository_id:
            query = query.filter(SlackConfiguration.repository_id == repository_id)

        configs = query.all()

        return {
            'success': True,
            'configurations': [config.to_dict() for config in configs]
        }


@app.post("/api/slack/config")
async def create_slack_config(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """Create or update Slack configuration"""
    from src.core.database import SlackConfiguration

    webhook_url = data.get('webhook_url')
    if not webhook_url:
        raise HTTPException(status_code=400, detail="webhook_url is required")

    config_id = data.get('id')
    repository_id = data.get('repository_id')

    with db_manager.get_session() as db:
        if config_id:
            # Update existing
            config = db.query(SlackConfiguration).filter(
                SlackConfiguration.id == config_id,
                SlackConfiguration.user_id == user.id
            ).first()

            if not config:
                raise HTTPException(status_code=404, detail="Configuration not found")
        else:
            # Create new
            config = SlackConfiguration(
                user_id=user.id,
                repository_id=repository_id
            )
            db.add(config)

        # Update fields
        config.webhook_url = webhook_url
        config.channel = data.get('channel')
        config.username = data.get('username', 'Code Review Assistant')
        config.icon_emoji = data.get('icon_emoji', ':robot_face:')
        config.enabled = data.get('enabled', True)
        config.notify_pr_opened = data.get('notify_pr_opened', True)
        config.notify_pr_analysis_complete = data.get('notify_pr_analysis_complete', True)
        config.notify_critical_issues = data.get('notify_critical_issues', True)
        config.notify_analysis_failed = data.get('notify_analysis_failed', True)
        config.use_threads = data.get('use_threads', True)
        config.min_severity = data.get('min_severity', 'info')
        config.only_failures = data.get('only_failures', False)

        db.commit()
        db.refresh(config)

        return {
            'success': True,
            'configuration': config.to_dict()
        }


@app.delete("/api/slack/config/{config_id}")
async def delete_slack_config(
    config_id: str,
    user = Depends(get_current_user)
):
    """Delete Slack configuration"""
    from src.core.database import SlackConfiguration

    with db_manager.get_session() as db:
        config = db.query(SlackConfiguration).filter(
            SlackConfiguration.id == config_id,
            SlackConfiguration.user_id == user.id
        ).first()

        if not config:
            raise HTTPException(status_code=404, detail="Configuration not found")

        db.delete(config)
        db.commit()

        return {
            'success': True,
            'message': 'Slack configuration deleted'
        }


@app.post("/api/slack/test")
async def test_slack_connection(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """Test Slack webhook connection"""
    from src.services.slack_service import SlackService

    webhook_url = data.get('webhook_url')
    channel = data.get('channel')

    if not webhook_url:
        raise HTTPException(status_code=400, detail="webhook_url is required")

    # Create temporary Slack service
    slack_service = SlackService(webhook_url=webhook_url)

    # Send test message
    result = slack_service.send_message(
        text=f"Test message from Code Review Assistant for user {user.username}",
        blocks=[
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': ':white_check_mark: *Slack Integration Test*\n\nYour Slack webhook is configured correctly!'
                }
            }
        ],
        channel=channel
    )

    return result


# ============================================================================
# Email Configuration Routes
# ============================================================================

@app.get("/api/email/config")
async def get_email_config(
    repository_id: Optional[str] = None,
    user = Depends(get_current_user)
):
    """Get Email configuration for user/repository"""
    from src.core.database import EmailConfiguration

    with db_manager.get_session() as db:
        query = db.query(EmailConfiguration).filter(
            EmailConfiguration.user_id == user.id
        )

        if repository_id:
            query = query.filter(EmailConfiguration.repository_id == repository_id)

        configs = query.all()

        return {
            'success': True,
            'configurations': [config.to_dict() for config in configs]
        }


@app.post("/api/email/config")
async def create_email_config(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """Create or update Email configuration"""
    from src.core.database import EmailConfiguration

    # Required fields
    from_email = data.get('from_email')
    to_email = data.get('to_email')

    if not from_email or not to_email:
        raise HTTPException(status_code=400, detail="from_email and to_email are required")

    config_id = data.get('id')
    repository_id = data.get('repository_id')

    with db_manager.get_session() as db:
        if config_id:
            # Update existing
            config = db.query(EmailConfiguration).filter(
                EmailConfiguration.id == config_id,
                EmailConfiguration.user_id == user.id
            ).first()

            if not config:
                raise HTTPException(status_code=404, detail="Configuration not found")
        else:
            # Create new
            config = EmailConfiguration(
                user_id=user.id,
                repository_id=repository_id,
                from_email=from_email,
                to_email=to_email
            )
            db.add(config)

        # Update fields
        config.smtp_host = data.get('smtp_host')
        config.smtp_port = data.get('smtp_port', 587)
        config.smtp_username = data.get('smtp_username')
        config.smtp_password = data.get('smtp_password')
        config.smtp_use_tls = data.get('smtp_use_tls', True)
        config.from_email = from_email
        config.from_name = data.get('from_name', 'Code Review Assistant')
        config.to_email = to_email
        config.reply_to = data.get('reply_to')
        config.enabled = data.get('enabled', True)
        config.notify_pr_opened = data.get('notify_pr_opened', True)
        config.notify_pr_analysis_complete = data.get('notify_pr_analysis_complete', True)
        config.notify_critical_issues = data.get('notify_critical_issues', True)
        config.notify_analysis_failed = data.get('notify_analysis_failed', True)
        config.enable_digest = data.get('enable_digest', False)
        config.digest_frequency = data.get('digest_frequency', 'daily')
        config.digest_time = data.get('digest_time', '09:00')
        config.min_severity = data.get('min_severity', 'info')
        config.only_failures = data.get('only_failures', False)

        db.commit()
        db.refresh(config)

        return {
            'success': True,
            'configuration': config.to_dict()
        }


@app.delete("/api/email/config/{config_id}")
async def delete_email_config(
    config_id: str,
    user = Depends(get_current_user)
):
    """Delete Email configuration"""
    from src.core.database import EmailConfiguration

    with db_manager.get_session() as db:
        config = db.query(EmailConfiguration).filter(
            EmailConfiguration.id == config_id,
            EmailConfiguration.user_id == user.id
        ).first()

        if not config:
            raise HTTPException(status_code=404, detail="Configuration not found")

        db.delete(config)
        db.commit()

        return {
            'success': True,
            'message': 'Email configuration deleted'
        }


@app.post("/api/email/test")
async def test_email_connection(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """Test Email SMTP connection"""
    from src.services.email_service import EmailService

    # Required fields
    smtp_host = data.get('smtp_host')
    smtp_port = data.get('smtp_port', 587)
    smtp_username = data.get('smtp_username')
    smtp_password = data.get('smtp_password')
    from_email = data.get('from_email')
    to_email = data.get('to_email')

    if not all([smtp_host, smtp_username, smtp_password, from_email, to_email]):
        raise HTTPException(
            status_code=400,
            detail="smtp_host, smtp_username, smtp_password, from_email, and to_email are required"
        )

    # Create temporary Email service
    email_service = EmailService(
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password=smtp_password,
        smtp_use_tls=data.get('smtp_use_tls', True),
        from_email=from_email,
        from_name=data.get('from_name', 'Code Review Assistant')
    )

    # Send test email
    html_body = """
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #10b981;">✅ Email Configuration Test</h2>
        <p>Your email configuration is working correctly!</p>
        <p style="color: #6b7280; font-size: 12px;">
            This is a test email from Code Review Assistant.
        </p>
    </body>
    </html>
    """

    result = email_service.send_email(
        to_email=to_email,
        subject='Code Review Assistant - Email Test',
        html_body=html_body,
        text_body='Email Configuration Test\n\nYour email configuration is working correctly!'
    )

    return result


# ============================================================================
# Discord Configuration Routes
# ============================================================================

@app.get("/api/discord/config")
async def get_discord_config(
    repository_id: Optional[str] = None,
    user = Depends(get_current_user)
):
    """Get Discord configuration for user/repository"""
    from src.core.database import DiscordConfiguration

    with db_manager.get_session() as db:
        query = db.query(DiscordConfiguration).filter(
            DiscordConfiguration.user_id == user.id
        )

        if repository_id:
            query = query.filter(DiscordConfiguration.repository_id == repository_id)

        configs = query.all()

        return {
            'success': True,
            'configurations': [config.to_dict() for config in configs]
        }


@app.post("/api/discord/config")
async def create_discord_config(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """Create or update Discord configuration"""
    from src.core.database import DiscordConfiguration

    webhook_url = data.get('webhook_url')
    if not webhook_url:
        raise HTTPException(status_code=400, detail="webhook_url is required")

    config_id = data.get('id')
    repository_id = data.get('repository_id')

    with db_manager.get_session() as db:
        if config_id:
            # Update existing
            config = db.query(DiscordConfiguration).filter(
                DiscordConfiguration.id == config_id,
                DiscordConfiguration.user_id == user.id
            ).first()

            if not config:
                raise HTTPException(status_code=404, detail="Configuration not found")
        else:
            # Create new
            config = DiscordConfiguration(
                user_id=user.id,
                repository_id=repository_id
            )
            db.add(config)

        # Update fields
        config.webhook_url = webhook_url
        config.username = data.get('username', 'Code Review Assistant')
        config.avatar_url = data.get('avatar_url')
        config.enabled = data.get('enabled', True)
        config.notify_pr_opened = data.get('notify_pr_opened', True)
        config.notify_pr_analysis_complete = data.get('notify_pr_analysis_complete', True)
        config.notify_critical_issues = data.get('notify_critical_issues', True)
        config.notify_analysis_failed = data.get('notify_analysis_failed', True)
        config.min_severity = data.get('min_severity', 'info')
        config.only_failures = data.get('only_failures', False)

        db.commit()
        db.refresh(config)

        return {
            'success': True,
            'configuration': config.to_dict()
        }


@app.delete("/api/discord/config/{config_id}")
async def delete_discord_config(
    config_id: str,
    user = Depends(get_current_user)
):
    """Delete Discord configuration"""
    from src.core.database import DiscordConfiguration

    with db_manager.get_session() as db:
        config = db.query(DiscordConfiguration).filter(
            DiscordConfiguration.id == config_id,
            DiscordConfiguration.user_id == user.id
        ).first()

        if not config:
            raise HTTPException(status_code=404, detail="Configuration not found")

        db.delete(config)
        db.commit()

        return {
            'success': True,
            'message': 'Discord configuration deleted'
        }


@app.post("/api/discord/test")
async def test_discord_connection(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """Test Discord webhook connection"""
    from src.services.discord_service import DiscordService

    webhook_url = data.get('webhook_url')

    if not webhook_url:
        raise HTTPException(status_code=400, detail="webhook_url is required")

    # Create temporary Discord service
    discord_service = DiscordService(webhook_url=webhook_url)

    # Send test message
    result = discord_service.send_message(
        content=f"✅ **Discord Integration Test**",
        embeds=[{
            'title': '✅ Discord Integration Test',
            'description': f'Your Discord webhook is configured correctly for user **{user.username}**!',
            'color': 0x10b981,
            'footer': {
                'text': 'Code Review Assistant'
            }
        }]
    )

    return result


# ============================================================================
# Notification Rules Routes
# ============================================================================

@app.get("/api/notification-rules")
async def get_notification_rules(
    repository_id: Optional[str] = None,
    user = Depends(get_current_user)
):
    """Get notification rules for user/repository"""
    from src.core.database import NotificationRule

    with db_manager.get_session() as db:
        query = db.query(NotificationRule).filter(
            NotificationRule.user_id == user.id
        )

        if repository_id:
            query = query.filter(
                (NotificationRule.repository_id == repository_id) |
                (NotificationRule.repository_id == None)
            )

        rules = query.order_by(NotificationRule.priority.asc()).all()

        return {
            'success': True,
            'rules': [rule.to_dict() for rule in rules]
        }


@app.post("/api/notification-rules")
async def create_notification_rule(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """Create or update notification rule"""
    from src.core.database import NotificationRule

    # Required fields
    name = data.get('name')
    conditions = data.get('conditions')

    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not conditions:
        raise HTTPException(status_code=400, detail="conditions are required")

    rule_id = data.get('id')
    repository_id = data.get('repository_id')

    with db_manager.get_session() as db:
        if rule_id:
            # Update existing
            rule = db.query(NotificationRule).filter(
                NotificationRule.id == rule_id,
                NotificationRule.user_id == user.id
            ).first()

            if not rule:
                raise HTTPException(status_code=404, detail="Rule not found")
        else:
            # Create new
            rule = NotificationRule(
                user_id=user.id,
                repository_id=repository_id,
                name=name,
                conditions=conditions
            )
            db.add(rule)

        # Update fields
        rule.name = name
        rule.description = data.get('description')
        rule.enabled = data.get('enabled', True)
        rule.priority = data.get('priority', 100)
        rule.conditions = conditions
        rule.notify_slack = data.get('notify_slack', False)
        rule.notify_email = data.get('notify_email', False)
        rule.notify_discord = data.get('notify_discord', False)
        rule.slack_config_id = data.get('slack_config_id')
        rule.email_config_id = data.get('email_config_id')
        rule.discord_config_id = data.get('discord_config_id')
        rule.quiet_hours_enabled = data.get('quiet_hours_enabled', False)
        rule.quiet_hours = data.get('quiet_hours')
        rule.batch_notifications = data.get('batch_notifications', False)
        rule.batch_interval_minutes = data.get('batch_interval_minutes', 60)
        rule.rate_limit_enabled = data.get('rate_limit_enabled', False)
        rule.max_notifications_per_hour = data.get('max_notifications_per_hour', 10)

        db.commit()
        db.refresh(rule)

        return {
            'success': True,
            'rule': rule.to_dict()
        }


@app.delete("/api/notification-rules/{rule_id}")
async def delete_notification_rule(
    rule_id: str,
    user = Depends(get_current_user)
):
    """Delete notification rule"""
    from src.core.database import NotificationRule

    with db_manager.get_session() as db:
        rule = db.query(NotificationRule).filter(
            NotificationRule.id == rule_id,
            NotificationRule.user_id == user.id
        ).first()

        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

        db.delete(rule)
        db.commit()

        return {
            'success': True,
            'message': 'Notification rule deleted'
        }


@app.post("/api/notification-rules/{rule_id}/test")
async def test_notification_rule(
    rule_id: str,
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """Test a notification rule with sample issue"""
    from src.core.database import NotificationRule
    from src.services.notification_rules_engine import get_rules_engine

    with db_manager.get_session() as db:
        rule = db.query(NotificationRule).filter(
            NotificationRule.id == rule_id,
            NotificationRule.user_id == user.id
        ).first()

        if not rule:
            raise HTTPException(status_code=404, detail="Rule not found")

    # Get sample issue from request or use default
    sample_issue = data.get('issue', {
        'type': 'Test Issue',
        'severity': 'warning',
        'category': 'style',
        'file': 'test.py',
        'line': 10,
        'message': 'This is a test issue',
        'confidence': 90
    })

    sample_pr = data.get('pr_info', {
        'number': 999,
        'title': 'Test PR',
        'author': 'testuser',
        'repository': 'test/repo',
        'url': 'https://github.com/test/repo/pull/999'
    })

    # Evaluate rule
    engine = get_rules_engine()
    matches = engine._evaluate_rule(rule, sample_issue, sample_pr)

    result = {
        'success': True,
        'rule_name': rule.name,
        'matches': matches,
        'sample_issue': sample_issue,
        'sample_pr': sample_pr
    }

    if matches:
        action = engine._create_action(rule, sample_issue, sample_pr)
        result['action'] = action
        result['would_notify'] = len(action['channels']) > 0 if action else False
    else:
        result['action'] = None
        result['would_notify'] = False

    return result


@app.post("/api/notification-rules/evaluate")
async def evaluate_notification_rules(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """Evaluate all rules against an issue"""
    from src.services.notification_rules_engine import get_rules_engine

    issue = data.get('issue')
    pr_info = data.get('pr_info')
    repository_id = data.get('repository_id')

    if not issue:
        raise HTTPException(status_code=400, detail="issue is required")

    engine = get_rules_engine()
    actions = engine.evaluate_issue(
        issue=issue,
        pr_info=pr_info,
        user_id=user.id,
        repository_id=repository_id
    )

    return {
        'success': True,
        'actions': actions,
        'matched_rules_count': len(actions)
    }


# ============================================================================
# Batch Notifications & Digest Routes
# ============================================================================

@app.post("/api/notifications/queue")
async def queue_notification(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """Queue a notification for processing"""
    from src.workers.notification_worker import queue_notification as queue_task

    issue = data.get('issue')
    pr_info = data.get('pr_info')
    repository_id = data.get('repository_id')
    context = data.get('context')

    if not issue:
        raise HTTPException(status_code=400, detail="issue is required")

    # Queue the notification task
    task = queue_task.apply_async(
        args=[issue, pr_info, user.id, repository_id, context]
    )

    return {
        'success': True,
        'task_id': task.id,
        'message': 'Notification queued for processing'
    }


@app.post("/api/notifications/batch")
async def process_batch_notifications(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """Process a batch of notifications"""
    from src.workers.notification_worker import process_batch_notifications as batch_task

    notifications = data.get('notifications')
    batch_interval = data.get('batch_interval_minutes', 60)

    if not notifications:
        raise HTTPException(status_code=400, detail="notifications are required")

    # Queue batch processing task
    task = batch_task.apply_async(
        args=[notifications, batch_interval]
    )

    return {
        'success': True,
        'task_id': task.id,
        'batch_size': len(notifications),
        'message': 'Batch processing queued'
    }


@app.post("/api/digest/send")
async def send_digest(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """Send notification digest for user"""
    from src.workers.notification_worker import send_user_digest

    period = data.get('period', 'daily')
    repository_id = data.get('repository_id')

    if period not in ['daily', 'weekly']:
        raise HTTPException(status_code=400, detail="period must be 'daily' or 'weekly'")

    # Queue digest sending
    task = send_user_digest.apply_async(
        args=[user.id, period, repository_id]
    )

    return {
        'success': True,
        'task_id': task.id,
        'period': period,
        'message': f'{period.capitalize()} digest queued for sending'
    }


@app.get("/api/digest/preview")
async def preview_digest(
    period: str = 'daily',
    repository_id: Optional[str] = None,
    user = Depends(get_current_user)
):
    """Preview digest data without sending"""
    from src.services.notification_digest_service import get_digest_service

    if period not in ['daily', 'weekly']:
        raise HTTPException(status_code=400, detail="period must be 'daily' or 'weekly'")

    digest_service = get_digest_service()
    digest_data = digest_service.aggregate_notifications(
        user_id=user.id,
        period=period,
        repository_id=repository_id
    )

    return {
        'success': True,
        'digest': digest_data
    }


@app.post("/api/digest/test")
async def test_digest(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """Send a test digest"""
    from src.services.notification_digest_service import get_digest_service

    channel = data.get('channel', 'email')
    period = data.get('period', 'daily')
    repository_id = data.get('repository_id')

    if channel not in ['email', 'slack', 'discord']:
        raise HTTPException(status_code=400, detail="channel must be 'email', 'slack', or 'discord'")

    if period not in ['daily', 'weekly']:
        raise HTTPException(status_code=400, detail="period must be 'daily' or 'weekly'")

    digest_service = get_digest_service()

    if channel == 'email':
        result = digest_service.create_email_digest(
            user_id=user.id,
            period=period,
            repository_id=repository_id
        )
    elif channel == 'slack':
        result = digest_service.create_slack_digest(
            user_id=user.id,
            period=period,
            repository_id=repository_id
        )
    else:  # discord
        result = digest_service.create_discord_digest(
            user_id=user.id,
            period=period,
            repository_id=repository_id
        )

    return result


# ============================================================================
# Pull Request Routes
# ============================================================================

@app.post("/api/prs/import")
async def import_pull_request(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """Import a pull request from GitHub"""
    repository_id = data.get('repository_id')
    pr_number = data.get('pr_number')

    if not repository_id or not pr_number:
        raise HTTPException(
            status_code=400,
            detail="repository_id and pr_number are required"
        )

    # Get user's GitHub token
    with db_manager.get_session() as db:
        db_user = db.query(User).filter(User.id == user.id).first()

        if not db_user.github_token:
            raise HTTPException(
                status_code=400,
                detail="GitHub token not configured. Please set your GitHub token first."
            )

        # Verify user owns the repository
        repo = db.query(Repository).filter(
            Repository.id == repository_id,
            Repository.user_id == user.id
        ).first()

        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Import PR
        pr_service = PullRequestService(db)
        success, pr, error = pr_service.import_from_github(
            repository_id=repository_id,
            pr_number=pr_number,
            github_token=db_user.github_token
        )

        if not success:
            raise HTTPException(status_code=400, detail=error)

        return {
            "success": True,
            "message": "Pull request imported successfully",
            "pull_request": pr.to_dict()
        }


@app.get("/api/prs")
async def list_pull_requests(
    repository_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user = Depends(get_current_user)
):
    """List pull requests"""
    with db_manager.get_session() as db:
        # Parse status if provided
        pr_status = None
        if status:
            try:
                pr_status = PRStatus(status)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        pr_service = PullRequestService(db)
        success, prs, error = pr_service.list_prs(
            repository_id=repository_id,
            user_id=user.id,
            status=pr_status,
            limit=limit,
            offset=offset
        )

        if not success:
            raise HTTPException(status_code=400, detail=error)

        return {
            "success": True,
            "pull_requests": [pr.to_dict() for pr in prs],
            "count": len(prs)
        }


@app.get("/api/prs/{pr_id}")
async def get_pull_request(
    pr_id: str,
    user = Depends(get_current_user)
):
    """Get pull request details"""
    with db_manager.get_session() as db:
        pr_service = PullRequestService(db)
        success, pr, error = pr_service.get_pr(pr_id, user_id=user.id)

        if not success:
            raise HTTPException(status_code=404, detail=error)

        return {
            "success": True,
            "pull_request": pr.to_dict()
        }


@app.put("/api/prs/{pr_id}/status")
async def update_pull_request_status(
    pr_id: str,
    data: Dict[str, str],
    user = Depends(get_current_user)
):
    """Update pull request status"""
    status_str = data.get('status')

    if not status_str:
        raise HTTPException(status_code=400, detail="status is required")

    try:
        status = PRStatus(status_str)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status_str}")

    with db_manager.get_session() as db:
        # Verify user owns the PR's repository
        pr_service = PullRequestService(db)
        success, pr, error = pr_service.get_pr(pr_id, user_id=user.id)

        if not success:
            raise HTTPException(status_code=404, detail=error)

        # Update status
        success, error = pr_service.update_status(pr_id, status)

        if not success:
            raise HTTPException(status_code=400, detail=error)

        return {
            "success": True,
            "message": "Pull request status updated"
        }


@app.delete("/api/prs/{pr_id}")
async def delete_pull_request(
    pr_id: str,
    user = Depends(get_current_user)
):
    """Delete a pull request"""
    with db_manager.get_session() as db:
        pr_service = PullRequestService(db)
        success, error = pr_service.delete_pr(pr_id, user_id=user.id)

        if not success:
            raise HTTPException(status_code=404, detail=error)

        return {
            "success": True,
            "message": "Pull request deleted"
        }


@app.post("/api/prs/{pr_id}/sync")
async def sync_pull_request(
    pr_id: str,
    user = Depends(get_current_user)
):
    """Sync pull request with latest data from GitHub"""
    with db_manager.get_session() as db:
        db_user = db.query(User).filter(User.id == user.id).first()

        if not db_user.github_token:
            raise HTTPException(
                status_code=400,
                detail="GitHub token not configured"
            )

        # Get PR
        pr_service = PullRequestService(db)
        success, pr, error = pr_service.get_pr(pr_id, user_id=user.id)

        if not success:
            raise HTTPException(status_code=404, detail=error)

        # Update from GitHub
        success, updated_pr, error = pr_service._update_from_github(
            pr,
            db_user.github_token
        )

        if not success:
            raise HTTPException(status_code=400, detail=error)

        return {
            "success": True,
            "message": "Pull request synced successfully",
            "pull_request": updated_pr.to_dict()
        }


@app.post("/api/prs/{pr_id}/analyze")
async def analyze_pull_request(
    pr_id: str,
    user = Depends(get_current_user)
):
    """Start async analysis of a pull request"""
    with db_manager.get_session() as db:
        # Get user's GitHub token
        db_user = db.query(User).filter(User.id == user.id).first()

        if not db_user.github_token:
            raise HTTPException(
                status_code=400,
                detail="GitHub token not configured"
            )

        # Verify user owns the PR's repository
        pr_service = PullRequestService(db)
        success, pr, error = pr_service.get_pr(pr_id, user_id=user.id)

        if not success:
            raise HTTPException(status_code=404, detail=error)

        # Start async analysis task
        task = analyze_pr_task.delay(pr_id, db_user.github_token)

        return {
            "success": True,
            "message": "Pull request analysis started",
            "job_id": task.id,
            "pr_id": pr_id
        }


@app.get("/api/prs/{pr_id}/analysis/status")
async def get_pr_analysis_status(
    pr_id: str,
    job_id: Optional[str] = None,
    user = Depends(get_current_user)
):
    """Get PR analysis job status"""
    with db_manager.get_session() as db:
        # Verify user owns the PR
        pr_service = PullRequestService(db)
        success, pr, error = pr_service.get_pr(pr_id, user_id=user.id)

        if not success:
            raise HTTPException(status_code=404, detail=error)

        # Get PR data
        pr_data = pr.to_dict()

        # If job_id provided, get task status
        if job_id:
            task = AsyncResult(job_id)

            task_info = {
                'state': task.state,
                'info': task.info if task.info else {}
            }

            if task.state == 'SUCCESS':
                task_info['result'] = task.result

            pr_data['analysis_job'] = task_info

        return {
            "success": True,
            "pull_request": pr_data
        }


@app.get("/api/prs/{pr_id}/diff")
async def get_pr_diff(
    pr_id: str,
    analyze: bool = False,
    user = Depends(get_current_user)
):
    """
    Get diff for a pull request.

    Args:
        pr_id: Pull request ID
        analyze: Whether to analyze the diff (default: False)
    """
    with db_manager.get_session() as db:
        # Get PR
        pr_service = PullRequestService(db)
        success, pr, error = pr_service.get_pr(pr_id, user_id=user.id)

        if not success:
            raise HTTPException(status_code=404, detail=error)

        # Get repository
        repository = pr.repository

        # Get user's GitHub token
        db_user = db.query(User).filter(User.id == user.id).first()

        if not db_user or not db_user.github_token:
            raise HTTPException(
                status_code=400,
                detail="GitHub token not configured. Please configure it in settings."
            )

        # Fetch diff from GitHub
        from src.services.github_service import GitHubService

        github_service = GitHubService(github_token=db_user.github_token)
        success, diff_text, error = github_service.get_pull_request_diff(
            repository.github_url,
            pr.pr_number
        )
        github_service.close()

        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to fetch diff: {error}")

        response = {
            "success": True,
            "pr_id": pr_id,
            "pr_number": pr.pr_number,
            "diff": diff_text
        }

        # Optionally analyze the diff
        if analyze:
            from src.services.diff_analyzer_service import DiffAnalyzerService

            diff_analyzer = DiffAnalyzerService()
            success, analysis, error = diff_analyzer.analyze_pr_diff(
                diff_text,
                language='python'
            )

            if success:
                response['analysis'] = analysis
            else:
                response['analysis_error'] = error

        return response


@app.get("/api/prs/{pr_id}/files")
async def get_pr_files(
    pr_id: str,
    user = Depends(get_current_user)
):
    """Get list of files changed in a pull request."""
    with db_manager.get_session() as db:
        # Get PR
        pr_service = PullRequestService(db)
        success, pr, error = pr_service.get_pr(pr_id, user_id=user.id)

        if not success:
            raise HTTPException(status_code=404, detail=error)

        # Get repository
        repository = pr.repository

        # Get user's GitHub token
        db_user = db.query(User).filter(User.id == user.id).first()

        if not db_user or not db_user.github_token:
            raise HTTPException(
                status_code=400,
                detail="GitHub token not configured"
            )

        # Fetch files from GitHub
        from src.services.github_service import GitHubService

        github_service = GitHubService(github_token=db_user.github_token)
        success, files_info, error = github_service.get_pull_request_files(
            repository.github_url,
            pr.pr_number
        )
        github_service.close()

        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to fetch files: {error}")

        return {
            "success": True,
            "pr_id": pr_id,
            "files": files_info
        }


@app.post("/api/prs/{pr_id}/review/post")
async def post_pr_review_to_github(
    pr_id: str,
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """
    Post review to GitHub PR.

    Args:
        pr_id: Pull request ID
        data: {
            "review_id": Optional review ID to post,
            "event": "APPROVE" | "REQUEST_CHANGES" | "COMMENT",
            "body": Optional review body
        }
    """
    with db_manager.get_session() as db:
        # Get PR
        pr_service = PullRequestService(db)
        success, pr, error = pr_service.get_pr(pr_id, user_id=user.id)

        if not success:
            raise HTTPException(status_code=404, detail=error)

        # Get repository
        repository = pr.repository

        # Get user's GitHub token
        db_user = db.query(User).filter(User.id == user.id).first()

        if not db_user or not db_user.github_token:
            raise HTTPException(
                status_code=400,
                detail="GitHub token not configured"
            )

        # Get review if review_id provided
        review_id = data.get('review_id')
        event = data.get('event', 'COMMENT')
        body = data.get('body')

        comments = []
        summary = body

        if review_id:
            # Get review from database
            from src.services.review_service import ReviewService

            review_service = ReviewService(db)
            success, review, error = review_service.get_review(review_id)

            if not success:
                raise HTTPException(status_code=404, detail="Review not found")

            # Get review comments
            success, db_comments, error = review_service.get_review_comments(review_id)

            if success:
                # Format comments for GitHub
                comments = [
                    {
                        'file_path': c.file_path,
                        'line_number': c.line_number,
                        'comment_text': c.comment_text
                    }
                    for c in db_comments
                ]

            # Use review summary as body if not provided
            if not summary:
                summary = review.summary

        # Post to GitHub
        from src.services.github_service import GitHubService

        github_service = GitHubService(github_token=db_user.github_token)
        success, error = github_service.create_pr_review(
            repository.github_url,
            pr.pr_number,
            event=event,
            body=summary,
            comments=comments if comments else None
        )
        github_service.close()

        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to post review: {error}")

        return {
            "success": True,
            "message": "Review posted to GitHub successfully",
            "pr_id": pr_id,
            "event": event
        }


@app.post("/api/prs/{pr_id}/assign-reviewers")
async def assign_pr_reviewers(
    pr_id: str,
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """
    Automatically assign reviewers to a pull request.

    Args:
        pr_id: Pull request ID
        data: {
            "strategy": "balanced" | "expertise" | "round_robin",
            "num_reviewers": int (default 2)
        }
    """
    try:
        from src.services.review_assignment_service import review_assignment_service

        strategy = data.get('strategy', 'balanced')
        num_reviewers = data.get('num_reviewers', 2)

        result = review_assignment_service.assign_reviewers(
            pr_id=pr_id,
            strategy=strategy,
            num_reviewers=num_reviewers
        )

        if not result.get('success'):
            raise HTTPException(status_code=400, detail=result.get('error'))

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to assign reviewers: {str(e)}")


@app.get("/api/prs/{pr_id}/approval-status")
async def get_pr_approval_status(
    pr_id: str,
    required_approvals: int = 1,
    require_owner_approval: bool = False,
    user = Depends(get_current_user)
):
    """
    Check if PR has sufficient approvals for merge.

    Args:
        pr_id: Pull request ID
        required_approvals: Minimum number of approvals required
        require_owner_approval: Whether code owner approval is required
    """
    try:
        from src.services.review_assignment_service import review_assignment_service

        result = review_assignment_service.check_review_approval(
            pr_id=pr_id,
            required_approvals=required_approvals,
            require_owner_approval=require_owner_approval
        )

        if not result.get('success'):
            raise HTTPException(status_code=404, detail=result.get('error'))

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to check approval status: {str(e)}")


@app.get("/api/users/{user_id}/reviewer-stats")
async def get_user_reviewer_stats(
    user_id: str,
    days: int = 30,
    user = Depends(get_current_user)
):
    """
    Get review statistics for a user.

    Args:
        user_id: User ID
        days: Number of days to analyze (default 30)
    """
    try:
        from src.services.review_assignment_service import review_assignment_service

        stats = review_assignment_service.get_reviewer_stats(
            user_id=user_id,
            days=days
        )

        return stats

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get reviewer stats: {str(e)}")


# ============================================================================
# Template Routes
# ============================================================================

# Optional dependency for template routes
async def get_current_user_optional(session_token: Optional[str] = Cookie(None)):
    """Get current user if authenticated, None otherwise"""
    if not session_token:
        return None

    try:
        with db_manager.get_session() as db:
            auth_manager = AuthManager(db, SESSION_TTL_DAYS)
            success, user, error = auth_manager.validate_session(session_token)
            return user if success else None
    except:
        return None


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root endpoint - redirect to dashboard"""
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, user = Depends(get_current_user_optional)):
    """Dashboard page showing recent analyses"""
    if not user:
        return RedirectResponse(url="/login")

    # Get recent analyses
    recent_analyses = get_all_cached_analyses()[:5]

    # Get repositories from database
    with db_manager.get_session() as db:
        # Get recent repositories for display
        repositories = db.query(Repository).filter(
            Repository.user_id == user.id
        ).order_by(Repository.created_at.desc()).limit(5).all()

        # Get total count
        total_repositories = db.query(Repository).filter(
            Repository.user_id == user.id
        ).count()

    # Calculate stats
    stats = {
        'repositories': total_repositories,
        'pull_requests': 0,
        'issues': sum(len(a.get('issues', [])) for a in get_all_cached_analyses()),
        'reviews': 0
    }

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "stats": stats,
        "repositories": repositories,
        "pull_requests": [],
        "issues": [issue for a in recent_analyses for issue in a.get('issues', [])][:10]
    })


@app.get("/analyze", response_class=HTMLResponse)
async def analyze_page(request: Request, user = Depends(get_current_user_optional)):
    """File analysis page"""
    if not user:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse("analyze.html", {
        "request": request,
        "user": user
    })


@app.get("/notifications", response_class=HTMLResponse)
async def notifications_page(request: Request, user = Depends(get_current_user_optional)):
    """Notification center page"""
    if not user:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse("notifications.html", {
        "request": request,
        "user": user
    })


@app.get("/notifications/preferences", response_class=HTMLResponse)
async def notification_preferences_page(request: Request, user = Depends(get_current_user_optional)):
    """Notification preferences page"""
    if not user:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse("notification_preferences.html", {
        "request": request,
        "user": user
    })


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, user = Depends(get_current_user_optional)):
    """Settings and configuration page"""
    if not user:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse("settings.html", {
        "request": request,
        "user": user
    })


@app.get("/settings/github-app", response_class=HTMLResponse)
async def github_app_page(request: Request, user = Depends(get_current_user_optional)):
    """GitHub App configuration page"""
    if not user:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse("github-app.html", {
        "request": request,
        "user": user
    })


@app.get("/api/settings")
async def get_user_settings(user = Depends(get_current_user)):
    """Get user settings"""
    # For now, return empty dict (settings are stored in localStorage)
    # In a production app, you'd store these in the database
    return JSONResponse({})


@app.post("/api/settings")
async def save_user_settings(request: Request, user = Depends(get_current_user)):
    """Save user settings"""
    try:
        settings = await request.json()

        # For now, just acknowledge receipt
        # In a production app, you'd save these to the database
        # with db_manager.get_session() as db:
        #     db_user = db.query(User).filter(User.id == user.id).first()
        #     db_user.settings_json = json.dumps(settings)
        #     db.commit()

        return JSONResponse({
            "success": True,
            "message": "Settings saved successfully"
        })
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/issues", response_class=HTMLResponse)
async def issues_page(request: Request, user = Depends(get_current_user_optional)):
    """Issues list page"""
    if not user:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse("issues.html", {
        "request": request,
        "user": user
    })


@app.get("/issues/{issue_id}", response_class=HTMLResponse)
async def issue_detail_page(request: Request, issue_id: str, user = Depends(get_current_user_optional)):
    """Issue detail page"""
    if not user:
        return RedirectResponse(url="/login")

    with db_manager.get_session() as db:
        # Get the issue
        issue = db.query(Issue).filter(Issue.id == issue_id).first()

        if not issue:
            raise HTTPException(status_code=404, detail="Issue not found")

        # Get code file information
        code_file = db.query(CodeFile).filter(CodeFile.id == issue.code_file_id).first()

        # Verify user has access to this issue (through repository ownership)
        if code_file:
            pr = db.query(PullRequest).filter(PullRequest.id == code_file.pull_request_id).first()
            if pr:
                repo = db.query(Repository).filter(Repository.id == pr.repository_id).first()
                if repo and repo.user_id != user.id:
                    raise HTTPException(status_code=403, detail="Access denied")

        # Get refactoring suggestion if exists
        refactoring = db.query(Refactoring).filter(Refactoring.issue_id == issue_id).first()

        # Get related issues in the same file
        related_issues = []
        if code_file:
            related_issues = db.query(Issue).filter(
                Issue.code_file_id == code_file.id,
                Issue.id != issue_id
            ).limit(5).all()

        # Convert to dict for template
        issue_dict = {
            'id': issue.id,
            'category': issue.category,
            'severity': issue.severity,
            'rule_id': issue.rule_id,
            'title': issue.title,
            'description': issue.description,
            'line_number': issue.line_number,
            'code_snippet': issue.code_snippet,
            'file_path': code_file.file_path if code_file else 'Unknown',
            'language': code_file.language if code_file else 'python',
            'ai_explanation': issue.ai_explanation,
            'fix_suggestion': None,
            'refactoring': None
        }

        # Add fix suggestion if available
        if issue.fix_suggestion:
            issue_dict['fix_suggestion'] = {
                'suggested_fix': issue.fix_suggestion,
                'confidence_score': issue.fix_confidence or 0.0,
                'can_auto_apply': issue.can_auto_apply or False
            }

        # Add refactoring if available
        if refactoring:
            issue_dict['refactoring'] = {
                'id': refactoring.id,
                'refactoring_type': refactoring.refactoring_type,
                'explanation': refactoring.explanation,
                'confidence': refactoring.confidence,
                'original_code': refactoring.original_code,
                'refactored_code': refactoring.refactored_code,
                'diff': refactoring.diff,
                'status': refactoring.status.value
            }

        # Convert related issues to dict
        related_issues_dict = []
        for rel_issue in related_issues:
            related_issues_dict.append({
                'id': rel_issue.id,
                'severity': rel_issue.severity,
                'title': rel_issue.title,
                'line_number': rel_issue.line_number
            })

        return templates.TemplateResponse("issue_detail.html", {
            "request": request,
            "user": user,
            "issue": issue_dict,
            "related_issues": related_issues_dict
        })


@app.get("/demo/diff-viewer", response_class=HTMLResponse)
async def diff_viewer_demo_page(request: Request, user = Depends(get_current_user_optional)):
    """Diff viewer component demo page"""
    if not user:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse("diff_viewer_demo.html", {
        "request": request,
        "user": user
    })


@app.get("/demo/advanced-filters", response_class=HTMLResponse)
async def advanced_filters_demo_page(request: Request, user = Depends(get_current_user_optional)):
    """Advanced filters component demo page"""
    if not user:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse("advanced_filters_demo.html", {
        "request": request,
        "user": user
    })


@app.get("/repositories", response_class=HTMLResponse)
async def repositories_page(request: Request, user = Depends(get_current_user_optional)):
    """Repositories list page"""
    if not user:
        return RedirectResponse(url="/login")

    # Calculate repository statistics
    with db_manager.get_session() as db:
        repos = db.query(Repository).filter(Repository.user_id == user.id).all()
        stats = {
            'total': len(repos),
            'ready': sum(1 for r in repos if r.status == RepositoryStatus.READY),
            'pending': sum(1 for r in repos if r.status == RepositoryStatus.PENDING),
            'error': sum(1 for r in repos if r.status == RepositoryStatus.ERROR)
        }

    return templates.TemplateResponse("repositories.html", {
        "request": request,
        "user": user,
        "stats": stats
    })


@app.get("/schedules", response_class=HTMLResponse)
async def schedules_page(request: Request, user = Depends(get_current_user_optional)):
    """Scheduled analysis page"""
    if not user:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse("schedules.html", {
        "request": request,
        "user": user
    })


@app.get("/teams", response_class=HTMLResponse)
async def teams_page(request: Request, user = Depends(get_current_user_optional)):
    """Team dashboard page"""
    if not user:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse("team_dashboard.html", {
        "request": request,
        "user": user
    })


@app.get("/repositories/new", response_class=HTMLResponse)
async def repository_add_page(request: Request, user = Depends(get_current_user_optional)):
    """Add repository page"""
    if not user:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse("repository_add.html", {
        "request": request,
        "user": user
    })


@app.get("/repositories/{repository_id}", response_class=HTMLResponse)
async def repository_detail_page(
    request: Request,
    repository_id: str,
    user = Depends(get_current_user_optional)
):
    """Repository detail page"""
    if not user:
        return RedirectResponse(url="/login")

    with db_manager.get_session() as db:
        repository = db.query(Repository).filter(
            Repository.id == repository_id,
            Repository.user_id == user.id
        ).first()

        if not repository:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Get repository statistics (will be implemented in PR phase)
        stats = {
            'pull_requests_count': 0,
            'total_issues': 0,
            'reviews_count': 0,
            'health_score': None
        }

        return templates.TemplateResponse("repository_detail.html", {
            "request": request,
            "user": user,
            "repository": repository,
            "stats": stats
        })


@app.get("/pull-requests", response_class=HTMLResponse)
async def pull_requests_page(request: Request, user = Depends(get_current_user_optional)):
    """Pull requests list page"""
    if not user:
        return RedirectResponse(url="/login")

    with db_manager.get_session() as db:
        # Get user's repositories for filter dropdown
        repositories = db.query(Repository).filter(
            Repository.user_id == user.id
        ).order_by(Repository.name).all()

        # Get user's pull requests
        pr_service = PullRequestService(db)

        # Get filter parameters from query string
        repository_id = request.query_params.get('repository_id')
        status = request.query_params.get('status')

        # Build filters
        filters = {'user_id': user.id}
        if repository_id:
            filters['repository_id'] = repository_id
        if status:
            try:
                filters['status'] = PRStatus[status.upper()]
            except KeyError:
                pass  # Invalid status, ignore

        success, pull_requests, error = pr_service.list_prs(**filters)

        if not success:
            pull_requests = []

    return templates.TemplateResponse("pull_requests.html", {
        "request": request,
        "user": user,
        "repositories": repositories,
        "pull_requests": pull_requests,
        "selected_repository": repository_id,
        "selected_status": status
    })


@app.get("/pull-requests/import", response_class=HTMLResponse)
async def pull_request_import_page(request: Request, user = Depends(get_current_user_optional)):
    """Pull request import page"""
    if not user:
        return RedirectResponse(url="/login")

    with db_manager.get_session() as db:
        # Get user's repositories for dropdown
        repositories = db.query(Repository).filter(
            Repository.user_id == user.id,
            Repository.status == RepositoryStatus.READY
        ).order_by(Repository.name).all()

    return templates.TemplateResponse("pull_request_import.html", {
        "request": request,
        "user": user,
        "repositories": repositories
    })


@app.get("/pull-requests/{pr_id}", response_class=HTMLResponse)
async def pull_request_detail_page(
    request: Request,
    pr_id: str,
    user = Depends(get_current_user_optional)
):
    """Pull request detail page"""
    if not user:
        return RedirectResponse(url="/login")

    with db_manager.get_session() as db:
        # Get PR
        pr_service = PullRequestService(db)
        success, pr, error = pr_service.get_pr(pr_id, user_id=user.id)

        if not success:
            raise HTTPException(status_code=404, detail="Pull request not found")

        # Get analyzed files
        code_files = db.query(CodeFile).filter(
            CodeFile.pull_request_id == pr_id
        ).order_by(CodeFile.file_path).all()

        # Get analysis job status if PR is analyzing
        analysis_job = None
        job_id = request.query_params.get('job_id')

        if job_id:
            try:
                task_result = AsyncResult(job_id, app=celery_app)
                analysis_job = {
                    'id': job_id,
                    'state': task_result.state,
                    'info': task_result.info if task_result.info else {}
                }
            except Exception as e:
                print(f"Error fetching job status: {e}")

        # Calculate stats
        total_issues = sum(1 for f in code_files if f.last_analyzed_at)

        return templates.TemplateResponse("pull_request_detail.html", {
            "request": request,
            "user": user,
            "pr": pr,
            "repository": pr.repository,
            "code_files": code_files,
            "analysis_job": analysis_job,
            "total_issues": total_issues
        })


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page"""
    return templates.TemplateResponse("login.html", {
        "request": request
    })


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Registration page"""
    return templates.TemplateResponse("register.html", {
        "request": request
    })


@app.get("/terms", response_class=HTMLResponse)
async def terms_page(request: Request):
    """Terms of Service page"""
    return templates.TemplateResponse("terms.html", {
        "request": request
    })


@app.get("/privacy", response_class=HTMLResponse)
async def privacy_page(request: Request):
    """Privacy Policy page"""
    return templates.TemplateResponse("privacy.html", {
        "request": request
    })


@app.get("/logout", response_class=HTMLResponse)
async def logout_page(response: Response, session_token: Optional[str] = Cookie(None)):
    """Logout page - clears session and redirects"""
    if session_token:
        with db_manager.get_session() as db:
            auth_manager = AuthManager(db, SESSION_TTL_DAYS)
            auth_manager.delete_session(session_token)

    response = RedirectResponse(url="/login")
    response.delete_cookie(key="session_token")
    return response


@app.get("/rules/builder", response_class=HTMLResponse)
async def rule_builder_page(request: Request, user = Depends(get_current_user_optional)):
    """Rule builder page - visual custom rule editor"""
    if not user:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse("rule_builder.html", {
        "request": request,
        "user": user
    })


@app.get("/plugins", response_class=HTMLResponse)
async def plugins_page(request: Request, user = Depends(get_current_user_optional)):
    """Plugin management page"""
    if not user:
        return RedirectResponse(url="/login")

    return templates.TemplateResponse("plugins.html", {
        "request": request,
        "user": user
    })


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "code-review-assistant"}


# ============================================================================
# Analysis Endpoints
# ============================================================================

class AnalyzeFileRequest(BaseModel):
    """Request model for file analysis"""
    code: str
    filename: str = "code.py"
    analyzer_ids: Optional[List[str]] = None


@app.post("/api/analyze/file")
async def analyze_file(
    file: UploadFile = File(...),
    analyzer_ids: Optional[str] = Form(None),
    user = Depends(get_current_user)
):
    """
    Upload and analyze a Python file.

    Returns a job ID that can be used to check analysis status.
    """
    # Validate file type
    if not file.filename.endswith('.py'):
        raise HTTPException(status_code=400, detail="Only Python files (.py) are supported")

    # Read file content
    try:
        content = await file.read()
        file_content = content.decode('utf-8')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {str(e)}")

    # Parse analyzer IDs if provided
    analyzer_list = None
    if analyzer_ids:
        analyzer_list = [a.strip() for a in analyzer_ids.split(',')]

    # Queue async analysis task
    task = analyze_file_task.delay(
        file_content=file_content,
        filename=file.filename,
        analyzer_ids=analyzer_list
    )

    return {
        "success": True,
        "job_id": task.id,
        "filename": file.filename,
        "message": "Analysis queued successfully"
    }


@app.post("/api/analyze/code")
async def analyze_code(
    data: AnalyzeFileRequest,
    user = Depends(get_current_user)
):
    """
    Analyze Python code directly (without file upload).

    For synchronous analysis, use this endpoint for quick results.
    """
    # Create analyzer service
    service = CodeAnalyzerService()

    # Analyze synchronously
    result = service.analyze_code(
        source_code=data.code,
        file_path=data.filename,
        analyzer_ids=data.analyzer_ids
    )

    if not result['success']:
        raise HTTPException(status_code=400, detail=result.get('error', 'Analysis failed'))

    return result


@app.get("/api/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    user = Depends(get_current_user)
):
    """
    Get status and results of an analysis job.

    Job states:
    - PENDING: Task waiting to be executed
    - PROCESSING: Task is running
    - SUCCESS: Task completed successfully
    - FAILURE: Task failed
    """
    task = AsyncResult(job_id, app=celery_app)

    if task.state == 'PENDING':
        return {
            "job_id": job_id,
            "state": "PENDING",
            "status": "Task is waiting in queue"
        }
    elif task.state == 'PROCESSING':
        return {
            "job_id": job_id,
            "state": "PROCESSING",
            "status": task.info.get('status', 'Processing...'),
            "progress": task.info
        }
    elif task.state == 'SUCCESS':
        result = task.result
        return {
            "job_id": job_id,
            "state": "SUCCESS",
            "result": result
        }
    elif task.state == 'FAILURE':
        return {
            "job_id": job_id,
            "state": "FAILURE",
            "error": str(task.info)
        }
    else:
        return {
            "job_id": job_id,
            "state": task.state,
            "info": str(task.info)
        }


@app.get("/api/tasks/{task_id}/status")
async def get_task_status(
    task_id: str,
    user = Depends(get_current_user)
):
    """
    Get the current status of a task (for polling).
    Returns progress information in a simple format.
    """
    task = AsyncResult(task_id, app=celery_app)

    response = {
        "task_id": task_id,
        "status": task.state.lower(),
        "progress": 0
    }

    if task.state == 'PENDING':
        response["message"] = "Task is pending..."
    elif task.state == 'PROCESSING' or task.state == 'STARTED':
        info = task.info or {}
        response["status"] = "in_progress"
        response["progress"] = info.get('progress', 0)
        response["message"] = info.get('message', 'Processing...')
        response["current"] = info.get('current', 0)
        response["total"] = info.get('total', 0)
    elif task.state == 'SUCCESS':
        response["status"] = "completed"
        response["progress"] = 100
        response["message"] = "Task completed successfully"
        response["result"] = task.result
    elif task.state == 'FAILURE':
        response["status"] = "failed"
        response["error"] = str(task.info)
        response["message"] = "Task failed"

    return response


@app.get("/api/tasks/{task_id}/progress")
async def task_progress_stream(
    task_id: str,
    user = Depends(get_current_user)
):
    """
    Server-Sent Events endpoint for real-time task progress updates.
    Streams progress events until the task completes or fails.
    """
    import asyncio
    import json

    async def event_generator():
        task = AsyncResult(task_id, app=celery_app)

        while True:
            # Get current task state
            state = task.state

            if state == 'PENDING':
                data = {
                    "status": "pending",
                    "progress": 0,
                    "message": "Task is pending..."
                }
                yield f"data: {json.dumps(data)}\n\n"

            elif state == 'PROCESSING' or state == 'STARTED':
                info = task.info or {}
                data = {
                    "status": "in_progress",
                    "progress": info.get('progress', 0),
                    "message": info.get('message', 'Processing...'),
                    "current": info.get('current', 0),
                    "total": info.get('total', 0)
                }
                yield f"event: progress\ndata: {json.dumps(data)}\n\n"

            elif state == 'SUCCESS':
                data = {
                    "status": "completed",
                    "progress": 100,
                    "message": "Task completed successfully",
                    "result": task.result
                }
                yield f"event: complete\ndata: {json.dumps(data)}\n\n"
                break

            elif state == 'FAILURE':
                data = {
                    "status": "failed",
                    "error": str(task.info),
                    "message": "Task failed"
                }
                yield f"event: error\ndata: {json.dumps(data)}\n\n"
                break

            # Wait before checking again
            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )


# ============================================================================
# Dashboard Endpoints
# ============================================================================

@app.get("/api/dashboard/metrics")
async def get_dashboard_metrics(user = Depends(get_current_user)):
    """
    Get overall dashboard metrics and statistics.

    Returns:
    - total_issues: Total number of issues across all analyses
    - issues_by_severity: Breakdown by critical/error/warning/info
    - total_repositories: Number of repositories (estimate)
    - total_lines_of_code: Total LOC analyzed
    - avg_complexity: Average cyclomatic complexity
    - test_coverage: Estimated test coverage (placeholder)
    """
    all_issues = []
    total_loc = 0
    complexity_scores = []

    # Get all cached analyses
    analyses = get_all_cached_analyses()

    # Collect metrics from all analyses
    for analysis in analyses:
        issues = analysis.get('issues', [])
        all_issues.extend(issues)

        # Extract LOC if available
        metadata = analysis.get('metadata', {})
        loc = metadata.get('lines_of_code', 0)
        total_loc += loc

        # Extract complexity metrics
        for issue in issues:
            if issue.get('category') == 'complexity':
                # Try to extract complexity value from description
                desc = issue.get('description', '')
                if 'complexity' in desc.lower():
                    try:
                        # Extract number from description
                        import re
                        match = re.search(r'(\d+)', desc)
                        if match:
                            complexity_scores.append(int(match.group(1)))
                    except:
                        pass

    # Count issues by severity
    severity_counts = {
        'critical': 0,
        'error': 0,
        'warning': 0,
        'info': 0
    }

    for issue in all_issues:
        severity = issue.get('severity', 'info').lower()
        if severity in severity_counts:
            severity_counts[severity] += 1

    # Calculate average complexity
    avg_complexity = sum(complexity_scores) / len(complexity_scores) if complexity_scores else 0

    # Estimate repositories (count unique source filenames)
    unique_sources = set()
    for analysis in analyses:
        filename = analysis.get('filename', '')
        if filename:
            # Extract potential repo name from path
            parts = filename.split('/')
            if len(parts) > 2:
                unique_sources.add('/'.join(parts[:3]))
            else:
                unique_sources.add(filename)

    return JSONResponse({
        "total_issues": len(all_issues),
        "critical_issues": severity_counts['critical'],
        "error_issues": severity_counts['error'],
        "warning_issues": severity_counts['warning'],
        "info_issues": severity_counts['info'],
        "total_repositories": len(unique_sources) if unique_sources else 1,
        "total_lines_of_code": total_loc,
        "avg_complexity": round(avg_complexity, 2),
        "test_coverage": 75.0  # Placeholder - would need actual test analysis
    })


@app.get("/api/dashboard/trends")
async def get_dashboard_trends(days: int = 30, user = Depends(get_current_user)):
    """
    Get issue trends over time.

    Query parameters:
    - days: Number of days to include in trends (default 30)

    Returns array of:
    - date: ISO date string
    - critical: Count of critical issues
    - error: Count of error issues
    - warning: Count of warning issues
    - info: Count of info issues
    """
    from datetime import datetime, timedelta

    # Get all cached analyses
    analyses = get_all_cached_analyses()

    # Create date buckets
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    # Initialize daily counts
    daily_counts = {}
    current_date = start_date
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        daily_counts[date_str] = {
            'critical': 0,
            'error': 0,
            'warning': 0,
            'info': 0
        }
        current_date += timedelta(days=1)

    # Group issues by date
    for analysis in analyses:
        analyzed_at = analysis.get('analyzed_at')
        if not analyzed_at:
            continue

        try:
            # Parse analyzed_at timestamp
            if isinstance(analyzed_at, str):
                analysis_date = datetime.fromisoformat(analyzed_at.replace('Z', '+00:00'))
            else:
                analysis_date = analyzed_at

            # Check if within range
            if start_date <= analysis_date <= end_date:
                date_str = analysis_date.strftime('%Y-%m-%d')

                # Count issues by severity
                for issue in analysis.get('issues', []):
                    severity = issue.get('severity', 'info').lower()
                    if severity in daily_counts[date_str]:
                        daily_counts[date_str][severity] += 1
        except:
            continue

    # Convert to array format
    trends = [
        {
            'date': date_str,
            'critical': counts['critical'],
            'error': counts['error'],
            'warning': counts['warning'],
            'info': counts['info']
        }
        for date_str, counts in sorted(daily_counts.items())
    ]

    return JSONResponse(trends)


@app.get("/api/dashboard/activity")
async def get_recent_activity(limit: int = 10, user = Depends(get_current_user)):
    """
    Get recent activity feed.

    Query parameters:
    - limit: Maximum number of activities to return (default 10)

    Returns array of activity objects with:
    - type: Activity type (analysis, issue_found, etc.)
    - title: Activity title
    - description: Activity description
    - timestamp: ISO timestamp
    - severity: Optional severity for issue-related activities
    """
    from datetime import datetime

    activities = []

    # Get all cached analyses
    analyses = get_all_cached_analyses()

    # Sort by timestamp (most recent first)
    sorted_analyses = sorted(
        analyses,
        key=lambda a: a.get('analyzed_at', ''),
        reverse=True
    )

    # Generate activity items
    for analysis in sorted_analyses[:limit]:
        analyzed_at = analysis.get('analyzed_at', datetime.now().isoformat())
        filename = analysis.get('filename', 'Unknown file')
        issues = analysis.get('issues', [])

        # Add analysis activity
        activities.append({
            'type': 'analysis',
            'title': f'Analyzed {filename}',
            'description': f'Found {len(issues)} issue(s)',
            'timestamp': analyzed_at,
            'icon': '📝'
        })

        # Add critical issue activities
        critical_issues = [i for i in issues if i.get('severity') == 'critical']
        for issue in critical_issues[:2]:  # Limit to 2 per analysis
            activities.append({
                'type': 'issue_found',
                'title': issue.get('title', 'Critical Issue'),
                'description': f"In {filename}: {issue.get('description', '')[:100]}...",
                'timestamp': analyzed_at,
                'severity': 'critical',
                'icon': '🚨'
            })

    # Sort all activities by timestamp and limit
    activities.sort(key=lambda a: a.get('timestamp', ''), reverse=True)

    return JSONResponse(activities[:limit])


# ============================================================================
# Analytics Endpoints
# ============================================================================

@app.get("/api/analytics/health-score")
async def get_health_score(user = Depends(get_current_user)):
    """
    Get comprehensive health score for all analyzed code

    Returns:
    - score: Health score (0-100)
    - grade: Letter grade (A-F)
    - color: Color code for visualization
    - status: Status text
    - severity_counts: Breakdown by severity
    - category_breakdown: Breakdown by category
    """
    from src.services.analytics_service import analytics_service
    from src.services.cache_service import cache_service

    # Check cache first (TTL: 5 minutes)
    cache_key = f"analytics:health_score:{user.id}"
    cached_result = cache_service.get(cache_key)
    if cached_result is not None:
        return JSONResponse(cached_result)

    # Get all cached analyses
    analyses = get_all_cached_analyses()

    # Collect all issues
    all_issues = []
    for analysis in analyses:
        all_issues.extend(analysis.get('issues', []))

    # Calculate health score
    result = analytics_service.calculate_health_score(all_issues)

    # Cache the result (TTL: 300 seconds = 5 minutes)
    cache_service.set(cache_key, result, ttl=300)

    return JSONResponse(result)


@app.get("/api/analytics/trends")
async def get_analytics_trends(
    days: int = 30,
    grouping: str = 'day',
    user = Depends(get_current_user)
):
    """
    Get issue trends over time

    Query parameters:
    - days: Number of days to include (default 30)
    - grouping: 'day', 'week', or 'month' (default 'day')

    Returns array of trend data points with date and issue counts
    """
    from src.services.analytics_service import analytics_service
    from src.services.cache_service import cache_service

    # Check cache first (TTL: 10 minutes)
    cache_key = f"analytics:trends:{user.id}:{days}:{grouping}"
    cached_result = cache_service.get(cache_key)
    if cached_result is not None:
        return JSONResponse(cached_result)

    # Get all cached analyses
    analyses = get_all_cached_analyses()

    # Calculate trends
    trends = analytics_service.calculate_issue_trends(
        analyses,
        days=days,
        grouping=grouping
    )

    # Cache the result (TTL: 600 seconds = 10 minutes)
    cache_service.set(cache_key, trends, ttl=600)

    return JSONResponse(trends)


@app.get("/api/analytics/repository")
async def get_repository_analytics(user = Depends(get_current_user)):
    """
    Get comprehensive repository metrics

    Returns:
    - total_analyses: Total number of analyses
    - total_issues: Total issues found
    - total_files: Number of files analyzed
    - total_lines_of_code: Total LOC
    - avg_issues_per_file: Average issues per file
    - avg_complexity: Average complexity score
    - most_common_issues: Top 10 most common issues
    - severity_distribution: Issues by severity
    - category_distribution: Issues by category
    - health_score: Overall health score
    """
    from src.services.analytics_service import analytics_service
    from src.services.cache_service import cache_service

    # Check cache first (TTL: 15 minutes)
    cache_key = f"analytics:repository:{user.id}"
    cached_result = cache_service.get(cache_key)
    if cached_result is not None:
        return JSONResponse(cached_result)

    # Get all cached analyses
    analyses = get_all_cached_analyses()

    # Calculate repository metrics
    metrics = analytics_service.calculate_repository_metrics(analyses)

    # Cache the result (TTL: 900 seconds = 15 minutes)
    cache_service.set(cache_key, metrics, ttl=900)

    return JSONResponse(metrics)


@app.get("/api/analytics/insights")
async def get_analytics_insights(user = Depends(get_current_user)):
    """
    Get actionable insights based on code analysis

    Returns array of insights with:
    - type: Insight type identifier
    - severity: Insight severity (critical/error/warning/info)
    - title: Insight title
    - message: Detailed message
    - recommendation: Actionable recommendation
    """
    from src.services.analytics_service import analytics_service

    # Get repository metrics
    analyses = get_all_cached_analyses()
    metrics = analytics_service.calculate_repository_metrics(analyses)

    # Generate insights
    insights = analytics_service.generate_insights(metrics)

    return JSONResponse(insights)


@app.get("/api/analytics/compare")
async def compare_periods(
    current_days: int = 7,
    previous_days: int = 7,
    user = Depends(get_current_user)
):
    """
    Compare metrics between two time periods

    Query parameters:
    - current_days: Days to include in current period (default 7)
    - previous_days: Days to include in previous period (default 7)

    Returns:
    - current: Metrics for current period
    - previous: Metrics for previous period
    - changes: Change metrics with direction indicators
    """
    from src.services.analytics_service import analytics_service
    from datetime import datetime, timedelta

    # Get all analyses
    all_analyses = get_all_cached_analyses()

    # Split into current and previous periods
    now = datetime.now()
    current_start = now - timedelta(days=current_days)
    previous_start = current_start - timedelta(days=previous_days)

    current_period = []
    previous_period = []

    for analysis in all_analyses:
        analyzed_at = analysis.get('analyzed_at')
        if not analyzed_at:
            continue

        try:
            if isinstance(analyzed_at, str):
                analysis_date = datetime.fromisoformat(analyzed_at.replace('Z', '+00:00'))
            else:
                analysis_date = analyzed_at

            if current_start <= analysis_date <= now:
                current_period.append(analysis)
            elif previous_start <= analysis_date < current_start:
                previous_period.append(analysis)

        except:
            continue

    # Compare periods
    comparison = analytics_service.compare_periods(current_period, previous_period)

    return JSONResponse(comparison)


@app.get("/api/analytics/export")
async def export_analytics(
    format: str = 'json',
    days: int = 30,
    user = Depends(get_current_user)
):
    """
    Export analytics data in CSV or JSON format

    Query parameters:
    - format: 'json' or 'csv' (default 'json')
    - days: Number of days to include (default 30)

    Returns:
    - JSON: JSON response with all analytics data
    - CSV: CSV file download
    """
    from src.services.analytics_service import analytics_service
    from datetime import datetime, timedelta
    import csv
    import io

    # Get analyses for the period
    all_analyses = get_all_cached_analyses()
    cutoff_date = datetime.now() - timedelta(days=days)

    # Filter by date
    recent_analyses = []
    for analysis in all_analyses:
        analyzed_at = analysis.get('analyzed_at')
        if not analyzed_at:
            continue

        try:
            if isinstance(analyzed_at, str):
                analysis_date = datetime.fromisoformat(analyzed_at.replace('Z', '+00:00'))
            else:
                analysis_date = analyzed_at

            if analysis_date >= cutoff_date:
                recent_analyses.append(analysis)
        except:
            continue

    # Calculate metrics
    metrics = analytics_service.calculate_repository_metrics(recent_analyses)
    trends = analytics_service.calculate_issue_trends(recent_analyses, days=days)
    health_score = analytics_service.calculate_health_score(
        [issue for analysis in recent_analyses for issue in analysis.get('issues', [])]
    )

    data = {
        'export_date': datetime.now().isoformat(),
        'period_days': days,
        'health_score': health_score,
        'repository_metrics': metrics,
        'trends': trends
    }

    if format.lower() == 'csv':
        # Create CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Write health score
        writer.writerow(['Health Score Metrics'])
        writer.writerow(['Score', 'Grade', 'Status'])
        writer.writerow([health_score['score'], health_score['grade'], health_score['status']])
        writer.writerow([])

        # Write repository metrics
        writer.writerow(['Repository Metrics'])
        writer.writerow(['Metric', 'Value'])
        for key, value in metrics.items():
            if not isinstance(value, (dict, list)):
                writer.writerow([key, value])
        writer.writerow([])

        # Write trends
        writer.writerow(['Issue Trends'])
        if trends:
            headers = list(trends[0].keys())
            writer.writerow(headers)
            for trend in trends:
                writer.writerow([trend.get(h, '') for h in headers])

        # Return CSV response
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=analytics_export_{datetime.now().strftime('%Y%m%d')}.csv"}
        )

    # Return JSON
    return JSONResponse(data)


# ============================================================================
# Notification Endpoints
# ============================================================================

@app.get("/api/notifications")
async def get_notifications(
    user_id: Optional[str] = None,
    notification_type: Optional[str] = None,
    unread_only: bool = False,
    limit: int = 50,
    user = Depends(get_current_user)
):
    """
    Get notifications with optional filtering

    Query parameters:
    - user_id: Filter by user ID
    - notification_type: Filter by type (info, warning, error, etc.)
    - unread_only: Only return unread notifications
    - limit: Maximum number of notifications to return
    """
    from src.services.notification_service import notification_service, NotificationType

    # Parse notification type if provided
    filter_type = None
    if notification_type:
        try:
            filter_type = NotificationType(notification_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid notification type: {notification_type}")

    # Get notifications
    notifications = notification_service.get_notifications(
        user_id=user_id,
        notification_type=filter_type,
        unread_only=unread_only
    )

    # Apply limit
    if limit:
        notifications = notifications[:limit]

    return JSONResponse({'notifications': notifications, 'count': len(notifications)})


@app.get("/api/notifications/{notification_id}")
async def get_notification(notification_id: str, user = Depends(get_current_user)):
    """Get a specific notification by ID"""
    from src.services.notification_service import notification_service

    notification = notification_service.get_notification(notification_id)

    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    return JSONResponse(notification)


@app.post("/api/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, user = Depends(get_current_user)):
    """Mark a notification as read"""
    from src.services.notification_service import notification_service

    success = notification_service.mark_as_read(notification_id)

    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")

    return JSONResponse({'success': True, 'message': 'Notification marked as read'})


@app.post("/api/notifications/read-all")
async def mark_all_notifications_read(
    user_id: Optional[str] = None,
    user = Depends(get_current_user)
):
    """Mark all notifications as read for a user"""
    from src.services.notification_service import notification_service

    count = notification_service.mark_all_as_read(user_id=user_id)

    return JSONResponse({'success': True, 'count': count, 'message': f'Marked {count} notifications as read'})


@app.post("/api/notifications/{notification_id}/dismiss")
async def dismiss_notification(notification_id: str, user = Depends(get_current_user)):
    """Dismiss a notification"""
    from src.services.notification_service import notification_service

    success = notification_service.dismiss_notification(notification_id)

    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")

    return JSONResponse({'success': True, 'message': 'Notification dismissed'})


@app.delete("/api/notifications/{notification_id}")
async def delete_notification(notification_id: str, user = Depends(get_current_user)):
    """Permanently delete a notification"""
    from src.services.notification_service import notification_service

    success = notification_service.delete_notification(notification_id)

    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")

    return JSONResponse({'success': True, 'message': 'Notification deleted'})


@app.delete("/api/notifications/old")
async def clear_old_notifications(days: int = 30, user = Depends(get_current_user)):
    """Clear notifications older than specified days"""
    from src.services.notification_service import notification_service

    count = notification_service.clear_old_notifications(days=days)

    return JSONResponse({'success': True, 'count': count, 'message': f'Deleted {count} old notifications'})


@app.get("/api/notifications/preferences")
async def get_notification_preferences(user = Depends(get_current_user)):
    """Get notification preferences"""
    from src.services.notification_service import notification_service

    preferences = notification_service.get_preferences()

    return JSONResponse(preferences)


@app.post("/api/notifications/preferences")
async def update_notification_preferences(preferences: Dict[str, Any], user = Depends(get_current_user)):
    """Update notification preferences"""
    from src.services.notification_service import notification_service

    success = notification_service.update_preferences(preferences)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to update preferences")

    return JSONResponse({'success': True, 'message': 'Preferences updated'})


@app.get("/api/notifications/statistics")
async def get_notification_statistics(user_id: Optional[str] = None, user = Depends(get_current_user)):
    """Get notification statistics"""
    from src.services.notification_service import notification_service

    stats = notification_service.get_statistics(user_id=user_id)

    return JSONResponse(stats)


# ============================================================================
# Logging Endpoints
# ============================================================================

@app.get("/api/logs")
async def get_logs(
    level: Optional[str] = None,
    correlation_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    user = Depends(get_current_user)
):
    """
    Get logs with optional filtering

    Query parameters:
    - level: Filter by log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    - correlation_id: Filter by correlation ID
    - limit: Maximum number of logs to return
    - offset: Number of logs to skip
    """
    from src.services.logging_service import logging_service, LogLevel

    # Parse log level if provided
    filter_level = None
    if level:
        try:
            filter_level = LogLevel(level.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid log level: {level}")

    # Get logs
    logs = logging_service.get_logs(
        level=filter_level,
        correlation_id=correlation_id,
        limit=limit,
        offset=offset
    )

    return JSONResponse({'logs': logs, 'count': len(logs)})


@app.get("/api/logs/errors")
async def get_error_logs(limit: int = 100, user = Depends(get_current_user)):
    """Get recent error logs"""
    from src.services.logging_service import logging_service

    errors = logging_service.get_errors(limit=limit)

    return JSONResponse({'errors': errors, 'count': len(errors)})


@app.get("/api/logs/statistics")
async def get_logging_statistics(user = Depends(get_current_user)):
    """Get logging statistics"""
    from src.services.logging_service import logging_service

    stats = logging_service.get_statistics()

    return JSONResponse(stats)


@app.delete("/api/logs")
async def clear_logs(user = Depends(get_current_user)):
    """Clear all logs"""
    from src.services.logging_service import logging_service

    # Only admins can clear logs
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can clear logs")

    count = logging_service.clear_logs()

    return JSONResponse({'success': True, 'count': count, 'message': f'Cleared {count} logs'})


@app.delete("/api/logs/errors")
async def clear_error_logs(user = Depends(get_current_user)):
    """Clear error logs"""
    from src.services.logging_service import logging_service

    # Only admins can clear error logs
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Only admins can clear error logs")

    count = logging_service.clear_errors()

    return JSONResponse({'success': True, 'count': count, 'message': f'Cleared {count} error logs'})


@app.get("/api/logs/export")
async def export_logs(format: str = 'json', user = Depends(get_current_user)):
    """
    Export logs in JSON or CSV format

    Query parameters:
    - format: Export format ('json' or 'csv')
    """
    from src.services.logging_service import logging_service
    from datetime import datetime

    if format.lower() not in ['json', 'csv']:
        raise HTTPException(status_code=400, detail="Format must be 'json' or 'csv'")

    exported = logging_service.export_logs(format=format.lower())

    if format.lower() == 'csv':
        return StreamingResponse(
            iter([exported]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=logs_export_{datetime.now().strftime('%Y%m%d')}.csv"}
        )

    return JSONResponse(exported)


# ============================================================================
# Issues Endpoints
# ============================================================================

@app.get("/api/issues")
async def list_issues(
    severity: Optional[str] = None,
    category: Optional[str] = None,
    file_path: Optional[str] = None,
    job_id: Optional[str] = None,
    repository: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user = Depends(get_current_user)
):
    """
    List issues with filtering and pagination.

    Query parameters:
    - severity: Filter by severity (info, warning, error, critical)
    - category: Filter by category (security, smell, complexity)
    - file_path: Filter by file path (partial match)
    - job_id: Filter by analysis job ID
    - repository: Filter by repository ID
    - limit: Maximum number of issues to return (default 50)
    - offset: Number of issues to skip (default 0)
    """
    all_issues = []

    # Try to get issues from database first (supports both repository-specific and all issues)
    with db_manager.get_session() as db:
        from src.core.database import Issue, CodeFile

        # Build query
        query = db.query(Issue).join(CodeFile)

        # Apply repository filter if provided
        if repository:
            query = query.filter(CodeFile.repository_id == repository)

        # Apply other filters
        if severity:
            query = query.filter(Issue.severity == severity.lower())
        if category:
            query = query.filter(Issue.category == category.lower())
        if file_path:
            query = query.filter(CodeFile.file_path.contains(file_path))

        # Get total count before pagination
        total = query.count()

        # If there are database issues, return them
        if total > 0:
            # Apply pagination and fetch
            issues_db = query.order_by(
                Issue.severity.desc(),
                Issue.created_at.desc()
            ).limit(limit).offset(offset).all()

            # Convert to dict
            all_issues = [
                {
                    'id': issue.id,
                    'title': issue.title,
                    'description': issue.description,
                    'severity': issue.severity.value,
                    'category': issue.category.value,
                    'rule_id': issue.rule_id,
                    'file_path': issue.code_file.file_path,
                    'line_number': issue.line_number,
                    'column_number': issue.column_number,
                    'code_snippet': issue.code_snippet,
                    'confidence': issue.confidence,
                    'created_at': issue.created_at.isoformat() if issue.created_at else None
                }
                for issue in issues_db
            ]

            return {
                "success": True,
                "total": total,
                "limit": limit,
                "offset": offset,
                "issues": all_issues,
                "filters": {
                    "severity": severity,
                    "category": category,
                    "file_path": file_path,
                    "repository": repository
                }
            }

    # Fallback to cached analyses if no database issues (legacy behavior for file uploads)
    analyses = get_all_cached_analyses()

    # Collect issues from all analyses
    for analysis in analyses:
        for issue in analysis.get('issues', []):
            # Add metadata about the source
            issue_with_meta = issue.copy()
            issue_with_meta['analyzed_at'] = analysis.get('analyzed_at')
            issue_with_meta['source_filename'] = analysis.get('filename')
            all_issues.append(issue_with_meta)

    # Apply filters
    filtered_issues = all_issues

    if severity:
        filtered_issues = [i for i in filtered_issues if i.get('severity') == severity.lower()]

    if category:
        filtered_issues = [i for i in filtered_issues if i.get('category') == category.lower()]

    if file_path:
        filtered_issues = [i for i in filtered_issues if file_path.lower() in i.get('file_path', '').lower()]

    if job_id:
        # Get specific job's issues
        job_analysis = get_analysis_results(job_id)
        if job_analysis:
            filtered_issues = job_analysis.get('issues', [])
        else:
            filtered_issues = []

    # Sort by severity (critical > error > warning > info)
    severity_order = {'critical': 0, 'error': 1, 'warning': 2, 'info': 3}
    filtered_issues.sort(key=lambda x: severity_order.get(x.get('severity', 'info'), 3))

    # Pagination
    total = len(filtered_issues)
    paginated_issues = filtered_issues[offset:offset + limit]

    return {
        "success": True,
        "total": total,
        "limit": limit,
        "offset": offset,
        "issues": paginated_issues,
        "filters": {
            "severity": severity,
            "category": category,
            "file_path": file_path,
            "job_id": job_id
        }
    }


@app.get("/api/issues/{issue_id}")
async def get_issue(
    issue_id: str,
    user = Depends(get_current_user)
):
    """
    Get detailed information about a specific issue.

    Supports both database UUIDs and legacy synthetic IDs.
    """
    # Try to find in database first (repository analysis issues)
    with db_manager.get_session() as db:
        from src.core.database import Issue, CodeFile

        issue = db.query(Issue).filter(Issue.id == issue_id).first()

        if issue:
            return {
                "success": True,
                "issue": {
                    "id": issue.id,
                    "title": issue.title,
                    "description": issue.description,
                    "severity": issue.severity.value,
                    "category": issue.category.value,
                    "rule_id": issue.rule_id,
                    "file_path": issue.code_file.file_path,
                    "line_number": issue.line_number,
                    "column_number": issue.column_number,
                    "code_snippet": issue.code_snippet,
                    "confidence": issue.confidence,
                    "ai_explanation": issue.ai_explanation,
                    "fix_suggestion": issue.fix_suggestion,
                    "created_at": issue.created_at.isoformat() if issue.created_at else None,
                    "repository_id": issue.code_file.repository_id,
                    "repository_name": issue.code_file.repository.name if issue.code_file.repository else None
                }
            }

    # Fallback to in-memory cache for legacy file upload issues
    analyses = get_all_cached_analyses()

    for analysis in analyses:
        for idx, issue in enumerate(analysis.get('issues', [])):
            # Create a synthetic ID based on file and position
            synthetic_id = f"{analysis.get('filename', 'unknown')}_{idx}"

            if synthetic_id == issue_id or str(idx) == issue_id:
                return {
                    "success": True,
                    "issue": {
                        **issue,
                        "id": synthetic_id,
                        "analyzed_at": analysis.get('analyzed_at'),
                        "source_filename": analysis.get('filename')
                    }
                }

    raise HTTPException(status_code=404, detail="Issue not found")


@app.post("/api/issues/{issue_id}/create-github-issue")
async def create_github_issue_from_code_issue(
    issue_id: str,
    user = Depends(get_current_user)
):
    """
    Create a GitHub issue from a code analysis issue.

    Args:
        issue_id: The code analysis issue ID

    Returns:
        GitHub issue information
    """
    try:
        # Get the issue from database
        with db_manager.get_session() as db:
            from src.core.database import Issue, CodeFile, Repository

            issue = db.query(Issue).filter(Issue.id == issue_id).first()

            if not issue:
                raise HTTPException(status_code=404, detail="Issue not found")

            # Get repository information
            repository = issue.code_file.repository if issue.code_file else None

            if not repository:
                raise HTTPException(
                    status_code=400,
                    detail="Issue is not associated with a repository. Cannot create GitHub issue."
                )

            if not repository.github_url:
                raise HTTPException(
                    status_code=400,
                    detail="Repository does not have a GitHub URL configured."
                )

            # Format issue body for GitHub
            severity_emoji = {
                'info': 'ℹ️',
                'warning': '⚠️',
                'error': '❌',
                'critical': '🚨'
            }

            category_emoji = {
                'security': '🔒',
                'smell': '👃',
                'complexity': '🧩',
                'performance': '⚡',
                'best_practice': '✅'
            }

            emoji_severity = severity_emoji.get(issue.severity.value, '')
            emoji_category = category_emoji.get(issue.category.value, '')

            issue_body = f"""## {emoji_severity} Code Issue Detected by AI Code Review Assistant

**Severity:** {issue.severity.value.upper()}
**Category:** {emoji_category} {issue.category.value.title()}
**Rule:** `{issue.rule_id}`

### Description
{issue.description}

### Location
- **File:** `{issue.code_file.file_path}`
- **Line:** {issue.line_number or 'N/A'}
{f"- **Column:** {issue.column_number}" if issue.column_number else ""}

### Code Snippet
```{issue.code_file.language or 'text'}
{issue.code_snippet or 'N/A'}
```

### Confidence
{issue.confidence * 100:.0f}%

{f"### AI Explanation\\n{issue.ai_explanation}\\n" if issue.ai_explanation else ""}

{f"### Suggested Fix\\n{issue.fix_suggestion}\\n" if issue.fix_suggestion else ""}

---
*This issue was automatically detected and reported by [AI Code Review Assistant](https://github.com/AKHIL-149/ai-experiments-hub)*
"""

            # Create GitHub issue using GitHubService
            from src.services.github_service import GitHubService

            # Get GitHub token from environment or repository settings
            github_token = os.getenv('GITHUB_TOKEN')
            if not github_token:
                raise HTTPException(
                    status_code=500,
                    detail="GitHub token not configured. Set GITHUB_TOKEN environment variable."
                )

            github_service = GitHubService(github_token=github_token)

            # Create the issue
            issue_title = f"[{issue.severity.value.upper()}] {issue.title}"

            # Determine labels based on category and severity
            labels = [issue.category.value, issue.severity.value]

            success, github_issue, error = github_service.create_issue(
                repo_url=repository.github_url,
                title=issue_title,
                body=issue_body,
                labels=labels
            )

            if not success:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to create GitHub issue: {error}"
                )

            return {
                "success": True,
                "message": "GitHub issue created successfully",
                "github_issue": github_issue,
                "code_issue_id": issue_id
            }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating GitHub issue: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal error: {str(e)}"
        )


@app.post("/api/issues/{issue_id}/dismiss")
async def dismiss_issue(
    issue_id: str,
    reason: Optional[str] = None,
    user = Depends(get_current_user)
):
    """
    Dismiss an issue as false positive or not relevant.

    Args:
        issue_id: The issue ID to dismiss
        reason: Optional reason for dismissal

    Returns:
        Success status and updated issue information
    """
    try:
        with db_manager.get_session() as db:
            from src.core.database import Issue
            from datetime import datetime

            # Get the issue
            issue = db.query(Issue).filter(Issue.id == issue_id).first()

            if not issue:
                raise HTTPException(status_code=404, detail="Issue not found")

            # Mark as dismissed
            issue.dismissed = True
            issue.dismissed_at = datetime.utcnow()
            issue.dismissed_by = user.id
            issue.dismissal_reason = reason

            db.commit()

            return {
                "success": True,
                "message": "Issue dismissed successfully",
                "issue": {
                    "id": issue.id,
                    "dismissed": issue.dismissed,
                    "dismissed_at": issue.dismissed_at.isoformat(),
                    "dismissed_by": user.username,
                    "dismissal_reason": issue.dismissal_reason
                }
            }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error dismissing issue: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to dismiss issue: {str(e)}"
        )


@app.post("/api/issues/{issue_id}/restore")
async def restore_issue(
    issue_id: str,
    user = Depends(get_current_user)
):
    """
    Restore a dismissed issue.

    Args:
        issue_id: The issue ID to restore

    Returns:
        Success status and updated issue information
    """
    try:
        with db_manager.get_session() as db:
            from src.core.database import Issue

            # Get the issue
            issue = db.query(Issue).filter(Issue.id == issue_id).first()

            if not issue:
                raise HTTPException(status_code=404, detail="Issue not found")

            # Restore the issue
            issue.dismissed = False
            issue.dismissed_at = None
            issue.dismissed_by = None
            issue.dismissal_reason = None

            db.commit()

            return {
                "success": True,
                "message": "Issue restored successfully",
                "issue": {
                    "id": issue.id,
                    "dismissed": issue.dismissed
                }
            }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error restoring issue: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to restore issue: {str(e)}"
        )


@app.get("/api/issues/summary/stats")
async def get_issues_stats(
    user = Depends(get_current_user)
):
    """
    Get aggregated statistics about all issues.

    Returns counts by severity, category, and file.
    """
    analyses = get_all_cached_analyses()

    total_issues = 0
    by_severity = {}
    by_category = {}
    by_file = {}

    for analysis in analyses:
        issues = analysis.get('issues', [])
        total_issues += len(issues)

        for issue in issues:
            # Count by severity
            sev = issue.get('severity', 'unknown')
            by_severity[sev] = by_severity.get(sev, 0) + 1

            # Count by category
            cat = issue.get('category', 'unknown')
            by_category[cat] = by_category.get(cat, 0) + 1

            # Count by file
            file = issue.get('file_path', 'unknown')
            by_file[file] = by_file.get(file, 0) + 1

    return {
        "success": True,
        "total_issues": total_issues,
        "total_files_analyzed": len(analyses),
        "by_severity": by_severity,
        "by_category": by_category,
        "by_file": by_file,
        "most_problematic_files": sorted(
            by_file.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]
    }


# ============================================================================
# Refactoring Endpoints
# ============================================================================

@app.get("/api/refactorings")
async def list_refactorings(
    status: Optional[str] = None,
    issue_id: Optional[str] = None,
    code_file_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user = Depends(get_current_user)
):
    """
    List refactoring suggestions with filtering and pagination.

    Query parameters:
    - status: Filter by status (suggested/accepted/rejected/applied)
    - issue_id: Filter by issue ID
    - code_file_id: Filter by code file ID
    - limit: Maximum number of refactorings to return (default 50)
    - offset: Number of refactorings to skip (default 0)
    """
    from src.core.database import Refactoring, RefactoringStatus

    with db_manager.get_session() as db:
        query = db.query(Refactoring)

        # Apply filters
        if status:
            try:
                status_enum = RefactoringStatus(status.lower())
                query = query.filter(Refactoring.status == status_enum)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

        if issue_id:
            query = query.filter(Refactoring.issue_id == issue_id)

        if code_file_id:
            query = query.filter(Refactoring.code_file_id == code_file_id)

        # Get total count
        total = query.count()

        # Apply pagination
        refactorings = query.limit(limit).offset(offset).all()

        return {
            "success": True,
            "total": total,
            "limit": limit,
            "offset": offset,
            "refactorings": [r.to_dict() for r in refactorings],
            "filters": {
                "status": status,
                "issue_id": issue_id,
                "code_file_id": code_file_id
            }
        }


@app.get("/api/refactorings/{refactoring_id}")
async def get_refactoring(
    refactoring_id: str,
    user = Depends(get_current_user)
):
    """Get detailed information about a specific refactoring suggestion."""
    from src.services.refactoring_service import RefactoringService

    with db_manager.get_session() as db:
        service = RefactoringService(db)
        success, refactoring, error = service.get_refactoring(refactoring_id)

        if not success:
            raise HTTPException(status_code=404, detail=error)

        return {
            "success": True,
            "refactoring": refactoring.to_dict()
        }


@app.post("/api/refactorings")
async def create_refactoring(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """
    Create a new refactoring suggestion.

    Required fields:
    - issue_id: Associated issue ID
    - code_file_id: Code file ID
    - refactoring_type: Type of refactoring
    - original_code: Original code snippet
    - refactored_code: Refactored code snippet
    - explanation: Explanation of the refactoring

    Optional fields:
    - benefits: Benefits of applying this refactoring
    - confidence: Confidence score (0.0-1.0, default 0.5)
    """
    from src.services.refactoring_service import RefactoringService

    # Validate required fields
    required_fields = ['issue_id', 'code_file_id', 'refactoring_type',
                      'original_code', 'refactored_code', 'explanation']
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    with db_manager.get_session() as db:
        service = RefactoringService(db)

        success, refactoring, error = service.create_refactoring(
            issue_id=data['issue_id'],
            code_file_id=data['code_file_id'],
            refactoring_type=data['refactoring_type'],
            original_code=data['original_code'],
            refactored_code=data['refactored_code'],
            explanation=data['explanation'],
            benefits=data.get('benefits'),
            confidence=data.get('confidence', 0.5)
        )

        if not success:
            raise HTTPException(status_code=500, detail=error)

        return {
            "success": True,
            "refactoring": refactoring.to_dict()
        }


@app.post("/api/refactorings/{refactoring_id}/accept")
async def accept_refactoring(
    refactoring_id: str,
    user = Depends(get_current_user)
):
    """Accept a refactoring suggestion."""
    from src.services.refactoring_service import RefactoringService

    with db_manager.get_session() as db:
        service = RefactoringService(db)
        success, refactoring, error = service.accept_refactoring(refactoring_id)

        if not success:
            raise HTTPException(status_code=404, detail=error)

        return {
            "success": True,
            "refactoring": refactoring.to_dict()
        }


@app.post("/api/refactorings/{refactoring_id}/reject")
async def reject_refactoring(
    refactoring_id: str,
    user = Depends(get_current_user)
):
    """Reject a refactoring suggestion."""
    from src.services.refactoring_service import RefactoringService

    with db_manager.get_session() as db:
        service = RefactoringService(db)
        success, refactoring, error = service.reject_refactoring(refactoring_id)

        if not success:
            raise HTTPException(status_code=404, detail=error)

        return {
            "success": True,
            "refactoring": refactoring.to_dict()
        }


@app.post("/api/refactorings/{refactoring_id}/apply")
async def mark_refactoring_applied(
    refactoring_id: str,
    user = Depends(get_current_user)
):
    """Mark a refactoring as applied."""
    from src.services.refactoring_service import RefactoringService

    with db_manager.get_session() as db:
        service = RefactoringService(db)
        success, refactoring, error = service.mark_refactoring_applied(refactoring_id)

        if not success:
            raise HTTPException(status_code=404, detail=error)

        return {
            "success": True,
            "refactoring": refactoring.to_dict()
        }


@app.get("/api/refactorings/stats/summary")
async def get_refactoring_stats(
    user = Depends(get_current_user)
):
    """Get refactoring statistics."""
    from src.services.refactoring_service import RefactoringService

    with db_manager.get_session() as db:
        service = RefactoringService(db)
        stats = service.get_stats()

        return {
            "success": True,
            **stats
        }


# ============================================================================
# AI Refactoring Endpoints
# ============================================================================

@app.post("/api/refactor/multi-step")
async def generate_multi_step_refactoring(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """
    Generate a multi-step refactoring chain to fix multiple issues.

    Required fields:
    - code: Original code to refactor
    - language: Programming language
    - issues: List of issues to fix

    Optional fields:
    - max_steps: Maximum number of refactoring steps (default 5)
    """
    from src.services.ai_refactoring_service import ai_refactoring_service

    # Validate required fields
    required_fields = ['code', 'language', 'issues']
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    try:
        refactoring_chain = ai_refactoring_service.generate_multi_step_refactoring(
            code=data['code'],
            language=data['language'],
            issues=data['issues'],
            max_steps=data.get('max_steps', 5)
        )

        return {
            "success": True,
            "steps": refactoring_chain.steps,
            "original_code": refactoring_chain.original_code,
            "final_code": refactoring_chain.final_code,
            "confidence": refactoring_chain.confidence,
            "explanation": refactoring_chain.explanation,
            "estimated_time": refactoring_chain.estimated_time
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating refactoring: {str(e)}")


@app.post("/api/refactor/auto-fix/{issue_id}")
async def apply_automated_fix(
    issue_id: str,
    generate_test: bool = True,
    user = Depends(get_current_user)
):
    """
    Automatically apply a fix for an issue.

    Query parameters:
    - generate_test: Whether to generate a test for the fix (default true)
    """
    from src.services.ai_refactoring_service import ai_refactoring_service

    try:
        result = ai_refactoring_service.apply_automated_fix(
            issue_id=issue_id,
            generate_test=generate_test
        )

        if not result.get('success'):
            raise HTTPException(status_code=404, detail=result.get('error', 'Unknown error'))

        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error applying fix: {str(e)}")


@app.get("/api/technical-debt")
async def get_technical_debt_estimation(
    user = Depends(get_current_user)
):
    """
    Get technical debt estimation for all analyzed code.

    Returns metrics including:
    - Total files, LOC, and issues
    - Debt ratio (issues per 1000 LOC)
    - Estimated hours and cost to fix
    - Prioritized recommendations
    """
    from src.services.ai_refactoring_service import ai_refactoring_service
    from src.core.database import CodeFile, Issue

    with db_manager.get_session() as db:
        # Get all code files
        code_files = db.query(CodeFile).all()
        code_file_data = [{
            'file_path': cf.file_path,
            'lines_of_code': cf.lines_of_code or 0,
            'language': cf.language
        } for cf in code_files]

        # Get all issues
        issues = db.query(Issue).all()
        issue_data = [{
            'severity': i.severity.value if hasattr(i.severity, 'value') else i.severity,
            'category': i.category.value if hasattr(i.category, 'value') else i.category,
            'title': i.title
        } for i in issues]

        try:
            debt_estimation = ai_refactoring_service.estimate_technical_debt(
                code_files=code_file_data,
                issues=issue_data
            )

            return {
                "success": True,
                **debt_estimation
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error estimating technical debt: {str(e)}")


@app.post("/api/ai/pair-programming")
async def ai_pair_programming(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """
    AI pair programming mode - interactive code assistance.

    Required fields:
    - prompt: User's request or question

    Optional fields:
    - context: Optional context (current_file, issues, recent_changes)
    - language: Programming language (default 'python')
    """
    from src.services.ai_refactoring_service import ai_refactoring_service

    # Validate required fields
    if 'prompt' not in data:
        raise HTTPException(status_code=400, detail="Missing required field: prompt")

    try:
        result = ai_refactoring_service.ai_pair_programming(
            prompt=data['prompt'],
            context=data.get('context'),
            language=data.get('language', 'python')
        )

        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error in AI pair programming: {str(e)}")


@app.post("/api/ai/predict-smells")
async def predict_code_smells(
    data: Dict[str, Any],
    user = Depends(get_current_user)
):
    """
    Predict potential code smells using AI.

    Required fields:
    - code: Code to analyze
    - language: Programming language
    """
    from src.services.ai_refactoring_service import ai_refactoring_service

    # Validate required fields
    required_fields = ['code', 'language']
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    try:
        smells = ai_refactoring_service.predict_code_smells(
            code=data['code'],
            language=data['language']
        )

        return {
            "success": True,
            "code_smells": smells,
            "count": len(smells)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error predicting code smells: {str(e)}")


# ============================================================================
# Historical Analytics Endpoints
# ============================================================================

@app.get("/api/analytics/repository/{repository_id}/health")
async def get_repository_health(
    repository_id: str,
    time_window_days: int = 30,
    user = Depends(get_current_user)
):
    """
    Get repository health score and metrics.

    Query parameters:
    - time_window_days: Days to analyze (default 30)

    Returns health score (0-100), grade, issues per KLOC, and trend
    """
    from src.services.historical_analytics_service import historical_analytics_service

    try:
        health = historical_analytics_service.get_repository_health_score(
            repository_id=repository_id,
            time_window_days=time_window_days
        )

        return {
            "success": True,
            "score": health.score,
            "grade": health.grade,
            "issues_per_kloc": health.issues_per_kloc,
            "critical_issues": health.critical_issues,
            "total_issues": health.total_issues,
            "trend": health.trend
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating health score: {str(e)}")


@app.get("/api/analytics/repository/{repository_id}/trends")
async def get_quality_trends(
    repository_id: str,
    days: int = 90,
    granularity: str = 'daily',
    user = Depends(get_current_user)
):
    """
    Get time-series quality trends.

    Query parameters:
    - days: Number of days to analyze (default 90)
    - granularity: 'daily', 'weekly', or 'monthly' (default 'daily')

    Returns trend data for total issues, critical issues, health score, and issues per KLOC
    """
    from src.services.historical_analytics_service import historical_analytics_service

    if granularity not in ['daily', 'weekly', 'monthly']:
        raise HTTPException(status_code=400, detail="Invalid granularity. Must be 'daily', 'weekly', or 'monthly'")

    try:
        trends = historical_analytics_service.get_quality_trends(
            repository_id=repository_id,
            days=days,
            granularity=granularity
        )

        return {
            "success": True,
            "repository_id": repository_id,
            "time_period": f"{days} days",
            "granularity": granularity,
            **trends
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting quality trends: {str(e)}")


@app.get("/api/analytics/repository/{repository_id}/developers")
async def get_developer_contributions(
    repository_id: str,
    days: int = 30,
    user = Depends(get_current_user)
):
    """
    Get developer contribution analysis.

    Query parameters:
    - days: Days to analyze (default 30)

    Returns statistics for each developer including PRs, reviews, issues, and quality scores
    """
    from src.services.historical_analytics_service import historical_analytics_service

    try:
        analysis = historical_analytics_service.get_developer_contribution_analysis(
            repository_id=repository_id,
            days=days
        )

        return {
            "success": True,
            "repository_id": repository_id,
            "time_period": f"{days} days",
            "developers": analysis,
            "total_developers": len(analysis)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing developer contributions: {str(e)}")


@app.get("/api/analytics/repository/{repository_id}/heatmap")
async def get_technical_debt_heatmap(
    repository_id: str,
    user = Depends(get_current_user)
):
    """
    Get technical debt heatmap showing problem areas in the codebase.

    Returns files sorted by debt score with detailed metrics for each
    """
    from src.services.historical_analytics_service import historical_analytics_service

    try:
        heatmap = historical_analytics_service.get_technical_debt_heatmap(
            repository_id=repository_id
        )

        return {
            "success": True,
            "repository_id": repository_id,
            **heatmap
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating heatmap: {str(e)}")


@app.get("/api/analytics/repository/{repository_id}/quality-gate")
async def get_quality_gate_status(
    repository_id: str,
    user = Depends(get_current_user)
):
    """
    Get quality gate metrics and SLO status.

    Returns overall gate status (passed/failed) and individual SLO metrics
    """
    from src.services.historical_analytics_service import historical_analytics_service

    try:
        metrics = historical_analytics_service.get_quality_gate_metrics(
            repository_id=repository_id
        )

        return {
            "success": True,
            "repository_id": repository_id,
            **metrics
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error checking quality gate: {str(e)}")


# ============================================================================
# Repository Endpoints
# ============================================================================

@app.post("/api/repositories")
async def create_repository(
    data: CreateRepositoryRequest,
    user = Depends(get_current_user)
):
    """
    Create a new repository for code review.

    Validates GitHub URL and stores repository metadata.
    Actual cloning happens asynchronously.
    """
    # Validate GitHub URL format
    if not data.github_url.startswith(('https://github.com/', 'git@github.com:')):
        raise HTTPException(
            status_code=400,
            detail="Invalid GitHub URL. Must start with https://github.com/ or git@github.com:"
        )

    # Extract repo name from URL if not provided
    name = data.name
    if not name:
        # Extract from URL like https://github.com/user/repo.git
        parts = data.github_url.rstrip('/').rstrip('.git').split('/')
        if len(parts) >= 2:
            name = parts[-1]
        else:
            raise HTTPException(status_code=400, detail="Could not extract repository name from URL")

    with db_manager.get_session() as db:
        # Create repository record
        repo = Repository(
            user_id=user.id,
            name=name,
            github_url=data.github_url,
            status=RepositoryStatus.PENDING
        )

        db.add(repo)
        db.commit()
        db.refresh(repo)

        repo_id = repo.id
        repo_dict = repo.to_dict()

    # Start async cloning task
    task = clone_repository_task.delay(
        repository_id=repo_id,
        github_url=data.github_url,
        branch=None,  # Use default branch
        depth=1  # Shallow clone
    )

    return {
        "success": True,
        "repository": repo_dict,
        "clone_job_id": task.id,
        "message": "Repository added successfully. Cloning started in background."
    }


@app.get("/api/repositories")
async def list_repositories(
    user = Depends(get_current_user)
):
    """
    List all repositories for the current user.

    Returns repositories with their status and metadata.
    """
    with db_manager.get_session() as db:
        repositories = db.query(Repository).filter(
            Repository.user_id == user.id
        ).order_by(Repository.created_at.desc()).all()

        return {
            "success": True,
            "total": len(repositories),
            "repositories": [repo.to_dict() for repo in repositories]
        }


@app.get("/api/repositories/{repository_id}")
async def get_repository(
    repository_id: str,
    user = Depends(get_current_user)
):
    """
    Get details of a specific repository.

    Returns full repository information including pull requests count.
    """
    with db_manager.get_session() as db:
        repo = db.query(Repository).filter(
            Repository.id == repository_id,
            Repository.user_id == user.id
        ).first()

        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Get pull requests count
        pr_count = len(repo.pull_requests) if repo.pull_requests else 0

        repo_dict = repo.to_dict()
        repo_dict['pull_requests_count'] = pr_count

        return {
            "success": True,
            "repository": repo_dict
        }


@app.put("/api/repositories/{repository_id}")
async def update_repository(
    repository_id: str,
    data: UpdateRepositoryRequest,
    user = Depends(get_current_user)
):
    """
    Update repository settings.

    Allows updating name, default branch, and custom settings.
    """
    with db_manager.get_session() as db:
        repo = db.query(Repository).filter(
            Repository.id == repository_id,
            Repository.user_id == user.id
        ).first()

        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Update fields if provided
        if data.name is not None:
            repo.name = data.name
        if data.default_branch is not None:
            repo.default_branch = data.default_branch
        if data.settings is not None:
            repo.settings_json = data.settings

        db.commit()
        db.refresh(repo)

        return {
            "success": True,
            "repository": repo.to_dict(),
            "message": "Repository updated successfully"
        }


@app.delete("/api/repositories/{repository_id}")
async def delete_repository(
    repository_id: str,
    user = Depends(get_current_user)
):
    """
    Delete a repository.

    Removes repository and all associated data (PRs, issues, etc.) via cascade.
    Also deletes cloned files asynchronously.
    """
    with db_manager.get_session() as db:
        repo = db.query(Repository).filter(
            Repository.id == repository_id,
            Repository.user_id == user.id
        ).first()

        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")

        repo_name = repo.name
        clone_path = repo.clone_path

        # Delete from database
        db.delete(repo)
        db.commit()

    # Delete cloned files asynchronously if they exist
    job_id = None
    if clone_path:
        task = delete_repository_task.delay(
            repository_id=repository_id,
            clone_path=clone_path
        )
        job_id = task.id

    return {
        "success": True,
        "message": f"Repository '{repo_name}' deleted successfully",
        "cleanup_job_id": job_id
    }


@app.post("/api/repositories/{repository_id}/sync")
async def sync_repository(
    repository_id: str,
    user = Depends(get_current_user)
):
    """
    Sync repository with GitHub.

    Fetches and pulls latest changes from GitHub.
    """
    with db_manager.get_session() as db:
        repo = db.query(Repository).filter(
            Repository.id == repository_id,
            Repository.user_id == user.id
        ).first()

        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Check if repository has been cloned
        if not repo.clone_path:
            # Start cloning if not cloned yet
            task = clone_repository_task.delay(
                repository_id=repository_id,
                github_url=repo.github_url,
                branch=repo.default_branch,
                depth=1
            )
            return {
                "success": True,
                "message": "Repository not cloned yet. Cloning started.",
                "job_id": task.id
            }

        # Start sync task
        task = sync_repository_task.delay(
            repository_id=repository_id,
            clone_path=repo.clone_path
        )

        return {
            "success": True,
            "message": "Repository sync started",
            "job_id": task.id
        }


@app.get("/api/repositories/{repository_id}/status")
async def get_repository_status(
    repository_id: str,
    job_id: Optional[str] = None,
    user = Depends(get_current_user)
):
    """
    Get repository status including clone/sync job status.

    Combines repository database status with active job status if job_id provided.
    """
    with db_manager.get_session() as db:
        repo = db.query(Repository).filter(
            Repository.id == repository_id,
            Repository.user_id == user.id
        ).first()

        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")

        repo_dict = repo.to_dict()

        # If job_id provided, get job status
        job_status = None
        if job_id:
            task = AsyncResult(job_id, app=celery_app)
            job_status = {
                "job_id": job_id,
                "state": task.state,
            }

            if task.state == 'PENDING':
                job_status["status"] = "Task is waiting in queue"
            elif task.state in ['CLONING', 'SYNCING', 'DELETING']:
                job_status["status"] = task.info.get('status', f'{task.state}...')
                job_status["progress"] = task.info
            elif task.state == 'SUCCESS':
                job_status["status"] = "Completed successfully"
                job_status["result"] = task.result
            elif task.state == 'FAILURE':
                job_status["status"] = "Failed"
                job_status["error"] = str(task.info)
            else:
                job_status["info"] = str(task.info)

        return {
            "success": True,
            "repository": repo_dict,
            "job": job_status
        }


@app.post("/api/repositories/{repository_id}/analyze")
async def analyze_repository(
    repository_id: str,
    user = Depends(get_current_user)
):
    """
    Analyze all code files in the repository.

    This endpoint triggers an asynchronous analysis of all supported code files
    in the repository. Supported languages: Python, JavaScript, TypeScript, Java, Go, Rust.

    Returns:
        Job ID for tracking analysis progress
    """
    with db_manager.get_session() as db:
        # Verify repository exists and user owns it
        repo = db.query(Repository).filter(
            Repository.id == repository_id,
            Repository.user_id == user.id
        ).first()

        if not repo:
            raise HTTPException(status_code=404, detail="Repository not found")

        # Check if repository has been cloned
        if not repo.clone_path or not os.path.exists(repo.clone_path):
            raise HTTPException(
                status_code=400,
                detail="Repository not cloned yet. Please sync the repository first."
            )

        # Start analysis task
        task = analyze_repository_task.delay(repository_id=repository_id)

        return {
            "success": True,
            "message": "Repository analysis started",
            "job_id": task.id,
            "repository_id": repository_id,
            "repository_name": repo.name
        }


# ============================================================================
# Custom Rules API
# ============================================================================

class CustomRuleRequest(BaseModel):
    """Request model for custom rule"""
    id: str
    name: str
    description: str
    category: str
    severity: str
    languages: List[str]
    pattern_type: str
    message: str
    fix_suggestion: Optional[str] = None
    auto_fixable: bool = False
    ast_patterns: Optional[List[Dict[str, Any]]] = None
    regex_pattern: Optional[Dict[str, Any]] = None


class TestRuleRequest(BaseModel):
    """Request model for testing a rule"""
    rule: Dict[str, Any]
    code: str
    language: str


@app.post("/api/rules/custom")
async def save_custom_rule(
    request: CustomRuleRequest,
    user = Depends(get_current_user)
):
    """
    Save a custom analysis rule.

    The rule will be stored and can be used in future analyses.
    """
    try:
        from src.core.database import CustomRule

        with db_manager.get_session() as db:
            # Check if rule ID already exists
            existing_rule = db.query(CustomRule).filter(
                CustomRule.id == request.id,
                CustomRule.user_id == user.id
            ).first()

            if existing_rule:
                # Update existing rule
                existing_rule.name = request.name
                existing_rule.description = request.description
                existing_rule.category = request.category
                existing_rule.severity = request.severity
                existing_rule.languages = ','.join(request.languages)
                existing_rule.pattern_type = request.pattern_type
                existing_rule.pattern_data = {
                    'ast_patterns': request.ast_patterns,
                    'regex_pattern': request.regex_pattern
                }
                existing_rule.message = request.message
                existing_rule.fix_suggestion = request.fix_suggestion
                existing_rule.auto_fixable = request.auto_fixable
            else:
                # Create new rule
                new_rule = CustomRule(
                    id=request.id,
                    user_id=user.id,
                    name=request.name,
                    description=request.description,
                    category=request.category,
                    severity=request.severity,
                    languages=','.join(request.languages),
                    pattern_type=request.pattern_type,
                    pattern_data={
                        'ast_patterns': request.ast_patterns,
                        'regex_pattern': request.regex_pattern
                    },
                    message=request.message,
                    fix_suggestion=request.fix_suggestion,
                    auto_fixable=request.auto_fixable,
                    enabled=True
                )
                db.add(new_rule)

            db.commit()

        return {"success": True, "message": "Rule saved successfully"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rules/custom")
async def get_custom_rules(user = Depends(get_current_user)):
    """
    Get all custom rules for the current user.
    """
    try:
        from src.core.database import CustomRule

        with db_manager.get_session() as db:
            rules = db.query(CustomRule).filter(
                CustomRule.user_id == user.id
            ).all()

            return {
                "success": True,
                "rules": [rule.to_dict() for rule in rules]
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/rules/custom/{rule_id}")
async def get_custom_rule(rule_id: str, user = Depends(get_current_user)):
    """
    Get a specific custom rule.
    """
    try:
        from src.core.database import CustomRule

        with db_manager.get_session() as db:
            rule = db.query(CustomRule).filter(
                CustomRule.id == rule_id,
                CustomRule.user_id == user.id
            ).first()

            if not rule:
                raise HTTPException(status_code=404, detail="Rule not found")

            return {
                "success": True,
                "rule": rule.to_dict()
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/rules/custom/{rule_id}")
async def delete_custom_rule(rule_id: str, user = Depends(get_current_user)):
    """
    Delete a custom rule.
    """
    try:
        from src.core.database import CustomRule

        with db_manager.get_session() as db:
            rule = db.query(CustomRule).filter(
                CustomRule.id == rule_id,
                CustomRule.user_id == user.id
            ).first()

            if not rule:
                raise HTTPException(status_code=404, detail="Rule not found")

            db.delete(rule)
            db.commit()

        return {"success": True, "message": "Rule deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/rules/test")
async def test_rule(
    request: TestRuleRequest,
    user = Depends(get_current_user)
):
    """
    Test a custom rule against code.

    Returns matches found by the rule.
    """
    try:
        from src.services.custom_rule_service import CustomRuleService

        rule_service = CustomRuleService()
        matches = rule_service.test_rule(
            rule=request.rule,
            code=request.code,
            language=request.language
        )

        return {
            "success": True,
            "matches": matches
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "matches": []
        }


# ============================================================================
# Rule Marketplace API
# ============================================================================

class PublishRuleRequest(BaseModel):
    """Request model for publishing a rule"""
    tags: Optional[List[str]] = None


class RateRuleRequest(BaseModel):
    """Request model for rating a rule"""
    rating: int
    review: Optional[str] = None


@app.get("/api/marketplace/rules")
async def get_marketplace_rules(
    category: Optional[str] = None,
    language: Optional[str] = None,
    search: Optional[str] = None,
    sort_by: str = 'popular',
    limit: int = 50,
    offset: int = 0,
    user = Depends(get_current_user_optional)
):
    """
    Get rules from the marketplace.

    Query parameters:
    - category: Filter by category
    - language: Filter by language
    - search: Search query
    - sort_by: Sort order (popular, recent, rating, forks)
    - limit: Results per page
    - offset: Pagination offset
    """
    try:
        from src.services.rule_marketplace_service import RuleMarketplaceService

        marketplace_service = RuleMarketplaceService()
        result = marketplace_service.get_marketplace_rules(
            category=category,
            language=language,
            search=search,
            sort_by=sort_by,
            limit=limit,
            offset=offset
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get marketplace rules: {str(e)}")


@app.get("/api/marketplace/featured")
async def get_featured_rules(
    limit: int = 10,
    user = Depends(get_current_user_optional)
):
    """Get featured rules from the marketplace."""
    try:
        from src.services.rule_marketplace_service import RuleMarketplaceService

        marketplace_service = RuleMarketplaceService()
        rules = marketplace_service.get_featured_rules(limit=limit)

        return {
            "success": True,
            "rules": rules
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get featured rules: {str(e)}")


@app.post("/api/marketplace/rules/{rule_id}/fork")
async def fork_rule(
    rule_id: str,
    user = Depends(get_current_user)
):
    """Fork a public rule to user's collection."""
    try:
        from src.services.rule_marketplace_service import RuleMarketplaceService

        marketplace_service = RuleMarketplaceService()
        result = marketplace_service.fork_rule(rule_id, user.id)

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fork rule: {str(e)}")


@app.post("/api/marketplace/rules/{rule_id}/rate")
async def rate_rule(
    rule_id: str,
    request: RateRuleRequest,
    user = Depends(get_current_user)
):
    """Rate a rule in the marketplace."""
    try:
        from src.services.rule_marketplace_service import RuleMarketplaceService

        marketplace_service = RuleMarketplaceService()
        result = marketplace_service.rate_rule(
            rule_id=rule_id,
            user_id=user.id,
            rating=request.rating,
            review=request.review
        )

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to rate rule: {str(e)}")


@app.get("/api/marketplace/rules/{rule_id}/ratings")
async def get_rule_ratings(
    rule_id: str,
    limit: int = 10,
    offset: int = 0,
    user = Depends(get_current_user_optional)
):
    """Get ratings for a specific rule."""
    try:
        from src.services.rule_marketplace_service import RuleMarketplaceService

        marketplace_service = RuleMarketplaceService()
        result = marketplace_service.get_rule_ratings(
            rule_id=rule_id,
            limit=limit,
            offset=offset
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get ratings: {str(e)}")


@app.post("/api/rules/custom/{rule_id}/publish")
async def publish_rule(
    rule_id: str,
    request: PublishRuleRequest,
    user = Depends(get_current_user)
):
    """Publish a custom rule to the marketplace."""
    try:
        from src.services.rule_marketplace_service import RuleMarketplaceService

        marketplace_service = RuleMarketplaceService()
        result = marketplace_service.publish_rule(
            rule_id=rule_id,
            user_id=user.id,
            tags=request.tags
        )

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to publish rule: {str(e)}")


@app.post("/api/rules/custom/{rule_id}/unpublish")
async def unpublish_rule(
    rule_id: str,
    user = Depends(get_current_user)
):
    """Unpublish a rule from the marketplace."""
    try:
        from src.services.rule_marketplace_service import RuleMarketplaceService

        marketplace_service = RuleMarketplaceService()
        result = marketplace_service.unpublish_rule(
            rule_id=rule_id,
            user_id=user.id
        )

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unpublish rule: {str(e)}")


@app.get("/api/rules/export")
async def export_rules(
    rule_ids: Optional[str] = None,
    user = Depends(get_current_user)
):
    """
    Export user's custom rules to JSON.

    Query parameters:
    - rule_ids: Comma-separated list of rule IDs (exports all if omitted)
    """
    try:
        from src.services.rule_marketplace_service import RuleMarketplaceService

        marketplace_service = RuleMarketplaceService()

        ids_list = rule_ids.split(',') if rule_ids else None
        rules = marketplace_service.export_rules_bulk(user.id, ids_list)

        return {
            "success": True,
            "rules": rules,
            "count": len(rules)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to export rules: {str(e)}")


@app.post("/api/rules/import")
async def import_rules(
    rules: List[Dict[str, Any]],
    overwrite: bool = False,
    user = Depends(get_current_user)
):
    """
    Import rules from JSON.

    Body:
    - rules: List of rule data dictionaries
    - overwrite: Whether to overwrite existing rules with same ID
    """
    try:
        from src.services.rule_marketplace_service import RuleMarketplaceService

        marketplace_service = RuleMarketplaceService()

        results = []
        for rule_data in rules:
            result = marketplace_service.import_rule(
                rule_data=rule_data,
                user_id=user.id,
                overwrite=overwrite
            )
            results.append(result)

        success_count = sum(1 for r in results if r['success'])

        return {
            "success": True,
            "imported": success_count,
            "total": len(rules),
            "results": results
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to import rules: {str(e)}")


# ============================================================================
# Plugin Management API
# ============================================================================

class LoadPluginRequest(BaseModel):
    """Request model for loading a plugin"""
    file_path: str
    enabled: bool = True


class UpdatePluginRequest(BaseModel):
    """Request model for updating plugin configuration"""
    enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None


@app.get("/api/plugins")
async def list_plugins(user = Depends(get_current_user)):
    """
    List all installed plugins for the current user.

    Returns list of plugins with their status and statistics.
    """
    try:
        from src.core.database import Plugin

        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            plugins = db.query(Plugin).filter(
                Plugin.user_id == user.id
            ).all()

            return {
                "success": True,
                "plugins": [plugin.to_dict() for plugin in plugins]
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list plugins: {str(e)}")


@app.post("/api/plugins/load")
async def load_plugin(
    request: LoadPluginRequest,
    user = Depends(get_current_user)
):
    """
    Load a plugin from a file path.

    Validates the plugin and registers it in the database.
    """
    try:
        from src.core.database import Plugin
        from src.core.plugin_manager import PluginManager
        import os

        # Validate file exists
        if not os.path.exists(request.file_path):
            raise HTTPException(status_code=404, detail="Plugin file not found")

        # Load plugin using PluginManager
        plugin_manager = PluginManager()
        plugin_instance = plugin_manager.load_plugin_from_file(request.file_path)

        if not plugin_instance:
            raise HTTPException(status_code=400, detail="Failed to load plugin")

        # Check if plugin already exists
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            existing = db.query(Plugin).filter(
                Plugin.name == plugin_instance.metadata.name,
                Plugin.user_id == user.id
            ).first()

            if existing:
                raise HTTPException(status_code=400, detail="Plugin already installed")

            # Create plugin database record
            plugin_record = Plugin(
                user_id=user.id,
                name=plugin_instance.metadata.name,
                version=plugin_instance.metadata.version,
                author=plugin_instance.metadata.author,
                description=plugin_instance.metadata.description,
                plugin_type=plugin_instance.metadata.plugin_type.value,
                status='active' if request.enabled else 'inactive',
                file_path=request.file_path,
                homepage=plugin_instance.metadata.homepage,
                license=plugin_instance.metadata.license,
                supported_languages=','.join(plugin_instance.metadata.supported_languages) if plugin_instance.metadata.supported_languages else '',
                enabled=request.enabled,
                load_count=1
            )

            db.add(plugin_record)
            db.commit()
            db.refresh(plugin_record)

            # Register plugin in PluginManager
            if request.enabled:
                plugin_manager.register_plugin(plugin_instance)

            return {
                "success": True,
                "message": "Plugin loaded successfully",
                "plugin": plugin_record.to_dict()
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load plugin: {str(e)}")


@app.get("/api/plugins/{plugin_id}")
async def get_plugin(
    plugin_id: str,
    user = Depends(get_current_user)
):
    """
    Get details about a specific plugin.
    """
    try:
        from src.core.database import Plugin

        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            plugin = db.query(Plugin).filter(
                Plugin.id == plugin_id,
                Plugin.user_id == user.id
            ).first()

            if not plugin:
                raise HTTPException(status_code=404, detail="Plugin not found")

            return {
                "success": True,
                "plugin": plugin.to_dict()
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get plugin: {str(e)}")


@app.put("/api/plugins/{plugin_id}")
async def update_plugin(
    plugin_id: str,
    request: UpdatePluginRequest,
    user = Depends(get_current_user)
):
    """
    Update plugin configuration or enable/disable it.
    """
    try:
        from src.core.database import Plugin
        from src.core.plugin_manager import PluginManager

        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            plugin = db.query(Plugin).filter(
                Plugin.id == plugin_id,
                Plugin.user_id == user.id
            ).first()

            if not plugin:
                raise HTTPException(status_code=404, detail="Plugin not found")

            # Update fields
            if request.enabled is not None:
                plugin.enabled = request.enabled
                plugin.status = 'active' if request.enabled else 'inactive'

                # Update in PluginManager
                plugin_manager = PluginManager()
                if request.enabled:
                    # Reload and enable plugin
                    plugin_instance = plugin_manager.load_plugin_from_file(plugin.file_path)
                    if plugin_instance:
                        plugin_manager.register_plugin(plugin_instance)
                else:
                    # Disable plugin
                    existing_plugin = plugin_manager.get_plugin(plugin.name)
                    if existing_plugin:
                        plugin_manager.unregister_plugin(plugin.name)

            if request.config is not None:
                plugin.config_json = request.config

            db.commit()
            db.refresh(plugin)

            return {
                "success": True,
                "message": "Plugin updated successfully",
                "plugin": plugin.to_dict()
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update plugin: {str(e)}")


@app.delete("/api/plugins/{plugin_id}")
async def delete_plugin(
    plugin_id: str,
    user = Depends(get_current_user)
):
    """
    Uninstall and delete a plugin.
    """
    try:
        from src.core.database import Plugin
        from src.core.plugin_manager import PluginManager

        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            plugin = db.query(Plugin).filter(
                Plugin.id == plugin_id,
                Plugin.user_id == user.id
            ).first()

            if not plugin:
                raise HTTPException(status_code=404, detail="Plugin not found")

            # Unregister from PluginManager
            plugin_manager = PluginManager()
            plugin_manager.unregister_plugin(plugin.name)

            # Delete from database
            db.delete(plugin)
            db.commit()

            return {
                "success": True,
                "message": "Plugin deleted successfully"
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete plugin: {str(e)}")


@app.get("/api/plugins/{plugin_id}/manifest")
async def get_plugin_manifest(
    plugin_id: str,
    user = Depends(get_current_user)
):
    """
    Get detailed manifest/metadata for a plugin.
    """
    try:
        from src.core.database import Plugin
        from src.core.plugin_manager import PluginManager

        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            plugin = db.query(Plugin).filter(
                Plugin.id == plugin_id,
                Plugin.user_id == user.id
            ).first()

            if not plugin:
                raise HTTPException(status_code=404, detail="Plugin not found")

            # Get plugin instance from manager
            plugin_manager = PluginManager()
            plugin_instance = plugin_manager.get_plugin(plugin.name)

            manifest = plugin.to_dict()

            if plugin_instance:
                # Add additional runtime information
                manifest['hooks'] = list(plugin_instance.hooks.keys())
                manifest['metadata'] = {
                    'name': plugin_instance.metadata.name,
                    'version': plugin_instance.metadata.version,
                    'author': plugin_instance.metadata.author,
                    'description': plugin_instance.metadata.description,
                    'plugin_type': plugin_instance.metadata.plugin_type.value,
                    'supported_languages': plugin_instance.metadata.supported_languages,
                    'homepage': plugin_instance.metadata.homepage,
                    'license': plugin_instance.metadata.license
                }

                # Get rules if it's an analyzer plugin
                if hasattr(plugin_instance, 'get_rules'):
                    manifest['rules'] = plugin_instance.get_rules()

            return {
                "success": True,
                "manifest": manifest
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get manifest: {str(e)}")


# ============================================================================
# Team Management Endpoints
# ============================================================================

@app.post("/api/teams")
async def create_team(request: Request, user=Depends(get_current_user)):
    """Create a new team."""
    try:
        from src.services.team_service import TeamService

        data = await request.json()
        team_service = TeamService()

        result = team_service.create_team(
            name=data['name'],
            slug=data['slug'],
            user_id=user.id,
            description=data.get('description'),
            visibility=data.get('visibility', 'private')
        )

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create team: {str(e)}")


@app.get("/api/teams")
async def get_user_teams(user=Depends(get_current_user)):
    """Get all teams for the current user."""
    try:
        from src.services.team_service import TeamService

        team_service = TeamService()
        teams = team_service.get_user_teams(user.id)

        return {"teams": teams}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get teams: {str(e)}")


@app.get("/api/teams/{team_id}")
async def get_team(team_id: str, user=Depends(get_current_user)):
    """Get team details."""
    try:
        from src.services.team_service import TeamService

        team_service = TeamService()
        team = team_service.get_team(team_id, user.id)

        if not team:
            raise HTTPException(status_code=404, detail="Team not found")

        return team

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get team: {str(e)}")


@app.put("/api/teams/{team_id}")
async def update_team(team_id: str, request: Request, user=Depends(get_current_user)):
    """Update team settings."""
    try:
        from src.services.team_service import TeamService

        data = await request.json()
        team_service = TeamService()

        result = team_service.update_team(team_id, user.id, **data)

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update team: {str(e)}")


@app.delete("/api/teams/{team_id}")
async def delete_team(team_id: str, user=Depends(get_current_user)):
    """Delete a team."""
    try:
        from src.services.team_service import TeamService

        team_service = TeamService()
        result = team_service.delete_team(team_id, user.id)

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete team: {str(e)}")


@app.get("/api/teams/{team_id}/members")
async def get_team_members(team_id: str, user=Depends(get_current_user)):
    """Get all team members."""
    try:
        from src.services.team_service import TeamService

        team_service = TeamService()
        members = team_service.get_team_members(team_id)

        return {"members": members}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get members: {str(e)}")


@app.post("/api/teams/{team_id}/members")
async def add_team_member(team_id: str, request: Request, user=Depends(get_current_user)):
    """Add a member to the team."""
    try:
        from src.services.team_service import TeamService

        data = await request.json()
        team_service = TeamService()

        result = team_service.add_member(
            team_id=team_id,
            user_id=data['user_id'],
            inviter_id=user.id,
            role=data.get('role', 'member')
        )

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add member: {str(e)}")


@app.delete("/api/teams/{team_id}/members/{user_id}")
async def remove_team_member(team_id: str, user_id: str, user=Depends(get_current_user)):
    """Remove a member from the team."""
    try:
        from src.services.team_service import TeamService

        team_service = TeamService()
        result = team_service.remove_member(team_id, user_id, user.id)

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove member: {str(e)}")


@app.put("/api/teams/{team_id}/members/{user_id}/role")
async def update_member_role(team_id: str, user_id: str, request: Request, user=Depends(get_current_user)):
    """Update a member's role."""
    try:
        from src.services.team_service import TeamService

        data = await request.json()
        team_service = TeamService()

        result = team_service.update_member_role(
            team_id=team_id,
            user_id=user_id,
            new_role=data['role'],
            updater_id=user.id
        )

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update role: {str(e)}")


@app.post("/api/teams/{team_id}/invitations")
async def create_team_invitation(team_id: str, request: Request, user=Depends(get_current_user)):
    """Create a team invitation."""
    try:
        from src.services.team_service import TeamService

        data = await request.json()
        team_service = TeamService()

        result = team_service.create_invitation(
            team_id=team_id,
            inviter_id=user.id,
            email=data.get('email'),
            user_id=data.get('user_id'),
            role=data.get('role', 'member'),
            expires_in_days=data.get('expires_in_days', 7)
        )

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create invitation: {str(e)}")


@app.get("/api/teams/{team_id}/invitations")
async def get_team_invitations(team_id: str, status: Optional[str] = None, user=Depends(get_current_user)):
    """Get team invitations."""
    try:
        from src.services.team_service import TeamService

        team_service = TeamService()
        invitations = team_service.get_team_invitations(team_id, status)

        return {"invitations": invitations}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get invitations: {str(e)}")


@app.get("/api/teams/{team_id}/analytics")
async def get_team_analytics(team_id: str, user=Depends(get_current_user)):
    """Get team analytics including issue trends and health metrics."""
    try:
        from src.services.team_analytics_service import team_analytics_service

        analytics = team_analytics_service.get_team_analytics(team_id)
        return analytics

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get team analytics: {str(e)}")


@app.get("/api/teams/{team_id}/repositories")
async def get_team_repositories(team_id: str, user=Depends(get_current_user)):
    """Get all repositories for a team with health metrics."""
    try:
        from src.services.team_analytics_service import team_analytics_service

        repositories = team_analytics_service.get_team_repositories(team_id)
        return {"repositories": repositories}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get team repositories: {str(e)}")


@app.get("/api/teams/{team_id}/leaderboard")
async def get_team_leaderboard(team_id: str, user=Depends(get_current_user)):
    """Get team member leaderboard ranked by contributions."""
    try:
        from src.services.team_analytics_service import team_analytics_service

        leaderboard = team_analytics_service.get_team_leaderboard(team_id)
        return {"leaderboard": leaderboard}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get team leaderboard: {str(e)}")


@app.get("/api/teams/{team_id}/activity")
async def get_team_activity(team_id: str, limit: int = 50, user=Depends(get_current_user)):
    """Get recent team activity feed."""
    try:
        from src.services.team_analytics_service import team_analytics_service

        activity = team_analytics_service.get_team_activity(team_id, limit)
        return {"activity": activity}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get team activity: {str(e)}")


@app.post("/api/invitations/{token}/accept")
async def accept_team_invitation(token: str, user=Depends(get_current_user)):
    """Accept a team invitation."""
    try:
        from src.services.team_service import TeamService

        team_service = TeamService()
        result = team_service.accept_invitation(token, user.id)

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to accept invitation: {str(e)}")


@app.post("/api/invitations/{token}/decline")
async def decline_team_invitation(token: str, user=Depends(get_current_user)):
    """Decline a team invitation."""
    try:
        from src.services.team_service import TeamService

        team_service = TeamService()
        result = team_service.decline_invitation(token, user.id)

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to decline invitation: {str(e)}")


@app.delete("/api/invitations/{invitation_id}")
async def cancel_team_invitation(invitation_id: str, user=Depends(get_current_user)):
    """Cancel a team invitation."""
    try:
        from src.services.team_service import TeamService

        team_service = TeamService()
        result = team_service.cancel_invitation(invitation_id, user.id)

        if not result['success']:
            raise HTTPException(status_code=400, detail=result['error'])

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cancel invitation: {str(e)}")


@app.get("/api/me/invitations")
async def get_my_invitations(user=Depends(get_current_user)):
    """Get pending invitations for the current user."""
    try:
        from src.services.team_service import TeamService

        team_service = TeamService()
        invitations = team_service.get_user_invitations(user.id, user.email)

        return {"invitations": invitations}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get invitations: {str(e)}")


# ============================================================================
# Scheduled Analysis Endpoints
# ============================================================================

@app.post("/api/schedules")
async def create_schedule(request: Request, user=Depends(get_current_user)):
    """Create a new analysis schedule."""
    try:
        data = await request.json()

        with get_db_session() as session:
            schedule_service = ScheduleService(session)
            schedule = schedule_service.create_schedule(
                repository_id=data.get('repository_id'),
                user_id=user.id,
                name=data.get('name'),
                schedule_type=data.get('schedule_type'),
                cron_expression=data.get('cron_expression'),
                interval_minutes=data.get('interval_minutes'),
                description=data.get('description'),
                analyze_all_files=data.get('analyze_all_files', True),
                file_patterns=data.get('file_patterns'),
                enabled_rules=data.get('enabled_rules'),
                severity_threshold=data.get('severity_threshold', 'info'),
                notify_on_completion=data.get('notify_on_completion', False),
                notify_on_issues=data.get('notify_on_issues', True),
                notification_emails=data.get('notification_emails'),
                slack_webhook_url=data.get('slack_webhook_url')
            )

            return schedule

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create schedule: {str(e)}")


@app.get("/api/schedules")
async def list_schedules(
    repository_id: Optional[str] = None,
    enabled_only: bool = False,
    user=Depends(get_current_user)
):
    """List all schedules for the current user."""
    try:
        with get_db_session() as session:
            schedule_service = ScheduleService(session)
            schedules = schedule_service.list_schedules(
                user_id=user.id,
                repository_id=repository_id,
                enabled_only=enabled_only
            )

            return {"schedules": schedules}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list schedules: {str(e)}")


@app.get("/api/schedules/{schedule_id}")
async def get_schedule(schedule_id: str, user=Depends(get_current_user)):
    """Get schedule details."""
    try:
        with get_db_session() as session:
            schedule_service = ScheduleService(session)
            schedule = schedule_service.get_schedule(schedule_id, user_id=user.id)

            if not schedule:
                raise HTTPException(status_code=404, detail="Schedule not found")

            return schedule

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get schedule: {str(e)}")


@app.put("/api/schedules/{schedule_id}")
async def update_schedule(schedule_id: str, request: Request, user=Depends(get_current_user)):
    """Update schedule settings."""
    try:
        data = await request.json()

        with get_db_session() as session:
            schedule_service = ScheduleService(session)
            schedule = schedule_service.update_schedule(
                schedule_id=schedule_id,
                user_id=user.id,
                **data
            )

            return schedule

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update schedule: {str(e)}")


@app.delete("/api/schedules/{schedule_id}")
async def delete_schedule(schedule_id: str, user=Depends(get_current_user)):
    """Delete a schedule."""
    try:
        with get_db_session() as session:
            schedule_service = ScheduleService(session)
            result = schedule_service.delete_schedule(schedule_id, user.id)

            return result

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete schedule: {str(e)}")


@app.post("/api/schedules/{schedule_id}/toggle")
async def toggle_schedule(schedule_id: str, request: Request, user=Depends(get_current_user)):
    """Enable or disable a schedule."""
    try:
        data = await request.json()
        enabled = data.get('enabled', True)

        with get_db_session() as session:
            schedule_service = ScheduleService(session)
            schedule = schedule_service.toggle_schedule(schedule_id, user.id, enabled)

            return schedule

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to toggle schedule: {str(e)}")


@app.post("/api/schedules/{schedule_id}/trigger")
async def trigger_schedule(schedule_id: str, user=Depends(get_current_user)):
    """Manually trigger a schedule to run immediately."""
    try:
        with get_db_session() as session:
            schedule_service = ScheduleService(session)
            run = schedule_service.trigger_schedule(schedule_id, user.id)

            return run

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to trigger schedule: {str(e)}")


@app.get("/api/schedules/{schedule_id}/runs")
async def get_schedule_runs(
    schedule_id: str,
    status: Optional[str] = None,
    limit: int = 50,
    user=Depends(get_current_user)
):
    """Get runs for a specific schedule."""
    try:
        with get_db_session() as session:
            schedule_service = ScheduleService(session)

            # Verify user has access to this schedule
            schedule = schedule_service.get_schedule(schedule_id, user_id=user.id)
            if not schedule:
                raise HTTPException(status_code=404, detail="Schedule not found")

            runs = schedule_service.list_runs(
                schedule_id=schedule_id,
                status=status,
                limit=limit
            )

            return {"runs": runs}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get runs: {str(e)}")


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str, user=Depends(get_current_user)):
    """Get run details."""
    try:
        with get_db_session() as session:
            schedule_service = ScheduleService(session)
            run = schedule_service.get_run(run_id)

            if not run:
                raise HTTPException(status_code=404, detail="Run not found")

            # Verify user has access to this run's schedule
            schedule = schedule_service.get_schedule(run['schedule_id'], user_id=user.id)
            if not schedule:
                raise HTTPException(status_code=404, detail="Schedule not found")

            return run

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get run: {str(e)}")


# ============================================================================
# Run server
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    host = os.getenv('HOST', '0.0.0.0')
    port = int(os.getenv('PORT', '8000'))

    print(f"🚀 Starting AI Code Review Assistant on http://{host}:{port}")
    print(f"📖 API Docs: http://{host}:{port}/docs")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )
