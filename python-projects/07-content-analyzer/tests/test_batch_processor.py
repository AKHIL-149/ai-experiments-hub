"""Batch analysis / OCR and the exports."""
import csv
import json
import threading
import time

import pytest
from PIL import Image

from src.core.batch_processor import BatchProcessor, csv_safe

IMAGES = [Image.new('RGB', (10, 10), c) for c in ('red', 'green', 'blue', 'white')]


class FakeVision:
    def __init__(self, fail=(), delay=0.0):
        self.fail, self.delay = set(fail), delay
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()

    def analyze(self, prompt, images, temperature=0.7, max_tokens=1000):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(self.delay)
        with self.lock:
            self.active -= 1
        color = images[0].getpixel((0, 0))
        if color in self.fail:
            raise RuntimeError(f'cannot read {color}')
        return f'result for {color}'


class FakeOCR:
    def __init__(self, results):
        self.results = results

    def extract_text(self, image, language, fallback_to_vision, confidence_threshold):
        return self.results[image.getpixel((0, 0))]


def test_results_keep_input_order_even_when_workers_finish_out_of_order():
    class Slow(FakeVision):
        def analyze(self, prompt, images, **k):
            time.sleep(0.05 if images[0].getpixel((0, 0)) == (255, 0, 0) else 0)
            return super().analyze(prompt, images, **k)
    out = BatchProcessor(vision_client=Slow(), max_workers=4).batch_analyze(IMAGES, ['a', 'b', 'c', 'd'], prompt='p')
    assert [r['name'] for r in out['results']] == ['a', 'b', 'c', 'd']
    assert [r['index'] for r in out['results']] == [0, 1, 2, 3]


def test_one_failure_does_not_stop_the_others():
    out = BatchProcessor(vision_client=FakeVision(fail={(0, 128, 0)}), max_workers=2).batch_analyze(IMAGES, prompt='p')
    assert (out['total_images'], out['successful'], out['failed']) == (4, 3, 1)
    assert out['errors'][0]['index'] == 1 and 'cannot read' in out['errors'][0]['error']


def test_default_names_and_worker_limit():
    vision = FakeVision(delay=0.05)
    out = BatchProcessor(vision_client=vision, max_workers=2).batch_analyze(IMAGES, prompt='p')
    assert [r['name'] for r in out['results']] == ['image_1', 'image_2', 'image_3', 'image_4']
    assert vision.peak <= 2


def test_progress_callback_is_called_once_per_image():
    seen = []
    BatchProcessor(vision_client=FakeVision()).batch_analyze(IMAGES, prompt='p', progress_callback=lambda done, total, r: seen.append((done, total)))
    assert sorted(seen) == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_empty_batch():
    out = BatchProcessor(vision_client=FakeVision()).batch_analyze([], prompt='p')
    assert out['total_images'] == 0 and out['avg_time_per_image'] == 0


def test_a_client_is_required():
    with pytest.raises(ValueError):
        BatchProcessor().batch_analyze(IMAGES, prompt='p')
    with pytest.raises(ValueError):
        BatchProcessor().batch_ocr(IMAGES)


def ocr_result(text, method='tesseract', details=None):
    return {'text': text, 'confidence': 90.0, 'method': method, 'language': 'eng', 'details': details or {}}


def test_ocr_batch_reports_engine_failures_as_failures_not_empty_successes():
    results = {
        (255, 0, 0): ocr_result('hello'),
        (0, 128, 0): ocr_result('', method='none', details={'vision_error': 'model down'}),
        (0, 0, 255): ocr_result('', method='none', details={'tesseract_error': 'no language data'}),
        (255, 255, 255): ocr_result('', method='tesseract'),               # genuinely no text: a success
    }
    out = BatchProcessor(ocr_processor=FakeOCR(results)).batch_ocr(IMAGES)
    assert out['successful'] == 2 and out['failed'] == 2
    assert {e['error'] for e in out['errors']} == {'model down', 'no language data'}


def test_ocr_batch_exception_in_one_image():
    class Broken(FakeOCR):
        def extract_text(self, image, **k):
            raise RuntimeError('boom')
    out = BatchProcessor(ocr_processor=Broken({})).batch_ocr(IMAGES[:1])
    assert out['failed'] == 1 and out['errors'][0]['error'] == 'boom'


def test_vision_method_enables_the_fallback_flag():
    seen = []

    class Spy(FakeOCR):
        def extract_text(self, image, language, fallback_to_vision, confidence_threshold):
            seen.append(fallback_to_vision)
            return ocr_result('x')
    BatchProcessor(ocr_processor=Spy({})).batch_ocr(IMAGES[:1], method='vision', fallback_to_vision=False)
    BatchProcessor(ocr_processor=Spy({})).batch_ocr(IMAGES[:1], method='auto', fallback_to_vision=False)
    assert seen == [True, False]


# ------------------------------------------------------------------ exports

@pytest.fixture
def vision_batch():
    return BatchProcessor(vision_client=FakeVision(fail={(0, 128, 0)})).batch_analyze(IMAGES, ['a.png', 'b.png', 'c.png', 'd.png'], prompt='p')


def test_csv_neutralises_formulas(tmp_path):
    batch = {'results': [{'index': 0, 'name': '=cmd|calc', 'result': '=HYPERLINK("http://evil","x")', 'success': True},
                         {'index': 1, 'name': '+1', 'result': '@SUM(A1)', 'success': True},
                         {'index': 2, 'name': 'ok', 'result': '-5 degrees', 'success': True}],
             'errors': [{'index': 3, 'name': '=bad', 'error': '=ERR()'}]}
    path = tmp_path / 'out.csv'
    BatchProcessor().export_to_csv(batch, path, 'vision')
    rows = list(csv.DictReader(open(path, newline='', encoding='utf-8')))
    assert [r['name'] for r in rows] == ["'=cmd|calc", "'+1", 'ok']
    assert [r['result'] for r in rows] == ["'=HYPERLINK(\"http://evil\",\"x\")", "'@SUM(A1)", "'-5 degrees"]
    errors = list(csv.DictReader(open(tmp_path / 'out_errors.csv', newline='', encoding='utf-8')))
    assert errors[0]['name'] == "'=bad" and errors[0]['error'] == "'=ERR()"


@pytest.mark.parametrize('value,expected', [('=1', "'=1"), ('+1', "'+1"), ('-1', "'-1"), ('@a', "'@a"), ('\tx', "'\tx"),
                                            ('normal', 'normal'), ('', ''), (5, 5), (None, None), ('a=b', 'a=b')])
def test_csv_safe(value, expected):
    assert csv_safe(value) == expected


def test_csv_ocr_columns_and_multiline_text(tmp_path):
    batch = {'results': [{'index': 0, 'name': 'r.png', 'text': 'line1\nline2, with comma', 'method': 'tesseract',
                          'confidence': 91.5, 'language': 'eng', 'success': True}], 'errors': []}
    path = tmp_path / 'ocr.csv'
    BatchProcessor().export_to_csv(batch, path, 'ocr')
    row = list(csv.DictReader(open(path, newline='', encoding='utf-8')))[0]
    assert row['text'] == 'line1\nline2, with comma' and row['confidence'] == '91.5'
    assert not (tmp_path / 'ocr_errors.csv').exists()


def test_json_export_keeps_unicode_and_metadata(tmp_path, vision_batch):
    vision_batch['results'][0]['result'] = '日本語 ✓'
    path = tmp_path / 'out.json'
    BatchProcessor().export_to_json(vision_batch, path)
    data = json.loads(path.read_text(encoding='utf-8'))
    assert '日本語 ✓' in path.read_text(encoding='utf-8')
    assert data['metadata']['total_images'] == 4 and data['metadata']['failed'] == 1
    BatchProcessor().export_to_json(vision_batch, tmp_path / 'bare.json', include_metadata=False)
    assert 'metadata' not in json.loads((tmp_path / 'bare.json').read_text())


def test_txt_export(tmp_path, vision_batch):
    path = tmp_path / 'out.txt'
    BatchProcessor().export_to_txt(vision_batch, path, 'vision')
    text = path.read_text(encoding='utf-8')
    assert 'Total Images: 4' in text and '[1] a.png' in text and 'ERRORS' in text and 'b.png' in text
