"""The web API: statuses, validation, limits, batch bookkeeping and CORS (a fake model; no network)."""
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import server
from src.core.cache_manager import CacheManager
from src.core.vision_client import VisionError
from tests.conftest import png_bytes, text_image

client = TestClient(server.app, raise_server_exceptions=False)


class FakeVision:
    """Stands in for VisionClient. `behaviour` is a function(prompt, images) -> text, or raises."""
    behaviour = staticmethod(lambda prompt, images: 'A calm beach.')
    instances = []

    def __init__(self, backend='ollama', model=None, cache_manager=None, enable_cache=True, **kwargs):
        if backend == 'anthropic' and not server.os.getenv('ANTHROPIC_API_KEY'):
            raise ValueError('ANTHROPIC_API_KEY not found in environment')
        self.backend = backend
        self.model = model or 'llava'
        self.cache_manager = cache_manager
        self.truncated = False
        self.last_cached = False
        self.calls = []
        FakeVision.instances.append(self)

    def analyze(self, prompt, images, max_tokens=1000, temperature=0.7):
        self.calls.append({'prompt': prompt, 'max_tokens': max_tokens, 'temperature': temperature, 'n': len(images)})
        return FakeVision.behaviour(prompt, images)


@pytest.fixture(autouse=True)
def fake_model(monkeypatch, tmp_path):
    FakeVision.behaviour = staticmethod(lambda prompt, images: 'A calm beach.')
    FakeVision.instances = []
    monkeypatch.setattr(server, 'VisionClient', FakeVision)
    monkeypatch.setattr(server, 'cache_manager', CacheManager(str(tmp_path / 'cache')))
    server._ocr_status.clear()


def upload(image=None, fmt='PNG', name='a.png', **extra):
    image = image or text_image(size=(200, 80))
    return {'file': (name, png_bytes(image, fmt), 'image/png')}


def error_of(response):
    body = response.json()
    assert body['success'] is False and body['error'] == body['detail']
    assert '\n' not in body['error']
    return body['error']


# ------------------------------------------------------------------ basics

def test_home_page_and_head_request():
    page = client.get('/')
    assert page.status_code == 200 and 'Content Analyzer' in page.text
    assert '/static/app.js?v=' in page.text                  # cache-busted script
    assert client.head('/').status_code == 200


def test_health_reports_version_providers_and_ocr(monkeypatch):
    body = client.get('/api/health').json()
    from src.version import __version__
    assert body['status'] == 'healthy' and body['version'] == __version__
    assert set(body['providers']) == {'ollama', 'anthropic', 'openai'}
    assert body['providers']['anthropic']['available'] is False
    assert set(body['ocr']) == {'tesseract', 'languages', 'problem'}


def test_health_shows_a_key_as_available_without_revealing_it(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-very-secret')
    text = client.get('/api/health').text
    assert '"openai":{"available":true}' in text.replace(' ', '') and 'sk-very-secret' not in text


def test_presets():
    presets = client.get('/api/presets').json()['presets']
    assert 'vehicle' in presets and presets['vehicle']['description']


def test_app_version_is_the_shared_constant():
    from src.version import __version__
    assert server.app.version == __version__


# ------------------------------------------------------------------ /api/analyze

def test_analyze_success_shape():
    r = client.post('/api/analyze', files=upload(), data={'preset': 'vehicle', 'max_tokens': '55', 'temperature': '0.1'})
    body = r.json()
    assert r.status_code == 200 and body['success'] and body['result'] == 'A calm beach.'
    assert body['metadata']['dimensions'] == '200x80' and body['metadata']['format'] == 'PNG'
    assert body['metadata']['size_mb'] >= 0 and body['metadata']['preset'] == 'vehicle'
    call = FakeVision.instances[0].calls[0]
    assert call['max_tokens'] == 55 and call['temperature'] == 0.1 and 'vehicle' in call['prompt'].lower()


def test_custom_prompt_wins_over_preset():
    client.post('/api/analyze', files=upload(), data={'prompt': 'How many cats?', 'preset': 'vehicle'})
    assert FakeVision.instances[0].calls[0]['prompt'] == 'How many cats?'


def test_blank_prompt_uses_the_default():
    client.post('/api/analyze', files=upload(), data={'prompt': '   '})
    assert 'Describe this image' in FakeVision.instances[0].calls[0]['prompt']


def test_cached_and_truncated_flags_come_from_the_client(monkeypatch):
    original = FakeVision.analyze

    def analyze(self, *a, **k):
        self.last_cached, self.truncated = True, True
        return original(self, *a, **k)
    monkeypatch.setattr(FakeVision, 'analyze', analyze)
    body = client.post('/api/analyze', files=upload()).json()
    assert body['cached'] is True and body['truncated'] is True


@pytest.mark.parametrize('data,status,fragment', [
    ({'provider': 'skynet'}, 400, 'Unsupported provider'),
    ({'preset': 'astrology'}, 400, 'Unknown preset'),
    ({'temperature': '5'}, 422, 'temperature must be between'),
    ({'temperature': '-1'}, 422, 'temperature must be between'),
    ({'max_tokens': '0'}, 422, 'max_tokens must be between'),
    ({'max_tokens': '999999'}, 422, 'max_tokens must be between'),
    ({'temperature': 'hot'}, 422, 'temperature'),
])
def test_analyze_validation(data, status, fragment):
    r = client.post('/api/analyze', files=upload(), data=data)
    assert r.status_code == status and fragment in error_of(r)
    assert not FakeVision.instances


def test_analyze_without_a_file():
    r = client.post('/api/analyze')
    assert r.status_code == 422 and 'file' in error_of(r)


@pytest.mark.parametrize('payload,status,fragment', [
    (b'', 400, 'empty'),
    (b'not an image', 400, 'not an image'),
    (png_bytes(text_image(), 'JPEG')[:1500], 400, 'damaged or cut off'),
])
def test_unusable_uploads(payload, status, fragment):
    r = client.post('/api/analyze', files={'file': ('x.jpg', payload, 'image/jpeg')})
    assert r.status_code == status and fragment in error_of(r)


def test_too_large_upload(monkeypatch):
    monkeypatch.setenv('MAX_UPLOAD_MB', '0.001')
    r = client.post('/api/analyze', files=upload())
    assert r.status_code == 413 and 'limit' in error_of(r)


def test_too_many_pixels(monkeypatch):
    monkeypatch.setenv('MAX_IMAGE_PIXELS', '100')
    r = client.post('/api/analyze', files=upload())
    assert r.status_code == 413 and 'megapixels' in error_of(r)


def test_decompression_bomb_is_a_413_not_a_crash():
    bomb = png_bytes(Image.new('1', (20000, 20000), 1), optimize=True)
    r = client.post('/api/analyze', files={'file': ('bomb.png', bomb, 'image/png')})
    assert r.status_code == 413 and not FakeVision.instances


@pytest.mark.parametrize('kind,status', [
    ('unavailable', 503), ('timeout', 504), ('rate_limit', 429), ('auth', 502), ('model', 400),
    ('bad_request', 400), ('server', 502), ('empty', 502), ('other', 502),
])
def test_model_failures_map_to_statuses(kind, status):
    def fail(prompt, images):
        raise VisionError(kind, f'it failed ({kind})')
    FakeVision.behaviour = staticmethod(fail)
    r = client.post('/api/analyze', files=upload())
    assert r.status_code == status and error_of(r) == f'it failed ({kind})'


def test_missing_api_key_is_a_503_with_the_fix():
    r = client.post('/api/analyze', files=upload(), data={'provider': 'anthropic'})
    assert r.status_code == 503 and 'ANTHROPIC_API_KEY' in error_of(r)


def test_unexpected_crash_is_json_with_no_internals(monkeypatch):
    def boom(prompt, images):
        raise ZeroDivisionError('secret path /Users/someone/x.py')
    FakeVision.behaviour = staticmethod(boom)
    r = client.post('/api/analyze', files=upload())
    assert r.status_code == 500 and r.json()['error'] == 'Unexpected server error: ZeroDivisionError'
    assert 'secret' not in r.text


def test_the_event_loop_is_not_blocked_while_the_model_works(monkeypatch):
    import threading
    import time
    started = threading.Event()

    def slow(prompt, images):
        started.set()
        time.sleep(0.6)
        return 'late'
    FakeVision.behaviour = staticmethod(slow)
    holder = {}
    worker = threading.Thread(target=lambda: holder.update(r=client.post('/api/analyze', files=upload())))
    worker.start()
    started.wait(2)
    t = time.time()
    assert client.get('/api/presets').status_code == 200
    assert time.time() - t < 0.4                       # answered while the model call was still running
    worker.join()
    assert holder['r'].json()['result'] == 'late'


# ------------------------------------------------------------------ /api/compare

def test_compare_without_ai_scores_pixels():
    a = upload(text_image())
    r = client.post('/api/compare', files={'file1': a['file'], 'file2': ('b.png', png_bytes(text_image()), 'image/png')})
    body = r.json()
    assert r.status_code == 200 and body['result']['identical'] and body['result']['similarity_score'] == 100
    assert body['result']['ai_analysis'] is None and not FakeVision.instances


def test_compare_with_ai_uses_the_model():
    FakeVision.behaviour = staticmethod(lambda prompt, images: 'Same. Similarity rating: 88%')
    other = text_image('OTHER TEXT')
    r = client.post('/api/compare', files={'file1': ('a.png', png_bytes(text_image()), 'image/png'),
                                           'file2': ('b.png', png_bytes(other), 'image/png')},
                    data={'use_ai': 'true', 'mode': 'visual'})
    result = r.json()['result']
    assert r.status_code == 200 and result['ai_analysis']['extracted_similarity'] == 88 and result['mode'] == 'visual'


def test_compare_names_the_bad_image_and_validates_mode():
    good = ('a.png', png_bytes(text_image()), 'image/png')
    r = client.post('/api/compare', files={'file1': good, 'file2': ('b.png', b'junk', 'image/png')})
    assert r.status_code == 400 and error_of(r).startswith('Image 2:')
    r = client.post('/api/compare', files={'file1': ('a.png', b'', 'image/png'), 'file2': good})
    assert error_of(r).startswith('Image 1:')
    r = client.post('/api/compare', files={'file1': good, 'file2': good}, data={'mode': 'psychic'})
    assert r.status_code == 400 and 'Unsupported mode' in error_of(r)


# ------------------------------------------------------------------ /api/ocr and /api/detect-language

class FakeOCR:
    last = None
    result = {'text': 'Hello', 'confidence': 91.0, 'method': 'tesseract', 'language': 'eng', 'details': {}}

    def __init__(self, use_tesseract=True, vision_client=None, **kwargs):
        FakeOCR.last = self
        self.use_tesseract = use_tesseract
        self.vision_client = vision_client
        self.tesseract_problem = None
        self.args = None

    def extract_text(self, image, language, fallback_to_vision, confidence_threshold):
        self.args = (language, fallback_to_vision, confidence_threshold)
        return dict(FakeOCR.result)

    def installed_languages(self):
        return ['eng', 'fra']

    def detect_language(self, image):
        return {'primary_language': 'eng', 'languages': [], 'method': 'tesseract'}


@pytest.fixture
def fake_ocr(monkeypatch):
    FakeOCR.result = {'text': 'Hello', 'confidence': 91.0, 'method': 'tesseract', 'language': 'eng', 'details': {}}
    monkeypatch.setattr(server, 'OCRProcessor', FakeOCR)


def test_ocr_success_and_options(fake_ocr):
    r = client.post('/api/ocr', files=upload(), data={'language': 'eng+fra', 'confidence': '70', 'fallback': 'false'})
    body = r.json()
    assert r.status_code == 200 and body['text'] == 'Hello' and body['method'] == 'tesseract'
    assert FakeOCR.last.args == ('eng+fra', False, 70.0) and FakeOCR.last.vision_client is None


def test_ocr_vision_method_forces_the_fallback(fake_ocr):
    client.post('/api/ocr', files=upload(), data={'method': 'vision', 'fallback': 'false'})
    assert FakeOCR.last.use_tesseract is False and FakeOCR.last.args[1] is True
    assert FakeOCR.last.vision_client is not None


@pytest.mark.parametrize('data,fragment', [
    ({'method': 'magic'}, 'Unsupported method'),
    ({'language': 'eng;rm -rf'}, 'not a language code'),
    ({'language': '../x'}, 'not a language code'),
    ({'confidence': '150'}, 'confidence must be between'),
    ({'provider': 'x'}, 'Unsupported provider'),
])
def test_ocr_validation(fake_ocr, data, fragment):
    r = client.post('/api/ocr', files=upload(), data=data)
    assert r.status_code in (400, 422) and fragment in error_of(r)


def test_ocr_engine_errors_become_http_errors(fake_ocr):
    FakeOCR.result = {'text': '', 'confidence': 0.0, 'method': 'none', 'language': 'fra',
                      'details': {'tesseract_error': 'Tesseract has no language data for: fra'}}
    r = client.post('/api/ocr', files=upload(), data={'language': 'fra'})
    assert r.status_code == 400 and 'no language data' in error_of(r)
    FakeOCR.result['details'] = {'vision_error': 'model down'}
    r = client.post('/api/ocr', files=upload())
    assert r.status_code == 502 and error_of(r) == 'model down'


def test_ocr_result_with_no_text_is_still_a_success(fake_ocr):
    FakeOCR.result = {'text': '', 'confidence': 0.0, 'method': 'tesseract', 'language': 'eng', 'details': {}}
    body = client.post('/api/ocr', files=upload()).json()
    assert body['success'] is True and body['text'] == ''


def test_detect_language(fake_ocr):
    body = client.post('/api/detect-language', files=upload()).json()
    assert body['success'] and body['result']['primary_language'] == 'eng'
    r = client.post('/api/detect-language', files={'file': ('x.png', b'junk', 'image/png')})
    assert r.status_code == 400


def test_real_tesseract_result_can_be_serialised_by_the_api(monkeypatch):
    import shutil
    if shutil.which('tesseract') is None:
        pytest.skip('tesseract is not installed')
    from src.core.ocr_processor import OCRProcessor
    monkeypatch.setattr(server, 'OCRProcessor', OCRProcessor)
    r = client.post('/api/ocr', files=upload(text_image()), data={'method': 'tesseract', 'fallback': 'false'})
    assert r.status_code == 200, r.text                    # used to be a 500: Version is not JSON serialisable
    assert r.json()['text'] == 'INVOICE 4821\nTotal due: $93.50'


# ------------------------------------------------------------------ batches

def batch_files(*items):
    return [('files', (name, data, 'image/png')) for name, data in items]


def test_batch_reports_rejected_files_with_their_original_position():
    good = png_bytes(text_image(size=(100, 40)))
    r = client.post('/api/batch-analyze', files=batch_files(('one.png', good), ('bad.png', b'junk'), ('three.png', good), ('empty.png', b'')))
    body = r.json()
    assert r.status_code == 200
    assert (body['total_images'], body['successful'], body['failed']) == (4, 2, 2)
    assert [(x['index'], x['name']) for x in body['results']] == [(0, 'one.png'), (2, 'three.png')]
    assert [(e['index'], e['name']) for e in body['errors']] == [(1, 'bad.png'), (3, 'empty.png')]
    assert 'not an image' in body['errors'][0]['error'] and 'empty' in body['errors'][1]['error']


def test_batch_model_failures_keep_original_positions():
    good = png_bytes(text_image(size=(100, 40)))

    def pick(prompt, images):
        if images[0].getpixel((0, 0)) == (1, 2, 3):
            raise VisionError('other', 'cannot read this one')
        return 'fine'
    FakeVision.behaviour = staticmethod(pick)
    odd = png_bytes(Image.new('RGB', (30, 30), (1, 2, 3)))
    body = client.post('/api/batch-analyze', files=batch_files(('bad.png', b'junk'), ('good.png', good), ('odd.png', odd))).json()
    assert [(e['index'], e['name']) for e in body['errors']] == [(0, 'bad.png'), (2, 'odd.png')]
    assert [(r['index'], r['name']) for r in body['results']] == [(1, 'good.png')]


def test_batch_with_no_usable_file():
    r = client.post('/api/batch-analyze', files=batch_files(('a.txt', b'text'), ('b.png', b'')))
    assert r.status_code == 400 and 'None of the files' in error_of(r) and 'a.txt' in error_of(r)


def test_batch_size_limit(monkeypatch):
    monkeypatch.setenv('MAX_BATCH_FILES', '2')
    good = png_bytes(text_image(size=(50, 20)))
    r = client.post('/api/batch-analyze', files=batch_files(('1.png', good), ('2.png', good), ('3.png', good)))
    assert r.status_code == 413 and 'at most 2' in error_of(r)


@pytest.mark.parametrize('workers', ['0', '9', '1000', '-2'])
def test_worker_count_is_bounded(workers):
    good = png_bytes(text_image(size=(50, 20)))
    r = client.post('/api/batch-analyze', files=batch_files(('1.png', good)), data={'workers': workers})
    assert r.status_code == 422 and 'workers' in error_of(r)


def test_batch_ocr(fake_ocr):
    good = png_bytes(text_image(size=(50, 20)))
    body = client.post('/api/batch-ocr', files=batch_files(('a.png', good), ('b.png', b'junk')), data={'language': 'eng'}).json()
    assert (body['total_images'], body['successful'], body['failed']) == (2, 1, 1)
    assert body['results'][0]['text'] == 'Hello' and body['errors'][0]['name'] == 'b.png'


def test_batch_analyze_validates_like_the_single_endpoint():
    good = png_bytes(text_image(size=(50, 20)))
    assert client.post('/api/batch-analyze', files=batch_files(('a.png', good)), data={'preset': 'zzz'}).status_code == 400
    assert client.post('/api/batch-analyze', files=batch_files(('a.png', good)), data={'provider': 'zzz'}).status_code == 400


# ------------------------------------------------------------------ cache endpoints, CORS

def test_cache_endpoints():
    assert client.get('/api/cache/stats').json()['stats']['hits'] == 0
    assert client.post('/api/cache/cleanup', params={'keep_hours': 5}).json()['success']
    assert client.post('/api/cache/cleanup', params={'keep_hours': -1}).status_code == 422
    assert client.post('/api/cache/clear').json()['success']


def test_no_cors_headers_by_default():
    r = client.get('/api/health', headers={'Origin': 'https://evil.example'})
    assert 'access-control-allow-origin' not in r.headers


def test_cors_is_opt_in_and_never_a_wildcard():
    # the middleware is installed when the module is imported, so check it in a fresh interpreter
    import subprocess
    import sys
    code = (
        "from fastapi.testclient import TestClient\n"
        "import server\n"
        "c = TestClient(server.app)\n"
        "ok = c.get('/api/health', headers={'Origin': 'https://ok.example'})\n"
        "bad = c.get('/api/health', headers={'Origin': 'https://evil.example'})\n"
        "print(ok.headers.get('access-control-allow-origin'), 'access-control-allow-origin' in bad.headers)\n"
    )
    env = dict(__import__('os').environ, CORS_ORIGINS='*, https://ok.example')
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env, cwd=str(server.project_root))
    assert out.stdout.strip().splitlines()[-1] == 'https://ok.example False', out.stderr[-500:]


def test_server_binds_to_loopback_by_default():
    source = (server.project_root / 'server.py').read_text()
    assert 'os.getenv("HOST", "127.0.0.1")' in source and '0.0.0.0"' not in source.replace('HOST=0.0.0.0', '')


def test_a_missing_key_discovered_during_the_call_is_also_a_503():
    def no_key(prompt, images):
        raise ValueError('OPENAI_API_KEY not found in environment')
    FakeVision.behaviour = staticmethod(no_key)
    r = client.post('/api/analyze', files=upload())
    assert r.status_code == 503 and 'OPENAI_API_KEY' in error_of(r)


def test_a_missing_sdk_is_a_503_with_the_install_command():
    def no_sdk(prompt, images):
        raise ImportError('Anthropic library not installed. Install with: pip install anthropic')
    FakeVision.behaviour = staticmethod(no_sdk)
    r = client.post('/api/analyze', files=upload())
    assert r.status_code == 503 and 'pip install anthropic' in error_of(r)
