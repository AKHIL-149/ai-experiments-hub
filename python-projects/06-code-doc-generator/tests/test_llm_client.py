"""LLM client: request shape, error classification and truncation, without any real model."""
import pytest
import requests

from src.core import llm_client
from src.core.llm_client import LLMClient, LLMError, context_window_for


class FakeResponse:
    def __init__(self, body=None, status=200):
        self.body, self.status_code = body if body is not None else {}, status

    def json(self):
        if isinstance(self.body, Exception):
            raise self.body
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code}')


@pytest.fixture
def client(monkeypatch):
    c = LLMClient('ollama', 'test-model')
    c.sent = []
    c.queue = []

    def fake_post(url, json=None, timeout=None):
        c.sent.append({'url': url, 'payload': json, 'timeout': timeout})
        item = c.queue.pop(0) if c.queue else FakeResponse({'response': 'text', 'done_reason': 'stop'})
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(llm_client.requests, 'post', fake_post)
    monkeypatch.setattr(llm_client.time, 'sleep', lambda s: None)
    return c


def test_request_carries_system_text_in_its_own_field_not_glued_to_the_prompt(client):
    client.generate('PROMPT', system='RULES', max_tokens=50, temperature=0.1)
    payload = client.sent[0]['payload']
    assert payload['prompt'] == 'PROMPT' and payload['system'] == 'RULES'
    assert payload['stream'] is False and payload['model'] == 'test-model'
    assert payload['options']['temperature'] == 0.1 and payload['options']['num_predict'] == 50


def test_no_system_field_when_none_is_given(client):
    client.generate('PROMPT')
    assert 'system' not in client.sent[0]['payload']


def test_thinking_is_off_unless_asked_for(client, monkeypatch):
    client.generate('p')
    assert client.sent[0]['payload']['think'] is False
    monkeypatch.setenv('OLLAMA_THINK', 'true')
    client.generate('p')
    assert client.sent[1]['payload']['think'] is True


def test_context_window_fits_prompt_system_and_reply():
    assert context_window_for('x' * 100, 'y' * 100, 200) == 4096
    needed = context_window_for('x' * 30000, 'y' * 1000, 500)
    assert needed % 1024 == 0 and needed >= (31000 // 3) + 500
    assert context_window_for('x' * 10_000_000, '', 500) == llm_client.MAX_CONTEXT


def test_request_asks_for_a_context_that_fits(client):
    client.generate('x' * 12000, system='s' * 600, max_tokens=300)
    assert client.sent[0]['payload']['options']['num_ctx'] >= 12600 // 3 + 300


def test_timeouts_are_configurable_with_a_short_connect_timeout(client, monkeypatch):
    monkeypatch.setenv('LLM_TIMEOUT', '17')
    client.generate('p')
    assert client.sent[0]['timeout'] == (5, 17)


def test_truncation_is_reported_and_resets(client):
    client.queue = [FakeResponse({'response': 'cut off mid sen', 'done_reason': 'length'})]
    assert client.generate('p') == 'cut off mid sen' and client.truncated is True
    client.generate('p')
    assert client.truncated is False


# ------------------------------------------------------------------ errors, each with a clear one-line message

def raises(client, kind, text_part):
    with pytest.raises(LLMError) as info:
        client.generate('p')
    assert info.value.kind == kind, (info.value.kind, str(info.value))
    assert text_part.lower() in str(info.value).lower(), str(info.value)
    assert '\n' not in str(info.value) and 'HTTPConnectionPool' not in str(info.value) and 'Traceback' not in str(info.value)
    return info.value


def test_ollama_not_running(client):
    client.queue = [requests.ConnectionError("HTTPConnectionPool(host='x', port=1): Max retries exceeded")]
    error = raises(client, 'unavailable', 'ollama serve')
    assert error.permanent


def test_timeout(client):
    client.queue = [requests.ReadTimeout('slow')]
    error = raises(client, 'timeout', 'did not answer within')
    assert not error.permanent


def test_model_not_installed_gets_a_pull_hint(client):
    client.queue = [FakeResponse({'error': "model 'nope:1b' not found"}, 404)]
    error = raises(client, 'model', 'ollama pull test-model')
    assert error.permanent


def test_other_client_errors_show_ollamas_message(client):
    client.queue = [FakeResponse({'error': 'invalid options: num_ctx too large'}, 400)]
    raises(client, 'other', 'invalid options: num_ctx too large')


def test_a_server_error_is_retried_once(client):
    client.queue = [FakeResponse({'error': 'busy'}, 503), FakeResponse({'response': 'ok', 'done_reason': 'stop'})]
    assert client.generate('p') == 'ok' and len(client.sent) == 2


def test_a_persistent_server_error_is_reported_after_one_retry(client):
    client.queue = [FakeResponse({'error': 'busy'}, 503), FakeResponse({'error': 'busy'}, 503)]
    raises(client, 'other', 'busy')
    assert len(client.sent) == 2


def test_an_empty_reply_is_an_error(client):
    client.queue = [FakeResponse({'response': '  ', 'done_reason': 'stop'})]
    raises(client, 'empty', 'empty reply')
    client.queue = [FakeResponse({'response': '', 'done_reason': 'length', 'thinking': 'hmm'})]
    raises(client, 'empty', 'token limit')


def test_a_non_json_reply_is_an_error_not_a_crash(client):
    client.queue = [FakeResponse(ValueError('not json'))]
    raises(client, 'other', 'invalid reply')


def test_connection_errors_are_never_retried(client):
    client.queue = [requests.ConnectionError('refused'), FakeResponse({'response': 'ok'})]
    raises(client, 'unavailable', 'ollama')
    assert len(client.sent) == 1


# ------------------------------------------------------------------ other providers (fake SDK clients)

class _Status(Exception):
    def __init__(self, status):
        super().__init__(f'status {status}')
        self.status_code = status


def _provider_client(backend, monkeypatch, create):
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'k')
    monkeypatch.setenv('OPENAI_API_KEY', 'k')
    c = LLMClient.__new__(LLMClient)
    c.backend, c.model, c.truncated = backend, 'm', False
    holder = type('H', (), {})()
    if backend == 'anthropic':
        holder.messages = type('M', (), {'create': staticmethod(create)})()
    else:
        holder.chat = type('C', (), {'completions': type('P', (), {'create': staticmethod(create)})()})()
    c.client = holder
    return c


@pytest.mark.parametrize('status, kind', [(401, 'auth'), (403, 'auth'), (404, 'model'), (429, 'rate_limit'), (500, 'other')])
@pytest.mark.parametrize('backend', ['anthropic', 'openai'])
def test_sdk_errors_are_classified_by_status(backend, status, kind, monkeypatch):
    def create(**kwargs):
        raise _Status(status)
    with pytest.raises(LLMError) as info:
        _provider_client(backend, monkeypatch, create).generate('p')
    assert info.value.kind == kind
    assert info.value.permanent == (kind in ('auth', 'model'))


def test_sdk_connection_and_timeout_errors(monkeypatch):
    class APIConnectionError(Exception):
        pass

    class APITimeoutError(Exception):
        pass

    def conn(**kwargs):
        raise APIConnectionError('x')

    def slow(**kwargs):
        raise APITimeoutError('x')
    with pytest.raises(LLMError) as a:
        _provider_client('anthropic', monkeypatch, conn).generate('p')
    with pytest.raises(LLMError) as b:
        _provider_client('openai', monkeypatch, slow).generate('p')
    assert (a.value.kind, b.value.kind) == ('unavailable', 'timeout')


def test_anthropic_truncation_and_empty(monkeypatch):
    block = type('B', (), {'text': 'cut off'})()
    message = type('R', (), {'content': [block], 'stop_reason': 'max_tokens'})()
    c = _provider_client('anthropic', monkeypatch, lambda **k: message)
    assert c.generate('p') == 'cut off' and c.truncated is True
    empty = type('R', (), {'content': [], 'stop_reason': 'end_turn'})()
    with pytest.raises(LLMError, match='empty reply'):
        _provider_client('anthropic', monkeypatch, lambda **k: empty).generate('p')


def test_openai_truncation_and_empty(monkeypatch):
    def reply(text, reason):
        choice = type('Ch', (), {'message': type('Mg', (), {'content': text})(), 'finish_reason': reason})()
        return type('R', (), {'choices': [choice]})()
    c = _provider_client('openai', monkeypatch, lambda **k: reply('cut', 'length'))
    assert c.generate('p') == 'cut' and c.truncated is True
    with pytest.raises(LLMError, match='empty reply'):
        _provider_client('openai', monkeypatch, lambda **k: reply(None, 'stop')).generate('p')


def test_system_text_reaches_each_sdk_in_its_own_place(monkeypatch):
    seen = {}

    def anthropic_create(**kwargs):
        seen['anthropic'] = kwargs
        return type('R', (), {'content': [type('B', (), {'text': 'a'})()], 'stop_reason': 'end_turn'})()

    def openai_create(**kwargs):
        seen['openai'] = kwargs
        choice = type('Ch', (), {'message': type('Mg', (), {'content': 'o'})(), 'finish_reason': 'stop'})()
        return type('R', (), {'choices': [choice]})()
    _provider_client('anthropic', monkeypatch, anthropic_create).generate('P', system='S')
    _provider_client('openai', monkeypatch, openai_create).generate('P', system='S')
    assert seen['anthropic']['system'] == 'S' and seen['anthropic']['messages'] == [{'role': 'user', 'content': 'P'}]
    assert seen['openai']['messages'] == [{'role': 'system', 'content': 'S'}, {'role': 'user', 'content': 'P'}]


# ------------------------------------------------------------------ construction

def test_unknown_backend_is_refused():
    with pytest.raises(ValueError, match='Unsupported backend'):
        LLMClient('bogus')


@pytest.mark.parametrize('backend, var', [('anthropic', 'ANTHROPIC_API_KEY'), ('openai', 'OPENAI_API_KEY')])
def test_a_missing_api_key_names_the_variable(backend, var, monkeypatch):
    monkeypatch.delenv(var, raising=False)
    import sys
    monkeypatch.setitem(sys.modules, backend, type(sys)(backend))   # the package is "installed"
    with pytest.raises(ValueError, match=var):
        LLMClient(backend)


def test_the_default_model_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv('OLLAMA_MODEL', 'qwen3:8b')
    assert LLMClient('ollama').model == 'qwen3:8b'
    assert LLMClient('ollama', 'other').model == 'other'


def test_a_long_system_text_alone_grows_the_context_window():
    assert context_window_for('short', 'rules ' * 5000, 200) >= 30000 // 3 + 200


def test_the_truncated_flag_does_not_survive_into_a_failed_call(client):
    client.queue = [FakeResponse({'response': 'cut', 'done_reason': 'length'}), requests.ConnectionError('refused')]
    client.generate('p')
    assert client.truncated is True
    with pytest.raises(LLMError):
        client.generate('p')
    assert client.truncated is False


def test_error_messages_from_the_backend_are_flattened_to_one_line(client):
    client.queue = [FakeResponse({'error': 'line one\n\n   line two\n\tline three'}, 400)]
    error = raises(client, 'other', 'line one line two line three')
