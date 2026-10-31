"""Shared helpers: a project-root import path, image builders and a quiet environment."""
import io
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    """No test may reach a real model, a real key, or the project's real cache."""
    for name in ('ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'MAX_UPLOAD_MB', 'MAX_IMAGE_PIXELS', 'MAX_IMAGE_DIMENSION',
                 'MAX_IMAGE_SIZE_MB', 'MAX_BATCH_FILES', 'CORS_ORIGINS', 'DEBUG', 'ANTHROPIC_MODEL', 'OPENAI_MODEL',
                 'DEFAULT_PROVIDER', 'TESSERACT_TIMEOUT'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('OLLAMA_API_URL', 'http://127.0.0.1:9')       # closed port
    monkeypatch.setenv('OLLAMA_VISION_MODEL', 'llava')


def png_bytes(image: Image.Image, fmt: str = 'PNG', **kwargs) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **kwargs)
    return buffer.getvalue()


def text_image(text: str = 'INVOICE 4821\nTotal due: $93.50', size=(900, 300)) -> Image.Image:
    image = Image.new('RGB', size, 'white')
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype('/System/Library/Fonts/Helvetica.ttc', 56)
    except OSError:
        try:
            font = ImageFont.truetype('DejaVuSans.ttf', 56)
        except OSError:
            font = ImageFont.load_default()
    draw.text((30, 40), text, fill='black', font=font)
    return image
