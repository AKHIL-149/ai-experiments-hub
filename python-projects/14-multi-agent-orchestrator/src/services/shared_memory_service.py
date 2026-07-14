"""
Shared Memory Service

Manages shared memory for multi-agent coordination and data exchange.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
import json

from src.models import Agent, Workflow, Task
from src.core.logging import logger


class MemoryScope:
    """Memory scope constants"""
    GLOBAL = "global"
    WORKFLOW = "workflow"
    AGENT = "agent"
    TASK = "task"
    SESSION = "session"


class MemoryType:
    """Memory type constants"""
    PERMANENT = "permanent"
    TEMPORARY = "temporary"
    SESSION = "session"


class SharedMemoryService:
    """Service for managing shared memory across agents"""

    # In-memory storage for fast access
    _memory_store: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def _get_memory_key(
        scope: str,
        scope_id: Optional[str] = None,
        key: str = ""
    ) -> str:
        """Generate a unique memory key"""
        if scope_id:
            return f"{scope}:{scope_id}:{key}"
        return f"{scope}:{key}"

    @staticmethod
    def set_memory(
        session: Session,
        scope: str,
        key: str,
        value: Any,
        scope_id: Optional[str] = None,
        memory_type: str = MemoryType.TEMPORARY,
        ttl_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Set a memory value.

        Args:
            session: Database session
            scope: Memory scope (global/workflow/agent/task/session)
            key: Memory key
            value: Value to store
            scope_id: Optional scope identifier (workflow_id, agent_id, etc.)
            memory_type: Memory type (permanent/temporary/session)
            ttl_seconds: Optional time-to-live in seconds
            metadata: Optional metadata

        Returns:
            Memory entry details
        """
        memory_key = SharedMemoryService._get_memory_key(scope, scope_id, key)

        # Calculate expiration
        expires_at = None
        if ttl_seconds:
            expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

        memory_entry = {
            "scope": scope,
            "scope_id": scope_id,
            "key": key,
            "value": value,
            "memory_type": memory_type,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else None,
            "metadata": metadata or {},
            "version": 1
        }

        # Check if key exists and increment version
        if memory_key in SharedMemoryService._memory_store:
            old_entry = SharedMemoryService._memory_store[memory_key]
            memory_entry["version"] = old_entry.get("version", 0) + 1
            memory_entry["created_at"] = old_entry.get("created_at")

        SharedMemoryService._memory_store[memory_key] = memory_entry

        logger.debug(f"Memory set: {memory_key} = {value}")

        return memory_entry

    @staticmethod
    def get_memory(
        session: Session,
        scope: str,
        key: str,
        scope_id: Optional[str] = None,
        default: Any = None
    ) -> Any:
        """
        Get a memory value.

        Args:
            session: Database session
            scope: Memory scope
            key: Memory key
            scope_id: Optional scope identifier
            default: Default value if not found

        Returns:
            Memory value or default
        """
        memory_key = SharedMemoryService._get_memory_key(scope, scope_id, key)

        if memory_key not in SharedMemoryService._memory_store:
            return default

        entry = SharedMemoryService._memory_store[memory_key]

        # Check expiration
        if entry.get("expires_at"):
            expires_at = datetime.fromisoformat(entry["expires_at"])
            if datetime.utcnow() > expires_at:
                # Expired, remove and return default
                del SharedMemoryService._memory_store[memory_key]
                return default

        return entry["value"]

    @staticmethod
    def delete_memory(
        session: Session,
        scope: str,
        key: str,
        scope_id: Optional[str] = None
    ) -> bool:
        """
        Delete a memory value.

        Args:
            session: Database session
            scope: Memory scope
            key: Memory key
            scope_id: Optional scope identifier

        Returns:
            True if deleted, False if not found
        """
        memory_key = SharedMemoryService._get_memory_key(scope, scope_id, key)

        if memory_key in SharedMemoryService._memory_store:
            del SharedMemoryService._memory_store[memory_key]
            logger.debug(f"Memory deleted: {memory_key}")
            return True

        return False

    @staticmethod
    def list_memory(
        session: Session,
        scope: Optional[str] = None,
        scope_id: Optional[str] = None,
        memory_type: Optional[str] = None,
        pattern: Optional[str] = None,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        List memory entries with optional filtering.

        Args:
            session: Database session
            scope: Optional scope filter
            scope_id: Optional scope ID filter
            memory_type: Optional memory type filter
            pattern: Optional key pattern (supports wildcards)
            limit: Maximum entries to return

        Returns:
            Dictionary with memory entries
        """
        # Clean expired entries first
        SharedMemoryService._cleanup_expired_memory()

        filtered_entries = []

        for memory_key, entry in SharedMemoryService._memory_store.items():
            # Filter by scope
            if scope and entry["scope"] != scope:
                continue

            # Filter by scope_id
            if scope_id and entry.get("scope_id") != scope_id:
                continue

            # Filter by memory_type
            if memory_type and entry["memory_type"] != memory_type:
                continue

            # Filter by pattern
            if pattern:
                import re
                # Convert wildcard pattern to regex
                regex_pattern = pattern.replace("*", ".*")
                if not re.match(regex_pattern, entry["key"]):
                    continue

            filtered_entries.append({
                "scope": entry["scope"],
                "scope_id": entry["scope_id"],
                "key": entry["key"],
                "value": entry["value"],
                "memory_type": entry["memory_type"],
                "created_at": entry["created_at"],
                "updated_at": entry["updated_at"],
                "expires_at": entry.get("expires_at"),
                "version": entry["version"]
            })

            if len(filtered_entries) >= limit:
                break

        return {
            "total": len(filtered_entries),
            "entries": filtered_entries
        }

    @staticmethod
    def _cleanup_expired_memory() -> int:
        """
        Clean up expired memory entries.

        Returns:
            Number of entries cleaned up
        """
        now = datetime.utcnow()
        expired_keys = []

        for memory_key, entry in SharedMemoryService._memory_store.items():
            if entry.get("expires_at"):
                expires_at = datetime.fromisoformat(entry["expires_at"])
                if now > expires_at:
                    expired_keys.append(memory_key)

        for key in expired_keys:
            del SharedMemoryService._memory_store[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired memory entries")

        return len(expired_keys)

    @staticmethod
    def clear_scope(
        session: Session,
        scope: str,
        scope_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Clear all memory in a scope.

        Args:
            session: Database session
            scope: Memory scope
            scope_id: Optional scope identifier

        Returns:
            Dictionary with deletion statistics
        """
        prefix = SharedMemoryService._get_memory_key(scope, scope_id, "")
        keys_to_delete = [
            key for key in SharedMemoryService._memory_store.keys()
            if key.startswith(prefix)
        ]

        for key in keys_to_delete:
            del SharedMemoryService._memory_store[key]

        logger.info(f"Cleared {len(keys_to_delete)} entries from scope {scope}:{scope_id}")

        return {
            "scope": scope,
            "scope_id": scope_id,
            "entries_deleted": len(keys_to_delete)
        }

    @staticmethod
    def get_memory_stats(session: Session) -> Dict[str, Any]:
        """
        Get memory statistics.

        Args:
            session: Database session

        Returns:
            Dictionary with memory statistics
        """
        # Clean expired entries first
        expired_cleaned = SharedMemoryService._cleanup_expired_memory()

        stats = {
            "total_entries": len(SharedMemoryService._memory_store),
            "expired_cleaned": expired_cleaned,
            "by_scope": {},
            "by_type": {},
            "by_scope_id": {}
        }

        for entry in SharedMemoryService._memory_store.values():
            scope = entry["scope"]
            memory_type = entry["memory_type"]
            scope_id = entry.get("scope_id", "none")

            stats["by_scope"][scope] = stats["by_scope"].get(scope, 0) + 1
            stats["by_type"][memory_type] = stats["by_type"].get(memory_type, 0) + 1
            stats["by_scope_id"][scope_id] = stats["by_scope_id"].get(scope_id, 0) + 1

        return stats

    @staticmethod
    def create_snapshot(
        session: Session,
        scope: str,
        scope_id: Optional[str] = None,
        snapshot_name: str = ""
    ) -> Dict[str, Any]:
        """
        Create a snapshot of memory state.

        Args:
            session: Database session
            scope: Memory scope
            scope_id: Optional scope identifier
            snapshot_name: Optional snapshot name

        Returns:
            Snapshot details
        """
        prefix = SharedMemoryService._get_memory_key(scope, scope_id, "")
        snapshot_entries = {}

        for key, entry in SharedMemoryService._memory_store.items():
            if key.startswith(prefix):
                snapshot_entries[key] = entry.copy()

        snapshot_key = f"snapshot:{scope}:{scope_id or 'global'}:{snapshot_name or datetime.utcnow().isoformat()}"

        snapshot = {
            "snapshot_name": snapshot_name,
            "scope": scope,
            "scope_id": scope_id,
            "entries": snapshot_entries,
            "created_at": datetime.utcnow().isoformat(),
            "entry_count": len(snapshot_entries)
        }

        # Store snapshot in memory
        SharedMemoryService._memory_store[snapshot_key] = snapshot

        logger.info(f"Created snapshot {snapshot_key} with {len(snapshot_entries)} entries")

        return {
            "snapshot_key": snapshot_key,
            "snapshot_name": snapshot_name,
            "entry_count": len(snapshot_entries),
            "created_at": snapshot["created_at"]
        }

    @staticmethod
    def restore_snapshot(
        session: Session,
        snapshot_key: str,
        overwrite: bool = False
    ) -> Dict[str, Any]:
        """
        Restore memory from a snapshot.

        Args:
            session: Database session
            snapshot_key: Snapshot key
            overwrite: Whether to overwrite existing entries

        Returns:
            Restoration details
        """
        if snapshot_key not in SharedMemoryService._memory_store:
            raise ValueError(f"Snapshot {snapshot_key} not found")

        snapshot = SharedMemoryService._memory_store[snapshot_key]
        if "entries" not in snapshot:
            raise ValueError(f"Invalid snapshot {snapshot_key}")

        entries_restored = 0
        entries_skipped = 0

        for key, entry in snapshot["entries"].items():
            if not overwrite and key in SharedMemoryService._memory_store:
                entries_skipped += 1
                continue

            SharedMemoryService._memory_store[key] = entry.copy()
            entries_restored += 1

        logger.info(f"Restored {entries_restored} entries from snapshot {snapshot_key}")

        return {
            "snapshot_key": snapshot_key,
            "entries_restored": entries_restored,
            "entries_skipped": entries_skipped
        }

    @staticmethod
    def atomic_increment(
        session: Session,
        scope: str,
        key: str,
        scope_id: Optional[str] = None,
        delta: int = 1
    ) -> int:
        """
        Atomically increment a numeric value.

        Args:
            session: Database session
            scope: Memory scope
            key: Memory key
            scope_id: Optional scope identifier
            delta: Amount to increment by

        Returns:
            New value after increment
        """
        memory_key = SharedMemoryService._get_memory_key(scope, scope_id, key)

        current_value = 0
        if memory_key in SharedMemoryService._memory_store:
            entry = SharedMemoryService._memory_store[memory_key]
            current_value = entry.get("value", 0)

        new_value = current_value + delta

        SharedMemoryService.set_memory(
            session=session,
            scope=scope,
            key=key,
            value=new_value,
            scope_id=scope_id
        )

        return new_value

    @staticmethod
    def compare_and_swap(
        session: Session,
        scope: str,
        key: str,
        expected_value: Any,
        new_value: Any,
        scope_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Compare-and-swap operation for atomic updates.

        Args:
            session: Database session
            scope: Memory scope
            key: Memory key
            expected_value: Expected current value
            new_value: New value to set
            scope_id: Optional scope identifier

        Returns:
            Success status and current value
        """
        memory_key = SharedMemoryService._get_memory_key(scope, scope_id, key)

        current_value = None
        if memory_key in SharedMemoryService._memory_store:
            current_value = SharedMemoryService._memory_store[memory_key].get("value")

        if current_value == expected_value:
            SharedMemoryService.set_memory(
                session=session,
                scope=scope,
                key=key,
                value=new_value,
                scope_id=scope_id
            )
            return {
                "success": True,
                "old_value": current_value,
                "new_value": new_value
            }

        return {
            "success": False,
            "expected_value": expected_value,
            "actual_value": current_value,
            "message": "Value mismatch"
        }

    @staticmethod
    def get_or_set(
        session: Session,
        scope: str,
        key: str,
        default_value: Any,
        scope_id: Optional[str] = None
    ) -> Any:
        """
        Get value if exists, otherwise set default and return it.

        Args:
            session: Database session
            scope: Memory scope
            key: Memory key
            default_value: Default value to set if not exists
            scope_id: Optional scope identifier

        Returns:
            Existing or default value
        """
        value = SharedMemoryService.get_memory(session, scope, key, scope_id)

        if value is None:
            SharedMemoryService.set_memory(
                session=session,
                scope=scope,
                key=key,
                value=default_value,
                scope_id=scope_id
            )
            return default_value

        return value
