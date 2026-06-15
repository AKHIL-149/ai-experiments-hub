"""
FastAPI server for AI Code Review Assistant
"""

import os
import tempfile
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, Response, Cookie, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List

from src.core.database import DatabaseManager
from src.core.auth_manager import AuthManager, UserRole
from src.services.code_analyzer_service import CodeAnalyzerService
from src.workers.analysis_worker import (
    analyze_file_task,
    get_analysis_results,
    get_all_cached_analyses
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

# CORS configuration
allowed_origins = os.getenv('ALLOWED_ORIGINS', 'http://localhost:8000').split(',')
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize database
db_url = os.getenv('DATABASE_URL')
db_manager = DatabaseManager(db_url)

# Session configuration
SESSION_TTL_DAYS = int(os.getenv('SESSION_TTL_DAYS', '30'))
COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'

# Mount static files (will add later)
# app.mount("/static", StaticFiles(directory="static"), name="static")


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
# Root Endpoint
# ============================================================================

@app.get("/", response_class=HTMLResponse)
async def root():
    """Root endpoint - serve dashboard HTML"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI Code Review Assistant</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                max-width: 800px;
                margin: 50px auto;
                padding: 20px;
                background: #f5f5f5;
            }
            .container {
                background: white;
                padding: 40px;
                border-radius: 8px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            h1 { color: #333; margin-top: 0; }
            .status { color: #28a745; font-weight: bold; }
            ul { line-height: 2; }
            code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🔍 AI Code Review Assistant</h1>
            <p class="status">✓ Server Running</p>

            <h2>API Endpoints</h2>
            <ul>
                <li><code>POST /api/auth/register</code> - Register new user</li>
                <li><code>POST /api/auth/login</code> - Login</li>
                <li><code>POST /api/auth/logout</code> - Logout</li>
                <li><code>GET /api/auth/me</code> - Get current user</li>
                <li><code>GET /docs</code> - API Documentation (Swagger)</li>
            </ul>

            <p style="margin-top: 40px; color: #666;">
                Project 13 - Week 1 Implementation
            </p>
        </div>
    </body>
    </html>
    """


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


# ============================================================================
# Issues Endpoints
# ============================================================================

@app.get("/api/issues")
async def list_issues(
    severity: Optional[str] = None,
    category: Optional[str] = None,
    file_path: Optional[str] = None,
    job_id: Optional[str] = None,
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
    - limit: Maximum number of issues to return (default 50)
    - offset: Number of issues to skip (default 0)
    """
    all_issues = []

    # Get all cached analyses
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

    Note: This implementation uses in-memory cache.
    Issue IDs are synthetic based on position in results.
    """
    # Since we're using in-memory cache, find issue across all analyses
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
