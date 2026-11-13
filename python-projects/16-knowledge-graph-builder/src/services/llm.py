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
    def generate_json(self, system: str, prompt: str, schema: dict) -> dict:
        """Return a dict that follows `schema`. Raise LLMError on any failure."""


def _parse_json(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"):] if "{" in text else text
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise LLMBadOutput("The model did not return JSON")
        try:
            value = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise LLMBadOutput("The model returned broken JSON") from exc
    if not isinstance(value, dict):
        raise LLMBadOutput("The model returned JSON that is not an object")
    return value


class OllamaClient(LLMClient):
    def __init__(self, base_url: str, model: str, num_ctx: int = 8192, timeout: float = 300.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.timeout = timeout
        self.name = f"ollama:{model}"

    def generate_json(self, system: str, prompt: str, schema: dict) -> dict:
        body = {
            "model": self.model,
            "stream": False,
            "format": schema,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "options": {"temperature": 0, "num_ctx": self.num_ctx},
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

    def generate_json(self, system: str, prompt: str, schema: dict) -> dict:
        import anthropic
        client = anthropic.Anthropic(api_key=self.api_key)
        try:
            msg = client.messages.create(
                model=self.model, max_tokens=4096, temperature=0, system=system,
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

    def generate_json(self, system: str, prompt: str, schema: dict) -> dict:
        import openai
        client = openai.OpenAI(api_key=self.api_key)
        try:
            resp = client.chat.completions.create(
                model=self.model, temperature=0,
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
        return OllamaClient(s.ollama_base_url, s.ollama_model, s.ollama_num_ctx, s.ollama_timeout)
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
