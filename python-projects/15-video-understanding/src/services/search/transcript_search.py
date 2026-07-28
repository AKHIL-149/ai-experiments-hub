"""
Transcript search engine for text content retrieval
Full-text and semantic search in video transcripts
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
import re

logger = logging.getLogger(__name__)


@dataclass
class TranscriptSearchConfig:
    """Configuration for transcript search"""
    # Search mode
    use_semantic_search: bool = True  # Use embeddings vs keyword search
    case_sensitive: bool = False

    # Retrieval settings
    top_k: int = 10
    min_similarity: float = 0.0

    # Filtering
    video_ids: Optional[List[str]] = None
    speaker_ids: Optional[List[str]] = None
    time_range: Optional[Tuple[float, float]] = None

    # Context
    include_context: bool = True
    context_window: int = 2  # Number of sentences before/after

    # Highlighting
    highlight_matches: bool = True

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TranscriptMatch:
    """Single transcript match result"""
    transcript_id: str
    video_id: str

    # Temporal info
    start_time: float
    end_time: float
    timestamp: float  # Center timestamp

    # Content
    text: str
    matched_text: Optional[str] = None  # Actual matching portion

    # Speaker
    speaker_id: Optional[str] = None
    speaker_name: Optional[str] = None

    # Scene context
    scene_id: Optional[int] = None

    # Similarity
    similarity_score: float = 0.0

    # Context
    context_before: Optional[str] = None
    context_after: Optional[str] = None

    # Ranking
    rank: Optional[int] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TranscriptSearchResults:
    """Collection of transcript search results"""
    query: str
    matches: List[TranscriptMatch]
    total_matches: int

    # Search info
    search_mode: str  # "semantic" or "keyword"
    config: TranscriptSearchConfig
    search_time_ms: float = 0.0

    metadata: Dict[str, Any] = field(default_factory=dict)


class TranscriptSearchEngine:
    """
    Search engine for text content in video transcripts
    Support both semantic and keyword-based search
    """

    def __init__(
        self,
        transcript_vector_store=None,
        text_embedder=None,
        database=None,  # For keyword search
        default_config: Optional[TranscriptSearchConfig] = None,
    ):
        """
        Initialize transcript search engine

        Args:
            transcript_vector_store: TranscriptVectorStore for semantic search
            text_embedder: Text embedder for query encoding
            database: Database connection for keyword search
            default_config: Default search configuration
        """
        self.transcript_vector_store = transcript_vector_store
        self.text_embedder = text_embedder
        self.database = database
        self.default_config = default_config or TranscriptSearchConfig()

        logger.info("Initialized TranscriptSearchEngine")

    def search(
        self,
        query: str,
        config: Optional[TranscriptSearchConfig] = None,
    ) -> TranscriptSearchResults:
        """
        Search transcripts for query

        Args:
            query: Search query
            config: Search configuration

        Returns:
            TranscriptSearchResults
        """
        import time
        start_time = time.time()

        config = config or self.default_config

        logger.info(
            f"Searching transcripts for: '{query}' "
            f"(mode={'semantic' if config.use_semantic_search else 'keyword'})"
        )

        # Search based on mode
        if config.use_semantic_search:
            matches, search_mode = self._search_semantic(query, config)
        else:
            matches, search_mode = self._search_keyword(query, config)

        # Apply filters
        matches = self._apply_filters(matches, config)

        # Add context if requested
        if config.include_context:
            matches = self._add_context(matches, config.context_window)

        # Highlight matches if requested
        if config.highlight_matches and not config.use_semantic_search:
            matches = self._highlight_matches(matches, query, config.case_sensitive)

        # Sort by similarity/relevance
        matches = sorted(
            matches,
            key=lambda m: m.similarity_score,
            reverse=True,
        )

        # Limit to top_k
        matches = matches[:config.top_k]

        # Assign ranks
        for i, match in enumerate(matches, 1):
            match.rank = i

        # Calculate search time
        search_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Found {len(matches)} transcript matches in {search_time_ms:.2f}ms"
        )

        return TranscriptSearchResults(
            query=query,
            matches=matches,
            total_matches=len(matches),
            search_mode=search_mode,
            config=config,
            search_time_ms=search_time_ms,
        )

    def _search_semantic(
        self,
        query: str,
        config: TranscriptSearchConfig,
    ) -> Tuple[List[TranscriptMatch], str]:
        """Search using semantic similarity"""
        if not self.transcript_vector_store or not self.text_embedder:
            logger.warning(
                "Semantic search not available, falling back to keyword search"
            )
            return self._search_keyword(query, config)

        # Encode query
        query_embedding = self.text_embedder.encode(query)

        # Search vector store
        raw_results = self.transcript_vector_store.search(
            query_embedding=query_embedding,
            top_k=config.top_k * 2,  # Get more for filtering
            min_similarity=config.min_similarity,
            video_ids=config.video_ids,
        )

        # Convert to matches
        matches = self._convert_to_matches(raw_results)

        return matches, "semantic"

    def _search_keyword(
        self,
        query: str,
        config: TranscriptSearchConfig,
    ) -> Tuple[List[TranscriptMatch], str]:
        """Search using keyword matching"""
        if not self.database:
            logger.warning("Keyword search not available (no database)")
            return [], "keyword"

        # Build SQL query
        # This is a simplified version - actual implementation would use
        # database-specific full-text search
        search_pattern = query if config.case_sensitive else query.lower()

        # Query transcripts table
        # NOTE: This is pseudo-code - actual implementation depends on database
        sql = """
            SELECT
                id, video_id, start_time, end_time, text,
                speaker_id, scene_id
            FROM transcripts
            WHERE
        """

        # Add text search condition
        if config.case_sensitive:
            sql += "text LIKE ?"
            params = [f"%{search_pattern}%"]
        else:
            sql += "LOWER(text) LIKE ?"
            params = [f"%{search_pattern}%"]

        # Add video filter
        if config.video_ids:
            placeholders = ",".join("?" * len(config.video_ids))
            sql += f" AND video_id IN ({placeholders})"
            params.extend(config.video_ids)

        # Add speaker filter
        if config.speaker_ids:
            placeholders = ",".join("?" * len(config.speaker_ids))
            sql += f" AND speaker_id IN ({placeholders})"
            params.extend(config.speaker_ids)

        # Add time range filter
        if config.time_range:
            start_time, end_time = config.time_range
            sql += " AND start_time >= ? AND end_time <= ?"
            params.extend([start_time, end_time])

        sql += " ORDER BY start_time LIMIT ?"
        params.append(config.top_k * 2)

        # Execute query (pseudo-code)
        # results = self.database.execute(sql, params)

        # For now, return empty list
        # Actual implementation would convert database results to TranscriptMatch
        matches = []

        # Mock implementation for demonstration
        # In real implementation, fetch from database and convert
        logger.debug(f"Keyword search query: {sql}")
        logger.debug(f"Parameters: {params}")

        return matches, "keyword"

    def search_by_speaker(
        self,
        speaker_id: str,
        query: Optional[str] = None,
        config: Optional[TranscriptSearchConfig] = None,
    ) -> TranscriptSearchResults:
        """
        Search transcripts by specific speaker

        Args:
            speaker_id: Speaker identifier
            query: Optional text query
            config: Search configuration

        Returns:
            TranscriptSearchResults
        """
        config = config or self.default_config

        # Set speaker filter
        filtered_config = TranscriptSearchConfig(
            use_semantic_search=config.use_semantic_search,
            case_sensitive=config.case_sensitive,
            top_k=config.top_k,
            min_similarity=config.min_similarity,
            video_ids=config.video_ids,
            speaker_ids=[speaker_id],
            time_range=config.time_range,
            include_context=config.include_context,
            context_window=config.context_window,
            highlight_matches=config.highlight_matches,
        )

        # If no query, get all segments for speaker
        if not query:
            query = "*"  # Match all

        return self.search(query, filtered_config)

    def search_in_time_range(
        self,
        query: str,
        start_time: float,
        end_time: float,
        video_id: Optional[str] = None,
        config: Optional[TranscriptSearchConfig] = None,
    ) -> TranscriptSearchResults:
        """
        Search transcripts in specific time range

        Args:
            query: Search query
            start_time: Start time in seconds
            end_time: End time in seconds
            video_id: Optional video filter
            config: Search configuration

        Returns:
            TranscriptSearchResults
        """
        config = config or self.default_config

        # Set filters
        filtered_config = TranscriptSearchConfig(
            use_semantic_search=config.use_semantic_search,
            case_sensitive=config.case_sensitive,
            top_k=config.top_k,
            min_similarity=config.min_similarity,
            video_ids=[video_id] if video_id else config.video_ids,
            speaker_ids=config.speaker_ids,
            time_range=(start_time, end_time),
            include_context=config.include_context,
            context_window=config.context_window,
            highlight_matches=config.highlight_matches,
        )

        return self.search(query, filtered_config)

    def find_phrase(
        self,
        phrase: str,
        exact_match: bool = True,
        config: Optional[TranscriptSearchConfig] = None,
    ) -> TranscriptSearchResults:
        """
        Find exact phrase in transcripts

        Args:
            phrase: Phrase to find
            exact_match: Require exact match
            config: Search configuration

        Returns:
            TranscriptSearchResults
        """
        config = config or self.default_config

        # Force keyword search for exact matching
        phrase_config = TranscriptSearchConfig(
            use_semantic_search=False,
            case_sensitive=exact_match,
            top_k=config.top_k,
            min_similarity=0.0,
            video_ids=config.video_ids,
            speaker_ids=config.speaker_ids,
            time_range=config.time_range,
            include_context=config.include_context,
            context_window=config.context_window,
            highlight_matches=True,
        )

        return self.search(phrase, phrase_config)

    def _convert_to_matches(
        self,
        raw_results: List[Dict[str, Any]],
    ) -> List[TranscriptMatch]:
        """Convert raw results to TranscriptMatch objects"""
        matches = []

        for result in raw_results:
            # Calculate center timestamp
            start_time = result.get("start_time", 0.0)
            end_time = result.get("end_time", 0.0)
            timestamp = (start_time + end_time) / 2

            match = TranscriptMatch(
                transcript_id=result.get("transcript_id", ""),
                video_id=result.get("video_id", ""),
                start_time=start_time,
                end_time=end_time,
                timestamp=timestamp,
                text=result.get("text", ""),
                speaker_id=result.get("speaker_id"),
                speaker_name=result.get("speaker_name"),
                scene_id=result.get("scene_id"),
                similarity_score=result.get("similarity", 0.0),
                metadata=result.get("metadata", {}),
            )
            matches.append(match)

        return matches

    def _apply_filters(
        self,
        matches: List[TranscriptMatch],
        config: TranscriptSearchConfig,
    ) -> List[TranscriptMatch]:
        """Apply filters to matches"""
        filtered = matches

        # Filter by video IDs
        if config.video_ids:
            filtered = [
                m for m in filtered
                if m.video_id in config.video_ids
            ]

        # Filter by speaker IDs
        if config.speaker_ids:
            filtered = [
                m for m in filtered
                if m.speaker_id in config.speaker_ids
            ]

        # Filter by time range
        if config.time_range:
            start_time, end_time = config.time_range
            filtered = [
                m for m in filtered
                if m.start_time >= start_time and m.end_time <= end_time
            ]

        # Filter by minimum similarity
        if config.min_similarity > 0.0:
            filtered = [
                m for m in filtered
                if m.similarity_score >= config.min_similarity
            ]

        return filtered

    def _add_context(
        self,
        matches: List[TranscriptMatch],
        context_window: int,
    ) -> List[TranscriptMatch]:
        """Add context before and after each match"""
        # This would fetch surrounding transcript segments
        # For now, just return matches as-is
        # Actual implementation would query database for adjacent segments
        logger.debug(f"Adding context (window={context_window})")

        return matches

    def _highlight_matches(
        self,
        matches: List[TranscriptMatch],
        query: str,
        case_sensitive: bool,
    ) -> List[TranscriptMatch]:
        """Highlight matching text in results"""
        for match in matches:
            if not match.text:
                continue

            # Find matching portion
            if case_sensitive:
                pattern = re.escape(query)
                flags = 0
            else:
                pattern = re.escape(query)
                flags = re.IGNORECASE

            # Find first match
            search_result = re.search(pattern, match.text, flags)

            if search_result:
                match.matched_text = search_result.group(0)

        return matches

    def get_full_transcript(
        self,
        video_id: str,
        speaker_id: Optional[str] = None,
    ) -> List[TranscriptMatch]:
        """
        Get full transcript for a video

        Args:
            video_id: Video ID
            speaker_id: Optional speaker filter

        Returns:
            List of transcript segments in order
        """
        config = TranscriptSearchConfig(
            use_semantic_search=False,
            top_k=10000,  # Get all
            video_ids=[video_id],
            speaker_ids=[speaker_id] if speaker_id else None,
            include_context=False,
        )

        results = self.search("*", config)

        # Sort by timestamp
        matches = sorted(results.matches, key=lambda m: m.start_time)

        return matches

    def export_to_dict(
        self,
        results: TranscriptSearchResults,
    ) -> Dict[str, Any]:
        """Export results to dictionary"""
        return {
            "query": results.query,
            "search_mode": results.search_mode,
            "total_matches": results.total_matches,
            "search_time_ms": results.search_time_ms,
            "matches": [
                {
                    "transcript_id": m.transcript_id,
                    "video_id": m.video_id,
                    "start_time": m.start_time,
                    "end_time": m.end_time,
                    "timestamp": m.timestamp,
                    "text": m.text,
                    "matched_text": m.matched_text,
                    "speaker_id": m.speaker_id,
                    "speaker_name": m.speaker_name,
                    "scene_id": m.scene_id,
                    "similarity_score": m.similarity_score,
                    "context_before": m.context_before,
                    "context_after": m.context_after,
                    "rank": m.rank,
                    "metadata": m.metadata,
                }
                for m in results.matches
            ],
            "config": {
                "search_mode": "semantic" if results.config.use_semantic_search else "keyword",
                "top_k": results.config.top_k,
                "min_similarity": results.config.min_similarity,
                "case_sensitive": results.config.case_sensitive,
            },
            "metadata": results.metadata,
        }


def search_transcripts(
    query: str,
    transcript_vector_store=None,
    text_embedder=None,
    use_semantic: bool = True,
    top_k: int = 10,
) -> TranscriptSearchResults:
    """
    Convenience function to search transcripts

    Args:
        query: Search query
        transcript_vector_store: Transcript vector store
        text_embedder: Text embedder
        use_semantic: Use semantic search
        top_k: Number of results

    Returns:
        TranscriptSearchResults
    """
    config = TranscriptSearchConfig(
        use_semantic_search=use_semantic,
        top_k=top_k,
    )

    engine = TranscriptSearchEngine(
        transcript_vector_store=transcript_vector_store,
        text_embedder=text_embedder,
        default_config=config,
    )

    return engine.search(query, config)
