"""Adding docstrings to source files: the result must still be valid code and must not hold filler text."""
import ast
import shutil
from pathlib import Path

import pytest

from src.formatters import DocstringFormatter
from src.formatters.base_formatter import FormatterError
from src.parsers.java_parser import JavaParser
from src.parsers.javascript_parser import JavaScriptParser
from src.parsers.python_parser import PythonParser

ROOT = Path(__file__).resolve().parents[1]
HAS_NODE = shutil.which('node') is not None and (ROOT / 'node_modules' / '@babel' / 'parser').exists()
SUMMARY = 'Does the thing.'


def explain_everything(module, described=()):
    """What the AI step does, with a fixed explanation; `described` names parameters that get a description."""
    def mark(func):
        func.ai_explanation = SUMMARY
        for p in func.parameters:
            if p.name in described:
                p.description = f'The {p.name} value.'
    for f in module.functions:
        mark(f)
    for c in module.classes:
        c.ai_explanation = SUMMARY
        for m in c.methods:
            mark(m)
    return module


def enhance(tmp_path, source, name='mod.py', parser=PythonParser, style='google', described=()):
    path = tmp_path / name
    path.write_text(source)
    module = explain_everything(parser().parse_file(str(path)), described)
    out = tmp_path / ('out_' + name)
    DocstringFormatter(style=style, create_backup=False).format(module, str(out))
    return out.read_text()


# ------------------------------------------------------------------ Python

def test_documents_functions_methods_and_classes_and_keeps_the_code(tmp_path):
    src = 'def f(x):\n    y = x * 2\n    return y\n\n\nclass K:\n    def m(self):\n        return 1\n'
    out = enhance(tmp_path, src)
    tree = ast.parse(out)
    assert ast.get_docstring(tree.body[0]) == SUMMARY
    assert ast.get_docstring(tree.body[1]) == SUMMARY
    assert ast.get_docstring(tree.body[1].body[1]) == SUMMARY          # body[0] is the class docstring
    assert 'y = x * 2\n    return y' in out


def test_existing_docstrings_are_left_alone(tmp_path):
    out = enhance(tmp_path, 'def f():\n    """Mine."""\n    return 1\n')
    assert ast.get_docstring(ast.parse(out).body[0]) == 'Mine.'
    assert SUMMARY not in out


def test_multi_line_signature_with_annotations_gets_the_docstring_after_the_whole_header(tmp_path):
    src = 'def f(\n    a: int,\n    b: str = "x",\n) -> dict:\n    return {a: b}\n'
    out = enhance(tmp_path, src)
    func = ast.parse(out).body[0]
    assert ast.get_docstring(func) == SUMMARY
    assert [a.arg for a in func.args.args] == ['a', 'b']


def test_one_line_definition_is_skipped_not_broken(tmp_path):
    src = 'def s(v): return v\n\n\ndef ok(v):\n    return v\n'
    out = enhance(tmp_path, src)
    tree = ast.parse(out)
    assert ast.get_docstring(tree.body[0]) is None
    assert ast.get_docstring(tree.body[1]) == SUMMARY
    assert 'def s(v): return v' in out


def test_body_that_starts_with_a_decorated_definition(tmp_path):
    src = 'def outer():\n    @staticmethod\n    def inner():\n        return 1\n    return inner\n'
    out = enhance(tmp_path, src)
    tree = ast.parse(out)
    assert ast.get_docstring(tree.body[0]) == SUMMARY
    inner = tree.body[0].body[1]                      # body[0] is outer's new docstring
    assert inner.name == 'inner' and inner.decorator_list      # nested functions are not documented, but stay intact


def test_comment_before_the_first_statement_stays_with_it(tmp_path):
    out = enhance(tmp_path, 'def f(x):\n    # note\n    return x\n')
    assert ast.get_docstring(ast.parse(out).body[0]) == SUMMARY
    assert out.index(SUMMARY) < out.index('# note') or out.index('# note') < out.index('return x')


def test_indentation_of_methods_and_tabs(tmp_path):
    out = enhance(tmp_path, 'class A:\n\tdef m(self):\n\t\treturn 1\n')
    assert '\t\t"""' in out
    ast.parse(out)


def test_async_functions_and_nested_classes(tmp_path):
    out = enhance(tmp_path, 'async def f():\n    return 1\n\n\nclass A:\n    class B:\n        def g(self):\n            return 1\n')
    tree = ast.parse(out)
    assert ast.get_docstring(tree.body[0]) == SUMMARY
    assert ast.get_docstring(tree.body[1]) == SUMMARY
    assert [type(n).__name__ for n in tree.body[1].body] == ['Expr', 'ClassDef']      # B is left as it was


def test_windows_line_endings_stay_consistent(tmp_path):
    path = tmp_path / 'crlf.py'
    path.write_bytes(b'def f(x):\r\n    return x\r\n')
    module = explain_everything(PythonParser().parse_file(str(path)))
    out = tmp_path / 'out.py'
    DocstringFormatter(create_backup=False).format(module, str(out))
    data = out.read_bytes()
    assert b'\n' not in data.replace(b'\r\n', b'')
    ast.parse(data.decode())


def test_explanation_with_quotes_and_backslashes_cannot_break_the_file(tmp_path):
    nasty = 'Splits on \\d+ and \\n """quoted""" text'
    path = tmp_path / 'm.py'
    path.write_text('def f(x):\n    return x\n')
    module = PythonParser().parse_file(str(path))
    module.functions[0].ai_explanation = nasty
    out = tmp_path / 'out.py'
    DocstringFormatter(create_backup=False).format(module, str(out))
    assert ast.get_docstring(ast.parse(out.read_text()).body[0], clean=False).strip() == nasty


def test_no_filler_text_when_nothing_is_known(tmp_path):
    out = enhance(tmp_path, 'class K:\n    attr = 1\n\n    def m(self, n) -> int:\n        return n\n')
    for filler in ('Parameter description', 'Attribute description', 'Return value description', 'Class description'):
        assert filler not in out
    assert 'Args:' not in out and 'Returns:' not in out and 'Attributes:' not in out


def test_only_described_parameters_are_listed_and_self_is_not(tmp_path):
    out = enhance(tmp_path, 'class K:\n    def m(self, n, m):\n        return n\n', described=('self', 'n'))
    doc = ast.get_docstring(ast.parse(out).body[0].body[1])
    assert 'n: The n value.' in doc
    assert 'self' not in doc and 'm:' not in doc


def test_numpy_style(tmp_path):
    out = enhance(tmp_path, 'def f(n: int):\n    return n\n', style='numpy', described=('n',))
    doc = ast.get_docstring(ast.parse(out).body[0])
    assert doc == f'{SUMMARY}\n\nParameters\n----------\nn : int\n    The n value.'
    assert '    The n value.\n    """' in out                   # no blank line before the closing quotes


def test_google_style_includes_the_type(tmp_path):
    out = enhance(tmp_path, 'def f(n: int):\n    return n\n', described=('n',))
    assert 'n (int): The n value.' in out


def test_backup_is_made_next_to_the_original_when_asked(tmp_path):
    path = tmp_path / 'm.py'
    path.write_text('def f():\n    return 1\n')
    module = explain_everything(PythonParser().parse_file(str(path)))
    DocstringFormatter(create_backup=True).format(module, str(tmp_path / 'out.py'))
    assert (tmp_path / 'm.py.backup').read_text() == 'def f():\n    return 1\n'
    assert path.read_text() == 'def f():\n    return 1\n'          # the original is never modified


def test_source_that_does_not_parse_is_refused(tmp_path):
    path = tmp_path / 'm.py'
    path.write_text('def f():\n    return 1\n')
    module = explain_everything(PythonParser().parse_file(str(path)))
    path.write_text('def f(:\n')
    with pytest.raises(FormatterError, match='does not parse'):
        DocstringFormatter(create_backup=False).format(module, str(tmp_path / 'out.py'))


def test_latin1_source_can_be_enhanced(tmp_path):
    path = tmp_path / 'l.py'
    path.write_bytes('# caf\xe9\ndef f():\n    return 1\n'.encode('cp1252'))
    module = explain_everything(PythonParser().parse_file(str(path)))
    out = tmp_path / 'out.py'
    DocstringFormatter(create_backup=False).format(module, str(out))
    assert SUMMARY in out.read_text()


# ------------------------------------------------------------------ JavaScript / TypeScript

@pytest.mark.skipif(not HAS_NODE, reason='Node.js or @babel/parser is not installed')
class TestJavaScript:
    def test_comment_goes_above_the_definition_and_its_decorators(self, tmp_path):
        src = '@Injectable()\nexport class Svc {\n  run(a) { return a; }\n}\n'
        out = enhance(tmp_path, src, 'svc.ts', JavaScriptParser, described=('a',))
        lines = out.split('\n')
        assert lines[0] == '/**'
        assert lines.index('@Injectable()') > lines.index(' */')
        assert '  /**' in lines and '   * @param a - The a value.' in lines

    def test_documented_functions_are_not_documented_twice(self, tmp_path):
        out = enhance(tmp_path, '/** Mine. */\nfunction f() {}\n', 'm.js', JavaScriptParser)
        assert out.count('/**') == 1 and SUMMARY not in out

    def test_documented_class_methods_are_not_documented_twice(self, tmp_path):
        src = 'class A {\n  /** Mine. */\n  run() {}\n  other() {}\n}\n'
        out = enhance(tmp_path, src, 'm.js', JavaScriptParser)
        assert out.count('Mine.') == 1 and out.count(SUMMARY) == 2      # class + other(); run keeps its own

    def test_decorated_methods_are_documented_above_the_decorator(self, tmp_path):
        src = 'class A {\n  @HostListener("x")\n  run() {}\n}\n'
        out = enhance(tmp_path, src, 'm.ts', JavaScriptParser)
        lines = [l.strip() for l in out.split('\n')]
        at = lines.index('@HostListener("x")')
        assert lines[at - 1] == '*/' and lines[at + 1] == 'run() {}'

    def test_no_filler_text(self, tmp_path):
        out = enhance(tmp_path, 'function f(a, b) { return a; }\n', 'm.js', JavaScriptParser, described=('a',))
        assert '@param a - The a value.' in out
        assert '@param' in out and 'b -' not in out and 'description' not in out

    def test_comment_cannot_be_ended_early(self, tmp_path):
        path = tmp_path / 'm.js'
        path.write_text('function f() {}\n')
        module = JavaScriptParser().parse_file(str(path))
        module.functions[0].ai_explanation = 'Matches */ end'
        out = tmp_path / 'out.js'
        DocstringFormatter(create_backup=False).format(module, str(out))
        assert out.read_text().count('*/') == 1


# ------------------------------------------------------------------ Java

class TestJava:
    def test_javadoc_goes_above_annotations(self, tmp_path):
        src = 'class A {\n    @Override\n    public String toString() { return ""; }\n}\n'
        out = enhance(tmp_path, src, 'A.java', JavaParser)
        lines = [l.strip() for l in out.split('\n')]
        at = lines.index('@Override')
        assert lines[at - 1] == '*/' and lines[at + 1] == 'public String toString() { return ""; }'

    def test_documented_methods_are_not_documented_twice(self, tmp_path):
        src = 'class A {\n    /** Mine. */\n    void f() {}\n}\n'
        out = enhance(tmp_path, src, 'A.java', JavaParser)
        assert out.count('Mine.') == 1 and out.count('/**') == 2      # the class gets one, f keeps its own
        assert SUMMARY in out

    def test_no_filler_text(self, tmp_path):
        src = 'class A {\n    int f(int a, int b) { return a; }\n}\n'
        out = enhance(tmp_path, src, 'A.java', JavaParser, described=('a',))
        assert '@param a The a value.' in out
        assert '@param b' not in out and '@return' not in out and 'description' not in out
