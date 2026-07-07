"""
Shared Memory API endpoints
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.shared_memory_service import SharedMemoryService, MemoryScope, MemoryType
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class SetMemoryRequest(BaseModel):
    """Request model for setting memory"""
    scope: str = Field(..., description="Memory scope (global/workflow/agent/task/session)")
    key: str = Field(..., description="Memory key")
    value: Any = Field(..., description="Value to store")
    scope_id: Optional[str] = Field(None, description="Scope identifier")
    memory_type: str = Field(MemoryType.TEMPORARY, description="Memory type")
    ttl_seconds: Optional[int] = Field(None, ge=1, description="Time-to-live in seconds")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class GetMemoryRequest(BaseModel):
    """Request model for getting memory"""
    scope: str = Field(..., description="Memory scope")
    key: str = Field(..., description="Memory key")
    scope_id: Optional[str] = Field(None, description="Scope identifier")
    default: Any = Field(None, description="Default value if not found")


class DeleteMemoryRequest(BaseModel):
    """Request model for deleting memory"""
    scope: str = Field(..., description="Memory scope")
    key: str = Field(..., description="Memory key")
    scope_id: Optional[str] = Field(None, description="Scope identifier")


class ClearScopeRequest(BaseModel):
    """Request model for clearing scope"""
    scope: str = Field(..., description="Memory scope")
    scope_id: Optional[str] = Field(None, description="Scope identifier")


class CreateSnapshotRequest(BaseModel):
    """Request model for creating snapshot"""
    scope: str = Field(..., description="Memory scope")
    scope_id: Optional[str] = Field(None, description="Scope identifier")
    snapshot_name: str = Field("", description="Optional snapshot name")


class RestoreSnapshotRequest(BaseModel):
    """Request model for restoring snapshot"""
    snapshot_key: str = Field(..., description="Snapshot key")
    overwrite: bool = Field(False, description="Overwrite existing entries")


class AtomicIncrementRequest(BaseModel):
    """Request model for atomic increment"""
    scope: str = Field(..., description="Memory scope")
    key: str = Field(..., description="Memory key")
    scope_id: Optional[str] = Field(None, description="Scope identifier")
    delta: int = Field(1, description="Amount to increment by")


class CompareAndSwapRequest(BaseModel):
    """Request model for compare-and-swap"""
    scope: str = Field(..., description="Memory scope")
    key: str = Field(..., description="Memory key")
    expected_value: Any = Field(..., description="Expected current value")
    new_value: Any = Field(..., description="New value to set")
    scope_id: Optional[str] = Field(None, description="Scope identifier")


class GetOrSetRequest(BaseModel):
    """Request model for get-or-set"""
    scope: str = Field(..., description="Memory scope")
    key: str = Field(..., description="Memory key")
    default_value: Any = Field(..., description="Default value if not exists")
    scope_id: Optional[str] = Field(None, description="Scope identifier")


# Endpoints

@router.post("/set")
async def set_memory(
    request: SetMemoryRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Set a memory value.

    Stores a value in shared memory with specified scope.

    Scopes:
    - **global**: Accessible by all agents
    - **workflow**: Scoped to a specific workflow
    - **agent**: Scoped to a specific agent
    - **task**: Scoped to a specific task
    - **session**: Scoped to a session

    Memory types:
    - **permanent**: Never expires
    - **temporary**: Expires based on TTL
    - **session**: Expires when session ends
    """
    try:
        result = SharedMemoryService.set_memory(
            session=db,
            scope=request.scope,
            key=request.key,
            value=request.value,
            scope_id=request.scope_id,
            memory_type=request.memory_type,
            ttl_seconds=request.ttl_seconds,
            metadata=request.metadata
        )

        return {
            "success": True,
            "memory": result,
            "message": f"Memory set: {request.scope}:{request.scope_id}:{request.key}"
        }

    except Exception as e:
        logger.error(f"Failed to set memory: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/get")
async def get_memory(
    request: GetMemoryRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get a memory value.

    Retrieves a value from shared memory.
    Returns default value if key not found or expired.
    """
    try:
        value = SharedMemoryService.get_memory(
            session=db,
            scope=request.scope,
            key=request.key,
            scope_id=request.scope_id,
            default=request.default
        )

        return {
            "success": True,
            "value": value,
            "found": value is not None
        }

    except Exception as e:
        logger.error(f"Failed to get memory: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/delete")
async def delete_memory(
    request: DeleteMemoryRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Delete a memory value.

    Removes a specific key from shared memory.
    """
    try:
        deleted = SharedMemoryService.delete_memory(
            session=db,
            scope=request.scope,
            key=request.key,
            scope_id=request.scope_id
        )

        return {
            "success": True,
            "deleted": deleted,
            "message": "Memory deleted" if deleted else "Memory not found"
        }

    except Exception as e:
        logger.error(f"Failed to delete memory: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/list")
async def list_memory(
    scope: Optional[str] = Query(None, description="Filter by scope"),
    scope_id: Optional[str] = Query(None, description="Filter by scope ID"),
    memory_type: Optional[str] = Query(None, description="Filter by memory type"),
    pattern: Optional[str] = Query(None, description="Key pattern (supports wildcards)"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum entries to return"),
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    List memory entries.

    Returns memory entries with optional filtering by:
    - Scope (global/workflow/agent/task/session)
    - Scope ID
    - Memory type
    - Key pattern (supports * wildcard)

    Automatically cleans up expired entries before listing.
    """
    try:
        result = SharedMemoryService.list_memory(
            session=db,
            scope=scope,
            scope_id=scope_id,
            memory_type=memory_type,
            pattern=pattern,
            limit=limit
        )

        return {
            "success": True,
            **result,
            "message": f"Retrieved {result['total']} memory entries"
        }

    except Exception as e:
        logger.error(f"Failed to list memory: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/clear-scope")
async def clear_scope(
    request: ClearScopeRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Clear all memory in a scope.

    Deletes all memory entries matching the scope and optional scope_id.

    Use with caution - this permanently deletes data.
    """
    try:
        result = SharedMemoryService.clear_scope(
            session=db,
            scope=request.scope,
            scope_id=request.scope_id
        )

        return {
            "success": True,
            **result,
            "message": f"Cleared {result['entries_deleted']} entries from scope"
        }

    except Exception as e:
        logger.error(f"Failed to clear scope: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/stats")
async def get_memory_stats(
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get memory statistics.

    Returns:
    - Total entries
    - Expired entries cleaned
    - Breakdown by scope
    - Breakdown by memory type
    - Breakdown by scope ID
    """
    try:
        stats = SharedMemoryService.get_memory_stats(session=db)

        return {
            "success": True,
            "stats": stats,
            "message": f"Memory stats: {stats['total_entries']} total entries"
        }

    except Exception as e:
        logger.error(f"Failed to get memory stats: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/snapshot/create")
async def create_snapshot(
    request: CreateSnapshotRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Create a snapshot of memory state.

    Captures current state of memory for a specific scope.
    Useful for:
    - Backup and restore
    - Debugging
    - Rollback scenarios
    """
    try:
        result = SharedMemoryService.create_snapshot(
            session=db,
            scope=request.scope,
            scope_id=request.scope_id,
            snapshot_name=request.snapshot_name
        )

        return {
            "success": True,
            **result,
            "message": f"Snapshot created with {result['entry_count']} entries"
        }

    except Exception as e:
        logger.error(f"Failed to create snapshot: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/snapshot/restore")
async def restore_snapshot(
    request: RestoreSnapshotRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Restore memory from a snapshot.

    Restores memory state from a previously created snapshot.

    Set overwrite=true to replace existing entries.
    Set overwrite=false to only restore missing entries.
    """
    try:
        result = SharedMemoryService.restore_snapshot(
            session=db,
            snapshot_key=request.snapshot_key,
            overwrite=request.overwrite
        )

        return {
            "success": True,
            **result,
            "message": f"Restored {result['entries_restored']} entries from snapshot"
        }

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to restore snapshot: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/atomic/increment")
async def atomic_increment(
    request: AtomicIncrementRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Atomically increment a numeric value.

    Thread-safe increment operation.
    Creates the key with initial value 0 if not exists.

    Useful for:
    - Counters
    - Sequence generation
    - Tracking metrics
    """
    try:
        new_value = SharedMemoryService.atomic_increment(
            session=db,
            scope=request.scope,
            key=request.key,
            scope_id=request.scope_id,
            delta=request.delta
        )

        return {
            "success": True,
            "value": new_value,
            "message": f"Incremented to {new_value}"
        }

    except Exception as e:
        logger.error(f"Failed to increment: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/atomic/cas")
async def compare_and_swap(
    request: CompareAndSwapRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Compare-and-swap operation.

    Atomically updates value only if current value matches expected value.

    Returns success=true if swap occurred, false if value mismatch.

    Useful for:
    - Lock-free synchronization
    - Conditional updates
    - Optimistic concurrency control
    """
    try:
        result = SharedMemoryService.compare_and_swap(
            session=db,
            scope=request.scope,
            key=request.key,
            expected_value=request.expected_value,
            new_value=request.new_value,
            scope_id=request.scope_id
        )

        return {
            **result,
            "message": "Swap successful" if result["success"] else "Value mismatch"
        }

    except Exception as e:
        logger.error(f"Failed compare-and-swap: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/get-or-set")
async def get_or_set(
    request: GetOrSetRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """
    Get value if exists, otherwise set default.

    Atomically returns existing value or sets and returns default.

    Useful for:
    - Lazy initialization
    - Default value handling
    - Cache-or-compute patterns
    """
    try:
        value = SharedMemoryService.get_or_set(
            session=db,
            scope=request.scope,
            key=request.key,
            default_value=request.default_value,
            scope_id=request.scope_id
        )

        return {
            "success": True,
            "value": value,
            "message": "Retrieved existing or set default value"
        }

    except Exception as e:
        logger.error(f"Failed get-or-set: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/scopes")
async def list_scopes() -> Dict[str, Any]:
    """
    List all memory scope types.

    Returns available memory scopes with descriptions.
    """
    scopes = [
        {
            "scope": MemoryScope.GLOBAL,
            "description": "Accessible by all agents globally"
        },
        {
            "scope": MemoryScope.WORKFLOW,
            "description": "Scoped to a specific workflow"
        },
        {
            "scope": MemoryScope.AGENT,
            "description": "Scoped to a specific agent"
        },
        {
            "scope": MemoryScope.TASK,
            "description": "Scoped to a specific task"
        },
        {
            "scope": MemoryScope.SESSION,
            "description": "Scoped to a session"
        }
    ]

    return {
        "success": True,
        "total_scopes": len(scopes),
        "scopes": scopes,
        "message": "List of all memory scopes"
    }


@router.get("/types")
async def list_memory_types() -> Dict[str, Any]:
    """
    List all memory type constants.

    Returns available memory types with descriptions.
    """
    types = [
        {
            "type": MemoryType.PERMANENT,
            "description": "Never expires, persists indefinitely"
        },
        {
            "type": MemoryType.TEMPORARY,
            "description": "Expires based on TTL setting"
        },
        {
            "type": MemoryType.SESSION,
            "description": "Expires when session ends"
        }
    ]

    return {
        "success": True,
        "total_types": len(types),
        "types": types,
        "message": "List of all memory types"
    }
