"""
Tests for vector storage services
Tests embedding insertion, retrieval, and multi-modal search
"""

import pytest
import numpy as np
from pathlib import Path
import tempfile
import shutil

from src.services.vector.frame_store import (
    FrameVectorStore,
    FrameSearchResult,
    add_frames_to_vector_store,
)
from src.services.vector.transcript_store import (
    TranscriptVectorStore,
    TranscriptSearchResult,
    add_transcript_to_vector_store,
)
from src.services.vector.scene_store import (
    SceneVectorStore,
    SceneSearchResult,
    add_scenes_to_vector_store,
)
from src.services.vector.retriever import (
    MultiModalVectorRetriever,
    MultiModalResult,
    RankedResult,
)


@pytest.fixture
def temp_chroma_dir():
    """Temporary directory for ChromaDB"""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    shutil.rmtree(temp_path)


@pytest.fixture
def sample_frame_embeddings():
    """Sample frame embeddings for testing"""
    n_frames = 20
    dim = 512
    embeddings = np.random.randn(n_frames, dim).astype(np.float32)
    # Normalize
    embeddings = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8)
    return embeddings


@pytest.fixture
def sample_transcript_embeddings():
    """Sample transcript embeddings for testing"""
    n_segments = 15
    dim = 512
    embeddings = np.random.randn(n_segments, dim).astype(np.float32)
    # Normalize
    embeddings = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8)
    return embeddings


@pytest.fixture
def sample_scene_embeddings():
    """Sample scene embeddings for testing"""
    n_scenes = 10
    dim = 512
    embeddings = np.random.randn(n_scenes, dim).astype(np.float32)
    # Normalize
    embeddings = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8)
    return embeddings


# ============================================================================
# FrameVectorStore Tests
# ============================================================================

@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_frame_store_initialization(temp_chroma_dir):
    """Test FrameVectorStore initialization"""
    store = FrameVectorStore(persist_directory=temp_chroma_dir)

    assert store.store is not None
    assert store.store.frames_collection is not None


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_add_video_frames(temp_chroma_dir, sample_frame_embeddings):
    """Test adding frame embeddings"""
    store = FrameVectorStore(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"
    frame_numbers = list(range(20))
    timestamps = [i * 0.5 for i in range(20)]
    frame_paths = [f"frame_{i:03d}.jpg" for i in range(20)]

    store.add_video_frames(
        video_id=video_id,
        frame_embeddings=sample_frame_embeddings,
        frame_numbers=frame_numbers,
        timestamps=timestamps,
        frame_paths=frame_paths,
    )

    # Verify count
    count = store.count_video_frames(video_id)
    assert count == 20


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_search_frames(temp_chroma_dir, sample_frame_embeddings):
    """Test frame search"""
    store = FrameVectorStore(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"
    frame_numbers = list(range(20))
    timestamps = [i * 0.5 for i in range(20)]

    store.add_video_frames(
        video_id=video_id,
        frame_embeddings=sample_frame_embeddings,
        frame_numbers=frame_numbers,
        timestamps=timestamps,
    )

    # Search with first embedding
    query_embedding = sample_frame_embeddings[0]

    result = store.search_frames(
        query_embedding=query_embedding,
        n_results=5,
        video_id=video_id,
    )

    assert isinstance(result, FrameSearchResult)
    assert result.video_id == video_id
    assert len(result.frame_ids) == 5
    assert len(result.similarities) == 5

    # Top result should be the query itself (frame 0)
    assert result.frame_numbers[0] == 0


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_get_frames_in_range(temp_chroma_dir, sample_frame_embeddings):
    """Test getting frames in time range"""
    store = FrameVectorStore(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"
    frame_numbers = list(range(20))
    timestamps = [i * 0.5 for i in range(20)]

    store.add_video_frames(
        video_id=video_id,
        frame_embeddings=sample_frame_embeddings,
        frame_numbers=frame_numbers,
        timestamps=timestamps,
    )

    # Get frames between 2.0 and 5.0 seconds
    frames = store.get_frames_in_range(
        video_id=video_id,
        start_time=2.0,
        end_time=5.0,
    )

    assert "ids" in frames
    # Should have frames 4-10 (timestamps 2.0-5.0)
    assert len(frames["ids"]) >= 6


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_find_similar_frames(temp_chroma_dir, sample_frame_embeddings):
    """Test finding similar frames"""
    store = FrameVectorStore(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"
    frame_numbers = list(range(20))
    timestamps = [i * 0.5 for i in range(20)]

    store.add_video_frames(
        video_id=video_id,
        frame_embeddings=sample_frame_embeddings,
        frame_numbers=frame_numbers,
        timestamps=timestamps,
    )

    # Find similar to frame 5
    result = store.find_similar_frames(
        video_id=video_id,
        frame_number=5,
        n_results=5,
    )

    assert isinstance(result, FrameSearchResult)
    assert len(result.frame_ids) <= 6  # 5 + source frame


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_frame_statistics(temp_chroma_dir, sample_frame_embeddings):
    """Test frame statistics"""
    store = FrameVectorStore(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"
    frame_numbers = list(range(20))
    timestamps = [i * 0.5 for i in range(20)]
    scene_ids = [i // 5 for i in range(20)]  # 4 scenes

    store.add_video_frames(
        video_id=video_id,
        frame_embeddings=sample_frame_embeddings,
        frame_numbers=frame_numbers,
        timestamps=timestamps,
        scene_ids=scene_ids,
    )

    stats = store.get_frame_statistics(video_id)

    assert stats["count"] == 20
    assert stats["min_timestamp"] == 0.0
    assert stats["max_timestamp"] == 9.5
    assert stats["unique_scenes"] == 4


# ============================================================================
# TranscriptVectorStore Tests
# ============================================================================

@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_transcript_store_initialization(temp_chroma_dir):
    """Test TranscriptVectorStore initialization"""
    store = TranscriptVectorStore(persist_directory=temp_chroma_dir)

    assert store.store is not None
    assert store.store.transcripts_collection is not None


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_add_video_transcript(temp_chroma_dir, sample_transcript_embeddings):
    """Test adding transcript embeddings"""
    store = TranscriptVectorStore(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"
    segment_ids = [f"seg_{i:03d}" for i in range(15)]
    texts = [f"This is segment {i}" for i in range(15)]
    start_times = [i * 2.0 for i in range(15)]
    end_times = [(i + 1) * 2.0 for i in range(15)]
    speakers = ["Speaker_A" if i % 2 == 0 else "Speaker_B" for i in range(15)]

    store.add_video_transcript(
        video_id=video_id,
        transcript_embeddings=sample_transcript_embeddings,
        segment_ids=segment_ids,
        texts=texts,
        start_times=start_times,
        end_times=end_times,
        speakers=speakers,
    )

    # Verify count
    count = store.count_video_segments(video_id)
    assert count == 15


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_search_transcripts(temp_chroma_dir, sample_transcript_embeddings):
    """Test transcript search"""
    store = TranscriptVectorStore(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"
    segment_ids = [f"seg_{i:03d}" for i in range(15)]
    texts = [f"This is segment {i}" for i in range(15)]
    start_times = [i * 2.0 for i in range(15)]
    end_times = [(i + 1) * 2.0 for i in range(15)]

    store.add_video_transcript(
        video_id=video_id,
        transcript_embeddings=sample_transcript_embeddings,
        segment_ids=segment_ids,
        texts=texts,
        start_times=start_times,
        end_times=end_times,
    )

    # Search with first embedding
    query_embedding = sample_transcript_embeddings[0]

    result = store.search_transcripts(
        query_embedding=query_embedding,
        n_results=5,
        video_id=video_id,
    )

    assert isinstance(result, TranscriptSearchResult)
    assert result.video_id == video_id
    assert len(result.segment_ids) == 5
    assert len(result.texts) == 5


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_get_full_transcript(temp_chroma_dir, sample_transcript_embeddings):
    """Test getting full transcript"""
    store = TranscriptVectorStore(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"
    segment_ids = [f"seg_{i:03d}" for i in range(15)]
    texts = [f"Segment {i}" for i in range(15)]
    start_times = [i * 2.0 for i in range(15)]
    end_times = [(i + 1) * 2.0 for i in range(15)]

    store.add_video_transcript(
        video_id=video_id,
        transcript_embeddings=sample_transcript_embeddings,
        segment_ids=segment_ids,
        texts=texts,
        start_times=start_times,
        end_times=end_times,
    )

    transcript = store.get_full_transcript(video_id, sort_by_time=True)

    assert len(transcript) == 15
    # Check sorted by time
    for i in range(len(transcript) - 1):
        assert transcript[i]["start_time"] <= transcript[i + 1]["start_time"]


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_get_speaker_segments(temp_chroma_dir, sample_transcript_embeddings):
    """Test getting speaker segments"""
    store = TranscriptVectorStore(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"
    segment_ids = [f"seg_{i:03d}" for i in range(15)]
    texts = [f"Segment {i}" for i in range(15)]
    start_times = [i * 2.0 for i in range(15)]
    end_times = [(i + 1) * 2.0 for i in range(15)]
    speakers = ["Speaker_A" if i % 2 == 0 else "Speaker_B" for i in range(15)]

    store.add_video_transcript(
        video_id=video_id,
        transcript_embeddings=sample_transcript_embeddings,
        segment_ids=segment_ids,
        texts=texts,
        start_times=start_times,
        end_times=end_times,
        speakers=speakers,
    )

    speaker_a_segments = store.get_speaker_segments(video_id, "Speaker_A")

    # Should have 8 segments (0, 2, 4, 6, 8, 10, 12, 14)
    assert len(speaker_a_segments["ids"]) == 8


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_transcript_statistics(temp_chroma_dir, sample_transcript_embeddings):
    """Test transcript statistics"""
    store = TranscriptVectorStore(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"
    segment_ids = [f"seg_{i:03d}" for i in range(15)]
    texts = [f"Segment {i}" for i in range(15)]
    start_times = [i * 2.0 for i in range(15)]
    end_times = [(i + 1) * 2.0 for i in range(15)]
    speakers = ["Speaker_A" if i % 2 == 0 else "Speaker_B" for i in range(15)]

    store.add_video_transcript(
        video_id=video_id,
        transcript_embeddings=sample_transcript_embeddings,
        segment_ids=segment_ids,
        texts=texts,
        start_times=start_times,
        end_times=end_times,
        speakers=speakers,
    )

    stats = store.get_transcript_statistics(video_id)

    assert stats["count"] == 15
    assert stats["unique_speakers"] == 2
    assert stats["min_start_time"] == 0.0
    assert stats["max_end_time"] == 30.0


# ============================================================================
# SceneVectorStore Tests
# ============================================================================

@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_scene_store_initialization(temp_chroma_dir):
    """Test SceneVectorStore initialization"""
    store = SceneVectorStore(persist_directory=temp_chroma_dir)

    assert store.store is not None
    assert store.store.scenes_collection is not None


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_add_video_scenes(temp_chroma_dir, sample_scene_embeddings):
    """Test adding scene embeddings"""
    store = SceneVectorStore(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"
    scene_numbers = list(range(10))
    start_times = [i * 3.0 for i in range(10)]
    end_times = [(i + 1) * 3.0 for i in range(10)]
    descriptions = [f"Scene {i}: test description" for i in range(10)]
    scene_types = ["static" if i % 2 == 0 else "motion" for i in range(10)]

    store.add_video_scenes(
        video_id=video_id,
        scene_embeddings=sample_scene_embeddings,
        scene_numbers=scene_numbers,
        start_times=start_times,
        end_times=end_times,
        descriptions=descriptions,
        scene_types=scene_types,
    )

    # Verify count
    count = store.count_video_scenes(video_id)
    assert count == 10


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_search_scenes(temp_chroma_dir, sample_scene_embeddings):
    """Test scene search"""
    store = SceneVectorStore(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"
    scene_numbers = list(range(10))
    start_times = [i * 3.0 for i in range(10)]
    end_times = [(i + 1) * 3.0 for i in range(10)]

    store.add_video_scenes(
        video_id=video_id,
        scene_embeddings=sample_scene_embeddings,
        scene_numbers=scene_numbers,
        start_times=start_times,
        end_times=end_times,
    )

    # Search with first embedding
    query_embedding = sample_scene_embeddings[0]

    result = store.search_scenes(
        query_embedding=query_embedding,
        n_results=5,
        video_id=video_id,
    )

    assert isinstance(result, SceneSearchResult)
    assert result.video_id == video_id
    assert len(result.scene_ids) == 5


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_create_aggregated_scene_embedding(temp_chroma_dir, sample_frame_embeddings):
    """Test scene embedding aggregation"""
    store = SceneVectorStore(persist_directory=temp_chroma_dir)

    # Use first 5 frames for a scene
    frame_embeddings = sample_frame_embeddings[:5]

    # Aggregate
    scene_embedding = store.create_aggregated_scene_embedding(frame_embeddings)

    assert scene_embedding.shape == (512,)
    # Should be normalized
    assert np.abs(np.linalg.norm(scene_embedding) - 1.0) < 1e-5


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_get_scenes_by_type(temp_chroma_dir, sample_scene_embeddings):
    """Test getting scenes by type"""
    store = SceneVectorStore(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"
    scene_numbers = list(range(10))
    start_times = [i * 3.0 for i in range(10)]
    end_times = [(i + 1) * 3.0 for i in range(10)]
    scene_types = ["static" if i % 2 == 0 else "motion" for i in range(10)]

    store.add_video_scenes(
        video_id=video_id,
        scene_embeddings=sample_scene_embeddings,
        scene_numbers=scene_numbers,
        start_times=start_times,
        end_times=end_times,
        scene_types=scene_types,
    )

    static_scenes = store.get_scenes_by_type(video_id, "static")

    # Should have 5 static scenes (0, 2, 4, 6, 8)
    assert len(static_scenes["ids"]) == 5


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_scene_statistics(temp_chroma_dir, sample_scene_embeddings):
    """Test scene statistics"""
    store = SceneVectorStore(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"
    scene_numbers = list(range(10))
    start_times = [i * 3.0 for i in range(10)]
    end_times = [(i + 1) * 3.0 for i in range(10)]
    scene_types = ["static" if i % 2 == 0 else "motion" for i in range(10)]

    store.add_video_scenes(
        video_id=video_id,
        scene_embeddings=sample_scene_embeddings,
        scene_numbers=scene_numbers,
        start_times=start_times,
        end_times=end_times,
        scene_types=scene_types,
    )

    stats = store.get_scene_statistics(video_id)

    assert stats["count"] == 10
    assert stats["total_duration"] == 30.0
    assert stats["avg_duration"] == 3.0
    assert "scene_type_distribution" in stats


# ============================================================================
# MultiModalVectorRetriever Tests
# ============================================================================

@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_retriever_initialization(temp_chroma_dir):
    """Test MultiModalVectorRetriever initialization"""
    retriever = MultiModalVectorRetriever(persist_directory=temp_chroma_dir)

    assert retriever.frame_store is not None
    assert retriever.transcript_store is not None
    assert retriever.scene_store is not None


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_search_all_modalities(
    temp_chroma_dir,
    sample_frame_embeddings,
    sample_transcript_embeddings,
    sample_scene_embeddings,
):
    """Test searching across all modalities"""
    retriever = MultiModalVectorRetriever(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"

    # Add frames
    retriever.frame_store.add_video_frames(
        video_id=video_id,
        frame_embeddings=sample_frame_embeddings,
        frame_numbers=list(range(20)),
        timestamps=[i * 0.5 for i in range(20)],
    )

    # Add transcript
    retriever.transcript_store.add_video_transcript(
        video_id=video_id,
        transcript_embeddings=sample_transcript_embeddings,
        segment_ids=[f"seg_{i}" for i in range(15)],
        texts=[f"Segment {i}" for i in range(15)],
        start_times=[i * 2.0 for i in range(15)],
        end_times=[(i + 1) * 2.0 for i in range(15)],
    )

    # Add scenes
    retriever.scene_store.add_video_scenes(
        video_id=video_id,
        scene_embeddings=sample_scene_embeddings,
        scene_numbers=list(range(10)),
        start_times=[i * 3.0 for i in range(10)],
        end_times=[(i + 1) * 3.0 for i in range(10)],
    )

    # Search all
    query_embedding = sample_frame_embeddings[0]

    results = retriever.search_all_modalities(
        query_embedding=query_embedding,
        n_results_per_modality=5,
        video_id=video_id,
    )

    assert "frames" in results
    assert "transcripts" in results
    assert "scenes" in results


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_hybrid_search(
    temp_chroma_dir,
    sample_frame_embeddings,
    sample_transcript_embeddings,
):
    """Test hybrid search"""
    retriever = MultiModalVectorRetriever(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"

    # Add frames
    retriever.frame_store.add_video_frames(
        video_id=video_id,
        frame_embeddings=sample_frame_embeddings,
        frame_numbers=list(range(20)),
        timestamps=[i * 0.5 for i in range(20)],
    )

    # Add transcript
    retriever.transcript_store.add_video_transcript(
        video_id=video_id,
        transcript_embeddings=sample_transcript_embeddings,
        segment_ids=[f"seg_{i}" for i in range(15)],
        texts=[f"Segment {i}" for i in range(15)],
        start_times=[i * 2.0 for i in range(15)],
        end_times=[(i + 1) * 2.0 for i in range(15)],
    )

    # Hybrid search
    result = retriever.hybrid_search(
        visual_embedding=sample_frame_embeddings[0],
        text_embedding=sample_transcript_embeddings[0],
        n_results=10,
        video_id=video_id,
        fusion_method="rrf",
    )

    assert isinstance(result, MultiModalResult)
    assert result.video_id == video_id
    assert len(result.items) <= 10


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_get_comprehensive_context(
    temp_chroma_dir,
    sample_frame_embeddings,
    sample_transcript_embeddings,
    sample_scene_embeddings,
):
    """Test getting comprehensive context"""
    retriever = MultiModalVectorRetriever(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"

    # Add all data
    retriever.frame_store.add_video_frames(
        video_id=video_id,
        frame_embeddings=sample_frame_embeddings,
        frame_numbers=list(range(20)),
        timestamps=[i * 0.5 for i in range(20)],
    )

    retriever.transcript_store.add_video_transcript(
        video_id=video_id,
        transcript_embeddings=sample_transcript_embeddings,
        segment_ids=[f"seg_{i}" for i in range(15)],
        texts=[f"Segment {i}" for i in range(15)],
        start_times=[i * 2.0 for i in range(15)],
        end_times=[(i + 1) * 2.0 for i in range(15)],
    )

    retriever.scene_store.add_video_scenes(
        video_id=video_id,
        scene_embeddings=sample_scene_embeddings,
        scene_numbers=list(range(10)),
        start_times=[i * 3.0 for i in range(10)],
        end_times=[(i + 1) * 3.0 for i in range(10)],
    )

    # Get context around timestamp 5.0
    context = retriever.get_comprehensive_context(
        video_id=video_id,
        timestamp=5.0,
        context_window=6.0,
    )

    assert context["video_id"] == video_id
    assert context["timestamp"] == 5.0
    assert "frames" in context
    assert "transcripts" in context
    assert "scenes" in context


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_delete_all_video_data(temp_chroma_dir, sample_frame_embeddings):
    """Test deleting all video data"""
    retriever = MultiModalVectorRetriever(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"

    # Add frames
    retriever.frame_store.add_video_frames(
        video_id=video_id,
        frame_embeddings=sample_frame_embeddings,
        frame_numbers=list(range(20)),
        timestamps=[i * 0.5 for i in range(20)],
    )

    # Verify added
    count = retriever.frame_store.count_video_frames(video_id)
    assert count == 20

    # Delete all
    retriever.delete_all_video_data(video_id)

    # Verify deleted
    count_after = retriever.frame_store.count_video_frames(video_id)
    assert count_after == 0


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_get_video_statistics(
    temp_chroma_dir,
    sample_frame_embeddings,
    sample_transcript_embeddings,
    sample_scene_embeddings,
):
    """Test getting video statistics"""
    retriever = MultiModalVectorRetriever(persist_directory=temp_chroma_dir)

    video_id = "test_video_001"

    # Add all data
    retriever.frame_store.add_video_frames(
        video_id=video_id,
        frame_embeddings=sample_frame_embeddings,
        frame_numbers=list(range(20)),
        timestamps=[i * 0.5 for i in range(20)],
    )

    retriever.transcript_store.add_video_transcript(
        video_id=video_id,
        transcript_embeddings=sample_transcript_embeddings,
        segment_ids=[f"seg_{i}" for i in range(15)],
        texts=[f"Segment {i}" for i in range(15)],
        start_times=[i * 2.0 for i in range(15)],
        end_times=[(i + 1) * 2.0 for i in range(15)],
    )

    retriever.scene_store.add_video_scenes(
        video_id=video_id,
        scene_embeddings=sample_scene_embeddings,
        scene_numbers=list(range(10)),
        start_times=[i * 3.0 for i in range(10)],
        end_times=[(i + 1) * 3.0 for i in range(10)],
    )

    # Get stats
    stats = retriever.get_video_statistics(video_id)

    assert stats["video_id"] == video_id
    assert stats["frames"]["count"] == 20
    assert stats["transcripts"]["count"] == 15
    assert stats["scenes"]["count"] == 10


# ============================================================================
# Convenience Functions Tests
# ============================================================================

@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_add_frames_to_vector_store_convenience(
    temp_chroma_dir, sample_frame_embeddings
):
    """Test convenience function for adding frames"""
    video_id = "test_video_001"

    store = add_frames_to_vector_store(
        video_id=video_id,
        frame_embeddings=sample_frame_embeddings,
        frame_numbers=list(range(20)),
        timestamps=[i * 0.5 for i in range(20)],
        persist_directory=temp_chroma_dir,
    )

    assert isinstance(store, FrameVectorStore)
    count = store.count_video_frames(video_id)
    assert count == 20


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_add_transcript_to_vector_store_convenience(
    temp_chroma_dir, sample_transcript_embeddings
):
    """Test convenience function for adding transcript"""
    video_id = "test_video_001"

    store = add_transcript_to_vector_store(
        video_id=video_id,
        transcript_embeddings=sample_transcript_embeddings,
        segment_ids=[f"seg_{i}" for i in range(15)],
        texts=[f"Segment {i}" for i in range(15)],
        start_times=[i * 2.0 for i in range(15)],
        end_times=[(i + 1) * 2.0 for i in range(15)],
        persist_directory=temp_chroma_dir,
    )

    assert isinstance(store, TranscriptVectorStore)
    count = store.count_video_segments(video_id)
    assert count == 15


@pytest.mark.skipif(True, reason="Requires ChromaDB installation")
def test_add_scenes_to_vector_store_convenience(
    temp_chroma_dir, sample_scene_embeddings
):
    """Test convenience function for adding scenes"""
    video_id = "test_video_001"

    store = add_scenes_to_vector_store(
        video_id=video_id,
        scene_embeddings=sample_scene_embeddings,
        scene_numbers=list(range(10)),
        start_times=[i * 3.0 for i in range(10)],
        end_times=[(i + 1) * 3.0 for i in range(10)],
        persist_directory=temp_chroma_dir,
    )

    assert isinstance(store, SceneVectorStore)
    count = store.count_video_scenes(video_id)
    assert count == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
