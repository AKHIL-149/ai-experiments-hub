"""
Configuration management using Pydantic Settings
Loads settings from environment variables and .env file
"""

from typing import List, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    All settings have defaults and can be overridden via .env file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application Settings
    app_env: str = Field(default="development", description="Application environment")
    debug: bool = Field(default=True, description="Debug mode")
    secret_key: str = Field(default="dev-secret-key-change-in-production", description="Secret key for JWT")
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")

    # Database Configuration
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/video_understanding",
        description="Database connection URL"
    )
    db_echo: bool = Field(default=False, description="Echo SQL queries")

    # Video Processing Settings
    ffmpeg_path: str = Field(default="/usr/local/bin/ffmpeg", description="Path to ffmpeg executable")
    ffprobe_path: str = Field(default="/usr/local/bin/ffprobe", description="Path to ffprobe executable")
    frame_extraction_fps: int = Field(default=1, description="Frames per second for extraction")
    keyframe_threshold: float = Field(default=0.3, description="Threshold for keyframe detection")
    max_video_size_mb: int = Field(default=500, description="Maximum video size in MB")

    # Storage Paths
    storage_base_path: str = Field(default="./storage", description="Base storage directory")
    videos_path: str = Field(default="./storage/videos", description="Videos storage path")
    frames_path: str = Field(default="./storage/frames", description="Frames storage path")
    clips_path: str = Field(default="./storage/clips", description="Clips storage path")
    temp_path: str = Field(default="./storage/temp", description="Temporary files path")
    cache_path: str = Field(default="./storage/cache", description="Cache storage path")

    # AI Model Configuration
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API key")

    # Whisper Configuration
    whisper_model: str = Field(default="base", description="Whisper model size")
    whisper_device: str = Field(default="cpu", description="Device for Whisper (cpu/cuda)")
    whisper_use_api: bool = Field(default=False, description="Use Whisper API instead of local")

    # Vision Model Configuration
    vision_provider: str = Field(default="ollama", description="Vision model provider")
    vision_model: str = Field(default="llava:latest", description="Vision model name")
    vision_max_tokens: int = Field(default=500, description="Max tokens for vision model")

    # CLIP Configuration
    clip_model: str = Field(default="ViT-B/32", description="CLIP model name")
    clip_device: str = Field(default="cpu", description="Device for CLIP (cpu/cuda)")
    clip_batch_size: int = Field(default=32, description="Batch size for CLIP processing")

    # ChromaDB Configuration
    chroma_persist_directory: str = Field(default="./chroma_data", description="ChromaDB persistence directory")
    chroma_collection_frames: str = Field(default="frames", description="ChromaDB collection for frames")
    chroma_collection_transcripts: str = Field(default="transcripts", description="ChromaDB collection for transcripts")
    chroma_collection_scenes: str = Field(default="scenes", description="ChromaDB collection for scenes")

    # Scene Detection Configuration
    scene_detector_type: str = Field(default="content", description="Scene detector type")
    scene_threshold: float = Field(default=27.0, description="Scene detection threshold")
    min_scene_length: float = Field(default=1.0, description="Minimum scene length in seconds")

    # Speaker Diarization
    diarization_model: str = Field(default="pyannote/speaker-diarization-3.1", description="Diarization model")
    diarization_use_auth_token: bool = Field(default=False, description="Use HuggingFace auth token")
    hf_token: Optional[str] = Field(default=None, description="HuggingFace token")

    # Cache Configuration
    cache_enabled: bool = Field(default=True, description="Enable caching")
    cache_ttl_seconds: int = Field(default=3600, description="Cache TTL in seconds")
    cache_max_size_mb: int = Field(default=500, description="Maximum cache size in MB")

    # Processing Configuration
    max_concurrent_videos: int = Field(default=3, description="Maximum concurrent video processing")
    processing_timeout_seconds: int = Field(default=3600, description="Processing timeout in seconds")
    enable_gpu: bool = Field(default=False, description="Enable GPU acceleration")

    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_file: str = Field(default="./logs/app.log", description="Log file path")
    log_format: str = Field(default="json", description="Log format (json/text)")

    # CORS Settings
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="CORS allowed origins"
    )
    cors_allow_credentials: bool = Field(default=True, description="CORS allow credentials")

    # Rate Limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_per_minute: int = Field(default=60, description="Requests per minute limit")

    # WebSocket
    ws_heartbeat_interval: int = Field(default=30, description="WebSocket heartbeat interval in seconds")
    ws_max_connections: int = Field(default=100, description="Maximum WebSocket connections")

    # YouTube Download
    yt_dlp_format: str = Field(default="best", description="yt-dlp format string")
    yt_dlp_max_filesize_mb: int = Field(default=100, description="Max filesize for YouTube downloads in MB")

    # Monitoring
    enable_metrics: bool = Field(default=True, description="Enable metrics collection")
    metrics_port: int = Field(default=9090, description="Metrics server port")


# Singleton instance
settings = Settings()
