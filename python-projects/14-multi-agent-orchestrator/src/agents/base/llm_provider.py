"""
LLM Provider Integration

Unified interface for multiple LLM providers (OpenAI, Anthropic, etc.)
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from enum import Enum
from pydantic import BaseModel, Field
import os

from src.core.config import settings
from src.core.logging import logger


class LLMRole(str, Enum):
    """Message role"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    FUNCTION = "function"


class LLMMessage(BaseModel):
    """LLM message"""
    role: LLMRole
    content: str
    name: Optional[str] = None
    function_call: Optional[Dict[str, Any]] = None

    class Config:
        use_enum_values = True


class LLMResponse(BaseModel):
    """LLM response"""
    content: str
    role: LLMRole = LLMRole.ASSISTANT
    finish_reason: Optional[str] = None
    function_call: Optional[Dict[str, Any]] = None
    tokens_used: Optional[int] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    cost: Optional[float] = None
    model: str
    provider: str

    class Config:
        use_enum_values = True


class LLMProvider(ABC):
    """
    Abstract LLM Provider

    Base class for all LLM provider implementations.
    """

    def __init__(
        self,
        model: str,
        api_key: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        **kwargs
    ):
        """
        Initialize LLM provider

        Args:
            model: Model identifier
            api_key: API key (optional, can use environment variable)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific arguments
        """
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.kwargs = kwargs

        logger.info(f"Initialized LLM provider: {self.__class__.__name__} with model {model}")

    @abstractmethod
    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """
        Generate completion from messages

        Args:
            messages: Conversation messages
            temperature: Override temperature
            max_tokens: Override max tokens
            **kwargs: Additional generation parameters

        Returns:
            LLMResponse: Generated response
        """
        pass

    @abstractmethod
    async def generate_streaming(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """
        Generate completion with streaming

        Args:
            messages: Conversation messages
            temperature: Override temperature
            max_tokens: Override max tokens
            **kwargs: Additional generation parameters

        Yields:
            str: Generated tokens
        """
        pass

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """
        Calculate API cost

        Args:
            prompt_tokens: Number of prompt tokens
            completion_tokens: Number of completion tokens

        Returns:
            float: Cost in USD
        """
        # Override in subclasses with provider-specific pricing
        return 0.0

    def get_model_info(self) -> Dict[str, Any]:
        """Get model information"""
        return {
            "provider": self.__class__.__name__,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }


class OpenAIProvider(LLMProvider):
    """OpenAI LLM Provider"""

    # Pricing per 1K tokens (as of 2024)
    PRICING = {
        "gpt-4": {"prompt": 0.03, "completion": 0.06},
        "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
        "gpt-3.5-turbo": {"prompt": 0.001, "completion": 0.002},
    }

    def __init__(self, model: str = "gpt-4", api_key: Optional[str] = None, **kwargs):
        super().__init__(model, api_key or os.getenv("OPENAI_API_KEY"), **kwargs)

        try:
            import openai
            self.client = openai.AsyncOpenAI(api_key=self.api_key)
        except ImportError:
            raise ImportError("OpenAI package not installed. Install with: pip install openai")

    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate completion using OpenAI API"""
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": msg.role, "content": msg.content} for msg in messages],
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                **kwargs
            )

            choice = response.choices[0]
            usage = response.usage

            cost = self.calculate_cost(usage.prompt_tokens, usage.completion_tokens)

            return LLMResponse(
                content=choice.message.content,
                finish_reason=choice.finish_reason,
                tokens_used=usage.total_tokens,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                cost=cost,
                model=self.model,
                provider="OpenAI"
            )

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    async def generate_streaming(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """Generate completion with streaming"""
        try:
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": msg.role, "content": msg.content} for msg in messages],
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                stream=True,
                **kwargs
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
            raise

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate OpenAI API cost"""
        # Use base model name for pricing lookup
        base_model = self.model.split("-")[0] + "-" + self.model.split("-")[1]
        if base_model not in self.PRICING:
            base_model = "gpt-4"

        pricing = self.PRICING.get(base_model, self.PRICING["gpt-4"])

        prompt_cost = (prompt_tokens / 1000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1000) * pricing["completion"]

        return round(prompt_cost + completion_cost, 6)


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM Provider"""

    # Pricing per 1K tokens
    PRICING = {
        "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
        "claude-3-sonnet": {"prompt": 0.003, "completion": 0.015},
        "claude-3-haiku": {"prompt": 0.00025, "completion": 0.00125},
    }

    def __init__(self, model: str = "claude-3-sonnet-20240229", api_key: Optional[str] = None, **kwargs):
        super().__init__(model, api_key or os.getenv("ANTHROPIC_API_KEY"), **kwargs)

        try:
            import anthropic
            self.client = anthropic.AsyncAnthropic(api_key=self.api_key)
        except ImportError:
            raise ImportError("Anthropic package not installed. Install with: pip install anthropic")

    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate completion using Anthropic API"""
        try:
            # Extract system message
            system_message = None
            chat_messages = []

            for msg in messages:
                if msg.role == LLMRole.SYSTEM:
                    system_message = msg.content
                else:
                    chat_messages.append({"role": msg.role, "content": msg.content})

            response = await self.client.messages.create(
                model=self.model,
                messages=chat_messages,
                system=system_message,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                **kwargs
            )

            cost = self.calculate_cost(response.usage.input_tokens, response.usage.output_tokens)

            return LLMResponse(
                content=response.content[0].text,
                finish_reason=response.stop_reason,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                cost=cost,
                model=self.model,
                provider="Anthropic"
            )

        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise

    async def generate_streaming(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """Generate completion with streaming"""
        try:
            # Extract system message
            system_message = None
            chat_messages = []

            for msg in messages:
                if msg.role == LLMRole.SYSTEM:
                    system_message = msg.content
                else:
                    chat_messages.append({"role": msg.role, "content": msg.content})

            async with self.client.messages.stream(
                model=self.model,
                messages=chat_messages,
                system=system_message,
                temperature=temperature or self.temperature,
                max_tokens=max_tokens or self.max_tokens,
                **kwargs
            ) as stream:
                async for text in stream.text_stream:
                    yield text

        except Exception as e:
            logger.error(f"Anthropic streaming error: {e}")
            raise

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate Anthropic API cost"""
        # Extract base model name
        base_model = "-".join(self.model.split("-")[:3])
        if base_model not in self.PRICING:
            base_model = "claude-3-sonnet"

        pricing = self.PRICING.get(base_model, self.PRICING["claude-3-sonnet"])

        prompt_cost = (prompt_tokens / 1000) * pricing["prompt"]
        completion_cost = (completion_tokens / 1000) * pricing["completion"]

        return round(prompt_cost + completion_cost, 6)


class OllamaProvider(LLMProvider):
    """
    Local Ollama LLM Provider

    Talks to a local Ollama server (default http://localhost:11434) - no
    API key, no cost, no external network call. This is the default
    provider for this project; OpenAI/Anthropic remain available as an
    opt-in for users who'd rather use their own cloud API key.
    """

    def __init__(
        self,
        model: str = "llama3.2",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        **kwargs
    ):
        super().__init__(model, api_key, **kwargs)

        self.base_url = (
            base_url
            or os.getenv("OLLAMA_BASE_URL")
            or getattr(settings, "OLLAMA_BASE_URL", None)
            or "http://localhost:11434"
        ).rstrip("/")

        try:
            import httpx
        except ImportError:
            raise ImportError("httpx package not installed. Install with: pip install httpx")

    async def generate(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> LLMResponse:
        """Generate completion using a local Ollama model"""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
                        "stream": False,
                        "options": {
                            "temperature": temperature if temperature is not None else self.temperature,
                            "num_predict": max_tokens or self.max_tokens,
                        },
                    },
                )
                response.raise_for_status()
                data = response.json()

            prompt_tokens = data.get("prompt_eval_count", 0)
            completion_tokens = data.get("eval_count", 0)

            return LLMResponse(
                content=data["message"]["content"],
                finish_reason="stop" if data.get("done") else None,
                tokens_used=prompt_tokens + completion_tokens,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost=0.0,
                model=self.model,
                provider="Ollama"
            )

        except httpx.ConnectError as e:
            logger.error(f"Could not reach Ollama at {self.base_url} - is `ollama serve` running? {e}")
            raise
        except Exception as e:
            logger.error(f"Ollama API error: {e}")
            raise

    async def generate_streaming(
        self,
        messages: List[LLMMessage],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        **kwargs
    ):
        """Generate completion with streaming from a local Ollama model"""
        import httpx
        import json as json_module

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [{"role": msg.role, "content": msg.content} for msg in messages],
                        "stream": True,
                        "options": {
                            "temperature": temperature if temperature is not None else self.temperature,
                            "num_predict": max_tokens or self.max_tokens,
                        },
                    },
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        chunk = json_module.loads(line)
                        content = chunk.get("message", {}).get("content", "")
                        if content:
                            yield content

        except Exception as e:
            logger.error(f"Ollama streaming error: {e}")
            raise

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Local inference - always free"""
        return 0.0


def create_llm_provider(
    provider: str = "ollama",
    model: Optional[str] = None,
    **kwargs
) -> LLMProvider:
    """
    Factory function to create LLM provider

    Args:
        provider: Provider name ("ollama", "openai", or "anthropic") - defaults
            to "ollama" (local, no API key needed). OpenAI/Anthropic are
            available for users who want to use their own cloud API key.
        model: Model identifier (optional)
        **kwargs: Additional provider arguments

    Returns:
        LLMProvider: Provider instance
    """
    providers = {
        "ollama": OllamaProvider,
        "openai": OpenAIProvider,
        "anthropic": AnthropicProvider,
    }

    if provider.lower() not in providers:
        raise ValueError(f"Unknown provider: {provider}. Available: {list(providers.keys())}")

    provider_class = providers[provider.lower()]

    if model:
        return provider_class(model=model, **kwargs)
    else:
        return provider_class(**kwargs)
