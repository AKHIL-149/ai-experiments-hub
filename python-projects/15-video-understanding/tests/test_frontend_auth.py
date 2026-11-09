"""
The sign-in page (frontend/login.js) and the sign-in handling in frontend/app.js, run in node against a stub
DOM, stub fetch and a stub location (skipped when node is not installed).

What they pin down: a hostile server message or display name stays text, a "next" address can only lead to a
path on this site (never "//evil.example"), a 401 anywhere sends the person to the sign-in page, and the page
offers only what the server allows.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[1] / "frontend"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

HARNESS = r"""
const vm = require('vm'), fs = require('fs');
const input = JSON.parse(process.argv[process.argv.length - 1]);
const elements = {}, created = [], calls = [], redirects = [], timers = [];

function el(id) {
  const e = {id, innerHTML: '', textContent: '', outerHTML: '', value: '', style: {}, dataset: {}, children: [], hidden: false,
    disabled: false, listeners: {}, attrs: {}, href: '', type: '', autocomplete: '',
    classList: {add() {}, remove() {}, toggle() {}},
    appendChild(c) { this.children.push(c); return c; }, append(...c) { this.children.push(...c); },
    remove() {}, scrollIntoView() {}, setAttribute(k, v) { this.attrs[k] = v; },
    querySelector() { return null; }, querySelectorAll() { return []; },
    addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }};
  return e;
}
const document = {
  addEventListener() {}, querySelectorAll() { return []; }, querySelector() { return null; },
  getElementById(id) { return elements[id] || (elements[id] = el(id)); },
  createElement(tag) { const e = el(tag); e.tag = tag; created.push(e); return e; },
};
const location = {origin: 'http://localhost:8000', pathname: input.path || '/', search: input.search || '', hash: input.hash || '',
  replace(url) { redirects.push(url); }, set href(v) { redirects.push(v); }};

const ctx = {
  document, location, window: {location}, console: {log() {}, error() {}, warn() {}},
  URLSearchParams, encodeURIComponent, setTimeout(fn, ms) { timers.push(ms); return timers.length; }, clearTimeout() {}, WebSocket: function () { this.close = () => {}; },
  confirm: () => true, alert() {}, URL, Date, Math, JSON, Number, String, Promise, parseFloat, isNaN, Object, Array, RegExp,
  fetch: async (url, options) => {
    calls.push({url: String(url), method: (options && options.method) || 'GET', body: options && options.body, credentials: options && options.credentials});
    const hit = input.routes.find(([part]) => String(url).includes(part));
    const [, status, body] = hit || [null, 200, {}];
    return {ok: status >= 200 && status < 300, status, json: async () => body};
  },
};
ctx.window.document = document;
vm.createContext(ctx);

const run = async () => {
  for (const file of input.files) vm.runInContext(fs.readFileSync(file, 'utf8'), ctx);
  await new Promise(r => setImmediate(r));
  await new Promise(r => setImmediate(r));
  await vm.runInContext('(async () => {' + input.script + '})()', ctx);
  await new Promise(r => setImmediate(r));
  const out = {redirects, calls, timers, byId: {}, created: created.map(c => ({tag: c.tag, textContent: c.textContent, innerHTML: c.innerHTML, href: c.href, type: c.type,
    listeners: Object.keys(c.listeners)}))};
  for (const [id, e] of Object.entries(elements)) out.byId[id] = {innerHTML: e.innerHTML, textContent: e.textContent, hidden: e.hidden, disabled: e.disabled,
    listeners: Object.keys(e.listeners), children: e.children.map(k => ({tag: k.tag, textContent: k.textContent, innerHTML: k.innerHTML, href: k.href}))};
  console.log(JSON.stringify(out));
};
// helper for scripts: fire the handlers registered on an element
ctx.fire = async (id, type, event) => { for (const fn of (elements[id].listeners[type] || [])) await fn(event || {preventDefault() {}}); await new Promise(r => setImmediate(r)); };
run().catch(e => { console.error(e); process.exit(1); });
"""


def run(files, routes, script="", path="/", search="", hash=""):
    payload = json.dumps({"files": [str(FRONTEND / f) for f in files], "routes": routes, "script": script,
                          "path": path, "search": search, "hash": hash})
    result = subprocess.run(["node", "-e", HARNESS, payload], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


CONFIG = {"registration": True, "guests": True, "guest_ttl_hours": 24, "guest_max_videos": 3, "min_password": 8}
SIGNED_OUT = ["/api/auth/me", 401, {"detail": "Not signed in"}]


def login_routes(**extra):
    return [["/api/auth/config", 200, {**CONFIG, **extra.pop("config", {})}], SIGNED_OUT,
            *extra.pop("more", [])]


class TestLoginPage:
    def test_the_form_is_shown_and_wired_when_nobody_is_signed_in(self):
        page = run(["login.js"], login_routes())
        assert page["redirects"] == []
        assert "submit" in page["byId"]["login-form"]["listeners"]
        assert page["byId"]["guest-box"]["hidden"] is False
        assert "3 videos" in page["byId"]["guest-note"]["textContent"] and "24 hours" in page["byId"]["guest-note"]["textContent"]

    def test_someone_already_signed_in_goes_straight_on(self):
        page = run(["login.js"], [["/api/auth/config", 200, CONFIG], ["/api/auth/me", 200, {"username": "ann"}]], search="?next=/videos")
        assert page["redirects"] == ["/videos"]

    def test_only_what_the_server_allows_is_offered(self):
        page = run(["login.js"], login_routes(config={"registration": False, "guests": False}))
        assert page["byId"]["tab-register"]["hidden"] is True
        # the box starts hidden in the HTML; the script must not reveal it
        assert page["byId"].get("guest-box", {"hidden": True})["hidden"] is True

    @pytest.mark.parametrize("next_value,expected", [
        ("/videos", "/videos"), ("/", "/"), ("/?x=1#a", "/?x=1#a"),
        ("//evil.example", "/"), ("//evil.example/path", "/"), ("https://evil.example", "/"), ("http://evil.example/", "/"),
        ("/\\evil.example", "/"), ("javascript:alert(1)", "/"), ("evil.example", "/"), ("", "/"), ("\\\\evil.example", "/"),
    ])
    def test_after_signing_in_only_a_path_on_this_site_is_followed(self, next_value, expected):
        from urllib.parse import quote
        script = "await fire('login-form', 'submit');"
        page = run(["login.js"], login_routes(more=[["/api/auth/login", 200, {"username": "ann"}]]), script,
                   search="?next=" + quote(next_value, safe=""))
        assert page["redirects"] == [expected]

    def test_sign_in_posts_the_form_with_same_origin_cookies(self):
        script = ("document.getElementById('username').value = 'ann'; document.getElementById('password').value = 'pw12345678';"
                  "await fire('login-form', 'submit');")
        page = run(["login.js"], login_routes(more=[["/api/auth/login", 200, {"username": "ann"}]]), script)
        post = [c for c in page["calls"] if c["url"].endswith("/api/auth/login")][0]
        assert post["method"] == "POST" and post["credentials"] == "same-origin"
        assert json.loads(post["body"])["username"] == "ann" and json.loads(post["body"])["password"] == "pw12345678"

    def test_register_tab_posts_to_register_with_the_display_name(self):
        script = ("await fire('tab-register', 'click');"
                  "document.getElementById('username').value = 'ann'; document.getElementById('password').value = 'pw12345678';"
                  "document.getElementById('display-name').value = 'Ann B';"
                  "await fire('login-form', 'submit');")
        page = run(["login.js"], login_routes(more=[["/api/auth/register", 200, {"username": "ann"}]]), script)
        post = [c for c in page["calls"] if "/api/auth/" in c["url"] and c["method"] == "POST"][0]
        assert post["url"].endswith("/api/auth/register") and json.loads(post["body"])["display_name"] == "Ann B"
        assert page["byId"]["submit"]["textContent"] == "Create account"

    def test_guest_button_starts_a_guest_session(self):
        page = run(["login.js"], login_routes(more=[["/api/auth/guest", 200, {"username": "guest-1"}]]),
                   "await fire('guest-btn', 'click');", search="?next=/videos")
        assert [c["url"] for c in page["calls"] if c["method"] == "POST"] == ["/api/auth/guest"]
        assert page["redirects"] == ["/videos"]

    def test_an_error_from_the_server_is_shown_as_text_never_as_html(self):
        hostile = '<img src=x onerror="PWN()">'
        page = run(["login.js"], login_routes(more=[["/api/auth/login", 401, {"detail": hostile}]]),
                   "await fire('login-form', 'submit');")
        error = page["byId"]["login-error"]
        assert error["textContent"] == hostile and error["innerHTML"] == "" and error["hidden"] is False
        assert page["redirects"] == [] and page["byId"]["submit"]["disabled"] is False

    def test_an_unreadable_error_gets_a_plain_message(self):
        page = run(["login.js"], login_routes(more=[["/api/auth/login", 500, {"detail": [{"msg": "x"}]}]]),
                   "await fire('login-form', 'submit');")
        assert page["byId"]["login-error"]["textContent"] == "Something went wrong, please try again"

    def test_the_button_cannot_be_pressed_twice_while_a_sign_in_is_running(self):
        page = run(["login.js"], login_routes(more=[["/api/auth/login", 200, {"username": "ann"}]]),
                   "await fire('login-form', 'submit');")
        assert page["byId"]["submit"]["disabled"] is True  # stays disabled while the page navigates away


class TestAppSignIn:
    def test_a_401_sends_the_person_to_sign_in_and_back_afterwards(self):
        page = run(["app.js"], [["/api/videos", 401, {"detail": "Not signed in"}]],
                   "try { await apiCall('/api/videos'); } catch (e) {}", path="/", search="?q=1", hash="#videos")
        assert page["redirects"] == ["/login?next=" + "%2F%3Fq%3D1%23videos"]

    def test_the_login_page_does_not_redirect_to_itself(self):
        page = run(["app.js"], [["/api/videos", 401, {}]], "try { await apiCall('/api/videos'); } catch (e) {}", path="/login")
        assert page["redirects"] == []

    def test_other_errors_do_not_redirect(self):
        page = run(["app.js"], [["/api/videos", 500, {"detail": "boom"}]], "try { await apiCall('/api/videos'); } catch (e) {}")
        assert page["redirects"] == []

    def test_requests_carry_the_cookie(self):
        page = run(["app.js"], [["/api/videos", 200, {"videos": []}]], "await apiCall('/api/videos');")
        assert page["calls"][0]["credentials"] == "include"

    def test_the_header_shows_the_name_as_text_and_offers_sign_out(self):
        hostile = '<img src=x onerror="PWN()">'
        page = run(["app.js"], [["/api/auth/me", 200, {"username": "ann", "display_name": hostile, "is_guest": False}]],
                   "await loadCurrentUser();")
        chip = page["byId"]["user-chip"]
        assert chip["children"][0]["textContent"] == hostile and chip["children"][0]["innerHTML"] == ""
        assert [c["textContent"] for c in chip["children"]] == [hostile, "Sign out"]
        assert page["byId"].get("guest-banner", {"textContent": ""})["textContent"] == ""

    def test_guests_are_told_their_videos_expire(self):
        page = run(["app.js"], [["/api/auth/me", 200, {"username": "guest-1", "display_name": "Guest", "is_guest": True, "guest_ttl_hours": 12}]],
                   "await loadCurrentUser();")
        banner = page["byId"]["guest-banner"]
        assert banner["hidden"] is False and "12 hours" in banner["textContent"]
        assert banner["children"][0]["textContent"] == "Create an account to keep them"

    def test_accounts_get_no_guest_banner(self):
        page = run(["app.js"], [["/api/auth/me", 200, {"username": "ann", "is_guest": False}]], "await loadCurrentUser();")
        assert page["byId"].get("guest-banner", {"textContent": ""})["textContent"] == ""

    def test_single_user_mode_has_no_sign_out(self):
        page = run(["app.js"], [["/api/auth/me", 200, {"username": "local", "display_name": "Local user", "local_mode": True}]],
                   "await loadCurrentUser();")
        assert [c["textContent"] for c in page["byId"]["user-chip"]["children"]] == ["Local user"]

    def test_signing_out_posts_to_logout_and_leaves(self):
        page = run(["app.js"], [["/api/auth/me", 200, {"username": "ann", "is_guest": False}], ["/api/auth/logout", 200, {"success": True}]],
                   "await loadCurrentUser(); document.getElementById('user-chip').children[1].listeners.click[0]();")
        logout = [c for c in page["calls"] if c["url"].endswith("/api/auth/logout")]
        assert logout and logout[0]["method"] == "POST" and logout[0]["credentials"] == "include"
        assert page["redirects"] == ["/login"]

    def test_a_401_on_me_goes_to_sign_in(self):
        page = run(["app.js"], [["/api/auth/me", 401, {}]], "await loadCurrentUser();", path="/videos")
        assert page["redirects"] == ["/login?next=%2Fvideos"]
