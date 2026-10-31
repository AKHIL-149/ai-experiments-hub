"""Opening, normalising and encoding images safely."""
import io

import pytest
import requests
from PIL import Image

from src.core.image_processor import ImageError, ImageProcessor
from tests.conftest import png_bytes, text_image

proc = ImageProcessor()


def jpeg_with_orientation(orientation: int) -> bytes:
    image = Image.new('RGB', (40, 20), 'white')            # wide image
    exif = Image.Exif()
    exif[0x0112] = orientation
    return png_bytes(image, 'JPEG', exif=exif)


# ------------------------------------------------------------------ open_bytes: refusing bad input

def test_empty_file():
    with pytest.raises(ImageError, match='empty'):
        proc.open_bytes(b'')


def test_not_an_image():
    with pytest.raises(ImageError, match='not an image'):
        proc.open_bytes(b'hello, this is text')


def test_truncated_file_fails_at_open_not_later():
    data = png_bytes(text_image(), 'JPEG')
    with pytest.raises(ImageError, match='damaged or cut off'):
        proc.open_bytes(data[:2000])


def test_too_many_bytes():
    data = png_bytes(text_image())
    with pytest.raises(ImageError, match='limit is 0 MB|limit is'):
        proc.open_bytes(data, max_bytes=100)


def test_upload_limit_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv('MAX_UPLOAD_MB', '0.0001')
    with pytest.raises(ImageError, match='MB'):
        proc.open_bytes(png_bytes(text_image()))


def test_too_many_pixels_is_refused_before_decoding(monkeypatch):
    monkeypatch.setenv('MAX_IMAGE_PIXELS', '1000')
    with pytest.raises(ImageError, match='megapixels'):
        proc.open_bytes(png_bytes(Image.new('RGB', (100, 100))))


def test_decompression_bomb_is_refused():
    # 1-bit PNG, 20000x20000: a few KB on disk, 400 million pixels
    bomb = png_bytes(Image.new('1', (20000, 20000), 1), optimize=True)
    with pytest.raises(ImageError, match='pixels'):
        proc.open_bytes(bomb)


# ------------------------------------------------------------------ open_bytes + normalize

@pytest.mark.parametrize('fmt', ['PNG', 'JPEG', 'WEBP', 'BMP', 'TIFF', 'GIF'])
def test_common_formats_open_and_keep_their_format_name(fmt):
    image = proc.open_bytes(png_bytes(text_image(size=(60, 30)), fmt))
    assert image.format == fmt
    assert image.size == (60, 30)


def test_exif_orientation_is_applied():
    upright = proc.open_bytes(jpeg_with_orientation(6))          # 6 = rotate 90 clockwise to view
    assert upright.size == (20, 40)
    assert proc.open_bytes(jpeg_with_orientation(1)).size == (40, 20)


def test_transparency_is_composited_on_white_not_black():
    rgba = Image.new('RGBA', (10, 10), (0, 0, 0, 0))            # fully transparent
    out = proc.open_bytes(png_bytes(rgba))
    assert out.mode == 'RGB' and out.getpixel((5, 5)) == (255, 255, 255)


def test_palette_image_with_transparency():
    p = Image.new('P', (10, 10), 0)
    p.putpalette([0, 0, 0] * 256)
    out = proc.open_bytes(png_bytes(p, transparency=0))
    assert out.mode == 'RGB' and out.getpixel((1, 1)) == (255, 255, 255)


@pytest.mark.parametrize('mode,color', [('P', 3), ('1', 1), ('CMYK', (0, 0, 0, 0)), ('L', 100), ('LA', (100, 255))])
def test_other_colour_modes_become_rgb_or_gray(mode, color):
    image = Image.new(mode, (8, 8), color)
    out = proc.normalize(image)
    assert out.mode in ('RGB', 'L')


def test_sixteen_bit_image_is_scaled_to_eight_bit():
    image = Image.new('I;16', (8, 8), 30000)
    out = proc.normalize(image)
    assert out.mode == 'L' and out.getpixel((0, 0)) == 117      # 30000 / 256


def test_animated_gif_uses_the_first_frame():
    frames = [Image.new('RGB', (10, 10), c) for c in ('red', 'green', 'blue')]
    buffer = io.BytesIO()
    frames[0].save(buffer, format='GIF', save_all=True, append_images=frames[1:], loop=0)
    out = proc.open_bytes(buffer.getvalue())
    assert out.getpixel((0, 0))[0] > 200 and out.getpixel((0, 0))[1] < 50      # red


def test_mpo_phone_jpeg_is_a_supported_format():
    buffer = io.BytesIO()
    a, b = Image.new('RGB', (20, 20), 'red'), Image.new('RGB', (20, 20), 'blue')
    a.save(buffer, format='MPO', save_all=True, append_images=[b])
    image = proc.open_bytes(buffer.getvalue())
    assert image.format == 'MPO'
    assert proc.validate_image(image)['valid']


# ------------------------------------------------------------------ validate / metadata

def test_validate_rejects_unknown_format():
    image = Image.new('RGB', (5, 5))
    image.format = 'ICO'
    result = proc.validate_image(image)
    assert not result['valid'] and 'Unsupported format: ICO' in result['errors'][0]


def test_validate_does_not_re_encode_to_measure_size():
    image = proc.open_bytes(png_bytes(text_image()))
    assert proc.validate_image(image, 1234)['size_bytes'] == 1234
    assert proc.validate_image(image)['size_bytes'] == image.source_bytes


def test_metadata_reports_the_original_file_size():
    data = png_bytes(text_image(), 'JPEG')
    image = proc.open_bytes(data)
    meta = proc.extract_metadata(image)
    assert meta['size_bytes'] == len(data) and meta['dimensions'] == '900x300' and meta['format'] == 'JPEG'


# ------------------------------------------------------------------ loading from paths and URLs

def test_load_from_path(tmp_path):
    path = tmp_path / 'a.png'
    path.write_bytes(png_bytes(text_image()))
    assert proc.load_image(str(path)).size == (900, 300)


def test_load_missing_path_and_directory(tmp_path):
    with pytest.raises(ValueError, match='not found'):
        proc.load_image(str(tmp_path / 'nope.png'))
    with pytest.raises(ValueError, match='not a file'):
        proc.load_image(str(tmp_path))


def test_load_from_bytes():
    assert proc.load_image(png_bytes(text_image())).size == (900, 300)


class FakeResponse:
    def __init__(self, body: bytes, status: int = 200):
        self.body, self.status = body, status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            raise requests.HTTPError(f"{self.status} error")

    def iter_content(self, chunk_size=1):
        for i in range(0, len(self.body), chunk_size):
            yield self.body[i:i + chunk_size]


def test_download_from_url(monkeypatch):
    body = png_bytes(text_image())
    monkeypatch.setattr(requests, 'get', lambda *a, **k: FakeResponse(body))
    assert proc.load_image('https://example.com/a.png').size == (900, 300)


def test_download_is_limited_while_streaming(monkeypatch):
    monkeypatch.setenv('MAX_UPLOAD_MB', '0.001')
    monkeypatch.setattr(requests, 'get', lambda *a, **k: FakeResponse(b'x' * 100_000))
    with pytest.raises(ValueError, match='larger than'):
        proc.load_image('https://example.com/big.png')


def test_download_http_error(monkeypatch):
    monkeypatch.setattr(requests, 'get', lambda *a, **k: FakeResponse(b'', 404))
    with pytest.raises(ValueError, match='Failed to download'):
        proc.load_image('https://example.com/missing.png')


# ------------------------------------------------------------------ encoding for a model

def test_small_images_are_sent_as_lossless_png_and_the_media_type_matches():
    data, media_type = proc.encode_for_model(text_image(size=(300, 100)))
    assert media_type == 'image/png' and data[:8] == b'\x89PNG\r\n\x1a\n'


def test_large_images_are_sent_as_jpeg_and_the_media_type_matches():
    data, media_type = proc.encode_for_model(Image.new('RGB', (1800, 1200), 'white'))
    assert media_type == 'image/jpeg' and data[:3] == b'\xff\xd8\xff'


def test_images_are_scaled_down_to_the_maximum_dimension(monkeypatch):
    monkeypatch.setenv('MAX_IMAGE_DIMENSION', '500')
    data, _ = proc.encode_for_model(Image.new('RGB', (2000, 1000), 'white'))
    assert Image.open(io.BytesIO(data)).size == (500, 250)


def test_default_maximum_dimension_is_2048():
    data, _ = proc.encode_for_model(Image.new('RGB', (6000, 3000), 'white'))
    assert Image.open(io.BytesIO(data)).size == (2048, 1024)


def test_encoded_size_limit_is_respected():
    import random
    rnd = random.Random(1)
    noisy = Image.frombytes('RGB', (1500, 1000), bytes(rnd.getrandbits(8) for _ in range(1500 * 1000 * 3)))
    data, media_type = proc.encode_for_model(noisy, max_encoded_mb=0.3)
    assert media_type == 'image/jpeg' and len(data) <= 0.3 * 1024 * 1024


def test_images_with_transparency_are_encoded_without_alpha():
    data, _ = proc.encode_for_model(Image.new('RGBA', (50, 50), (255, 0, 0, 0)))
    assert Image.open(io.BytesIO(data)).mode in ('RGB', 'L')


def test_to_base64_handles_modes_jpeg_cannot_store():
    assert proc.to_base64(Image.new('RGBA', (5, 5)), 'JPEG')
    assert proc.to_base64(Image.new('P', (5, 5)), 'JPEG')


def test_resize_if_needed_keeps_aspect_ratio_and_never_returns_zero():
    out = proc.resize_if_needed(Image.new('RGB', (10000, 10)), 100)
    assert out.size == (100, 1)
    small = Image.new('RGB', (50, 50))
    assert proc.resize_if_needed(small, 100) is small


def test_a_tall_image_is_scaled_by_its_longer_side(monkeypatch):
    monkeypatch.setenv('MAX_IMAGE_DIMENSION', '500')
    data, _ = proc.encode_for_model(Image.new('RGB', (1000, 3000), 'white'))
    assert Image.open(io.BytesIO(data)).size == (166, 500)


def test_an_animation_that_was_already_advanced_is_rewound_to_the_first_frame():
    frames = [Image.new('RGB', (10, 10), c) for c in ('red', 'green', 'blue')]
    buffer = io.BytesIO()
    frames[0].save(buffer, format='GIF', save_all=True, append_images=frames[1:], loop=0)
    gif = Image.open(io.BytesIO(buffer.getvalue()))
    gif.seek(2)
    out = proc.normalize(gif)
    assert out.getpixel((0, 0))[0] > 200
