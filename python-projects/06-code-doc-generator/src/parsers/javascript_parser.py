"""JavaScript/TypeScript code parser using the Babel parser via Node.js"""
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

from .base_parser import BaseParser, ParseError
from .models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo


class JavaScriptParser(BaseParser):
    """
    Parser for JavaScript/TypeScript source code.

    Uses @babel/parser (via Node.js) to parse JavaScript, JSX and TypeScript and extract code structure.
    Requires Node.js and `npm install` in the project folder.
    """

    def __init__(self, node_path: Optional[str] = None):
        """
        Initialize JavaScript parser.

        Args:
            node_path: Path to Node.js executable (default: $NODEJS_PATH or 'node')
        """
        if node_path is None:
            # Lazy import: src.core imports the parsers, so a top-level import would be circular
            from ..core import settings
            node_path = settings.nodejs_path()
        self.node_path = node_path
        self.helper_script = Path(__file__).parent / 'js_parser_helper.js'
        self._nodejs_verified = False

    @property
    def supported_extensions(self) -> List[str]:
        return ['.js', '.jsx', '.mjs', '.cjs', '.ts', '.tsx', '.mts', '.cts']

    def _verify_nodejs(self):
        """Verify Node.js is installed and accessible"""
        try:
            result = subprocess.run(
                [self.node_path, '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                raise RuntimeError("Node.js not found or not working")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            raise RuntimeError(
                f"Node.js is required for JavaScript parsing. "
                f"Please install Node.js: https://nodejs.org/\n"
                f"Error: {str(e)}"
            )

    def parse_file(self, file_path: str) -> ParsedModule:
        """Parse a JavaScript/TypeScript file"""
        # Verify Node.js is available (lazy check)
        if not self._nodejs_verified:
            self._verify_nodejs()
            self._nodejs_verified = True

        if not Path(file_path).exists():
            raise ParseError(f"File not found: {file_path}", file_path=file_path)

        try:
            # Call Node.js helper script
            result = subprocess.run(
                [self.node_path, str(self.helper_script), file_path],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                # Parse error from stderr
                try:
                    error_data = json.loads(result.stderr)
                    if "@babel/parser" in str(error_data.get('error', '')):
                        raise ParseError(
                            "JavaScript parsing needs the @babel/parser package. "
                            f"Run `npm install` in {Path(__file__).resolve().parents[2]}",
                            file_path=file_path
                        )
                    raise ParseError(
                        error_data.get('error', 'Unknown parsing error'),
                        file_path=file_path,
                        line_number=error_data.get('line')
                    )
                except json.JSONDecodeError:
                    if "@babel/parser" in result.stderr and "Cannot find module" in result.stderr:
                        raise ParseError(
                            "JavaScript parsing needs the @babel/parser package. "
                            f"Run `npm install` in {Path(__file__).resolve().parents[2]}",
                            file_path=file_path
                        )
                    raise ParseError(
                        f"Failed to parse JavaScript: {result.stderr.strip()[-500:]}",
                        file_path=file_path
                    )

            # Parse JSON output
            try:
                data = json.loads(result.stdout)
            except json.JSONDecodeError as e:
                raise ParseError(
                    f"Failed to parse JavaScript parser output: {str(e)}",
                    file_path=file_path
                )

            # Convert to ParsedModule
            return self._convert_to_parsed_module(data, file_path)

        except subprocess.TimeoutExpired:
            raise ParseError(
                "JavaScript parsing timed out (> 30 seconds)",
                file_path=file_path
            )
        except Exception as e:
            if isinstance(e, ParseError):
                raise
            raise ParseError(f"Failed to parse JavaScript file: {str(e)}", file_path=file_path)

    def parse_code(self, code: str, file_path: str = "<string>") -> ParsedModule:
        """Parse JavaScript/TypeScript code string"""
        # Create temporary file
        import tempfile

        # the extension picks the dialect (.ts for TypeScript, .jsx/.tsx for JSX)
        suffix = Path(file_path).suffix.lower()
        if suffix not in self.supported_extensions:
            suffix = '.js'
        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name

        try:
            result = self.parse_file(temp_path)
            result.file_path = file_path  # Update to original path
            return result
        finally:
            # Clean up temp file
            Path(temp_path).unlink(missing_ok=True)

    def _convert_to_parsed_module(self, data: Dict[str, Any], file_path: str) -> ParsedModule:
        """Convert JSON data from Node.js to ParsedModule"""

        # Extract imports
        imports = []
        for imp in data.get('imports', []):
            source = imp['source']
            keyword = 'import type' if imp.get('type_only') else 'import'
            if not imp.get('specifiers'):
                imports.append(f"import '{source}'")          # side-effect import
            for spec in imp.get('specifiers', []):
                if spec.get('isDefault'):
                    imports.append(f"{keyword} {spec['name']} from '{source}'")
                elif spec.get('isNamespace'):
                    imports.append(f"{keyword} * as {spec['alias']} from '{source}'")
                else:
                    name = spec['name']
                    alias = spec.get('alias')
                    if alias:
                        imports.append(f"{keyword} {{ {name} as {alias} }} from '{source}'")
                    else:
                        imports.append(f"{keyword} {{ {name} }} from '{source}'")

        # Convert functions
        functions = []
        for func_data in data.get('functions', []):
            if not func_data.get('is_method', False):
                functions.append(self._convert_function(func_data))

        # Convert classes
        classes = []
        for class_data in data.get('classes', []):
            classes.append(self._convert_class(class_data))

        # Convert global variables
        variables = []
        for var_data in data.get('variables', []):
            variables.append({
                'name': var_data['name'],
                'type': var_data.get('kind'),  # const, let, var
                'value': '<initialized>' if var_data.get('has_init') else '<uninitialized>',
                'line_number': var_data.get('line_number')
            })

        return ParsedModule(
            file_path=file_path,
            language=data.get('language', 'javascript'),
            module_docstring=None,  # JS doesn't have module-level docstrings
            imports=imports,
            functions=functions,
            classes=classes,
            global_variables=variables,
            parse_timestamp=datetime.now().isoformat()
        )

    def _convert_function(self, func_data: Dict[str, Any]) -> FunctionInfo:
        """Convert function data to FunctionInfo"""
        # Convert parameters
        parameters = []
        for param in func_data.get('parameters', []):
            parameters.append(ParameterInfo(
                name=param['name'],
                type_hint=param.get('type'),
                default_value=param.get('default_value'),
                description=None,
                kind='var_positional' if param.get('is_rest') else 'positional_or_keyword'
            ))

        # Calculate complexity (simple heuristic)
        line_count = (func_data.get('end_line') or 0) - (func_data.get('line_number') or 0)
        if line_count <= 10:
            complexity = 'Simple'
        elif line_count <= 30:
            complexity = 'Medium'
        else:
            complexity = 'Complex'

        return FunctionInfo(
            name=func_data['name'],
            line_number=func_data.get('line_number', 0),
            parameters=parameters,
            return_type=func_data.get('return_type'),
            docstring=func_data.get('docstring'),
            decorators=list(func_data.get('decorators', [])),
            body_summary=func_data.get('body_summary'),
            body_lines=func_data.get('body_lines'),
            complexity=complexity,
            is_async=func_data.get('is_async', False),
            is_method=func_data.get('is_method', False),
            is_static=func_data.get('is_static', False),
            is_classmethod=False  # Not applicable in JS
        )

    def _convert_class(self, class_data: Dict[str, Any]) -> ClassInfo:
        """Convert class data to ClassInfo"""
        # Convert methods
        methods = []
        for method_data in class_data.get('methods', []):
            method = self._convert_function(method_data)
            method.is_method = True

            # Set special method types
            if method_data.get('kind') == 'constructor':
                method.name = 'constructor'
            elif method_data.get('kind') == 'get':
                method.decorators.append('@getter')
            elif method_data.get('kind') == 'set':
                method.decorators.append('@setter')

            method.is_static = method_data.get('is_static', False)
            methods.append(method)

        # Convert properties
        attributes = []
        for prop_data in class_data.get('properties', []):
            attributes.append({
                'name': prop_data['name'],
                'type': prop_data.get('type'),
                'default_value': prop_data.get('default_value'),
                'line_number': prop_data.get('line_number'),
                'is_static': prop_data.get('is_static', False)
            })

        return ClassInfo(
            name=class_data['name'],
            line_number=class_data.get('line_number', 0),
            docstring=class_data.get('docstring'),
            base_classes=class_data.get('base_classes', []),
            methods=methods,
            attributes=attributes,
            decorators=list(class_data.get('decorators', []))
        )
