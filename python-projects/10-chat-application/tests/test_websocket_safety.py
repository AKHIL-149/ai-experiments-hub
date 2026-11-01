"""
The chat WebSocket: who may open it, what it accepts, and how it ends.

Found by probing: a page on another origin (a different localhost port is still "same-site", so the
SameSite=Strict cookie went along) could open the socket and chat as the user; a frame that was not
JSON, or was a JSON list, raised out of the handler; an empty or non-string message was saved and sent
to the model (null crashed on the database); deleting the conversation, or logging out, while a socket
was open either crashed the handler or did nothing; and sockets were only forgotten on a clean
disconnect.
"""

import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import server
from src.core.llm_client import LLMClient


def eventually(condition, seconds=5.0):
    """The handler finishes on the server's thread after the client has left: older Starlette test
    clients return from `with websocket_connect` before it has, newer ones wait."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


@pytest.fixture
def client():
    server.active_connections.clear()
    with TestClient(server.app) as c:
        assert c.post("/api/auth/guest").status_code == 200
        yield c


@pytest.fixture(autouse=True)
def reply(monkeypatch):
    async def stream(messages, provider="ollama", model=None, temperature=0.7):
        yield "Hel"
        yield "lo"
    monkeypatch.setattr(server.llm_client, "stream_completion", stream)


def conversation(client, **fields):
    return client.post("/api/conversations", json=fields).json()["id"]


def receive_until_end(ws):
    events = []
    while True:
        event = ws.receive_json()
        events.append(event)
        if event["type"] in ("done", "error"):
            return events


def stored(client, conversation_id):
    return [(m["role"], m["content"]) for m in client.get(f"/api/conversations/{conversation_id}/messages").json()["messages"]]


class TestOrigin:
    def test_a_page_on_another_origin_is_refused(self, client):
        cid = conversation(client)
        with pytest.raises(WebSocketDisconnect) as refused:
            with client.websocket_connect(f"/ws/{cid}", headers={"origin": "http://localhost:3000"}):
                pass
        assert refused.value.code == 1008

    def test_the_apps_own_origin_is_accepted(self, client):
        cid = conversation(client)
        # TestClient's Host header is "testserver"
        with client.websocket_connect(f"/ws/{cid}", headers={"origin": "http://testserver"}) as ws:
            ws.send_json({"type": "message", "content": "hi"})
            assert receive_until_end(ws)[-1]["type"] == "done"

    def test_clients_without_an_origin_are_accepted(self, client):
        cid = conversation(client)
        with client.websocket_connect(f"/ws/{cid}") as ws:
            ws.send_json({"type": "message", "content": "hi"})
            assert receive_until_end(ws)[-1]["type"] == "done"

    def test_allowed_origins_setting_admits_listed_origins(self, client, monkeypatch):
        monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:8000, http://chat.example.com")
        assert server.origin_allowed("http://chat.example.com", "localhost:9999")
        assert not server.origin_allowed("http://evil.example.com", "localhost:9999")

    @pytest.mark.parametrize("origin,host,ok", [
        (None, "localhost:8000", True),
        ("http://localhost:8000", "localhost:8000", True),
        ("http://192.168.1.5:8000", "192.168.1.5:8000", True),       # opened by network address
        ("http://localhost:3000", "localhost:8000", False),          # another dev server, same site
        ("http://127.0.0.1:8000", "localhost:8000", True),           # listed in ALLOWED_ORIGINS
        ("http://evil.example", "localhost:8000", False),
        ("http://evil.example", None, False),
    ])
    def test_origin_rules(self, monkeypatch, origin, host, ok):
        monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")
        assert server.origin_allowed(origin, host) is ok


class TestFrames:
    def test_a_frame_that_is_not_json_is_answered_and_the_socket_lives_on(self, client):
        cid = conversation(client)
        with client.websocket_connect(f"/ws/{cid}") as ws:
            ws.send_text("not json")
            assert ws.receive_json() == {"type": "error", "error": "Messages must be JSON objects"}
            ws.send_json({"type": "message", "content": "still here"})
            assert receive_until_end(ws)[-1]["type"] == "done"

    @pytest.mark.parametrize("frame", [[1, 2], "text", 5, None, {"type": "ping"}, {"content": "no type"}])
    def test_other_json_is_ignored_not_crashed_on(self, client, frame):
        cid = conversation(client)
        with client.websocket_connect(f"/ws/{cid}") as ws:
            ws.send_json(frame)
            ws.send_json({"type": "message", "content": "after"})
            assert receive_until_end(ws)[-1]["type"] == "done"
        assert stored(client, cid) == [("user", "after"), ("assistant", "Hello")]

    @pytest.mark.parametrize("content", ["", "   \n", None, 123, ["x"]])
    def test_messages_without_text_are_refused_and_not_saved(self, client, content):
        cid = conversation(client)
        with client.websocket_connect(f"/ws/{cid}") as ws:
            ws.send_json({"type": "message", "content": content})
            event = ws.receive_json()
        assert event == {"type": "error", "error": "Message cannot be empty"}
        assert stored(client, cid) == []

    def test_an_oversized_message_is_refused_and_not_saved(self, client):
        cid = conversation(client)
        with client.websocket_connect(f"/ws/{cid}") as ws:
            ws.send_json({"type": "message", "content": "x" * (server.MAX_MESSAGE_CHARS + 1)})
            event = ws.receive_json()
        assert event["type"] == "error" and "too long" in event["error"]
        assert stored(client, cid) == []


class TestEndingTheConnection:
    def test_deleting_the_conversation_ends_the_socket_with_a_message(self, client):
        cid = conversation(client)
        with client.websocket_connect(f"/ws/{cid}") as ws:
            client.delete(f"/api/conversations/{cid}")
            ws.send_json({"type": "message", "content": "hello?"})
            assert ws.receive_json() == {"type": "error", "error": "This conversation was deleted"}
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()

    def test_logging_out_ends_an_open_socket(self, client):
        cid = conversation(client)
        with client.websocket_connect(f"/ws/{cid}") as ws:
            client.post("/api/auth/logout")
            ws.send_json({"type": "message", "content": "after logout"})
            with pytest.raises(WebSocketDisconnect) as closed:
                ws.receive_json()
        assert closed.value.code == 1008

    def test_sockets_are_forgotten_however_the_handler_ends(self, client):
        cid = conversation(client)
        with client.websocket_connect(f"/ws/{cid}") as ws:
            assert len(server.active_connections[cid]) == 1
            ws.send_text("not json")      # used to end the handler with an exception
            ws.receive_json()
        assert eventually(lambda: server.active_connections == {})

        with client.websocket_connect(f"/ws/{cid}") as ws:
            client.delete(f"/api/conversations/{cid}")
            ws.send_json({"type": "message", "content": "x"})
            ws.receive_json()
        assert eventually(lambda: server.active_connections == {})

    def test_another_users_conversation_is_refused(self, client):
        cid = conversation(client)
        other = TestClient(server.app)
        other.post("/api/auth/guest")
        with pytest.raises(WebSocketDisconnect):
            with other.websocket_connect(f"/ws/{cid}"):
                pass

    def test_generation_stops_when_the_browser_leaves(self, client, monkeypatch):
        # Driven with a fake socket: whether a test client reports a closed browser to the app
        # differs between Starlette versions, a real server (uvicorn) raises on the next send.
        import asyncio
        state = {"closed": False, "yielded": 0}

        async def endless(messages, provider="ollama", model=None, temperature=0.7):
            try:
                while True:
                    state["yielded"] += 1
                    yield "tok"
                    if state["yielded"] > 5000:
                        return
            finally:
                state["closed"] = True

        monkeypatch.setattr(server.llm_client, "stream_completion", endless)
        cid = conversation(client)
        token = client.cookies.get("session_token")

        class GoneAfterThreeTokens:
            headers = {}
            sent = 0

            async def accept(self):
                pass

            async def close(self, code=1000, reason=""):
                pass

            async def receive_json(self):
                return {"type": "message", "content": "go"}

            async def send_json(self, payload):
                self.sent += 1
                if self.sent > 3:
                    raise RuntimeError('Cannot call "send" once a close message has been sent.')

        # Not asyncio.run(): it finalises leftover generators on exit, which would hide a handler
        # that forgot to close the model stream itself
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(server.websocket_endpoint(GoneAfterThreeTokens(), cid, session_token=token))
            assert state["closed"] and state["yielded"] < 10      # stopped right after the failed send
        finally:
            loop.close()
        assert server.active_connections == {}


class TestHistory:
    def history(self, system_prompt, contents, provider="ollama", num_ctx=100):
        class Msg:
            def __init__(self, role, content): self.role, self.content = role, content
        class Conv:
            pass
        conv = Conv()
        conv.system_prompt = system_prompt
        conv.messages = [Msg("user" if i % 2 == 0 else "assistant", c) for i, c in enumerate(contents)]
        old = server.llm_client.num_ctx
        server.llm_client.num_ctx = num_ctx
        try:
            return server.history_for_model(conv, provider)
        finally:
            server.llm_client.num_ctx = old

    def test_everything_is_kept_when_it_fits(self):
        out = self.history("be brief", ["a", "b", "c"])
        assert [m["role"] for m in out] == ["system", "user", "assistant", "user"]

    def test_the_oldest_messages_go_first_and_the_system_prompt_stays(self):
        out = self.history("S" * 50, ["a" * 100, "b" * 100, "c" * 100], num_ctx=100)    # budget 300 - 50
        assert out[0]["role"] == "system"
        assert [m["content"][0] for m in out[1:]] == ["b", "c"]

    def test_the_newest_message_is_always_sent_however_large(self):
        out = self.history(None, ["a", "b" * 10_000], num_ctx=100)
        assert [len(m["content"]) for m in out] == [10_000]

    def test_only_the_last_20_messages_are_considered(self):
        out = self.history(None, [str(i) for i in range(30)], num_ctx=100_000)
        assert [m["content"] for m in out] == [str(i) for i in range(10, 30)]

    def test_cloud_providers_get_a_much_larger_budget(self):
        big = ["x" * 50_000] * 4
        assert len(self.history(None, big, provider="ollama", num_ctx=8192)) < 4
        assert len(self.history(None, big, provider="openai", num_ctx=8192)) == 4

    def test_the_server_uses_it_for_the_model_request(self, client, monkeypatch):
        seen = {}

        async def spy(messages, provider="ollama", model=None, temperature=0.7):
            seen["messages"] = messages
            yield "ok"

        monkeypatch.setattr(server.llm_client, "stream_completion", spy)
        cid = conversation(client, system_prompt="be brief")
        with client.websocket_connect(f"/ws/{cid}") as ws:
            ws.send_json({"type": "message", "content": "hi"})
            receive_until_end(ws)
        assert seen["messages"] == [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hi"}]


def test_the_ollama_request_asks_for_the_configured_context_window(monkeypatch):
    from tests.test_ollama_errors import FakeOllama, run_with_server, collect, tokens
    fake = FakeOllama()
    fake.lines = tokens("hi")

    def with_ctx(client):
        client.num_ctx = 12345
        return collect(client)

    run_with_server(fake, with_ctx)
    assert fake.requests[0]["options"]["num_ctx"] == 12345


def test_num_ctx_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("OLLAMA_NUM_CTX", "16384")
    assert LLMClient().num_ctx == 16384
    monkeypatch.delenv("OLLAMA_NUM_CTX")
    assert LLMClient().num_ctx == 8192


def test_expired_sessions_are_cleaned_up_at_startup():
    from datetime import datetime, timedelta
    from src.core.database import Session as SessionModel, User
    with server.db_manager.get_session() as db:
        user = User(username="cleanup-user", email="cleanup@example.com", password_hash="x")
        db.add(user)
        db.commit()
        db.add_all([
            SessionModel(id="expired-token", user_id=user.id, expires_at=datetime.utcnow() - timedelta(days=1)),
            SessionModel(id="live-token", user_id=user.id, expires_at=datetime.utcnow() + timedelta(days=1)),
        ])
        db.commit()
    from src.core.auth_manager import AuthManager
    with server.db_manager.get_session() as db:
        AuthManager(db).cleanup_expired_sessions()
        ids = {s.id for s in db.query(SessionModel).all()}
    assert "expired-token" not in ids and "live-token" in ids
