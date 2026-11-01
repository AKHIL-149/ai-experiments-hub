"""Shared fixtures. Nothing here touches the real data/ directory or the network."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

# server.py reads its configuration when it is imported, so the environment has to be
# set before any test imports it: everything goes to a scratch directory.
_SCRATCH = tempfile.mkdtemp(prefix="meeting-summarizer-tests-")
os.environ.update({
    "DATA_DIR": _SCRATCH,
    "UPLOAD_DIR": f"{_SCRATCH}/uploads",
    "OUTPUT_DIR": f"{_SCRATCH}/output",
    "CACHE_DIR": f"{_SCRATCH}/cache",
    "TEMP_DIR": f"{_SCRATCH}/temp",
    "PROGRESS_DIR": f"{_SCRATCH}/progress",
    "DATABASE_URL": f"sqlite:///{_SCRATCH}/test.db",
    "TRANSCRIPTION_BACKEND": "whisper-cpp",
    "LLM_PROVIDER": "ollama",
    "MAX_AUDIO_SIZE_MB": "5",
    "ALLOWED_ORIGINS": "http://localhost:8000,http://127.0.0.1:8000",
})
os.environ.pop("HF_AUTH_TOKEN", None)


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_SCRATCH, ignore_errors=True)




@pytest.fixture
def scratch():
    return Path(_SCRATCH)


@pytest.fixture
def tone_wav(tmp_path):
    """A 3 second loud tone: not silence, so it reaches the transcriber"""
    from pydub.generators import Sine
    path = tmp_path / "tone.wav"
    Sine(440).to_audio_segment(duration=3000, volume=-6).export(path, format="wav")
    return path


@pytest.fixture
def silent_wav(tmp_path):
    from pydub import AudioSegment
    path = tmp_path / "silence.wav"
    AudioSegment.silent(duration=3000).export(path, format="wav")
    return path
