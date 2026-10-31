"""VisionClient against fake HTTP and fake provider SDKs: payloads, errors, retries, caching."""
import base64
import sys
import types

import pytest
import requests

from src.core import vision_client as vc
from src.core.cache_manager import CacheManager
from src.core.rate_limiter import RateLimiter
from src.core.retry_handler import RetryHandler
from src.core.vision_client import VisionClient, VisionError
from tests.conftest import png_bytes, text_image

NO_WAIT = RetryHandler(max_retries=2, base_delay=0, jitter=False)


class Resp:
    def __init__(self, status=200, body=None, text=''):
        self.status_code = status
        self._body = body
        self.text = text

    def json(self):
        if self._body is None:
            raise ValueError('not json')
        return self._body


def ollama_ok(text='A receipt.', reason='stop'):
    return Resp(200, {'message': {'content': text}, 'done_reason': reason})


@pytest.fixture
def post(monkeypatch):
    """Replace requests.post; `post.replies` is consumed in order, `post.calls` records the payloads."""
    class Poster:
        replies = []
        calls = []

        def __call__(self, url, json=None, timeout=None):
            self.calls.append({'url': url, 'json': json, 'timeout': timeout})
            reply = self.replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
    poster = Poster()
    poster.replies, poster.calls = [], []
    monkeypatch.setattr(requests, 'post', poster)
    return poster


def client(**kwargs):
    kwargs.setdefault('retry_handler', NO_WAIT)
    return VisionClient(backend='ollama', **kwargs)


IMG = text_image(size=(300, 100))


# ------------------------------------------------------------------ construction

def test_unknown_backend_is_rejected_up_front():
    with pytest.raises(ValueError, match='Unsupported backend'):
        VisionClient(backend='skynet')


def test_default_models(monkeypatch):
    monkeypatch.delenv('ANTHROPIC_MODEL', raising=False)
    monkeypatch.delenv('OPENAI_MODEL', raising=False)
    assert VisionClient('ollama').model == 'llava'
    assert VisionClient('anthropic').model == 'claude-sonnet-5-5'
    assert VisionClient('openai').model == 'gpt-4o'
    monkeypatch.setenv('OPENAI_MODEL', 'mine')
    assert VisionClient('openai').model == 'mine'


# ------------------------------------------------------------------ Ollama

def test_ollama_payload_has_the_image_options_and_timeout(post):
    post.replies = [ollama_ok()]
    out = client().analyze('What is this?', [IMG], max_tokens=77, temperature=0.2)
    call = post.calls[0]
    assert out == 'A receipt.'
    assert call['url'] == 'http://127.0.0.1:9/api/chat'
    body = call['json']
    assert body['model'] == 'llava' and body['stream'] is False
    assert body['options'] == {'temperature': 0.2, 'num_predict': 77}
    assert body['messages'][0]['content'] == 'What is this?'
    assert base64.b64decode(body['messages'][0]['images'][0])[:4] == b'\x89PNG'
    assert call['timeout'] == (5, 300)


def test_images_may_be_paths_bytes_or_pil(post, tmp_path):
    path = tmp_path / 'a.png'
    path.write_bytes(png_bytes(IMG))
    post.replies = [ollama_ok(), ollama_ok(), ollama_ok()]
    c = client()
    c.analyze('p', [str(path)])
    c.analyze('p', [png_bytes(IMG)])
    c.analyze('p', [IMG])
    assert len(post.calls) == 3
    with pytest.raises(TypeError):
        c.analyze('p', [12345])


def test_text_only_prompt_sends_no_images(post):
    post.replies = [ollama_ok('42')]
    client().analyze('2+2?', [])
    assert post.calls[0]['json']['messages'][0]['images'] == []


def test_ollama_not_running(post):
    post.replies = [requests.ConnectionError('refused')] * 3
    with pytest.raises(VisionError) as error:
        client().analyze('p', [IMG])
    assert error.value.kind == 'unavailable' and 'ollama serve' in str(error.value)
    assert len(post.calls) == 1                       # permanent: not retried


def test_missing_model_says_how_to_install_it(post):
    post.replies = [Resp(404, {'error': "model 'nosuch' not found"})]
    with pytest.raises(VisionError) as error:
        client(model='nosuch').analyze('p', [IMG])
    assert error.value.kind == 'model' and 'ollama pull nosuch' in str(error.value)


def test_text_model_cannot_read_images(post):
    post.replies = [Resp(400, {'error': 'this model does not support images'})]
    with pytest.raises(VisionError) as error:
        client(model='llama3').analyze('p', [IMG])
    assert error.value.kind == 'bad_request' and 'llava' in str(error.value)


def test_server_error_is_retried_then_succeeds(post):
    post.replies = [Resp(503, {'error': 'loading model'}), ollama_ok('second try')]
    assert client().analyze('p', [IMG]) == 'second try'
    assert len(post.calls) == 2


def test_timeout_is_retried_then_reported(post):
    post.replies = [requests.Timeout()] * 3
    with pytest.raises(VisionError) as error:
        client().analyze('p', [IMG])
    assert error.value.kind == 'timeout' and '300s' in str(error.value)
    assert len(post.calls) == 3                       # first try + 2 retries


def test_bad_request_is_not_retried(post):
    post.replies = [Resp(400, {'error': 'bad thing'})]
    with pytest.raises(VisionError):
        client().analyze('p', [IMG])
    assert len(post.calls) == 1


def test_empty_reply_is_an_error_not_an_empty_string(post):
    post.replies = [ollama_ok('   ')]
    with pytest.raises(VisionError) as error:
        client().analyze('p', [IMG])
    assert error.value.kind == 'empty'


def test_invalid_json_from_ollama(post):
    post.replies = [Resp(200, None)]
    with pytest.raises(VisionError, match='not JSON'):
        client().analyze('p', [IMG])


def test_truncation_is_reported(post):
    post.replies = [ollama_ok('cut off mid-sen', reason='length')]
    c = client()
    assert c.analyze('p', [IMG]) == 'cut off mid-sen' and c.truncated is True
    post.replies = [ollama_ok('whole answer')]
    c.analyze('p', [IMG])
    assert c.truncated is False


# ------------------------------------------------------------------ cache

@pytest.fixture
def cache(tmp_path):
    return CacheManager(str(tmp_path / 'cache'))


def test_second_identical_call_is_served_from_the_cache(post, cache):
    post.replies = [ollama_ok('first')]
    c = client(cache_manager=cache)
    assert c.analyze('p', [IMG]) == 'first' and c.last_cached is False
    assert c.analyze('p', [IMG]) == 'first' and c.last_cached is True
    assert len(post.calls) == 1


def test_a_bigger_token_limit_is_a_different_request(post, cache):
    post.replies = [ollama_ok('short'), ollama_ok('a much longer answer')]
    c = client(cache_manager=cache)
    c.analyze('p', [IMG], max_tokens=50)
    assert c.analyze('p', [IMG], max_tokens=500) == 'a much longer answer'
    assert len(post.calls) == 2


def test_temperature_is_part_of_the_key(post, cache):
    post.replies = [ollama_ok('cold'), ollama_ok('hot')]
    c = client(cache_manager=cache)
    c.analyze('p', [IMG], temperature=0.0)
    assert c.analyze('p', [IMG], temperature=1.0) == 'hot'


def test_a_cut_off_answer_is_not_cached(post, cache):
    post.replies = [ollama_ok('cut', reason='length'), ollama_ok('complete')]
    c = client(cache_manager=cache)
    c.analyze('p', [IMG], max_tokens=5)
    assert c.analyze('p', [IMG], max_tokens=5) == 'complete'


def test_different_images_and_models_do_not_share_cache_entries(post, cache):
    post.replies = [ollama_ok('a'), ollama_ok('b'), ollama_ok('c')]
    c = client(cache_manager=cache)
    c.analyze('p', [IMG])
    c.analyze('p', [text_image('OTHER', size=(300, 100))])
    client(cache_manager=cache, model='bakllava').analyze('p', [IMG])
    assert len(post.calls) == 3


def test_cache_can_be_switched_off(post, cache):
    post.replies = [ollama_ok('a'), ollama_ok('b')]
    c = client(cache_manager=cache, enable_cache=False)
    c.analyze('p', [IMG])
    c.analyze('p', [IMG])
    assert len(post.calls) == 2


# ------------------------------------------------------------------ hosted providers (fake SDKs)

class FakeAnthropic:
    last = None

    def __init__(self, api_key=None, max_retries=None):
        FakeAnthropic.last = self
        self.max_retries = max_retries
        self.messages = self
        self.kwargs = None
        self.outcome = types.SimpleNamespace(content=[types.SimpleNamespace(type='text', text='claude says')],
                                             stop_reason='end_turn')

    def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class FakeOpenAI:
    last = None

    def __init__(self, api_key=None, max_retries=None):
        FakeOpenAI.last = self
        self.max_retries = max_retries
        self.chat = types.SimpleNamespace(completions=self)
        self.kwargs = None
        self.outcome = types.SimpleNamespace(choices=[types.SimpleNamespace(
            message=types.SimpleNamespace(content='gpt says'), finish_reason='stop')])

    def create(self, **kwargs):
        self.kwargs = kwargs
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.fixture
def sdks(monkeypatch):
    monkeypatch.setitem(sys.modules, 'anthropic', types.SimpleNamespace(Anthropic=FakeAnthropic))
    monkeypatch.setitem(sys.modules, 'openai', types.SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'test-key')
    monkeypatch.setenv('OPENAI_API_KEY', 'test-key')
    monkeypatch.setattr(vc, 'get_rate_limiter', lambda provider: RateLimiter(10000))


def hosted(backend, **kwargs):
    kwargs.setdefault('retry_handler', NO_WAIT)
    return VisionClient(backend=backend, **kwargs)


def test_anthropic_media_type_matches_the_bytes_that_are_sent(sdks):
    # a small image is PNG, a big one JPEG; the declared type used to be "image/jpeg" for both
    c = hosted('anthropic')
    c.analyze('p', [IMG])
    block = FakeAnthropic.last.kwargs['messages'][0]['content'][0]
    assert block['source']['media_type'] == 'image/png'
    assert base64.b64decode(block['source']['data'])[:4] == b'\x89PNG'

    big = text_image(size=(1800, 1200))
    c.analyze('p', [big])
    block = FakeAnthropic.last.kwargs['messages'][0]['content'][0]
    assert block['source']['media_type'] == 'image/jpeg'
    assert base64.b64decode(block['source']['data'])[:2] == b'\xff\xd8'


def test_anthropic_request_shape(sdks):
    out = hosted('anthropic').analyze('describe', [IMG, IMG], max_tokens=50, temperature=1.7)
    kwargs = FakeAnthropic.last.kwargs
    assert out == 'claude says'
    assert kwargs['model'] == 'claude-sonnet-5-5' and kwargs['max_tokens'] == 50
    assert kwargs['temperature'] == 1.0                      # Anthropic accepts 0..1
    types_ = [b['type'] for b in kwargs['messages'][0]['content']]
    assert types_ == ['image', 'image', 'text']
    assert FakeAnthropic.last.max_retries == 0              # retrying is the client's job


def test_openai_data_uri_uses_the_real_media_type(sdks):
    out = hosted('openai').analyze('describe', [IMG])
    content = FakeOpenAI.last.kwargs['messages'][0]['content']
    assert out == 'gpt says'
    assert content[0] == {'type': 'text', 'text': 'describe'}
    assert content[1]['image_url']['url'].startswith('data:image/png;base64,')


def test_missing_api_key_is_a_clear_error(sdks, monkeypatch):
    monkeypatch.delenv('ANTHROPIC_API_KEY')
    with pytest.raises(ValueError, match='ANTHROPIC_API_KEY'):
        hosted('anthropic').analyze('p', [IMG])


def test_missing_sdk_is_a_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, 'openai', None)
    monkeypatch.setenv('OPENAI_API_KEY', 'k')
    with pytest.raises(ImportError, match='pip install openai'):
        hosted('openai', rate_limit=False).analyze('p', [IMG])


class StatusError(Exception):
    def __init__(self, status):
        super().__init__(f'http {status}')
        self.status_code = status


@pytest.mark.parametrize('status,kind,retried', [
    (401, 'auth', False), (403, 'auth', False), (404, 'model', False), (400, 'bad_request', False),
    (429, 'rate_limit', True), (500, 'server', True), (529, 'server', True),
])
def test_hosted_errors_are_classified_and_only_transient_ones_retried(sdks, status, kind, retried):
    c = hosted('anthropic')
    attempts = []
    original = FakeAnthropic.create

    def create(self, **kwargs):
        attempts.append(1)
        raise StatusError(status)
    FakeAnthropic.create = create
    try:
        with pytest.raises(VisionError) as error:
            c.analyze('p', [IMG])
    finally:
        FakeAnthropic.create = original
    assert error.value.kind == kind
    assert len(attempts) == (3 if retried else 1)


def test_hosted_timeout_and_connection_names_are_recognised():
    class APITimeoutError(Exception):
        pass

    class APIConnectionError(Exception):
        pass
    assert VisionClient._classify(APITimeoutError(), 'X').kind == 'timeout'
    assert VisionClient._classify(APIConnectionError(), 'X').kind == 'connection'
    assert VisionClient._classify(RuntimeError('boom'), 'X').kind == 'other'


def test_auth_message_never_contains_the_key(sdks):
    class E(Exception):
        status_code = 401
    err = VisionClient._classify(E('Invalid key sk-secret-123'), 'OpenAI')
    assert 'sk-secret-123' not in str(err)


def test_hosted_truncation_flag(sdks):
    c = hosted('anthropic')
    c.analyze('p', [IMG])
    assert c.truncated is False
    FakeAnthropic.create_original = FakeAnthropic.create
    FakeAnthropic.create = lambda self, **k: types.SimpleNamespace(
        content=[types.SimpleNamespace(type='text', text='cut')], stop_reason='max_tokens')
    try:
        c.analyze('p', [IMG])
    finally:
        FakeAnthropic.create = FakeAnthropic.create_original
    assert c.truncated is True


def test_rate_limiter_is_used_for_hosted_providers_only(sdks, monkeypatch, post):
    acquired = []

    class Limiter:
        def acquire(self, timeout=None):
            acquired.append(1)
    monkeypatch.setattr(vc, 'get_rate_limiter', lambda provider: Limiter())
    hosted('anthropic').analyze('p', [IMG])
    assert acquired == [1]
    post.replies = [ollama_ok()]
    client().analyze('p', [IMG])
    assert acquired == [1]


def test_rate_limit_wait_timeout_becomes_a_rate_limit_error(sdks, monkeypatch):
    class Limiter:
        def acquire(self, timeout=None):
            raise TimeoutError
    monkeypatch.setattr(vc, 'get_rate_limiter', lambda provider: Limiter())
    with pytest.raises(VisionError) as error:
        hosted('anthropic', retry_handler=RetryHandler(max_retries=0)).analyze('p', [IMG])
    assert error.value.kind == 'rate_limit'


def test_vision_error_transient_flags():
    assert VisionError('timeout', 'x').transient and VisionError('rate_limit', 'x').transient
    assert VisionError('server', 'x').transient and VisionError('connection', 'x').transient
    assert not VisionError('auth', 'x').transient and not VisionError('unavailable', 'x').transient
