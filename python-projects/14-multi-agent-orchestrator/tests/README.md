# Multi-Agent Task Orchestrator - Test Suite

Comprehensive test suite for the Multi-Agent Task Orchestrator API.

## Test Structure

```
tests/
├── __init__.py
├── conftest.py                    # Shared test fixtures and configuration
├── README.md                      # This file
├── integration/                   # Integration tests
│   ├── test_api_health.py        # Health check endpoints
│   ├── test_api_workflows.py     # Workflow engine endpoints  
│   ├── test_api_tasks.py         # Task management endpoints
│   └── test_api_agents.py        # Agent endpoints
└── unit/                          # Unit tests
    └── ...
```

## Running Tests

### Quick Start

```bash
# Run all tests
./run_tests.sh

# Run with coverage
./run_tests.sh --coverage

# Run specific test type
./run_tests.sh integration
./run_tests.sh unit
```

### Using Pytest Directly

```bash
# Run all tests
pytest

# Run integration tests only
pytest -m integration

# Run specific test file
pytest tests/integration/test_api_workflows.py

# Run specific test class
pytest tests/integration/test_api_workflows.py::TestWorkflowCreation

# Run specific test
pytest tests/integration/test_api_workflows.py::TestWorkflowCreation::test_create_workflow

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=src --cov-report=html

# Run fast tests only (skip slow)
pytest -m "not slow"
```

## Test Markers

Tests are organized using pytest markers:

- `@pytest.mark.unit` - Unit tests (fast, isolated)
- `@pytest.mark.integration` - Integration tests (slower, with dependencies)
- `@pytest.mark.database` - Tests requiring database
- `@pytest.mark.slow` - Slow-running tests
- `@pytest.mark.api` - API endpoint tests
- `@pytest.mark.workflows` - Workflow-specific tests
- `@pytest.mark.agents` - Agent-specific tests
- `@pytest.mark.tasks` - Task-specific tests

Filter tests by marker:

```bash
# Run only integration tests
pytest -m integration

# Run only fast tests
pytest -m "not slow"

# Run workflow tests
pytest -m workflows

# Combine markers
pytest -m "integration and not slow"
```

## Test Coverage

Generate coverage reports:

```bash
# HTML report
pytest --cov=src --cov-report=html
open htmlcov/index.html

# Terminal report
pytest --cov=src --cov-report=term-missing

# Coverage with minimum threshold
pytest --cov=src --cov-fail-under=70
```

## Integration Tests

Integration tests verify API endpoints work correctly end-to-end.

### Prerequisites

1. **Start the server** (in another terminal):
   ```bash
   python3 server.py
   ```

2. **Database and Redis** must be running:
   ```bash
   # PostgreSQL
   pg_ctl start
   
   # Redis
   redis-server
   ```

### Test Categories

**Health Checks** (`test_api_health.py`):
- Server health status
- Root endpoint
- API documentation availability

**Workflows** (`test_api_workflows.py`):
- Create workflows
- Execute workflows
- Monitor workflow status
- Pause/resume workflows
- Validate workflow configuration
- Delete workflows

**Tasks** (`test_api_tasks.py`):
- Create tasks
- Retrieve task details
- Update tasks
- Filter and search tasks
- Delete tasks
- Task dependencies

**Agents** (`test_api_agents.py`):
- List agents
- Get agent details
- Agent performance metrics
- Agent capabilities
- Agent statistics

## Writing New Tests

### Integration Test Template

```python
"""
Integration tests for [Feature] API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from server import app


@pytest.fixture(scope="module")
def client():
    """Create test client"""
    with TestClient(app) as c:
        yield c


class TestFeature:
    """Test feature endpoints"""

    def test_feature_endpoint(self, client):
        """Test feature endpoint"""
        response = client.get("/api/feature")
        
        assert response.status_code == 200
        data = response.json()
        assert "expected_field" in data
```

### Using Fixtures

```python
def test_with_sample_data(client, sample_task_data):
    """Test using predefined fixtures"""
    response = client.post("/api/tasks", json=sample_task_data)
    
    assert response.status_code == 200
    assert response.json()["title"] == sample_task_data["title"]
```

## Continuous Integration

Tests run automatically on:
- Pull requests
- Commits to main branch
- Scheduled nightly builds

GitHub Actions workflow: `.github/workflows/tests.yml`

## Troubleshooting

### Tests Fail to Connect

**Error**: `Connection refused` or `Server not available`

**Solution**: Start the server first:
```bash
python3 server.py
```

### Database Errors

**Error**: `Could not connect to database`

**Solution**: Ensure PostgreSQL is running:
```bash
pg_ctl start
createdb multi_agent_orchestrator
```

### Import Errors

**Error**: `ModuleNotFoundError`

**Solution**: Install dependencies:
```bash
pip install -r requirements.txt
```

### Redis Connection Errors

**Error**: `Redis connection failed`

**Solution**: Start Redis:
```bash
redis-server
```

### Slow Tests

Run only fast tests:
```bash
pytest -m "not slow"
```

Or increase timeout:
```bash
pytest --timeout=300
```

## Test Best Practices

1. **Isolation**: Each test should be independent
2. **Cleanup**: Use fixtures to clean up resources
3. **Assertions**: Use clear, specific assertions
4. **Naming**: Use descriptive test names (test_should_do_what_when_condition)
5. **Documentation**: Add docstrings to complex tests
6. **Fixtures**: Reuse fixtures for common setup
7. **Markers**: Tag tests appropriately for filtering

## Coverage Goals

- **Overall**: > 70%
- **Core modules**: > 80%
- **API endpoints**: > 90%

Check current coverage:
```bash
./run_tests.sh --coverage
```

## Performance Testing

For load testing and performance benchmarks:

```bash
# Install locust
pip install locust

# Run load tests
locust -f tests/performance/locustfile.py
```

## Next Steps

1. Run the test suite: `./run_tests.sh`
2. Check coverage: `./run_tests.sh --coverage`
3. Write tests for new features
4. Keep coverage above 70%

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Coverage.py](https://coverage.readthedocs.io/)
