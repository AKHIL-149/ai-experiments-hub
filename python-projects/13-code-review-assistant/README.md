# AI Code Review & Refactoring Assistant

**Version**: 0.5.8 (GitHub App Integration UI)
**Status**: Production-Ready with Multi-Language Support & GitHub App Management UI

An intelligent code review system that analyzes Python, JavaScript/TypeScript, Java, Go, and Rust code, detects issues, suggests refactorings, and integrates with GitHub pull requests. Features async processing, AI-powered insights, real-time analytics, intelligent language auto-detection, webhook-triggered automatic PR analysis, and comprehensive production monitoring.

## 🚀 Features

### Core Analysis
- **Multi-Language Support**: Python, JavaScript, TypeScript, JSX, TSX, Java, Go, Rust
- **Intelligent Auto-Detection**:
  - **Extension-based**: Automatic parser selection from file extension
  - **Content-based**: Pattern matching on imports, keywords, and syntax
  - **Shebang detection**: Script language detection from `#!/usr/bin/env` lines
  - **Scoring algorithm**: Selects language with most pattern matches
  - **Fallback support**: Graceful degradation when extension is unknown
- **Python Analysis**: Security vulnerabilities, code smells, complexity metrics
- **JavaScript/TypeScript Analysis**: ES6+, React/JSX support, async/await patterns
- **Java Analysis**: Spring Framework patterns, Javadoc extraction, enterprise security rules
- **Go Analysis**: Structs, interfaces, goroutines, package documentation
- **Rust Analysis**: Ownership patterns, traits, impl blocks, derive macros
- **22+ Analysis Rules**: SQL injection, hardcoded secrets, long methods, deep nesting, XXE, weak cryptography
- **AI-Powered Insights**: Ollama/Anthropic/OpenAI integration for explanations and refactorings
- **Severity Levels**: Info, Warning, Error, Critical with confidence scoring

### GitHub Integration
- **Repository Management**: Clone, sync, and manage GitHub repositories
- **Pull Request Reviews**: Automatic PR analysis with inline comments
- **Webhook Infrastructure**: Real-time PR analysis triggered by GitHub events
  - GitHub App authentication with JWT tokens
  - HMAC-SHA256 signature verification for security
  - Installation token caching and automatic refresh
  - Event-driven architecture (PR opened, synchronized, reopened)
- **Diff Viewer**: Unified and split diff visualization with syntax highlighting
- **Review Posting**: Post comprehensive reviews back to GitHub

### Analytics & Insights
- **Health Score**: 0-100 score with A-F grading based on issue severity
- **Trend Analysis**: Time-series issue tracking (daily/weekly/monthly)
- **Repository Metrics**: Lines of code, issue density, complexity averages
- **AI Insights**: Actionable recommendations based on code patterns
- **Export**: JSON and CSV export for all analytics

### Advanced UI Components
- **Dashboard**: Real-time health scores with Chart.js, activity feed, issue trends
- **Issue Browser**: Advanced filtering (severity, category, file, date range), saved presets
- **Diff Viewer**: Syntax-highlighted unified/split diff views
- **Progress Tracker**: Real-time progress with SSE and polling fallback
- **Settings Panel**: Configurable rules, thresholds, AI providers, theme switching

### Production Features
- **Notifications**: In-app notification system with 10 types, preferences, event-driven architecture
- **Logging**: Structured logging with correlation IDs, sensitive data masking, export capabilities
- **Caching**: Redis caching with in-memory fallback, TTL support, cache decorators
- **Performance**: Database indexes (9 composite indexes), query optimization
- **Authentication**: Session-based auth with RBAC (User/Admin roles)
- **Async Processing**: Celery + Redis for background jobs

## 📊 Test Coverage

- **Total Tests**: 846+
- **Coverage**: 90%+
- **Test Suites**:
  - Parser tests: 30 Java tests, 44 JavaScript/TypeScript tests, 32 registry tests (100% passing)
  - Analyzer tests: 22 Java analyzer tests, 30 JavaScript analyzer tests (100% passing)
  - Service tests: 100+ tests (100% passing)
  - Webhook infrastructure tests: 25 tests (100% passing)
  - Webhook worker tests: 8 tests (100% passing)
  - GitHub App UI tests: 13 tests (endpoint coverage)
  - Endpoint tests: 200+ tests (auth requirement verified)
  - E2E tests: 15 comprehensive workflow tests
  - Integration tests: 365+ tests

## 🏗️ Architecture

### Tech Stack
- **Backend**: FastAPI 0.104.1, SQLAlchemy 2.0.23, Python 3.10+
- **Task Queue**: Celery 5.3.4, Redis 5.0.1
- **Database**: SQLite (dev), PostgreSQL (production ready)
- **AI**: Anthropic Claude, OpenAI GPT, Ollama (local)
- **Frontend**: Vanilla JavaScript ES6+, Chart.js 4.4.0, Highlight.js 11.9.0
- **Analysis**: Python AST, Radon (complexity), custom rule engines

### Database Schema (10 Models)
1. **User** - Authentication & authorization with RBAC
2. **UserSession** - Session management with TTL
3. **Repository** - GitHub repo tracking and sync
4. **PullRequest** - PR metadata, status, and metrics
5. **CodeFile** - File analysis results and parsed data
6. **AnalysisJob** - Async job tracking with Celery
7. **Issue** - Detected code issues with AI explanations
8. **Refactoring** - Refactoring suggestions with diffs
9. **Review** - PR review summaries and scores
10. **ReviewComment** - Individual review comments

## 🚦 Quick Start

### Prerequisites
- Python 3.10+
- Redis (optional, for caching/Celery)
- Git

### 1. Install Dependencies
```bash
cd python-projects/13-code-review-assistant
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
# Edit .env with your settings (see Configuration section)
```

### 3. Start Services

**Terminal 1 - Redis** (optional):
```bash
redis-server
```

**Terminal 2 - Celery Worker** (optional):
```bash
celery -A celery_app worker --loglevel=info
```

**Terminal 3 - FastAPI Server**:
```bash
python server.py
```

### 4. Access Application
Open [http://localhost:8000](http://localhost:8000)

**Default Admin Account**:
- Username: `admin`
- Password: `admin123` (⚠️ change immediately!)

## ⚙️ Configuration

### Environment Variables (.env)
```env
# Server
HOST=0.0.0.0
PORT=8000
ALLOWED_ORIGINS=http://localhost:8000

# Database
DATABASE_URL=sqlite:///./data/database.db
# PostgreSQL: postgresql://user:pass@localhost/dbname

# Authentication
SESSION_TTL_DAYS=30
COOKIE_SECURE=false  # Set true for HTTPS

# GitHub Integration
GITHUB_TOKEN=ghp_your_token_here
GITHUB_WEBHOOK_SECRET=your_secret

# Git
GIT_CLONE_DIR=./data/repos

# AI/LLM (Choose one)
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...

# Analysis Thresholds
COMPLEXITY_THRESHOLD_WARN=10
COMPLEXITY_THRESHOLD_ERROR=15

# Celery/Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
REDIS_URL=redis://localhost:6379/2
```

## 📖 Usage

### Web Interface

#### Analyze File
1. Navigate to [http://localhost:8000](http://localhost:8000)
2. Click "Upload File" or drag-and-drop Python file
3. View analysis results with severity, AI explanations
4. Accept refactoring suggestions

#### GitHub PR Review
1. Add repository: Enter GitHub URL + token
2. Import PR: Enter PR number
3. System analyzes changed files automatically
4. View comprehensive review
5. (Optional) Post review back to GitHub

#### Analytics Dashboard
1. View health score (0-100, A-F grade)
2. Explore issue trends over time
3. Filter by severity, category, date range
4. Export data as JSON or CSV

### API Usage

#### Authentication
```bash
# Register
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"user","email":"user@example.com","password":"pass123"}'

# Login (returns session_token)
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user","password":"pass123"}'

export TOKEN="your_session_token"
```

#### Analyze Code
```bash
# Upload file
curl -X POST http://localhost:8000/api/analyze \
  -H "Cookie: session_token=$TOKEN" \
  -F "file=@test.py"

# Get analytics
curl http://localhost:8000/api/analytics/health-score \
  -H "Cookie: session_token=$TOKEN"
```

### Language Auto-Detection

The system intelligently detects programming languages using multiple strategies:

#### 1. Extension-Based Detection (Primary)
```python
from src.parsers import get_registry

registry = get_registry()

# Detects Python from .py extension
language = registry.detect_language('script.py')  # Returns: 'python'

# Detects JavaScript from .js/.jsx/.ts/.tsx
language = registry.detect_language('App.tsx')    # Returns: 'javascript'

# Detects Java from .java
language = registry.detect_language('Main.java')  # Returns: 'java'
```

#### 2. Content-Based Detection (Fallback)
```python
# Python code without extension
code = """
import os
from pathlib import Path

def main():
    pass
"""
language = registry.detect_language_from_content(code)  # Returns: 'python'

# JavaScript code detection
code = """
import React from 'react';

export default function App() {
    return <div>Hello</div>;
}
"""
language = registry.detect_language_from_content(code)  # Returns: 'javascript'
```

#### 3. Shebang Detection (Scripts)
```python
# Python script
code = """#!/usr/bin/env python3
print("Hello")
"""
language = registry.detect_language_from_content(code)  # Returns: 'python'

# Node.js script
code = """#!/usr/bin/env node
console.log('Hello');
"""
language = registry.detect_language_from_content(code)  # Returns: 'javascript'
```

#### 4. Auto-Detection During Parsing
```python
# Automatically detects language and parses
parsed_module = registry.parse_file('script')  # No extension, uses content

# Disable auto-detection to force extension-based only
parsed_module = registry.parse_file('script.py', auto_detect=False)
```

#### Registry Statistics
```python
# Get parser information
info = registry.get_parser_info()
# Returns: {
#   'python': {'language': 'python', 'extensions': ['.py'], ...},
#   'javascript': {'language': 'javascript', 'extensions': ['.js', '.jsx', ...], ...},
#   ...
# }

# Get parsing statistics
stats = registry.get_statistics()
# Returns: {'python': 45, 'javascript': 23, 'java': 12, ...}

# Get comprehensive stats
total_langs, total_exts, parse_counts = registry.get_language_stats()
# Returns: (5, 12, {'python': 45, 'javascript': 23, ...})

# Reset statistics
registry.reset_statistics()
```

#### Supported Languages & Extensions
- **Python**: `.py`, `.pyw`
- **JavaScript/TypeScript**: `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`
- **Java**: `.java`
- **Go**: `.go`
- **Rust**: `.rs`

## 📚 API Reference

### Core Endpoints (30+)

**Authentication** (4 endpoints)
- `POST /api/auth/register` - Register user
- `POST /api/auth/login` - Login
- `POST /api/auth/logout` - Logout
- `GET /api/auth/me` - Get current user

**Analytics** (6 endpoints)
- `GET /api/analytics/health-score` - Health metrics
- `GET /api/analytics/trends` - Time-series data
- `GET /api/analytics/repository` - Repo metrics
- `GET /api/analytics/insights` - AI insights
- `GET /api/analytics/compare` - Period comparison
- `GET /api/analytics/export` - Export (JSON/CSV)

**Notifications** (10 endpoints)
- `GET /api/notifications` - List with filters
- `POST /api/notifications/{id}/read` - Mark read
- `POST /api/notifications/read-all` - Mark all read
- `GET /api/notifications/preferences` - Get prefs
- `POST /api/notifications/preferences` - Update prefs
- And more...

**Logging** (6 endpoints)
- `GET /api/logs` - Get logs with filters
- `GET /api/logs/errors` - Error logs
- `GET /api/logs/statistics` - Stats
- `DELETE /api/logs` - Clear (admin only)
- `GET /api/logs/export` - Export logs

**GitHub Integration** (1 endpoint)
- `POST /api/github/webhook` - GitHub webhook receiver
  * Signature verification (HMAC-SHA256)
  * Event routing (ping, pull_request, push, installation)
  * Automatic PR analysis queuing

**Full API documentation**: [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger UI)

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ -v --cov=src --cov-report=html

# Run specific suites
pytest tests/test_e2e.py -v                    # E2E tests
pytest tests/test_*_service.py -v              # Service tests
pytest tests/test_*_endpoints.py -v            # API tests
```

**Test Statistics**:
- Total: 680+ tests
- Service layer: 100% passing
- E2E workflows: 15 comprehensive tests
- Coverage: 89%+

## 🐳 Docker Deployment

### Using Docker Compose
```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f app

# Stop services
docker-compose down
```

### Manual Docker
```bash
# Build image
docker build -t code-review-assistant .

# Run container
docker run -d -p 8000:8000 \
  -e DATABASE_URL=postgresql://... \
  -e REDIS_URL=redis://host:6379/0 \
  code-review-assistant
```

## 📁 Project Structure
```
13-code-review-assistant/
├── src/
│   ├── core/                     # Core infrastructure
│   │   ├── database.py          # 10 SQLAlchemy models
│   │   ├── auth_manager.py      # RBAC authentication
│   │   ├── llm_client.py        # AI integration
│   │   ├── git_client.py        # Git operations
│   │   ├── github_app.py        # GitHub App authentication (JWT)
│   │   └── webhook_handler.py   # Webhook event handling
│   ├── parsers/                 # Code parsing
│   │   ├── python_parser.py     # Python AST
│   │   └── models.py            # Parse models
│   ├── analyzers/               # Analysis rules
│   │   ├── security_analyzer.py # 6 security rules
│   │   ├── smell_analyzer.py    # 6 smell rules
│   │   └── complexity_analyzer.py # Complexity metrics
│   ├── services/                # Business logic
│   │   ├── code_analyzer_service.py
│   │   ├── pr_service.py
│   │   ├── webhook_service.py   # Webhook event processing
│   │   ├── analytics_service.py # Health scoring, trends
│   │   ├── notification_service.py # 10 notification types
│   │   ├── logging_service.py   # Structured logging
│   │   └── cache_service.py     # Redis + in-memory
│   ├── workers/                 # Celery tasks
│   │   ├── analysis_worker.py
│   │   ├── pr_worker.py
│   │   └── repository_worker.py
│   └── utils/
├── static/
│   ├── css/                     # Responsive styles
│   │   ├── style.css
│   │   ├── dashboard.css
│   │   ├── diff-viewer.css
│   │   └── settings.css
│   └── js/                      # ES6+ JavaScript
│       ├── main.js
│       ├── dashboard.js         # Chart.js components
│       ├── diff-viewer.js       # Diff rendering
│       ├── progress-tracker.js  # SSE + polling
│       ├── advanced-filters.js  # Multi-criteria filtering
│       └── settings.js          # Settings management
├── templates/
│   ├── index.html               # Dashboard
│   ├── analysis.html
│   ├── repositories.html
│   └── settings.html
├── tests/                       # 680+ tests
│   ├── test_*_service.py        # Service tests
│   ├── test_*_endpoints.py      # API tests
│   └── test_e2e.py              # E2E workflows
├── data/
│   ├── database.db              # SQLite DB
│   └── repos/                   # Cloned repos
├── server.py                    # FastAPI app
├── celery_app.py                # Celery config
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## 🔧 Development

### Adding Analysis Rules
1. Create rule in `src/analyzers/`
2. Register in registry
3. Add tests
4. Update settings UI

### Database Migrations
```bash
# Auto-generate migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

## ⚡ Performance

### Caching Strategy
- Analysis results: 5 min TTL
- Repository data: 15 min TTL
- Analytics: 2 min TTL
- Typical hit rate: 60-70%

### Database Optimization
- 9 composite indexes on frequently queried columns
- Timestamp indexes for time-range queries
- Foreign key indexes for efficient joins

### Async Processing
- File analysis: Background Celery tasks
- PR reviews: Non-blocking with progress tracking
- Repository cloning: Async operations

## 🐛 Troubleshooting

**Database errors on startup**
```bash
rm data/database.db
python server.py  # Auto-creates DB
```

**Celery worker not processing**
```bash
redis-cli ping  # Check Redis
celery -A celery_app worker --loglevel=debug
```

**GitHub rate limits**
```bash
# Use authenticated token in .env
GITHUB_TOKEN=ghp_your_token
```

## 🤝 Contributing

1. Fork repository
2. Create feature branch
3. Add tests for new features
4. Ensure tests pass
5. Submit pull request

## 📄 License

MIT License - see LICENSE file

## 🙏 Acknowledgments

- **Anthropic Claude** for AI capabilities
- **FastAPI** for excellent web framework
- **Celery** for async task processing
- **Chart.js** for visualizations

Built as part of the AI Experiments Hub project series. Patterns reused from Project 6 (Code Doc Generator) and Project 12 (Content Moderation).

---

## 📈 Recent Updates

### Version 0.5.8 - GitHub App Integration UI (90% Complete)
**Commit 13.5.8 (AKHIL-158)** - Added GitHub App configuration interface:
- GitHub App settings page with interactive UI (/settings/github-app)
- 4 new API endpoints for GitHub App management
- Real-time status monitoring and validation
- Installation management and display
- Connection testing with detailed diagnostics
- Secure credential configuration (admin only)
- GitHubAppManager JavaScript class (500+ lines)
- Toast notifications for user feedback
- 13 comprehensive endpoint tests

### Version 0.5.7 - Automatic PR Analysis Worker (87% Complete)
**Commit 13.5.7 (AKHIL-157)** - Implemented webhook-triggered PR analysis:
- Added `analyze_pr_webhook` Celery task for async PR processing
- GitHub App authentication with installation tokens
- Multi-language PR analysis (Python, JS/TS, Java, Go, Rust)
- Priority-based job queuing (high/normal/low)
- Real-time progress tracking with Celery state updates
- Complete workflow: fetch → parse → analyze → store
- Enhanced queue manager with Celery task dispatching
- 8 comprehensive tests (100% passing)

### Version 0.5.6 - Webhook Infrastructure & GitHub App Integration (83% Complete)
**Commit 13.5.6 (AKHIL-156)** - Added comprehensive webhook infrastructure:
- GitHub App authentication with JWT token generation
- Installation token caching with automatic refresh
- Webhook signature verification (HMAC-SHA256)
- Event-driven PR analysis (opened, synchronized, reopened)
- 25 comprehensive tests (100% passing)

### Version 0.5.5 - Language Auto-Detection & Registry Enhancement (80% Complete)
**Commit 13.5.5 (AKHIL-155)** - Enhanced parser registry:
- Content-based language detection with pattern matching
- Shebang detection for scripts
- Extension-based auto-detection with fallbacks
- 32 registry tests (100% passing)

### Version 0.5.4 - Rust Parser Implementation (77% Complete)
**Commit 13.5.4 (AKHIL-154)** - Added Rust language support

### Version 0.5.3 - Go Parser Implementation (73% Complete)
**Commit 13.5.3 (AKHIL-153)** - Added Go language support

### Version 0.5.2 - Java Analysis Suite (70% Complete)
**Commit 13.5.2 (AKHIL-152)** - Added Java analyzers

### Version 0.5.1 - Java Parser Foundation (67% Complete)
**Commit 13.5.1 (AKHIL-151)** - Added Java language support

---

**Project 13 - Phase 5.8 Complete**
Production-ready with GitHub App UI, webhook-triggered PR analysis, multi-language support, and comprehensive monitoring ✨
