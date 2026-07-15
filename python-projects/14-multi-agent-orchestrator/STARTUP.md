# Multi-Agent Task Orchestrator - Startup Guide

## Prerequisites

1. **Python 3.9+** (tested with Python 3.9)
2. **PostgreSQL** database
3. **Redis** server
4. **Environment variables** configured

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Setup Environment

Create a `.env` file in the project root:

```bash
cp .env.example .env
```

Edit `.env` and configure:
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` - LLM API keys
- Other settings as needed

### 3. Create Database

```bash
# Create PostgreSQL database
createdb multi_agent_orchestrator

# Or using psql
psql -U postgres -c "CREATE DATABASE multi_agent_orchestrator;"
```

### 4. Run Database Migrations

Initialize database schema with Alembic migrations:

```bash
# Using the helper script (recommended)
./migrate.sh upgrade

# Or using alembic directly
alembic upgrade head
```

This will create all required tables including:
- `tasks`, `agents`, `agent_executions`
- `agent_messages`, `shared_memory`
- `workflows`, `workflow_steps`
- `users` and other application tables

See [migrations/README.md](migrations/README.md) for detailed migration documentation.

### 5. Start Redis

```bash
# macOS (using Homebrew)
brew services start redis

# Linux
sudo systemctl start redis

# Or run Redis directly
redis-server
```

### 6. Start the Server

#### Full Server (All 500+ Endpoints)

```bash
python3 server.py
```

The server will start on `http://0.0.0.0:8001`

#### Minimal Server (Core Endpoints Only)

For testing or development with minimal dependencies:

```bash
python3 server_minimal.py
```

The minimal server starts on `http://0.0.0.0:8001`

## Verify Server is Running

### Health Check

```bash
curl http://localhost:8001/api/health
```

Expected response:
```json
{
    "status": "healthy",
    "timestamp": "2026-07-14T03:25:58.446283",
    "service": "multi-agent-orchestrator"
}
```

### API Documentation

Open in browser:
- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc
- **GraphQL Playground**: http://localhost:8001/graphql

## Architecture Overview

The Multi-Agent Task Orchestrator is built with:

- **FastAPI** - Web framework with 500+ REST endpoints
- **LangGraph v0.6** - Multi-agent workflow orchestration
- **LangChain v0.3** - AI agent framework
- **PostgreSQL** - Primary database (SQLAlchemy ORM)
- **Redis** - Cache, message broker, rate limiting
- **Celery** - Asynchronous task queue
- **OpenAI/Anthropic** - LLM backends

### Key Features

1. **Multi-Agent Coordination**: Research, Code, Data Analyst, Writer, and Planner agents
2. **DAG Workflows**: Define complex task dependencies and execution graphs
3. **Shared Memory**: Inter-agent communication and state sharing
4. **Human-in-the-Loop**: Approval gates for critical decisions
5. **Real-time Updates**: WebSocket support for live progress tracking

## Common Issues

### Port Already in Use

If port 8001 is already in use, change `API_PORT` in `.env`:

```bash
API_PORT=8002
```

### Database Connection Failed

Verify PostgreSQL is running and credentials are correct:

```bash
psql -U postgres -d multi_agent_orchestrator -c "SELECT 1;"
```

### Redis Connection Failed

Verify Redis is running:

```bash
redis-cli ping
# Should return: PONG
```

### Import Errors

If you see import errors, ensure all dependencies are installed:

```bash
pip install --upgrade -r requirements.txt
```

## Development Mode

Run with auto-reload enabled (default in DEBUG mode):

```bash
DEBUG=true python3 server.py
```

## Production Deployment

For production, use a production-grade ASGI server:

```bash
# Using Gunicorn with Uvicorn workers
gunicorn server:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8001 \
    --log-level info
```

## API Endpoints Summary

The full server includes 500+ endpoints across these categories:

- **Core**: Tasks, Agents, Workflows, Executions
- **Communication**: Messages, Shared Memory, Events
- **Orchestration**: Load Balancing, Scheduling, Priorities
- **Collaboration**: Negotiations, Coalitions, Consensus
- **Reputation**: Agent Performance, Trust, Incentives
- **Learning**: Agent Knowledge, Learning, Profiling
- **Infrastructure**: Monitoring, Logging, Tracing, Alerts
- **Management**: Configuration, Secrets, Backup, Recovery
- **Quality**: Testing, Documentation, API Gateway
- **Operations**: Deployment, Migrations, Capacity Planning
- **Security**: Authentication, Rate Limiting, Data Privacy
- **Analytics**: Dashboards, Metrics, Audit Logs

## Next Steps

1. Explore the API documentation at `/docs`
2. Create your first task via POST `/api/tasks`
3. Monitor execution via WebSocket at `/ws/tasks/{task_id}`
4. Review agent collaboration in `/api/collaboration`
5. Set up workflows in `/api/workflows`

For detailed API usage, see the interactive documentation at http://localhost:8001/docs
