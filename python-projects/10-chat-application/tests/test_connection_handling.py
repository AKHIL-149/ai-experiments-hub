"""
What the page does when the WebSocket is not usable, and how it shows image generation.

The real static/app.js and static/voice-and-image-features.js run in Node with a small fake DOM.
Found in the code: sending on a socket that was still connecting threw after the question and an empty
reply bubble were already on screen; on a closed one the message was dropped silently; a second message
sent while a reply streamed made a second placeholder tokens never reached; a connection that dropped
mid-reply left the bubble "typing" forever; a failed delete removed the conversation from the list
anyway; and the "Generating image..." bubble stayed above the finished image.
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
const files = process.argv.slice(2);

class Element {
  constructor(tag, id) {
    this.tagName = tag.toUpperCase(); this.id = id || ''; this.children = []; this.listeners = {};
    this.style = {}; this.className = ''; this._text = ''; this.removed = false; this.value = '';
    this.classes = new Set(); this.parent = null;
    const owner = this;
    this.classList = {
      add: (...c) => c.forEach(x => owner.classes.add(x)),
      remove: (...c) => c.forEach(x => owner.classes.delete(x)),
      contains: c => owner.classes.has(c) || owner.className.split(/\s+/).includes(c),
    };
  }
  set textContent(v) { this._text = String(v); } get textContent() { return this._text; }
  set innerHTML(v) { this._html = v; if (v === '') this.children = []; else {
      // the two-part message markup used by addMessage/showError: pull out the content text
      const m = /message-content">([^<]*)</.exec(v); this._text = m ? m[1] : ''; } }
  get innerHTML() { return this._html || ''; }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  append(...cs) { cs.forEach(c => typeof c === 'string' ? null : this.appendChild(c)); }
  addEventListener(t, fn) { this.listeners[t] = fn; }
  remove() { this.removed = true; if (this.parent) this.parent.children = this.parent.children.filter(c => c !== this); }
  hasClass(c) { return this.className.split(/\s+/).includes(c) || this.classes.has(c); }
  get isStreaming() { return this.hasClass('streaming'); }
  querySelector(sel) {
    const cls = sel.replace(/^\./, '').split('.');
    const matches = el => cls.every(c => el.hasClass(c));
    for (const child of this.children) {
      if (matches(child)) return child;
      const deeper = child.querySelector(sel); if (deeper) return deeper;
    }
    if (this._contentChild && sel === '.message-content') return this._contentChild;
    return null;
  }
  querySelectorAll() { return this.children; }
}

const byId = {};
function el(id) { return byId[id] || (byId[id] = new Element('div', id)); }
const alerts = [];
let fetchPlan = [];
const fetchCalls = [];

// A message element carries its own .message-content child so tokens can be appended
function makeMessage(html) {
  const div = new Element('div');
  const content = new Element('div'); content.className = 'message-content';
  const m = /message-content">([^<]*)</.exec(html || ''); content._text = m ? m[1] : '';
  div.children.push(content); content.parent = div;
  return div;
}

class FakeSocket {
  constructor(url) { this.url = url; this.readyState = 0; this.sent = []; FakeSocket.all.push(this); }
  send(data) { if (this.readyState === 0) throw new Error('InvalidStateError'); this.sent.push(data); }
  close() { this.readyState = 3; this.closedByCode = true; }
}
FakeSocket.all = [];

const context = {
  console: { error() {}, log() {} },
  setTimeout(fn) { return 0; },
  alert: m => alerts.push(m),
  confirm: () => true,
  WebSocket: FakeSocket,
  window: { location: { protocol: 'http:', host: 'localhost:8000' }, chatApp: null },
  document: {
    getElementById: id => el(id),
    createElement(tag) {
      const e = new Element(tag);
      Object.defineProperty(e, 'innerHTML', { set(v) { this._html = v; if (v === '') this.children = []; else if (/message-content/.test(v)) { this.children = makeMessage(v).children; this.children.forEach(c => c.parent = this); } }, get() { return this._html || ''; } });
      return e;
    },
    addEventListener() {},
    head: { appendChild() {} },
    querySelector: () => null,
  },
  fetch: async (url, opts) => {
    fetchCalls.push({ url, opts });
    const next = fetchPlan.shift() || { ok: true, status: 200, body: {} };
    return { ok: next.ok, status: next.status, json: async () => next.body };
  },
};
// container.querySelector('.message.streaming') and '.message-content' work through the tree
context.window.chatApp = null;
vm.createContext(context);
// top-level `class` declarations are not properties of the context: publish the ones the tests use
const EXPORT = ";['ChatView','ConversationManager','ImageGenerationManager'].forEach(n => { try { globalThis[n] = eval(n); } catch (e) {} });";
for (const f of files) vm.runInContext(fs.readFileSync(f, 'utf8') + EXPORT, context, { filename: f });
module.exports = { context, el, alerts, FakeSocket, fetchCalls, setFetchPlan: p => { fetchPlan = p; }, Element, makeMessage };

const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
const run = new AsyncFunction('h', scenario.code);
(async () => { const out = await run(module.exports); console.log(JSON.stringify(out)); })().catch(e => { console.log(JSON.stringify({ crash: String(e && e.stack || e) })); });
"""


def run(code, *files):
    scripts = files or ("app.js",)
    done = subprocess.run(
        ["node", "-e", HARNESS, json.dumps({"code": code})] + [str(ROOT / "static" / f) for f in scripts],
        capture_output=True, text=True, timeout=30,
    )
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert "crash" not in out, out["crash"]
    return out


# A chat view wired to a fake app, with a conversation open
SETUP = r"""
const { context, el } = h;
const app = {
  currentConversation: { id: 'c1', messages: [] }, websocket: null, currentUser: { username: 'u' },
  conversationManager: { loadConversations() {}, conversations: [] },
  shown: [],
  showAuthInterface() { this.shown.push('auth'); },
};
const view = new context.ChatView(app);
// tests need a real message tree: build it through the page's own addMessage
view.addMessage = function (role, content, streaming = false) {
  const div = h.makeMessage('message-content">' + content + '<');
  div.className = 'message ' + role + '-message' + (streaming ? ' streaming' : '');
  const container = el('message-container'); container.appendChild(div); return div;
};
view.showError = function (text) { (this.errors = this.errors || []).push(text); };
const container = el('message-container');
const messages = () => container.children.map(c => ({ cls: c.className, text: c.children[0] ? c.children[0].textContent : '' }));
"""


class TestSending:
    def test_a_message_sent_to_an_open_socket_is_shown_and_sent(self):
        out = run(SETUP + r"""
          view.connectWebSocket(); const s = h.FakeSocket.all[0]; s.readyState = 1;
          el('user-input').value = 'hello'; view.sendMessage();
          return { sent: s.sent.map(JSON.parse), input: el('user-input').value, messages: messages() };
        """)
        assert out["sent"] == [{"type": "message", "content": "hello"}]
        assert out["input"] == ""
        assert [m["cls"] for m in out["messages"]] == ["message user-message", "message assistant-message streaming"]

    def test_a_socket_that_is_still_connecting_keeps_the_text_and_shows_nothing_broken(self):
        out = run(SETUP + r"""
          view.connectWebSocket(); // readyState stays 0 (connecting)
          el('user-input').value = 'too early'; view.sendMessage();
          return { sent: h.FakeSocket.all[0].sent, input: el('user-input').value, messages: messages(), errors: view.errors, sockets: h.FakeSocket.all.length };
        """)
        assert out["messages"] == [] and out["input"] == "too early"
        assert out["sent"] == [] and out["sockets"] == 1
        assert "Still connecting" in out["errors"][0]

    def test_with_no_socket_it_reconnects_and_keeps_the_text(self):
        out = run(SETUP + r"""
          el('user-input').value = 'hello'; view.sendMessage();
          return { sockets: h.FakeSocket.all.length, input: el('user-input').value, messages: messages(), errors: view.errors };
        """)
        assert out["sockets"] == 1 and out["input"] == "hello" and out["messages"] == []
        assert "Reconnecting" in out["errors"][0]

    def test_a_send_that_throws_leaves_no_orphan_bubbles(self):
        out = run(SETUP + r"""
          view.connectWebSocket(); const s = h.FakeSocket.all[0]; s.readyState = 1;
          s.send = () => { throw new Error('boom'); };
          el('user-input').value = 'hello'; view.sendMessage();
          return { messages: messages(), input: el('user-input').value, errors: view.errors };
        """)
        assert out["messages"] == [] and out["input"] == "hello" and "Could not send" in out["errors"][0]

    def test_nothing_is_sent_while_a_reply_is_still_streaming(self):
        out = run(SETUP + r"""
          view.connectWebSocket(); const s = h.FakeSocket.all[0]; s.readyState = 1;
          el('user-input').value = 'first'; view.sendMessage();
          el('user-input').value = 'second'; view.sendMessage();
          return { sent: s.sent.length, input: el('user-input').value, messages: messages().length };
        """)
        assert out == {"sent": 1, "input": "second", "messages": 2}

    def test_blank_input_and_no_conversation_do_nothing(self):
        out = run(SETUP + r"""
          view.connectWebSocket(); const s = h.FakeSocket.all[0]; s.readyState = 1;
          el('user-input').value = '   '; view.sendMessage();
          app.currentConversation = null; el('user-input').value = 'x'; view.sendMessage();
          return { sent: s.sent.length, messages: messages().length };
        """)
        assert out == {"sent": 0, "messages": 0}


class TestConnectionDrops:
    def test_a_connection_lost_mid_reply_ends_the_bubble_with_a_message(self):
        out = run(SETUP + r"""
          view.finishStreaming = function () { const m = container.querySelector('.message.streaming'); if (m) { m.className = 'message assistant-message'; } };
          view.connectWebSocket(); const s = h.FakeSocket.all[0]; s.readyState = 1;
          el('user-input').value = 'hi'; view.sendMessage();
          view.appendTokenToLastMessage('par');
          s.readyState = 3; s.onclose({ code: 1006, reason: '' });
          return { errors: view.errors, streaming: view.isStreaming(), socket: app.websocket, messages: messages() };
        """)
        assert "Connection lost" in out["errors"][0]
        assert out["streaming"] is False and out["socket"] is None
        assert out["messages"][-1]["text"] == "par"          # the partial text is kept

    def test_a_reply_that_had_not_started_is_removed(self):
        out = run(SETUP + r"""
          view.connectWebSocket(); const s = h.FakeSocket.all[0]; s.readyState = 1;
          el('user-input').value = 'hi'; view.sendMessage();
          s.onclose({ code: 1006, reason: '' });
          return { messages: messages() };
        """)
        assert [m["cls"] for m in out["messages"]] == ["message user-message"]

    def test_closing_on_purpose_reports_nothing(self):
        out = run(SETUP + r"""
          view.connectWebSocket(); const first = h.FakeSocket.all[0]; first.readyState = 1;
          el('user-input').value = 'hi'; view.sendMessage();
          view.connectWebSocket();                  // another conversation was opened
          first.onclose({ code: 1005, reason: '' });
          return { errors: view.errors || [], current: h.FakeSocket.all.length, same: app.websocket === h.FakeSocket.all[1] };
        """)
        assert out == {"errors": [], "current": 2, "same": True}

    def test_an_ended_session_returns_to_the_sign_in_screen(self):
        out = run(SETUP + r"""
          view.connectWebSocket(); const s = h.FakeSocket.all[0]; s.readyState = 1;
          s.onclose({ code: 1008, reason: 'Session expired' });
          return { shown: app.shown, user: app.currentUser };
        """)
        assert out == {"shown": ["auth"], "user": None}

    def test_a_refused_conversation_is_not_taken_for_a_dead_session(self):
        out = run(SETUP + r"""
          view.connectWebSocket(); const s = h.FakeSocket.all[0];
          s.onclose({ code: 1008, reason: 'Conversation not found' });
          return { shown: app.shown };
        """)
        assert out["shown"] == []


class TestDeleting:
    def manager(self, status):
        return run(r"""
          const { context, el } = h;
          const cm = new context.ConversationManager({ currentConversation: null, chatView: { clear() {} } });
          cm.conversations = [{ id: 'a', title: 'A' }, { id: 'b', title: 'B' }];
          cm.renderConversationList = () => {};
          h.setFetchPlan([{ ok: %s, status: %d, body: {} }]);
          await cm.deleteConversation('a');
          return { ids: cm.conversations.map(c => c.id), alerts: h.alerts };
        """ % (str(status < 400).lower(), status))

    def test_a_delete_that_worked_removes_it(self):
        assert self.manager(200)["ids"] == ["b"]

    def test_already_gone_counts_as_deleted(self):
        assert self.manager(404)["ids"] == ["b"]

    @pytest.mark.parametrize("status", [401, 500])
    def test_a_failed_delete_keeps_it_and_says_so(self, status):
        out = self.manager(status)
        assert out["ids"] == ["a", "b"] and "Could not delete" in out["alerts"][0]


class TestImages:
    SETUP = r"""
      const { context, el } = h;
      const added = [];
      const container = el('message-container');
      const chatView = { addMessage(role, text) {
        const div = new h.Element('div'); div.textContent = text; div.className = 'message';
        container.appendChild(div); added.push(text); return div; } };
      context.window.chatApp = { chatView };
      const manager = new context.ImageGenerationManager();
      const texts = () => container.children.map(c => c.textContent);
    """

    def test_the_generating_bubble_is_gone_once_the_image_is_shown(self):
        out = run(self.SETUP + r"""
          manager.displayGeneratedImage = (url, prompt) => { const d = new h.Element('div'); d.textContent = 'IMAGE ' + url; container.appendChild(d); };
          h.setFetchPlan([{ ok: true, status: 200, body: { image_url: '/x.png' } }]);
          await manager.generateImage('a fox');
          return { texts: texts(), generating: manager.generating };
        """, "voice-and-image-features.js")
        assert out == {"texts": ["IMAGE /x.png"], "generating": False}

    def test_a_failure_replaces_it_with_the_servers_message_only(self):
        out = run(self.SETUP + r"""
          h.setFetchPlan([{ ok: false, status: 503, body: { detail: 'Stable Diffusion dependencies not installed.' } }]);
          await manager.generateImage('a fox');
          return { texts: texts(), generating: manager.generating };
        """, "voice-and-image-features.js")
        assert out == {"texts": ["⚠️ Stable Diffusion dependencies not installed."], "generating": False}

    def test_a_second_request_is_refused_while_one_is_running(self):
        out = run(self.SETUP + r"""
          let release; h.context.fetch = () => new Promise(r => { release = () => r({ ok: true, json: async () => ({ image_url: '/a.png' }) }); });
          manager.displayGeneratedImage = () => {};
          const first = manager.generateImage('one');
          await manager.generateImage('two');
          const during = texts();
          release(); await first;
          return { during, after: texts(), generating: manager.generating };
        """, "voice-and-image-features.js")
        assert out["during"][-1].startswith("⚠️ An image is already being generated")
        assert out["generating"] is False
        assert out["after"] == [out["during"][-1]]            # loading bubble removed, warning stays
