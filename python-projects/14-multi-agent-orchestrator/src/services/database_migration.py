"""
Database Migration Management

Provides database schema migration management, version control, and rollback capabilities.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict
import uuid
import random


class MigrationStatus:
    """Migration status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    SKIPPED = "skipped"


class MigrationType:
    """Migration types"""
    SCHEMA = "schema"
    DATA = "data"
    SEED = "seed"
    ROLLBACK = "rollback"
    CLEANUP = "cleanup"


class DatabaseType:
    """Supported database types"""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MONGODB = "mongodb"
    SQLITE = "sqlite"
    MSSQL = "mssql"


class ValidationLevel:
    """Migration validation levels"""
    NONE = "none"
    BASIC = "basic"
    STRICT = "strict"


class DatabaseMigration:
    """Database Migration Management service"""

    # In-memory storage
    _migrations = {}
    _migration_history = defaultdict(list)
    _schemas = {}
    _rollback_points = defaultdict(list)
    _validation_results = {}
    _execution_logs = defaultdict(list)

    @staticmethod
    def create_migration(
        session,
        migration_name: str,
        version: str,
        migration_type: str,
        up_script: str,
        down_script: str,
        database_type: str = DatabaseType.POSTGRESQL,
        description: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        checksum: Optional[str] = None
    ) -> dict:
        """
        Create database migration.

        Args:
            session: Database session
            migration_name: Migration name
            version: Version number (semver or timestamp)
            migration_type: Type of migration
            up_script: SQL script for forward migration
            down_script: SQL script for rollback
            database_type: Target database type
            description: Migration description
            dependencies: List of migration dependencies
            checksum: Script checksum for validation

        Returns:
            Created migration
        """
        migration_id = f"migration_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        migration = {
            "id": migration_id,
            "name": migration_name,
            "version": version,
            "type": migration_type,
            "up_script": up_script,
            "down_script": down_script,
            "database_type": database_type,
            "description": description,
            "dependencies": dependencies or [],
            "checksum": checksum or f"sha256_{uuid.uuid4().hex[:16]}",
            "status": MigrationStatus.PENDING,
            "created_at": now.isoformat(),
            "executed_at": None,
            "execution_duration_ms": 0,
            "affected_rows": 0,
            "created_by": "system",
            "validated": False,
            "can_rollback": True
        }

        DatabaseMigration._migrations[migration_id] = migration
        return migration

    @staticmethod
    def execute_migration(
        session,
        migration_id: str,
        dry_run: bool = False,
        validate_before_run: bool = True
    ) -> dict:
        """
        Execute database migration.

        Args:
            session: Database session
            migration_id: Migration ID
            dry_run: Execute in dry-run mode without applying changes
            validate_before_run: Validate migration before execution

        Returns:
            Execution result
        """
        migration = DatabaseMigration._migrations.get(migration_id)
        if not migration:
            raise ValueError(f"Migration not found: {migration_id}")

        if migration["status"] == MigrationStatus.COMPLETED:
            raise ValueError("Migration already executed")

        now = datetime.utcnow()

        # Validate if requested
        if validate_before_run:
            validation = DatabaseMigration._validate_migration(migration)
            if not validation["is_valid"]:
                raise ValueError(f"Migration validation failed: {validation['errors']}")

        # Check dependencies
        for dep_id in migration["dependencies"]:
            dep = DatabaseMigration._migrations.get(dep_id)
            if not dep or dep["status"] != MigrationStatus.COMPLETED:
                raise ValueError(f"Dependency not met: {dep_id}")

        migration["status"] = MigrationStatus.RUNNING

        # Simulate execution
        execution_time_ms = random.uniform(100, 5000)
        success = random.random() > 0.05  # 95% success rate

        if success and not dry_run:
            migration["status"] = MigrationStatus.COMPLETED
            migration["executed_at"] = now.isoformat()
            migration["execution_duration_ms"] = execution_time_ms
            migration["affected_rows"] = random.randint(0, 1000)
            migration["validated"] = True

            # Record in history
            DatabaseMigration._migration_history[migration["version"]].append({
                "migration_id": migration_id,
                "action": "executed",
                "timestamp": now.isoformat(),
                "dry_run": dry_run
            })

            # Create rollback point
            DatabaseMigration._rollback_points[migration["database_type"]].append({
                "migration_id": migration_id,
                "version": migration["version"],
                "timestamp": now.isoformat()
            })
        elif success and dry_run:
            migration["status"] = MigrationStatus.PENDING  # Keep pending in dry-run
        else:
            migration["status"] = MigrationStatus.FAILED

        execution_result = {
            "migration_id": migration_id,
            "migration_name": migration["name"],
            "version": migration["version"],
            "status": migration["status"],
            "dry_run": dry_run,
            "execution_time_ms": execution_time_ms,
            "affected_rows": migration["affected_rows"] if success else 0,
            "executed_at": now.isoformat()
        }

        # Log execution
        DatabaseMigration._execution_logs[migration_id].append(execution_result)

        return execution_result

    @staticmethod
    def rollback_migration(
        session,
        migration_id: str,
        force: bool = False
    ) -> dict:
        """
        Rollback database migration.

        Args:
            session: Database session
            migration_id: Migration ID to rollback
            force: Force rollback even if risky

        Returns:
            Rollback result
        """
        migration = DatabaseMigration._migrations.get(migration_id)
        if not migration:
            raise ValueError(f"Migration not found: {migration_id}")

        if migration["status"] != MigrationStatus.COMPLETED:
            raise ValueError("Can only rollback completed migrations")

        if not migration["can_rollback"] and not force:
            raise ValueError("Migration cannot be safely rolled back. Use force=True to override.")

        now = datetime.utcnow()

        # Simulate rollback
        rollback_time_ms = random.uniform(100, 3000)
        success = random.random() > 0.1  # 90% success rate

        if success:
            migration["status"] = MigrationStatus.ROLLED_BACK
            migration["executed_at"] = None
            migration["affected_rows"] = 0

            # Record in history
            DatabaseMigration._migration_history[migration["version"]].append({
                "migration_id": migration_id,
                "action": "rolled_back",
                "timestamp": now.isoformat(),
                "forced": force
            })

        rollback_result = {
            "migration_id": migration_id,
            "migration_name": migration["name"],
            "version": migration["version"],
            "status": "success" if success else "failed",
            "rollback_time_ms": rollback_time_ms,
            "rolled_back_at": now.isoformat()
        }

        return rollback_result

    @staticmethod
    def validate_migration(
        session,
        migration_id: str,
        validation_level: str = ValidationLevel.BASIC
    ) -> dict:
        """
        Validate migration scripts.

        Args:
            session: Database session
            migration_id: Migration ID
            validation_level: Level of validation

        Returns:
            Validation result
        """
        migration = DatabaseMigration._migrations.get(migration_id)
        if not migration:
            raise ValueError(f"Migration not found: {migration_id}")

        validation = DatabaseMigration._validate_migration(migration, validation_level)

        DatabaseMigration._validation_results[migration_id] = validation
        return validation

    @staticmethod
    def _validate_migration(migration: dict, level: str = ValidationLevel.BASIC) -> dict:
        """Internal validation logic"""
        errors = []
        warnings = []

        # Basic validation
        if not migration["up_script"]:
            errors.append("Missing up script")
        if not migration["down_script"] and migration["type"] != MigrationType.SEED:
            warnings.append("Missing down script - rollback may not be possible")

        # Strict validation
        if level == ValidationLevel.STRICT:
            # Check for dangerous operations
            dangerous_keywords = ["DROP TABLE", "TRUNCATE", "DELETE FROM"]
            for keyword in dangerous_keywords:
                if keyword in migration["up_script"].upper():
                    warnings.append(f"Script contains potentially dangerous operation: {keyword}")

        is_valid = len(errors) == 0

        return {
            "migration_id": migration["id"],
            "is_valid": is_valid,
            "validation_level": level,
            "errors": errors,
            "warnings": warnings,
            "validated_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def get_migration_status(
        session,
        database_type: Optional[str] = None
    ) -> dict:
        """
        Get migration status overview.

        Args:
            session: Database session
            database_type: Filter by database type

        Returns:
            Migration status overview
        """
        migrations = list(DatabaseMigration._migrations.values())

        if database_type:
            migrations = [m for m in migrations if m["database_type"] == database_type]

        # Calculate statistics
        total = len(migrations)
        pending = len([m for m in migrations if m["status"] == MigrationStatus.PENDING])
        completed = len([m for m in migrations if m["status"] == MigrationStatus.COMPLETED])
        failed = len([m for m in migrations if m["status"] == MigrationStatus.FAILED])
        rolled_back = len([m for m in migrations if m["status"] == MigrationStatus.ROLLED_BACK])

        # Get latest version
        latest_version = None
        if migrations:
            completed_migrations = [m for m in migrations if m["status"] == MigrationStatus.COMPLETED]
            if completed_migrations:
                latest_version = max(completed_migrations, key=lambda m: m["executed_at"] or "")["version"]

        return {
            "database_type": database_type or "all",
            "total_migrations": total,
            "pending": pending,
            "completed": completed,
            "failed": failed,
            "rolled_back": rolled_back,
            "latest_version": latest_version,
            "pending_migrations": [
                {"id": m["id"], "name": m["name"], "version": m["version"]}
                for m in migrations if m["status"] == MigrationStatus.PENDING
            ][:10]
        }

    @staticmethod
    def generate_migration_plan(
        session,
        target_version: Optional[str] = None
    ) -> dict:
        """
        Generate migration execution plan.

        Args:
            session: Database session
            target_version: Target version to migrate to

        Returns:
            Migration plan
        """
        plan_id = f"plan_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # Get pending migrations
        pending_migrations = [
            m for m in DatabaseMigration._migrations.values()
            if m["status"] == MigrationStatus.PENDING
        ]

        # Sort by version
        pending_migrations.sort(key=lambda m: m["version"])

        # Filter by target version if specified
        if target_version:
            pending_migrations = [
                m for m in pending_migrations
                if m["version"] <= target_version
            ]

        # Resolve dependencies
        execution_order = []
        for migration in pending_migrations:
            # Check if all dependencies are met
            deps_met = all(
                DatabaseMigration._migrations.get(dep_id, {}).get("status") == MigrationStatus.COMPLETED
                for dep_id in migration["dependencies"]
            )
            execution_order.append({
                "migration_id": migration["id"],
                "name": migration["name"],
                "version": migration["version"],
                "type": migration["type"],
                "dependencies_met": deps_met,
                "estimated_duration_ms": random.uniform(100, 5000)
            })

        total_estimated_time_ms = sum(m["estimated_duration_ms"] for m in execution_order)

        migration_plan = {
            "plan_id": plan_id,
            "generated_at": now.isoformat(),
            "target_version": target_version or "latest",
            "total_migrations": len(execution_order),
            "execution_order": execution_order,
            "estimated_total_time_ms": total_estimated_time_ms,
            "warnings": []
        }

        # Add warnings for risky migrations
        for migration in execution_order:
            mig = DatabaseMigration._migrations[migration["migration_id"]]
            if "DROP" in mig["up_script"].upper() or "TRUNCATE" in mig["up_script"].upper():
                migration_plan["warnings"].append(
                    f"Migration {migration['name']} contains destructive operations"
                )

        return migration_plan

    @staticmethod
    def get_schema_version(
        session,
        database_type: str
    ) -> dict:
        """
        Get current schema version.

        Args:
            session: Database session
            database_type: Database type

        Returns:
            Schema version information
        """
        # Get all completed migrations for this database
        completed = [
            m for m in DatabaseMigration._migrations.values()
            if m["database_type"] == database_type and m["status"] == MigrationStatus.COMPLETED
        ]

        if not completed:
            current_version = "0.0.0"
            last_migration = None
        else:
            latest = max(completed, key=lambda m: m["executed_at"] or "")
            current_version = latest["version"]
            last_migration = {
                "id": latest["id"],
                "name": latest["name"],
                "executed_at": latest["executed_at"]
            }

        return {
            "database_type": database_type,
            "current_version": current_version,
            "last_migration": last_migration,
            "total_migrations_applied": len(completed)
        }

    @staticmethod
    def compare_schemas(
        session,
        source_db: str,
        target_db: str
    ) -> dict:
        """
        Compare schema versions between databases.

        Args:
            session: Database session
            source_db: Source database type
            target_db: Target database type

        Returns:
            Schema comparison
        """
        source_migrations = [
            m for m in DatabaseMigration._migrations.values()
            if m["database_type"] == source_db and m["status"] == MigrationStatus.COMPLETED
        ]

        target_migrations = [
            m for m in DatabaseMigration._migrations.values()
            if m["database_type"] == target_db and m["status"] == MigrationStatus.COMPLETED
        ]

        source_versions = {m["version"] for m in source_migrations}
        target_versions = {m["version"] for m in target_migrations}

        only_in_source = source_versions - target_versions
        only_in_target = target_versions - source_versions
        common_versions = source_versions & target_versions

        return {
            "source_database": source_db,
            "target_database": target_db,
            "are_in_sync": len(only_in_source) == 0 and len(only_in_target) == 0,
            "common_versions": len(common_versions),
            "only_in_source": list(only_in_source),
            "only_in_target": list(only_in_target),
            "version_drift": len(only_in_source) + len(only_in_target)
        }

    @staticmethod
    def get_statistics(session) -> dict:
        """Get database migration statistics"""
        migrations = list(DatabaseMigration._migrations.values())

        # Status distribution
        status_dist = defaultdict(int)
        for mig in migrations:
            status_dist[mig["status"]] += 1

        # Type distribution
        type_dist = defaultdict(int)
        for mig in migrations:
            type_dist[mig["type"]] += 1

        # Database distribution
        db_dist = defaultdict(int)
        for mig in migrations:
            db_dist[mig["database_type"]] += 1

        # Success rate
        total_executed = len([m for m in migrations if m["status"] in [MigrationStatus.COMPLETED, MigrationStatus.FAILED]])
        successful = len([m for m in migrations if m["status"] == MigrationStatus.COMPLETED])
        success_rate = (successful / total_executed * 100) if total_executed > 0 else 0

        # Average execution time
        completed_migrations = [m for m in migrations if m["status"] == MigrationStatus.COMPLETED]
        avg_execution_time = (
            sum(m["execution_duration_ms"] for m in completed_migrations) / len(completed_migrations)
            if completed_migrations else 0
        )

        return {
            "total_migrations": len(migrations),
            "status_distribution": dict(status_dist),
            "type_distribution": dict(type_dist),
            "database_distribution": dict(db_dist),
            "success_rate": success_rate,
            "total_rollbacks": len([m for m in migrations if m["status"] == MigrationStatus.ROLLED_BACK]),
            "average_execution_time_ms": avg_execution_time,
            "total_affected_rows": sum(m["affected_rows"] for m in migrations),
            "validated_migrations": len([m for m in migrations if m["validated"]]),
            "total_execution_logs": sum(len(logs) for logs in DatabaseMigration._execution_logs.values())
        }
