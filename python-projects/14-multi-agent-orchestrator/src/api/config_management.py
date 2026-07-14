"""
Configuration Management API

REST API endpoints for centralized configuration management with versioning.
"""

from typing import Optional, Union
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.config_management import (
    ConfigManagement,
    ConfigEnvironment,
    ConfigType,
    ConfigStatus
)


router = APIRouter()


# Request/Response Models
class CreateConfigurationRequest(BaseModel):
    key: str = Field(..., description="Configuration key")
    value: Union[dict, str, int, float, bool] = Field(..., description="Configuration value")
    config_type: str = Field(..., description="Type of configuration")
    environment: str = Field(ConfigEnvironment.DEVELOPMENT, description="Target environment")
    description: Optional[str] = Field(None, description="Configuration description")
    encrypted: bool = Field(False, description="Whether value should be encrypted")
    validation_schema: Optional[dict] = Field(None, description="JSON schema for validation")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class UpdateConfigurationRequest(BaseModel):
    value: Optional[Union[dict, str, int, float, bool]] = Field(None, description="New value")
    description: Optional[str] = Field(None, description="Updated description")
    metadata: Optional[dict] = Field(None, description="Updated metadata")


class RollbackConfigurationRequest(BaseModel):
    target_version: int = Field(..., description="Version to rollback to")
    environment: str = Field(ConfigEnvironment.DEVELOPMENT, description="Environment")


class CreateTemplateRequest(BaseModel):
    name: str = Field(..., description="Template name")
    template_data: dict = Field(..., description="Template structure")
    description: Optional[str] = Field(None, description="Template description")


@router.post("/configurations")
def create_configuration(
    request: CreateConfigurationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a configuration.

    Creates a new configuration with optional validation, encryption,
    and versioning support.
    """
    try:
        config = ConfigManagement.create_configuration(
            session=session,
            key=request.key,
            value=request.value,
            config_type=request.config_type,
            environment=request.environment,
            description=request.description,
            encrypted=request.encrypted,
            validation_schema=request.validation_schema,
            metadata=request.metadata
        )

        return {
            "success": True,
            "configuration": config,
            "message": f"Configuration created: {config['id']}"
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
    Update a configuration.

    Updates a configuration by creating a new version and marking
    the old version as deprecated.
    """
    try:
        config = ConfigManagement.update_configuration(
            session=session,
            config_id=config_id,
            value=request.value,
            description=request.description,
            metadata=request.metadata
        )

        return {
            "success": True,
            "configuration": config,
            "message": f"Configuration updated to version {config['version']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configurations/{config_id}/activate")
def activate_configuration(
    config_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Activate a configuration.

    Activates a configuration version, making it the active version
    for its environment and key.
    """
    try:
        config = ConfigManagement.activate_configuration(
            session=session,
            config_id=config_id
        )

        return {
            "success": True,
            "configuration": config,
            "message": f"Configuration activated in {config['environment']} environment"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configurations")
def list_configurations(
    config_type: Optional[str] = None,
    environment: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    List configurations.

    Returns configurations with optional filtering by type,
    environment, and status.
    """
    try:
        result = ConfigManagement.list_configurations(
            session=session,
            config_type=config_type,
            environment=environment,
            status=status,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configurations/{config_id}")
def get_configuration_by_id(
    config_id: str,
    decrypt: bool = True,
    session: Session = Depends(get_db_session)
):
    """
    Get configuration by ID.

    Returns a specific configuration version by its ID,
    with optional decryption of encrypted values.
    """
    try:
        config = ConfigManagement.get_configuration_by_id(
            session=session,
            config_id=config_id,
            decrypt=decrypt
        )

        return {
            "success": True,
            "configuration": config
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configurations/key/{key}")
def get_configuration_by_key(
    key: str,
    environment: str = ConfigEnvironment.DEVELOPMENT,
    decrypt: bool = True,
    session: Session = Depends(get_db_session)
):
    """
    Get active configuration by key.

    Returns the currently active configuration for the specified
    key and environment.
    """
    try:
        config = ConfigManagement.get_configuration(
            session=session,
            key=key,
            environment=environment,
            decrypt=decrypt
        )

        return {
            "success": True,
            "configuration": config
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/configurations/{key}/history")
def get_configuration_history(
    key: str,
    session: Session = Depends(get_db_session)
):
    """
    Get configuration history.

    Returns all versions and change history for a configuration key.
    """
    try:
        result = ConfigManagement.get_configuration_history(
            session=session,
            key=key
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/configurations/{key}/rollback")
def rollback_configuration(
    key: str,
    request: RollbackConfigurationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Rollback configuration.

    Creates a new version based on a previous version,
    effectively rolling back changes.
    """
    try:
        config = ConfigManagement.rollback_configuration(
            session=session,
            key=key,
            target_version=request.target_version,
            environment=request.environment
        )

        return {
            "success": True,
            "configuration": config,
            "message": f"Configuration rolled back to version {request.target_version}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates")
def create_template(
    request: CreateTemplateRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a configuration template.

    Creates a reusable configuration template for standardizing
    configuration structure.
    """
    try:
        template = ConfigManagement.create_template(
            session=session,
            name=request.name,
            template_data=request.template_data,
            description=request.description
        )

        return {
            "success": True,
            "template": template,
            "message": f"Template created: {template['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export")
def export_configurations(
    environment: Optional[str] = None,
    config_type: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Export configurations.

    Exports configurations for backup, migration, or documentation
    purposes with optional filtering.
    """
    try:
        export = ConfigManagement.export_configurations(
            session=session,
            environment=environment,
            config_type=config_type
        )

        return {
            "success": True,
            "export": export,
            "message": f"Exported {export['config_count']} configurations"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get configuration management statistics.

    Returns aggregate metrics including total configs, status
    distribution, and environment distribution.
    """
    try:
        stats = ConfigManagement.get_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/environments")
def list_environments():
    """
    List all environments.

    Returns all available configuration environments.
    """
    return {
        "success": True,
        "environments": [
            {"environment": ConfigEnvironment.DEVELOPMENT, "description": "Development environment"},
            {"environment": ConfigEnvironment.STAGING, "description": "Staging environment"},
            {"environment": ConfigEnvironment.PRODUCTION, "description": "Production environment"},
            {"environment": ConfigEnvironment.TEST, "description": "Test environment"}
        ]
    }


@router.get("/types")
def list_config_types():
    """
    List all configuration types.

    Returns all available configuration types and their descriptions.
    """
    return {
        "success": True,
        "config_types": [
            {"type": ConfigType.SYSTEM, "description": "System-level configuration"},
            {"type": ConfigType.AGENT, "description": "Agent-specific configuration"},
            {"type": ConfigType.WORKFLOW, "description": "Workflow configuration"},
            {"type": ConfigType.LLM, "description": "LLM provider configuration"},
            {"type": ConfigType.SECURITY, "description": "Security and authentication configuration"},
            {"type": ConfigType.INTEGRATION, "description": "Third-party integration configuration"},
            {"type": ConfigType.CUSTOM, "description": "Custom configuration"}
        ]
    }


@router.get("/statuses")
def list_config_statuses():
    """
    List all configuration statuses.

    Returns all possible configuration lifecycle statuses.
    """
    return {
        "success": True,
        "statuses": [
            {"status": ConfigStatus.DRAFT, "description": "Draft - not yet activated"},
            {"status": ConfigStatus.ACTIVE, "description": "Active - currently in use"},
            {"status": ConfigStatus.DEPRECATED, "description": "Deprecated - replaced by newer version"},
            {"status": ConfigStatus.ARCHIVED, "description": "Archived - no longer in use"}
        ]
    }
