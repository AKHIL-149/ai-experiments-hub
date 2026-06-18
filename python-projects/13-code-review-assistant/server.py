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
    CodeFile, Issue, Refactoring, RefactoringStatus
)
from src.core.auth_manager import AuthManager, UserRole
from src.services.code_analyzer_service import CodeAnalyzerService
from src.services.pr_service import PullRequestService
from src.workers.analysis_worker import (
    analyze_file_task,
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
