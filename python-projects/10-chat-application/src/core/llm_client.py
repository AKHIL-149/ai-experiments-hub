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
        # Ollama answers with a 4096-token window unless asked for more, and silently drops the
        # oldest text of a longer conversation (including its opening instructions)
        self.num_ctx = int(os.getenv('OLLAMA_NUM_CTX', 8192))
        self.openai_client = None
        self.anthropic_client = None

        # Initialize clients if API keys present. Reject the literal
        # placeholder values shipped in .env.example ("your_openai_key_here"
        # / "your_anthropic_key_here") - a user who follows the README's
        # own setup steps (`cp .env.example .env`) without editing those
        # two lines ends up with that exact string in the env var, which
        # is truthy/non-empty, so a plain "if os.getenv(...)" check
        # reports the provider as configured/available. Confirmed live:
        # /api/health returned {"openai": true, "anthropic": true} with
        # the untouched placeholder .env, and actually sending a message
        # on that provider failed with a raw 401 from the SDK.
        openai_key = os.getenv('OPENAI_API_KEY')
        if openai_key and not openai_key.startswith('your_'):
            self.openai_client = AsyncOpenAI(api_key=openai_key)

        anthropic_key = os.getenv('ANTHROPIC_API_KEY')
        if anthropic_key and not anthropic_key.startswith('your_'):
            self.anthropic_client = AsyncAnthropic(api_key=anthropic_key)

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
        """
        Stream from Ollama API.

        Ollama reports a missing model as HTTP 404 with {"error": "model 'x' not found"}, and
        errors that happen mid-stream as an {"error": ...} line. Both used to be ignored (only
        "message" lines were read), so the chat saw a successful reply with no text in it.
        """
        import aiohttp
        import json

        url = f"{self.ollama_url}/api/chat"
        payload = {
            'model': model,
            'messages': messages,
            'stream': True,
            'options': {
                'temperature': temperature,
                'num_ctx': self.num_ctx
            }
        }

        got_text = False
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        detail = ''
                        try:
                            detail = (await response.json()).get('error', '')
                        except Exception:
                            pass
                        raise RuntimeError(self._ollama_error_message(detail or f"HTTP {response.status}", model))

                    async for raw in response.content:
                        line = raw.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                        except ValueError:
                            continue
                        if 'error' in data:
                            raise RuntimeError(self._ollama_error_message(str(data['error']), model))
                        token = (data.get('message') or {}).get('content', '')
                        if token:
                            got_text = True
                            yield token
        except aiohttp.ClientConnectorError:
            raise RuntimeError(
                f"Could not reach Ollama at {self.ollama_url}. Is it running? Start it with: ollama serve"
            )

        if not got_text:
            raise RuntimeError(f"The model '{model}' returned an empty response. Try again, or pick another model.")

    @staticmethod
    def _ollama_error_message(detail: str, model: str) -> str:
        """Ollama's own wording, plus what to do about the common case"""
        if 'not found' in detail.lower():
            return f"Ollama does not have the model '{model}'. Install it with: ollama pull {model}"
        return f"Ollama error: {detail}"

    async def list_ollama_models(self) -> List[str]:
        """Names of the models Ollama has installed (empty if it cannot be reached)"""
        import aiohttp

        try:
            timeout = aiohttp.ClientTimeout(total=3)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.ollama_url}/api/tags") as response:
                    if response.status != 200:
                        return []
                    data = await response.json()
            # Embedding models (nomic-embed-text ...) are installed too but cannot chat
            return sorted(
                m['name'] for m in data.get('models', [])
                if m.get('name') and 'embed' not in m['name'].lower()
                and 'bert' not in (m.get('details') or {}).get('family', '').lower()
            )
        except Exception:
            return []

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
