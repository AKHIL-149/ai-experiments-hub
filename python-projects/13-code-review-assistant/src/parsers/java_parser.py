"""
Java Parser
Parses Java source files using javalang
"""

import re
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

try:
    import javalang
    JAVALANG_AVAILABLE = True
except ImportError:
    JAVALANG_AVAILABLE = False
    print("Warning: javalang not installed. Java parsing will use fallback mode.")

from .base_parser import BaseParser, ParseError
from .models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo


class JavaParser(BaseParser):
    """
    Parser for Java source files.

    Supports:
    - Java 8+ syntax
    - Classes and interfaces
    - Methods and constructors
    - Annotations
    - Generics (basic support)
    - Enums
    """

    @property
    def supported_extensions(self) -> List[str]:
        """Supported file extensions"""
        return ['.java']

    def parse_file(self, file_path: str) -> ParsedModule:
        """Parse a Java file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            return self.parse_code(code, file_path)
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {file_path}")
        except Exception as e:
            raise ParseError(f"Failed to read file: {str(e)}", file_path)

    def parse_code(self, code: str, file_path: str = "<string>") -> ParsedModule:
        """Parse Java source code"""

        if JAVALANG_AVAILABLE:
            try:
                return self._parse_with_javalang(code, file_path)
            except Exception as e:
                # Fallback to regex parsing
                print(f"Javalang parsing failed: {e}. Using fallback parser.")
                return self._parse_with_regex(code, file_path)
        else:
            return self._parse_with_regex(code, file_path)

    def _parse_with_javalang(self, code: str, file_path: str) -> ParsedModule:
        """Parse using javalang library"""
        try:
            tree = javalang.parse.parse(code)
        except Exception as e:
            raise ParseError(f"Java parse error: {str(e)}", file_path)

        # Extract package and imports
        package_name = tree.package.name if tree.package else None
        imports = []
        for imp in tree.imports:
            import_path = imp.path
            if imp.wildcard:
                import_path += '.*'
            imports.append(import_path)

        # Extract classes and interfaces
        classes = []
        functions = []  # Top-level methods (rare in Java)
        global_variables = []

        # Iterate through top-level type declarations
        if tree.types:
            for type_decl in tree.types:
                if isinstance(type_decl, javalang.tree.ClassDeclaration):
                    classes.append(self._parse_class(type_decl, code))
                elif isinstance(type_decl, javalang.tree.InterfaceDeclaration):
                    classes.append(self._parse_interface(type_decl, code))
                elif isinstance(type_decl, javalang.tree.EnumDeclaration):
                    classes.append(self._parse_enum(type_decl, code))

        # Module docstring (Javadoc at top of file)
        module_docstring = self._extract_file_javadoc(code)

        return ParsedModule(
            file_path=file_path,
            language='java',
            module_docstring=module_docstring,
            imports=imports,
            functions=functions,
            classes=classes,
            global_variables=global_variables,
            parse_timestamp=datetime.now(timezone.utc).isoformat()
        )

    def _parse_class(self, node, source_code: str) -> ClassInfo:
        """Parse a class declaration"""
        name = node.name
        line_number = node.position.line if node.position else 0

        # Extract base class
        base_classes = []
        if node.extends:
            if isinstance(node.extends, list):
                base_classes.extend([self._get_type_name(ext) for ext in node.extends])
            else:
                base_classes.append(self._get_type_name(node.extends))

        # Extract implemented interfaces
        if node.implements:
            for impl in node.implements:
                base_classes.append(self._get_type_name(impl))

        # Extract annotations/decorators
        decorators = []
        if node.annotations:
            for annotation in node.annotations:
                decorators.append(f"@{annotation.name}")

        # Extract methods
        methods = []
        attributes = []

        if node.body:
            for member in node.body:
                if isinstance(member, javalang.tree.MethodDeclaration):
                    methods.append(self._parse_method(member, source_code))
                elif isinstance(member, javalang.tree.ConstructorDeclaration):
                    methods.append(self._parse_constructor(member, source_code))
                elif isinstance(member, javalang.tree.FieldDeclaration):
                    for declarator in member.declarators:
                        attributes.append({
                            'name': declarator.name,
                            'type': self._get_type_name(member.type),
                            'modifiers': member.modifiers if member.modifiers else []
                        })

        # Extract Javadoc
        docstring = self._extract_javadoc(source_code, line_number)

        return ClassInfo(
            name=name,
            line_number=line_number,
            docstring=docstring,
            base_classes=base_classes,
            methods=methods,
            attributes=attributes,
            decorators=decorators
        )

    def _parse_interface(self, node, source_code: str) -> ClassInfo:
        """Parse an interface declaration"""
        name = node.name
        line_number = node.position.line if node.position else 0

        # Extract extended interfaces
        base_classes = []
        if node.extends:
            for ext in node.extends:
                base_classes.append(self._get_type_name(ext))

        # Extract annotations
        decorators = []
        if node.annotations:
            for annotation in node.annotations:
                decorators.append(f"@{annotation.name}")

        # Extract methods (interface methods)
        methods = []
        if node.body:
            for member in node.body:
                if isinstance(member, javalang.tree.MethodDeclaration):
                    methods.append(self._parse_method(member, source_code))

        docstring = self._extract_javadoc(source_code, line_number)

        return ClassInfo(
            name=name + " (interface)",
            line_number=line_number,
            docstring=docstring,
            base_classes=base_classes,
            methods=methods,
            attributes=[],
            decorators=decorators
        )

    def _parse_enum(self, node, source_code: str) -> ClassInfo:
        """Parse an enum declaration"""
        name = node.name
        line_number = node.position.line if node.position else 0

        # Extract enum constants as attributes
        attributes = []
        if node.body and node.body.constants:
            for constant in node.body.constants:
                attributes.append({
                    'name': constant.name,
                    'type': 'enum constant',
                    'modifiers': []
                })

        # Extract methods in enum
        methods = []
        if node.body and node.body.declarations:
            for member in node.body.declarations:
                if isinstance(member, javalang.tree.MethodDeclaration):
                    methods.append(self._parse_method(member, source_code))

        docstring = self._extract_javadoc(source_code, line_number)

        return ClassInfo(
            name=name + " (enum)",
            line_number=line_number,
            docstring=docstring,
            base_classes=[],
            methods=methods,
            attributes=attributes,
            decorators=[]
        )

    def _parse_method(self, node, source_code: str) -> FunctionInfo:
        """Parse a method declaration"""
        name = node.name
        line_number = node.position.line if node.position else 0

        # Extract parameters
        parameters = []
        if node.parameters:
            for param in node.parameters:
                param_type = self._get_type_name(param.type)
                parameters.append(ParameterInfo(
                    name=param.name,
                    type_hint=param_type,
                    default_value=None
                ))

        # Extract return type
        return_type = self._get_type_name(node.return_type) if node.return_type else 'void'

        # Extract annotations
        decorators = []
        if node.annotations:
            for annotation in node.annotations:
                decorators.append(f"@{annotation.name}")

        # Check modifiers
        is_static = 'static' in node.modifiers if node.modifiers else False

        # Extract Javadoc
        docstring = self._extract_javadoc(source_code, line_number)

        return FunctionInfo(
            name=name,
            line_number=line_number,
            parameters=parameters,
            return_type=return_type,
            docstring=docstring,
            decorators=decorators,
            is_async=False,  # Java doesn't have async keyword
            is_method=True,
            is_static=is_static
        )

    def _parse_constructor(self, node, source_code: str) -> FunctionInfo:
        """Parse a constructor declaration"""
        name = node.name
        line_number = node.position.line if node.position else 0

        # Extract parameters
        parameters = []
        if node.parameters:
            for param in node.parameters:
                param_type = self._get_type_name(param.type)
                parameters.append(ParameterInfo(
                    name=param.name,
                    type_hint=param_type
                ))

        # Extract annotations
        decorators = []
        if node.annotations:
            for annotation in node.annotations:
                decorators.append(f"@{annotation.name}")

        docstring = self._extract_javadoc(source_code, line_number)

        return FunctionInfo(
            name=f"{name} (constructor)",
            line_number=line_number,
            parameters=parameters,
            return_type=None,
            docstring=docstring,
            decorators=decorators,
            is_method=True
        )

    def _get_type_name(self, type_node) -> str:
        """Extract type name from type node"""
        if type_node is None:
            return 'void'

        if isinstance(type_node, str):
            return type_node

        if hasattr(type_node, 'name'):
            name = type_node.name
            # Handle generics
            if hasattr(type_node, 'arguments') and type_node.arguments:
                args = ', '.join([self._get_type_name(arg) for arg in type_node.arguments])
                return f"{name}<{args}>"
            return name

        if hasattr(type_node, 'dimensions'):
            # Array type
            base_type = self._get_type_name(type_node)
            return base_type + '[]' * (type_node.dimensions or 0)

        return str(type_node)

    def _extract_javadoc(self, source_code: str, line_number: int) -> Optional[str]:
        """Extract Javadoc comment before a declaration"""
        lines = source_code.split('\n')
        if line_number <= 0 or line_number > len(lines):
            return None

        # Look backwards for Javadoc (/** ... */)
        javadoc_lines = []
        in_javadoc = False

        for i in range(line_number - 2, -1, -1):
            line = lines[i].strip()

            if line.endswith('*/'):
                in_javadoc = True
                javadoc_lines.insert(0, line)
                continue

            if in_javadoc:
                javadoc_lines.insert(0, line)
                if line.startswith('/**'):
                    break

            if not in_javadoc and line and not line.startswith('//') and not line.startswith('@'):
                break

        if javadoc_lines:
            # Clean up Javadoc
            doc = '\n'.join(javadoc_lines)
            doc = doc.replace('/**', '').replace('*/', '').replace('*', '').strip()
            return doc if doc else None

        return None

    def _extract_file_javadoc(self, source_code: str) -> Optional[str]:
        """Extract file-level Javadoc (at the top of the file)"""
        lines = source_code.split('\n')

        # Look for Javadoc in first 10 lines
        javadoc_lines = []
        in_javadoc = False

        for line in lines[:10]:
            stripped = line.strip()

            if stripped.startswith('/**'):
                in_javadoc = True
                javadoc_lines.append(stripped)
            elif in_javadoc:
                javadoc_lines.append(stripped)
                if stripped.endswith('*/'):
                    break
            elif stripped and not stripped.startswith('//'):
                # Stop if we hit non-comment code
                break

        if javadoc_lines:
            doc = '\n'.join(javadoc_lines)
            doc = doc.replace('/**', '').replace('*/', '').replace('*', '').strip()
            return doc if doc else None

        return None

    def _parse_with_regex(self, code: str, file_path: str) -> ParsedModule:
        """
        Fallback regex-based parser for basic structure extraction.
        Not as accurate as javalang but works without dependencies.
        """

        # Extract package
        package_match = re.search(r'package\s+([\w.]+)\s*;', code)
        package_name = package_match.group(1) if package_match else None

        # Extract imports
        imports = []
        for match in re.finditer(r'import\s+(?:static\s+)?([\w.*]+)\s*;', code):
            imports.append(match.group(1))

        # Extract classes
        classes = []
        class_pattern = r'(?:public|private|protected)?\s*(?:static|final|abstract)?\s*class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s]+))?\s*\{'
        for match in re.finditer(class_pattern, code):
            class_name = match.group(1)
            extends = match.group(2)
            implements = match.group(3)
            line_num = code[:match.start()].count('\n') + 1

            base_classes = []
            if extends:
                base_classes.append(extends)
            if implements:
                base_classes.extend([i.strip() for i in implements.split(',')])

            classes.append(ClassInfo(
                name=class_name,
                line_number=line_num,
                base_classes=base_classes,
                methods=[],  # Would need more complex parsing
                attributes=[]
            ))

        # Extract interfaces
        interface_pattern = r'(?:public|private)?\s*interface\s+(\w+)(?:\s+extends\s+([\w,\s]+))?\s*\{'
        for match in re.finditer(interface_pattern, code):
            interface_name = match.group(1)
            extends = match.group(2)
            line_num = code[:match.start()].count('\n') + 1

            base_classes = []
            if extends:
                base_classes.extend([i.strip() for i in extends.split(',')])

            classes.append(ClassInfo(
                name=interface_name + " (interface)",
                line_number=line_num,
                base_classes=base_classes,
                methods=[],
                attributes=[]
            ))

        # Extract enums
        enum_pattern = r'(?:public|private)?\s*enum\s+(\w+)\s*\{'
        for match in re.finditer(enum_pattern, code):
            enum_name = match.group(1)
            line_num = code[:match.start()].count('\n') + 1

            classes.append(ClassInfo(
                name=enum_name + " (enum)",
                line_number=line_num,
                base_classes=[],
                methods=[],
                attributes=[]
            ))

        # Extract methods (simple pattern)
        functions = []
        method_pattern = r'(?:public|private|protected)\s+(?:static\s+)?(?:final\s+)?(\w+(?:<[^>]+>)?)\s+(\w+)\s*\(([^)]*)\)'
        for match in re.finditer(method_pattern, code):
            return_type = match.group(1)
            method_name = match.group(2)
            params_str = match.group(3)
            line_num = code[:match.start()].count('\n') + 1

            # Skip constructors and common Java keywords
            if method_name in ['class', 'interface', 'enum', 'if', 'for', 'while']:
                continue

            # Parse parameters
            parameters = []
            if params_str.strip():
                for param in params_str.split(','):
                    param = param.strip()
                    if param:
                        parts = param.split()
                        if len(parts) >= 2:
                            param_type = ' '.join(parts[:-1])
                            param_name = parts[-1]
                            parameters.append(ParameterInfo(
                                name=param_name,
                                type_hint=param_type
                            ))

            functions.append(FunctionInfo(
                name=method_name,
                line_number=line_num,
                parameters=parameters,
                return_type=return_type,
                is_method=True
            ))

        return ParsedModule(
            file_path=file_path,
            language='java',
            module_docstring=None,
            imports=imports,
            functions=functions,
            classes=classes,
            global_variables=[],
            parse_timestamp=datetime.now(timezone.utc).isoformat()
        )
