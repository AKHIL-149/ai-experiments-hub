"""
Video processing API endpoints
Start processing, get results (scenes, transcripts, frames)
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from datetime import datetime

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/videos", tags=["processing"])


# ============================================================================
# Request/Response Models
# ============================================================================


class ProcessVideoRequest(BaseModel):
    """Request to process video"""
    extract_scenes: bool = Field(True, description="Extract scenes")
    extract_frames: bool = Field(True, description="Extract frames")
    transcribe_audio: bool = Field(True, description="Transcribe audio")
    analyze_visual: bool = Field(True, description="Analyze visual content")
    generate_embeddings: bool = Field(True, description="Generate embeddings")
    generate_summary: bool = Field(True, description="Generate summary")
    detect_highlights: bool = Field(True, description="Detect highlights")


class ProcessVideoResponse(BaseModel):
    """Response for process video request"""
    video_id: str
    status: str
    message: str
    started_at: datetime


class SceneResponse(BaseModel):
    """Scene information"""
    scene_id: int
    scene_number: int
    start_time: float
    end_time: float
    duration: float
    frame_count: int
    keyframe_path: Optional[str] = None
    scene_type: Optional[str] = None
    transition_type: Optional[str] = None
    description: Optional[str] = None


class ScenesListResponse(BaseModel):
    """List of scenes"""
    video_id: str
    scenes: List[SceneResponse]
    total_scenes: int
    total_duration: float


class TranscriptSegment(BaseModel):
    """Transcript segment"""
    segment_id: str
    start_time: float
    end_time: float
    text: str
    speaker_id: Optional[str] = None
    speaker_name: Optional[str] = None
    confidence: Optional[float] = None


class TranscriptResponse(BaseModel):
    """Full transcript"""
    video_id: str
    segments: List[TranscriptSegment]
    total_segments: int
    total_duration: float
    language: Optional[str] = None
    num_speakers: int


class FrameResponse(BaseModel):
    """Frame information"""
    frame_id: str
    frame_number: int
    timestamp: float
    file_path: str
    is_keyframe: bool
    scene_id: Optional[int] = None
    description: Optional[str] = None


class FramesListResponse(BaseModel):
    """List of frames"""
    video_id: str
    frames: List[FrameResponse]
    total_frames: int
    page: int
    page_size: int


class ReprocessRequest(BaseModel):
    """Request to reprocess video"""
    reprocess_scenes: bool = Field(False, description="Reprocess scenes")
    reprocess_transcription: bool = Field(False, description="Reprocess transcription")
    reprocess_visual: bool = Field(False, description="Reprocess visual analysis")
    regenerate_embeddings: bool = Field(False, description="Regenerate embeddings")


# ============================================================================
# Processing Control Endpoints
# ============================================================================


@router.post("/{video_id}/process", response_model=ProcessVideoResponse)
async def process_video(
    video_id: str,
    background_tasks: BackgroundTasks,
    request: Optional[ProcessVideoRequest] = None,
):
    """
    Start video processing - typically for a video uploaded with
    auto_process=false, but also safe to call again on an
    already-completed video (it clears prior results first, same as
    /reprocess).

    - **video_id**: Video identifier

    Runs the full pipeline (frames, scenes, transcription, diarization,
    visual understanding, embeddings, summary, highlights) - the
    per-stage flags on the request body are not yet honored, it's
    all-or-nothing.

    Returns processing status
    """
    try:
        logger.info(f"Starting processing for video {video_id}")

        from src.core.database import get_db
        from src.models import Video, VideoStatus
        from src.api.videos import process_video_background

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")
            if not video.file_path:
                raise HTTPException(status_code=400, detail="Video has no source file yet (still downloading?)")
            if video.processing_status == VideoStatus.PROCESSING:
                raise HTTPException(status_code=409, detail="Video is already being processed")

            video.processing_status = VideoStatus.PROCESSING

        # Schedule the real processing pipeline
        background_tasks.add_task(process_video_background, video_id)

        return ProcessVideoResponse(
            video_id=video_id,
            status="processing",
            message="Video processing started",
            started_at=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start processing: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start processing: {str(e)}"
        )


@router.post("/{video_id}/reprocess", response_model=ProcessVideoResponse)
async def reprocess_video(
    video_id: str,
    background_tasks: BackgroundTasks,
    request: ReprocessRequest,
):
    """
    Reprocess a video from scratch.

    - **video_id**: Video identifier

    Re-runs the full pipeline; process_video_background clears prior
    scenes/frames/transcript/summaries/highlights/chapters (and their
    vector embeddings) itself before regenerating, so this is safe to
    call on an already-completed video. The per-stage flags on the
    request body are not yet honored - this always does a full
    reprocess, not a selective one.

    Returns processing status
    """
    try:
        logger.info(f"Reprocessing video {video_id}")

        from src.core.database import get_db
        from src.models import Video, VideoStatus
        from src.api.videos import process_video_background

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")
            if not video.file_path:
                raise HTTPException(status_code=400, detail="Video has no source file to reprocess")
            if video.processing_status == VideoStatus.PROCESSING:
                raise HTTPException(status_code=409, detail="Video is already being processed")

            video.processed_at = None
            video.error_message = None

        # Schedule the real processing pipeline (it clears prior data itself)
        background_tasks.add_task(process_video_background, video_id)

        return ProcessVideoResponse(
            video_id=video_id,
            status="processing",
            message="Video reprocessing started",
            started_at=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start reprocessing: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start reprocessing: {str(e)}"
        )


# ============================================================================
# Results Retrieval Endpoints
# ============================================================================


@router.get("/{video_id}/scenes", response_model=ScenesListResponse)
async def get_video_scenes(video_id: str):
    """
    Get detected scenes for a video

    - **video_id**: Video identifier

    Returns all detected scenes with metadata
    """
    try:
        logger.info(f"Getting scenes for video {video_id}")

        from src.core.database import get_db
        from src.models import Video, Scene

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")

            rows = db.query(Scene).filter(Scene.video_id == video.id).order_by(Scene.start_time).all()

            scenes = [
                SceneResponse(
                    scene_id=s.id,
                    scene_number=s.scene_number,
                    start_time=s.start_time,
                    end_time=s.end_time,
                    duration=s.duration,
                    frame_count=s.frame_count or 0,
                    keyframe_path=s.keyframe_path,
                    scene_type=s.scene_type.value if s.scene_type else None,
                    transition_type=s.transition_type.value if s.transition_type else None,
                    description=s.description,
                )
                for s in rows
            ]
            total_duration = sum(s.duration for s in scenes)

        return ScenesListResponse(
            video_id=video_id,
            scenes=scenes,
            total_scenes=len(scenes),
            total_duration=total_duration,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scenes: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get scenes: {str(e)}"
        )


@router.get("/{video_id}/transcript", response_model=TranscriptResponse)
async def get_video_transcript(
    video_id: str,
    speaker_id: Optional[str] = Query(None, description="Filter by speaker"),
):
    """
    Get transcript for a video

    - **video_id**: Video identifier
    - **speaker_id**: Optional filter by speaker

    Returns full transcript with timestamps
    """
    try:
        logger.info(f"Getting transcript for video {video_id}")

        from src.core.database import get_db
        from src.models import Video, Transcript

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")

            query = db.query(Transcript).filter(Transcript.video_id == video.id)
            if speaker_id:
                query = query.filter(Transcript.speaker_id == speaker_id)
            rows = query.order_by(Transcript.start_time).all()

            segments = [
                TranscriptSegment(
                    segment_id=str(t.id),
                    start_time=t.start_time,
                    end_time=t.end_time,
                    text=t.text,
                    speaker_id=t.speaker_id,
                    confidence=t.confidence,
                )
                for t in rows
            ]
            language = rows[0].language if rows else None
            num_speakers = len({s.speaker_id for s in segments if s.speaker_id})
            total_duration = max((s.end_time for s in segments), default=0.0)

        return TranscriptResponse(
            video_id=video_id,
            segments=segments,
            total_segments=len(segments),
            total_duration=total_duration,
            language=language,
            num_speakers=num_speakers,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get transcript: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get transcript: {str(e)}"
        )


@router.get("/{video_id}/frames", response_model=FramesListResponse)
async def get_video_frames(
    video_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=200, description="Frames per page"),
    keyframes_only: bool = Query(False, description="Only return keyframes"),
    scene_id: Optional[int] = Query(None, description="Filter by scene"),
):
    """
    Get extracted frames for a video

    - **video_id**: Video identifier
    - **page**: Page number
    - **page_size**: Frames per page
    - **keyframes_only**: Only return keyframes
    - **scene_id**: Filter by scene ID

    Returns paginated list of frames
    """
    try:
        logger.info(f"Getting frames for video {video_id}")

        from src.core.database import get_db
        from src.models import Video, Frame

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")

            query = db.query(Frame).filter(Frame.video_id == video.id)
            if keyframes_only:
                query = query.filter(Frame.is_keyframe == True)
            if scene_id is not None:
                query = query.filter(Frame.scene_id == scene_id)

            total = query.count()
            rows = (
                query.order_by(Frame.timestamp)
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )

            frames = [
                FrameResponse(
                    frame_id=str(f.id),
                    frame_number=f.frame_number,
                    timestamp=f.timestamp,
                    file_path=f.file_path or "",
                    is_keyframe=f.is_keyframe,
                    scene_id=f.scene_id,
                    description=f.description,
                )
                for f in rows
            ]

        return FramesListResponse(
            video_id=video_id,
            frames=frames,
            total_frames=total,
            page=page,
            page_size=page_size,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get frames: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get frames: {str(e)}"
        )


@router.get("/{video_id}/keyframes", response_model=FramesListResponse)
async def get_video_keyframes(video_id: str):
    """
    Get keyframes for a video

    - **video_id**: Video identifier

    Returns all keyframes (one per scene)
    """
    return await get_video_frames(
        video_id=video_id,
        page=1,
        page_size=1000,
        keyframes_only=True,
        scene_id=None,
    )


