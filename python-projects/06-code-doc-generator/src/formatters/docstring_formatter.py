"""Docstring formatter for enhancing source code with AI-generated documentation"""
import ast
from pathlib import Path
from typing import List, Optional
import re
import shutil

from ..parsers.base_parser import read_source_text
from ..parsers.models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo
from .base_formatter import BaseFormatter, FormatterError


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

        original_code = read_source_text(str(source_path))

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
        """Add docstrings to the functions, methods and classes that have none.

        The place for each docstring comes from the syntax tree (right before the first statement of
        the body), so multi-line signatures, annotations with colons and decorated nested
        definitions are handled; a definition whose body is on the same line as its header
        ("def f(x): return x") is left alone, because a docstring cannot be put there safely.
        """
        try:
            tree = ast.parse(original_code)
        except SyntaxError as error:
            raise FormatterError(f"Cannot add docstrings to a file that does not parse: {error.msg} (line {error.lineno})")

        definitions = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                definitions.setdefault(node.lineno, node)

        eol = '\r' if '\r\n' in original_code else ''
        lines = original_code.split('\n')

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

        # Bottom to top, so that inserting lines does not move the ones still to be handled
        items.sort(key=lambda x: x[1], reverse=True)

        for item_type, line_num, item in items:
            node = definitions.get(line_num)
            if node is None or ast.get_docstring(node, clean=False) is not None:
                continue
            first = node.body[0]
            first_line = min([first.lineno] + [d.lineno for d in getattr(first, 'decorator_list', [])])
            text = lines[first_line - 1]
            if text[:first.col_offset].strip():
                continue                                 # body shares the header's line
            indent = text[:len(text) - len(text.lstrip())]

            if item_type == 'class':
                docstring = self._generate_python_class_docstring(item, style)
            else:
                docstring = self._generate_python_docstring(item, style)
            block = self._format_python_docstring_block(docstring, indent)
            for i, line in enumerate(block):
                lines.insert(first_line - 1 + i, line + eol)

        return '\n'.join(lines)

    def _enhance_javascript(self, module: ParsedModule, original_code: str) -> str:
        """Enhance JavaScript/TypeScript code with JSDoc comments"""
        lines = original_code.split('\n')

        # Collect items to enhance
        items = []

        for func in module.functions:
            if func.ai_explanation and not func.docstring:
                items.append(('function', func.line_number, func))

        for cls in module.classes:
            if cls.ai_explanation and not cls.docstring:
                items.append(('class', cls.line_number, cls))
            for method in cls.methods:
                if method.ai_explanation and not method.docstring:
                    items.append(('method', method.line_number, method))

        # Sort by line number in reverse order
        items.sort(key=lambda x: x[1], reverse=True)

        # Insert JSDoc comments
        for item_type, line_num, item in items:
            # JSDoc goes BEFORE the definition (and before its decorators)
            insert_line = self._above_decorators(lines, line_num - 1, '@')

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
            if func.ai_explanation and not func.docstring:
                items.append(('function', func.line_number, func))

        for cls in module.classes:
            if cls.ai_explanation and not cls.docstring:
                items.append(('class', cls.line_number, cls))
            for method in cls.methods:
                if method.ai_explanation and not method.docstring:
                    items.append(('method', method.line_number, method))

        # Sort by line number in reverse order
        items.sort(key=lambda x: x[1], reverse=True)

        # Insert Javadoc comments
        for item_type, line_num, item in items:
            # Javadoc goes BEFORE the definition (and before its annotations)
            insert_line = self._above_decorators(lines, line_num - 1, '@')

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

    @staticmethod
    def _documented_parameters(func: FunctionInfo) -> List[ParameterInfo]:
        """Parameters that have a real description (self and cls never need one)"""
        return [p for p in func.parameters if p.description and p.name not in ('self', 'cls')]

    @staticmethod
    def _escape_docstring(text: str) -> str:
        """Text that is safe inside a triple-quoted docstring: backslashes are doubled and triple quotes escaped"""
        return text.replace('\\', '\\\\').replace('"""', '\\"\\"\\"').rstrip()

    def _generate_google_docstring(self, func: FunctionInfo) -> str:
        """Google-style docstring: the explanation, and the parameters that have a description"""
        parts = [self._escape_docstring(func.ai_explanation or "")]

        documented = self._documented_parameters(func)
        if documented:
            parts.append("\nArgs:")
            for param in documented:
                type_str = f" ({param.type_hint})" if param.type_hint else ""
                parts.append(f"    {param.name}{type_str}: {self._escape_docstring(param.description)}")

        return "\n".join(parts)

    def _generate_numpy_docstring(self, func: FunctionInfo) -> str:
        """NumPy-style docstring: the explanation, and the parameters that have a description"""
        parts = [self._escape_docstring(func.ai_explanation or "")]

        documented = self._documented_parameters(func)
        if documented:
            parts.append("")
            parts.append("Parameters")
            parts.append("----------")
            for param in documented:
                type_str = f" : {param.type_hint}" if param.type_hint else ""
                parts.append(f"{param.name}{type_str}")
                parts.append(f"    {self._escape_docstring(param.description)}")
                parts.append("")
            parts.pop()

        return "\n".join(parts)

    def _generate_python_class_docstring(self, cls: ClassInfo, style: str) -> str:
        """Class docstring: the explanation (attribute descriptions are not known, so none are made up)"""
        return self._escape_docstring(cls.ai_explanation or "")

    def _generate_jsdoc_function(self, func: FunctionInfo, indent: str) -> str:
        """Generate JSDoc comment for function"""
        lines = [f"{indent}/**"]
        lines.append(f"{indent} * {self._comment_text(func.ai_explanation)}")

        # Parameters that have a description
        for param in func.parameters:
            if not param.description:
                continue
            type_str = f" {{{param.type_hint}}}" if param.type_hint else ""
            lines.append(f"{indent} * @param{type_str} {param.name} - {self._comment_text(param.description)}")

        lines.append(f"{indent} */")
        return "\n".join(lines)

    def _generate_jsdoc_class(self, cls: ClassInfo, indent: str) -> str:
        """Generate JSDoc comment for class"""
        lines = [f"{indent}/**"]
        lines.append(f"{indent} * {self._comment_text(cls.ai_explanation)}")
        lines.append(f"{indent} */")
        return "\n".join(lines)

    def _generate_javadoc_function(self, func: FunctionInfo, indent: str) -> str:
        """Generate Javadoc comment for method"""
        lines = [f"{indent}/**"]
        lines.append(f"{indent} * {self._comment_text(func.ai_explanation)}")

        # Parameters that have a description
        for param in func.parameters:
            if param.description:
                lines.append(f"{indent} * @param {param.name} {self._comment_text(param.description)}")

        lines.append(f"{indent} */")
        return "\n".join(lines)

    def _generate_javadoc_class(self, cls: ClassInfo, indent: str) -> str:
        """Generate Javadoc comment for class"""
        lines = [f"{indent}/**"]
        lines.append(f"{indent} * {self._comment_text(cls.ai_explanation)}")
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

    @staticmethod
    def _comment_text(text: Optional[str]) -> str:
        """Text for the inside of a /** */ comment: one line, and it cannot end the comment early"""
        return " ".join((text or "").split()).replace("*/", "* /")

    @staticmethod
    def _above_decorators(lines: List[str], index: int, marker: str) -> int:
        """Index to insert a comment at: above the decorator/annotation lines that sit over the definition"""
        while index > 0 and lines[index - 1].strip().startswith(marker):
            index -= 1
        return index

    def _get_indentation(self, line: str) -> str:
        """Get indentation from line"""
        match = re.match(r'^(\s*)', line)
        return match.group(1) if match else ""
