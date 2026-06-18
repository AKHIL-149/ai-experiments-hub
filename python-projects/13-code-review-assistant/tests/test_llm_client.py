"""Tests for LLM client"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from src.core.llm_client import LLMClient


def test_llm_client_initialization_ollama():
    """Test LLM client initialization with Ollama backend"""
    with patch('requests.get') as mock_get:
        mock_get.return_value.raise_for_status = Mock()

        client = LLMClient(backend="ollama")

        assert client.backend == "ollama"
        assert client.model == "llama3.2"  # Default model
        assert client.max_retries == 3


def test_llm_client_initialization_with_custom_model():
    """Test initialization with custom model"""
    with patch('requests.get'):
        client = LLMClient(backend="ollama", model="custom-model")

        assert client.model == "custom-model"


def test_llm_client_initialization_invalid_backend():
    """Test initialization with invalid backend"""
    with pytest.raises(ValueError, match="Unsupported backend"):
        LLMClient(backend="invalid")


def test_llm_client_anthropic_missing_key(monkeypatch):
    """Test Anthropic initialization without API key"""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not found"):
        LLMClient(backend="anthropic")


def test_llm_client_openai_missing_key(monkeypatch):
    """Test OpenAI initialization without API key"""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENAI_API_KEY not found"):
        LLMClient(backend="openai")


def test_generate_ollama_success():
    """Test successful generation with Ollama"""
    with patch('requests.get'):  # For initialization
        with patch('requests.post') as mock_post:
            # Mock successful response
            mock_response = Mock()
            mock_response.json.return_value = {"response": "Generated text"}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            client = LLMClient(backend="ollama")
            result = client.generate("Test prompt")

            assert result == "Generated text"
            assert mock_post.called


def test_generate_with_system_message():
    """Test generation with system message"""
    with patch('requests.get'):
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"response": "Response"}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            client = LLMClient(backend="ollama")
            result = client.generate(
                "User prompt",
                system="You are a helpful assistant"
            )

            # Check that system message was included in the call
            call_args = mock_post.call_args
            payload = call_args[1]['json']
            assert "You are a helpful assistant" in payload['prompt']


def test_generate_with_retry_on_failure():
    """Test retry logic on generation failure"""
    with patch('requests.get'):
        with patch('requests.post') as mock_post:
            # First two attempts fail, third succeeds
            mock_post.side_effect = [
                Exception("Network error"),
                Exception("Network error"),
                Mock(json=lambda: {"response": "Success"}, raise_for_status=Mock())
            ]

            with patch('time.sleep'):  # Skip actual sleep
                client = LLMClient(backend="ollama", max_retries=3)
                result = client.generate("Test")

                assert result == "Success"
                assert mock_post.call_count == 3


def test_generate_fails_after_max_retries():
    """Test that generation fails after max retries"""
    with patch('requests.get'):
        with patch('requests.post') as mock_post:
            mock_post.side_effect = Exception("Network error")

            with patch('time.sleep'):
                client = LLMClient(backend="ollama", max_retries=2)

                with pytest.raises(Exception, match="failed after 2 attempts"):
                    client.generate("Test")


def test_load_prompt_template(tmp_path):
    """Test loading prompt template"""
    # Create a temporary prompts directory
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir(parents=True)

    # Create a template file
    template_file = prompts_dir / "test_template.txt"
    template_file.write_text("Hello {name}, you are {age} years old.")

    with patch('requests.get'):
        client = LLMClient(backend="ollama")
        result = client.load_prompt_template(
            "test_template",
            prompts_dir=prompts_dir,
            name="Alice",
            age=30
        )

        assert result == "Hello Alice, you are 30 years old."


def test_load_prompt_template_not_found():
    """Test loading non-existent template"""
    with patch('requests.get'):
        client = LLMClient(backend="ollama")

        with pytest.raises(FileNotFoundError):
            client.load_prompt_template("nonexistent")


def test_test_connection_success():
    """Test connection test success"""
    with patch('requests.get'):
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"response": "OK"}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            client = LLMClient(backend="ollama")
            result = client.test_connection()

            assert result is True


def test_test_connection_failure():
    """Test connection test failure"""
    with patch('requests.get'):
        with patch('requests.post') as mock_post:
            mock_post.side_effect = Exception("Connection failed")

            with patch('time.sleep'):
                client = LLMClient(backend="ollama")
                result = client.test_connection()

                assert result is False


def test_get_info():
    """Test get_info returns correct information"""
    with patch('requests.get'):
        client = LLMClient(
            backend="ollama",
            model="custom-model",
            max_retries=5,
            retry_delay=2.0
        )

        info = client.get_info()

        assert info["backend"] == "ollama"
        assert info["model"] == "custom-model"
        assert info["max_retries"] == 5
        assert info["retry_delay"] == 2.0


def test_generate_from_template(tmp_path):
    """Test generating from template"""
    # Create template
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir(parents=True)

    template_file = prompts_dir / "test.txt"
    template_file.write_text("Explain {topic}")

    with patch('requests.get'):
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"response": "Explanation"}
            mock_response.raise_for_status = Mock()
            mock_post.return_value = mock_response

            client = LLMClient(backend="ollama")
            result = client.generate_from_template(
                "test",
                {"topic": "Python"},
                prompts_dir=prompts_dir
            )

            assert result == "Explanation"
