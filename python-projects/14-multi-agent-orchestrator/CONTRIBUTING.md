# Contributing to Multi-Agent Task Orchestrator

Thank you for your interest in contributing to the Multi-Agent Task Orchestrator! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Development Workflow](#development-workflow)
- [Coding Standards](#coding-standards)
- [Testing Guidelines](#testing-guidelines)
- [Documentation](#documentation)
- [Pull Request Process](#pull-request-process)
- [Release Process](#release-process)

## Code of Conduct

This project adheres to a code of conduct that all contributors are expected to follow:

- **Be Respectful**: Treat everyone with respect and kindness
- **Be Collaborative**: Work together and help others
- **Be Professional**: Maintain professional communication
- **Be Inclusive**: Welcome contributors from all backgrounds
- **Focus on the Project**: Keep discussions focused on improving the project

## Getting Started

### Prerequisites

Before you begin, ensure you have the following installed:

- Python 3.9 or higher
- PostgreSQL 14 or higher
- Redis 7 or higher
- Git
- pip (Python package manager)

### Fork and Clone

1. Fork the repository on GitHub
2. Clone your fork locally:

```bash
git clone https://github.com/YOUR_USERNAME/ai-experiments-hub.git
cd ai-experiments-hub/python-projects/14-multi-agent-orchestrator
```

3. Add the upstream repository:

```bash
git remote add upstream https://github.com/ORIGINAL_OWNER/ai-experiments-hub.git
```

## Development Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Development dependencies
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your local configuration
```

### 3. Set Up Database

```bash
# Create database
createdb multi_agent_orchestrator

# Run migrations
./migrate.sh upgrade
```

### 4. Start Services

```bash
# Terminal 1: Start PostgreSQL (if not running)
# Terminal 2: Start Redis (if not running)

# Terminal 3: Start the development server
python3 server.py
```

### 5. Verify Setup

```bash
# Run health check
curl http://localhost:8001/api/health

# Run tests
./run_tests.sh
```

## Development Workflow

### 1. Create a Branch

Always create a new branch for your work:

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-number-description
```

Branch naming conventions:
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation updates
- `refactor/` - Code refactoring
- `test/` - Test improvements

### 2. Make Changes

- Write clear, concise code
- Follow the coding standards (see below)
- Add tests for new features
- Update documentation as needed

### 3. Test Your Changes

```bash
# Run all tests
./run_tests.sh

# Run specific tests
pytest tests/integration/test_api_tasks.py

# Run with coverage
./run_tests.sh --coverage

# Check code style
black --check src/
flake8 src/
```

### 4. Commit Your Changes

Use semantic commit messages:

```bash
git commit -m "feat: Add agent collaboration feature"
git commit -m "fix: Resolve database connection timeout"
git commit -m "docs: Update API usage guide"
git commit -m "test: Add workflow execution tests"
```

Commit message format:
```
<type>: <subject>

<body>

<footer>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

### 5. Push and Create Pull Request

```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub.

## Coding Standards

### Python Style Guide

We follow PEP 8 with some specific conventions:

#### Code Formatting

- Use **Black** for code formatting:
  ```bash
  black src/
  ```

- Line length: 100 characters maximum
- Use 4 spaces for indentation (no tabs)

#### Naming Conventions

- **Classes**: `PascalCase`
  ```python
  class AgentOrchestrator:
      pass
  ```

- **Functions/Methods**: `snake_case`
  ```python
  def execute_workflow(task_id: int):
      pass
  ```

- **Constants**: `UPPER_SNAKE_CASE`
  ```python
  MAX_RETRY_ATTEMPTS = 3
  ```

- **Private members**: Prefix with single underscore
  ```python
  def _internal_helper():
      pass
  ```

#### Type Hints

Always use type hints for function signatures:

```python
from typing import List, Dict, Optional

def process_tasks(
    task_ids: List[int],
    options: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Process multiple tasks with optional configuration."""
    pass
```

#### Docstrings

Use Google-style docstrings:

```python
def create_agent(name: str, role: AgentRole, capabilities: List[str]) -> Agent:
    """
    Create a new agent with specified capabilities.

    Args:
        name: Human-readable name for the agent
        role: Agent role (RESEARCH, CODE, etc.)
        capabilities: List of agent capabilities

    Returns:
        Newly created Agent instance

    Raises:
        ValueError: If name is empty or role is invalid

    Example:
        >>> agent = create_agent("Research Agent", AgentRole.RESEARCH, ["web_search"])
        >>> print(agent.name)
        Research Agent
    """
    pass
```

#### Imports

Group imports in this order:

```python
# 1. Standard library
import os
import sys
from typing import List, Dict

# 2. Third-party libraries
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session

# 3. Local application imports
from src.core.database import get_db
from src.models import Task, Agent
from src.services.agent_service import AgentService
```

### Code Organization

#### File Structure

- One class per file (generally)
- Related functionality grouped in modules
- Keep files under 500 lines when possible

#### Function Length

- Keep functions focused and under 50 lines
- Extract complex logic into helper functions
- Use descriptive names for clarity

#### Error Handling

Always handle errors appropriately:

```python
from src.core.exceptions import AgentNotFoundException

def get_agent(agent_id: int) -> Agent:
    """Retrieve agent by ID."""
    try:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise AgentNotFoundException(f"Agent {agent_id} not found")
        return agent
    except SQLAlchemyError as e:
        logger.error(f"Database error retrieving agent {agent_id}: {e}")
        raise
```

## Testing Guidelines

### Test Structure

Follow the Arrange-Act-Assert pattern:

```python
def test_create_task():
    # Arrange
    task_data = {
        "title": "Test Task",
        "description": "Test description",
        "priority": "HIGH"
    }

    # Act
    response = client.post("/api/tasks", json=task_data)

    # Assert
    assert response.status_code == 200
    assert response.json()["title"] == "Test Task"
```

### Test Coverage

- Aim for 80%+ code coverage
- Test happy paths and error cases
- Include edge cases and boundary conditions

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/integration/test_api_agents.py

# Specific test function
pytest tests/integration/test_api_agents.py::test_create_agent

# With markers
pytest -m api          # API tests only
pytest -m integration  # Integration tests only

# With coverage
pytest --cov=src --cov-report=html
```

### Test Fixtures

Reuse fixtures for common setup:

```python
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client():
    """Create test client."""
    from server import app
    with TestClient(app) as c:
        yield c

@pytest.fixture
def sample_task():
    """Create sample task data."""
    return {
        "title": "Test Task",
        "description": "Test description",
        "priority": "HIGH"
    }

def test_create_task(client, sample_task):
    response = client.post("/api/tasks", json=sample_task)
    assert response.status_code == 200
```

## Documentation

### Code Documentation

- Document all public APIs with docstrings
- Include type hints
- Provide usage examples in docstrings
- Keep comments up-to-date with code changes

### API Documentation

- Update `API_USAGE.md` for new endpoints
- Include request/response examples
- Document error responses
- Add curl examples to `curl_examples.sh`

### README Updates

Update `README.md` when adding:
- New features
- New dependencies
- Configuration options
- Breaking changes

## Pull Request Process

### Before Submitting

1. **Update from upstream**:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Run all checks**:
   ```bash
   # Format code
   black src/

   # Run linters
   flake8 src/

   # Run tests
   ./run_tests.sh --coverage

   # Check types (if using mypy)
   mypy src/
   ```

3. **Update documentation**:
   - Add docstrings to new functions
   - Update relevant .md files
   - Add examples if applicable

### PR Template

When creating a pull request, include:

```markdown
## Description
Brief description of the changes

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change
- [ ] Documentation update

## Testing
Describe how you tested your changes

## Checklist
- [ ] Code follows style guidelines
- [ ] Self-review completed
- [ ] Comments added for complex code
- [ ] Documentation updated
- [ ] Tests added/updated
- [ ] All tests passing
- [ ] No new warnings
```

### Review Process

1. Maintainers will review your PR
2. Address any requested changes
3. Once approved, your PR will be merged

### Commit Squashing

- We prefer clean commit history
- Squash commits if requested during review
- Use meaningful commit messages

## Release Process

### Versioning

We use semantic versioning (MAJOR.MINOR.PATCH):

- **MAJOR**: Breaking changes
- **MINOR**: New features (backward compatible)
- **PATCH**: Bug fixes (backward compatible)

### Release Checklist

1. Update version numbers
2. Update CHANGELOG.md
3. Run full test suite
4. Create git tag
5. Push to repository
6. Create GitHub release

## Getting Help

- **Issues**: Check existing GitHub issues
- **Questions**: Open a discussion on GitHub
- **Chat**: Join our community chat (if available)

## Additional Resources

- [Python PEP 8 Style Guide](https://www.python.org/dev/peps/pep-0008/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to the Multi-Agent Task Orchestrator! 🚀
