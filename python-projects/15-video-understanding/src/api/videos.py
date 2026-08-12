"""
Video management API endpoints
Upload, retrieve, and manage videos
"""

import logging
import os
import uuid
from typing import Optional, List
from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Form
from pydantic import BaseModel, Field
from datetime import datetime

from src.core.database import get_db
from src.models import Video, VideoStatus, SourceType

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


@router.post("/upload", response_model=VideoUploadResponse)
async def upload_video(
    background_tasks: BackgroundTasks,
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

        # Use title or filename
        video_title = title or os.path.splitext(file.filename)[0]

        # Save uploaded file
        upload_dir = "./uploads/videos"
        os.makedirs(upload_dir, exist_ok=True)

        file_path = os.path.join(upload_dir, f"{video_id}{file_ext}")

        # Write file
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        logger.info(f"Saved video to {file_path}")

        # Get video duration using ffprobe
        duration = await get_video_duration(file_path)

        with get_db() as db:
            video = Video(
                external_id=video_id,
                title=video_title,
                description=description,
                source_type=SourceType.LOCAL,
                file_path=file_path,
                duration_seconds=duration,
                processing_status=VideoStatus.PENDING,
            )
            db.add(video)

        # Schedule processing if auto_process
        if auto_process:
            background_tasks.add_task(process_video_background, video_id)
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
            created_at=datetime.now(),
        )

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/youtube", response_model=VideoUploadResponse)
async def process_youtube_video(
    background_tasks: BackgroundTasks,
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
    try:
        logger.info(f"Processing YouTube video: {request.url}")

        # Validate YouTube URL
        if not ("youtube.com" in request.url or "youtu.be" in request.url):
            raise HTTPException(
                status_code=400,
                detail="Invalid YouTube URL"
            )

        # Generate video ID
        import uuid
        video_id = str(uuid.uuid4())

        with get_db() as db:
            video = Video(
                external_id=video_id,
                title=request.title or "YouTube Video",
                source_type=SourceType.YOUTUBE,
                source_url=request.url,
                processing_status=VideoStatus.DOWNLOADING,
            )
            db.add(video)

        # Download video using yt-dlp (in background)
        background_tasks.add_task(
            download_youtube_video,
            video_id,
            request.url,
            request.title,
            request.download_quality,
            auto_process,
        )

        return VideoUploadResponse(
            video_id=video_id,
            title=request.title or "YouTube Video",
            status="downloading",
            message="YouTube video download started",
            created_at=datetime.now(),
        )

    except Exception as e:
        logger.error(f"YouTube processing failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"YouTube processing failed: {str(e)}"
        )


@router.post("/stream", response_model=VideoUploadResponse)
async def process_streaming_video(
    background_tasks: BackgroundTasks,
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
        if not (request.url.startswith("http://") or request.url.startswith("https://")):
            raise HTTPException(
                status_code=400,
                detail="Invalid streaming URL (must be HTTP/HTTPS)"
            )

        # Generate video ID
        import uuid
        video_id = str(uuid.uuid4())

        with get_db() as db:
            video = Video(
                external_id=video_id,
                title=request.title or "Streaming Video",
                source_type=SourceType.STREAM,
                source_url=request.url,
                processing_status=VideoStatus.DOWNLOADING,
            )
            db.add(video)

        # Download video in background
        background_tasks.add_task(
            download_streaming_video,
            video_id,
            request.url,
            request.title,
            auto_process,
        )

        return VideoUploadResponse(
            video_id=video_id,
            title=request.title or "Streaming Video",
            status="downloading",
            message="Streaming video download started",
            created_at=datetime.now(),
        )

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
            query = db.query(Video)
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
            videos = [VideoResponse(**_video_to_response_dict(v)) for v in rows]

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
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")

            return VideoResponse(**_video_to_response_dict(video))

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
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")

            if delete_files and video.file_path and os.path.exists(video.file_path):
                os.remove(video.file_path)

            db.delete(video)

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


@router.get("/{video_id}/status", response_model=VideoStatusResponse)
async def get_video_status(video_id: str):
    """
    Get video processing status

    - **video_id**: Video identifier

    Returns current processing status and progress
    """
    try:
        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")

            return VideoStatusResponse(
                video_id=video_id,
                status=video.processing_status.value,
                progress=100.0 if video.processing_status == VideoStatus.COMPLETED else 0.0,
                stage=video.processing_status.value,
                error_message=video.error_message,
                started_at=video.created_at,
                completed_at=video.processed_at,
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


def _run_video_analysis(video_path: str, video_uuid: str) -> dict:
    """
    Real (synchronous, CPU/IO-bound) analysis pipeline: sparse frame
    sampling, scene detection, audio transcription, per-scene keyframe
    captioning, and visual/audio understanding (objects, faces, OCR,
    actions, audio energy). Run off the event loop via asyncio.to_thread.
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

    # Sparse raw frame sampling (for storage/browsing)
    frames_dir = Path(settings.frames_path) / video_uuid
    sampled_frames = processor.extract_frames(path, frames_dir, fps=0.2)

    # Real scene detection (histogram-based content detector)
    detector = ContentBasedSceneDetector(
        SceneDetectorConfig(
            threshold=settings.scene_threshold,
            min_scene_length=settings.min_scene_length,
        )
    )
    scenes = detector.detect_scenes(path)

    # Real audio transcription (local Whisper)
    audio_path = Path(settings.temp_path) / f"{video_uuid}.wav"
    processor.extract_audio(path, audio_path)
    transcriber = TranscriptionService(prefer_local=True, model_name=settings.whisper_model)
    transcription = transcriber.transcribe(audio_path, use_local=True)

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

    # Real per-scene keyframe extraction, captioning (local BLIP), and
    # visual understanding (objects/faces/OCR) + audio energy
    captioner = ImageCaptioningService(use_local=True)
    object_detector = ObjectDetectionService()
    face_detector = FaceDetectionService(backend="opencv")
    ocr = OCRService(engine="easyocr")
    audio_extractor = AudioFeatureExtractor()

    keyframes_dir = frames_dir / "keyframes"
    keyframes_dir.mkdir(parents=True, exist_ok=True)
    scene_results = []
    for scene in scenes:
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
        })

    return {
        "sampled_frame_paths": [str(f) for f in sampled_frames],
        "scenes": scene_results,
        "transcription": transcription,
    }


_embedding_model = None


def _get_embedding_model():
    """Lazily load a shared sentence-transformers model for text embeddings"""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embedding_model


async def process_video_background(video_id: str):
    """Process video in background: real analysis, DB persistence, and progress updates"""
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

    try:
        logger.info(f"Starting background processing for video {video_id}")

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise RuntimeError(f"Video {video_id} not found in database")
            video.processing_status = VideoStatus.PROCESSING
            file_path = video.file_path

            # Clear any prior analysis before regenerating, so calling this
            # more than once (e.g. /process on an already-completed video,
            # not just /reprocess) doesn't duplicate scenes/frames/
            # transcripts - confirmed live: without this, a second run
            # doubled every count (4->8 scenes, 149->298 transcripts).
            db.query(ChapterModel).filter(ChapterModel.video_id == video.id).delete()
            db.query(HighlightModel).filter(HighlightModel.video_id == video.id).delete()
            db.query(SummaryModel).filter(SummaryModel.video_id == video.id).delete()
            db.query(TranscriptModel).filter(TranscriptModel.video_id == video.id).delete()
            db.query(FrameModel).filter(FrameModel.video_id == video.id).delete()
            db.query(SceneModel).filter(SceneModel.video_id == video.id).delete()

        vector_store_for_cleanup = VideoVectorStore(persist_directory=Path(settings.chroma_persist_directory))
        vector_store_for_cleanup.initialize_collections()
        vector_store_for_cleanup.delete_video_embeddings(video_id)

        # Stage 1-2: Frame sampling + scene detection + transcription + captioning
        # (runs off the event loop; it's CPU/subprocess-bound)
        await send_progress_update(
            video_id=video_id,
            stage="frame_extraction",
            progress=10.0,
            message="Extracting frames and detecting scenes...",
        )

        analysis = await asyncio.to_thread(_run_video_analysis, file_path, video_id)
        transcription = analysis["transcription"]

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

            for item, scene_row in zip(analysis["scenes"], scene_rows):
                s = item["scene"]
                db.add(FrameModel(
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
                ))

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

            video.processing_status = VideoStatus.COMPLETED
            video.processed_at = datetime.now()

        await send_stage_complete(
            video_id=video_id,
            stage="embeddings",
            message="Embedding generation complete",
            results={"embeddings_created": transcript_count + caption_count},
        )

        # Stage 4: Summary + highlight generation (local Ollama LLM + heuristic scoring)
        await send_progress_update(
            video_id=video_id,
            stage="summarization",
            progress=95.0,
            message="Generating video summary, highlights, and chapters...",
        )

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
                "embeddings": transcript_count + caption_count,
            },
        )

        logger.info(f"Background processing complete for video {video_id}")

    except Exception as e:
        logger.error(f"Background processing failed: {e}", exc_info=True)
        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if video:
                video.processing_status = VideoStatus.FAILED
                video.error_message = str(e)
        await send_processing_error(
            video_id=video_id,
            stage="unknown",
            error_message=str(e),
        )


async def download_youtube_video(
    video_id: str,
    url: str,
    title: Optional[str],
    quality: str,
    auto_process: bool,
):
    """Download YouTube video with progress updates"""
    try:
        from src.api.websockets import send_progress_update, send_processing_error
        import yt_dlp

        logger.info(f"Downloading YouTube video: {url}")

        # Send initial download progress (0-30%)
        await send_progress_update(
            video_id=video_id,
            stage="download",
            progress=5.0,
            message="Starting YouTube video download...",
        )

        # Configure output directory
        output_dir = "./data/uploads"
        os.makedirs(output_dir, exist_ok=True)

        # Configure yt-dlp options
        ydl_opts = {
            'format': f'bestvideo[height<={quality.replace("p", "")}]+bestaudio/best' if quality != 'best' else 'best',
            'outtmpl': f'{output_dir}/{video_id}.%(ext)s',
            'merge_output_format': 'mp4',
            'quiet': False,
            'no_warnings': False,
        }

        # Download video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Inform user download is in progress
            await send_progress_update(
                video_id=video_id,
                stage="download",
                progress=15.0,
                message="Fetching video information...",
            )

            info = ydl.extract_info(url, download=True)

            # Get downloaded file info
            video_title = title or info.get('title', 'YouTube Video')
            duration = info.get('duration', 0)

            # Find the downloaded file
            file_path = f"{output_dir}/{video_id}.mp4"

            logger.info(f"Downloaded: {video_title} ({duration}s) -> {file_path}")

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if video:
                video.title = video_title
                video.file_path = file_path
                video.duration_seconds = duration
                video.processing_status = (
                    VideoStatus.PROCESSING if auto_process else VideoStatus.PENDING
                )

        # Download complete
        await send_progress_update(
            video_id=video_id,
            stage="download",
            progress=30.0,
            message=f"Download complete: {video_title}",
        )

        # If auto_process, start processing
        if auto_process:
            await process_video_background(video_id)

    except Exception as e:
        logger.error(f"YouTube download failed: {e}")
        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if video:
                video.processing_status = VideoStatus.FAILED
                video.error_message = str(e)
        await send_processing_error(
            video_id=video_id,
            stage="download",
            error_message=f"Download failed: {str(e)}",
        )


async def download_streaming_video(
    video_id: str,
    url: str,
    title: Optional[str],
    auto_process: bool,
):
    """Download streaming video (HTTP/HLS) with ffmpeg"""
    import subprocess
    from src.api.websockets import send_progress_update, send_processing_error

    # Safety cap: a truly live (infinite) stream would otherwise hang the
    # pipeline forever. VOD streams finish well before this.
    MAX_STREAM_DURATION_SECONDS = 3600

    try:
        logger.info(f"Downloading streaming video: {url}")

        await send_progress_update(
            video_id=video_id,
            stage="download",
            progress=5.0,
            message="Starting stream download...",
        )

        output_dir = "./data/uploads"
        os.makedirs(output_dir, exist_ok=True)
        file_path = f"{output_dir}/{video_id}.mp4"

        cmd = [
            "ffmpeg",
            "-i", url,
            "-t", str(MAX_STREAM_DURATION_SECONDS),
            "-c", "copy",
            "-y",
            "-hide_banner",
            "-loglevel", "error",
            file_path,
        ]
        import asyncio
        result = await asyncio.to_thread(
            subprocess.run, cmd, capture_output=True, text=True, timeout=MAX_STREAM_DURATION_SECONDS + 60
        )
        if result.returncode != 0 or not os.path.exists(file_path):
            raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")

        duration = await get_video_duration(file_path)
        video_title = title or "Streaming Video"

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if video:
                video.title = video_title
                video.file_path = file_path
                video.duration_seconds = duration
                video.processing_status = (
                    VideoStatus.PROCESSING if auto_process else VideoStatus.PENDING
                )

        logger.info(f"Downloaded stream: {video_title} ({duration:.1f}s) -> {file_path}")

        await send_progress_update(
            video_id=video_id,
            stage="download",
            progress=30.0,
            message=f"Download complete: {video_title}",
        )

        if auto_process:
            await process_video_background(video_id)

    except Exception as e:
        logger.error(f"Streaming download failed: {e}")
        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if video:
                video.processing_status = VideoStatus.FAILED
                video.error_message = str(e)
        await send_processing_error(
            video_id=video_id,
            stage="download",
            error_message=f"Stream download failed: {str(e)}",
        )
