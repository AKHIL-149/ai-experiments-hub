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

    llm_provider: str = Field(default="ollama", description="ollama | anthropic | openai")
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_num_ctx: int = 8192
    ollama_timeout: float = 300.0
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
    resolution_use_llm: bool = Field(default=False, description="Ask the model for a second opinion on suggested merges")
    max_upload_mb: int = 20
    max_document_chars: int = Field(default=100_000, description="Longest text accepted (a model reads ~1,500 characters per call)")


@lru_cache
def get_settings() -> Settings:
    return Settings()
