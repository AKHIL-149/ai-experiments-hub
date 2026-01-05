"""Unified LLM client interface for multiple backends"""
import os
import requests
from typing import Optional


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

        # Lazy import and initialization for optional dependencies
        if self.backend == "anthropic":
            try:
                import anthropic
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if not api_key:
                    raise ValueError("ANTHROPIC_API_KEY not found in environment")
                self.client = anthropic.Anthropic(api_key=api_key)
            except ImportError:
                raise ImportError(
                    "anthropic package required for Anthropic backend. "
                    "Install it with: pip install anthropic"
                )

        elif self.backend == "openai":
            try:
                import openai
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OPENAI_API_KEY not found in environment")
                self.client = openai.OpenAI(api_key=api_key)
            except ImportError:
                raise ImportError(
                    "openai package required for OpenAI backend. "
                    "Install it with: pip install openai"
                )

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
            Generated text response

        Raises:
            Exception: If generation fails
        """
        try:
            if self.backend == "ollama":
                return self._generate_ollama(prompt, max_tokens, temperature, system)
            elif self.backend == "anthropic":
                return self._generate_anthropic(prompt, max_tokens, temperature, system)
            elif self.backend == "openai":
                return self._generate_openai(prompt, max_tokens, temperature, system)
        except Exception as e:
            raise Exception(f"Generation failed ({self.backend}): {str(e)}")

    def _generate_ollama(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system: Optional[str]
    ) -> str:
        """Generate using Ollama local model."""
        url = f"{self.ollama_url}/api/generate"

        # Add system message to prompt if provided
        if system:
            full_prompt = f"{system}\n\n{prompt}"
        else:
            full_prompt = prompt

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        return response.json()["response"]

    def _generate_anthropic(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system: Optional[str]
    ) -> str:
        """Generate using Anthropic Claude."""
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}]
        }

        if system:
            kwargs["system"] = system

        message = self.client.messages.create(**kwargs)
        return message.content[0].text

    def _generate_openai(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system: Optional[str]
    ) -> str:
        """Generate using OpenAI."""
        messages = []

        if system:
            messages.append({"role": "system", "content": system})

        messages.append({"role": "user", "content": prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=messages
        )
        return response.choices[0].message.content
