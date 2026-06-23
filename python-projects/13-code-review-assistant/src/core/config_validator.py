"""
Configuration Validator
Validates environment variables and configuration at startup
"""

import os
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum


class ConfigLevel(Enum):
    """Configuration validation level"""
    REQUIRED = "required"       # Must be set
    RECOMMENDED = "recommended" # Should be set
    OPTIONAL = "optional"       # Nice to have


@dataclass
class ConfigRule:
    """Configuration validation rule"""
    name: str
    level: ConfigLevel
    validator: callable = None
    default: Any = None
    description: str = ""


class ConfigValidator:
    """Validates application configuration"""

    # Configuration rules
    RULES = [
        # Server configuration
        ConfigRule(
            name='HOST',
            level=ConfigLevel.OPTIONAL,
            default='0.0.0.0',
            description='Server host address'
        ),
        ConfigRule(
            name='PORT',
            level=ConfigLevel.OPTIONAL,
            validator=lambda x: x.isdigit() and 1 <= int(x) <= 65535,
            default='8000',
            description='Server port (1-65535)'
        ),

        # Database configuration
        ConfigRule(
            name='DATABASE_URL',
            level=ConfigLevel.RECOMMENDED,
            validator=lambda x: x.startswith(('sqlite:///', 'postgresql://', 'mysql://')),
            default='sqlite:///./data/database.db',
            description='Database connection URL'
        ),

        # Redis configuration
        ConfigRule(
            name='REDIS_URL',
            level=ConfigLevel.RECOMMENDED,
            validator=lambda x: x.startswith('redis://'),
            default='redis://localhost:6379/0',
            description='Redis connection URL for caching and Celery'
        ),

        # Celery configuration
        ConfigRule(
            name='CELERY_BROKER_URL',
            level=ConfigLevel.RECOMMENDED,
            validator=lambda x: x.startswith('redis://'),
            default='redis://localhost:6379/0',
            description='Celery broker URL'
        ),
        ConfigRule(
            name='CELERY_RESULT_BACKEND',
            level=ConfigLevel.RECOMMENDED,
            validator=lambda x: x.startswith('redis://'),
            default='redis://localhost:6379/1',
            description='Celery result backend URL'
        ),

        # Security configuration
        ConfigRule(
            name='SESSION_TTL_DAYS',
            level=ConfigLevel.OPTIONAL,
            validator=lambda x: x.isdigit() and int(x) > 0,
            default='30',
            description='Session TTL in days'
        ),
        ConfigRule(
            name='COOKIE_SECURE',
            level=ConfigLevel.RECOMMENDED,
            validator=lambda x: x.lower() in ('true', 'false'),
            default='false',
            description='Use secure cookies (true in production)'
        ),
        ConfigRule(
            name='ALLOWED_ORIGINS',
            level=ConfigLevel.RECOMMENDED,
            default='http://localhost:8000',
            description='CORS allowed origins (comma-separated)'
        ),

        # GitHub integration
        ConfigRule(
            name='GITHUB_TOKEN',
            level=ConfigLevel.OPTIONAL,
            validator=lambda x: x.startswith(('ghp_', 'gho_')) and len(x) > 35,
            description='GitHub personal access token (ghp_...)'
        ),
        ConfigRule(
            name='GITHUB_WEBHOOK_SECRET',
            level=ConfigLevel.OPTIONAL,
            description='GitHub webhook secret'
        ),

        # LLM configuration
        ConfigRule(
            name='OLLAMA_API_URL',
            level=ConfigLevel.OPTIONAL,
            validator=lambda x: x.startswith('http'),
            default='http://localhost:11434',
            description='Ollama API URL'
        ),
        ConfigRule(
            name='OLLAMA_MODEL',
            level=ConfigLevel.OPTIONAL,
            default='llama3.2',
            description='Ollama model name'
        ),
        ConfigRule(
            name='ANTHROPIC_API_KEY',
            level=ConfigLevel.OPTIONAL,
            validator=lambda x: x.startswith('sk-ant-'),
            description='Anthropic API key (sk-ant-...)'
        ),
        ConfigRule(
            name='OPENAI_API_KEY',
            level=ConfigLevel.OPTIONAL,
            validator=lambda x: x.startswith('sk-'),
            description='OpenAI API key (sk-...)'
        ),

        # Analysis configuration
        ConfigRule(
            name='COMPLEXITY_THRESHOLD_WARN',
            level=ConfigLevel.OPTIONAL,
            validator=lambda x: x.isdigit() and int(x) > 0,
            default='10',
            description='Cyclomatic complexity warning threshold'
        ),
        ConfigRule(
            name='COMPLEXITY_THRESHOLD_ERROR',
            level=ConfigLevel.OPTIONAL,
            validator=lambda x: x.isdigit() and int(x) > 0,
            default='15',
            description='Cyclomatic complexity error threshold'
        ),

        # Git configuration
        ConfigRule(
            name='GIT_CLONE_DIR',
            level=ConfigLevel.OPTIONAL,
            default='./data/repos',
            description='Directory for cloned repositories'
        ),
    ]

    def __init__(self):
        """Initialize configuration validator"""
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

    def validate(self) -> bool:
        """
        Validate all configuration rules

        Returns:
            True if valid (no REQUIRED rules failed), False otherwise
        """
        self.errors = []
        self.warnings = []
        self.info = []

        for rule in self.RULES:
            value = os.getenv(rule.name)

            if value is None:
                # Variable not set
                if rule.level == ConfigLevel.REQUIRED:
                    self.errors.append(
                        f"REQUIRED: {rule.name} is not set. {rule.description}"
                    )
                elif rule.level == ConfigLevel.RECOMMENDED:
                    self.warnings.append(
                        f"RECOMMENDED: {rule.name} is not set. {rule.description}"
                    )
                    if rule.default:
                        self.info.append(
                            f"Using default for {rule.name}: {rule.default}"
                        )
                else:  # OPTIONAL
                    if rule.default:
                        self.info.append(
                            f"Optional: {rule.name} not set, using default: {rule.default}"
                        )
            else:
                # Variable is set, validate it
                if rule.validator:
                    try:
                        if not rule.validator(value):
                            if rule.level == ConfigLevel.REQUIRED:
                                self.errors.append(
                                    f"INVALID: {rule.name}={value} failed validation. {rule.description}"
                                )
                            else:
                                self.warnings.append(
                                    f"INVALID: {rule.name}={value} failed validation. {rule.description}"
                                )
                    except Exception as e:
                        self.errors.append(
                            f"VALIDATION ERROR: {rule.name} - {str(e)}"
                        )

        return len(self.errors) == 0

    def print_report(self):
        """Print validation report"""
        print("\n" + "="*60)
        print("CONFIGURATION VALIDATION REPORT")
        print("="*60)

        if self.errors:
            print(f"\n❌ ERRORS ({len(self.errors)}):")
            for error in self.errors:
                print(f"   {error}")

        if self.warnings:
            print(f"\n⚠️  WARNINGS ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"   {warning}")

        if self.info:
            print(f"\nℹ️  INFO ({len(self.info)}):")
            for info_msg in self.info:
                print(f"   {info_msg}")

        if not self.errors and not self.warnings:
            print("\n✅ All configuration validated successfully!")

        print("="*60 + "\n")

    def get_summary(self) -> Dict[str, Any]:
        """
        Get validation summary

        Returns:
            Dictionary with validation results
        """
        return {
            'valid': len(self.errors) == 0,
            'errors': self.errors,
            'warnings': self.warnings,
            'info': self.info,
            'error_count': len(self.errors),
            'warning_count': len(self.warnings)
        }


def validate_startup_config() -> bool:
    """
    Validate configuration at application startup

    Returns:
        True if valid, False if critical errors found
    """
    validator = ConfigValidator()
    is_valid = validator.validate()
    validator.print_report()

    if not is_valid:
        print("❌ Configuration validation failed! Please fix the errors above.")
        print("   Set missing required environment variables in .env file")
        return False

    if validator.warnings:
        print("⚠️  Configuration has warnings but will continue startup.")
        print("   Consider addressing the warnings for production use.")

    return True


def check_health_dependencies() -> Dict[str, bool]:
    """
    Check health of external dependencies

    Returns:
        Dictionary with dependency status
    """
    import redis
    from sqlalchemy import create_engine

    health = {
        'database': False,
        'redis': False,
        'celery_broker': False
    }

    # Check database
    try:
        db_url = os.getenv('DATABASE_URL', 'sqlite:///./data/database.db')
        engine = create_engine(db_url)
        with engine.connect() as conn:
            conn.execute("SELECT 1")
        health['database'] = True
    except Exception as e:
        print(f"Database health check failed: {e}")

    # Check Redis
    try:
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        redis_client = redis.from_url(redis_url, socket_connect_timeout=5)
        redis_client.ping()
        health['redis'] = True
    except Exception as e:
        print(f"Redis health check failed: {e}")

    # Check Celery broker (usually same as Redis)
    try:
        broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
        broker_client = redis.from_url(broker_url, socket_connect_timeout=5)
        broker_client.ping()
        health['celery_broker'] = True
    except Exception as e:
        print(f"Celery broker health check failed: {e}")

    return health


# Global validator instance
config_validator = ConfigValidator()
