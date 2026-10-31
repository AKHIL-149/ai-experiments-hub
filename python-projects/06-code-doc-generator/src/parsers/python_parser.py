"""Python code parser using AST module"""
import ast
import re
import textwrap
from typing import Iterator, List, Optional, Union
from datetime import datetime

from .base_parser import BaseParser, ParseError, read_source_text
from .models import ParsedModule, FunctionInfo, ClassInfo, ParameterInfo


class PythonParser(BaseParser):
    """Parser for Python source code using the built-in ast module"""

    @property
    def supported_extensions(self) -> List[str]:
        return ['.py', '.pyw']

    def parse_file(self, file_path: str) -> ParsedModule:
        """Parse a Python file"""
        try:
            code = read_source_text(file_path)
        except FileNotFoundError:
            raise ParseError(f"File not found: {file_path}", file_path=file_path)
        except ParseError as error:
            raise ParseError(error.message, file_path=file_path)
        except OSError as error:
            raise ParseError(f"Cannot read file: {error.strerror or error}", file_path=file_path)
        return self.parse_code(code, file_path)

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
        """Extract import statements, in source order (relative imports keep their dots)"""
        nodes = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        nodes.sort(key=lambda n: (n.lineno, n.col_offset))

        imports = []
        for node in nodes:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(f"import {alias.name} as {alias.asname}" if alias.asname else f"import {alias.name}")
            else:
                module = "." * node.level + (node.module or "")
                for alias in node.names:
                    imports.append(
                        f"from {module} import {alias.name} as {alias.asname}" if alias.asname
                        else f"from {module} import {alias.name}"
                    )
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

        body_summary = self._body_preview(node, source_code)
        self._mark_used_parameters(node, parameters)

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
            body_lines=self._body_line_count(node, source_code),
            complexity=complexity,
            is_async=isinstance(node, ast.AsyncFunctionDef),
            is_method=is_method,
            is_static=is_static,
            is_classmethod=is_classmethod
        )

    def _body_preview(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef], source_code: str) -> Optional[str]:
        """The first few lines of what the function does (after its docstring), with indentation kept.

        This is what the AI is shown, so it starts at the first real statement: a body without a
        docstring must not lose its first line, and a multi-line signature must not leak in.
        """
        body = list(node.body)
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], 'value', None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            body = body[1:]  # the docstring
        if not body:
            return None

        if body[0].lineno == node.lineno:
            # "def f(): return 1": the body shares a line with the header, so take the statement itself
            lines = (ast.get_source_segment(source_code, body[0]) or '').split('\n')
            picked = [line.rstrip() for line in lines if line.strip()][:5]
        else:
            lines = re.split(r'\r\n|\r|\n', source_code)  # the same line breaks Python itself uses
            end = node.end_lineno or body[-1].lineno
            picked = [line.rstrip() for line in lines[body[0].lineno - 1:end] if line.strip()][:5]
        return textwrap.dedent('\n'.join(picked)) or None

    @staticmethod
    def _real_body(node: Union[ast.FunctionDef, ast.AsyncFunctionDef]) -> list:
        """The statements of a function without its docstring."""
        body = list(node.body)
        if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], 'value', None), ast.Constant) \
                and isinstance(body[0].value.value, str):
            body = body[1:]
        return body

    def _body_line_count(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef], source_code: str) -> int:
        """Non-blank source lines of the body, docstring excluded."""
        body = self._real_body(node)
        if not body:
            return 0
        if body[0].lineno == node.lineno:
            return len([l for l in (ast.get_source_segment(source_code, body[0]) or '').split('\n') if l.strip()])
        lines = re.split(r'\r\n|\r|\n', source_code)
        return len([l for l in lines[body[0].lineno - 1:node.end_lineno or body[-1].lineno] if l.strip()])

    def _mark_used_parameters(self, node: Union[ast.FunctionDef, ast.AsyncFunctionDef], parameters: List[ParameterInfo]) -> None:
        """Set ParameterInfo.used: False for a parameter the body never mentions."""
        names = set()
        dynamic = False
        for statement in self._real_body(node):
            for child in ast.walk(statement):
                if isinstance(child, ast.Name):
                    names.add(child.id)
                    if child.id in ('locals', 'vars', 'eval', 'exec', 'globals'):
                        dynamic = True  # the body can read any parameter by name
        for index, param in enumerate(parameters):
            bare = param.name.lstrip('*')
            if index == 0 and bare in ('self', 'cls'):
                param.used = None                  # the instance or class: never worth reporting
            else:
                param.used = True if dynamic else bare in names

    def _extract_parameters(self, args: ast.arguments) -> List[ParameterInfo]:
        """Extract every parameter: positional-only, regular, *args, keyword-only and **kwargs"""

        def make(arg: ast.arg, default, kind: str, prefix: str = "") -> ParameterInfo:
            return ParameterInfo(
                name=f"{prefix}{arg.arg}",
                type_hint=ast.unparse(arg.annotation) if arg.annotation else None,
                default_value=ast.unparse(default) if default is not None else None,
                kind=kind,
            )

        parameters: List[ParameterInfo] = []

        # Defaults belong to the *last* positional parameters, positional-only ones included
        positional = list(args.posonlyargs) + list(args.args)
        defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
        for index, (arg, default) in enumerate(zip(positional, defaults)):
            kind = 'positional_only' if index < len(args.posonlyargs) else 'positional_or_keyword'
            parameters.append(make(arg, default, kind))

        if args.vararg:
            parameters.append(make(args.vararg, None, 'var_positional', prefix="*"))

        # kw_defaults has one entry per keyword-only parameter, None where there is no default
        for arg, default in zip(args.kwonlyargs, args.kw_defaults):
            parameters.append(make(arg, default, 'keyword_only'))

        if args.kwarg:
            parameters.append(make(args.kwarg, None, 'var_keyword', prefix="**"))

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

        # Class attributes: assignments directly in the class body
        attributes = []
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.AnnAssign) and isinstance(child.target, ast.Name):
                attributes.append({
                    'name': child.target.id,
                    'type': ast.unparse(child.annotation) if child.annotation else None,
                    'default_value': ast.unparse(child.value) if child.value else None,
                    'line_number': child.lineno,
                    'scope': 'class'
                })
            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        attributes.append({
                            'name': target.id,
                            'type': None,
                            'default_value': ast.unparse(child.value),
                            'line_number': child.lineno,
                            'scope': 'class'
                        })

        # Instance attributes: "self.x = ..." in __init__ (the only place they are reliably declared)
        attributes.extend(self._instance_attributes(node))

        return ClassInfo(
            name=node.name,
            line_number=node.lineno,
            docstring=docstring,
            base_classes=base_classes,
            methods=methods,
            attributes=attributes,
            decorators=decorators
        )

    @staticmethod
    def _walk_without_nested_definitions(node: ast.AST) -> Iterator[ast.AST]:
        """Every node under `node`, skipping the insides of nested functions and classes."""
        for child in ast.iter_child_nodes(node):
            yield child
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                yield from PythonParser._walk_without_nested_definitions(child)

    def _instance_attributes(self, class_node: ast.ClassDef) -> List[dict]:
        """Attributes assigned as ``self.name = ...`` in ``__init__`` (first assignment of each name)."""
        init = next((c for c in class_node.body
                     if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef)) and c.name == '__init__'), None)
        if init is None or not init.args.args:
            return []
        self_name = init.args.args[0].arg

        def is_self_attr(target) -> bool:
            return (isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                    and target.value.id == self_name)

        found = {}
        for node in self._walk_without_nested_definitions(init):
            entries = []
            if isinstance(node, ast.AnnAssign) and is_self_attr(node.target):
                entries.append((node.target.attr, ast.unparse(node.annotation), ast.unparse(node.value) if node.value else None))
            elif isinstance(node, ast.Assign):
                targets = []
                for target in node.targets:
                    targets.extend(target.elts if isinstance(target, (ast.Tuple, ast.List)) else [target])
                single = len(node.targets) == 1 and not isinstance(node.targets[0], (ast.Tuple, ast.List))
                for target in targets:
                    if is_self_attr(target):
                        entries.append((target.attr, None, ast.unparse(node.value) if single else None))
            for name, type_hint, value in entries:
                found.setdefault(name, {
                    'name': name, 'type': type_hint, 'default_value': value,
                    'line_number': node.lineno, 'scope': 'instance'
                })
        return list(found.values())

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
