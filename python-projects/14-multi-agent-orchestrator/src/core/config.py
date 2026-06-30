"""
Application configuration
"""

import os
from typing import List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Application settings"""

    # Application
    APP_NAME: str = os.getenv("APP_NAME", "Multi-Agent Task Orchestrator")
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8001"))

    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/multi_agent_orchestrator"
    )
    DB_ECHO: bool = os.getenv("DB_ECHO", "false").lower() == "true"

    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

    # LLM API Keys
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # LLM Settings
    DEFAULT_LLM_PROVIDER: str = os.getenv("DEFAULT_LLM_PROVIDER", "openai")
    DEFAULT_MODEL: str = os.getenv("DEFAULT_MODEL", "gpt-4-turbo-preview")
    ANTHROPIC_MODEL: str = os.getenv("ANTHROPIC_MODEL", "claude-3-sonnet-20240229")
    TEMPERATURE: float = float(os.getenv("TEMPERATURE", "0.7"))
    MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "4000"))

    # Agent Configuration
    MAX_AGENT_ITERATIONS: int = int(os.getenv("MAX_AGENT_ITERATIONS", "10"))
    AGENT_TIMEOUT: int = int(os.getenv("AGENT_TIMEOUT", "300"))
    ENABLE_HUMAN_APPROVAL: bool = os.getenv("ENABLE_HUMAN_APPROVAL", "true").lower() == "true"

    # Task Orchestration
    MAX_PARALLEL_TASKS: int = int(os.getenv("MAX_PARALLEL_TASKS", "5"))
    TASK_RETRY_LIMIT: int = int(os.getenv("TASK_RETRY_LIMIT", "3"))
    TASK_TIMEOUT: int = int(os.getenv("TASK_TIMEOUT", "1800"))

    # Monitoring
    ENABLE_METRICS: bool = os.getenv("ENABLE_METRICS", "true").lower() == "true"
    METRICS_PORT: int = int(os.getenv("METRICS_PORT", "9090"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Cost Tracking
    ENABLE_COST_TRACKING: bool = os.getenv("ENABLE_COST_TRACKING", "true").lower() == "true"
    COST_ALERT_THRESHOLD: float = float(os.getenv("COST_ALERT_THRESHOLD", "10.0"))

    # File Storage
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./data/repos")
    TEMP_DIR: str = os.getenv("TEMP_DIR", "./data/temp")
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", "104857600"))  # 100MB

    # WebSocket
    WS_HEARTBEAT_INTERVAL: int = int(os.getenv("WS_HEARTBEAT_INTERVAL", "30"))

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8001",
    ]

    class Config:
        case_sensitive = True


# Singleton instance
settings = Settings()
