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

from src.core.auth import current_caller

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
        # connection -> (account id, is administrator): a notification about a video goes to its owner only
        self.owners: Dict[WebSocket, tuple] = {}

    async def connect(
        self, websocket: WebSocket, resource_id: Optional[str] = None,
        owner_id: Optional[int] = None, is_admin: bool = False,
    ):
        """
        Accept and register a new WebSocket connection

        Args:
            websocket: WebSocket connection
            resource_id: Optional resource ID (e.g., video_id) to subscribe to
        """
        await websocket.accept()

        self.all_connections.add(websocket)
        self.owners[websocket] = (owner_id, is_admin)

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
        self.owners.pop(websocket, None)

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

    async def broadcast_to_owner(self, message: dict, owner_id: Optional[int]):
        """Send to the connections of one account (and of administrators), nobody else"""
        for connection in list(self.all_connections):
            conn_owner, is_admin = self.owners.get(connection, (None, False))
            if is_admin or (owner_id is not None and conn_owner == owner_id):
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Failed to send to connection: {e}")
                    self.disconnect(connection)

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


def _may_watch(video_id: str) -> bool:
    from src.core.database import SessionLocal
    from src.core.access import find_video
    db = SessionLocal()
    try:
        return find_video(db, video_id) is not None
    finally:
        db.close()


def _owner_of(video_id: str) -> Optional[int]:
    from src.core.database import SessionLocal
    from src.models.video import Video
    db = SessionLocal()
    try:
        row = db.query(Video.user_id).filter(Video.external_id == video_id).first()
        return row[0] if row else None
    finally:
        db.close()


async def _authorize(websocket: WebSocket, video_id: Optional[str] = None):
    """The signed-in caller, or None after refusing the connection (4401 not signed in, 4404 not your video)"""
    caller = current_caller()
    if caller is None:
        await websocket.close(code=4401)
        return None
    if video_id is not None and not await asyncio.to_thread(_may_watch, video_id):
        await websocket.close(code=4404)
        return None
    return caller


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
    caller = await _authorize(websocket, video_id)
    if caller is None:
        return
    await manager.connect(websocket, video_id, caller.user_id, caller.is_admin)

    try:
        # Send initial connection confirmation
        await manager.send_personal_message({
            "event": "connected",
            "video_id": video_id,
            "message": f"Connected to processing updates for video {video_id}",
            "timestamp": datetime.utcnow().isoformat(),
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
                        "timestamp": datetime.utcnow().isoformat(),
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
    caller = await _authorize(websocket)
    if caller is None:
        return
    await manager.connect(websocket, owner_id=caller.user_id, is_admin=caller.is_admin)

    try:
        # Send initial connection confirmation
        await manager.send_personal_message({
            "event": "connected",
            "message": "Connected to notifications",
            "timestamp": datetime.utcnow().isoformat(),
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
                        "timestamp": datetime.utcnow().isoformat(),
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


# The newest progress of each video that is being processed, so GET .../status
# can answer with it (the WebSocket is push only). Single process by design.
_latest_progress: dict = {}
_MAX_TRACKED = 200


def get_latest_progress(video_id: str) -> Optional[dict]:
    """The last {stage, progress, message} sent for a video, or None"""
    return _latest_progress.get(video_id)


def forget_progress(video_id: str) -> None:
    _latest_progress.pop(video_id, None)


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
    _latest_progress[video_id] = {"stage": stage, "progress": progress, "message": message}
    while len(_latest_progress) > _MAX_TRACKED:
        _latest_progress.pop(next(iter(_latest_progress)))

    update = {
        "event": "progress",
        "video_id": video_id,
        "stage": stage,
        "progress": progress,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
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
        "timestamp": datetime.utcnow().isoformat(),
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
    forget_progress(video_id)
    update = {
        "event": "complete",
        "video_id": video_id,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
        "summary": summary or {},
    }

    await manager.broadcast_to_resource(update, video_id)

    # Also send as general notification
    await send_notification(
        notification_type="success",
        title="Processing Complete",
        message=f"Video {video_id} has finished processing",
        metadata={"video_id": video_id},
        video_id=video_id,
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
    forget_progress(video_id)
    update = {
        "event": "error",
        "video_id": video_id,
        "stage": stage,
        "message": error_message,
        "timestamp": datetime.utcnow().isoformat(),
        "error_details": error_details or {},
    }

    await manager.broadcast_to_resource(update, video_id)

    # Also send as general notification
    await send_notification(
        notification_type="error",
        title="Processing Error",
        message=f"Error processing video {video_id}: {error_message}",
        metadata={"video_id": video_id, "stage": stage},
        video_id=video_id,
    )

    logger.error(f"Processing error: {video_id} - {stage} - {error_message}")


async def send_notification(
    notification_type: str,
    title: str,
    message: str,
    metadata: Optional[dict] = None,
    video_id: Optional[str] = None,
):
    """
    Send a notification: to the owner of `video_id` (and administrators) when it is about a video,
    otherwise to every connected client

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
        "timestamp": datetime.utcnow().isoformat(),
        "metadata": metadata or {},
    }

    if video_id:
        await manager.broadcast_to_owner(notification, await asyncio.to_thread(_owner_of, video_id))
    else:
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
