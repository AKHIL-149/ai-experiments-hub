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

from .base_parser import BaseParser, ParseError
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
            code = Path(file_path).read_text(encoding='utf-8')
            return self.parse_code(code, file_path)
        except FileNotFoundError:
            raise ParseError(f"File not found: {file_path}", file_path=file_path)
        except Exception as e:
            raise ParseError(f"Failed to read file: {str(e)}", file_path=file_path)

    def parse_code(self, code: str, file_path: str = "<string>") -> ParsedModule:
        """Parse Java code string"""
        try:
            tree = javalang.parse.parse(code)
        except javalang.parser.JavaSyntaxError as e:
            raise ParseError(
                f"Java syntax error: {str(e)}",
                file_path=file_path,
                line_number=getattr(e, 'line', None)
            )
        except Exception as e:
            raise ParseError(f"Failed to parse Java code: {str(e)}", file_path=file_path)

        # Extract package and imports
        package_name = tree.package.name if tree.package else None
        imports = self._extract_imports(tree)

        # Extract classes (Java requires everything in classes)
        classes = []
        functions = []  # Top-level functions don't exist in Java, but we'll check anyway

        for path, node in tree.filter(javalang.tree.ClassDeclaration):
            classes.append(self._extract_class(node, code))

        for path, node in tree.filter(javalang.tree.InterfaceDeclaration):
            # Treat interfaces similar to classes
            classes.append(self._extract_interface(node, code))

        for path, node in tree.filter(javalang.tree.EnumDeclaration):
            # Treat enums as classes
            classes.append(self._extract_enum(node, code))

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
        """Extract file-level Javadoc comment if present"""
        lines = code.strip().split('\n')

        # Look for /** */ comment at the beginning
        in_comment = False
        comment_lines = []

        for line in lines:
            stripped = line.strip()

            if stripped.startswith('/**'):
                in_comment = True
                comment_lines.append(stripped[3:].strip())
            elif in_comment:
                if stripped.endswith('*/'):
                    comment_lines.append(stripped[:-2].strip())
                    break
                else:
                    # Remove leading * if present
                    if stripped.startswith('*'):
                        comment_lines.append(stripped[1:].strip())
                    else:
                        comment_lines.append(stripped)
            elif stripped and not stripped.startswith('//'):
                # Hit non-comment code
                break

        if comment_lines:
            return '\n'.join(line for line in comment_lines if line).strip()
        return None

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
            methods.append(self._extract_constructor(constructor, code))

        # Extract fields (attributes)
        attributes = []
        for field in node.fields or []:
            attributes.extend(self._extract_field(field))

        # Extract modifiers
        modifiers = node.modifiers or []
        decorators = [f"@{mod}" for mod in modifiers if mod not in ['public', 'private', 'protected']]

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
            method_info.decorators.append('@abstract')
            methods.append(method_info)

        return ClassInfo(
            name=node.name,
            line_number=getattr(node.position, 'line', 0) if hasattr(node, 'position') else 0,
            docstring=docstring,
            base_classes=base_classes,
            methods=methods,
            attributes=[],
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

        return ClassInfo(
            name=node.name,
            line_number=getattr(node.position, 'line', 0) if hasattr(node, 'position') else 0,
            docstring=docstring,
            base_classes=[],
            methods=[],
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

        return FunctionInfo(
            name=node.name,
            line_number=getattr(node.position, 'line', 0) if hasattr(node, 'position') else 0,
            parameters=parameters,
            return_type=return_type,
            docstring=docstring,
            decorators=decorators,
            body_summary=None,
            complexity='Medium',  # Default complexity for Java methods
            is_async=False,  # Java doesn't have async/await
            is_method=True,
            is_static=is_static,
            is_classmethod=False
        )

    def _extract_constructor(self, node: Any, code: str) -> FunctionInfo:
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

        return FunctionInfo(
            name='<init>',  # Constructor name
            line_number=getattr(node.position, 'line', 0) if hasattr(node, 'position') else 0,
            parameters=parameters,
            return_type=None,  # Constructors don't have return types
            docstring=docstring,
            decorators=decorators,
            body_summary=None,
            complexity='Medium',
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
        """Clean Javadoc comment"""
        lines = javadoc.split('\n')
        cleaned = []

        for line in lines:
            # Remove leading/trailing whitespace and asterisks
            line = line.strip()
            if line.startswith('*'):
                line = line[1:].strip()

            # Skip @param, @return, etc. tags for now (could parse separately)
            if line.startswith('@'):
                continue

            if line:
                cleaned.append(line)

        return '\n'.join(cleaned).strip()
