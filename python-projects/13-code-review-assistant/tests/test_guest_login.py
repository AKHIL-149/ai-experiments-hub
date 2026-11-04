"""
"Continue as guest": POST /api/auth/guest makes a throwaway account and signs it in, the login and
register pages offer it, and the limiter that protects it counts every request (it used to store
requests under whole-second keys, so a burst inside one second counted as one).
"""

import re
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.core.auth_manager import AuthManager
from src.core.database import DatabaseManager, GUEST_EMAIL_DOMAIN, User
from src.middleware.rate_limiter import RateLimiter, RateLimitMiddleware, RATE_LIMITS

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def auth_manager():
    db = DatabaseManager('sqlite:///:memory:')
    db.init_db()
    with db.get_session() as session:
        yield AuthManager(session, session_ttl_days=30)
    db.close()


class TestGuestAccounts:
    def test_creates_a_guest_with_generated_credentials(self, auth_manager):
        ok, user, error = auth_manager.create_guest_user()
        assert ok and error is None
        assert re.fullmatch(r'guest_[0-9a-f]{8}', user.username)
        assert user.email == f'{user.username}@{GUEST_EMAIL_DOMAIN}'
        assert user.is_guest is True
        assert user.to_dict()['is_guest'] is True
        assert user.role.value == 'user'

    def test_every_guest_is_a_different_account(self, auth_manager):
        names = {auth_manager.create_guest_user()[1].username for _ in range(5)}
        assert len(names) == 5

    def test_a_guest_cannot_sign_in_again(self, auth_manager):
        # The password is random and never shown
        _, user, _ = auth_manager.create_guest_user()
        for guess in ('', 'password', 'guest', user.username):
            ok, _, _ = auth_manager.authenticate(user.username, guess)
            assert not ok

    def test_normal_users_are_not_guests(self, auth_manager):
        _, user, _ = auth_manager.register_user('alice', 'alice@example.com', 'password123')
        assert user.is_guest is False
        assert user.to_dict()['is_guest'] is False

    @pytest.mark.parametrize('email', [
        'x@guest.local', 'X@GUEST.LOCAL', ' x@guest.local ', 'someone@guest.local',
    ])
    def test_nobody_can_register_in_the_guest_domain(self, auth_manager, email):
        ok, user, error = auth_manager.register_user('mallory', email, 'password123')
        assert not ok and user is None
        assert 'reserved' in error

    def test_similar_looking_domains_are_fine(self, auth_manager):
        ok, user, _ = auth_manager.register_user('bob', 'bob@notguest.local', 'password123')
        assert ok and user.is_guest is False


@pytest.fixture
def client():
    from server import app
    redis_client = None
    try:
        import redis
        redis_client = redis.from_url('redis://localhost:6379/0', socket_connect_timeout=1)
        redis_client.ping()
    except Exception:
        redis_client = None

    def clear_limits():
        if redis_client:
            for key in redis_client.scan_iter('ratelimit:ip:testclient:*'):
                redis_client.delete(key)

    clear_limits()
    yield TestClient(app)
    clear_limits()


class TestGuestEndpoint:
    def test_signs_in_and_returns_the_guest(self, client):
        response = client.post('/api/auth/guest')
        assert response.status_code == 200
        body = response.json()
        assert body['success'] is True and body['user']['is_guest'] is True
        assert 'session_token' in response.cookies
        assert 'password' not in str(body).lower().replace('password_hash', '')

        me = client.get('/api/auth/me')
        assert me.status_code == 200
        assert me.json()['user']['username'] == body['user']['username']
        assert me.json()['user']['is_guest'] is True

    def test_the_cookie_is_http_only_and_strict(self, client):
        cookie = client.post('/api/auth/guest').headers['set-cookie'].lower()
        assert 'httponly' in cookie and 'samesite=strict' in cookie

    def test_the_guest_can_use_the_pages_and_sees_the_badge(self, client):
        client.post('/api/auth/guest')
        page = client.get('/dashboard')
        assert page.status_code == 200
        assert 'badge-guest' in page.text

    def test_a_normal_user_page_has_no_guest_badge(self, client):
        name = f'tmp_notguest_{int(time.time() * 1000) % 10**9}'
        r = client.post('/api/auth/register', json={
            'username': name, 'email': f'{name}@example.com', 'password': 'TmpPass-12345'})
        assert r.status_code == 200
        try:
            page = client.get('/dashboard')
            assert page.status_code == 200 and 'badge-guest' not in page.text
            assert client.get('/api/auth/me').json()['user']['is_guest'] is False
        finally:
            _delete_user(name)

    def test_register_endpoint_refuses_the_guest_domain(self, client):
        r = client.post('/api/auth/register', json={
            'username': 'tmp_fake_guest', 'email': 'a@guest.local', 'password': 'TmpPass-12345'})
        assert r.status_code == 400 and 'reserved' in r.json()['detail']

    def test_logout_ends_the_guest_session(self, client):
        client.post('/api/auth/guest')
        assert client.get('/api/auth/me').status_code == 200
        client.post('/api/auth/logout')
        assert client.get('/api/auth/me').status_code == 401

    def test_guest_creation_is_limited(self, client, monkeypatch):
        # conftest turns the middleware into a passthrough for the whole session
        from tests import conftest
        monkeypatch.setattr(RateLimitMiddleware, 'dispatch', conftest._real_dispatch)
        # The middleware binds dispatch when the stack is built (at the app's first request)
        from server import app
        app.middleware_stack = None
        try:
            self._burst(client)
        finally:
            monkeypatch.undo()
            app.middleware_stack = None

    def _burst(self, client):
        limit = RATE_LIMITS['/api/auth/guest']['limit']
        codes = [client.post('/api/auth/guest').status_code for _ in range(limit + 2)]
        # Back to back, well inside one second
        assert codes[:limit] == [200] * limit
        assert codes[limit:] == [429, 429]


def _delete_user(username):
    from server import db_manager
    with db_manager.get_session() as db:
        user = db.query(User).filter(User.username == username).first()
        if user:
            db.delete(user)
            db.commit()


class FakeRedis:
    """Just the sorted-set calls RateLimiter makes"""

    def __init__(self):
        self.sets = {}

    def zremrangebyscore(self, key, low, high):
        entries = self.sets.get(key, {})
        for member in [m for m, score in entries.items() if low <= score <= high]:
            del entries[member]

    def zcard(self, key):
        return len(self.sets.get(key, {}))

    def zrange(self, key, start, stop, withscores=False):
        ordered = sorted(self.sets.get(key, {}).items(), key=lambda item: item[1])
        return ordered[:1]

    def zadd(self, key, mapping):
        self.sets.setdefault(key, {}).update(mapping)

    def expire(self, key, seconds):
        pass


class TestRateLimiterCountsEveryRequest:
    def make(self):
        limiter = RateLimiter()
        limiter.redis_client, limiter.enabled = FakeRedis(), True
        return limiter

    def test_a_burst_inside_one_second_is_counted(self):
        limiter = self.make()
        results = [limiter.is_allowed('ip:1', '/x', 5, 60)[0] for _ in range(8)]
        assert results == [True] * 5 + [False] * 3

    def test_each_identifier_has_its_own_count(self):
        limiter = self.make()
        for _ in range(5):
            limiter.is_allowed('ip:1', '/x', 5, 60)
        assert limiter.is_allowed('ip:1', '/x', 5, 60)[0] is False
        assert limiter.is_allowed('ip:2', '/x', 5, 60)[0] is True

    def test_a_blocked_request_says_when_to_retry(self):
        limiter = self.make()
        for _ in range(3):
            limiter.is_allowed('ip:1', '/x', 3, 60)
        allowed, retry_after = limiter.is_allowed('ip:1', '/x', 3, 60)
        assert not allowed and 1 <= retry_after <= 60


PAGES = [
    '/dashboard', '/analyze', '/repositories', '/repositories/new', '/pull-requests',
    '/pull-requests/import', '/issues', '/teams', '/schedules', '/notifications',
    '/notifications/preferences', '/settings', '/settings/github-app', '/plugins',
    '/rules/builder', '/demo/diff-viewer', '/demo/advanced-filters', '/login', '/register',
]


class TestGuestIsShownOnEveryPage:
    """Some pages do not extend base.html and had their own header, so a guest saw no name
    and no badge there (and /login and /register were never given the user at all)"""

    @pytest.mark.parametrize('path', PAGES)
    def test_page_shows_who_is_signed_in(self, client, path):
        user = client.post('/api/auth/guest').json()['user']
        page = client.get(path)
        assert page.status_code == 200
        assert user['username'] in page.text, path
        assert 'badge-guest' in page.text, path

    @pytest.mark.parametrize('path', ['/teams', '/schedules', '/settings', '/plugins', '/settings/github-app'])
    def test_a_signed_out_visitor_gets_no_badge(self, client, path):
        page = client.get(path, follow_redirects=True)
        assert 'badge-guest' not in page.text

    def test_login_page_for_a_signed_out_visitor_still_offers_login(self, client):
        page = client.get('/login')
        assert 'badge-guest' not in page.text and 'href="/register"' in page.text

    def test_every_routed_standalone_template_includes_the_nav(self):
        routed = set(re.findall(r'TemplateResponse\(request, "([^"]+)"', (ROOT / 'server.py').read_text()))
        missing = []
        for name in sorted(routed):
            html = (ROOT / 'templates' / name).read_text()
            if 'extends "base.html"' not in html and '_nav.html' not in html:
                missing.append(name)
        # Login-less pages are plain documents with no header
        assert set(missing) <= {'terms.html', 'privacy.html'}, missing


class TestPages:
    @pytest.mark.parametrize('name', ['login.html', 'register.html'])
    def test_both_auth_pages_offer_the_guest_button(self, name):
        html = (ROOT / 'templates' / name).read_text()
        assert 'id="guestButton"' in html and 'Continue as Guest' in html
        assert "fetch('/api/auth/guest', { method: 'POST'" in html
        assert "window.location.href = '/dashboard'" in html

    def test_the_pages_render_the_button(self, client):
        for path in ('/login', '/register'):
            page = client.get(path)
            assert page.status_code == 200 and 'guestButton' in page.text
