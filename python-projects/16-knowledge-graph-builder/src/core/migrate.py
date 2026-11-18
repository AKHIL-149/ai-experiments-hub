"""Bring the database up to the current schema with Alembic (and adopt a database made before migrations existed)"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

ROOT = Path(__file__).resolve().parent.parent.parent
BASELINE = "0001"   # the schema of steps 1-3, which was created by create_all with no migrations
ACCOUNTS = "0002"
JOBS = "0003"
CONFLICTS = "0004"


def _config(url: str) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def upgrade_to_head(engine) -> None:
    """Create or upgrade every table. A database with tables but no migration history is stamped first, at the newest
    revision whose table it already has (`jobs`, then `users`, else the step 1-3 schema), and then upgraded."""
    url = engine.url.render_as_string(hide_password=False)
    tables = set(inspect(engine).get_table_names())
    cfg = _config(url)
    if tables and "alembic_version" not in tables:
        command.stamp(cfg, CONFLICTS if "conflicts" in tables else JOBS if "jobs" in tables else ACCOUNTS if "users" in tables else BASELINE)
    command.upgrade(cfg, "head")
