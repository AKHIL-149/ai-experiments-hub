"""Settings loaded from environment variables and .env"""
from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    debug: bool = False
    api_host: str = "127.0.0.1"
    api_port: int = 8016

    database_url: str = "sqlite:///./data/kg.db"
    db_echo: bool = False

    # --- accounts (step 4) ---
    require_login: bool = Field(default=True, description="False = single-user mode: no sign-in, everything belongs to 'local'")
    allow_registration: bool = True
    allow_guests: bool = True
    guest_ttl_hours: int = Field(default=24, ge=1, description="A guest account and its data are removed after this long")
    guest_max_documents: int = Field(default=3, ge=1, description="Documents a guest may add")
    session_days: int = Field(default=14, ge=1)
    cookie_secure: bool = Field(default=False, description="True when served over HTTPS (the cookie then never travels over plain HTTP)")
    allowed_origins: str = Field(default="", description="Extra browser origins allowed to write (comma separated), e.g. http://localhost:3000")

    # --- background jobs (step 4) ---
    job_workers_enabled: bool = Field(default=True, description="False = no worker threads (tests, or a separate worker process)")
    max_concurrent_documents: int = Field(default=1, ge=1, le=8, description="Documents read at the same time (a local model answers one request at a time)")
    max_queued_jobs_per_user: int = Field(default=10, ge=1, description="Waiting plus running jobs one account may have")
    job_max_attempts: int = Field(default=2, ge=1, description="Tries for a job whose worker died")
    job_stale_seconds: int = Field(default=45, ge=10, description="A running job whose heartbeat is older than this is put back in the queue")

    llm_provider: str = Field(default="ollama", description="ollama | anthropic | openai")
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_num_ctx: int = 8192
    ollama_timeout: float = 300.0
    llm_max_tokens: int = Field(default=3072, ge=256, le=8192, description="Longest answer one model call may write (stops a repetition loop from running for minutes)")
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-haiku-5-5"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"

    embedding_model: str = Field(default="nomic-embed-text", description="Ollama embedding model for passages, facts and questions")
    index_chunks: bool = Field(default=True, description="Embed passages while reading a document (needed for passage search)")
    ask_max_facts: int = Field(default=30, ge=5, le=100, description="Most facts handed to the model for one question")
    ask_top_chunks: int = Field(default=4, ge=1, le=12, description="Passages added by passage search / hybrid")
    ask_max_hops: int = Field(default=2, ge=1, le=4, description="How far around the entities of a question the facts are collected")
    predicate_threshold: float = Field(default=0.62, ge=0.0, le=1.0, description="How alike a relation word and a stored predicate must be")
    chunk_chars: int = Field(default=1500, ge=300)
    chunk_overlap_chars: int = Field(default=200, ge=0)
    verify_facts: bool = True
    gleaning_passes: int = Field(default=1, ge=0, le=3, description="Extra 'what did you miss?' calls per chunk")
    auto_resolve: bool = Field(default=True, description="After each document, merge entities whose names are the same apart from case, titles, suffixes")
    auto_detect_conflicts: bool = Field(default=True, description="After each document, look for facts that cannot both be true (code only, no model)")
    resolution_use_llm: bool = Field(default=False, description="Ask the model for a second opinion on suggested merges")
    max_upload_mb: int = 20
    max_document_chars: int = Field(default=100_000, description="Longest text accepted (a model reads ~1,500 characters per call)")


@lru_cache
def get_settings() -> Settings:
    return Settings()
