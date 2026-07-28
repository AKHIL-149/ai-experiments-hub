"""
Video query processor for question answering
RAG-based approach with multi-modal context retrieval
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class QueryConfig:
    """Configuration for query processing"""
    # Retrieval settings
    retrieval_top_k: int = 10
    min_similarity: float = 0.3

    # Context building
    max_context_length: int = 2000  # Characters
    include_visual_context: bool = True
    include_transcript_context: bool = True

    # Answer generation
    max_answer_length: int = 500  # Characters
    include_sources: bool = True
    include_timestamps: bool = True

    # LLM settings
    temperature: float = 0.3
    use_cache: bool = True

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QuerySource:
    """Source used for answering query"""
    source_id: str
    source_type: str  # "frame", "transcript", "scene"
    video_id: str

    # Temporal info
    timestamp: float
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    # Content
    content: str
    similarity_score: float = 0.0

    # Visual content
    frame_path: Optional[str] = None
    description: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryAnswer:
    """Answer to user query"""
    query: str
    answer: str

    # Sources
    sources: List[QuerySource] = field(default_factory=list)
    num_sources: int = 0

    # Confidence
    confidence: Optional[float] = None

    # Processing info
    context_used: str = ""
    processing_time_ms: float = 0.0

    # LLM info
    model_used: Optional[str] = None
    tokens_used: Optional[Dict[str, int]] = None
    cached: bool = False

    metadata: Dict[str, Any] = field(default_factory=dict)


class VideoQueryProcessor:
    """
    Process natural language queries about video content
    Use RAG approach with multi-modal retrieval
    """

    def __init__(
        self,
        semantic_search=None,
        frame_search=None,
        transcript_search=None,
        llm_client=None,
        default_config: Optional[QueryConfig] = None,
    ):
        """
        Initialize video query processor

        Args:
            semantic_search: SemanticVideoSearch instance
            frame_search: FrameSearchEngine instance
            transcript_search: TranscriptSearchEngine instance
            llm_client: LLM client for answer generation
            default_config: Default query configuration
        """
        self.semantic_search = semantic_search
        self.frame_search = frame_search
        self.transcript_search = transcript_search
        self.llm_client = llm_client
        self.default_config = default_config or QueryConfig()

        logger.info("Initialized VideoQueryProcessor")

    def answer_query(
        self,
        query: str,
        video_id: Optional[str] = None,
        config: Optional[QueryConfig] = None,
    ) -> QueryAnswer:
        """
        Answer natural language query about video(s)

        Args:
            query: User question
            video_id: Optional video to query (None = all videos)
            config: Query configuration

        Returns:
            QueryAnswer
        """
        import time
        start_time = time.time()

        config = config or self.default_config

        logger.info(
            f"Processing query: '{query}' "
            f"(video_id={video_id or 'all'})"
        )

        # Retrieve relevant context
        sources = self._retrieve_context(query, video_id, config)

        # Build context for LLM
        context = self._build_context(sources, config)

        # Generate answer using LLM
        if self.llm_client:
            answer_text, llm_info = self._generate_answer(
                query=query,
                context=context,
                config=config,
            )
        else:
            # Fallback: simple extraction
            answer_text = self._extract_answer_from_context(context)
            llm_info = {}

        # Calculate processing time
        processing_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Answered query in {processing_time_ms:.2f}ms "
            f"(sources={len(sources)})"
        )

        return QueryAnswer(
            query=query,
            answer=answer_text,
            sources=sources,
            num_sources=len(sources),
            context_used=context,
            processing_time_ms=processing_time_ms,
            model_used=llm_info.get("model"),
            tokens_used=llm_info.get("tokens"),
            cached=llm_info.get("cached", False),
        )

    def answer_with_timestamp(
        self,
        query: str,
        video_id: str,
        timestamp: float,
        context_window: float = 30.0,
        config: Optional[QueryConfig] = None,
    ) -> QueryAnswer:
        """
        Answer query with temporal context around timestamp

        Args:
            query: User question
            video_id: Video ID
            timestamp: Timestamp to focus on
            context_window: Window size in seconds
            config: Query configuration

        Returns:
            QueryAnswer
        """
        config = config or self.default_config

        logger.info(
            f"Processing query at {timestamp}s: '{query}'"
        )

        # Retrieve context around timestamp
        sources = self._retrieve_temporal_context(
            query=query,
            video_id=video_id,
            timestamp=timestamp,
            window=context_window,
            config=config,
        )

        # Build context
        context = self._build_context(sources, config)

        # Generate answer
        if self.llm_client:
            answer_text, llm_info = self._generate_answer(
                query=query,
                context=context,
                config=config,
            )
        else:
            answer_text = self._extract_answer_from_context(context)
            llm_info = {}

        return QueryAnswer(
            query=query,
            answer=answer_text,
            sources=sources,
            num_sources=len(sources),
            context_used=context,
            model_used=llm_info.get("model"),
            tokens_used=llm_info.get("tokens"),
            cached=llm_info.get("cached", False),
        )

    def _retrieve_context(
        self,
        query: str,
        video_id: Optional[str],
        config: QueryConfig,
    ) -> List[QuerySource]:
        """Retrieve relevant context for query"""
        sources = []

        # Search transcripts
        if config.include_transcript_context and self.transcript_search:
            transcript_results = self.transcript_search.search(
                query=query,
                config=self._get_transcript_search_config(video_id, config),
            )

            for match in transcript_results.matches[:config.retrieval_top_k]:
                source = QuerySource(
                    source_id=match.transcript_id,
                    source_type="transcript",
                    video_id=match.video_id,
                    timestamp=match.timestamp,
                    start_time=match.start_time,
                    end_time=match.end_time,
                    content=match.text,
                    similarity_score=match.similarity_score,
                )
                sources.append(source)

        # Search frames
        if config.include_visual_context and self.frame_search:
            frame_results = self.frame_search.search(
                query=query,
                config=self._get_frame_search_config(video_id, config),
            )

            for match in frame_results.matches[:config.retrieval_top_k]:
                source = QuerySource(
                    source_id=match.frame_id,
                    source_type="frame",
                    video_id=match.video_id,
                    timestamp=match.timestamp,
                    content=match.description or "Visual frame",
                    similarity_score=match.similarity_score,
                    frame_path=match.frame_path,
                    description=match.description,
                )
                sources.append(source)

        # Sort by similarity
        sources = sorted(
            sources,
            key=lambda s: s.similarity_score,
            reverse=True,
        )

        # Limit to top_k
        sources = sources[:config.retrieval_top_k]

        logger.debug(f"Retrieved {len(sources)} context sources")

        return sources

    def _retrieve_temporal_context(
        self,
        query: str,
        video_id: str,
        timestamp: float,
        window: float,
        config: QueryConfig,
    ) -> List[QuerySource]:
        """Retrieve context around specific timestamp"""
        sources = []

        half_window = window / 2
        start_time = max(0, timestamp - half_window)
        end_time = timestamp + half_window

        # Get transcript context
        if config.include_transcript_context and self.transcript_search:
            from src.services.search.transcript_search import TranscriptSearchConfig

            transcript_config = TranscriptSearchConfig(
                use_semantic_search=True,
                top_k=config.retrieval_top_k,
                video_ids=[video_id],
                time_range=(start_time, end_time),
            )

            transcript_results = self.transcript_search.search(
                query=query,
                config=transcript_config,
            )

            for match in transcript_results.matches:
                source = QuerySource(
                    source_id=match.transcript_id,
                    source_type="transcript",
                    video_id=match.video_id,
                    timestamp=match.timestamp,
                    start_time=match.start_time,
                    end_time=match.end_time,
                    content=match.text,
                    similarity_score=match.similarity_score,
                )
                sources.append(source)

        # Get visual context
        if config.include_visual_context and self.frame_search:
            from src.services.search.frame_search import FrameSearchConfig

            frame_config = FrameSearchConfig(
                top_k=config.retrieval_top_k,
                video_ids=[video_id],
                time_range=(start_time, end_time),
            )

            frame_results = self.frame_search.search(
                query=query,
                config=frame_config,
            )

            for match in frame_results.matches:
                source = QuerySource(
                    source_id=match.frame_id,
                    source_type="frame",
                    video_id=match.video_id,
                    timestamp=match.timestamp,
                    content=match.description or "Visual content",
                    similarity_score=match.similarity_score,
                    frame_path=match.frame_path,
                    description=match.description,
                )
                sources.append(source)

        return sources

    def _build_context(
        self,
        sources: List[QuerySource],
        config: QueryConfig,
    ) -> str:
        """Build context string from sources"""
        context_parts = []
        current_length = 0

        for source in sources:
            # Format source
            if source.source_type == "transcript":
                timestamp_str = self._format_timestamp(source.timestamp)
                part = f"[{timestamp_str}] {source.content}"
            elif source.source_type == "frame":
                timestamp_str = self._format_timestamp(source.timestamp)
                part = f"[{timestamp_str}] Visual: {source.content}"
            else:
                part = source.content

            # Check length
            if current_length + len(part) > config.max_context_length:
                break

            context_parts.append(part)
            current_length += len(part)

        context = "\n".join(context_parts)

        logger.debug(
            f"Built context: {len(context)} chars from {len(context_parts)} sources"
        )

        return context

    def _generate_answer(
        self,
        query: str,
        context: str,
        config: QueryConfig,
    ) -> tuple[str, Dict[str, Any]]:
        """Generate answer using LLM"""
        # Build prompt
        system_prompt = """You are a helpful assistant that answers questions about video content.
You will be given context from video transcripts and visual descriptions.
Answer the question based on the provided context.
If the context doesn't contain enough information, say so."""

        user_prompt = f"""Context from video:
{context}

Question: {query}

Please answer the question based on the context above."""

        # Generate answer
        response = self.llm_client.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            max_tokens=config.max_answer_length,
            temperature=config.temperature,
            use_cache=config.use_cache,
        )

        answer_text = response.get("text", "")

        llm_info = {
            "model": response.get("model"),
            "tokens": response.get("tokens"),
            "cached": response.get("cached", False),
        }

        return answer_text, llm_info

    def _extract_answer_from_context(
        self,
        context: str,
    ) -> str:
        """Extract answer from context (fallback when no LLM)"""
        # Simple extraction: return first few lines
        lines = context.split("\n")
        return "\n".join(lines[:3]) + "\n\n(Answer generated without LLM - install LLM client for better answers)"

    def _get_transcript_search_config(
        self,
        video_id: Optional[str],
        config: QueryConfig,
    ):
        """Get transcript search configuration"""
        from src.services.search.transcript_search import TranscriptSearchConfig

        return TranscriptSearchConfig(
            use_semantic_search=True,
            top_k=config.retrieval_top_k,
            min_similarity=config.min_similarity,
            video_ids=[video_id] if video_id else None,
        )

    def _get_frame_search_config(
        self,
        video_id: Optional[str],
        config: QueryConfig,
    ):
        """Get frame search configuration"""
        from src.services.search.frame_search import FrameSearchConfig

        return FrameSearchConfig(
            top_k=config.retrieval_top_k,
            min_similarity=config.min_similarity,
            video_ids=[video_id] if video_id else None,
        )

    def _format_timestamp(self, seconds: float) -> str:
        """Format timestamp"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"

    def export_to_dict(
        self,
        answer: QueryAnswer,
    ) -> Dict[str, Any]:
        """Export answer to dictionary"""
        return {
            "query": answer.query,
            "answer": answer.answer,
            "num_sources": answer.num_sources,
            "confidence": answer.confidence,
            "processing_time_ms": answer.processing_time_ms,
            "model_used": answer.model_used,
            "cached": answer.cached,
            "sources": [
                {
                    "source_id": s.source_id,
                    "source_type": s.source_type,
                    "video_id": s.video_id,
                    "timestamp": s.timestamp,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "content": s.content,
                    "similarity_score": s.similarity_score,
                    "frame_path": s.frame_path,
                    "description": s.description,
                }
                for s in answer.sources
            ],
            "metadata": answer.metadata,
        }

    def ask_multiple_questions(
        self,
        questions: List[str],
        video_id: Optional[str] = None,
        config: Optional[QueryConfig] = None,
    ) -> List[QueryAnswer]:
        """
        Answer multiple questions about video

        Args:
            questions: List of questions
            video_id: Optional video ID
            config: Query configuration

        Returns:
            List of answers
        """
        answers = []

        for question in questions:
            answer = self.answer_query(
                query=question,
                video_id=video_id,
                config=config,
            )
            answers.append(answer)

        return answers

    def summarize_with_questions(
        self,
        video_id: str,
        questions: Optional[List[str]] = None,
        config: Optional[QueryConfig] = None,
    ) -> Dict[str, QueryAnswer]:
        """
        Generate structured summary using predefined questions

        Args:
            video_id: Video ID
            questions: Optional custom questions (uses defaults if None)
            config: Query configuration

        Returns:
            Dictionary mapping questions to answers
        """
        # Default questions for summary
        default_questions = [
            "What is the main topic of this video?",
            "What are the key points discussed?",
            "Who are the main speakers or people in this video?",
            "What conclusions or takeaways are presented?",
        ]

        questions = questions or default_questions

        summary = {}

        for question in questions:
            answer = self.answer_query(
                query=question,
                video_id=video_id,
                config=config,
            )
            summary[question] = answer

        return summary


def answer_video_query(
    query: str,
    video_id: Optional[str] = None,
    semantic_search=None,
    frame_search=None,
    transcript_search=None,
    llm_client=None,
) -> QueryAnswer:
    """
    Convenience function to answer video query

    Args:
        query: User question
        video_id: Optional video ID
        semantic_search: SemanticVideoSearch instance
        frame_search: FrameSearchEngine instance
        transcript_search: TranscriptSearchEngine instance
        llm_client: LLM client

    Returns:
        QueryAnswer
    """
    processor = VideoQueryProcessor(
        semantic_search=semantic_search,
        frame_search=frame_search,
        transcript_search=transcript_search,
        llm_client=llm_client,
    )

    return processor.answer_query(query, video_id)
