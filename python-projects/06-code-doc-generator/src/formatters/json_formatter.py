"""JSON API reference formatter"""
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from parsers.models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo
from formatters.base_formatter import BaseFormatter


class JSONFormatter(BaseFormatter):
    """
    Generates JSON API reference documentation.

    Outputs structured JSON that can be consumed by API documentation tools,
    IDE plugins, or used for programmatic analysis.
    """

    def __init__(self, pretty: bool = True, include_metadata: bool = True):
        """
        Initialize JSON formatter.

        Args:
            pretty: Whether to pretty-print JSON with indentation
            include_metadata: Whether to include generation metadata
        """
        self.pretty = pretty
        self.include_metadata = include_metadata

    def supports_batch(self) -> bool:
        """JSON formatter supports batch processing"""
        return True

    def format(self, parsed_module: ParsedModule, output_path: str) -> str:
        """Generate JSON documentation for single module"""
        data = self._module_to_dict(parsed_module)

        if self.include_metadata:
            data = {
                "metadata": self._get_metadata(),
                "module": data
            }

        json_content = self._serialize(data)
        return self._safe_write(output_path, json_content)

    def format_batch(self, parsed_modules: List[ParsedModule], output_path: str) -> str:
        """Generate combined JSON documentation for multiple modules"""
        if not parsed_modules:
            raise ValueError("No modules provided for batch formatting")

        modules_data = [self._module_to_dict(m) for m in parsed_modules]

        data = {"modules": modules_data}

        if self.include_metadata:
            data["metadata"] = self._get_metadata()
            data["metadata"]["total_modules"] = len(parsed_modules)
            data["metadata"]["total_functions"] = sum(len(m.functions) for m in parsed_modules)
            data["metadata"]["total_classes"] = sum(len(m.classes) for m in parsed_modules)

        json_content = self._serialize(data)
        return self._safe_write(output_path, json_content)

    def _serialize(self, data: Dict[str, Any]) -> str:
        """Serialize data to JSON string"""
        if self.pretty:
            return json.dumps(data, indent=2, ensure_ascii=False)
        return json.dumps(data, ensure_ascii=False)

    def _get_metadata(self) -> Dict[str, Any]:
        """Generate metadata section"""
        return {
            "generated_at": datetime.now().isoformat(),
            "generator": "code-doc-generator",
            "version": "0.6.3"
        }

    def _module_to_dict(self, module: ParsedModule) -> Dict[str, Any]:
        """Convert ParsedModule to dictionary"""
        return {
            "file_path": module.file_path,
            "file_name": Path(module.file_path).name,
            "language": module.language,
            "module_docstring": module.module_docstring,
            "ai_summary": module.ai_summary,
            "parse_timestamp": module.parse_timestamp,
            "imports": module.imports,
            "functions": [self._function_to_dict(f) for f in module.functions],
            "classes": [self._class_to_dict(c) for c in module.classes],
            "global_variables": module.global_variables,
            "statistics": {
                "function_count": len(module.functions),
                "class_count": len(module.classes),
                "import_count": len(module.imports),
                "total_methods": sum(len(c.methods) for c in module.classes)
            }
        }

    def _function_to_dict(self, func: FunctionInfo) -> Dict[str, Any]:
        """Convert FunctionInfo to dictionary"""
        # Build signature
        params_sig = ", ".join([self._param_signature(p) for p in func.parameters])
        async_marker = "async " if func.is_async else ""
        return_type = f" -> {func.return_type}" if func.return_type else ""
        signature = f"{async_marker}def {func.name}({params_sig}){return_type}"

        return {
            "name": func.name,
            "line_number": func.line_number,
            "signature": signature,
            "docstring": func.docstring,
            "ai_explanation": func.ai_explanation,
            "parameters": [self._parameter_to_dict(p) for p in func.parameters],
            "return_type": func.return_type,
            "decorators": func.decorators,
            "complexity": func.complexity,
            "is_async": func.is_async,
            "is_method": func.is_method,
            "is_static": func.is_static,
            "is_classmethod": func.is_classmethod,
            "body_summary": func.body_summary
        }

    def _class_to_dict(self, cls: ClassInfo) -> Dict[str, Any]:
        """Convert ClassInfo to dictionary"""
        return {
            "name": cls.name,
            "line_number": cls.line_number,
            "docstring": cls.docstring,
            "ai_explanation": cls.ai_explanation,
            "base_classes": cls.base_classes,
            "decorators": cls.decorators,
            "attributes": cls.attributes,
            "methods": [self._function_to_dict(m) for m in cls.methods],
            "statistics": {
                "method_count": len(cls.methods),
                "attribute_count": len(cls.attributes),
                "has_constructor": any(m.name in ['__init__', 'constructor'] for m in cls.methods)
            }
        }

    def _parameter_to_dict(self, param: ParameterInfo) -> Dict[str, Any]:
        """Convert ParameterInfo to dictionary"""
        return {
            "name": param.name,
            "type_hint": param.type_hint,
            "default_value": param.default_value,
            "description": param.description
        }

    def _param_signature(self, param: ParameterInfo) -> str:
        """Generate parameter signature string"""
        parts = [param.name]
        if param.type_hint:
            parts.append(f": {param.type_hint}")
        if param.default_value:
            parts.append(f" = {param.default_value}")
        return "".join(parts)
