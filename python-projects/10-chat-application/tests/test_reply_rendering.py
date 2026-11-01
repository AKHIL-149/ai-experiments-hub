"""
How the page renders a model's reply. A reply is untrusted text: it used to go through marked.parse()
straight into innerHTML, so '<img src=x onerror=...>' in a reply ran as script in the user's session
(and again every time the saved conversation was reopened).

The real text-display-enhancements.js is loaded in Node with stand-ins for marked and DOMPurify, so
what is tested is *this file's* guarantee: HTML only leaves renderContent() sanitised, or escaped.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

HARNESS = r"""
const fs = require('fs'), vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const scenario = JSON.parse(process.argv[2]);
const calls = { sanitize: [], parse: [], hooks: [] };

const context = {
  console: { error() {}, log() {} },
  setInterval() { return 0; }, clearInterval() {}, setTimeout() { return 0; },
  document: {
    addEventListener() {},
    createElement() {
      let text = '';
      return {
        set textContent(v) { text = String(v); },
        get innerHTML() { return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); },
      };
    },
  },
  window: {},
};
if (scenario.marked) {
  context.marked = {
    setOptions() {},
    parse(text) {
      calls.parse.push(text);
      if (scenario.markedThrows) throw new Error('boom');
      return scenario.markedOutput !== undefined ? scenario.markedOutput : '<p>' + text + '</p>';
    },
  };
}
if (scenario.dompurify) {
  context.DOMPurify = {
    addHook(name, fn) { calls.hooks.push({ name, fn }); },
    sanitize(html, options) { calls.sanitize.push({ html, options }); return 'SANITIZED(' + html + ')'; },
  };
}
vm.createContext(context);
const Renderer = vm.runInContext(source + '\n;MessageRenderer', context);
const renderer = Object.create(Renderer.prototype);

const out = { result: renderer.renderContent(scenario.content, scenario.role || 'assistant', false) };
out.sanitizeCalls = calls.sanitize;
out.parseCalls = calls.parse;
out.hookNames = calls.hooks.map(h => h.name);
if (calls.hooks.length) {
  const link = { tagName: 'A', attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } };
  const other = { tagName: 'P', attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } };
  calls.hooks[0].fn(link); calls.hooks[0].fn(other);
  out.linkAttrs = link.attrs; out.otherAttrs = other.attrs;
}
console.log(JSON.stringify(out));
"""


def render(content, **scenario):
    scenario = {"marked": True, "dompurify": True, "content": content, **scenario}
    done = subprocess.run(
        ["node", "-e", HARNESS, str(ROOT / "static" / "text-display-enhancements.js"), json.dumps(scenario)],
        capture_output=True, text=True, timeout=30,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


EVIL = '<img src=x onerror="alert(1)"> <script>alert(2)</script>'


class TestSanitising:
    def test_markdown_output_is_sanitised_before_it_is_returned(self):
        out = render(EVIL)
        assert out["result"].startswith("SANITIZED(")                 # what came back is DOMPurify's output...
        assert len(out["sanitizeCalls"]) == 1
        assert EVIL in out["sanitizeCalls"][0]["html"]                # ...made from the markdown output, nothing skipped

    def test_images_styles_and_forms_are_not_allowed_in_a_reply(self):
        options = render("hi")["sanitizeCalls"][0]["options"]
        assert {"img", "style", "form", "input", "button"} <= set(options["FORBID_TAGS"])
        assert "style" in options["FORBID_ATTR"]

    def test_code_block_classes_are_added_before_sanitising(self):
        html = render("x", markedOutput='<pre><code class="language-python">print(1)</code></pre>')["sanitizeCalls"][0]["html"]
        assert 'class="language-python hljs"' in html

    def test_links_open_in_a_new_tab_and_cannot_reach_back(self):
        out = render("hi")
        assert out["hookNames"] == ["afterSanitizeAttributes"]
        assert out["linkAttrs"] == {"target": "_blank", "rel": "noopener noreferrer"}
        assert out["otherAttrs"] == {}                                # only links are touched


class TestFailsClosed:
    """If a library did not load (CDN down, offline) the reply is text - never raw markup"""

    @pytest.mark.parametrize("scenario", [
        {"dompurify": False},
        {"marked": False},
        {"marked": False, "dompurify": False},
        {"markedThrows": True},
    ])
    def test_reply_is_escaped_text(self, scenario):
        out = render(EVIL, **scenario)["result"]
        assert "<img" not in out and "<script" not in out
        assert "&lt;img" in out and "&lt;script&gt;" in out

    def test_unsanitised_markdown_is_never_returned_when_dompurify_is_missing(self):
        out = render("**x**", dompurify=False, markedOutput="<strong>x</strong>")
        assert "<strong>" not in out["result"]

    def test_line_breaks_survive_the_fallback(self):
        assert render("one\ntwo", dompurify=False)["result"] == "one<br>two"


class TestOtherRoles:
    def test_the_users_own_message_is_always_escaped_not_rendered(self):
        out = render(EVIL + "\nnext line", role="user")
        assert "<img" not in out["result"] and "&lt;img" in out["result"] and "<br>" in out["result"]
        assert out["parseCalls"] == [] and out["sanitizeCalls"] == []      # markdown is not even attempted

    def test_empty_content(self):
        assert render("")["result"] == ""
        assert render("", role="user")["result"] == ""


class TestPageWiring:
    def test_dompurify_is_loaded_before_the_renderer_and_pinned(self):
        html = (ROOT / "templates" / "index.html").read_text()
        purify = html.index("dompurify@3.")
        assert "dompurify@3.2.6/dist/purify.min.js" in html
        assert html.index("marked@") < purify < html.index("text-display-enhancements.js")

    def test_every_assistant_html_write_goes_through_the_renderer(self):
        source = (ROOT / "static" / "text-display-enhancements.js").read_text()
        writes = [line.strip() for line in source.splitlines() if "innerHTML =" in line and "textContent" not in line]
        # the message shell, the streamed update and the final render - each fed by renderContent()
        assert any("renderedContent" in w or "renderContent" in w or "rendered;" in w or w.endswith("`") for w in writes)
        assert source.count("this.renderContent(") >= 3

    def test_generated_image_message_does_not_put_text_in_an_attribute(self):
        source = (ROOT / "static" / "voice-and-image-features.js").read_text()
        assert 'alt="${' not in source and 'src="${' not in source
