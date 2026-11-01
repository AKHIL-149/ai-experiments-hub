"""
The "Copy" button under assistant replies, and the clipboard helper behind it.

The real text-display-enhancements.js is loaded in Node with a very small fake DOM, so these tests check
this file's own logic: what is copied (the model's original text, not HTML), when a button appears, the
fallback for pages where navigator.clipboard does not exist (http:// on a network address), and that
failures are shown instead of hidden. Wiring into the live page was checked in a browser.
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

const log = { execCalls: [], textareas: [], writes: [], timers: [], cleared: [], copyCalls: [] };

class Element {
  constructor(tag) {
    this.tagName = tag.toUpperCase(); this.children = []; this.attrs = {}; this.dataset = {};
    this.listeners = {}; this.style = {}; this.className = ''; this._text = ''; this.removed = false;
    this.classes = new Set();
    this.classList = {
      add: (...c) => c.forEach(x => this.classes.add(x)),
      remove: (...c) => c.forEach(x => this.classes.delete(x)),
      toggle: (c, force) => { (force === undefined ? !this.classes.has(c) : force) ? this.classes.add(c) : this.classes.delete(c); },
    };
  }
  set textContent(v) { this._text = String(v); } get textContent() { return this._text; }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  appendChild(c) { this.children.push(c); return c; }
  addEventListener(type, fn) { this.listeners[type] = fn; }
  select() { this.selected = true; }
  remove() { this.removed = true; }
  hasClass(c) { return this.className.split(/\s+/).includes(c); }
  querySelector(sel) {
    const cls = sel.replace('.', '');
    for (const child of this.children) {
      if (child.hasClass(cls)) return child;
      const deeper = child.querySelector(sel);
      if (deeper) return deeper;
    }
    return null;
  }
}

const body = new Element('body');
const context = {
  console: { error() {}, log() {} },
  setInterval() { return 0; }, clearInterval() {},
  setTimeout(fn, ms) { log.timers.push({ fn, ms }); return log.timers.length; },
  clearTimeout(id) { log.cleared.push(id); },
  window: {},
  document: {
    body,
    addEventListener() {},
    createElement(tag) { const e = new Element(tag); if (tag === 'textarea') log.textareas.push(e); return e; },
    execCommand(cmd) {
      log.execCalls.push({ cmd, selected: log.textareas.length ? log.textareas[log.textareas.length - 1].selected : null,
                           value: log.textareas.length ? log.textareas[log.textareas.length - 1].value : null });
      if (scenario.execThrows) throw new Error('not allowed');
      return scenario.execResult !== false;
    },
  },
  navigator: {},
};
if (scenario.clipboard) {
  context.navigator.clipboard = {
    writeText: async (t) => { log.writes.push(t); if (scenario.clipboard === 'reject') throw new Error('denied'); },
  };
}
vm.createContext(context);
const api = vm.runInContext(source + '\n;({ copyToClipboard, attachCopyButton, COPY_LABELS, COPY_FEEDBACK_MS })', context);

(async () => {
  const out = {};
  if (scenario.mode === 'copy') {
    out.result = await api.copyToClipboard(scenario.text);
  } else {
    const message = new Element('div');
    message.dataset.raw = scenario.raw;
    const fakeCopy = async (text) => { log.copyCalls.push(text); return scenario.copyResult !== false; };
    const button = api.attachCopyButton(message, fakeCopy);
    out.created = !!button;
    out.childCount = message.children.length;
    if (button) {
      const actions = message.children[0];
      out.actions = { className: actions.className, aria: actions.attrs['aria-live'] };
      out.button = { type: button.type, className: button.className, title: button.title, aria: button.attrs['aria-label'], label: button.textContent };
      out.again = !!api.attachCopyButton(message, fakeCopy);          // a second call must not add another
      out.childCountAfterSecond = message.children.length;
      for (const step of scenario.steps || []) {
        if (step.setRaw !== undefined) message.dataset.raw = step.setRaw;
        if (step.click) await button.listeners.click();
        if (step.runTimer) log.timers[log.timers.length - 1].fn();
        (out.snapshots = out.snapshots || []).push({ label: button.textContent, classes: [...button.classes].sort() });
      }
    }
    out.copyCalls = log.copyCalls;
    out.timerDelays = log.timers.map(t => t.ms);
    out.cleared = log.cleared;
    out.labels = api.COPY_LABELS;
  }
  out.writes = log.writes;
  out.execCalls = log.execCalls;
  out.textareas = log.textareas.map(t => ({ value: t.value, readonly: 'readonly' in t.attrs, removed: t.removed, selected: !!t.selected, offscreen: /-9999px/.test(t.style.cssText || '') }));
  out.bodyChildren = body.children.length;
  console.log(JSON.stringify(out));
})();
"""


def run(**scenario):
    done = subprocess.run(
        ["node", "-e", HARNESS, str(ROOT / "static" / "text-display-enhancements.js"), json.dumps(scenario)],
        capture_output=True, text=True, timeout=30,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


class TestCopyToClipboard:
    def test_uses_the_clipboard_api_when_it_exists(self):
        out = run(mode="copy", text="hello **world**", clipboard=True)
        assert out["result"] is True and out["writes"] == ["hello **world**"]
        assert out["textareas"] == [] and out["execCalls"] == []            # the fallback is not touched

    def test_falls_back_to_a_textarea_where_there_is_no_clipboard_api(self):
        # http:// on a network address: navigator.clipboard is undefined there
        out = run(mode="copy", text="plain http page")
        assert out["result"] is True
        (area,) = out["textareas"]
        assert area["value"] == "plain http page" and area["selected"] and area["readonly"] and area["offscreen"]
        assert out["execCalls"] == [{"cmd": "copy", "selected": True, "value": "plain http page"}]

    def test_falls_back_when_the_clipboard_api_refuses(self):
        out = run(mode="copy", text="refused", clipboard="reject")
        assert out["result"] is True and out["writes"] == ["refused"] and len(out["execCalls"]) == 1

    def test_the_helper_textarea_is_always_removed(self):
        for scenario in ({}, {"execResult": False}, {"execThrows": True}):
            out = run(mode="copy", text="x", **scenario)
            assert all(t["removed"] for t in out["textareas"]), scenario

    def test_reports_failure_when_nothing_works(self):
        assert run(mode="copy", text="x", execResult=False)["result"] is False
        assert run(mode="copy", text="x", execThrows=True)["result"] is False
        assert run(mode="copy", text="x", clipboard="reject", execResult=False)["result"] is False

    def test_text_is_copied_exactly(self):
        text = "line one\n\n```python\nprint('<b>')\n```\n| a | b |\n|---|---|\n日本語 🎉"
        assert run(mode="copy", text=text, clipboard=True)["writes"] == [text]
        assert run(mode="copy", text=text)["textareas"][0]["value"] == text


class TestCopyButton:
    def test_a_reply_gets_one_accessible_button(self):
        out = run(mode="attach", raw="The answer is 4.")
        assert out["created"] and out["childCount"] == 1
        assert out["actions"] == {"className": "message-actions", "aria": "polite"}
        assert out["button"] == {
            "type": "button", "className": "copy-btn", "title": "Copy this response",
            "aria": "Copy this response to the clipboard", "label": out["labels"]["idle"],
        }

    def test_never_a_second_button(self):
        out = run(mode="attach", raw="text")
        assert out["again"] is False and out["childCountAfterSecond"] == 1

    @pytest.mark.parametrize("raw", ["", "   ", "\n\n\t"])
    def test_an_empty_reply_gets_no_button(self, raw):
        out = run(mode="attach", raw=raw)
        assert out["created"] is False and out["childCount"] == 0

    def test_click_copies_the_original_text_and_confirms(self):
        raw = "**List**\n\n* one\n* two"
        out = run(mode="attach", raw=raw, steps=[{"click": True}])
        assert out["copyCalls"] == [raw]
        assert out["snapshots"][0] == {"label": out["labels"]["copied"], "classes": ["copied"]}

    def test_the_confirmation_goes_away(self):
        out = run(mode="attach", raw="x", steps=[{"click": True}, {"runTimer": True}])
        assert out["timerDelays"] == [1800]
        assert out["snapshots"][1] == {"label": out["labels"]["idle"], "classes": []}

    def test_a_failed_copy_is_shown_not_hidden(self):
        out = run(mode="attach", raw="x", copyResult=False, steps=[{"click": True}, {"runTimer": True}])
        assert out["snapshots"][0] == {"label": out["labels"]["failed"], "classes": ["failed"]}
        assert out["snapshots"][1] == {"label": out["labels"]["idle"], "classes": []}   # it resets, so it can be tried again

    def test_a_second_click_restarts_the_timer(self):
        out = run(mode="attach", raw="x", steps=[{"click": True}, {"click": True}])
        assert len(out["timerDelays"]) == 2
        assert [c for c in out["cleared"] if c is not None] == [1]           # the first timer was cancelled

    def test_it_copies_whatever_the_reply_text_is_at_click_time(self):
        out = run(mode="attach", raw="first", steps=[{"setRaw": "second", "click": True}])
        assert out["copyCalls"] == ["second"]

    def test_labels_say_what_happened(self):
        labels = run(mode="attach", raw="x")["labels"]
        assert "Copy" in labels["idle"] and "Copied" in labels["copied"] and "Could not copy" in labels["failed"]


class TestWiring:
    """The button must be added in exactly the two places an assistant reply is finished"""

    source = (ROOT / "static" / "text-display-enhancements.js").read_text()

    def test_added_for_finished_assistant_messages_only(self):
        add = self.source[self.source.index("chatView.addMessage = "):self.source.index("chatView.appendTokenToLastMessage = ")]
        assert "role === 'assistant'" in add and "if (!streaming) attachCopyButton(messageDiv)" in add

    def test_added_when_a_streamed_reply_completes_with_its_raw_text(self):
        finish = self.source[self.source.index("chatView.finishStreaming = "):]
        assert "dataset.raw = rawContent" in finish and "attachCopyButton(streamingMessage)" in finish

    def test_the_style_hides_it_while_streaming_and_shows_it_on_touch_screens(self):
        css = (ROOT / "static" / "styles.css").read_text()
        assert ".message.streaming .message-actions" in css and "@media (hover: none)" in css
        assert ".message-actions:focus-within" in css                              # reachable by keyboard
