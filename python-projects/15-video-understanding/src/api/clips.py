"""
Video clip API endpoints
Create, manage, and download video clips
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from datetime import datetime

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api", tags=["clips"])


# ============================================================================
# Request/Response Models
# ============================================================================


class CreateClipRequest(BaseModel):
    """Request to create video clip"""
    title: Optional[str] = Field(None, description="Clip title")
    description: Optional[str] = Field(None, description="Clip description")
    start_time: float = Field(..., ge=0.0, description="Start timestamp (seconds)")
    end_time: float = Field(..., gt=0.0, description="End timestamp (seconds)")
    include_audio: bool = Field(True, description="Include audio in clip")
    format: str = Field("mp4", description="Output format (mp4, webm, gif)")
    resolution: Optional[str] = Field(None, description="Resolution (720p, 1080p, original)")
    add_fade: bool = Field(False, description="Add fade in/out effects")
    add_subtitles: bool = Field(False, description="Include subtitles from transcript")


class ClipResponse(BaseModel):
    """Clip information response"""
    clip_id: str
    video_id: str
    title: str
    description: Optional[str] = None
    start_time: float
    end_time: float
    duration: float
    file_path: Optional[str] = None
    file_size: Optional[int] = None
    format: str
    resolution: str
    status: str  # pending, processing, completed, failed
    error_message: Optional[str] = None
    thumbnail_path: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class ClipListResponse(BaseModel):
    """List of clips response"""
    clips: List[ClipResponse]
    total: int
    page: int
    page_size: int


class CreateHighlightReelRequest(BaseModel):
    """Request to create highlight reel from multiple clips"""
    title: str = Field(..., description="Reel title")
    description: Optional[str] = Field(None, description="Reel description")
    clip_ids: List[str] = Field(..., min_items=1, description="Clips to include")
    transition_type: str = Field("fade", description="Transition type (fade, cut, dissolve)")
    transition_duration: float = Field(0.5, ge=0.0, le=2.0, description="Transition duration")
    add_intro: bool = Field(False, description="Add intro card")
    intro_text: Optional[str] = Field(None, description="Intro text")
    add_outro: bool = Field(False, description="Add outro card")
    outro_text: Optional[str] = Field(None, description="Outro text")
    background_music: Optional[str] = Field(None, description="Background music file path")


class BatchClipRequest(BaseModel):
    """Request to create multiple clips"""
    video_id: str
    clips: List[CreateClipRequest]
    create_highlight_reel: bool = Field(False, description="Also create reel from clips")


def _clip_to_response(clip, db) -> "ClipResponse":
    """Map a Clip ORM row to the ClipResponse shape (video_id as the
    external/public video identifier, not the internal integer FK)"""
    from src.models import Video

    video = db.query(Video).filter(Video.id == clip.video_id).first()
    return ClipResponse(
        clip_id=clip.external_id,
        video_id=video.external_id if video else "",
        title=clip.title,
        description=clip.description,
        start_time=clip.start_time,
        end_time=clip.end_time,
        duration=clip.end_time - clip.start_time,
        file_path=clip.file_path,
        file_size=clip.file_size,
        format=clip.format,
        resolution=clip.resolution,
        status=clip.status.value,
        error_message=clip.error_message,
        thumbnail_path=clip.thumbnail_path,
        created_at=clip.created_at,
        completed_at=clip.completed_at,
    )


# ============================================================================
# Clip Creation Endpoints
# ============================================================================


@router.post("/videos/{video_id}/clip", response_model=ClipResponse)
async def create_clip(
    video_id: str,
    background_tasks: BackgroundTasks,
    request: CreateClipRequest,
):
    """
    Create a video clip from timestamp range

    - **video_id**: Source video identifier
    - **start_time**: Clip start timestamp (seconds)
    - **end_time**: Clip end timestamp (seconds)
    - **title**: Optional clip title
    - **include_audio**: Include audio track
    - **format**: Output format (mp4, webm, gif)
    - **resolution**: Output resolution
    - **add_fade**: Add fade in/out effects
    - **add_subtitles**: Burn in subtitles from transcript

    Creates clip in background and returns clip ID
    """
    try:
        # Validate timestamps
        if request.end_time <= request.start_time:
            raise HTTPException(
                status_code=400,
                detail="end_time must be greater than start_time"
            )

        logger.info(f"Creating clip for video {video_id}: {request.start_time}-{request.end_time}")

        from src.core.database import get_db
        from src.models import Video, Clip, ClipStatus

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")
            if not video.file_path:
                raise HTTPException(status_code=400, detail="Video has no source file")

            import uuid
            clip_id = str(uuid.uuid4())
            duration = request.end_time - request.start_time
            title = request.title or f"Clip {request.start_time:.1f}-{request.end_time:.1f}"

            db.add(Clip(
                external_id=clip_id,
                video_id=video.id,
                title=title,
                description=request.description,
                start_time=request.start_time,
                end_time=request.end_time,
                format=request.format,
                resolution=request.resolution or "original",
                status=ClipStatus.PENDING,
            ))

        # Schedule clip creation
        background_tasks.add_task(
            create_clip_task,
            clip_id,
            video_id,
            request,
        )

        return ClipResponse(
            clip_id=clip_id,
            video_id=video_id,
            title=title,
            description=request.description,
            start_time=request.start_time,
            end_time=request.end_time,
            duration=duration,
            format=request.format,
            resolution=request.resolution or "original",
            status="pending",
            created_at=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create clip: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create clip: {str(e)}"
        )


@router.post("/videos/{video_id}/clips/batch", response_model=ClipListResponse)
async def create_clips_batch(
    video_id: str,
    background_tasks: BackgroundTasks,
    request: BatchClipRequest,
):
    """
    Create multiple clips from a video

    - **video_id**: Source video identifier
    - **clips**: List of clip specifications
    - **create_highlight_reel**: Also create a reel from all clips

    Useful for creating multiple clips at once
    """
    try:
        logger.info(f"Creating {len(request.clips)} clips for video {video_id}")

        # TODO: Verify video exists

        clips = []
        for clip_req in request.clips:
            # Create each clip
            clip_response = await create_clip(video_id, background_tasks, clip_req)
            clips.append(clip_response)

        # If requested, create highlight reel. The individual clips above are
        # only *scheduled* at this point, not yet completed - BackgroundTasks
        # run strictly in the order they were added, so by the time this
        # task actually executes they will be, but that means (unlike
        # create_highlight_reel) we can't validate completion status yet.
        if request.create_highlight_reel:
            clip_ids = [c.clip_id for c in clips]
            total_duration = sum(c.duration for c in clips)

            from src.core.database import get_db
            from src.models import Video, Clip as ClipModel, ClipStatus

            import uuid
            reel_id = str(uuid.uuid4())
            with get_db() as db:
                source_video = db.query(Video).filter(Video.external_id == video_id).first()
                db.add(ClipModel(
                    external_id=reel_id,
                    video_id=source_video.id,
                    title="Highlight Reel",
                    start_time=0.0,
                    end_time=total_duration,
                    format="mp4",
                    resolution="original",
                    status=ClipStatus.PENDING,
                    extra_metadata={"is_reel": True, "source_clip_ids": clip_ids},
                ))

            background_tasks.add_task(
                create_highlight_reel_task,
                reel_id,
                clip_ids,
                "Highlight Reel",
                "fade",
                0.5,
            )

        return ClipListResponse(
            clips=clips,
            total=len(clips),
            page=1,
            page_size=len(clips),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create batch clips: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create batch clips: {str(e)}"
        )


@router.post("/clips/highlight-reel", response_model=ClipResponse)
async def create_highlight_reel(
    background_tasks: BackgroundTasks,
    request: CreateHighlightReelRequest,
):
    """
    Create highlight reel from multiple clips

    - **title**: Reel title
    - **clip_ids**: List of clip IDs to include
    - **transition_type**: Transition between clips (fade, cut, dissolve)
    - **transition_duration**: Transition duration (seconds)
    - **add_intro**: Add intro card
    - **intro_text**: Text for intro card
    - **add_outro**: Add outro card
    - **outro_text**: Text for outro card
    - **background_music**: Optional background music

    Concatenates clips with real transitions (fade/dissolve/wipe via
    ffmpeg). Intro/outro text cards and background music are not yet
    implemented - the underlying HighlightExporter.add_title_cards()
    is itself an unimplemented stub - so those fields are accepted but
    have no effect rather than silently claiming to work.
    """
    try:
        logger.info(f"Creating highlight reel from {len(request.clip_ids)} clips")

        from src.core.database import get_db
        from src.models import Clip as ClipModel, ClipStatus

        from src.models import Video

        with get_db() as db:
            clips = db.query(ClipModel).filter(ClipModel.external_id.in_(request.clip_ids)).all()
            if len(clips) != len(request.clip_ids):
                raise HTTPException(status_code=404, detail="One or more clips not found")
            not_ready = [c.external_id for c in clips if c.status != ClipStatus.COMPLETED]
            if not_ready:
                raise HTTPException(
                    status_code=400,
                    detail=f"Clips not ready (must be completed): {not_ready}"
                )

            # Associate the reel with the first clip's source video, so it's
            # queryable through the same /clips endpoints as a normal clip
            reel_video_id = clips[0].video_id
            reel_source_video = db.query(Video).filter(Video.id == reel_video_id).first()
            reel_source_video_ext_id = reel_source_video.external_id if reel_source_video else ""
            total_duration = sum(c.end_time - c.start_time for c in clips)

            import uuid
            reel_id = str(uuid.uuid4())
            db.add(ClipModel(
                external_id=reel_id,
                video_id=reel_video_id,
                title=request.title,
                description=request.description,
                start_time=0.0,
                end_time=total_duration,
                format="mp4",
                resolution="original",
                status=ClipStatus.PENDING,
                extra_metadata={"is_reel": True, "source_clip_ids": request.clip_ids},
            ))

        # Schedule reel creation
        background_tasks.add_task(
            create_highlight_reel_task,
            reel_id,
            request.clip_ids,
            request.title,
            request.transition_type,
            request.transition_duration,
        )

        return ClipResponse(
            clip_id=reel_id,
            video_id=reel_source_video_ext_id,
            title=request.title,
            description=request.description,
            start_time=0.0,
            end_time=total_duration,
            duration=total_duration,
            format="mp4",
            resolution="original",
            status="pending",
            created_at=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create highlight reel: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create highlight reel: {str(e)}"
        )


# ============================================================================
# Clip Retrieval Endpoints
# ============================================================================


@router.get("/clips", response_model=ClipListResponse)
async def list_clips(
    video_id: Optional[str] = Query(None, description="Filter by video"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    List all clips with pagination

    - **video_id**: Optional filter by source video
    - **status**: Optional filter by status (pending, processing, completed, failed)
    - **page**: Page number
    - **page_size**: Clips per page

    Returns paginated list of clips
    """
    try:
        logger.info(f"Listing clips (page={page}, video_id={video_id})")

        from src.core.database import get_db
        from src.models import Video, Clip as ClipModel, ClipStatus

        with get_db() as db:
            query = db.query(ClipModel)
            if video_id:
                video = db.query(Video).filter(Video.external_id == video_id).first()
                query = query.filter(ClipModel.video_id == (video.id if video else -1))
            if status:
                query = query.filter(ClipModel.status == ClipStatus(status))

            total = query.count()
            rows = (
                query.order_by(ClipModel.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            clips = [_clip_to_response(c, db) for c in rows]

        return ClipListResponse(
            clips=clips,
            total=total,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error(f"Failed to list clips: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list clips: {str(e)}"
        )


@router.get("/clips/{clip_id}", response_model=ClipResponse)
async def get_clip(clip_id: str):
    """
    Get clip details by ID

    - **clip_id**: Clip identifier

    Returns clip information and status
    """
    try:
        logger.info(f"Getting clip {clip_id}")

        from src.core.database import get_db
        from src.models import Clip as ClipModel

        with get_db() as db:
            clip = db.query(ClipModel).filter(ClipModel.external_id == clip_id).first()
            if not clip:
                raise HTTPException(status_code=404, detail="Clip not found")
            return _clip_to_response(clip, db)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get clip: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get clip: {str(e)}"
        )


@router.delete("/clips/{clip_id}")
async def delete_clip(
    clip_id: str,
    delete_file: bool = Query(True, description="Also delete clip file"),
):
    """
    Delete a clip

    - **clip_id**: Clip identifier
    - **delete_file**: Also delete the clip file (default: true)

    Returns deletion confirmation
    """
    try:
        logger.info(f"Deleting clip {clip_id}")

        import os as os_module
        from src.core.database import get_db
        from src.models import Clip as ClipModel

        with get_db() as db:
            clip = db.query(ClipModel).filter(ClipModel.external_id == clip_id).first()
            if not clip:
                raise HTTPException(status_code=404, detail="Clip not found")

            if delete_file and clip.file_path and os_module.path.exists(clip.file_path):
                os_module.remove(clip.file_path)

            db.delete(clip)

        return {
            "clip_id": clip_id,
            "success": True,
            "message": "Clip deleted successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete clip: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete clip: {str(e)}"
        )


# ============================================================================
# Clip Download Endpoints
# ============================================================================


@router.get("/clips/{clip_id}/download")
async def download_clip(clip_id: str):
    """
    Download clip file

    - **clip_id**: Clip identifier

    Returns clip file as download
    """
    try:
        logger.info(f"Downloading clip {clip_id}")

        import os as os_module
        from src.core.database import get_db
        from src.models import Clip as ClipModel, ClipStatus

        with get_db() as db:
            clip = db.query(ClipModel).filter(ClipModel.external_id == clip_id).first()
            if not clip:
                raise HTTPException(status_code=404, detail="Clip not found")
            if clip.status != ClipStatus.COMPLETED:
                raise HTTPException(status_code=400, detail="Clip not ready for download")
            if not clip.file_path or not os_module.path.exists(clip.file_path):
                raise HTTPException(status_code=404, detail="Clip file not found")

            return FileResponse(
                path=clip.file_path,
                media_type="video/mp4",
                filename=f"{clip.title}.{clip.format}",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download clip: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to download clip: {str(e)}"
        )


@router.get("/clips/{clip_id}/thumbnail")
async def get_clip_thumbnail(clip_id: str):
    """
    Get clip thumbnail image

    - **clip_id**: Clip identifier

    Returns thumbnail as image
    """
    try:
        logger.info(f"Getting thumbnail for clip {clip_id}")

        import os as os_module
        from src.core.database import get_db
        from src.models import Clip as ClipModel

        with get_db() as db:
            clip = db.query(ClipModel).filter(ClipModel.external_id == clip_id).first()
            if not clip or not clip.thumbnail_path or not os_module.path.exists(clip.thumbnail_path):
                raise HTTPException(status_code=404, detail="Thumbnail not found")

            return FileResponse(path=clip.thumbnail_path, media_type="image/jpeg")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get thumbnail: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get thumbnail: {str(e)}"
        )


# ============================================================================
# Background Task Functions
# ============================================================================


async def create_clip_task(
    clip_id: str,
    video_id: str,
    config: CreateClipRequest,
):
    """
    Create video clip in background

    Uses ffmpeg (via ClipCreator) to extract clip from source video.
    add_subtitles is not yet implemented - it's ignored rather than
    silently claimed to have worked.
    """
    import asyncio
    from pathlib import Path
    from src.core.database import get_db
    from src.models import Video, Clip as ClipModel, ClipStatus

    RESOLUTION_HEIGHTS = {"480p": 480, "720p": 720, "1080p": 1080}

    try:
        logger.info(f"Creating clip {clip_id}")

        with get_db() as db:
            clip_row = db.query(ClipModel).filter(ClipModel.external_id == clip_id).first()
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not clip_row or not video or not video.file_path:
                raise RuntimeError(f"Clip {clip_id} or its source video not found")
            clip_row.status = ClipStatus.PROCESSING
            video_path = video.file_path

        from src.services.highlights.clip_creator import ClipCreator, ClipConfig

        clip_config = ClipConfig(
            output_format=config.format,
            include_audio=config.include_audio,
            fade_in_duration=0.5 if config.add_fade else 0.0,
            fade_out_duration=0.5 if config.add_fade else 0.0,
            max_height=RESOLUTION_HEIGHTS.get(config.resolution) if config.resolution else None,
        )

        def _create():
            creator = ClipCreator(output_dir="./storage/clips")
            return creator.create_clip(
                video_path=video_path,
                start_time=config.start_time,
                end_time=config.end_time,
                video_id=video_id,
                output_filename=f"{video_id}_{clip_id}.{config.format}",
                config=clip_config,
            )

        metadata = await asyncio.to_thread(_create)

        # Thumbnail from the clip's midpoint
        thumbnail_path = None
        try:
            from src.core.video_processor import create_video_processor
            processor = create_video_processor()
            thumb_dir = Path("./storage/clips/thumbnails")
            thumb_dir.mkdir(parents=True, exist_ok=True)
            thumb_path = thumb_dir / f"{clip_id}.jpg"
            midpoint = (config.start_time + config.end_time) / 2
            await asyncio.to_thread(
                processor.extract_single_frame, Path(video_path), thumb_path, midpoint
            )
            thumbnail_path = str(thumb_path)
        except Exception as e:
            logger.warning(f"Thumbnail generation failed for clip {clip_id}: {e}")

        with get_db() as db:
            clip_row = db.query(ClipModel).filter(ClipModel.external_id == clip_id).first()
            clip_row.file_path = metadata.output_path
            clip_row.file_size = metadata.file_size_bytes
            clip_row.thumbnail_path = thumbnail_path
            clip_row.status = ClipStatus.COMPLETED
            clip_row.completed_at = datetime.now()

        logger.info(f"Clip {clip_id} created successfully: {metadata.output_path}")

    except Exception as e:
        logger.error(f"Clip creation failed: {e}", exc_info=True)
        with get_db() as db:
            clip_row = db.query(ClipModel).filter(ClipModel.external_id == clip_id).first()
            if clip_row:
                clip_row.status = ClipStatus.FAILED
                clip_row.error_message = str(e)


async def create_highlight_reel_task(
    reel_id: str,
    clip_ids: List[str],
    title: str,
    transition_type: str,
    transition_duration: float,
):
    """
    Create highlight reel from multiple clips

    Uses ffmpeg (via HighlightExporter) to concatenate clips with real
    transitions. Intro/outro cards and background music aren't
    implemented yet (see create_highlight_reel's docstring).
    """
    import asyncio
    from types import SimpleNamespace
    from src.core.database import get_db
    from src.models import Clip as ClipModel, ClipStatus

    try:
        logger.info(f"Creating highlight reel {reel_id} from {len(clip_ids)} clips")

        with get_db() as db:
            reel_row = db.query(ClipModel).filter(ClipModel.external_id == reel_id).first()
            source_clips = (
                db.query(ClipModel)
                .filter(ClipModel.external_id.in_(clip_ids))
                .all()
            )
            # Preserve the order the caller requested, not DB return order
            by_id = {c.external_id: c for c in source_clips}
            ordered_clips = [by_id[cid] for cid in clip_ids]
            clip_paths = [c.file_path for c in ordered_clips]
            durations = [c.end_time - c.start_time for c in ordered_clips]
            if not reel_row or any(p is None for p in clip_paths):
                raise RuntimeError(f"Reel {reel_id} or one of its source clips is missing a file")
            reel_row.status = ClipStatus.PROCESSING

        from src.services.highlights.exporter import HighlightExporter, ExportConfig, TransitionConfig

        export_config = ExportConfig(
            transition=TransitionConfig(
                transition_type=transition_type if transition_type != "cut" else "none",
                transition_duration=transition_duration,
            ),
        )
        # export_highlight_reel only needs .duration off each "highlight"
        fake_highlights = [SimpleNamespace(duration=d) for d in durations]

        def _export():
            exporter = HighlightExporter(output_dir="./storage/clips")
            return exporter.export_highlight_reel(
                video_id=reel_id,
                highlights=fake_highlights,
                clip_paths=clip_paths,
                reel_id=reel_id,
                output_filename=f"reel_{reel_id}.mp4",
                config=export_config,
            )

        reel_meta = await asyncio.to_thread(_export)

        with get_db() as db:
            reel_row = db.query(ClipModel).filter(ClipModel.external_id == reel_id).first()
            reel_row.file_path = reel_meta.output_path
            reel_row.file_size = reel_meta.file_size_bytes
            reel_row.status = ClipStatus.COMPLETED
            reel_row.completed_at = datetime.now()

        logger.info(f"Highlight reel {reel_id} created successfully: {reel_meta.output_path}")

    except Exception as e:
        logger.error(f"Reel creation failed: {e}", exc_info=True)
        with get_db() as db:
            reel_row = db.query(ClipModel).filter(ClipModel.external_id == reel_id).first()
            if reel_row:
                reel_row.status = ClipStatus.FAILED
                reel_row.error_message = str(e)
