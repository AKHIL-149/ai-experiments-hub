"""
Search and query API endpoints
Semantic search across videos, frames, and transcripts
"""

import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import datetime

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/search", tags=["search"])


# ============================================================================
# Request/Response Models
# ============================================================================


class SemanticSearchRequest(BaseModel):
    """Semantic search request"""
    query: str = Field(..., min_length=1, description="Search query")
    top_k: int = Field(10, ge=1, le=100, description="Number of results to return")
    video_ids: Optional[List[str]] = Field(None, description="Filter by specific videos")
    search_type: str = Field("multi_modal", description="Search type: multi_modal, visual, text")
    min_similarity: float = Field(0.5, ge=0.0, le=1.0, description="Minimum similarity score")


class SearchResult(BaseModel):
    """Single search result"""
    result_id: str
    result_type: str  # frame, transcript, scene
    video_id: str
    video_title: str
    timestamp: float
    similarity_score: float
    content: str
    thumbnail_path: Optional[str] = None
    metadata: dict = {}


class SearchResponse(BaseModel):
    """Search results response"""
    query: str
    results: List[SearchResult]
    total_results: int
    search_time_ms: float


class FrameSearchRequest(BaseModel):
    """Frame search request"""
    query: str = Field(..., description="Visual search query")
    top_k: int = Field(10, ge=1, le=100)
    video_ids: Optional[List[str]] = None
    min_similarity: float = Field(0.6, ge=0.0, le=1.0)
    keyframes_only: bool = Field(False, description="Search only keyframes")


class FrameSearchResult(BaseModel):
    """Frame search result"""
    frame_id: str
    video_id: str
    video_title: str
    timestamp: float
    frame_number: int
    similarity_score: float
    frame_path: str
    description: Optional[str] = None
    scene_id: Optional[int] = None
    objects_detected: Optional[List[str]] = None


class FrameSearchResponse(BaseModel):
    """Frame search results"""
    query: str
    results: List[FrameSearchResult]
    total_results: int
    search_time_ms: float


class TranscriptSearchRequest(BaseModel):
    """Transcript search request"""
    query: str = Field(..., min_length=1)
    top_k: int = Field(10, ge=1, le=100)
    video_ids: Optional[List[str]] = None
    speaker_id: Optional[str] = Field(None, description="Filter by speaker")
    search_mode: str = Field("semantic", description="Mode: semantic, keyword, fuzzy")
    context_window: int = Field(30, ge=0, le=120, description="Context window in seconds")


class TranscriptSearchResult(BaseModel):
    """Transcript search result"""
    segment_id: str
    video_id: str
    video_title: str
    start_time: float
    end_time: float
    text: str
    speaker_id: Optional[str] = None
    speaker_name: Optional[str] = None
    similarity_score: float
    context_before: Optional[str] = None
    context_after: Optional[str] = None


class TranscriptSearchResponse(BaseModel):
    """Transcript search results"""
    query: str
    results: List[TranscriptSearchResult]
    total_results: int
    search_time_ms: float


class VideoQueryRequest(BaseModel):
    """Natural language query about video content"""
    question: str = Field(..., min_length=1, description="Question about the video")
    video_id: Optional[str] = Field(None, description="Specific video to query (optional)")
    max_context_items: int = Field(5, ge=1, le=20, description="Max context items to retrieve")
    include_sources: bool = Field(True, description="Include source references in answer")


class QuerySource(BaseModel):
    """Source reference for query answer"""
    source_type: str  # frame, transcript, scene
    video_id: str
    timestamp: float
    content: str
    relevance_score: float


class VideoQueryResponse(BaseModel):
    """Query answer response"""
    question: str
    answer: str
    confidence: float
    sources: List[QuerySource]
    video_ids: List[str]
    processing_time_ms: float


# ============================================================================
# Semantic Search Endpoints
# ============================================================================


@router.post("/semantic", response_model=SearchResponse)
async def semantic_search(request: SemanticSearchRequest):
    """
    Perform multi-modal semantic search across videos

    - **query**: Natural language search query
    - **top_k**: Number of results to return
    - **video_ids**: Optional filter by specific videos
    - **search_type**: Search mode (multi_modal, visual, text)
    - **min_similarity**: Minimum similarity threshold

    Searches across frames, transcripts, and scenes using CLIP and text embeddings
    """
    try:
        logger.info(f"Semantic search: '{request.query}' (top_k={request.top_k})")

        start_time = datetime.now()

        from pathlib import Path
        from src.core.config import settings
        from src.core.database import get_db
        from src.models import Video
        from src.core.vector_store import VideoVectorStore
        from src.api.videos import _get_embedding_model

        embed_model = _get_embedding_model()
        query_vector = embed_model.encode([request.query])[0]

        store = VideoVectorStore(persist_directory=Path(settings.chroma_persist_directory))
        store.initialize_collections()

        raw_hits = []  # (similarity, result_type, timestamp, content, video_id, metadata)

        transcript_hits = store.search_transcripts(query_vector, n_results=request.top_k)
        for i, doc_id in enumerate(transcript_hits.ids):
            meta = transcript_hits.metadatas[i]
            similarity = 1.0 - transcript_hits.distances[i]
            text = transcript_hits.documents[i] if transcript_hits.documents else ""
            raw_hits.append((
                similarity, "transcript", meta.get("start_time", 0.0), text,
                meta.get("video_id"), meta,
            ))

        scene_hits = store.search_scenes(query_vector, n_results=request.top_k)
        for i, doc_id in enumerate(scene_hits.ids):
            meta = scene_hits.metadatas[i]
            similarity = 1.0 - scene_hits.distances[i]
            text = scene_hits.documents[i] if scene_hits.documents else ""
            raw_hits.append((
                similarity, "scene", meta.get("start_time", 0.0), text,
                meta.get("video_id"), meta,
            ))

        if request.video_ids:
            raw_hits = [h for h in raw_hits if h[4] in request.video_ids]
        raw_hits = [h for h in raw_hits if h[0] >= request.min_similarity]
        raw_hits.sort(key=lambda h: h[0], reverse=True)
        raw_hits = raw_hits[:request.top_k]

        video_titles = {}
        with get_db() as db:
            ext_ids = {h[4] for h in raw_hits if h[4]}
            if ext_ids:
                rows = db.query(Video).filter(Video.external_id.in_(ext_ids)).all()
                video_titles = {v.external_id: v.title for v in rows}

        results = [
            SearchResult(
                result_id=f"{h[1]}_{i}",
                result_type=h[1],
                video_id=h[4] or "",
                video_title=video_titles.get(h[4], "Unknown"),
                timestamp=h[2],
                similarity_score=h[0],
                content=h[3],
                metadata=h[5],
            )
            for i, h in enumerate(raw_hits)
        ]

        end_time = datetime.now()
        search_time = (end_time - start_time).total_seconds() * 1000

        return SearchResponse(
            query=request.query,
            results=results,
            total_results=len(results),
            search_time_ms=search_time,
        )

    except Exception as e:
        logger.error(f"Semantic search failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Semantic search failed: {str(e)}"
        )


# ============================================================================
# Frame Search Endpoints
# ============================================================================


@router.post("/frames", response_model=FrameSearchResponse)
async def search_frames(request: FrameSearchRequest):
    """
    Search for specific visual content in frames

    - **query**: Visual search query (e.g., "person walking", "red car")
    - **top_k**: Number of frames to return
    - **video_ids**: Optional filter by videos
    - **min_similarity**: Minimum CLIP similarity threshold
    - **keyframes_only**: Search only keyframes

    Uses CLIP embeddings for visual similarity search
    """
    try:
        logger.info(f"Frame search: '{request.query}' (top_k={request.top_k})")

        start_time = datetime.now()

        # TODO: Implement frame search
        # 1. Generate CLIP text embedding for query
        # 2. Query frame vector store in ChromaDB
        # 3. Apply filters (video_ids, keyframes_only, min_similarity)
        # 4. Retrieve frame metadata from database
        # 5. Load descriptions and detected objects
        # 6. Return top_k frames with thumbnails

        # Mock response
        results = []

        end_time = datetime.now()
        search_time = (end_time - start_time).total_seconds() * 1000

        return FrameSearchResponse(
            query=request.query,
            results=results,
            total_results=len(results),
            search_time_ms=search_time,
        )

    except Exception as e:
        logger.error(f"Frame search failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Frame search failed: {str(e)}"
        )


# ============================================================================
# Transcript Search Endpoints
# ============================================================================


@router.post("/transcript", response_model=TranscriptSearchResponse)
async def search_transcript(request: TranscriptSearchRequest):
    """
    Search within video transcripts

    - **query**: Search query
    - **top_k**: Number of segments to return
    - **video_ids**: Optional filter by videos
    - **speaker_id**: Optional filter by speaker
    - **search_mode**: Search mode (semantic, keyword, fuzzy)
    - **context_window**: Include context before/after match (seconds)

    Supports semantic search using embeddings or keyword-based search
    """
    try:
        logger.info(f"Transcript search: '{request.query}' (mode={request.search_mode})")

        start_time = datetime.now()

        from pathlib import Path
        from src.core.config import settings
        from src.core.database import get_db
        from src.models import Video, Transcript
        from src.core.vector_store import VideoVectorStore

        with get_db() as db:
            if request.search_mode == "semantic":
                from src.api.videos import _get_embedding_model
                embed_model = _get_embedding_model()
                query_vector = embed_model.encode([request.query])[0]

                store = VideoVectorStore(persist_directory=Path(settings.chroma_persist_directory))
                store.initialize_collections()

                video_id_filter = request.video_ids[0] if request.video_ids and len(request.video_ids) == 1 else None
                hits = store.search_transcripts(
                    query_vector,
                    n_results=request.top_k,
                    video_id=video_id_filter,
                    speaker=request.speaker_id,
                )
                matches = [
                    {
                        "video_id": hits.metadatas[i].get("video_id"),
                        "segment_id": hits.metadatas[i].get("segment_id"),
                        "seg_start": hits.metadatas[i].get("start_time", 0.0),
                        "seg_end": hits.metadatas[i].get("end_time", 0.0),
                        "text": hits.documents[i] if hits.documents else "",
                        "similarity": 1.0 - hits.distances[i],
                        "speaker_id": hits.metadatas[i].get("speaker") or None,
                    }
                    for i in range(len(hits.ids))
                ]
                if request.video_ids and len(request.video_ids) > 1:
                    matches = [m for m in matches if m["video_id"] in request.video_ids]
            else:
                # keyword / fuzzy: case-insensitive substring match against Postgres
                query_db = db.query(Transcript).filter(Transcript.text.ilike(f"%{request.query}%"))
                if request.speaker_id:
                    query_db = query_db.filter(Transcript.speaker_id == request.speaker_id)
                if request.video_ids:
                    query_db = query_db.join(Video).filter(Video.external_id.in_(request.video_ids))
                rows = query_db.limit(request.top_k).all()
                matches = [
                    {
                        "video_id": t.video.external_id,
                        "segment_id": str(t.id),
                        "seg_start": t.start_time,
                        "seg_end": t.end_time,
                        "text": t.text,
                        "similarity": 1.0,
                        "speaker_id": t.speaker_id,
                    }
                    for t in rows
                ]

            matches = matches[:request.top_k]

            video_titles = {}
            ext_ids = {m["video_id"] for m in matches if m["video_id"]}
            if ext_ids:
                video_titles = {
                    v.external_id: v.title
                    for v in db.query(Video).filter(Video.external_id.in_(ext_ids)).all()
                }

            results = []
            for m in matches:
                context_before, context_after = None, None
                if request.context_window > 0 and m["video_id"]:
                    video = db.query(Video).filter(Video.external_id == m["video_id"]).first()
                    if video:
                        before = (
                            db.query(Transcript)
                            .filter(
                                Transcript.video_id == video.id,
                                Transcript.end_time <= m["seg_start"],
                                Transcript.end_time >= m["seg_start"] - request.context_window,
                            )
                            .order_by(Transcript.start_time)
                            .all()
                        )
                        after = (
                            db.query(Transcript)
                            .filter(
                                Transcript.video_id == video.id,
                                Transcript.start_time >= m["seg_end"],
                                Transcript.start_time <= m["seg_end"] + request.context_window,
                            )
                            .order_by(Transcript.start_time)
                            .all()
                        )
                        context_before = " ".join(t.text for t in before) or None
                        context_after = " ".join(t.text for t in after) or None

                results.append(TranscriptSearchResult(
                    segment_id=str(m["segment_id"]),
                    video_id=m["video_id"] or "",
                    video_title=video_titles.get(m["video_id"], "Unknown"),
                    start_time=m["seg_start"],
                    end_time=m["seg_end"],
                    text=m["text"],
                    speaker_id=m["speaker_id"],
                    similarity_score=m["similarity"],
                    context_before=context_before,
                    context_after=context_after,
                ))

        end_time = datetime.now()
        search_time = (end_time - start_time).total_seconds() * 1000

        return TranscriptSearchResponse(
            query=request.query,
            results=results,
            total_results=len(results),
            search_time_ms=search_time,
        )

    except Exception as e:
        logger.error(f"Transcript search failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Transcript search failed: {str(e)}"
        )


# ============================================================================
# Natural Language Query Endpoints
# ============================================================================


@router.post("/query", response_model=VideoQueryResponse)
async def query_videos(request: VideoQueryRequest):
    """
    Ask natural language questions about video content

    - **question**: Question to answer (e.g., "What are the main topics?")
    - **video_id**: Optional specific video to query
    - **max_context_items**: Maximum context items to retrieve
    - **include_sources**: Include source references in answer

    Uses RAG (Retrieval-Augmented Generation) to answer questions
    """
    try:
        logger.info(f"Video query: '{request.question}'")

        start_time = datetime.now()

        # TODO: Implement RAG-based query
        # 1. Parse and understand the question
        # 2. Retrieve relevant context:
        #    - Semantic search in transcripts
        #    - Frame search for visual questions
        #    - Scene summaries
        # 3. Combine context from multiple sources
        # 4. Use LLM to generate answer with context
        # 5. Extract source references
        # 6. Calculate confidence score

        # Mock response
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds() * 1000

        return VideoQueryResponse(
            question=request.question,
            answer="This is a placeholder answer.",
            confidence=0.0,
            sources=[],
            video_ids=[],
            processing_time_ms=processing_time,
        )

    except Exception as e:
        logger.error(f"Video query failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Video query failed: {str(e)}"
        )


@router.post("/videos/{video_id}/ask", response_model=VideoQueryResponse)
async def ask_video_question(
    video_id: str,
    request: VideoQueryRequest,
):
    """
    Ask questions about a specific video

    - **video_id**: Video to query
    - **question**: Question to answer
    - **max_context_items**: Maximum context items to retrieve
    - **include_sources**: Include source timestamps

    Scoped version of query endpoint for single video
    """
    try:
        logger.info(f"Video {video_id} query: '{request.question}'")

        # TODO: Verify video exists
        # video = db.query(Video).filter(Video.id == video_id).first()
        # if not video:
        #     raise HTTPException(status_code=404, detail="Video not found")

        # Override video_id in request
        request.video_id = video_id

        # Use main query function
        return await query_videos(request)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Video question failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Video question failed: {str(e)}"
        )


# ============================================================================
# Advanced Search Endpoints
# ============================================================================


@router.get("/videos/{video_id}/similar", response_model=SearchResponse)
async def find_similar_videos(
    video_id: str,
    top_k: int = Query(5, ge=1, le=20),
    similarity_metric: str = Query("visual", description="Metric: visual, semantic, combined"),
):
    """
    Find videos similar to a given video

    - **video_id**: Reference video
    - **top_k**: Number of similar videos to return
    - **similarity_metric**: Comparison metric (visual, semantic, combined)

    Compares videos by a "fingerprint" (the mean of a video's own
    transcript + scene-caption embeddings), matched against other
    videos' individual embeddings. No real CLIP visual embeddings are
    wired up yet, so "visual" and "combined" currently behave the same
    as "semantic".
    """
    try:
        logger.info(f"Finding videos similar to {video_id}")

        start_time = datetime.now()

        # No real CLIP visual embeddings are wired up yet (deferred - see
        # WORKFLOW_TEST_RESULTS.md), so "visual" and "combined" currently
        # fall back to the same real text embeddings "semantic" uses.
        import numpy as np
        from pathlib import Path
        from src.core.config import settings
        from src.core.database import get_db
        from src.models import Video
        from src.core.vector_store import VideoVectorStore

        with get_db() as db:
            ref_video = db.query(Video).filter(Video.external_id == video_id).first()
            if not ref_video:
                raise HTTPException(status_code=404, detail="Video not found")

        store = VideoVectorStore(persist_directory=Path(settings.chroma_persist_directory))
        store.initialize_collections()

        ref_embeddings = store.get_video_embeddings(video_id)
        transcript_vecs = ref_embeddings.get("transcripts", {}).get("embeddings")
        scene_vecs = ref_embeddings.get("scenes", {}).get("embeddings")
        vectors = list(transcript_vecs) if transcript_vecs is not None else []
        vectors += list(scene_vecs) if scene_vecs is not None else []
        if not vectors:
            return SearchResponse(
                query=f"Videos similar to {video_id}",
                results=[],
                total_results=0,
                search_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
            )

        fingerprint = np.mean(np.array(vectors), axis=0)

        best_per_video = {}
        for hits in (
            store.search_transcripts(fingerprint, n_results=top_k * 5 + 5),
            store.search_scenes(fingerprint, n_results=top_k * 5 + 5),
        ):
            for i in range(len(hits.ids)):
                other_video_id = hits.metadatas[i].get("video_id")
                if not other_video_id or other_video_id == video_id:
                    continue
                similarity = 1.0 - hits.distances[i]
                if other_video_id not in best_per_video or similarity > best_per_video[other_video_id]:
                    best_per_video[other_video_id] = similarity

        ranked = sorted(best_per_video.items(), key=lambda kv: kv[1], reverse=True)[:top_k]

        with get_db() as db:
            titles = {
                v.external_id: v.title
                for v in db.query(Video).filter(Video.external_id.in_([vid for vid, _ in ranked])).all()
            } if ranked else {}

        results = [
            SearchResult(
                result_id=f"video_{vid}",
                result_type="video",
                video_id=vid,
                video_title=titles.get(vid, "Unknown"),
                timestamp=0.0,
                similarity_score=score,
                content=titles.get(vid, "Unknown"),
                metadata={"similarity_metric": similarity_metric},
            )
            for vid, score in ranked
        ]

        return SearchResponse(
            query=f"Videos similar to {video_id}",
            results=results,
            total_results=len(results),
            search_time_ms=(datetime.now() - start_time).total_seconds() * 1000,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Similar video search failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Similar video search failed: {str(e)}"
        )


@router.post("/temporal", response_model=SearchResponse)
async def temporal_search(
    query: str = Query(..., description="Search query"),
    start_time: float = Query(0.0, ge=0.0, description="Search from timestamp"),
    end_time: Optional[float] = Query(None, description="Search until timestamp"),
    video_ids: Optional[List[str]] = Query(None),
    top_k: int = Query(10, ge=1, le=100),
):
    """
    Search within specific time ranges

    - **query**: Search query
    - **start_time**: Search from this timestamp
    - **end_time**: Search until this timestamp (optional)
    - **video_ids**: Filter by videos
    - **top_k**: Number of results

    Performs semantic search restricted to time range
    """
    try:
        logger.info(f"Temporal search: '{query}' ({start_time}-{end_time})")

        search_started = datetime.now()

        from pathlib import Path
        from src.core.config import settings
        from src.core.database import get_db
        from src.models import Video
        from src.core.vector_store import VideoVectorStore
        from src.api.videos import _get_embedding_model

        embed_model = _get_embedding_model()
        query_vector = embed_model.encode([query])[0]

        store = VideoVectorStore(persist_directory=Path(settings.chroma_persist_directory))
        store.initialize_collections()

        raw_hits = []  # (similarity, result_type, timestamp, content, video_id, metadata)

        transcript_hits = store.search_transcripts(query_vector, n_results=top_k * 5 + 10)
        for i in range(len(transcript_hits.ids)):
            meta = transcript_hits.metadatas[i]
            similarity = 1.0 - transcript_hits.distances[i]
            text = transcript_hits.documents[i] if transcript_hits.documents else ""
            raw_hits.append((
                similarity, "transcript", meta.get("start_time", 0.0), text,
                meta.get("video_id"), meta,
            ))

        scene_hits = store.search_scenes(query_vector, n_results=top_k * 5 + 10)
        for i in range(len(scene_hits.ids)):
            meta = scene_hits.metadatas[i]
            similarity = 1.0 - scene_hits.distances[i]
            text = scene_hits.documents[i] if scene_hits.documents else ""
            raw_hits.append((
                similarity, "scene", meta.get("start_time", 0.0), text,
                meta.get("video_id"), meta,
            ))

        if video_ids:
            raw_hits = [h for h in raw_hits if h[4] in video_ids]
        raw_hits = [h for h in raw_hits if h[2] >= start_time]
        if end_time is not None:
            raw_hits = [h for h in raw_hits if h[2] <= end_time]
        raw_hits.sort(key=lambda h: h[0], reverse=True)
        raw_hits = raw_hits[:top_k]

        video_titles = {}
        with get_db() as db:
            ext_ids = {h[4] for h in raw_hits if h[4]}
            if ext_ids:
                rows = db.query(Video).filter(Video.external_id.in_(ext_ids)).all()
                video_titles = {v.external_id: v.title for v in rows}

        results = [
            SearchResult(
                result_id=f"{h[1]}_{i}",
                result_type=h[1],
                video_id=h[4] or "",
                video_title=video_titles.get(h[4], "Unknown"),
                timestamp=h[2],
                similarity_score=h[0],
                content=h[3],
                metadata=h[5],
            )
            for i, h in enumerate(raw_hits)
        ]

        return SearchResponse(
            query=query,
            results=results,
            total_results=len(results),
            search_time_ms=(datetime.now() - search_started).total_seconds() * 1000,
        )

    except Exception as e:
        logger.error(f"Temporal search failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Temporal search failed: {str(e)}"
        )
