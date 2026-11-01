"""
Accounts, input limits and the failed-login throttle.

Found by probing the running app: "ALICE" could be registered next to "alice", a username of three
spaces was valid, a password longer than bcrypt's 72 bytes was silently cut (the password plus any
suffix logged in), an unknown username answered 250 ms faster than a wrong password, passwords could
be guessed without limit, and nothing bounded titles, system prompts, messages, list sizes or image sizes.
"""

import inspect
import itertools

import bcrypt
import pytest
from fastapi.testclient import TestClient

import server
from src.core import auth_manager
from src.core.rate_limit import FailureThrottle

counter = itertools.count()


@pytest.fixture
def client():
    server.login_throttle._failures.clear()
    with TestClient(server.app) as c:
        yield c


def register(client, username=None, email=None, password="password1"):
    n = next(counter)
    return client.post("/api/auth/register", json={
        "username": username if username is not None else f"user{n}",
        "email": email if email is not None else f"user{n}@example.com",
        "password": password,
    })


@pytest.fixture
def guest(client):
    assert client.post("/api/auth/guest").status_code == 200
    return client


class TestRegistration:
    def test_a_normal_account_works(self, client):
        assert register(client).status_code == 200

    def test_usernames_are_unique_ignoring_case(self, client):
        assert register(client, username="Alice-case", email="a1@example.com").status_code == 200
        again = register(client, username="ALICE-CASE", email="a2@example.com")
        assert again.status_code == 400 and "already exists" in again.json()["detail"]

    def test_emails_are_unique_ignoring_case(self, client):
        assert register(client, email="Same@Example.com").status_code == 200
        assert register(client, email="same@example.com").status_code == 400

    @pytest.mark.parametrize("username", ["   ", "ab", " a ", "x" * 51])
    def test_blank_or_badly_sized_usernames_are_rejected(self, client, username):
        response = register(client, username=username)
        assert response.status_code == 400 and "3-50" in response.json()["detail"]

    def test_surrounding_spaces_are_not_part_of_the_name(self, client):
        response = register(client, username="  padded-name  ")
        assert response.status_code == 200 and response.json()["username"] == "padded-name"

    def test_control_characters_in_a_username_are_rejected(self, client):
        assert register(client, username="bad\nname").status_code == 400

    def test_a_password_bcrypt_would_truncate_is_rejected(self, client):
        response = register(client, password="x" * 73)
        assert response.status_code == 400 and "72 bytes" in response.json()["detail"]

    def test_72_bytes_is_still_fine_and_bytes_not_characters_are_counted(self, client):
        assert register(client, password="x" * 72).status_code == 200
        assert register(client, password="é" * 37).status_code == 400   # 74 bytes

    def test_an_email_longer_than_the_column_is_rejected(self, client):
        assert register(client, email="a" * 100 + "@example.com").status_code == 400


class TestLogin:
    def test_correct_password_works_and_wrong_one_does_not(self, client):
        register(client, username="loginuser", password="correct-horse")
        assert client.post("/api/auth/login", json={"username": "loginuser", "password": "wrong-horse"}).status_code == 401
        assert client.post("/api/auth/login", json={"username": "loginuser", "password": "correct-horse"}).status_code == 200

    def test_an_account_made_with_a_long_password_still_logs_in(self, client, guest, monkeypatch):
        # bcrypt 5 refuses passwords over 72 bytes instead of cutting them: behave like it here
        real = bcrypt.checkpw

        def strict(password, hashed):
            if len(password) > 72:
                raise ValueError("password cannot be longer than 72 bytes")
            return real(password, hashed)
        monkeypatch.setattr(auth_manager.bcrypt, "checkpw", strict)

        # Created before the 72-byte limit existed: bcrypt had cut the password when hashing
        with server.db_manager.get_session() as db:
            from src.core.database import User
            long_password = "p" * 90
            hashed = bcrypt.hashpw(long_password.encode()[:72], bcrypt.gensalt(4)).decode()
            db.add(User(username="legacy-user", email="legacy@example.com", password_hash=hashed))
            db.commit()
        assert client.post("/api/auth/login", json={"username": "legacy-user", "password": long_password}).status_code == 200

    def test_an_unknown_user_costs_a_password_check_like_a_known_one(self, client, monkeypatch):
        checks = []
        real = bcrypt.checkpw
        monkeypatch.setattr(auth_manager.bcrypt, "checkpw", lambda p, h: checks.append(h) or real(p, h))
        client.post("/api/auth/login", json={"username": "nobody-here", "password": "whatever1"})
        assert checks == [auth_manager._DUMMY_HASH]

    def test_login_handlers_run_in_a_worker_thread(self):
        # bcrypt is ~0.25 s of CPU: as `async def` it froze every open chat stream
        for handler in (server.login, server.register, server.guest_login):
            assert not inspect.iscoroutinefunction(handler), handler.__name__


class TestThrottle:
    def attempt(self, client, password="bad-password", username="throttled"):
        return client.post("/api/auth/login", json={"username": username, "password": password})

    def test_too_many_failures_lock_the_username_out(self, client):
        register(client, username="throttled", password="right-password")
        statuses = [self.attempt(client).status_code for _ in range(server.login_throttle.max_failures)]
        assert statuses == [401] * server.login_throttle.max_failures
        blocked = self.attempt(client, password="right-password")   # even the right password waits
        assert blocked.status_code == 429
        assert int(blocked.headers["Retry-After"]) > 0 and "Try again in" in blocked.json()["detail"]

    def test_other_usernames_are_not_affected(self, client):
        register(client, username="throttled", password="right-password")
        register(client, username="innocent", password="right-password")
        for _ in range(server.login_throttle.max_failures):
            self.attempt(client)
        assert self.attempt(client, "right-password", "innocent").status_code == 200

    def test_a_successful_login_clears_the_count(self, client):
        register(client, username="throttled", password="right-password")
        for _ in range(server.login_throttle.max_failures - 1):
            self.attempt(client)
        assert self.attempt(client, "right-password").status_code == 200
        for _ in range(server.login_throttle.max_failures - 1):
            assert self.attempt(client).status_code == 401


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class TestFailureThrottle:
    def test_blocks_at_the_limit_and_reports_a_wait(self):
        clock = FakeClock()
        throttle = FailureThrottle(max_failures=3, window_seconds=60, clock=clock)
        for _ in range(2):
            throttle.record_failure("k")
        assert throttle.retry_after("k") == 0
        throttle.record_failure("k")
        assert 59 <= throttle.retry_after("k") <= 61

    def test_failures_expire(self):
        clock = FakeClock()
        throttle = FailureThrottle(max_failures=2, window_seconds=60, clock=clock)
        throttle.record_failure("k")
        throttle.record_failure("k")
        assert throttle.retry_after("k") > 0
        clock.now += 61
        assert throttle.retry_after("k") == 0
        assert "k" not in throttle._failures

    def test_keys_are_independent_and_reset_clears(self):
        throttle = FailureThrottle(max_failures=1, window_seconds=60, clock=FakeClock())
        throttle.record_failure("a")
        assert throttle.retry_after("a") > 0 and throttle.retry_after("b") == 0
        throttle.reset("a")
        assert throttle.retry_after("a") == 0

    def test_memory_is_bounded(self):
        throttle = FailureThrottle(max_failures=1, window_seconds=60, clock=FakeClock())
        for i in range(10050):
            throttle.record_failure(f"user{i}")
        assert len(throttle._failures) <= 10000


class TestLimits:
    def test_provider_must_be_a_known_one(self, guest):
        assert guest.post("/api/conversations", json={"llm_provider": "nope"}).status_code == 422
        conversation = guest.post("/api/conversations", json={"llm_provider": "anthropic"}).json()
        assert guest.patch(f"/api/conversations/{conversation['id']}", json={"llm_provider": "nope"}).status_code == 422
        assert guest.patch(f"/api/conversations/{conversation['id']}", json={"llm_provider": "openai"}).status_code == 200

    @pytest.mark.parametrize("field,size", [("title", 201), ("llm_model", 101), ("system_prompt", server.MAX_SYSTEM_PROMPT_CHARS + 1)])
    def test_fields_are_capped_on_create_and_update(self, guest, field, size):
        assert guest.post("/api/conversations", json={field: "x" * size}).status_code == 422
        conversation = guest.post("/api/conversations", json={}).json()
        assert guest.patch(f"/api/conversations/{conversation['id']}", json={field: "x" * size}).status_code == 422

    def test_the_largest_allowed_values_are_accepted(self, guest):
        response = guest.post("/api/conversations", json={
            "title": "t" * 200, "llm_model": "m" * 100, "system_prompt": "s" * server.MAX_SYSTEM_PROMPT_CHARS})
        assert response.status_code == 200

    @pytest.mark.parametrize("query", ["limit=0", "limit=-1", "limit=201", "offset=-1"])
    def test_list_paging_is_bounded(self, guest, query):
        assert guest.get(f"/api/conversations?{query}").status_code == 422

    def test_message_listing_is_bounded_too(self, guest):
        conversation = guest.post("/api/conversations", json={}).json()["id"]
        assert guest.get(f"/api/conversations/{conversation}/messages?limit=501").status_code == 422
        assert guest.get(f"/api/conversations/{conversation}/messages?limit=500").status_code == 200

    def test_messages_must_have_text_and_a_sane_size(self, guest):
        conversation = guest.post("/api/conversations", json={}).json()["id"]
        url = f"/api/conversations/{conversation}/messages"
        assert guest.post(url, json={"content": "   "}).status_code == 422
        assert guest.post(url, json={"content": "x" * (server.MAX_MESSAGE_CHARS + 1)}).status_code == 422
        assert guest.post(url, json={"content": "x" * server.MAX_MESSAGE_CHARS}).status_code == 200

    def test_validation_errors_are_one_readable_sentence(self, guest):
        # Every page script shows `detail`; a list of objects displayed as "[object Object]"
        detail = guest.post("/api/conversations", json={"llm_provider": "nope"}).json()["detail"]
        assert isinstance(detail, str) and detail.startswith("llm_provider: ")
        blank = guest.post("/api/generate-image", json={"prompt": " "}).json()["detail"]
        assert blank == "prompt: Prompt cannot be empty"


class TestImageRequests:
    def post(self, client, **body):
        return client.post("/api/generate-image", json={"prompt": "a red fox", **body})

    def test_needs_a_session(self, client):
        client.cookies.clear()
        assert self.post(client).status_code == 401

    @pytest.mark.parametrize("body", [
        {"width": 100000, "height": 100000}, {"width": 0}, {"height": -8}, {"width": 513}, {"width": 1032},
        {"prompt": "x" * 1001}, {"prompt": ""},
    ])
    def test_sizes_and_prompts_are_bounded(self, guest, body):
        assert self.post(guest, **body).status_code == 422

    def test_generation_runs_off_the_event_loop_and_returns_the_url(self, guest, monkeypatch):
        import asyncio
        seen = {}

        def fake(prompt, width, height):
            try:
                asyncio.get_running_loop()
                seen["on_loop"] = True
            except RuntimeError:
                seen["on_loop"] = False
            seen["args"] = (prompt, width, height)
            return "/static/generated_images/x.png"

        monkeypatch.setattr(server, "generate_local_image", fake)
        response = self.post(guest, width=256, height=768)
        assert response.status_code == 200
        assert response.json()["image_url"] == "/static/generated_images/x.png"
        assert seen == {"on_loop": False, "args": ("a red fox", 256, 768)}

    def test_a_failure_is_reported_not_raised(self, guest, monkeypatch):
        def boom(*a):
            raise MemoryError("out of memory")
        monkeypatch.setattr(server, "generate_local_image", boom)
        response = self.post(guest)
        assert response.status_code == 500 and "out of memory" in response.json()["detail"]

    @pytest.mark.parametrize("width,height,expected", [
        (512, 512, "1024x1024"), (1024, 1024, "1024x1024"), (1024, 576, "1792x1024"), (512, 1024, "1024x1792"),
    ])
    def test_dalle_gets_a_size_it_accepts(self, width, height, expected):
        assert server.dalle_size(width, height) == expected

    def test_dalle_without_a_key_is_a_clear_error(self, guest):
        response = self.post(guest, provider="dall-e")
        assert response.status_code == 400 and "not configured" in response.json()["detail"]
