"""analyze.py as a user runs it (Ollama points at a closed port, so no model is involved)."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import ROOT, png_bytes, text_image


def cli(*args, cwd=None, env=None):
    full = dict(os.environ)
    full.update({'OLLAMA_API_URL': 'http://127.0.0.1:9', 'DEFAULT_PROVIDER': 'ollama', 'PYTHONDONTWRITEBYTECODE': '1'})
    full.pop('DEBUG', None)
    full.update(env or {})
    return subprocess.run([sys.executable, str(ROOT / 'analyze.py'), *args], capture_output=True, text=True,
                          cwd=cwd or ROOT, env=full, timeout=120)


@pytest.fixture
def images(tmp_path):
    folder = tmp_path / 'imgs'
    folder.mkdir()
    (folder / 'text.png').write_bytes(png_bytes(text_image()))
    (folder / 'copy.png').write_bytes(png_bytes(text_image()))
    (folder / 'other.png').write_bytes(png_bytes(text_image('SOMETHING ELSE')))
    (folder / 'junk.png').write_bytes(b'not an image')
    return folder


@pytest.fixture(autouse=True)
def private_cache(tmp_path, monkeypatch):
    """The CLI keeps its cache under ./data/cache of the working directory: use a throwaway one."""
    monkeypatch.chdir(tmp_path)


def run_in(tmp_path, *args, **kw):
    return cli(*args, cwd=tmp_path, **kw)


def test_unreadable_image_is_a_one_line_error_without_a_traceback(images, tmp_path):
    out = run_in(tmp_path, 'describe', str(images / 'junk.png'))
    assert out.returncode == 1
    assert 'not an image' in out.stdout and 'Traceback' not in out.stdout + out.stderr


def test_traceback_appears_with_debug(images, tmp_path):
    out = run_in(tmp_path, 'describe', str(images / 'junk.png'), env={'DEBUG': '1'})
    assert out.returncode == 1 and 'Traceback' in out.stdout + out.stderr


def test_missing_file(tmp_path):
    out = run_in(tmp_path, 'describe', str(tmp_path / 'nope.png'))
    assert out.returncode == 1 and 'not found' in out.stdout


def test_describe_when_ollama_is_not_running(images, tmp_path):
    out = run_in(tmp_path, 'describe', str(images / 'text.png'))
    assert out.returncode == 1 and 'ollama serve' in out.stdout and 'Traceback' not in out.stdout + out.stderr


def test_compare_without_ai(images, tmp_path):
    same = run_in(tmp_path, 'compare', str(images / 'text.png'), str(images / 'copy.png'))
    assert same.returncode == 0 and 'Identical: ✅ Yes' in same.stdout and 'Similarity Score: 100%' in same.stdout
    different = run_in(tmp_path, 'compare', str(images / 'text.png'), str(images / 'other.png'))
    assert 'Identical: ❌ No' in different.stdout


def test_compare_with_a_bad_second_image(images, tmp_path):
    out = run_in(tmp_path, 'compare', str(images / 'text.png'), str(images / 'junk.png'))
    assert out.returncode == 1 and 'not an image' in out.stdout


def test_cache_commands(tmp_path):
    stats = run_in(tmp_path, 'cache-stats')
    assert stats.returncode == 0 and 'Hit Rate' in stats.stdout
    assert run_in(tmp_path, 'cache-cleanup').returncode == 0
    assert run_in(tmp_path, 'cache-clear').returncode == 0


@pytest.mark.skipif(shutil.which('tesseract') is None, reason='the tesseract program is not installed')
class TestOcr:
    def test_reads_text(self, images, tmp_path):
        out = run_in(tmp_path, 'ocr', str(images / 'text.png'), '--method', 'tesseract')
        assert out.returncode == 0
        assert 'INVOICE 4821' in out.stdout and 'Total due: $93.50' in out.stdout and 'Confidence: 9' in out.stdout

    def test_json_output(self, images, tmp_path):
        target = tmp_path / 'out.json'
        out = run_in(tmp_path, 'ocr', str(images / 'text.png'), '--method', 'tesseract', '--output-json', str(target))
        assert out.returncode == 0
        data = json.loads(target.read_text())
        assert data['text'] == 'INVOICE 4821\nTotal due: $93.50' and data['method'] == 'tesseract'

    def test_missing_language_is_explained(self, images, tmp_path):
        out = run_in(tmp_path, 'ocr', str(images / 'text.png'), '--method', 'tesseract', '--language', 'xyz')
        assert 'no language data' in out.stdout

    def test_detect_language(self, images, tmp_path):
        out = run_in(tmp_path, 'detect-language', str(images / 'text.png'))
        assert out.returncode == 0 and 'eng' in out.stdout


def test_batch_describe_help_and_batch_ocr_with_a_bad_file(images, tmp_path):
    if shutil.which('tesseract') is None:
        pytest.skip('the tesseract program is not installed')
    out = run_in(tmp_path, 'batch-ocr', '--directory', str(images), '--method', 'tesseract', '--output-json', str(tmp_path / 'b.json'))
    assert 'junk.png' in out.stdout
    data = json.loads((tmp_path / 'b.json').read_text())
    assert data['metadata']['total_images'] == 4 and data['metadata']['failed'] == 1
    assert [(e['index'], e['name']) for e in data['errors']] == [(1, 'junk.png')]         # sorted: copy, junk, other, text
    assert [(r['index'], r['name']) for r in data['results']] == [(0, 'copy.png'), (2, 'other.png'), (3, 'text.png')]


# ------------------------------------------------------------------ finding images in a folder

def folder(tmp_path):
    base = tmp_path / 'f'
    for name in ('a.png', 'B.JPG', 'c.jpeg', 'd.webp', 'e.tiff', 'notes.txt', 'doc.pdf', '.hidden.png', 'sub/f.png', 'sub/deep/g.gif'):
        path = base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x')
    return base


def names(paths, base):
    return [str(Path(p).relative_to(base)) for p in paths]


def test_default_pattern_finds_every_image_type_in_any_case_but_not_other_files(tmp_path):
    import analyze
    base = folder(tmp_path)
    assert names(analyze.find_images(str(base)), base) == ['B.JPG', 'a.png', 'c.jpeg', 'd.webp', 'e.tiff']


def test_recursive_search_goes_into_subfolders(tmp_path):
    import analyze
    base = folder(tmp_path)
    assert names(analyze.find_images(str(base), recursive=True), base) == [
        'B.JPG', 'a.png', 'c.jpeg', 'd.webp', 'e.tiff', 'sub/deep/g.gif', 'sub/f.png']


def test_a_glob_pattern_is_honoured(tmp_path):
    import analyze
    base = folder(tmp_path)
    assert names(analyze.find_images(str(base), '*.png'), base) == ['a.png']
    assert names(analyze.find_images(str(base), '*.png', recursive=True), base) == ['a.png', 'sub/f.png']


def test_brace_patterns_match_nothing_because_glob_has_no_braces(tmp_path):
    import analyze
    assert analyze.find_images(str(folder(tmp_path)), '*.{png,jpg}') == []


def test_missing_directory(tmp_path):
    import analyze
    with pytest.raises(FileNotFoundError):
        analyze.find_images(str(tmp_path / 'nope'))


def test_directory_with_no_images_says_so(tmp_path):
    (tmp_path / 'empty').mkdir()
    out = run_in(tmp_path, 'batch-ocr', '--directory', str(tmp_path / 'empty'))
    assert out.returncode == 1 and 'No images found' in out.stdout
    out = run_in(tmp_path, 'batch-ocr', '--directory', str(tmp_path / 'missing'))
    assert out.returncode == 1 and 'Directory not found' in out.stdout


def test_batch_csv_export_lists_the_unreadable_file_in_the_errors_file(images, tmp_path):
    if shutil.which('tesseract') is None:
        pytest.skip('the tesseract program is not installed')
    target = tmp_path / 'b.csv'
    run_in(tmp_path, 'batch-ocr', '--directory', str(images), '--method', 'tesseract', '--output-csv', str(target))
    assert 'junk.png' in (tmp_path / 'b_errors.csv').read_text()
    assert 'junk.png' not in target.read_text()
