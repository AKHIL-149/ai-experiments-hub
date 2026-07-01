"""
WebSocket API endpoints for real-time notifications
"""

from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from uuid import uuid4
import json

from src.core.websocket import connection_manager
from src.core.auth import get_current_user_ws
from src.core.logging import logger


router = APIRouter()


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
        # Authenticate user if token provided
        if token:
            try:
                # In production, validate JWT token here
                # For now, we'll accept any token and extract user info
                # user = await get_current_user_ws(token)
                # user_id = user.id
                pass
            except Exception as e:
                logger.warning(f"WebSocket auth failed: {e}")
                await websocket.close(code=1008, reason="Invalid token")
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
        # Authenticate if token provided
        if token:
            try:
                # Validate token and get user
                pass
            except Exception as e:
                logger.warning(f"WebSocket auth failed: {e}")
                await websocket.close(code=1008, reason="Invalid token")
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
        # Authenticate if token provided
        if token:
            try:
                # Validate token and get user
                pass
            except Exception as e:
                logger.warning(f"WebSocket auth failed: {e}")
                await websocket.close(code=1008, reason="Invalid token")
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
