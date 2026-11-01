import pytest
import requests

from core.llm_client import LLMClient


class FakeResponse:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} Server Error")


@pytest.fixture
def ollama(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_URL", "http://ollama.test:11434")
    monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
    calls = []

    class Setup:
        reply = {"response": "hi", "prompt_eval_count": 100, "eval_count": 5}
        chat_reply = {"message": {"content": "hi"}, "prompt_eval_count": 100, "eval_count": 5}
        status = 200
        error = None
    setup = Setup()

    def post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json, "timeout": timeout})
        if setup.error:
            raise setup.error
        return FakeResponse(setup.status, setup.chat_reply if url.endswith("/api/chat") else setup.reply)

    monkeypatch.setattr("core.llm_client.requests.post", post)
    monkeypatch.setattr("core.llm_client.time.sleep", lambda s: None)
    setup.calls = calls
    return setup


class TestOllama:
    def test_a_larger_context_window_is_requested(self, ollama):
        # Ollama's default is 4096 tokens and it silently drops the rest of the prompt
        LLMClient("ollama", "llama3.2").generate("hello")
        assert ollama.calls[0]["json"]["options"]["num_ctx"] == 8192

    def test_context_window_is_configurable(self, ollama, monkeypatch):
        monkeypatch.setenv("OLLAMA_NUM_CTX", "16384")
        LLMClient("ollama", "llama3.2").generate("hello")
        assert ollama.calls[0]["json"]["options"]["num_ctx"] == 16384
        LLMClient("ollama", "llama3.2", ollama_num_ctx=2048).generate("hello")
        assert ollama.calls[1]["json"]["options"]["num_ctx"] == 2048

    def test_request_shape(self, ollama):
        result = LLMClient("ollama", "llama3.2").generate("question", max_tokens=77, temperature=0.1, system_prompt="be brief")
        payload = ollama.calls[0]["json"]
        assert ollama.calls[0]["url"] == "http://ollama.test:11434/api/generate"
        assert payload["prompt"] == "be brief\n\nquestion" and payload["model"] == "llama3.2"
        assert payload["options"]["num_predict"] == 77 and payload["options"]["temperature"] == 0.1
        assert payload["stream"] is False and "format" not in payload
        assert result["text"] == "hi" and result["tokens"] == {"prompt": 100, "completion": 5, "total": 105}

    def test_json_mode(self, ollama):
        LLMClient("ollama", "llama3.2").generate("x", json_mode=True)
        assert ollama.calls[0]["json"]["format"] == "json"

    def test_truncation_is_detected_and_flagged(self, ollama):
        ollama.reply = {"response": "x", "prompt_eval_count": 8192, "eval_count": 1}
        client = LLMClient("ollama", "llama3.2")
        assert client.generate("x")["truncated"] is True
        ollama.reply = {"response": "x", "prompt_eval_count": 3000, "eval_count": 1}
        assert client.generate("x")["truncated"] is False

    def test_chat_endpoint_gets_the_same_treatment(self, ollama):
        ollama.chat_reply = {"message": {"content": "ok"}, "prompt_eval_count": 8190, "eval_count": 2}
        result = LLMClient("ollama", "llama3.2").generate_with_messages([{"role": "user", "content": "x"}])
        assert ollama.calls[0]["json"]["options"]["num_ctx"] == 8192
        assert result["truncated"] is True and result["text"] == "ok"

    def test_missing_model_says_how_to_install_it(self, ollama):
        ollama.status = 404
        with pytest.raises(RuntimeError, match="ollama pull llama3.2"):
            LLMClient("ollama", "llama3.2").generate("x")

    def test_ollama_not_running(self, ollama):
        ollama.error = requests.exceptions.ConnectionError("refused")
        with pytest.raises(RuntimeError, match="Is it running\\? Start it with: ollama serve"):
            LLMClient("ollama", "llama3.2").generate("x")
        assert len(ollama.calls) == 2            # one retry in case it was only loading a model

    def test_timeout_message(self, ollama):
        ollama.error = requests.exceptions.Timeout("slow")
        with pytest.raises(RuntimeError, match="did not answer within 5 minutes"):
            LLMClient("ollama", "llama3.2").generate("x")

    def test_server_errors_are_wrapped(self, ollama):
        ollama.status = 500
        with pytest.raises(RuntimeError, match="LLM generation failed"):
            LLMClient("ollama", "llama3.2").generate("x")

    def test_default_model_comes_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_MODEL", "qwen3:8b")
        assert LLMClient("ollama").model == "qwen3:8b"


class TestOpenAI:
    def make(self, monkeypatch):
        sent = []

        class Completions:
            def create(self, **kwargs):
                sent.append(kwargs)
                class Msg: content = '{"ok": true}'
                class Choice: message = Msg()
                class Usage: prompt_tokens, completion_tokens, total_tokens = 3, 2, 5
                class Resp: choices = [Choice()]; usage = Usage()
                return Resp()

        class Client:
            def __init__(self, api_key): self.chat = type("c", (), {"completions": Completions()})()

        import openai
        monkeypatch.setattr(openai, "OpenAI", Client)
        return LLMClient("openai", "gpt-4o-mini", api_key="sk-x"), sent

    def test_json_mode_asks_for_a_json_object(self, monkeypatch):
        client, sent = self.make(monkeypatch)
        client.generate("give json", json_mode=True)
        assert sent[0]["response_format"] == {"type": "json_object"}

    def test_normal_calls_do_not_ask_for_json(self, monkeypatch):
        client, sent = self.make(monkeypatch)
        client.generate("hi", system_prompt="sys")
        assert "response_format" not in sent[0]
        assert [m["role"] for m in sent[0]["messages"]] == ["system", "user"]

    def test_key_is_required(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            LLMClient("openai")

    def test_unsupported_backend(self):
        with pytest.raises(ValueError, match="Unsupported backend"):
            LLMClient("telepathy")


class TestCostEstimate:
    def client(self, backend, model):
        c = LLMClient.__new__(LLMClient)
        c.backend, c.model = backend, model
        return c

    TOKENS = {"prompt": 100_000, "completion": 10_000}

    def test_mini_is_not_priced_as_the_full_model(self):
        # "gpt-4o" is a substring of "gpt-4o-mini": the first match used to win, so the
        # mini model was billed at the full model's price (30x too much).
        full = self.client("openai", "gpt-4o").estimate_cost(self.TOKENS)
        mini = self.client("openai", "gpt-4o-mini").estimate_cost(self.TOKENS)
        assert full == pytest.approx(0.65)
        assert mini == pytest.approx(0.021)

    def test_dated_model_names_match_their_family(self):
        assert self.client("openai", "gpt-4o-mini-2024-07-18").estimate_cost(self.TOKENS) == pytest.approx(0.021)

    def test_anthropic(self):
        assert self.client("anthropic", "claude-3-haiku-20240307").estimate_cost(self.TOKENS) == pytest.approx(0.0375)

    def test_unknown_model_gets_a_default_price(self):
        assert self.client("openai", "mystery").estimate_cost(self.TOKENS) == pytest.approx(0.13)

    def test_local_models_are_free(self):
        assert self.client("ollama", "llama3.2").estimate_cost(self.TOKENS) == 0.0
