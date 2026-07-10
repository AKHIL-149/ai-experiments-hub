"""
Secret Management Service

Provides secure storage, rotation, and access control for secrets and credentials.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import uuid
import json
import hashlib
import secrets
import base64


class SecretType:
    """Secret type constants"""
    API_KEY = "api_key"
    DATABASE_CREDENTIAL = "database_credential"
    CERTIFICATE = "certificate"
    TOKEN = "token"
    SSH_KEY = "ssh_key"
    WEBHOOK_SECRET = "webhook_secret"
    ENCRYPTION_KEY = "encryption_key"
    CUSTOM = "custom"


class SecretStatus:
    """Secret status"""
    ACTIVE = "active"
    ROTATED = "rotated"
    EXPIRED = "expired"
    REVOKED = "revoked"
    PENDING_DELETION = "pending_deletion"


class VaultProvider:
    """Vault provider types"""
    IN_MEMORY = "in_memory"
    HASHICORP_VAULT = "hashicorp_vault"
    AWS_SECRETS_MANAGER = "aws_secrets_manager"
    AZURE_KEY_VAULT = "azure_key_vault"
    GCP_SECRET_MANAGER = "gcp_secret_manager"


class SecretManagement:
    """Secret Management service for secure credential storage"""

    # In-memory storage
    _secrets = {}
    _secret_versions = defaultdict(list)
    _secret_leases = {}
    _access_policies = {}
    _rotation_policies = {}
    _access_logs = defaultdict(list)
    _encryption_keys = {}
    _vault_config = {"provider": VaultProvider.IN_MEMORY}

    @staticmethod
    def create_secret(
        session,
        name: str,
        secret_data: dict,
        secret_type: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        rotation_days: Optional[int] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create a secret.

        Args:
            session: Database session
            name: Secret name/identifier
            secret_data: Secret data to store
            secret_type: Type of secret
            description: Secret description
            tags: Tags for categorization
            rotation_days: Days until rotation required
            metadata: Additional metadata

        Returns:
            Created secret
        """
        secret_id = f"secret_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # Encrypt secret data
        encrypted_data = SecretManagement._encrypt_secret(secret_data)

        secret = {
            "id": secret_id,
            "name": name,
            "secret_type": secret_type,
            "description": description,
            "encrypted_data": encrypted_data,
            "tags": tags or [],
            "status": SecretStatus.ACTIVE,
            "version": 1,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "created_by": metadata.get("created_by", "system") if metadata else "system",
            "last_accessed_at": None,
            "access_count": 0,
            "rotation_days": rotation_days,
            "next_rotation_at": (now + timedelta(days=rotation_days)).isoformat() if rotation_days else None,
            "expires_at": None,
            "metadata": metadata or {}
        }

        SecretManagement._secrets[secret_id] = secret
        SecretManagement._secret_versions[name].append(secret)

        # Log creation
        SecretManagement._log_access(
            secret_id=secret_id,
            action="created",
            actor=secret.get("created_by", "system")
        )

        return secret

    @staticmethod
    def get_secret(
        session,
        secret_id: str,
        decrypt: bool = True,
        actor: Optional[str] = None
    ) -> dict:
        """
        Get a secret by ID.

        Args:
            session: Database session
            secret_id: Secret ID
            decrypt: Whether to decrypt the secret
            actor: User/system requesting the secret

        Returns:
            Secret with optional decryption
        """
        secret = SecretManagement._secrets.get(secret_id)
        if not secret:
            raise ValueError(f"Secret not found: {secret_id}")

        if secret["status"] == SecretStatus.REVOKED:
            raise ValueError(f"Secret has been revoked: {secret_id}")

        if secret["status"] == SecretStatus.EXPIRED:
            raise ValueError(f"Secret has expired: {secret_id}")

        # Update access tracking
        now = datetime.utcnow()
        secret["last_accessed_at"] = now.isoformat()
        secret["access_count"] += 1

        # Log access
        SecretManagement._log_access(
            secret_id=secret_id,
            action="accessed",
            actor=actor or "unknown"
        )

        # Return decrypted if requested
        if decrypt:
            decrypted_secret = secret.copy()
            decrypted_secret["secret_data"] = SecretManagement._decrypt_secret(
                secret["encrypted_data"]
            )
            del decrypted_secret["encrypted_data"]
            return decrypted_secret

        return secret

    @staticmethod
    def get_secret_by_name(
        session,
        name: str,
        version: Optional[int] = None,
        decrypt: bool = True,
        actor: Optional[str] = None
    ) -> dict:
        """
        Get a secret by name.

        Args:
            session: Database session
            name: Secret name
            version: Specific version (default: latest active)
            decrypt: Whether to decrypt
            actor: User/system requesting

        Returns:
            Secret
        """
        versions = SecretManagement._secret_versions.get(name, [])
        if not versions:
            raise ValueError(f"No secret found with name: {name}")

        # Get specific version or latest active
        if version:
            target = next((v for v in versions if v["version"] == version), None)
            if not target:
                raise ValueError(f"Version {version} not found for secret: {name}")
        else:
            # Get latest active version
            active_versions = [v for v in versions if v["status"] == SecretStatus.ACTIVE]
            if not active_versions:
                raise ValueError(f"No active version found for secret: {name}")
            target = max(active_versions, key=lambda x: x["version"])

        return SecretManagement.get_secret(
            session=session,
            secret_id=target["id"],
            decrypt=decrypt,
            actor=actor
        )

    @staticmethod
    def update_secret(
        session,
        secret_id: str,
        secret_data: dict,
        description: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Update a secret (creates new version).

        Args:
            session: Database session
            secret_id: Secret to update
            secret_data: New secret data
            description: Updated description
            metadata: Updated metadata

        Returns:
            New secret version
        """
        old_secret = SecretManagement._secrets.get(secret_id)
        if not old_secret:
            raise ValueError(f"Secret not found: {secret_id}")

        now = datetime.utcnow()
        new_secret_id = f"secret_{uuid.uuid4().hex[:12]}"
        new_version = old_secret["version"] + 1

        # Create new version
        new_secret = old_secret.copy()
        new_secret["id"] = new_secret_id
        new_secret["version"] = new_version
        new_secret["encrypted_data"] = SecretManagement._encrypt_secret(secret_data)
        new_secret["updated_at"] = now.isoformat()
        new_secret["access_count"] = 0
        new_secret["last_accessed_at"] = None

        if description:
            new_secret["description"] = description
        if metadata:
            new_secret["metadata"].update(metadata)

        # Update rotation schedule if configured
        if new_secret.get("rotation_days"):
            new_secret["next_rotation_at"] = (
                now + timedelta(days=new_secret["rotation_days"])
            ).isoformat()

        # Store new version
        SecretManagement._secrets[new_secret_id] = new_secret
        SecretManagement._secret_versions[old_secret["name"]].append(new_secret)

        # Mark old version as rotated
        old_secret["status"] = SecretStatus.ROTATED
        old_secret["updated_at"] = now.isoformat()

        # Log rotation
        SecretManagement._log_access(
            secret_id=new_secret_id,
            action="rotated",
            actor=metadata.get("updated_by", "system") if metadata else "system",
            details={"previous_version": old_secret["version"]}
        )

        return new_secret

    @staticmethod
    def rotate_secret(
        session,
        secret_id: str,
        new_secret_data: dict,
        actor: Optional[str] = None
    ) -> dict:
        """
        Rotate a secret.

        Args:
            session: Database session
            secret_id: Secret to rotate
            new_secret_data: New secret data
            actor: User/system performing rotation

        Returns:
            New secret version
        """
        return SecretManagement.update_secret(
            session=session,
            secret_id=secret_id,
            secret_data=new_secret_data,
            metadata={"updated_by": actor or "system", "rotation": True}
        )

    @staticmethod
    def revoke_secret(
        session,
        secret_id: str,
        reason: Optional[str] = None,
        actor: Optional[str] = None
    ) -> dict:
        """
        Revoke a secret.

        Args:
            session: Database session
            secret_id: Secret to revoke
            reason: Revocation reason
            actor: User/system revoking

        Returns:
            Revoked secret
        """
        secret = SecretManagement._secrets.get(secret_id)
        if not secret:
            raise ValueError(f"Secret not found: {secret_id}")

        now = datetime.utcnow()
        secret["status"] = SecretStatus.REVOKED
        secret["updated_at"] = now.isoformat()
        secret["metadata"]["revoked_at"] = now.isoformat()
        secret["metadata"]["revoked_by"] = actor or "system"
        secret["metadata"]["revocation_reason"] = reason

        # Log revocation
        SecretManagement._log_access(
            secret_id=secret_id,
            action="revoked",
            actor=actor or "system",
            details={"reason": reason}
        )

        return secret

    @staticmethod
    def create_lease(
        session,
        secret_id: str,
        lease_duration_seconds: int,
        accessor: str,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create a time-limited lease for secret access.

        Args:
            session: Database session
            secret_id: Secret to lease
            lease_duration_seconds: Lease duration
            accessor: User/system accessing
            metadata: Additional metadata

        Returns:
            Created lease
        """
        secret = SecretManagement._secrets.get(secret_id)
        if not secret:
            raise ValueError(f"Secret not found: {secret_id}")

        lease_id = f"lease_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=lease_duration_seconds)

        lease = {
            "id": lease_id,
            "secret_id": secret_id,
            "accessor": accessor,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "duration_seconds": lease_duration_seconds,
            "renewed_count": 0,
            "revoked": False,
            "metadata": metadata or {}
        }

        SecretManagement._secret_leases[lease_id] = lease

        # Log lease creation
        SecretManagement._log_access(
            secret_id=secret_id,
            action="lease_created",
            actor=accessor,
            details={"lease_id": lease_id, "duration": lease_duration_seconds}
        )

        return lease

    @staticmethod
    def renew_lease(
        session,
        lease_id: str,
        additional_seconds: int
    ) -> dict:
        """
        Renew a lease.

        Args:
            session: Database session
            lease_id: Lease to renew
            additional_seconds: Additional time to add

        Returns:
            Renewed lease
        """
        lease = SecretManagement._secret_leases.get(lease_id)
        if not lease:
            raise ValueError(f"Lease not found: {lease_id}")

        if lease["revoked"]:
            raise ValueError(f"Lease has been revoked: {lease_id}")

        now = datetime.utcnow()
        current_expires = datetime.fromisoformat(lease["expires_at"])
        new_expires = current_expires + timedelta(seconds=additional_seconds)

        lease["expires_at"] = new_expires.isoformat()
        lease["renewed_count"] += 1
        lease["duration_seconds"] += additional_seconds

        # Log renewal
        SecretManagement._log_access(
            secret_id=lease["secret_id"],
            action="lease_renewed",
            actor=lease["accessor"],
            details={"lease_id": lease_id, "additional_seconds": additional_seconds}
        )

        return lease

    @staticmethod
    def create_rotation_policy(
        session,
        name: str,
        secret_name_pattern: str,
        rotation_days: int,
        auto_rotate: bool = True,
        notification_days_before: int = 7,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Create a rotation policy for secrets.

        Args:
            session: Database session
            name: Policy name
            secret_name_pattern: Pattern to match secret names
            rotation_days: Days between rotations
            auto_rotate: Whether to auto-rotate
            notification_days_before: Days before rotation to notify
            metadata: Additional metadata

        Returns:
            Created policy
        """
        policy_id = f"rotation_policy_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        policy = {
            "id": policy_id,
            "name": name,
            "secret_name_pattern": secret_name_pattern,
            "rotation_days": rotation_days,
            "auto_rotate": auto_rotate,
            "notification_days_before": notification_days_before,
            "created_at": now.isoformat(),
            "enabled": True,
            "last_applied_at": None,
            "secrets_matched": 0,
            "rotations_performed": 0,
            "metadata": metadata or {}
        }

        SecretManagement._rotation_policies[policy_id] = policy
        return policy

    @staticmethod
    def list_secrets(
        session,
        secret_type: Optional[str] = None,
        status: Optional[str] = None,
        tags: Optional[List[str]] = None,
        limit: int = 50
    ) -> dict:
        """
        List secrets with filtering.

        Args:
            session: Database session
            secret_type: Filter by type
            status: Filter by status
            tags: Filter by tags
            limit: Maximum secrets to return

        Returns:
            Filtered secrets
        """
        secrets = list(SecretManagement._secrets.values())

        # Apply filters
        if secret_type:
            secrets = [s for s in secrets if s["secret_type"] == secret_type]
        if status:
            secrets = [s for s in secrets if s["status"] == status]
        if tags:
            secrets = [s for s in secrets if any(tag in s["tags"] for tag in tags)]

        # Sort by updated_at descending
        secrets.sort(key=lambda x: x["updated_at"], reverse=True)

        # Remove encrypted data from list view
        secrets = [{k: v for k, v in s.items() if k != "encrypted_data"} for s in secrets]

        # Apply limit
        secrets = secrets[:limit]

        return {
            "secrets": secrets,
            "total_secrets": len(SecretManagement._secrets),
            "returned_count": len(secrets)
        }

    @staticmethod
    def get_secret_access_log(
        session,
        secret_id: str,
        limit: int = 50
    ) -> dict:
        """
        Get access log for a secret.

        Args:
            session: Database session
            secret_id: Secret ID
            limit: Maximum log entries

        Returns:
            Access log
        """
        logs = SecretManagement._access_logs.get(secret_id, [])
        logs = sorted(logs, key=lambda x: x["timestamp"], reverse=True)[:limit]

        return {
            "secret_id": secret_id,
            "total_accesses": len(SecretManagement._access_logs.get(secret_id, [])),
            "access_log": logs
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get secret management statistics"""
        secrets = list(SecretManagement._secrets.values())
        leases = list(SecretManagement._secret_leases.values())

        # Status distribution
        status_dist = defaultdict(int)
        for secret in secrets:
            status_dist[secret["status"]] += 1

        # Type distribution
        type_dist = defaultdict(int)
        for secret in secrets:
            type_dist[secret["secret_type"]] += 1

        # Rotation status
        now = datetime.utcnow()
        needs_rotation = 0
        for secret in secrets:
            if secret.get("next_rotation_at"):
                next_rotation = datetime.fromisoformat(secret["next_rotation_at"])
                if next_rotation <= now:
                    needs_rotation += 1

        # Active leases
        active_leases = 0
        for lease in leases:
            if not lease["revoked"]:
                expires = datetime.fromisoformat(lease["expires_at"])
                if expires > now:
                    active_leases += 1

        return {
            "total_secrets": len(secrets),
            "total_secret_names": len(SecretManagement._secret_versions),
            "status_distribution": dict(status_dist),
            "type_distribution": dict(type_dist),
            "secrets_needing_rotation": needs_rotation,
            "total_leases": len(leases),
            "active_leases": active_leases,
            "rotation_policies": len(SecretManagement._rotation_policies),
            "total_accesses": sum(len(logs) for logs in SecretManagement._access_logs.values())
        }

    @staticmethod
    def _encrypt_secret(data: dict) -> str:
        """Encrypt secret data"""
        # In production, use proper encryption (Fernet, AWS KMS, etc.)
        data_json = json.dumps(data)
        # Add random salt for additional security
        salt = secrets.token_hex(16)
        salted_data = f"{salt}:{data_json}"
        encrypted = base64.b64encode(salted_data.encode()).decode()
        return f"enc_v1:{encrypted}"

    @staticmethod
    def _decrypt_secret(encrypted_data: str) -> dict:
        """Decrypt secret data"""
        if not encrypted_data.startswith("enc_v1:"):
            raise ValueError("Invalid encrypted data format")

        encrypted = encrypted_data.replace("enc_v1:", "")
        decrypted = base64.b64decode(encrypted.encode()).decode()
        # Remove salt
        _, data_json = decrypted.split(":", 1)
        return json.loads(data_json)

    @staticmethod
    def _log_access(
        secret_id: str,
        action: str,
        actor: str,
        details: Optional[dict] = None
    ):
        """Log secret access"""
        now = datetime.utcnow()
        log_entry = {
            "timestamp": now.isoformat(),
            "action": action,
            "actor": actor,
            "details": details or {}
        }
        SecretManagement._access_logs[secret_id].append(log_entry)
