"""OCR: Tesseract (a scripted fake for the logic, the real program for one end-to-end check) and the vision fallback."""
import shutil
import types

import pytest
from PIL import Image

from src.core.ocr_processor import OCRProcessor, clean_vision_text
from tests.conftest import text_image


def table(words, conf=None, lines=None):
    """A Tesseract-style word table. words: list of (text, conf, block, par, line)."""
    keys = ['text', 'conf', 'block_num', 'par_num', 'line_num']
    data = {k: [] for k in keys + ['left', 'top', 'width', 'height']}
    for i, (text, c, b, p, l) in enumerate(words):
        for k, v in zip(keys, (text, c, b, p, l)):
            data[k].append(v)
        data['left'].append(10 * i)
        data['top'].append(20)
        data['width'].append(30)
        data['height'].append(12)
    return data


class FakeTesseract:
    Output = types.SimpleNamespace(DICT='dict')

    def __init__(self, data=None, languages=('eng', 'osd'), error=None):
        self.data = data
        self.languages = list(languages)
        self.error = error
        self.calls = []

    def image_to_data(self, image, lang='eng', config='', output_type=None, timeout=0):
        self.calls.append({'size': image.size, 'mode': image.mode, 'lang': lang, 'config': config, 'timeout': timeout})
        if self.error:
            raise self.error
        return self.data

    def image_to_osd(self, image, output_type=None):
        return {'script': 'Latin', 'script_conf': 4.0}

    def get_languages(self, config=''):
        return self.languages

    def get_tesseract_version(self):
        class Version:                # like packaging.version.Version: not JSON serialisable
            def __str__(self):
                return '5.5.4'
        return Version()


class FakeVision:
    backend, model = 'ollama', 'llava'

    def __init__(self, reply='Hello world', error=None):
        self.reply, self.error, self.prompts = reply, error, []

    def analyze(self, prompt, images, temperature=0.7, max_tokens=1000):
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.reply


def processor(fake=None, vision=None):
    ocr = OCRProcessor(use_tesseract=True, vision_client=vision)
    ocr._pytesseract = fake or FakeTesseract()
    ocr.use_tesseract = True
    return ocr


IMG = Image.new('RGB', (1200, 400), 'white')


# ------------------------------------------------------------------ the confidence bug

def test_empty_words_do_not_count_towards_confidence():
    # a page with no text: Tesseract still returns empty "words" with a high score
    data = table([('', 95, 1, 1, 1), ('', 95, 1, 1, 2)])
    result = processor(FakeTesseract(data)).extract_text(IMG, fallback_to_vision=False)
    assert result['text'] == '' and result['confidence'] == 0.0
    assert result['method'] == 'tesseract'


def test_no_text_falls_back_to_the_vision_model_instead_of_returning_95_percent_nothing():
    data = table([('', 95, 1, 1, 1)])
    vision = FakeVision('Signboard text')
    result = processor(FakeTesseract(data), vision).extract_text(IMG)
    assert result['method'] == 'vision' and result['text'] == 'Signboard text'
    assert len(vision.prompts) == 1


def test_confidence_is_the_mean_over_real_words_only():
    data = table([('Hello', 90, 1, 1, 1), ('', 99, 1, 1, 1), ('world', 70, 1, 1, 1), ('x', -1, 1, 1, 1)])
    result = processor(FakeTesseract(data)).extract_text(IMG, fallback_to_vision=False)
    assert result['confidence'] == 80.0


def test_no_text_is_never_accepted_even_with_a_zero_threshold():
    vision = FakeVision('Rescued')
    result = processor(FakeTesseract(table([('', 95, 1, 1, 1)])), vision).extract_text(IMG, confidence_threshold=0)
    assert result['method'] == 'vision'


@pytest.mark.parametrize('mode', ['RGBA', 'P', 'CMYK', '1'])
def test_odd_colour_modes_reach_tesseract_as_rgb(mode):
    fake = FakeTesseract(table([('Hi', 90, 1, 1, 1)]))
    processor(fake).extract_text(Image.new(mode, (1200, 300)), fallback_to_vision=False)
    assert fake.calls[0]['mode'] in ('RGB', 'L')


def test_confident_tesseract_result_skips_the_vision_model():
    data = table([('Hello', 90, 1, 1, 1)])
    vision = FakeVision()
    result = processor(FakeTesseract(data), vision).extract_text(IMG)
    assert result['method'] == 'tesseract' and vision.prompts == []


def test_low_confidence_uses_vision_when_allowed_and_keeps_tesseract_when_not():
    data = table([('Heljo', 30, 1, 1, 1)])
    assert processor(FakeTesseract(data), FakeVision('Hello')).extract_text(IMG)['text'] == 'Hello'
    kept = processor(FakeTesseract(data), FakeVision('Hello')).extract_text(IMG, fallback_to_vision=False)
    assert kept['text'] == 'Heljo' and kept['method'] == 'tesseract'


def test_threshold_is_respected():
    data = table([('Heljo', 30, 1, 1, 1)])
    result = processor(FakeTesseract(data), FakeVision('Hello')).extract_text(IMG, confidence_threshold=20)
    assert result['method'] == 'tesseract'


# ------------------------------------------------------------------ text layout

def test_text_is_rebuilt_in_lines_and_paragraphs():
    data = table([('Total', 90, 1, 1, 1), ('due:', 90, 1, 1, 1), ('$5', 90, 1, 1, 1),
                  ('Thank', 90, 1, 1, 2), ('you', 90, 1, 1, 2),
                  ('Footer', 90, 2, 1, 1)])
    result = processor(FakeTesseract(data)).extract_text(IMG, fallback_to_vision=False)
    assert result['text'] == 'Total due: $5\nThank you\n\nFooter'


def test_one_tesseract_pass_per_image():
    fake = FakeTesseract(table([('Hello', 90, 1, 1, 1)]))
    processor(fake).extract_text(IMG, fallback_to_vision=False)
    assert len(fake.calls) == 1


def test_version_is_a_string_so_the_result_can_be_sent_as_json():
    import json
    result = processor(FakeTesseract(table([('Hello', 90, 1, 1, 1)]))).extract_text(IMG, fallback_to_vision=False)
    json.dumps(result)                                         # used to raise: Version is not serialisable
    assert result['details']['tesseract_version'] == '5.5.4'


def test_word_boxes_are_given_in_original_image_pixels_after_enlargement():
    fake = FakeTesseract(table([('Hi', 90, 1, 1, 1), ('there', 90, 1, 1, 1)]))
    small = Image.new('RGB', (300, 100), 'white')              # enlarged 3x before recognition
    result = processor(fake).extract_text(small, fallback_to_vision=False)
    assert fake.calls[0]['size'] == (900, 300)
    boxes = [b['bbox'] for b in result['details']['bounding_boxes']]
    assert boxes[0] == {'x': 0, 'y': 7, 'width': 10, 'height': 4}
    assert boxes[1] == {'x': 3, 'y': 7, 'width': 10, 'height': 4}     # left 10 in the enlarged image


def test_large_images_are_not_enlarged():
    fake = FakeTesseract(table([('Hi', 90, 1, 1, 1)]))
    processor(fake).extract_text(Image.new('RGB', (1500, 500)), fallback_to_vision=False)
    assert fake.calls[0]['size'] == (1500, 500)


def test_timeout_is_passed_to_tesseract(monkeypatch):
    monkeypatch.setenv('TESSERACT_TIMEOUT', '7')
    fake = FakeTesseract(table([('Hi', 90, 1, 1, 1)]))
    processor(fake).extract_text(IMG, fallback_to_vision=False)
    assert fake.calls[0]['timeout'] == 7


# ------------------------------------------------------------------ languages

def test_language_that_is_not_installed_is_explained():
    result = processor(FakeTesseract(table([]))).extract_text(IMG, language='fra', fallback_to_vision=False)
    assert result['method'] == 'none'
    message = result['details']['tesseract_error']
    assert 'fra' in message and 'brew install tesseract-lang' in message and 'eng' in message


def test_missing_language_falls_back_to_vision_and_keeps_the_reason():
    result = processor(FakeTesseract(table([])), FakeVision('Bonjour')).extract_text(IMG, language='fra')
    assert result['method'] == 'vision' and 'fra' in result['details']['tesseract_error']


def test_combined_languages_are_checked_one_by_one():
    fake = FakeTesseract(table([('Hi', 90, 1, 1, 1)]), languages=('eng', 'fra', 'osd'))
    assert processor(fake).extract_text(IMG, language='eng+fra', fallback_to_vision=False)['method'] == 'tesseract'
    bad = processor(FakeTesseract(table([]))).extract_text(IMG, language='eng+deu', fallback_to_vision=False)
    assert 'deu' in bad['details']['tesseract_error']


@pytest.mark.parametrize('language', ['', 'eng;rm', '../x', 'eng fra', '--oem 0'])
def test_language_codes_are_validated(language):
    result = processor(FakeTesseract(table([]))).extract_text(IMG, language=language, fallback_to_vision=False)
    assert 'not a Tesseract language code' in result['details']['tesseract_error']


def test_tesseract_program_missing_has_an_install_hint():
    class TesseractNotFoundError(Exception):
        pass

    class Missing(FakeTesseract):
        def get_languages(self, config=''):
            raise TesseractNotFoundError('tesseract is not installed')
    result = processor(Missing()).extract_text(IMG, fallback_to_vision=False)
    assert 'brew install tesseract' in result['details']['tesseract_error']


def test_engine_failure_is_recorded_and_vision_takes_over():
    fake = FakeTesseract(error=RuntimeError('tesseract crashed\nwith a long\nmessage'))
    result = processor(fake, FakeVision('Rescued')).extract_text(IMG)
    assert result['method'] == 'vision' and result['text'] == 'Rescued'
    assert '\n' not in result['details']['tesseract_error']


def test_both_engines_failing_reports_both():
    fake = FakeTesseract(error=RuntimeError('tesseract crashed'))
    result = processor(fake, FakeVision(error=RuntimeError('vision down'))).extract_text(IMG)
    assert result['method'] == 'none'
    assert result['details']['tesseract_error'] and result['details']['vision_error'] == 'vision down'


def test_pytesseract_missing_is_reported_not_crashed(monkeypatch):
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == 'pytesseract':
            raise ImportError('no module')
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', fake_import)
    ocr = OCRProcessor(use_tesseract=True, vision_client=FakeVision('Via vision'))
    assert ocr.use_tesseract is False and 'pip install pytesseract' in ocr.tesseract_problem
    assert ocr.extract_text(IMG)['method'] == 'vision'
    alone = OCRProcessor(use_tesseract=True)
    assert 'pytesseract' in alone.extract_text(IMG)['details']['tesseract_error']


# ------------------------------------------------------------------ vision method

def test_vision_result_is_flagged_as_an_estimate():
    result = processor(vision=FakeVision('Hello')).extract_text(IMG, fallback_to_vision=True, confidence_threshold=101)
    assert result['method'] == 'vision' or result['method'] == 'tesseract'
    ocr = OCRProcessor(use_tesseract=False, vision_client=FakeVision('Hello'))
    vision = ocr.extract_text(IMG)
    assert vision['method'] == 'vision' and vision['confidence'] == 85.0
    assert vision['details']['confidence_estimated'] is True


@pytest.mark.parametrize('raw,clean', [
    ('Here is the extracted text:\n\nHello\nWorld', 'Hello\nWorld'),
    ('Sure, here is the text from the image:\nHello', 'Hello'),
    ('Here are the words:\n```\nHello\n```', '```\nHello\n```'.replace('```\n', '').replace('\n```', '')),
    ('```text\nHello\nWorld\n```', 'Hello\nWorld'),
    ('Here is nothing special', 'Here is nothing special'),
    ('The sign says: HELLO', 'The sign says: HELLO'),
    ('  \n Hello \n ', 'Hello'),
    ('', ''),
])
def test_vision_introductions_and_fences_are_removed(raw, clean):
    assert clean_vision_text(raw) == clean


def test_vision_prompt_names_the_language():
    vision = FakeVision('x')
    OCRProcessor(use_tesseract=False, vision_client=vision).extract_text(IMG, language='fra')
    assert 'French' in vision.prompts[0]


# ------------------------------------------------------------------ language detection

def test_detect_language_compares_installed_languages_and_notes_the_limit():
    fake = FakeTesseract(table([('Hello', 90, 1, 1, 1)]))
    result = processor(fake).detect_language(IMG)
    assert result['primary_language'] == 'eng' and result['method'] == 'tesseract'
    assert 'Only eng is installed' in result['note']
    assert result['script'] == 'Latin'


def test_detect_language_only_tries_common_installed_languages():
    fake = FakeTesseract(table([('Hello', 90, 1, 1, 1)]), languages=('eng', 'fra', 'tur', 'osd'))
    processor(fake).detect_language(IMG)
    assert sorted(c['lang'] for c in fake.calls) == ['eng', 'fra']


def test_detect_language_engine_failure_is_reported():
    result = processor(FakeTesseract(error=RuntimeError('boom\nbad'))).detect_language(IMG)
    assert result['error'] == 'Language detection failed: boom bad' and result['primary_language'] is None


def test_detect_language_with_no_text_and_no_vision_finds_nothing():
    result = processor(FakeTesseract(table([('', 95, 1, 1, 1)]))).detect_language(IMG)
    assert result['primary_language'] is None and result['method'] == 'none'


def test_detect_language_uses_vision_when_tesseract_finds_nothing():
    vision = FakeVision('French: 100%')
    result = processor(FakeTesseract(table([])), vision).detect_language(IMG)
    assert result['method'] == 'vision' and result['languages'][0]['description'] == 'French: 100%'


def test_script_that_installed_languages_cannot_read_is_flagged():
    class Han(FakeTesseract):
        def image_to_osd(self, image, output_type=None):
            return {'script': 'Han', 'script_conf': 9.0}
    result = processor(Han(table([('x', 20, 1, 1, 1)]))).detect_language(IMG)
    assert 'Han script' in result['script_note']


# ------------------------------------------------------------------ real Tesseract, end to end

@pytest.mark.skipif(shutil.which('tesseract') is None, reason='the tesseract program is not installed')
class TestRealTesseract:
    def test_reads_rendered_text_exactly(self):
        result = OCRProcessor(use_tesseract=True).extract_text(text_image(), fallback_to_vision=False)
        assert result['text'] == 'INVOICE 4821\nTotal due: $93.50'
        assert result['confidence'] > 85

    def test_a_blank_page_has_no_text_and_zero_confidence(self):
        result = OCRProcessor(use_tesseract=True).extract_text(Image.new('RGB', (800, 600), 'white'),
                                                                  fallback_to_vision=False)
        assert result['text'] == '' and result['confidence'] == 0.0

    def test_sideways_phone_photo_is_read_after_orientation_is_applied(self, tmp_path):
        from src.core.image_processor import ImageProcessor
        from tests.conftest import png_bytes
        sideways = text_image().rotate(90, expand=True)         # stored rotated, with an EXIF "rotate back" tag
        exif = Image.Exif()
        exif[0x0112] = 6
        data = png_bytes(sideways, 'JPEG', exif=exif)
        upright = ImageProcessor().open_bytes(data)
        result = OCRProcessor(use_tesseract=True).extract_text(upright, fallback_to_vision=False)
        assert 'INVOICE 4821' in result['text']

    def test_transparent_png_with_black_text_is_read(self):
        rgba = text_image().convert('RGBA')
        rgba.putalpha(Image.eval(rgba.convert('L'), lambda v: 255 - v))     # text opaque, background transparent
        out = OCRProcessor(use_tesseract=True).extract_text(rgba, fallback_to_vision=False)
        assert 'INVOICE' in out['text']

    def test_language_data_that_is_not_installed(self):
        result = OCRProcessor(use_tesseract=True).extract_text(text_image(), language='xyz', fallback_to_vision=False)
        assert 'no language data' in result['details']['tesseract_error']
