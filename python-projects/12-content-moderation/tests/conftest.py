"""
Pytest-wide fixtures.

Critical: DatabaseManager() with no explicit db_url defaults to the real
application database (./data/database.db - see DatabaseManager.__init__
in src/core/database.py). That's not just a risk in a test file's own
fixture - it's called with no args in several places across the app
(queue_manager, image/video/text workers, analytics_service, admin_service
as a fallback), none of them dependency-injected in a test-safe way.
server.py's own module-level singleton also resolves to this same file:
    db_manager = DatabaseManager(os.getenv('DATABASE_URL'))
and .env sets DATABASE_URL=sqlite:///./data/database.db explicitly, so
`from server import app` in a test (e.g. tests/test_admin_endpoints.py)
builds that singleton against the real DB at import time - before any
fixture body runs. Any test that goes through server.py's actual routes
via TestClient(app), not just a test file with an obviously-unsafe
fixture, would read and write the real live database - the one holding
real users/content submitted during manual browser testing.

Fix: patch DatabaseManager.__init__ itself, process-wide, for the whole
test session, so any db_url that resolves to the real app database -
whether via the no-arg default or via the explicit DATABASE_URL value -
redirects to an isolated temp-file database instead. A genuinely
different explicit URL (e.g. a test file's own sqlite:///:memory:
fixture) is left untouched, since that's deliberate test-local isolation,
not a leak. Done at conftest.py's own module level (not inside a
fixture) so the patch is live before `server` can be imported for the
first time by anything, including a module-level import during
collection.

Second: RateLimitMiddleware is real and Redis-backed, not mocked out
anywhere, and /api/auth/register + /api/auth/guest each allow 5 requests
per 5 minutes, /api/auth/login allows 5 per minute - keyed by client IP.
Starlette's TestClient always presents the same fake client host, so
every test file's register/login/guest calls in a single `pytest tests/`
run share ONE budget in real Redis. This is the exact same failure mode
already hit and fixed in project 13's conftest.py - patching proactively
here rather than waiting to rediscover it the same way.

Fix: patch RateLimitMiddleware.dispatch (the HTTP-level enforcement
point) to a no-op passthrough, for the whole test session. Deliberately
NOT patching RateLimiter.is_allowed itself, so any future test that
wants to exercise the actual rate-limiting logic can still do so
directly against RateLimiter - only requests made through
TestClient(app) skip enforcement.
"""
import os
import tempfile

from src.core.database import DatabaseManager
from src.middleware.rate_limiter import RateLimitMiddleware

# Matches .env's DATABASE_URL and DatabaseManager's own no-arg default
# (src/core/database.py). Any call that resolves to this - whether by
# omitting db_url or by passing it explicitly, e.g. via
# os.getenv('DATABASE_URL') in server.py - is redirected to the test DB.
_REAL_APP_DB_URL = 'sqlite:///./data/database.db'

_fd, _test_db_path = tempfile.mkstemp(suffix='.db', prefix='pytest_')
os.close(_fd)
_test_db_url = f'sqlite:///{_test_db_path}'
_real_env_db_url = os.getenv('DATABASE_URL')

_real_init = DatabaseManager.__init__


def _patched_init(self, database_url=None):
    if not database_url or database_url == _REAL_APP_DB_URL or database_url == _real_env_db_url:
        database_url = _test_db_url
    _real_init(self, database_url)


DatabaseManager.__init__ = _patched_init

_real_dispatch = RateLimitMiddleware.dispatch


async def _passthrough_dispatch(self, request, call_next):
    return await call_next(request)


RateLimitMiddleware.dispatch = _passthrough_dispatch


def pytest_sessionfinish(session, exitstatus):
    DatabaseManager.__init__ = _real_init
    RateLimitMiddleware.dispatch = _real_dispatch
    try:
        os.remove(_test_db_path)
    except OSError:
        pass
