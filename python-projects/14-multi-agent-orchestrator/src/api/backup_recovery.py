"""
Backup and Recovery API

REST API endpoints for backup, restore, and disaster recovery operations.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.backup_recovery import (
    BackupRecovery,
    BackupType,
    BackupStatus,
    RecoveryStatus
)


router = APIRouter()


# Request/Response Models
class CreateBackupRequest(BaseModel):
    backup_type: str = Field(BackupType.FULL, description="Type of backup")
    description: Optional[str] = Field(None, description="Backup description")
    include_data_types: Optional[List[str]] = Field(None, description="Data types to include")
    compress: bool = Field(True, description="Whether to compress backup")
    encrypt: bool = Field(False, description="Whether to encrypt backup")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class RestoreBackupRequest(BaseModel):
    restore_point: Optional[str] = Field(None, description="Specific point in time to restore")
    target_location: Optional[str] = Field(None, description="Target location for restore")
    overwrite: bool = Field(False, description="Whether to overwrite existing data")


class CreateBackupScheduleRequest(BaseModel):
    name: str = Field(..., description="Schedule name")
    backup_type: str = Field(BackupType.FULL, description="Type of backup")
    schedule_cron: str = Field(..., description="Cron expression for schedule")
    retention_days: int = Field(30, description="Days to retain backups")
    include_data_types: Optional[List[str]] = Field(None, description="Data types to include")
    compress: bool = Field(True, description="Whether to compress")
    encrypt: bool = Field(False, description="Whether to encrypt")
    enabled: bool = Field(True, description="Whether schedule is enabled")


@router.post("/backups")
def create_backup(
    request: CreateBackupRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a backup.

    Creates a new backup of system data with optional compression
    and encryption.
    """
    try:
        backup = BackupRecovery.create_backup(
            session=session,
            backup_type=request.backup_type,
            description=request.description,
            include_data_types=request.include_data_types,
            compress=request.compress,
            encrypt=request.encrypt,
            metadata=request.metadata
        )

        return {
            "success": True,
            "backup": backup,
            "message": f"Backup created: {backup['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backups/{backup_id}/restore")
def restore_backup(
    backup_id: str,
    request: RestoreBackupRequest,
    session: Session = Depends(get_db_session)
):
    """
    Restore from backup.

    Restores data from a specific backup to recover from data loss
    or system failure.
    """
    try:
        recovery = BackupRecovery.restore_backup(
            session=session,
            backup_id=backup_id,
            restore_point=request.restore_point,
            target_location=request.target_location,
            overwrite=request.overwrite
        )

        return {
            "success": True,
            "recovery": recovery,
            "message": f"Restore operation initiated: {recovery['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backups/{backup_id}/verify")
def verify_backup(
    backup_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Verify backup integrity.

    Verifies that a backup is complete and uncorrupted by checking
    checksums and file counts.
    """
    try:
        verification = BackupRecovery.verify_backup(
            session=session,
            backup_id=backup_id
        )

        return {
            "success": True,
            "verification": verification,
            "message": "Backup verified" if verification["integrity_valid"] else "Backup verification failed"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backups/{backup_id}")
def get_backup(
    backup_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get backup details.

    Returns complete information about a specific backup including
    size, status, and verification results.
    """
    try:
        backup = BackupRecovery._backups.get(backup_id)
        if not backup:
            raise ValueError(f"Backup not found: {backup_id}")

        return {
            "success": True,
            "backup": backup
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backups")
def list_backups(
    backup_type: Optional[str] = None,
    status: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    List backups.

    Returns backups with optional filtering by type, status,
    and date range.
    """
    try:
        result = BackupRecovery.list_backups(
            session=session,
            backup_type=backup_type,
            status=status,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/schedules")
def create_backup_schedule(
    request: CreateBackupScheduleRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create backup schedule.

    Creates an automated backup schedule that runs on a
    defined cron schedule.
    """
    try:
        schedule = BackupRecovery.create_backup_schedule(
            session=session,
            name=request.name,
            backup_type=request.backup_type,
            schedule_cron=request.schedule_cron,
            retention_days=request.retention_days,
            include_data_types=request.include_data_types,
            compress=request.compress,
            encrypt=request.encrypt,
            enabled=request.enabled
        )

        return {
            "success": True,
            "schedule": schedule,
            "message": f"Backup schedule created: {schedule['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
def get_backup_health(
    session: Session = Depends(get_db_session)
):
    """
    Get backup system health.

    Returns health status, recent backup activity, and any
    issues requiring attention.
    """
    try:
        health = BackupRecovery.get_backup_health(session=session)

        return {
            "success": True,
            "health": health
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get backup and recovery statistics.

    Returns aggregate metrics including backup counts, sizes,
    and recovery success rates.
    """
    try:
        stats = BackupRecovery.get_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backup-types")
def list_backup_types():
    """
    List all backup types.

    Returns all available backup types and their descriptions.
    """
    return {
        "success": True,
        "backup_types": [
            {"type": BackupType.FULL, "description": "Complete backup of all data"},
            {"type": BackupType.INCREMENTAL, "description": "Backup of changes since last backup"},
            {"type": BackupType.DIFFERENTIAL, "description": "Backup of changes since last full backup"}
        ]
    }


@router.get("/backup-statuses")
def list_backup_statuses():
    """
    List all backup statuses.

    Returns all possible backup lifecycle statuses.
    """
    return {
        "success": True,
        "statuses": [
            {"status": BackupStatus.PENDING, "description": "Backup pending"},
            {"status": BackupStatus.IN_PROGRESS, "description": "Backup in progress"},
            {"status": BackupStatus.COMPLETED, "description": "Backup completed"},
            {"status": BackupStatus.FAILED, "description": "Backup failed"},
            {"status": BackupStatus.VERIFIED, "description": "Backup verified"},
            {"status": BackupStatus.EXPIRED, "description": "Backup expired"}
        ]
    }


@router.get("/recovery-statuses")
def list_recovery_statuses():
    """
    List all recovery statuses.

    Returns all possible recovery operation statuses.
    """
    return {
        "success": True,
        "statuses": [
            {"status": RecoveryStatus.INITIATED, "description": "Recovery initiated"},
            {"status": RecoveryStatus.IN_PROGRESS, "description": "Recovery in progress"},
            {"status": RecoveryStatus.COMPLETED, "description": "Recovery completed"},
            {"status": RecoveryStatus.FAILED, "description": "Recovery failed"},
            {"status": RecoveryStatus.ROLLED_BACK, "description": "Recovery rolled back"}
        ]
    }
