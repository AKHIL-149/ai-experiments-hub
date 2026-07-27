"""
Tests for multi-modal fusion services
Test temporal alignment, fusion quality, and search performance
"""

import pytest
import numpy as np
from datetime import datetime

from src.services.fusion.temporal_aligner import (
    TemporalAligner,
    AlignedSegment,
    align_transcript_with_scenes,
)
from src.services.fusion.visual_audio_fuser import (
    VisualAudioFuser,
    FusionWeights,
    fuse_visual_audio_context,
)
from src.services.fusion.context_aggregator import (
    ContextAggregator,
    aggregate_scene_context,
)
from src.services.fusion.timeline_builder import (
    TimelineBuilder,
    build_video_timeline,
)
from src.services.fusion.scene_enricher import (
    SceneEnricher,
    enrich_scene,
)
from src.services.fusion.multimodal_embedder import (
    MultiModalEmbedder,
    EmbeddingFusionConfig,
    FusionStrategy,
    fuse_multimodal_embeddings,
)
from src.services.fusion.contextual_search import (
    ContextualSearchEngine,
    SearchQuery,
    SearchMode,
    ReRankingMethod,
    search_contextual,
)


# Fixtures

@pytest.fixture
def sample_scenes():
    """Sample scenes for testing"""
    return [
        {
            "scene_number": 1,
            "start_time": 0.0,
            "end_time": 10.0,
            "scene_type": "static",
        },
        {
            "scene_number": 2,
            "start_time": 10.0,
            "end_time": 25.0,
            "scene_type": "motion",
        },
        {
            "scene_number": 3,
            "start_time": 25.0,
            "end_time": 35.0,
            "scene_type": "dialogue",
        },
    ]


@pytest.fixture
def sample_transcript_segments():
    """Sample transcript segments"""
    return [
        {
            "start_time": 2.0,
            "end_time": 8.0,
            "text": "Hello, welcome to this video.",
            "speaker": "Speaker 1",
        },
        {
            "start_time": 12.0,
            "end_time": 20.0,
            "text": "Today we will discuss machine learning.",
            "speaker": "Speaker 1",
        },
        {
            "start_time": 27.0,
            "end_time": 33.0,
            "text": "Let's start with the basics.",
            "speaker": "Speaker 2",
        },
    ]


@pytest.fixture
def sample_visual_context():
    """Sample visual analysis context"""
    return {
        "keyframe_indices": [0, 5, 10],
        "features": np.random.rand(512).astype(np.float32),
        "embedding": np.random.rand(512).astype(np.float32),
        "description": "A person sitting at a desk",
        "objects": ["person", "desk", "computer"],
        "actions": ["sitting", "typing"],
    }


@pytest.fixture
def sample_audio_context():
    """Sample audio/transcript context"""
    return {
        "text": "Hello, welcome to this video.",
        "speakers": ["Speaker 1"],
        "embedding": np.random.rand(512).astype(np.float32),
        "features": {
            "mfcc": np.random.rand(20),
            "energy": 0.8,
        },
    }


# Temporal Aligner Tests

def test_temporal_aligner_initialization():
    """Test TemporalAligner initialization"""
    aligner = TemporalAligner()
    assert aligner is not None
    assert aligner.drift_threshold > 0


def test_align_transcript_with_scenes(sample_scenes, sample_transcript_segments):
    """Test aligning transcript with scenes"""
    aligner = TemporalAligner()

    result = aligner.align_transcript_with_scenes(
        video_id="test_video",
        scenes=sample_scenes,
        transcript_segments=sample_transcript_segments,
    )

    assert result is not None
    assert result.video_id == "test_video"
    assert len(result.aligned_segments) > 0

    # Check alignment
    for aligned in result.aligned_segments:
        assert aligned.scene_id >= 0
        assert len(aligned.transcript_segments) >= 0


def test_temporal_aligner_drift_detection(sample_scenes, sample_transcript_segments):
    """Test drift detection"""
    aligner = TemporalAligner(drift_threshold=0.5)

    # Introduce drift by offsetting transcript
    drifted_segments = [
        {**seg, "start_time": seg["start_time"] + 2.0, "end_time": seg["end_time"] + 2.0}
        for seg in sample_transcript_segments
    ]

    result = aligner.align_transcript_with_scenes(
        video_id="test_video",
        scenes=sample_scenes,
        transcript_segments=drifted_segments,
    )

    assert result.drift_detected
    assert abs(result.drift_amount) > 0


def test_temporal_aligner_convenience_function(sample_scenes, sample_transcript_segments):
    """Test convenience function"""
    result = align_transcript_with_scenes(
        video_id="test_video",
        scenes=sample_scenes,
        transcript_segments=sample_transcript_segments,
    )

    assert result is not None
    assert len(result.aligned_segments) > 0


# Visual-Audio Fuser Tests

def test_visual_audio_fuser_initialization():
    """Test VisualAudioFuser initialization"""
    fuser = VisualAudioFuser()
    assert fuser is not None
    assert fuser.default_weights is not None


def test_fusion_weights_normalization():
    """Test FusionWeights normalization"""
    weights = FusionWeights(visual=0.6, audio=0.3, text=0.3)
    weights.normalize()

    total = weights.visual + weights.audio + weights.text
    assert abs(total - 1.0) < 1e-6


def test_fuse_scene(sample_scenes, sample_visual_context, sample_audio_context):
    """Test fusing scene"""
    fuser = VisualAudioFuser()

    fused = fuser.fuse_scene(
        scene_data=sample_scenes[0],
        visual_context=sample_visual_context,
        audio_context=sample_audio_context,
    )

    assert fused is not None
    assert fused.scene_id == 1
    assert fused.fused_embedding is not None
    assert fused.unified_description is not None
    assert fused.importance_score >= 0.0


def test_fuse_scenes_batch(sample_scenes, sample_visual_context, sample_audio_context):
    """Test batch fusion"""
    fuser = VisualAudioFuser()

    visual_contexts = [sample_visual_context] * len(sample_scenes)
    audio_contexts = [sample_audio_context] * len(sample_scenes)

    fused_scenes = fuser.fuse_scenes_batch(
        scenes_data=sample_scenes,
        visual_contexts=visual_contexts,
        audio_contexts=audio_contexts,
    )

    assert len(fused_scenes) == len(sample_scenes)
    for fused in fused_scenes:
        assert fused.fused_embedding is not None


def test_adaptive_weight_adjustment(sample_visual_context, sample_audio_context):
    """Test adaptive weight adjustment"""
    fuser = VisualAudioFuser()

    weights = fuser.adaptive_weight_adjustment(
        visual_context=sample_visual_context,
        audio_context=sample_audio_context,
    )

    assert weights is not None
    total = weights.visual + weights.audio + weights.text
    assert abs(total - 1.0) < 1e-6


def test_visual_audio_fuser_convenience_function(sample_scenes, sample_visual_context, sample_audio_context):
    """Test convenience function"""
    fused = fuse_visual_audio_context(
        scene_data=sample_scenes[0],
        visual_context=sample_visual_context,
        audio_context=sample_audio_context,
    )

    assert fused is not None
    assert fused.scene_id == 1


# Context Aggregator Tests

def test_context_aggregator_initialization():
    """Test ContextAggregator initialization"""
    aggregator = ContextAggregator()
    assert aggregator is not None


def test_aggregate_scene_context(sample_scenes):
    """Test aggregating scene context"""
    aggregator = ContextAggregator()

    frames = [
        {"timestamp": 2.0, "frame_number": 0},
        {"timestamp": 5.0, "frame_number": 1},
    ]

    transcript_segments = [
        {"start_time": 2.0, "end_time": 8.0, "text": "Hello", "speaker": "Speaker 1"},
    ]

    visual_analysis = {
        "objects": ["person", "desk"],
        "actions": ["sitting"],
        "faces": [{"confidence": 0.9}],
        "text_regions": ["Title"],
    }

    context = aggregator.aggregate_scene_context(
        scene_data=sample_scenes[0],
        frames=frames,
        transcript_segments=transcript_segments,
        visual_analysis=visual_analysis,
    )

    assert context is not None
    assert context.scene_id == 1
    assert context.num_frames == 2
    assert len(context.detected_objects) > 0
    assert len(context.speakers) > 0


def test_aggregate_video_context(sample_scenes):
    """Test aggregating video context"""
    aggregator = ContextAggregator()

    scenes_contexts = []
    for scene in sample_scenes:
        ctx = aggregator.aggregate_scene_context(scene_data=scene)
        scenes_contexts.append(ctx)

    video_context = aggregator.aggregate_video_context(
        video_id="test_video",
        duration=35.0,
        scene_contexts=scenes_contexts,
    )

    assert video_context is not None
    assert video_context.video_id == "test_video"
    assert video_context.total_scenes == 3


def test_context_aggregator_convenience_function(sample_scenes):
    """Test convenience function"""
    context = aggregate_scene_context(scene_data=sample_scenes[0])

    assert context is not None
    assert context.scene_id == 1


# Timeline Builder Tests

def test_timeline_builder_initialization():
    """Test TimelineBuilder initialization"""
    builder = TimelineBuilder()
    assert builder is not None


def test_build_timeline(sample_scenes, sample_transcript_segments):
    """Test building timeline"""
    builder = TimelineBuilder()

    timeline = builder.build_timeline(
        video_id="test_video",
        duration=35.0,
        scenes=sample_scenes,
        transcript_segments=sample_transcript_segments,
    )

    assert timeline is not None
    assert timeline.video_id == "test_video"
    assert len(timeline.segments) > 0
    assert len(timeline.events) > 0
    assert len(timeline.chapters) > 0


def test_timeline_export_json(sample_scenes):
    """Test exporting timeline to JSON"""
    builder = TimelineBuilder()

    timeline = builder.build_timeline(
        video_id="test_video",
        duration=35.0,
        scenes=sample_scenes,
    )

    json_data = builder.export_timeline_json(timeline)

    assert json_data is not None
    assert json_data["video_id"] == "test_video"
    assert "segments" in json_data
    assert "chapters" in json_data


def test_timeline_export_vtt(sample_scenes):
    """Test exporting timeline to WebVTT"""
    builder = TimelineBuilder()

    timeline = builder.build_timeline(
        video_id="test_video",
        duration=35.0,
        scenes=sample_scenes,
    )

    vtt = builder.export_timeline_vtt(timeline)

    assert vtt is not None
    assert vtt.startswith("WEBVTT")


def test_timeline_builder_convenience_function(sample_scenes, sample_transcript_segments):
    """Test convenience function"""
    timeline = build_video_timeline(
        video_id="test_video",
        duration=35.0,
        scenes=sample_scenes,
        transcript_segments=sample_transcript_segments,
    )

    assert timeline is not None
    assert len(timeline.segments) > 0


# Scene Enricher Tests

def test_scene_enricher_initialization():
    """Test SceneEnricher initialization"""
    enricher = SceneEnricher()
    assert enricher is not None


def test_enrich_scene(sample_scenes, sample_visual_context, sample_audio_context):
    """Test enriching scene"""
    enricher = SceneEnricher()

    transcript_segments = [
        {"start_time": 2.0, "end_time": 8.0, "text": "Hello", "speaker": "Speaker 1"},
    ]

    enriched = enricher.enrich_scene(
        scene_data=sample_scenes[0],
        transcript_segments=transcript_segments,
        visual_analysis=sample_visual_context,
        audio_analysis=sample_audio_context,
    )

    assert enriched is not None
    assert enriched.scene_id == 1
    assert enriched.fused_scene is not None
    assert enriched.scene_context is not None
    assert enriched.title is not None


def test_enrich_video_scenes(sample_scenes):
    """Test enriching all video scenes"""
    enricher = SceneEnricher()

    result = enricher.enrich_video_scenes(
        video_id="test_video",
        scenes=sample_scenes,
    )

    assert result is not None
    assert result.video_id == "test_video"
    assert result.total_scenes == 3
    assert len(result.enriched_scenes) == 3


def test_scene_enricher_convenience_function(sample_scenes):
    """Test convenience function"""
    enriched = enrich_scene(scene_data=sample_scenes[0])

    assert enriched is not None
    assert enriched.scene_id == 1


# MultiModal Embedder Tests

def test_multimodal_embedder_initialization():
    """Test MultiModalEmbedder initialization"""
    embedder = MultiModalEmbedder()
    assert embedder is not None


def test_weighted_sum_fusion():
    """Test weighted sum fusion strategy"""
    config = EmbeddingFusionConfig(strategy=FusionStrategy.WEIGHTED_SUM)
    embedder = MultiModalEmbedder(config=config)

    visual_emb = np.random.rand(512).astype(np.float32)
    text_emb = np.random.rand(512).astype(np.float32)

    fused = embedder.fuse_embeddings(
        visual_embedding=visual_emb,
        text_embedding=text_emb,
    )

    assert fused is not None
    assert fused.fused_embedding.shape[0] == 512
    assert len(fused.source_embeddings) == 2


def test_concatenation_fusion():
    """Test concatenation fusion strategy"""
    config = EmbeddingFusionConfig(strategy=FusionStrategy.CONCATENATION)
    embedder = MultiModalEmbedder(config=config)

    visual_emb = np.random.rand(256).astype(np.float32)
    text_emb = np.random.rand(256).astype(np.float32)

    fused = embedder.fuse_embeddings(
        visual_embedding=visual_emb,
        text_embedding=text_emb,
    )

    assert fused is not None
    assert fused.fused_embedding.shape[0] == 512  # 256 + 256


def test_attention_fusion():
    """Test attention fusion strategy"""
    config = EmbeddingFusionConfig(strategy=FusionStrategy.ATTENTION)
    embedder = MultiModalEmbedder(config=config)

    visual_emb = np.random.rand(512).astype(np.float32)
    text_emb = np.random.rand(512).astype(np.float32)

    fused = embedder.fuse_embeddings(
        visual_embedding=visual_emb,
        text_embedding=text_emb,
    )

    assert fused is not None
    assert fused.fused_embedding.shape[0] == 512


def test_max_pooling_fusion():
    """Test max pooling fusion strategy"""
    config = EmbeddingFusionConfig(strategy=FusionStrategy.MAX_POOLING)
    embedder = MultiModalEmbedder(config=config)

    visual_emb = np.random.rand(512).astype(np.float32)
    text_emb = np.random.rand(512).astype(np.float32)

    fused = embedder.fuse_embeddings(
        visual_embedding=visual_emb,
        text_embedding=text_emb,
    )

    assert fused is not None
    assert fused.fused_embedding.shape[0] == 512


def test_fuse_batch():
    """Test batch fusion"""
    embedder = MultiModalEmbedder()

    visual_embs = [np.random.rand(512).astype(np.float32) for _ in range(3)]
    text_embs = [np.random.rand(512).astype(np.float32) for _ in range(3)]

    fused_list = embedder.fuse_batch(
        visual_embeddings=visual_embs,
        text_embeddings=text_embs,
    )

    assert len(fused_list) == 3
    for fused in fused_list:
        assert fused.fused_embedding is not None


def test_compute_similarity():
    """Test computing similarity between embeddings"""
    embedder = MultiModalEmbedder()

    visual_emb1 = np.random.rand(512).astype(np.float32)
    text_emb1 = np.random.rand(512).astype(np.float32)

    fused1 = embedder.fuse_embeddings(
        visual_embedding=visual_emb1,
        text_embedding=text_emb1,
    )

    fused2 = embedder.fuse_embeddings(
        visual_embedding=visual_emb1,  # Same visual
        text_embedding=text_emb1,  # Same text
    )

    similarity = embedder.compute_similarity(fused1, fused2, metric="cosine")

    assert similarity > 0.9  # Should be very similar


def test_multimodal_embedder_convenience_function():
    """Test convenience function"""
    visual_emb = np.random.rand(512).astype(np.float32)
    text_emb = np.random.rand(512).astype(np.float32)

    fused = fuse_multimodal_embeddings(
        visual_embedding=visual_emb,
        text_embedding=text_emb,
    )

    assert fused is not None
    assert fused.fused_embedding is not None


# Contextual Search Engine Tests

def test_contextual_search_engine_initialization():
    """Test ContextualSearchEngine initialization"""
    engine = ContextualSearchEngine()
    assert engine is not None


def test_search_query_creation():
    """Test creating search query"""
    query = SearchQuery(
        query_text="person walking",
        top_k=10,
        search_mode=SearchMode.TEXT_ONLY,
    )

    assert query is not None
    assert query.query_text == "person walking"
    assert query.top_k == 10


def test_search_mode_adaptive():
    """Test adaptive search mode"""
    query = SearchQuery(
        query_text="test",
        search_mode=SearchMode.ADAPTIVE,
    )

    assert query.search_mode == SearchMode.ADAPTIVE


def test_reranking_methods():
    """Test different re-ranking methods"""
    methods = [
        ReRankingMethod.TEMPORAL_COHERENCE,
        ReRankingMethod.DIVERSITY,
        ReRankingMethod.IMPORTANCE,
        ReRankingMethod.COMBINED,
    ]

    for method in methods:
        query = SearchQuery(
            query_text="test",
            rerank_method=method,
        )
        assert query.rerank_method == method


# Integration Tests

def test_full_fusion_pipeline(sample_scenes, sample_transcript_segments, sample_visual_context, sample_audio_context):
    """Test full fusion pipeline"""
    # 1. Temporal alignment
    aligner = TemporalAligner()
    alignment_result = aligner.align_transcript_with_scenes(
        video_id="test_video",
        scenes=sample_scenes,
        transcript_segments=sample_transcript_segments,
    )

    assert alignment_result is not None

    # 2. Visual-audio fusion
    fuser = VisualAudioFuser()
    fused_scene = fuser.fuse_scene(
        scene_data=sample_scenes[0],
        visual_context=sample_visual_context,
        audio_context=sample_audio_context,
    )

    assert fused_scene is not None

    # 3. Context aggregation
    aggregator = ContextAggregator()
    scene_context = aggregator.aggregate_scene_context(
        scene_data=sample_scenes[0],
        transcript_segments=sample_transcript_segments[:1],
    )

    assert scene_context is not None

    # 4. Timeline building
    builder = TimelineBuilder()
    timeline = builder.build_timeline(
        video_id="test_video",
        duration=35.0,
        scenes=sample_scenes,
        transcript_segments=sample_transcript_segments,
    )

    assert timeline is not None

    # 5. Scene enrichment
    enricher = SceneEnricher()
    enriched = enricher.enrich_scene(
        scene_data=sample_scenes[0],
        transcript_segments=sample_transcript_segments[:1],
        visual_analysis=sample_visual_context,
        audio_analysis=sample_audio_context,
    )

    assert enriched is not None


def test_multimodal_embedding_integration():
    """Test multi-modal embedding integration"""
    embedder = MultiModalEmbedder()

    # Create sample embeddings
    visual_emb = np.random.rand(512).astype(np.float32)
    text_emb = np.random.rand(512).astype(np.float32)

    # Test different strategies
    strategies = [
        FusionStrategy.WEIGHTED_SUM,
        FusionStrategy.CONCATENATION,
        FusionStrategy.ATTENTION,
        FusionStrategy.MAX_POOLING,
        FusionStrategy.AVERAGE_POOLING,
    ]

    for strategy in strategies:
        config = EmbeddingFusionConfig(strategy=strategy)
        embedder = MultiModalEmbedder(config=config)

        fused = embedder.fuse_embeddings(
            visual_embedding=visual_emb,
            text_embedding=text_emb,
        )

        assert fused is not None
        assert fused.fusion_strategy == strategy
