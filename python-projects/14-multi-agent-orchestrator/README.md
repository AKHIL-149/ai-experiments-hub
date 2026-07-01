# Project 14: Multi-Agent Task Orchestrator

[![CI - Tests and Coverage](https://github.com/yourusername/ai-experiments-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/yourusername/ai-experiments-hub/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An advanced AI-powered system that coordinates multiple specialized agents to autonomously break down, execute, and monitor complex tasks using LangGraph.

## Overview

This system demonstrates sophisticated multi-agent coordination where specialized AI agents work together to accomplish complex tasks:

- **Researcher Agent**: Gathers information and context
- **Coder Agent**: Implements solutions and writes code
- **Reviewer Agent**: Reviews code quality and suggests improvements
- **Tester Agent**: Creates and runs tests
- **Writer Agent**: Generates documentation

## Architecture

- **Framework**: LangGraph for agent orchestration with DAG-based workflows
- **Backend**: FastAPI + Celery + Redis
- **Database**: PostgreSQL with SQLAlchemy ORM
- **AI Models**: OpenAI GPT-4 / Anthropic Claude
- **Real-time**: WebSocket for live progress monitoring

## Features

- Multi-agent task decomposition and execution
- DAG-based workflow orchestration
- Shared memory and context across agents
- Human-in-the-loop approval gates
- Real-time progress monitoring
- Cost tracking and optimization
- Agent performance analytics

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- OpenAI or Anthropic API key

### Installation

#### Option 1: Docker (Recommended)

1. Configure environment:
```bash
cd python-projects/14-multi-agent-orchestrator
cp .env.example .env
# Edit .env with your API keys and settings
```

2. Build and start services:
```bash
make build
make up
```

3. View logs:
```bash
make logs
```

4. Access the application:
- API: http://localhost:8001
- PostgreSQL: localhost:5432
- Redis: localhost:6379

#### Option 2: Local Development

1. Install dependencies:
```bash
cd python-projects/14-multi-agent-orchestrator
pip install -r requirements.txt
```

2. Start PostgreSQL and Redis locally

3. Configure environment:
```bash
cp .env.example .env
# Edit .env with your settings
```

4. Initialize database:
```bash
alembic upgrade head
```

5. Start services:
```bash
# Terminal 1: Start Celery worker
celery -A celery_app worker --loglevel=info

# Terminal 2: Start Celery Beat
celery -A celery_app beat --loglevel=info

# Terminal 3: Start FastAPI server
python server.py
```

### Docker Commands

- `make build` - Build Docker images
- `make up` - Start all services
- `make down` - Stop all services
- `make restart` - Restart services
- `make logs` - View logs
- `make shell` - Open app container shell
- `make db-shell` - Open PostgreSQL shell
- `make redis-shell` - Open Redis CLI
- `make clean` - Remove containers and volumes

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run unit tests only
pytest -m unit

# Run integration tests only
pytest -m integration

# Run with coverage
pytest --cov=src --cov-report=html --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_validators.py -v

# Run tests excluding slow/LLM tests
pytest -m "not slow and not llm"
```

### Code Quality

```bash
# Format code with Black
black src/ tests/

# Sort imports with isort
isort src/ tests/

# Run linting checks
flake8 src/ tests/

# Run static analysis
pylint src/

# Run all quality checks
black --check src/ tests/ && \
isort --check-only src/ tests/ && \
flake8 src/ tests/ && \
pytest -m unit
```

### Pre-commit Hooks

Pre-commit hooks automatically run code quality checks before each commit, ensuring consistent code quality.

**Installation:**

```bash
# Install development dependencies (includes pre-commit)
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

**What Gets Checked:**

The pre-commit hooks run the following checks:
- **Black**: Code formatting (line length 100)
- **isort**: Import sorting (Black-compatible)
- **Flake8**: Linting with additional plugins
- **pyupgrade**: Upgrade syntax to Python 3.11+
- **Bandit**: Security vulnerability scanning
- **Trailing whitespace**: Remove trailing spaces
- **End of file**: Ensure newline at end
- **YAML/JSON/TOML**: Validate file syntax
- **Large files**: Prevent files > 1MB
- **Merge conflicts**: Detect conflict markers
- **Hadolint**: Dockerfile linting
- **ShellCheck**: Shell script analysis
- **Markdownlint**: Markdown formatting

**Manual Execution:**

```bash
# Run on all files
pre-commit run --all-files

# Run specific hook
pre-commit run black --all-files

# Update hook versions
pre-commit autoupdate

# Skip hooks for a commit (use sparingly)
git commit --no-verify
```

**Benefits:**
- Catches issues before CI/CD
- Ensures consistent code style
- Prevents common errors
- Faster feedback loop

### CI/CD

The project uses GitHub Actions for continuous integration:

- **Tests**: Runs on Python 3.11 and 3.12 with PostgreSQL and Redis
- **Code Quality**: Black, isort, Flake8, Pylint checks
- **Security**: Safety (dependency vulnerabilities) and Bandit (security issues)
- **Docker Build**: Validates Docker image builds successfully

All checks must pass before merging pull requests.

## Usage Guide

### Quick Start

After starting the services, initialize the database and seed default agents:

```bash
# Using Docker
make shell
python scripts/init_db.py
python scripts/seed_sample_data.py
exit

# Or locally
python scripts/init_db.py
python scripts/seed_sample_data.py
```

### API Usage Examples

#### 1. Health Check

```bash
# Check overall system health
curl http://localhost:8001/api/health

# Check individual components
curl http://localhost:8001/api/health/db
curl http://localhost:8001/api/health/celery
curl http://localhost:8001/api/health/full
```

#### 2. List Available Agents

```bash
# Get all agents
curl http://localhost:8001/api/agents

# Get only available agents
curl http://localhost:8001/api/agents/available

# Filter by role
curl http://localhost:8001/api/agents?role=coder
```

#### 3. Create a Task

```bash
curl -X POST http://localhost:8001/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Implement user authentication",
    "description": "Add JWT-based authentication to the API",
    "task_type": "coding",
    "priority": 8,
    "input_data": {
      "requirements": [
        "JWT token generation",
        "Password hashing",
        "Login endpoint"
      ]
    }
  }'
```

#### 4. Assign Task to Agent

```bash
# Update task with agent assignment
curl -X PATCH http://localhost:8001/api/tasks/1 \
  -H "Content-Type: application/json" \
  -d '{
    "assigned_agent_id": 2,
    "status": "queued"
  }'
```

#### 5. Create Task Dependencies

```bash
# Task 3 depends on Task 1 and Task 2
curl -X POST http://localhost:8001/api/tasks/3/dependencies \
  -H "Content-Type: application/json" \
  -d '{
    "dependency_ids": [1, 2]
  }'
```

#### 6. Monitor Task Progress

```bash
# Get task details
curl http://localhost:8001/api/tasks/1

# Get task dependencies
curl http://localhost:8001/api/tasks/1/dependencies

# Filter tasks by status
curl http://localhost:8001/api/tasks?status=in_progress
```

#### 7. View Agent Metrics

```bash
# Get agent performance metrics
curl http://localhost:8001/api/agents/1/metrics

# Get system-wide metrics
curl http://localhost:8001/api/metrics/summary
```

### Common Workflows

#### Workflow 1: Simple Task Execution

```python
import requests

BASE_URL = "http://localhost:8001/api"

# 1. Create a task
task_response = requests.post(f"{BASE_URL}/tasks", json={
    "title": "Research Python best practices",
    "description": "Gather information on modern Python development practices",
    "task_type": "research",
    "priority": 5
})
task_id = task_response.json()["id"]

# 2. Get available researcher agent
agents = requests.get(f"{BASE_URL}/agents/available?role=researcher").json()
researcher_id = agents[0]["id"]

# 3. Assign task to agent
requests.patch(f"{BASE_URL}/tasks/{task_id}", json={
    "assigned_agent_id": researcher_id,
    "status": "queued"
})

# 4. Monitor progress
task = requests.get(f"{BASE_URL}/tasks/{task_id}").json()
print(f"Task status: {task['status']}")
print(f"Progress: {task['progress']}%")
```

#### Workflow 2: Multi-Step Task with Dependencies

```python
import requests

BASE_URL = "http://localhost:8001/api"

# 1. Create research task
research_task = requests.post(f"{BASE_URL}/tasks", json={
    "title": "Research authentication methods",
    "task_type": "research",
    "priority": 7
}).json()

# 2. Create coding task (depends on research)
coding_task = requests.post(f"{BASE_URL}/tasks", json={
    "title": "Implement authentication",
    "task_type": "coding",
    "priority": 8,
    "dependency_ids": [research_task["id"]]
}).json()

# 3. Create testing task (depends on coding)
testing_task = requests.post(f"{BASE_URL}/tasks", json={
    "title": "Test authentication",
    "task_type": "testing",
    "priority": 7,
    "dependency_ids": [coding_task["id"]]
}).json()

# 4. Create documentation task (depends on testing)
docs_task = requests.post(f"{BASE_URL}/tasks", json={
    "title": "Document authentication",
    "task_type": "documentation",
    "priority": 6,
    "dependency_ids": [testing_task["id"]]
}).json()

print(f"Created task chain: {research_task['id']} -> {coding_task['id']} -> {testing_task['id']} -> {docs_task['id']}")
```

#### Workflow 3: Agent Configuration

```python
import requests

BASE_URL = "http://localhost:8001/api"

# Create a custom agent
agent = requests.post(f"{BASE_URL}/agents", json={
    "name": "Senior Python Developer",
    "role": "coder",
    "description": "Expert Python developer specializing in backend systems",
    "llm_provider": "anthropic",
    "llm_model": "claude-3-5-sonnet-20241022",
    "temperature": 0.2,
    "max_tokens": 4096,
    "system_prompt": """You are a senior Python developer with expertise in:
- FastAPI and async programming
- SQLAlchemy ORM
- Pytest and testing
- Clean code principles
- Performance optimization

Always write production-ready code with proper error handling and documentation."""
}).json()

print(f"Created agent: {agent['name']} (ID: {agent['id']})")
```

### Architecture Details

#### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                      Client Application                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Server                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Tasks API    │  │ Agents API   │  │ Metrics API  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ PostgreSQL  │  │   Redis     │  │  Celery     │
│  Database   │  │   Cache     │  │  Workers    │
└─────────────┘  └─────────────┘  └─────────────┘
                                          │
                         ┌────────────────┼────────────────┐
                         ▼                ▼                ▼
                  ┌──────────┐    ���──────────┐    ┌──────────┐
                  │  Task    │    │  Agent   │    │Monitoring│
                  │  Queue   │    │  Queue   │    │  Queue   │
                  └──────────┘    └──────────┘    └──────────┘
```

#### Task Lifecycle

1. **PENDING**: Task created, awaiting dependencies
2. **QUEUED**: Dependencies met, queued for execution
3. **IN_PROGRESS**: Agent actively working on task
4. **WAITING_APPROVAL**: Human review required
5. **COMPLETED**: Task finished successfully
6. **FAILED**: Task execution failed
7. **CANCELLED**: Task manually cancelled

#### Agent Roles and Configurations

| Agent | Role | Temperature | Purpose |
|-------|------|-------------|---------|
| Research Agent | RESEARCHER | 0.7 | Information gathering, analysis |
| Coder Agent | CODER | 0.3 | Code implementation |
| Reviewer Agent | REVIEWER | 0.4 | Code review, suggestions |
| Tester Agent | TESTER | 0.5 | Test creation and execution |
| Writer Agent | WRITER | 0.6 | Documentation generation |
| Coordinator Agent | COORDINATOR | 0.5 | Task orchestration |

### Monitoring and Metrics

#### Prometheus Metrics

The system exposes Prometheus metrics at `/api/metrics`:

```bash
# View metrics in Prometheus format
curl http://localhost:8001/api/metrics

# View metrics summary in JSON
curl http://localhost:8001/api/metrics/summary
```

**Available Metrics**:
- `task_created_total` - Total tasks created by type
- `task_completed_total` - Completed tasks by type and status
- `task_duration_seconds` - Task execution duration histogram
- `agent_active_total` - Currently active agents by role
- `llm_call_total` - LLM API calls by provider and model
- `llm_cost_total` - Total LLM costs by provider
- `http_requests_total` - HTTP requests by method, path, status

#### Logging

Logs are written in structured JSON format:

```bash
# View application logs
tail -f logs/app.log

# View error logs only
tail -f logs/error.log

# View Docker logs
make logs
```

### Troubleshooting

#### Database Connection Issues

```bash
# Check database health
curl http://localhost:8001/api/health/db

# Connect to PostgreSQL shell
make db-shell

# Verify tables exist
\dt

# Check agent count
SELECT COUNT(*) FROM agents;
```

#### Celery Worker Issues

```bash
# Check Celery health
curl http://localhost:8001/api/health/celery

# View Celery logs
docker logs multi-agent-orchestrator-celery_worker-1

# Restart Celery worker
docker restart multi-agent-orchestrator-celery_worker-1
```

#### Task Stuck in PENDING

Tasks remain PENDING if dependencies are not met:

```bash
# Check task dependencies
curl http://localhost:8001/api/tasks/{task_id}/dependencies

# Verify dependency tasks are completed
curl http://localhost:8001/api/tasks/{dependency_id}
```

#### High LLM Costs

Monitor and optimize LLM usage:

```python
# Get cost summary
response = requests.get("http://localhost:8001/api/metrics/summary")
costs = response.json()["llm_costs"]

# Adjust agent temperature (lower = more focused, cheaper)
requests.patch("http://localhost:8001/api/agents/1", json={
    "temperature": 0.2,  # More deterministic
    "max_tokens": 2048   # Limit response length
})
```

### Environment Variables

Key configuration options in `.env`:

```bash
# LLM Provider Selection
LLM_PROVIDER=openai          # or 'anthropic'
LLM_MODEL=gpt-4             # or 'claude-3-5-sonnet-20241022'
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=4096

# Agent Configuration
MAX_CONCURRENT_AGENTS=5
AGENT_TIMEOUT_SECONDS=300
ENABLE_AGENT_MEMORY=true

# Task Configuration
MAX_TASK_RETRIES=3
TASK_TIMEOUT_SECONDS=600
ENABLE_HUMAN_APPROVAL=false

# Cost Tracking
ENABLE_COST_TRACKING=true
COST_ALERT_THRESHOLD=100.0
```

### API Documentation

Interactive API documentation is available at:
- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

## Project Status

🚧 **In Development** - Block Phase 1: Foundation & Infrastructure (60% complete)

Current Progress: Commit 12/100

## Implementation Roadmap

### Block 1: Foundation & Infrastructure (Commits 1-20)
- Project structure and dependencies
- Database models and migrations
- FastAPI server setup
- Celery task queue configuration
- Basic authentication

### Block 2: Basic Agent Implementation (Commits 21-40)
- Agent base classes
- Individual agent implementations
- LangGraph integration
- Basic task execution

### Block 3: Multi-Agent Coordination (Commits 41-60)
- DAG workflow engine
- Shared memory system
- Agent communication
- Task decomposition

### Block 4: Advanced Features (Commits 61-80)
- Human approval gates
- Cost tracking
- Performance monitoring
- WebSocket real-time updates

### Block 5: Production & Polish (Commits 81-100)
- Frontend interface
- Production deployment
- Documentation
- Testing and optimization

## Tech Stack

- **Backend**: FastAPI, Celery, SQLAlchemy
- **Database**: PostgreSQL
- **Cache**: Redis
- **AI**: LangGraph, LangChain, OpenAI/Anthropic
- **Monitoring**: Prometheus, custom metrics
- **Frontend**: React (coming in Block 5)

## License

MIT License - see main repository LICENSE file
