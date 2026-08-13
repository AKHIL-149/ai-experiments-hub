"""
Unit tests for LLM providers - primarily the local Ollama provider, since
it's the default provider for this project (no API key required) and had
no coverage at all.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.agents.base.llm_provider import (
    OllamaProvider,
    LLMMessage,
    LLMRole,
    create_llm_provider,
)


class TestCreateLLMProvider:
    """Tests for the create_llm_provider factory"""

    def test_defaults_to_ollama(self):
        """This project is local-first: the factory's own default should
        be ollama, not a cloud provider that needs an API key."""
        provider = create_llm_provider()
        assert isinstance(provider, OllamaProvider)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            create_llm_provider(provider="not-a-real-provider")


class TestOllamaProvider:
    """Tests for OllamaProvider - real local HTTP calls to Ollama, mocked here"""

    def test_defaults_base_url_to_localhost(self):
        provider = OllamaProvider()
        assert provider.base_url == "http://localhost:11434"
        assert provider.model == "llama3.2"

    def test_explicit_base_url_is_respected_and_trailing_slash_stripped(self):
        provider = OllamaProvider(base_url="http://ollama-host:11434/")
        assert provider.base_url == "http://ollama-host:11434"

    def test_cost_is_always_zero(self):
        """Local inference - no per-token billing"""
        provider = OllamaProvider()
        assert provider.calculate_cost(prompt_tokens=100000, completion_tokens=100000) == 0.0

    @pytest.mark.asyncio
    async def test_generate_parses_real_ollama_response_shape(self):
        """Regression test against the actual /api/chat response shape
        confirmed live against a real running Ollama server."""
        provider = OllamaProvider(model="llama3.2")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "message": {"role": "assistant", "content": "REST is an architectural style for APIs."},
            "done": True,
            "prompt_eval_count": 42,
            "eval_count": 13,
        }

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await provider.generate([LLMMessage(role=LLMRole.USER, content="What is REST?")])

        assert result.content == "REST is an architectural style for APIs."
        assert result.provider == "Ollama"
        assert result.model == "llama3.2"
        assert result.prompt_tokens == 42
        assert result.completion_tokens == 13
        assert result.tokens_used == 55
        assert result.cost == 0.0

        # Confirm the actual Ollama chat API contract was used, not some
        # other shape (stream=False for the non-streaming path, correct URL)
        call_args = mock_client.post.call_args
        assert call_args.args[0] == "http://localhost:11434/api/chat"
        assert call_args.kwargs["json"]["stream"] is False
        assert call_args.kwargs["json"]["model"] == "llama3.2"

    @pytest.mark.asyncio
    async def test_generate_streaming_yields_content_chunks(self):
        provider = OllamaProvider(model="llama3.2")

        lines = [
            '{"message": {"content": "Hello"}, "done": false}',
            '{"message": {"content": " world"}, "done": false}',
            '{"message": {"content": ""}, "done": true}',
        ]

        async def fake_aiter_lines():
            for line in lines:
                yield line

        mock_stream_response = MagicMock()
        mock_stream_response.raise_for_status = MagicMock()
        mock_stream_response.aiter_lines = fake_aiter_lines

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__.return_value = mock_stream_response
        mock_stream_ctx.__aexit__.return_value = False

        mock_client = AsyncMock()
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = False

        with patch("httpx.AsyncClient", return_value=mock_client):
            chunks = [
                chunk async for chunk in
                provider.generate_streaming([LLMMessage(role=LLMRole.USER, content="Hi")])
            ]

        assert chunks == ["Hello", " world"]
