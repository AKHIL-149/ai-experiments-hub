# Changelog

All notable changes to the Multi-Agent Task Orchestrator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [14.7.5] - 2026-07-14

### Added
- **Monitoring Dashboard**: Real-time web dashboard at `/dashboard`
  - Auto-refreshing metrics (30-second intervals)
  - Visual KPI cards for tasks, agents, workflows
  - Agent performance leaderboard
  - System health status with warnings
  - Time-range selectors (24h, 7d, 30d)
- **MonitoringService**: Backend service for metrics collection
  - Dashboard overview aggregation
  - Task metrics by time range
  - Agent performance tracking
  - Workflow execution statistics
  - System health monitoring with issue detection
- **Monitoring API Endpoints**:
  - `GET /api/monitoring/dashboard` - Overview metrics
  - `GET /api/monitoring/tasks` - Task statistics
  - `GET /api/monitoring/agents` - Agent performance
  - `GET /api/monitoring/workflows` - Workflow metrics
  - `GET /api/monitoring/health` - System health status
- **MONITORING.md**: Comprehensive monitoring documentation

## [14.7.4] - 2026-07-14

### Added
- **Alembic Database Migrations**: Complete migration infrastructure
  - `alembic.ini` configuration
  - `migrations/env.py` with all model imports
  - `migrations/script.py.mako` template
  - `001_add_workflow_models.py` initial migration
- **Migration Helper Script**: `migrate.sh` with commands
  - `upgrade` - Apply migrations
  - `downgrade` - Rollback migrations
  - `status` - Check current version
  - `create` - Generate new migration
  - `test` - Test migration round-trip
- **migrations/README.md**: 400+ line migration guide
  - Command reference
  - Best practices
  - Troubleshooting
  - Production deployment checklist

### Changed
- **STARTUP.md**: Added database migration step to setup process

## [14.7.3] - 2026-07-14

### Added
- **Integration Test Suite**: 150+ test cases
  - `test_api_health.py` - Health check endpoints
  - `test_api_tasks.py` - Task management endpoints
  - `test_api_agents.py` - Agent endpoints
  - `test_api_workflows.py` - Workflow endpoints
- **Test Configuration**:
  - `pytest.ini` with markers and coverage settings
  - `run_tests.sh` test runner script
  - `tests/README.md` testing guide
- **Test Fixtures**: Reusable test client and sample data

## [14.7.2] - 2026-07-14

### Added
- **API_USAGE.md**: Comprehensive API documentation (800+ lines)
  - Complete endpoint reference
  - Request/response examples
  - Authentication guide
  - WebSocket usage
  - Error handling patterns
- **curl_examples.sh**: 17 ready-to-run API examples
  - Task management
  - Agent operations
  - Workflow execution
  - Monitoring
  - Authentication flows

## [14.7.1] - 2026-07-14

### Added
- **8 Production Workflow Templates**:
  - `code_review_workflow.py` - Multi-agent code review
  - `data_analysis_workflow.py` - ETL pipeline
  - `content_generation_workflow.py` - Content creation
  - `research_synthesis_workflow.py` - Research aggregation
  - `testing_pipeline_workflow.py` - Test generation
  - `documentation_generation_workflow.py` - Docs automation
  - `etl_workflow.py` - Data processing
  - `ml_experiment_workflow.py` - ML training pipeline
- **run_workflow.py**: Interactive workflow executor
- **examples/README.md**: Usage guide for workflow templates

## [14.6.8] - 2026-07-14

### Added
- **FIXES.md**: Comprehensive changelog of bug fixes
- **server_minimal.py**: Minimal server for testing (core endpoints only)
- **STARTUP.md**: Complete startup and installation guide

## [14.6.7] - 2026-07-14

### Fixed
- Server startup documentation and guides

## [14.6.6] - 2026-07-14

### Fixed
- Verified complete server startup with all 500+ endpoints
- Tested health check, docs, and API functionality

## [14.6.5] - 2026-07-14

### Fixed
- **Import Path Errors** (42 files):
  - Fixed 12 service files using wrong model import path
  - Fixed 13 API files using wrong database import path
  - Corrected all `src.database` → `src.core.database` imports
  - Corrected all `src.models.database` → `src.models` imports

- **Workflow Model Missing**:
  - Created `src/models/workflow.py` with Workflow and WorkflowStep models
  - Added WorkflowStatus and WorkflowType enums
  - Updated `src/models/__init__.py` with new exports
  - Fixed workflow_engine.py and shared_memory_service.py imports

- **Python 3.9 Compatibility**:
  - Fixed union type syntax (`dict | str` → `Union[dict, str]`)
  - Added proper typing imports
  - Fixed config_management.py type annotations

- **Syntax Errors**:
  - Added missing `pass` statement in testing_framework.py
  - Fixed empty conditional blocks

### Added
- Complete Workflow model with JSON fields for flexible definitions
- WorkflowStep model for DAG workflow support
- Proper enum types for workflow status and type

## [14.6.0-14.6.4] - Previous Versions

### Added
- Initial FastAPI server structure
- 500+ REST API endpoints across all categories
- LangGraph v0.6 multi-agent orchestration
- PostgreSQL database with SQLAlchemy models
- Redis caching and pub/sub
- Celery task queue
- WebSocket real-time updates
- JWT authentication
- Agent implementations (Research, Code, Data Analyst, Writer, Planner)
- Workflow engine with DAG support
- Shared memory system
- Agent collaboration protocols
- Reputation and trust scoring
- Load balancing
- Circuit breakers
- Distributed tracing
- Cost tracking
- Performance monitoring
- Alert management
- Audit logging
- Backup/recovery
- Configuration management
- Secret management
- And 480+ other endpoints

## Version History Overview

### Phase 14.7 - Features & Examples (July 2026)
Focus: Production-ready features, documentation, and testing
- Monitoring dashboard
- Database migrations
- Integration tests
- API documentation
- Workflow examples

### Phase 14.6 - Bug Fixes & Stability (July 2026)
Focus: Server startup fixes and compatibility
- Fixed all import errors
- Added missing models
- Python 3.9 compatibility
- Complete server startup

### Phase 14.0-14.5 - Initial Development
Focus: Core infrastructure and features
- Multi-agent system
- 500+ API endpoints
- Database and caching
- Authentication
- Workflow orchestration

## Breaking Changes

### [14.7.4] Database Migrations
- **Action Required**: Run `alembic upgrade head` or `./migrate.sh upgrade`
- Database schema now managed via Alembic migrations
- New `alembic_version` table tracks migration state

### [14.6.5] Model Imports
- Import paths changed from `src.models.database` to `src.models`
- Database imports changed from `src.database` to `src.core.database`
- Update any custom code importing these modules

## Upgrade Guide

### From 14.6.x to 14.7.x

1. **Install New Dependencies**:
   ```bash
   pip install --upgrade -r requirements.txt
   ```

2. **Run Database Migrations**:
   ```bash
   ./migrate.sh upgrade
   ```

3. **Update Environment Variables** (optional):
   ```bash
   # Add to .env for monitoring features
   ENABLE_MONITORING=true
   ```

4. **Restart Server**:
   ```bash
   python3 server.py
   ```

5. **Access New Features**:
   - Monitoring dashboard: http://localhost:8001/dashboard
   - API documentation: See API_USAGE.md
   - Workflow examples: See examples/README.md

### From 14.5.x to 14.6.x

1. **Update Imports** in custom code:
   ```python
   # Old
   from src.models.database import Task
   from src.database import get_db

   # New
   from src.models import Task
   from src.core.database import get_db
   ```

2. **Python Version**: Ensure Python 3.9+ is installed

3. **Restart Services**: No database changes, just restart server

## Deprecations

None currently.

## Security Updates

### [14.7.x]
- No security updates in this release

### [14.6.x]
- Fixed import paths that could cause module resolution issues
- Improved error handling in authentication flows

## Known Issues

### [14.7.5]
- Dashboard metrics may be slow on very large databases (>100k tasks)
  - **Workaround**: Add database indexes on frequently queried columns
  - **Fix**: Planned for 14.8 - metric caching and pre-aggregation

### [14.7.4]
- Alembic auto-generate may miss some custom index definitions
  - **Workaround**: Create manual migrations for custom indexes
  - See migrations/README.md for manual migration guide

### [14.6.x]
- None

## Contributors

- Primary Development: AI Experiments Hub Team
- Testing: Community Contributors
- Documentation: Community Contributors

## Links

- [GitHub Repository](https://github.com/yourusername/ai-experiments-hub)
- [Documentation](./README.md)
- [Issue Tracker](https://github.com/yourusername/ai-experiments-hub/issues)
- [LangGraph](https://github.com/langchain-ai/langgraph)
- [FastAPI](https://fastapi.tiangolo.com/)

---

For detailed API changes, see [API_USAGE.md](API_USAGE.md)
For migration guides, see [migrations/README.md](migrations/README.md)
For monitoring setup, see [MONITORING.md](MONITORING.md)
