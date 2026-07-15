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
```

Server runs on **http://localhost:8001**

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

**Monitor via WebSocket:**
```javascript
const ws = new WebSocket('ws://localhost:8001/ws/tasks/{task_id}');
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
