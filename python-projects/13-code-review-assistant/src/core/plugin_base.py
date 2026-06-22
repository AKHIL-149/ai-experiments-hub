"""
Plugin Base Classes and Interfaces
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Callable
from enum import Enum
import inspect


class PluginType(Enum):
    """Plugin types"""
    ANALYZER = "analyzer"
    FORMATTER = "formatter"
    REPORTER = "reporter"
    INTEGRATION = "integration"
    CUSTOM = "custom"


class PluginStatus(Enum):
    """Plugin status"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    DISABLED = "disabled"


class PluginHook(Enum):
    """Available plugin hooks"""
    # Analysis hooks
    BEFORE_ANALYSIS = "before_analysis"
    AFTER_ANALYSIS = "after_analysis"
    ON_ISSUE_FOUND = "on_issue_found"

    # File processing hooks
    BEFORE_FILE_PARSE = "before_file_parse"
    AFTER_FILE_PARSE = "after_file_parse"

    # Review hooks
    BEFORE_REVIEW_GENERATE = "before_review_generate"
    AFTER_REVIEW_GENERATE = "after_review_generate"

    # PR hooks
    ON_PR_OPENED = "on_pr_opened"
    ON_PR_UPDATED = "on_pr_updated"
    ON_PR_CLOSED = "on_pr_closed"

    # Custom hooks
    CUSTOM = "custom"


class PluginMetadata:
    """Plugin metadata"""

    def __init__(
        self,
        name: str,
        version: str,
        author: str,
        description: str,
        plugin_type: PluginType,
        supported_languages: Optional[List[str]] = None,
        dependencies: Optional[List[str]] = None,
        homepage: Optional[str] = None,
        license: Optional[str] = None
    ):
        self.name = name
        self.version = version
        self.author = author
        self.description = description
        self.plugin_type = plugin_type
        self.supported_languages = supported_languages or []
        self.dependencies = dependencies or []
        self.homepage = homepage
        self.license = license

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'name': self.name,
            'version': self.version,
            'author': self.author,
            'description': self.description,
            'type': self.plugin_type.value,
            'supported_languages': self.supported_languages,
            'dependencies': self.dependencies,
            'homepage': self.homepage,
            'license': self.license
        }


class BasePlugin(ABC):
    """Base class for all plugins"""

    def __init__(self, metadata: PluginMetadata):
        self.metadata = metadata
        self.status = PluginStatus.INACTIVE
        self.hooks: Dict[PluginHook, List[Callable]] = {}
        self._enabled = False

    @abstractmethod
    def initialize(self) -> bool:
        """
        Initialize the plugin.

        Returns:
            True if initialization successful, False otherwise
        """
        pass

    @abstractmethod
    def shutdown(self) -> bool:
        """
        Shutdown the plugin.

        Returns:
            True if shutdown successful, False otherwise
        """
        pass

    def register_hook(self, hook: PluginHook, callback: Callable):
        """
        Register a hook callback.

        Args:
            hook: Hook to register for
            callback: Callback function
        """
        if hook not in self.hooks:
            self.hooks[hook] = []
        self.hooks[hook].append(callback)

    def get_hooks(self, hook: PluginHook) -> List[Callable]:
        """
        Get callbacks for a hook.

        Args:
            hook: Hook to get callbacks for

        Returns:
            List of callback functions
        """
        return self.hooks.get(hook, [])

    def is_enabled(self) -> bool:
        """Check if plugin is enabled"""
        return self._enabled and self.status == PluginStatus.ACTIVE

    def enable(self):
        """Enable the plugin"""
        self._enabled = True
        if self.status == PluginStatus.INACTIVE:
            if self.initialize():
                self.status = PluginStatus.ACTIVE
            else:
                self.status = PluginStatus.ERROR

    def disable(self):
        """Disable the plugin"""
        self._enabled = False
        self.shutdown()
        self.status = PluginStatus.DISABLED

    def get_info(self) -> Dict[str, Any]:
        """Get plugin information"""
        return {
            'metadata': self.metadata.to_dict(),
            'status': self.status.value,
            'enabled': self._enabled,
            'hooks': [hook.value for hook in self.hooks.keys()]
        }


class AnalyzerPlugin(BasePlugin):
    """Base class for analyzer plugins"""

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        if metadata.plugin_type != PluginType.ANALYZER:
            raise ValueError("AnalyzerPlugin must have type ANALYZER")

    @abstractmethod
    def analyze(self, code: str, language: str, file_path: str) -> List[Dict[str, Any]]:
        """
        Analyze code and return issues.

        Args:
            code: Code to analyze
            language: Programming language
            file_path: File path

        Returns:
            List of issues found
        """
        pass

    def get_rules(self) -> List[Dict[str, Any]]:
        """
        Get analysis rules provided by this plugin.

        Returns:
            List of rule definitions
        """
        return []


class FormatterPlugin(BasePlugin):
    """Base class for formatter plugins"""

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        if metadata.plugin_type != PluginType.FORMATTER:
            raise ValueError("FormatterPlugin must have type FORMATTER")

    @abstractmethod
    def format_code(self, code: str, language: str, options: Optional[Dict[str, Any]] = None) -> str:
        """
        Format code according to plugin's rules.

        Args:
            code: Code to format
            language: Programming language
            options: Formatting options

        Returns:
            Formatted code
        """
        pass


class ReporterPlugin(BasePlugin):
    """Base class for reporter plugins"""

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        if metadata.plugin_type != PluginType.REPORTER:
            raise ValueError("ReporterPlugin must have type REPORTER")

    @abstractmethod
    def generate_report(
        self,
        issues: List[Dict[str, Any]],
        format: str = "html"
    ) -> str:
        """
        Generate a report from analysis results.

        Args:
            issues: List of issues
            format: Report format (html, markdown, json, etc.)

        Returns:
            Generated report content
        """
        pass


class IntegrationPlugin(BasePlugin):
    """Base class for integration plugins"""

    def __init__(self, metadata: PluginMetadata):
        super().__init__(metadata)
        if metadata.plugin_type != PluginType.INTEGRATION:
            raise ValueError("IntegrationPlugin must have type INTEGRATION")

    @abstractmethod
    def connect(self, config: Dict[str, Any]) -> bool:
        """
        Connect to external service.

        Args:
            config: Connection configuration

        Returns:
            True if connection successful
        """
        pass

    @abstractmethod
    def send_notification(self, event: str, data: Dict[str, Any]) -> bool:
        """
        Send notification to integrated service.

        Args:
            event: Event type
            data: Event data

        Returns:
            True if notification sent successfully
        """
        pass


class PluginContext:
    """Context object passed to plugin callbacks"""

    def __init__(
        self,
        user_id: Optional[str] = None,
        repository_id: Optional[str] = None,
        pr_id: Optional[str] = None,
        file_path: Optional[str] = None,
        language: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.user_id = user_id
        self.repository_id = repository_id
        self.pr_id = pr_id
        self.file_path = file_path
        self.language = language
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'user_id': self.user_id,
            'repository_id': self.repository_id,
            'pr_id': self.pr_id,
            'file_path': self.file_path,
            'language': self.language,
            'metadata': self.metadata
        }


class PluginException(Exception):
    """Base exception for plugin errors"""
    pass


class PluginLoadError(PluginException):
    """Plugin loading error"""
    pass


class PluginExecutionError(PluginException):
    """Plugin execution error"""
    pass


class PluginValidationError(PluginException):
    """Plugin validation error"""
    pass
