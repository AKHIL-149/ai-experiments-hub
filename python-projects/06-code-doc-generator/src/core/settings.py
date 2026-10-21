"""Environment-driven settings (documented in .env.example).

Importing this module loads the project's .env once. Real environment
variables always win over values in the file. Explicit CLI flags and function
arguments still override everything here.
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
except ImportError:
    pass


def env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    try:
        return int(value) if value and value.strip() else default
    except ValueError:
        return default


def default_provider() -> str:
    """Provider from LLM_PROVIDER, else ollama."""
    return env_str("LLM_PROVIDER", "ollama").lower()


def cache_enabled() -> bool:
    return env_bool("ENABLE_CACHE", True)


def cache_dir() -> str:
    return env_str("CACHE_DIR", "./data/cache")


def cache_expiry_days() -> int:
    return env_int("CACHE_EXPIRY_DAYS", 7)


def default_output_dir() -> str:
    return env_str("DEFAULT_OUTPUT_DIR", "./data/output")


def default_format() -> str:
    return env_str("DEFAULT_FORMAT", "markdown")


def web_host() -> str:
    return env_str("WEB_HOST", "127.0.0.1")


def web_port() -> int:
    return env_int("WEB_PORT", 8000)


def nodejs_path() -> str:
    return env_str("NODEJS_PATH", "node")
