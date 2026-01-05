"""JavaScript/TypeScript code parser using esprima via Node.js"""
import subprocess
import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from .base_parser import BaseParser, ParseError
from .models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo


class JavaScriptParser(BaseParser):
    """
    Parser for JavaScript/TypeScript source code.

    Uses esprima (via Node.js) to parse JavaScript and extract code structure.
    Requires Node.js and esprima to be installed.
    """

    def __init__(self, node_path: str = 'node'):
        """
        Initialize JavaScript parser.

        Args:
            node_path: Path to Node.js executable (default: 'node')
        """
        self.node_path = node_path
        self.helper_script = Path(__file__).parent / 'js_parser_helper.js'
        self._nodejs_verified = False

    @property
    def supported_extensions(self) -> List[str]:
        return ['.js', '.jsx', '.mjs', '.ts', '.tsx']

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
                    raise ParseError(
                        error_data.get('error', 'Unknown parsing error'),
                        file_path=file_path,
                        line_number=error_data.get('line')
                    )
                except json.JSONDecodeError:
                    raise ParseError(
                        f"Failed to parse JavaScript: {result.stderr}",
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

        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
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
            for spec in imp.get('specifiers', []):
                if spec.get('isDefault'):
                    imports.append(f"import {spec['name']} from '{source}'")
                elif spec.get('isNamespace'):
                    imports.append(f"import * as {spec['alias']} from '{source}'")
                else:
                    name = spec['name']
                    alias = spec.get('alias')
                    if alias:
                        imports.append(f"import {{ {name} as {alias} }} from '{source}'")
                    else:
                        imports.append(f"import {{ {name} }} from '{source}'")

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
            language='javascript',
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
                type_hint=None,  # JS doesn't have native type hints (TS does, but we'd need TypeScript compiler)
                default_value=param.get('default_value'),
                description=None
            ))

        # Calculate complexity (simple heuristic)
        line_count = (func_data.get('end_line', 0) - func_data.get('line_number', 0))
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
            return_type=None,
            docstring=func_data.get('docstring'),
            decorators=[],  # JS doesn't have decorators (except in proposals/TS)
            body_summary=func_data.get('body_summary'),
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
                'type': None,
                'default_value': None,
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
            decorators=[]
        )
