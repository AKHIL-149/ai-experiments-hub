"""LLM clients that return JSON matching a schema. Ollama is the default; cloud providers are optional."""
import json
from abc import ABC, abstractmethod

import httpx

from src.core.config import Settings, get_settings


class LLMError(RuntimeError):
    """The model could not be reached or answered badly (message is safe to show to the user)"""


class LLMBadOutput(LLMError):
    """The model answered but not with usable JSON (worth one retry; not worth failing a whole document)"""


class LLMClient(ABC):
    name: str = "llm"

    @abstractmethod
    def generate_json(self, system: str, prompt: str, schema: dict, max_tokens: int | None = None) -> dict:
        """Return a dict that follows `schema`. `max_tokens` caps how much the model may write (None = the client's default).
        Raise LLMError on any failure."""


def _salvage(text: str) -> str | None:
    """A reply cut off by the token cap ('{"relations": [ {...}, {...}, {"subj') keeps every complete element: close the list"""
    start = text.find("{")
    if start < 0:
        return None
    depth, in_str, esc, last_ok = 0, False, False, None
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if depth == 2 and c == "}":   # an element of the list inside the top-level object is complete
                last_ok = i
    if last_ok is None:
        return None
    return text[start:last_ok + 1] + "]}"


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    value = None
    for candidate in (text, text[text.find("{"):text.rfind("}") + 1] if "{" in text and "}" in text else None, _salvage(text)):
        if not candidate:
            continue
        try:
            value = json.loads(candidate)
            break
        except json.JSONDecodeError:
            continue
    if value is None:
        raise LLMBadOutput("The model did not return JSON" if "{" not in text else "The model returned broken JSON")
    if not isinstance(value, dict):
        raise LLMBadOutput("The model returned JSON that is not an object")
    return value


class OllamaClient(LLMClient):
    def __init__(self, base_url: str, model: str, num_ctx: int = 8192, timeout: float = 300.0, max_tokens: int = 3072):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.name = f"ollama:{model}"

    def generate_json(self, system: str, prompt: str, schema: dict, max_tokens: int | None = None) -> dict:
        body = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "options": {"temperature": 0, "num_ctx": self.num_ctx, "num_predict": max_tokens or self.max_tokens},
        }
        try:
            r = httpx.post(f"{self.base_url}/api/chat", json=body, timeout=self.timeout)
        except httpx.ConnectError as exc:
            raise LLMError(f"Cannot reach Ollama at {self.base_url}. Is it running? (ollama serve)") from exc
        except httpx.TimeoutException as exc:
            raise LLMError(f"Ollama took longer than {self.timeout:.0f}s to answer") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Ollama request failed ({type(exc).__name__})") from exc
        if r.status_code == 404:
            raise LLMError(f"Ollama does not have the model '{self.model}'. Run: ollama pull {self.model}")
        if r.status_code != 200:
            raise LLMError(f"Ollama returned HTTP {r.status_code}")
        try:
            return _parse_json(r.json()["message"]["content"])
        except (KeyError, ValueError) as exc:
            raise LLMBadOutput("Ollama returned an unexpected response") from exc


class AnthropicClient(LLMClient):
    """Uses a forced tool call so the answer always follows the schema"""

    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model
        self.name = f"anthropic:{model}"

    def generate_json(self, system: str, prompt: str, schema: dict, max_tokens: int | None = None) -> dict:
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        try:
            msg = client.messages.create(
                model=self.model, max_tokens=max_tokens or 4096, temperature=0, system=system,
                messages=[{"role": "user", "content": prompt}],
                tools=[{"name": "answer", "description": "Return the answer", "input_schema": schema}],
                tool_choice={"type": "tool", "name": "answer"},
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic request failed ({type(exc).__name__})") from exc
        for block in msg.content:
            if getattr(block, "type", "") == "tool_use" and isinstance(block.input, dict):
                return block.input
        raise LLMBadOutput("Anthropic did not return a structured answer")


class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str):
        self.api_key, self.model = api_key, model
        self.name = f"openai:{model}"

    def generate_json(self, system: str, prompt: str, schema: dict, max_tokens: int | None = None) -> dict:
        import openai
        client = openai.OpenAI(api_key=self.api_key)
        try:
            resp = client.chat.completions.create(
                model=self.model, temperature=0, max_tokens=max_tokens or 4096,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenAI request failed ({type(exc).__name__})") from exc
        return _parse_json(resp.choices[0].message.content or "")


def get_llm(settings: Settings | None = None) -> LLMClient:
    s = settings or get_settings()
    provider = s.llm_provider.lower()
    if provider == "ollama":
        return OllamaClient(s.ollama_base_url, s.ollama_model, s.ollama_num_ctx, s.ollama_timeout, s.llm_max_tokens)
    if provider == "anthropic":
        if not s.anthropic_api_key:
            raise LLMError("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set")
        return AnthropicClient(s.anthropic_api_key, s.anthropic_model)
    if provider == "openai":
        if not s.openai_api_key:
            raise LLMError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set")
        return OpenAIClient(s.openai_api_key, s.openai_model)
    raise LLMError(f"Unknown LLM_PROVIDER '{s.llm_provider}' (use ollama, anthropic or openai)")


def llm_status(settings: Settings | None = None) -> dict:
    """Is the configured model usable right now? (cheap check, no generation)"""
    s = settings or get_settings()
    provider = s.llm_provider.lower()
    if provider == "ollama":
        try:
            r = httpx.get(f"{s.ollama_base_url.rstrip('/')}/api/tags", timeout=3)
            names = {m.get("name") for m in r.json().get("models", [])}
        except Exception:
            return {"provider": provider, "model": s.ollama_model, "ready": False,
                    "detail": f"Cannot reach Ollama at {s.ollama_base_url}"}
        have = s.ollama_model in names or f"{s.ollama_model}:latest" in names
        return {"provider": provider, "model": s.ollama_model, "ready": have,
                "detail": "ok" if have else f"Model not installed. Run: ollama pull {s.ollama_model}"}
    key = s.anthropic_api_key if provider == "anthropic" else s.openai_api_key if provider == "openai" else None
    model = s.anthropic_model if provider == "anthropic" else s.openai_model
    return {"provider": provider, "model": model, "ready": bool(key),
            "detail": "API key is set (not checked against the service)" if key else "API key is not set"}
