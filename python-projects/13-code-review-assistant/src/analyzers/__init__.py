"""
Code analyzers for detecting issues in source code.
"""
from .base_analyzer import BaseAnalyzer, CodeIssue, IssueCategory, IssueSeverity
from .security_analyzer import SecurityAnalyzer
from .smell_analyzer import SmellAnalyzer
from .complexity_analyzer import ComplexityAnalyzer
from .javascript_security_analyzer import JavaScriptSecurityAnalyzer
from .javascript_smell_analyzer import JavaScriptSmellAnalyzer
from .analyzer_registry import AnalyzerRegistry, get_registry

__all__ = [
    'BaseAnalyzer',
    'CodeIssue',
    'IssueCategory',
    'IssueSeverity',
    'SecurityAnalyzer',
    'SmellAnalyzer',
    'ComplexityAnalyzer',
    'JavaScriptSecurityAnalyzer',
    'JavaScriptSmellAnalyzer',
    'AnalyzerRegistry',
    'get_registry'
]
