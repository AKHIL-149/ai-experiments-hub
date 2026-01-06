"""Code Documentation Generator - AI-powered code documentation tool

A comprehensive tool for generating documentation from source code using AST
parsing and LLM-powered explanations. Supports Python, JavaScript/TypeScript,
and Java with multiple output formats.
"""

from .core import DocGenerator, LLMClient, AIExplainer, CacheManager
from .parsers.models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo
from .parsers.parser_registry import ParserRegistry
from .formatters import (
    MarkdownFormatter,
    HTMLFormatter,
    JSONFormatter,
    DocstringFormatter
)
from .utils import FileDiscovery

__version__ = '0.7.1'
__author__ = 'AI Experiments Hub'

__all__ = [
    # Core components
    'DocGenerator',
    'LLMClient',
    'AIExplainer',
    'CacheManager',

    # Data models
    'ParsedModule',
    'FunctionInfo',
    'ClassInfo',
    'ParameterInfo',

    # Parsers
    'ParserRegistry',

    # Formatters
    'MarkdownFormatter',
    'HTMLFormatter',
    'JSONFormatter',
    'DocstringFormatter',

    # Utilities
    'FileDiscovery',
]
