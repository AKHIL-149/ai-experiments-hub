"""
Pytest configuration and shared fixtures
"""

import os
import pytest
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from src.models.base import Base
from src.models.task import Task, TaskStatus
from src.models.agent import Agent, AgentRole, AgentStatus
from src.core.config import settings
from src.core.database import DatabaseManager


# Set testing environment
os.environ['TESTING'] = 'true'


@pytest.fixture(scope="session")
def test_db_url() -> str:
    """
    Generate test database URL

    Returns:
        str: SQLite in-memory database URL for testing
    """
    return "sqlite:///:memory:"


@pytest.fixture(scope="session")
def engine(test_db_url):
    """
    Create test database engine

    Args:
        test_db_url: Test database URL fixture

    Returns:
        Engine: SQLAlchemy engine for testing
    """
    engine = create_engine(
        test_db_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )

    # Create all tables
    Base.metadata.create_all(bind=engine)

    yield engine

    # Drop all tables after tests
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(engine) -> Generator[Session, None, None]:
    """
    Create a new database session for a test

    Args:
        engine: SQLAlchemy engine fixture

    Yields:
        Session: Database session for testing
    """
    connection = engine.connect()
    transaction = connection.begin()

    SessionLocal = sessionmaker(bind=connection)
    session = SessionLocal()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def sample_agent(db_session) -> Agent:
    """
    Create a sample agent for testing

    Args:
        db_session: Database session fixture

    Returns:
        Agent: Sample agent instance
    """
    agent = Agent(
        name="Test Coder Agent",
        role=AgentRole.CODER,
        description="Test agent for coding tasks",
        status=AgentStatus.IDLE,
        llm_provider="openai",
        llm_model="gpt-4",
        temperature=0.3,
        max_tokens=2048,
        system_prompt="You are a test coding agent."
    )
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    return agent


@pytest.fixture
def sample_task(db_session, sample_agent) -> Task:
    """
    Create a sample task for testing

    Args:
        db_session: Database session fixture
        sample_agent: Sample agent fixture

    Returns:
        Task: Sample task instance
    """
    task = Task(
        title="Test Task",
        description="This is a test task",
        task_type="coding",
        status=TaskStatus.PENDING,
        priority=5,
        assigned_agent_id=sample_agent.id,
        input_data={"requirement": "Test requirement"}
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


@pytest.fixture
def multiple_agents(db_session) -> list[Agent]:
    """
    Create multiple agents for testing

    Args:
        db_session: Database session fixture

    Returns:
        list[Agent]: List of agent instances
    """
    agents = [
        Agent(
            name="Research Agent",
            role=AgentRole.RESEARCHER,
            status=AgentStatus.IDLE,
            temperature=0.7
        ),
        Agent(
            name="Coder Agent",
            role=AgentRole.CODER,
            status=AgentStatus.IDLE,
            temperature=0.3
        ),
        Agent(
            name="Reviewer Agent",
            role=AgentRole.REVIEWER,
            status=AgentStatus.IDLE,
            temperature=0.4
        ),
    ]

    for agent in agents:
        db_session.add(agent)

    db_session.commit()

    for agent in agents:
        db_session.refresh(agent)

    return agents


@pytest.fixture
def multiple_tasks(db_session, multiple_agents) -> list[Task]:
    """
    Create multiple tasks for testing

    Args:
        db_session: Database session fixture
        multiple_agents: Multiple agents fixture

    Returns:
        list[Task]: List of task instances
    """
    tasks = [
        Task(
            title="Research Task",
            task_type="research",
            status=TaskStatus.PENDING,
            priority=7,
            assigned_agent_id=multiple_agents[0].id
        ),
        Task(
            title="Coding Task",
            task_type="coding",
            status=TaskStatus.QUEUED,
            priority=8,
            assigned_agent_id=multiple_agents[1].id
        ),
        Task(
            title="Review Task",
            task_type="review",
            status=TaskStatus.IN_PROGRESS,
            priority=6,
            assigned_agent_id=multiple_agents[2].id
        ),
    ]

    for task in tasks:
        db_session.add(task)

    db_session.commit()

    for task in tasks:
        db_session.refresh(task)

    return tasks


@pytest.fixture
def mock_llm_response():
    """
    Mock LLM API response for testing

    Returns:
        dict: Mock LLM response data
    """
    return {
        "id": "test-response-id",
        "model": "gpt-4",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "This is a test response from the LLM."
                },
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 15,
            "total_tokens": 25
        }
    }


@pytest.fixture
def mock_celery_task():
    """
    Mock Celery task for testing

    Returns:
        Mock: Mock Celery task object
    """
    class MockCeleryTask:
        def __init__(self):
            self.id = "test-task-id"
            self.state = "PENDING"
            self.result = None

        def get(self, timeout=None):
            return self.result

        def ready(self):
            return self.state in ["SUCCESS", "FAILURE"]

        def successful(self):
            return self.state == "SUCCESS"

        def failed(self):
            return self.state == "FAILURE"

    return MockCeleryTask()


# Pytest configuration hooks

def pytest_configure(config):
    """
    Configure pytest with custom settings
    """
    # Set environment variables for testing
    os.environ['TESTING'] = 'true'
    os.environ['LOG_LEVEL'] = 'WARNING'


def pytest_collection_modifyitems(config, items):
    """
    Modify test collection to add markers automatically
    """
    for item in items:
        # Add unit marker to tests in unit/ directory
        if "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)

        # Add integration marker to tests in integration/ directory
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)

        # Add database marker to tests using db_session fixture
        if "db_session" in item.fixturenames:
            item.add_marker(pytest.mark.database)
