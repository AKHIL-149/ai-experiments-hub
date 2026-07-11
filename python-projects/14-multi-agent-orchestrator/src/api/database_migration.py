"""
Database Migration Management API

REST API endpoints for database schema migration management and version control.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.database_migration import (
    DatabaseMigration,
    MigrationStatus,
    MigrationType,
    DatabaseType,
    ValidationLevel
)


router = APIRouter()


# Request/Response Models
class CreateMigrationRequest(BaseModel):
    migration_name: str = Field(..., description="Migration name")
    version: str = Field(..., description="Version number (semver or timestamp)")
    migration_type: str = Field(MigrationType.SCHEMA, description="Type of migration")
    up_script: str = Field(..., description="SQL script for forward migration")
    down_script: str = Field(..., description="SQL script for rollback")
    database_type: str = Field(DatabaseType.POSTGRESQL, description="Target database type")
    description: Optional[str] = Field(None, description="Migration description")
    dependencies: Optional[List[str]] = Field(None, description="Migration dependencies")
    checksum: Optional[str] = Field(None, description="Script checksum")


class ExecuteMigrationRequest(BaseModel):
    dry_run: bool = Field(False, description="Execute in dry-run mode")
    validate_before_run: bool = Field(True, description="Validate before execution")


class RollbackMigrationRequest(BaseModel):
    force: bool = Field(False, description="Force rollback even if risky")


@router.post("/migrations")
def create_migration(
    request: CreateMigrationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create database migration.

    Creates a new migration with forward (up) and backward (down)
    scripts for schema changes.
    """
    try:
        migration = DatabaseMigration.create_migration(
            session=session,
            migration_name=request.migration_name,
            version=request.version,
            migration_type=request.migration_type,
            up_script=request.up_script,
            down_script=request.down_script,
            database_type=request.database_type,
            description=request.description,
            dependencies=request.dependencies,
            checksum=request.checksum
        )

        return {
            "success": True,
            "migration": migration,
            "message": f"Migration created: {migration['name']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/migrations/{migration_id}/execute")
def execute_migration(
    migration_id: str,
    request: ExecuteMigrationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Execute database migration.

    Runs the migration script to apply schema changes.
    Supports dry-run mode for testing.
    """
    try:
        result = DatabaseMigration.execute_migration(
            session=session,
            migration_id=migration_id,
            dry_run=request.dry_run,
            validate_before_run=request.validate_before_run
        )

        return {
            "success": True,
            "execution": result,
            "message": f"Migration {'validated' if request.dry_run else 'executed'}: {result['status']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/migrations/{migration_id}/rollback")
def rollback_migration(
    migration_id: str,
    request: RollbackMigrationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Rollback database migration.

    Reverts a previously applied migration using the down script.
    Use with caution as this can result in data loss.
    """
    try:
        result = DatabaseMigration.rollback_migration(
            session=session,
            migration_id=migration_id,
            force=request.force
        )

        return {
            "success": True,
            "rollback": result,
            "message": f"Migration rolled back: {result['status']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/migrations/{migration_id}/validate")
def validate_migration(
    migration_id: str,
    validation_level: str = ValidationLevel.BASIC,
    session: Session = Depends(get_db_session)
):
    """
    Validate migration scripts.

    Performs validation checks on migration scripts including
    syntax validation and dangerous operation detection.
    """
    try:
        validation = DatabaseMigration.validate_migration(
            session=session,
            migration_id=migration_id,
            validation_level=validation_level
        )

        return {
            "success": True,
            "validation": validation
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/status")
def get_migration_status(
    database_type: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get migration status overview.

    Returns comprehensive status of all migrations including
    pending, completed, and failed migrations.
    """
    try:
        status = DatabaseMigration.get_migration_status(
            session=session,
            database_type=database_type
        )

        return {
            "success": True,
            "status": status
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plan")
def generate_migration_plan(
    target_version: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Generate migration execution plan.

    Creates an execution plan showing the order in which
    migrations will be applied to reach the target version.
    """
    try:
        plan = DatabaseMigration.generate_migration_plan(
            session=session,
            target_version=target_version
        )

        return {
            "success": True,
            "plan": plan
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema/{database_type}/version")
def get_schema_version(
    database_type: str,
    session: Session = Depends(get_db_session)
):
    """
    Get current schema version.

    Returns the current schema version for the specified
    database type based on applied migrations.
    """
    try:
        version_info = DatabaseMigration.get_schema_version(
            session=session,
            database_type=database_type
        )

        return {
            "success": True,
            "version_info": version_info
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schema/compare")
def compare_schemas(
    source_db: str,
    target_db: str,
    session: Session = Depends(get_db_session)
):
    """
    Compare schema versions between databases.

    Compares the migration history between two databases
    to identify version drift and synchronization issues.
    """
    try:
        comparison = DatabaseMigration.compare_schemas(
            session=session,
            source_db=source_db,
            target_db=target_db
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
    Get database migration statistics.

    Returns aggregate statistics including migration counts,
    success rates, and execution metrics.
    """
    try:
        stats = DatabaseMigration.get_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/migration-types")
def list_migration_types():
    """
    List all migration types.

    Returns all available migration type options.
    """
    return {
        "success": True,
        "migration_types": [
            {"type": MigrationType.SCHEMA, "description": "Schema changes (DDL)"},
            {"type": MigrationType.DATA, "description": "Data modifications (DML)"},
            {"type": MigrationType.SEED, "description": "Seed/initial data"},
            {"type": MigrationType.ROLLBACK, "description": "Rollback operation"},
            {"type": MigrationType.CLEANUP, "description": "Cleanup/maintenance"}
        ]
    }


@router.get("/database-types")
def list_database_types():
    """
    List all supported database types.

    Returns all supported database platforms.
    """
    return {
        "success": True,
        "database_types": [
            {"type": DatabaseType.POSTGRESQL, "description": "PostgreSQL database"},
            {"type": DatabaseType.MYSQL, "description": "MySQL/MariaDB database"},
            {"type": DatabaseType.MONGODB, "description": "MongoDB NoSQL database"},
            {"type": DatabaseType.SQLITE, "description": "SQLite embedded database"},
            {"type": DatabaseType.MSSQL, "description": "Microsoft SQL Server"}
        ]
    }


@router.get("/validation-levels")
def list_validation_levels():
    """
    List all validation levels.

    Returns all available validation level options.
    """
    return {
        "success": True,
        "validation_levels": [
            {"level": ValidationLevel.NONE, "description": "No validation"},
            {"level": ValidationLevel.BASIC, "description": "Basic syntax validation"},
            {"level": ValidationLevel.STRICT, "description": "Strict validation with safety checks"}
        ]
    }
