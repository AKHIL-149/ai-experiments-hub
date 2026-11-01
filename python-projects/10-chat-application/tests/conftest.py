"""Shared setup: the app is imported against a scratch database, never data/database.db."""

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_SCRATCH = tempfile.mkdtemp(prefix="chat-app-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_SCRATCH}/test.db"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_SCRATCH, ignore_errors=True)
