"""JavaScript / TypeScript parsing (needs Node.js and `npm install`; skipped without them)."""
import shutil
import subprocess
from pathlib import Path

import pytest

from src.parsers.base_parser import ParseError
from src.parsers.javascript_parser import JavaScriptParser

ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    shutil.which('node') is None or not (ROOT / 'node_modules' / '@babel' / 'parser').exists(),
    reason='Node.js or @babel/parser is not installed',
)


def parse(code, name='mod.js'):
    return JavaScriptParser().parse_code(code, name)


def fn(module, name):
    return next(f for f in module.functions if f.name == name)


def cls(module, name):
    return next(c for c in module.classes if c.name == name)


# ------------------------------------------------------------------ modern JavaScript

def test_class_fields_private_members_and_static():
    m = parse('class A {\n  static count = 0;\n  #secret = 1;\n  name = "x";\n  #hidden() {}\n  static make() {}\n}\n')
    a = cls(m, 'A')
    assert [(x['name'], x['default_value'], x['is_static']) for x in a.attributes] == \
        [('count', '0', True), ('#secret', '1', False), ('name', '"x"', False)]
    assert [(x.name, x.is_static) for x in a.methods] == [('#hidden', False), ('make', True)]


def test_arrow_functions_and_function_expressions_assigned_to_names_are_functions():
    m = parse('const mul = (x, y) => x * y;\nlet div = function (a, b) { return a / b; };\nconst n = 5;\n')
    assert [f.name for f in m.functions] == ['mul', 'div']
    assert [v['name'] for v in m.global_variables] == ['n']


def test_export_forms_keep_functions_and_their_comments():
    m = parse('/** Adds. */\nexport async function add(a, b = 2, ...rest) { return a + b; }\n'
              'export default class Shape {}\nexport const sub = (a) => a;\n')
    add = fn(m, 'add')
    assert add.is_async and add.docstring == 'Adds.'
    assert [(p.name, p.default_value, p.kind) for p in add.parameters] == \
        [('a', None, 'positional_or_keyword'), ('b', '2', 'positional_or_keyword'), ('...rest', None, 'var_positional')]
    assert [c.name for c in m.classes] == ['Shape']
    assert 'sub' in [f.name for f in m.functions]


def test_anonymous_default_export_is_named_default():
    m = parse('export default function () { return 1; }\n')
    assert [f.name for f in m.functions] == ['default']


def test_commonjs_exports():
    m = parse('exports.helper = function (v) { return v; };\nmodule.exports.other = () => 1;\n'
              'module.exports = class Thing {};\n')
    assert sorted(f.name for f in m.functions) == ['helper', 'other']
    assert [c.name for c in m.classes] == ['Thing']


def test_destructured_and_default_parameters_are_shown_as_written():
    m = parse('function f({ a, b }, [c, d], e = { x: 1 }, f = compute(2)) {}\n')
    assert [(p.name, p.default_value) for p in fn(m, 'f').parameters] == \
        [('{ a, b }', None), ('[c, d]', None), ('e', '{ x: 1 }'), ('f', 'compute(2)')]


def test_modern_syntax_does_not_break_parsing():
    m = parse('const a = x?.y ?? z;\nconst v = await Promise.resolve(1);\nfunction* g() { yield 1; }\n')
    assert [f.name for f in m.functions] == ['g']


def test_jsx():
    m = parse('export const App = () => <div>hi</div>;\n', 'app.jsx')
    assert [f.name for f in m.functions] == ['App']


def test_getters_setters_constructor_and_async_generators():
    m = parse('class A {\n  constructor(n) { this.n = n; }\n  get size() { return 1; }\n  set size(v) {}\n'
              '  async *items() { yield 1; }\n}\n')
    methods = cls(m, 'A').methods
    assert [(x.name, x.decorators, x.is_async) for x in methods] == [
        ('constructor', [], False), ('size', ['@getter'], False), ('size', ['@setter'], False), ('items', [], True)]
    assert methods[0].parameters[0].name == 'n'


def test_imports_are_listed_in_source_order():
    m = parse("import fs, { readFile as rf } from 'fs';\nimport * as path from 'path';\nimport './side-effect';\n")
    assert m.imports == ["import fs from 'fs'", "import { readFile as rf } from 'fs'",
                         "import * as path from 'path'", "import './side-effect'"]


# ------------------------------------------------------------------ documentation comments

def test_only_a_comment_right_above_counts_as_documentation():
    m = parse('/** Far away. */\n\nfunction a() {}\n\n/* plain */\nfunction b() {}\n\n// one\n// two\nfunction c() {}\n')
    assert fn(m, 'a').docstring is None          # blank line between
    assert fn(m, 'b').docstring is None          # not a /** block
    assert fn(m, 'c').docstring == 'one\ntwo'


def test_jsdoc_tags_are_kept_and_stars_removed():
    m = parse('/**\n * Adds two numbers.\n *\n * @param {number} a first\n * @returns {number} sum\n */\nfunction add(a) {}\n')
    assert fn(m, 'add').docstring == 'Adds two numbers.\n\n@param {number} a first\n@returns {number} sum'


# ------------------------------------------------------------------ body for the AI prompt

def test_body_preview_is_dedented_and_counted():
    m = parse('function f(a) {\n    const x = a;\n    if (x) {\n        return 1;\n    }\n    return 2;\n    // end\n}\n')
    f = fn(m, 'f')
    assert f.body_lines == 6
    assert f.body_summary.split('\n')[:2] == ['const x = a;', 'if (x) {']
    assert len(f.body_summary.split('\n')) == 5


def test_empty_and_one_line_bodies():
    m = parse('function e() {}\nfunction one() { return 1; }\nconst arrow = (a) => a * 2;\n')
    assert (fn(m, 'e').body_lines, fn(m, 'e').body_summary) == (0, None)
    assert (fn(m, 'one').body_lines, fn(m, 'one').body_summary) == (1, 'return 1;')
    assert (fn(m, 'arrow').body_lines, fn(m, 'arrow').body_summary) == (1, 'a * 2')


# ------------------------------------------------------------------ TypeScript

TS = '''import type { A } from './a';
interface User { name: string; age?: number; greet(g: string): void }
/** Greets. */
export function greet(u: User, greeting: string = 'hi', ...more: string[]): string { return greeting; }
@Injectable()
abstract class Svc<T> extends Base<T> implements IRun {
  private x: number = 1;
  constructor(private repo: T, public name?: string) { super(); }
  protected async load<K>(id: K): Promise<T | null> { return null; }
  abstract nothing(): void;
}
enum Color { Red, Green = 'g' }
type Id = string | number;
declare function over(a: string): void;
declare function over(a: number): void;
function over(a: any) {}
'''


def test_typescript_is_parsed_and_reported_as_typescript():
    m = parse(TS, 'mod.ts')
    assert m.language == 'typescript'
    assert m.imports == ["import type { A } from './a'"]


def test_typescript_types_on_parameters_and_returns():
    greet = fn(parse(TS, 'mod.ts'), 'greet')
    assert [(p.name, p.type_hint, p.default_value) for p in greet.parameters] == \
        [('u', 'User', None), ('greeting', 'string', "'hi'"), ('...more', 'string[]', None)]
    assert greet.return_type == 'string'
    assert greet.docstring == 'Greets.'


def test_typescript_class_members():
    svc = cls(parse(TS, 'mod.ts'), 'Svc')
    assert svc.base_classes == ['Base', 'implements IRun']
    assert svc.decorators == ['@Injectable()']
    methods = {m.name: m for m in svc.methods}
    assert [(p.name, p.type_hint) for p in methods['constructor'].parameters] == [('repo', 'T'), ('name?', 'string')]
    assert methods['load'].return_type == 'Promise<T | null>' and methods['load'].is_async
    assert 'nothing' in methods                      # an abstract method is part of the API
    assert [(a['name'], a['type'], a['default_value']) for a in svc.attributes] == [('x', 'number', '1')]


def test_interfaces_enums_and_aliases():
    m = parse(TS, 'mod.ts')
    user = cls(m, 'User')
    assert user.decorators == ['interface']
    assert [(a['name'], a['type']) for a in user.attributes] == [('name', 'string'), ('age', 'number')]
    assert [(x.name, x.return_type) for x in user.methods] == [('greet', 'void')]
    color = cls(m, 'Color')
    assert color.decorators == ['enum']
    assert [(a['name'], a['default_value']) for a in color.attributes] == [('Red', None), ('Green', "'g'")]
    assert [(v['name'], v['type']) for v in m.global_variables] == [('Id', 'type')]


def test_overload_signatures_are_not_listed_as_separate_functions():
    m = parse(TS, 'mod.ts')
    assert [f.name for f in m.functions].count('over') == 1


def test_tsx():
    m = parse('const C = (p: { a: number }) => <div>{p.a}</div>;\n', 'c.tsx')
    assert m.language == 'typescript' and [f.name for f in m.functions] == ['C']


def test_typescript_syntax_is_an_error_in_a_js_file():
    with pytest.raises(ParseError):
        parse('function f(a: number): string { return ""; }\n', 'mod.js')


# ------------------------------------------------------------------ errors and odds and ends

def test_syntax_error_says_what_and_where():
    with pytest.raises(ParseError) as error:
        parse('function ok() {}\n\nconst a = ;\nfunction after() {}\n', 'bad.js')
    assert error.value.line_number == 3
    assert 'Unexpected token' in error.value.message and '\n' not in error.value.message


def test_shebang_and_bom_are_fine():
    m = parse('﻿#!/usr/bin/env node\nfunction main() {}\n')
    assert [f.name for f in m.functions] == ['main']


def test_empty_file_has_no_members():
    m = parse('')
    assert m.functions == [] and m.classes == []


def test_complexity_follows_length():
    body = ''.join(f'  x{i} = {i};\n' for i in range(40))
    assert fn(parse(f'function big() {{\n{body}}}\nfunction small() {{}}\n'), 'big').complexity == 'Complex'


def test_file_extensions_are_matched_ignoring_case():
    assert JavaScriptParser().can_parse('A.TS') and JavaScriptParser().can_parse('a.MJS')
    assert not JavaScriptParser().can_parse('a.json')


def test_missing_babel_package_gives_an_actionable_message(tmp_path, monkeypatch):
    # a helper copy in a folder without node_modules cannot find @babel/parser
    lone = tmp_path / 'helper.js'
    lone.write_text((ROOT / 'src' / 'parsers' / 'js_parser_helper.js').read_text())
    parser = JavaScriptParser()
    parser.helper_script = lone
    source = tmp_path / 'a.js'
    source.write_text('function f() {}\n')
    with pytest.raises(ParseError) as error:
        parser.parse_file(str(source))
    assert 'npm install' in str(error.value)


def test_multi_line_expression_body_is_kept_whole():
    m = parse('const f = (a) =>\n  a.map(x => x + 1)\n   .filter(Boolean);\n')
    f = fn(m, 'f')
    assert f.body_lines == 2
    assert f.body_summary.startswith('a.map(x => x + 1)')


def test_class_method_overloads_are_one_method():
    m = parse('class A {\n  f(a: string): void;\n  f(a: number): void;\n  f(a: any) {}\n}\n', 'a.ts')
    assert [x.name for x in cls(m, 'A').methods] == ['f']


def test_other_assignments_are_not_exports():
    m = parse('foo.bar = function () {};\nwindow.x = () => 1;\nexports.ok = () => 1;\n')
    assert [f.name for f in m.functions] == ['ok']


def test_namespace_members_are_listed():
    m = parse('namespace NS { export function inner() {} }\n', 'a.ts')
    assert [f.name for f in m.functions] == ['inner']


def test_top_level_return_in_a_commonjs_script_is_accepted():
    m = parse('function f() {}\nif (!process.env.X) { return; }\n')
    assert [f.name for f in m.functions] == ['f']
