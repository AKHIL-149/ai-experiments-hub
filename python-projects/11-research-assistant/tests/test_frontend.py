"""
static/app.js, run in Node with a small fake DOM (so these check the script's logic, not how it looks).

Found in the page: the research list, findings, source titles and links, and the summary went into innerHTML
unescaped, and they come from web pages and from a model reading them (stored XSS, again on every reopen); a
source link could be "javascript:..."; the progress bar never moved; a failed download did nothing; the
sources of a saved research all showed type "undefined".
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
const scenario = JSON.parse(process.argv[1]);
const source = fs.readFileSync(process.argv[2], 'utf8');

class Element {
  constructor(tag, id) {
    this.tagName = tag; this.id = id || ''; this.children = []; this.style = {}; this.value = ''; this.checked = false;
    this._html = ''; this.textContent = ''; this.listeners = {}; this.className = ''; this.dataset = {};
    this.classList = { add() {}, remove() {} };
  }
  set innerHTML(v) { this._html = v; if (v === '') this.children = []; }
  get innerHTML() { return this._html; }
  appendChild(c) { this.children.push(c); return c; }
  after(c) { this.sibling = c; }
  addEventListener(t, fn) { this.listeners[t] = fn; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  click() { this.clicked = true; }
  all() { return [this, ...this.children.flatMap(c => c.all())]; }
}

const byId = {};
const el = id => byId[id] || (byId[id] = new Element('div', id));
const alerts = [], fetches = [], timers = [];
let fetchPlan = [];
const body = new Element('body');

const context = {
  console: { error() {}, log() {} },
  alert: m => alerts.push(m), confirm: () => true,
  setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
  document: {
    getElementById: el,
    createElement: tag => new Element(tag),
    querySelector: sel => (sel === '.results-meta' ? el('results-meta') : sel === '.results-actions' ? el('results-actions') : null),
    addEventListener() {},
    body,
  },
  window: { location: { href: 'http://localhost:8000/' }, URL: { createObjectURL: () => 'blob:x', revokeObjectURL() {} }, crypto: { randomUUID: () => 'uuid-for-test-1234' } },
  URL: URL,
  crypto: { randomUUID: () => 'uuid-for-test-1234' },
  fetch: async (url, opts) => {
    fetches.push({ url, opts });
    const next = fetchPlan.shift() || { ok: true, status: 200, body: {} };
    return { ok: next.ok, status: next.status || (next.ok ? 200 : 500), json: async () => next.body, blob: async () => ({}) };
  },
};
context.window.URL = Object.assign(function () {}, { createObjectURL: () => 'blob:x', revokeObjectURL() {} });
vm.createContext(context);
vm.runInContext(source + '\n;globalThis.ResearchApp = ResearchApp;', context);
const app = Object.create(context.ResearchApp.prototype);
app.currentUser = { username: 'u' }; app.researchList = []; app.currentResearch = null;
app.showView = v => { app.view = v; };
app.loadResearchList = async () => {};
app.formatDate = () => 'now';
const h = { app, el, alerts, fetches, timers, Element, context, byId, body, setFetchPlan: p => { fetchPlan = p; } };
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
(async () => { console.log(JSON.stringify(await new AsyncFunction('h', scenario.code)(h))); })()
  .catch(e => console.log(JSON.stringify({ crash: String(e && e.stack || e) })));
"""


def run(code):
    done = subprocess.run(["node", "-e", HARNESS, json.dumps({"code": code}), str(ROOT / "static" / "app.js")],
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert "crash" not in out, out["crash"]
    return out


EVIL = "<img src=x onerror=alert(1)>"


class TestEscaping:
    def test_escape_covers_quotes_so_it_is_safe_in_attributes(self):
        out = run("""return { a: h.app.escapeHtml('<b>"x" & \\'y\\'</b>'), n: h.app.escapeHtml(null), num: h.app.escapeHtml(5) };""")
        assert out == {"a": "&lt;b&gt;&quot;x&quot; &amp; &#39;y&#39;&lt;/b&gt;", "n": "", "num": "5"}

    @pytest.mark.parametrize("url,expected", [
        ("https://example.com/a?b=1", "https://example.com/a?b=1"), ("http://example.com/", "http://example.com/"),
        ("javascript:alert(1)", None), ("JaVaScRiPt:alert(1)", None), ("data:text/html,<script>1</script>", None),
        ("vbscript:x", None), ("", None), (None, None),
    ])
    def test_only_web_addresses_are_links(self, url, expected):
        assert run(f"return {{ v: h.app.safeUrl({json.dumps(url)}) }};")["v"] == expected

    def test_the_research_list_is_escaped(self):
        out = run(f"""
          h.app.researchList = [{{ query_id: 'q1', query: {json.dumps(EVIL)}, status: '<b>done</b>', created_at: 'x' }}];
          h.app.renderResearchList();
          return {{ html: h.el('research-list').children.map(c => c.innerHTML).join('') }};
        """)
        assert "<img" not in out["html"] and "<b>" not in out["html"] and "&lt;img" in out["html"]

    def results(self, research, extra=""):
        return run(f"""
          h.app.currentResearch = {json.dumps(research)};
          h.app.renderResults();
          const all = id => h.el(id).children.map(c => c.innerHTML).join('');
          return {{ findings: all('results-findings'), sources: all('results-sources-list'), summary: h.el('results-summary').innerHTML,
                   warnings: h.el('results-warnings').innerHTML, warnShown: h.el('results-warnings').style.display, {extra} }};
        """)

    def test_findings_sources_and_summary_are_escaped(self):
        research = {"query_id": "q", "query": "q", "summary": f"**Heading**\n\nText {EVIL} (Source: 2)",
                    "findings": [{"finding_text": EVIL, "finding_type": "<script>", "confidence": 0.5, "num_sources": 2}],
                    "sources": [{"title": EVIL, "url": "https://x.example/\"onmouseover=\"alert(1)", "type": "web"},
                                {"title": "js", "url": "javascript:alert(2)", "type": "web"}],
                    "citations": []}
        out = self.results(research)
        for field in ("findings", "sources", "summary"):
            assert "<img" not in out[field] and "<script" not in out[field], field
        assert "&lt;img" in out["findings"] and "&lt;script&gt;" in out["findings"]
        assert 'href="javascript' not in out["sources"] and "javascript:alert(2)" in out["sources"]
        assert 'onmouseover="alert' not in out["sources"] and "%22onmouseover" in out["sources"]
        assert "rel=\"noopener noreferrer\"" in out["sources"]

    def test_the_summary_keeps_its_formatting(self):
        out = self.results({"query_id": "q", "query": "q", "summary": "**Title**\n\nA **bold** claim (Source: 2).\n\nTwo (Sources: 1, 3).",
                            "findings": [], "sources": [], "citations": []})
        assert "<h3>Title</h3>" in out["summary"] and "<strong>bold</strong>" in out["summary"]
        assert '<span class="source-ref">(Source: 2)</span>' in out["summary"]
        assert "(Sources: 1, 3)" in out["summary"]

    def test_a_saved_sources_type_is_shown(self):
        out = self.results({"query_id": "q", "query": "q", "summary": "s", "findings": [], "citations": [],
                            "sources": [{"title": "T", "url": None, "source_type": "arxiv"}]})
        assert ">arxiv<" in out["sources"] and "undefined" not in out["sources"]

    def test_warnings_are_shown_escaped(self):
        out = self.results({"query_id": "q", "query": "q", "summary": "s", "findings": [], "sources": [], "citations": [],
                            "warnings": [f"Ignored 2 sources {EVIL}"]})
        assert out["warnShown"] == "block" and "Ignored 2 sources" in out["warnings"] and "<img" not in out["warnings"]

    def test_no_warnings_hides_the_box(self):
        out = self.results({"query_id": "q", "query": "q", "summary": "s", "findings": [], "sources": [], "citations": []})
        assert out["warnShown"] == "none"

    def test_a_failed_research_shows_why(self):
        out = self.results({"query_id": "q", "query": "q", "summary": None, "status": "failed", "error_message": "Could not reach Ollama",
                            "findings": [], "sources": [], "citations": []})
        assert "Could not reach Ollama" in out["warnings"]


class TestProgress:
    def test_the_bar_and_the_line_follow_the_server(self):
        out = run("""
          h.app.showProgress({ step: 4, total: 6, message: 'Reading 3 sources' });
          return { width: h.el('progress-fill').style.width, text: h.el('progress-status').textContent };
        """)
        assert out == {"width": "67%", "text": "Step 4 of 6: Reading 3 sources"}

    def test_the_first_step_is_never_shown_as_step_0(self):
        assert "Step 1 of 6" in run("h.app.showProgress({ step: 0, total: 6, message: 'Starting' }); return { t: h.el('progress-status').textContent };")["t"]

    def test_polling_asks_every_second_until_stopped(self):
        out = run("""
          h.setFetchPlan([{ ok: true, body: { step: 2, total: 6, message: 'Removing duplicates' } }, { ok: true, body: { step: 3, total: 6, message: 'Ranking' } }]);
          const stop = h.app.pollProgress('uuid-for-test-1234');
          const run = async () => { const t = h.timers.shift(); await t.fn(); await new Promise(r => setImmediate(r)); return t.ms; };
          const first = await run(); const afterFirst = h.el('progress-status').textContent;
          const second = await run(); const afterSecond = h.el('progress-status').textContent;
          stop(); const pending = h.timers.shift(); const before = h.fetches.length; await pending.fn();
          return { first, second, afterFirst, afterSecond, urls: h.fetches.map(f => f.url), fetchedAfterStop: h.fetches.length - before };
        """)
        assert out["first"] == 400 and out["second"] == 1000
        assert "Removing duplicates" in out["afterFirst"] and "Ranking" in out["afterSecond"]
        assert set(out["urls"]) == {"/api/research/progress/uuid-for-test-1234"} and out["fetchedAfterStop"] == 0

    def test_a_failing_poll_does_not_break_the_run(self):
        out = run("""
          h.context.fetch = async () => { throw new Error('offline'); };
          h.app.pollProgress('abc'); const t = h.timers.shift(); await t.fn(); await new Promise(r => setImmediate(r));
          return { next: h.timers.length };
        """)
        assert out["next"] == 1


class TestStartResearch:
    SETUP = """
      h.el('research-query').value = 'What is retrieval augmented generation?';
      h.el('source-web').checked = true; h.el('source-arxiv').checked = true; h.el('source-documents').checked = false;
      h.el('max-sources').value = '8'; h.el('citation-style').value = 'APA';
      h.app.renderResults = () => {};
    """

    def test_the_request_carries_an_id_and_polling_stops_afterwards(self):
        out = run(self.SETUP + """
          h.setFetchPlan([{ ok: true, body: { query_id: 'q1', query: 'x' } }]);
          await h.app.handleStartResearch();
          const post = h.fetches.find(f => f.url === '/api/research');
          return { body: JSON.parse(post.opts.body), progressShown: h.el('research-progress').style.display,
                   disabled: h.el('start-research-btn').disabled, queryCleared: h.el('research-query').value === '' };
        """)
        assert out["body"]["request_id"] == "uuid-for-test-1234" and out["body"]["max_sources"] == 8
        assert out["progressShown"] == "none" and out["disabled"] is False and out["queryCleared"] is True

    def test_a_failed_research_keeps_the_question_and_says_why(self):
        out = run(self.SETUP + """
          h.setFetchPlan([{ ok: false, status: 500, body: { detail: 'Could not reach Ollama' } }]);
          await h.app.handleStartResearch();
          return { alerts: h.alerts, query: h.el('research-query').value, disabled: h.el('start-research-btn').disabled };
        """)
        assert out["alerts"] == ["Research failed: Could not reach Ollama"]
        assert out["query"] == "What is retrieval augmented generation?" and out["disabled"] is False

    def test_a_network_failure_keeps_the_question_too(self):
        out = run(self.SETUP + """
          h.context.fetch = async (url) => { if (url === '/api/research') throw new Error('offline'); return { ok: false, json: async () => ({}) }; };
          await h.app.handleStartResearch();
          return { alerts: h.alerts, query: h.el('research-query').value, disabled: h.el('start-research-btn').disabled };
        """)
        assert out["alerts"] == ["Research failed. Please try again."]
        assert out["query"] == "What is retrieval augmented generation?" and out["disabled"] is False

    def test_no_source_chosen_is_stopped_before_any_request(self):
        out = run(self.SETUP + """
          h.el('source-web').checked = false; h.el('source-arxiv').checked = false;
          await h.app.handleStartResearch();
          return { alerts: h.alerts, fetches: h.fetches.length };
        """)
        assert out == {"alerts": ["Choose at least one source to search"], "fetches": 0}

    @pytest.mark.parametrize("value,expected", [("", 20), ("abc", 20), ("0", 1), ("-5", 1), ("500", 50), ("12", 12), ("7.9", 7)])
    def test_max_sources_is_always_something_the_server_accepts(self, value, expected):
        assert run(f"h.el('max-sources').value = {json.dumps(value)}; return {{ v: h.app.readMaxSources() }};")["v"] == expected


class TestDownloads:
    def test_a_failed_download_says_why(self):
        out = run("""
          h.app.currentResearch = { query_id: 'q1' };
          h.setFetchPlan([{ ok: false, status: 501, body: { detail: 'PDF generation not available: weasyprint needs the pango library' } }]);
          await h.app.downloadReport('pdf');
          return { alerts: h.alerts };
        """)
        assert out["alerts"] == ["PDF generation not available: weasyprint needs the pango library"]

    def test_a_download_gets_the_right_file_name(self):
        out = run("""
          h.app.currentResearch = { query_id: 'q1' };
          const links = []; const real = h.context.document.createElement;
          h.context.document.createElement = tag => { const e = real(tag); links.push(e); return e; };
          h.context.document.body.appendChild = () => {}; h.context.document.body.removeChild = () => {};
          await h.app.downloadReport('markdown');
          return { names: links.map(l => l.download).filter(Boolean), url: h.fetches[0].url };
        """)
        assert out["names"] == ["research_q1.md"] and out["url"] == "/api/research/q1/download?format=markdown"

    def test_pdf_and_docx_buttons_appear_only_when_the_server_can_make_them(self):
        out = run("""
          h.setFetchPlan([{ ok: true, body: { formats: ['markdown', 'html', 'json', 'docx'] } }]);
          h.context.document.querySelector = sel => sel === '.results-actions' ? h.el('results-actions') : null;
          // the page has no PDF/DOCX button until one is added (the fake would invent one on lookup)
          h.context.document.getElementById = id => h.byId[id] || (id.startsWith('download-') ? null : h.el(id));
          await h.app.loadExportFormats();
          await h.app.loadExportFormats();   // a second call must not add a second button
          return { buttons: h.el('results-actions').children.map(c => c.textContent) };
        """)
        assert out["buttons"] == ["Download DOCX"]
