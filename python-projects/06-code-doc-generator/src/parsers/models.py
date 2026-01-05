"""Data models for parsed code structures"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


@dataclass
class ParameterInfo:
    """Information about a function parameter"""
    name: str
    type_hint: Optional[str] = None
    default_value: Optional[str] = None
    description: Optional[str] = None  # AI-generated


@dataclass
class FunctionInfo:
    """Information about a function or method"""
    name: str
    line_number: int
    parameters: List[ParameterInfo] = field(default_factory=list)
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    decorators: List[str] = field(default_factory=list)
    body_summary: Optional[str] = None  # First few lines or AI summary
    complexity: Optional[str] = None    # Simple/Medium/Complex
    ai_explanation: Optional[str] = None
    is_async: bool = False
    is_method: bool = False
    is_static: bool = False
    is_classmethod: bool = False


@dataclass
class ClassInfo:
    """Information about a class"""
    name: str
    line_number: int
    docstring: Optional[str] = None
    base_classes: List[str] = field(default_factory=list)
    methods: List[FunctionInfo] = field(default_factory=list)
    attributes: List[Dict[str, Any]] = field(default_factory=list)
    ai_explanation: Optional[str] = None
    decorators: List[str] = field(default_factory=list)


@dataclass
class ParsedModule:
    """Complete parsed module structure"""
    file_path: str
    language: str
    module_docstring: Optional[str] = None
    imports: List[str] = field(default_factory=list)
    functions: List[FunctionInfo] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    global_variables: List[Dict[str, Any]] = field(default_factory=list)
    parse_timestamp: Optional[str] = None
    ai_summary: Optional[str] = None  # Module-level AI summary

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'file_path': self.file_path,
            'language': self.language,
            'module_docstring': self.module_docstring,
            'imports': self.imports,
            'functions': [self._function_to_dict(f) for f in self.functions],
            'classes': [self._class_to_dict(c) for c in self.classes],
            'global_variables': self.global_variables,
            'parse_timestamp': self.parse_timestamp,
            'ai_summary': self.ai_summary
        }

    @staticmethod
    def _function_to_dict(func: FunctionInfo) -> Dict[str, Any]:
        """Convert FunctionInfo to dictionary"""
        return {
            'name': func.name,
            'line_number': func.line_number,
            'parameters': [
                {
                    'name': p.name,
                    'type_hint': p.type_hint,
                    'default_value': p.default_value,
                    'description': p.description
                }
                for p in func.parameters
            ],
            'return_type': func.return_type,
            'docstring': func.docstring,
            'decorators': func.decorators,
            'body_summary': func.body_summary,
            'complexity': func.complexity,
            'ai_explanation': func.ai_explanation,
            'is_async': func.is_async,
            'is_method': func.is_method,
            'is_static': func.is_static,
            'is_classmethod': func.is_classmethod
        }

    @staticmethod
    def _class_to_dict(cls: ClassInfo) -> Dict[str, Any]:
        """Convert ClassInfo to dictionary"""
        return {
            'name': cls.name,
            'line_number': cls.line_number,
            'docstring': cls.docstring,
            'base_classes': cls.base_classes,
            'methods': [ParsedModule._function_to_dict(m) for m in cls.methods],
            'attributes': cls.attributes,
            'ai_explanation': cls.ai_explanation,
            'decorators': cls.decorators
        }
