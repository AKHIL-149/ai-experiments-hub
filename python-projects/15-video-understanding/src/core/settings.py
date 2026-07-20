"""
Configuration management utilities and helpers
Provides additional tools for working with application settings
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.core.config import settings

logger = logging.getLogger(__name__)


class ConfigurationValidator:
    """Validate application configuration"""

    @staticmethod
    def validate_paths() -> List[str]:
        """
        Validate that all configured paths are accessible

        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []

        # Check ffmpeg paths
        ffmpeg_path = Path(settings.ffmpeg_path)
        if not ffmpeg_path.exists():
            errors.append(f"ffmpeg not found at: {settings.ffmpeg_path}")

        ffprobe_path = Path(settings.ffprobe_path)
        if not ffprobe_path.exists():
            errors.append(f"ffprobe not found at: {settings.ffprobe_path}")

        # Check storage paths (will be created if needed, just warn)
        storage_paths = [
            settings.storage_base_path,
            settings.videos_path,
            settings.frames_path,
            settings.clips_path,
            settings.temp_path,
            settings.cache_path,
        ]

        for path_str in storage_paths:
            path = Path(path_str)
            if not path.exists():
                logger.warning(f"Storage path will be created: {path_str}")

        return errors

    @staticmethod
    def validate_api_keys() -> List[str]:
        """
        Validate that required API keys are configured

        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []

        # Check if at least one AI provider is configured
        has_openai = settings.openai_api_key is not None
        has_anthropic = settings.anthropic_api_key is not None

        if not has_openai and not has_anthropic:
            errors.append(
                "No AI provider API key configured. "
                "Set OPENAI_API_KEY or ANTHROPIC_API_KEY for vision/LLM features."
            )

        # Warn about Whisper API usage
        if settings.whisper_use_api and not has_openai:
            errors.append(
                "Whisper API enabled but OPENAI_API_KEY not set. "
                "Either set the key or use local Whisper."
            )

        return errors

    @staticmethod
    def validate_database() -> List[str]:
        """
        Validate database configuration

        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []

        if not settings.database_url:
            errors.append("DATABASE_URL not configured")

        # Check if using SQLite in production
        if settings.app_env == "production" and settings.database_url.startswith("sqlite"):
            errors.append(
                "SQLite is not recommended for production. "
                "Consider using PostgreSQL."
            )

        return errors

    @staticmethod
    def validate_all() -> Dict[str, List[str]]:
        """
        Run all validation checks

        Returns:
            Dictionary with validation results by category
        """
        return {
            'paths': ConfigurationValidator.validate_paths(),
            'api_keys': ConfigurationValidator.validate_api_keys(),
            'database': ConfigurationValidator.validate_database(),
        }


class ConfigurationExporter:
    """Export configuration for documentation or debugging"""

    @staticmethod
    def export_settings(include_sensitive: bool = False) -> Dict[str, Any]:
        """
        Export current settings as dictionary

        Args:
            include_sensitive: Include sensitive values (API keys, secrets)

        Returns:
            Dictionary with current settings
        """
        config = {
            'application': {
                'environment': settings.app_env,
                'debug': settings.debug,
                'host': settings.api_host,
                'port': settings.api_port,
            },
            'database': {
                'url': settings.database_url if include_sensitive else '***',
                'echo': settings.db_echo,
            },
            'video_processing': {
                'ffmpeg_path': settings.ffmpeg_path,
                'ffprobe_path': settings.ffprobe_path,
                'frame_extraction_fps': settings.frame_extraction_fps,
                'keyframe_threshold': settings.keyframe_threshold,
                'max_video_size_mb': settings.max_video_size_mb,
            },
            'storage': {
                'base_path': settings.storage_base_path,
                'videos_path': settings.videos_path,
                'frames_path': settings.frames_path,
                'clips_path': settings.clips_path,
                'temp_path': settings.temp_path,
                'cache_path': settings.cache_path,
            },
            'ai_models': {
                'openai_api_key': '***' if settings.openai_api_key and not include_sensitive else None,
                'anthropic_api_key': '***' if settings.anthropic_api_key and not include_sensitive else None,
                'whisper_model': settings.whisper_model,
                'whisper_device': settings.whisper_device,
                'whisper_use_api': settings.whisper_use_api,
                'vision_provider': settings.vision_provider,
                'vision_model': settings.vision_model,
                'clip_model': settings.clip_model,
                'clip_device': settings.clip_device,
            },
            'chromadb': {
                'persist_directory': settings.chroma_persist_directory,
                'collection_frames': settings.chroma_collection_frames,
                'collection_transcripts': settings.chroma_collection_transcripts,
                'collection_scenes': settings.chroma_collection_scenes,
            },
            'scene_detection': {
                'detector_type': settings.scene_detector_type,
                'threshold': settings.scene_threshold,
                'min_scene_length': settings.min_scene_length,
            },
            'cache': {
                'enabled': settings.cache_enabled,
                'ttl_seconds': settings.cache_ttl_seconds,
                'max_size_mb': settings.cache_max_size_mb,
            },
            'processing': {
                'max_concurrent_videos': settings.max_concurrent_videos,
                'timeout_seconds': settings.processing_timeout_seconds,
                'enable_gpu': settings.enable_gpu,
            },
            'logging': {
                'level': settings.log_level,
                'file': settings.log_file,
                'format': settings.log_format,
            },
            'cors': {
                'origins': settings.cors_origins,
                'allow_credentials': settings.cors_allow_credentials,
            },
            'rate_limiting': {
                'enabled': settings.rate_limit_enabled,
                'per_minute': settings.rate_limit_per_minute,
            },
        }

        return config

    @staticmethod
    def export_environment_template() -> str:
        """
        Generate .env template with all available settings

        Returns:
            Template string for .env file
        """
        template = """# Video Understanding Platform - Environment Configuration

# Application Settings
APP_ENV=development
DEBUG=True
SECRET_KEY=dev-secret-key-change-in-production
API_HOST=0.0.0.0
API_PORT=8000

# Database Configuration
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/video_understanding
DB_ECHO=False

# Video Processing Settings
FFMPEG_PATH=/usr/local/bin/ffmpeg
FFPROBE_PATH=/usr/local/bin/ffprobe
FRAME_EXTRACTION_FPS=1
KEYFRAME_THRESHOLD=0.3
MAX_VIDEO_SIZE_MB=500

# Storage Paths
STORAGE_BASE_PATH=./storage
VIDEOS_PATH=./storage/videos
FRAMES_PATH=./storage/frames
CLIPS_PATH=./storage/clips
TEMP_PATH=./storage/temp
CACHE_PATH=./storage/cache

# AI Model Configuration
OPENAI_API_KEY=your-openai-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here

# Whisper Configuration
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
WHISPER_USE_API=False

# Vision Model Configuration
VISION_PROVIDER=ollama
VISION_MODEL=llava:latest
VISION_MAX_TOKENS=500

# CLIP Configuration
CLIP_MODEL=ViT-B/32
CLIP_DEVICE=cpu
CLIP_BATCH_SIZE=32

# ChromaDB Configuration
CHROMA_PERSIST_DIRECTORY=./chroma_data
CHROMA_COLLECTION_FRAMES=frames
CHROMA_COLLECTION_TRANSCRIPTS=transcripts
CHROMA_COLLECTION_SCENES=scenes

# Scene Detection Configuration
SCENE_DETECTOR_TYPE=content
SCENE_THRESHOLD=27.0
MIN_SCENE_LENGTH=1.0

# Speaker Diarization
DIARIZATION_MODEL=pyannote/speaker-diarization-3.1
DIARIZATION_USE_AUTH_TOKEN=False
HF_TOKEN=your-huggingface-token-here

# Cache Configuration
CACHE_ENABLED=True
CACHE_TTL_SECONDS=3600
CACHE_MAX_SIZE_MB=500

# Processing Configuration
MAX_CONCURRENT_VIDEOS=3
PROCESSING_TIMEOUT_SECONDS=3600
ENABLE_GPU=False

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/app.log
LOG_FORMAT=json

# CORS Settings
CORS_ORIGINS=http://localhost:3000,http://localhost:8000
CORS_ALLOW_CREDENTIALS=True

# Rate Limiting
RATE_LIMIT_ENABLED=True
RATE_LIMIT_PER_MINUTE=60

# WebSocket
WS_HEARTBEAT_INTERVAL=30
WS_MAX_CONNECTIONS=100

# YouTube Download
YT_DLP_FORMAT=best
YT_DLP_MAX_FILESIZE_MB=100

# Monitoring
ENABLE_METRICS=True
METRICS_PORT=9090
"""
        return template


def validate_configuration() -> bool:
    """
    Validate complete configuration and log results

    Returns:
        True if valid, False if errors found
    """
    logger.info("Validating configuration...")

    validation_results = ConfigurationValidator.validate_all()

    has_errors = False
    for category, errors in validation_results.items():
        if errors:
            has_errors = True
            logger.error(f"Configuration errors in {category}:")
            for error in errors:
                logger.error(f"  - {error}")

    if not has_errors:
        logger.info("✅ Configuration validation passed")
    else:
        logger.warning("⚠️  Configuration validation found errors")

    return not has_errors


def print_configuration_summary():
    """Print configuration summary to console"""
    config = ConfigurationExporter.export_settings(include_sensitive=False)

    print("\n" + "=" * 60)
    print("VIDEO UNDERSTANDING PLATFORM - CONFIGURATION SUMMARY")
    print("=" * 60)

    print(f"\n📦 Application:")
    print(f"  Environment: {config['application']['environment']}")
    print(f"  Debug: {config['application']['debug']}")
    print(f"  API: {config['application']['host']}:{config['application']['port']}")

    print(f"\n🗄️  Database:")
    print(f"  URL: {config['database']['url']}")

    print(f"\n🎬 Video Processing:")
    print(f"  Frame FPS: {config['video_processing']['frame_extraction_fps']}")
    print(f"  Max Size: {config['video_processing']['max_video_size_mb']} MB")

    print(f"\n💾 Storage:")
    print(f"  Base: {config['storage']['base_path']}")

    print(f"\n🤖 AI Models:")
    print(f"  Vision: {config['ai_models']['vision_provider']} / {config['ai_models']['vision_model']}")
    print(f"  Whisper: {config['ai_models']['whisper_model']} ({'API' if config['ai_models']['whisper_use_api'] else 'Local'})")
    print(f"  CLIP: {config['ai_models']['clip_model']}")

    print(f"\n⚡ Processing:")
    print(f"  Max Concurrent: {config['processing']['max_concurrent_videos']}")
    print(f"  GPU Enabled: {config['processing']['enable_gpu']}")

    print(f"\n📝 Logging:")
    print(f"  Level: {config['logging']['level']}")
    print(f"  Format: {config['logging']['format']}")

    print("\n" + "=" * 60 + "\n")
