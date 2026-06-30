"""
Custom exceptions for the multi-agent orchestrator
"""


class MultiAgentOrchestratorException(Exception):
    """Base exception for all custom exceptions"""
    pass


class TaskException(MultiAgentOrchestratorException):
    """Base exception for task-related errors"""
    pass


class TaskNotFoundError(TaskException):
    """Raised when a task is not found"""
    def __init__(self, task_id: int):
        self.task_id = task_id
        super().__init__(f"Task {task_id} not found")


class TaskAlreadyExistsError(TaskException):
    """Raised when attempting to create a duplicate task"""
    def __init__(self, task_id: int):
        self.task_id = task_id
        super().__init__(f"Task {task_id} already exists")


class TaskDependencyError(TaskException):
    """Raised when task dependencies are invalid"""
    def __init__(self, message: str):
        super().__init__(f"Task dependency error: {message}")


class TaskExecutionError(TaskException):
    """Raised when task execution fails"""
    def __init__(self, task_id: int, error: str):
        self.task_id = task_id
        self.error = error
        super().__init__(f"Task {task_id} execution failed: {error}")


class AgentException(MultiAgentOrchestratorException):
    """Base exception for agent-related errors"""
    pass


class AgentNotFoundError(AgentException):
    """Raised when an agent is not found"""
    def __init__(self, agent_id: int):
        self.agent_id = agent_id
        super().__init__(f"Agent {agent_id} not found")


class AgentNotAvailableError(AgentException):
    """Raised when an agent is not available for task assignment"""
    def __init__(self, agent_id: int, reason: str = None):
        self.agent_id = agent_id
        message = f"Agent {agent_id} is not available"
        if reason:
            message += f": {reason}"
        super().__init__(message)


class AgentCapabilityError(AgentException):
    """Raised when an agent lacks required capabilities"""
    def __init__(self, agent_id: int, required_capability: str):
        self.agent_id = agent_id
        self.required_capability = required_capability
        super().__init__(f"Agent {agent_id} lacks required capability: {required_capability}")


class LLMException(MultiAgentOrchestratorException):
    """Base exception for LLM-related errors"""
    pass


class LLMAPIError(LLMException):
    """Raised when LLM API call fails"""
    def __init__(self, provider: str, error: str):
        self.provider = provider
        self.error = error
        super().__init__(f"LLM API error ({provider}): {error}")


class LLMRateLimitError(LLMException):
    """Raised when LLM API rate limit is exceeded"""
    def __init__(self, provider: str, retry_after: int = None):
        self.provider = provider
        self.retry_after = retry_after
        message = f"LLM rate limit exceeded ({provider})"
        if retry_after:
            message += f". Retry after {retry_after} seconds"
        super().__init__(message)


class LLMTokenLimitError(LLMException):
    """Raised when LLM token limit is exceeded"""
    def __init__(self, provider: str, tokens_used: int, token_limit: int):
        self.provider = provider
        self.tokens_used = tokens_used
        self.token_limit = token_limit
        super().__init__(
            f"LLM token limit exceeded ({provider}): "
            f"used {tokens_used} tokens, limit {token_limit}"
        )


class DatabaseException(MultiAgentOrchestratorException):
    """Base exception for database-related errors"""
    pass


class DatabaseConnectionError(DatabaseException):
    """Raised when database connection fails"""
    def __init__(self, error: str):
        super().__init__(f"Database connection error: {error}")


class DatabaseIntegrityError(DatabaseException):
    """Raised when database integrity constraint is violated"""
    def __init__(self, error: str):
        super().__init__(f"Database integrity error: {error}")


class ValidationException(MultiAgentOrchestratorException):
    """Base exception for validation errors"""
    pass


class InvalidInputError(ValidationException):
    """Raised when input validation fails"""
    def __init__(self, field: str, error: str):
        self.field = field
        super().__init__(f"Invalid input for '{field}': {error}")


class ConfigurationException(MultiAgentOrchestratorException):
    """Base exception for configuration errors"""
    pass


class MissingConfigurationError(ConfigurationException):
    """Raised when required configuration is missing"""
    def __init__(self, config_key: str):
        self.config_key = config_key
        super().__init__(f"Missing required configuration: {config_key}")


class InvalidConfigurationError(ConfigurationException):
    """Raised when configuration is invalid"""
    def __init__(self, config_key: str, error: str):
        self.config_key = config_key
        super().__init__(f"Invalid configuration for '{config_key}': {error}")


class WorkflowException(MultiAgentOrchestratorException):
    """Base exception for workflow-related errors"""
    pass


class CircularDependencyError(WorkflowException):
    """Raised when circular dependency is detected in task graph"""
    def __init__(self, task_ids: list):
        self.task_ids = task_ids
        super().__init__(f"Circular dependency detected: {' -> '.join(map(str, task_ids))}")


class WorkflowExecutionError(WorkflowException):
    """Raised when workflow execution fails"""
    def __init__(self, workflow_id: str, error: str):
        self.workflow_id = workflow_id
        super().__init__(f"Workflow {workflow_id} execution failed: {error}")
