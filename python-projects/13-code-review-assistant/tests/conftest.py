"""
Pytest-wide fixtures.

Critical: DatabaseManager() with no explicit db_url defaults to the real
application database (./data/database.db - see DatabaseManager.__init__
in src/core/database.py). That's not just a test file's own fixture - it's
called with no args in 70+ places across the app (every service module,
every worker, server.py itself), none of them dependency-injected. Any
test that exercises a service through its normal code path - not just a
test file with an obviously-unsafe fixture - ends up reading and writing
the real live database.

Confirmed live: tests/test_rule_marketplace.py's fixture created a
DatabaseManager() with no URL and, on teardown, ran
db.query(User).delete() - which cascades via foreign keys to
Repository/CodeFile/Issue. Running that one test file wiped a real user
account and every repository/issue built up during a full day of manual
testing against the running app.

Fix: patch DatabaseManager itself, process-wide, for the whole test
session, so a no-arg DatabaseManager() resolves to an isolated database
instead of the real one - this covers every call site, including ones
buried inside application services that test files never construct
directly. Uses a temp file rather than sqlite:///:memory: because each
:memory: connection is its own private database; a temp file lets the
many separate DatabaseManager() instances created across a single test
(one in the test's own fixture, others created internally by whatever
service the test exercises) actually see the same data.

Second layer, found while verifying the first fix: server.py has its own
module-level singleton -
    db_url = os.getenv('DATABASE_URL')
    db_manager = DatabaseManager(db_url)
- built at import time (i.e. whenever a test does `from server import
app`). .env sets DATABASE_URL=sqlite:///./data/database.db explicitly,
so this call passes a truthy, real value - `db_url or test_db_url`
never fires, and every route handler using this singleton (most of
them, via `with db_manager.get_session() as db:`) kept writing to the
real database even with the patch above in place. Confirmed live: two
leaked rows (`testuser`, `admin_integration`) survived a full run of
the previously-destructive test files even after the first fix.

Fix: redirect any db_url that resolves to the real app database -
whether via the no-arg default or via an explicit value that equals
the real path - to the isolated test database. A genuinely different
explicit URL (e.g. a test file's own sqlite:///:memory:) is left
untouched, since that's deliberate test-local isolation, not a leak.

Third layer, found running the FULL suite (`pytest tests/`) after the
first two fixes verified clean on the 4 originally-destructive files in
isolation: 3 more rows leaked (`discord_test_user`, `email_test_user`,
`testuser`). Root cause: tests/test_pr_diff_endpoint.py and
tests/test_pr_ui_routes.py do `from server import app` at MODULE level
(column 0), not inside a fixture function. Module-level imports execute
during pytest's *collection* phase, which runs before ANY fixture -
including a session-scoped autouse one. Since Python caches `server` in
sys.modules after its first import, whichever of these two files pytest
collects first constructs server.py's module-level `db_manager`
singleton against the real, unpatched DatabaseManager - before the
fixture below ever gets a chance to run. Every other test file's later
`from server import app` (even ones done lazily inside a fixture body)
just gets the same already-broken cached module back.

Fix: do the monkeypatch at conftest.py's own module level instead of
inside a fixture body. pytest always imports every conftest.py before
collecting any test file, so this guarantees the patch is live before
`server` (or any service module) can be imported for the first time by
anything, module-level import included. Cleanup moves to the
pytest_sessionfinish hook, since there's no fixture teardown to rely on.
"""
import os
import tempfile

from src.core.database import DatabaseManager

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


def _patched_init(self, db_url=None):
    if not db_url or db_url == _REAL_APP_DB_URL or db_url == _real_env_db_url:
        db_url = _test_db_url
    _real_init(self, db_url)


DatabaseManager.__init__ = _patched_init


def pytest_sessionfinish(session, exitstatus):
    DatabaseManager.__init__ = _real_init
    try:
        os.remove(_test_db_path)
    except OSError:
        pass
