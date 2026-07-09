"""
Configuration Management Service

Provides centralized, versioned, and validated configuration management.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from collections import defaultdict
import uuid
import json
import copy


class ConfigEnvironment:
    """Configuration environment types"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class ConfigType:
    """Configuration types"""
    SYSTEM = "system"
    AGENT = "agent"
    WORKFLOW = "workflow"
    LLM = "llm"
    SECURITY = "security"
    INTEGRATION = "integration"
    CUSTOM = "custom"


class ConfigStatus:
    """Configuration status"""
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class ConfigManagement:
    """Configuration Management service for centralized config"""

    # In-memory storage
    _configurations = {}
    _config_versions = defaultdict(list)
    _config_templates = {}
    _config_validation_schemas = {}
    _active_configs = {}  # env -> config_key -> config_id
    _config_history = defaultdict(list)

    @staticmethod
    def create_configuration(
        session,
        key: str,
        value: Any,
        config_type: str,
        environment: str = ConfigEnvironment.DEVELOPMENT,
        description: Optional[str] = None,
        encrypted: bool = False,
        validation_schema: Optional[dict] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create a configuration.

        Args:
            session: Database session
            key: Configuration key
            value: Configuration value
            config_type: Type of configuration
            environment: Target environment
            description: Configuration description
            encrypted: Whether value should be encrypted
            validation_schema: JSON schema for validation
            metadata: Additional metadata

        Returns:
            Created configuration
        """
        # Validate against schema if provided
        if validation_schema:
            ConfigManagement._validate_config(value, validation_schema)

        config_id = f"config_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        config = {
            "id": config_id,
            "key": key,
            "value": ConfigManagement._encrypt_value(value) if encrypted else value,
            "config_type": config_type,
            "environment": environment,
            "description": description,
            "encrypted": encrypted,
            "validation_schema": validation_schema,
            "metadata": metadata or {},
            "status": ConfigStatus.DRAFT,
            "version": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "created_by": metadata.get("created_by", "system") if metadata else "system",
            "activated_at": None
        }

        ConfigManagement._configurations[config_id] = config
        ConfigManagement._config_versions[key].append(config)

        # Record in history
        ConfigManagement._config_history[key].append({
            "timestamp": now.isoformat(),
            "action": "created",
            "config_id": config_id,
            "version": 1
        })

        return config

    @staticmethod
    def update_configuration(
        session,
        config_id: str,
        value: Optional[Any] = None,
        description: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Update a configuration.

        Args:
            session: Database session
            config_id: Configuration ID
            value: New value
            description: Updated description
            metadata: Updated metadata

        Returns:
            Updated configuration
        """
        config = ConfigManagement._configurations.get(config_id)
        if not config:
            raise ValueError(f"Configuration not found: {config_id}")

        now = datetime.utcnow()

        # Create new version
        new_version = config["version"] + 1
        new_config_id = f"config_{uuid.uuid4().hex[:12]}"

        new_config = copy.deepcopy(config)
        new_config["id"] = new_config_id
        new_config["version"] = new_version
        new_config["updated_at"] = now.isoformat()

        if value is not None:
            # Validate if schema exists
            if config.get("validation_schema"):
                ConfigManagement._validate_config(value, config["validation_schema"])

            new_config["value"] = ConfigManagement._encrypt_value(value) if config["encrypted"] else value

        if description is not None:
            new_config["description"] = description

        if metadata is not None:
            new_config["metadata"].update(metadata)

        # Store new version
        ConfigManagement._configurations[new_config_id] = new_config
        ConfigManagement._config_versions[config["key"]].append(new_config)

        # Mark old version as deprecated
        config["status"] = ConfigStatus.DEPRECATED

        # Record in history
        ConfigManagement._config_history[config["key"]].append({
            "timestamp": now.isoformat(),
            "action": "updated",
            "config_id": new_config_id,
            "version": new_version,
            "previous_version": config["version"]
        })

        return new_config

    @staticmethod
    def activate_configuration(
        session,
        config_id: str
    ) -> dict:
        """
        Activate a configuration.

        Args:
            session: Database session
            config_id: Configuration to activate

        Returns:
            Activated configuration
        """
        config = ConfigManagement._configurations.get(config_id)
        if not config:
            raise ValueError(f"Configuration not found: {config_id}")

        now = datetime.utcnow()

        # Deactivate existing active config with same key and environment
        env_key = (config["environment"], config["key"])
        if env_key in ConfigManagement._active_configs:
            old_config_id = ConfigManagement._active_configs[env_key]
            old_config = ConfigManagement._configurations.get(old_config_id)
            if old_config:
                old_config["status"] = ConfigStatus.DEPRECATED

        # Activate new config
        config["status"] = ConfigStatus.ACTIVE
        config["activated_at"] = now.isoformat()
        ConfigManagement._active_configs[env_key] = config_id

        # Record in history
        ConfigManagement._config_history[config["key"]].append({
            "timestamp": now.isoformat(),
            "action": "activated",
            "config_id": config_id,
            "environment": config["environment"]
        })

        return config

    @staticmethod
    def get_configuration(
        session,
        key: str,
        environment: str = ConfigEnvironment.DEVELOPMENT,
        decrypt: bool = True
    ) -> dict:
        """
        Get active configuration by key and environment.

        Args:
            session: Database session
            key: Configuration key
            environment: Environment
            decrypt: Whether to decrypt encrypted values

        Returns:
            Configuration
        """
        env_key = (environment, key)
        config_id = ConfigManagement._active_configs.get(env_key)

        if not config_id:
            raise ValueError(f"No active configuration found for key '{key}' in environment '{environment}'")

        config = ConfigManagement._configurations.get(config_id)
        if not config:
            raise ValueError(f"Configuration not found: {config_id}")

        # Decrypt if requested and encrypted
        if decrypt and config["encrypted"]:
            config_copy = copy.deepcopy(config)
            config_copy["value"] = ConfigManagement._decrypt_value(config["value"])
            return config_copy

        return config

    @staticmethod
    def get_configuration_by_id(
        session,
        config_id: str,
        decrypt: bool = True
    ) -> dict:
        """Get configuration by ID"""
        config = ConfigManagement._configurations.get(config_id)
        if not config:
            raise ValueError(f"Configuration not found: {config_id}")

        # Decrypt if requested and encrypted
        if decrypt and config["encrypted"]:
            config_copy = copy.deepcopy(config)
            config_copy["value"] = ConfigManagement._decrypt_value(config["value"])
            return config_copy

        return config

    @staticmethod
    def list_configurations(
        session,
        config_type: Optional[str] = None,
        environment: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50
    ) -> dict:
        """
        List configurations with filtering.

        Args:
            session: Database session
            config_type: Filter by type
            environment: Filter by environment
            status: Filter by status
            limit: Maximum configs to return

        Returns:
            Filtered configurations
        """
        configs = list(ConfigManagement._configurations.values())

        # Apply filters
        if config_type:
            configs = [c for c in configs if c["config_type"] == config_type]
        if environment:
            configs = [c for c in configs if c["environment"] == environment]
        if status:
            configs = [c for c in configs if c["status"] == status]

        # Sort by updated_at descending
        configs.sort(key=lambda x: x["updated_at"], reverse=True)

        # Apply limit
        configs = configs[:limit]

        return {
            "configurations": configs,
            "total_configurations": len(ConfigManagement._configurations),
            "returned_count": len(configs)
        }

    @staticmethod
    def get_configuration_history(
        session,
        key: str
    ) -> dict:
        """
        Get configuration history.

        Args:
            session: Database session
            key: Configuration key

        Returns:
            Configuration history
        """
        versions = ConfigManagement._config_versions.get(key, [])
        history = ConfigManagement._config_history.get(key, [])

        return {
            "key": key,
            "total_versions": len(versions),
            "versions": sorted(versions, key=lambda x: x["version"], reverse=True),
            "history": sorted(history, key=lambda x: x["timestamp"], reverse=True)
        }

    @staticmethod
    def rollback_configuration(
        session,
        key: str,
        target_version: int,
        environment: str = ConfigEnvironment.DEVELOPMENT
    ) -> dict:
        """
        Rollback configuration to a previous version.

        Args:
            session: Database session
            key: Configuration key
            target_version: Version to rollback to
            environment: Environment

        Returns:
            Rolled back configuration
        """
        versions = ConfigManagement._config_versions.get(key, [])
        target_config = None

        for version in versions:
            if version["version"] == target_version and version["environment"] == environment:
                target_config = version
                break

        if not target_config:
            raise ValueError(f"Version {target_version} not found for key '{key}' in environment '{environment}'")

        # Create new version from target
        new_config_id = f"config_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # Get latest version number
        max_version = max(v["version"] for v in versions)
        new_version = max_version + 1

        new_config = copy.deepcopy(target_config)
        new_config["id"] = new_config_id
        new_config["version"] = new_version
        new_config["updated_at"] = now.isoformat()
        new_config["status"] = ConfigStatus.DRAFT
        new_config["metadata"]["rolled_back_from"] = target_version

        ConfigManagement._configurations[new_config_id] = new_config
        ConfigManagement._config_versions[key].append(new_config)

        # Record in history
        ConfigManagement._config_history[key].append({
            "timestamp": now.isoformat(),
            "action": "rolled_back",
            "config_id": new_config_id,
            "version": new_version,
            "target_version": target_version
        })

        return new_config

    @staticmethod
    def create_template(
        session,
        name: str,
        template_data: dict,
        description: Optional[str] = None
    ) -> dict:
        """
        Create a configuration template.

        Args:
            session: Database session
            name: Template name
            template_data: Template structure
            description: Template description

        Returns:
            Created template
        """
        template_id = f"template_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        template = {
            "id": template_id,
            "name": name,
            "template_data": template_data,
            "description": description,
            "created_at": now.isoformat(),
            "usage_count": 0
        }

        ConfigManagement._config_templates[template_id] = template
        return template

    @staticmethod
    def export_configurations(
        session,
        environment: Optional[str] = None,
        config_type: Optional[str] = None
    ) -> dict:
        """
        Export configurations.

        Args:
            session: Database session
            environment: Filter by environment
            config_type: Filter by type

        Returns:
            Export data
        """
        configs = list(ConfigManagement._configurations.values())

        # Apply filters
        if environment:
            configs = [c for c in configs if c["environment"] == environment]
        if config_type:
            configs = [c for c in configs if c["config_type"] == config_type]

        export_id = f"export_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        export = {
            "id": export_id,
            "exported_at": now.isoformat(),
            "config_count": len(configs),
            "configurations": configs
        }

        return export

    @staticmethod
    def get_statistics(session) -> dict:
        """Get configuration management statistics"""
        configs = list(ConfigManagement._configurations.values())

        # Status distribution
        status_dist = defaultdict(int)
        for config in configs:
            status_dist[config["status"]] += 1

        # Type distribution
        type_dist = defaultdict(int)
        for config in configs:
            type_dist[config["config_type"]] += 1

        # Environment distribution
        env_dist = defaultdict(int)
        for config in configs:
            env_dist[config["environment"]] += 1

        # Active configs per environment
        active_per_env = defaultdict(int)
        for config in configs:
            if config["status"] == ConfigStatus.ACTIVE:
                active_per_env[config["environment"]] += 1

        return {
            "total_configurations": len(configs),
            "total_keys": len(ConfigManagement._config_versions),
            "total_templates": len(ConfigManagement._config_templates),
            "status_distribution": dict(status_dist),
            "type_distribution": dict(type_dist),
            "environment_distribution": dict(env_dist),
            "active_per_environment": dict(active_per_env),
            "encrypted_configs": len([c for c in configs if c["encrypted"]])
        }

    @staticmethod
    def _validate_config(value: Any, schema: dict):
        """Validate configuration value against schema"""
        # Simple validation (in production, use jsonschema library)
        value_type = type(value).__name__
        expected_type = schema.get("type")

        if expected_type and value_type.lower() != expected_type.lower():
            raise ValueError(f"Invalid value type: expected {expected_type}, got {value_type}")

        # Additional validations...
        if "minimum" in schema and isinstance(value, (int, float)):
            if value < schema["minimum"]:
                raise ValueError(f"Value {value} is below minimum {schema['minimum']}")

        if "maximum" in schema and isinstance(value, (int, float)):
            if value > schema["maximum"]:
                raise ValueError(f"Value {value} exceeds maximum {schema['maximum']}")

    @staticmethod
    def _encrypt_value(value: Any) -> str:
        """Encrypt sensitive configuration value (simplified)"""
        # In production, use proper encryption (Fernet, AWS KMS, etc.)
        import base64
        value_json = json.dumps(value)
        encrypted = base64.b64encode(value_json.encode()).decode()
        return f"encrypted:{encrypted}"

    @staticmethod
    def _decrypt_value(encrypted_value: str) -> Any:
        """Decrypt encrypted configuration value"""
        if not encrypted_value.startswith("encrypted:"):
            return encrypted_value

        import base64
        encrypted = encrypted_value.replace("encrypted:", "")
        decrypted = base64.b64decode(encrypted.encode()).decode()
        return json.loads(decrypted)
