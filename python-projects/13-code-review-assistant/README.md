# AI Code Review & Refactoring Assistant

An intelligent code review system that analyzes Python code, detects issues, suggests refactorings, and integrates with GitHub pull requests. Powered by AI for smart code analysis and improvement suggestions.

## Features

### Code Analysis
- **Security Analysis**: Detect SQL injection, command injection, hardcoded secrets, path traversal, unsafe deserialization, and weak cryptography
- **Code Smell Detection**: Identify long methods, god classes, deep nesting, magic numbers, and duplicate code
- **Complexity Analysis**: Measure cyclomatic complexity and cognitive complexity with configurable thresholds
- **Style Checking**: PEP8 compliance and code formatting issues
- **Pattern Recognition**: Identify common anti-patterns and suggest best practices

### AI-Powered Features
- Intelligent issue explanations with context
- Automated refactoring suggestions with code examples
- Smart diff generation for fixes
- Confidence scoring for all suggestions

### GitHub Integration
- Pull request analysis and review
- Automated comment posting on GitHub PRs
- Repository synchronization
- Branch and commit tracking

### Async Processing
- Celery-based task queue for background analysis
- Real-time job status updates
- Handles large repositories and PRs efficiently

### Web Interface
- Modern, responsive dashboard
- Repository management
- Pull request review interface
- Issue browser with filtering
- Refactoring viewer with diffs
- User authentication and role-based access control

## Tech Stack

**Backend:**
- FastAPI - Modern web framework
- SQLAlchemy - ORM and database management
- Celery - Asynchronous task processing
- Redis - Message broker and result backend
- bcrypt - Password hashing
- Python AST - Code parsing

**Git & GitHub:**
- GitPython - Git operations
- PyGithub - GitHub API integration

**Analysis:**
- radon - Complexity metrics
- pycodestyle - PEP8 checking
- Custom analyzers for security and smells

**Frontend:**
- HTML/CSS/JavaScript
- Responsive design
- AJAX for real-time updates

## Installation

### Prerequisites

- Python 3.8 or higher
- Redis server
- Git
- GitHub account with personal access token

### Step 1: Clone the Repository

```bash
cd python-projects/13-code-review-assistant
```

### Step 2: Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

### Step 4: Set Up Environment Variables

Copy the example environment file:

```bash
cp .env.example .env
```

Edit `.env` and configure the following:

```env
# Server
HOST=0.0.0.0
PORT=8000
ALLOWED_ORIGINS=http://localhost:8000

# Database
DATABASE_URL=sqlite:///./data/database.db

# Auth
SESSION_TTL_DAYS=30
COOKIE_SECURE=false

# GitHub
GITHUB_TOKEN=ghp_your_personal_access_token_here

# Git
GIT_CLONE_DIR=./data/repos

# LLM (optional - for AI features)
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
# Or use cloud providers:
# ANTHROPIC_API_KEY=your_key_here
# OPENAI_API_KEY=your_key_here

# Analysis Thresholds
COMPLEXITY_THRESHOLD_WARN=10
COMPLEXITY_THRESHOLD_ERROR=15

# Celery
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
```

### Step 5: Create Required Directories

```bash
mkdir -p data/repos
```

### Step 6: Initialize Database

```bash
python -c "from src.core.database import DatabaseManager; DatabaseManager().init_db()"
```

### Step 7: Start Redis Server

In a new terminal:

```bash
redis-server
```

### Step 8: Start Celery Worker

In a new terminal:

```bash
source venv/bin/activate
celery -A celery_app worker --loglevel=info
```

### Step 9: Start FastAPI Server

```bash
python server.py
```

The application will be available at `http://localhost:8000`

## Usage

### First Time Setup

1. Open `http://localhost:8000` in your browser
2. Click "Register" to create an account
3. Login with your credentials

### Adding a Repository

1. Navigate to "Repositories" in the navigation menu
2. Click "Add Repository"
3. Enter the GitHub repository URL
4. Provide your GitHub personal access token
5. Click "Add" - the system will clone the repository

### Analyzing a Pull Request

1. Go to "Repositories" and select a repository
2. Click "Import PR"
3. Enter the pull request number
4. The system will fetch PR details and queue analysis
5. View results on the PR review page

### Analyzing a Single File

1. Click "Analyze File" from the dashboard
2. Upload a Python file
3. Review detected issues and refactoring suggestions

### Viewing Issues

1. Navigate to "Issues"
2. Filter by severity, category, or file
3. Click on an issue to view details and suggested fixes

## Configuration

### Analysis Thresholds

Adjust in `.env`:

```env
COMPLEXITY_THRESHOLD_WARN=10  # Warning for complexity > 10
COMPLEXITY_THRESHOLD_ERROR=15  # Error for complexity > 15
```

### Session Settings

```env
SESSION_TTL_DAYS=30  # Session expires after 30 days
COOKIE_SECURE=true   # Enable for HTTPS in production
```

### Git Settings

```env
GIT_CLONE_DIR=./data/repos  # Where repositories are cloned
```

## API Documentation

Interactive API documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Key Endpoints

**Authentication:**
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login
- `POST /api/auth/logout` - Logout
- `GET /api/auth/me` - Get current user

**Repositories:**
- `POST /api/repositories` - Add repository
- `GET /api/repositories` - List repositories
- `POST /api/repositories/{id}/sync` - Sync with GitHub

**Pull Requests:**
- `POST /api/prs` - Import PR from GitHub
- `GET /api/prs/{id}` - Get PR details
- `POST /api/prs/{id}/analyze` - Analyze PR

**Analysis:**
- `POST /api/analyze/file` - Analyze single file
- `GET /api/jobs/{id}` - Get job status

**Issues:**
- `GET /api/issues` - List issues with filters
- `GET /api/issues/{id}` - Get issue details

## Development

### Running Tests

```bash
pytest tests/ -v --cov=src
```

### Code Style

The project follows PEP8. Run style checks:

```bash
pycodestyle src/
```

### Project Structure

```
13-code-review-assistant/
├── src/
│   ├── core/           # Database, auth, queue management
│   ├── parsers/        # Code parsing (from Project 6)
│   ├── analyzers/      # Analysis rules
│   ├── services/       # Business logic
│   ├── workers/        # Celery tasks
│   └── utils/          # Utilities
├── static/             # CSS, JS, images
├── templates/          # HTML templates
├── data/               # Database and cloned repos
├── tests/              # Test suite
├── server.py           # FastAPI application
├── celery_app.py       # Celery configuration
└── requirements.txt    # Dependencies
```

## Security Considerations

- Never commit `.env` file with secrets
- Use HTTPS in production (`COOKIE_SECURE=true`)
- Regularly rotate GitHub tokens
- Keep dependencies updated
- Review user permissions before granting admin access

## Troubleshooting

### Redis Connection Error

Ensure Redis is running:
```bash
redis-cli ping
```
Should return `PONG`

### Celery Worker Not Starting

Check Redis connection and ensure no other workers are running on the same queue.

### GitHub API Rate Limiting

Use authenticated requests with a personal access token. Rate limit: 5000 requests/hour.

### Database Locked Error

SQLite doesn't handle concurrent writes well. Consider PostgreSQL for production:
```env
DATABASE_URL=postgresql://user:pass@localhost/dbname
```

## Roadmap

- [ ] Support for JavaScript/TypeScript analysis
- [ ] Multi-language code analysis
- [ ] Custom rule creation via web UI
- [ ] Team collaboration features
- [ ] Integration with CI/CD pipelines
- [ ] Slack/Discord notifications
- [ ] Automated fix application

## Contributing

This is a personal learning project. Contributions, suggestions, and feedback are welcome!

## License

MIT License - feel free to use this for learning and experimentation.

## Acknowledgments

- Built as part of the AI Experiments Hub project series
- Inspired by GitHub's CodeQL and other static analysis tools
- Uses patterns from Projects 6 (Code Doc Generator) and 12 (Content Moderation)

---

**Project 13** - Part of the AI Experiments Hub series
Week 1 MVP - Authentication, database, Celery, and basic web UI complete
