import pytest
import requests

from llm_client import GenerationError, LLMClient


class Resp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code, self._p, self.text, self.ok = status, payload, text, status < 400

    def json(self):
        if self._p is None:
            raise ValueError
        return self._p


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for v in ("OLLAMA_MODEL", "OLLAMA_API_URL", "OLLAMA_TIMEOUT"):
        monkeypatch.delenv(v, raising=False)


@pytest.mark.parametrize("chars,max_tokens,expected", [
    (100, 1000, 4096),          # never below 4096
    (12000, 1000, 6144),        # grows with the prompt
    (24000, 1000, 10240),
    (10_000_000, 1000, 32768),  # capped
])
def test_context_window_sizing(chars, max_tokens, expected):
    assert LLMClient.context_window_for("x" * chars, max_tokens) == expected


def test_request_carries_context_window_and_options(monkeypatch):
    seen = {}

    def post(url, json, timeout):
        seen.update(json=json, timeout=timeout)
        return Resp(200, {"response": "hi", "done_reason": "length"})

    monkeypatch.setattr(requests, "post", post)
    c = LLMClient()
    assert c.generate("x" * 24000, temperature=0.2, max_tokens=300) == "hi"
    opts = seen["json"]["options"]
    assert opts["temperature"] == 0.2 and opts["num_predict"] == 300 and opts["num_ctx"] >= 8000
    assert c.truncated is True and seen["timeout"] == 120


def test_friendly_errors(monkeypatch):
    c = LLMClient()
    monkeypatch.setattr(requests, "post", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("urllib3")))
    with pytest.raises(GenerationError, match="ollama serve"):
        c.generate("p")
    monkeypatch.setattr(requests, "post", lambda *a, **k: (_ for _ in ()).throw(requests.Timeout()))
    with pytest.raises(GenerationError, match="OLLAMA_TIMEOUT"):
        c.generate("p")
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp(404, {"error": "model 'x' not found"}))
    with pytest.raises(GenerationError, match="ollama pull"):
        c.generate("p")
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp(500, {"error": "oom"}))
    with pytest.raises(GenerationError, match="500.*oom"):
        c.generate("p")
