"""
The server: who can read what, what it accepts, and how it behaves while a research runs.

Found by trying it: GET /api/research/{id} and its download returned any user's research to any signed-in
user; a research ran on the event loop (every other request, even the health check, waited a minute);
the progress bar could not move because nothing reported progress; nothing bounded the question,
max_sources, citation style, list sizes or days; a download in an unknown format was a 500; "ALICE" could
be registered next to "alice"; passwords could be guessed without limit; the WebSocket accepted any
origin and took the session token in the URL; and the server listened on 0.0.0.0 with auto-reload on.
"""

import inspect
import itertools
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import server
from src.core.research_orchestrator import ResearchOrchestrator
from tests.test_orchestrator_flow import FakeArxiv, FakeLLM, paper

ROOT = Path(__file__).resolve().parent.parent
counter = itertools.count()


@pytest.fixture(autouse=True)
def reset_state():
    server.login_throttle._failures.clear()
    server.research_progress.clear()
    server.running_research.clear()


@pytest.fixture
def fake_research(monkeypatch):
    """Research runs against fake clients; returns the orchestrator factory's call log"""
    calls = []

    def factory(search_web=True, search_arxiv=True):
        calls.append({"search_web": search_web, "search_arxiv": search_arxiv})
        return ResearchOrchestrator(
            db_path="sqlite:///./data/database.db", web_search_client=None, arxiv_client=FakeArxiv([paper(1), paper(2)]),
            llm_client=FakeLLM(), embedding_model=None, cache_manager=None)
    monkeypatch.setattr(server, "create_research_orchestrator", factory)
    return calls


def new_client():
    client = TestClient(server.app)
    assert client.post("/api/auth/guest").status_code == 200
    return client


@pytest.fixture
def client():
    return new_client()


def run_research(client, **body):
    return client.post("/api/research", json={"query": "retrieval augmented generation versus fine tuning",
                                              "search_web": False, "search_arxiv": True, "max_sources": 4, **body})


class TestOwnership:
    def test_another_user_cannot_read_download_or_delete_a_research(self, client, fake_research):
        query_id = run_research(client).json()["query_id"]
        other = new_client()
        assert other.get(f"/api/research/{query_id}").status_code == 404
        assert other.get(f"/api/research/{query_id}/download?format=json").status_code == 404
        assert other.delete(f"/api/research/{query_id}").status_code == 404
        assert client.get(f"/api/research/{query_id}").status_code == 200          # still there, still the owner's

    def test_the_owner_can_download_in_every_format_available(self, client, fake_research):
        query_id = run_research(client).json()["query_id"]
        for fmt, media in (("markdown", "text/markdown"), ("html", "text/html"), ("json", "application/json")):
            response = client.get(f"/api/research/{query_id}/download?format={fmt}")
            assert response.status_code == 200 and response.headers["content-type"].startswith(media)
            assert f"research_{query_id}" in response.headers["content-disposition"]
        assert "Fine tuning" in client.get(f"/api/research/{query_id}/download?format=markdown").text

    def test_a_listing_only_shows_the_users_own(self, client, fake_research):
        run_research(client)
        assert new_client().get("/api/research").json()["queries"] == []

    def test_everything_needs_a_session(self):
        anonymous = TestClient(server.app)
        for method, path in (("get", "/api/research"), ("get", "/api/research/x"), ("get", "/api/research/progress/abcdefgh"),
                             ("get", "/api/export-formats"), ("get", "/api/research/x/download"), ("delete", "/api/research/x"),
                             ("post", "/api/research"), ("get", "/api/documents")):
            assert getattr(anonymous, method)(path).status_code in (401, 422), path


class TestDownloads:
    def test_an_unknown_format_is_a_400_listing_the_formats(self, client, fake_research):
        query_id = run_research(client).json()["query_id"]
        response = client.get(f"/api/research/{query_id}/download?format=exe")
        assert response.status_code == 400 and "markdown" in response.json()["detail"]

    def test_a_format_the_server_cannot_make_is_a_501_with_the_reason(self, client, fake_research, monkeypatch):
        query_id = run_research(client).json()["query_id"]

        def unavailable(self, *a, **k):
            raise ValueError("PDF generation not available: weasyprint needs the pango library")
        monkeypatch.setattr(server.ReportGenerator, "_generate_pdf", unavailable)
        response = client.get(f"/api/research/{query_id}/download?format=pdf")
        assert response.status_code == 501 and "pango" in response.json()["detail"]

    def test_the_available_formats_are_listed(self, client):
        formats = client.get("/api/export-formats").json()["formats"]
        assert {"markdown", "html", "json"} <= set(formats)


class TestValidation:
    @pytest.mark.parametrize("body,fragment", [
        ({"query": ""}, "Enter a research question"),
        ({"query": "  ab  "}, "at least 3 characters"),
        ({"query": "x" * 2001}, "query:"),
        ({"max_sources": 0}, "max_sources"),
        ({"max_sources": 51}, "max_sources"),
        ({"max_sources": -4}, "max_sources"),
        ({"citation_style": "Harvard"}, "Unknown citation style"),
        ({"search_web": False, "search_arxiv": False, "search_documents": False}, "at least one source"),
        ({"request_id": "bad id!"}, "request_id"),
    ])
    def test_bad_requests_are_422_with_a_sentence(self, client, fake_research, body, fragment):
        response = run_research(client, **body)
        assert response.status_code == 422 and isinstance(response.json()["detail"], str)
        assert fragment in response.json()["detail"]
        assert fake_research == []                                           # nothing was started

    def test_the_citation_style_is_case_insensitive_and_normalised(self, client, fake_research):
        assert run_research(client, citation_style="ieee").status_code == 200

    def test_paging_and_analytics_ranges_are_bounded(self, client):
        for path in ("/api/research?limit=0", "/api/research?limit=201", "/api/research?offset=-1",
                     "/api/analytics/usage?days=0", "/api/analytics/costs?days=100000"):
            assert client.get(path).status_code == 422, path

    def test_the_total_is_the_users_count_not_the_page(self, client, fake_research):
        for _ in range(3):
            run_research(client)
        page = client.get("/api/research?limit=2").json()
        assert len(page["queries"]) == 2 and page["total"] == 3


class TestProgress:
    def test_progress_is_reported_while_running_and_only_to_the_owner(self, client, fake_research, monkeypatch):
        seen = {}
        started, release = threading.Event(), threading.Event()
        original = ResearchOrchestrator._synthesize_findings

        def slow(self, query, ranked):
            started.set()
            release.wait(5)
            return original(self, query, ranked)
        monkeypatch.setattr(ResearchOrchestrator, "_synthesize_findings", slow)

        def go():
            seen["response"] = run_research(client, request_id="progress-test-1")
        thread = threading.Thread(target=go)
        thread.start()
        assert started.wait(10)
        mid = client.get("/api/research/progress/progress-test-1").json()
        assert mid["status"] == "running" and mid["step"] == 4 and mid["total"] == 6 and "Reading" in mid["message"]
        assert new_client().get("/api/research/progress/progress-test-1").status_code == 404
        release.set()
        thread.join(30)
        assert seen["response"].status_code == 200
        assert client.get("/api/research/progress/progress-test-1").json()["status"] == "done"

    def test_the_server_stays_responsive_while_a_research_runs(self, client, fake_research, monkeypatch):
        started, release = threading.Event(), threading.Event()

        def slow(self, query, ranked):
            started.set()
            release.wait(5)
            return "summary", []
        monkeypatch.setattr(ResearchOrchestrator, "_synthesize_findings", slow)
        thread = threading.Thread(target=lambda: run_research(client))
        thread.start()
        assert started.wait(10)
        began = time.time()
        assert TestClient(server.app).get("/api/health").status_code == 200
        assert time.time() - began < 2
        release.set()
        thread.join(30)

    def test_unknown_progress_is_404(self, client):
        assert client.get("/api/research/progress/never-started").status_code == 404

    def test_a_failed_research_reports_why(self, client, monkeypatch):
        def factory(search_web=True, search_arxiv=True):
            from src.core.arxiv_client import ArXivSearchError
            return ResearchOrchestrator(db_path="sqlite:///./data/database.db", arxiv_client=FakeArxiv(error=ArXivSearchError("ArXiv search failed: 429")),
                                        llm_client=FakeLLM(), embedding_model=None, cache_manager=None)
        monkeypatch.setattr(server, "create_research_orchestrator", factory)
        response = run_research(client, request_id="progress-fail-1")
        assert response.status_code == 500 and "429" in response.json()["detail"]
        progress = client.get("/api/research/progress/progress-fail-1").json()
        assert progress["status"] == "failed" and "429" in progress["message"]

    def test_old_progress_entries_are_dropped(self, client):
        server.set_progress("old-entry-1", "u", message="x")
        server.research_progress["old-entry-1"]["updated"] -= server.PROGRESS_TTL_SECONDS + 1
        server.set_progress("new-entry-1", "u", message="y")
        assert "old-entry-1" not in server.research_progress and "new-entry-1" in server.research_progress

    def test_one_research_at_a_time_per_user(self, client, fake_research, monkeypatch):
        started, release = threading.Event(), threading.Event()

        def slow(self, query, ranked):
            started.set()
            release.wait(5)
            return "summary", []
        monkeypatch.setattr(ResearchOrchestrator, "_synthesize_findings", slow)
        thread = threading.Thread(target=lambda: run_research(client))
        thread.start()
        assert started.wait(10)
        second = run_research(client)
        assert second.status_code == 429 and "already running" in second.json()["detail"]
        assert run_research(new_client()).status_code in (200, 500)        # another user is not blocked
        release.set()
        thread.join(30)
        assert run_research(client).status_code == 200                      # and the slot is free again

    def test_the_handler_runs_in_a_worker_thread(self):
        for handler in (server.create_research, server.upload_document, server.login, server.register, server.guest_login):
            assert not inspect.iscoroutinefunction(handler), handler.__name__


class TestAccounts:
    def register(self, client, username, email=None, password="password1"):
        n = next(counter)
        return client.post("/api/auth/register", json={"username": username, "email": email or f"acct{n}@example.com", "password": password})

    def test_usernames_and_emails_are_unique_ignoring_case(self, client):
        assert self.register(client, "Alice_case", "a1@example.com").status_code == 200
        assert self.register(client, "ALICE_CASE", "a2@example.com").status_code == 400
        assert self.register(client, "other_name", "A1@EXAMPLE.COM").status_code == 400

    @pytest.mark.parametrize("username", ["ali\nce", " ", "ab", "bad name", "x" * 51])
    def test_bad_usernames(self, client, username):
        assert self.register(client, username).status_code == 400

    def test_surrounding_whitespace_is_trimmed_from_a_username(self, client):
        # `$` in the old pattern also matched before a trailing newline: "trimmed_name\n" was a different name
        response = self.register(client, "trimmed_name\n")
        assert response.status_code == 200 and response.json()["username"] == "trimmed_name"

    def test_a_password_bcrypt_would_cut_is_refused(self, client):
        assert self.register(client, "longpw1", password="x" * 73).status_code == 400
        assert self.register(client, "longpw2", password="x" * 72).status_code == 200

    def test_login_is_throttled_per_username(self, client):
        self.register(client, "throttled_user", password="right-password")
        for _ in range(server.login_throttle.max_failures):
            assert client.post("/api/auth/login", json={"username": "throttled_user", "password": "wrong"}).status_code == 401
        blocked = client.post("/api/auth/login", json={"username": "throttled_user", "password": "right-password"})
        assert blocked.status_code == 429 and int(blocked.headers["Retry-After"]) > 0
        assert client.post("/api/auth/login", json={"username": "someone_else", "password": "x"}).status_code == 401

    def test_unknown_users_cost_the_same_work_as_wrong_passwords(self, monkeypatch):
        from src.core import auth_manager
        import bcrypt
        checks = []
        real = bcrypt.checkpw
        monkeypatch.setattr(auth_manager.bcrypt, "checkpw", lambda p, h: checks.append(h) or real(p, h))
        TestClient(server.app).post("/api/auth/login", json={"username": "nobody_here", "password": "whatever1"})
        assert checks == [auth_manager._DUMMY_HASH]


class TestUploads:
    def test_an_oversized_upload_is_refused_without_reading_it_all(self, client, monkeypatch):
        monkeypatch.setattr(server, "max_upload_bytes", 1000)
        response = client.post("/api/documents", files={"file": ("big.txt", b"x" * 5000, "text/plain")})
        assert response.status_code == 400 and "too large" in response.json()["detail"]

    def test_the_body_is_read_only_up_to_the_limit_plus_one_byte(self, client, monkeypatch):
        # called directly: a test client does not show how much the handler asked the file for
        from fastapi import HTTPException
        monkeypatch.setattr(server, "max_upload_bytes", 1000)
        asked = []

        class Reader:
            def read(self, n=-1):
                asked.append(n)
                return b"x" * (n if n > 0 else 50_000_000)

        class Upload:
            filename = "huge.txt"
            file = Reader()
        with pytest.raises(HTTPException) as refused:
            server.upload_document(file=Upload(), session_token=client.cookies.get("session_token"))
        assert refused.value.status_code == 400 and asked == [1001]

    def test_the_file_name_is_a_bare_printable_name(self, client, monkeypatch):
        if not server.vector_store:
            pytest.skip("document search is not available here")
        monkeypatch.setattr(server.embedding_service, "embed_texts", lambda texts: [[0.1] * 384 for _ in texts])
        response = client.post("/api/documents", files={"file": ("../../etc/<b>evil</b>\x07.txt", b"some text to store " * 10, "text/plain")})
        assert response.status_code == 200
        name = response.json()["filename"]
        assert "/" not in name and "\x07" not in name and name.endswith(".txt")

    def test_an_unsupported_type_and_an_empty_file_are_refused(self, client):
        assert client.post("/api/documents", files={"file": ("x.exe", b"MZ", "application/octet-stream")}).status_code == 400
        assert client.post("/api/documents", files={"file": ("x.txt", b"", "text/plain")}).status_code == 400


class TestWebSocket:
    def connect(self, client, headers=None, query=""):
        return client.websocket_connect(f"/ws/research/q1{query}", headers=headers or {})

    def test_the_session_cookie_is_enough(self, client):
        with self.connect(client) as ws:
            assert ws.receive_json()["type"] == "connected"
            ws.send_text("ping")
            assert ws.receive_json()["type"] == "pong"

    def test_a_token_in_the_url_is_no_longer_accepted(self, client):
        token = client.cookies.get("session_token")
        anonymous = TestClient(server.app)
        with pytest.raises(WebSocketDisconnect):
            with anonymous.websocket_connect(f"/ws/research/q1?session_token={token}"):
                pass

    def test_another_origin_is_refused(self, client):
        with pytest.raises(WebSocketDisconnect) as refused:
            with self.connect(client, {"origin": "http://localhost:3000"}):
                pass
        assert refused.value.code == 1008

    def test_the_apps_own_origin_is_accepted(self, client):
        with self.connect(client, {"origin": "http://testserver"}) as ws:
            assert ws.receive_json()["type"] == "connected"

    @pytest.mark.parametrize("origin,host,ok", [
        (None, "localhost:8000", True), ("http://localhost:8000", "localhost:8000", True),
        ("http://192.168.1.5:8000", "192.168.1.5:8000", True), ("http://localhost:3000", "localhost:8000", False),
        ("http://evil.example", "localhost:8000", False), ("http://evil.example", None, False),
    ])
    def test_origin_rules(self, origin, host, ok, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:8000")
        assert server.origin_allowed(origin, host) is ok

    def test_sockets_are_forgotten_on_disconnect(self, client):
        with self.connect(client) as ws:
            ws.receive_json()
            assert "q1" in server.ws_connections
        deadline = time.time() + 5
        while "q1" in server.ws_connections and time.time() < deadline:
            time.sleep(0.02)
        assert "q1" not in server.ws_connections


def run_python(code, env=None):
    full_env = {**os.environ, "PYTHONPATH": str(ROOT), "DATABASE_URL": f"sqlite:///{tempfile.mkdtemp()}/s.db"}
    for key in ("HOST", "RELOAD"):
        full_env.pop(key, None)
    full_env.update(env or {})
    # The developer's own .env (HOST=0.0.0.0 ...) must not decide what these tests see
    code = "import dotenv; dotenv.load_dotenv = lambda *a, **k: False\n" + code
    done = subprocess.run([sys.executable, "-W", "ignore", "-c", code], cwd=ROOT, env=full_env, capture_output=True, text=True, timeout=180)
    assert done.returncode == 0, done.stderr[-2000:]
    return done.stdout.strip().splitlines()[-1] if done.stdout.strip() else ""


class TestStartup:
    RUN = """
import runpy, uvicorn
calls = []
uvicorn.run = lambda app, **kw: calls.append(kw)
runpy.run_path('server.py', run_name='__main__')
print({k: calls[0][k] for k in ('host', 'port', 'reload')})
"""

    def test_loopback_and_no_auto_reload_by_default(self):
        assert run_python(self.RUN) == "{'host': '127.0.0.1', 'port': 8000, 'reload': False}"

    def test_the_environment_can_open_it_up(self):
        assert run_python(self.RUN, {"HOST": "0.0.0.0", "PORT": "9100", "RELOAD": "true"}) == "{'host': '0.0.0.0', 'port': 9100, 'reload': True}"

    def test_research_left_processing_is_failed_at_startup(self):
        code = """
import asyncio
from src.core.database import DatabaseManager, ResearchQuery, User
import server
server.db_manager.create_tables()
with server.db_manager.get_session() as db:
    u = User(username='stuck_user', email='stuck@example.com', password_hash='x'); db.add(u); db.commit()
    db.add(ResearchQuery(user_id=u.id, query_text='stuck', status='processing')); db.commit()
asyncio.run(server.startup_event())
with server.db_manager.get_session() as db:
    q = db.query(ResearchQuery).first(); print(q.status, '|', q.error_message)
"""
        assert run_python(code).startswith("failed | Interrupted")
