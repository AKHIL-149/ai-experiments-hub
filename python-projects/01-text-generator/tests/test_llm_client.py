import sys
import types

import pytest
import requests

import llm_client
from llm_client import GenerationError, LLMClient


class FakeResponse:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload
        self.text = text or (str(payload) if payload is not None else "")
        self.ok = status < 400

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("OLLAMA_MODEL", "OLLAMA_API_URL", "OLLAMA_TIMEOUT", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


# ---- construction / defaults
def test_default_models():
    assert LLMClient("ollama").model == "llama3.2"
    assert LLMClient("ollama").ollama_url == "http://localhost:11434"


def test_ollama_env_overrides(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    monkeypatch.setenv("OLLAMA_API_URL", "http://example:1234")
    c = LLMClient("ollama")
    assert (c.model, c.ollama_url) == ("qwen3:8b", "http://example:1234")


def test_explicit_model_beats_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    assert LLMClient("ollama", model="x").model == "x"


def test_backend_is_case_insensitive():
    assert LLMClient("OLLAMA").backend == "ollama"


def test_unsupported_backend():
    with pytest.raises(ValueError):
        LLMClient("bard")


@pytest.mark.parametrize("backend,var", [("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY")])
def test_missing_api_key(backend, var, monkeypatch):
    monkeypatch.setitem(sys.modules, backend, types.ModuleType(backend))
    with pytest.raises(ValueError, match=var):
        LLMClient(backend)


# ---- ollama
def test_ollama_success_payload_and_options(monkeypatch):
    seen = {}

    def fake_post(url, json, timeout):
        seen.update(url=url, json=json, timeout=timeout)
        return FakeResponse(200, {"response": "hello", "done_reason": "stop"})

    monkeypatch.setattr(requests, "post", fake_post)
    c = LLMClient("ollama")
    assert c.generate("hi", max_tokens=42, temperature=0.2) == "hello"
    assert c.truncated is False
    assert seen["url"] == "http://localhost:11434/api/generate"
    assert seen["json"]["model"] == "llama3.2"
    assert seen["json"]["stream"] is False
    assert seen["json"]["options"] == {"temperature": 0.2, "num_predict": 42}
    assert seen["timeout"] == 120


def test_ollama_timeout_env(monkeypatch):
    seen = {}
    monkeypatch.setenv("OLLAMA_TIMEOUT", "7")
    monkeypatch.setattr(
        requests, "post",
        lambda url, json, timeout: seen.update(t=timeout) or FakeResponse(200, {"response": "x"}),
    )
    LLMClient("ollama").generate("hi")
    assert seen["t"] == 7


def test_ollama_truncation_flag(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(200, {"response": "abc", "done_reason": "length"}))
    c = LLMClient("ollama")
    c.generate("hi")
    assert c.truncated is True


def test_truncated_flag_resets_between_calls(monkeypatch):
    replies = iter([{"response": "a", "done_reason": "length"}, {"response": "b", "done_reason": "stop"}])
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(200, next(replies)))
    c = LLMClient("ollama")
    c.generate("1")
    assert c.truncated is True
    c.generate("2")
    assert c.truncated is False


def test_ollama_connection_error_is_friendly(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("Max retries exceeded ... <urllib3 internals>")

    monkeypatch.setattr(requests, "post", boom)
    with pytest.raises(GenerationError) as exc:
        LLMClient("ollama").generate("hi")
    msg = str(exc.value)
    assert "Cannot reach Ollama" in msg and "ollama serve" in msg
    assert "urllib3" not in msg


def test_ollama_timeout_is_friendly(monkeypatch):
    def boom(*a, **k):
        raise requests.Timeout()

    monkeypatch.setattr(requests, "post", boom)
    with pytest.raises(GenerationError, match="OLLAMA_TIMEOUT"):
        LLMClient("ollama").generate("hi")


def test_ollama_missing_model_message(monkeypatch):
    monkeypatch.setattr(
        requests, "post",
        lambda *a, **k: FakeResponse(404, {"error": "model 'foo' not found"}),
    )
    with pytest.raises(GenerationError, match="ollama pull foo"):
        LLMClient("ollama", model="foo").generate("hi")


def test_ollama_other_http_error_includes_server_message(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(500, {"error": "out of memory"}))
    with pytest.raises(GenerationError, match="500.*out of memory"):
        LLMClient("ollama").generate("hi")


def test_ollama_non_json_error_body(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: FakeResponse(502, None, text="Bad Gateway"))
    with pytest.raises(GenerationError, match="Bad Gateway"):
        LLMClient("ollama").generate("hi")


# ---- anthropic / openai with fake SDKs
def _install_fake_anthropic(monkeypatch, stop_reason="end_turn", text="claude says hi", error=None):
    calls = {}

    class Messages:
        def create(self, **kw):
            calls.update(kw)
            if error:
                raise error
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(text=text)], stop_reason=stop_reason
            )

    mod = types.ModuleType("anthropic")
    mod.Anthropic = lambda api_key: types.SimpleNamespace(messages=Messages())
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    return calls


def test_anthropic_success_and_default_model(monkeypatch):
    calls = _install_fake_anthropic(monkeypatch)
    c = LLMClient("anthropic")
    assert c.generate("hi", max_tokens=55, temperature=0.4) == "claude says hi"
    assert calls["model"] == "claude-sonnet-5-5"
    assert calls["max_tokens"] == 55 and calls["temperature"] == 0.4
    assert calls["messages"] == [{"role": "user", "content": "hi"}]
    assert c.truncated is False


def test_anthropic_truncation(monkeypatch):
    _install_fake_anthropic(monkeypatch, stop_reason="max_tokens")
    c = LLMClient("anthropic")
    c.generate("hi")
    assert c.truncated is True


def test_anthropic_error_wrapped(monkeypatch):
    _install_fake_anthropic(monkeypatch, error=RuntimeError("401 invalid x-api-key"))
    with pytest.raises(GenerationError, match="Generation failed: 401 invalid x-api-key"):
        LLMClient("anthropic").generate("hi")


def _install_fake_openai(monkeypatch, finish="stop", content="gpt says hi"):
    calls = {}

    class Completions:
        def create(self, **kw):
            calls.update(kw)
            return types.SimpleNamespace(
                choices=[types.SimpleNamespace(
                    message=types.SimpleNamespace(content=content), finish_reason=finish
                )]
            )

    mod = types.ModuleType("openai")
    mod.OpenAI = lambda api_key: types.SimpleNamespace(chat=types.SimpleNamespace(completions=Completions()))
    monkeypatch.setitem(sys.modules, "openai", mod)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    return calls


def test_openai_success_and_default_model(monkeypatch):
    calls = _install_fake_openai(monkeypatch)
    c = LLMClient("openai")
    assert c.generate("hi", max_tokens=9, temperature=1.1) == "gpt says hi"
    assert calls["model"] == "gpt-4o-mini" and calls["max_tokens"] == 9
    assert c.truncated is False


def test_openai_truncation(monkeypatch):
    _install_fake_openai(monkeypatch, finish="length")
    c = LLMClient("openai")
    c.generate("hi")
    assert c.truncated is True
