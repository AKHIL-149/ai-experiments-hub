"""HTML output: ids must be unique and every in-page link must have a target."""
import re

from src.formatters import HTMLFormatter
from src.parsers.python_parser import PythonParser


def parse(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source)
    return PythonParser().parse_file(str(path))


def ids_and_links(html):
    ids = re.findall(r'\bid="([^"]+)"', html)
    links = [l for l in re.findall(r'href="#([^"]*)"', html) if l]
    return ids, links


def test_function_and_class_differing_only_in_case_keep_distinct_ids(tmp_path):
    module = parse(tmp_path, "a.py", "class A:\n    def go(self): pass\ndef a(): pass\n")
    out = tmp_path / "out.html"
    HTMLFormatter().format(module, str(out))
    ids, links = ids_and_links(out.read_text())
    assert len(ids) == len(set(ids))
    assert len(links) == 3
    assert set(links) <= set(ids)


def test_batch_with_same_function_name_in_two_files(tmp_path):
    one = parse(tmp_path, "one.py", "def run(): pass\nclass Run: pass\n")
    two = parse(tmp_path, "two.py", "def run(): pass\n")
    out = tmp_path / "batch.html"
    HTMLFormatter().format_batch([one, two], str(out))
    ids, links = ids_and_links(out.read_text())
    assert len(ids) == len(set(ids))
    assert set(links) <= set(ids)
    assert len(links) >= 5


def test_ids_are_usable_in_a_css_selector(tmp_path):
    # the page scrolls to a link target with querySelector('#' + id); "$" and "." would break that
    module = parse(tmp_path, "my file.v2.py", "def f(): pass\n")
    out = tmp_path / "out.html"
    HTMLFormatter().format(module, str(out))
    ids, links = ids_and_links(out.read_text())
    for target in links:
        assert re.fullmatch(r"[a-z0-9_-]+", target), target
    assert set(links) <= set(ids)


def test_text_from_the_code_is_escaped(tmp_path):
    module = parse(tmp_path, "x.py", 'def f(a="<script>alert(1)</script>"):\n    """<img src=x onerror=alert(2)>"""\n')
    out = tmp_path / "out.html"
    HTMLFormatter().format(module, str(out))
    html = out.read_text()
    assert "<script>alert(1)" not in html
    assert "<img src=x" not in html
