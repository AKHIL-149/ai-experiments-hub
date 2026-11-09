"""
Video management API endpoints
Upload, retrieve, and manage videos
"""

import asyncio
import logging
import os
import threading
import uuid
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from pydantic import BaseModel, Field
from datetime import datetime

from src.core.auth import current_caller
from src.services.video_cleanup import purge_video
from src.core.access import find_video, find_clip, find_frame, scope_videos, restrict_video_ids, can_see_video
from src.core.database import get_db
from src.utils.input_checks import (
    InvalidMedia, probe_media, short_error, is_youtube_url, check_public_http_url,
    clean_title, clean_description, fit_segments_to_duration,
)
from src.models import Video, VideoStatus, SourceType
from src.models.job import ACTIVE_STATUSES, Job, JobKind
from src.services import job_queue
from src.services.job_queue import JobCancelled, JobContext, QueueFull

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/videos", tags=["videos"])


# ============================================================================
# Request/Response Models
# ============================================================================


class VideoUploadResponse(BaseModel):
    """Response for video upload"""
    video_id: str
    title: str
    status: str
    message: str
    file_path: Optional[str] = None
    duration: Optional[float] = None
    created_at: datetime
    job_id: Optional[str] = None          # the queue job that will do the work
    queue_position: Optional[int] = None  # 1 = next in line


class YouTubeVideoRequest(BaseModel):
    """Request to process YouTube video"""
    url: str = Field(..., description="YouTube video URL")
    title: Optional[str] = Field(None, description="Optional custom title")
    download_quality: str = Field("best", description="Download quality (best, 1080p, 720p, 480p)")


class StreamingVideoRequest(BaseModel):
    """Request to process streaming video"""
    url: str = Field(..., description="Streaming video URL")
    title: Optional[str] = Field(None, description="Optional custom title")


class VideoResponse(BaseModel):
    """Video information response"""
    video_id: str
    title: str
    description: Optional[str] = None
    source_type: str
    source_url: Optional[str] = None
    duration_seconds: Optional[float] = None
    file_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    processing_status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    processed_at: Optional[datetime] = None
    metadata: dict = {}
    job_id: Optional[str] = None          # a waiting or running job for this video, if any
    job_status: Optional[str] = None      # queued | running
    queue_position: Optional[int] = None  # while queued: 1 = next in line


class VideoListResponse(BaseModel):
    """List of videos response"""
    videos: List[VideoResponse]
    total: int
    page: int
    page_size: int


class VideoStatusResponse(BaseModel):
    """Video processing status"""
    video_id: str
    status: str
    progress: float
    stage: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    job_id: Optional[str] = None
    job_status: Optional[str] = None
    queue_position: Optional[int] = None


class DeleteResponse(BaseModel):
    """Delete operation response"""
    video_id: str
    success: bool
    message: str


def _video_to_response_dict(video: Video) -> dict:
    """Map a Video ORM row to the VideoResponse field shape"""
    d = video.to_dict()
    d["video_id"] = d.pop("id")
    return d


# ============================================================================
# Video Upload Endpoints
# ============================================================================


def _upload_allowance() -> tuple:
    """
    (owner id, largest upload in MB) for the current caller, or an HTTP error when they may not add a video.
    Guests get a small allowance because their videos exist only to try the platform.
    """
    from src.core.config import settings
    caller = current_caller()
    if caller is None:
        raise HTTPException(status_code=401, detail="Not signed in")
    max_mb = settings.max_video_size_mb
    if caller.is_guest:
        max_mb = min(max_mb, settings.guest_max_video_size_mb)
    if caller.user_id is not None and not caller.is_admin:
        limit = settings.guest_max_videos if caller.is_guest else settings.max_videos_per_user
        with get_db() as db:
            count = db.query(Video).filter(Video.user_id == caller.user_id).count()
            waiting = db.query(Job).filter(Job.user_id == caller.user_id, Job.status.in_(ACTIVE_STATUSES)).count()
        if count >= limit:
            hint = "delete one or create an account" if caller.is_guest else "delete one first"
            raise HTTPException(status_code=403, detail=f"You can keep at most {limit} videos: {hint}")
        if waiting >= settings.max_queued_jobs_per_user:
            raise HTTPException(
                status_code=429,
                detail=f"You already have {waiting} videos waiting or running: wait for some to finish or cancel one",
            )
    return caller.user_id, max_mb


def _position_of(job_id: Optional[str]) -> Optional[int]:
    if not job_id:
        return None
    with get_db() as db:
        return job_queue.queue_positions(db).get(job_id)


def _job_fields(db, videos) -> dict:
    """video row id -> job_id / job_status / queue_position for the videos that have a waiting or running job"""
    active = job_queue.active_jobs_for_videos(db, [v.id for v in videos])
    if not active:
        return {}
    positions = job_queue.queue_positions(db)
    return {
        vid: {"job_id": job.id, "job_status": job.status, "queue_position": positions.get(job.id)}
        for vid, job in active.items()
    }


@router.post("/upload", response_model=VideoUploadResponse)
async def upload_video(
    file: UploadFile = File(..., description="Video file to upload"),
    title: Optional[str] = Form(None, description="Video title"),
    description: Optional[str] = Form(None, description="Video description"),
    auto_process: bool = Form(True, description="Automatically start processing"),
):
    """
    Upload a local video file

    - **file**: Video file (mp4, avi, mov, mkv, webm)
    - **title**: Optional video title (defaults to filename)
    - **description**: Optional video description
    - **auto_process**: Start processing automatically (default: true)

    Returns video ID and upload status
    """
    try:
        logger.info(f"Uploading video: {file.filename}")
        owner_id, max_mb = _upload_allowance()

        # Validate file type
        allowed_extensions = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
        import os
        file_ext = os.path.splitext(file.filename)[1].lower()

        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
            )

        # Generate video ID
        import uuid
        video_id = str(uuid.uuid4())

        # Use title or filename (never a directory part of the filename)
        video_title = clean_title(title, file.filename)
        description = clean_description(description)

        # Save uploaded file in chunks so a huge upload is refused without
        # being held in memory, and a refused one leaves nothing behind
        from src.core.config import settings
        max_bytes = max_mb * 1024 * 1024
        upload_dir = "./uploads/videos"
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, f"{video_id}{file_ext}")

        written = 0
        try:
            with open(file_path, "wb") as f:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f"Video is larger than the {max_mb} MB limit",
                        )
                    f.write(chunk)

            # The extension proves nothing: ask ffprobe what the file is
            try:
                media = await asyncio.to_thread(probe_media, file_path)
            except InvalidMedia as e:
                raise HTTPException(status_code=400, detail=str(e))
        except BaseException:
            if os.path.exists(file_path):
                os.remove(file_path)
            raise

        logger.info(f"Saved video to {file_path}")
        duration = media.duration

        job_id = position = None
        with get_db() as db:
            video = Video(
                external_id=video_id,
                user_id=owner_id,
                title=video_title,
                description=description,
                source_type=SourceType.LOCAL,
                file_path=file_path,
                duration_seconds=duration,
                processing_status=VideoStatus.PENDING,
            )
            db.add(video)
            db.flush()
            # Analysis starts when a worker is free (MAX_CONCURRENT_VIDEOS at a time), not on arrival
            if auto_process:
                job, _ = job_queue.enqueue(db, video, JobKind.PROCESS.value)
                job_id = job.id
        if auto_process:
            job_queue.notify()
            position = _position_of(job_id)
            status_msg = "Video uploaded and queued for processing"
        else:
            status_msg = "Video uploaded successfully"

        return VideoUploadResponse(
            video_id=video_id,
            title=video_title,
            status="pending" if auto_process else "uploaded",
            message=status_msg,
            file_path=file_path,
            duration=duration,
            created_at=datetime.utcnow(),
            job_id=job_id,
            queue_position=position,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/youtube", response_model=VideoUploadResponse)
async def process_youtube_video(
    request: YouTubeVideoRequest,
    auto_process: bool = True,
):
    """
    Process a YouTube video URL

    - **url**: YouTube video URL
    - **title**: Optional custom title
    - **download_quality**: Video quality (best, 1080p, 720p, 480p)
    - **auto_process**: Start processing automatically

    Downloads the video and optionally starts processing
    """
    from src.core.config import settings
    try:
        logger.info(f"Processing YouTube video: {request.url}")

        # Validate YouTube URL
        if not is_youtube_url(request.url):
            raise HTTPException(
                status_code=400,
                detail="Invalid YouTube URL"
            )

        owner_id, max_mb = _upload_allowance()

        # Generate video ID
        import uuid
        video_id = str(uuid.uuid4())

        with get_db() as db:
            video = Video(
                external_id=video_id,
                user_id=owner_id,
                title=clean_title(request.title, None) if request.title else "YouTube Video",
                source_type=SourceType.YOUTUBE,
                source_url=request.url,
                processing_status=VideoStatus.DOWNLOADING,
            )
            db.add(video)
            db.flush()
            job, _ = job_queue.enqueue(db, video, JobKind.DOWNLOAD.value, {
                "source": "youtube", "url": request.url, "title": request.title,
                "quality": request.download_quality, "auto_process": auto_process,
                "max_mb": min(max_mb, settings.yt_dlp_max_filesize_mb),
            })
            job_id = job.id
        job_queue.notify()

        return VideoUploadResponse(
            video_id=video_id,
            title=request.title or "YouTube Video",
            status="downloading",
            message="YouTube video queued for download",
            created_at=datetime.utcnow(),
            job_id=job_id,
            queue_position=_position_of(job_id),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"YouTube processing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"YouTube processing failed: {str(e)}"
        )


@router.post("/stream", response_model=VideoUploadResponse)
async def process_streaming_video(
    request: StreamingVideoRequest,
    auto_process: bool = True,
):
    """
    Process a streaming video URL

    - **url**: Streaming video URL (HTTP/HTTPS, M3U8)
    - **title**: Optional custom title
    - **auto_process**: Start processing automatically

    Downloads the video and optionally starts processing
    """
    try:
        logger.info(f"Processing streaming video: {request.url}")

        # Validate URL
        try:
            request.url = await asyncio.wait_for(
                asyncio.to_thread(check_public_http_url, request.url), timeout=8
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=400, detail="The streaming URL's host did not answer in time")
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        owner_id, max_mb = _upload_allowance()

        # Generate video ID
        import uuid
        video_id = str(uuid.uuid4())

        with get_db() as db:
            video = Video(
                external_id=video_id,
                user_id=owner_id,
                title=clean_title(request.title, None) if request.title else "Streaming Video",
                source_type=SourceType.STREAM,
                source_url=request.url,
                processing_status=VideoStatus.DOWNLOADING,
            )
            db.add(video)
            db.flush()
            job, _ = job_queue.enqueue(db, video, JobKind.DOWNLOAD.value, {
                "source": "stream", "url": request.url, "title": request.title,
                "auto_process": auto_process, "max_mb": max_mb,
            })
            job_id = job.id
        job_queue.notify()

        return VideoUploadResponse(
            video_id=video_id,
            title=request.title or "Streaming Video",
            status="downloading",
            message="Streaming video queued for download",
            created_at=datetime.utcnow(),
            job_id=job_id,
            queue_position=_position_of(job_id),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Streaming processing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Streaming processing failed: {str(e)}"
        )


# ============================================================================
# Video Retrieval Endpoints
# ============================================================================


@router.get("", response_model=VideoListResponse)
async def list_videos(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    source_type: Optional[str] = None,
):
    """
    List all videos with pagination

    - **page**: Page number (1-indexed)
    - **page_size**: Number of videos per page
    - **status**: Filter by processing status
    - **source_type**: Filter by source type (local, youtube, stream)

    Returns paginated list of videos
    """
    try:
        with get_db() as db:
            query = scope_videos(db.query(Video))
            if status:
                query = query.filter(Video.processing_status == VideoStatus(status))
            if source_type:
                query = query.filter(Video.source_type == SourceType(source_type))

            total = query.count()
            rows = (
                query.order_by(Video.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
                .all()
            )
            jobs = _job_fields(db, rows)
            videos = [VideoResponse(**_video_to_response_dict(v), **jobs.get(v.id, {})) for v in rows]

        return VideoListResponse(
            videos=videos,
            total=total,
            page=page,
            page_size=page_size,
        )

    except Exception as e:
        logger.error(f"List videos failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list videos: {str(e)}"
        )


@router.get("/{video_id}", response_model=VideoResponse)
async def get_video(video_id: str):
    """
    Get video details by ID

    - **video_id**: Video identifier

    Returns complete video information
    """
    try:
        with get_db() as db:
            video = find_video(db, video_id)
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")

            return VideoResponse(**_video_to_response_dict(video), **_job_fields(db, [video]).get(video.id, {}))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get video failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get video: {str(e)}"
        )


@router.delete("/{video_id}", response_model=DeleteResponse)
async def delete_video(
    video_id: str,
    delete_files: bool = True,
):
    """
    Delete a video

    - **video_id**: Video identifier
    - **delete_files**: Also delete video files (default: true)

    Returns deletion status
    """
    try:
        with get_db() as db:
            video = find_video(db, video_id)
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")

            # a running job notices that its video is gone at its next checkpoint and stops
            db.query(Job).filter(Job.video_id == video.id, Job.status.in_(ACTIVE_STATUSES)).update(
                {Job.cancel_requested: True}, synchronize_session=False)
            # the upload, frames, clips, thumbnails and search embeddings go too (only the upload used to)
            purge_video(db, video, delete_files=delete_files)

        return DeleteResponse(
            video_id=video_id,
            success=True,
            message="Video deleted successfully",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete video failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete video: {str(e)}"
        )


def _processing_started_at(video) -> Optional[datetime]:
    """When the latest processing run began, else when the video was added"""
    stamp = (video.extra_metadata or {}).get("processing_started_at")
    if stamp:
        try:
            return datetime.fromisoformat(stamp)
        except ValueError:
            pass
    return video.created_at


@router.get("/{video_id}/status", response_model=VideoStatusResponse)
async def get_video_status(video_id: str):
    """
    Get video processing status

    - **video_id**: Video identifier

    Returns current processing status and progress
    """
    try:
        with get_db() as db:
            video = find_video(db, video_id)
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")

            from src.api.websockets import get_latest_progress
            job = _job_fields(db, [video]).get(video.id, {})
            waiting = job.get("job_status") == "queued"
            live = get_latest_progress(video_id) if video.processing_status == VideoStatus.PROCESSING else None
            progress = 100.0 if video.processing_status == VideoStatus.COMPLETED and not job else (
                float(live["progress"]) if live and not waiting else 0.0
            )
            return VideoStatusResponse(
                video_id=video_id,
                status=video.processing_status.value,
                progress=progress,
                stage="queued" if waiting else (live["stage"] if live else video.processing_status.value),
                error_message=video.error_message,
                started_at=_processing_started_at(video),
                completed_at=video.processed_at,
                **job,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get status failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get status: {str(e)}"
        )


# ============================================================================
# Background Tasks
# ============================================================================


async def get_video_duration(file_path: str) -> float:
    """Get video duration using ffprobe"""
    try:
        import subprocess
        import json

        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            file_path,
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)

        duration = float(data["format"]["duration"])
        return duration

    except Exception as e:
        logger.warning(f"Failed to get duration: {e}")
        return 0.0


def _aggregate_scene_actions(actions: list, start_time: float, end_time: float) -> dict:
    """
    Motion-based action recognition emits one event per few frames (hundreds
    per scene), which is too granular to feed the importance scorer directly
    (it would saturate identically for every scene). Aggregate to a 0-1
    activity ratio (fraction of the scene's duration spent in a non-stationary
    action) and the single dominant action label.
    """
    scene_duration = max(end_time - start_time, 0.001)
    overlapping = [a for a in actions if a.start_time < end_time and a.end_time > start_time]

    active_seconds = sum(
        (min(a.end_time, end_time) - max(a.start_time, start_time))
        for a in overlapping if a.action != "stationary"
    )
    activity_ratio = min(1.0, active_seconds / scene_duration)

    dominant_action = None
    if overlapping:
        by_duration = {}
        for a in overlapping:
            dur = min(a.end_time, end_time) - max(a.start_time, start_time)
            by_duration[a.action] = by_duration.get(a.action, 0.0) + dur
        dominant_action = max(by_duration, key=by_duration.get)

    return {"activity_ratio": activity_ratio, "dominant_action": dominant_action}


def _run_video_analysis(video_path: str, video_uuid: str, progress_callback=None, check_cancel=None) -> dict:
    """
    Real (synchronous, CPU/IO-bound) analysis pipeline: sparse frame
    sampling, scene detection, audio transcription, per-scene keyframe
    captioning, and visual/audio understanding (objects, faces, OCR,
    actions, audio energy). Run off the event loop via asyncio.to_thread.

    progress_callback(scene_index, total_scenes), if given, is invoked
    after each scene's per-scene analysis - this is the longest-running
    part of the pipeline (BLIP/YOLO/OCR/CLIP per scene, all on CPU) and
    otherwise produces zero progress feedback for its entire duration.

    check_cancel(), if given, is called between stages and before every scene; it raises JobCancelled when the
    job was cancelled (or the server is shutting down). A stage that is already running (transcribing a long
    video, say) finishes first: it cannot be interrupted from outside.
    """
    from pathlib import Path
    from src.core.config import settings
    from src.core.video_processor import create_video_processor
    from src.services.scene_detection.content_detector import ContentBasedSceneDetector
    from src.services.scene_detection.base import SceneDetectorConfig
    from src.services.transcription_service import TranscriptionService
    from src.services.image_captioning import ImageCaptioningService
    from src.services.object_detection import ObjectDetectionService
    from src.services.face_detection import FaceDetectionService
    from src.services.ocr_service import OCRService
    from src.services.action_recognition import ActionRecognitionService
    from src.services.audio_features import AudioFeatureExtractor

    path = Path(video_path)
    processor = create_video_processor()
    checkpoint = check_cancel or (lambda: None)

    # Sparse raw frame sampling (for storage/browsing)
    frames_dir = Path(settings.frames_path) / video_uuid
    sampled_frames = processor.extract_frames(path, frames_dir, fps=0.2)
    checkpoint()

    # Real scene detection (histogram-based content detector)
    detector = ContentBasedSceneDetector(
        SceneDetectorConfig(
            threshold=settings.scene_threshold,
            min_scene_length=settings.min_scene_length,
        )
    )
    scenes = detector.detect_scenes(path)
    checkpoint()

    # Real audio transcription (local Whisper)
    audio_path = Path(settings.temp_path) / f"{video_uuid}.wav"
    processor.extract_audio(path, audio_path)
    transcriber = TranscriptionService(prefer_local=True, model_name=settings.whisper_model)
    transcription = transcriber.transcribe(audio_path, use_local=True)
    try:
        transcription.segments = fit_segments_to_duration(
            transcription.segments, probe_media(str(path)).duration
        )
    except Exception as e:
        logger.warning(f"Could not check transcript segments against the video length: {e}")

    checkpoint()

    # Real speaker diarization (pyannote.audio), if a HF token is configured
    if settings.diarization_use_auth_token and settings.hf_token:
        try:
            from src.services.speaker_diarization import SpeakerDiarization
            diarizer = SpeakerDiarization(hf_token=settings.hf_token)
            diarization_result = diarizer.diarize(audio_path)
            merged = diarizer.merge_with_transcription(diarization_result, transcription.segments)
            for seg, merged_seg in zip(transcription.segments, merged):
                seg.speaker = merged_seg["speaker"]
            logger.info(f"Diarization found {diarization_result.num_speakers} speakers")
        except Exception as e:
            logger.warning(f"Speaker diarization failed, continuing without it: {e}")

    # Real motion-based action recognition, once for the whole video
    try:
        action_result = ActionRecognitionService(method="motion_based").recognize_actions(path)
        all_actions = action_result.actions
    except Exception as e:
        logger.warning(f"Action recognition failed: {e}")
        all_actions = []

    # Real per-scene keyframe extraction, captioning (the configured Ollama vision model, BLIP as fallback), and
    # visual understanding (objects/faces/OCR) + audio energy
    captioner = ImageCaptioningService.from_settings()
    object_detector = ObjectDetectionService()
    face_detector = FaceDetectionService(backend="opencv")
    ocr = OCRService(engine="easyocr")
    audio_extractor = AudioFeatureExtractor()
    clip_model = _get_clip_model()

    keyframes_dir = frames_dir / "keyframes"
    keyframes_dir.mkdir(parents=True, exist_ok=True)
    scene_results = []
    total_scenes = len(scenes)
    for scene_index, scene in enumerate(scenes):
        checkpoint()
        ts = scene.keyframe_timestamp or scene.middle_timestamp
        kf_path = keyframes_dir / f"scene_{scene.scene_id:03d}.jpg"
        caption = ""
        objects, faces, ocr_text = [], [], ""

        try:
            processor.extract_single_frame(path, kf_path, ts)
            caption = captioner.caption_image(kf_path).text
        except Exception as e:
            logger.warning(f"Keyframe/caption failed for scene {scene.scene_id}: {e}")

        if kf_path.exists():
            try:
                objects = [o.label for o in object_detector.detect_objects(kf_path).objects]
            except Exception as e:
                logger.warning(f"Object detection failed for scene {scene.scene_id}: {e}")
            try:
                faces = [{"bbox": f.bbox, "confidence": f.confidence} for f in face_detector.detect_faces(kf_path).faces]
            except Exception as e:
                logger.warning(f"Face detection failed for scene {scene.scene_id}: {e}")
            try:
                ocr_text = ocr.extract_text(kf_path).text
            except Exception as e:
                logger.warning(f"OCR failed for scene {scene.scene_id}: {e}")

        clip_embedding = None
        if kf_path.exists():
            try:
                clip_embedding = clip_model.encode_image(kf_path)
            except Exception as e:
                logger.warning(f"CLIP embedding failed for scene {scene.scene_id}: {e}")

        action_summary = _aggregate_scene_actions(all_actions, scene.start_time, scene.end_time)

        audio_energy = 0.0
        try:
            features = audio_extractor.extract_segment_features(audio_path, scene.start_time, scene.end_time)
            # RMS energy on typical speech/ambient audio sits well under 1.0;
            # scale so a normal speaking segment isn't perpetually near zero
            audio_energy = min(1.0, features.rms_energy * 10)
        except Exception as e:
            logger.warning(f"Audio feature extraction failed for scene {scene.scene_id}: {e}")

        scene_results.append({
            "scene": scene,
            "keyframe_path": str(kf_path),
            "caption": caption,
            "objects": objects,
            "faces": faces,
            "ocr_text": ocr_text,
            "activity_ratio": action_summary["activity_ratio"],
            "dominant_action": action_summary["dominant_action"],
            "audio_energy": audio_energy,
            "clip_embedding": clip_embedding,
        })

        if progress_callback:
            try:
                progress_callback(scene_index, total_scenes)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")

    return {
        "sampled_frame_paths": [str(f) for f in sampled_frames],
        "scenes": scene_results,
        "transcription": transcription,
    }


_embedding_model = None
_model_lock = threading.Lock()  # two workers starting together must not both load a model (memory, and a race)


def _get_embedding_model():
    """Lazily load a shared sentence-transformers model for text embeddings"""
    global _embedding_model
    if _embedding_model is None:
        with _model_lock:
            if _embedding_model is None:
                from sentence_transformers import SentenceTransformer
                _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


_clip_model = None


def _get_clip_model():
    """Lazily load a shared CLIP model for real image/text visual embeddings.
    Separate vector space from _get_embedding_model()'s sentence-transformer -
    never mix the two in the same ChromaDB collection or query."""
    global _clip_model
    if _clip_model is None:
        with _model_lock:
            if _clip_model is None:
                from src.services.clip.clip_model import CLIPModel, CLIPConfig
                _clip_model = CLIPModel(CLIPConfig(device="cpu"))
    return _clip_model


def _clear_analysis(db, video) -> None:
    """Delete a video's scenes, frames, transcript, summary, highlights and chapters (not the video itself)"""
    from src.models import (
        Scene as SceneModel, Frame as FrameModel, Transcript as TranscriptModel, Summary as SummaryModel,
        Highlight as HighlightModel, Chapter as ChapterModel,
    )
    for model in (ChapterModel, HighlightModel, SummaryModel, TranscriptModel, FrameModel, SceneModel):
        db.query(model).filter(model.video_id == video.id).delete()


def _clear_embeddings(video_id: str) -> None:
    from pathlib import Path
    from src.core.config import settings
    from src.core.vector_store import VideoVectorStore
    store = VideoVectorStore(persist_directory=Path(settings.chroma_persist_directory))
    store.initialize_collections()
    store.delete_video_embeddings(video_id)


def _after_stop(video_id: str, reason: str) -> None:
    """
    A run that was stopped part-way leaves its video where the person can act on it.
    cancelled: partial results are removed and the video is "pending" again;
    shutdown: the job goes back in the queue, so the video simply waits;
    deleted: the video is gone, nothing to do.
    """
    if reason == "deleted":
        return
    with get_db() as db:
        video = db.query(Video).filter(Video.external_id == video_id).first()
        if video is None:
            return
        video.processing_status = VideoStatus.PENDING
        if reason == "cancelled":
            _clear_analysis(db, video)
            video.error_message = "Processing cancelled"
            video.processed_at = None
        else:
            video.error_message = None
    if reason == "cancelled":
        try:
            _clear_embeddings(video_id)
        except Exception as e:
            logger.warning(f"Could not remove partial embeddings of {video_id}: {e}")


async def process_video_background(video_id: str, ctx: Optional[JobContext] = None):
    """
    The analysis pipeline for one video: real analysis, DB persistence, progress updates.

    Runs as a queue job (ctx says which). Raises JobCancelled when the job was cancelled or the server is
    shutting down, and re-raises any other failure after recording it on the video, so the queue can mark the
    job failed.
    """
    import asyncio
    from pathlib import Path
    from src.core.config import settings
    from src.core.vector_store import VideoVectorStore
    from src.models import (
        Scene as SceneModel,
        SceneType as SceneTypeDB,
        TransitionType as TransitionTypeDB,
        Frame as FrameModel,
        Transcript as TranscriptModel,
        Summary as SummaryModel,
        Highlight as HighlightModel,
        Chapter as ChapterModel,
    )
    from src.api.websockets import (
        send_progress_update,
        send_stage_complete,
        send_processing_complete,
        send_processing_error,
    )

    async def checkpoint():
        if ctx is not None:
            await asyncio.to_thread(ctx.check_cancel)

    try:
        logger.info(f"Starting background processing for video {video_id}")

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise RuntimeError(f"Video {video_id} not found in database")
            video.processing_status = VideoStatus.PROCESSING
            video.error_message = None
            # when this run began (created_at is when the file was uploaded)
            video.extra_metadata = {
                **(video.extra_metadata or {}),
                "processing_started_at": datetime.utcnow().isoformat(),
            }
            file_path = video.file_path

            # Clear any prior analysis before regenerating, so running this more than once (a reprocess)
            # does not duplicate scenes/frames/transcripts (confirmed live: a second run doubled every count)
            _clear_analysis(db, video)

        await asyncio.to_thread(_clear_embeddings, video_id)
        await checkpoint()

        # Stage 1-2: Frame sampling + scene detection + transcription + captioning
        # (runs off the event loop; it's CPU/subprocess-bound)
        await send_progress_update(
            video_id=video_id,
            stage="frame_extraction",
            progress=10.0,
            message="Extracting frames and detecting scenes...",
        )

        # _run_video_analysis is the longest-running stage (per-scene BLIP/
        # YOLO/OCR/CLIP, all on CPU) and runs in a worker thread, so report
        # its progress back to the frontend via a thread-safe callback -
        # otherwise the UI sees zero updates for the whole stage and looks
        # frozen even though real work is happening (confirmed live: WS
        # connects and receives the "connected" event, then nothing until
        # the entire analysis finishes several minutes later).
        loop = asyncio.get_running_loop()

        def _on_scene_progress(scene_index: int, total_scenes: int):
            if total_scenes <= 0:
                return
            pct = 10.0 + (scene_index + 1) / total_scenes * 60.0
            asyncio.run_coroutine_threadsafe(
                send_progress_update(
                    video_id=video_id,
                    stage="scene_analysis",
                    progress=pct,
                    message=f"Analyzing scene {scene_index + 1}/{total_scenes}...",
                ),
                loop,
            )

        analysis = await asyncio.to_thread(
            _run_video_analysis, file_path, video_id, _on_scene_progress,
            ctx.check_cancel if ctx is not None else None,
        )
        transcription = analysis["transcription"]
        await checkpoint()

        await send_stage_complete(
            video_id=video_id,
            stage="frame_extraction",
            message="Frame extraction complete",
            results={"frames_extracted": len(analysis["sampled_frame_paths"])},
        )

        await send_stage_complete(
            video_id=video_id,
            stage="scene_detection",
            message="Scene detection complete",
            results={"scenes_detected": len(analysis["scenes"])},
        )

        await send_stage_complete(
            video_id=video_id,
            stage="transcription",
            message="Transcription complete",
            results={"segments": len(transcription.segments), "language": transcription.language},
        )

        await send_stage_complete(
            video_id=video_id,
            stage="visual_analysis",
            message="Visual analysis complete",
            results={"scenes_captioned": len(analysis["scenes"])},
        )

        # Stage 3: Persist scenes/frames/transcript + build real embeddings
        await send_progress_update(
            video_id=video_id,
            stage="embeddings",
            progress=80.0,
            message="Generating embeddings...",
        )

        embed_model = await asyncio.to_thread(_get_embedding_model)
        await checkpoint()

        transcript_count = 0
        caption_count = 0

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()

            scene_rows = []
            for item in analysis["scenes"]:
                s = item["scene"]
                scene_metadata = dict(s.metadata or {})
                scene_metadata.update({
                    "activity_ratio": item["activity_ratio"],
                    "dominant_action": item["dominant_action"],
                    "audio_energy": item["audio_energy"],
                })
                scene_row = SceneModel(
                    video_id=video.id,
                    scene_number=s.scene_id,
                    start_time=s.start_time,
                    end_time=s.end_time,
                    duration=s.duration,
                    frame_count=s.frame_count,
                    keyframe_path=item["keyframe_path"],
                    scene_type=SceneTypeDB(s.scene_type.value),
                    transition_type=TransitionTypeDB(s.transition_type.value),
                    description=item["caption"],
                    extra_metadata=scene_metadata,
                )
                db.add(scene_row)
                scene_rows.append(scene_row)
            db.flush()  # assign scene_row.id values

            frame_rows = []
            for item, scene_row in zip(analysis["scenes"], scene_rows):
                s = item["scene"]
                clip_emb = item.get("clip_embedding")
                frame_row = FrameModel(
                    video_id=video.id,
                    scene_id=scene_row.id,
                    timestamp=s.keyframe_timestamp or s.middle_timestamp,
                    frame_number=s.start_frame,
                    file_path=item["keyframe_path"],
                    is_keyframe=True,
                    description=item["caption"],
                    objects_detected=item["objects"],
                    faces_detected=item["faces"],
                    ocr_text=item["ocr_text"],
                    clip_embedding=clip_emb.tolist() if clip_emb is not None else None,
                )
                db.add(frame_row)
                frame_rows.append(frame_row)
            db.flush()  # assign frame_row.id values

            transcript_rows = []
            for seg in transcription.segments:
                t_row = TranscriptModel(
                    video_id=video.id,
                    start_time=seg.start,
                    end_time=seg.end,
                    text=seg.text,
                    confidence=seg.confidence,
                    language=seg.language or transcription.language,
                    speaker_id=seg.speaker,
                )
                db.add(t_row)
                transcript_rows.append(t_row)
            db.flush()

            video.duration_seconds = video.duration_seconds or transcription.duration

            # Push real text embeddings into ChromaDB for semantic search
            store = VideoVectorStore(persist_directory=Path(settings.chroma_persist_directory))
            store.initialize_collections()

            texts = [t.text for t in transcript_rows if t.text.strip()]
            if texts:
                text_rows = [t for t in transcript_rows if t.text.strip()]
                vectors = embed_model.encode(texts)
                store.add_transcript_embeddings(
                    video_id=video_id,
                    transcript_embeddings=vectors,
                    segment_ids=[str(t.id) for t in text_rows],
                    texts=texts,
                    timestamps=[(t.start_time, t.end_time) for t in text_rows],
                    # ChromaDB metadata rejects None, so use "" for
                    # segments with no diarization data
                    speakers=[t.speaker_id or "" for t in text_rows],
                )
                transcript_count = len(texts)

            caption_pairs = [
                (item["caption"], sr) for item, sr in zip(analysis["scenes"], scene_rows)
                if item["caption"].strip()
            ]
            if caption_pairs:
                captions = [c for c, _ in caption_pairs]
                caption_scene_rows = [sr for _, sr in caption_pairs]
                vectors = embed_model.encode(captions)
                store.add_scene_embeddings(
                    video_id=video_id,
                    scene_embeddings=vectors,
                    scene_numbers=[sr.scene_number for sr in caption_scene_rows],
                    scene_timestamps=[(sr.start_time, sr.end_time) for sr in caption_scene_rows],
                    scene_descriptions=captions,
                )
                caption_count = len(captions)

            frame_count = 0
            frames_with_clip = [f for f in frame_rows if f.clip_embedding]
            if frames_with_clip:
                import numpy as np
                store.add_frame_embeddings(
                    video_id=video_id,
                    frame_embeddings=np.array([f.clip_embedding for f in frames_with_clip]),
                    frame_numbers=[f.frame_number for f in frames_with_clip],
                    timestamps=[f.timestamp for f in frames_with_clip],
                    frame_paths=[f.file_path for f in frames_with_clip],
                    additional_metadata=[
                        {"scene_id": f.scene_id, "description": f.description or "", "frame_db_id": f.id}
                        for f in frames_with_clip
                    ],
                )
                frame_count = len(frames_with_clip)

            video.processing_status = VideoStatus.COMPLETED
            video.processed_at = datetime.utcnow()

        await send_stage_complete(
            video_id=video_id,
            stage="embeddings",
            message="Embedding generation complete",
            results={"embeddings_created": transcript_count + caption_count + frame_count},
        )

        # Stage 4: Summary + highlight generation (local Ollama LLM + heuristic scoring)
        await send_progress_update(
            video_id=video_id,
            stage="summarization",
            progress=95.0,
            message="Generating video summary, highlights, and chapters...",
        )

        await checkpoint()
        from src.api.analysis import (
            generate_summary_task,
            generate_highlights_task,
            generate_chapters_task,
            GenerateSummaryRequest,
            GenerateHighlightsRequest,
        )
        await generate_summary_task(video_id, GenerateSummaryRequest())
        await generate_highlights_task(video_id, GenerateHighlightsRequest())
        await generate_chapters_task(video_id)

        await send_stage_complete(
            video_id=video_id,
            stage="summarization",
            message="Summary, highlights, and chapters generated",
        )

        # Final completion
        await send_processing_complete(
            video_id=video_id,
            message="Video processing complete! ✅",
            summary={
                "frames": len(analysis["sampled_frame_paths"]),
                "scenes": len(analysis["scenes"]),
                "transcripts": transcript_count,
                "embeddings": transcript_count + caption_count + frame_count,
            },
        )

        logger.info(f"Background processing complete for video {video_id}")

    except JobCancelled as stop:
        logger.info(f"Processing of {video_id} stopped: {stop.reason}")
        await asyncio.to_thread(_after_stop, video_id, stop.reason)
        raise
    except Exception as e:
        logger.error(f"Background processing failed: {e}", exc_info=True)
        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if video:
                video.processing_status = VideoStatus.FAILED
                video.error_message = short_error(e)
        await send_processing_error(
            video_id=video_id,
            stage="unknown",
            error_message=short_error(e),
        )
        raise


# ============================================================================
# Download jobs (YouTube and streams)
# ============================================================================


def _download_finished(video_id: str, title: str, file_path: str, duration: float, auto_process: bool) -> None:
    """The file is on disk: record it, and queue the analysis when the person asked for it"""
    with get_db() as db:
        video = db.query(Video).filter(Video.external_id == video_id).first()
        if video is None:
            return
        video.title = title
        video.file_path = file_path
        video.duration_seconds = duration
        video.processing_status = VideoStatus.PENDING
        video.error_message = None
        if auto_process:
            try:
                job_queue.enqueue(db, video, JobKind.PROCESS.value)
            except QueueFull as e:
                video.error_message = str(e)
    if auto_process:
        job_queue.notify()


def _record_download_failure(video_id: str, message: str) -> None:
    with get_db() as db:
        video = db.query(Video).filter(Video.external_id == video_id).first()
        if video:
            video.processing_status = VideoStatus.FAILED
            video.error_message = message


def _download_youtube_blocking(url: str, video_id: str, quality: str, ctx: JobContext, max_mb: int):
    """yt-dlp is synchronous: it runs in a worker thread so the server keeps answering while it downloads"""
    import time
    import yt_dlp

    output_dir = "./data/uploads"
    os.makedirs(output_dir, exist_ok=True)
    last_check = [0.0]

    def on_progress(_info):
        # called many times a second: look at the cancel flag about once a second
        if time.monotonic() - last_check[0] >= 1.0:
            last_check[0] = time.monotonic()
            ctx.check_cancel()

    ydl_opts = {
        'format': f'bestvideo[height<={quality.replace("p", "")}]+bestaudio/best' if quality != 'best' else 'best',
        'outtmpl': f'{output_dir}/{video_id}.%(ext)s',
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'max_filesize': max_mb * 1024 * 1024,   # refuse (do not fill the disk with) a huge video
        'progress_hooks': [on_progress],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    return info, f"{output_dir}/{video_id}.mp4"


async def download_youtube_video(
    video_id: str,
    url: str,
    title: Optional[str],
    quality: str,
    auto_process: bool,
    ctx: Optional[JobContext] = None,
    max_mb: Optional[int] = None,
):
    """Download a YouTube video (a queue job). Raises on failure after recording it on the video."""
    from src.api.websockets import send_progress_update, send_processing_error
    from src.core.config import settings

    ctx = ctx or JobContext(job_id="", kind="download", video_id=video_id, user_id=None)
    if not ctx.job_id:
        ctx.check_cancel = lambda: None  # called directly (no queue): nothing to check
    max_mb = max_mb or settings.yt_dlp_max_filesize_mb

    try:
        logger.info(f"Downloading YouTube video: {url}")
        await send_progress_update(video_id=video_id, stage="download", progress=5.0,
                                   message="Starting YouTube video download...")

        info, file_path = await asyncio.to_thread(_download_youtube_blocking, url, video_id, quality, ctx, max_mb)
        if not os.path.exists(file_path):  # yt-dlp skips (without an error) a video over the size limit
            raise RuntimeError(f"The video is larger than the {max_mb} MB limit or could not be downloaded")

        video_title = clean_title(title or info.get('title'), None) if (title or info.get('title')) else "YouTube Video"
        duration = info.get('duration') or 0
        logger.info(f"Downloaded: {video_title} ({duration}s) -> {file_path}")

        await asyncio.to_thread(ctx.check_cancel)
        await asyncio.to_thread(_download_finished, video_id, video_title, file_path, duration, auto_process)
        await send_progress_update(video_id=video_id, stage="download", progress=30.0,
                                   message=f"Download complete: {video_title}")

    except JobCancelled as stop:
        await asyncio.to_thread(_after_download_stop, video_id, stop.reason)
        raise
    except Exception as e:
        logger.error(f"YouTube download failed: {e}")
        await asyncio.to_thread(_record_download_failure, video_id, short_error(e))
        await send_processing_error(video_id=video_id, stage="download",
                                    error_message=f"Download failed: {short_error(e)}")
        raise


def _after_download_stop(video_id: str, reason: str) -> None:
    """A download that was stopped leaves no half file behind"""
    for ext in ("mp4", "mkv", "webm", "part", "mp4.part"):
        try:
            os.remove(f"./data/uploads/{video_id}.{ext}")
        except OSError:
            pass
    if reason in ("deleted", "failed"):
        return  # (a failure records its own message)
    with get_db() as db:
        video = db.query(Video).filter(Video.external_id == video_id).first()
        if video is None:
            return
        if reason == "cancelled":
            video.processing_status = VideoStatus.FAILED
            video.error_message = "Download cancelled"
        else:  # shutdown: the job goes back in the queue and starts over
            video.processing_status = VideoStatus.DOWNLOADING
            video.error_message = None


def _download_stream_blocking(cmd: list, file_path: str, ctx: JobContext, timeout: int) -> None:
    """Run ffmpeg and watch it: it is stopped as soon as the job is cancelled (subprocess.run could not be)"""
    import subprocess
    import time

    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    started = time.monotonic()
    try:
        while True:
            try:
                _, stderr = process.communicate(timeout=1.0)
                break
            except subprocess.TimeoutExpired:
                ctx.check_cancel()
                if time.monotonic() - started > timeout:
                    raise RuntimeError("The stream took too long to download")
    except BaseException:
        process.kill()
        process.wait()
        raise
    if process.returncode != 0 or not os.path.exists(file_path):
        raise RuntimeError(f"ffmpeg failed: {(stderr or '')[-500:]}")


async def download_streaming_video(
    video_id: str,
    url: str,
    title: Optional[str],
    auto_process: bool,
    ctx: Optional[JobContext] = None,
    max_mb: Optional[int] = None,
):
    """Download a stream (HTTP/HLS) with ffmpeg (a queue job). Raises on failure after recording it."""
    from src.api.websockets import send_progress_update, send_processing_error
    from src.core.config import settings

    ctx = ctx or JobContext(job_id="", kind="download", video_id=video_id, user_id=None)
    if not ctx.job_id:
        ctx.check_cancel = lambda: None
    max_mb = max_mb or settings.max_video_size_mb

    # Safety cap: a truly live (infinite) stream would otherwise hang for ever. VOD streams finish well before.
    MAX_STREAM_DURATION_SECONDS = 3600

    try:
        logger.info(f"Downloading streaming video: {url}")
        await send_progress_update(video_id=video_id, stage="download", progress=5.0,
                                   message="Starting stream download...")

        output_dir = "./data/uploads"
        os.makedirs(output_dir, exist_ok=True)
        file_path = f"{output_dir}/{video_id}.mp4"

        cmd = [
            "ffmpeg",
            # a playlist (m3u8) can name other files: allow only the network
            # protocols, never file: or anything local
            "-protocol_whitelist", "http,https,tcp,tls,crypto",
            "-i", url,
            "-t", str(MAX_STREAM_DURATION_SECONDS),
            "-fs", str(max_mb * 1024 * 1024),   # stop writing at the size limit instead of filling the disk
            "-c", "copy",
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            file_path,
        ]
        await asyncio.to_thread(_download_stream_blocking, cmd, file_path, ctx, MAX_STREAM_DURATION_SECONDS + 60)

        duration = await get_video_duration(file_path)
        video_title = clean_title(title, None) if title else "Streaming Video"
        logger.info(f"Downloaded stream: {video_title} ({duration:.1f}s) -> {file_path}")

        await asyncio.to_thread(ctx.check_cancel)
        await asyncio.to_thread(_download_finished, video_id, video_title, file_path, duration, auto_process)
        await send_progress_update(video_id=video_id, stage="download", progress=30.0,
                                   message=f"Download complete: {video_title}")

    except JobCancelled as stop:
        await asyncio.to_thread(_after_download_stop, video_id, stop.reason)
        raise
    except Exception as e:
        logger.error(f"Streaming download failed: {e}")
        await asyncio.to_thread(_after_download_stop, video_id, "failed")
        await asyncio.to_thread(_record_download_failure, video_id, short_error(e))
        await send_processing_error(video_id=video_id, stage="download",
                                    error_message=f"Stream download failed: {short_error(e)}")
        raise


# ============================================================================
# Queue runners: how the queue starts each kind of job
# ============================================================================


async def run_process_job(ctx: JobContext) -> None:
    await process_video_background(ctx.video_id, ctx)


async def run_download_job(ctx: JobContext) -> None:
    payload = ctx.payload
    if payload.get("source") == "youtube":
        await download_youtube_video(
            ctx.video_id, payload["url"], payload.get("title"), payload.get("quality", "best"),
            bool(payload.get("auto_process", True)), ctx, payload.get("max_mb"),
        )
    else:
        await download_streaming_video(
            ctx.video_id, payload["url"], payload.get("title"), bool(payload.get("auto_process", True)),
            ctx, payload.get("max_mb"),
        )


QUEUE_RUNNERS = {JobKind.PROCESS.value: run_process_job, JobKind.DOWNLOAD.value: run_download_job}
