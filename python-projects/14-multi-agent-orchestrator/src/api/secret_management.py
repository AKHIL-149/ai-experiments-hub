"""
Secret Management API

REST API endpoints for secure secret storage and management.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.secret_management import (
    SecretManagement,
    SecretType,
    SecretStatus,
    VaultProvider
)


router = APIRouter()


# Request/Response Models
class CreateSecretRequest(BaseModel):
    name: str = Field(..., description="Secret name/identifier")
    secret_data: dict = Field(..., description="Secret data to store")
    secret_type: str = Field(..., description="Type of secret")
    description: Optional[str] = Field(None, description="Secret description")
    tags: Optional[List[str]] = Field(None, description="Tags for categorization")
    rotation_days: Optional[int] = Field(None, description="Days until rotation required")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class UpdateSecretRequest(BaseModel):
    secret_data: dict = Field(..., description="New secret data")
    description: Optional[str] = Field(None, description="Updated description")
    metadata: Optional[dict] = Field(None, description="Updated metadata")


class RotateSecretRequest(BaseModel):
    new_secret_data: dict = Field(..., description="New secret data")
    actor: Optional[str] = Field(None, description="User/system performing rotation")


class RevokeSecretRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Revocation reason")
    actor: Optional[str] = Field(None, description="User/system revoking")


class CreateLeaseRequest(BaseModel):
    lease_duration_seconds: int = Field(..., description="Lease duration in seconds")
    accessor: str = Field(..., description="User/system accessing")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class RenewLeaseRequest(BaseModel):
    additional_seconds: int = Field(..., description="Additional time to add")


class CreateRotationPolicyRequest(BaseModel):
    name: str = Field(..., description="Policy name")
    secret_name_pattern: str = Field(..., description="Pattern to match secret names")
    rotation_days: int = Field(..., description="Days between rotations")
    auto_rotate: bool = Field(True, description="Whether to auto-rotate")
    notification_days_before: int = Field(7, description="Days before rotation to notify")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


@router.post("/secrets")
def create_secret(
    request: CreateSecretRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a secret.

    Creates a new secret with encryption and optional rotation policy.
    """
    try:
        secret = SecretManagement.create_secret(
            session=session,
            name=request.name,
            secret_data=request.secret_data,
            secret_type=request.secret_type,
            description=request.description,
            tags=request.tags,
            rotation_days=request.rotation_days,
            metadata=request.metadata
        )

        # Remove encrypted data from response
        response_secret = {k: v for k, v in secret.items() if k != "encrypted_data"}

        return {
            "success": True,
            "secret": response_secret,
            "message": f"Secret created: {secret['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/secrets/{secret_id}")
def get_secret(
    secret_id: str,
    decrypt: bool = True,
    actor: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get a secret by ID.

    Returns the secret with optional decryption. Access is logged.
    """
    try:
        secret = SecretManagement.get_secret(
            session=session,
            secret_id=secret_id,
            decrypt=decrypt,
            actor=actor
        )

        return {
            "success": True,
            "secret": secret
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/secrets/name/{name}")
def get_secret_by_name(
    name: str,
    version: Optional[int] = None,
    decrypt: bool = True,
    actor: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get a secret by name.

    Returns the latest active version or a specific version if requested.
    """
    try:
        secret = SecretManagement.get_secret_by_name(
            session=session,
            name=name,
            version=version,
            decrypt=decrypt,
            actor=actor
        )

        return {
            "success": True,
            "secret": secret
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/secrets/{secret_id}")
def update_secret(
    secret_id: str,
    request: UpdateSecretRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update a secret.

    Updates a secret by creating a new version and marking the old one as rotated.
    """
    try:
        secret = SecretManagement.update_secret(
            session=session,
            secret_id=secret_id,
            secret_data=request.secret_data,
            description=request.description,
            metadata=request.metadata
        )

        # Remove encrypted data from response
        response_secret = {k: v for k, v in secret.items() if k != "encrypted_data"}

        return {
            "success": True,
            "secret": response_secret,
            "message": f"Secret updated to version {secret['version']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/secrets/{secret_id}/rotate")
def rotate_secret(
    secret_id: str,
    request: RotateSecretRequest,
    session: Session = Depends(get_db_session)
):
    """
    Rotate a secret.

    Creates a new version with new secret data and marks the old one as rotated.
    """
    try:
        secret = SecretManagement.rotate_secret(
            session=session,
            secret_id=secret_id,
            new_secret_data=request.new_secret_data,
            actor=request.actor
        )

        # Remove encrypted data from response
        response_secret = {k: v for k, v in secret.items() if k != "encrypted_data"}

        return {
            "success": True,
            "secret": response_secret,
            "message": f"Secret rotated to version {secret['version']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/secrets/{secret_id}/revoke")
def revoke_secret(
    secret_id: str,
    request: RevokeSecretRequest,
    session: Session = Depends(get_db_session)
):
    """
    Revoke a secret.

    Marks the secret as revoked, preventing further access.
    """
    try:
        secret = SecretManagement.revoke_secret(
            session=session,
            secret_id=secret_id,
            reason=request.reason,
            actor=request.actor
        )

        # Remove encrypted data from response
        response_secret = {k: v for k, v in secret.items() if k != "encrypted_data"}

        return {
            "success": True,
            "secret": response_secret,
            "message": "Secret revoked"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/secrets")
def list_secrets(
    secret_type: Optional[str] = None,
    status: Optional[str] = None,
    tags: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    List secrets.

    Returns secrets with optional filtering by type, status, and tags.
    Encrypted data is not included in the list view.
    """
    try:
        # Parse tags if provided
        tag_list = tags.split(",") if tags else None

        result = SecretManagement.list_secrets(
            session=session,
            secret_type=secret_type,
            status=status,
            tags=tag_list,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/secrets/{secret_id}/leases")
def create_lease(
    secret_id: str,
    request: CreateLeaseRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a lease.

    Creates a time-limited lease for accessing a secret.
    """
    try:
        lease = SecretManagement.create_lease(
            session=session,
            secret_id=secret_id,
            lease_duration_seconds=request.lease_duration_seconds,
            accessor=request.accessor,
            metadata=request.metadata
        )

        return {
            "success": True,
            "lease": lease,
            "message": f"Lease created for {request.lease_duration_seconds} seconds"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/leases/{lease_id}/renew")
def renew_lease(
    lease_id: str,
    request: RenewLeaseRequest,
    session: Session = Depends(get_db_session)
):
    """
    Renew a lease.

    Extends the lease duration by adding additional time.
    """
    try:
        lease = SecretManagement.renew_lease(
            session=session,
            lease_id=lease_id,
            additional_seconds=request.additional_seconds
        )

        return {
            "success": True,
            "lease": lease,
            "message": f"Lease renewed for {request.additional_seconds} additional seconds"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rotation-policies")
def create_rotation_policy(
    request: CreateRotationPolicyRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a rotation policy.

    Defines automatic rotation rules for secrets matching a pattern.
    """
    try:
        policy = SecretManagement.create_rotation_policy(
            session=session,
            name=request.name,
            secret_name_pattern=request.secret_name_pattern,
            rotation_days=request.rotation_days,
            auto_rotate=request.auto_rotate,
            notification_days_before=request.notification_days_before,
            metadata=request.metadata
        )

        return {
            "success": True,
            "policy": policy,
            "message": f"Rotation policy created: {policy['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/secrets/{secret_id}/access-log")
def get_secret_access_log(
    secret_id: str,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    Get secret access log.

    Returns the access history for a secret.
    """
    try:
        result = SecretManagement.get_secret_access_log(
            session=session,
            secret_id=secret_id,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get secret management statistics.

    Returns aggregate metrics including secret counts, status distribution,
    and rotation status.
    """
    try:
        stats = SecretManagement.get_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/secret-types")
def list_secret_types():
    """
    List all secret types.

    Returns all available secret types and their descriptions.
    """
    return {
        "success": True,
        "secret_types": [
            {"type": SecretType.API_KEY, "description": "API keys and tokens"},
            {"type": SecretType.DATABASE_CREDENTIAL, "description": "Database credentials"},
            {"type": SecretType.CERTIFICATE, "description": "SSL/TLS certificates"},
            {"type": SecretType.TOKEN, "description": "Authentication tokens"},
            {"type": SecretType.SSH_KEY, "description": "SSH private keys"},
            {"type": SecretType.WEBHOOK_SECRET, "description": "Webhook secrets"},
            {"type": SecretType.ENCRYPTION_KEY, "description": "Encryption keys"},
            {"type": SecretType.CUSTOM, "description": "Custom secrets"}
        ]
    }


@router.get("/statuses")
def list_secret_statuses():
    """
    List all secret statuses.

    Returns all possible secret lifecycle statuses.
    """
    return {
        "success": True,
        "statuses": [
            {"status": SecretStatus.ACTIVE, "description": "Active - currently in use"},
            {"status": SecretStatus.ROTATED, "description": "Rotated - replaced by newer version"},
            {"status": SecretStatus.EXPIRED, "description": "Expired - past expiration date"},
            {"status": SecretStatus.REVOKED, "description": "Revoked - access denied"},
            {"status": SecretStatus.PENDING_DELETION, "description": "Pending deletion"}
        ]
    }


@router.get("/vault-providers")
def list_vault_providers():
    """
    List all vault providers.

    Returns all supported vault backend providers.
    """
    return {
        "success": True,
        "providers": [
            {"provider": VaultProvider.IN_MEMORY, "description": "In-memory storage (development)"},
            {"provider": VaultProvider.HASHICORP_VAULT, "description": "HashiCorp Vault"},
            {"provider": VaultProvider.AWS_SECRETS_MANAGER, "description": "AWS Secrets Manager"},
            {"provider": VaultProvider.AZURE_KEY_VAULT, "description": "Azure Key Vault"},
            {"provider": VaultProvider.GCP_SECRET_MANAGER, "description": "GCP Secret Manager"}
        ]
    }
