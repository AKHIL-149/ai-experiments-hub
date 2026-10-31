"""Python parser: parameters, body previews, imports, attributes and encodings."""
import pytest

from src.parsers.base_parser import ParseError
from src.parsers.python_parser import PythonParser

parser = PythonParser()


def parse(code):
    return parser.parse_code(code)


def func(code, name=None):
    module = parse(code)
    functions = module.functions + [m for c in module.classes for m in c.methods]
    return next(f for f in functions if name is None or f.name == name)


def sig(f):
    """name, kind and default of every parameter, for compact assertions."""
    return [(p.name, p.kind, p.default_value) for p in f.parameters]


# ------------------------------------------------------------------ parameters

def test_all_parameter_kinds_in_order_with_the_right_defaults():
    f = func('def f(a, b=2, /, c=3, *args, d, e=5, **kw):\n    pass\n')
    assert sig(f) == [
        ('a', 'positional_only', None), ('b', 'positional_only', '2'),
        ('c', 'positional_or_keyword', '3'),
        ('*args', 'var_positional', None),
        ('d', 'keyword_only', None), ('e', 'keyword_only', '5'),
        ('**kw', 'var_keyword', None),
    ]


def test_keyword_only_parameters_after_a_bare_star_are_kept():
    f = func('def f(a, *, key=None, flag: bool = False):\n    pass\n')
    assert sig(f) == [('a', 'positional_or_keyword', None), ('key', 'keyword_only', 'None'), ('flag', 'keyword_only', 'False')]
    assert f.parameters[2].type_hint == 'bool'


def test_defaults_line_up_with_the_last_parameters():
    f = func('def f(a, b, c=1, d=2):\n    pass\n')
    assert [(p.name, p.default_value) for p in f.parameters] == [('a', None), ('b', None), ('c', '1'), ('d', '2')]


def test_falsy_defaults_are_not_mistaken_for_missing():
    f = func('def f(a=0, b="", c=None, d=False, e=[]):\n    pass\n')
    assert [p.default_value for p in f.parameters] == ['0', "''", 'None', 'False', '[]']


def test_type_hints_and_varargs_annotations():
    f = func('def f(x: int, *args: str, **kw: "dict[str, int]") -> None:\n    pass\n')
    assert [(p.name, p.type_hint) for p in f.parameters] == [('x', 'int'), ('*args', 'str'), ('**kw', "'dict[str, int]'")]
    assert f.return_type == 'None'


def test_methods_keep_self_and_flags():
    module = parse('class A:\n    @staticmethod\n    def s(x): return x\n    @classmethod\n    def c(cls): return cls\n    @property\n    def p(self): return 1\n    async def a(self): pass\n')
    methods = {m.name: m for m in module.classes[0].methods}
    assert methods['s'].is_static and methods['c'].is_classmethod and methods['a'].is_async
    assert methods['p'].decorators == ['property'] and all(m.is_method for m in methods.values())


# ------------------------------------------------------------------ body preview (what the AI is shown)

def test_a_body_without_a_docstring_keeps_its_first_line():
    assert func('async def sync(url: str, retries: int = 3) -> bool:\n    return True\n').body_summary == 'return True'


def test_one_line_docstring_is_skipped_and_the_code_after_it_shown():
    assert func('def f(x):\n    """Doc."""\n    y = x + 1\n    return y\n').body_summary == 'y = x + 1\nreturn y'


def test_multi_line_docstring_is_skipped():
    code = 'def f(x):\n    """Line one.\n\n    More text.\n    """\n    y = x + 1\n    return y\n'
    assert func(code).body_summary == 'y = x + 1\nreturn y'


def test_a_docstring_only_function_has_no_preview():
    assert func('def f():\n    """Just a doc."""\n').body_summary is None
    assert func('def f():\n    """Just a doc."""\n    """A second string statement."""\n').body_summary == '"""A second string statement."""'


def test_multi_line_signature_does_not_leak_into_the_preview():
    code = 'def f(\n    a,\n    b=2,\n):\n    total = a + b\n    return total\n'
    assert func(code).body_summary == 'total = a + b\nreturn total'


def test_preview_keeps_relative_indentation_and_is_limited_to_five_lines():
    code = 'def f(xs):\n    out = []\n    for x in xs:\n        if x:\n            out.append(x)\n    a = 1\n    b = 2\n    return out\n'
    assert func(code).body_summary == 'out = []\nfor x in xs:\n    if x:\n        out.append(x)\na = 1'


def test_preview_of_decorated_property_and_pass():
    module = parse('class A:\n    @property\n    def v(self):\n        return self._v\n    def n(self):\n        pass\n')
    assert [m.body_summary for m in module.classes[0].methods] == ['return self._v', 'pass']


def test_preview_with_tabs_and_windows_line_endings():
    assert func('def f():\r\n\treturn 1\r\n').body_summary == 'return 1'


def test_preview_of_nested_function_and_one_liners():
    assert func('def f(): return 1\n').body_summary == 'return 1'
    assert func('def outer():\n    def inner():\n        return 1\n    return inner\n', 'outer').body_summary == 'def inner():\n    return 1\nreturn inner'


# ------------------------------------------------------------------ imports

def test_relative_imports_keep_their_dots():
    module = parse('from . import x\nfrom .utils import helper\nfrom ..pkg.mod import Thing as T\nfrom ... import z\n')
    assert module.imports == ['from . import x', 'from .utils import helper', 'from ..pkg.mod import Thing as T', 'from ... import z']


def test_absolute_imports_and_aliases():
    module = parse('import os.path as osp\nimport sys, json\nfrom collections import OrderedDict as OD, deque\n')
    assert module.imports == ['import os.path as osp', 'import sys', 'import json', 'from collections import OrderedDict as OD', 'from collections import deque']


def test_imports_are_listed_in_source_order_including_nested_ones():
    module = parse('import a\n\ndef f():\n    import b\n\nimport c\n')
    assert module.imports == ['import a', 'import b', 'import c']


# ------------------------------------------------------------------ attributes

def test_instance_attributes_set_in_init_are_found():
    module = parse('class W:\n    kind = "wallet"\n    def __init__(self, owner: str, balance: float = 0.0):\n        self.owner = owner\n        self.balance: float = balance\n        self.owner = "again"\n        local = 1\n')
    attrs = {a['name']: a for a in module.classes[0].attributes}
    assert list(attrs) == ['kind', 'owner', 'balance']
    assert attrs['kind']['scope'] == 'class' and attrs['owner']['scope'] == 'instance'
    assert attrs['balance']['type'] == 'float' and attrs['owner']['default_value'] == 'owner'


def test_attributes_assigned_in_other_methods_are_not_guessed():
    module = parse('class A:\n    def setup(self):\n        self.late = 1\n')
    assert module.classes[0].attributes == []


def test_class_level_annotated_and_plain_attributes():
    module = parse('class A:\n    x: int = 1\n    y = "s"\n    z: str\n')
    assert [(a['name'], a['type'], a['default_value']) for a in module.classes[0].attributes] == [('x', 'int', '1'), ('y', None, "'s'"), ('z', 'str', None)]


# ------------------------------------------------------------------ module level

def test_empty_and_comment_only_files_parse_to_nothing():
    for code in ('', '# nothing here\n', '\n\n'):
        module = parse(code)
        assert (module.functions, module.classes, module.imports) == ([], [], [])


def test_docstrings_complexity_and_line_numbers():
    module = parse('"""Module doc."""\n\ndef simple():\n    """Hi."""\n    return 1\n\ndef big(x):\n' + ''.join(f'    if x == {i}:\n        x += 1\n' for i in range(8)) + '    return x\n')
    assert module.module_docstring == 'Module doc.'
    simple, big = module.functions
    assert (simple.line_number, simple.docstring, simple.complexity) == (3, 'Hi.', 'Simple')
    assert big.complexity in ('Medium', 'Complex') and big.line_number == 7


def test_global_variables():
    module = parse('MAX = 10\nNAME: str = "x"\n')
    assert [(v['name'], v['type'], v['value']) for v in module.global_variables] == [('MAX', None, '10'), ('NAME', 'str', "'x'")]


def test_unicode_identifiers():
    f = func('def größe(Ünit: str) -> int:\n    return 1\n')
    assert f.name == 'größe' and f.parameters[0].name == 'Ünit'


def test_match_statement_body_is_previewed():
    code = 'def f(cmd):\n    match cmd:\n        case "a":\n            return 1\n'
    assert func(code).body_summary.startswith('match cmd:')


# ------------------------------------------------------------------ errors and files

def test_a_syntax_error_says_what_and_where():
    with pytest.raises(ParseError) as error:
        parse('def f(:\n    pass\n')
    message = str(error.value)
    assert 'invalid syntax' in message.lower() and 'line 1' in message.lower()


def test_parse_file_does_not_wrap_a_syntax_error_in_a_misleading_read_error(tmp_path):
    bad = tmp_path / 'bad.py'
    bad.write_text('def f(:\n')
    with pytest.raises(ParseError) as error:
        parser.parse_file(str(bad))
    assert 'Failed to read file' not in str(error.value)
    assert str(error.value).count('Parse error') == 1


def test_missing_file_is_reported_as_missing():
    with pytest.raises(ParseError, match='File not found'):
        parser.parse_file('/nonexistent/dir/x.py')


def test_utf8_bom_is_accepted(tmp_path):
    f = tmp_path / 'bom.py'
    f.write_bytes('\ufeffdef f():\n    return 1\n'.encode('utf-8'))
    assert [x.name for x in parser.parse_file(str(f)).functions] == ['f']


def test_source_encoding_declared_in_a_comment_is_honoured(tmp_path):
    f = tmp_path / 'latin.py'
    f.write_bytes('# -*- coding: latin-1 -*-\ndef caf\xe9():\n    return "\xe9"\n'.encode('latin-1'))
    assert [x.name for x in parser.parse_file(str(f)).functions] == ['café']


def test_undeclared_non_utf8_bytes_fall_back_to_windows_1252_instead_of_failing(tmp_path):
    f = tmp_path / 'cp.py'
    f.write_bytes(b'def f():\n    """Costs 5 \x80 (euro in Windows-1252), caf\xe9."""\n    return 1\n')
    module = parser.parse_file(str(f))
    assert [x.name for x in module.functions] == ['f']
    assert module.functions[0].docstring == 'Costs 5 \u20ac (euro in Windows-1252), caf\u00e9.'


def test_bytes_that_are_not_even_windows_1252_still_parse_as_latin_1(tmp_path):
    f = tmp_path / 'odd.py'
    f.write_bytes(b'def f():\n    """Undefined in cp1252: \x81\x8d."""\n    return 1\n')
    assert parser.parse_file(str(f)).functions[0].docstring == 'Undefined in cp1252: \x81\x8d.'


def test_a_binary_file_is_rejected_clearly(tmp_path):
    f = tmp_path / 'bin.py'
    f.write_bytes(b'\x00\x01\x02\xff\xfe' * 10)
    with pytest.raises(ParseError) as error:
        parser.parse_file(str(f))
    assert 'binary file' in str(error.value).lower()


def test_attributes_set_inside_nested_functions_or_lambdas_of_init_are_not_the_classs_attributes():
    code = ('class A:\n    def __init__(self):\n        self.real = 1\n        def later():\n            self.hidden = 2\n'
            '        callback = lambda: setattr(self, "x", 1)\n        class Inner:\n            def m(inner):\n                self.deep = 3\n')
    assert [a['name'] for a in parse(code).classes[0].attributes] == ['real']


def test_tuple_and_chained_assignments_in_init():
    module = parse('class A:\n    def __init__(self):\n        self.a, self.b = 1, 2\n        self.c = self.d = 0\n')
    attrs = {a['name']: a['default_value'] for a in module.classes[0].attributes}
    assert attrs == {'a': None, 'b': None, 'c': None, 'd': None}   # no value guessed when it cannot be read off directly


def test_uppercase_extensions_are_still_python():
    assert parser.can_parse('SCRIPT.PY') and parser.can_parse('x.Pyw') and not parser.can_parse('x.pyc')


# ------------------------------------------------------------------ facts the AI should not have to guess

def used(code, name=None):
    return {p.name: p.used for p in func(code, name).parameters}


def test_unused_parameters_are_detected():
    assert used('async def sync(url: str, retries: int = 3) -> bool:\n    return True\n') == {'url': False, 'retries': False}
    assert used('def f(a, b):\n    return a\n') == {'a': True, 'b': False}


def test_parameters_used_anywhere_in_the_body_count_as_used():
    code = ('def f(a, b, c, d, e):\n    x = [a for _ in range(1)]\n    if b:\n        pass\n'
            '    def inner():\n        return c\n    d += 1\n    print(f"{e}")\n')
    assert used(code) == {'a': True, 'b': True, 'c': True, 'd': True, 'e': True}


def test_star_parameters_use_their_bare_names():
    assert used('def f(*args, **kw):\n    return args, kw\n') == {'*args': True, '**kw': True}
    assert used('def f(*args, **kw):\n    return 1\n') == {'*args': False, '**kw': False}


def test_self_and_cls_are_not_reported():
    module = parse('class A:\n    def m(self, x):\n        return 1\n    @classmethod\n    def c(cls, y):\n        return 1\n')
    assert [(p.name, p.used) for p in module.classes[0].methods[0].parameters] == [('self', None), ('x', False)]
    assert [(p.name, p.used) for p in module.classes[0].methods[1].parameters] == [('cls', None), ('y', False)]


def test_dynamic_access_means_nothing_can_be_called_unused():
    assert used('def f(a, b):\n    return locals()\n') == {'a': True, 'b': True}
    assert used('def f(a, b):\n    return eval("a")\n') == {'a': True, 'b': True}


def test_a_stub_body_leaves_every_parameter_unused():
    assert used('def f(a, b):\n    pass\n') == {'a': False, 'b': False}
    assert used('def f(a):\n    """Doc."""\n') == {'a': False}
    assert used('def f(a):\n    raise NotImplementedError\n') == {'a': False}


def test_body_line_count_tells_whether_the_preview_is_complete():
    assert func('def f():\n    return 1\n').body_lines == 1
    assert func('def f(x):\n    """Doc."""\n    a = 1\n\n    b = 2\n    return a + b\n').body_lines == 3
    assert func('def f():\n    """Only a docstring."""\n').body_lines == 0
    long = 'def f():\n' + ''.join(f'    x{i} = {i}\n' for i in range(9))
    assert func(long).body_lines == 9 and len(func(long).body_summary.split('\n')) == 5
