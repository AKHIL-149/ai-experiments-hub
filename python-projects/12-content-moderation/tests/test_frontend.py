"""
static/js/app.js, run in Node with a small fake DOM (so these check the script's logic, not how the page looks).

Found in the page: the text a user typed, file names, user names and e-mails went into innerHTML unescaped
(shown in their own list AND in the moderators' queue and the admin user list); a refused submission lost the
typed text; every visit to "My Content" added another copy of the filter listeners; results arrived
without the list ever updating; users were offered the critical priority the server refuses; and nothing
said that no worker was running.
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
// the script ends by creating the app, which would start talking to the server: leave that line out
const source = fs.readFileSync(process.argv[2], 'utf8').replace('const app = new ContentModerationApp();', '');

class Element {
  constructor(id) {
    this.id = id; this.children = []; this.style = {}; this.value = ''; this._html = ''; this.textContent = '';
    this.listeners = []; this.className = ''; this.siblings = [];
  }
  set innerHTML(v) { this._html = v; } get innerHTML() { return this._html; }
  addEventListener(t, fn) { this.listeners.push(t); }
  before(el) { this.siblings.push(el); byId[el.id] = el; }  // inserting it into the page makes it findable
  remove() { this.removed = true; }
}
const byId = {}, optionLists = [];
const el = id => byId[id] || (byId[id] = new Element(id));
const alerts = [], timers = [], cleared = [];
let fetchPlan = [];
const fetches = [];

const context = {
  console: { error() {}, log() {} },
  alert: m => alerts.push(m), prompt: () => null, confirm: () => true,
  setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
  clearTimeout: id => cleared.push(id),
  document: {
    getElementById: id => byId[id] || (id === 'worker-notice' ? null : el(id)),
    createElement: () => new Element(''),
    querySelectorAll: sel => { const opts = optionLists.filter(o => sel.includes(o.sel)); return { forEach: fn => opts.forEach(fn), length: opts.length }; },
    addEventListener() {},
  },
  window: { location: { href: 'http://localhost:7000/' } },
  fetch: async (url, opts) => {
    fetches.push({ url, opts });
    const next = fetchPlan.shift() || { ok: true, body: {} };
    return { ok: next.ok !== false, status: next.status || 200, json: async () => next.body };
  },
  FormData: class { constructor() { this.entries = []; } append(k, v) { this.entries.push([k, v]); } },
};
vm.createContext(context);
vm.runInContext(source + '\n;globalThis.ContentModerationApp = ContentModerationApp;', context);
const app = Object.create(context.ContentModerationApp.prototype);
app.currentUser = { username: 'u', role: 'user' }; app.currentView = 'my-content';
const h = { app, el, alerts, timers, cleared, fetches, byId, context, optionLists, setFetchPlan: p => { fetchPlan = p; } };
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
(async () => { console.log(JSON.stringify(await new AsyncFunction('h', scenario.code)(h))); })()
  .catch(e => console.log(JSON.stringify({ crash: String(e && e.stack || e) })));
"""


def run(code):
    done = subprocess.run(["node", "-e", HARNESS, json.dumps({"code": code}), str(ROOT / "static" / "js" / "app.js")],
                          capture_output=True, text=True, timeout=30)
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout)
    assert "crash" not in out, out["crash"]
    return out


EVIL = "<img src=x onerror=alert(1)>"


class TestEscaping:
    def test_escape_covers_quotes(self):
        out = run("""return { a: h.app.escapeHtml('<b>"x" & \\'y\\'</b>'), n: h.app.escapeHtml(null), num: h.app.escapeHtml(0) };""")
        assert out == {"a": "&lt;b&gt;&quot;x&quot; &amp; &#39;y&#39;&lt;/b&gt;", "n": "", "num": "0"}

    def test_a_text_item_is_escaped(self):
        out = run(f"""
          const item = {{ id: 'i1', content_type: 'text', status: 'processing', priority: 0, created_at: '2026-01-01', text_content: {json.dumps(EVIL + ' hello')} }};
          return {{ html: h.app.renderContentItem(item) }};
        """)
        assert "<img" not in out["html"] and "&lt;img" in out["html"] and "hello" in out["html"]

    def test_a_file_name_the_classification_and_ids_are_escaped(self):
        out = run(f"""
          const item = {{ id: '"><script>x</script>', content_type: 'image', status: 'flagged', priority: 5, created_at: '2026-01-01',
                         file_path: 'data/uploads/{EVIL}.png',
                         classifications: [{{ category: {json.dumps(EVIL)}, confidence: 0.5, provider: '<b>p</b>' }}] }};
          return {{ html: h.app.renderContentItem(item, true) }};
        """)
        for tag in ("<img", "<script", "<b>"):
            assert tag not in out["html"], tag

    def test_a_status_or_priority_cannot_carry_markup(self):
        out = run("""
          const item = { id: 'i', content_type: 'text', status: 'x"><svg onload=1>', priority: '9<script>', created_at: '2026-01-01', text_content: 't' };
          return { html: h.app.renderContentItem(item) };
        """)
        assert "<svg" not in out["html"] and "<script" not in out["html"]

    def test_the_appeal_button_is_only_on_rejected_content_in_the_users_list(self):
        out = run("""
          const base = { id: 'i1', content_type: 'text', priority: 0, created_at: '2026-01-01', text_content: 't' };
          return { rejected: h.app.renderContentItem({ ...base, status: 'rejected' }).includes('appealContent'),
                   approved: h.app.renderContentItem({ ...base, status: 'approved' }).includes('appealContent'),
                   queue: h.app.renderContentItem({ ...base, status: 'rejected' }, true).includes('appealContent') };
        """)
        assert out == {"rejected": True, "approved": False, "queue": False}

    def test_user_names_and_emails_in_the_admin_list_are_escaped(self):
        out = run(f"""
          return {{ html: h.app.renderUserItem({{ id: 'u1', username: {json.dumps(EVIL)}, email: '<i>e</i>@x.y', role: 'user', is_active: true }}) }};
        """)
        assert "<img" not in out["html"] and "<i>" not in out["html"] and "&lt;img" in out["html"]


class TestSubmitting:
    SETUP = """
      h.el('text-content').value = 'my carefully written text'; h.el('text-priority').value = '0';
      h.el('submit-error'); h.el('submit-success');
    """

    def test_an_accepted_text_clears_the_form(self):
        out = run(self.SETUP + """
          h.setFetchPlan([{ ok: true, body: { message: 'Content submitted' } }]);
          await h.app.submitText();
          return { text: h.el('text-content').value, success: h.el('submit-success').textContent };
        """)
        assert out == {"text": "", "success": "Content submitted"}

    @pytest.mark.parametrize("plan,message", [
        ("{ ok: false, status: 400, body: { detail: 'Text is too long (20000 characters, the limit is 10000)' } }", "Text is too long"),
        ("{ ok: false, status: 429, body: { error: 'Rate limit exceeded', detail: 'Too many requests. Retry after 5 seconds.' } }", "Too many requests"),
        ("{ ok: false, status: 403, body: { detail: 'Critical priority is reserved for moderators' } }", "reserved for moderators"),
    ])
    def test_a_refused_text_is_kept_and_the_reason_shown(self, plan, message):
        out = run(self.SETUP + f"""
          h.setFetchPlan([{plan}]);
          await h.app.submitText();
          return {{ text: h.el('text-content').value, error: h.el('submit-error').textContent }};
        """)
        assert out["text"] == "my carefully written text" and message in out["error"]

    def test_a_network_failure_keeps_the_text_too(self):
        out = run(self.SETUP + """
          h.context.fetch = async () => { throw new Error('offline'); };
          await h.app.submitText();
          return { text: h.el('text-content').value, error: h.el('submit-error').textContent };
        """)
        assert out["text"] == "my carefully written text" and "Network error" in out["error"]

    def test_a_refused_image_keeps_the_selection(self):
        out = run("""
          h.el('image-file').files = [{ name: 'x.png' }]; h.el('image-file').value = 'x.png'; h.el('image-priority').value = '0';
          h.el('image-preview'); h.el('submit-error'); h.el('submit-success');
          h.setFetchPlan([{ ok: false, status: 400, body: { detail: 'The file is not a valid image' } }]);
          await h.app.submitImage();
          return { value: h.el('image-file').value, error: h.el('submit-error').textContent };
        """)
        assert out == {"value": "x.png", "error": "The file is not a valid image"}

    @pytest.mark.parametrize("data,expected", [
        ({"detail": "bad"}, "bad"), ({"error": "Rate limit exceeded"}, "Rate limit exceeded"),
        ({"detail": [{"msg": "x"}]}, "fallback"), ({}, "fallback"), (None, "fallback"),
    ])
    def test_error_text_is_always_a_string(self, data, expected):
        assert run(f"return {{ v: h.app.errorText({json.dumps(data)}, 'fallback') }};")["v"] == expected


class TestPriorityOptions:
    def options(self, role):
        return run(f"""
          const make = sel => ({{ sel, removed: false, remove() {{ this.removed = true; }} }});
          h.optionLists.push(make('#text-priority option[value="10"]'), make('#image-priority option[value="10"]'));
          h.app.currentUser = {{ username: 'u', role: '{role}', is_guest: false }};
          h.el('app-view'); h.el('auth-view'); h.el('user-info'); h.el('current-username'); h.el('user-role');
          try {{ h.app.updateUserInfo(); }} catch (e) {{ /* other parts need more DOM than the fake has */ }}
          return {{ removed: h.optionLists.map(o => o.removed) }};
        """)["removed"]

    def test_users_are_not_offered_the_critical_priority(self):
        assert self.options("user") == [True, True]

    @pytest.mark.parametrize("role", ["moderator", "admin"])
    def test_moderators_and_admins_are(self, role):
        assert self.options(role) == [False, False]


class TestMyContentList:
    def load(self, items, health=None, extra=""):
        return run(f"""
          h.el('content-list'); h.el('content-status-filter').value = '';
          h.setFetchPlan([{{ ok: true, body: {{ content: {json.dumps(items)} }} }}, {{ ok: true, body: {json.dumps(health or {"worker": {"available": True}})} }}]);
          await h.app.loadMyContent();
          {extra}
          return {{ timers: h.timers.map(t => t.ms), cleared: h.cleared.length,
                   notice: h.byId['worker-notice'] ? [h.byId['worker-notice'].textContent, h.byId['worker-notice'].style.display] : null,
                   filterListeners: h.el('content-status-filter').listeners.length + h.el('refresh-content-btn').listeners.length,
                   urls: h.fetches.map(f => f.url) }};
        """)

    PROCESSING = [{"id": "a", "content_type": "text", "status": "processing", "priority": 0, "created_at": "2026-01-01", "text_content": "t"}]
    DONE = [{"id": "a", "content_type": "text", "status": "approved", "priority": 0, "created_at": "2026-01-01", "text_content": "t"}]

    def test_the_list_refreshes_itself_while_something_is_processing(self):
        assert self.load(self.PROCESSING)["timers"] == [4000]

    def test_it_stops_when_everything_is_decided(self):
        assert self.load(self.DONE)["timers"] == []

    def test_pending_counts_as_waiting_too(self):
        items = [{**self.PROCESSING[0], "status": "pending"}]
        assert self.load(items)["timers"] == [4000]

    def test_the_refresh_stops_when_the_user_leaves_the_page(self):
        out = run(f"""
          h.el('content-list'); h.el('content-status-filter').value = '';
          h.app.currentView = 'submit';
          h.setFetchPlan([{{ ok: true, body: {{ content: {json.dumps(self.PROCESSING)} }} }}]);
          await h.app.loadMyContent();
          return {{ timers: h.timers.length }};
        """)
        assert out["timers"] == 0

    def test_a_pending_refresh_is_cancelled_when_the_list_is_loaded_again(self):
        assert self.load(self.PROCESSING, extra="h.app.contentRefreshTimer = 7; h.setFetchPlan([{ok:true, body:{content:[]}}]); await h.app.loadMyContent();")["cleared"] >= 1

    def test_loading_the_list_does_not_add_listeners(self):
        assert self.load(self.PROCESSING)["filterListeners"] == 0       # they were added here on every visit

    def test_the_listeners_are_added_once_at_start_up(self):
        out = run("""
          h.el('content-status-filter'); h.el('refresh-content-btn');
          h.app.setupListFilterListeners();
          return { n: h.el('content-status-filter').listeners.length + h.el('refresh-content-btn').listeners.length };
        """)
        assert out["n"] == 2

    def test_start_up_sets_the_listeners_up(self):
        out = run("""
          const called = [];
          for (const name of ['checkAuth', 'setupAuthListeners', 'setupNavigationListeners', 'setupSubmitListeners', 'setupListFilterListeners', 'setupModalListeners']) {
            h.app[name] = async () => { called.push(name); };
          }
          await h.app.init();
          return { called };
        """)
        assert "setupListFilterListeners" in out["called"] and len(out["called"]) == 6

    def test_no_worker_is_said_when_something_is_waiting(self):
        out = self.load(self.PROCESSING, health={"worker": {"available": False, "workers": 0}})
        assert out["notice"][1] == "block" and "No moderation worker is running" in out["notice"][0]

    def test_a_running_worker_gives_no_notice(self):
        assert self.load(self.PROCESSING, health={"worker": {"available": True, "workers": 1}})["notice"][1] == "none"

    def test_nothing_waiting_means_no_health_request(self):
        assert "/api/health" not in self.load(self.DONE)["urls"]
