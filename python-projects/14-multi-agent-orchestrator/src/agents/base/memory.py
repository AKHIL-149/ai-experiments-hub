"""
Agent Memory System

Provides short-term and long-term memory for agents.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field

from src.core.logging import logger


class MemoryType(str, Enum):
    """Memory item type"""
    OBSERVATION = "observation"
    ACTION = "action"
    RESULT = "result"
    REFLECTION = "reflection"
    CONTEXT = "context"


class MemoryItem(BaseModel):
    """Memory item"""
    type: MemoryType
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    importance: float = Field(default=0.5, ge=0, le=1, description="Item importance (0-1)")

    class Config:
        use_enum_values = True


class AgentMemory:
    """
    Agent Memory System

    Features:
    - Short-term memory (recent items)
    - Long-term memory (important items)
    - Memory summarization
    - Importance scoring
    - Automatic pruning
    """

    def __init__(
        self,
        max_short_term: int = 10,
        max_long_term: int = 100,
        importance_threshold: float = 0.7
    ):
        """
        Initialize memory system

        Args:
            max_short_term: Maximum short-term memory items
            max_long_term: Maximum long-term memory items
            importance_threshold: Threshold for long-term storage
        """
        self.max_short_term = max_short_term
        self.max_long_term = max_long_term
        self.importance_threshold = importance_threshold

        self.short_term: List[MemoryItem] = []
        self.long_term: List[MemoryItem] = []

        logger.info("Initialized agent memory system")

    def add(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.OBSERVATION,
        importance: float = 0.5,
        metadata: Optional[Dict[str, Any]] = None
    ) -> MemoryItem:
        """
        Add memory item

        Args:
            content: Memory content
            memory_type: Type of memory
            importance: Item importance (0-1)
            metadata: Additional metadata

        Returns:
            MemoryItem: Created memory item
        """
        item = MemoryItem(
            type=memory_type,
            content=content,
            importance=importance,
            metadata=metadata or {}
        )

        # Add to short-term memory
        self.short_term.append(item)

        # Prune short-term memory if needed
        if len(self.short_term) > self.max_short_term:
            # Move important items to long-term before pruning
            for old_item in self.short_term[:-self.max_short_term]:
                if old_item.importance >= self.importance_threshold:
                    self._add_to_long_term(old_item)

            # Keep only recent items
            self.short_term = self.short_term[-self.max_short_term:]

        logger.debug(f"Added memory: {memory_type} (importance: {importance})")

        return item

    def _add_to_long_term(self, item: MemoryItem):
        """Add item to long-term memory"""
        self.long_term.append(item)

        # Prune long-term memory if needed
        if len(self.long_term) > self.max_long_term:
            # Sort by importance and timestamp
            self.long_term.sort(key=lambda x: (x.importance, x.timestamp), reverse=True)
            self.long_term = self.long_term[:self.max_long_term]

    def get_recent(self, n: int = 5, memory_type: Optional[MemoryType] = None) -> List[MemoryItem]:
        """
        Get recent memory items

        Args:
            n: Number of items to retrieve
            memory_type: Optional type filter

        Returns:
            List[MemoryItem]: Recent memory items
        """
        items = self.short_term

        if memory_type:
            items = [item for item in items if item.type == memory_type]

        return items[-n:]

    def get_important(self, n: int = 5, min_importance: float = 0.7) -> List[MemoryItem]:
        """
        Get important memory items

        Args:
            n: Number of items to retrieve
            min_importance: Minimum importance threshold

        Returns:
            List[MemoryItem]: Important memory items
        """
        # Combine short-term and long-term
        all_items = self.short_term + self.long_term

        # Filter by importance
        important = [item for item in all_items if item.importance >= min_importance]

        # Sort by importance and timestamp
        important.sort(key=lambda x: (x.importance, x.timestamp), reverse=True)

        return important[:n]

    def search(self, query: str, n: int = 5) -> List[MemoryItem]:
        """
        Search memory by content

        Args:
            query: Search query
            n: Number of results

        Returns:
            List[MemoryItem]: Matching memory items
        """
        # Simple keyword search (can be enhanced with semantic search)
        all_items = self.short_term + self.long_term

        matches = [
            item for item in all_items
            if query.lower() in item.content.lower()
        ]

        # Sort by timestamp (most recent first)
        matches.sort(key=lambda x: x.timestamp, reverse=True)

        return matches[:n]

    def get_summary(self, max_items: int = 10) -> str:
        """
        Get memory summary

        Args:
            max_items: Maximum items to include

        Returns:
            str: Memory summary
        """
        recent = self.get_recent(max_items)

        if not recent:
            return "No memory available."

        summary_parts = []
        for item in recent:
            timestamp = item.timestamp.strftime("%H:%M:%S")
            summary_parts.append(f"[{timestamp}] {item.type}: {item.content}")

        return "\n".join(summary_parts)

    def clear_short_term(self):
        """Clear short-term memory"""
        # Move important items to long-term
        for item in self.short_term:
            if item.importance >= self.importance_threshold:
                self._add_to_long_term(item)

        self.short_term = []
        logger.info("Cleared short-term memory")

    def clear_all(self):
        """Clear all memory"""
        self.short_term = []
        self.long_term = []
        logger.info("Cleared all memory")

    def get_stats(self) -> Dict[str, Any]:
        """Get memory statistics"""
        return {
            "short_term_count": len(self.short_term),
            "long_term_count": len(self.long_term),
            "total_items": len(self.short_term) + len(self.long_term),
            "max_short_term": self.max_short_term,
            "max_long_term": self.max_long_term,
            "importance_threshold": self.importance_threshold
        }

    def __len__(self) -> int:
        """Get total memory items"""
        return len(self.short_term) + len(self.long_term)

    def __repr__(self) -> str:
        return f"<AgentMemory(short_term={len(self.short_term)}, long_term={len(self.long_term)})>"
