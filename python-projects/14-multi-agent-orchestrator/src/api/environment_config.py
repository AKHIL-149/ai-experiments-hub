"""
Environment Configuration and Feature Flags API

REST API endpoints for environment configuration management and feature flags.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.environment_config import (
    EnvironmentConfig,
    ConfigScope,
    FeatureFlagStrategy,
    ConfigType,
    ReadinessStatus
)


router = APIRouter()


# Request/Response Models
class CreateConfigurationRequest(BaseModel):
    config_key: str = Field(..., description="Configuration key")
    config_value: str = Field(..., description="Configuration value")
    environment: str = Field(..., description="Target environment")
    config_type: str = Field(ConfigType.STRING, description="Configuration type")
    scope: str = Field(ConfigScope.ENVIRONMENT, description="Configuration scope")
    is_secret: bool = Field(False, description="Whether value is sensitive")
    description: Optional[str] = Field(None, description="Configuration description")
    tags: Optional[List[str]] = Field(None, description="Configuration tags")


class UpdateConfigurationRequest(BaseModel):
    new_value: str = Field(..., description="New configuration value")


class CreateFeatureFlagRequest(BaseModel):
    flag_name: str = Field(..., description="Feature flag name")
    enabled: bool = Field(..., description="Whether flag is enabled")
    strategy: str = Field(FeatureFlagStrategy.ALL_USERS, description="Rollout strategy")
    rollout_percentage: Optional[float] = Field(None, description="Percentage for gradual rollout", ge=0, le=100)
    target_users: Optional[List[str]] = Field(None, description="Specific users for targeted rollout")
    description: Optional[str] = Field(None, description="Flag description")
    environments: Optional[List[str]] = Field(None, description="Environments where flag applies")


class EvaluateFeatureFlagRequest(BaseModel):
    user_id: Optional[str] = Field(None, description="User ID for evaluation")
    context: Optional[dict] = Field(None, description="Additional evaluation context")


class CreateTemplateRequest(BaseModel):
    template_name: str = Field(..., description="Template name")
    environment: str = Field(..., description="Target environment")
    configurations: List[dict] = Field(..., description="List of configuration items")
    description: Optional[str] = Field(None, description="Template description")


class ApplyTemplateRequest(BaseModel):
    target_environment: str = Field(..., description="Target environment")


@router.post("/configurations")
def create_configuration(
    request: CreateConfigurationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create configuration entry.

    Creates a new configuration entry for the specified environment
    with optional secret handling.
    """
    try:
        config = EnvironmentConfig.create_configuration(
            session=session,
            config_key=request.config_key,
            config_value=request.config_value,
            environment=request.environment,
            config_type=request.config_type,
            scope=request.scope,
            is_secret=request.is_secret,
            description=request.description,
            tags=request.tags
        )

        return {
            "success": True,
            "configuration": config,
            "message": f"Configuration created: {config['key']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/configurations/{config_id}")
def update_configuration(
    config_id: str,
    request: UpdateConfigurationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update configuration value.

    Updates an existing configuration with a new value
    and increments the version number.
    """
    try:
        config = EnvironmentConfig.update_configuration(
            session=session,
            config_id=config_id,
            new_value=request.new_value
        )

        return {
            "success": True,
            "configuration": config,
            "message": f"Configuration updated to version {config['version']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feature-flags")
def create_feature_flag(
    request: CreateFeatureFlagRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create feature flag.

    Creates a new feature flag with the specified rollout strategy
    and targeting rules.
    """
    try:
        flag = EnvironmentConfig.create_feature_flag(
            session=session,
            flag_name=request.flag_name,
            enabled=request.enabled,
            strategy=request.strategy,
            rollout_percentage=request.rollout_percentage,
            target_users=request.target_users,
            description=request.description,
            environments=request.environments
        )

        return {
            "success": True,
            "feature_flag": flag,
            "message": f"Feature flag created: {flag['name']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feature-flags/{flag_id}/evaluate")
def evaluate_feature_flag(
    flag_id: str,
    request: EvaluateFeatureFlagRequest,
    session: Session = Depends(get_db_session)
):
    """
    Evaluate feature flag for a user.

    Evaluates whether the feature flag is enabled for the specified
    user based on the rollout strategy.
    """
    try:
        result = EnvironmentConfig.evaluate_feature_flag(
            session=session,
            flag_id=flag_id,
            user_id=request.user_id,
            context=request.context
        )

        return {
            "success": True,
            "evaluation": result
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates")
def create_config_template(
    request: CreateTemplateRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create configuration template.

    Creates a reusable template containing multiple configuration
    entries that can be applied to different environments.
    """
    try:
        template = EnvironmentConfig.create_config_template(
            session=session,
            template_name=request.template_name,
            environment=request.environment,
            configurations=request.configurations,
            description=request.description
        )

        return {
            "success": True,
            "template": template,
            "message": f"Template created: {template['name']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/{template_id}/apply")
def apply_template(
    template_id: str,
    request: ApplyTemplateRequest,
    session: Session = Depends(get_db_session)
):
    """
    Apply configuration template to environment.

    Applies all configurations from a template to the
    specified target environment.
    """
    try:
        result = EnvironmentConfig.apply_template(
            session=session,
            template_id=template_id,
            target_environment=request.target_environment
        )

        return {
            "success": True,
            "result": result,
            "message": f"Template applied to {request.target_environment}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/readiness/{environment}")
def perform_readiness_check(
    environment: str,
    check_categories: Optional[List[str]] = None,
    session: Session = Depends(get_db_session)
):
    """
    Perform production readiness check.

    Runs comprehensive checks to verify the environment
    is ready for production deployment.
    """
    try:
        check_result = EnvironmentConfig.perform_readiness_check(
            session=session,
            environment=environment,
            check_categories=check_categories
        )

        return {
            "success": True,
            "readiness_check": check_result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configurations/{config_id}/validate")
def validate_configuration(
    config_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Validate configuration against schema.

    Validates that the configuration value matches
    the expected type and format.
    """
    try:
        validation = EnvironmentConfig.validate_configuration(
            session=session,
            config_id=config_id
        )

        return {
            "success": True,
            "validation": validation
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/environments/{environment}/configurations")
def get_config_by_environment(
    environment: str,
    include_secrets: bool = False,
    session: Session = Depends(get_db_session)
):
    """
    Get all configurations for environment.

    Returns all configuration entries for the specified
    environment with optional secret values.
    """
    try:
        result = EnvironmentConfig.get_config_by_environment(
            session=session,
            environment=environment,
            include_secrets=include_secrets
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/environments/compare")
def compare_environments(
    source_env: str,
    target_env: str,
    session: Session = Depends(get_db_session)
):
    """
    Compare configurations between environments.

    Compares configuration keys and values between two
    environments and returns the differences.
    """
    try:
        comparison = EnvironmentConfig.compare_environments(
            session=session,
            source_env=source_env,
            target_env=target_env
        )

        return {
            "success": True,
            "comparison": comparison
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get environment configuration statistics.

    Returns aggregate statistics including configuration counts,
    feature flag usage, and environment distribution.
    """
    try:
        stats = EnvironmentConfig.get_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config-types")
def list_config_types():
    """
    List all configuration types.

    Returns all available configuration type options.
    """
    return {
        "success": True,
        "config_types": [
            {"type": ConfigType.STRING, "description": "String value"},
            {"type": ConfigType.INTEGER, "description": "Integer value"},
            {"type": ConfigType.FLOAT, "description": "Floating point value"},
            {"type": ConfigType.BOOLEAN, "description": "Boolean value (true/false)"},
            {"type": ConfigType.JSON, "description": "JSON object"},
            {"type": ConfigType.SECRET, "description": "Sensitive/encrypted value"}
        ]
    }


@router.get("/config-scopes")
def list_config_scopes():
    """
    List all configuration scopes.

    Returns all available configuration scope options.
    """
    return {
        "success": True,
        "config_scopes": [
            {"scope": ConfigScope.GLOBAL, "description": "Global configuration"},
            {"scope": ConfigScope.ENVIRONMENT, "description": "Environment-specific"},
            {"scope": ConfigScope.SERVICE, "description": "Service-specific"},
            {"scope": ConfigScope.USER, "description": "User-specific"}
        ]
    }


@router.get("/feature-flag-strategies")
def list_feature_flag_strategies():
    """
    List all feature flag strategies.

    Returns all available feature flag rollout strategies.
    """
    return {
        "success": True,
        "strategies": [
            {"strategy": FeatureFlagStrategy.ALL_USERS, "description": "Enable for all users"},
            {"strategy": FeatureFlagStrategy.PERCENTAGE, "description": "Enable for percentage of users"},
            {"strategy": FeatureFlagStrategy.USER_LIST, "description": "Enable for specific user list"},
            {"strategy": FeatureFlagStrategy.GRADUAL_ROLLOUT, "description": "Gradual percentage-based rollout"},
            {"strategy": FeatureFlagStrategy.A_B_TEST, "description": "A/B testing with two variants"}
        ]
    }
