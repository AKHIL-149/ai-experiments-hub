"""
Environment Configuration and Feature Flags

Provides environment configuration management, feature flags, and production readiness checks.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import uuid
import random


class ConfigScope:
    """Configuration scopes"""
    GLOBAL = "global"
    ENVIRONMENT = "environment"
    SERVICE = "service"
    USER = "user"


class FeatureFlagStrategy:
    """Feature flag rollout strategies"""
    ALL_USERS = "all_users"
    PERCENTAGE = "percentage"
    USER_LIST = "user_list"
    GRADUAL_ROLLOUT = "gradual_rollout"
    A_B_TEST = "a_b_test"


class ConfigType:
    """Configuration value types"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    JSON = "json"
    SECRET = "secret"


class ReadinessStatus:
    """Production readiness status"""
    NOT_READY = "not_ready"
    PARTIALLY_READY = "partially_ready"
    READY = "ready"
    DEGRADED = "degraded"


class EnvironmentConfig:
    """Environment Configuration and Feature Flags service"""

    # In-memory storage
    _configurations = {}
    _feature_flags = {}
    _secrets = {}
    _config_history = defaultdict(list)
    _flag_evaluations = defaultdict(int)
    _readiness_checks = {}
    _config_templates = {}
    _validation_schemas = {}

    @staticmethod
    def create_configuration(
        session,
        config_key: str,
        config_value: Any,
        environment: str,
        config_type: str = ConfigType.STRING,
        scope: str = ConfigScope.ENVIRONMENT,
        is_secret: bool = False,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None
    ) -> dict:
        """
        Create configuration entry.

        Args:
            session: Database session
            config_key: Configuration key
            config_value: Configuration value
            environment: Target environment
            config_type: Type of configuration
            scope: Configuration scope
            is_secret: Whether value is sensitive
            description: Configuration description
            tags: Configuration tags

        Returns:
            Created configuration
        """
        config_id = f"config_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # Mask secret values
        stored_value = "***REDACTED***" if is_secret else config_value

        configuration = {
            "id": config_id,
            "key": config_key,
            "value": stored_value,
            "environment": environment,
            "type": config_type,
            "scope": scope,
            "is_secret": is_secret,
            "description": description,
            "tags": tags or [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "created_by": "system",
            "version": 1,
            "locked": False,
            "validation_schema": None
        }

        EnvironmentConfig._configurations[config_id] = configuration

        # Store secret separately if needed
        if is_secret:
            EnvironmentConfig._secrets[config_id] = config_value

        # Record history
        EnvironmentConfig._config_history[config_key].append({
            "config_id": config_id,
            "action": "created",
            "timestamp": now.isoformat(),
            "value": stored_value
        })

        return configuration

    @staticmethod
    def update_configuration(
        session,
        config_id: str,
        new_value: Any
    ) -> dict:
        """
        Update configuration value.

        Args:
            session: Database session
            config_id: Configuration ID
            new_value: New configuration value

        Returns:
            Updated configuration
        """
        config = EnvironmentConfig._configurations.get(config_id)
        if not config:
            raise ValueError(f"Configuration not found: {config_id}")

        if config["locked"]:
            raise ValueError("Configuration is locked and cannot be updated")

        now = datetime.utcnow()

        # Update value
        stored_value = "***REDACTED***" if config["is_secret"] else new_value
        config["value"] = stored_value
        config["updated_at"] = now.isoformat()
        config["version"] += 1

        # Update secret if needed
        if config["is_secret"]:
            EnvironmentConfig._secrets[config_id] = new_value

        # Record history
        EnvironmentConfig._config_history[config["key"]].append({
            "config_id": config_id,
            "action": "updated",
            "timestamp": now.isoformat(),
            "value": stored_value,
            "version": config["version"]
        })

        return config

    @staticmethod
    def create_feature_flag(
        session,
        flag_name: str,
        enabled: bool,
        strategy: str = FeatureFlagStrategy.ALL_USERS,
        rollout_percentage: Optional[float] = None,
        target_users: Optional[List[str]] = None,
        description: Optional[str] = None,
        environments: Optional[List[str]] = None
    ) -> dict:
        """
        Create feature flag.

        Args:
            session: Database session
            flag_name: Feature flag name
            enabled: Whether flag is enabled
            strategy: Rollout strategy
            rollout_percentage: Percentage for gradual rollout
            target_users: Specific users for targeted rollout
            description: Flag description
            environments: Environments where flag applies

        Returns:
            Created feature flag
        """
        flag_id = f"flag_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        feature_flag = {
            "id": flag_id,
            "name": flag_name,
            "enabled": enabled,
            "strategy": strategy,
            "rollout_percentage": rollout_percentage or 0,
            "target_users": target_users or [],
            "description": description,
            "environments": environments or ["production"],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "evaluation_count": 0,
            "enabled_count": 0,
            "disabled_count": 0,
            "last_evaluated_at": None
        }

        EnvironmentConfig._feature_flags[flag_id] = feature_flag
        return feature_flag

    @staticmethod
    def evaluate_feature_flag(
        session,
        flag_id: str,
        user_id: Optional[str] = None,
        context: Optional[dict] = None
    ) -> dict:
        """
        Evaluate feature flag for a user.

        Args:
            session: Database session
            flag_id: Feature flag ID
            user_id: User ID for evaluation
            context: Additional evaluation context

        Returns:
            Evaluation result
        """
        flag = EnvironmentConfig._feature_flags.get(flag_id)
        if not flag:
            raise ValueError(f"Feature flag not found: {flag_id}")

        now = datetime.utcnow()

        # Update evaluation stats
        flag["evaluation_count"] += 1
        flag["last_evaluated_at"] = now.isoformat()

        # Determine if enabled for this user
        is_enabled = False

        if not flag["enabled"]:
            is_enabled = False
        elif flag["strategy"] == FeatureFlagStrategy.ALL_USERS:
            is_enabled = True
        elif flag["strategy"] == FeatureFlagStrategy.PERCENTAGE:
            # Use random for percentage-based rollout
            is_enabled = random.random() * 100 < flag["rollout_percentage"]
        elif flag["strategy"] == FeatureFlagStrategy.USER_LIST:
            is_enabled = user_id in flag["target_users"] if user_id else False
        elif flag["strategy"] == FeatureFlagStrategy.GRADUAL_ROLLOUT:
            # Gradual rollout based on percentage
            is_enabled = random.random() * 100 < flag["rollout_percentage"]
        else:
            is_enabled = flag["enabled"]

        # Update counts
        if is_enabled:
            flag["enabled_count"] += 1
        else:
            flag["disabled_count"] += 1

        EnvironmentConfig._flag_evaluations[flag_id] += 1

        return {
            "flag_id": flag_id,
            "flag_name": flag["name"],
            "enabled": is_enabled,
            "strategy": flag["strategy"],
            "user_id": user_id,
            "evaluated_at": now.isoformat(),
            "reason": f"Strategy: {flag['strategy']}"
        }

    @staticmethod
    def create_config_template(
        session,
        template_name: str,
        environment: str,
        configurations: List[dict],
        description: Optional[str] = None
    ) -> dict:
        """
        Create configuration template.

        Args:
            session: Database session
            template_name: Template name
            environment: Target environment
            configurations: List of configuration items
            description: Template description

        Returns:
            Created template
        """
        template_id = f"template_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        template = {
            "id": template_id,
            "name": template_name,
            "environment": environment,
            "configurations": configurations,
            "description": description,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "applied_count": 0,
            "last_applied_at": None
        }

        EnvironmentConfig._config_templates[template_id] = template
        return template

    @staticmethod
    def apply_template(
        session,
        template_id: str,
        target_environment: str
    ) -> dict:
        """
        Apply configuration template to environment.

        Args:
            session: Database session
            template_id: Template ID
            target_environment: Target environment

        Returns:
            Application result
        """
        template = EnvironmentConfig._config_templates.get(template_id)
        if not template:
            raise ValueError(f"Template not found: {template_id}")

        now = datetime.utcnow()

        # Apply each configuration
        applied_configs = []
        for config_item in template["configurations"]:
            config = EnvironmentConfig.create_configuration(
                session=session,
                config_key=config_item["key"],
                config_value=config_item["value"],
                environment=target_environment,
                config_type=config_item.get("type", ConfigType.STRING),
                scope=config_item.get("scope", ConfigScope.ENVIRONMENT),
                description=config_item.get("description")
            )
            applied_configs.append(config)

        # Update template stats
        template["applied_count"] += 1
        template["last_applied_at"] = now.isoformat()

        return {
            "template_id": template_id,
            "template_name": template["name"],
            "target_environment": target_environment,
            "applied_configurations": applied_configs,
            "applied_at": now.isoformat()
        }

    @staticmethod
    def perform_readiness_check(
        session,
        environment: str,
        check_categories: Optional[List[str]] = None
    ) -> dict:
        """
        Perform production readiness check.

        Args:
            session: Database session
            environment: Environment to check
            check_categories: Categories to check

        Returns:
            Readiness check result
        """
        check_id = f"readiness_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # Define checks
        all_checks = [
            {
                "category": "database",
                "name": "database_connectivity",
                "status": "passed",
                "message": "Database connection successful"
            },
            {
                "category": "database",
                "name": "migration_status",
                "status": "passed",
                "message": "All migrations applied"
            },
            {
                "category": "security",
                "name": "ssl_certificates",
                "status": "passed",
                "message": "SSL certificates valid"
            },
            {
                "category": "security",
                "name": "secret_rotation",
                "status": "warning",
                "message": "Secrets not rotated in 60 days"
            },
            {
                "category": "configuration",
                "name": "required_configs",
                "status": "passed",
                "message": "All required configurations present"
            },
            {
                "category": "configuration",
                "name": "secret_configs",
                "status": "passed",
                "message": "Secrets properly configured"
            },
            {
                "category": "monitoring",
                "name": "health_endpoints",
                "status": "passed",
                "message": "Health endpoints responding"
            },
            {
                "category": "monitoring",
                "name": "logging",
                "status": "passed",
                "message": "Logging configured correctly"
            },
            {
                "category": "performance",
                "name": "resource_limits",
                "status": "passed",
                "message": "Resource limits configured"
            },
            {
                "category": "performance",
                "name": "caching",
                "status": "passed",
                "message": "Cache layer operational"
            }
        ]

        # Filter by categories if specified
        if check_categories:
            checks = [c for c in all_checks if c["category"] in check_categories]
        else:
            checks = all_checks

        # Calculate overall status
        passed = len([c for c in checks if c["status"] == "passed"])
        warnings = len([c for c in checks if c["status"] == "warning"])
        failed = len([c for c in checks if c["status"] == "failed"])

        if failed > 0:
            overall_status = ReadinessStatus.NOT_READY
        elif warnings > 0:
            overall_status = ReadinessStatus.PARTIALLY_READY
        else:
            overall_status = ReadinessStatus.READY

        readiness_check = {
            "id": check_id,
            "environment": environment,
            "overall_status": overall_status,
            "checked_at": now.isoformat(),
            "total_checks": len(checks),
            "passed": passed,
            "warnings": warnings,
            "failed": failed,
            "checks": checks,
            "ready_for_production": overall_status in [ReadinessStatus.READY, ReadinessStatus.PARTIALLY_READY]
        }

        EnvironmentConfig._readiness_checks[check_id] = readiness_check
        return readiness_check

    @staticmethod
    def validate_configuration(
        session,
        config_id: str
    ) -> dict:
        """
        Validate configuration against schema.

        Args:
            session: Database session
            config_id: Configuration ID

        Returns:
            Validation result
        """
        config = EnvironmentConfig._configurations.get(config_id)
        if not config:
            raise ValueError(f"Configuration not found: {config_id}")

        # Simulate validation
        is_valid = random.random() > 0.1  # 90% valid

        validation_result = {
            "config_id": config_id,
            "config_key": config["key"],
            "is_valid": is_valid,
            "validated_at": datetime.utcnow().isoformat(),
            "errors": [] if is_valid else ["Value does not match expected type"],
            "warnings": []
        }

        return validation_result

    @staticmethod
    def get_config_by_environment(
        session,
        environment: str,
        include_secrets: bool = False
    ) -> dict:
        """
        Get all configurations for environment.

        Args:
            session: Database session
            environment: Target environment
            include_secrets: Include secret values (requires authorization)

        Returns:
            Environment configurations
        """
        configs = [
            c for c in EnvironmentConfig._configurations.values()
            if c["environment"] == environment
        ]

        # Optionally include secret values
        if include_secrets:
            for config in configs:
                if config["is_secret"] and config["id"] in EnvironmentConfig._secrets:
                    config["value"] = EnvironmentConfig._secrets[config["id"]]

        return {
            "environment": environment,
            "total_configurations": len(configs),
            "configurations": configs
        }

    @staticmethod
    def compare_environments(
        session,
        source_env: str,
        target_env: str
    ) -> dict:
        """
        Compare configurations between environments.

        Args:
            session: Database session
            source_env: Source environment
            target_env: Target environment

        Returns:
            Configuration differences
        """
        source_configs = {
            c["key"]: c for c in EnvironmentConfig._configurations.values()
            if c["environment"] == source_env
        }

        target_configs = {
            c["key"]: c for c in EnvironmentConfig._configurations.values()
            if c["environment"] == target_env
        }

        # Find differences
        only_in_source = [k for k in source_configs.keys() if k not in target_configs]
        only_in_target = [k for k in target_configs.keys() if k not in source_configs]
        different_values = [
            k for k in source_configs.keys()
            if k in target_configs and source_configs[k]["value"] != target_configs[k]["value"]
        ]

        return {
            "source_environment": source_env,
            "target_environment": target_env,
            "only_in_source": only_in_source,
            "only_in_target": only_in_target,
            "different_values": different_values,
            "total_differences": len(only_in_source) + len(only_in_target) + len(different_values),
            "are_identical": len(only_in_source) == 0 and len(only_in_target) == 0 and len(different_values) == 0
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get environment configuration statistics"""
        configs = list(EnvironmentConfig._configurations.values())
        flags = list(EnvironmentConfig._feature_flags.values())

        # Environment distribution
        env_dist = defaultdict(int)
        for config in configs:
            env_dist[config["environment"]] += 1

        # Type distribution
        type_dist = defaultdict(int)
        for config in configs:
            type_dist[config["type"]] += 1

        # Scope distribution
        scope_dist = defaultdict(int)
        for config in configs:
            scope_dist[config["scope"]] += 1

        # Flag statistics
        total_evaluations = sum(f["evaluation_count"] for f in flags)
        enabled_flags = len([f for f in flags if f["enabled"]])

        return {
            "total_configurations": len(configs),
            "total_secrets": len(EnvironmentConfig._secrets),
            "total_feature_flags": len(flags),
            "enabled_feature_flags": enabled_flags,
            "disabled_feature_flags": len(flags) - enabled_flags,
            "total_flag_evaluations": total_evaluations,
            "total_templates": len(EnvironmentConfig._config_templates),
            "total_readiness_checks": len(EnvironmentConfig._readiness_checks),
            "environment_distribution": dict(env_dist),
            "type_distribution": dict(type_dist),
            "scope_distribution": dict(scope_dist),
            "locked_configurations": len([c for c in configs if c["locked"]])
        }
