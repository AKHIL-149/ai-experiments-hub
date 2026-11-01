"""The server's side of the same bug: an empty reply must be an error, never a saved message."""

import pytest
from fastapi.testclient import TestClient

import server


@pytest.fixture
def client():
    with TestClient(server.app) as c:
        assert c.post("/api/auth/guest").status_code == 200
        yield c


def new_conversation(client, **fields):
    response = client.post("/api/conversations", json={"llm_provider": "ollama", "llm_model": "llama3.2:3b", **fields})
    assert response.status_code == 200, response.text
    return response.json()["id"]


def send(client, conversation_id, content="hello"):
    """Send one message over the WebSocket; returns every message the server sent back"""
    received = []
    with client.websocket_connect(f"/ws/{conversation_id}") as ws:
        ws.send_json({"type": "message", "content": content})
        while True:
            message = ws.receive_json()
            received.append(message)
            if message["type"] in ("done", "error"):
                return received


def saved_messages(client, conversation_id):
    return client.get(f"/api/conversations/{conversation_id}/messages").json()


def fake_stream(monkeypatch, tokens=(), error=None):
    async def stream(messages, provider="ollama", model=None, temperature=0.7):
        for token in tokens:
            yield token
        if error:
            raise error
    monkeypatch.setattr(server.llm_client, "stream_completion", stream)


def messages_of(payload):
    return payload["messages"] if isinstance(payload, dict) else payload


def test_a_normal_reply_is_streamed_and_saved(client, monkeypatch):
    fake_stream(monkeypatch, tokens=["Hel", "lo"])
    conversation = new_conversation(client)
    received = send(client, conversation)
    assert [m["type"] for m in received] == ["token", "token", "done"]
    saved = messages_of(saved_messages(client, conversation))
    assert [(m["role"], m["content"]) for m in saved] == [("user", "hello"), ("assistant", "Hello")]


def test_an_empty_reply_is_reported_and_not_saved(client, monkeypatch):
    fake_stream(monkeypatch, tokens=[])
    conversation = new_conversation(client)
    received = send(client, conversation)
    assert received[-1]["type"] == "error" and "empty response" in received[-1]["error"]
    roles = [m["role"] for m in messages_of(saved_messages(client, conversation))]
    assert roles == ["user"]                      # no blank assistant message


def test_whitespace_only_reply_counts_as_empty(client, monkeypatch):
    fake_stream(monkeypatch, tokens=["  ", "\n"])
    conversation = new_conversation(client)
    assert send(client, conversation)[-1]["type"] == "error"
    assert [m["role"] for m in messages_of(saved_messages(client, conversation))] == ["user"]


def test_a_provider_error_reaches_the_page_and_nothing_is_saved(client, monkeypatch):
    fake_stream(monkeypatch, error=RuntimeError("Ollama does not have the model 'phi3:mini'. Install it with: ollama pull phi3:mini"))
    conversation = new_conversation(client, llm_model="phi3:mini")
    received = send(client, conversation)
    assert received[-1] == {"type": "error", "error": "Ollama does not have the model 'phi3:mini'. Install it with: ollama pull phi3:mini"}
    assert [m["role"] for m in messages_of(saved_messages(client, conversation))] == ["user"]


def test_a_failure_after_some_text_saves_nothing_either(client, monkeypatch):
    fake_stream(monkeypatch, tokens=["partial"], error=RuntimeError("Ollama error: crashed"))
    conversation = new_conversation(client)
    received = send(client, conversation)
    assert [m["type"] for m in received] == ["token", "error"]
    assert [m["role"] for m in messages_of(saved_messages(client, conversation))] == ["user"]


def test_the_conversation_keeps_working_after_a_failed_reply(client, monkeypatch):
    conversation = new_conversation(client)
    fake_stream(monkeypatch, tokens=[])
    assert send(client, conversation)[-1]["type"] == "error"
    fake_stream(monkeypatch, tokens=["fine"])
    assert send(client, conversation, "again")[-1]["type"] == "done"


class TestModelsEndpoint:
    def test_requires_a_login(self):
        with TestClient(server.app) as anonymous:
            assert anonymous.get("/api/models").status_code == 401

    def test_returns_what_ollama_has(self, client, monkeypatch):
        async def installed():
            return ["llama3.2:3b", "qwen3:8b"]
        monkeypatch.setattr(server.llm_client, "list_ollama_models", installed)
        assert client.get("/api/models").json() == {"ollama": ["llama3.2:3b", "qwen3:8b"]}

    def test_empty_list_when_ollama_is_unreachable(self, client, monkeypatch):
        async def none():
            return []
        monkeypatch.setattr(server.llm_client, "list_ollama_models", none)
        assert client.get("/api/models").json() == {"ollama": []}
