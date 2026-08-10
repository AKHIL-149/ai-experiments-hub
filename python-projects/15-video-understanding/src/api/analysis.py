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

        # TODO: Query database for chapters
        # Chapters are generated during summary phase

        # Mock response
        chapters = []
        total_duration = 0.0

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


@router.get("/{video_id}/timeline", response_model=TimelineResponse)
async def get_video_timeline(video_id: str):
    """
    Get annotated video timeline

    - **video_id**: Video identifier

    Returns timeline with all detected events (scenes, speakers, objects, actions)
    """
    try:
        logger.info(f"Getting timeline for video {video_id}")

        # TODO: Build timeline from multiple sources
        # - Scene boundaries
        # - Speaker changes
        # - Object detections
        # - Action events
        # - OCR text appearances
        # - Highlight moments

        # Mock response
        events = []

        return TimelineResponse(
            video_id=video_id,
            events=events,
            total_events=len(events),
            duration=0.0,
            event_types=[],
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

        # TODO: Query and filter timeline events
        # Apply filters for event type and time range

        # Mock response
        events = []

        return TimelineResponse(
            video_id=video_id,
            events=events,
            total_events=len(events),
            duration=0.0,
            event_types=[],
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


def _run_highlight_detection(video_id: str, duration: float, scenes: list, transcripts_by_scene: dict, config: GenerateHighlightsRequest) -> list:
    """Synchronous scoring/detection run off the event loop"""
    from src.services.highlights.importance_scorer import ImportanceScorer
    from src.services.highlights.highlight_detector import HighlightDetector

    scorer = ImportanceScorer()
    scores = [
        scorer.score_scene(scene_data=s, transcript_segments=transcripts_by_scene.get(s["scene_number"], []))
        for s in scenes
    ]

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
    return collection.highlights


async def generate_highlights_task(
    video_id: str,
    config: GenerateHighlightsRequest,
):
    """Generate highlights in background using ImportanceScorer + HighlightDetector"""
    import asyncio
    from src.core.database import get_db
    from src.models import Video, Scene, Transcript, Highlight as HighlightModel, HighlightType as HighlightTypeDB

    try:
        logger.info(f"Starting highlight generation for video {video_id}")

        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
            if not video:
                logger.error(f"Video {video_id} not found for highlight generation")
                return

            scene_rows = db.query(Scene).filter(Scene.video_id == video.id).order_by(Scene.start_time).all()
            transcript_rows = db.query(Transcript).filter(Transcript.video_id == video.id).all()
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
                    {"text": t.text, "start": t.start_time, "end": t.end_time}
                    for t in transcript_rows
                    if t.start_time >= s.start_time and t.start_time < s.end_time
                ]

        if not scenes:
            logger.info(f"No scenes available for video {video_id}, skipping highlight generation")
            return

        highlights = await asyncio.to_thread(
            _run_highlight_detection, video_id, duration, scenes, transcripts_by_scene, config
        )

        known_types = {t.value for t in HighlightTypeDB}
        with get_db() as db:
            video = db.query(Video).filter(Video.external_id == video_id).first()
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
                    extra_metadata=h.metadata or {},
                ))

        logger.info(f"Highlight generation complete for video {video_id}: {len(highlights)} highlights")

    except Exception as e:
        logger.error(f"Highlight generation failed: {e}", exc_info=True)

        logger.info(f"Highlight generation complete for video {video_id}")

    except Exception as e:
        logger.error(f"Highlight generation failed: {e}")
