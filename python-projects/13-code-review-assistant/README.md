# AI Code Review & Refactoring Assistant

**Version**: 0.5.20 (Team Collaboration & Review Workflows)
**Status**: Production-Ready with Team Collaboration, Automated Review Assignment, Shared Workspaces, Plugin Architecture, Rule Marketplace & Comprehensive Notifications

An intelligent code review system that analyzes Python, JavaScript/TypeScript, Java, Go, and Rust code, detects issues, suggests refactorings, and integrates with GitHub pull requests. Features team collaboration with automated reviewer assignment, shared workspaces with analytics dashboards, async processing, AI-powered insights, real-time analytics, intelligent language auto-detection, webhook-triggered automatic PR analysis, scheduled automated scans, visual custom rule builder, extensible plugin system, rule marketplace for sharing analysis rules, and comprehensive production monitoring.

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
- **Rule Builder**: Visual editor for creating custom analysis rules
  - AST pattern matching builder with node type selectors
  - Regex pattern tester with live validation
  - Live code preview and rule testing
  - Template library for quick starts
  - Save/load custom rules
- **Plugin Manager**: Visual interface for managing plugins
  - Plugin loading and unloading
  - Enable/disable plugins
  - View plugin details, rules, and statistics
  - Monitor plugin execution and errors
- **Diff Viewer**: Syntax-highlighted unified/split diff views
- **Progress Tracker**: Real-time progress with SSE and polling fallback
- **Settings Panel**: Configurable rules, thresholds, AI providers, theme switching

### Plugin System
- **Extensible Architecture**: Plugin-based system for custom analyzers, formatters, reporters
- **Plugin Types**: Analyzer, Formatter, Reporter, Integration, Custom
- **Hook System**: 12+ hooks for analysis lifecycle (before/after analysis, on issue found, etc.)
- **Example Plugin**: Security analyzer demonstrating plugin API
- **Plugin API**: Full API for loading, managing, and executing plugins
- **Plugin UI**: Web interface for plugin management and configuration
- **Dynamic Loading**: Load plugins from Python files at runtime
- **Language Support**: Per-plugin language support configuration
- **Statistics Tracking**: Plugin load count, execution count, error tracking

### Rule Marketplace
- **Rule Sharing**: Publish custom analysis rules to community marketplace
- **Visibility Controls**: Private, public, and unlisted visibility options
- **Fork & Import**: Fork public rules to customize for your needs
- **Export/Import**: Export rules as JSON for sharing and backup
- **Rating & Reviews**: 5-star rating system with written reviews
- **Discovery**: Browse marketplace with filters (category, language, search)
- **Sorting**: Sort by popularity, recency, rating, or fork count
- **Featured Rules**: Curated collection of high-quality rules
- **Statistics**: Track download count, fork count, and usage metrics
- **Pagination**: Efficient browsing of large rule collections
- **Bulk Operations**: Export/import multiple rules at once

### Scheduled Analysis & Automated Scanning
- **Flexible Scheduling**: 4 schedule types (daily, weekly, interval, custom cron)
- **Cron Expression Support**: Full cron syntax with croniter validation
- **Automated Execution**: Celery Beat periodic task checks for due schedules every minute
- **Configurable Analysis**:
  - Analyze all files or specific patterns (glob support)
  - Custom rule selection and severity thresholds
  - Repository-specific schedules
- **Notifications**:
  - Email and Slack webhook integration
  - Notify on completion or only when issues found
  - Multiple recipients support
- **Run Tracking**:
  - Detailed execution history with status, duration, and results
  - Issue counts by severity (critical, error, warning, info)
  - Files analyzed and error logging
- **Management UI**:
  - Visual schedule creation and editing
  - Enable/disable schedules
  - Manual trigger for immediate runs
  - View run history and details
- **Async Execution**: Background processing via Celery workers

### Team Collaboration
- **Teams & Organizations**: Create teams with hierarchical role-based access control
  - Owner, Admin, Member, Viewer roles with granular permissions
  - Team invitations with token-based acceptance
  - Team settings and visibility controls
- **Shared Workspaces**: Collaborative team dashboards with comprehensive analytics
  - Team overview stats (members, repositories, issues, health score)
  - Shared repository pools across team members
  - Team analytics with Chart.js visualizations (severity, category, health trends)
  - Team leaderboard ranking members by contributions
  - Activity feed tracking team analyses and reviews
- **Automated Review Assignment**: Intelligent reviewer routing with multiple strategies
  - **Balanced Assignment**: Distributes reviews based on current workload
  - **Expertise Assignment**: Routes to reviewers with file modification history
  - **Round Robin Assignment**: Evenly distributes reviews across team
  - Excludes PR authors from assignment pool
  - Respects team roles and permissions
- **Code Ownership Tracking**: CODEOWNERS file support for ownership mapping
  - Glob pattern matching for file ownership
  - Automatic owner identification for changed files
  - Required owner approval workflows
- **Review Workflows**: Approval validation and merge readiness checks
  - Configurable approval requirements (count, owner approval)
  - Reviewer performance statistics and metrics
  - Approval rate tracking and workload analytics

### Production Features
- **Notifications**: In-app notification system with 10 types, preferences, event-driven architecture
- **Logging**: Structured logging with correlation IDs, sensitive data masking, export capabilities
- **Caching**: Redis caching with in-memory fallback, TTL support, cache decorators
- **Performance**: Database indexes (9 composite indexes), query optimization
- **Authentication**: Session-based auth with RBAC (User/Admin roles)
- **Async Processing**: Celery + Redis for background jobs

## 📊 Test Coverage

- **Total Tests**: 1130+
- **Coverage**: 90%+
- **Test Suites**:
  - Parser tests: 30 Java tests, 44 JavaScript/TypeScript tests, 32 registry tests (100% passing)
  - Analyzer tests: 22 Java analyzer tests, 30 JavaScript analyzer tests (100% passing)
  - Service tests: 100+ tests (100% passing)
  - Webhook infrastructure tests: 25 tests (100% passing)
  - Webhook worker tests: 8 tests (100% passing)
  - GitHub App UI tests: 13 tests (endpoint coverage)
  - Slack integration tests: 24 tests (100% passing)
  - Email integration tests: 24 tests (100% passing)
  - Discord integration tests: 28 tests (100% passing)
  - Notification rules tests: 25 tests (100% passing)
  - Notification digest tests: 41 tests (100% passing)
  - Notification UI tests: 20 tests (100% passing)
  - Custom rule service tests: 24 tests (100% passing)
  - Rule builder endpoint tests: 28 tests (100% passing)
  - Plugin system tests: 23 tests (100% passing)
  - Rule marketplace tests: 30 tests (100% passing)
  - Schedule service tests: 24 tests (100% passing)
  - Team management tests: 10 tests (100% passing)
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

### Database Schema (22 Models)
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
11. **SlackConfiguration** - Slack webhook configuration
12. **EmailConfiguration** - Email SMTP configuration
13. **DiscordConfiguration** - Discord webhook configuration
14. **NotificationRule** - Conditional notification rules
15. **CustomRule** - User-defined custom analysis rules with marketplace support
16. **Plugin** - Installed plugin metadata and statistics
17. **RuleRating** - Marketplace rule ratings and reviews
18. **Team** - Teams/Organizations for collaborative code review
19. **TeamMember** - Team membership with role-based access control
20. **TeamInvitation** - Pending invitations to join a team
21. **AnalysisSchedule** - Scheduled recurring analysis for repositories
22. **ScheduledRun** - Individual execution run of a scheduled analysis

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

## 🔌 Plugin System

The plugin system allows you to extend the code review assistant with custom analyzers, formatters, reporters, and integrations.

### Plugin Architecture

The system supports five plugin types:
- **Analyzer**: Custom code analysis rules and patterns
- **Formatter**: Code formatting and style checking
- **Reporter**: Custom report generation
- **Integration**: External service integrations
- **Custom**: General-purpose plugins

### Creating a Plugin

Create a Python file in the `plugins/` directory:

```python
from src.core.plugin_base import AnalyzerPlugin, PluginMetadata, PluginType, PluginHook

class MyCustomAnalyzer(AnalyzerPlugin):
    def __init__(self):
        metadata = PluginMetadata(
            name="my-custom-analyzer",
            version="1.0.0",
            author="Your Name",
            description="Custom analyzer for specific patterns",
            plugin_type=PluginType.ANALYZER,
            supported_languages=["python", "javascript"],
            homepage="https://github.com/yourname/plugin",
            license="MIT"
        )
        super().__init__(metadata)

        # Register hooks (optional)
        self.register_hook(PluginHook.ON_ISSUE_FOUND, self.on_issue_callback)

    def initialize(self) -> bool:
        """Initialize the plugin"""
        print(f"Initializing {self.metadata.name}")
        return True

    def shutdown(self) -> bool:
        """Shutdown the plugin"""
        print(f"Shutting down {self.metadata.name}")
        return True

    def analyze(self, code: str, language: str, file_path: str):
        """Analyze code and return issues"""
        issues = []

        # Your custom analysis logic
        lines = code.split('\n')
        for line_num, line in enumerate(lines, 1):
            if 'TODO' in line:
                issues.append({
                    'type': 'info',
                    'severity': 'info',
                    'message': 'TODO comment found',
                    'file': file_path,
                    'line': line_num,
                    'code_snippet': line.strip(),
                    'plugin': self.metadata.name
                })

        return issues

    def on_issue_callback(self, context, issue):
        """Hook callback when an issue is found"""
        print(f"Issue detected: {issue.get('message')}")

    def get_rules(self):
        """Return analysis rules (optional)"""
        return [
            {
                'id': 'MY_TODO_CHECK',
                'name': 'TODO Comment Detection',
                'description': 'Detects TODO comments in code',
                'severity': 'info',
                'category': 'custom'
            }
        ]

# Plugin entry point
def get_plugin():
    return MyCustomAnalyzer()
```

### Loading Plugins

#### Via API
```bash
curl -X POST http://localhost:8000/api/plugins/load \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "./plugins/my_custom_analyzer.py",
    "enabled": true
  }'
```

#### Via Python
```python
from src.core.plugin_manager import PluginManager

manager = PluginManager()
plugin = manager.load_plugin_from_file("./plugins/my_custom_analyzer.py")
manager.register_plugin(plugin)
```

#### Via UI
1. Navigate to `/plugins` in the web interface
2. Click "Load Plugin"
3. Enter the plugin file path
4. Click "Load Plugin"

### Plugin Hooks

Available hooks for plugin lifecycle events:

- `BEFORE_ANALYSIS` - Before analyzing code
- `AFTER_ANALYSIS` - After analyzing code
- `ON_ISSUE_FOUND` - When an issue is detected
- `BEFORE_FILE_PARSE` - Before parsing a file
- `AFTER_FILE_PARSE` - After parsing a file
- `BEFORE_PR_REVIEW` - Before reviewing a PR
- `AFTER_PR_REVIEW` - After reviewing a PR
- `ON_PR_OPENED` - When a PR is opened
- `ON_PR_SYNCHRONIZED` - When a PR is updated
- `ON_PR_CLOSED` - When a PR is closed
- `ON_PR_MERGED` - When a PR is merged
- `ON_REPOSITORY_ADDED` - When a repository is added

### Plugin API Endpoints

- `GET /api/plugins` - List all installed plugins
- `POST /api/plugins/load` - Load a new plugin
- `GET /api/plugins/{plugin_id}` - Get plugin details
- `PUT /api/plugins/{plugin_id}` - Update plugin (enable/disable)
- `DELETE /api/plugins/{plugin_id}` - Delete plugin
- `GET /api/plugins/{plugin_id}/manifest` - Get plugin manifest with rules

### Example Plugin

The system includes an example security analyzer (`plugins/example_analyzer.py`) that detects:
- Hardcoded passwords, API keys, secrets, tokens
- Dangerous function usage (eval, exec, os.system)
- Command injection vulnerabilities
- XSS vulnerabilities (JavaScript)

View the example plugin for a complete reference implementation.

### Plugin Statistics

Each plugin tracks:
- **Load count**: Number of times the plugin was loaded
- **Execution count**: Number of times the plugin executed
- **Error count**: Number of errors encountered
- **Last error**: Most recent error message
- **Last used**: Timestamp of last execution

### Best Practices

1. **Error Handling**: Always handle exceptions in your plugin code
2. **Language Support**: Specify supported languages to avoid unnecessary execution
3. **Performance**: Keep analysis fast; avoid blocking operations
4. **Documentation**: Include clear descriptions and rule definitions
5. **Testing**: Write tests for your plugin logic
6. **Versioning**: Use semantic versioning for your plugins
7. **Hooks**: Use hooks sparingly and only when necessary

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

**Scheduled Analysis** (10 endpoints)
- `POST /api/schedules` - Create schedule
- `GET /api/schedules` - List schedules (with filters)
- `GET /api/schedules/{schedule_id}` - Get schedule details
- `PUT /api/schedules/{schedule_id}` - Update schedule
- `DELETE /api/schedules/{schedule_id}` - Delete schedule
- `POST /api/schedules/{schedule_id}/toggle` - Enable/disable
- `POST /api/schedules/{schedule_id}/trigger` - Trigger manual run
- `GET /api/schedules/{schedule_id}/runs` - Get schedule runs
- `GET /api/runs/{run_id}` - Get run details
  * Supports: daily, weekly, interval, cron schedules
  * Notifications: email and Slack webhooks
  * Run tracking: status, duration, issue counts

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
- Total: 1008+ tests
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
│   │   ├── settings.css
│   │   └── notifications.css    # Notification UI styles
│   └── js/                      # ES6+ JavaScript
│       ├── main.js
│       ├── dashboard.js         # Chart.js components
│       ├── diff-viewer.js       # Diff rendering
│       ├── progress-tracker.js  # SSE + polling
│       ├── advanced-filters.js  # Multi-criteria filtering
│       ├── settings.js          # Settings management
│       └── notification-manager.js # Notification center
├── templates/
│   ├── index.html               # Dashboard
│   ├── analysis.html
│   ├── repositories.html
│   ├── notifications.html       # Notification center
│   ├── notification_preferences.html # Notification settings
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

### Version 0.5.23 - Historical Analytics & Quality Tracking (88% Complete)
**Commit 13.5.23 (AKHIL-168)** - Implemented historical analytics and time-series tracking:
- HistoricalAnalyticsService for trend analysis and quality tracking
  * get_repository_health_score() - 0-100 score with grade (A+ to F)
  * get_quality_trends() - Time-series data (daily/weekly/monthly)
  * get_developer_contribution_analysis() - Developer performance metrics
  * get_technical_debt_heatmap() - File-level debt visualization
  * get_quality_gate_metrics() - SLO compliance checking
- Repository health scoring:
  * 0-100 point scale with letter grades
  * Deductions: critical=-15, error=-5, warning=-2, info=-0.5
  * Issues per KLOC metric
  * Trend analysis (improving/stable/declining)
  * Period-over-period comparison
- Time-series quality trends:
  * Configurable granularity (daily/weekly/monthly)
  * Total issues, critical issues, health score, issues/KLOC
  * Time bucket aggregation with labeled data points
  * Trend visualization data
- Developer contribution analysis:
  * PRs created and reviewed per developer
  * Files modified tracking
  * Issues introduced by developer
  * Quality score (inverse of issues per PR)
  * Contribution score (PRs×10 + reviews×5)
  * Severity distribution per developer
- Technical debt heatmap:
  * File-level debt scoring and density
  * Debt levels (low <0.1, medium <0.3, high <0.5, critical >0.5)
  * Severity distribution per file
  * Sorted by debt score (highest first)
- Quality gate metrics and SLOs:
  * Health score minimum: 80
  * Critical issues max: 0
  * Issues per KLOC max: 10
  * Acceptable trends: improving, stable
  * Overall pass/fail status
- 5 new API endpoints (health, trends, developers, heatmap, quality-gate)
- 15+ historical analytics tests
- Total tests: 1180+

### Version 0.5.22 - Advanced AI Features & Refactoring (87% Complete)
**Commit 13.5.22 (AKHIL-167)** - Implemented AI-powered refactoring and code generation:
- AIRefactoringService for intelligent code improvements
  * generate_multi_step_refactoring() - Sequential refactoring chains with dependencies
  * apply_automated_fix() - Automated issue fixing with test generation
  * estimate_technical_debt() - Time/cost metrics and recommendations
  * ai_pair_programming() - Interactive AI code assistance
  * predict_code_smells() - LLM-based code smell prediction
- RefactoringChain dataclass for sequential refactoring steps
- RefactoringType enum (extract_method, rename, simplify, optimize, security_fix, etc.)
- Technical debt estimation:
  * Debt ratio calculation (issues per 1000 LOC)
  * Time estimates: critical=4h, error=2h, warning=1h, info=0.5h
  * Cost calculation at $100/hour rate
  * Categorized debt levels (low <5, medium <15, high <30, critical >30)
  * Prioritized recommendations by severity
- 5 new API endpoints:
  * POST /api/refactor/multi-step - Generate refactoring chains
  * POST /api/refactor/auto-fix/{issue_id} - Apply automated fixes
  * GET /api/technical-debt - Debt estimation with recommendations
  * POST /api/ai/pair-programming - Interactive code assistance
  * POST /api/ai/predict-smells - Predict code issues
- 20+ AI refactoring tests, 15+ API endpoint tests
- Total tests: 1165+

### Version 0.5.21 - CI/CD Integration & CLI Tool (85% Complete)
**Commit 13.5.21 (AKHIL-166)** - Implemented CI/CD integration and command-line tool:
- CLI tool (cli.py) with 4 subcommands:
  * analyze - Analyze code files with filtering and thresholds
  * report - Generate reports in text/JSON/markdown/HTML
  * quality-gate - Check quality thresholds with exit codes
  * badge - Generate SVG quality badges
- GitHub Actions workflow (.github/workflows/code-review.yml)
  * Multi-language parallel analysis (Python, JavaScript, Java, Go, Rust)
  * Security scan with critical threshold
  * Quality gate enforcement with configurable thresholds
  * Report generation (markdown + HTML)
  * Badge creation for main branch
  * Workflow dispatch with custom parameters
- GitLab CI configuration (.gitlab-ci.yml)
  * 4-stage pipeline (test, analyze, report, quality-gate)
  * Security scan with zero-failure tolerance
  * Parallel language-specific analysis
  * Nightly scheduled analysis
  * MR-specific analysis with markdown reports
- Jenkins pipeline (Jenkinsfile)
  * Docker-based Python 3.10 environment
  * Parameterized builds (severity threshold, max issues)
  * Parallel report generation (markdown + HTML)
  * Build badge integration
  * Multi-branch pipeline support
- Pre-commit hook generator (scripts/generate-pre-commit-hook.py)
  * Configurable severity threshold and max issues
  * Staged files only analysis
  * Automatic hook installation to .git/hooks
- Configuration file (.code-review-config.yml)
  * Analysis settings (languages, categories, exclusions)
  * Quality gate thresholds
  * CI/CD integration options
  * Notification channels (Slack, Email)
  * Pre-commit hook settings
- Exit code based quality enforcement for CI/CD pipelines
- Multi-format reporting (text, JSON, markdown, HTML)
- 25+ CI integration tests (to be implemented)
- Total tests: 1130+

### Version 0.5.20 - Review Assignment & Workflows (Phase 5 Complete - 100%)
**Commit 13.5.20 (AKHIL-165)** - Implemented automated review assignment and workflows:
- ReviewAssignmentService for managing review workflows
  * assign_reviewers() with 3 strategies (balanced, expertise, round_robin)
  * parse_codeowners() - CODEOWNERS file format parsing
  * get_file_owners() - File ownership mapping with glob patterns
  * check_review_approval() - PR approval status validation
  * get_reviewer_stats() - Reviewer performance metrics
- Balanced assignment: Routes to reviewers with lowest current workload
- Expertise assignment: Routes based on file modification history
- Round robin assignment: Distributes reviews evenly across team
- CODEOWNERS pattern matching for code ownership tracking
- Approval workflow validation with configurable rules
- Reviewer workload tracking and performance analytics
- 3 new API endpoints (assign-reviewers, approval-status, reviewer-stats)
- Excludes PR authors from reviewer candidates
- Respects team roles and permissions
- Total tests: 1130+

### Version 0.5.19 - Shared Workspaces & Team Analytics (98% Complete)
**Commit 13.5.19 (AKHIL-164)** - Implemented shared workspaces and team analytics:
- TeamAnalyticsService for team-level metrics aggregation
  * get_team_analytics() - Issues by severity/category across team repos
  * get_team_repositories() - Team repos with health scores
  * get_team_leaderboard() - Member rankings by contribution score
  * get_team_activity() - Recent team activities (analyses, reviews)
- Team dashboard UI (team_dashboard.html) with comprehensive analytics
  * Team selector dropdown with overview stats
  * Shared repositories grid with health metrics
  * Chart.js visualizations (severity, category, health trend, activity)
  * Team leaderboard table with rankings
  * Activity feed with icons and timestamps
- Dashboard JavaScript (team-dashboard.js, 420 lines)
  * Parallel data loading with Promise.all()
  * Chart.js integration for 4 analytics charts
  * Dynamic rendering for repositories and leaderboard
- Responsive CSS (team-dashboard.css, 390 lines) with gradient stat cards
- 4 new API endpoints (analytics, repositories, leaderboard, activity)
- Added "Teams" link to main navigation
- Total tests: 1130+

### Version 0.5.17b - Team Management Tests & Fixes (95% Complete)
**Commit 13.5.17b** - Added team management tests and SQLAlchemy 2.0 fixes:
- 10 comprehensive team management tests (test_team_basic.py)
  * Team creation, retrieval, and deletion
  * Member addition and role management
  * Team invitations and permissions
  * All tests passing with unique ID fixtures
- Fixed SQLAlchemy 2.0 compatibility issue in TeamService
  * Changed func.case() to case() import for proper sorting
  * Removed deprecated func usage
- Added Any type import to database.py
- Tests use success/error dict pattern from TeamService API
- Total tests: 1130+

### Version 0.5.15 - Plugin System (103% Complete)
**Commit 13.5.15** - Implemented extensible plugin architecture:
- Plugin base classes (plugin_base.py, 371 lines) with abstract interfaces
- PluginManager (plugin_manager.py, 398 lines) with singleton pattern
- 5 plugin types: Analyzer, Formatter, Reporter, Integration, Custom
- 12+ plugin hooks for lifecycle events (before/after analysis, on issue found, etc.)
- PluginContext for passing state to plugin callbacks
- Dynamic plugin loading from Python files at runtime
- Plugin validation and registration system
- Example security analyzer plugin (example_analyzer.py, 158 lines)
  - Detects hardcoded credentials (passwords, API keys, secrets, tokens)
  - Detects dangerous functions (eval, exec, os.system)
  - Supports Python and JavaScript analysis
- Plugin database model (16th model) with statistics tracking
- 6 plugin management API endpoints (list, load, get, update, delete, manifest)
- Plugin manager UI (plugins.html) with visual plugin cards
- Plugin manager JavaScript (plugin-manager.js, 550+ lines)
- Enable/disable plugins with status tracking
- Plugin statistics (load count, execution count, error count)
- Plugin manifest export with rules and metadata
- 30 comprehensive plugin tests (100% passing)
- Load count: 1, Execution count: 0, Error count: 0
- Total tests: 1090+

### Version 0.5.14 - Rule Builder UI (102% Complete)
**Commit 13.5.14** - Implemented visual custom rule builder:
- Rule builder HTML template (rule_builder.html) with comprehensive form interface
- Rule builder CSS (rule-builder.css, 700+ lines) with responsive design
- RuleBuilder JavaScript class (1000+ lines) for interactive rule creation
- AST pattern matching builder with node type selectors for Python and JavaScript
- Regex pattern tester with live validation and multi-flag support
- Live code preview with syntax highlighting and real-time rule testing
- Rule templates library (security, smells, complexity templates)
- CustomRule database model for storing user-defined rules
- CustomRuleService for testing and applying custom rules
- 5 new API endpoints (save, get, get-by-id, delete, test rules)
- Pattern matching support: AST patterns, regex patterns, or combined
- Support for multiple programming languages per rule
- Auto-fixable rule flagging
- 52 comprehensive tests (24 service + 28 endpoint, 100% passing)

### Version 0.5.13 - Notification UI & Management (100% Complete)
**Commit 13.5.13** - Completed comprehensive notification user interface:
- Notification center page (notifications.html) with filtering and modal views
- Notification preferences page (notification_preferences.html) with full configuration UI
- NotificationManager JavaScript class (1000+ lines) for client-side management
- PreferencesManager class for channel configuration and testing
- RulesManager class for creating and editing notification rules
- Complete notification CSS (notifications.css, 630+ lines) with responsive design
- Channel configuration cards (Email, Slack, Discord) with toggle switches
- Interactive rule editor modal with conditions and actions builder
- Severity filters with visual checkboxes
- Quiet hours configuration with timezone support
- Advanced settings (batch notifications, rate limiting)
- Real-time polling for new notifications (30-second interval)
- Browser notification API integration
- Navigation update with notification bell and badge
- 2 new page routes (/notifications, /notifications/preferences)
- Save reminder for unsaved changes
- Empty state and loading state handling
- 20 comprehensive UI tests (100% passing)

### Version 0.5.12 - Notification Digest & Batching Worker (98% Complete)
**Commit 13.5.12** - Implemented notification batching and digest system:
- NotificationDigestService for aggregating and formatting digests
- Notification batching worker with Celery tasks
- Scheduled digest sending (daily at 9:00 AM, weekly on Mondays)
- Batch notification processing with multi-channel support
- 5 new Celery tasks (queue, batch, daily/weekly digests, user digest)
- 6 new API endpoints (queue, batch, send, preview, test digest)
- Email, Slack, and Discord digest formatting
- Quiet hours checking with configurable send times
- Celery Beat integration for scheduled tasks
- Notification grouping by user and channel type
- Batched HTML email generation
- 41 comprehensive tests (25 digest + 16 worker, 100% passing)

### Version 0.5.11 - Notification Rules Engine (96% Complete)
**Commit 13.5.11** - Implemented advanced notification rules and routing:
- NotificationRulesEngine with condition builder and evaluation system
- NotificationRule database model with JSON conditions and actions
- Condition types: severity, category, file patterns, PR author, issue type, confidence
- Quiet hours support with timezone handling and day-of-week configuration
- Rate limiting to prevent notification spam
- Priority-based rule execution (lower number = higher priority)
- Multi-channel routing (Slack, Email, Discord) per rule
- Batch notifications with configurable intervals
- 5 new API endpoints (create, update, delete, test, evaluate rules)
- Pattern matching for file paths (wildcards, recursive patterns)
- Rule testing with sample issues before deployment
- 25 comprehensive tests (100% passing)

### Version 0.5.10 - Email & Discord Notifications (94% Complete)
**Commit 13.5.10** - Added comprehensive multi-channel notification support:
- EmailService with SMTP integration and HTML email templates
- DiscordService with rich embed formatting and webhook support
- EmailConfiguration and DiscordConfiguration database models
- Notification preferences with digest mode and severity filtering
- 8 new API endpoints (Email and Discord configuration management)
- HTML email templates for all notification types (PR analysis, critical issues, failures)
- Discord embeds with color coding and rich formatting
- Digest mode with daily/weekly batching for email notifications
- Test endpoints for SMTP and Discord webhook validation
- 52 comprehensive tests (24 email + 28 Discord, 100% passing)

### Version 0.5.9 - Slack Integration (92% Complete)
**Commit 13.5.9** - Implemented Slack notifications and webhooks:
- SlackService with rich message formatting (blocks, attachments)
- 4 notification types: PR analysis complete, critical issues, failures, PR opened
- SlackConfiguration database model with per-user/repo settings
- Notification preferences (severity filtering, threading, channels)
- 4 new API endpoints for Slack configuration management
- Thread reply support for organized conversations
- Test endpoint for webhook validation
- 24 comprehensive tests (100% passing)

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

**Project 13 - Phase 5 Complete (Team Collaboration)**
Production-ready with team collaboration, automated review assignment, shared workspaces with analytics dashboards, visual custom rule builder, complete notification UI, digest & batching system, advanced rules engine, multi-channel notifications, GitHub App UI, webhook-triggered PR analysis, multi-language support, and comprehensive monitoring ✨
