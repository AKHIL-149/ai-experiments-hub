"""Docstring formatter for enhancing source code with AI-generated documentation"""
from pathlib import Path
from typing import List, Optional
import re
import sys
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent))
from parsers.models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo
from formatters.base_formatter import BaseFormatter, FormatterError


class DocstringFormatter(BaseFormatter):
    """
    Enhances source code by adding or updating docstrings.

    Features:
    - Inserts AI-generated docstrings into source code
    - Follows language-specific conventions (Google-style for Python, JSDoc for JS, Javadoc for Java)
    - Preserves existing code formatting
    - Creates backup before modification
    - Never overwrites original file (outputs to new file)
    """

    def __init__(self, style: str = "auto", create_backup: bool = True):
        """
        Initialize docstring formatter.

        Args:
            style: Docstring style ('auto', 'google', 'numpy', 'jsdoc', 'javadoc')
            create_backup: Whether to create backup of original file
        """
        self.style = style
        self.create_backup = create_backup

    def supports_batch(self) -> bool:
        """Docstring formatter does not support batch processing"""
        return False

    def format(self, parsed_module: ParsedModule, output_path: str) -> str:
        """
        Generate enhanced source code with docstrings.

        Args:
            parsed_module: Parsed module with AI explanations
            output_path: Path where enhanced code should be saved

        Returns:
            Path to the generated file
        """
        # Read original source
        source_path = Path(parsed_module.file_path)
        if not source_path.exists():
            raise FormatterError(f"Source file not found: {source_path}")

        original_code = source_path.read_text(encoding='utf-8')

        # Create backup if requested
        if self.create_backup:
            backup_path = source_path.with_suffix(source_path.suffix + '.backup')
            shutil.copy2(source_path, backup_path)

        # Determine docstring style
        style = self._determine_style(parsed_module.language)

        # Enhance code based on language
        if parsed_module.language == "python":
            enhanced_code = self._enhance_python(parsed_module, original_code, style)
        elif parsed_module.language in ["javascript", "typescript"]:
            enhanced_code = self._enhance_javascript(parsed_module, original_code)
        elif parsed_module.language == "java":
            enhanced_code = self._enhance_java(parsed_module, original_code)
        else:
            raise FormatterError(f"Unsupported language: {parsed_module.language}")

        return self._safe_write(output_path, enhanced_code)

    def format_batch(self, parsed_modules: List[ParsedModule], output_path: str) -> str:
        """Docstring formatter does not support batch mode"""
        raise NotImplementedError("Docstring formatter only works with single files")

    def _determine_style(self, language: str) -> str:
        """Determine docstring style based on language"""
        if self.style != "auto":
            return self.style

        style_map = {
            "python": "google",
            "javascript": "jsdoc",
            "typescript": "jsdoc",
            "java": "javadoc"
        }
        return style_map.get(language, "google")

    def _enhance_python(self, module: ParsedModule, original_code: str, style: str) -> str:
        """Enhance Python code with docstrings"""
        lines = original_code.split('\n')

        # Process functions and classes
        # We need to insert docstrings right after function/class definition
        # Work from bottom to top to preserve line numbers

        # Collect all items to enhance with their line numbers
        items = []

        for func in module.functions:
            if func.ai_explanation:
                items.append(('function', func.line_number, func))

        for cls in module.classes:
            if cls.ai_explanation:
                items.append(('class', cls.line_number, cls))
            for method in cls.methods:
                if method.ai_explanation:
                    items.append(('method', method.line_number, method))

        # Sort by line number in reverse order (process from bottom to top)
        items.sort(key=lambda x: x[1], reverse=True)

        # Insert docstrings
        for item_type, line_num, item in items:
            if item_type == 'function' or item_type == 'method':
                docstring = self._generate_python_docstring(item, style)
            else:  # class
                docstring = self._generate_python_class_docstring(item, style)

            # Find the line after the definition (accounting for decorators)
            insert_line = self._find_python_insertion_point(lines, line_num)

            if insert_line is not None:
                # Get indentation from the definition line
                indent = self._get_indentation(lines[insert_line - 1])
                # Add one more level of indentation for the docstring
                docstring_indent = indent + "    "

                # Check if docstring already exists
                if not self._has_existing_docstring(lines, insert_line):
                    # Format docstring lines
                    docstring_lines = self._format_python_docstring_block(docstring, docstring_indent)
                    # Insert docstring
                    for i, line in enumerate(docstring_lines):
                        lines.insert(insert_line + i, line)

        return '\n'.join(lines)

    def _enhance_javascript(self, module: ParsedModule, original_code: str) -> str:
        """Enhance JavaScript/TypeScript code with JSDoc comments"""
        lines = original_code.split('\n')

        # Collect items to enhance
        items = []

        for func in module.functions:
            if func.ai_explanation:
                items.append(('function', func.line_number, func))

        for cls in module.classes:
            if cls.ai_explanation:
                items.append(('class', cls.line_number, cls))
            for method in cls.methods:
                if method.ai_explanation:
                    items.append(('method', method.line_number, method))

        # Sort by line number in reverse order
        items.sort(key=lambda x: x[1], reverse=True)

        # Insert JSDoc comments
        for item_type, line_num, item in items:
            # JSDoc goes BEFORE the definition
            insert_line = line_num - 1  # Line numbers are 1-indexed

            if 0 <= insert_line < len(lines):
                indent = self._get_indentation(lines[insert_line])

                if item_type == 'class':
                    jsdoc = self._generate_jsdoc_class(item, indent)
                else:
                    jsdoc = self._generate_jsdoc_function(item, indent)

                # Insert JSDoc comment
                jsdoc_lines = jsdoc.split('\n')
                for i, line in enumerate(jsdoc_lines):
                    lines.insert(insert_line + i, line)

        return '\n'.join(lines)

    def _enhance_java(self, module: ParsedModule, original_code: str) -> str:
        """Enhance Java code with Javadoc comments"""
        lines = original_code.split('\n')

        # Collect items to enhance
        items = []

        for func in module.functions:
            if func.ai_explanation:
                items.append(('function', func.line_number, func))

        for cls in module.classes:
            if cls.ai_explanation:
                items.append(('class', cls.line_number, cls))
            for method in cls.methods:
                if method.ai_explanation:
                    items.append(('method', method.line_number, method))

        # Sort by line number in reverse order
        items.sort(key=lambda x: x[1], reverse=True)

        # Insert Javadoc comments
        for item_type, line_num, item in items:
            # Javadoc goes BEFORE the definition
            insert_line = line_num - 1  # Line numbers are 1-indexed

            if 0 <= insert_line < len(lines):
                indent = self._get_indentation(lines[insert_line])

                if item_type == 'class':
                    javadoc = self._generate_javadoc_class(item, indent)
                else:
                    javadoc = self._generate_javadoc_function(item, indent)

                # Insert Javadoc comment
                javadoc_lines = javadoc.split('\n')
                for i, line in enumerate(javadoc_lines):
                    lines.insert(insert_line + i, line)

        return '\n'.join(lines)

    def _generate_python_docstring(self, func: FunctionInfo, style: str) -> str:
        """Generate Python docstring for function"""
        if style == "google":
            return self._generate_google_docstring(func)
        elif style == "numpy":
            return self._generate_numpy_docstring(func)
        else:
            return self._generate_google_docstring(func)  # Default

    def _generate_google_docstring(self, func: FunctionInfo) -> str:
        """Generate Google-style Python docstring"""
        parts = []

        # Summary
        parts.append(func.ai_explanation or "Function description.")

        # Parameters
        if func.parameters:
            parts.append("\nArgs:")
            for param in func.parameters:
                type_str = f" ({param.type_hint})" if param.type_hint else ""
                desc = param.description or "Parameter description"
                parts.append(f"    {param.name}{type_str}: {desc}")

        # Returns
        if func.return_type:
            parts.append(f"\nReturns:")
            parts.append(f"    {func.return_type}: Return value description")

        return "\n".join(parts)

    def _generate_numpy_docstring(self, func: FunctionInfo) -> str:
        """Generate NumPy-style Python docstring"""
        parts = []

        # Summary
        parts.append(func.ai_explanation or "Function description.")
        parts.append("")

        # Parameters
        if func.parameters:
            parts.append("Parameters")
            parts.append("----------")
            for param in func.parameters:
                type_str = f" : {param.type_hint}" if param.type_hint else ""
                parts.append(f"{param.name}{type_str}")
                desc = param.description or "Parameter description"
                parts.append(f"    {desc}")
                parts.append("")

        # Returns
        if func.return_type:
            parts.append("Returns")
            parts.append("-------")
            parts.append(func.return_type)
            parts.append("    Return value description")

        return "\n".join(parts)

    def _generate_python_class_docstring(self, cls: ClassInfo, style: str) -> str:
        """Generate Python docstring for class"""
        parts = []

        # Summary
        parts.append(cls.ai_explanation or "Class description.")

        # Attributes
        if cls.attributes:
            parts.append("\nAttributes:")
            for attr in cls.attributes[:5]:  # Limit to first 5
                attr_type = attr.get('type', '')
                type_str = f" ({attr_type})" if attr_type else ""
                parts.append(f"    {attr['name']}{type_str}: Attribute description")

        return "\n".join(parts)

    def _generate_jsdoc_function(self, func: FunctionInfo, indent: str) -> str:
        """Generate JSDoc comment for function"""
        lines = [f"{indent}/**"]
        lines.append(f"{indent} * {func.ai_explanation or 'Function description.'}")

        # Parameters
        for param in func.parameters:
            type_str = f"{{{param.type_hint}}}" if param.type_hint else "{*}"
            desc = param.description or "Parameter description"
            lines.append(f"{indent} * @param {type_str} {param.name} - {desc}")

        # Returns
        if func.return_type:
            lines.append(f"{indent} * @returns {{{func.return_type}}} Return value description")

        lines.append(f"{indent} */")
        return "\n".join(lines)

    def _generate_jsdoc_class(self, cls: ClassInfo, indent: str) -> str:
        """Generate JSDoc comment for class"""
        lines = [f"{indent}/**"]
        lines.append(f"{indent} * {cls.ai_explanation or 'Class description.'}")

        # Base classes
        if cls.base_classes:
            for base in cls.base_classes:
                lines.append(f"{indent} * @extends {base}")

        lines.append(f"{indent} */")
        return "\n".join(lines)

    def _generate_javadoc_function(self, func: FunctionInfo, indent: str) -> str:
        """Generate Javadoc comment for method"""
        lines = [f"{indent}/**"]
        lines.append(f"{indent} * {func.ai_explanation or 'Method description.'}")

        # Parameters
        for param in func.parameters:
            desc = param.description or "Parameter description"
            lines.append(f"{indent} * @param {param.name} {desc}")

        # Returns
        if func.return_type and func.return_type != "void":
            lines.append(f"{indent} * @return Return value description")

        lines.append(f"{indent} */")
        return "\n".join(lines)

    def _generate_javadoc_class(self, cls: ClassInfo, indent: str) -> str:
        """Generate Javadoc comment for class"""
        lines = [f"{indent}/**"]
        lines.append(f"{indent} * {cls.ai_explanation or 'Class description.'}")

        # Author and version tags could be added here
        lines.append(f"{indent} */")
        return "\n".join(lines)

    def _format_python_docstring_block(self, docstring: str, indent: str) -> List[str]:
        """Format Python docstring with proper quotes and indentation"""
        lines = [f'{indent}"""']

        for line in docstring.split('\n'):
            if line.strip():
                lines.append(f"{indent}{line}")
            else:
                lines.append("")

        lines.append(f'{indent}"""')
        return lines

    def _find_python_insertion_point(self, lines: List[str], def_line: int) -> Optional[int]:
        """Find where to insert Python docstring (after def line, accounting for 1-indexed line numbers)"""
        # def_line is 1-indexed, convert to 0-indexed
        idx = def_line - 1

        if idx < 0 or idx >= len(lines):
            return None

        # The docstring goes right after the def/class line
        # Skip to the line after the colon
        while idx < len(lines):
            if ':' in lines[idx]:
                return idx + 1
            idx += 1

        return None

    def _get_indentation(self, line: str) -> str:
        """Get indentation from line"""
        match = re.match(r'^(\s*)', line)
        return match.group(1) if match else ""

    def _has_existing_docstring(self, lines: List[str], start_line: int) -> bool:
        """Check if docstring already exists at this position"""
        if start_line >= len(lines):
            return False

        line = lines[start_line].strip()
        return line.startswith('"""') or line.startswith("'''") or line.startswith('/*')
