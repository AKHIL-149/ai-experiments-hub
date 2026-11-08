"""
The tracker shows agent answers through static/js/markdown.js. It is plain JavaScript with no DOM, so
these tests run it in node (skipped when node is not installed).
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "static" / "js" / "markdown.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")


def run(source):
    code = f"const m = require({json.dumps(str(SCRIPT))}); console.log(JSON.stringify(m.parse(JSON.parse(process.argv[1]))));"
    result = subprocess.run(["node", "-e", code, json.dumps(source)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def text_of(tokens):
    """The words of an inline token list, without the markup"""
    out = ""
    for token in tokens:
        out += token["v"] if "v" in token else text_of(token["c"])
    return out


def kinds(tokens):
    return [t["t"] for t in tokens]


class TestBlocks:
    def test_bold_line_is_a_heading_and_asterisks_are_gone(self):
        blocks = run("**Overview**\n\nA REST API is a style.")
        assert [b["type"] for b in blocks] == ["heading", "p"]
        assert text_of(blocks[0]["inline"]) == "Overview"
        assert "*" not in json.dumps(blocks)

    def test_bold_line_with_a_trailing_colon(self):
        assert text_of(run("**Key Findings:**")[0]["inline"]) == "Key Findings"

    def test_hash_headings(self):
        blocks = run("# Title\n## Sub ##")
        assert [b["type"] for b in blocks] == ["heading", "heading"]
        assert [text_of(b["inline"]) for b in blocks] == ["Title", "Sub"]

    def test_underline_rules_are_dropped(self):
        blocks = run("**Tiny Flask Endpoint**\n======================\n\nBelow is a sample.\n---\nDone")
        assert [b["type"] for b in blocks] == ["heading", "p", "p"]

    def test_bullets(self):
        (block,) = run("* one\n* two\n- three\n• four")
        assert block["type"] == "list" and block["ordered"] is False
        assert [text_of(i["inline"]) for i in block["items"]] == ["one", "two", "three", "four"]

    def test_numbered_list(self):
        (block,) = run("1. first\n2) second\n10. tenth")
        assert block["ordered"] is True and [text_of(i["inline"]) for i in block["items"]] == ["first", "second", "tenth"]

    def test_nesting_by_indent(self):
        (block,) = run("* top\n  * child\n    * grandchild\n          * deep")
        assert [i["level"] for i in block["items"]] == [0, 1, 2, 3]

    def test_indented_line_continues_the_item(self):
        (block,) = run("* first part\n  second part")
        assert len(block["items"]) == 1 and text_of(block["items"][0]["inline"]) == "first part second part"

    def test_blank_line_ends_a_list(self):
        blocks = run("* a\n\n* b")
        assert [b["type"] for b in blocks] == ["list", "list"]

    def test_switching_between_numbers_and_bullets_starts_a_new_list(self):
        blocks = run("1. a\n* b")
        assert [(b["type"], b["ordered"]) for b in blocks] == [("list", True), ("list", False)]

    def test_code_fence_is_kept_verbatim(self):
        blocks = run("Before\n```python\nif a:\n    **not bold** <b>x</b>\n```\nAfter")
        assert [b["type"] for b in blocks] == ["p", "code", "p"]
        assert blocks[1]["text"] == "if a:\n    **not bold** <b>x</b>"

    def test_unclosed_fence_swallows_the_rest_instead_of_failing(self):
        blocks = run("```\nline 1\nline 2")
        assert blocks == [{"type": "code", "text": "line 1\nline 2"}]

    def test_paragraph_lines_stay_separate(self):
        (block,) = run("Task name: A\nDescription: B")
        assert block["type"] == "p" and len(block["lines"]) == 2

    def test_empty_and_odd_input(self):
        assert run("") == [] and run("\n\n  \n") == []
        assert run("a\r\nb")[0]["lines"] and len(run("a\r\nb")[0]["lines"]) == 2


class TestInline:
    def test_bold_italic_code(self):
        (block,) = run("Use **bold**, *italic*, __also bold__ and `code` here.")
        tokens = block["lines"][0]
        assert kinds(tokens) == ["text", "strong", "text", "em", "text", "strong", "text", "code", "text"]
        assert [t["v"] for t in tokens if t["t"] == "code"] == ["code"]

    def test_markup_inside_code_is_not_parsed(self):
        (block,) = run("see `**x**` now")
        assert [t for t in block["lines"][0] if t["t"] == "code"][0]["v"] == "**x**"

    def test_nested_bold_and_italic(self):
        (block,) = run("**bold and *italic* inside**")
        strong = block["lines"][0][0]
        assert strong["t"] == "strong" and kinds(strong["c"]) == ["text", "em", "text"]

    def test_arithmetic_stars_stay_text(self):
        (block,) = run("2 * 3 * 4 = 24")
        assert kinds(block["lines"][0]) == ["text"] and text_of(block["lines"][0]) == "2 * 3 * 4 = 24"

    def test_https_links_become_links(self):
        (block,) = run("read [the docs](https://example.com/a?b=1) now")
        link = [t for t in block["lines"][0] if t["t"] == "link"][0]
        assert link == {"t": "link", "v": "the docs", "href": "https://example.com/a?b=1"}

    @pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,<script>1</script>", "//evil.example", "file:///etc/passwd"])
    def test_only_http_links_are_links(self, url):
        (block,) = run(f"[click]({url})")
        assert "link" not in kinds(block["lines"][0])

    def test_html_stays_text(self):
        (block,) = run("<img src=x onerror=alert(1)> and <script>alert(2)</script>")
        tokens = block["lines"][0]
        assert kinds(tokens) == ["text"] and "<script>" in tokens[0]["v"]


class TestHostileInput:
    """An answer is whatever a model wrote: it must never hang or crash the page"""

    @pytest.mark.parametrize("source", [
        "*" * 20000,
        "**" + "a*" * 8000,
        "**a" * 6000,
        "`" * 20000,
        "[x](https://" + "a" * 20000,
        "* " * 8000,
        "\n".join(["* item **bold *it* x**"] * 3000),
        "_" * 20000 + "__a__",
    ], ids=["stars", "bold-then-stars", "unclosed-bold", "backticks", "unclosed-link", "bullet-stars", "many-items", "underscores"])
    def test_pathological_text_finishes_quickly(self, source):
        import time
        started = time.time()
        run(source)  # run() has a 20 second ceiling and asserts a clean exit
        assert time.time() - started < 8

    def test_deeply_nested_markup_does_not_blow_the_stack(self):
        run("**" * 3000 + "x" + "**" * 3000)
        run("*a **b *c **d *e **f*** ***")


def test_the_page_builds_elements_from_the_tree_not_from_html():
    page = (SCRIPT.parent / "tracker.js").read_text()
    assert "window.TrackerMarkdown.parse" in page
    assert "/static/js/markdown.js" in (SCRIPT.parents[2] / "templates" / "workflow_tracker.html").read_text()
