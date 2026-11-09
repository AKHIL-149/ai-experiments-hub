"""
Frame captions (src/services/image_captioning.py).

Found on real videos: the pipeline ignored VISION_PROVIDER/VISION_MODEL and
always used BLIP-base, which captioned a slide titled "HOW DATA BECOMES
EVIDENCE" as "how to use a data flow chart in java" (that went into the
summary) and a "TRACEABILITY" slide as "traceability for react react react ..."
with the word repeated 100+ times.
"""

import json
from pathlib import Path

import pytest

from src.services import image_captioning as ic
from src.services.image_captioning import ImageCaptioningService, clean_caption


class TestCleanCaption:
    def test_a_looping_word_is_cut(self):
        assert clean_caption("traceability for " + "react " * 100) == "traceability for react"

    def test_two_in_a_row_is_normal_english(self):
        assert clean_caption("It was very very good") == "It was very very good"

    def test_loop_in_the_middle_keeps_the_start(self):
        assert clean_caption("a slide " + "the " * 20 + "about data") == "a slide the"

    def test_whitespace_and_quotes(self):
        assert clean_caption('  "A woman   talking.\nSecond line."  ') == "A woman talking. Second line."

    def test_long_text_is_cut_at_a_sentence(self):
        out = clean_caption("This is a sentence. " * 40, max_chars=100)
        assert len(out) <= 100 and out.endswith(".")

    def test_long_text_without_sentences_is_cut_at_a_word(self):
        out = clean_caption(" ".join(f"w{i}" for i in range(200)), max_chars=100)
        assert out.endswith("…") and len(out) <= 101 and not out[:-1].endswith("w")

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_nothing(self, value):
        assert clean_caption(value) == ""


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


@pytest.fixture
def image(tmp_path):
    path = tmp_path / "frame.jpg"
    path.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")
    return path


def fake_ollama(monkeypatch, installed, answer="A slide titled X.", calls=None):
    def urlopen(request, timeout=None):
        url = request if isinstance(request, str) else request.full_url
        if calls is not None:
            calls.append(url)
        if url.endswith("/api/tags"):
            return FakeResponse({"models": [{"name": n} for n in installed]})
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse({"message": {"content": answer}})
    monkeypatch.setattr(ic.urllib.request, "urlopen", urlopen)


class TestOllamaProvider:
    def test_the_configured_model_is_used(self, monkeypatch, image):
        calls = []
        fake_ollama(monkeypatch, ["llava:latest", "qwen3-vl:8b"], "A slide titled X.", calls)
        service = ImageCaptioningService(use_local=True, provider="ollama", ollama_model="qwen3-vl:8b")
        caption = service.caption_image(image)
        assert caption.text == "A slide titled X." and caption.model == "ollama:qwen3-vl:8b"
        assert calls == ["http://localhost:11434/api/tags", "http://localhost:11434/api/chat"]

    def test_the_request_sends_the_image_and_a_budget_big_enough_for_thinking_models(self, monkeypatch, image):
        sent = {}

        def urlopen(request, timeout=None):
            if isinstance(request, str):          # the /api/tags check
                return FakeResponse({"models": [{"name": "llava:latest"}]})
            sent.update(json.loads(request.data))
            return FakeResponse({"message": {"content": "ok then"}})
        monkeypatch.setattr(ic.urllib.request, "urlopen", urlopen)
        ImageCaptioningService(provider="ollama", ollama_model="llava").caption_image(image)
        assert sent["model"] == "llava:latest" and sent["stream"] is False
        assert sent["messages"][0]["images"] and sent["options"]["temperature"] == 0
        assert sent["options"]["num_predict"] >= 1000

    def test_model_name_without_tag_matches_latest(self, monkeypatch):
        fake_ollama(monkeypatch, ["llava:latest"])
        service = ImageCaptioningService(provider="ollama", ollama_model="llava")
        assert service._resolve_ollama() and service.ollama_model == "llava:latest"

    def test_missing_model_falls_back_to_an_installed_vision_model(self, monkeypatch):
        fake_ollama(monkeypatch, ["llama3.2:3b", "nomic-embed-text:latest", "llava:latest"])
        service = ImageCaptioningService(provider="ollama", ollama_model="does-not-exist")
        assert service._resolve_ollama() and service.ollama_model == "llava:latest"

    def test_no_vision_model_installed_means_blip(self, monkeypatch):
        fake_ollama(monkeypatch, ["llama3.2:3b", "nomic-embed-text:latest"])
        service = ImageCaptioningService(provider="ollama", ollama_model="llava")
        assert service._resolve_ollama() is False

    def test_unreachable_ollama_means_blip(self, monkeypatch):
        def refuse(*a, **k):
            raise OSError("connection refused")
        monkeypatch.setattr(ic.urllib.request, "urlopen", refuse)
        assert ImageCaptioningService(provider="ollama", ollama_model="llava")._resolve_ollama() is False

    def test_availability_is_checked_once(self, monkeypatch, image):
        calls = []
        fake_ollama(monkeypatch, ["llava:latest"], "fine thanks", calls)
        service = ImageCaptioningService(provider="ollama", ollama_model="llava")
        service.caption_image(image)
        service.caption_image(image)
        assert sum(c.endswith("/api/tags") for c in calls) == 1

    def test_a_failing_frame_falls_back_to_blip_for_that_frame(self, monkeypatch, image):
        fake_ollama(monkeypatch, ["llava:latest"], RuntimeError("model crashed"))
        service = ImageCaptioningService(use_local=True, provider="ollama", ollama_model="llava")
        monkeypatch.setattr(service, "_caption_local", lambda path, prompt: ic.ImageCaption(text="blip text", model="blip-base"))
        assert service.caption_image(image).model == "blip-base"

    def test_an_empty_answer_is_a_failure_not_an_empty_caption(self, monkeypatch, image):
        fake_ollama(monkeypatch, ["llava:latest"], "   ")
        service = ImageCaptioningService(use_local=True, provider="ollama", ollama_model="llava")
        monkeypatch.setattr(service, "_caption_local", lambda path, prompt: ic.ImageCaption(text="blip text", model="blip-base"))
        assert service.caption_image(image).text == "blip text"

    def test_a_looping_answer_is_cleaned(self, monkeypatch, image):
        fake_ollama(monkeypatch, ["llava:latest"], "A slide " + "data " * 50)
        assert ImageCaptioningService(provider="ollama", ollama_model="llava").caption_image(image).text == "A slide data"

    def test_other_providers_never_call_ollama(self, monkeypatch, image):
        calls = []
        fake_ollama(monkeypatch, ["llava:latest"], calls=calls)
        service = ImageCaptioningService(use_local=True, provider=None)
        monkeypatch.setattr(service, "_caption_local", lambda path, prompt: ic.ImageCaption(text="blip", model="blip-base"))
        assert service.caption_image(image).model == "blip-base" and calls == []

    def test_from_settings_reads_the_vision_settings(self, monkeypatch):
        from src.core.config import settings
        monkeypatch.setattr(settings, "vision_provider", " Ollama ")
        monkeypatch.setattr(settings, "vision_model", "qwen3-vl:8b")
        service = ImageCaptioningService.from_settings()
        assert service.provider == "ollama" and service.ollama_model == "qwen3-vl:8b"


def test_the_pipeline_uses_the_configured_captioner():
    source = (Path(__file__).resolve().parents[1] / "src" / "api" / "videos.py").read_text()
    assert "ImageCaptioningService.from_settings()" in source
    assert "ImageCaptioningService(use_local=True)" not in source
