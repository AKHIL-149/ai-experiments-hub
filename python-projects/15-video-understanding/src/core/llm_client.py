"""
LLM Client - Unified interface for multiple LLM backends
Enhanced with rate limiting and response caching for video summarization
"""

import os
import requests
import logging
import time
import hashlib
import json
from typing import Optional, Dict, List
from pathlib import Path

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Unified interface for different LLM backends:
    - OpenAI (GPT-4, GPT-3.5)
    - Anthropic (Claude)
    - Ollama (local models)

    Enhanced with:
    - Response caching
    - Rate limiting
    - Token counting
    """

    def __init__(
        self,
        backend: str = "openai",
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        enable_cache: bool = True,
        cache_dir: Optional[str] = None,
        rate_limit_rpm: Optional[int] = None,
    ):
        """
        Initialize LLM Client

        Args:
            backend: "openai", "anthropic", or "ollama"
            model: Model name (optional, uses defaults)
            api_key: API key (optional, reads from env)
            enable_cache: Enable response caching
            cache_dir: Cache directory (default: ./llm_cache)
            rate_limit_rpm: Rate limit in requests per minute
        """
        self.backend = backend.lower()
        self.model = model or self._get_default_model()
        self.client = None

        # Caching
        self.enable_cache = enable_cache
        self.cache_dir = Path(cache_dir or "./llm_cache")
        if self.enable_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Rate limiting
        self.rate_limit_rpm = rate_limit_rpm
        self.last_request_time = 0.0
        self.request_count = 0
        self.request_times = []

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

    def _get_cache_key(self, prompt: str, max_tokens: int, temperature: float, system_prompt: Optional[str]) -> str:
        """Generate cache key for request"""
        content = f"{self.backend}:{self.model}:{system_prompt}:{prompt}:{max_tokens}:{temperature}"
        return hashlib.sha256(content.encode()).hexdigest()

    def _load_from_cache(self, cache_key: str) -> Optional[Dict]:
        """Load response from cache"""
        if not self.enable_cache:
            return None

        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                logger.debug(f"Cache hit: {cache_key}")
                return data
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")

        return None

    def _save_to_cache(self, cache_key: str, response: Dict):
        """Save response to cache"""
        if not self.enable_cache:
            return

        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump(response, f)
            logger.debug(f"Cached response: {cache_key}")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def _apply_rate_limit(self):
        """Apply rate limiting"""
        if not self.rate_limit_rpm:
            return

        current_time = time.time()

        # Remove requests older than 1 minute
        self.request_times = [t for t in self.request_times if current_time - t < 60]

        # Check if we've exceeded the rate limit
        if len(self.request_times) >= self.rate_limit_rpm:
            # Wait until the oldest request is older than 1 minute
            sleep_time = 60 - (current_time - self.request_times[0]) + 0.1
            if sleep_time > 0:
                logger.info(f"Rate limit reached, sleeping for {sleep_time:.1f}s")
                time.sleep(sleep_time)

        # Record this request
        self.request_times.append(time.time())

    def generate(
        self,
        prompt: str,
        max_tokens: int = 2000,
        temperature: float = 0.7,
        system_prompt: Optional[str] = None,
        use_cache: bool = True,
    ) -> Dict:
        """
        Generate text from prompt

        Args:
            prompt: User prompt
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0-1)
            system_prompt: Optional system message
            use_cache: Use cached response if available

        Returns:
            dict with response and usage info:
                {
                    "text": str,
                    "tokens": {"prompt": int, "completion": int, "total": int},
                    "cached": bool
                }
        """
        # Check cache
        cache_key = self._get_cache_key(prompt, max_tokens, temperature, system_prompt)
        if use_cache and self.enable_cache:
            cached = self._load_from_cache(cache_key)
            if cached:
                cached["cached"] = True
                return cached

        # Apply rate limiting
        self._apply_rate_limit()

        try:
            if self.backend == "openai":
                result = self._generate_openai(prompt, max_tokens, temperature, system_prompt)
            elif self.backend == "anthropic":
                result = self._generate_anthropic(prompt, max_tokens, temperature, system_prompt)
            elif self.backend == "ollama":
                result = self._generate_ollama(prompt, max_tokens, temperature, system_prompt)

            result["cached"] = False

            # Save to cache
            if use_cache:
                self._save_to_cache(cache_key, result)

            return result

        except Exception as e:
            logger.error(f"Generation failed: {str(e)}")
            raise RuntimeError(f"LLM generation failed: {str(e)}")

    def generate_with_messages(
        self,
        messages: List[Dict],
        max_tokens: int = 2000,
        temperature: float = 0.7,
        use_cache: bool = True,
    ) -> Dict:
        """
        Generate text from conversation messages

        Args:
            messages: List of message dicts with "role" and "content"
                     [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature
            use_cache: Use cached response if available

        Returns:
            dict with response and usage info
        """
        # Create cache key from messages
        messages_str = json.dumps(messages, sort_keys=True)
        cache_key = hashlib.sha256(
            f"{self.backend}:{self.model}:{messages_str}:{max_tokens}:{temperature}".encode()
        ).hexdigest()

        # Check cache
        if use_cache and self.enable_cache:
            cached = self._load_from_cache(cache_key)
            if cached:
                cached["cached"] = True
                return cached

        # Apply rate limiting
        self._apply_rate_limit()

        try:
            if self.backend == "openai":
                result = self._generate_openai_messages(messages, max_tokens, temperature)
            elif self.backend == "anthropic":
                result = self._generate_anthropic_messages(messages, max_tokens, temperature)
            elif self.backend == "ollama":
                result = self._generate_ollama_messages(messages, max_tokens, temperature)

            result["cached"] = False

            # Save to cache
            if use_cache:
                self._save_to_cache(cache_key, result)

            return result

        except Exception as e:
            logger.error(f"Generation with messages failed: {str(e)}")
            raise RuntimeError(f"LLM generation failed: {str(e)}")

    def _generate_openai(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str]
    ) -> Dict:
        """Generate using OpenAI"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

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

    def _generate_ollama(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        system_prompt: Optional[str]
    ) -> Dict:
        """Generate using Ollama"""
        url = f"{self.ollama_url}/api/generate"

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()

        return {
            "text": data["response"],
            "tokens": {
                "prompt": data.get("prompt_eval_count", 0),
                "completion": data.get("eval_count", 0),
                "total": data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
            }
        }

    def _generate_ollama_messages(
        self,
        messages: List[Dict],
        max_tokens: int,
        temperature: float
    ) -> Dict:
        """Generate using Ollama with message list"""
        url = f"{self.ollama_url}/api/chat"

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens
            }
        }

        response = requests.post(url, json=payload, timeout=300)
        response.raise_for_status()
        data = response.json()

        return {
            "text": data["message"]["content"],
            "tokens": {
                "prompt": data.get("prompt_eval_count", 0),
                "completion": data.get("eval_count", 0),
                "total": data.get("prompt_eval_count", 0) + data.get("eval_count", 0)
            }
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
        model_pricing = None
        if backend in pricing:
            for model_name, prices in pricing[backend].items():
                if model_name in self.model:
                    model_pricing = prices
                    break

        if not model_pricing:
            # Default to mid-range pricing
            model_pricing = {"input": 0.001, "output": 0.003}

        # Calculate cost
        input_cost = (tokens.get("prompt", 0) / 1000) * model_pricing["input"]
        output_cost = (tokens.get("completion", 0) / 1000) * model_pricing["output"]

        return input_cost + output_cost

    def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text

        Args:
            text: Input text

        Returns:
            Estimated token count
        """
        # Simple estimation: ~4 characters per token
        return len(text) // 4

    def clear_cache(self):
        """Clear response cache"""
        if not self.enable_cache:
            return

        import shutil
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Cache cleared")

    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        if not self.enable_cache:
            return {"enabled": False}

        cache_files = list(self.cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in cache_files)

        return {
            "enabled": True,
            "cache_dir": str(self.cache_dir),
            "num_entries": len(cache_files),
            "total_size_mb": total_size / (1024 * 1024),
        }

    def get_info(self) -> Dict:
        """Get client information"""
        info = {
            "backend": self.backend,
            "model": self.model,
            "rate_limit_rpm": self.rate_limit_rpm,
            "cache_enabled": self.enable_cache,
        }

        if self.backend == "ollama":
            info["ollama_url"] = self.ollama_url

        if self.enable_cache:
            info["cache_stats"] = self.get_cache_stats()

        return info
