"""Markdown documentation formatter"""
from pathlib import Path
from typing import List
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from parsers.models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo
from formatters.base_formatter import BaseFormatter


class MarkdownFormatter(BaseFormatter):
    """
    Generates Markdown documentation from parsed code.

    Supports both single-file and multi-file batch processing.
    Includes AI-generated explanations when available.
    """

    def __init__(self, include_toc: bool = True, include_source_links: bool = True):
        """
        Initialize Markdown formatter.

        Args:
            include_toc: Whether to include table of contents
            include_source_links: Whether to include links to source files
        """
        self.include_toc = include_toc
        self.include_source_links = include_source_links

    def supports_batch(self) -> bool:
        """Markdown formatter supports batch processing"""
        return True

    def format(self, parsed_module: ParsedModule, output_path: str) -> str:
        """Generate Markdown documentation for single module"""
        content = self._generate_module_doc(parsed_module)
        return self._safe_write(output_path, content)

    def format_batch(self, parsed_modules: List[ParsedModule], output_path: str) -> str:
        """Generate combined Markdown documentation for multiple modules"""
        if not parsed_modules:
            raise ValueError("No modules provided for batch formatting")

        sections = []

        # Header
        sections.append("# Project Documentation\n")
        sections.append(f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n")

        # Table of contents (if enabled)
        if self.include_toc:
            sections.append(self._generate_batch_toc(parsed_modules))

        # Individual module docs
        for module in parsed_modules:
            sections.append("---\n")
            sections.append(self._generate_module_doc(module, level=2))

        content = "\n".join(sections)
        return self._safe_write(output_path, content)

    def _generate_module_doc(self, module: ParsedModule, level: int = 1) -> str:
        """Generate documentation for a single module"""
        sections = []
        heading = "#" * level

        # Module header
        module_name = Path(module.file_path).name
        sections.append(f"{heading} Module: `{module_name}`\n")

        if self.include_source_links:
            sections.append(f"**Source**: `{module.file_path}`\n")

        sections.append(f"**Language**: {module.language}\n")

        # Module docstring or AI summary
        if module.ai_summary:
            sections.append(f"\n{module.ai_summary}\n")
        elif module.module_docstring:
            sections.append(f"\n{module.module_docstring}\n")

        # Statistics
        func_count = len(module.functions)
        class_count = len(module.classes)
        sections.append(f"\n**Contents**: {func_count} function(s), {class_count} class(es)\n")

        # Table of contents for this module
        if self.include_toc and (module.functions or module.classes):
            sections.append(self._generate_module_toc(module, level + 1))

        # Imports section
        if module.imports:
            sections.append(f"\n{heading}# Imports\n")
            sections.append("```")
            for imp in module.imports[:10]:  # Limit to first 10
                sections.append(imp)
            if len(module.imports) > 10:
                sections.append(f"... and {len(module.imports) - 10} more")
            sections.append("```\n")

        # Functions section
        if module.functions:
            sections.append(f"\n{heading}# Functions\n")
            for func in module.functions:
                sections.append(self._format_function(func, level + 2))

        # Classes section
        if module.classes:
            sections.append(f"\n{heading}# Classes\n")
            for cls in module.classes:
                sections.append(self._format_class(cls, level + 2))

        return "\n".join(sections)

    def _generate_batch_toc(self, modules: List[ParsedModule]) -> str:
        """Generate table of contents for batch documentation"""
        lines = ["\n## Table of Contents\n"]

        for module in modules:
            module_name = Path(module.file_path).name
            # Create anchor link (lowercase, replace spaces/dots with hyphens)
            anchor = module_name.lower().replace('.', '').replace(' ', '-')
            lines.append(f"- [{module_name}](#{anchor})")

        lines.append("")
        return "\n".join(lines)

    def _generate_module_toc(self, module: ParsedModule, level: int) -> str:
        """Generate table of contents for single module"""
        lines = [f"\n{'#' * level} Contents\n"]

        if module.functions:
            lines.append("**Functions:**")
            for func in module.functions:
                lines.append(f"- [`{func.name}()`](#{func.name.lower()})")

        if module.classes:
            lines.append("\n**Classes:**")
            for cls in module.classes:
                lines.append(f"- [`{cls.name}`](#{cls.name.lower()})")

        lines.append("")
        return "\n".join(lines)

    def _format_function(self, func: FunctionInfo, level: int) -> str:
        """Format function documentation"""
        sections = []
        heading = "#" * level

        # Function signature
        params = ", ".join([self._format_param_signature(p) for p in func.parameters])
        return_type = f" -> {func.return_type}" if func.return_type else ""
        async_marker = "async " if func.is_async else ""

        sections.append(f"{heading} `{async_marker}{func.name}({params}){return_type}`\n")
        sections.append(f"**Line**: {func.line_number}\n")

        # Decorators
        if func.decorators:
            decorators_str = ", ".join([f"`{d}`" for d in func.decorators])
            sections.append(f"**Decorators**: {decorators_str}\n")

        # AI explanation or docstring
        if func.ai_explanation:
            sections.append(f"\n{func.ai_explanation}\n")
        elif func.docstring:
            sections.append(f"\n{func.docstring}\n")

        # Parameters section
        if func.parameters:
            sections.append(f"\n**Parameters**:\n")
            for param in func.parameters:
                sections.append(self._format_parameter(param))

        # Return type
        if func.return_type:
            sections.append(f"\n**Returns**: `{func.return_type}`\n")

        # Complexity indicator
        if func.complexity:
            sections.append(f"**Complexity**: {func.complexity}\n")

        sections.append("")
        return "\n".join(sections)

    def _format_class(self, cls: ClassInfo, level: int) -> str:
        """Format class documentation"""
        sections = []
        heading = "#" * level

        # Class header
        inheritance = ""
        if cls.base_classes:
            inheritance = f" (extends {', '.join([f'`{b}`' for b in cls.base_classes])})"

        sections.append(f"{heading} `{cls.name}`{inheritance}\n")
        sections.append(f"**Line**: {cls.line_number}\n")

        # Decorators (for Java interfaces/enums)
        if cls.decorators:
            decorators_str = ", ".join([f"`{d}`" for d in cls.decorators])
            sections.append(f"**Type**: {decorators_str}\n")

        # AI explanation or docstring
        if cls.ai_explanation:
            sections.append(f"\n{cls.ai_explanation}\n")
        elif cls.docstring:
            sections.append(f"\n{cls.docstring}\n")

        # Attributes
        if cls.attributes:
            sections.append(f"\n**Attributes**:\n")
            for attr in cls.attributes[:10]:  # Limit to first 10
                attr_type = attr.get('type', '')
                type_str = f": `{attr_type}`" if attr_type else ""
                sections.append(f"- `{attr['name']}`{type_str}")
            if len(cls.attributes) > 10:
                sections.append(f"- *... and {len(cls.attributes) - 10} more*")
            sections.append("")

        # Methods
        if cls.methods:
            sections.append(f"\n**Methods**:\n")
            for method in cls.methods:
                sections.append(self._format_method_brief(method, level + 1))

        sections.append("")
        return "\n".join(sections)

    def _format_method_brief(self, method: FunctionInfo, level: int) -> str:
        """Format brief method documentation"""
        heading = "#" * level
        params = ", ".join([p.name for p in method.parameters])
        return_type = f" -> {method.return_type}" if method.return_type else ""

        lines = [f"{heading} `{method.name}({params}){return_type}`\n"]

        if method.ai_explanation:
            lines.append(f"{method.ai_explanation}\n")
        elif method.docstring:
            # Show first line only
            first_line = method.docstring.split('\n')[0]
            lines.append(f"{first_line}\n")

        return "\n".join(lines)

    def _format_parameter(self, param: ParameterInfo) -> str:
        """Format single parameter"""
        type_str = f": `{param.type_hint}`" if param.type_hint else ""
        default_str = f" = `{param.default_value}`" if param.default_value else ""
        desc_str = f" - {param.description}" if param.description else ""

        return f"- **`{param.name}`**{type_str}{default_str}{desc_str}"

    def _format_param_signature(self, param: ParameterInfo) -> str:
        """Format parameter for function signature"""
        parts = [param.name]
        if param.type_hint:
            parts.append(f": {param.type_hint}")
        if param.default_value:
            parts.append(f" = {param.default_value}")
        return "".join(parts)
