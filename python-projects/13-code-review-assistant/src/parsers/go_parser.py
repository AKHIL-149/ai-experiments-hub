"""
Go Parser
Parses Go source files using regex patterns
"""

import re
from typing import List, Optional
from datetime import datetime, timezone

from .base_parser import BaseParser, ParseError
from .models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo


class GoParser(BaseParser):
    """
    Parser for Go source files.

    Supports:
    - Go 1.x syntax
    - Packages and imports
    - Functions and methods
    - Structs and interfaces
    - Type declarations

    Note: Uses regex-based parsing for simplicity and no external dependencies
    """

    @property
    def supported_extensions(self) -> List[str]:
        """Supported file extensions"""
        return ['.go']

    def parse_file(self, file_path: str) -> ParsedModule:
        """Parse a Go file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            return self.parse_code(code, file_path)
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {file_path}")
        except Exception as e:
            raise ParseError(f"Failed to read file: {str(e)}", file_path)

    def parse_code(self, code: str, file_path: str = "<string>") -> ParsedModule:
        """Parse Go source code"""

        # Extract package
        package_name = self._extract_package(code)

        # Extract imports
        imports = self._extract_imports(code)

        # Extract structs (Go's version of classes)
        classes = self._extract_structs(code)

        # Extract interfaces
        classes.extend(self._extract_interfaces(code))

        # Extract functions
        functions = self._extract_functions(code)

        # Extract global variables and constants
        global_variables = self._extract_globals(code)

        # Extract module-level comment
        module_docstring = self._extract_package_comment(code)

        return ParsedModule(
            file_path=file_path,
            language='go',
            module_docstring=module_docstring,
            imports=imports,
            functions=functions,
            classes=classes,
            global_variables=global_variables,
            parse_timestamp=datetime.now(timezone.utc).isoformat()
        )

    def _extract_package(self, code: str) -> Optional[str]:
        """Extract package name"""
        match = re.search(r'package\s+(\w+)', code)
        return match.group(1) if match else None

    def _extract_imports(self, code: str) -> List[str]:
        """Extract import statements"""
        imports = []

        # Single import: import "fmt"
        for match in re.finditer(r'import\s+"([^"]+)"', code):
            imports.append(match.group(1))

        # Multi-import block
        import_block_pattern = r'import\s*\(((?:[^)]+|\([^)]*\))*)\)'
        for block_match in re.finditer(import_block_pattern, code, re.DOTALL):
            block = block_match.group(1)
            # Extract individual imports from block
            for match in re.finditer(r'"([^"]+)"', block):
                imports.append(match.group(1))

        return imports

    def _extract_structs(self, code: str) -> List[ClassInfo]:
        """Extract struct declarations"""
        structs = []

        # Pattern: type StructName struct { ... }
        struct_pattern = r'type\s+(\w+)\s+struct\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}'

        for match in re.finditer(struct_pattern, code, re.DOTALL):
            name = match.group(1)
            body = match.group(2)
            line_number = code[:match.start()].count('\n') + 1

            # Extract fields (struct's attributes)
            attributes = self._parse_struct_fields(body)

            # Extract methods for this struct
            methods = self._extract_methods(code, name)

            # Extract doc comment
            docstring = self._extract_doc_comment(code, line_number)

            structs.append(ClassInfo(
                name=name + " (struct)",
                line_number=line_number,
                docstring=docstring,
                base_classes=[],  # Go doesn't have inheritance
                methods=methods,
                attributes=attributes,
                decorators=[]
            ))

        return structs

    def _extract_interfaces(self, code: str) -> List[ClassInfo]:
        """Extract interface declarations"""
        interfaces = []

        # Pattern: type InterfaceName interface { ... }
        interface_pattern = r'type\s+(\w+)\s+interface\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}'

        for match in re.finditer(interface_pattern, code, re.DOTALL):
            name = match.group(1)
            body = match.group(2)
            line_number = code[:match.start()].count('\n') + 1

            # Extract method signatures
            methods = self._parse_interface_methods(body, line_number)

            # Extract doc comment
            docstring = self._extract_doc_comment(code, line_number)

            interfaces.append(ClassInfo(
                name=name + " (interface)",
                line_number=line_number,
                docstring=docstring,
                base_classes=[],
                methods=methods,
                attributes=[],
                decorators=[]
            ))

        return interfaces

    def _extract_functions(self, code: str) -> List[FunctionInfo]:
        """Extract function declarations"""
        functions = []

        # Pattern: func functionName(params) returnType { ... }
        func_pattern = r'func\s+(\w+)\s*\(([^)]*)\)\s*([^{]*)\s*\{'

        for match in re.finditer(func_pattern, code):
            name = match.group(1)
            params_str = match.group(2)
            return_str = match.group(3).strip()
            line_number = code[:match.start()].count('\n') + 1

            # Parse parameters
            parameters = self._parse_parameters(params_str)

            # Parse return type
            return_type = return_str if return_str else 'void'

            # Extract doc comment
            docstring = self._extract_doc_comment(code, line_number)

            functions.append(FunctionInfo(
                name=name,
                line_number=line_number,
                parameters=parameters,
                return_type=return_type,
                docstring=docstring,
                decorators=[],
                is_async=False,  # Go uses goroutines, not async/await
                is_method=False
            ))

        return functions

    def _extract_methods(self, code: str, struct_name: str) -> List[FunctionInfo]:
        """Extract methods for a specific struct"""
        methods = []

        # Pattern: func (receiver Type) methodName(params) returnType { ... }
        method_pattern = rf'func\s*\([^)]*\b{struct_name}\b[^)]*\)\s+(\w+)\s*\(([^)]*)\)\s*([^{{]*)\s*\{{'

        for match in re.finditer(method_pattern, code):
            name = match.group(1)
            params_str = match.group(2)
            return_str = match.group(3).strip()
            line_number = code[:match.start()].count('\n') + 1

            # Parse parameters
            parameters = self._parse_parameters(params_str)

            # Parse return type
            return_type = return_str if return_str else 'void'

            # Extract doc comment
            docstring = self._extract_doc_comment(code, line_number)

            methods.append(FunctionInfo(
                name=name,
                line_number=line_number,
                parameters=parameters,
                return_type=return_type,
                docstring=docstring,
                decorators=[],
                is_async=False,
                is_method=True
            ))

        return methods

    def _parse_struct_fields(self, body: str) -> List[dict]:
        """Parse struct field declarations"""
        attributes = []

        # Pattern: fieldName fieldType
        field_pattern = r'(\w+)\s+([^\n;]+)'

        for match in re.finditer(field_pattern, body):
            name = match.group(1)
            field_type = match.group(2).strip()

            # Skip if it looks like a tag or comment
            if name.startswith('//') or name.startswith('`'):
                continue

            attributes.append({
                'name': name,
                'type': field_type,
                'modifiers': []
            })

        return attributes

    def _parse_interface_methods(self, body: str, base_line: int) -> List[FunctionInfo]:
        """Parse method signatures in interface"""
        methods = []

        # Pattern: MethodName(params) returnType
        method_pattern = r'(\w+)\s*\(([^)]*)\)\s*([^\n]*)'

        offset = 0
        for match in re.finditer(method_pattern, body):
            name = match.group(1)
            params_str = match.group(2)
            return_str = match.group(3).strip()

            parameters = self._parse_parameters(params_str)
            return_type = return_str if return_str else 'void'

            methods.append(FunctionInfo(
                name=name,
                line_number=base_line + body[:match.start()].count('\n'),
                parameters=parameters,
                return_type=return_type,
                docstring=None,
                decorators=[],
                is_async=False,
                is_method=True
            ))

        return methods

    def _parse_parameters(self, params_str: str) -> List[ParameterInfo]:
        """Parse function parameters"""
        parameters = []

        if not params_str.strip():
            return parameters

        # Split by comma, handling nested types
        param_parts = self._smart_split(params_str, ',')

        for part in param_parts:
            part = part.strip()
            if not part:
                continue

            # Pattern: name type or just type
            tokens = part.split()
            if len(tokens) >= 2:
                name = tokens[0]
                param_type = ' '.join(tokens[1:])
            elif len(tokens) == 1:
                # Unnamed parameter (just type)
                name = 'arg'
                param_type = tokens[0]
            else:
                continue

            parameters.append(ParameterInfo(
                name=name,
                type_hint=param_type,
                default_value=None
            ))

        return parameters

    def _extract_globals(self, code: str) -> List[dict]:
        """Extract global variables and constants"""
        globals_list = []

        # Pattern: var name type = value
        var_pattern = r'var\s+(\w+)\s+([^\s=]+)(?:\s*=\s*([^\n]+))?'
        for match in re.finditer(var_pattern, code):
            name = match.group(1)
            var_type = match.group(2)
            line_number = code[:match.start()].count('\n') + 1

            globals_list.append({
                'name': name,
                'type': var_type,
                'line_number': line_number
            })

        # Pattern: const name type = value
        const_pattern = r'const\s+(\w+)\s+([^\s=]+)(?:\s*=\s*([^\n]+))?'
        for match in re.finditer(const_pattern, code):
            name = match.group(1)
            const_type = match.group(2)
            line_number = code[:match.start()].count('\n') + 1

            globals_list.append({
                'name': name,
                'type': const_type,
                'line_number': line_number
            })

        return globals_list

    def _extract_package_comment(self, code: str) -> Optional[str]:
        """Extract package-level doc comment"""
        # Look for comment before package declaration
        package_match = re.search(r'package\s+\w+', code)
        if not package_match:
            return None

        package_line = code[:package_match.start()].count('\n')

        # Look backwards for comment
        lines = code[:package_match.start()].split('\n')
        comment_lines = []

        for line in reversed(lines):
            stripped = line.strip()
            if stripped.startswith('//'):
                comment_lines.insert(0, stripped[2:].strip())
            elif stripped.startswith('/*'):
                # Multi-line comment
                comment_lines.insert(0, stripped[2:].strip())
            elif stripped.endswith('*/'):
                comment_lines.insert(0, stripped[:-2].strip())
            elif stripped and not stripped.startswith('//'):
                break

        return '\n'.join(comment_lines) if comment_lines else None

    def _extract_doc_comment(self, code: str, line_number: int) -> Optional[str]:
        """Extract doc comment before a declaration"""
        lines = code.split('\n')
        if line_number <= 0 or line_number > len(lines):
            return None

        comment_lines = []

        # Look backwards from the line before the declaration
        for i in range(line_number - 2, -1, -1):
            line = lines[i].strip()

            if line.startswith('//'):
                comment_lines.insert(0, line[2:].strip())
            elif line.startswith('/*'):
                comment_lines.insert(0, line[2:].strip())
            elif line.endswith('*/'):
                comment_lines.insert(0, line[:-2].strip())
            elif line and not line.startswith('//'):
                break

        return '\n'.join(comment_lines) if comment_lines else None

    def _smart_split(self, text: str, delimiter: str) -> List[str]:
        """Split text by delimiter, respecting nested brackets"""
        parts = []
        current = []
        depth = 0

        for char in text:
            if char in '([{':
                depth += 1
                current.append(char)
            elif char in ')]}':
                depth -= 1
                current.append(char)
            elif char == delimiter and depth == 0:
                parts.append(''.join(current))
                current = []
            else:
                current.append(char)

        if current:
            parts.append(''.join(current))

        return parts
