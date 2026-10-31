"""Java code parser using javalang"""
from pathlib import Path
from typing import List, Optional, Any
from datetime import datetime

try:
    import javalang
    JAVALANG_AVAILABLE = True
except ImportError:
    JAVALANG_AVAILABLE = False
    javalang = None  # Dummy assignment for type hints

import re

from .base_parser import BaseParser, ParseError, read_source_text
from .models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo


class JavaParser(BaseParser):
    """
    Parser for Java source code using javalang library.

    Requires: pip install javalang
    """

    def __init__(self):
        if not JAVALANG_AVAILABLE:
            raise ImportError(
                "javalang is required for Java parsing. "
                "Install it with: pip install javalang"
            )

    @property
    def supported_extensions(self) -> List[str]:
        return ['.java']

    def parse_file(self, file_path: str) -> ParsedModule:
        """Parse a Java file"""
        try:
            code = read_source_text(file_path)
        except FileNotFoundError:
            raise ParseError(f"File not found: {file_path}", file_path=file_path)
        except ParseError as e:
            raise ParseError(e.message, file_path=file_path)
        except OSError as e:
            raise ParseError(f"Cannot read file: {e}", file_path=file_path)
        return self.parse_code(code, file_path)

    def parse_code(self, code: str, file_path: str = "<string>") -> ParsedModule:
        """Parse Java code string"""
        try:
            tree = javalang.parse.parse(code)
        except (javalang.parser.JavaSyntaxError, javalang.tokenizer.LexerError) as e:
            line = getattr(getattr(e, 'at', None), 'position', None)
            line = getattr(line, 'line', None)
            raise ParseError(
                f"Java syntax error: {self._describe_error(e)}{self._modern_syntax_hint(code)}",
                file_path=file_path,
                line_number=line
            )
        except Exception as e:
            raise ParseError(f"Failed to parse Java code: {' '.join(str(e).split()) or type(e).__name__}", file_path=file_path)

        # Extract package and imports
        package_name = tree.package.name if tree.package else None
        imports = self._extract_imports(tree)

        # Extract classes (Java requires everything in classes)
        classes = []
        functions = []  # Top-level functions don't exist in Java, but we'll check anyway

        for node in tree.types or []:
            self._collect_type(node, code, '', classes)

        # Module docstring (extract from first Javadoc comment if any)
        module_docstring = self._extract_file_docstring(code)

        return ParsedModule(
            file_path=file_path,
            language='java',
            module_docstring=module_docstring,
            imports=imports,
            functions=functions,
            classes=classes,
            global_variables=[],  # Java doesn't have module-level variables
            parse_timestamp=datetime.now().isoformat()
        )

    MODERN_SYNTAX = (
        (r'\brecord\s+\w+\s*(?:<[^>]*>)?\s*\(', 'records'),
        (r'\b(?:sealed|non-sealed)\b|\bpermits\b', 'sealed types'),
        (r'"""', 'text blocks'),
        (r'\bcase\b[^:\n]*->|\bswitch\s*\([^)]*\)\s*\{[^}]*->', 'switch expressions'),
        (r'\binstanceof\s+[\w.<>]+\s+\w+\s*[&)]', 'pattern matching'),
    )

    @staticmethod
    def _describe_error(error) -> str:
        """What the parser objected to, in one line (the exception's own text is empty)"""
        detail = getattr(error, 'description', None) or str(error) or type(error).__name__
        at = getattr(error, 'at', None)
        text = f"{detail}: {at}" if at is not None and not isinstance(at, str) else str(detail)
        return ' '.join(text.split())

    def _modern_syntax_hint(self, code: str) -> str:
        """The parser understands Java up to version 8; say so when the file uses newer syntax"""
        found = [label for pattern, label in self.MODERN_SYNTAX if re.search(pattern, code)]
        if not found:
            return ''
        return f" (this file uses newer Java syntax: {', '.join(found)}; the Java parser supports Java 8 syntax)"

    def _collect_type(self, node: Any, code: str, prefix: str, out: List[ClassInfo]) -> None:
        """Add a type and, after it, the types declared inside it (named Outer.Inner)"""
        if isinstance(node, javalang.tree.ClassDeclaration):
            info = self._extract_class(node, code)
            members = node.body
        elif isinstance(node, javalang.tree.InterfaceDeclaration):
            info = self._extract_interface(node, code)
            members = node.body
        elif isinstance(node, javalang.tree.EnumDeclaration):
            info = self._extract_enum(node, code)
            members = node.body.declarations if node.body else []
        else:
            return
        info.name = prefix + info.name
        out.append(info)
        for member in members or []:
            self._collect_type(member, code, info.name + '.', out)

    def _extract_imports(self, tree: Any) -> List[str]:
        """Extract import statements"""
        imports = []

        if tree.imports:
            for imp in tree.imports:
                import_str = f"import {imp.path}"
                if imp.static:
                    import_str = f"import static {imp.path}"
                if imp.wildcard:
                    import_str += ".*"
                imports.append(import_str)

        return imports

    def _extract_file_docstring(self, code: str) -> Optional[str]:
        """The file-level Javadoc: a /** */ comment at the top that is followed by package or import.

        A comment straight above the first type is that type's documentation, not the file's.
        """
        match = re.match(r'\s*(/\*\*.*?\*/)\s*(?:package|import)\b', code, re.S)
        if not match:
            return None
        return self._clean_javadoc(match.group(1)) or None

    def _extract_class(self, node: Any, code: str) -> ClassInfo:
        """Extract class information"""
        # Extract Javadoc
        docstring = self._extract_javadoc(node.documentation)

        # Extract base class and interfaces
        base_classes = []
        if node.extends:
            base_classes.append(node.extends.name)
        if node.implements:
            base_classes.extend([impl.name for impl in node.implements])

        # Extract methods
        methods = []
        for method in node.methods or []:
            methods.append(self._extract_method(method, code))

        # Extract constructors (treat as special methods)
        for constructor in node.constructors or []:
            methods.append(self._extract_constructor(constructor, code, node.name))

        # Extract fields (attributes)
        attributes = []
        for field in node.fields or []:
            attributes.extend(self._extract_field(field))

        # Extract modifiers
        modifiers = node.modifiers or []
        decorators = [f"@{mod}" for mod in modifiers if mod not in ['public', 'private', 'protected']]
        decorators += [f"@{a.name}" for a in node.annotations or []]

        return ClassInfo(
            name=node.name,
            line_number=getattr(node.position, 'line', 0) if hasattr(node, 'position') else 0,
            docstring=docstring,
            base_classes=base_classes,
            methods=methods,
            attributes=attributes,
            decorators=decorators
        )

    def _extract_interface(self, node: Any, code: str) -> ClassInfo:
        """Extract interface information (treat as a class)"""
        docstring = self._extract_javadoc(node.documentation)

        # Interfaces can extend other interfaces
        base_classes = []
        if node.extends:
            base_classes.extend([ext.name for ext in node.extends])

        # Extract methods (all abstract in interfaces)
        methods = []
        for method in node.methods or []:
            method_info = self._extract_method(method, code)
            if method.body is None:                     # default and static methods have a body
                method_info.decorators.append('@abstract')
            methods.append(method_info)

        # Constants declared in the interface
        attributes = []
        for field in node.fields or []:
            attributes.extend(self._extract_field(field))

        return ClassInfo(
            name=node.name,
            line_number=getattr(node.position, 'line', 0) if hasattr(node, 'position') else 0,
            docstring=docstring,
            base_classes=base_classes,
            methods=methods,
            attributes=attributes,
            decorators=['@interface']
        )

    def _extract_enum(self, node: Any, code: str) -> ClassInfo:
        """Extract enum information (treat as a class)"""
        docstring = self._extract_javadoc(node.documentation)

        # Extract enum constants as attributes
        attributes = []
        for constant in node.body.constants or []:
            attributes.append({
                'name': constant.name,
                'type': 'enum constant',
                'default_value': None,
                'line_number': getattr(constant.position, 'line', 0) if hasattr(constant, 'position') else 0
            })

        # Fields, constructors and methods declared in the enum body
        methods = []
        for member in (node.body.declarations if node.body else None) or []:
            if isinstance(member, javalang.tree.MethodDeclaration):
                methods.append(self._extract_method(member, code))
            elif isinstance(member, javalang.tree.ConstructorDeclaration):
                methods.append(self._extract_constructor(member, code, node.name))
            elif isinstance(member, javalang.tree.FieldDeclaration):
                attributes.extend(self._extract_field(member))

        base_classes = [impl.name for impl in node.implements or []]

        return ClassInfo(
            name=node.name,
            line_number=getattr(node.position, 'line', 0) if hasattr(node, 'position') else 0,
            docstring=docstring,
            base_classes=base_classes,
            methods=methods,
            attributes=attributes,
            decorators=['@enum']
        )

    def _extract_method(self, node: Any, code: str) -> FunctionInfo:
        """Extract method information"""
        docstring = self._extract_javadoc(node.documentation)

        # Extract parameters
        parameters = []
        for param in node.parameters or []:
            param_type = self._type_to_string(param.type)
            parameters.append(ParameterInfo(
                name=param.name,
                type_hint=param_type,
                default_value=None,  # Java doesn't have default values
                description=None
            ))

        # Extract return type
        return_type = self._type_to_string(node.return_type) if node.return_type else 'void'

        # Extract modifiers
        modifiers = node.modifiers or []
        is_static = 'static' in modifiers
        decorators = [f"@{mod}" for mod in modifiers if mod in ['abstract', 'final', 'synchronized']]

        # Add access modifier as decorator
        if 'public' in modifiers:
            decorators.insert(0, '@public')
        elif 'private' in modifiers:
            decorators.insert(0, '@private')
        elif 'protected' in modifiers:
            decorators.insert(0, '@protected')
        decorators += [f"@{a.name}" for a in node.annotations or []]

        summary, line_count = self._body_of(node, code)

        return FunctionInfo(
            name=node.name,
            line_number=getattr(node.position, 'line', 0) if hasattr(node, 'position') else 0,
            parameters=parameters,
            return_type=return_type,
            docstring=docstring,
            decorators=decorators,
            body_summary=summary,
            body_lines=line_count,
            complexity=self._complexity(line_count),
            is_async=False,  # Java doesn't have async/await
            is_method=True,
            is_static=is_static,
            is_classmethod=False
        )

    def _extract_constructor(self, node: Any, code: str, class_name: str = '<init>') -> FunctionInfo:
        """Extract constructor information"""
        docstring = self._extract_javadoc(node.documentation)

        # Extract parameters
        parameters = []
        for param in node.parameters or []:
            param_type = self._type_to_string(param.type)
            parameters.append(ParameterInfo(
                name=param.name,
                type_hint=param_type,
                default_value=None,
                description=None
            ))

        # Extract modifiers
        modifiers = node.modifiers or []
        decorators = ['@constructor']

        if 'public' in modifiers:
            decorators.append('@public')
        elif 'private' in modifiers:
            decorators.append('@private')
        elif 'protected' in modifiers:
            decorators.append('@protected')

        summary, line_count = self._body_of(node, code)

        return FunctionInfo(
            name=class_name,  # a constructor is named like its class
            line_number=getattr(node.position, 'line', 0) if hasattr(node, 'position') else 0,
            parameters=parameters,
            return_type=None,  # Constructors don't have return types
            docstring=docstring,
            decorators=decorators,
            body_summary=summary,
            body_lines=line_count,
            complexity=self._complexity(line_count),
            is_async=False,
            is_method=True,
            is_static=False,
            is_classmethod=False
        )

    def _extract_field(self, node: Any) -> List[dict]:
        """Extract field (attribute) information"""
        attributes = []
        field_type = self._type_to_string(node.type)
        modifiers = node.modifiers or []

        for declarator in node.declarators:
            is_static = 'static' in modifiers
            is_final = 'final' in modifiers

            attributes.append({
                'name': declarator.name,
                'type': field_type,
                'default_value': None,
                'line_number': getattr(node.position, 'line', 0) if hasattr(node, 'position') else 0,
                'is_static': is_static,
                'is_final': is_final
            })

        return attributes

    @staticmethod
    def _complexity(line_count: Optional[int]) -> str:
        if line_count is None or line_count <= 10:
            return 'Simple'
        return 'Medium' if line_count <= 30 else 'Complex'

    def _body_of(self, node: Any, code: str):
        """(first lines of the body as written, number of non-blank body lines) of a method or constructor.

        (None, None) when the position is unknown; (None, 0) for an empty body or no body at all
        (abstract and interface methods).
        """
        position = getattr(node, 'position', None)
        if position is None:
            return None, None
        if getattr(node, 'body', None) is None and not isinstance(node, javalang.tree.ConstructorDeclaration):
            return None, 0
        text = self._find_body(code, position.line, position.column, node.name)
        if text is None:
            return None, None
        kept = [line for line in text.split('\n') if line.strip()]
        if not kept:
            return None, 0
        indent = min(len(line) - len(line.lstrip()) for line in kept)
        shown = [line[indent:].rstrip() for line in kept[:5]]
        return '\n'.join(shown), len(kept)

    @staticmethod
    def _find_body(code: str, line: int, column: int, name: str) -> Optional[str]:
        """The text between the braces of the body of the method whose name starts at (line, column)"""
        lines = code.split('\n')
        if line < 1 or line > len(lines):
            return None
        offset = sum(len(l) + 1 for l in lines[:line - 1]) + max(column - 1, 0)
        i = code.find('(', offset)
        if i < 0:
            return None

        def skip(i: int) -> int:
            """If a string, char literal or comment starts at i, the index after it; else i"""
            if code.startswith('//', i):
                end = code.find('\n', i)
                return len(code) if end < 0 else end
            if code.startswith('/*', i):
                end = code.find('*/', i + 2)
                return len(code) if end < 0 else end + 2
            if code[i] in '"\'':
                quote, j = code[i], i + 1
                while j < len(code) and code[j] != quote and code[j] != '\n':
                    j += 2 if code[j] == '\\' else 1
                return j + 1
            return i

        depth = 0
        while i < len(code):                       # the parameter list
            j = skip(i)
            if j != i:
                i = j
                continue
            if code[i] == '(':
                depth += 1
            elif code[i] == ')':
                depth -= 1
                if depth == 0:
                    i += 1
                    break
            i += 1
        while i < len(code) and code[i] not in '{;':      # throws clause, annotation defaults
            j = skip(i)
            i = j if j != i else i + 1
        if i >= len(code) or code[i] == ';':
            return None
        start, depth = i + 1, 0
        while i < len(code):
            j = skip(i)
            if j != i:
                i = j
                continue
            if code[i] == '{':
                depth += 1
            elif code[i] == '}':
                depth -= 1
                if depth == 0:
                    return code[start:i]
            i += 1
        return None

    def _type_to_string(self, type_obj) -> str:
        """Convert javalang type object to string"""
        if type_obj is None:
            return 'void'

        if isinstance(type_obj, javalang.tree.BasicType):
            return type_obj.name

        if isinstance(type_obj, javalang.tree.ReferenceType):
            type_str = type_obj.name

            # Add generic parameters if present
            if type_obj.arguments:
                args = ', '.join(self._type_to_string(arg.type) for arg in type_obj.arguments if hasattr(arg, 'type'))
                type_str += f"<{args}>"

            # Add array dimensions
            if type_obj.dimensions:
                type_str += '[]' * len([d for d in type_obj.dimensions if d])

            return type_str

        return str(type_obj)

    def _extract_javadoc(self, doc_node) -> Optional[str]:
        """Extract and clean Javadoc comment"""
        if not doc_node:
            return None

        # Javadoc is stored as a string in the documentation attribute
        if isinstance(doc_node, str):
            return self._clean_javadoc(doc_node)

        return None

    def _clean_javadoc(self, javadoc: str) -> str:
        """Clean a Javadoc comment: no /** */ delimiters or leading asterisks; @param/@return tags are kept"""
        javadoc = re.sub(r'^\s*/\*+', '', javadoc)
        javadoc = re.sub(r'\*+/\s*$', '', javadoc)
        cleaned = []
        for line in javadoc.split('\n'):
            line = re.sub(r'^\s*\*+\s?', '', line).strip()
            if line:
                cleaned.append(line)
        return '\n'.join(cleaned).strip()
