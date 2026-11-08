"""
WebSocket API endpoints for real-time notifications
"""

from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from uuid import uuid4
import json

import asyncio

from fastapi import HTTPException

from src.core import portal
from src.core.auth import authenticate_token
from src.core.database import SessionLocal
from src.core.websocket import connection_manager
from src.core.logging import logger
from src.models.task import Task


router = APIRouter()


async def authenticate_socket(websocket: WebSocket, token: Optional[str], admin_only: bool = False):
    """
    The user id of a valid token (None when sign-in is not required and none was given); closes the
    socket and returns False if it is not allowed in. Browsers cannot set headers on a WebSocket,
    so these endpoints take the access token in the query string.
    """
    if not portal.REQUIRE_LOGIN and not token:
        return None

    def check():
        db = SessionLocal()
        try:
            user, _ = authenticate_token(token or "", db)
            return user.id, user.is_admin()
        finally:
            db.close()

    try:
        user_id, is_admin = await asyncio.to_thread(check)
    except HTTPException:
        await websocket.close(code=1008, reason="Invalid or missing token")
        return False
    if admin_only and not is_admin:
        await websocket.close(code=1008, reason="Admin only")
        return False
    return user_id


async def can_watch_task(user_id: Optional[int], task_id: int) -> bool:
    """You may follow your own tasks (an admin or a disabled sign-in gate: any task)"""
    if user_id is None:
        return True

    def check():
        db = SessionLocal()
        try:
            from src.models.user import User
            user = db.query(User).filter(User.id == user_id).first()
            if user is not None and user.is_admin():
                return True
            owner = db.query(Task.created_by_user_id).filter(Task.id == task_id).first()
            return owner is not None and owner[0] == user_id
        finally:
            db.close()

    return await asyncio.to_thread(check)


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    Main WebSocket endpoint for real-time notifications

    Connect to receive updates about:
    - Task status changes
    - Agent status changes
    - Workflow progress
    - System events

    Usage:
        ws://localhost:8001/api/ws?token=<access_token>

    Message format:
        {
            "timestamp": "2024-01-15T10:30:00.000Z",
            "data": {
                "type": "task_update",
                "event": "status_changed",
                "task_id": 123,
                "status": "in_progress",
                ...
            }
        }
    """
    connection_id = str(uuid4())
    user_id = None

    try:
        # Signed-in users only; the broadcast channel carries every user's events, so it is admin-only
        user_id = await authenticate_socket(websocket, token, admin_only=True)
        if user_id is False:
            return

        # Accept connection
        await connection_manager.connect(websocket, connection_id, user_id)

        # Send welcome message
        await websocket.send_json({
            "type": "connection",
            "event": "connected",
            "connection_id": connection_id,
            "message": "WebSocket connection established"
        })

        # Listen for messages
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                await handle_client_message(websocket, connection_id, message)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON format"
                })
            except Exception as e:
                logger.error(f"Error handling message: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": "Failed to process message"
                })

    except WebSocketDisconnect:
        connection_manager.disconnect(connection_id, user_id)
        logger.info(f"WebSocket disconnected: {connection_id}")

    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        connection_manager.disconnect(connection_id, user_id)


async def handle_client_message(
    websocket: WebSocket,
    connection_id: str,
    message: dict
):
    """
    Handle incoming messages from client

    Supported message types:
    - subscribe: Subscribe to a room/channel
    - unsubscribe: Unsubscribe from a room/channel
    - ping: Heartbeat/keepalive

    Args:
        websocket: WebSocket connection
        connection_id: Connection identifier
        message: Parsed message data
    """
    message_type = message.get("type")

    if message_type == "subscribe":
        # Subscribe to a room (e.g., specific task or agent)
        room_name = message.get("room")
        if room_name:
            connection_manager.join_room(connection_id, room_name)
            await websocket.send_json({
                "type": "subscription",
                "event": "subscribed",
                "room": room_name
            })
            logger.debug(f"Connection {connection_id} subscribed to {room_name}")

    elif message_type == "unsubscribe":
        # Unsubscribe from a room
        room_name = message.get("room")
        if room_name:
            connection_manager.leave_room(connection_id, room_name)
            await websocket.send_json({
                "type": "subscription",
                "event": "unsubscribed",
                "room": room_name
            })
            logger.debug(f"Connection {connection_id} unsubscribed from {room_name}")

    elif message_type == "ping":
        # Respond to ping with pong
        await websocket.send_json({
            "type": "pong",
            "timestamp": message.get("timestamp")
        })

    elif message_type == "get_stats":
        # Send connection statistics
        stats = connection_manager.get_stats()
        await websocket.send_json({
            "type": "stats",
            "data": stats
        })

    else:
        await websocket.send_json({
            "type": "error",
            "message": f"Unknown message type: {message_type}"
        })


@router.websocket("/ws/tasks/{task_id}")
async def task_websocket(
    websocket: WebSocket,
    task_id: int,
    token: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for task-specific updates

    Connect to receive real-time updates for a specific task:
    - Status changes
    - Progress updates
    - Workflow node transitions
    - Agent assignments

    Usage:
        ws://localhost:8001/api/ws/tasks/123?token=<access_token>
    """
    connection_id = str(uuid4())
    user_id = None
    room_name = f"task_{task_id}"

    try:
        user_id = await authenticate_socket(websocket, token)
        if user_id is False:
            return
        if not await can_watch_task(user_id, task_id):
            await websocket.close(code=1008, reason="Task not found")
            return

        # Accept connection and join task room
        await connection_manager.connect(websocket, connection_id, user_id)
        connection_manager.join_room(connection_id, room_name)

        # Send welcome message
        await websocket.send_json({
            "type": "connection",
            "event": "connected",
            "connection_id": connection_id,
            "task_id": task_id,
            "message": f"Connected to task {task_id} updates"
        })

        # Keep connection alive
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                await handle_client_message(websocket, connection_id, message)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON format"
                })

    except WebSocketDisconnect:
        connection_manager.leave_room(connection_id, room_name)
        connection_manager.disconnect(connection_id, user_id)
        logger.info(f"Task {task_id} WebSocket disconnected: {connection_id}")

    except Exception as e:
        logger.error(f"Task {task_id} WebSocket error: {e}")
        connection_manager.disconnect(connection_id, user_id)


@router.websocket("/ws/agents/{agent_id}")
async def agent_websocket(
    websocket: WebSocket,
    agent_id: int,
    token: Optional[str] = Query(None)
):
    """
    WebSocket endpoint for agent-specific updates

    Connect to receive real-time updates for a specific agent:
    - Status changes
    - Task assignments
    - Performance metrics updates

    Usage:
        ws://localhost:8001/api/ws/agents/45?token=<access_token>
    """
    connection_id = str(uuid4())
    user_id = None
    room_name = f"agent_{agent_id}"

    try:
        user_id = await authenticate_socket(websocket, token)
        if user_id is False:
            return

        # Accept connection and join agent room
        await connection_manager.connect(websocket, connection_id, user_id)
        connection_manager.join_room(connection_id, room_name)

        # Send welcome message
        await websocket.send_json({
            "type": "connection",
            "event": "connected",
            "connection_id": connection_id,
            "agent_id": agent_id,
            "message": f"Connected to agent {agent_id} updates"
        })

        # Keep connection alive
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                await handle_client_message(websocket, connection_id, message)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON format"
                })

    except WebSocketDisconnect:
        connection_manager.leave_room(connection_id, room_name)
        connection_manager.disconnect(connection_id, user_id)
        logger.info(f"Agent {agent_id} WebSocket disconnected: {connection_id}")

    except Exception as e:
        logger.error(f"Agent {agent_id} WebSocket error: {e}")
        connection_manager.disconnect(connection_id, user_id)


@router.get("/ws/stats")
async def get_websocket_stats():
    """
    Get WebSocket connection statistics

    Returns:
        dict: Connection statistics including total connections, rooms, etc.
    """
    return connection_manager.get_stats()
