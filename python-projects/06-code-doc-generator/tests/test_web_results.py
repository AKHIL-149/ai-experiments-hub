"""The /results page must never run script that came from code or from a crafted form."""
import re

import pytest
from fastapi.testclient import TestClient

from src.web.app import app, markdown_to_html

client = TestClient(app)

HOSTILE = [
    '<img src=x onerror="document.title=\'XSS\'">',
    '<script>document.title="XSS"</script>',
    '<a href="javascript:alert(1)">click</a>',
    '<svg onload=alert(1)>',
    '[click](javascript:alert(1))',
    '<iframe srcdoc="<script>alert(1)</script>"></iframe>',
    '</div><script>alert(1)</script>',
]


def post(documentation, fmt='markdown', **extra):
    data = {'code': 'x = 1', 'documentation': documentation, 'raw_documentation': documentation, 'format': fmt,
            'language': 'python', 'ai_enhanced': 'false', 'stats': '{}', 'metadata': '{}'}
    data.update(extra)
    return client.post('/results', data=data)


def real_tags(html):
    """Every actual tag in the HTML (escaped text such as &lt;img&gt; is not a tag)."""
    return re.findall(r'<[a-zA-Z][^>]*>', html)


def assert_no_active_markup(html):
    for tag in real_tags(html):
        low = tag.lower()
        assert not re.search(r'\son\w+\s*=', low), f'event handler in {tag}'
        assert 'javascript:' not in low, f'javascript: URL in {tag}'
        assert not low.startswith(('<script', '<iframe', '<svg', '<img', '<object', '<embed', '<style')), tag


def docs_block(html):
    """Just the container that holds the generated documentation (not the page's own buttons)."""
    start = html.index('id="docsContent"')
    end = html.index('id="rawDocs"', start)
    return html[start:end]


@pytest.mark.parametrize('payload', HOSTILE)
def test_markdown_docs_cannot_inject_script_into_the_page(payload):
    response = post(f'# Title\n\nDocstring: {payload}\n')
    assert response.status_code == 200
    block = docs_block(response.text)
    assert_no_active_markup(block)


def test_markdown_docs_keep_their_structure_and_show_hostile_text_as_text():
    response = post('# Title\n\n**bold** and `code`\n\n<script>alert(1)</script>\n')
    block = docs_block(response.text)
    assert '<h1' in block and '<strong>bold</strong>' in block and '<code>code</code>' in block
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in block
    assert '<script>alert(1)</script>' not in block


def test_a_crafted_html_format_form_runs_only_inside_a_sandboxed_frame():
    response = post('<html><body><script>parent.document.title="XSS"</script></body></html>', fmt='html')
    text = response.text
    assert 'sandbox="allow-scripts"' in text and 'srcdoc="' in text
    assert 'allow-same-origin' not in text
    # the document is inside the srcdoc attribute, escaped, not part of this page
    assert '<script>parent.document.title' not in text
    assert '&lt;script&gt;parent.document.title' in text


def test_json_and_other_formats_are_shown_as_escaped_text():
    for fmt in ('json', 'docstring', 'text'):
        text = post('<script>alert(1)</script>', fmt=fmt).text
        assert '<script>alert(1)</script>' not in text
        assert '&lt;script&gt;alert(1)&lt;/script&gt;' in text


def test_the_code_panel_is_escaped_too():
    text = post('ok', code='<script>alert("code")</script>').text
    assert '<script>alert("code")</script>' not in text


def test_markdown_to_html_directly():
    html = markdown_to_html('A <b onclick=x>b</b> [l](javascript:x) [ok](https://example.com)')
    assert_no_active_markup(html)
    assert 'href="https://example.com"' in html
    assert '&lt;b onclick=x&gt;' in html                    # shown as text, not run


def test_markdown_to_html_without_the_markdown_library_is_also_safe(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def no_markdown(name, *args, **kwargs):
        if name == 'markdown':
            raise ImportError('simulated')
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', no_markdown)
    html = markdown_to_html('# T\n\n<img src=x onerror=alert(1)> **b** [x](javascript:alert(1))')
    assert_no_active_markup(html)
    assert '<h1>T</h1>' in html and '<strong>b</strong>' in html


def test_no_wildcard_cors_with_credentials():
    response = client.get('/api/health', headers={'Origin': 'https://evil.example'})
    assert response.headers.get('access-control-allow-origin') is None
    assert response.headers.get('access-control-allow-credentials') is None


def _cors_headers(origins_env, origin):
    """Start a fresh interpreter (the app reads CORS_ORIGINS when it is imported) and return the CORS headers."""
    import json, os, subprocess, sys
    code = (
        "import json\n"
        "from fastapi.testclient import TestClient\n"
        "from src.web.app import app\n"
        f"r = TestClient(app).get('/api/health', headers={{'Origin': {origin!r}}})\n"
        "print(json.dumps({k: v for k, v in r.headers.items() if k.startswith('access-control')}))\n"
    )
    env = {**os.environ, 'CORS_ORIGINS': origins_env, 'PYTHONWARNINGS': 'ignore'}
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, env=env, timeout=60)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_a_wildcard_in_cors_origins_is_ignored():
    assert _cors_headers('*', 'https://evil.example') == {}
    assert _cors_headers('https://good.example, *', 'https://evil.example') == {}


def test_listed_origins_are_allowed_and_others_are_not():
    allowed = _cors_headers('https://good.example', 'https://good.example')
    assert allowed.get('access-control-allow-origin') == 'https://good.example'
    assert 'access-control-allow-credentials' not in allowed
    assert _cors_headers('https://good.example', 'https://evil.example').get('access-control-allow-origin') is None
