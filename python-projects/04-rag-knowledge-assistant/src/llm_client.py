"""LLM client for generating responses."""

import math
import os
import requests


class GenerationError(Exception):
    """Raised when the model cannot produce text; the message is user-facing."""


class LLMClient:
    """Simple Ollama client for text generation."""

    def __init__(self, model: str = None):
        self.ollama_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2")
        # True when the last generation stopped because it hit max_tokens
        self.truncated = False

    @staticmethod
    def context_window_for(prompt: str, max_tokens: int) -> int:
        """Context size (tokens) big enough for the prompt plus the answer.

        Ollama's default window is small; a prompt that does not fit is silently cut,
        which drops the retrieved context or the question. Estimate ~3 chars/token.
        """
        needed = math.ceil(len(prompt) / 3) + max_tokens + 256
        return min(max(4096, math.ceil(needed / 1024) * 1024), 32768)

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1000) -> str:
        """Generate text using Ollama."""
        self.truncated = False
        url = f"{self.ollama_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self.context_window_for(prompt, max_tokens)
            }
        }

        timeout = int(os.getenv("OLLAMA_TIMEOUT", "120"))
        try:
            response = requests.post(url, json=payload, timeout=timeout)
        except requests.ConnectionError:
            raise GenerationError(
                f"Cannot reach Ollama at {self.ollama_url}. "
                "Is it running? Start it with: ollama serve"
            )
        except requests.Timeout:
            raise GenerationError(
                f"Ollama did not finish within {timeout}s. Try a smaller model or "
                "fewer/shorter chunks (--top-k, --chunk-size), or raise OLLAMA_TIMEOUT."
            )

        if not response.ok:
            try:
                detail = response.json().get("error", response.text)
            except ValueError:
                detail = response.text
            if response.status_code == 404 and "not found" in detail.lower():
                raise GenerationError(
                    f"Model '{self.model}' is not installed. Install it with: ollama pull {self.model}"
                )
            raise GenerationError(f"Ollama error ({response.status_code}): {detail}")

        data = response.json()
        self.truncated = data.get("done_reason") == "length"
        return data["response"]
