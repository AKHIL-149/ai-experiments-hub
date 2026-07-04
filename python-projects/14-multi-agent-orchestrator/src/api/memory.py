"""
Shared Memory API endpoints
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.memory_service import MemoryService
from src.models.shared_memory import MemoryScope, MemoryType
from src.core.logging import logger


router = APIRouter()


# Pydantic Models

class MemorySetRequest(BaseModel):
    """Request model for setting memory"""
    key: str
    value: Dict[str, Any]
    scope: str = "workflow"
    scope_id: Optional[str] = None
    memory_type: str = "context"
    description: Optional[str] = None
    created_by_agent_id: Optional[int] = None
    is_public: bool = True
    ttl_seconds: Optional[int] = None


class MemoryResponse(BaseModel):
    """Response model for memory"""
    id: int
    key: str
    scope: str
    scope_id: Optional[str]
    memory_type: str
    value: Dict[str, Any]
    version: int
    access_count: int


# Endpoints

@router.post("/set")
async def set_memory(
    request: MemorySetRequest,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Set a value in shared memory"""
    try:
        memory = MemoryService.set(
            session=db,
            key=request.key,
            value=request.value,
            scope=MemoryScope(request.scope),
            scope_id=request.scope_id,
            memory_type=MemoryType(request.memory_type),
            description=request.description,
            created_by_agent_id=request.created_by_agent_id,
            is_public=request.is_public,
            ttl_seconds=request.ttl_seconds
        )

        db.commit()
        return memory.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to set memory: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/get/{key}")
async def get_memory(
    key: str,
    scope: str = "workflow",
    scope_id: Optional[str] = None,
    agent_id: Optional[int] = None,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get a value from shared memory"""
    try:
        memory = MemoryService.get(
            session=db,
            key=key,
            scope=MemoryScope(scope),
            scope_id=scope_id,
            agent_id=agent_id
        )

        if not memory:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")

        db.commit()  # Commit access tracking
        return memory.to_dict()

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get memory: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/delete/{key}")
async def delete_memory(
    key: str,
    scope: str = "workflow",
    scope_id: Optional[str] = None,
    db: Session = Depends(get_db_session)
) -> Dict[str, bool]:
    """Delete a memory entry"""
    try:
        deleted = MemoryService.delete(
            session=db,
            key=key,
            scope=MemoryScope(scope),
            scope_id=scope_id
        )

        db.commit()
        return {"deleted": deleted}

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete memory: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/list")
async def list_memory_keys(
    scope: Optional[str] = None,
    scope_id: Optional[str] = None,
    memory_type: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db_session)
) -> List[str]:
    """List memory keys"""
    try:
        keys = MemoryService.list_keys(
            session=db,
            scope=MemoryScope(scope) if scope else None,
            scope_id=scope_id,
            memory_type=MemoryType(memory_type) if memory_type else None,
            limit=limit
        )

        return keys

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list memory keys: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/all")
async def get_all_memory(
    scope: Optional[str] = None,
    scope_id: Optional[str] = None,
    memory_type: Optional[str] = None,
    agent_id: Optional[int] = None,
    limit: int = 100,
    db: Session = Depends(get_db_session)
) -> List[Dict[str, Any]]:
    """Get all memory entries"""
    try:
        memories = MemoryService.get_all(
            session=db,
            scope=MemoryScope(scope) if scope else None,
            scope_id=scope_id,
            memory_type=MemoryType(memory_type) if memory_type else None,
            agent_id=agent_id,
            limit=limit
        )

        return [m.to_dict() for m in memories]

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get all memory: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/cleanup")
async def cleanup_expired(
    db: Session = Depends(get_db_session)
) -> Dict[str, int]:
    """Clean up expired memory entries"""
    try:
        count = MemoryService.cleanup_expired(session=db)
        db.commit()
        return {"deleted": count}

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to cleanup memory: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/statistics")
async def get_statistics(
    scope: Optional[str] = None,
    scope_id: Optional[str] = None,
    db: Session = Depends(get_db_session)
) -> Dict[str, Any]:
    """Get memory statistics"""
    try:
        stats = MemoryService.get_statistics(
            session=db,
            scope=MemoryScope(scope) if scope else None,
            scope_id=scope_id
        )

        return stats

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
