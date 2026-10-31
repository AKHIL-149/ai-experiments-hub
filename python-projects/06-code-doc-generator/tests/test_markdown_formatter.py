"""Markdown output: every table-of-contents link must land on a real heading."""
import re
import textwrap

import pytest

from src.formatters import MarkdownFormatter
from src.formatters.markdown_formatter import Slugger
from src.parsers.python_parser import PythonParser

SOURCE = textwrap.dedent('''
    """Money helpers."""
    import math

    class Account:
        """An account."""
        rate: float = 0.5

        def __init__(self, owner, *tags, **extra):
            self.owner = owner

        def compound_interest(self, years):
            """Interest."""
            return years

    def compound_interest(principal, rate=0.05):
        """Top level one, same name as the method."""
        return principal * rate

    async def fetch(url: str) -> bytes:
        return b""

    def account():
        return 1
''')


def parse(tmp_path, name="money.py", source=SOURCE):
    path = tmp_path / name
    path.write_text(source)
    return PythonParser().parse_file(str(path))


def anchors_of(markdown):
    """Anchors GitHub would create for the headings, in order."""
    slugger = Slugger()
    found = []
    in_fence = False
    for line in markdown.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and re.match(r"#{1,6} ", line):
            text = re.sub(r"^#+ ", "", line).replace("`", "")
            found.append(slugger.slug(text))
    return found


def toc_links(markdown):
    return re.findall(r"\]\(#([^)]+)\)", markdown)


def test_single_file_toc_links_all_resolve(tmp_path):
    out = tmp_path / "out.md"
    MarkdownFormatter().format(parse(tmp_path), str(out))
    md = out.read_text()
    links = toc_links(md)
    assert len(links) == 4          # 3 functions + 1 class
    assert set(links) <= set(anchors_of(md))


def test_toc_link_for_function_does_not_point_at_the_method_with_same_name(tmp_path):
    out = tmp_path / "out.md"
    MarkdownFormatter().format(parse(tmp_path), str(out))
    md = out.read_text()
    lines = md.splitlines()
    link = [l for l in lines if "compound_interest()" in l][0]
    anchor = re.search(r"\(#([^)]+)\)", link).group(1)
    index = anchors_of(md).index(anchor)
    headings = [l for l in lines if re.match(r"#{1,6} ", l)]
    # the module-level function sits under "Functions", so it comes before the class and its methods
    assert headings[index] == "### `compound_interest`"
    assert "Account" not in "".join(headings[:index])


def test_function_and_class_with_names_differing_only_in_case_get_distinct_anchors(tmp_path):
    out = tmp_path / "out.md"
    MarkdownFormatter().format(parse(tmp_path), str(out))
    md = out.read_text()
    links = toc_links(md)
    assert len(links) == len(set(links))
    assert "account" in links and "account-1" in links


def test_batch_toc_links_resolve_even_with_same_file_names(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    one = parse(tmp_path / "a", "utils.py")
    two = parse(tmp_path / "b", "utils.py")
    out = tmp_path / "batch.md"
    MarkdownFormatter().format_batch([one, two], str(out))
    md = out.read_text()
    anchors = anchors_of(md)
    module_links = toc_links(md.split("---")[0])
    assert module_links == ["module-utilspy", "module-utilspy-1"]
    for link in toc_links(md):
        assert link in anchors


def test_signature_is_kept_in_a_code_block(tmp_path):
    out = tmp_path / "out.md"
    MarkdownFormatter().format(parse(tmp_path), str(out))
    md = out.read_text()
    assert "async fetch(url: str) -> bytes" in md
    assert "compound_interest(principal, rate = 0.05)" in md or "compound_interest(principal, rate=0.05)" in md


def test_class_attributes_show_default_and_scope(tmp_path):
    out = tmp_path / "out.md"
    MarkdownFormatter().format(parse(tmp_path), str(out))
    md = out.read_text()
    assert "- `rate`: `float` = `0.5` *(class attribute)*" in md
    assert "- `owner` = `owner` *(instance attribute)*" in md


def test_bases_are_not_part_of_the_heading(tmp_path):
    module = parse(tmp_path, source="class Child(Base, Other):\n    pass\n")
    out = tmp_path / "out.md"
    MarkdownFormatter().format(module, str(out))
    md = out.read_text()
    assert "#### `Child`\n" in md or "### `Child`\n" in md
    assert "**Extends**: `Base`, `Other`" in md
    assert set(toc_links(md)) <= set(anchors_of(md))


def test_toc_can_be_switched_off(tmp_path):
    out = tmp_path / "out.md"
    MarkdownFormatter(include_toc=False).format(parse(tmp_path), str(out))
    assert toc_links(out.read_text()) == []


def test_slugger_matches_github_rules():
    s = Slugger()
    assert s.slug("Module: `x.py`".replace("`", "")) == "module-xpy"
    assert s.slug("Hello World") == "hello-world"
    assert s.slug("Hello World") == "hello-world-1"
    assert s.slug("Hello World") == "hello-world-2"
    assert s.slug("snake_case_name") == "snake_case_name"


def test_formatters_do_not_modify_sys_path():
    from pathlib import Path as P
    import src.formatters as pkg
    for f in P(pkg.__file__).parent.glob("*.py"):
        assert "sys.path" not in f.read_text(), f.name


def test_function_named_contents_does_not_clash_with_the_contents_heading(tmp_path):
    module = parse(tmp_path, source="def contents():\n    return 1\n")
    out = tmp_path / "out.md"
    MarkdownFormatter().format(module, str(out))
    md = out.read_text()
    assert "(#contents-1)" in md
    assert "contents-1" in anchors_of(md)


def test_class_named_like_an_earlier_method_gets_a_suffixed_anchor(tmp_path):
    module = parse(tmp_path, source="class Foo:\n    def bar(self):\n        return 1\n\nclass Bar:\n    pass\n")
    out = tmp_path / "out.md"
    MarkdownFormatter().format(module, str(out))
    md = out.read_text()
    assert "[`Bar`](#bar-1)" in md
