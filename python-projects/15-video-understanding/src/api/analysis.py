"""
Video analysis API endpoints
Generate summaries, highlights, and timelines
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from datetime import datetime

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/videos", tags=["analysis"])


# ============================================================================
# Request/Response Models
# ============================================================================


class SummaryResponse(BaseModel):
    """Video summary response"""
    video_id: str
    summary_type: str
    content: str
    timestamp_ranges: Optional[List[dict]] = None
    key_points: Optional[List[str]] = None
    duration_covered: Optional[float] = None
    generated_at: datetime


class GenerateSummaryRequest(BaseModel):
    """Request to generate custom summary"""
    summary_type: str = Field("overall", description="Type: overall, scene, highlight, chapter")
    length: str = Field("medium", description="Length: brief, medium, detailed")
    include_timestamps: bool = Field(True, description="Include timestamps in summary")
    focus_areas: Optional[List[str]] = Field(None, description="Areas to focus on")


class ChapterResponse(BaseModel):
    """Video chapter"""
    chapter_id: str
    chapter_number: int
    title: str
    description: str
    start_time: float
    end_time: float
    duration: float
    keyframe_path: Optional[str] = None


class ChaptersResponse(BaseModel):
    """List of video chapters"""
    video_id: str
    chapters: List[ChapterResponse]
    total_chapters: int
    total_duration: float


class HighlightResponse(BaseModel):
    """Video highlight"""
    highlight_id: str
    title: str
    description: str
    start_time: float
    end_time: float
    duration: float
    importance_score: float
    highlight_type: str
    clip_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
    tags: Optional[List[str]] = None


class HighlightsResponse(BaseModel):
    """List of video highlights"""
    video_id: str
    highlights: List[HighlightResponse]
    total_highlights: int
    average_importance: float


class GenerateHighlightsRequest(BaseModel):
    """Request to generate highlights"""
    max_highlights: int = Field(5, ge=1, le=20, description="Maximum number of highlights")
    min_importance: float = Field(0.7, ge=0.0, le=1.0, description="Minimum importance score")
    highlight_types: Optional[List[str]] = Field(None, description="Filter by types")
    min_duration: float = Field(3.0, description="Minimum highlight duration (seconds)")
    max_duration: float = Field(30.0, description="Maximum highlight duration (seconds)")


class TimelineEvent(BaseModel):
    """Timeline event"""
    event_id: str
    timestamp: float
    event_type: str
    title: str
    description: Optional[str] = None
    metadata: dict = {}


class TimelineResponse(BaseModel):
    """Annotated video timeline"""
    video_id: str
    events: List[TimelineEvent]
    total_events: int
    duration: float
    event_types: List[str]


class TimelineFilterRequest(BaseModel):
    """Filter timeline events"""
    event_types: Optional[List[str]] = Field(None, description="Filter by event types")
    start_time: Optional[float] = Field(None, description="Filter events after this time")
    end_time: Optional[float] = Field(None, description="Filter events before this time")


# ============================================================================
# Summary Endpoints
# ============================================================================


@router.get("/{video_id}/summary", response_model=SummaryResponse)
async def get_video_summary(
    video_id: str,
    summary_type: str = Query("overall", description="Summary type"),
):
    """
    Get video summary

    - **video_id**: Video identifier
    - **summary_type**: Type of summary (overall, scene, highlight, chapter)

    Returns generated summary with key points and timestamps
    """
    try:
        logger.info(f"Getting {summary_type} summary for video {video_id}")

        from src.core.database import get_db
        from src.models import Video, Summary, SummaryType

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")

            summary = (
                db.query(Summary)
                .filter(
                    Summary.video_id == video.id,
                    Summary.summary_type == SummaryType(summary_type),
                )
                .order_by(Summary.created_at.desc())
                .first()
            )
            if not summary:
                raise HTTPException(status_code=404, detail="Summary not found")

            meta = summary.extra_metadata or {}
            return SummaryResponse(
                video_id=video_id,
                summary_type=summary.summary_type.value,
                content=summary.content,
                timestamp_ranges=summary.timestamp_ranges or [],
                key_points=meta.get("key_points", []),
                duration_covered=meta.get("duration_covered", 0.0),
                generated_at=summary.created_at,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get summary: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get summary: {str(e)}"
        )


@router.post("/{video_id}/summarize", response_model=SummaryResponse)
async def generate_video_summary(
    video_id: str,
    background_tasks: BackgroundTasks,
    request: GenerateSummaryRequest,
):
    """
    Generate custom video summary

    - **video_id**: Video identifier
    - **summary_type**: Type of summary to generate
    - **length**: Summary length (brief, medium, detailed)
    - **include_timestamps**: Include timestamps in summary
    - **focus_areas**: Specific areas to focus on

    Generates summary in background and returns immediately
    """
    try:
        logger.info(f"Generating {request.summary_type} summary for video {video_id}")

        # TODO: Verify video exists and is processed
        # video = db.query(Video).filter(Video.id == video_id).first()
        # if not video:
        #     raise HTTPException(status_code=404, detail="Video not found")
        #
        # if video.processing_status != "completed":
        #     raise HTTPException(status_code=400, detail="Video not fully processed")

        # Schedule summary generation
        background_tasks.add_task(
            generate_summary_task,
            video_id,
            request,
        )

        return SummaryResponse(
            video_id=video_id,
            summary_type=request.summary_type,
            content="Summary generation started...",
            generated_at=datetime.now(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate summary: {str(e)}"
        )


@router.get("/{video_id}/chapters", response_model=ChaptersResponse)
async def get_video_chapters(video_id: str):
    """
    Get video chapters

    - **video_id**: Video identifier

    Returns automatically detected chapters with titles and descriptions
    """
    try:
        logger.info(f"Getting chapters for video {video_id}")

        from src.core.database import get_db
        from src.models import Video, Chapter as ChapterModel

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")

            rows = (
                db.query(ChapterModel)
                .filter(ChapterModel.video_id == video.id)
                .order_by(ChapterModel.chapter_number)
                .all()
            )

            chapters = [
                ChapterResponse(
                    chapter_id=str(c.id),
                    chapter_number=c.chapter_number,
                    title=c.title,
                    description=c.description or "",
                    start_time=c.start_time,
                    end_time=c.end_time,
                    duration=c.end_time - c.start_time,
                    keyframe_path=c.keyframe_path,
                )
                for c in rows
            ]
            total_duration = sum(c.duration for c in chapters)

        return ChaptersResponse(
            video_id=video_id,
            chapters=chapters,
            total_chapters=len(chapters),
            total_duration=total_duration,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chapters: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get chapters: {str(e)}"
        )


# ============================================================================
# Highlight Endpoints
# ============================================================================


@router.get("/{video_id}/highlights", response_model=HighlightsResponse)
async def get_video_highlights(
    video_id: str,
    min_importance: float = Query(0.7, ge=0.0, le=1.0),
    highlight_type: Optional[str] = Query(None),
):
    """
    Get video highlights

    - **video_id**: Video identifier
    - **min_importance**: Minimum importance score filter
    - **highlight_type**: Filter by highlight type

    Returns detected highlights with importance scores
    """
    try:
        logger.info(f"Getting highlights for video {video_id}")

        from src.core.database import get_db
        from src.models import Video, Highlight as HighlightModel, HighlightType as HighlightTypeDB

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")

            query = db.query(HighlightModel).filter(
                HighlightModel.video_id == video.id,
                HighlightModel.importance_score >= min_importance,
            )
            if highlight_type:
                query = query.filter(HighlightModel.highlight_type == HighlightTypeDB(highlight_type))
            rows = query.order_by(HighlightModel.importance_score.desc()).all()

            highlights = [
                HighlightResponse(
                    highlight_id=str(h.id),
                    title=h.title,
                    description=h.description or "",
                    start_time=h.start_time,
                    end_time=h.end_time,
                    duration=h.end_time - h.start_time,
                    importance_score=h.importance_score,
                    highlight_type=h.highlight_type.value,
                    clip_path=h.clip_path,
                    thumbnail_path=h.thumbnail_path,
                    tags=(h.extra_metadata or {}).get("tags", []),
                )
                for h in rows
            ]
            avg_importance = (
                sum(h.importance_score for h in highlights) / len(highlights)
                if highlights else 0.0
            )

        return HighlightsResponse(
            video_id=video_id,
            highlights=highlights,
            total_highlights=len(highlights),
            average_importance=avg_importance,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get highlights: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get highlights: {str(e)}"
        )


@router.get("/{video_id}/highlights/{highlight_id}/thumbnail")
async def get_highlight_thumbnail(video_id: str, highlight_id: str):
    """Get the keyframe image for a highlight, so a viewer can see what the
    moment actually looks like instead of just an importance score."""
    import os as os_module
    from fastapi.responses import FileResponse
    from src.core.database import get_db
    from src.models import Highlight as HighlightModel

    try:
        with get_db() as db:
            highlight = db.query(HighlightModel).filter(HighlightModel.id == int(highlight_id)).first()
            if not highlight or not highlight.thumbnail_path or not os_module.path.exists(highlight.thumbnail_path):
                raise HTTPException(status_code=404, detail="Thumbnail not found")

            return FileResponse(path=highlight.thumbnail_path, media_type="image/jpeg")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get highlight thumbnail: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get highlight thumbnail: {str(e)}")


@router.post("/{video_id}/highlights/generate", response_model=HighlightsResponse)
async def generate_video_highlights(
    video_id: str,
    background_tasks: BackgroundTasks,
    request: GenerateHighlightsRequest,
):
    """
    Generate video highlights

    - **video_id**: Video identifier
    - **max_highlights**: Maximum number of highlights to generate
    - **min_importance**: Minimum importance threshold
    - **highlight_types**: Filter by specific highlight types
    - **min_duration**: Minimum highlight duration
    - **max_duration**: Maximum highlight duration

    Detects and generates highlight moments
    """
    try:
        logger.info(f"Generating highlights for video {video_id}")

        # TODO: Verify video exists and is processed

        # Schedule highlight generation
        background_tasks.add_task(
            generate_highlights_task,
            video_id,
            request,
        )

        return HighlightsResponse(
            video_id=video_id,
            highlights=[],
            total_highlights=0,
            average_importance=0.0,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate highlights: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate highlights: {str(e)}"
        )


# ============================================================================
# Timeline Endpoints
# ============================================================================


def _build_timeline_events(db, video) -> List[TimelineEvent]:
    """Aggregate scenes, transcript, highlights, and chapters into a
    single chronological timeline for a video. Must be called with an
    open db session (attributes are read while it's still active)."""
    from src.models import Scene, Transcript, Highlight, Chapter

    events: List[TimelineEvent] = []

    scenes = db.query(Scene).filter(Scene.video_id == video.id).order_by(Scene.start_time).all()
    for s in scenes:
        events.append(TimelineEvent(
            event_id=f"scene_{s.id}",
            timestamp=s.start_time,
            event_type="scene",
            title=f"Scene {s.scene_number}",
            description=s.description,
            metadata={"end_time": s.end_time, "scene_number": s.scene_number},
        ))

    transcripts = db.query(Transcript).filter(Transcript.video_id == video.id).order_by(Transcript.start_time).all()
    for t in transcripts:
        events.append(TimelineEvent(
            event_id=f"transcript_{t.id}",
            timestamp=t.start_time,
            event_type="speech",
            title=t.speaker_id or "Speech",
            description=t.text,
            metadata={"end_time": t.end_time, "speaker_id": t.speaker_id},
        ))

    highlights = db.query(Highlight).filter(Highlight.video_id == video.id).order_by(Highlight.start_time).all()
    for h in highlights:
        events.append(TimelineEvent(
            event_id=f"highlight_{h.id}",
            timestamp=h.start_time,
            event_type="highlight",
            title=h.title,
            description=h.description,
            metadata={"end_time": h.end_time, "importance_score": h.importance_score},
        ))

    chapters = db.query(Chapter).filter(Chapter.video_id == video.id).order_by(Chapter.start_time).all()
    for c in chapters:
        events.append(TimelineEvent(
            event_id=f"chapter_{c.id}",
            timestamp=c.start_time,
            event_type="chapter",
            title=c.title,
            description=c.description,
            metadata={"end_time": c.end_time, "chapter_number": c.chapter_number},
        ))

    events.sort(key=lambda e: e.timestamp)
    return events


@router.get("/{video_id}/timeline", response_model=TimelineResponse)
async def get_video_timeline(video_id: str):
    """
    Get annotated video timeline

    - **video_id**: Video identifier

    Returns timeline with all detected events (scenes, speakers, objects, actions)
    """
    try:
        logger.info(f"Getting timeline for video {video_id}")

        from src.core.database import get_db
        from src.models import Video

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")

            events = _build_timeline_events(db, video)
            duration = video.duration_seconds or 0.0

        return TimelineResponse(
            video_id=video_id,
            events=events,
            total_events=len(events),
            duration=duration,
            event_types=sorted({e.event_type for e in events}),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get timeline: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get timeline: {str(e)}"
        )


@router.post("/{video_id}/timeline/filter", response_model=TimelineResponse)
async def filter_video_timeline(
    video_id: str,
    request: TimelineFilterRequest,
):
    """
    Filter video timeline events

    - **video_id**: Video identifier
    - **event_types**: Filter by event types
    - **start_time**: Filter events after this timestamp
    - **end_time**: Filter events before this timestamp

    Returns filtered timeline events
    """
    try:
        logger.info(f"Filtering timeline for video {video_id}")

        from src.core.database import get_db
        from src.models import Video

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="Video not found")

            events = _build_timeline_events(db, video)
            duration = video.duration_seconds or 0.0

        if request.event_types:
            events = [e for e in events if e.event_type in request.event_types]
        if request.start_time is not None:
            events = [e for e in events if e.timestamp >= request.start_time]
        if request.end_time is not None:
            events = [e for e in events if e.timestamp <= request.end_time]

        return TimelineResponse(
            video_id=video_id,
            events=events,
            total_events=len(events),
            duration=duration,
            event_types=sorted({e.event_type for e in events}),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to filter timeline: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to filter timeline: {str(e)}"
        )


# ============================================================================
# Background Task Functions
# ============================================================================


def _run_summary_generation(video_id: str, duration: float, transcript_text: str, scenes: list, length: str) -> dict:
    """Synchronous LLM call (local Ollama) run off the event loop"""
    from src.core.llm_client import LLMClient
    from src.services.summarization.video_summarizer import VideoSummarizer, SummaryLength

    llm_client = LLMClient(backend="ollama", model="llama3.2")
    summarizer = VideoSummarizer(llm_client=llm_client, default_length=SummaryLength(length))
    result = summarizer.summarize_video(
        video_id=video_id,
        duration=duration,
        transcript=transcript_text,
        scenes=scenes,
    )
    return {
        "summary_text": result.summary_text,
        "key_points": result.key_points,
        "main_topics": result.main_topics,
        "word_count": result.word_count,
    }


async def generate_summary_task(
    video_id: str,
    config: GenerateSummaryRequest,
):
    """Generate summary in background using VideoSummarizer (local Ollama LLM)"""
    import asyncio
    from src.core.database import get_db
    from src.models import Video, Scene, Transcript, Summary, SummaryType

    try:
        logger.info(f"Starting summary generation for video {video_id}")

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                logger.error(f"Video {video_id} not found for summary generation")
                return

            scene_rows = db.query(Scene).filter(Scene.video_id == video.id).order_by(Scene.start_time).all()
            transcript_rows = (
                db.query(Transcript).filter(Transcript.video_id == video.id).order_by(Transcript.start_time).all()
            )
            duration = video.duration_seconds or 0.0
            scenes = [
                {
                    "scene_number": s.scene_number,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "description": s.description,
                }
                for s in scene_rows
            ]
            transcript_text = " ".join(t.text for t in transcript_rows)

        result = await asyncio.to_thread(
            _run_summary_generation, video_id, duration, transcript_text, scenes, config.length
        )

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            # Replace any prior summary of the same type rather than accumulate
            db.query(Summary).filter(
                Summary.video_id == video.id,
                Summary.summary_type == SummaryType(config.summary_type),
            ).delete()
            db.add(Summary(
                video_id=video.id,
                summary_type=SummaryType(config.summary_type),
                content=result["summary_text"],
                timestamp_ranges=[],
                extra_metadata={
                    "key_points": result["key_points"],
                    "main_topics": result["main_topics"],
                    "duration_covered": duration,
                },
            ))

        logger.info(f"Summary generation complete for video {video_id}")

    except Exception as e:
        logger.error(f"Summary generation failed: {e}", exc_info=True)


def _describe_highlight_reason(
    visual_context: Optional[dict],
    audio_context: Optional[dict],
    transcript_segments: list,
) -> str:
    """Turn the same raw signals ImportanceScorer weighs (objects, faces,
    motion, audio energy, speech) into a plain-language explanation of why a
    moment was picked - a data scientist can read an importance score, but a
    regular viewer needs "why", not "0.82"."""
    objects = (visual_context or {}).get("objects", [])
    faces = (visual_context or {}).get("faces", [])
    action_count = len((visual_context or {}).get("actions", []))
    energy = ((audio_context or {}).get("features", {}) or {}).get("energy", 0.0)

    reasons = []
    if action_count >= 7:
        reasons.append("a lot of visual movement/action")
    elif action_count >= 4:
        reasons.append("noticeable movement")
    if len(faces) > 0:
        reasons.append(f"{len(faces)} face{'s' if len(faces) != 1 else ''} on screen")
    unique_objects = sorted(set(objects) - {"person"})
    if unique_objects:
        reasons.append(f"{', '.join(unique_objects)} visible")
    if energy >= 0.6:
        reasons.append("raised/emphatic speaking energy")

    quote = ""
    if transcript_segments:
        text = " ".join(s.get("text", "") for s in transcript_segments).strip()
        if text:
            quote = text if len(text) <= 140 else text[:137] + "..."

    if not reasons and not quote:
        return "Selected as a comparatively distinctive moment in this video."

    summary = "Picked for " + " and ".join(reasons) + "." if reasons else "Picked as a notable moment."
    if quote:
        summary += f' Spoken here: "{quote}"'
    return summary


def _run_highlight_detection(
    video_id: str,
    duration: float,
    scenes: list,
    transcripts_by_scene: dict,
    visual_contexts_by_scene: dict,
    audio_contexts_by_scene: dict,
    keyframe_by_scene: dict,
    config: GenerateHighlightsRequest,
) -> list:
    """Synchronous scoring/detection run off the event loop"""
    from src.services.highlights.importance_scorer import ImportanceScorer
    from src.services.highlights.highlight_detector import HighlightDetector

    scorer = ImportanceScorer()
    scores = [
        scorer.score_scene(
            scene_data=s,
            transcript_segments=transcripts_by_scene.get(s["scene_number"], []),
            visual_context=visual_contexts_by_scene.get(s["scene_number"]),
            audio_context=audio_contexts_by_scene.get(s["scene_number"]),
        )
        for s in scenes
    ]
    # The raw heuristic score (see ImportanceScorer._calculate_heuristic_score)
    # realistically tops out well under the 0.7 min_importance default for
    # genuinely eventful scenes - confirmed live, every processed video got 0
    # highlights regardless of scene count or content. score_scenes_batch()
    # normalizes scores to each video's own 0-1 range before ranking, but this
    # per-scene scoring path (needed to wire in visual/audio/transcript
    # context per scene) bypassed that step entirely. Apply the same
    # normalization here so the threshold is relative to the video, not an
    # absolute bar the formula can't reach.
    scores = scorer._normalize_scene_scores(scores)

    detector = HighlightDetector(
        importance_scorer=scorer,
        min_importance=config.min_importance,
        min_highlight_duration=config.min_duration,
        max_highlight_duration=config.max_duration,
    )
    collection = detector.detect_highlights(
        video_id=video_id,
        duration=duration,
        scenes=scenes,
        scene_scores=scores,
        max_highlights=config.max_highlights,
    )

    # HighlightDetector's own description is a generic template ("Action
    # highlight from X to Y (importance: Z)") with no thumbnail - real but
    # meaningless to a non-technical viewer. Replace it with plain-language
    # reasoning and a real keyframe image using the same per-scene signals
    # already scored above.
    for h in collection.highlights:
        scene_number = h.scene_ids[0] if h.scene_ids else None
        h.thumbnail_path = keyframe_by_scene.get(scene_number)
        h.description = _describe_highlight_reason(
            visual_contexts_by_scene.get(scene_number),
            audio_contexts_by_scene.get(scene_number),
            transcripts_by_scene.get(scene_number, []),
        )

    return collection.highlights


async def generate_highlights_task(
    video_id: str,
    config: GenerateHighlightsRequest,
):
    """Generate highlights in background using ImportanceScorer + HighlightDetector"""
    import asyncio
    from src.core.database import get_db
    from src.models import (
        Video, Scene, Transcript, Frame,
        Highlight as HighlightModel, HighlightType as HighlightTypeDB,
    )

    try:
        logger.info(f"Starting highlight generation for video {video_id}")

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                logger.error(f"Video {video_id} not found for highlight generation")
                return

            scene_rows = db.query(Scene).filter(Scene.video_id == video.id).order_by(Scene.start_time).all()
            transcript_rows = db.query(Transcript).filter(Transcript.video_id == video.id).all()
            keyframes = {
                f.scene_id: f
                for f in db.query(Frame).filter(Frame.video_id == video.id, Frame.is_keyframe == True).all()
            }
            duration = video.duration_seconds or 0.0

            scenes = [
                {
                    "scene_number": s.scene_number,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "transition_type": s.transition_type.value if s.transition_type else None,
                }
                for s in scene_rows
            ]
            transcripts_by_scene = {}
            for s in scene_rows:
                transcripts_by_scene[s.scene_number] = [
                    {"text": t.text, "start": t.start_time, "end": t.end_time, "speaker": t.speaker_id}
                    for t in transcript_rows
                    if t.start_time >= s.start_time and t.start_time < s.end_time
                ]

            # Real visual/audio context from the visual-understanding pass
            # (object/face/OCR detection on the keyframe, motion-based action
            # ratio and audio energy stored on the scene) - see AKHIL-409.
            visual_contexts_by_scene = {}
            audio_contexts_by_scene = {}
            keyframe_by_scene = {}
            for s in scene_rows:
                meta = s.extra_metadata or {}
                keyframe = keyframes.get(s.id)
                activity_ratio = meta.get("activity_ratio", 0.0)
                visual_contexts_by_scene[s.scene_number] = {
                    "objects": (keyframe.objects_detected if keyframe else None) or [],
                    "faces": (keyframe.faces_detected if keyframe else None) or [],
                    # Synthesize a count proportional to motion activity so it
                    # contributes real, differentiated signal through the
                    # existing len(actions)-based scoring path.
                    "actions": ["motion"] * round(activity_ratio * 10),
                }
                audio_contexts_by_scene[s.scene_number] = {
                    "features": {"energy": meta.get("audio_energy", 0.0)}
                }
                keyframe_by_scene[s.scene_number] = (keyframe.file_path if keyframe else None) or s.keyframe_path

        if not scenes:
            logger.info(f"No scenes available for video {video_id}, skipping highlight generation")
            return

        highlights = await asyncio.to_thread(
            _run_highlight_detection, video_id, duration, scenes, transcripts_by_scene,
            visual_contexts_by_scene, audio_contexts_by_scene, keyframe_by_scene, config
        )

        known_types = {t.value for t in HighlightTypeDB}
        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            # Replace prior highlights rather than accumulate across calls
            db.query(HighlightModel).filter(HighlightModel.video_id == video.id).delete()
            for h in highlights:
                type_value = h.highlight_type.value if h.highlight_type.value in known_types else "unknown"
                db.add(HighlightModel(
                    video_id=video.id,
                    title=h.title or f"Highlight at {h.start_time:.0f}s",
                    description=h.description,
                    start_time=h.start_time,
                    end_time=h.end_time,
                    importance_score=h.importance_score,
                    highlight_type=HighlightTypeDB(type_value),
                    thumbnail_path=h.thumbnail_path,
                    extra_metadata=h.metadata or {},
                ))

        logger.info(f"Highlight generation complete for video {video_id}: {len(highlights)} highlights")

    except Exception as e:
        logger.error(f"Highlight generation failed: {e}", exc_info=True)


def _run_chapter_generation(video_id: str, duration: float, scenes: list) -> list:
    """Synchronous chapter detection run off the event loop"""
    from src.services.summarization.chapter_generator import ChapterGenerator

    generator = ChapterGenerator()
    collection = generator.generate_chapters(
        video_id=video_id,
        duration=duration,
        scenes=scenes,
        method="auto",
    )
    return collection.chapters


async def generate_chapters_task(video_id: str):
    """Generate chapters in background using ChapterGenerator, scored by
    the same real visual/audio/speaker importance signal as highlights"""
    import asyncio
    from src.core.database import get_db
    from src.models import Video, Scene, Transcript, Frame, Chapter as ChapterModel
    from src.services.highlights.importance_scorer import ImportanceScorer

    try:
        logger.info(f"Starting chapter generation for video {video_id}")

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                logger.error(f"Video {video_id} not found for chapter generation")
                return

            scene_rows = db.query(Scene).filter(Scene.video_id == video.id).order_by(Scene.start_time).all()
            transcript_rows = db.query(Transcript).filter(Transcript.video_id == video.id).all()
            keyframes = {
                f.scene_id: f
                for f in db.query(Frame).filter(Frame.video_id == video.id, Frame.is_keyframe == True).all()
            }
            duration = video.duration_seconds or 0.0

            if not scene_rows:
                logger.info(f"No scenes available for video {video_id}, skipping chapter generation")
                return

            scorer = ImportanceScorer()
            scenes = []
            for s in scene_rows:
                meta = s.extra_metadata or {}
                keyframe = keyframes.get(s.id)
                segs = [
                    {"text": t.text}
                    for t in transcript_rows
                    if s.start_time <= t.start_time < s.end_time
                ]
                visual_context = {
                    "objects": (keyframe.objects_detected if keyframe else None) or [],
                    "faces": (keyframe.faces_detected if keyframe else None) or [],
                    "actions": ["motion"] * round(meta.get("activity_ratio", 0.0) * 10),
                }
                audio_context = {"features": {"energy": meta.get("audio_energy", 0.0)}}
                score = scorer.score_scene(
                    scene_data={"scene_number": s.scene_number, "start_time": s.start_time, "end_time": s.end_time},
                    transcript_segments=segs,
                    visual_context=visual_context,
                    audio_context=audio_context,
                ).importance_score
                scenes.append({
                    "scene_number": s.scene_number,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "importance_score": score,
                    "description": s.description,
                    "keyframe_path": s.keyframe_path,
                })

        chapters = await asyncio.to_thread(_run_chapter_generation, video_id, duration, scenes)

        keyframe_by_scene_number = {s["scene_number"]: s["keyframe_path"] for s in scenes}
        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            # Replace prior chapters rather than accumulate across calls
            db.query(ChapterModel).filter(ChapterModel.video_id == video.id).delete()
            for c in chapters:
                first_scene_id = c.scene_ids[0] if c.scene_ids else None
                db.add(ChapterModel(
                    video_id=video.id,
                    chapter_number=c.chapter_number,
                    title=c.title,
                    description=c.description,
                    start_time=c.start_time,
                    end_time=c.end_time,
                    keyframe_path=keyframe_by_scene_number.get(first_scene_id),
                    importance_score=c.importance_score,
                    extra_metadata=c.metadata or {},
                ))

        logger.info(f"Chapter generation complete for video {video_id}: {len(chapters)} chapters")

    except Exception as e:
        logger.error(f"Chapter generation failed: {e}", exc_info=True)
