"""
Tests run in single-user mode (REQUIRE_LOGIN=false) unless a test file says otherwise with
`pytestmark = pytest.mark.accounts`: most tests are about videos, not about signing in, and the sign-in
gate is covered by tests/api/test_accounts.py.
"""

import pytest

from src.core.config import settings


def pytest_configure(config):
    config.addinivalue_line("markers", "accounts: run with sign-in required (the real default)")


@pytest.fixture(autouse=True)
def _single_user_mode(request, monkeypatch):
    if request.node.get_closest_marker("accounts"):
        monkeypatch.setattr(settings, "require_login", True)
    else:
        monkeypatch.setattr(settings, "require_login", False)
