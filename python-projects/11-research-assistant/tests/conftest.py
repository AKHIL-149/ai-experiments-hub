"""
Pytest-wide fixtures.

Critical: tests/test_phase4.py and tests/test_phase5.py do
    from server import app, db_manager
at module level - importing the REAL production db_manager singleton
directly (server.py: DatabaseManager(os.getenv('DATABASE_URL', 'sqlite:///./data/database.db')),
and .env sets DATABASE_URL to that exact same path). Both files then
build TestClient(app) and hit the real server routes through it, so
every user/query/source these tests create lands in the real,
live database - not an isolated one. test_phase4.py's autouse
cleanup_database fixture goes further and actively deletes rows
(db_session.query(User).filter(User.username.in_(test_usernames)).delete(...))
from that same real database before each session. This is the exact
same "tests destroy live data" vulnerability found and fixed in
projects 12 and 13's conftest.py - fixing it here before ever running
this project's test suite, rather than discovering it the hard way
after live-testing data already exists.

Fix: patch DatabaseManager.__init__ itself, process-wide, for the whole
test session, so any database_url that resolves to the real app
database - whether via the string default or via the explicit
DATABASE_URL env value (same string either way here) - redirects to an
isolated temp-file database instead. A genuinely different explicit URL
(e.g. a test file's own sqlite:///:memory:) is left untouched. Done at
conftest.py's own module level (not inside a fixture) so the patch is
live before `server` can be imported for the first time by anything,
including a module-level import during collection.
"""
import os
import tempfile

from src.core.database import DatabaseManager

# Matches .env's DATABASE_URL and DatabaseManager's own string default
# (src/core/database.py). Any call that resolves to this - whether by
# omitting database_url or by passing it explicitly, e.g. via
# os.getenv('DATABASE_URL', ...) in server.py - is redirected to the
# isolated test database.
_REAL_APP_DB_URL = 'sqlite:///./data/database.db'

_fd, _test_db_path = tempfile.mkstemp(suffix='.db', prefix='pytest_')
os.close(_fd)
_test_db_url = f'sqlite:///{_test_db_path}'
_real_env_db_url = os.getenv('DATABASE_URL')

_real_init = DatabaseManager.__init__


def _patched_init(self, database_url=_REAL_APP_DB_URL, echo=False):
    if not database_url or database_url == _REAL_APP_DB_URL or database_url == _real_env_db_url:
        database_url = _test_db_url
    _real_init(self, database_url, echo)


DatabaseManager.__init__ = _patched_init

# server.py only creates tables inside a FastAPI startup event
# (db_manager.create_tables()), which never fires for a bare
# TestClient(app) - test_phase4.py/test_phase5.py both do exactly that
# (no `with` context manager), so the isolated DB above would otherwise
# have no schema at all and every query fails with
# "sqlalchemy.exc.OperationalError: no such table". Create the schema
# here instead, once, before any test runs. DatabaseManager(_test_db_url)
# goes through the patch above like any other call, but _test_db_url
# already matches its own redirect target, so it's a no-op passthrough.
DatabaseManager(_test_db_url).create_tables()


def pytest_sessionfinish(session, exitstatus):
    DatabaseManager.__init__ = _real_init
    try:
        os.remove(_test_db_path)
    except OSError:
        pass
