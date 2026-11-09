"""
The page must show what the server sends as text, never as HTML.

Found by uploading a video titled <img src=x onerror=...>: the Videos tab put
the title into innerHTML and the script ran (also descriptions, summaries,
highlights, clips, search results, answers and error messages).

These tests run the real frontend/app.js in node against a stub DOM and a stub
fetch that return hostile data (skipped when node is not installed).
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "frontend" / "app.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

HARNESS = r"""
const vm = require('vm'), fs = require('fs');
const input = JSON.parse(process.argv[process.argv.length - 1]);
const elements = {}, created = [];
function el(id) {
  return {id, innerHTML: '', textContent: '', outerHTML: '', value: '', style: {}, dataset: {}, children: [],
    classList: {add() {}, remove() {}, toggle() {}}, appendChild(c) { this.children.push(c); return c; },
    append(...c) { this.children.push(...c); }, remove() {}, scrollIntoView() {}, addEventListener() {},
    setAttribute() {}, querySelector() { return null; }, querySelectorAll() { return []; }};
}
const document = {
  addEventListener() {}, querySelectorAll() { return []; }, querySelector() { return null; },
  getElementById(id) { return elements[id] || (elements[id] = el(id)); },
  createElement(tag) { const e = el(tag); created.push(e); return e; },
};
const ctx = {
  document, window: {location: {origin: 'http://localhost:8000'}}, console: {log() {}, error() {}, warn() {}},
  setTimeout() { return 0; }, clearTimeout() {}, WebSocket: function () { this.close = () => {}; },
  confirm: () => true, alert() {}, URL, Date, Math, JSON, Number, String, Promise, parseFloat, isNaN, Object, Array,
  fetch: async (url) => {
    const hit = input.routes.find(([part]) => String(url).includes(part));
    const body = hit ? hit[1] : {};
    return {ok: true, status: 200, json: async () => body};
  },
};
ctx.window.document = document;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(input.app, 'utf8'), ctx);
(async () => {
  await vm.runInContext('(async () => {' + input.script + '})()', ctx);
  const out = {byId: {}, created: created.map(c => ({innerHTML: c.innerHTML, textContent: c.textContent, children: c.children.map(k => ({tag: k.id, innerHTML: k.innerHTML, textContent: k.textContent}))}))};
  for (const [id, e] of Object.entries(elements)) out.byId[id] = {innerHTML: e.innerHTML, textContent: e.textContent};
  console.log(JSON.stringify(out));
})().catch(e => { console.error(e); process.exit(1); });
"""

IMG = '<img src=x onerror="PWN()">'
SCRIPT = "<script>PWN()</script>"
BREAKOUT = "');PWN();//"


def run_page(routes, script, tz=None):
    payload = json.dumps({"app": str(APP), "routes": routes, "script": script})
    env = {**os.environ, "TZ": tz} if tz else None
    result = subprocess.run(["node", "-e", HARNESS, payload], capture_output=True, text=True, timeout=30, env=env)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def everything(page):
    """All HTML the page wrote anywhere"""
    html = [e["innerHTML"] for e in page["byId"].values()]
    for c in page["created"]:
        html.append(c["innerHTML"])
        html.extend(k["innerHTML"] for k in c["children"])
    return "\n".join(html)


def assert_inert(html):
    assert "<img src=x" not in html and "<script>" not in html and 'onerror="PWN' not in html


class TestEscapeHtml:
    def test_escapes_the_five_characters(self):
        page = run_page([], "document.getElementById('o').textContent = escapeHtml(`<a href=\"x\">'&'</a>`);")
        assert page["byId"]["o"]["textContent"] == "&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;"

    @pytest.mark.parametrize("value", ["null", "undefined"])
    def test_nothing_becomes_the_text_null(self, value):
        page = run_page([], f"document.getElementById('o').textContent = '[' + escapeHtml({value}) + ']';")
        assert page["byId"]["o"]["textContent"] == "[]"

    def test_numbers(self):
        page = run_page([], "document.getElementById('o').textContent = escapeHtml(42) + escapeHtml(0);")
        assert page["byId"]["o"]["textContent"] == "420"


class TestHostileDataIsShownAsText:
    def test_video_list(self):
        page = run_page([("/api/videos", {"total": 1, "videos": [
            {"video_id": "v1", "title": IMG, "duration_seconds": 5, "processing_status": "completed"}]})], "await loadVideos();")
        html = page["byId"]["videos-list"]["innerHTML"]
        assert_inert(html) and None
        assert "&lt;img src=x onerror=&quot;PWN()&quot;&gt;" in html

    def test_video_status_cannot_break_out_of_its_attribute(self):
        page = run_page([("/api/videos", {"total": 1, "videos": [
            {"video_id": 'v1"><b id=x>', "title": "t", "duration_seconds": 5, "processing_status": 'done"><i>'}]})], "await loadVideos();")
        html = page["byId"]["videos-list"]["innerHTML"]
        assert '"><b' not in html and '"><i' not in html

    def test_video_details(self):
        video = {"video_id": "v1", "title": IMG, "description": SCRIPT, "duration_seconds": 5, "processing_status": IMG,
                 "source_type": SCRIPT, "created_at": "2026-11-09T05:00:00"}
        page = run_page([("/api/videos/v1", video)], "await showVideoDetails('v1');")
        assert_inert(page["byId"]["video-details"]["innerHTML"])

    def test_summary(self):
        summary = {"summary_type": IMG, "content": SCRIPT + IMG, "key_points": [IMG, SCRIPT], "generated_at": "2026-11-09T05:00:00",
                   "duration_covered": 60}
        page = run_page([("/summary", summary)], "await viewSummary('v1');")
        html = page["byId"]["summary-details"]["innerHTML"]
        assert_inert(html) and None
        assert "&lt;script&gt;PWN()&lt;/script&gt;" in html

    def test_highlights_and_the_clip_button(self):
        highlights = {"total_highlights": 1, "average_importance": 0.5, "highlights": [{
            "highlight_id": "h1", "title": BREAKOUT + IMG, "description": SCRIPT, "highlight_type": IMG, "start_time": 1, "end_time": 5,
            "importance_score": 0.9, "thumbnail_path": "x.jpg"}]}
        page = run_page([("/highlights", highlights)], "await viewHighlights('v1');")
        html = page["byId"]["highlights-details"]["innerHTML"]
        assert_inert(html)
        # the title travels in a data attribute, not inside JavaScript text
        assert "this.dataset.title" in html and "PWN()" not in re.search(r'onclick="[^"]*"', html).group(0)

    def test_clips(self):
        clips = {"total": 1, "clips": [{"clip_id": "c1", "video_id": "v1", "title": IMG, "status": "failed", "error_message": SCRIPT,
                                         "start_time": 1, "end_time": 5}]}
        page = run_page([("/api/clips", clips)], "await viewClips('v1');")
        assert_inert(page["byId"]["clips-details"]["innerHTML"])

    def test_search_results(self):
        data = {"total_results": 1, "search_time_ms": 1.5, "results": [
            {"result_type": IMG, "video_title": IMG, "content": SCRIPT, "similarity_score": 0.9, "timestamp": 3}]}
        page = run_page([], f"displaySearchResults({json.dumps(data)});")
        html = page["byId"]["search-results"]["innerHTML"]
        assert_inert(html) and None
        assert "&lt;script&gt;" in html

    def test_answers_and_their_sources(self):
        data = {"answer": IMG + SCRIPT, "confidence": 0.4, "sources": [{"source_type": IMG, "timestamp": 3, "content": SCRIPT}]}
        page = run_page([], f"displayQueryResult({json.dumps(data)});")
        assert_inert(page["byId"]["search-results"]["innerHTML"])

    def test_progress_messages(self):
        page = run_page([], f"addStageComplete('x', {json.dumps(IMG)});")
        assert_inert(everything(page))

    def test_toasts_are_text_not_html(self):
        page = run_page([], f"showToast({json.dumps(IMG)}, 'error');")
        assert all("<img" not in c["innerHTML"] for c in page["created"])
        assert any(c["textContent"] == IMG for c in page["created"])            # shown literally


def test_ordinary_data_still_renders():
    page = run_page([("/api/videos", {"total": 1, "videos": [
        {"video_id": "v1", "title": "Quarterly review & plan", "duration_seconds": 75, "processing_status": "completed"}]})],
        "await loadVideos();")
    html = page["byId"]["videos-list"]["innerHTML"]
    assert "Quarterly review &amp; plan" in html and "1:15" in html and "status-completed" in html


def test_every_server_field_in_a_template_goes_through_esc():
    """Guard for new code: server fields in HTML templates must be escaped"""
    fields = r"(?:title|description|content|answer|error_message|summary_type|source_type|video_title|highlight_type|processing_status)"
    skip = ("console.", "showToast(", "updateProgress(", "apiCall(", "fetch(", "title: ", "title,")

    def unsafe(line):
        line = re.sub(r"esc\([^()]*(?:\([^()]*\)[^()]*)*\)", "esc()", line)          # already escaped
        line = re.sub(r"[\w.]*\b" + fields + r"\s*\?", "CHECK?", line)               # only tested: ${x.title ? ... : ''}
        return re.search(r"\$\{[^}]*\b" + fields + r"\b[^}]*\}", line)

    offenders = [
        f"{number}: {line.strip()}" for number, line in enumerate(APP.read_text().splitlines(), 1)
        if unsafe(line) and not any(s in line for s in skip)
    ]
    assert offenders == []


def test_the_guard_itself_catches_an_unescaped_field(tmp_path, monkeypatch):
    bad = tmp_path / "app.js"
    bad.write_text("el.innerHTML = `<h4>${video.title}</h4>`;\n")
    monkeypatch.setattr(sys.modules[__name__], "APP", bad)
    with pytest.raises(AssertionError):
        test_every_server_field_in_a_template_goes_through_esc()


class TestServerTimes:
    """The API sends UTC times without a zone ('2026-11-09T05:03:12'); the page must not read them as local time"""

    def iso(self, value):
        # a computer west of Greenwich, where reading UTC as local time shows the wrong hour
        page = run_page([], f"document.getElementById('o').textContent = serverDate({json.dumps(value)}).toISOString();", tz="America/Chicago")
        return page["byId"]["o"]["textContent"]

    def test_a_time_without_a_zone_is_utc(self):
        assert self.iso("2026-11-09T05:03:12") == "2026-11-09T05:03:12.000Z"

    def test_fractional_seconds(self):
        assert self.iso("2026-11-09T05:03:12.788152") == "2026-11-09T05:03:12.788Z"

    @pytest.mark.parametrize("value,expected", [
        ("2026-11-09T05:03:12Z", "2026-11-09T05:03:12.000Z"),
        ("2026-11-09T05:03:12+02:00", "2026-11-09T03:03:12.000Z"),
        ("2026-11-09T05:03:12-0600", "2026-11-09T11:03:12.000Z"),
    ])
    def test_a_time_with_a_zone_keeps_it(self, value, expected):
        assert self.iso(value) == expected

    def test_the_pages_use_it(self):
        source = APP.read_text()
        assert "new Date(video.created_at)" not in source and "new Date(summary.generated_at)" not in source
        assert source.count("serverDate(") >= 3
