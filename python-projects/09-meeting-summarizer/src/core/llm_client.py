"""LLM Client - Unified interface for multiple LLM backends"""

import os
import time
import requests
import logging
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Unified interface for different LLM backends:
    - OpenAI (GPT-4, GPT-3.5)
    - Anthropic (Claude)
    - Ollama (local models)
    """

    def __init__(
        self,
        backend: str = "openai",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        ollama_num_ctx: Optional[int] = None
    ):
        """
        Initialize LLM Client

        Args:
            backend: "openai", "anthropic", or "ollama"
            model: Model name (optional, uses defaults)
            api_key: API key (optional, reads from env)
            ollama_num_ctx: Context window to request from Ollama (default OLLAMA_NUM_CTX
                or 8192). Ollama's own default is 4096 tokens and it silently drops
                whatever does not fit - about a 20 minute meeting's worth of transcript.
        """
        self.backend = backend.lower()
        self.model = model or self._get_default_model()
        self.client = None
        self.num_ctx = int(ollama_num_ctx or os.getenv("OLLAMA_NUM_CTX", 8192))

        # Initialize backend client
        if self.backend == "openai":
            from openai import OpenAI
            key = api_key or os.getenv("OPENAI_API_KEY")
            if not key:
                raise ValueError("OPENAI_API_KEY not found")
            self.client = OpenAI(api_key=key)
            logger.info(f"Initialized OpenAI client (model: {self.model})")

        elif self.backend == "anthropic":
            import anthropic
            key = api_key or os.getenv("ANTHROPIC_API_KEY")
            if not key:
                raise ValueError("ANTHROPIC_API_KEY not found")
            self.client = anthropic.Anthropic(api_key=key)
            logger.info(f"Initialized Anthropic client (model: {self.model})")

        elif self.backend == "ollama":
            self.ollama_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
            logger.info(f"Initialized Ollama client (model: {self.model}, url: {self.ollama_url})")

        else:
            raise ValueError(f"Unsupported backend: {backend}")

    def _get_default_model(self) -> str:
        """Get default model for each backend"""
        defaults = {
            "openai": os.getenv("LLM_MODEL", "gpt-4o-mini"),
            "anthropic": os.getenv("LLM_MODEL", "claude-3-5-sonnet-20241022"),
            "ollama": os.getenv("OLLAMA_MODEL", "llama3.2")
        }
        return defaults.get(self.backend, "gpt-4o-mini")

    def generate(
        self,
        prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        json_mode: bool = False
    ) -> Dict:
        """
        Generate text from prompt

        Args:
            prompt: User prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-1)
            system_prompt: Optional system message
            json_mode: Ask the model for a single valid JSON object (OpenAI and Ollama
                enforce it; for Anthropic the prompt has to ask for it)

        Returns:
            dict with response and usage info:
                {
                    "text": str,
                    "tokens": {"prompt": int, "completion": int, "total": int}
                }
        """
        try:
            if self.backend == "openai":
                return self._generate_openai(prompt, max_tokens, temperature, system_prompt, json_mode)
            elif self.backend == "anthropic":
                return self._generate_anthropic(prompt, max_tokens, temperature, system_prompt)
            elif self.backend == "ollama":
                return self._generate_ollama(prompt, max_tokens, temperature, system_prompt, json_mode)
        except Exception as e:
            logger.error(f"Generation failed: {str(e)}")
            raise RuntimeError(f"LLM generation failed: {str(e)}")

    def generate_with_messages(
        self,
        messages: List[Dict],
        max_tokens: int = 2000,
        temperature: float = 0.7
    ) -> Dict:
        """
        Generate text from conversation messages

        Args:
            messages: List of message dicts with "role" and "content"
                     [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature

        Returns:
            dict with response and usage info
        """
        try:
            if self.backend == "openai":
                return self._generate_openai_messages(messages, max_tokens, temperature)
            elif self.backend == "anthropic":
                return self._generate_anthropic_messages(messages, max_tokens, temperature)
            elif self.backend == "ollama":
                return self._generate_ollama_messages(messages, max_tokens, temperature)
        except Exception as e:
            logger.error(f"Generation with messages failed: {str(e)}")
            raise RuntimeError(f"LLM generation failed: {str(e)}")

    def _generate_openai(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str],
        json_mode: bool = False
    ) -> Dict:
        """Generate using OpenAI"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        kwargs = {}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            **kwargs
        )

        return {
            "text": response.choices[0].message.content,
            "tokens": {
                "prompt": response.usage.prompt_tokens,
                "completion": response.usage.completion_tokens,
                "total": response.usage.total_tokens
            }
        }

    def _generate_openai_messages(
        self,
        messages: List[Dict],
        max_tokens: int,
        temperature: float
    ) -> Dict:
        """Generate using OpenAI with message list"""
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature
        )

        return {
            "text": response.choices[0].message.content,
            "tokens": {
                "prompt": response.usage.prompt_tokens,
                "completion": response.usage.completion_tokens,
                "total": response.usage.total_tokens
            }
        }

    def _generate_anthropic(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str]
    ) -> Dict:
        """Generate using Anthropic Claude"""
        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}]
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        message = self.client.messages.create(**kwargs)

        return {
            "text": message.content[0].text,
            "tokens": {
                "prompt": message.usage.input_tokens,
                "completion": message.usage.output_tokens,
                "total": message.usage.input_tokens + message.usage.output_tokens
            }
        }

    def _generate_anthropic_messages(
        self,
        messages: List[Dict],
        max_tokens: int,
        temperature: float
    ) -> Dict:
        """Generate using Anthropic with message list"""
        # Extract system message if present
        system_prompt = None
        user_messages = []

        for msg in messages:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            else:
                user_messages.append(msg)

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": user_messages
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        message = self.client.messages.create(**kwargs)

        return {
            "text": message.content[0].text,
            "tokens": {
                "prompt": message.usage.input_tokens,
                "completion": message.usage.output_tokens,
                "total": message.usage.input_tokens + message.usage.output_tokens
            }
        }

    def _ollama_post(self, endpoint: str, payload: Dict) -> Dict:
        """
        POST to Ollama and return its JSON. Failures become messages that say what to do
        (the raw requests errors are a connection-pool traceback, or "404 Client Error").
        """
        url = f"{self.ollama_url}{endpoint}"
        last_error = None

        for attempt in (1, 2):
            try:
                response = requests.post(url, json=payload, timeout=300)
            except requests.exceptions.ConnectionError as e:
                last_error = e
                if attempt == 1:
                    time.sleep(1.5)          # Ollama may be (re)loading a model
                    continue
                raise RuntimeError(
                    f"Could not reach Ollama at {self.ollama_url}. Is it running? Start it with: ollama serve"
                )
            except requests.exceptions.Timeout:
                raise RuntimeError(
                    f"Ollama did not answer within 5 minutes (model {self.model}). "
                    f"The model may be too large for this machine."
                )

            if response.status_code == 404:
                raise RuntimeError(
                    f"Ollama does not have the model '{self.model}'. Install it with: ollama pull {self.model}"
                )
            response.raise_for_status()
            return response.json()

        raise RuntimeError(f"Could not reach Ollama: {last_error}")

    def _note_truncation(self, prompt_tokens: int) -> bool:
        """
        Ollama silently drops the part of a prompt that does not fit the context window.
        It reports having read exactly num_ctx tokens when that happened.
        """
        truncated = prompt_tokens >= self.num_ctx - 8
        if truncated:
            logger.warning(
                f"The prompt filled Ollama's whole {self.num_ctx}-token context window - the model "
                f"may not have seen all of it. Raise OLLAMA_NUM_CTX, or use a shorter input."
            )
        return truncated

    def _generate_ollama(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str],
        json_mode: bool = False
    ) -> Dict:
        """Generate using Ollama"""
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self.num_ctx
            }
        }
        if json_mode:
            payload["format"] = "json"

        data = self._ollama_post("/api/generate", payload)
        prompt_tokens = data.get("prompt_eval_count", 0)

        return {
            "text": data["response"],
            "tokens": {
                "prompt": prompt_tokens,
                "completion": data.get("eval_count", 0),
                "total": prompt_tokens + data.get("eval_count", 0)
            },
            "truncated": self._note_truncation(prompt_tokens)
        }

    def _generate_ollama_messages(
        self,
        messages: List[Dict],
        max_tokens: int,
        temperature: float
    ) -> Dict:
        """Generate using Ollama with message list"""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": self.num_ctx
            }
        }

        data = self._ollama_post("/api/chat", payload)
        prompt_tokens = data.get("prompt_eval_count", 0)

        return {
            "text": data["message"]["content"],
            "tokens": {
                "prompt": prompt_tokens,
                "completion": data.get("eval_count", 0),
                "total": prompt_tokens + data.get("eval_count", 0)
            },
            "truncated": self._note_truncation(prompt_tokens)
        }

    def estimate_cost(self, tokens: Dict, backend: Optional[str] = None) -> float:
        """
        Estimate cost based on token usage

        Args:
            tokens: Token usage dict from generate()
            backend: Override backend (optional)

        Returns:
            Estimated cost in USD
        """
        backend = backend or self.backend

        # Pricing per 1K tokens (as of Jan 2025)
        pricing = {
            "openai": {
                "gpt-4o": {"input": 0.005, "output": 0.015},
                "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
                "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015}
            },
            "anthropic": {
                "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
                "claude-3-haiku-20240307": {"input": 0.00025, "output": 0.00125}
            },
            "ollama": {
                # Local models are free
                "default": {"input": 0.0, "output": 0.0}
            }
        }

        if backend == "ollama":
            return 0.0

        # Get pricing for model
        # Longest matching name wins: "gpt-4o-mini" contains "gpt-4o", and must be priced
        # as the mini model, not as gpt-4o (30x more).
        model_pricing = None
        if backend in pricing:
            matches = [name for name in pricing[backend] if name in self.model]
            if matches:
                model_pricing = pricing[backend][max(matches, key=len)]

        if not model_pricing:
            # Default to mid-range pricing
            model_pricing = {"input": 0.001, "output": 0.003}

        # Calculate cost
        input_cost = (tokens.get("prompt", 0) / 1000) * model_pricing["input"]
        output_cost = (tokens.get("completion", 0) / 1000) * model_pricing["output"]

        return input_cost + output_cost

    def get_info(self) -> Dict:
        """Get client information"""
        return {
            "backend": self.backend,
            "model": self.model,
            "ollama_url": getattr(self, "ollama_url", None)
        }
