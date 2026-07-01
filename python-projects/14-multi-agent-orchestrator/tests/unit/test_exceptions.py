"""
Unit tests for custom exceptions
"""

import pytest
from src.core.exceptions import (
    MultiAgentOrchestratorException,
    TaskException,
    TaskNotFoundError,
    TaskAlreadyExistsError,
    TaskDependencyError,
    TaskExecutionError,
    AgentException,
    AgentNotFoundError,
    AgentNotAvailableError,
    AgentCapabilityError,
    LLMException,
    LLMAPIError,
    LLMRateLimitError,
    LLMTokenLimitError,
    DatabaseException,
    DatabaseConnectionError,
    DatabaseIntegrityError,
    ValidationException,
    InvalidInputError,
    ConfigurationException,
    MissingConfigurationError,
    InvalidConfigurationError,
    WorkflowException,
    CircularDependencyError,
    WorkflowExecutionError
)


class TestTaskExceptions:
    """Tests for task-related exceptions"""

    def test_task_not_found_error(self):
        """Test TaskNotFoundError"""
        error = TaskNotFoundError(task_id=42)
        assert error.task_id == 42
        assert "Task 42 not found" in str(error)
        assert isinstance(error, TaskException)
        assert isinstance(error, MultiAgentOrchestratorException)

    def test_task_already_exists_error(self):
        """Test TaskAlreadyExistsError"""
        error = TaskAlreadyExistsError(task_id=42)
        assert error.task_id == 42
        assert "Task 42 already exists" in str(error)
        assert isinstance(error, TaskException)

    def test_task_dependency_error(self):
        """Test TaskDependencyError"""
        error = TaskDependencyError("Circular dependency detected")
        assert "Task dependency error" in str(error)
        assert "Circular dependency detected" in str(error)
        assert isinstance(error, TaskException)

    def test_task_execution_error(self):
        """Test TaskExecutionError"""
        error = TaskExecutionError(task_id=42, error="Timeout")
        assert error.task_id == 42
        assert error.error == "Timeout"
        assert "Task 42 execution failed" in str(error)
        assert "Timeout" in str(error)
        assert isinstance(error, TaskException)


class TestAgentExceptions:
    """Tests for agent-related exceptions"""

    def test_agent_not_found_error(self):
        """Test AgentNotFoundError"""
        error = AgentNotFoundError(agent_id=10)
        assert error.agent_id == 10
        assert "Agent 10 not found" in str(error)
        assert isinstance(error, AgentException)

    def test_agent_not_available_error_without_reason(self):
        """Test AgentNotAvailableError without reason"""
        error = AgentNotAvailableError(agent_id=10)
        assert error.agent_id == 10
        assert "Agent 10 is not available" in str(error)
        assert isinstance(error, AgentException)

    def test_agent_not_available_error_with_reason(self):
        """Test AgentNotAvailableError with reason"""
        error = AgentNotAvailableError(agent_id=10, reason="Currently busy")
        assert error.agent_id == 10
        assert "Agent 10 is not available: Currently busy" in str(error)

    def test_agent_capability_error(self):
        """Test AgentCapabilityError"""
        error = AgentCapabilityError(agent_id=10, required_capability="code_review")
        assert error.agent_id == 10
        assert error.required_capability == "code_review"
        assert "Agent 10 lacks required capability: code_review" in str(error)
        assert isinstance(error, AgentException)


class TestLLMExceptions:
    """Tests for LLM-related exceptions"""

    def test_llm_api_error(self):
        """Test LLMAPIError"""
        error = LLMAPIError(provider="openai", error="Invalid API key")
        assert error.provider == "openai"
        assert error.error == "Invalid API key"
        assert "LLM API error (openai)" in str(error)
        assert "Invalid API key" in str(error)
        assert isinstance(error, LLMException)

    def test_llm_rate_limit_error_without_retry_after(self):
        """Test LLMRateLimitError without retry_after"""
        error = LLMRateLimitError(provider="openai")
        assert error.provider == "openai"
        assert error.retry_after is None
        assert "LLM rate limit exceeded (openai)" in str(error)
        assert isinstance(error, LLMException)

    def test_llm_rate_limit_error_with_retry_after(self):
        """Test LLMRateLimitError with retry_after"""
        error = LLMRateLimitError(provider="anthropic", retry_after=60)
        assert error.provider == "anthropic"
        assert error.retry_after == 60
        assert "LLM rate limit exceeded (anthropic)" in str(error)
        assert "Retry after 60 seconds" in str(error)

    def test_llm_token_limit_error(self):
        """Test LLMTokenLimitError"""
        error = LLMTokenLimitError(
            provider="openai",
            tokens_used=5000,
            token_limit=4096
        )
        assert error.provider == "openai"
        assert error.tokens_used == 5000
        assert error.token_limit == 4096
        assert "LLM token limit exceeded (openai)" in str(error)
        assert "used 5000 tokens" in str(error)
        assert "limit 4096" in str(error)
        assert isinstance(error, LLMException)


class TestDatabaseExceptions:
    """Tests for database-related exceptions"""

    def test_database_connection_error(self):
        """Test DatabaseConnectionError"""
        error = DatabaseConnectionError("Could not connect to host")
        assert "Database connection error" in str(error)
        assert "Could not connect to host" in str(error)
        assert isinstance(error, DatabaseException)

    def test_database_integrity_error(self):
        """Test DatabaseIntegrityError"""
        error = DatabaseIntegrityError("Duplicate key violation")
        assert "Database integrity error" in str(error)
        assert "Duplicate key violation" in str(error)
        assert isinstance(error, DatabaseException)


class TestValidationExceptions:
    """Tests for validation-related exceptions"""

    def test_invalid_input_error(self):
        """Test InvalidInputError"""
        error = InvalidInputError(field="email", error="Invalid format")
        assert error.field == "email"
        assert "Invalid input for 'email'" in str(error)
        assert "Invalid format" in str(error)
        assert isinstance(error, ValidationException)


class TestConfigurationExceptions:
    """Tests for configuration-related exceptions"""

    def test_missing_configuration_error(self):
        """Test MissingConfigurationError"""
        error = MissingConfigurationError(config_key="DATABASE_URL")
        assert error.config_key == "DATABASE_URL"
        assert "Missing required configuration: DATABASE_URL" in str(error)
        assert isinstance(error, ConfigurationException)

    def test_invalid_configuration_error(self):
        """Test InvalidConfigurationError"""
        error = InvalidConfigurationError(
            config_key="MAX_RETRIES",
            error="Must be positive integer"
        )
        assert error.config_key == "MAX_RETRIES"
        assert "Invalid configuration for 'MAX_RETRIES'" in str(error)
        assert "Must be positive integer" in str(error)
        assert isinstance(error, ConfigurationException)


class TestWorkflowExceptions:
    """Tests for workflow-related exceptions"""

    def test_circular_dependency_error(self):
        """Test CircularDependencyError"""
        error = CircularDependencyError(task_ids=[1, 2, 3, 1])
        assert error.task_ids == [1, 2, 3, 1]
        assert "Circular dependency detected" in str(error)
        assert "1 -> 2 -> 3 -> 1" in str(error)
        assert isinstance(error, WorkflowException)

    def test_workflow_execution_error(self):
        """Test WorkflowExecutionError"""
        error = WorkflowExecutionError(workflow_id="wf-123", error="Node failed")
        assert error.workflow_id == "wf-123"
        assert "Workflow wf-123 execution failed" in str(error)
        assert "Node failed" in str(error)
        assert isinstance(error, WorkflowException)


class TestExceptionHierarchy:
    """Tests for exception hierarchy"""

    def test_all_custom_exceptions_inherit_from_base(self):
        """Test that all custom exceptions inherit from MultiAgentOrchestratorException"""
        exception_classes = [
            TaskException,
            AgentException,
            LLMException,
            DatabaseException,
            ValidationException,
            ConfigurationException,
            WorkflowException
        ]

        for exc_class in exception_classes:
            instance = exc_class("test message")
            assert isinstance(instance, MultiAgentOrchestratorException)
            assert isinstance(instance, Exception)

    def test_specific_exceptions_inherit_from_category(self):
        """Test that specific exceptions inherit from their category"""
        test_cases = [
            (TaskNotFoundError(1), TaskException),
            (AgentNotFoundError(1), AgentException),
            (LLMAPIError("test", "error"), LLMException),
            (DatabaseConnectionError("error"), DatabaseException),
            (InvalidInputError("field", "error"), ValidationException),
            (MissingConfigurationError("key"), ConfigurationException),
            (CircularDependencyError([1, 2]), WorkflowException)
        ]

        for exception_instance, parent_class in test_cases:
            assert isinstance(exception_instance, parent_class)
            assert isinstance(exception_instance, MultiAgentOrchestratorException)
