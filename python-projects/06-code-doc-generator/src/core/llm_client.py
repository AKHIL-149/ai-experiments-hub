"""Unified LLM client interface for multiple backends"""
import os
import time
from typing import Optional

import requests

from .settings import default_provider  # noqa: F401  (also loads .env)

# Ollama silently drops the start of a prompt that does not fit its context window, so the
# window is sized to the prompt (3 characters per token is a safe estimate).
MIN_CONTEXT = 4096
MAX_CONTEXT = int(os.getenv("OLLAMA_MAX_CTX", "32768"))


def context_window_for(prompt: str, system: str, max_tokens: int) -> int:
    """Context size (a multiple of 1024) that fits the prompt, the system text and the reply."""
    needed = (len(prompt) + len(system or "")) // 3 + max_tokens + 256
    return min(MAX_CONTEXT, max(MIN_CONTEXT, -(-needed // 1024) * 1024))


class LLMError(Exception):
    """A generation failure with a one-line, user-readable message.

    kind: unavailable (backend not reachable), auth (key rejected), model (not installed/found),
          timeout, rate_limit, empty (no text came back) or other.
    permanent: retrying within the same run cannot help (backend down, bad key, missing model).
    """

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind

    @property
    def permanent(self) -> bool:
        return self.kind in ("unavailable", "auth", "model")


class LLMClient:
    """Unified interface for different LLM backends (Ollama, Anthropic, OpenAI)."""

    def __init__(self, backend: str = "ollama", model: Optional[str] = None):
        """
        Initialize LLM client.

        Args:
            backend: LLM backend to use ('ollama', 'anthropic', or 'openai')
            model: Model name (uses defaults if not specified)
        """
        self.backend = backend.lower()
        self.model = model or self._get_default_model()
        # True when the last reply was cut off by the token limit
        self.truncated = False

        # Lazy import and initialization for optional dependencies
        if self.backend == "anthropic":
            try:
                import anthropic
            except ImportError:
                raise ImportError(
                    "anthropic package required for Anthropic backend. "
                    "Install it with: pip install anthropic"
                )
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not found in environment")
            self.client = anthropic.Anthropic(api_key=api_key)

        elif self.backend == "openai":
            try:
                import openai
            except ImportError:
                raise ImportError(
                    "openai package required for OpenAI backend. "
                    "Install it with: pip install openai"
                )
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in environment")
            self.client = openai.OpenAI(api_key=api_key)

        elif self.backend == "ollama":
            self.ollama_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")

        else:
            raise ValueError(f"Unsupported backend: {backend}")

    def _get_default_model(self) -> str:
        """Get default model for each backend."""
        defaults = {
            "ollama": os.getenv("OLLAMA_MODEL", "llama3.2"),
            "anthropic": "claude-3-5-sonnet-20241022",
            "openai": "gpt-4o-mini"
        }
        return defaults.get(self.backend, "llama3.2")

    @staticmethod
    def _timeout() -> float:
        try:
            return float(os.getenv("LLM_TIMEOUT", "120"))
        except ValueError:
            return 120.0

    def generate(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7,
        system: Optional[str] = None
    ) -> str:
        """
        Generate text based on prompt.

        Args:
            prompt: The input prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 to 1.0)
            system: Optional system message/instructions

        Returns:
            Generated text response; self.truncated says whether it hit max_tokens

        Raises:
            LLMError: with a one-line message and a kind (see LLMError)
        """
        self.truncated = False
        if self.backend == "ollama":
            return self._generate_ollama(prompt, max_tokens, temperature, system)
        if self.backend == "anthropic":
            return self._generate_anthropic(prompt, max_tokens, temperature, system)
        return self._generate_openai(prompt, max_tokens, temperature, system)

    # ------------------------------------------------------------------ Ollama

    def _generate_ollama(self, prompt, max_tokens, temperature, system) -> str:
        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            # Thinking models spend the token budget reasoning first; documentation wants the answer
            "think": os.getenv("OLLAMA_THINK", "false").lower() == "true",
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": context_window_for(prompt, system or "", max_tokens),
            },
        }
        if system:
            payload["system"] = system

        timeout = self._timeout()
        data = None
        for attempt in (1, 2):
            try:
                response = requests.post(url, json=payload, timeout=(5, timeout))
            except requests.Timeout:
                raise LLMError("timeout", f"{self.model} did not answer within {timeout:g}s")
            except requests.ConnectionError:
                raise LLMError("unavailable", f"Cannot reach Ollama at {self.ollama_url}. Is it running? Start it with: ollama serve")

            if response.status_code >= 500 and attempt == 1:
                time.sleep(1)  # one retry: Ollama answers 500 while it swaps models
                continue
            if response.status_code >= 400:
                raise self._ollama_error(response)
            try:
                data = response.json()
            except ValueError:
                raise LLMError("other", "Ollama sent an invalid reply (not JSON)")
            break

        text = data.get("response") or ""
        self.truncated = data.get("done_reason") == "length"
        if not text.strip():
            if self.truncated:
                raise LLMError("empty", f"{self.model} used its whole token limit before it answered (thinking models do this)")
            raise LLMError("empty", f"{self.model} returned an empty reply")
        return text

    def _ollama_error(self, response) -> LLMError:
        try:
            detail = (response.json() or {}).get("error") or ""
        except ValueError:
            detail = ""
        detail = " ".join(str(detail).split()) or f"HTTP {response.status_code}"
        if response.status_code == 404 and "not found" in detail.lower():
            return LLMError("model", f"Model '{self.model}' is not installed. Install it with: ollama pull {self.model}")
        return LLMError("other", f"Ollama error ({response.status_code}): {detail}")

    # ------------------------------------------------------------------ hosted providers

    @staticmethod
    def _classify(error: Exception, provider: str) -> LLMError:
        """Turn an SDK exception into an LLMError without depending on the SDK's own classes."""
        status = getattr(error, "status_code", None)
        name = type(error).__name__
        detail = " ".join(str(error).split())[:200]
        if status in (401, 403):
            return LLMError("auth", f"{provider} rejected the API key ({status}). Check it in your .env file")
        if status == 404:
            return LLMError("model", f"{provider} does not know this model name")
        if status == 429:
            return LLMError("rate_limit", f"{provider} rate limit reached; try again in a moment")
        if "Timeout" in name:
            return LLMError("timeout", f"{provider} did not answer in time")
        if "Connection" in name:
            return LLMError("unavailable", f"Cannot reach {provider}. Check your network connection")
        return LLMError("other", f"{provider} error: {detail or name}")

    def _generate_anthropic(self, prompt, max_tokens, temperature, system) -> str:
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        try:
            message = self.client.messages.create(**kwargs)
        except Exception as error:
            raise self._classify(error, "Anthropic")

        self.truncated = getattr(message, "stop_reason", None) == "max_tokens"
        text = message.content[0].text if message.content else ""
        if not text or not text.strip():
            raise LLMError("empty", f"{self.model} returned an empty reply")
        return text

    def _generate_openai(self, prompt, max_tokens, temperature, system) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            response = self.client.chat.completions.create(
                model=self.model, max_tokens=max_tokens, temperature=temperature, messages=messages
            )
        except Exception as error:
            raise self._classify(error, "OpenAI")

        choice = response.choices[0]
        self.truncated = getattr(choice, "finish_reason", None) == "length"
        text = choice.message.content
        if not text or not text.strip():
            raise LLMError("empty", f"{self.model} returned an empty reply")
        return text
