"""
JavaScript/TypeScript Parser
Parses JavaScript and TypeScript files using esprima
"""

import re
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

try:
    import esprima
    from esprima import nodes
    ESPRIMA_AVAILABLE = True
except ImportError:
    ESPRIMA_AVAILABLE = False
    print("Warning: esprima not installed. JavaScript parsing will use fallback mode.")

from .base_parser import BaseParser, ParseError
from .models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo


class JavaScriptParser(BaseParser):
    """
    Parser for JavaScript and TypeScript files.

    Supports:
    - ES6+ syntax (arrow functions, classes, modules)
    - JSX (React)
    - TypeScript (basic support with type stripping)
    - Async/await
    - Decorators
    """

    @property
    def supported_extensions(self) -> List[str]:
        """Supported file extensions"""
        return ['.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs']

    def parse_file(self, file_path: str) -> ParsedModule:
        """Parse a JavaScript/TypeScript file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            return self.parse_code(code, file_path)
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found: {file_path}")
        except Exception as e:
            raise ParseError(f"Failed to read file: {str(e)}", file_path)

    def parse_code(self, code: str, file_path: str = "<string>") -> ParsedModule:
        """Parse JavaScript/TypeScript code"""

        # Determine language
        language = self._detect_language(file_path, code)

        # Preprocess TypeScript to remove type annotations
        if language in ['typescript', 'tsx']:
            code = self._strip_typescript_types(code)

        if ESPRIMA_AVAILABLE:
            try:
                return self._parse_with_esprima(code, file_path, language)
            except Exception as e:
                # Fallback to regex parsing
                print(f"Esprima parsing failed: {e}. Using fallback parser.")
                return self._parse_with_regex(code, file_path, language)
        else:
            return self._parse_with_regex(code, file_path, language)

    def _detect_language(self, file_path: str, code: str) -> str:
        """Detect specific JavaScript variant"""
        if file_path.endswith('.ts'):
            return 'typescript'
        elif file_path.endswith('.tsx'):
            return 'tsx'
        elif file_path.endswith('.jsx'):
            return 'jsx'
        elif 'export type' in code or 'interface ' in code:
            return 'typescript'
        elif '</' in code and 'React' in code:
            return 'jsx'
        else:
            return 'javascript'

    def _strip_typescript_types(self, code: str) -> str:
        """
        Remove TypeScript type annotations for basic parsing.
        This is a simplified approach - for production, use a proper TS parser.
        """
        # Remove type annotations from function parameters
        code = re.sub(r':\s*\w+(\[\])?(\s*\||\&\s*\w+)*(?=[,\)])', '', code)

        # Remove return type annotations
        code = re.sub(r'\):\s*\w+(\[\])?(\s*\||\&\s*\w+)*\s*{', ') {', code)

        # Remove interface and type declarations
        code = re.sub(r'interface\s+\w+\s*{[^}]*}', '', code)
        code = re.sub(r'type\s+\w+\s*=\s*[^;]+;', '', code)

        # Remove generic type parameters
        code = re.sub(r'<[^>]+>(?=\s*\()', '', code)

        # Remove as casts
        code = re.sub(r'\s+as\s+\w+', '', code)

        return code

    def _parse_with_esprima(self, code: str, file_path: str, language: str) -> ParsedModule:
        """Parse using esprima library"""
        try:
            # Parse with esprima (supports ES6+, JSX with jsx=True option)
            jsx_mode = language in ['jsx', 'tsx']
            tree = esprima.parseModule(code, options={'jsx': jsx_mode, 'loc': True, 'comment': True})
        except Exception as e:
            raise ParseError(f"Esprima parse error: {str(e)}", file_path)

        # Extract module docstring (first comment)
        module_docstring = None
        if hasattr(tree, 'comments') and tree.comments:
            first_comment = tree.comments[0]
            if first_comment.value:
                module_docstring = first_comment.value.strip()

        # Extract imports
        imports = self._extract_imports(tree)

        # Extract functions and classes
        functions = []
        classes = []
        global_variables = []

        for node in tree.body:
            if isinstance(node, nodes.FunctionDeclaration):
                functions.append(self._parse_function(node))
            elif isinstance(node, nodes.ClassDeclaration):
                classes.append(self._parse_class(node))
            elif isinstance(node, nodes.VariableDeclaration):
                global_variables.extend(self._parse_variable_declaration(node))
            elif isinstance(node, nodes.ExportNamedDeclaration):
                # Handle exported functions/classes
                if isinstance(node.declaration, nodes.FunctionDeclaration):
                    functions.append(self._parse_function(node.declaration))
                elif isinstance(node.declaration, nodes.ClassDeclaration):
                    classes.append(self._parse_class(node.declaration))
            elif isinstance(node, nodes.ExportDefaultDeclaration):
                # Handle default exports
                if isinstance(node.declaration, nodes.FunctionDeclaration):
                    functions.append(self._parse_function(node.declaration))
                elif isinstance(node.declaration, nodes.ClassDeclaration):
                    classes.append(self._parse_class(node.declaration))

        return ParsedModule(
            file_path=file_path,
            language=language,
            module_docstring=module_docstring,
            imports=imports,
            functions=functions,
            classes=classes,
            global_variables=global_variables,
            parse_timestamp=datetime.now(timezone.utc).isoformat()
        )

    def _extract_imports(self, tree) -> List[str]:
        """Extract import statements"""
        imports = []

        for node in tree.body:
            if isinstance(node, nodes.ImportDeclaration):
                # ES6 import
                source = node.source.value if hasattr(node.source, 'value') else str(node.source)
                imports.append(f"import from '{source}'")
            elif isinstance(node, nodes.VariableDeclaration):
                # CommonJS require()
                for declarator in node.declarations:
                    if (hasattr(declarator, 'init') and
                        isinstance(declarator.init, nodes.CallExpression) and
                        hasattr(declarator.init.callee, 'name') and
                        declarator.init.callee.name == 'require'):
                        if declarator.init.arguments:
                            arg = declarator.init.arguments[0]
                            if hasattr(arg, 'value'):
                                imports.append(f"require('{arg.value}')")

        return imports

    def _parse_function(self, node) -> FunctionInfo:
        """Parse a function declaration or expression"""
        name = node.id.name if hasattr(node, 'id') and node.id else '<anonymous>'
        line_number = node.loc.start.line if hasattr(node, 'loc') else 0

        # Extract parameters
        parameters = []
        if hasattr(node, 'params'):
            for param in node.params:
                param_name = self._get_param_name(param)
                parameters.append(ParameterInfo(
                    name=param_name,
                    type_hint=None,  # TypeScript types already stripped
                    default_value=None
                ))

        # Check if async
        is_async = getattr(node, 'async', False)

        # Check for decorators (experimental JavaScript feature)
        decorators = []
        if hasattr(node, 'decorators'):
            for decorator in node.decorators:
                if hasattr(decorator, 'expression'):
                    decorators.append(self._node_to_string(decorator.expression))

        return FunctionInfo(
            name=name,
            line_number=line_number,
            parameters=parameters,
            return_type=None,
            docstring=None,  # Could extract JSDoc comments
            decorators=decorators,
            is_async=is_async,
            is_method=False
        )

    def _parse_class(self, node) -> ClassInfo:
        """Parse a class declaration"""
        name = node.id.name if hasattr(node, 'id') and node.id else '<anonymous>'
        line_number = node.loc.start.line if hasattr(node, 'loc') else 0

        # Extract base classes
        base_classes = []
        if hasattr(node, 'superClass') and node.superClass:
            base_name = node.superClass.name if hasattr(node.superClass, 'name') else str(node.superClass)
            base_classes.append(base_name)

        # Extract methods
        methods = []
        attributes = []

        if hasattr(node, 'body') and hasattr(node.body, 'body'):
            for member in node.body.body:
                if isinstance(member, nodes.MethodDefinition):
                    method = self._parse_method(member)
                    methods.append(method)
                elif isinstance(member, nodes.PropertyDefinition):
                    # Class property
                    prop_name = member.key.name if hasattr(member.key, 'name') else str(member.key)
                    attributes.append({
                        'name': prop_name,
                        'type': None,
                        'default': None
                    })

        # Check for decorators
        decorators = []
        if hasattr(node, 'decorators'):
            for decorator in node.decorators:
                if hasattr(decorator, 'expression'):
                    decorators.append(self._node_to_string(decorator.expression))

        return ClassInfo(
            name=name,
            line_number=line_number,
            docstring=None,
            base_classes=base_classes,
            methods=methods,
            attributes=attributes,
            decorators=decorators
        )

    def _parse_method(self, node) -> FunctionInfo:
        """Parse a class method"""
        name = node.key.name if hasattr(node.key, 'name') else '<anonymous>'
        line_number = node.loc.start.line if hasattr(node, 'loc') else 0

        # Extract parameters
        parameters = []
        if hasattr(node.value, 'params'):
            for param in node.value.params:
                param_name = self._get_param_name(param)
                parameters.append(ParameterInfo(name=param_name))

        # Check method type
        is_static = node.static if hasattr(node, 'static') else False
        is_async = getattr(node.value, 'async', False) if hasattr(node, 'value') else False

        return FunctionInfo(
            name=name,
            line_number=line_number,
            parameters=parameters,
            is_async=is_async,
            is_method=True,
            is_static=is_static
        )

    def _parse_variable_declaration(self, node) -> List[Dict[str, Any]]:
        """Parse variable declarations"""
        variables = []

        for declarator in node.declarations:
            if hasattr(declarator, 'id'):
                var_name = declarator.id.name if hasattr(declarator.id, 'name') else str(declarator.id)
                variables.append({
                    'name': var_name,
                    'type': node.kind if hasattr(node, 'kind') else 'var',  # const, let, var
                    'line_number': node.loc.start.line if hasattr(node, 'loc') else 0
                })

        return variables

    def _get_param_name(self, param) -> str:
        """Extract parameter name from various param node types"""
        if hasattr(param, 'name'):
            return param.name
        elif hasattr(param, 'left') and hasattr(param.left, 'name'):
            # Default parameter
            return param.left.name
        elif hasattr(param, 'argument') and hasattr(param.argument, 'name'):
            # Rest parameter
            return '...' + param.argument.name
        else:
            return '<param>'

    def _node_to_string(self, node) -> str:
        """Convert AST node to string representation"""
        if hasattr(node, 'name'):
            return node.name
        elif hasattr(node, 'value'):
            return str(node.value)
        else:
            return str(node)

    def _parse_with_regex(self, code: str, file_path: str, language: str) -> ParsedModule:
        """
        Fallback regex-based parser for basic structure extraction.
        Not as accurate as AST parsing but works without dependencies.
        """

        # Extract imports
        imports = []
        # ES6 imports
        for match in re.finditer(r"import\s+.*\s+from\s+['\"]([^'\"]+)['\"]", code):
            imports.append(f"import from '{match.group(1)}'")
        # CommonJS requires
        for match in re.finditer(r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", code):
            imports.append(f"require('{match.group(1)}')")

        # Extract functions
        functions = []
        # Function declarations
        for match in re.finditer(
            r'(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)',
            code
        ):
            func_name = match.group(1)
            params_str = match.group(2)
            line_number = code[:match.start()].count('\n') + 1

            # Parse parameters
            parameters = []
            if params_str.strip():
                for param in params_str.split(','):
                    param = param.strip().split('=')[0].strip()  # Remove default values
                    if param:
                        parameters.append(ParameterInfo(name=param))

            functions.append(FunctionInfo(
                name=func_name,
                line_number=line_number,
                parameters=parameters,
                is_async='async' in match.group(0)
            ))

        # Arrow functions assigned to variables/constants
        for match in re.finditer(
            r'(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>',
            code
        ):
            func_name = match.group(1)
            line_number = code[:match.start()].count('\n') + 1

            functions.append(FunctionInfo(
                name=func_name,
                line_number=line_number,
                parameters=[],
                is_async='async' in match.group(0)
            ))

        # Extract classes
        classes = []
        for match in re.finditer(r'class\s+(\w+)(?:\s+extends\s+(\w+))?\s*{', code):
            class_name = match.group(1)
            base_class = match.group(2)
            line_number = code[:match.start()].count('\n') + 1

            base_classes = [base_class] if base_class else []

            classes.append(ClassInfo(
                name=class_name,
                line_number=line_number,
                base_classes=base_classes,
                methods=[],  # Would need more complex parsing
                attributes=[]
            ))

        # Extract global variables
        global_variables = []
        for match in re.finditer(r'(?:const|let|var)\s+(\w+)\s*=', code):
            var_name = match.group(1)
            line_number = code[:match.start()].count('\n') + 1

            global_variables.append({
                'name': var_name,
                'type': 'const/let/var',
                'line_number': line_number
            })

        return ParsedModule(
            file_path=file_path,
            language=language,
            module_docstring=None,
            imports=imports,
            functions=functions,
            classes=classes,
            global_variables=global_variables,
            parse_timestamp=datetime.now(timezone.utc).isoformat()
        )
