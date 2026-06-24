# API Reference

Complete API reference for the AI Code Review & Refactoring Assistant.

## Table of Contents

- [Base URL](#base-url)
- [Authentication](#authentication)
- [Rate Limiting](#rate-limiting)
- [Error Handling](#error-handling)
- [Pagination](#pagination)
- [API Endpoints](#api-endpoints)
  - [Authentication](#authentication-endpoints)
  - [Repositories](#repository-endpoints)
  - [Pull Requests](#pull-request-endpoints)
  - [Analysis](#analysis-endpoints)
  - [Issues](#issue-endpoints)
  - [Refactoring](#refactoring-endpoints)
  - [Teams](#team-endpoints)
  - [Analytics](#analytics-endpoints)
  - [Webhooks](#webhook-endpoints)

## Base URL

```
# Development
http://localhost:8000

# Production
https://your-domain.com
```

## Authentication

### Session-Based Authentication

The API uses session-based authentication with HTTP-only cookies.

**Login Flow:**
1. POST `/api/auth/login` with credentials
2. Receive `session_token` cookie
3. Include cookie in subsequent requests
4. Session lasts 30 days (configurable)

**Example:**
```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "password123"
  }' \
  -c cookies.txt

# Use session
curl http://localhost:8000/api/repositories \
  -b cookies.txt
```

### Headers

Required headers for authenticated requests:

```
Cookie: session_token=<session_token_value>
Content-Type: application/json
```

Optional headers:

```
X-Correlation-ID: <unique_request_id>
User-Agent: MyApp/1.0
```

## Rate Limiting

API endpoints are rate-limited to prevent abuse.

**Global Limits:**
- 100 requests per minute (default)
- 5,000 requests per hour

**Endpoint-Specific Limits:**
- `/api/auth/login`: 5 requests per minute
- `/api/auth/register`: 5 requests per 5 minutes
- `/api/analyze/*`: 10 requests per minute

**Rate Limit Headers:**

Response includes rate limit information:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1234567890
Retry-After: 60
```

**Rate Limit Exceeded:**

```json
{
  "error": "Rate limit exceeded",
  "detail": "Too many requests. Retry after 60 seconds.",
  "retry_after": 60
}
```

**Status Code:** `429 Too Many Requests`

## Error Handling

### Error Response Format

All errors follow a consistent format:

```json
{
  "error": "Error type",
  "detail": "Detailed error message",
  "code": "ERROR_CODE",
  "correlation_id": "uuid-v4-string",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### HTTP Status Codes

- `200 OK`: Success
- `201 Created`: Resource created
- `400 Bad Request`: Invalid input
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource not found
- `409 Conflict`: Resource conflict (duplicate)
- `422 Unprocessable Entity`: Validation error
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error
- `503 Service Unavailable`: Service temporarily unavailable

### Common Errors

**Validation Error:**
```json
{
  "error": "Validation Error",
  "detail": [
    {
      "field": "email",
      "message": "Invalid email format"
    }
  ]
}
```

**Authentication Error:**
```json
{
  "error": "Unauthorized",
  "detail": "Invalid credentials",
  "code": "AUTH_FAILED"
}
```

**Resource Not Found:**
```json
{
  "error": "Not Found",
  "detail": "Repository with id 123 not found",
  "code": "RESOURCE_NOT_FOUND"
}
```

## Pagination

List endpoints support pagination using offset/limit or cursor-based pagination.

**Query Parameters:**
- `page`: Page number (1-indexed)
- `per_page`: Items per page (default: 50, max: 100)
- `offset`: Skip N items
- `limit`: Return N items

**Response Format:**
```json
{
  "items": [...],
  "total": 150,
  "page": 1,
  "per_page": 50,
  "pages": 3,
  "has_next": true,
  "has_prev": false,
  "next_page": 2,
  "prev_page": null
}
```

**Example:**
```bash
# Page 1
curl "http://localhost:8000/api/issues?page=1&per_page=20"

# Page 2
curl "http://localhost:8000/api/issues?page=2&per_page=20"
```

## API Endpoints

### Authentication Endpoints

#### POST /api/auth/register

Register a new user account.

**Request:**
```json
{
  "username": "john_doe",
  "email": "john@example.com",
  "password": "SecurePass123!"
}
```

**Response:** `201 Created`
```json
{
  "id": 1,
  "username": "john_doe",
  "email": "john@example.com",
  "role": "USER",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Errors:**
- `409 Conflict`: Username or email already exists
- `422 Unprocessable Entity`: Validation error

---

#### POST /api/auth/login

Authenticate and create session.

**Request:**
```json
{
  "username": "john_doe",
  "password": "SecurePass123!"
}
```

**Response:** `200 OK`
```json
{
  "message": "Login successful",
  "user": {
    "id": 1,
    "username": "john_doe",
    "email": "john@example.com",
    "role": "USER"
  }
}
```

Sets `session_token` HTTP-only cookie.

**Errors:**
- `401 Unauthorized`: Invalid credentials
- `429 Too Many Requests`: Rate limit exceeded

---

#### POST /api/auth/logout

End session and clear cookie.

**Response:** `200 OK`
```json
{
  "message": "Logout successful"
}
```

---

#### GET /api/auth/me

Get current user information.

**Response:** `200 OK`
```json
{
  "id": 1,
  "username": "john_doe",
  "email": "john@example.com",
  "role": "USER",
  "created_at": "2024-01-15T10:30:00Z",
  "last_login": "2024-01-20T15:45:00Z"
}
```

**Errors:**
- `401 Unauthorized`: Not authenticated

---

### Repository Endpoints

#### POST /api/repositories

Add a new repository.

**Request:**
```json
{
  "name": "My Project",
  "github_url": "https://github.com/user/repo",
  "github_token": "ghp_token_here",
  "default_branch": "main"
}
```

**Response:** `201 Created`
```json
{
  "id": 1,
  "name": "My Project",
  "github_url": "https://github.com/user/repo",
  "default_branch": "main",
  "status": "cloning",
  "created_at": "2024-01-15T10:30:00Z",
  "last_synced_at": null
}
```

**Errors:**
- `409 Conflict`: Repository already exists
- `422 Unprocessable Entity`: Invalid GitHub URL

---

#### GET /api/repositories

List all repositories for current user.

**Query Parameters:**
- `page`: Page number (default: 1)
- `per_page`: Items per page (default: 50)
- `status`: Filter by status (cloning, ready, error)

**Response:** `200 OK`
```json
{
  "items": [
    {
      "id": 1,
      "name": "My Project",
      "github_url": "https://github.com/user/repo",
      "default_branch": "main",
      "status": "ready",
      "health_score": 85.5,
      "total_files": 150,
      "lines_of_code": 12500,
      "last_synced_at": "2024-01-20T12:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 50
}
```

---

#### GET /api/repositories/{id}

Get repository details.

**Response:** `200 OK`
```json
{
  "id": 1,
  "name": "My Project",
  "github_url": "https://github.com/user/repo",
  "default_branch": "main",
  "status": "ready",
  "health_score": 85.5,
  "total_files": 150,
  "lines_of_code": 12500,
  "created_at": "2024-01-15T10:30:00Z",
  "last_synced_at": "2024-01-20T12:00:00Z",
  "clone_path": "/app/data/repos/1"
}
```

**Errors:**
- `404 Not Found`: Repository not found

---

#### POST /api/repositories/{id}/sync

Sync repository with GitHub (fetch latest commits).

**Response:** `200 OK`
```json
{
  "message": "Sync started",
  "job_id": "abc123-def456",
  "status": "pending"
}
```

Track progress via `/api/jobs/{job_id}`

---

#### DELETE /api/repositories/{id}

Delete repository and all associated data.

**Response:** `200 OK`
```json
{
  "message": "Repository deleted successfully"
}
```

**Note:** This only deletes local data, not the GitHub repository.

---

### Pull Request Endpoints

#### POST /api/prs

Import pull request from GitHub.

**Request:**
```json
{
  "repository_id": 1,
  "pr_number": 42
}
```

**Response:** `201 Created`
```json
{
  "id": 1,
  "pr_number": 42,
  "title": "Fix authentication bug",
  "author": "john_doe",
  "source_branch": "fix/auth",
  "target_branch": "main",
  "status": "open",
  "analysis_job_id": "job_123",
  "created_at": "2024-01-15T10:30:00Z"
}
```

Analysis starts automatically in background.

---

#### GET /api/prs

List pull requests.

**Query Parameters:**
- `repository_id`: Filter by repository
- `status`: Filter by status (open, closed, merged)
- `author`: Filter by author
- `page`, `per_page`: Pagination

**Response:** `200 OK`
```json
{
  "items": [
    {
      "id": 1,
      "pr_number": 42,
      "title": "Fix authentication bug",
      "author": "john_doe",
      "status": "open",
      "health_score": 90.5,
      "total_issues": 3,
      "critical_issues": 0,
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 10,
  "page": 1,
  "per_page": 50
}
```

---

#### GET /api/prs/{id}

Get pull request details.

**Response:** `200 OK`
```json
{
  "id": 1,
  "pr_number": 42,
  "title": "Fix authentication bug",
  "description": "Fixes #123",
  "author": "john_doe",
  "source_branch": "fix/auth",
  "target_branch": "main",
  "status": "open",
  "health_score": 90.5,
  "total_issues": 3,
  "by_severity": {
    "critical": 0,
    "error": 1,
    "warning": 2,
    "info": 0
  },
  "files_changed": [
    {
      "path": "src/auth.py",
      "additions": 15,
      "deletions": 8,
      "issues_count": 2
    }
  ],
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

#### GET /api/prs/{id}/review

Get complete PR review.

**Response:** `200 OK`
```json
{
  "pr_id": 1,
  "overall_score": 90.5,
  "grade": "A",
  "summary": "Good code quality with minor issues",
  "issues": [
    {
      "id": 1,
      "severity": "warning",
      "category": "complexity",
      "title": "High cyclomatic complexity",
      "description": "Function has complexity of 12 (threshold: 10)",
      "file_path": "src/auth.py",
      "line_number": 45,
      "code_snippet": "def authenticate(...):",
      "recommendation": "Extract nested logic into separate functions"
    }
  ],
  "files": [
    {
      "path": "src/auth.py",
      "issues_count": 2,
      "diff": "...",
      "issues": [...]
    }
  ]
}
```

---

#### POST /api/prs/{id}/review/submit

Submit review to GitHub.

**Request:**
```json
{
  "approved": true,
  "summary": "Code looks good with minor suggestions",
  "post_to_github": true
}
```

**Response:** `200 OK`
```json
{
  "message": "Review submitted successfully",
  "github_review_id": 12345,
  "review_url": "https://github.com/user/repo/pull/42#pullrequestreview-12345"
}
```

---

### Analysis Endpoints

#### POST /api/analyze/file

Analyze a single uploaded file.

**Request:** `multipart/form-data`
- `file`: File to analyze
- `language`: (optional) Language hint
- `analyzers`: (optional) Comma-separated analyzer IDs

**Response:** `200 OK`
```json
{
  "success": true,
  "file_path": "uploaded_file.py",
  "report": {
    "total_issues": 5,
    "by_severity": {
      "critical": 1,
      "error": 2,
      "warning": 2,
      "info": 0
    },
    "issues": [
      {
        "rule_id": "SEC001",
        "severity": "critical",
        "category": "security",
        "title": "Hardcoded secret detected",
        "description": "Password should not be hardcoded",
        "line_number": 10,
        "code_snippet": 'password = "admin123"',
        "recommendation": "Use environment variables"
      }
    ],
    "health_score": {
      "overall_score": 75.5,
      "grade": "C"
    }
  }
}
```

---

#### POST /api/analyze/code

Analyze code snippet.

**Request:**
```json
{
  "code": "import os\npassword = 'secret123'\n",
  "filename": "test.py",
  "language": "python",
  "analyzers": ["security", "smell"]
}
```

**Response:** Same as `/api/analyze/file`

---

#### POST /api/analyze/repository

Analyze entire repository.

**Request:**
```json
{
  "repository_id": 1,
  "files": "**/*.py",
  "analyzers": ["security", "smell", "complexity"],
  "severity_threshold": "warning"
}
```

**Response:** `202 Accepted`
```json
{
  "message": "Analysis started",
  "job_id": "job_abc123",
  "status_url": "/api/jobs/job_abc123"
}
```

Track progress via WebSocket or polling `/api/jobs/{job_id}`

---

#### GET /api/jobs/{job_id}

Get analysis job status.

**Response:** `200 OK`
```json
{
  "job_id": "job_abc123",
  "status": "completed",
  "progress": 100,
  "started_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:35:00Z",
  "result": {
    "total_files": 50,
    "files_analyzed": 50,
    "total_issues": 25,
    "by_severity": {
      "critical": 2,
      "error": 8,
      "warning": 15,
      "info": 0
    }
  }
}
```

**Status values:**
- `pending`: Waiting to start
- `running`: In progress
- `completed`: Finished successfully
- `failed`: Error occurred

---

### Issue Endpoints

#### GET /api/issues

List issues with filtering.

**Query Parameters:**
- `repository_id`: Filter by repository
- `pr_id`: Filter by pull request
- `severity`: Filter by severity (critical, error, warning, info)
- `category`: Filter by category (security, smell, complexity)
- `status`: Filter by status (open, dismissed, fixed)
- `file_path`: Filter by file pattern (glob)
- `from_date`, `to_date`: Date range filter
- `page`, `per_page`: Pagination

**Response:** `200 OK`
```json
{
  "items": [
    {
      "id": 1,
      "rule_id": "SEC001",
      "severity": "critical",
      "category": "security",
      "title": "Hardcoded secret detected",
      "file_path": "src/config.py",
      "line_number": 15,
      "status": "open",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ],
  "total": 100,
  "page": 1,
  "per_page": 50
}
```

---

#### GET /api/issues/{id}

Get issue details.

**Response:** `200 OK`
```json
{
  "id": 1,
  "rule_id": "SEC001",
  "severity": "critical",
  "category": "security",
  "title": "Hardcoded secret detected",
  "description": "Hardcoded passwords pose a security risk",
  "file_path": "src/config.py",
  "line_number": 15,
  "code_snippet": "password = \"admin123\"",
  "recommendation": "Use environment variables for sensitive data",
  "confidence": 95.0,
  "status": "open",
  "refactoring": {
    "type": "security_fix",
    "original_code": "password = \"admin123\"",
    "refactored_code": "password = os.getenv('DB_PASSWORD')",
    "explanation": "Load password from environment variable"
  },
  "created_at": "2024-01-15T10:30:00Z"
}
```

---

#### POST /api/issues/{id}/dismiss

Dismiss an issue.

**Request:**
```json
{
  "reason": "false_positive",
  "comment": "This is a test credential, not production"
}
```

**Response:** `200 OK`
```json
{
  "message": "Issue dismissed successfully"
}
```

**Reasons:**
- `false_positive`
- `wont_fix`
- `already_fixed`
- `not_applicable`

---

### Refactoring Endpoints

#### GET /api/refactorings/{id}

Get refactoring suggestion.

**Response:** `200 OK`
```json
{
  "id": 1,
  "issue_id": 1,
  "type": "extract_method",
  "original_code": "def process():\n    # 50 lines...",
  "refactored_code": "def process():\n    validate_input()\n    transform_data()\n    save_result()",
  "diff": "--- original\n+++ refactored\n...",
  "explanation": "Extracted repeated logic into separate functions",
  "confidence": 85.0,
  "estimated_time_hours": 1.5
}
```

---

#### POST /api/refactorings/{id}/accept

Apply refactoring to code.

**Response:** `200 OK`
```json
{
  "message": "Refactoring applied successfully",
  "file_updated": "src/processor.py"
}
```

**Warning:** Creates backup before applying!

---

### Team Endpoints

#### POST /api/teams

Create a team (Admin only).

**Request:**
```json
{
  "name": "Engineering Team",
  "description": "Backend development team"
}
```

**Response:** `201 Created`
```json
{
  "id": 1,
  "name": "Engineering Team",
  "description": "Backend development team",
  "created_at": "2024-01-15T10:30:00Z",
  "members_count": 1
}
```

---

#### GET /api/teams

List teams.

**Response:** `200 OK`
```json
{
  "items": [
    {
      "id": 1,
      "name": "Engineering Team",
      "description": "Backend development team",
      "members_count": 5,
      "repositories_count": 10,
      "role": "admin"
    }
  ]
}
```

---

#### POST /api/teams/{id}/invite

Invite member to team.

**Request:**
```json
{
  "email": "john@example.com",
  "role": "reviewer"
}
```

**Response:** `200 OK`
```json
{
  "message": "Invitation sent successfully",
  "invite_id": "inv_abc123"
}
```

**Roles:**
- `admin`: Full team management
- `reviewer`: Can review and comment
- `viewer`: Read-only access

---

### Analytics Endpoints

#### GET /api/analytics/health/{repository_id}

Get repository health score.

**Response:** `200 OK`
```json
{
  "repository_id": 1,
  "score": 85.5,
  "grade": "B",
  "trend": "improving",
  "details": {
    "total_issues": 25,
    "critical_issues": 0,
    "issues_per_kloc": 2.0,
    "period_comparison": {
      "previous_score": 82.0,
      "change": +3.5,
      "change_percent": 4.3
    }
  }
}
```

---

#### GET /api/analytics/trends

Get quality trends over time.

**Query Parameters:**
- `repository_id`: Repository ID
- `granularity`: daily, weekly, monthly
- `from_date`, `to_date`: Date range

**Response:** `200 OK`
```json
{
  "granularity": "daily",
  "data_points": [
    {
      "date": "2024-01-15",
      "total_issues": 25,
      "critical_issues": 0,
      "health_score": 85.5,
      "issues_per_kloc": 2.0
    }
  ],
  "summary": {
    "trend": "improving",
    "avg_health_score": 84.2,
    "total_issues_fixed": 15
  }
}
```

---

#### GET /api/analytics/technical-debt

Get technical debt estimation.

**Query Parameters:**
- `repository_id`: Repository ID

**Response:** `200 OK`
```json
{
  "total_debt_hours": 45.5,
  "total_debt_cost": 4550.0,
  "debt_ratio": 3.64,
  "debt_level": "medium",
  "by_category": {
    "security": {
      "issues": 5,
      "hours": 20.0,
      "cost": 2000.0
    },
    "smell": {
      "issues": 15,
      "hours": 15.0,
      "cost": 1500.0
    },
    "complexity": {
      "issues": 10,
      "hours": 10.5,
      "cost": 1050.0
    }
  },
  "recommendations": [
    "Fix 5 critical security issues first (20 hours)",
    "Refactor 3 god classes (8 hours)",
    "Reduce complexity in auth module (6 hours)"
  ]
}
```

---

### Webhook Endpoints

#### POST /api/webhooks/github

GitHub webhook receiver.

**Headers:**
```
X-GitHub-Event: pull_request
X-Hub-Signature-256: sha256=signature_here
```

**Request:** GitHub webhook payload

**Response:** `200 OK`
```json
{
  "message": "Webhook processed",
  "action": "pull_request.opened",
  "pr_id": 1,
  "analysis_job_id": "job_abc123"
}
```

**Supported Events:**
- `pull_request.opened`
- `pull_request.synchronize`
- `pull_request.reopened`

---

## OpenAPI/Swagger Documentation

Interactive API documentation is available at:

```
http://localhost:8000/docs
```

Features:
- Full API specification
- Try it out functionality
- Request/response examples
- Schema definitions
- Authentication testing

Alternative ReDoc format:

```
http://localhost:8000/redoc
```

---

## Code Examples

### Python

```python
import requests

# Login
response = requests.post(
    "http://localhost:8000/api/auth/login",
    json={"username": "admin", "password": "password123"}
)
cookies = response.cookies

# List repositories
response = requests.get(
    "http://localhost:8000/api/repositories",
    cookies=cookies
)
repositories = response.json()["items"]

# Analyze file
with open("test.py", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/analyze/file",
        files={"file": f},
        cookies=cookies
    )
result = response.json()
```

### JavaScript

```javascript
// Login
const response = await fetch("http://localhost:8000/api/auth/login", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    username: "admin",
    password: "password123"
  }),
  credentials: "include"  // Include cookies
});

// List repositories
const repos = await fetch("http://localhost:8000/api/repositories", {
  credentials: "include"
}).then(r => r.json());

// Analyze code
const analysis = await fetch("http://localhost:8000/api/analyze/code", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  credentials: "include",
  body: JSON.stringify({
    code: "import os\npassword = 'secret'",
    filename: "test.py",
    language: "python"
  })
}).then(r => r.json());
```

### cURL

```bash
# Login and save cookies
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"password123"}' \
  -c cookies.txt

# Use session
curl http://localhost:8000/api/repositories \
  -b cookies.txt

# Analyze file
curl -X POST http://localhost:8000/api/analyze/file \
  -F "file=@test.py" \
  -b cookies.txt
```

---

## WebSocket (Server-Sent Events)

Real-time progress updates for long-running operations.

**Connect:**
```javascript
const eventSource = new EventSource(
  `http://localhost:8000/api/jobs/${jobId}/stream`
);

eventSource.addEventListener("progress", (event) => {
  const data = JSON.parse(event.data);
  console.log(`Progress: ${data.progress}%`);
});

eventSource.addEventListener("complete", (event) => {
  const data = JSON.parse(event.data);
  console.log("Analysis complete:", data.result);
  eventSource.close();
});

eventSource.addEventListener("error", (event) => {
  console.error("Error:", event);
  eventSource.close();
});
```

---

**For more information, see:**
- [User Guide](USER_GUIDE.md)
- [Deployment Guide](DEPLOYMENT.md)
- [Troubleshooting](TROUBLESHOOTING.md)
