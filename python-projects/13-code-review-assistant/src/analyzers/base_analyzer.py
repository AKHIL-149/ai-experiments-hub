"""Base analyzer interface for code analysis"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from enum import Enum


class IssueSeverity(str, Enum):
    """Severity levels for detected issues"""
    INFO = 'info'
    WARNING = 'warning'
    ERROR = 'error'
    CRITICAL = 'critical'


class IssueCategory(str, Enum):
    """Categories of code issues"""
    SECURITY = 'security'
    SMELL = 'smell'
    COMPLEXITY = 'complexity'
    STYLE = 'style'
    PATTERN = 'pattern'


@dataclass
class CodeIssue:
    """
    Represents a detected code issue.

    This is the core data structure for all analyzer findings.
    """
    rule_id: str
    category: IssueCategory
    severity: IssueSeverity
    title: str
    description: str
    file_path: str
    line_number: Optional[int] = None
    column_number: Optional[int] = None
    code_snippet: Optional[str] = None
    suggestion: Optional[str] = None
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert issue to dictionary for serialization"""
        return {
            'rule_id': self.rule_id,
            'category': self.category.value,
            'severity': self.severity.value,
            'title': self.title,
            'description': self.description,
            'file_path': self.file_path,
            'line_number': self.line_number,
            'column_number': self.column_number,
            'code_snippet': self.code_snippet,
            'suggestion': self.suggestion,
            'confidence': self.confidence,
            'metadata': self.metadata
        }


class BaseAnalyzer(ABC):
    """
    Abstract base class for all code analyzers.

    Each analyzer implements specific detection logic for a category of issues.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize analyzer with optional configuration.

        Args:
            config: Configuration dictionary for analyzer settings
        """
        self.config = config or {}
        self.enabled = self.config.get('enabled', True)

    @property
    @abstractmethod
    def analyzer_id(self) -> str:
        """
        Unique identifier for this analyzer.

        Returns:
            String identifier (e.g., 'security', 'smell', 'complexity')
        """
        pass

    @property
    @abstractmethod
    def category(self) -> IssueCategory:
        """
        Category of issues this analyzer detects.

        Returns:
            IssueCategory enum value
        """
        pass

    @abstractmethod
    def analyze(self, parsed_module, source_code: str) -> List[CodeIssue]:
        """
        Analyze parsed code and detect issues.

        Args:
            parsed_module: ParsedModule from parser
            source_code: Original source code string

        Returns:
            List of detected CodeIssue objects
        """
        pass

    def is_enabled(self) -> bool:
        """Check if analyzer is enabled"""
        return self.enabled

    def get_rule_ids(self) -> List[str]:
        """
        Get list of rule IDs this analyzer can detect.

        Returns:
            List of rule ID strings
        """
        return []

    def create_issue(
        self,
        rule_id: str,
        severity: IssueSeverity,
        title: str,
        description: str,
        file_path: str,
        line_number: Optional[int] = None,
        code_snippet: Optional[str] = None,
        suggestion: Optional[str] = None,
        confidence: float = 1.0,
        **metadata
    ) -> CodeIssue:
        """
        Helper method to create a CodeIssue.

        Args:
            rule_id: Rule identifier
            severity: Issue severity
            title: Short title
            description: Detailed description
            file_path: Path to file
            line_number: Line where issue occurs
            code_snippet: Relevant code snippet
            suggestion: Suggested fix
            confidence: Confidence score (0.0 to 1.0)
            **metadata: Additional metadata

        Returns:
            CodeIssue instance
        """
        return CodeIssue(
            rule_id=rule_id,
            category=self.category,
            severity=severity,
            title=title,
            description=description,
            file_path=file_path,
            line_number=line_number,
            code_snippet=code_snippet,
            suggestion=suggestion,
            confidence=confidence,
            metadata=metadata
        )

    def extract_code_snippet(
        self,
        source_code: str,
        line_number: int,
        context_lines: int = 2
    ) -> str:
        """
        Extract code snippet around a specific line.

        Args:
            source_code: Full source code
            line_number: Target line number (1-indexed)
            context_lines: Number of lines before/after to include

        Returns:
            Code snippet as string
        """
        lines = source_code.split('\n')
        start = max(0, line_number - context_lines - 1)
        end = min(len(lines), line_number + context_lines)

        snippet_lines = []
        for i in range(start, end):
            line_num = i + 1
            marker = '>>> ' if line_num == line_number else '    '
            snippet_lines.append(f"{marker}{line_num:4d} | {lines[i]}")

        return '\n'.join(snippet_lines)
