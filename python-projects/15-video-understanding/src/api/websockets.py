"""
WebSocket endpoints for real-time updates
Progress tracking, notifications, and live updates
"""

import logging
import json
import asyncio
from typing import Dict, Set, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from datetime import datetime

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(tags=["websockets"])


# ============================================================================
# Connection Manager
# ============================================================================


class ConnectionManager:
    """
    Manages WebSocket connections and broadcasts

    Supports multiple connections per video/resource
    Thread-safe connection management
    """

    def __init__(self):
        # video_id -> set of active connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # All active connections
        self.all_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, resource_id: Optional[str] = None):
        """
        Accept and register a new WebSocket connection

        Args:
            websocket: WebSocket connection
            resource_id: Optional resource ID (e.g., video_id) to subscribe to
        """
        await websocket.accept()

        self.all_connections.add(websocket)

        if resource_id:
            if resource_id not in self.active_connections:
                self.active_connections[resource_id] = set()
            self.active_connections[resource_id].add(websocket)

        logger.info(f"WebSocket connected (resource={resource_id}, total={len(self.all_connections)})")

    def disconnect(self, websocket: WebSocket, resource_id: Optional[str] = None):
        """
        Remove connection from manager

        Args:
            websocket: WebSocket connection to remove
            resource_id: Resource ID the connection was subscribed to
        """
        self.all_connections.discard(websocket)

        if resource_id and resource_id in self.active_connections:
            self.active_connections[resource_id].discard(websocket)

            # Clean up empty sets
            if not self.active_connections[resource_id]:
                del self.active_connections[resource_id]

        logger.info(f"WebSocket disconnected (resource={resource_id}, total={len(self.all_connections)})")

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """
        Send message to specific connection

        Args:
            message: Message dictionary
            websocket: Target WebSocket connection
        """
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")

    async def broadcast_to_resource(self, message: dict, resource_id: str):
        """
        Broadcast message to all connections subscribed to a resource

        Args:
            message: Message dictionary
            resource_id: Resource ID to broadcast to
        """
        if resource_id not in self.active_connections:
            logger.debug(f"No connections for resource {resource_id}")
            return

        connections = list(self.active_connections[resource_id])
        disconnected = []

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Failed to send to connection: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection, resource_id)

    async def broadcast_to_all(self, message: dict):
        """
        Broadcast message to all active connections

        Args:
            message: Message dictionary
        """
        connections = list(self.all_connections)
        disconnected = []

        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Failed to broadcast: {e}")
                disconnected.append(connection)

        # Clean up disconnected clients
        for connection in disconnected:
            self.disconnect(connection)


# Global connection manager
manager = ConnectionManager()


# ============================================================================
# WebSocket Endpoints
# ============================================================================


@router.websocket("/api/ws/process/{video_id}")
async def websocket_process_updates(websocket: WebSocket, video_id: str):
    """
    WebSocket endpoint for video processing updates

    Sends real-time progress updates for video processing

    Message format:
    {
        "event": "progress" | "stage_complete" | "complete" | "error",
        "video_id": str,
        "stage": str,
        "progress": float (0-100),
        "message": str,
        "timestamp": str,
        "metadata": dict
    }

    Example usage (JavaScript):
    ```javascript
    const ws = new WebSocket('ws://localhost:8000/api/ws/process/VIDEO_ID');

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log(`Progress: ${data.progress}% - ${data.message}`);
    };
    ```
    """
    await manager.connect(websocket, video_id)

    try:
        # Send initial connection confirmation
        await manager.send_personal_message({
            "event": "connected",
            "video_id": video_id,
            "message": f"Connected to processing updates for video {video_id}",
            "timestamp": datetime.now().isoformat(),
        }, websocket)

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages from client (e.g., ping, subscriptions)
                data = await websocket.receive_text()

                # Handle ping/pong for keep-alive
                message = json.loads(data)
                if message.get("type") == "ping":
                    await manager.send_personal_message({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat(),
                    }, websocket)

            except WebSocketDisconnect:
                manager.disconnect(websocket, video_id)
                break
            except json.JSONDecodeError:
                logger.warning("Received invalid JSON from WebSocket client")
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                break

    except WebSocketDisconnect:
        manager.disconnect(websocket, video_id)
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        manager.disconnect(websocket, video_id)


@router.websocket("/api/ws/notifications")
async def websocket_notifications(websocket: WebSocket):
    """
    WebSocket endpoint for general notifications

    Receives notifications about:
    - Processing completions
    - Errors and failures
    - System events

    Message format:
    {
        "event": "notification",
        "type": "info" | "success" | "warning" | "error",
        "title": str,
        "message": str,
        "timestamp": str,
        "metadata": dict
    }
    """
    await manager.connect(websocket)

    try:
        # Send initial connection confirmation
        await manager.send_personal_message({
            "event": "connected",
            "message": "Connected to notifications",
            "timestamp": datetime.now().isoformat(),
        }, websocket)

        # Keep connection alive
        while True:
            try:
                data = await websocket.receive_text()

                # Handle ping/pong
                message = json.loads(data)
                if message.get("type") == "ping":
                    await manager.send_personal_message({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat(),
                    }, websocket)

            except WebSocketDisconnect:
                manager.disconnect(websocket)
                break
            except Exception as e:
                logger.error(f"Notification WebSocket error: {e}")
                break

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket connection error: {e}")
        manager.disconnect(websocket)


# ============================================================================
# Progress Update Functions
# ============================================================================


async def send_progress_update(
    video_id: str,
    stage: str,
    progress: float,
    message: str,
    metadata: Optional[dict] = None,
):
    """
    Send progress update to all clients watching a video

    Args:
        video_id: Video being processed
        stage: Current processing stage
        progress: Progress percentage (0-100)
        message: Human-readable message
        metadata: Optional additional data
    """
    update = {
        "event": "progress",
        "video_id": video_id,
        "stage": stage,
        "progress": progress,
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "metadata": metadata or {},
    }

    await manager.broadcast_to_resource(update, video_id)
    logger.debug(f"Progress update sent: {video_id} - {stage} - {progress}%")


async def send_stage_complete(
    video_id: str,
    stage: str,
    message: str,
    results: Optional[dict] = None,
):
    """
    Notify clients that a processing stage is complete

    Args:
        video_id: Video being processed
        stage: Completed stage name
        message: Completion message
        results: Optional stage results
    """
    update = {
        "event": "stage_complete",
        "video_id": video_id,
        "stage": stage,
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "results": results or {},
    }

    await manager.broadcast_to_resource(update, video_id)
    logger.info(f"Stage complete: {video_id} - {stage}")


async def send_processing_complete(
    video_id: str,
    message: str,
    summary: Optional[dict] = None,
):
    """
    Notify clients that video processing is complete

    Args:
        video_id: Video that finished processing
        message: Completion message
        summary: Optional processing summary
    """
    update = {
        "event": "complete",
        "video_id": video_id,
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "summary": summary or {},
    }

    await manager.broadcast_to_resource(update, video_id)

    # Also send as general notification
    await send_notification(
        notification_type="success",
        title="Processing Complete",
        message=f"Video {video_id} has finished processing",
        metadata={"video_id": video_id},
    )

    logger.info(f"Processing complete: {video_id}")


async def send_processing_error(
    video_id: str,
    stage: str,
    error_message: str,
    error_details: Optional[dict] = None,
):
    """
    Notify clients of processing error

    Args:
        video_id: Video that encountered error
        stage: Stage where error occurred
        error_message: Error description
        error_details: Optional error details
    """
    update = {
        "event": "error",
        "video_id": video_id,
        "stage": stage,
        "message": error_message,
        "timestamp": datetime.now().isoformat(),
        "error_details": error_details or {},
    }

    await manager.broadcast_to_resource(update, video_id)

    # Also send as general notification
    await send_notification(
        notification_type="error",
        title="Processing Error",
        message=f"Error processing video {video_id}: {error_message}",
        metadata={"video_id": video_id, "stage": stage},
    )

    logger.error(f"Processing error: {video_id} - {stage} - {error_message}")


async def send_notification(
    notification_type: str,
    title: str,
    message: str,
    metadata: Optional[dict] = None,
):
    """
    Send general notification to all connected clients

    Args:
        notification_type: Type of notification (info, success, warning, error)
        title: Notification title
        message: Notification message
        metadata: Optional additional data
    """
    notification = {
        "event": "notification",
        "type": notification_type,
        "title": title,
        "message": message,
        "timestamp": datetime.now().isoformat(),
        "metadata": metadata or {},
    }

    await manager.broadcast_to_all(notification)
    logger.info(f"Notification sent: {notification_type} - {title}")


# ============================================================================
# Example Usage in Processing Pipeline
# ============================================================================


async def example_processing_with_updates(video_id: str):
    """
    Example of how to use WebSocket updates in processing pipeline

    This shows how to integrate progress updates into the video processing flow
    """
    try:
        # Stage 1: Frame Extraction
        await send_progress_update(
            video_id=video_id,
            stage="frame_extraction",
            progress=10.0,
            message="Starting frame extraction...",
        )

        # ... perform frame extraction ...
        # await extract_frames(video_id)

        await send_stage_complete(
            video_id=video_id,
            stage="frame_extraction",
            message="Frame extraction complete",
            results={"frames_extracted": 120},
        )

        # Stage 2: Scene Detection
        await send_progress_update(
            video_id=video_id,
            stage="scene_detection",
            progress=25.0,
            message="Detecting scenes...",
        )

        # ... perform scene detection ...

        await send_stage_complete(
            video_id=video_id,
            stage="scene_detection",
            message="Scene detection complete",
            results={"scenes_detected": 12},
        )

        # Continue for all stages...

        # Final completion
        await send_processing_complete(
            video_id=video_id,
            message="Video processing complete!",
            summary={
                "frames": 120,
                "scenes": 12,
                "duration": 300,
                "processing_time": 180,
            },
        )

    except Exception as e:
        await send_processing_error(
            video_id=video_id,
            stage="unknown",
            error_message=str(e),
        )
        raise
