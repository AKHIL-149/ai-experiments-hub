import os
import requests
from typing import Optional


class LLMClient:
    """Unified interface for different LLM backends."""

    def __init__(self, backend: str = "ollama", model: Optional[str] = None):
        self.backend = backend.lower()
        self.model = model or self._get_default_model()

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

    def generate(self, prompt: str, max_tokens: int = 1000, temperature: float = 0.7) -> str:
        """Generate text based on prompt."""
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
                "num_predict": max_tokens
            }
        }

        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()["response"]

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
        return response.choices[0].message.content
