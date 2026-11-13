import io

import docx
import httpx
import pytest

from src.core.config import Settings
from src.services import llm as llm_mod
from src.services.llm import LLMBadOutput, LLMError, OllamaClient, _parse_json, get_llm, llm_status
from src.services.readers import ReadError, clean_text, read_bytes


def test_text_encodings_and_cleaning():
    assert read_bytes("a.txt", "Café au lait.\r\n\r\n\r\n\r\nNext   line.".encode()) == "Café au lait.\n\nNext line."
    assert read_bytes("a.md", "﻿Hello world".encode("utf-8")) == "Hello world"
    assert read_bytes("a.txt", "Grüße".encode("utf-16")) == "Grüße"
    assert read_bytes("a.txt", b"caf\xe9 bar") == "café bar"  # latin-1 fallback
    assert clean_text("a\x00b") == "ab"
    assert clean_text("a\n\n\nb") == "a\n\nb"   # three blank-ish lines shrink to one paragraph break
    assert clean_text("a\n\nb") == "a\n\nb"


def test_docx_text_and_tables():
    d = docx.Document()
    d.add_paragraph("First paragraph.")
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Acme", "Beta"
    buf = io.BytesIO()
    d.save(buf)
    text = read_bytes("x.docx", buf.getvalue())
    assert "First paragraph." in text and "Acme | Beta" in text


@pytest.mark.parametrize("name,data", [("x.exe", b"1"), ("x", b"1"), ("x.txt", b""), ("x.txt", b"   \n "), ("x.pdf", b"junk")])
def test_unreadable_files_raise_readable_errors(name, data):
    with pytest.raises(ReadError):
        read_bytes(name, data)


def test_parse_json_variants():
    assert _parse_json('{"a": 1}') == {"a": 1}
    assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_json('Sure! {"a": 1} hope that helps') == {"a": 1}
    for bad in ("", "no json", "{broken", "[1, 2]"):
        with pytest.raises(LLMBadOutput):
            _parse_json(bad)


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


def ollama(monkeypatch, result):
    def post(url, json=None, timeout=None):
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(llm_mod.httpx, "post", post)
    return OllamaClient("http://x:11434/", "m", 4096, 5)


def test_ollama_success_and_error_messages(monkeypatch):
    ok = ollama(monkeypatch, Resp(200, {"message": {"content": '{"relations": []}'}}))
    assert ok.generate_json("s", "p", {}) == {"relations": []} and ok.name == "ollama:m"
    cases = [
        (httpx.ConnectError("x"), LLMError, "Cannot reach Ollama"),
        (httpx.ReadTimeout("x"), LLMError, "longer than"),
        (Resp(404, {}), LLMError, "ollama pull m"),
        (Resp(500, {}), LLMError, "HTTP 500"),
        (Resp(200, {"nope": 1}), LLMBadOutput, "unexpected"),
        (Resp(200, {"message": {"content": "not json"}}), LLMBadOutput, "JSON"),
    ]
    for result, exc, fragment in cases:
        with pytest.raises(exc, match=fragment):
            ollama(monkeypatch, result).generate_json("s", "p", {})


def test_ollama_request_is_deterministic_and_uses_the_schema(monkeypatch):
    sent = {}

    def post(url, json=None, timeout=None):
        sent.update(url=url, json=json, timeout=timeout)
        return Resp(200, {"message": {"content": "{}"}})
    monkeypatch.setattr(llm_mod.httpx, "post", post)
    OllamaClient("http://x:11434/", "m", 4096, 5).generate_json("sys", "usr", {"type": "object"})
    assert sent["url"] == "http://x:11434/api/chat" and sent["json"]["format"] == {"type": "object"}
    assert sent["json"]["options"] == {"temperature": 0, "num_ctx": 4096} and sent["json"]["stream"] is False
    assert [m["role"] for m in sent["json"]["messages"]] == ["system", "user"]


def test_provider_selection_and_missing_keys():
    s = lambda **kw: Settings(_env_file=None, **kw)  # noqa: E731
    assert get_llm(s()).name == "ollama:llama3.1:8b"
    assert get_llm(s(llm_provider="anthropic", anthropic_api_key="k")).name.startswith("anthropic:")
    assert get_llm(s(llm_provider="openai", openai_api_key="k")).name.startswith("openai:")
    for bad in (s(llm_provider="anthropic"), s(llm_provider="openai"), s(llm_provider="mystery")):
        with pytest.raises(LLMError):
            get_llm(bad)


def test_status_for_cloud_providers_never_calls_the_service():
    s = Settings(_env_file=None, llm_provider="anthropic", anthropic_api_key="k")
    assert llm_status(s)["ready"] is True
    assert llm_status(Settings(_env_file=None, llm_provider="openai"))["ready"] is False


def test_ollama_status_checks_the_installed_models(monkeypatch):
    monkeypatch.setattr(llm_mod.httpx, "get", lambda *a, **k: Resp(200, {"models": [{"name": "llama3.1:8b"}]}))
    assert llm_status(Settings(_env_file=None))["ready"] is True
    r = llm_status(Settings(_env_file=None, ollama_model="other"))
    assert r["ready"] is False and "ollama pull other" in r["detail"]
