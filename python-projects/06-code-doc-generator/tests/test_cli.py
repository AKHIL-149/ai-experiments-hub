"""The command line, run as a user would run it (no real model: Ollama points at a closed port)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GOOD = 'def add(a, b):\n    """Add."""\n    return a + b\n'


def cli(*args, cwd=None, extra_env=None):
    env = dict(os.environ)
    env.update({'OLLAMA_API_URL': 'http://127.0.0.1:9', 'ENABLE_CACHE': 'false', 'LLM_PROVIDER': 'ollama',
                'DEFAULT_FORMAT': 'markdown', 'PYTHONDONTWRITEBYTECODE': '1'})
    env.pop('OUTPUT_DIR', None)
    env.update(extra_env or {})
    return subprocess.run([sys.executable, str(ROOT / 'doc_gen.py'), *args], capture_output=True, text=True,
                          cwd=cwd or ROOT, env=env, timeout=60)


@pytest.fixture
def project(tmp_path):
    src = tmp_path / 'proj'
    src.mkdir()
    (src / 'good.py').write_text(GOOD)
    return src


def test_version_matches_the_package():
    from src.version import __version__
    out = cli('--version')
    assert out.returncode == 0 and __version__ in out.stdout


def test_no_command_shows_help_and_fails():
    out = cli()
    assert out.returncode == 1 and 'usage:' in out.stdout


def test_generate_markdown_and_json(project, tmp_path):
    out_dir = tmp_path / 'out'
    out = cli('generate', str(project / 'good.py'), '-o', str(out_dir), '--no-ai', '-f', 'markdown,json')
    assert out.returncode == 0, out.stdout + out.stderr
    assert sorted(p.name for p in out_dir.iterdir()) == ['good_docs.json', 'good_docs.md']
    assert json.loads((out_dir / 'good_docs.json').read_text())['module']['functions'][0]['name'] == 'add'
    assert 'Add.' in (out_dir / 'good_docs.md').read_text()
    from src.version import __version__
    assert f'Generator v{__version__}' in out.stdout


def test_generate_all_formats(project, tmp_path):
    out = cli('generate', str(project), '-o', str(tmp_path / 'o'), '--no-ai', '-f', 'all')
    assert out.returncode == 0
    assert sorted(p.suffix for p in (tmp_path / 'o').iterdir()) == ['.html', '.json', '.md']
    assert 'file://' in out.stdout            # the hint for opening the HTML


def test_default_format_comes_from_the_environment(project, tmp_path):
    out = cli('generate', str(project), '-o', str(tmp_path / 'o'), '--no-ai', extra_env={'DEFAULT_FORMAT': 'json'})
    assert out.returncode == 0 and [p.suffix for p in (tmp_path / 'o').iterdir()] == ['.json']


def test_bad_format_is_rejected_with_the_valid_choices(project, tmp_path):
    out = cli('generate', str(project), '-o', str(tmp_path / 'o'), '--no-ai', '-f', 'pdf')
    assert out.returncode == 1
    assert 'Invalid format: pdf' in out.stdout and 'markdown' in out.stdout
    assert not (tmp_path / 'o').exists()


def test_missing_input(tmp_path):
    out = cli('generate', str(tmp_path / 'nope'), '--no-ai')
    assert out.returncode == 1 and 'not found' in out.stdout


def test_directory_without_source_files(tmp_path):
    (tmp_path / 'readme.txt').write_text('hi')
    out = cli('generate', str(tmp_path), '-o', str(tmp_path / 'o'), '--no-ai')
    assert out.returncode == 1 and 'No supported source files' in out.stdout


def test_unparseable_file_is_a_warning_not_a_failure(project, tmp_path):
    (project / 'bad.py').write_text('def oops(:\n')
    out = cli('generate', str(project), '-o', str(tmp_path / 'o'), '--no-ai', '-f', 'json')
    assert out.returncode == 0
    assert '1 warning(s)' in out.stdout and 'Skipped bad.py' in out.stdout
    assert (tmp_path / 'o' / 'proj_docs.json').exists()


def test_model_that_cannot_be_reached_is_one_warning_and_docs_still_come_out(project, tmp_path):
    out = cli('generate', str(project / 'good.py'), '-o', str(tmp_path / 'o'), '-f', 'markdown')
    assert out.returncode == 0
    assert out.stdout.count('Cannot reach Ollama') == 1
    assert 'Add.' in (tmp_path / 'o' / 'good_docs.md').read_text()


def test_no_recursive(project, tmp_path):
    (project / 'sub').mkdir()
    (project / 'sub' / 'inner.py').write_text('def inner():\n    return 1\n')
    out = cli('generate', str(project), '-o', str(tmp_path / 'o'), '--no-ai', '--no-recursive', '-f', 'json')
    assert out.returncode == 0
    data = json.loads((tmp_path / 'o' / 'proj_docs.json').read_text())
    assert 'inner' not in json.dumps(data)


def test_enhance_with_unreachable_model_fails_and_writes_nothing(project, tmp_path):
    target = tmp_path / 'enhanced.py'
    out = cli('enhance', str(project / 'good.py'), '-o', str(target))
    assert out.returncode == 1
    assert 'Cannot reach Ollama' in out.stdout
    assert not target.exists()
    assert (project / 'good.py').read_text() == GOOD


def test_enhance_refuses_a_directory(project):
    out = cli('enhance', str(project))
    assert out.returncode == 1 and 'must be a file' in out.stdout


def test_analyze_counts_and_reports_unparseable_files(project):
    (project / 'bad.py').write_text('def oops(:\n')
    out = cli('analyze', str(project))
    assert 'Total functions: 1' in out.stdout
    assert 'could not be parsed' in out.stdout and 'bad.py' in out.stdout


def test_analyze_details_lists_names(project):
    out = cli('analyze', str(project), '--details')
    assert 'Functions: add' in out.stdout


def test_analyze_missing_path(tmp_path):
    out = cli('analyze', str(tmp_path / 'nope'))
    assert out.returncode == 1 and 'not found' in out.stdout
