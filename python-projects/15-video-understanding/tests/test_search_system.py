"""
Tests for search and query system
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

from src.services.search.semantic_search import (
    SemanticVideoSearch,
    SearchConfig,
    SearchMode,
    SearchResult,
    SearchResults,
    search_videos,
)
from src.services.search.frame_search import (
    FrameSearchEngine,
    FrameSearchConfig,
    FrameMatch,
    FrameSearchResults,
    search_frames,
)
from src.services.search.transcript_search import (
    TranscriptSearchEngine,
    TranscriptSearchConfig,
    TranscriptMatch,
    TranscriptSearchResults,
    search_transcripts,
)
from src.services.search.query_processor import (
    VideoQueryProcessor,
    QueryConfig,
    QuerySource,
    QueryAnswer,
    answer_video_query,
)
from src.services.search.result_ranker import (
    SearchResultRanker,
    RankingConfig,
    rank_search_results,
)


# ============================================================================
# SemanticVideoSearch Tests
# ============================================================================


class TestSemanticVideoSearch:
    """Test SemanticVideoSearch"""

    def test_init(self):
        """Test initialization"""
        searcher = SemanticVideoSearch()

        assert searcher.frame_vector_store is None
        assert searcher.transcript_vector_store is None
        assert searcher.default_config is not None

    def test_search_visual_only(self):
        """Test visual-only search"""
        # Mock frame vector store
        frame_store = Mock()
        frame_store.search.return_value = [
            {
                "frame_id": "frame1",
                "video_id": "video1",
                "timestamp": 10.0,
                "similarity": 0.9,
                "frame_path": "/path/frame1.jpg",
            }
        ]

        # Mock CLIP embedder
        clip_embedder = Mock()
        clip_embedder.encode_text.return_value = [0.1] * 512

        config = SearchConfig(mode=SearchMode.VISUAL_ONLY, top_k=5)

        searcher = SemanticVideoSearch(
            frame_vector_store=frame_store,
            clip_embedder=clip_embedder,
            default_config=config,
        )

        results = searcher.search("person walking", config)

        assert isinstance(results, SearchResults)
        assert results.search_mode == SearchMode.VISUAL_ONLY
        assert len(results.results) <= 5
        clip_embedder.encode_text.assert_called_once_with("person walking")

    def test_search_text_only(self):
        """Test text-only search"""
        # Mock transcript vector store
        transcript_store = Mock()
        transcript_store.search.return_value = [
            {
                "transcript_id": "trans1",
                "video_id": "video1",
                "timestamp": 15.0,
                "text": "This is a test",
                "similarity": 0.85,
            }
        ]

        # Mock text embedder
        text_embedder = Mock()
        text_embedder.encode.return_value = [0.2] * 768

        config = SearchConfig(mode=SearchMode.TEXT_ONLY, top_k=5)

        searcher = SemanticVideoSearch(
            transcript_vector_store=transcript_store,
            text_embedder=text_embedder,
            default_config=config,
        )

        results = searcher.search("machine learning", config)

        assert isinstance(results, SearchResults)
        assert results.search_mode == SearchMode.TEXT_ONLY
        text_embedder.encode.assert_called_once_with("machine learning")

    def test_search_multimodal(self):
        """Test multimodal search"""
        # Mock stores
        frame_store = Mock()
        frame_store.search.return_value = [
            {"frame_id": "f1", "video_id": "v1", "timestamp": 10.0, "similarity": 0.9}
        ]

        transcript_store = Mock()
        transcript_store.search.return_value = [
            {"transcript_id": "t1", "video_id": "v1", "timestamp": 15.0, "similarity": 0.8, "text": "test"}
        ]

        clip_embedder = Mock()
        clip_embedder.encode_text.return_value = [0.1] * 512

        text_embedder = Mock()
        text_embedder.encode.return_value = [0.2] * 768

        config = SearchConfig(mode=SearchMode.MULTIMODAL, top_k=10)

        searcher = SemanticVideoSearch(
            frame_vector_store=frame_store,
            transcript_vector_store=transcript_store,
            clip_embedder=clip_embedder,
            text_embedder=text_embedder,
            default_config=config,
        )

        results = searcher.search("test query", config)

        assert isinstance(results, SearchResults)
        assert results.search_mode == SearchMode.MULTIMODAL
        # Should have results from both modalities
        assert len(results.results) > 0

    def test_search_by_video(self):
        """Test searching within specific video"""
        frame_store = Mock()
        frame_store.search.return_value = []

        clip_embedder = Mock()
        clip_embedder.encode_text.return_value = [0.1] * 512

        searcher = SemanticVideoSearch(
            frame_vector_store=frame_store,
            clip_embedder=clip_embedder,
        )

        results = searcher.search_by_video(
            query="test",
            video_id="video123",
        )

        assert isinstance(results, SearchResults)
        # Verify video_id filter was applied
        frame_store.search.assert_called()


# ============================================================================
# FrameSearchEngine Tests
# ============================================================================


class TestFrameSearchEngine:
    """Test FrameSearchEngine"""

    def test_init(self):
        """Test initialization"""
        engine = FrameSearchEngine()

        assert engine.frame_vector_store is None
        assert engine.clip_embedder is None
        assert engine.default_config is not None

    def test_search_frames(self):
        """Test frame search"""
        # Mock frame store
        frame_store = Mock()
        frame_store.search.return_value = [
            {
                "frame_id": "frame1",
                "video_id": "video1",
                "frame_path": "/path/frame1.jpg",
                "timestamp": 10.0,
                "frame_number": 100,
                "similarity": 0.92,
                "scene_id": 1,
                "description": "A person walking",
            },
            {
                "frame_id": "frame2",
                "video_id": "video1",
                "frame_path": "/path/frame2.jpg",
                "timestamp": 12.0,
                "frame_number": 120,
                "similarity": 0.88,
                "scene_id": 1,
            },
        ]

        # Mock CLIP embedder
        clip_embedder = Mock()
        clip_embedder.encode_text.return_value = [0.1] * 512

        config = FrameSearchConfig(top_k=5, min_similarity=0.5)

        engine = FrameSearchEngine(
            frame_vector_store=frame_store,
            clip_embedder=clip_embedder,
            default_config=config,
        )

        results = engine.search("person walking", config)

        assert isinstance(results, FrameSearchResults)
        assert len(results.matches) == 2
        assert all(isinstance(m, FrameMatch) for m in results.matches)
        clip_embedder.encode_text.assert_called_once()

    def test_group_nearby_frames(self):
        """Test grouping nearby frames"""
        frame_store = Mock()
        clip_embedder = Mock()

        engine = FrameSearchEngine(
            frame_vector_store=frame_store,
            clip_embedder=clip_embedder,
        )

        # Create matches with nearby timestamps
        matches = [
            FrameMatch(
                frame_id="f1",
                video_id="v1",
                frame_path="/f1.jpg",
                timestamp=10.0,
                frame_number=100,
                similarity_score=0.9,
            ),
            FrameMatch(
                frame_id="f2",
                video_id="v1",
                frame_path="/f2.jpg",
                timestamp=10.5,  # Within threshold
                frame_number=105,
                similarity_score=0.85,
            ),
            FrameMatch(
                frame_id="f3",
                video_id="v1",
                frame_path="/f3.jpg",
                timestamp=20.0,  # Far away
                frame_number=200,
                similarity_score=0.8,
            ),
        ]

        grouped = engine._group_nearby_frames(matches, threshold=2.0)

        # Should group first two, keep third separate
        assert len(grouped) == 2
        # Should keep highest scoring from each group
        assert grouped[0].similarity_score == 0.9  # Best from first group
        assert grouped[1].similarity_score == 0.8  # Second group

    def test_search_by_example_frame(self):
        """Test search by example frame"""
        frame_store = Mock()
        frame_store.get_frame_at_timestamp.return_value = {
            "frame_id": "source_frame",
            "embedding": [0.1] * 512,
        }
        frame_store.search.return_value = [
            {
                "frame_id": "similar_frame",
                "video_id": "v2",
                "timestamp": 30.0,
                "frame_path": "/similar.jpg",
                "frame_number": 300,
                "similarity": 0.88,
            }
        ]

        engine = FrameSearchEngine(frame_vector_store=frame_store)

        results = engine.search_by_example_frame(
            video_id="v1",
            timestamp=10.0,
        )

        assert isinstance(results, FrameSearchResults)
        frame_store.get_frame_at_timestamp.assert_called_once_with(
            video_id="v1",
            timestamp=10.0,
        )


# ============================================================================
# TranscriptSearchEngine Tests
# ============================================================================


class TestTranscriptSearchEngine:
    """Test TranscriptSearchEngine"""

    def test_init(self):
        """Test initialization"""
        engine = TranscriptSearchEngine()

        assert engine.transcript_vector_store is None
        assert engine.text_embedder is None
        assert engine.default_config is not None

    def test_search_semantic(self):
        """Test semantic transcript search"""
        # Mock transcript store
        transcript_store = Mock()
        transcript_store.search.return_value = [
            {
                "transcript_id": "trans1",
                "video_id": "video1",
                "start_time": 10.0,
                "end_time": 15.0,
                "text": "This is about machine learning",
                "similarity": 0.9,
                "speaker_id": "speaker1",
            }
        ]

        # Mock text embedder
        text_embedder = Mock()
        text_embedder.encode.return_value = [0.2] * 768

        config = TranscriptSearchConfig(
            use_semantic_search=True,
            top_k=5,
        )

        engine = TranscriptSearchEngine(
            transcript_vector_store=transcript_store,
            text_embedder=text_embedder,
            default_config=config,
        )

        results = engine.search("machine learning", config)

        assert isinstance(results, TranscriptSearchResults)
        assert results.search_mode == "semantic"
        assert len(results.matches) > 0
        assert all(isinstance(m, TranscriptMatch) for m in results.matches)

    def test_search_by_speaker(self):
        """Test searching by speaker"""
        transcript_store = Mock()
        transcript_store.search.return_value = []

        text_embedder = Mock()
        text_embedder.encode.return_value = [0.2] * 768

        engine = TranscriptSearchEngine(
            transcript_vector_store=transcript_store,
            text_embedder=text_embedder,
        )

        results = engine.search_by_speaker(
            speaker_id="speaker1",
            query="test",
        )

        assert isinstance(results, TranscriptSearchResults)

    def test_find_phrase(self):
        """Test exact phrase search"""
        engine = TranscriptSearchEngine()

        results = engine.find_phrase(
            phrase="exact phrase",
            exact_match=True,
        )

        assert isinstance(results, TranscriptSearchResults)
        assert results.search_mode == "keyword"


# ============================================================================
# VideoQueryProcessor Tests
# ============================================================================


class TestVideoQueryProcessor:
    """Test VideoQueryProcessor"""

    def test_init(self):
        """Test initialization"""
        processor = VideoQueryProcessor()

        assert processor.semantic_search is None
        assert processor.llm_client is None
        assert processor.default_config is not None

    def test_answer_query_without_llm(self):
        """Test answering query without LLM (fallback)"""
        # Mock search engines
        frame_search = Mock()
        frame_search.search.return_value = FrameSearchResults(
            query="test",
            matches=[],
            total_matches=0,
            config=FrameSearchConfig(),
        )

        transcript_search = Mock()
        transcript_search.search.return_value = TranscriptSearchResults(
            query="test",
            matches=[
                TranscriptMatch(
                    transcript_id="t1",
                    video_id="v1",
                    start_time=10.0,
                    end_time=15.0,
                    timestamp=12.5,
                    text="This is the answer",
                    similarity_score=0.9,
                )
            ],
            total_matches=1,
            search_mode="semantic",
            config=TranscriptSearchConfig(),
        )

        processor = VideoQueryProcessor(
            frame_search=frame_search,
            transcript_search=transcript_search,
            llm_client=None,  # No LLM
        )

        answer = processor.answer_query("What is this about?")

        assert isinstance(answer, QueryAnswer)
        assert answer.query == "What is this about?"
        assert len(answer.answer) > 0
        assert answer.num_sources > 0

    def test_answer_query_with_llm(self):
        """Test answering query with LLM"""
        # Mock LLM client
        llm_client = Mock()
        llm_client.generate.return_value = {
            "text": "This video is about machine learning.",
            "model": "gpt-4",
            "tokens": {"prompt": 100, "completion": 20},
            "cached": False,
        }

        # Mock search
        transcript_search = Mock()
        transcript_search.search.return_value = TranscriptSearchResults(
            query="test",
            matches=[
                TranscriptMatch(
                    transcript_id="t1",
                    video_id="v1",
                    start_time=10.0,
                    end_time=15.0,
                    timestamp=12.5,
                    text="Machine learning context",
                    similarity_score=0.9,
                )
            ],
            total_matches=1,
            search_mode="semantic",
            config=TranscriptSearchConfig(),
        )

        processor = VideoQueryProcessor(
            transcript_search=transcript_search,
            llm_client=llm_client,
        )

        answer = processor.answer_query("What is this about?")

        assert isinstance(answer, QueryAnswer)
        assert "machine learning" in answer.answer.lower()
        assert answer.model_used == "gpt-4"
        llm_client.generate.assert_called_once()

    def test_answer_with_timestamp(self):
        """Test answering with temporal context"""
        transcript_search = Mock()
        transcript_search.search.return_value = TranscriptSearchResults(
            query="test",
            matches=[],
            total_matches=0,
            search_mode="semantic",
            config=TranscriptSearchConfig(),
        )

        processor = VideoQueryProcessor(
            transcript_search=transcript_search,
        )

        answer = processor.answer_with_timestamp(
            query="What happens here?",
            video_id="video1",
            timestamp=60.0,
            context_window=30.0,
        )

        assert isinstance(answer, QueryAnswer)


# ============================================================================
# SearchResultRanker Tests
# ============================================================================


class TestSearchResultRanker:
    """Test SearchResultRanker"""

    def test_init(self):
        """Test initialization"""
        ranker = SearchResultRanker()

        assert ranker.llm_client is None
        assert ranker.default_config is not None

    def test_rank_combined_results(self):
        """Test ranking combined results"""
        # Create mock visual results
        visual_results = [
            Mock(
                video_id="v1",
                timestamp=10.0,
                similarity_score=0.9,
            ),
            Mock(
                video_id="v1",
                timestamp=20.0,
                similarity_score=0.85,
            ),
        ]

        # Create mock text results
        text_results = [
            Mock(
                video_id="v1",
                timestamp=15.0,
                similarity_score=0.88,
            ),
        ]

        config = RankingConfig(
            visual_weight=0.5,
            text_weight=0.5,
            enforce_diversity=False,
        )

        ranker = SearchResultRanker(default_config=config)

        ranked = ranker.rank_combined_results(
            query="test",
            visual_results=visual_results,
            text_results=text_results,
            config=config,
        )

        assert len(ranked) > 0
        # Check that ranks are assigned
        assert all("rank" in r for r in ranked)
        # Check that scores are calculated
        assert all("final_score" in r for r in ranked)

    def test_enforce_diversity(self):
        """Test diversity enforcement"""
        ranker = SearchResultRanker()

        # Create results from same video at nearby timestamps
        results = [
            {
                "video_id": "v1",
                "timestamp": 10.0,
                "final_score": 0.9,
            },
            {
                "video_id": "v1",
                "timestamp": 12.0,  # Too close
                "final_score": 0.85,
            },
            {
                "video_id": "v1",
                "timestamp": 30.0,  # Far enough
                "final_score": 0.8,
            },
        ]

        config = RankingConfig(
            min_temporal_gap=10.0,
            max_same_video=10,
        )

        diverse = ranker._enforce_diversity(results, config)

        # Should filter out second result (too close to first)
        assert len(diverse) == 2
        assert diverse[0]["timestamp"] == 10.0  # Highest score
        assert diverse[1]["timestamp"] == 30.0  # Far enough


# ============================================================================
# Integration Tests
# ============================================================================


class TestSearchSystemIntegration:
    """Integration tests for complete search system"""

    def test_full_search_pipeline(self):
        """Test complete search pipeline"""
        # Mock all components
        frame_store = Mock()
        frame_store.search.return_value = [
            {
                "frame_id": "f1",
                "video_id": "v1",
                "timestamp": 10.0,
                "similarity": 0.9,
                "frame_path": "/f1.jpg",
                "frame_number": 100,
            }
        ]

        transcript_store = Mock()
        transcript_store.search.return_value = [
            {
                "transcript_id": "t1",
                "video_id": "v1",
                "timestamp": 15.0,
                "similarity": 0.85,
                "text": "Test transcript",
                "start_time": 14.0,
                "end_time": 16.0,
            }
        ]

        clip_embedder = Mock()
        clip_embedder.encode_text.return_value = [0.1] * 512

        text_embedder = Mock()
        text_embedder.encode.return_value = [0.2] * 768

        # Create search system
        semantic_search = SemanticVideoSearch(
            frame_vector_store=frame_store,
            transcript_vector_store=transcript_store,
            clip_embedder=clip_embedder,
            text_embedder=text_embedder,
        )

        # Search
        results = semantic_search.search(
            query="test query",
            config=SearchConfig(mode=SearchMode.MULTIMODAL, top_k=10),
        )

        assert isinstance(results, SearchResults)
        assert len(results.results) > 0

    def test_query_with_ranking(self):
        """Test query processing with result ranking"""
        # Mock components
        transcript_search = Mock()
        transcript_search.search.return_value = TranscriptSearchResults(
            query="test",
            matches=[
                TranscriptMatch(
                    transcript_id="t1",
                    video_id="v1",
                    start_time=10.0,
                    end_time=15.0,
                    timestamp=12.5,
                    text="Answer to question",
                    similarity_score=0.9,
                )
            ],
            total_matches=1,
            search_mode="semantic",
            config=TranscriptSearchConfig(),
        )

        llm_client = Mock()
        llm_client.generate.return_value = {
            "text": "The answer is...",
            "model": "test-model",
            "tokens": {},
        }

        # Create query processor
        processor = VideoQueryProcessor(
            transcript_search=transcript_search,
            llm_client=llm_client,
        )

        answer = processor.answer_query("What is the answer?")

        assert isinstance(answer, QueryAnswer)
        assert len(answer.sources) > 0


# ============================================================================
# Convenience Function Tests
# ============================================================================


def test_search_videos_convenience():
    """Test convenience function for video search"""
    frame_store = Mock()
    frame_store.search.return_value = []

    clip_embedder = Mock()
    clip_embedder.encode_text.return_value = [0.1] * 512

    results = search_videos(
        query="test",
        frame_vector_store=frame_store,
        clip_embedder=clip_embedder,
        mode=SearchMode.VISUAL_ONLY,
        top_k=5,
    )

    assert isinstance(results, SearchResults)


def test_search_frames_convenience():
    """Test convenience function for frame search"""
    frame_store = Mock()
    frame_store.search.return_value = []

    clip_embedder = Mock()
    clip_embedder.encode_text.return_value = [0.1] * 512

    results = search_frames(
        query="test",
        frame_vector_store=frame_store,
        clip_embedder=clip_embedder,
        top_k=5,
    )

    assert isinstance(results, FrameSearchResults)


def test_search_transcripts_convenience():
    """Test convenience function for transcript search"""
    transcript_store = Mock()
    transcript_store.search.return_value = []

    text_embedder = Mock()
    text_embedder.encode.return_value = [0.2] * 768

    results = search_transcripts(
        query="test",
        transcript_vector_store=transcript_store,
        text_embedder=text_embedder,
        use_semantic=True,
        top_k=5,
    )

    assert isinstance(results, TranscriptSearchResults)


def test_answer_video_query_convenience():
    """Test convenience function for video query"""
    transcript_search = Mock()
    transcript_search.search.return_value = TranscriptSearchResults(
        query="test",
        matches=[],
        total_matches=0,
        search_mode="semantic",
        config=TranscriptSearchConfig(),
    )

    answer = answer_video_query(
        query="test question",
        transcript_search=transcript_search,
    )

    assert isinstance(answer, QueryAnswer)


def test_rank_search_results_convenience():
    """Test convenience function for result ranking"""
    visual_results = [
        Mock(video_id="v1", timestamp=10.0, similarity_score=0.9)
    ]

    ranked = rank_search_results(
        query="test",
        visual_results=visual_results,
        text_results=[],
    )

    assert isinstance(ranked, list)
    assert len(ranked) > 0
