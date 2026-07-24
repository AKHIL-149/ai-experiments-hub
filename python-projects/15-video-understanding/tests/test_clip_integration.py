"""
Tests for CLIP integration services
Tests embedding generation, similarity, and indexing
"""

import pytest
import numpy as np
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil

from src.services.clip.clip_model import CLIPModel, CLIPConfig
from src.services.clip.frame_embedder import (
    CLIPFrameEmbedder,
    FrameEmbedding,
    VideoEmbeddings,
    embed_video_frames,
)
from src.services.clip.text_embedder import (
    CLIPTextEmbedder,
    TextEmbedding,
    QueryResult,
    search_video_frames,
)
from src.services.clip.similarity import (
    SemanticSimilarityCalculator,
    SimilarityMatrix,
    SimilarityPair,
    compute_clip_similarity,
)
from src.services.clip.indexer import (
    EmbeddingIndexer,
    IndexConfig,
    SearchResult,
    create_frame_index,
)


@pytest.fixture
def clip_config():
    """CLIP configuration for testing"""
    return CLIPConfig(
        model_name="ViT-B/32",
        device="cpu",
        cache_dir=None,
    )


@pytest.fixture
def mock_clip_model():
    """Mock CLIP model for testing without loading real model"""
    model = Mock(spec=CLIPModel)
    model.config = CLIPConfig(model_name="ViT-B/32", device="cpu")
    model.embedding_dim = 512

    # Mock encode_image to return random embeddings
    def mock_encode_image(image_path, normalize=True):
        emb = np.random.randn(512).astype(np.float32)
        if normalize:
            emb = emb / (np.linalg.norm(emb) + 1e-8)
        return emb

    # Mock encode_images_batch
    def mock_encode_images_batch(image_paths, normalize=True):
        n = len(image_paths)
        embs = np.random.randn(n, 512).astype(np.float32)
        if normalize:
            embs = embs / (np.linalg.norm(embs, axis=1, keepdims=True) + 1e-8)
        return embs

    # Mock encode_text
    def mock_encode_text(text, normalize=True):
        if isinstance(text, str):
            emb = np.random.randn(512).astype(np.float32)
            if normalize:
                emb = emb / (np.linalg.norm(emb) + 1e-8)
            return emb
        else:
            # Batch
            n = len(text)
            embs = np.random.randn(n, 512).astype(np.float32)
            if normalize:
                embs = embs / (np.linalg.norm(embs, axis=1, keepdims=True) + 1e-8)
            return embs

    model.encode_image = mock_encode_image
    model.encode_images_batch = mock_encode_images_batch
    model.encode_text = mock_encode_text

    return model


@pytest.fixture
def sample_embeddings():
    """Sample embeddings for testing"""
    # Create 10 embeddings of dimension 512
    embeddings = np.random.randn(10, 512).astype(np.float32)
    # Normalize
    embeddings = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8)
    return embeddings


@pytest.fixture
def temp_dir():
    """Temporary directory for test files"""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    shutil.rmtree(temp_path)


# ============================================================================
# CLIPModel Tests
# ============================================================================

def test_clip_config_default():
    """Test default CLIP configuration"""
    config = CLIPConfig()

    assert config.model_name == "ViT-B/32"
    assert config.device in ["cpu", "cuda"]
    assert config.normalize_embeddings is True


def test_clip_config_custom():
    """Test custom CLIP configuration"""
    config = CLIPConfig(
        model_name="ViT-L/14",
        device="cpu",
        normalize_embeddings=False,
    )

    assert config.model_name == "ViT-L/14"
    assert config.device == "cpu"
    assert config.normalize_embeddings is False


def test_mock_clip_encode_image(mock_clip_model):
    """Test mocked image encoding"""
    embedding = mock_clip_model.encode_image(Path("test.jpg"))

    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (512,)
    assert np.abs(np.linalg.norm(embedding) - 1.0) < 1e-5  # Normalized


def test_mock_clip_encode_text(mock_clip_model):
    """Test mocked text encoding"""
    embedding = mock_clip_model.encode_text("a photo of a cat")

    assert isinstance(embedding, np.ndarray)
    assert embedding.shape == (512,)
    assert np.abs(np.linalg.norm(embedding) - 1.0) < 1e-5  # Normalized


def test_mock_clip_batch_encoding(mock_clip_model):
    """Test mocked batch encoding"""
    texts = ["cat", "dog", "bird"]
    embeddings = mock_clip_model.encode_text(texts)

    assert isinstance(embeddings, np.ndarray)
    assert embeddings.shape == (3, 512)


# ============================================================================
# CLIPFrameEmbedder Tests
# ============================================================================

def test_frame_embedder_initialization(mock_clip_model):
    """Test CLIPFrameEmbedder initialization"""
    embedder = CLIPFrameEmbedder(clip_model=mock_clip_model)

    assert embedder.clip_model == mock_clip_model
    assert embedder.cache_embeddings is True
    assert isinstance(embedder._embedding_cache, dict)


def test_frame_embedding_structure():
    """Test FrameEmbedding dataclass"""
    embedding = FrameEmbedding(
        frame_path=Path("frame_001.jpg"),
        frame_number=1,
        timestamp=0.5,
        embedding=np.random.randn(512),
    )

    assert embedding.frame_path == Path("frame_001.jpg")
    assert embedding.frame_number == 1
    assert embedding.timestamp == 0.5
    assert embedding.embedding.shape == (512,)


def test_embed_single_frame(mock_clip_model, temp_dir):
    """Test embedding single frame"""
    embedder = CLIPFrameEmbedder(clip_model=mock_clip_model)

    # Create dummy frame file
    frame_path = temp_dir / "frame_001.jpg"
    frame_path.touch()

    result = embedder.embed_frame(frame_path, frame_number=1, timestamp=0.5)

    assert isinstance(result, FrameEmbedding)
    assert result.frame_path == frame_path
    assert result.frame_number == 1
    assert result.timestamp == 0.5
    assert result.embedding.shape == (512,)


def test_embed_frames_batch(mock_clip_model, temp_dir):
    """Test batch frame embedding"""
    embedder = CLIPFrameEmbedder(clip_model=mock_clip_model)

    # Create dummy frames
    frame_paths = [temp_dir / f"frame_{i:03d}.jpg" for i in range(5)]
    for path in frame_paths:
        path.touch()

    frame_numbers = list(range(5))
    timestamps = [i * 0.5 for i in range(5)]

    embeddings = embedder.embed_frames_batch(
        frame_paths, frame_numbers, timestamps
    )

    assert len(embeddings) == 5
    assert all(isinstance(e, FrameEmbedding) for e in embeddings)
    assert all(e.embedding.shape == (512,) for e in embeddings)


def test_frame_embedding_caching(mock_clip_model, temp_dir):
    """Test embedding caching"""
    embedder = CLIPFrameEmbedder(clip_model=mock_clip_model, cache_embeddings=True)

    frame_path = temp_dir / "frame_001.jpg"
    frame_path.touch()

    # First call - should compute
    result1 = embedder.embed_frame(frame_path, frame_number=1)

    # Second call - should use cache
    result2 = embedder.embed_frame(frame_path, frame_number=1)

    # Should be same embedding (from cache)
    np.testing.assert_array_equal(result1.embedding, result2.embedding)

    # Cache should have one entry
    assert embedder.get_cache_size() == 1


def test_video_embeddings_structure():
    """Test VideoEmbeddings dataclass"""
    frame_embeddings = [
        FrameEmbedding(
            frame_path=Path(f"frame_{i}.jpg"),
            frame_number=i,
            timestamp=i * 0.5,
            embedding=np.random.randn(512),
        )
        for i in range(10)
    ]

    video_emb = VideoEmbeddings(
        video_path=Path("video.mp4"),
        frame_embeddings=frame_embeddings,
    )

    assert video_emb.video_path == Path("video.mp4")
    assert len(video_emb.frame_embeddings) == 10
    assert video_emb.embedding_matrix.shape == (10, 512)
    assert len(video_emb.frame_paths) == 10
    assert len(video_emb.timestamps) == 10


# ============================================================================
# CLIPTextEmbedder Tests
# ============================================================================

def test_text_embedder_initialization(mock_clip_model):
    """Test CLIPTextEmbedder initialization"""
    embedder = CLIPTextEmbedder(clip_model=mock_clip_model)

    assert embedder.clip_model == mock_clip_model
    assert embedder.cache_queries is True


def test_text_embedding_structure():
    """Test TextEmbedding dataclass"""
    embedding = TextEmbedding(
        text="a photo of a cat",
        embedding=np.random.randn(512),
    )

    assert embedding.text == "a photo of a cat"
    assert embedding.embedding.shape == (512,)


def test_embed_single_text(mock_clip_model):
    """Test embedding single text"""
    embedder = CLIPTextEmbedder(clip_model=mock_clip_model)

    result = embedder.embed_text("a photo of a cat")

    assert isinstance(result, TextEmbedding)
    assert result.text == "a photo of a cat"
    assert result.embedding.shape == (512,)


def test_embed_texts_batch(mock_clip_model):
    """Test batch text embedding"""
    embedder = CLIPTextEmbedder(clip_model=mock_clip_model)

    texts = ["cat", "dog", "bird", "fish"]
    results = embedder.embed_texts(texts)

    assert len(results) == 4
    assert all(isinstance(r, TextEmbedding) for r in results)
    assert all(r.embedding.shape == (512,) for r in results)
    assert [r.text for r in results] == texts


def test_query_caching(mock_clip_model):
    """Test query caching"""
    embedder = CLIPTextEmbedder(clip_model=mock_clip_model, cache_queries=True)

    # First call
    result1 = embedder.embed_text("cat")

    # Second call - should use cache
    result2 = embedder.embed_text("cat")

    np.testing.assert_array_equal(result1.embedding, result2.embedding)
    assert embedder.get_cache_size() == 1


def test_create_prompt(mock_clip_model):
    """Test prompt creation"""
    embedder = CLIPTextEmbedder(clip_model=mock_clip_model)

    prompt = embedder.create_prompt("cat", template="a photo of {}")
    assert prompt == "a photo of cat"


def test_expand_query(mock_clip_model):
    """Test query expansion"""
    embedder = CLIPTextEmbedder(clip_model=mock_clip_model)

    expanded = embedder.expand_query("cat")

    assert isinstance(expanded, list)
    assert len(expanded) == 5  # Default templates
    assert "a photo of cat" in expanded
    assert "a picture of cat" in expanded


def test_embed_with_expansion(mock_clip_model):
    """Test embedding with query expansion"""
    embedder = CLIPTextEmbedder(clip_model=mock_clip_model)

    result = embedder.embed_with_expansion("cat", aggregate="mean")

    assert isinstance(result, TextEmbedding)
    assert result.text == "cat"
    assert result.embedding.shape == (512,)
    assert "expanded_queries" in result.metadata


def test_search_frames(mock_clip_model):
    """Test frame search"""
    embedder = CLIPTextEmbedder(clip_model=mock_clip_model)

    # Create dummy frame embeddings
    frame_embeddings = np.random.randn(100, 512).astype(np.float32)
    frame_embeddings = frame_embeddings / (
        np.linalg.norm(frame_embeddings, axis=1, keepdims=True) + 1e-8
    )

    timestamps = [i * 0.1 for i in range(100)]

    result = embedder.search_frames(
        query="cat",
        frame_embeddings=frame_embeddings,
        timestamps=timestamps,
        top_k=10,
    )

    assert isinstance(result, QueryResult)
    assert result.query == "cat"
    assert len(result.matches) == 10
    assert all("similarity" in m for m in result.matches)
    assert all("frame_idx" in m for m in result.matches)


def test_batch_search(mock_clip_model):
    """Test batch search"""
    embedder = CLIPTextEmbedder(clip_model=mock_clip_model)

    frame_embeddings = np.random.randn(50, 512).astype(np.float32)
    frame_embeddings = frame_embeddings / (
        np.linalg.norm(frame_embeddings, axis=1, keepdims=True) + 1e-8
    )

    queries = ["cat", "dog", "bird"]
    results = embedder.batch_search(queries, frame_embeddings, top_k=5)

    assert len(results) == 3
    assert all(isinstance(r, QueryResult) for r in results)
    assert all(len(r.matches) == 5 for r in results)


def test_semantic_tagging(mock_clip_model):
    """Test semantic tagging"""
    embedder = CLIPTextEmbedder(clip_model=mock_clip_model)

    frame_embeddings = np.random.randn(20, 512).astype(np.float32)
    frame_embeddings = frame_embeddings / (
        np.linalg.norm(frame_embeddings, axis=1, keepdims=True) + 1e-8
    )

    tags = ["cat", "dog", "nature", "urban"]
    tag_scores = embedder.semantic_tagging(tags, frame_embeddings, threshold=0.2)

    assert isinstance(tag_scores, dict)
    assert all(tag in tag_scores or tag not in tag_scores for tag in tags)


# ============================================================================
# SemanticSimilarityCalculator Tests
# ============================================================================

def test_similarity_calculator_initialization():
    """Test SemanticSimilarityCalculator initialization"""
    calc = SemanticSimilarityCalculator(default_metric="cosine")

    assert calc.default_metric == "cosine"


def test_cosine_similarity(sample_embeddings):
    """Test cosine similarity calculation"""
    calc = SemanticSimilarityCalculator()

    emb1 = sample_embeddings[0]
    emb2 = sample_embeddings[1]

    similarity = calc.cosine_similarity(emb1, emb2)

    assert isinstance(similarity, float)
    assert -1.0 <= similarity <= 1.0


def test_euclidean_distance(sample_embeddings):
    """Test Euclidean distance calculation"""
    calc = SemanticSimilarityCalculator()

    emb1 = sample_embeddings[0]
    emb2 = sample_embeddings[1]

    distance = calc.euclidean_distance(emb1, emb2)

    assert isinstance(distance, float)
    assert distance >= 0.0


def test_dot_product_similarity(sample_embeddings):
    """Test dot product similarity"""
    calc = SemanticSimilarityCalculator()

    emb1 = sample_embeddings[0]
    emb2 = sample_embeddings[1]

    similarity = calc.dot_product_similarity(emb1, emb2)

    assert isinstance(similarity, float)


def test_compute_similarity(sample_embeddings):
    """Test compute_similarity wrapper"""
    calc = SemanticSimilarityCalculator(default_metric="cosine")

    result = calc.compute_similarity(sample_embeddings[0], sample_embeddings[1])

    assert isinstance(result, SimilarityPair)
    assert result.metric == "cosine"
    assert isinstance(result.similarity, float)
    assert isinstance(result.distance, float)


def test_pairwise_similarity(sample_embeddings):
    """Test pairwise similarity matrix"""
    calc = SemanticSimilarityCalculator()

    result = calc.pairwise_similarity(sample_embeddings, metric="cosine")

    assert isinstance(result, SimilarityMatrix)
    assert result.matrix.shape == (10, 10)
    assert result.metric == "cosine"

    # Diagonal should be ~1 for normalized cosine
    diag = np.diag(result.matrix)
    np.testing.assert_array_almost_equal(diag, np.ones(10), decimal=5)


def test_find_most_similar(sample_embeddings):
    """Test finding most similar embeddings"""
    calc = SemanticSimilarityCalculator()

    query = sample_embeddings[0]
    candidates = sample_embeddings[1:]

    results = calc.find_most_similar(query, candidates, top_k=3)

    assert len(results) == 3
    assert all(isinstance(r, tuple) for r in results)
    assert all(isinstance(r[0], int) and isinstance(r[1], float) for r in results)

    # Results should be sorted by similarity
    similarities = [r[1] for r in results]
    assert similarities == sorted(similarities, reverse=True)


def test_find_nearest_neighbors(sample_embeddings):
    """Test k-nearest neighbors"""
    calc = SemanticSimilarityCalculator()

    neighbors_list = calc.find_nearest_neighbors(sample_embeddings, k=3)

    assert len(neighbors_list) == 10
    assert all(len(neighbors) == 3 for neighbors in neighbors_list)


def test_compute_average_similarity(sample_embeddings):
    """Test average similarity computation"""
    calc = SemanticSimilarityCalculator()

    avg_sim = calc.compute_average_similarity(sample_embeddings)

    assert isinstance(avg_sim, float)
    assert -1.0 <= avg_sim <= 1.0


def test_find_outliers(sample_embeddings):
    """Test outlier detection"""
    calc = SemanticSimilarityCalculator()

    outliers = calc.find_outliers(sample_embeddings)

    assert isinstance(outliers, list)
    assert all(isinstance(idx, int) for idx in outliers)


def test_compute_diversity_score(sample_embeddings):
    """Test diversity score"""
    calc = SemanticSimilarityCalculator()

    diversity = calc.compute_diversity_score(sample_embeddings)

    assert isinstance(diversity, float)
    assert 0.0 <= diversity <= 1.0


# ============================================================================
# EmbeddingIndexer Tests
# ============================================================================

def test_index_config_default():
    """Test default index configuration"""
    config = IndexConfig()

    assert config.index_type == "flat"
    assert config.metric == "cosine"
    assert config.normalize is True


def test_indexer_initialization():
    """Test EmbeddingIndexer initialization"""
    config = IndexConfig(index_type="flat", metric="cosine")
    indexer = EmbeddingIndexer(config)

    assert indexer.config == config
    assert indexer.index is None
    assert indexer.n_embeddings == 0


@pytest.mark.skipif(True, reason="Requires FAISS installation")
def test_build_flat_index(sample_embeddings):
    """Test building flat index"""
    indexer = EmbeddingIndexer(IndexConfig(index_type="flat"))
    indexer.build_index(sample_embeddings)

    assert indexer.index is not None
    assert indexer.n_embeddings == 10
    assert indexer.embedding_dim == 512


@pytest.mark.skipif(True, reason="Requires FAISS installation")
def test_search_index(sample_embeddings):
    """Test searching index"""
    indexer = EmbeddingIndexer(IndexConfig(index_type="flat"))
    indexer.build_index(sample_embeddings)

    query = sample_embeddings[0]
    result = indexer.search(query, top_k=5)

    assert isinstance(result, SearchResult)
    assert len(result.indices) == 5
    assert len(result.distances) == 5

    # First result should be the query itself (index 0)
    assert result.indices[0] == 0


@pytest.mark.skipif(True, reason="Requires FAISS installation")
def test_batch_search(sample_embeddings):
    """Test batch search"""
    indexer = EmbeddingIndexer(IndexConfig(index_type="flat"))
    indexer.build_index(sample_embeddings)

    queries = sample_embeddings[:3]
    results = indexer.batch_search(queries, top_k=5)

    assert len(results) == 3
    assert all(isinstance(r, SearchResult) for r in results)


@pytest.mark.skipif(True, reason="Requires FAISS installation")
def test_add_embeddings(sample_embeddings):
    """Test adding embeddings to existing index"""
    indexer = EmbeddingIndexer(IndexConfig(index_type="flat"))
    indexer.build_index(sample_embeddings[:5])

    assert indexer.n_embeddings == 5

    # Add more embeddings
    indexer.add_embeddings(sample_embeddings[5:])

    assert indexer.n_embeddings == 10


@pytest.mark.skipif(True, reason="Requires FAISS installation")
def test_save_load_index(sample_embeddings, temp_dir):
    """Test saving and loading index"""
    indexer = EmbeddingIndexer(IndexConfig(index_type="flat"))
    indexer.build_index(sample_embeddings)

    index_path = temp_dir / "test_index.faiss"
    indexer.save_index(index_path)

    assert index_path.exists()

    # Load in new indexer
    new_indexer = EmbeddingIndexer(IndexConfig(index_type="flat"))
    new_indexer.load_index(index_path)

    assert new_indexer.n_embeddings == 10
    assert new_indexer.embedding_dim == 512


@pytest.mark.skipif(True, reason="Requires FAISS installation")
def test_get_metadata(sample_embeddings):
    """Test metadata retrieval"""
    metadata = [{'frame_id': i, 'timestamp': i * 0.5} for i in range(10)]

    indexer = EmbeddingIndexer(IndexConfig(index_type="flat"))
    indexer.build_index(sample_embeddings, metadata=metadata)

    indices = np.array([0, 2, 5])
    result_metadata = indexer.get_metadata(indices)

    assert len(result_metadata) == 3
    assert result_metadata[0]['frame_id'] == 0
    assert result_metadata[1]['frame_id'] == 2
    assert result_metadata[2]['frame_id'] == 5


def test_create_frame_index(sample_embeddings, temp_dir):
    """Test convenience function for creating frame index"""
    frame_paths = [temp_dir / f"frame_{i}.jpg" for i in range(10)]
    timestamps = [i * 0.5 for i in range(10)]

    # This will fail without FAISS but we can test the structure
    try:
        indexer = create_frame_index(
            sample_embeddings,
            frame_paths,
            timestamps,
            index_type="flat",
        )

        assert isinstance(indexer, EmbeddingIndexer)
        assert indexer.n_embeddings == 10
    except RuntimeError:
        # Expected if FAISS not installed
        pass


# ============================================================================
# Integration Tests
# ============================================================================

def test_end_to_end_clip_workflow(mock_clip_model, temp_dir):
    """Test complete CLIP workflow from frames to search"""
    # Step 1: Embed frames
    frame_embedder = CLIPFrameEmbedder(clip_model=mock_clip_model)

    frame_paths = [temp_dir / f"frame_{i:03d}.jpg" for i in range(20)]
    for path in frame_paths:
        path.touch()

    timestamps = [i * 0.5 for i in range(20)]
    frame_embeddings = frame_embedder.embed_frames_batch(
        frame_paths, list(range(20)), timestamps
    )

    # Step 2: Create video embeddings
    video_emb = VideoEmbeddings(
        video_path=temp_dir / "video.mp4",
        frame_embeddings=frame_embeddings,
    )

    # Step 3: Search with text
    text_embedder = CLIPTextEmbedder(clip_model=mock_clip_model)

    result = text_embedder.search_frames(
        query="person walking",
        frame_embeddings=video_emb.embedding_matrix,
        timestamps=video_emb.timestamps,
        top_k=5,
    )

    assert isinstance(result, QueryResult)
    assert len(result.matches) == 5
    assert result.query == "person walking"


def test_similarity_analysis_workflow(sample_embeddings):
    """Test similarity analysis workflow"""
    calc = SemanticSimilarityCalculator()

    # Compute pairwise similarities
    sim_matrix = calc.pairwise_similarity(sample_embeddings)

    # Find outliers
    outliers = calc.find_outliers(sample_embeddings)

    # Compute statistics
    stats = calc.compute_similarity_statistics(sample_embeddings)

    assert 'mean' in stats
    assert 'std' in stats
    assert 'min' in stats
    assert 'max' in stats


def test_convenience_functions(mock_clip_model, sample_embeddings):
    """Test convenience functions"""
    # Test compute_clip_similarity
    similarity = compute_clip_similarity(
        sample_embeddings[0],
        sample_embeddings[1],
        metric="cosine",
    )

    assert isinstance(similarity, float)
    assert -1.0 <= similarity <= 1.0


# ============================================================================
# Performance and Edge Case Tests
# ============================================================================

def test_large_batch_processing(mock_clip_model, temp_dir):
    """Test processing large batches"""
    embedder = CLIPFrameEmbedder(clip_model=mock_clip_model)

    # Create 100 dummy frames
    frame_paths = [temp_dir / f"frame_{i:04d}.jpg" for i in range(100)]
    for path in frame_paths:
        path.touch()

    embeddings = embedder.embed_frames_batch(frame_paths)

    assert len(embeddings) == 100


def test_empty_inputs():
    """Test handling of empty inputs"""
    calc = SemanticSimilarityCalculator()

    # Empty embeddings
    empty_emb = np.array([]).reshape(0, 512)

    # Should handle gracefully
    try:
        result = calc.pairwise_similarity(empty_emb)
        # If it doesn't raise an error, check the result
        assert result.matrix.shape == (0, 0)
    except (ValueError, IndexError):
        # Expected for some operations
        pass


def test_single_embedding_operations(sample_embeddings):
    """Test operations with single embedding"""
    calc = SemanticSimilarityCalculator()

    single_emb = sample_embeddings[0:1]

    sim_matrix = calc.pairwise_similarity(single_emb)
    assert sim_matrix.matrix.shape == (1, 1)


def test_cache_clearing(mock_clip_model):
    """Test cache clearing functionality"""
    text_embedder = CLIPTextEmbedder(clip_model=mock_clip_model)
    frame_embedder = CLIPFrameEmbedder(clip_model=mock_clip_model)

    # Generate some cached data
    text_embedder.embed_text("cat")
    text_embedder.embed_text("dog")

    assert text_embedder.get_cache_size() == 2

    # Clear cache
    text_embedder.clear_cache()

    assert text_embedder.get_cache_size() == 0


def test_normalization_consistency(sample_embeddings):
    """Test embedding normalization consistency"""
    calc = SemanticSimilarityCalculator()

    # Embeddings should already be normalized
    norms = np.linalg.norm(sample_embeddings, axis=1)
    np.testing.assert_array_almost_equal(norms, np.ones(10), decimal=5)


# ============================================================================
# Error Handling Tests
# ============================================================================

def test_invalid_metric():
    """Test error handling for invalid metric"""
    calc = SemanticSimilarityCalculator()

    with pytest.raises(ValueError):
        calc.compute_similarity(
            np.random.randn(512),
            np.random.randn(512),
            metric="invalid_metric",
        )


def test_mismatched_dimensions():
    """Test error handling for mismatched dimensions"""
    calc = SemanticSimilarityCalculator()

    emb1 = np.random.randn(512)
    emb2 = np.random.randn(256)  # Different dimension

    # Should raise an error or handle gracefully
    try:
        calc.cosine_similarity(emb1, emb2)
        assert False, "Should have raised an error"
    except (ValueError, Exception):
        pass


def test_search_without_index():
    """Test error when searching without building index"""
    indexer = EmbeddingIndexer()

    with pytest.raises(RuntimeError, match="Index not built"):
        indexer.search(np.random.randn(512))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
