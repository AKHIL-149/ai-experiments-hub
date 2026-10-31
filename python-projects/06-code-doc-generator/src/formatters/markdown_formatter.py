"""Markdown documentation formatter"""
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from ..parsers.models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo
from .base_formatter import BaseFormatter


class Slugger:
    """Heading anchors the way GitHub makes them, including the -1, -2 suffix for repeated headings.

    Anchors have to be handed out in the order the headings appear in the document.
    """

    def __init__(self):
        self.used: Dict[str, int] = {}

    def slug(self, text: str) -> str:
        base = re.sub(r'[^\w\- ]', '', text.lower().strip()).replace(' ', '-')
        count = self.used.get(base, 0)
        self.used[base] = count + 1
        return base if count == 0 else f"{base}-{count}"


class MarkdownFormatter(BaseFormatter):
    """
    Generates Markdown documentation from parsed code.

    Supports both single-file and multi-file batch processing.
    Includes AI-generated explanations when available.
    Table-of-contents links point at the real heading anchors.
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
        content, _ = self._generate_module_doc(parsed_module, Slugger())
        return self._safe_write(output_path, content)

    def format_batch(self, parsed_modules: List[ParsedModule], output_path: str) -> str:
        """Generate combined Markdown documentation for multiple modules"""
        if not parsed_modules:
            raise ValueError("No modules provided for batch formatting")

        slugger = Slugger()
        slugger.slug("Project Documentation")
        sections = [
            "# Project Documentation\n",
            f"*Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n",
        ]

        # The contents list sits above the modules but needs their anchors, so it is filled in last
        toc_index = None
        if self.include_toc:
            slugger.slug("Table of Contents")
            toc_index = len(sections)
            sections.append("")

        entries: List[Tuple[str, str]] = []
        for module in parsed_modules:
            text, anchor = self._generate_module_doc(module, slugger, level=2)
            entries.append((Path(module.file_path).name, anchor))
            sections.append("---\n")
            sections.append(text)

        if toc_index is not None:
            sections[toc_index] = self._generate_batch_toc(entries)

        return self._safe_write(output_path, "\n".join(sections))

    # ------------------------------------------------------------------ pieces

    def _generate_module_doc(self, module: ParsedModule, slugger: Slugger, level: int = 1) -> Tuple[str, str]:
        """Documentation for one module, and the anchor of its heading"""
        sections = []
        heading = "#" * level

        module_name = Path(module.file_path).name
        sections.append(f"{heading} Module: `{module_name}`\n")
        module_anchor = slugger.slug(f"Module: {module_name}")

        if self.include_source_links:
            sections.append(f"**Source**: `{module.file_path}`\n")

        sections.append(f"**Language**: {module.language}\n")

        if module.ai_summary:
            sections.append(f"\n{module.ai_summary}\n")
        elif module.module_docstring:
            sections.append(f"\n{module.module_docstring}\n")

        sections.append(f"\n**Contents**: {len(module.functions)} function(s), {len(module.classes)} class(es)\n")

        toc_index = None
        if self.include_toc and (module.functions or module.classes):
            slugger.slug("Contents")
            toc_index = len(sections)
            sections.append("")

        if module.imports:
            slugger.slug("Imports")
            sections.append(f"\n{heading}# Imports\n")
            sections.append("```")
            for imp in module.imports[:10]:
                sections.append(imp)
            if len(module.imports) > 10:
                sections.append(f"... and {len(module.imports) - 10} more")
            sections.append("```\n")

        function_anchors = []
        if module.functions:
            slugger.slug("Functions")
            sections.append(f"\n{heading}# Functions\n")
            for func in module.functions:
                function_anchors.append(slugger.slug(func.name))
                sections.append(self._format_function(func, level + 2))

        class_anchors = []
        if module.classes:
            slugger.slug("Classes")
            sections.append(f"\n{heading}# Classes\n")
            for cls in module.classes:
                class_anchors.append(slugger.slug(cls.name))
                sections.append(self._format_class(cls, level + 2, slugger))

        if toc_index is not None:
            sections[toc_index] = self._generate_module_toc(
                module, level + 1, function_anchors, class_anchors
            )

        return "\n".join(sections), module_anchor

    def _generate_batch_toc(self, entries: List[Tuple[str, str]]) -> str:
        """Table of contents for batch documentation: (file name, anchor) per module"""
        lines = ["\n## Table of Contents\n"]
        for name, anchor in entries:
            lines.append(f"- [{name}](#{anchor})")
        lines.append("")
        return "\n".join(lines)

    def _generate_module_toc(self, module: ParsedModule, level: int,
                             function_anchors: List[str], class_anchors: List[str]) -> str:
        """Table of contents for a single module"""
        lines = [f"\n{'#' * level} Contents\n"]

        if module.functions:
            lines.append("**Functions:**")
            for func, anchor in zip(module.functions, function_anchors):
                lines.append(f"- [`{func.name}()`](#{anchor})")

        if module.classes:
            lines.append("\n**Classes:**")
            for cls, anchor in zip(module.classes, class_anchors):
                lines.append(f"- [`{cls.name}`](#{anchor})")

        lines.append("")
        return "\n".join(lines)

    def _signature(self, func: FunctionInfo) -> str:
        params = ", ".join(self._format_param_signature(p) for p in func.parameters)
        return_type = f" -> {func.return_type}" if func.return_type else ""
        async_marker = "async " if func.is_async else ""
        return f"{async_marker}{func.name}({params}){return_type}"

    def _format_function(self, func: FunctionInfo, level: int) -> str:
        """Format function documentation.

        The heading is just the name (so its anchor is predictable); the full signature follows in
        a code block.
        """
        sections = []
        heading = "#" * level

        sections.append(f"{heading} `{func.name}`\n")
        sections.append(f"```\n{self._signature(func)}\n```\n")
        sections.append(f"**Line**: {func.line_number}\n")

        if func.decorators:
            decorators_str = ", ".join([f"`{d}`" for d in func.decorators])
            sections.append(f"**Decorators**: {decorators_str}\n")

        if func.ai_explanation:
            sections.append(f"\n{func.ai_explanation}\n")
        elif func.docstring:
            sections.append(f"\n{func.docstring}\n")

        if func.parameters:
            sections.append("\n**Parameters**:\n")
            for param in func.parameters:
                sections.append(self._format_parameter(param))

        if func.return_type:
            sections.append(f"\n**Returns**: `{func.return_type}`\n")

        if func.complexity:
            sections.append(f"\n**Complexity**: {func.complexity}\n")

        sections.append("")
        return "\n".join(sections)

    def _format_class(self, cls: ClassInfo, level: int, slugger: Slugger) -> str:
        """Format class documentation"""
        sections = []
        heading = "#" * level

        sections.append(f"{heading} `{cls.name}`\n")
        if cls.base_classes:
            sections.append(f"**Extends**: {', '.join(f'`{b}`' for b in cls.base_classes)}\n")
        sections.append(f"**Line**: {cls.line_number}\n")

        if cls.decorators:
            decorators_str = ", ".join([f"`{d}`" for d in cls.decorators])
            sections.append(f"**Type**: {decorators_str}\n")

        if cls.ai_explanation:
            sections.append(f"\n{cls.ai_explanation}\n")
        elif cls.docstring:
            sections.append(f"\n{cls.docstring}\n")

        if cls.attributes:
            sections.append("\n**Attributes**:\n")
            for attr in cls.attributes[:10]:
                sections.append(self._format_attribute(attr))
            if len(cls.attributes) > 10:
                sections.append(f"- *... and {len(cls.attributes) - 10} more*")
            sections.append("")

        if cls.methods:
            sections.append("\n**Methods**:\n")
            for method in cls.methods:
                sections.append(self._format_method_brief(method, level + 1, slugger))

        sections.append("")
        return "\n".join(sections)

    @staticmethod
    def _format_attribute(attr: dict) -> str:
        type_str = f": `{attr['type']}`" if attr.get('type') else ""
        default_str = f" = `{attr['default_value']}`" if attr.get('default_value') else ""
        scope = attr.get('scope')
        scope_str = f" *({scope} attribute)*" if scope else ""
        return f"- `{attr['name']}`{type_str}{default_str}{scope_str}"

    def _format_method_brief(self, method: FunctionInfo, level: int, slugger: Slugger) -> str:
        """Format brief method documentation"""
        heading = "#" * level
        slugger.slug(method.name)

        lines = [f"{heading} `{method.name}`\n", f"```\n{self._signature(method)}\n```\n"]

        if method.ai_explanation:
            lines.append(f"{method.ai_explanation}\n")
        elif method.docstring:
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
