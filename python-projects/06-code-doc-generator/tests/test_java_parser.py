"""Java parsing (javalang: understands Java up to version 8)."""
import pytest

from src.parsers.base_parser import ParseError
from src.parsers.java_parser import JavaParser

SAMPLE = '''package a.b;
import java.util.List;
import static java.lang.Math.max;
/** A calculator. */
public class Calc<T> extends Base implements Runnable {
    private static final int MAX = 10;
    public Calc(int x) {
        this.x = x;
    }
    /**
     * Twice.
     * @param x the number
     */
    @Override
    public int twice(int x) throws Exception {
        if (x > 1) { return "}".length(); } // a } in a comment
        return x * 2;
    }
    public <U> List<U> wrap(U u, String... more) { return null; }
    public static class Inner { void f() {} enum Deep { Q } }
    enum Mode { A(1), B(2); private final int v; Mode(int v) { this.v = v; } int v() { return v; } }
}
interface Shape { double PI = 3.14; double area(); default String name() { return "s"; } static void make() {} }
'''


def parse(code=SAMPLE, name='Calc.java'):
    return JavaParser().parse_code(code, name)


def by_name(module):
    return {c.name: c for c in module.classes}


def methods(cls):
    return {m.name: m for m in cls.methods}


def test_classes_interfaces_enums_and_nested_types_are_all_found_with_qualified_names():
    assert sorted(by_name(parse())) == ['Calc', 'Calc.Inner', 'Calc.Inner.Deep', 'Calc.Mode', 'Shape']


def test_class_header():
    calc = by_name(parse())['Calc']
    assert calc.base_classes == ['Base', 'Runnable']
    assert calc.docstring == 'A calculator.'
    assert [a['name'] for a in calc.attributes] == ['MAX']


def test_constructor_is_named_like_its_class():
    calc = by_name(parse())['Calc']
    ctor = methods(calc)['Calc']
    assert '@constructor' in ctor.decorators
    assert [(p.name, p.type_hint) for p in ctor.parameters] == [('x', 'int')]
    assert '<init>' not in methods(calc)


def test_method_details():
    twice = methods(by_name(parse())['Calc'])['twice']
    assert twice.return_type == 'int'
    assert twice.decorators[:2] == ['@public', '@Override']
    assert twice.docstring == 'Twice.\n@param x the number'


def test_generic_method_and_varargs():
    wrap = methods(by_name(parse())['Calc'])['wrap']
    assert wrap.return_type == 'List<U>'
    assert [p.name for p in wrap.parameters] == ['u', 'more']


def test_method_body_is_read_even_with_braces_in_strings_and_comments():
    twice = methods(by_name(parse())['Calc'])['twice']
    assert twice.body_lines == 2
    assert twice.body_summary == 'if (x > 1) { return "}".length(); } // a } in a comment\nreturn x * 2;'


def test_body_of_constructor_and_empty_method():
    calc = by_name(parse())['Calc']
    assert methods(calc)['Calc'].body_summary == 'this.x = x;'
    inner = methods(by_name(parse())['Calc.Inner'])['f']
    assert (inner.body_summary, inner.body_lines) == (None, 0)


def test_abstract_and_interface_methods_have_no_body():
    shape = methods(by_name(parse())['Shape'])
    assert shape['area'].body_lines == 0 and '@abstract' in shape['area'].decorators


def test_default_and_static_interface_methods_are_not_abstract():
    shape = methods(by_name(parse())['Shape'])
    assert '@abstract' not in shape['name'].decorators and shape['name'].body_summary == 'return "s";'
    assert '@abstract' not in shape['make'].decorators


def test_interface_constants():
    assert [a['name'] for a in by_name(parse())['Shape'].attributes] == ['PI']


def test_enum_members_constructors_and_methods():
    mode = by_name(parse())['Calc.Mode']
    assert [a['name'] for a in mode.attributes] == ['A', 'B', 'v']
    assert sorted(methods(mode)) == ['Mode', 'v']
    assert mode.decorators == ['@enum']


def test_imports_including_static():
    assert parse().imports == ['import java.util.List', 'import static java.lang.Math.max']


def test_javadoc_delimiters_are_removed_and_tags_kept():
    m = parse('/** Calc.\n * Second line.\n */\nclass A {\n /** One liner. */\n void f() {}\n /**\n  * @return x\n  */\n int g(){return 1;}\n}\n')
    assert by_name(m)['A'].docstring == 'Calc.\nSecond line.'
    assert [x.docstring for x in by_name(m)['A'].methods] == ['One liner.', '@return x']


def test_class_javadoc_is_not_repeated_as_the_module_docstring():
    assert parse('/** The class. */\npublic class A {}\n').module_docstring is None


def test_file_comment_before_package_is_the_module_docstring():
    m = parse('/** About this file. */\npackage a;\npublic class A {}\n')
    assert m.module_docstring == 'About this file.'


# ------------------------------------------------------------------ errors

@pytest.mark.parametrize('code,label', [
    ('record Point(int x, int y) {}', 'records'),
    ('public sealed interface S permits A, B {}', 'sealed types'),
    ('class A { String s = """\n hi\n """; }', 'text blocks'),
    ('class A { int f(int x) { return switch (x) { case 1 -> 1; default -> 2; }; } }', 'switch expressions'),
])
def test_newer_java_syntax_is_named_in_the_error(code, label):
    with pytest.raises(ParseError) as error:
        parse(code)
    assert label in error.value.message and 'Java 8' in error.value.message
    assert '\n' not in error.value.message


def test_plain_syntax_error_has_a_reason_and_a_line():
    with pytest.raises(ParseError) as error:
        parse('class A {\n  int x = ;\n}\n')
    assert error.value.message.startswith('Java syntax error: Expected expression')
    assert error.value.line_number == 2
    assert 'newer Java' not in error.value.message


def test_file_errors_are_not_wrapped_twice(tmp_path):
    bad = tmp_path / 'Bad.java'
    bad.write_text('class A { int x = ; }')
    with pytest.raises(ParseError) as error:
        JavaParser().parse_file(str(bad))
    assert 'Failed to read file' not in error.value.message


def test_missing_file():
    with pytest.raises(ParseError, match='not found'):
        JavaParser().parse_file('/no/such/File.java')


def test_latin1_file_is_read(tmp_path):
    path = tmp_path / 'L.java'
    path.write_bytes('class L { String s = "caf\xe9"; }\n'.encode('cp1252'))
    assert [c.name for c in JavaParser().parse_file(str(path)).classes] == ['L']


def test_binary_file_is_refused(tmp_path):
    path = tmp_path / 'B.java'
    path.write_bytes(b'\x00\x01class A {}')
    with pytest.raises(ParseError) as error:
        JavaParser().parse_file(str(path))
    assert 'binary' in error.value.message


def test_braces_inside_block_comments_do_not_end_the_body():
    m = parse('class A {\n  int f() {\n    /* } { */\n    return 1;\n  }\n  int g() { return 2; }\n}\n')
    f = methods(by_name(m)['A'])['f']
    assert f.body_lines == 2 and f.body_summary.endswith('return 1;')


def test_complexity_follows_body_length():
    def lines(n):
        return ''.join(f'    int v{i} = {i};\n' for i in range(n))
    m = parse('class A {\n  void big() {\n' + lines(40) + '  }\n  void mid() {\n' + lines(15) + '  }\n  void tiny() {}\n}\n')
    got = {name: x.complexity for name, x in methods(by_name(m)['A']).items()}
    assert got['big'] == 'Complex' and got['mid'] == 'Medium' and got['tiny'] == 'Simple'


def test_enum_implements_interfaces():
    m = parse('enum E implements Runnable, Comparable<E> { A; public void run() {} }')
    assert by_name(m)['E'].base_classes == ['Runnable', 'Comparable']


@pytest.mark.parametrize('count,label', [(10, 'Simple'), (11, 'Medium'), (30, 'Medium'), (31, 'Complex')])
def test_complexity_boundaries(count, label):
    body = ''.join(f'    int v{i} = {i};\n' for i in range(count))
    m = parse('class A {\n  void f() {\n' + body + '  }\n}\n')
    assert methods(by_name(m)['A'])['f'].complexity == label
