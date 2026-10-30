import os
import time
import requests
from typing import Optional


# Default cap on generated tokens. A step that must produce a long table or report needs
# more than a chat reply does; a step can lower or raise it with "max_tokens" in its task.
DEFAULT_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))

# Ollama silently drops the start of a prompt that does not fit its context window,
# so the window is sized to the prompt (3 characters per token is a safe estimate).
MIN_CONTEXT = 4096
MAX_CONTEXT = int(os.getenv("OLLAMA_MAX_CTX", "32768"))


def context_window_for(prompt: str, max_tokens: int) -> int:
    """Context size (a multiple of 1024) that fits the prompt plus the reply."""
    needed = len(prompt) // 3 + max_tokens + 256
    return min(MAX_CONTEXT, max(MIN_CONTEXT, -(-needed // 1024) * 1024))


class LLMClient:
    """Unified interface for different LLM backends."""

    def __init__(self, backend: str = "ollama", model: Optional[str] = None):
        self.backend = backend.lower()
        self.model = model or self._get_default_model()
        # True when the last reply was cut off by the token limit
        self.truncated = False

        if self.backend == "anthropic":
            import anthropic
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not found in environment")
            self.client = anthropic.Anthropic(api_key=api_key)

        elif self.backend == "openai":
            import openai
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

    def generate(self, prompt: str, max_tokens: int = None, temperature: float = 0.7) -> str:
        """Generate text based on prompt. Sets self.truncated when the reply hit max_tokens."""
        max_tokens = max_tokens or DEFAULT_MAX_TOKENS
        self.truncated = False
        try:
            if self.backend == "ollama":
                return self._generate_ollama(prompt, max_tokens, temperature)
            elif self.backend == "anthropic":
                return self._generate_anthropic(prompt, max_tokens, temperature)
            elif self.backend == "openai":
                return self._generate_openai(prompt, max_tokens, temperature)
        except Exception as e:
            raise Exception(f"Generation failed: {str(e)}")

    def _generate_ollama(self, prompt: str, max_tokens: int, temperature: float) -> str:
        """Generate using Ollama local model."""
        url = f"{self.ollama_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": context_window_for(prompt, max_tokens)
            }
        }

        # Ollama occasionally answers 500 (e.g. while swapping models) or drops the
        # connection; retry briefly so one blip doesn't fail a whole workflow step
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
                response = requests.post(
                    url, json=payload, timeout=int(os.getenv("OLLAMA_TIMEOUT", "240"))
                )
                if response.status_code >= 500 and attempt < attempts:
                    time.sleep(2 * attempt)
                    continue
                response.raise_for_status()
                data = response.json()
                self.truncated = data.get("done_reason") == "length"
                return data["response"]
            except (requests.ConnectionError, requests.Timeout):
                if attempt == attempts:
                    raise
                time.sleep(2 * attempt)

    def _generate_anthropic(self, prompt: str, max_tokens: int, temperature: float) -> str:
        """Generate using Anthropic Claude."""
        message = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        self.truncated = message.stop_reason == "max_tokens"
        return message.content[0].text

    def _generate_openai(self, prompt: str, max_tokens: int, temperature: float) -> str:
        """Generate using OpenAI."""
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        self.truncated = response.choices[0].finish_reason == "length"
        return response.choices[0].message.content
