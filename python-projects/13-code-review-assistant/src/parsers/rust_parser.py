"""
Rust Parser
Parses Rust source files using regex patterns
"""

import re
from typing import List, Optional
from datetime import datetime, timezone

from .base_parser import BaseParser, ParseError
from .models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo


class RustParser(BaseParser):
    """
    Parser for Rust source files.

    Supports:
    - Rust 2018/2021 edition syntax
    - Modules and use statements
    - Functions and methods
    - Structs, enums, and traits
    - Impl blocks

    Note: Uses regex-based parsing for simplicity and no external dependencies
    """

    @property
    def supported_extensions(self) -> List[str]:
        """Supported file extensions"""
        return ['.rs']

    def parse_file(self, file_path: str) -> ParsedModule:
        """Parse a Rust file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            return self.parse_code(code, file_path)
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {file_path}")
        except Exception as e:
            raise ParseError(f"Failed to read file: {str(e)}", file_path)

    def parse_code(self, code: str, file_path: str = "<string>") -> ParsedModule:
        """Parse Rust source code"""

        # Remove comments for easier parsing
        code_no_comments = self._remove_comments(code)

        # Extract use statements (imports)
        imports = self._extract_uses(code_no_comments)

        # Extract structs
        classes = self._extract_structs(code, code_no_comments)

        # Extract enums
        classes.extend(self._extract_enums(code, code_no_comments))

        # Extract traits
        classes.extend(self._extract_traits(code, code_no_comments))

        # Extract functions
        functions = self._extract_functions(code, code_no_comments)

        # Extract global constants and statics
        global_variables = self._extract_globals(code_no_comments)

        # Extract module-level doc comment
        module_docstring = self._extract_module_comment(code)

        return ParsedModule(
            file_path=file_path,
            language='rust',
            module_docstring=module_docstring,
            imports=imports,
            functions=functions,
            classes=classes,
            global_variables=global_variables,
            parse_timestamp=datetime.now(timezone.utc).isoformat()
        )

    def _remove_comments(self, code: str) -> str:
        """Remove comments for easier parsing"""
        # Remove single-line comments
        code = re.sub(r'//[^\n]*', '', code)
        # Remove multi-line comments
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        return code

    def _extract_uses(self, code: str) -> List[str]:
        """Extract use statements"""
        imports = []

        # Pattern: use path::to::item;
        use_pattern = r'use\s+([^;]+);'

        for match in re.finditer(use_pattern, code):
            import_path = match.group(1).strip()
            # Handle use {...} patterns
            if '{' in import_path:
                # Extract base and items
                base_match = re.match(r'([^{]+)\{([^}]+)\}', import_path)
                if base_match:
                    base = base_match.group(1).strip()
                    items = base_match.group(2).split(',')
                    for item in items:
                        imports.append(f"{base}{item.strip()}")
            else:
                imports.append(import_path)

        return imports

    def _extract_structs(self, code: str, code_no_comments: str) -> List[ClassInfo]:
        """Extract struct declarations"""
        structs = []

        # Pattern: pub struct Name { ... } or struct Name { ... }
        struct_pattern = r'(?:pub\s+)?struct\s+(\w+)(?:<[^>]+>)?\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}'

        for match in re.finditer(struct_pattern, code_no_comments, re.DOTALL):
            name = match.group(1)
            body = match.group(2)
            line_number = code[:match.start()].count('\n') + 1

            # Extract fields
            attributes = self._parse_struct_fields(body)

            # Extract impl blocks for this struct
            methods = self._extract_impl_methods(code_no_comments, name)

            # Extract doc comment
            docstring = self._extract_doc_comment(code, line_number)

            # Extract derives (decorators)
            decorators = self._extract_derives(code, line_number)

            structs.append(ClassInfo(
                name=name + " (struct)",
                line_number=line_number,
                docstring=docstring,
                base_classes=[],  # Rust doesn't have inheritance
                methods=methods,
                attributes=attributes,
                decorators=decorators
            ))

        return structs

    def _extract_enums(self, code: str, code_no_comments: str) -> List[ClassInfo]:
        """Extract enum declarations"""
        enums = []

        # Pattern: pub enum Name { ... } or enum Name { ... }
        enum_pattern = r'(?:pub\s+)?enum\s+(\w+)(?:<[^>]+>)?\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}'

        for match in re.finditer(enum_pattern, code_no_comments, re.DOTALL):
            name = match.group(1)
            body = match.group(2)
            line_number = code[:match.start()].count('\n') + 1

            # Extract variants as attributes
            attributes = self._parse_enum_variants(body)

            # Extract impl blocks
            methods = self._extract_impl_methods(code_no_comments, name)

            # Extract doc comment
            docstring = self._extract_doc_comment(code, line_number)

            # Extract derives
            decorators = self._extract_derives(code, line_number)

            enums.append(ClassInfo(
                name=name + " (enum)",
                line_number=line_number,
                docstring=docstring,
                base_classes=[],
                methods=methods,
                attributes=attributes,
                decorators=decorators
            ))

        return enums

    def _extract_traits(self, code: str, code_no_comments: str) -> List[ClassInfo]:
        """Extract trait declarations"""
        traits = []

        # Pattern: pub trait Name { ... } or trait Name { ... }
        trait_pattern = r'(?:pub\s+)?trait\s+(\w+)(?:<[^>]+>)?\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}'

        for match in re.finditer(trait_pattern, code_no_comments, re.DOTALL):
            name = match.group(1)
            body = match.group(2)
            line_number = code[:match.start()].count('\n') + 1

            # Extract method signatures
            methods = self._parse_trait_methods(body, line_number)

            # Extract doc comment
            docstring = self._extract_doc_comment(code, line_number)

            traits.append(ClassInfo(
                name=name + " (trait)",
                line_number=line_number,
                docstring=docstring,
                base_classes=[],
                methods=methods,
                attributes=[],
                decorators=[]
            ))

        return traits

    def _extract_functions(self, code: str, code_no_comments: str) -> List[FunctionInfo]:
        """Extract function declarations (not in impl blocks)"""
        functions = []

        # Pattern: pub fn name(...) -> ReturnType { ... } or fn name(...) { ... }
        func_pattern = r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)(?:\s*->\s*([^{]+))?\s*\{'

        for match in re.finditer(func_pattern, code_no_comments):
            name = match.group(1)
            params_str = match.group(2)
            return_str = match.group(3)
            line_number = code[:match.start()].count('\n') + 1

            # Skip if this is inside an impl block
            if self._is_inside_impl(code_no_comments, match.start()):
                continue

            # Parse parameters
            parameters = self._parse_parameters(params_str)

            # Parse return type
            return_type = return_str.strip() if return_str else '()'

            # Check if async
            is_async = bool(re.search(r'async\s+fn\s+' + name, code))

            # Extract doc comment
            docstring = self._extract_doc_comment(code, line_number)

            functions.append(FunctionInfo(
                name=name,
                line_number=line_number,
                parameters=parameters,
                return_type=return_type,
                docstring=docstring,
                decorators=[],
                is_async=is_async,
                is_method=False
            ))

        return functions

    def _extract_impl_methods(self, code: str, type_name: str) -> List[FunctionInfo]:
        """Extract methods from impl blocks for a specific type"""
        methods = []

        # Pattern: impl TypeName { ... }
        impl_pattern = rf'impl(?:\s+<[^>]+>)?\s+{type_name}(?:\s+<[^>]+>)?\s*\{{([^}}]*(?:\{{[^}}]*\}}[^}}]*)*)\}}'

        for impl_match in re.finditer(impl_pattern, code, re.DOTALL):
            impl_body = impl_match.group(1)

            # Extract functions from impl block
            func_pattern = r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*(?:<[^>]+>)?\s*\(([^)]*)\)(?:\s*->\s*([^{]+))?\s*\{'

            for match in re.finditer(func_pattern, impl_body):
                name = match.group(1)
                params_str = match.group(2)
                return_str = match.group(3)

                # Calculate line number in original code
                offset = code.find(impl_body)
                line_number = code[:offset + match.start()].count('\n') + 1

                # Parse parameters
                parameters = self._parse_parameters(params_str)

                # Parse return type
                return_type = return_str.strip() if return_str else '()'

                # Check if async
                is_async = 'async' in match.group(0)

                methods.append(FunctionInfo(
                    name=name,
                    line_number=line_number,
                    parameters=parameters,
                    return_type=return_type,
                    docstring=None,
                    decorators=[],
                    is_async=is_async,
                    is_method=True
                ))

        return methods

    def _parse_struct_fields(self, body: str) -> List[dict]:
        """Parse struct field declarations"""
        attributes = []

        # Pattern: pub field_name: FieldType,
        field_pattern = r'(?:pub\s+)?(\w+)\s*:\s*([^,\n]+)'

        for match in re.finditer(field_pattern, body):
            name = match.group(1)
            field_type = match.group(2).strip().rstrip(',')

            attributes.append({
                'name': name,
                'type': field_type,
                'modifiers': []
            })

        return attributes

    def _parse_enum_variants(self, body: str) -> List[dict]:
        """Parse enum variant declarations"""
        variants = []

        # Pattern: VariantName or VariantName(...) or VariantName { ... }
        variant_pattern = r'(\w+)(?:\([^)]*\)|\{[^}]*\})?'

        for match in re.finditer(variant_pattern, body):
            name = match.group(1)

            variants.append({
                'name': name,
                'type': 'enum variant',
                'modifiers': []
            })

        return variants

    def _parse_trait_methods(self, body: str, base_line: int) -> List[FunctionInfo]:
        """Parse method signatures in trait"""
        methods = []

        # Pattern: fn method_name(...) -> ReturnType;
        method_pattern = r'fn\s+(\w+)\s*\(([^)]*)\)(?:\s*->\s*([^;{]+))?'

        for match in re.finditer(method_pattern, body):
            name = match.group(1)
            params_str = match.group(2)
            return_str = match.group(3)

            parameters = self._parse_parameters(params_str)
            return_type = return_str.strip() if return_str else '()'

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

        # Handle &self, &mut self, self
        if re.match(r'^\s*&?\s*(?:mut\s+)?self', params_str):
            params_str = re.sub(r'^\s*&?\s*(?:mut\s+)?self\s*,?\s*', '', params_str)

        # Split by comma
        param_parts = self._smart_split(params_str, ',')

        for part in param_parts:
            part = part.strip()
            if not part:
                continue

            # Pattern: name: type or mut name: type
            match = re.match(r'(?:mut\s+)?(\w+)\s*:\s*(.+)', part)
            if match:
                name = match.group(1)
                param_type = match.group(2).strip()

                parameters.append(ParameterInfo(
                    name=name,
                    type_hint=param_type,
                    default_value=None
                ))

        return parameters

    def _extract_globals(self, code: str) -> List[dict]:
        """Extract global constants and statics"""
        globals_list = []

        # Pattern: const NAME: Type = value;
        const_pattern = r'(?:pub\s+)?const\s+(\w+)\s*:\s*([^=]+)'
        for match in re.finditer(const_pattern, code):
            name = match.group(1)
            const_type = match.group(2).strip()
            line_number = code[:match.start()].count('\n') + 1

            globals_list.append({
                'name': name,
                'type': const_type,
                'line_number': line_number
            })

        # Pattern: static NAME: Type = value;
        static_pattern = r'(?:pub\s+)?static\s+(?:mut\s+)?(\w+)\s*:\s*([^=]+)'
        for match in re.finditer(static_pattern, code):
            name = match.group(1)
            static_type = match.group(2).strip()
            line_number = code[:match.start()].count('\n') + 1

            globals_list.append({
                'name': name,
                'type': static_type,
                'line_number': line_number
            })

        return globals_list

    def _extract_module_comment(self, code: str) -> Optional[str]:
        """Extract module-level doc comment"""
        # Look for //! at the start of the file
        lines = code.split('\n')
        doc_lines = []

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('//!'):
                doc_lines.append(stripped[3:].strip())
            elif stripped.startswith('/*!'):
                # Start of block doc comment
                doc_lines.append(stripped[3:].strip())
            elif stripped.endswith('*/') and doc_lines:
                doc_lines.append(stripped[:-2].strip())
                break
            elif doc_lines and stripped.startswith('*'):
                doc_lines.append(stripped[1:].strip())
            elif stripped and not stripped.startswith('//'):
                break

        return '\n'.join(doc_lines) if doc_lines else None

    def _extract_doc_comment(self, code: str, line_number: int) -> Optional[str]:
        """Extract doc comment before a declaration"""
        lines = code.split('\n')
        if line_number <= 0 or line_number > len(lines):
            return None

        comment_lines = []

        # Look backwards from the line before the declaration
        for i in range(line_number - 2, -1, -1):
            line = lines[i].strip()

            if line.startswith('///'):
                comment_lines.insert(0, line[3:].strip())
            elif line.startswith('/**'):
                comment_lines.insert(0, line[3:].strip())
            elif line.endswith('*/'):
                comment_lines.insert(0, line[:-2].strip())
            elif line and not line.startswith('//'):
                break

        return '\n'.join(comment_lines) if comment_lines else None

    def _extract_derives(self, code: str, line_number: int) -> List[str]:
        """Extract #[derive(...)] attributes"""
        derives = []
        lines = code.split('\n')

        if line_number <= 0 or line_number > len(lines):
            return derives

        # Look backwards for #[derive(...)]
        for i in range(line_number - 2, max(0, line_number - 10), -1):
            line = lines[i].strip()

            if line.startswith('#[derive('):
                # Extract derive items
                match = re.search(r'#\[derive\(([^)]+)\)', line)
                if match:
                    items = match.group(1).split(',')
                    derives.extend([f"#{item.strip()}" for item in items])

            if not line.startswith('#'):
                break

        return derives

    def _is_inside_impl(self, code: str, position: int) -> bool:
        """Check if position is inside an impl block"""
        # Count impl { and } before this position
        before = code[:position]
        impl_count = len(re.findall(r'\bimpl\b[^{]*\{', before))
        brace_count = before.count('{') - before.count('}')

        # If we're in an impl block, there should be unmatched impl
        return impl_count > 0 and brace_count > 0

    def _smart_split(self, text: str, delimiter: str) -> List[str]:
        """Split text by delimiter, respecting nested brackets"""
        parts = []
        current = []
        depth = 0

        for char in text:
            if char in '([{<':
                depth += 1
                current.append(char)
            elif char in ')]}>':
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
