"""
Tests for the sign-in portal: accounts, guests, device sessions, task isolation and the live presence socket.

They run a separate copy of the server (its own temp database, signing key and Redis database), so they
neither need nor touch the data of the copy you use.
"""

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from jose import jwt
from websockets.exceptions import ConnectionClosed, InvalidStatus
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[2]
PASSWORD = "correct-horse-battery"
WORKFLOWS = "/api/workflow-engine/workflows"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(work, **extra_env):
    port = _free_port()
    env = dict(
        os.environ,
        DATABASE_URL=f"sqlite:///{work / 'portal.db'}",
        JWT_SECRET_FILE=str(work / "jwt_secret"),
        REDIS_URL="redis://localhost:6379/9",
        API_HOST="127.0.0.1",
        API_PORT=str(port),
        DEBUG="false",
        ADMIN_USERNAMES="boss.user",
        GUEST_TTL_HOURS="24",
        CELERY_BROKER_URL="redis://localhost:6379/9",  # starting a workflow enqueues its tasks: not on your broker
        CELERY_RESULT_BACKEND="redis://localhost:6379/9",
        RATE_LIMIT_ENABLED="false",  # the general request limits would stop a test run; the portal's own stay on
        **extra_env,
    )
    for name in ("JWT_SECRET_KEY", "REQUIRE_LOGIN", "TRUST_PROXY"):
        env.pop(name, None)
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "server.py")], cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        try:
            if httpx.get(base + "/api/health", timeout=1).status_code == 200:
                return process, {"base": base, "port": port, "db": work / "portal.db", "secret_file": work / "jwt_secret"}
        except httpx.HTTPError:
            pass
        if process.poll() is not None:
            pytest.fail("test server exited during startup")
        time.sleep(0.25)
    process.kill()
    pytest.fail("test server did not start")


def stop_server(process):
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    # the default limits are per address and every test here comes from 127.0.0.1, so they are raised
    process, info = start_server(
        tmp_path_factory.mktemp("portal"), SIGNUPS_PER_HOUR="10000", GUESTS_PER_5_MINUTES="10000",
        LOGIN_FAILURES_PER_IP="10000")
    yield info
    stop_server(process)


@pytest.fixture(scope="module")
def limited_server(tmp_path_factory):
    process, info = start_server(tmp_path_factory.mktemp("limited"))  # the default limits
    yield info
    stop_server(process)


@pytest.fixture(scope="module")
def limited_http(limited_server):
    with httpx.Client(base_url=limited_server["base"], timeout=15) as client:
        yield client


@pytest.fixture(scope="module")
def admin_headers(http):
    response = http.post("/api/auth/register", json={"username": "boss.user", "password": PASSWORD})
    if response.status_code != 201:
        response = http.post("/api/auth/login", json={"username": "boss.user", "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="module")
def http(server):
    with httpx.Client(base_url=server["base"], timeout=15) as client:
        yield client


_counter = {"n": 0}


def unique(prefix="user"):
    _counter["n"] += 1
    return f"{prefix}{_counter['n']}x{int(time.time()) % 100000}"


def register(http, username=None, password=PASSWORD, email=None, **headers):
    username = username or unique()
    body = {"username": username, "password": password}
    if email:
        body["email"] = email
    response = http.post("/api/auth/register", json=body, headers=headers)
    return response


def account(http, username=None):
    """A registered account: (username, auth headers, session bundle)"""
    response = register(http, username)
    assert response.status_code == 201, response.text
    bundle = response.json()
    return bundle["user"]["username"], {"Authorization": f"Bearer {bundle['access_token']}"}, bundle


def guest(http):
    response = http.post("/api/auth/guest")
    assert response.status_code == 201, response.text
    bundle = response.json()
    return {"Authorization": f"Bearer {bundle['access_token']}"}, bundle


def make_task(http, headers, title="a task"):
    response = http.post("/api/tasks/", headers=headers, json={
        "title": title, "description": "d", "task_type": "research", "auto_execute": False,
    })
    assert response.status_code == 201, response.text
    return response.json()["id"]


# ---------------------------------------------------------------------------------------------------
class TestGate:
    def test_pages_and_health_are_public(self, http):
        assert http.get("/api/health").status_code == 200
        assert http.get("/login").status_code == 200
        assert "Continue as guest" in http.get("/login").text
        assert http.get("/dashboard").status_code == 200
        assert http.get("/static/js/portal.js").status_code == 200

    @pytest.mark.parametrize("path", [
        "/api/tasks/", "/api/agents", "/api/monitoring/dashboard", "/api/workflow-engine",
        "/api/auth/me", "/api/auth/online", "/api/auth/users", "/api/messages", "/api/costs/summary",
    ])
    def test_api_needs_a_sign_in(self, http, path):
        response = http.get(path)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_garbage_and_forged_tokens_are_refused(self, http):
        assert http.get("/api/tasks/", headers={"Authorization": "Bearer nonsense"}).status_code == 401
        assert http.get("/api/tasks/", headers={"Authorization": "Basic abc"}).status_code == 401
        # a token signed with the key that used to be written in the source code
        forged = jwt.encode(
            {"sub": "1", "sid": "x", "type": "access", "exp": datetime.utcnow() + timedelta(hours=1)},
            "your-secret-key-change-in-production", algorithm="HS256",
        )
        assert http.get("/api/tasks/", headers={"Authorization": f"Bearer {forged}"}).status_code == 401

    def test_signing_key_is_generated_per_installation(self, server):
        key = server["secret_file"].read_text().strip()
        assert len(key) >= 32 and key != "your-secret-key-change-in-production"
        assert oct(server["secret_file"].stat().st_mode & 0o777) == "0o600"

    def test_expired_token_is_refused(self, http, server):
        _, headers, bundle = account(http)
        key = server["secret_file"].read_text().strip()
        expired = jwt.encode(
            {"sub": str(bundle["user"]["id"]), "sid": bundle["session_id"], "type": "access",
             "exp": datetime.utcnow() - timedelta(minutes=1)}, key, algorithm="HS256")
        assert http.get("/api/tasks/", headers={"Authorization": f"Bearer {expired}"}).status_code == 401

    def test_token_without_a_session_is_refused(self, http, server):
        _, _, bundle = account(http)
        key = server["secret_file"].read_text().strip()
        no_sid = jwt.encode({"sub": str(bundle["user"]["id"]), "type": "access",
                             "exp": datetime.utcnow() + timedelta(hours=1)}, key, algorithm="HS256")
        assert http.get("/api/tasks/", headers={"Authorization": f"Bearer {no_sid}"}).status_code == 401


class TestRegistration:
    def test_register_signs_in(self, http):
        name = unique("alice")
        response = register(http, name, email=f"{name}@example.com")
        assert response.status_code == 201
        bundle = response.json()
        assert bundle["user"]["username"] == name and bundle["user"]["is_guest"] is False
        assert "hashed_password" not in json.dumps(bundle)
        me = http.get("/api/auth/me", headers={"Authorization": f"Bearer {bundle['access_token']}"})
        assert me.status_code == 200 and me.json()["username"] == name

    def test_email_is_optional_and_not_exposed_as_a_real_one(self, http):
        bundle = register(http).json()
        assert bundle["user"]["email"].endswith("@users.local")

    def test_usernames_are_unique_ignoring_case(self, http):
        name = unique("Bob")
        assert register(http, name).status_code == 201
        again = register(http, name.upper())
        assert again.status_code == 400 and "taken" in again.json()["detail"]

    def test_email_is_unique_ignoring_case(self, http):
        email = f"{unique('mail')}@example.com"
        assert register(http, unique(), email=email).status_code == 201
        assert register(http, unique(), email=email.upper()).status_code == 400

    @pytest.mark.parametrize("name", ["ab", "has space", "x" * 31, "semi;colon", "<script>", "-dash", "guest_abc123", "GUEST_x1y2"])
    def test_bad_usernames_refused(self, http, name):
        assert register(http, name).status_code == 400

    @pytest.mark.parametrize("password", ["short", "x" * 73, "é" * 40])
    def test_bad_passwords_refused(self, http, password):
        assert register(http, unique(), password=password).status_code == 400

    def test_reserved_email_domains_refused(self, http):
        # EmailStr itself refuses .local, so this is a 422 either way: never an account
        assert register(http, unique(), email="x@guest.local").status_code in (400, 422)

    def test_malformed_body(self, http):
        assert http.post("/api/auth/register", json={"username": "abc"}).status_code == 422
        assert http.post("/api/auth/register", content=b"not json",
                         headers={"content-type": "application/json"}).status_code == 422

    def test_passwords_are_stored_hashed(self, http, server):
        import sqlite3
        name = unique("hash")
        register(http, name)
        row = sqlite3.connect(server["db"]).execute(
            "select hashed_password from users where username = ?", (name,)).fetchone()
        assert row[0].startswith("$2") and PASSWORD not in row[0]


class TestLogin:
    def test_login_by_username_or_email_ignoring_case(self, http):
        name = unique("Carol")
        register(http, name, email=f"{name}@example.com")
        assert http.post("/api/auth/login", json={"username": name.upper(), "password": PASSWORD}).status_code == 200
        assert http.post("/api/auth/login", json={"username": f"{name}@EXAMPLE.com", "password": PASSWORD}).status_code == 200

    def test_wrong_password_and_unknown_user_look_the_same(self, http):
        name = unique("dave")
        register(http, name)
        wrong = http.post("/api/auth/login", json={"username": name, "password": "nope-nope-nope"})
        unknown = http.post("/api/auth/login", json={"username": unique("ghost"), "password": "nope-nope-nope"})
        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json()

    def test_over_long_password_is_not_truncated_to_match(self, http):
        name = unique("erin")
        register(http, name, password="a" * 72)
        assert http.post("/api/auth/login", json={"username": name, "password": "a" * 72 + "zzz"}).status_code == 401

    def test_failed_logins_are_throttled_per_account_even_when_headers_rotate(self, http):
        name = unique("frank")
        register(http, name)
        statuses = [
            http.post("/api/auth/login", json={"username": name, "password": "wrong-password"},
                      headers={"X-Forwarded-For": f"10.0.0.{i}"}).status_code
            for i in range(7)
        ]
        assert statuses[:5] == [401] * 5 and statuses[5:] == [429, 429]
        blocked = http.post("/api/auth/login", json={"username": name, "password": PASSWORD})
        assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) > 0

    def test_a_successful_login_clears_the_failures(self, http):
        name = unique("gina")
        register(http, name)
        for _ in range(3):
            http.post("/api/auth/login", json={"username": name, "password": "wrong-password"})
        assert http.post("/api/auth/login", json={"username": name, "password": PASSWORD}).status_code == 200
        for _ in range(3):
            http.post("/api/auth/login", json={"username": name, "password": "wrong-password"})
        assert http.post("/api/auth/login", json={"username": name, "password": PASSWORD}).status_code == 200

    def test_guest_accounts_cannot_be_signed_into_with_a_password(self, http):
        headers, bundle = guest(http)
        name = bundle["user"]["username"]
        assert http.post("/api/auth/login", json={"username": name, "password": ""}).status_code in (401, 422)
        assert http.post("/api/auth/login", json={"username": f"{name}@guest.local", "password": "anything-at-all"}).status_code == 401


class TestGuests:
    def test_guest_starts_without_details(self, http):
        headers, bundle = guest(http)
        user = bundle["user"]
        assert user["is_guest"] is True and user["username"].startswith("guest_")
        assert user["email"].endswith("@guest.local")
        assert http.get("/api/auth/me", headers=headers).json()["is_guest"] is True

    def test_every_guest_is_a_different_account(self, http):
        first = guest(http)[1]["user"]
        second = guest(http)[1]["user"]
        assert first["id"] != second["id"] and first["username"] != second["username"]

    def test_guests_can_work_and_cannot_see_each_others_tasks(self, http):
        a, _ = guest(http)
        b, _ = guest(http)
        task = make_task(http, a, "guest A's task")
        assert [t["id"] for t in http.get("/api/tasks/", headers=a).json()] == [task]
        assert http.get("/api/tasks/", headers=b).json() == []
        assert http.get(f"/api/tasks/{task}", headers=b).status_code == 404

    def test_guest_has_no_password_to_change(self, http):
        headers, _ = guest(http)
        response = http.post("/api/auth/change-password", headers=headers,
                             json={"current_password": "x", "new_password": "another-password"})
        assert response.status_code == 400

    def test_upgrade_keeps_the_guests_work(self, http):
        headers, bundle = guest(http)
        task = make_task(http, headers, "kept")
        name = unique("grown")
        response = http.post("/api/auth/guest/upgrade", headers=headers, json={"username": name, "password": PASSWORD})
        assert response.status_code == 200 and response.json()["user"]["is_guest"] is False
        assert response.json()["user"]["username"] == name
        assert http.get(f"/api/tasks/{task}", headers=headers).status_code == 200  # same token still works
        login = http.post("/api/auth/login", json={"username": name, "password": PASSWORD})
        assert login.status_code == 200
        assert http.get(f"/api/tasks/{task}", headers={"Authorization": f"Bearer {login.json()['access_token']}"}).status_code == 200

    def test_upgrade_refuses_taken_names_and_non_guests(self, http):
        taken, _, _ = account(http)
        headers, _ = guest(http)
        assert http.post("/api/auth/guest/upgrade", headers=headers,
                         json={"username": taken.upper(), "password": PASSWORD}).status_code == 400
        _, user_headers, _ = account(http)
        assert http.post("/api/auth/guest/upgrade", headers=user_headers,
                         json={"username": unique(), "password": PASSWORD}).status_code == 400


class TestIsolation:
    def test_tasks_belong_to_their_creator(self, http):
        _, alice, _ = account(http)
        _, bob, _ = account(http)
        task = make_task(http, alice, "alice's secret")

        assert [t["id"] for t in http.get("/api/tasks/", headers=alice).json()] == [task]
        assert http.get("/api/tasks/", headers=bob).json() == []
        assert http.get(f"/api/tasks/{task}", headers=bob).status_code == 404
        assert http.get(f"/api/tasks/{task}/dependencies", headers=bob).status_code == 404
        assert http.patch(f"/api/tasks/{task}", headers=bob, json={"status": "cancelled"}).status_code == 404
        assert http.delete(f"/api/tasks/{task}", headers=bob).status_code == 404
        assert http.get(f"/api/tasks/{task}", headers=alice).status_code == 200  # still there

    def test_cached_lists_do_not_cross_accounts(self, http):
        _, alice, _ = account(http)
        _, bob, _ = account(http)
        make_task(http, alice, "visible only to alice")
        for _ in range(3):  # the response cache would serve the same body to the next caller
            assert len(http.get("/api/tasks/", headers=alice).json()) == 1
            assert http.get("/api/tasks/", headers=bob).json() == []

    def test_a_new_task_shows_up_in_the_list_at_once(self, http):
        _, headers, _ = account(http)
        assert http.get("/api/tasks/?limit=15", headers=headers).json() == []
        task = make_task(http, headers)
        assert [t["id"] for t in http.get("/api/tasks/?limit=15", headers=headers).json()] == [task]
        http.delete(f"/api/tasks/{task}", headers=headers)
        assert http.get("/api/tasks/?limit=15", headers=headers).json() == []

    def test_a_new_task_cannot_hang_under_someone_elses_task(self, http):
        _, alice, _ = account(http)
        _, bob, _ = account(http)
        parent = make_task(http, alice)
        response = http.post("/api/tasks/", headers=bob, json={
            "title": "t", "description": "d", "task_type": "research", "auto_execute": False,
            "parent_task_id": parent})
        assert response.status_code == 404

    def test_list_limits_are_bounded(self, http):
        _, headers, _ = account(http)
        assert http.get("/api/tasks/?limit=-5", headers=headers).status_code == 422
        assert http.get("/api/tasks/?limit=100000", headers=headers).status_code == 422
        assert http.get("/api/tasks/?status=bogus", headers=headers).status_code == 400

    def test_workflows_belong_to_their_creator(self, http):
        _, alice, _ = account(http)
        _, bob, _ = account(http)
        created = http.post(WORKFLOWS, headers=alice, json={
            "name": "alice flow", "description": "d",
            "steps": [{"step_id": "s1", "name": "one", "agent_type": "writer", "task_description": "write"}],
        })
        assert created.status_code == 200, created.text
        workflow_id = created.json()["workflow"]["id"]

        assert http.get(f"{WORKFLOWS}/{workflow_id}/status", headers=alice).status_code == 200
        for method, path in [("GET", f"/{workflow_id}/status"), ("POST", f"/{workflow_id}/start"),
                             ("POST", f"/{workflow_id}/cancel"), ("DELETE", f"/{workflow_id}")]:
            assert http.request(method, WORKFLOWS + path, headers=bob).status_code == 404, path
        assert http.get(WORKFLOWS, headers=bob).json()["workflows"] == []
        assert [w["id"] for w in http.get(WORKFLOWS, headers=alice).json()["workflows"]] == [workflow_id]
        names = [w["name"] for w in http.get("/api/monitoring/workflows", headers=bob).json()["recent_workflows"]]
        assert "alice flow" not in names

    def test_dashboard_numbers_are_your_own(self, http, admin_headers):
        _, alice, _ = account(http)
        _, bob, _ = account(http)
        make_task(http, alice)
        make_task(http, alice)
        make_task(http, bob)
        assert http.get("/api/monitoring/dashboard", headers=alice).json()["overview"]["total_tasks"] == 2
        assert http.get("/api/monitoring/dashboard", headers=bob).json()["overview"]["total_tasks"] == 1
        assert sum(http.get("/api/monitoring/tasks", headers=alice).json()["by_status"].values()) == 2
        everything = http.get("/api/monitoring/dashboard", headers=admin_headers).json()["overview"]["total_tasks"]
        assert everything >= 3  # an admin counts everyone's

    def test_tasks_made_by_a_workflow_belong_to_its_owner(self, http):
        _, alice, _ = account(http)
        _, bob, _ = account(http)
        created = http.post(WORKFLOWS, headers=alice, json={
            "name": "owned steps", "description": "d",
            "steps": [{"step_id": "s1", "name": "first", "agent_type": "writer", "task_description": "write"}],
        }).json()
        workflow_id = created["workflow"]["id"]
        assert http.post(f"{WORKFLOWS}/{workflow_id}/start", headers=alice).status_code == 200
        titles = [t["title"] for t in http.get("/api/tasks/", headers=alice).json()]
        assert titles == ["owned steps - first"]
        assert http.get("/api/tasks/", headers=bob).json() == []

    def test_admin_sees_everything(self, http, admin_headers):
        _, alice, _ = account(http)
        task = make_task(http, alice, "for the admin")
        assert http.get("/api/auth/me", headers=admin_headers).json()["role"] == "admin"
        assert http.get(f"/api/tasks/{task}", headers=admin_headers).status_code == 200
        assert task in [t["id"] for t in http.get("/api/tasks/", headers=admin_headers).json()]
        assert http.get("/api/auth/users", headers=admin_headers).status_code == 200

    def test_only_listed_names_become_admin(self, http):
        _, headers, _ = account(http)
        assert http.get("/api/auth/me", headers=headers).json()["role"] == "user"

    def test_a_deactivated_account_is_locked_out_at_once(self, http, server):
        import sqlite3
        name, headers, _ = account(http)
        assert http.get("/api/auth/me", headers=headers).status_code == 200
        con = sqlite3.connect(server["db"])
        con.execute("update users set is_active = 0 where username = ?", (name,))
        con.commit(); con.close()
        assert http.get("/api/auth/me", headers=headers).status_code == 403
        assert http.get("/api/tasks/", headers=headers).status_code == 403
        assert http.post("/api/auth/login", json={"username": name, "password": PASSWORD}).status_code == 401

    def test_ordinary_users_cannot_list_accounts(self, http):
        _, headers, _ = account(http)
        assert http.get("/api/auth/users", headers=headers).status_code == 403


class TestSessions:
    def test_each_login_is_its_own_device(self, http):
        name, first, _ = account(http)
        second = http.post("/api/auth/login", json={"username": name, "password": PASSWORD},
                           headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) AppleWebKit Safari/604.1"}).json()
        second_headers = {"Authorization": f"Bearer {second['access_token']}"}
        devices = http.get("/api/auth/sessions", headers=second_headers).json()
        assert len(devices) == 2
        assert [d for d in devices if d["current"]][0]["device"] == "Safari on iPhone"
        assert all("ip_address" in d for d in devices)

    def test_signing_out_ends_the_token_at_once(self, http):
        _, headers, bundle = account(http)
        assert http.post("/api/auth/logout", headers=headers).status_code == 204
        assert http.get("/api/auth/me", headers=headers).status_code == 401
        refresh = http.post("/api/auth/refresh", json={"refresh_token": bundle["refresh_token"]})
        assert refresh.status_code == 401

    def test_one_device_can_sign_out_another(self, http):
        name, here, _ = account(http)
        other = http.post("/api/auth/login", json={"username": name, "password": PASSWORD}).json()
        other_headers = {"Authorization": f"Bearer {other['access_token']}"}
        assert http.delete(f"/api/auth/sessions/{other['session_id']}", headers=here).status_code == 204
        assert http.get("/api/auth/me", headers=other_headers).status_code == 401
        assert http.get("/api/auth/me", headers=here).status_code == 200

    def test_cannot_touch_somebody_elses_session(self, http):
        _, alice, alice_bundle = account(http)
        _, bob, _ = account(http)
        assert http.delete(f"/api/auth/sessions/{alice_bundle['session_id']}", headers=bob).status_code == 404
        assert http.get("/api/auth/me", headers=alice).status_code == 200

    def test_sign_out_other_devices(self, http):
        name, here, _ = account(http)
        others = [http.post("/api/auth/login", json={"username": name, "password": PASSWORD}).json() for _ in range(2)]
        assert http.post("/api/auth/sessions/revoke-others", headers=here).json() == {"signed_out": 2}
        for other in others:
            assert http.get("/api/auth/me", headers={"Authorization": f"Bearer {other['access_token']}"}).status_code == 401
        assert http.get("/api/auth/me", headers=here).status_code == 200

    def test_changing_the_password_signs_out_the_other_devices(self, http):
        name, here, _ = account(http)
        other = http.post("/api/auth/login", json={"username": name, "password": PASSWORD}).json()
        response = http.post("/api/auth/change-password", headers=here,
                             json={"current_password": PASSWORD, "new_password": "a-brand-new-password"})
        assert response.status_code == 200 and response.json()["other_devices_signed_out"] == 1
        assert http.get("/api/auth/me", headers={"Authorization": f"Bearer {other['access_token']}"}).status_code == 401
        assert http.post("/api/auth/login", json={"username": name, "password": PASSWORD}).status_code == 401
        assert http.post("/api/auth/login", json={"username": name, "password": "a-brand-new-password"}).status_code == 200

    def test_wrong_current_password_changes_nothing(self, http):
        _, headers, _ = account(http)
        response = http.post("/api/auth/change-password", headers=headers,
                             json={"current_password": "not-it-at-all", "new_password": "a-brand-new-password"})
        assert response.status_code == 400

    def test_refresh_and_access_tokens_are_not_interchangeable(self, http):
        _, headers, bundle = account(http)
        assert http.get("/api/auth/me", headers={"Authorization": f"Bearer {bundle['refresh_token']}"}).status_code == 401
        assert http.post("/api/auth/refresh", json={"refresh_token": bundle["access_token"]}).status_code == 401
        refreshed = http.post("/api/auth/refresh", json={"refresh_token": bundle["refresh_token"]})
        assert refreshed.status_code == 200
        assert http.get("/api/auth/me", headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"}).status_code == 200

    def test_online_endpoint_needs_a_sign_in(self, http):
        _, headers, _ = account(http)
        snapshot = http.get("/api/auth/online", headers=headers).json()
        assert {"online", "count", "guests", "activity"} <= set(snapshot)


# ---------------------------------------------------------------------------------------------------
def ws_url(server):
    return f"ws://127.0.0.1:{server['port']}/api/ws/presence"


def open_socket(server, token=None, origin=None, authenticate=True):
    ws = connect(ws_url(server), origin=origin, open_timeout=5)
    if authenticate:
        ws.send(json.dumps({"type": "auth", "token": token}))
    return ws


def next_message(ws, wanted=None, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        message = json.loads(ws.recv(timeout=max(0.1, deadline - time.time())))
        if wanted is None or wanted(message):
            return message
    raise AssertionError("expected message did not arrive")


class TestRealTime:
    def test_ready_message_has_me_and_who_is_online(self, http, server):
        name, _, bundle = account(http)
        with open_socket(server, bundle["access_token"]) as ws:
            ready = next_message(ws)
            assert ready["type"] == "ready" and ready["me"]["username"] == name
            assert name in [u["username"] for u in ready["online"]]
            ws.send('{"type":"ping"}')
            assert next_message(ws, lambda m: m["type"] == "pong")

    def test_other_people_appear_and_disappear_live(self, http, server):
        first, _, first_bundle = account(http)
        second, _, second_bundle = account(http)
        with open_socket(server, first_bundle["access_token"]) as watcher:
            next_message(watcher)
            with open_socket(server, second_bundle["access_token"]) as other:
                joined = next_message(watcher, lambda m: m.get("event", {}).get("kind") == "online"
                                      and m["event"]["username"] == second)
                assert second in [u["username"] for u in joined["online"]]
                next_message(other)
            left = next_message(watcher, lambda m: m.get("event", {}).get("kind") == "offline"
                                and m["event"]["username"] == second)
            assert second not in [u["username"] for u in left["online"]]

    def test_new_accounts_and_guests_are_announced(self, http, server):
        _, _, bundle = account(http)
        with open_socket(server, bundle["access_token"]) as watcher:
            next_message(watcher)
            newcomer = unique("newbie")
            register(http, newcomer)
            assert next_message(watcher, lambda m: m.get("event", {}).get("username") == newcomer)["event"]["kind"] == "joined"
            _, guest_bundle = guest(http)
            event = next_message(watcher, lambda m: m.get("event", {}).get("username") == guest_bundle["user"]["username"])["event"]
            assert event["kind"] == "guest" and event["is_guest"] is True

    def test_two_tabs_count_as_one_person(self, http, server):
        name, _, bundle = account(http)
        with open_socket(server, bundle["access_token"]) as one, open_socket(server, bundle["access_token"]) as two:
            next_message(one)
            snapshot = next_message(two)
            mine = [u for u in snapshot["online"] if u["username"] == name]
            assert len(mine) == 1 and mine[0]["devices"] == 2

    def test_signing_out_pushes_the_device_off_immediately(self, http, server):
        name, here, _ = account(http)
        other = http.post("/api/auth/login", json={"username": name, "password": PASSWORD}).json()
        with open_socket(server, other["access_token"]) as ws:
            next_message(ws)
            assert http.delete(f"/api/auth/sessions/{other['session_id']}", headers=here).status_code == 204
            assert next_message(ws, lambda m: m["type"] == "session_revoked")
            with pytest.raises(ConnectionClosed):
                ws.recv(timeout=5)

    def test_logout_closes_that_devices_socket(self, http, server):
        _, headers, bundle = account(http)
        with open_socket(server, bundle["access_token"]) as ws:
            next_message(ws)
            http.post("/api/auth/logout", headers=headers)
            assert next_message(ws, lambda m: m["type"] == "session_revoked")

    def test_bad_tokens_are_closed(self, http, server):
        for token, code in [("garbage", 4401), ("", 4401), (None, 4400)]:
            with open_socket(server, token) as ws:
                with pytest.raises(ConnectionClosed) as closed:
                    ws.recv(timeout=5)
                assert closed.value.rcvd.code == code

    def test_refresh_token_is_not_accepted(self, http, server):
        _, _, bundle = account(http)
        with open_socket(server, bundle["refresh_token"]) as ws:
            with pytest.raises(ConnectionClosed) as closed:
                ws.recv(timeout=5)
            assert closed.value.rcvd.code == 4401

    def test_first_message_must_be_auth(self, server):
        with open_socket(server, authenticate=False) as ws:
            ws.send('{"type":"ping"}')
            with pytest.raises(ConnectionClosed) as closed:
                ws.recv(timeout=5)
            assert closed.value.rcvd.code == 4400

    def test_other_sites_cannot_open_the_socket(self, http, server):
        _, _, bundle = account(http)
        with pytest.raises(InvalidStatus) as refused:  # the handshake itself is refused
            open_socket(server, bundle["access_token"], origin="http://evil.example")
        assert refused.value.response.status_code == 403
        with open_socket(server, bundle["access_token"], origin=f"http://127.0.0.1:{server['port']}") as ws:
            assert next_message(ws)["type"] == "ready"

    def test_oversized_message_is_refused(self, http, server):
        _, _, bundle = account(http)
        with open_socket(server, bundle["access_token"]) as ws:
            next_message(ws)
            ws.send("x" * 10000)
            with pytest.raises(ConnectionClosed):
                while True:
                    ws.recv(timeout=5)

    def test_the_old_task_socket_needs_a_token_and_your_own_task(self, http, server):
        _, alice, alice_bundle = account(http)
        _, _, bob_bundle = account(http)
        task = make_task(http, alice)
        base = f"ws://127.0.0.1:{server['port']}/api/ws/tasks/{task}"
        with pytest.raises(Exception):
            connect(base, open_timeout=5).recv(timeout=5)  # no token: refused before the handshake completes
        with pytest.raises(Exception):
            connect(base + f"?token={bob_bundle['access_token']}", open_timeout=5).recv(timeout=5)
        with connect(base + f"?token={alice_bundle['access_token']}", open_timeout=5) as ws:
            assert json.loads(ws.recv(timeout=5))["event"] == "connected"

    def test_the_global_broadcast_socket_is_admin_only(self, http, server):
        _, _, bundle = account(http)
        with pytest.raises(Exception):
            connect(f"ws://127.0.0.1:{server['port']}/api/ws?token={bundle['access_token']}", open_timeout=5).recv(timeout=5)


# ---------------------------------------------------------------------------------------------------
class TestUnits:
    def test_secret_key_is_generated_once_and_reused(self, tmp_path, monkeypatch):
        from src.core import auth
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.setenv("JWT_SECRET_FILE", str(tmp_path / "nested" / "secret"))
        first = auth._load_secret_key()
        assert len(first) >= 32 and auth._load_secret_key() == first
        assert oct((tmp_path / "nested" / "secret").stat().st_mode & 0o777) == "0o600"

    def test_two_installations_get_different_keys(self, tmp_path, monkeypatch):
        from src.core import auth
        monkeypatch.delenv("JWT_SECRET_KEY", raising=False)
        monkeypatch.setenv("JWT_SECRET_FILE", str(tmp_path / "a"))
        a = auth._load_secret_key()
        monkeypatch.setenv("JWT_SECRET_FILE", str(tmp_path / "b"))
        assert auth._load_secret_key() != a

    def test_placeholder_and_short_secrets(self, tmp_path, monkeypatch):
        from src.core import auth
        monkeypatch.setenv("JWT_SECRET_FILE", str(tmp_path / "s"))
        monkeypatch.setenv("JWT_SECRET_KEY", "your-secret-key-change-in-production")
        assert auth._load_secret_key() != "your-secret-key-change-in-production"
        monkeypatch.setenv("JWT_SECRET_KEY", "too-short")
        with pytest.raises(RuntimeError):
            auth._load_secret_key()
        monkeypatch.setenv("JWT_SECRET_KEY", "k" * 40)
        assert auth._load_secret_key() == "k" * 40

    def test_attempt_limiter(self):
        from src.core.portal import AttemptLimiter
        now = [0.0]
        limiter = AttemptLimiter(max_attempts=3, window_seconds=60, clock=lambda: now[0])
        for _ in range(3):
            assert limiter.retry_after("k") == 0
            limiter.record("k")
        assert limiter.retry_after("k") > 0 and limiter.retry_after("other") == 0
        now[0] = 61
        assert limiter.retry_after("k") == 0
        limiter.record("k"); limiter.reset("k")
        assert limiter.retry_after("k") == 0

    @pytest.mark.parametrize("agent,expected", [
        ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0 Safari/537.36", "Chrome on macOS"),
        ("Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/120 Safari/537.36 Edg/120", "Edge on Windows"),
        ("Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0", "Firefox on Linux"),
        ("Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36", "Chrome on Android"),
        ("curl/8.1", "curl"), (None, "Unknown device"), ("", "Unknown device"),
    ])
    def test_device_labels(self, agent, expected):
        from src.core.portal import describe_device
        assert describe_device(agent) == expected

    def test_forwarded_header_is_ignored_unless_a_proxy_is_trusted(self, monkeypatch):
        from types import SimpleNamespace
        from src.core import portal
        request = SimpleNamespace(headers={"x-forwarded-for": "6.6.6.6"}, client=SimpleNamespace(host="1.2.3.4"))
        monkeypatch.setattr(portal, "TRUST_PROXY", False)
        assert portal.client_ip(request) == "1.2.3.4"
        monkeypatch.setattr(portal, "TRUST_PROXY", True)
        assert portal.client_ip(request) == "6.6.6.6"

    def test_expired_guests_are_removed_with_their_work(self, db_session):
        from src.core import portal
        from src.models.task import Task
        from src.models.user import User, UserSession
        old = portal.create_guest_user(db_session)
        fresh = portal.create_guest_user(db_session)
        regular = portal.create_user(db_session, unique("keeper"), PASSWORD, None, None)
        for user in (old, fresh, regular):
            db_session.add(Task(title="t", description="d", task_type="x", created_by_user_id=user.id))
        long_ago = datetime.utcnow() - timedelta(days=3)
        old.created_at = long_ago
        regular.created_at = long_ago
        db_session.add(UserSession(id="old-session", user_id=old.id, created_at=long_ago, last_seen_at=long_ago,
                                   expires_at=datetime.utcnow() + timedelta(days=1)))
        db_session.commit()

        assert portal.purge_expired_guests(db_session, ttl_hours=24) == 1
        names = {u.username for u in db_session.query(User).all()}
        assert old.username not in names and fresh.username in names and regular.username in names
        assert db_session.query(UserSession).filter_by(user_id=old.id).count() == 0
        assert db_session.query(Task).filter_by(created_by_user_id=old.id).count() == 0
        assert db_session.query(Task).filter_by(created_by_user_id=fresh.id).count() == 1

    def test_a_guest_who_is_online_right_now_is_kept(self, db_session):
        from types import SimpleNamespace
        from src.core import portal
        from src.models.user import User
        guest_user = portal.create_guest_user(db_session)
        guest_user.created_at = datetime.utcnow() - timedelta(days=9)
        db_session.commit()
        portal.presence.connections["test-conn"] = portal.Connection(
            websocket=SimpleNamespace(), user_id=guest_user.id, username=guest_user.username,
            is_guest=True, session_id="s", since="2026-01-01T00:00:00Z")
        try:
            assert portal.purge_expired_guests(db_session, ttl_hours=24) == 0
        finally:
            portal.presence.connections.pop("test-conn")
        assert db_session.query(User).filter_by(id=guest_user.id).count() == 1
        assert portal.purge_expired_guests(db_session, ttl_hours=24) == 1

    def test_active_guest_session_keeps_the_guest(self, db_session):
        from src.core import portal
        from src.models.user import User, UserSession
        guest_user = portal.create_guest_user(db_session)
        guest_user.created_at = datetime.utcnow() - timedelta(days=9)
        db_session.add(UserSession(id="live-session", user_id=guest_user.id, expires_at=datetime.utcnow() + timedelta(days=1)))
        db_session.commit()
        assert portal.purge_expired_guests(db_session, ttl_hours=24) == 0
        assert db_session.query(User).filter_by(id=guest_user.id).count() == 1

    def test_schema_upgrade_adds_the_task_owner_column(self, tmp_path, monkeypatch):
        """A database made before accounts existed gets users, user_sessions and tasks.created_by_user_id"""
        import sqlite3
        db_file = tmp_path / "old.db"
        con = sqlite3.connect(db_file)
        con.execute("create table tasks (id integer primary key, title varchar(255) not null)")
        con.commit(); con.close()
        script = (
            "from src.core import portal\n"
            "portal.ensure_schema(); portal.ensure_schema()\n"
            "import sqlite3; con = sqlite3.connect(%r)\n"
            "print(sorted(r[1] for r in con.execute('pragma table_info(tasks)') if r[1] == 'created_by_user_id'))\n"
            "print(sorted(r[0] for r in con.execute(\"select name from sqlite_master where name in ('users','user_sessions')\")))\n"
        ) % str(db_file)
        result = subprocess.run(
            [sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True, timeout=60,
            env=dict(os.environ, DATABASE_URL=f"sqlite:///{db_file}", JWT_SECRET_FILE=str(tmp_path / "s"),
                     REDIS_URL="redis://localhost:6379/9"))
        # create_all would try to build the whole schema, which has FKs to tables the stub lacks: the
        # point is that the column and the two new tables exist afterwards
        assert "['created_by_user_id']" in result.stdout, result.stdout + result.stderr
        assert "['user_sessions', 'users']" in result.stdout, result.stdout + result.stderr


class TestLimits:
    def test_guest_creation_is_limited_per_address(self, limited_http):
        statuses = [limited_http.post("/api/auth/guest").status_code for _ in range(12)]
        assert statuses[:10] == [201] * 10 and statuses[10:] == [429, 429]

    def test_forwarded_header_does_not_buy_more_guests(self, limited_http):
        response = limited_http.post("/api/auth/guest", headers={"X-Forwarded-For": "9.9.9.9"})
        assert response.status_code == 429 and int(response.headers["retry-after"]) > 0

    def test_account_creation_is_limited_per_address(self, limited_http):
        statuses = [register(limited_http).status_code for _ in range(12)]
        assert statuses[:10] == [201] * 10 and statuses[10:] == [429, 429]
