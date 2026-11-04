"""
Server and page fixes found by using the app: accounts and login limits, the client address the limits
see, readable errors, bounded inputs, repository and plugin and webhook validation, the pages and
the startup settings.

What was wrong, in the order of the classes below:
  - any text was a username (an <img onerror> name was rendered into other people's pages), 'ALICE' could be
    registered next to 'alice', passwords over bcrypt's 72 bytes were silently cut, an unknown user was
    rejected faster than a wrong password, and passwords could be guessed without limit
  - X-Forwarded-For was believed from anyone, so a different header per request skipped every rate limit
  - validation errors were a list of objects (shown as [object Object]) and server messages never reached
    pages that read `.error`
  - limit=-5 and limit=100000 were accepted
  - repository URLs only had to start with https://github.com/, a blank name became 'reac' for 'react', and
    the form's blank name was a 422
  - POST /api/plugins/load ran any .py file on the machine for any account
  - Slack and Discord webhook URLs could be anything, and the test buttons posted to them at once
"""

import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import server
from src.core.auth_manager import AuthManager, MAX_PASSWORD_BYTES
from src.core.database import DatabaseManager, Repository, User
from src.middleware.rate_limiter import client_ip
from src.utils.rate_limit import FailureThrottle
from tests.test_data_isolation import make_issue, _delete_user

ROOT = Path(__file__).resolve().parent.parent
PASSWORD = 'TmpPass-12345'


def unique(prefix='hard'):
    return f'{prefix}_{uuid.uuid4().hex[:8]}'


@pytest.fixture
def client():
    return TestClient(server.app)


@pytest.fixture
def account(client):
    name = unique()
    response = client.post('/api/auth/register', json={
        'username': name, 'email': f'{name}@example.com', 'password': PASSWORD})
    assert response.status_code == 200, response.text
    client.account = response.json()['user']
    yield client
    _delete_user(client.account['id'])


class TestRegistration:
    @pytest.mark.parametrize('username', [
        'ab', 'a' * 51, '<img src=x onerror=alert(1)>', 'has space', 'a/b', '"><script>x', 'tab\there',
        'ééé',
    ])
    def test_a_username_must_be_plain_characters(self, client, username):
        response = client.post('/api/auth/register', json={
            'username': username, 'email': f'{unique()}@example.com', 'password': PASSWORD})
        assert response.status_code == 400
        assert 'letters, numbers' in response.json()['detail']

    def test_spaces_around_a_username_are_dropped(self, client):
        name = unique()
        response = client.post('/api/auth/register', json={
            'username': f'  {name}  ', 'email': f'{name}@example.com', 'password': PASSWORD})
        try:
            assert response.json()['user']['username'] == name
        finally:
            _delete_user(response.json()['user']['id'])

    def test_names_that_differ_only_in_case_are_one_name(self, account):
        other = account.post('/api/auth/register', json={
            'username': account.account['username'].upper(), 'email': f'{unique()}@example.com',
            'password': PASSWORD})
        assert other.status_code == 400 and 'already exists' in other.json()['detail']

    def test_emails_that_differ_only_in_case_are_one_email(self, account):
        other = account.post('/api/auth/register', json={
            'username': unique(), 'email': account.account['email'].upper(), 'password': PASSWORD})
        assert other.status_code == 400

    def test_a_password_over_72_bytes_is_refused_not_cut(self, client):
        too_long = client.post('/api/auth/register', json={
            'username': unique(), 'email': f'{unique()}@example.com', 'password': 'x' * (MAX_PASSWORD_BYTES + 1)})
        assert too_long.status_code == 400 and '72 bytes' in too_long.json()['detail']
        # 24 characters of 4 bytes each: short in characters, 96 bytes
        assert client.post('/api/auth/register', json={
            'username': unique(), 'email': f'{unique()}@example.com', 'password': '\U0001F600' * 24}).status_code == 400

    def test_exactly_72_bytes_is_fine(self, client):
        name = unique()
        response = client.post('/api/auth/register', json={
            'username': name, 'email': f'{name}@example.com', 'password': 'x' * MAX_PASSWORD_BYTES})
        try:
            assert response.status_code == 200
        finally:
            _delete_user(response.json()['user']['id'])

    @pytest.mark.parametrize('email', ['plain', 'a@b', '@b.co', 'a b@c.co', 'a<b>@c.co', 'x@y@z.co', 'a' * 100 + '@b.co'])
    def test_bad_emails(self, client, email):
        response = client.post('/api/auth/register', json={
            'username': unique(), 'email': email, 'password': PASSWORD})
        assert response.status_code == 400

    def test_fields_have_length_limits(self, client):
        response = client.post('/api/auth/register', json={
            'username': 'x' * 500, 'email': 'a@b.co', 'password': PASSWORD})
        assert response.status_code == 422 and 'username' in response.json()['detail']
        assert client.post('/api/auth/login', json={'username': 'x', 'password': 'p' * 100000}).status_code == 422


class TestLogin:
    def login(self, client, username, password):
        return client.post('/api/auth/login', json={'username': username, 'password': password})

    def test_the_username_is_not_case_sensitive(self, account):
        other = TestClient(server.app)
        assert self.login(other, account.account['username'].upper(), PASSWORD).status_code == 200

    def test_unknown_user_and_wrong_password_look_the_same(self, account):
        wrong = self.login(account, account.account['username'], 'not-the-password')
        unknown = self.login(account, unique('nobody'), 'not-the-password')
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json()['detail'] == unknown.json()['detail']

    def test_an_unknown_user_still_costs_a_password_check(self, monkeypatch):
        import bcrypt
        calls = []
        real = bcrypt.checkpw
        monkeypatch.setattr(bcrypt, 'checkpw', lambda *a, **k: calls.append(1) or real(*a, **k))
        db = DatabaseManager('sqlite:///:memory:')
        db.init_db()
        with db.get_session() as session:
            AuthManager(session).authenticate('nobody_at_all', 'password123')
        assert len(calls) == 1          # timing no longer says which usernames exist

    def test_a_deactivated_account_is_only_revealed_after_the_right_password(self, account):
        with DatabaseManager().get_session() as db:
            db.query(User).filter(User.id == account.account['id']).update({'is_active': False})
            db.commit()
        other = TestClient(server.app)
        username = account.account['username']
        assert self.login(other, username, 'wrong-password').json()['detail'] == 'Invalid username or password'
        right = self.login(other, username, PASSWORD)
        assert right.status_code == 401 and 'deactivated' in right.json()['detail']

    def test_repeated_failures_are_limited_per_username(self, account, monkeypatch):
        monkeypatch.setattr(server, 'login_throttle', FailureThrottle(3, 60))
        username = account.account['username']
        other = TestClient(server.app)
        codes = [self.login(other, username, 'wrong-password').status_code for _ in range(5)]
        assert codes == [401, 401, 401, 429, 429]
        blocked = self.login(other, username, PASSWORD)
        assert blocked.status_code == 429 and int(blocked.headers['Retry-After']) >= 1
        assert 'Too many failed logins' in blocked.json()['detail']
        # someone else is not affected by it
        assert self.login(other, unique('someone'), 'x').status_code == 401

    def test_a_success_clears_the_count(self, account, monkeypatch):
        monkeypatch.setattr(server, 'login_throttle', FailureThrottle(3, 60))
        username = account.account['username']
        other = TestClient(server.app)
        for _ in range(2):
            self.login(other, username, 'wrong-password')
        assert self.login(other, username, PASSWORD).status_code == 200
        assert [self.login(other, username, 'wrong-password').status_code for _ in range(2)] == [401, 401]

    def test_a_different_forwarded_address_does_not_get_a_fresh_allowance(self, account, monkeypatch):
        monkeypatch.delenv('TRUST_PROXY', raising=False)
        monkeypatch.setattr(server, 'login_throttle', FailureThrottle(3, 60))
        username = account.account['username']
        other = TestClient(server.app)
        codes = [
            other.post('/api/auth/login', json={'username': username, 'password': 'wrong-password'},
                       headers={'X-Forwarded-For': f'10.0.0.{i}'}).status_code
            for i in range(6)
        ]
        assert codes == [401, 401, 401, 429, 429, 429]

    def test_last_login_and_session_ip_are_recorded(self, account):
        other = TestClient(server.app)
        assert self.login(other, account.account['username'], PASSWORD).status_code == 200
        with DatabaseManager().get_session() as db:
            assert db.query(User).filter(User.id == account.account['id']).first().last_login is not None

    def test_the_change_password_limit_matches(self, account):
        response = account.post('/api/auth/change-password', json={
            'old_password': PASSWORD, 'new_password': 'y' * (MAX_PASSWORD_BYTES + 1)})
        assert response.status_code == 400 and '72 bytes' in response.json()['detail']


def fake_request(headers=None, host='198.51.100.7'):
    return SimpleNamespace(headers=headers or {}, client=SimpleNamespace(host=host) if host else None)


class TestClientIp:
    def test_the_connection_address_by_default(self, monkeypatch):
        monkeypatch.delenv('TRUST_PROXY', raising=False)
        assert client_ip(fake_request({'X-Forwarded-For': '1.2.3.4'})) == '198.51.100.7'

    def test_forwarded_header_only_when_a_proxy_is_trusted(self, monkeypatch):
        monkeypatch.setenv('TRUST_PROXY', 'true')
        assert client_ip(fake_request({'X-Forwarded-For': '1.2.3.4, 10.0.0.1'})) == '1.2.3.4'
        assert client_ip(fake_request({})) == '198.51.100.7'

    def test_no_client_at_all(self, monkeypatch):
        monkeypatch.delenv('TRUST_PROXY', raising=False)
        assert client_ip(fake_request(host=None)) == 'unknown'

    def test_the_rate_limiter_uses_it(self, monkeypatch):
        from src.middleware.rate_limiter import RateLimitMiddleware
        monkeypatch.delenv('TRUST_PROXY', raising=False)
        middleware = RateLimitMiddleware.__new__(RateLimitMiddleware)
        request = SimpleNamespace(headers={'X-Forwarded-For': '9.9.9.9'}, client=SimpleNamespace(host='198.51.100.7'),
                                  state=SimpleNamespace())
        assert middleware._get_identifier(request) == 'ip:198.51.100.7'


class TestReadableErrors:
    def test_validation_detail_is_one_sentence(self, client):
        response = client.post('/api/auth/login', json={'username': 5})
        assert response.status_code == 422
        detail = response.json()['detail']
        assert isinstance(detail, str) and 'username' in detail and 'password' in detail
        assert response.json()['error'] == detail

    def test_http_errors_carry_the_message_under_both_names(self, account):
        response = account.get('/api/repositories/does-not-exist')
        assert response.status_code == 404
        body = response.json()
        assert body['detail'] == body['error'] == 'Repository not found'

    def test_401_keeps_its_status_and_message(self, client):
        response = TestClient(server.app).get('/api/auth/me')
        assert response.status_code == 401 and response.json()['error'] == 'Not authenticated'

    def test_non_json_bodies_are_a_400_not_a_500(self, account):
        response = account.post('/api/teams', content='not json', headers={'Content-Type': 'application/json'})
        assert response.status_code == 400 and 'valid JSON' in response.json()['detail']
        assert account.post('/api/teams', json=[1, 2]).status_code == 400

    def test_missing_team_fields_name_the_field(self, account):
        response = account.post('/api/teams', json={'name': 'x'})
        assert response.status_code == 400 and 'slug' in response.json()['detail']
        assert account.put('/api/teams/x/members/y/role', json={}).status_code in (400, 404)


class TestBoundedInputs:
    @pytest.mark.parametrize('query', [
        'limit=-5', 'limit=0', 'limit=100000', 'limit=1001', 'offset=-1',
    ])
    def test_list_parameters_have_bounds(self, account, query):
        for path in ('/api/issues', '/api/refactorings', '/api/notifications'):
            if path == '/api/notifications' and query.startswith('offset'):
                continue
            assert account.get(f'{path}?{query}').status_code == 422, (path, query)

    def test_the_largest_page_the_front_end_asks_for_is_allowed(self, account):
        assert account.get('/api/issues?limit=1000').status_code == 200

    @pytest.mark.parametrize('path', [
        '/api/dashboard/trends?days=0', '/api/dashboard/trends?days=99999', '/api/analytics/trends?days=-1',
        '/api/analytics/compare?current_days=0', '/api/analytics/export?days=100000',
        '/api/dashboard/activity?limit=0',
    ])
    def test_day_ranges_and_limits_are_bounded(self, account, path):
        assert account.get(path).status_code == 422

    def test_analysis_input_is_capped(self, account):
        too_big = 'x = 1\n' * (server.MAX_SOURCE_BYTES // 6 + 10)
        assert account.post('/api/analyze/code', json={'code': too_big, 'filename': 'big.py'}).status_code == 422
        assert account.post('/api/analyze/code', json={'code': 'x=1', 'filename': 'a' * 300 + '.py'}).status_code == 422

    def test_analyze_code_does_not_run_on_the_event_loop(self):
        import asyncio
        # An async def ran the whole analysis in the event loop: 1.8 MB froze every request for 21 seconds
        assert not asyncio.iscoroutinefunction(server.analyze_code)

    def test_login_and_register_run_in_a_worker_thread(self):
        import asyncio
        for handler in (server.register, server.login, server.guest_login, server.change_password):
            assert not asyncio.iscoroutinefunction(handler), handler.__name__


class TestUploads:
    @pytest.fixture(autouse=True)
    def queue(self, monkeypatch):
        self.delay = Mock(return_value=Mock(id='job-1'))
        monkeypatch.setattr(server.analyze_file_task, 'delay', self.delay, raising=False)

    def upload(self, client, name, content, ctype='text/plain'):
        return client.post('/api/analyze/file', files={'file': (name, content, ctype)})

    def test_a_normal_file_is_queued_under_its_own_name(self, account):
        response = self.upload(account, 'app.py', 'x = 1\n')
        assert response.status_code == 200 and response.json()['filename'] == 'app.py'
        assert self.delay.call_args.kwargs['filename'] == 'app.py'
        assert self.delay.call_args.kwargs['user_id'] == account.account['id']

    @pytest.mark.parametrize('sent,stored', [
        ('../../etc/evil.py', 'evil.py'), ('..\\..\\evil.py', 'evil.py'), ('/abs/path/x.py', 'x.py'),
        ('A.PY', 'A.PY'), ('dir/sub/App.java', 'App.java'),
    ])
    def test_only_the_file_name_is_kept(self, account, sent, stored):
        response = self.upload(account, sent, 'x = 1\n' if sent.lower().endswith('.py') else 'class A {}')
        assert response.status_code == 200 and response.json()['filename'] == stored

    def test_too_large_is_refused_without_queueing(self, account):
        response = self.upload(account, 'big.py', b'x' * (server.MAX_SOURCE_BYTES + 1))
        assert response.status_code == 413 and 'too large' in response.json()['detail']
        self.delay.assert_not_called()

    def test_exactly_the_limit_is_accepted(self, account):
        assert self.upload(account, 'ok.py', b'#' * server.MAX_SOURCE_BYTES).status_code == 200

    @pytest.mark.parametrize('content,message', [
        (b'', 'empty'), (b'   \n\n', 'empty'), (b'\xff\xfe\x00bad', 'UTF-8'),
    ])
    def test_empty_and_binary_files(self, account, content, message):
        response = self.upload(account, 'x.py', content)
        assert response.status_code == 400 and message in response.json()['detail']
        self.delay.assert_not_called()

    @pytest.mark.parametrize('name', ['notes.txt', 'noext', '.py.txt', ''])
    def test_unsupported_names(self, account, name):
        assert self.upload(account, name or 'x', 'x').status_code in (400, 422)


class TestProgressStream:
    def test_an_unknown_task_does_not_stream_for_ever(self, account, monkeypatch):
        # A task id nobody ever queued is PENDING for ever
        monkeypatch.setattr(server, 'TASK_STREAM_MAX_SECONDS', 0)
        monkeypatch.setattr(server, 'AsyncResult', lambda *a, **k: SimpleNamespace(state='PENDING', info=None))
        response = account.get('/api/tasks/never-queued/progress')
        assert response.status_code == 200
        assert 'event: error' in response.text and 'Timed out' in response.text

    def test_a_finished_task_ends_the_stream(self, account, monkeypatch):
        monkeypatch.setattr(server, 'AsyncResult', lambda *a, **k: SimpleNamespace(state='SUCCESS', info=None, result={'ok': 1}))
        response = account.get('/api/tasks/done/progress')
        assert 'event: complete' in response.text

    def test_a_closed_connection_ends_the_stream(self, monkeypatch):
        import asyncio
        monkeypatch.setattr(server, 'AsyncResult', lambda *a, **k: SimpleNamespace(state='PENDING', info=None))

        class Gone:
            async def is_disconnected(self):
                return True

        async def run():
            response = await server.task_progress_stream('x', Gone(), SimpleNamespace(id='u'))
            return [chunk async for chunk in response.body_iterator]

        assert asyncio.run(run()) == []


class TestRepositories:
    @pytest.fixture(autouse=True)
    def queue(self, monkeypatch):
        self.delay = Mock(return_value=Mock(id='clone-1'))
        monkeypatch.setattr(server.clone_repository_task, 'delay', self.delay, raising=False)

    def add(self, client, url, name=None):
        body = {'github_url': url}
        if name is not None:
            body['name'] = name
        return client.post('/api/repositories', json=body)

    @pytest.mark.parametrize('url,name', [
        ('https://github.com/pypa/sampleproject', 'sampleproject'),
        ('https://github.com/facebook/react', 'react'),            # rstrip('.git') made this 'reac'
        ('https://github.com/a/digit.git', 'digit'),
        ('https://github.com/a/git', 'git'),
        ('https://github.com/a/b/', 'b'),
        ('git@github.com:o/r.git', 'r'),
        ('https://github.com/Some-Owner/my.repo_name', 'my.repo_name'),
    ])
    def test_a_blank_name_is_the_repositorys_own(self, account, url, name):
        response = self.add(account, url)           # the form leaves the key out
        assert response.status_code == 200, response.text
        assert response.json()['repository']['name'] == name
        self.delay.assert_called_once()

    def test_an_empty_name_string_is_blank_too(self, account):
        assert self.add(account, 'https://github.com/a/b', name='   ').json()['repository']['name'] == 'b'

    @pytest.mark.parametrize('url', [
        'https://github.com/', 'https://github.com/a', 'https://github.com/a/b c', 'https://github.com/a/..',
        'https://github.com/a/b?x=1', 'https://github.com/a/b/c', 'https://github.com.evil.com/a/b',
        'http://github.com/a/b', 'git@github.com:a', 'file:///etc/passwd', 'ssh://evil/x/y', '',
        'https://github.com/-bad/repo', 'https://github.com/a/b#frag', 'https://github.com/a/b\nx',
    ])
    def test_only_real_looking_github_urls(self, account, url):
        response = self.add(account, url)
        assert response.status_code == 400 and 'Invalid GitHub URL' in response.json()['detail']
        self.delay.assert_not_called()

    @pytest.mark.parametrize('name', ['<b>x</b>', 'a"b', "it's", 'a/b', 'x\ny'])
    def test_names_are_plain(self, account, name):
        response = self.add(account, 'https://github.com/a/b', name=name)
        assert response.status_code == 400 and 'Invalid name' in response.json()['detail']

    def test_a_long_name_is_refused(self, account):
        assert self.add(account, 'https://github.com/a/b', name='x' * 201).status_code == 422

    def test_the_same_repository_is_not_added_twice(self, account):
        assert self.add(account, 'https://github.com/a/b').status_code == 200
        again = self.add(account, 'https://github.com/a/b')
        assert again.status_code == 409 and 'already been added' in again.json()['detail']
        assert self.add(account, 'https://github.com/a/other').status_code == 200

    def test_two_accounts_can_add_the_same_repository(self, account):
        other = make_second_account()
        try:
            assert self.add(account, 'https://github.com/a/b').status_code == 200
            assert self.add(other, 'https://github.com/a/b').status_code == 200
        finally:
            _delete_user(other.account['id'])

    def test_the_uploads_repository_is_not_listed_or_counted(self, account):
        with DatabaseManager().get_session() as db:
            db.add(Repository(user_id=account.account['id'], name='Uploaded Files', github_url='local://uploads'))
            db.commit()
        self.add(account, 'https://github.com/a/real')
        listed = account.get('/api/repositories').json()
        assert [r['name'] for r in listed['repositories']] == ['real'] and listed['total'] == 1
        page = account.get('/repositories')
        assert page.status_code == 200 and 'Uploaded Files' not in page.text


def make_second_account():
    client = TestClient(server.app)
    name = unique('second')
    response = client.post('/api/auth/register', json={
        'username': name, 'email': f'{name}@example.com', 'password': PASSWORD})
    client.account = response.json()['user']
    return client


class TestPlugins:
    @pytest.mark.parametrize('path', [
        '/etc/passwd', '../../../../etc/passwd', 'plugins/../server.py', 'server.py',
        str(ROOT / 'server.py'), 'plugins', 'plugins/example_analyzer.pyc', '', '   ',
        '/tmp/evil.py',
    ])
    def test_files_outside_the_plugins_folder_are_refused(self, path):
        with pytest.raises(HTTPException) as refused:
            server.resolve_plugin_path(path)
        assert refused.value.status_code == 400 and 'plugins folder' in refused.value.detail

    @pytest.mark.parametrize('path', [
        './plugins/example_analyzer.py', 'plugins/example_analyzer.py', 'example_analyzer.py',
        str(ROOT / 'plugins' / 'example_analyzer.py'),
    ])
    def test_the_plugins_folder_is_allowed(self, path):
        assert server.resolve_plugin_path(path) == str(ROOT / 'plugins' / 'example_analyzer.py')

    def test_a_symlink_out_of_the_folder_is_refused(self, tmp_path, monkeypatch):
        target = tmp_path / 'evil.py'
        target.write_text('raise SystemExit')
        folder = tmp_path / 'plugins'
        folder.mkdir()
        (folder / 'link.py').symlink_to(target)
        monkeypatch.setattr(server, 'PLUGINS_DIR', os.path.realpath(folder))
        with pytest.raises(HTTPException):
            server.resolve_plugin_path('link.py')

    def test_the_endpoint_never_runs_a_file_outside(self, account, tmp_path):
        marker = tmp_path / 'ran'
        evil = tmp_path / 'evil.py'
        evil.write_text(f"open({str(marker)!r}, 'w').write('x')\n")
        response = account.post('/api/plugins/load', json={'file_path': str(evil)})
        assert response.status_code == 400 and not marker.exists()

    def test_re_enabling_a_stored_plugin_outside_the_folder_is_refused(self, account, tmp_path):
        from src.core.database import Plugin
        evil = tmp_path / 'evil.py'
        evil.write_text('x = 1\n')
        with DatabaseManager().get_session() as db:
            plugin = Plugin(user_id=account.account['id'], name='stored', version='1', author='a',
                            description='d', plugin_type='analyzer', status='inactive',
                            file_path=str(evil), enabled=False)
            db.add(plugin)
            db.commit()
            plugin_id = plugin.id
        response = account.put(f'/api/plugins/{plugin_id}', json={'enabled': True})
        assert response.status_code in (400, 500) and 'plugins folder' in response.text


class TestWebhooks:
    @pytest.mark.parametrize('path,url', [
        ('/api/slack/config', 'http://169.254.169.254/latest/meta-data'),
        ('/api/slack/config', 'https://evil.example.com/hooks.slack.com/'),
        ('/api/slack/config', 'https://hooks.slack.com.evil.example/x'),
        ('/api/slack/test', 'http://localhost:6379/'),
        ('/api/discord/config', 'http://10.0.0.1/api/webhooks/1/x'),
        ('/api/discord/config', 'https://discord.com.evil.example/api/webhooks/1/x'),
        ('/api/discord/test', 'file:///etc/passwd'),
    ])
    def test_only_the_services_own_addresses(self, account, path, url):
        response = account.post(path, json={'webhook_url': url})
        assert response.status_code == 400 and 'webhook URL must start with' in response.json()['detail']

    def test_real_looking_addresses_are_accepted(self, account):
        assert account.post('/api/slack/config', json={
            'webhook_url': 'https://hooks.slack.com/services/T000/B000/xxxx'}).status_code == 200
        assert account.post('/api/discord/config', json={
            'webhook_url': 'https://discord.com/api/webhooks/123/abc'}).status_code == 200

    def test_the_url_must_be_text(self, account):
        assert account.post('/api/slack/config', json={'webhook_url': 5}).status_code == 400
        assert account.post('/api/slack/config', json={'webhook_url': 'https://hooks.slack.com/' + 'x' * 600}).status_code == 400


class TestPagesAndStatics:
    def test_openapi_and_docs_work(self, client):
        # The contact address ended in .local, which pydantic refuses: /openapi.json was a 500
        spec = client.get('/openapi.json')
        assert spec.status_code == 200 and spec.json()['info']['contact']['email'] == 'support@example.com'
        assert client.get('/docs').status_code == 200

    def test_health_reports_the_apps_uptime(self, client):
        body = client.get('/health').json()
        # it reported the computer's uptime (21 days on a fresh start)
        assert 0 <= body['uptime_seconds'] < 3600

    def test_every_static_file_a_page_asks_for_exists(self):
        import re
        missing = []
        for source in list((ROOT / 'templates').glob('*.html')) + list((ROOT / 'static').rglob('*.js')):
            for path in re.findall(r'''["'`(=](/static/[A-Za-z0-9_./-]+\.(?:css|js|png|ico|svg))''', source.read_text()):
                if not (ROOT / path.lstrip('/')).is_file():
                    missing.append((source.name, path))
        assert missing == []

    def test_favicon_is_served(self, client):
        response = client.get('/favicon.ico')
        assert response.status_code == 200 and 'svg' in response.headers['content-type']
        assert '/static/favicon.svg' in client.get('/login').text

    def test_the_analyze_page_escapes_what_comes_from_the_file(self):
        html = (ROOT / 'templates' / 'analyze.html').read_text()
        for expression in ('issue.title', 'issue.description', 'issue.severity', 'issue.category', 'issue.rule_id', 'file.name'):
            assert f'escapeHtml({expression})' in html, expression
        assert '${issue.title}' not in html and '${issue.description}' not in html

    def test_the_analyze_page_offers_every_language_the_server_accepts(self):
        html = (ROOT / 'templates' / 'analyze.html').read_text()
        for extension in ('.py', '.js', '.ts', '.java', '.go', '.rs'):
            assert extension in html.split('accept="')[1].split('"')[0]
        assert 'Python file' not in html

    def test_the_repository_form_shows_the_servers_reason(self):
        html = (ROOT / 'templates' / 'repository_add.html').read_text()
        assert 'result.error' in html     # served as the message now that errors carry `error`


class TestIssueDetailPage:
    @pytest.fixture
    def owned(self, account):
        with DatabaseManager().get_session() as db:
            from src.core.database import CodeFile
            repository = Repository(user_id=account.account['id'], name='mine', github_url='https://github.com/o/mine')
            db.add(repository)
            db.commit()
            file_ = CodeFile(repository_id=repository.id, file_path='app.py', file_hash='h', language='python',
                             lines_of_code=3)
            db.add(file_)
            db.commit()
            return make_issue(db, file_).id

    def test_the_owner_sees_the_page(self, account, owned):
        page = account.get(f'/issues/{owned}')
        assert page.status_code == 200 and 'Issue Detail' in page.text

    def test_someone_else_gets_a_404_not_the_code(self, account, owned):
        other = make_second_account()
        try:
            page = other.get(f'/issues/{owned}')
            assert page.status_code == 404 and 'password' not in page.text.lower()
        finally:
            _delete_user(other.account['id'])

    def test_signed_out_goes_to_login(self, owned):
        response = TestClient(server.app).get(f'/issues/{owned}', follow_redirects=False)
        assert response.status_code in (302, 307) and response.headers['location'] == '/login'


class TestStartup:
    def run_main(self, env=None):
        code = ("import dotenv; dotenv.load_dotenv = lambda *a, **k: False\n"
                "import runpy, uvicorn\ncalls = []\nuvicorn.run = lambda app, **kw: calls.append(kw)\n"
                "runpy.run_path('server.py', run_name='__main__')\nprint(calls[0])\n")
        full_env = {**os.environ, 'PYTHONPATH': str(ROOT), 'DATABASE_URL': f'sqlite:///{tempfile.mkdtemp()}/s.db'}
        # importing server in this process loaded the developer's .env (HOST, PORT ...) into os.environ
        for key in ('HOST', 'PORT', 'ALLOWED_ORIGINS', 'TRUST_PROXY'):
            full_env.pop(key, None)
        full_env.update(env or {})
        done = subprocess.run([sys.executable, '-W', 'ignore', '-c', code], cwd=ROOT, env=full_env,
                              capture_output=True, text=True, timeout=180)
        assert done.returncode == 0, done.stderr[-1500:]
        return done.stdout.strip().splitlines()[-1]

    def test_the_server_listens_on_loopback_by_default(self):
        assert self.run_main() == "{'host': '127.0.0.1', 'port': 8000, 'log_level': 'info', 'proxy_headers': False}"

    def test_host_port_and_proxy_come_from_the_environment(self):
        out = self.run_main({'HOST': '0.0.0.0', 'PORT': '9100', 'TRUST_PROXY': 'true'})
        assert out == "{'host': '0.0.0.0', 'port': 9100, 'log_level': 'info', 'proxy_headers': True}"
