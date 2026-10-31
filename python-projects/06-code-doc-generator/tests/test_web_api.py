"""The JSON API: real HTTP status codes, honest warnings, no temp paths, no real model."""
import json

import pytest
from fastapi.testclient import TestClient

from src.core.llm_client import LLMError
from src.web.app import app
from src.web.routes import detect_language

client = TestClient(app)

PY = 'def add(a, b):\n    """Add two numbers."""\n    return a + b\n'
JS = 'function greet(name) {\n  return "hi " + name;\n}\n'
JAVA = 'public class Calc {\n    public int twice(int x) { return x * 2; }\n}\n'


class FakeLLM:
    """Stands in for the model client; `reply` may be text or an exception to raise."""
    reply = 'It adds two numbers.'
    calls = 0
    truncated = False

    def __init__(self, backend='ollama', model=None):
        if backend == 'anthropic':
            raise ValueError('ANTHROPIC_API_KEY not found in environment')
        self.backend = backend
        self.model = model or 'fake-model'

    def generate(self, prompt, max_tokens=1000, temperature=0.7, system=None):
        type(self).calls += 1
        if isinstance(type(self).reply, Exception):
            raise type(self).reply
        return type(self).reply


@pytest.fixture(autouse=True)
def fake_model(monkeypatch, tmp_path):
    FakeLLM.reply = 'It adds two numbers.'
    FakeLLM.calls = 0
    monkeypatch.setattr('src.core.doc_generator.LLMClient', FakeLLM)
    monkeypatch.setenv('ENABLE_CACHE', 'false')
    monkeypatch.setenv('CACHE_DIR', str(tmp_path / 'cache'))
    return FakeLLM


def generate(**fields):
    data = {'language': 'python', 'format': 'markdown', 'use_ai': 'false'}
    data.update(fields)
    files = data.pop('files', None)
    return client.post('/api/generate', data=data, files=files)


# ------------------------------------------------------------------ success

def test_generate_from_pasted_code():
    r = generate(code=PY)
    assert r.status_code == 200
    body = r.json()
    assert body['status'] == 'success'
    assert 'add' in body['documentation'] and 'Add two numbers.' in body['documentation']
    assert body['stats'] == {'language': 'python', 'functions': 1, 'classes': 0, 'lines': 3}
    assert body['ai_enhanced'] is False and body['warnings'] == []
    assert body['metadata']['model'] == 'n/a (AI off)'


def test_generate_with_ai_uses_the_model_and_reports_it():
    r = generate(code=PY, use_ai='true', model='my-model')
    body = r.json()
    assert 'It adds two numbers.' in body['documentation']
    assert body['ai_enhanced'] is True
    assert body['metadata']['model'] == 'my-model'
    assert body['warnings'] == []


def test_file_upload_decides_the_language_from_its_extension():
    r = generate(language='python', files={'file': ('app.js', JS.encode(), 'text/plain')})
    body = r.json()
    assert r.status_code == 200
    assert body['language'] == 'javascript' and 'greet' in body['documentation']
    assert 'app.js' in body['documentation'] or 'greet' in body['documentation']


def test_java_upload():
    r = generate(files={'file': ('Calc.java', JAVA.encode(), 'text/plain')})
    assert r.status_code == 200 and 'twice' in r.json()['documentation']


def test_json_and_html_formats():
    assert json.loads(generate(code=PY, format='json').json()['documentation'])
    assert '<html' in generate(code=PY, format='html').json()['documentation'].lower()


def test_format_name_is_case_insensitive():
    assert generate(code=PY, format='JSON').status_code == 200


def test_auto_language_is_detected_from_the_code():
    r = generate(code=JS, language='auto')
    assert r.status_code == 200 and r.json()['language'] == 'javascript'


def test_latin1_upload_is_read_not_rejected():
    source = '# caf\xe9 \u2013 notes\ndef f():\n    """na\xefve"""\n'.encode('cp1252')
    r = generate(files={'file': ('latin.py', source, 'text/plain')})
    assert r.status_code == 200
    assert 'f' in r.json()['documentation']


def test_utf8_with_bom_is_read():
    r = generate(files={'file': ('bom.py', b'\xef\xbb\xbf' + PY.encode(), 'text/plain')})
    assert r.status_code == 200


def test_temp_paths_never_reach_the_user():
    body = generate(code=PY).json()
    assert '/tmp' not in body['documentation'] and '/var/folders' not in body['documentation']
    assert 'pasted_code.py' in body['documentation']


def test_uploaded_file_name_is_shown_but_not_its_directory():
    body = generate(files={'file': ('../../etc/mine.py', PY.encode(), 'text/plain')}).json()
    assert 'mine.py' in body['documentation'] and '..' not in body['documentation']


# ------------------------------------------------------------------ the request is wrong -> 4xx

@pytest.mark.parametrize('fields,status,fragment', [
    ({}, 400, 'No code provided'),
    ({'code': '   \n '}, 400, 'No code provided'),
    ({'code': PY, 'format': 'pdf'}, 400, 'Unsupported format'),
    ({'code': PY, 'format': 'all'}, 400, 'Unsupported format'),
    ({'code': PY, 'format': 'docstring'}, 400, 'Unsupported format'),
    ({'code': PY, 'language': 'cobol'}, 400, 'Unsupported language'),
    ({'code': PY, 'provider': 'skynet'}, 400, 'Unsupported provider'),
    ({'code': 'def broken(:\n'}, 422, 'Could not parse pasted_code.py'),
])
def test_bad_requests_get_a_status_code_and_a_one_line_reason(fields, status, fragment):
    r = generate(**fields)
    assert r.status_code == status
    detail = r.json()['detail']
    assert fragment in detail and '\n' not in detail


def test_parse_error_message_has_no_temp_path():
    detail = generate(code='def broken(:\n').json()['detail']
    assert '/tmp' not in detail and '/var/' not in detail


def test_unsupported_upload_type():
    r = generate(files={'file': ('notes.txt', b'hello', 'text/plain')})
    assert r.status_code == 400 and '.txt' in r.json()['detail']


def test_empty_upload():
    r = generate(files={'file': ('empty.py', b'  \n', 'text/plain')})
    assert r.status_code == 400 and 'empty' in r.json()['detail']


def test_binary_upload():
    r = generate(files={'file': ('x.py', b'\x00\x01\x02def f(): pass', 'application/octet-stream')})
    assert r.status_code == 400 and 'binary' in r.json()['detail']


def test_oversized_source(monkeypatch):
    monkeypatch.setenv('MAX_CODE_BYTES', '100')
    r = generate(code='x = 1\n' * 100)
    assert r.status_code == 413 and 'limit' in r.json()['detail']


# ------------------------------------------------------------------ the model misbehaves -> warnings, not failure

def test_model_down_gives_docs_with_a_warning(fake_model):
    fake_model.reply = LLMError('unavailable', 'Cannot reach Ollama. Start it with: ollama serve')
    r = generate(code=PY, use_ai='true')
    body = r.json()
    assert r.status_code == 200
    assert body['ai_enhanced'] is False
    assert any('ollama serve' in w for w in body['warnings'])
    assert 'Add two numbers.' in body['documentation']           # falls back to the docstring
    assert 'Cannot reach' not in body['documentation']


def test_provider_without_a_key_gives_docs_and_a_warning():
    body = generate(code=PY, use_ai='true', provider='anthropic').json()
    assert body['ai_enhanced'] is False
    assert any('ANTHROPIC_API_KEY' in w for w in body['warnings'])
    assert 'Add two numbers.' in body['documentation']


def test_enhance_with_provider_without_a_key_is_503():
    r = client.post('/api/enhance', data={'code': PY, 'provider': 'anthropic'})
    assert r.status_code == 503 and 'ANTHROPIC_API_KEY' in r.json()['detail']


def test_enhance_without_a_model_is_503(fake_model):
    fake_model.reply = LLMError('unavailable', 'Cannot reach Ollama')
    r = client.post('/api/enhance', data={'code': PY, 'language': 'python'})
    assert r.status_code == 503 and 'Cannot reach' in r.json()['detail']


def test_enhance_returns_code_with_new_docstrings():
    r = client.post('/api/enhance', data={'code': 'def add(a, b):\n    return a + b\n', 'language': 'python'})
    body = r.json()
    assert r.status_code == 200 and body['success'] is True
    assert 'def add(a, b):' in body['enhanced_code'] and 'It adds two numbers.' in body['enhanced_code']


def test_enhance_bad_provider_and_missing_code():
    assert client.post('/api/enhance', data={'code': PY, 'provider': 'x'}).status_code == 400
    assert client.post('/api/enhance', data={}).status_code == 400


def test_enhance_unparseable_code_is_422():
    r = client.post('/api/enhance', data={'code': 'def broken(:\n'})
    assert r.status_code == 422 and '/tmp' not in r.json()['detail']


# ------------------------------------------------------------------ analyze

def test_analyze_lists_names():
    r = client.post('/api/analyze', data={'code': 'class A:\n    pass\ndef f(): pass\ndef g(): pass\n'})
    body = r.json()
    assert body['total_functions'] == 2 and body['total_classes'] == 1
    assert body['functions'] == ['f', 'g'] and body['classes'] == ['A']


def test_analyze_syntax_error_is_422_not_an_empty_success():
    r = client.post('/api/analyze', data={'code': 'def broken(:\n'})
    assert r.status_code == 422 and 'Could not parse' in r.json()['detail']


def test_analyze_needs_code():
    assert client.post('/api/analyze', data={}).status_code == 400


# ------------------------------------------------------------------ misc

def test_health_reports_the_package_version():
    from src.version import __version__
    assert client.get('/api/health').json() == {'status': 'healthy', 'version': __version__, 'service': 'code-doc-generator'}


def test_results_page_shows_run_warnings_escaped():
    r = client.post('/results', data={
        'code': 'x', 'documentation': 'd', 'format': 'markdown', 'language': 'python', 'ai_enhanced': 'false',
        'stats': '{}', 'metadata': '{}', 'warnings': json.dumps(['AI was off <script>alert(1)</script>']),
    })
    assert 'AI was off' in r.text
    assert '<script>alert(1)</script>' not in r.text


def test_results_page_survives_garbage_warnings():
    r = client.post('/results', data={'code': 'x', 'documentation': 'd', 'warnings': '{not json'})
    assert r.status_code == 200 and 'runWarnings' not in r.text


@pytest.mark.parametrize('code,language', [
    ('def f(x):\n    return x\n', 'python'),
    ('import os\nclass A: pass\n', 'python'),
    ('function add(a, b) { return a + b; }', 'javascript'),
    ('const x = () => 1;\nmodule.exports = x;', 'javascript'),
    ("import fs from 'fs';\nlet y = 2;", 'javascript'),
    ('interface User { name: string }\nfunction f(u: User): string { return u.name }', 'typescript'),
    ('enum Color { Red, Green }', 'typescript'),
    ('public class A {\n  public static void main(String[] a) { System.out.println(1); }\n}', 'java'),
    ('package a.b;\nimport java.util.List;\nclass X {}', 'java'),
])
def test_language_detection(code, language):
    assert detect_language(code) == language


def test_script_and_css_urls_carry_a_version_so_browsers_refetch_changed_files():
    html = client.get('/').text
    import re
    assert re.search(r'/static/js/main\.js\?v=\w+', html)
    assert re.search(r'/static/css/styles\.css\?v=\w+', html)
    assert client.get('/static/js/main.js?v=1').status_code == 200
