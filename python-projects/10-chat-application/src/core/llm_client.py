"""Multi-provider LLM client with streaming support"""

import os
import requests
from typing import AsyncIterator, Dict, List, Optional
from openai import AsyncOpenAI
from anthropic import AsyncAnthropic


class LLMClient:
    """Unified LLM client supporting Ollama, OpenAI, Anthropic"""

    def __init__(self):
        """Initialize LLM client with available providers"""
        self.ollama_url = os.getenv('OLLAMA_API_URL', 'http://localhost:11434')
        self.openai_client = None
        self.anthropic_client = None

        # Initialize clients if API keys present
        if os.getenv('OPENAI_API_KEY'):
            self.openai_client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))

        if os.getenv('ANTHROPIC_API_KEY'):
            self.anthropic_client = AsyncAnthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

    async def stream_completion(
        self,
        messages: List[Dict[str, str]],
        provider: str = 'ollama',
        model: Optional[str] = None,
        temperature: float = 0.7
    ) -> AsyncIterator[str]:
        """
        Stream completion tokens from LLM

        Args:
            messages: List of message dicts with 'role' and 'content'
            provider: 'ollama', 'openai', or 'anthropic'
            model: Model name (provider-specific)
            temperature: Generation temperature (0-1)

        Yields:
            Individual tokens as strings
        """
        if provider == 'ollama':
            async for token in self._stream_ollama(messages, model or 'llama3.2:3b', temperature):
                yield token

        elif provider == 'openai':
            if not self.openai_client:
                raise ValueError("OpenAI API key not configured")
            async for token in self._stream_openai(messages, model or 'gpt-4o-mini', temperature):
                yield token

        elif provider == 'anthropic':
            if not self.anthropic_client:
                raise ValueError("Anthropic API key not configured")
            async for token in self._stream_anthropic(messages, model or 'claude-3-5-sonnet-20241022', temperature):
                yield token

        else:
            raise ValueError(f"Unsupported provider: {provider}")

    async def _stream_ollama(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float
    ) -> AsyncIterator[str]:
        """Stream from Ollama API"""
        import aiohttp

        url = f"{self.ollama_url}/api/chat"
        payload = {
            'model': model,
            'messages': messages,
            'stream': True,
            'options': {
                'temperature': temperature
            }
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as response:
                async for line in response.content:
                    if line:
                        import json
                        data = json.loads(line)
                        if 'message' in data:
                            token = data['message'].get('content', '')
                            if token:
                                yield token

    async def _stream_openai(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float
    ) -> AsyncIterator[str]:
        """Stream from OpenAI API"""
        stream = await self.openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            stream=True
        )

        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def _stream_anthropic(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float
    ) -> AsyncIterator[str]:
        """Stream from Anthropic API"""
        # Extract system message if present
        system = None
        chat_messages = []

        for msg in messages:
            if msg['role'] == 'system':
                system = msg['content']
            else:
                chat_messages.append(msg)

        async with self.anthropic_client.messages.stream(
            model=model,
            messages=chat_messages,
            system=system,
            temperature=temperature,
            max_tokens=4096
        ) as stream:
            async for text in stream.text_stream:
                yield text

    def get_available_providers(self) -> Dict[str, bool]:
        """
        Check which providers are available

        Returns:
            Dictionary mapping provider name to availability
        """
        providers = {
            'ollama': self._check_ollama(),
            'openai': self.openai_client is not None,
            'anthropic': self.anthropic_client is not None
        }
        return providers

    def _check_ollama(self) -> bool:
        """Check if Ollama is running"""
        try:
            response = requests.get(f"{self.ollama_url}/api/tags", timeout=2)
            return response.status_code == 200
        except:
            return False
