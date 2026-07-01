"""
WebSocket connection manager for real-time notifications
"""

from typing import Dict, Set, Any, Optional
from datetime import datetime
import json
from fastapi import WebSocket
from src.core.logging import logger


class ConnectionManager:
    """
    Manages WebSocket connections and broadcasts messages

    Features:
    - Multiple active connections
    - Room-based messaging (task-specific channels)
    - Broadcast to all or specific rooms
    - Connection lifecycle management
    """

    def __init__(self):
        """Initialize connection manager"""
        # All active connections: {connection_id: websocket}
        self.active_connections: Dict[str, WebSocket] = {}

        # Room subscriptions: {room_name: set(connection_ids)}
        self.rooms: Dict[str, Set[str]] = {}

        # User connections: {user_id: set(connection_ids)}
        self.user_connections: Dict[int, Set[str]] = {}

    async def connect(
        self,
        websocket: WebSocket,
        connection_id: str,
        user_id: Optional[int] = None
    ) -> None:
        """
        Accept and register a new WebSocket connection

        Args:
            websocket: WebSocket instance
            connection_id: Unique connection identifier
            user_id: Optional user ID for user-specific messages
        """
        await websocket.accept()
        self.active_connections[connection_id] = websocket

        # Track user connections
        if user_id:
            if user_id not in self.user_connections:
                self.user_connections[user_id] = set()
            self.user_connections[user_id].add(connection_id)

        logger.info(
            f"WebSocket connected: {connection_id} "
            f"(user: {user_id}, total: {len(self.active_connections)})"
        )

    def disconnect(self, connection_id: str, user_id: Optional[int] = None) -> None:
        """
        Remove a WebSocket connection

        Args:
            connection_id: Connection identifier
            user_id: Optional user ID
        """
        # Remove from active connections
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]

        # Remove from all rooms
        for room_name, members in self.rooms.items():
            members.discard(connection_id)

        # Remove from user connections
        if user_id and user_id in self.user_connections:
            self.user_connections[user_id].discard(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]

        logger.info(
            f"WebSocket disconnected: {connection_id} "
            f"(remaining: {len(self.active_connections)})"
        )

    def join_room(self, connection_id: str, room_name: str) -> None:
        """
        Add connection to a room for targeted messaging

        Args:
            connection_id: Connection identifier
            room_name: Room name (e.g., "task_123", "agent_45")
        """
        if room_name not in self.rooms:
            self.rooms[room_name] = set()

        self.rooms[room_name].add(connection_id)
        logger.debug(f"Connection {connection_id} joined room: {room_name}")

    def leave_room(self, connection_id: str, room_name: str) -> None:
        """
        Remove connection from a room

        Args:
            connection_id: Connection identifier
            room_name: Room name
        """
        if room_name in self.rooms:
            self.rooms[room_name].discard(connection_id)
            if not self.rooms[room_name]:
                del self.rooms[room_name]
            logger.debug(f"Connection {connection_id} left room: {room_name}")

    async def send_personal_message(
        self,
        message: Dict[str, Any],
        connection_id: str
    ) -> bool:
        """
        Send message to a specific connection

        Args:
            message: Message data
            connection_id: Target connection

        Returns:
            bool: True if sent successfully
        """
        websocket = self.active_connections.get(connection_id)
        if websocket:
            try:
                await websocket.send_json(self._format_message(message))
                return True
            except Exception as e:
                logger.error(f"Failed to send message to {connection_id}: {e}")
                self.disconnect(connection_id)
                return False
        return False

    async def send_to_user(
        self,
        message: Dict[str, Any],
        user_id: int
    ) -> int:
        """
        Send message to all connections for a specific user

        Args:
            message: Message data
            user_id: Target user ID

        Returns:
            int: Number of connections messaged
        """
        connection_ids = self.user_connections.get(user_id, set())
        sent_count = 0

        for connection_id in list(connection_ids):
            if await self.send_personal_message(message, connection_id):
                sent_count += 1

        return sent_count

    async def broadcast_to_room(
        self,
        message: Dict[str, Any],
        room_name: str
    ) -> int:
        """
        Broadcast message to all connections in a room

        Args:
            message: Message data
            room_name: Target room

        Returns:
            int: Number of connections messaged
        """
        connection_ids = self.rooms.get(room_name, set())
        sent_count = 0

        for connection_id in list(connection_ids):
            if await self.send_personal_message(message, connection_id):
                sent_count += 1

        logger.debug(
            f"Broadcast to room {room_name}: "
            f"{sent_count}/{len(connection_ids)} connections"
        )

        return sent_count

    async def broadcast_all(self, message: Dict[str, Any]) -> int:
        """
        Broadcast message to all active connections

        Args:
            message: Message data

        Returns:
            int: Number of connections messaged
        """
        sent_count = 0

        for connection_id in list(self.active_connections.keys()):
            if await self.send_personal_message(message, connection_id):
                sent_count += 1

        logger.debug(
            f"Broadcast to all: {sent_count}/{len(self.active_connections)} connections"
        )

        return sent_count

    def _format_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format message with metadata

        Args:
            message: Raw message data

        Returns:
            dict: Formatted message with timestamp
        """
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "data": message
        }

    def get_stats(self) -> Dict[str, Any]:
        """
        Get connection statistics

        Returns:
            dict: Connection statistics
        """
        return {
            "total_connections": len(self.active_connections),
            "total_rooms": len(self.rooms),
            "total_users": len(self.user_connections),
            "rooms": {
                room: len(members)
                for room, members in self.rooms.items()
            }
        }


# Global connection manager instance
connection_manager = ConnectionManager()


async def notify_task_update(
    task_id: int,
    event_type: str,
    data: Dict[str, Any]
) -> int:
    """
    Send task update notification

    Args:
        task_id: Task ID
        event_type: Event type (created, updated, completed, failed, etc.)
        data: Event data

    Returns:
        int: Number of connections notified
    """
    message = {
        "type": "task_update",
        "event": event_type,
        "task_id": task_id,
        **data
    }

    # Send to task-specific room
    room_name = f"task_{task_id}"
    count = await connection_manager.broadcast_to_room(message, room_name)

    # Also broadcast to global tasks room
    count += await connection_manager.broadcast_to_room(message, "tasks")

    logger.info(f"Task {task_id} {event_type} notification sent to {count} connections")

    return count


async def notify_agent_update(
    agent_id: int,
    event_type: str,
    data: Dict[str, Any]
) -> int:
    """
    Send agent update notification

    Args:
        agent_id: Agent ID
        event_type: Event type (status_changed, assigned, metrics_updated, etc.)
        data: Event data

    Returns:
        int: Number of connections notified
    """
    message = {
        "type": "agent_update",
        "event": event_type,
        "agent_id": agent_id,
        **data
    }

    # Send to agent-specific room
    room_name = f"agent_{agent_id}"
    count = await connection_manager.broadcast_to_room(message, room_name)

    # Also broadcast to global agents room
    count += await connection_manager.broadcast_to_room(message, "agents")

    logger.info(f"Agent {agent_id} {event_type} notification sent to {count} connections")

    return count


async def notify_workflow_update(
    task_id: int,
    node_name: str,
    progress: int,
    data: Dict[str, Any]
) -> int:
    """
    Send workflow progress notification

    Args:
        task_id: Task ID
        node_name: Current workflow node
        progress: Progress percentage
        data: Additional data

    Returns:
        int: Number of connections notified
    """
    message = {
        "type": "workflow_update",
        "event": "progress",
        "task_id": task_id,
        "node": node_name,
        "progress": progress,
        **data
    }

    # Send to task-specific room
    room_name = f"task_{task_id}"
    count = await connection_manager.broadcast_to_room(message, room_name)

    logger.debug(
        f"Workflow update for task {task_id} at node {node_name} "
        f"({progress}%) sent to {count} connections"
    )

    return count


async def notify_system_event(
    event_type: str,
    data: Dict[str, Any]
) -> int:
    """
    Send system-wide event notification

    Args:
        event_type: Event type (maintenance, alert, etc.)
        data: Event data

    Returns:
        int: Number of connections notified
    """
    message = {
        "type": "system_event",
        "event": event_type,
        **data
    }

    count = await connection_manager.broadcast_all(message)

    logger.info(f"System event {event_type} sent to {count} connections")

    return count
