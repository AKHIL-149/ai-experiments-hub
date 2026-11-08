# Multi-Agent Task Orchestrator

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph 0.6](https://img.shields.io/badge/LangGraph-0.6-orange.svg)](https://github.com/langchain-ai/langgraph)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An advanced AI-powered system that coordinates multiple specialized agents to autonomously break down, execute, and monitor complex tasks using LangGraph v0.6 and LangChain v0.3.

## 🚀 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys and database settings

# 3. Initialize database
./migrate.sh upgrade

# 4. Start the server
python3 server.py

# 5. Start the Celery worker (separate terminal) - required for tasks to
# actually execute, not just get created. The -Q flags matter: task_routes
# in celery_app.py sends different task types to separate queues, so a
# worker started without them only consumes the default "celery" queue and
# silently never picks up anything else - no error, tasks just sit pending.
PYTHONPATH=. celery -A celery_app worker --loglevel=info -Q celery,tasks,agents,orchestration,monitoring
```

Server runs on **http://localhost:8001**. Open it, and you land on the sign-in page.

## 🔐 Accounts and sign-in

The app has its own sign-in portal, so everyone who reaches **your running copy** uses **their own account**:

- **Create account** (username + password, email optional), **Sign in**, or **Continue as guest** (no details, removed after `GUEST_TTL_HOURS` = 24 h without use; a guest can turn the account into a real one and keep their tasks).
- **Per installation:** each clone has its own database and its own token-signing key (generated on first launch into `data/.jwt_secret`, git-ignored). Nothing is shared between copies and no account or password ships in the repository.
- **Other devices:** set `API_HOST=0.0.0.0` (the default in `.env.example`) and people on your network open `http://<your-computer>:8001` from their own devices and make their own accounts. Each sign-in is a device session: the panel at the top right lists your devices and signs any of them out, and a signed-out device is cut off immediately.
- **Real time:** the bar at the top right shows who is online right now, and sign-ins, sign-outs, new accounts and guests appear live to everyone (WebSocket `/api/ws/presence`, authenticated by its first message, not the URL).
- **Your data is yours:** tasks and workflows (and the dashboard numbers) belong to their creator; other accounts get a 404 for them. Admins (`ADMIN_USERNAMES`) see everything.
- **Safety:** passwords are bcrypt-hashed (8-72 bytes); failed sign-ins are throttled per account (5 / 15 min) and per address; account and guest creation are limited per address; `X-Forwarded-For` is ignored unless `TRUST_PROXY=true`; the API answers 401 without a valid session (`REQUIRE_LOGIN=false` turns that off).
- **Existing data:** tasks created before accounts existed have no owner, so only admins see them.

From a script, sign in once and send the token with every call (all the `curl` examples below need it):

```bash
TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/login -H "Content-Type: application/json" \
  -d '{"username":"YOUR_USERNAME","password":"YOUR_PASSWORD"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
curl -H "Authorization: Bearer $TOKEN" http://localhost:8001/api/tasks/
```

API: `POST /api/auth/register | login | guest | refresh | logout | guest/upgrade | change-password`, `GET /api/auth/me | sessions | online`, `DELETE /api/auth/sessions/{id}`; send `Authorization: Bearer <access_token>`.

📚 **Full Setup Guide**: See [STARTUP.md](STARTUP.md) for detailed installation instructions

## ✨ Key Features

### Multi-Agent Orchestration
- **5 Specialized Agents**: Research, Code, Data Analyst, Writer, and Planner
- **DAG-based Workflows**: Complex task dependency graphs
- **Shared Memory**: Inter-agent communication and state sharing
- **Human-in-the-Loop**: Approval gates for critical decisions

### Production-Ready Infrastructure
- **500+ REST API Endpoints**: Comprehensive API coverage
- **Real-time Monitoring**: Live dashboard at `/dashboard`
- **Database Migrations**: Alembic-managed schema versioning
- **WebSocket Support**: Real-time task progress updates
- **Complete Test Suite**: 150+ integration tests

### Advanced Features
- Agent reputation and trust scoring
- Coalition formation and negotiation
- Dynamic load balancing
- Cost tracking and optimization
- Distributed tracing
- Circuit breakers and retry logic

## 📊 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    FastAPI Server                       │
│                  (500+ Endpoints)                       │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   LangGraph  │  │    Celery    │  │  WebSockets  │ │
│  │   Workflow   │  │ Task Queue   │  │   Real-time  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
├─────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐  │
│  │           5 Specialized AI Agents                │  │
│  │  Research • Code • Data Analyst • Writer • Plan  │  │
│  └──────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│  │ PostgreSQL  │  │    Redis    │  │   OpenAI/   │   │
│  │  Database   │  │  Cache+Pub  │  │  Anthropic  │   │
│  └─────────────┘  └─────────────┘  └─────────────┘   │
└─────────────────────────────────────────────────────────┘
```

**Tech Stack**:
- **Framework**: FastAPI + LangGraph 0.6 + LangChain 0.3
- **Database**: PostgreSQL with SQLAlchemy ORM + Alembic migrations
- **Cache/Queue**: Redis + Celery
- **AI Models**: OpenAI GPT-4 / Anthropic Claude
- **Monitoring**: Built-in dashboard with real-time metrics

## 📖 Documentation

| Document | Description |
|----------|-------------|
| [STARTUP.md](STARTUP.md) | Complete setup and installation guide |
| [API_USAGE.md](API_USAGE.md) | API reference with 800+ lines of examples |
| [MONITORING.md](MONITORING.md) | Monitoring dashboard and metrics guide |
| [FIXES.md](FIXES.md) | Version 14.6.x bug fixes changelog |
| [examples/README.md](examples/README.md) | Workflow examples and templates |
| [tests/README.md](tests/README.md) | Testing guide and framework docs |
| [migrations/README.md](migrations/README.md) | Database migration documentation |

## 🎯 Example Workflows

The system includes 8 production-ready workflow templates:

```bash
# Run code review workflow
python3 examples/run_workflow.py --template code_review

# Run data analysis pipeline
python3 examples/run_workflow.py --template data_analysis

# Run content generation workflow
python3 examples/run_workflow.py --template content_generation
```

**Available Templates**:
- `code_review` - Multi-agent code review with security scanning
- `data_analysis` - ETL pipeline with visualization
- `content_generation` - AI-powered content creation
- `research_synthesis` - Information gathering and synthesis
- `testing_pipeline` - Test generation and execution
- `documentation_generation` - Automated docs creation
- `etl_workflow` - Data extraction, transformation, and loading
- `ml_experiment` - ML model training and evaluation

See [examples/README.md](examples/README.md) for detailed usage.

## 🖥️ Monitoring Dashboard

Access the real-time monitoring dashboard:

```
http://localhost:8001/dashboard
```

**Dashboard Features**:
- Task execution metrics (success rates, durations)
- Agent performance leaderboard
- System health status with alerts
- Workflow execution statistics
- Auto-refresh every 30 seconds

**API Endpoints**:
```bash
# Get dashboard overview
curl http://localhost:8001/api/monitoring/dashboard

# Get agent performance
curl http://localhost:8001/api/monitoring/agents

# Get system health
curl http://localhost:8001/api/monitoring/health
```

See [MONITORING.md](MONITORING.md) for complete guide.

## 🧪 Testing

The project includes a comprehensive test suite:

```bash
# Run all tests
./run_tests.sh

# Run with coverage
./run_tests.sh --coverage

# Run specific test category
pytest -m api          # API tests only
pytest -m integration  # Integration tests only
```

**Test Coverage**:
- 150+ integration tests
- API endpoint validation
- Agent execution workflows
- Database operations
- WebSocket connections
- Sign-in portal: `tests/integration/test_portal.py` (accounts, guests, sessions, isolation, live presence); it starts its own server on a temporary database

See [tests/README.md](tests/README.md) for testing guide.

## 💾 Database Migrations

Database schema is managed with Alembic:

```bash
# Run migrations
./migrate.sh upgrade

# Check current version
./migrate.sh status

# Create new migration
./migrate.sh create "Add new field"

# Rollback one version
./migrate.sh downgrade
```

See [migrations/README.md](migrations/README.md) for migration guide.

## 🔌 API Overview

The system provides 500+ REST endpoints organized by category:

### Core Endpoints
- `/api/tasks` - Task management and orchestration
- `/api/agents` - Agent lifecycle and capabilities
- `/api/workflows` - Workflow execution and templates
- `/api/executions` - Agent execution tracking

### Collaboration
- `/api/collaboration` - Agent collaboration protocols
- `/api/negotiations` - Agent negotiation system
- `/api/coalitions` - Coalition formation
- `/api/consensus` - Consensus mechanisms

### Intelligence
- `/api/learning` - Agent learning and adaptation
- `/api/knowledge` - Knowledge base management
- `/api/reputation` - Agent reputation scoring
- `/api/performance` - Performance analytics

### Infrastructure
- `/api/monitoring` - System monitoring and metrics
- `/api/health` - Health checks
- `/api/alerts` - Alert management
- `/api/audit` - Audit logging
- `/api/tracing` - Distributed tracing

### Quick Examples

**Create a task:**
```bash
curl -X POST http://localhost:8001/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Analyze sales data",
    "description": "Generate insights from Q4 sales data",
    "task_type": "data_analysis",
    "priority": "HIGH"
  }'
```

**Execute a workflow:**
```bash
curl -X POST http://localhost:8001/api/workflow-engine/workflows \
  -H "Content-Type: application/json" \
  -d @examples/workflows/code_review_workflow.json
```

**Monitor via WebSocket** (sign in first; the task sockets take `?token=<access_token>` and only open for your own tasks):
```javascript
const ws = new WebSocket('ws://localhost:8001/api/ws/tasks/{task_id}?token=' + accessToken);
ws.onmessage = (event) => {
  const update = JSON.parse(event.data);
  console.log('Task update:', update);
};
```

See [API_USAGE.md](API_USAGE.md) for comprehensive API documentation and [curl_examples.sh](curl_examples.sh) for ready-to-run examples.

## 🏗️ Project Structure

```
14-multi-agent-orchestrator/
├── src/
│   ├── agents/          # Agent implementations (Research, Code, etc.)
│   ├── api/             # FastAPI route handlers (500+ endpoints)
│   ├── core/            # Core functionality (config, database, logging)
│   ├── models/          # SQLAlchemy database models
│   ├── services/        # Business logic services
│   ├── utils/           # Utility functions
│   └── workflows/       # LangGraph workflow definitions
├── examples/            # Workflow templates and examples
├── tests/               # Integration and unit tests
├── migrations/          # Alembic database migrations
├── templates/           # HTML templates (monitoring dashboard)
├── scripts/             # Utility scripts
├── server.py            # Main FastAPI application (full server)
├── server_minimal.py    # Minimal server for testing
├── alembic.ini          # Alembic configuration
├── migrate.sh           # Migration helper script
└── requirements.txt     # Python dependencies
```

## 🚦 Server Modes

### Full Server (Production)
```bash
python3 server.py
```
- All 500+ endpoints enabled
- Complete monitoring and analytics
- Full agent capabilities
- WebSocket support

### Minimal Server (Development/Testing)
```bash
python3 server_minimal.py
```
- Core endpoints only
- Faster startup
- Lower resource usage
- Useful for testing

## 🔧 Configuration

Key environment variables (`.env`):

```bash
# API Settings
API_HOST=0.0.0.0
API_PORT=8001
DEBUG=false

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/orchestrator

# Redis
REDIS_URL=redis://localhost:6379/0

# LLM Provider
DEFAULT_LLM_PROVIDER=openai  # or anthropic
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Model Selection
DEFAULT_MODEL=gpt-4  # or claude-3-opus-20240229

# Feature Flags
ENABLE_MONITORING=true
ENABLE_DISTRIBUTED_TRACING=true
ENABLE_CACHING=true
```

See `.env.example` for complete configuration options.

## 📈 Recent Improvements (v14.6-14.7)

### Version 14.7.x - Features & Polish (Latest)
- ✅ **Monitoring Dashboard**: Real-time metrics and system health
- ✅ **Database Migrations**: Alembic schema management
- ✅ **Integration Tests**: 150+ test cases with pytest
- ✅ **API Documentation**: Comprehensive guides and examples
- ✅ **Workflow Templates**: 8 production-ready examples

### Version 14.6.x - Bug Fixes & Stability
- ✅ **Server Startup**: Fixed all import errors (42 files)
- ✅ **Workflow Model**: Created missing database models
- ✅ **Python 3.9 Compatibility**: Fixed type hint syntax
- ✅ **Import Paths**: Corrected all module imports

See [FIXES.md](FIXES.md) for detailed changelog.

## 🤝 Contributing

Contributions welcome! Please follow these guidelines:

1. **Code Style**: Follow PEP 8 and use `black` formatter
2. **Tests**: Add tests for new features
3. **Documentation**: Update relevant docs
4. **Commits**: Use semantic commit messages

```bash
# Format code
black src/

# Run linter
flake8 src/

# Run tests
pytest tests/
```

## 📝 License

MIT License - see [LICENSE](LICENSE) file for details

## 🆘 Support

- **Issues**: Report bugs via GitHub Issues
- **Documentation**: Check docs in `/docs` folder
- **Examples**: See `/examples` for usage patterns

## 🎓 Learning Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangChain Documentation](https://python.langchain.com/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Multi-Agent Systems](https://en.wikipedia.org/wiki/Multi-agent_system)

## 🗺️ Roadmap

- [ ] Advanced workflow visualization
- [ ] Agent marketplace and discovery
- [ ] Multi-region deployment support
- [ ] Enhanced security features
- [ ] Performance optimization tools

---

**Built with** 🤖 **by combining the power of LangGraph, LangChain, and FastAPI**

For questions or feedback, please open an issue on GitHub.
