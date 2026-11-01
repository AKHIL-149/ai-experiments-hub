"""Helpers shared by the tests (importable: from tests.helpers import ...)"""

import shutil

import pytest

HAVE_FFMPEG = shutil.which("ffmpeg") is not None
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg is not installed")


class FakeLLM:
    """Stands in for LLMClient: replies from a script, records every call"""

    backend = "fake"
    model = "fake-model"

    def __init__(self, replies=None, default="OK", truncated=False):
        self.replies = list(replies or [])
        self.default = default
        self.truncated = truncated
        self.calls = []

    def generate(self, prompt, max_tokens=2000, temperature=0.7, system_prompt=None, json_mode=False):
        self.calls.append({
            "prompt": prompt, "max_tokens": max_tokens, "temperature": temperature,
            "system_prompt": system_prompt, "json_mode": json_mode,
        })
        text = self.replies.pop(0) if self.replies else self.default
        return {"text": text, "tokens": {"prompt": 10, "completion": 5, "total": 15}, "truncated": self.truncated}

    def estimate_cost(self, tokens, backend=None):
        return 0.0
