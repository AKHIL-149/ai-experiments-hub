import pytest
import requests

from llm_client import GenerationError, OllamaClient


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


def test_defaults_and_overrides(monkeypatch):
    c = OllamaClient()
    assert (c.model, c.ollama_url) == ("llama3.2", "http://localhost:11434")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
    assert OllamaClient().model == "qwen3:8b"
    assert OllamaClient(model="x").model == "x"


def test_payload_and_truncation(monkeypatch):
    seen = {}

    def post(url, json, timeout):
        seen.update(url=url, json=json, timeout=timeout)
        return Resp(200, {"response": "hi", "done_reason": "length"})

    monkeypatch.setattr(requests, "post", post)
    c = OllamaClient()
    assert c.generate("p", temperature=0.3, max_tokens=50) == "hi"
    assert c.truncated is True
    assert seen["json"]["options"] == {"temperature": 0.3, "num_predict": 50}
    assert seen["json"]["stream"] is False and seen["timeout"] == 120


def test_connection_error_friendly(monkeypatch):
    def post(*a, **k):
        raise requests.ConnectionError("urllib3 internals")

    monkeypatch.setattr(requests, "post", post)
    with pytest.raises(GenerationError) as e:
        OllamaClient().generate("p")
    assert "ollama serve" in str(e.value) and "urllib3" not in str(e.value)


def test_timeout_friendly(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: (_ for _ in ()).throw(requests.Timeout()))
    with pytest.raises(GenerationError, match="OLLAMA_TIMEOUT"):
        OllamaClient().generate("p")


def test_missing_model(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp(404, {"error": "model 'zz' not found"}))
    with pytest.raises(GenerationError, match="ollama pull zz"):
        OllamaClient(model="zz").generate("p")


def test_other_http_errors(monkeypatch):
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp(500, {"error": "oom"}))
    with pytest.raises(GenerationError, match="500.*oom"):
        OllamaClient().generate("p")
    monkeypatch.setattr(requests, "post", lambda *a, **k: Resp(502, None, "Bad Gateway"))
    with pytest.raises(GenerationError, match="Bad Gateway"):
        OllamaClient().generate("p")
