"""Start-up behaviour of server.py, run in a fresh interpreter (it happens at import / `python server.py`)."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def python(code, env=None, tmp=None):
    full_env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp}/start.db", "PYTHONPATH": str(ROOT)}
    full_env.pop("HOST", None)
    full_env.update(env or {})
    # The developer's own .env (HOST=0.0.0.0 ...) must not decide what these tests see
    code = "import dotenv; dotenv.load_dotenv = lambda *a, **k: False\n" + code
    done = subprocess.run([sys.executable, "-W", "ignore", "-c", code], cwd=ROOT, env=full_env,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    lines = done.stdout.strip().splitlines()
    return lines[-1] if lines else ""


def test_expired_sessions_are_deleted_when_the_server_starts():
    with tempfile.TemporaryDirectory() as tmp:
        seed = """
from datetime import datetime, timedelta
from src.core.database import DatabaseManager, Session, User
m = DatabaseManager(None)
with m.get_session() as db:
    u = User(username='seed-user', email='seed@example.com', password_hash='x'); db.add(u); db.commit()
    db.add_all([Session(id='old', user_id=u.id, expires_at=datetime.utcnow() - timedelta(days=2)),
                Session(id='new', user_id=u.id, expires_at=datetime.utcnow() + timedelta(days=2))]); db.commit()
"""
        python(seed.replace("DatabaseManager(None)", "DatabaseManager('sqlite:///%s/start.db')" % tmp), tmp=tmp)
        left = python("""
import server
from src.core.database import Session
with server.db_manager.get_session() as db:
    print(sorted(s.id for s in db.query(Session).all()))
""", tmp=tmp)
        assert left == "['new']"


def serve_args(env=None):
    with tempfile.TemporaryDirectory() as tmp:
        return python("""
import runpy, uvicorn
calls = []
uvicorn.run = lambda app, **kw: calls.append(kw)
runpy.run_path('server.py', run_name='__main__')
print(calls[0])
""", env=env, tmp=tmp)


def test_the_server_listens_on_loopback_by_default():
    assert serve_args() == "{'host': '127.0.0.1', 'port': 8000}"


def test_host_and_port_from_the_environment_are_used():
    assert serve_args({"HOST": "0.0.0.0", "PORT": "9100"}) == "{'host': '0.0.0.0', 'port': 9100}"
