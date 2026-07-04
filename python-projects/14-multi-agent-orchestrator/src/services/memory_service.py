"""
Memory Service for managing shared memory across agents
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from src.models.shared_memory import SharedMemory, MemoryScope, MemoryType
from src.core.logging import logger


class MemoryService:
    """
    Service for managing shared memory across agents.

    Provides storage and retrieval of shared context, results,
    and state information across different scopes.
    """

    @staticmethod
    def set(
        session: Session,
        key: str,
        value: Any,
        scope: MemoryScope = MemoryScope.WORKFLOW,
        scope_id: Optional[str] = None,
        memory_type: MemoryType = MemoryType.CONTEXT,
        description: Optional[str] = None,
        created_by_agent_id: Optional[int] = None,
        is_public: bool = True,
        allowed_agent_ids: Optional[List[int]] = None,
        ttl_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> SharedMemory:
        """
        Set a value in shared memory.

        Args:
            session: Database session
            key: Memory key
            value: Value to store
            scope: Memory scope
            scope_id: Scope identifier
            memory_type: Type of memory
            description: Description
            created_by_agent_id: Creating agent ID
            is_public: Whether publicly accessible
            allowed_agent_ids: List of allowed agent IDs
            ttl_seconds: Time to live
            metadata: Additional metadata
            tags: Tags

        Returns:
            SharedMemory: Created memory entry
        """
        # Check if key exists in scope
        existing = MemoryService.get(session, key, scope, scope_id, update_access=False)

        if existing:
            # Update existing entry (create new version)
            new_memory = SharedMemory(
                key=key,
                scope=scope,
                scope_id=scope_id,
                memory_type=memory_type,
                value=value,
                description=description or existing.description,
                created_by_agent_id=created_by_agent_id or existing.created_by_agent_id,
                is_public=is_public,
                allowed_agent_ids=allowed_agent_ids,
                version=existing.version + 1,
                previous_version_id=existing.id,
                ttl_seconds=ttl_seconds or existing.ttl_seconds,
                expires_at=datetime.utcnow() + timedelta(seconds=ttl_seconds) if ttl_seconds else existing.expires_at,
                metadata=metadata or existing.metadata,
                tags=tags or existing.tags
            )
        else:
            # Create new entry
            new_memory = SharedMemory(
                key=key,
                scope=scope,
                scope_id=scope_id,
                memory_type=memory_type,
                value=value,
                description=description,
                created_by_agent_id=created_by_agent_id,
                is_public=is_public,
                allowed_agent_ids=allowed_agent_ids,
                ttl_seconds=ttl_seconds,
                expires_at=datetime.utcnow() + timedelta(seconds=ttl_seconds) if ttl_seconds else None,
                metadata=metadata,
                tags=tags
            )

        session.add(new_memory)
        session.flush()

        logger.info(f"Memory set: key={key}, scope={scope.value}, scope_id={scope_id}, version={new_memory.version}")

        return new_memory

    @staticmethod
    def get(
        session: Session,
        key: str,
        scope: MemoryScope = MemoryScope.WORKFLOW,
        scope_id: Optional[str] = None,
        agent_id: Optional[int] = None,
        update_access: bool = True
    ) -> Optional[SharedMemory]:
        """
        Get a value from shared memory.

        Args:
            session: Database session
            key: Memory key
            scope: Memory scope
            scope_id: Scope identifier
            agent_id: Requesting agent ID (for access control)
            update_access: Whether to update access tracking

        Returns:
            SharedMemory or None
        """
        # Get latest version
        query = session.query(SharedMemory).filter(
            SharedMemory.key == key,
            SharedMemory.scope == scope
        )

        if scope_id:
            query = query.filter(SharedMemory.scope_id == scope_id)

        memory = query.order_by(SharedMemory.version.desc()).first()

        if not memory:
            return None

        # Check if expired
        if memory.is_expired():
            logger.info(f"Memory expired: key={key}, scope={scope.value}")
            return None

        # Check access control
        if agent_id and not memory.is_accessible_by(agent_id):
            logger.warning(f"Access denied: agent={agent_id}, key={key}")
            return None

        # Update access tracking
        if update_access:
            memory.update_access()
            session.flush()

        return memory

    @staticmethod
    def delete(
        session: Session,
        key: str,
        scope: MemoryScope = MemoryScope.WORKFLOW,
        scope_id: Optional[str] = None
    ) -> bool:
        """
        Delete a memory entry.

        Args:
            session: Database session
            key: Memory key
            scope: Memory scope
            scope_id: Scope identifier

        Returns:
            bool: True if deleted, False if not found
        """
        query = session.query(SharedMemory).filter(
            SharedMemory.key == key,
            SharedMemory.scope == scope
        )

        if scope_id:
            query = query.filter(SharedMemory.scope_id == scope_id)

        memories = query.all()

        if not memories:
            return False

        for memory in memories:
            session.delete(memory)

        session.flush()

        logger.info(f"Memory deleted: key={key}, scope={scope.value}, versions={len(memories)}")

        return True

    @staticmethod
    def list_keys(
        session: Session,
        scope: Optional[MemoryScope] = None,
        scope_id: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[str]:
        """
        List memory keys.

        Args:
            session: Database session
            scope: Filter by scope
            scope_id: Filter by scope ID
            memory_type: Filter by memory type
            tags: Filter by tags
            limit: Result limit

        Returns:
            List of keys
        """
        query = session.query(SharedMemory.key).distinct()

        if scope:
            query = query.filter(SharedMemory.scope == scope)

        if scope_id:
            query = query.filter(SharedMemory.scope_id == scope_id)

        if memory_type:
            query = query.filter(SharedMemory.memory_type == memory_type)

        if tags:
            for tag in tags:
                query = query.filter(SharedMemory.tags.contains([tag]))

        keys = [row[0] for row in query.limit(limit).all()]

        return keys

    @staticmethod
    def get_all(
        session: Session,
        scope: Optional[MemoryScope] = None,
        scope_id: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        agent_id: Optional[int] = None,
        include_expired: bool = False,
        limit: int = 100
    ) -> List[SharedMemory]:
        """
        Get all memory entries.

        Args:
            session: Database session
            scope: Filter by scope
            scope_id: Filter by scope ID
            memory_type: Filter by memory type
            agent_id: Filter by accessible to agent
            include_expired: Include expired entries
            limit: Result limit

        Returns:
            List of SharedMemory
        """
        # Get latest versions only
        subquery = session.query(
            SharedMemory.key,
            SharedMemory.scope,
            SharedMemory.scope_id,
            session.query(SharedMemory.id).filter(
                and_(
                    SharedMemory.key == SharedMemory.key,
                    SharedMemory.scope == SharedMemory.scope,
                    or_(
                        SharedMemory.scope_id == SharedMemory.scope_id,
                        and_(SharedMemory.scope_id.is_(None), SharedMemory.scope_id.is_(None))
                    )
                )
            ).order_by(SharedMemory.version.desc()).limit(1).scalar_subquery().label('max_id')
        ).distinct().subquery()

        query = session.query(SharedMemory).filter(
            SharedMemory.id.in_(session.query(subquery.c.max_id))
        )

        if scope:
            query = query.filter(SharedMemory.scope == scope)

        if scope_id:
            query = query.filter(SharedMemory.scope_id == scope_id)

        if memory_type:
            query = query.filter(SharedMemory.memory_type == memory_type)

        memories = query.order_by(SharedMemory.created_at.desc()).limit(limit).all()

        # Filter out expired and inaccessible
        filtered = []
        for memory in memories:
            if not include_expired and memory.is_expired():
                continue

            if agent_id and not memory.is_accessible_by(agent_id):
                continue

            filtered.append(memory)

        return filtered

    @staticmethod
    def cleanup_expired(session: Session) -> int:
        """
        Clean up expired memory entries.

        Args:
            session: Database session

        Returns:
            Number of entries deleted
        """
        expired = session.query(SharedMemory).filter(
            and_(
                SharedMemory.expires_at.isnot(None),
                SharedMemory.expires_at < datetime.utcnow()
            )
        ).all()

        count = len(expired)

        for memory in expired:
            session.delete(memory)

        session.flush()

        if count > 0:
            logger.info(f"Cleaned up {count} expired memory entries")

        return count

    @staticmethod
    def get_statistics(
        session: Session,
        scope: Optional[MemoryScope] = None,
        scope_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get memory statistics.

        Args:
            session: Database session
            scope: Filter by scope
            scope_id: Filter by scope ID

        Returns:
            Statistics dictionary
        """
        query = session.query(SharedMemory)

        if scope:
            query = query.filter(SharedMemory.scope == scope)

        if scope_id:
            query = query.filter(SharedMemory.scope_id == scope_id)

        total_entries = query.count()

        return {
            "total_entries": total_entries,
            "by_scope": {
                scope.value: query.filter(SharedMemory.scope == scope).count()
                for scope in MemoryScope
            },
            "by_type": {
                mem_type.value: query.filter(SharedMemory.memory_type == mem_type).count()
                for mem_type in MemoryType
            },
            "total_access_count": sum([m.access_count for m in query.all()]),
            "scope": scope.value if scope else None,
            "scope_id": scope_id
        }
