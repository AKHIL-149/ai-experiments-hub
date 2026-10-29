"""Simple LLM client for Ollama."""

import os
import requests


class GenerationError(Exception):
    """Raised when the model cannot produce text; the message is user-facing."""


class OllamaClient:
    """Client for Ollama API."""

    def __init__(self, model: str = None):
        self.ollama_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2")
        # True when the last generation stopped because it hit max_tokens
        self.truncated = False

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
                "num_predict": max_tokens
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
                f"Ollama did not finish within {timeout}s. Try a smaller --max-tokens "
                "or model, or raise OLLAMA_TIMEOUT."
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
