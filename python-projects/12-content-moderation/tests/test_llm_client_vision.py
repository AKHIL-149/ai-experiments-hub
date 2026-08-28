"""
Tests for LLMClient's image classification paths.

classify_image() previously had no real Ollama implementation - it fell
back to text-only classification on the NSFW detector's description (no
actual image understanding), or a hardcoded "not supported" result, even
though Ollama's /api/chat endpoint supports vision via an `images` field
and llava is commonly pulled locally. These tests lock in the fix and
the accompanying provider/model fields that were missing from all three
vision paths (openai/anthropic/ollama), which would otherwise crash
image_worker.py's Classification(provider=result['provider'], ...) with
a KeyError - never triggered before now since neither placeholder API
key ever got far enough to return a result.
"""

import base64
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.core.llm_client import LLMClient


@pytest.fixture
def tmp_image_path():
    fd, path = tempfile.mkstemp(suffix='.jpg')
    with open(fd, 'wb') as f:
        f.write(b'\xff\xd8\xff\xe0fake-jpeg-bytes')
    yield path


def _mock_ollama_client():
    """LLMClient(provider='ollama') pings Ollama at init - mock that so
    tests don't need a real Ollama server running."""
    return patch('requests.get', return_value=MagicMock(raise_for_status=lambda: None))


def test_classify_image_ollama_includes_images_field(tmp_image_path):
    with _mock_ollama_client():
        client = LLMClient(provider='ollama', model='llama3.2:3b')

    chat_response = MagicMock()
    chat_response.raise_for_status = lambda: None
    chat_response.json.return_value = {
        'message': {'content': '{"category": "clean", "confidence": 0.8, "is_violation": false, "reasoning": "looks fine"}'}
    }

    with patch('requests.post', return_value=chat_response) as mock_post:
        result = client.classify_image(tmp_image_path)

        assert mock_post.called
        sent_payload = mock_post.call_args.kwargs['json']
        assert 'images' in sent_payload['messages'][0]
        # The image field should be the base64-encoded file content
        assert sent_payload['messages'][0]['images'][0] == base64.b64encode(
            open(tmp_image_path, 'rb').read()
        ).decode('utf-8')

    assert result['provider'] == 'ollama'
    assert result['model'] == 'llava'  # default OLLAMA_VISION_MODEL
    assert result['category'] == 'clean'
    assert result['confidence'] == 0.8
    assert result['cost'] == 0.0


def test_classify_image_ollama_uses_configured_vision_model(tmp_image_path, monkeypatch):
    monkeypatch.setenv('OLLAMA_VISION_MODEL', 'custom-vision-model')

    with _mock_ollama_client():
        client = LLMClient(provider='ollama', model='llama3.2:3b')

    chat_response = MagicMock()
    chat_response.raise_for_status = lambda: None
    chat_response.json.return_value = {
        'message': {'content': '{"category": "clean", "confidence": 0.5, "is_violation": false, "reasoning": ""}'}
    }

    with patch('requests.post', return_value=chat_response) as mock_post:
        result = client.classify_image(tmp_image_path)
        assert mock_post.call_args.kwargs['json']['model'] == 'custom-vision-model'

    assert result['model'] == 'custom-vision-model'

    # Original text model must be restored after the vision call, so
    # later classify_text() calls still use the configured text model.
    assert client.model == 'llama3.2:3b'


def test_classify_image_ollama_fails_gracefully(tmp_image_path):
    with _mock_ollama_client():
        client = LLMClient(provider='ollama', model='llama3.2:3b')

    with patch('requests.post', side_effect=Exception('ollama unreachable')):
        result = client.classify_image(tmp_image_path)

    assert result['provider'] == 'ollama'
    assert result['category'] == 'clean'
    assert result['confidence'] == 0.0
    assert 'error' in result['reasoning'].lower() or 'ollama unreachable' in result['reasoning']


def test_classify_image_openai_result_includes_provider_and_model(tmp_image_path):
    client = LLMClient(provider='openai', model='gpt-4o-mini', api_key='fake-key')

    fake_message = MagicMock()
    fake_message.content = '{"category": "clean", "confidence": 0.9, "is_violation": false, "reasoning": "fine"}'
    fake_choice = MagicMock()
    fake_choice.message = fake_message
    fake_response = MagicMock()
    fake_response.choices = [fake_choice]
    fake_response.usage.prompt_tokens = 10
    fake_response.usage.completion_tokens = 5

    with patch.object(client.client.chat.completions, 'create', return_value=fake_response):
        result = client.classify_image(tmp_image_path)

    assert result['provider'] == 'openai'
    assert result['model'] == 'gpt-4o'  # VISION_MODEL default
    assert result['category'] == 'clean'


def test_classify_image_anthropic_result_includes_provider_and_model(tmp_image_path):
    client = LLMClient(provider='anthropic', model='claude-3-5-sonnet-20241022', api_key='fake-key')

    fake_content_block = MagicMock()
    fake_content_block.text = '{"category": "clean", "confidence": 0.9, "is_violation": false, "reasoning": "fine"}'
    fake_response = MagicMock()
    fake_response.content = [fake_content_block]
    fake_response.usage.input_tokens = 10
    fake_response.usage.output_tokens = 5

    with patch.object(client.client.messages, 'create', return_value=fake_response):
        result = client.classify_image(tmp_image_path)

    assert result['provider'] == 'anthropic'
    assert result['model'] == 'claude-3-5-sonnet-20241022'
    assert result['category'] == 'clean'
