"""Python code parser using AST module"""
import ast
from pathlib import Path
from typing import List, Optional, Union
from datetime import datetime

from .base_parser import BaseParser, ParseError
from .models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo


class PythonParser(BaseParser):
    """Parser for Python source code using the built-in ast module"""

    @property
    def supported_extensions(self) -> List[str]:
        return ['.py', '.pyw']

    def parse_file(self, file_path: str) -> ParsedModule:
        """Parse a Python file"""
        try:
            code = Path(file_path).read_text(encoding='utf-8')
            return self.parse_code(code, file_path)
        except FileNotFoundError:
            raise ParseError(f"File not found: {file_path}", file_path=file_path)
        except Exception as e:
            raise ParseError(f"Failed to read file: {str(e)}", file_path=file_path)

    def parse_code(self, code: str, file_path: str = "<string>") -> ParsedModule:
        """Parse Python code string"""
        try:
            tree = ast.parse(code, filename=file_path)
        except SyntaxError as e:
            raise ParseError(
                f"Syntax error: {e.msg}",
                file_path=file_path,
                line_number=e.lineno
            )
        except Exception as e:
            raise ParseError(f"Failed to parse code: {str(e)}", file_path=file_path)

        # Extract module-level docstring
        module_docstring = ast.get_docstring(tree)

        # Extract imports
        imports = self._extract_imports(tree)

        # Extract functions (module-level only)
        functions = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(self._extract_function(node, code))

        # Extract classes
        classes = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                classes.append(self._extract_class(node, code))

        # Extract global variables
        global_variables = self._extract_global_variables(tree)

        return ParsedModule(
            file_path=file_path,
            language='python',
            module_docstring=module_docstring,
            imports=imports,
            functions=functions,
            classes=classes,
            global_variables=global_variables,
            parse_timestamp=datetime.now().isoformat()
        )

    def _extract_imports(self, tree: ast.AST) -> List[str]:
        """Extract import statements"""
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.asname:
                        imports.append(f"import {alias.name} as {alias.asname}")
                    else:
                        imports.append(f"import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ''
                for alias in node.names:
                    if alias.asname:
                        imports.append(f"from {module} import {alias.name} as {alias.asname}")
                    else:
                        imports.append(f"from {module} import {alias.name}")
        return imports

    def _extract_function(
        self,
        node: Union[ast.FunctionDef, ast.AsyncFunctionDef],
        source_code: str,
        is_method: bool = False
    ) -> FunctionInfo:
        """Extract function information from AST node"""
        # Get docstring
        docstring = ast.get_docstring(node)

        # Extract parameters
        parameters = self._extract_parameters(node.args)

        # Extract return type
        return_type = None
        if node.returns:
            return_type = ast.unparse(node.returns)

        # Extract decorators
        decorators = [ast.unparse(dec) for dec in node.decorator_list]

        # Determine if static/classmethod
        is_static = '@staticmethod' in decorators or 'staticmethod' in decorators
        is_classmethod = '@classmethod' in decorators or 'classmethod' in decorators

        # Get body summary (first 5 lines of function body)
        body_lines = source_code.split('\n')[node.lineno:node.end_lineno]
        # Skip the function definition line and docstring
        body_start = 1
        if docstring:
            # Skip docstring lines
            for i, line in enumerate(body_lines[1:], 1):
                if '"""' in line or "'''" in line:
                    body_start = i + 1
                    break
        body_summary_lines = [line.strip() for line in body_lines[body_start:body_start+5] if line.strip()]
        body_summary = '\n'.join(body_summary_lines) if body_summary_lines else None

        # Calculate complexity (simple heuristic)
        complexity = self._calculate_complexity(node)

        return FunctionInfo(
            name=node.name,
            line_number=node.lineno,
            parameters=parameters,
            return_type=return_type,
            docstring=docstring,
            decorators=decorators,
            body_summary=body_summary,
            complexity=complexity,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_method=is_method,
            is_static=is_static,
            is_classmethod=is_classmethod
        )

    def _extract_parameters(self, args: ast.arguments) -> List[ParameterInfo]:
        """Extract function parameters"""
        parameters = []

        # Regular args
        all_args = args.args
        defaults = [None] * (len(all_args) - len(args.defaults)) + list(args.defaults)

        for arg, default in zip(all_args, defaults):
            param_name = arg.arg
            type_hint = ast.unparse(arg.annotation) if arg.annotation else None
            default_value = ast.unparse(default) if default else None

            parameters.append(ParameterInfo(
                name=param_name,
                type_hint=type_hint,
                default_value=default_value
            ))

        # *args
        if args.vararg:
            type_hint = ast.unparse(args.vararg.annotation) if args.vararg.annotation else None
            parameters.append(ParameterInfo(
                name=f"*{args.vararg.arg}",
                type_hint=type_hint
            ))

        # **kwargs
        if args.kwarg:
            type_hint = ast.unparse(args.kwarg.annotation) if args.kwarg.annotation else None
            parameters.append(ParameterInfo(
                name=f"**{args.kwarg.arg}",
                type_hint=type_hint
            ))

        return parameters

    def _extract_class(self, node: ast.ClassDef, source_code: str) -> ClassInfo:
        """Extract class information from AST node"""
        # Get docstring
        docstring = ast.get_docstring(node)

        # Extract base classes
        base_classes = [ast.unparse(base) for base in node.bases]

        # Extract decorators
        decorators = [ast.unparse(dec) for dec in node.decorator_list]

        # Extract methods
        methods = []
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods.append(self._extract_function(child, source_code, is_method=True))

        # Extract class attributes (assignments at class level)
        attributes = []
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                attr_type = ast.unparse(child.annotation) if child.annotation else None
                attr_value = ast.unparse(child.value) if child.value else None
                attributes.append({
                    'name': child.target.id,
                    'type': attr_type,
                    'default_value': attr_value,
                    'line_number': child.lineno
                })
            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        attributes.append({
                            'name': target.id,
                            'type': None,
                            'default_value': ast.unparse(child.value),
                            'line_number': child.lineno
                        })

        return ClassInfo(
            name=node.name,
            line_number=node.lineno,
            docstring=docstring,
            base_classes=base_classes,
            methods=methods,
            attributes=attributes,
            decorators=decorators
        )

    def _extract_global_variables(self, tree: ast.AST) -> List[dict]:
        """Extract module-level variable assignments"""
        variables = []

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                var_type = ast.unparse(node.annotation) if node.annotation else None
                var_value = ast.unparse(node.value) if node.value else None
                variables.append({
                    'name': node.target.id,
                    'type': var_type,
                    'value': var_value,
                    'line_number': node.lineno
                })
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        variables.append({
                            'name': target.id,
                            'type': None,
                            'value': ast.unparse(node.value),
                            'line_number': node.lineno
                        })

        return variables

    def _calculate_complexity(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> str:
        """
        Calculate function complexity using simple heuristics.

        Returns:
            'Simple', 'Medium', or 'Complex'
        """
        # Count lines
        line_count = (node.end_lineno or node.lineno) - node.lineno

        # Count control flow statements
        control_flow_count = sum(
            1 for _ in ast.walk(node)
            if isinstance(_, (ast.If, ast.For, ast.While, ast.Try, ast.With))
        )

        # Simple heuristic
        if line_count <= 10 and control_flow_count <= 2:
            return 'Simple'
        elif line_count <= 30 and control_flow_count <= 5:
            return 'Medium'
        else:
            return 'Complex'
