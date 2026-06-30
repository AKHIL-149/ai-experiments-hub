# Project 14: Multi-Agent Task Orchestrator

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

## Project Status

🚧 **In Development** - Block Phase 1: Foundation & Infrastructure (20% complete)

Current Progress: Commit 7/100

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
