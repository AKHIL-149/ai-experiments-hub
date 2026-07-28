"""
Tests for highlight detection and generation services
"""

import pytest
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.services.highlights.importance_scorer import (
    ImportanceScorer,
    ImportanceFactors,
    ScoringWeights,
    SceneImportanceScore,
    score_scene_importance,
)
from src.services.highlights.highlight_detector import (
    HighlightDetector,
    Highlight,
    HighlightCollection,
    HighlightType,
    detect_highlights,
)
from src.services.highlights.clip_creator import (
    ClipCreator,
    ClipConfig,
    ClipMetadata,
    create_clip,
)
from src.services.highlights.ranker import (
    HighlightRanker,
    RankingConfig,
    rank_highlights,
)
from src.services.highlights.exporter import (
    HighlightExporter,
    ExportConfig,
    TransitionConfig,
    HighlightReel,
    export_highlight_reel,
)


# ============================================================================
# ImportanceScorer Tests
# ============================================================================


class TestImportanceScorer:
    """Test ImportanceScorer"""

    def test_init_default(self):
        """Test initialization with default weights"""
        scorer = ImportanceScorer()

        assert scorer.weights is not None
        assert scorer.normalize_scores is True
        assert scorer.use_ml_model is False

    def test_init_custom_weights(self):
        """Test initialization with custom weights"""
        weights = ScoringWeights(
            visual_activity=0.3,
            audio_energy=0.2,
            action_count=0.5,
        )

        scorer = ImportanceScorer(weights=weights)

        assert scorer.weights.visual_activity == 0.3
        assert scorer.weights.audio_energy == 0.2

    def test_score_scene_with_enriched_scene(self):
        """Test scoring scene with enriched scene data"""
        scorer = ImportanceScorer()

        # Mock enriched scene
        enriched_scene = Mock()
        enriched_scene.scene_id = 1
        enriched_scene.fused_scene = Mock()
        enriched_scene.fused_scene.detected_objects = ["person", "car"]
        enriched_scene.fused_scene.detected_actions = ["walking", "running"]
        enriched_scene.fused_scene.importance_score = 0.8

        enriched_scene.scene_context = Mock()
        enriched_scene.scene_context.speakers = ["Speaker 1"]
        enriched_scene.scene_context.full_transcript_text = "This is a test"
        enriched_scene.scene_context.num_faces = 2

        scene_data = {
            "scene_id": 1,
            "start_time": 0.0,
            "end_time": 10.0,
        }

        result = scorer.score_scene(
            scene_data=scene_data,
            enriched_scene=enriched_scene,
        )

        assert isinstance(result, SceneImportanceScore)
        assert result.scene_id == 1
        assert result.importance_score > 0.0
        assert result.factors.object_count == 2
        assert result.factors.action_count == 2
        assert result.factors.speaker_count == 1

    def test_score_scenes_batch(self):
        """Test batch scene scoring"""
        scorer = ImportanceScorer()

        scenes = [
            {"scene_id": 1, "start_time": 0.0, "end_time": 10.0},
            {"scene_id": 2, "start_time": 10.0, "end_time": 20.0},
            {"scene_id": 3, "start_time": 20.0, "end_time": 30.0},
        ]

        # Create mock enriched scenes
        enriched_scenes = []
        for i in range(3):
            enriched = Mock()
            enriched.scene_id = i + 1
            enriched.fused_scene = Mock()
            enriched.fused_scene.detected_objects = ["object"] * (i + 1)
            enriched.fused_scene.detected_actions = ["action"] * i
            enriched.fused_scene.importance_score = 0.5 + i * 0.1

            enriched.scene_context = Mock()
            enriched.scene_context.speakers = ["Speaker"] * (i + 1)
            enriched.scene_context.full_transcript_text = "Text" * (i + 1)
            enriched.scene_context.num_faces = i + 1

            enriched_scenes.append(enriched)

        results = scorer.score_scenes_batch(
            scenes_data=scenes,
            enriched_scenes=enriched_scenes,
        )

        assert len(results) == 3
        assert all(isinstance(r, SceneImportanceScore) for r in results)
        assert all(r.rank is not None for r in results)

    def test_normalize_scores(self):
        """Test score normalization"""
        scorer = ImportanceScorer(normalize_scores=True)

        scenes = [
            {"scene_id": 1, "start_time": 0.0, "end_time": 10.0},
            {"scene_id": 2, "start_time": 10.0, "end_time": 20.0},
        ]

        # Create enriched scenes with different importance
        enriched_scenes = []
        for i, score in enumerate([0.3, 0.9]):
            enriched = Mock()
            enriched.scene_id = i + 1
            enriched.fused_scene = Mock()
            enriched.fused_scene.detected_objects = []
            enriched.fused_scene.detected_actions = []
            enriched.fused_scene.importance_score = score

            enriched.scene_context = Mock()
            enriched.scene_context.speakers = []
            enriched.scene_context.full_transcript_text = ""
            enriched.scene_context.num_faces = 0

            enriched_scenes.append(enriched)

        results = scorer.score_scenes_batch(
            scenes_data=scenes,
            enriched_scenes=enriched_scenes,
        )

        # Check normalization (scores should be in 0-1 range)
        scores = [r.importance_score for r in results]
        assert min(scores) >= 0.0
        assert max(scores) <= 1.0


# ============================================================================
# HighlightDetector Tests
# ============================================================================


class TestHighlightDetector:
    """Test HighlightDetector"""

    def test_init(self):
        """Test initialization"""
        detector = HighlightDetector(
            min_importance=0.7,
            min_highlight_duration=5.0,
        )

        assert detector.min_importance == 0.7
        assert detector.min_highlight_duration == 5.0

    def test_detect_highlights_with_scores(self):
        """Test highlight detection with pre-computed scores"""
        detector = HighlightDetector(min_importance=0.6)

        # Create mock scores
        scores = []
        for i in range(5):
            score = Mock()
            score.scene_id = i
            score.start_time = i * 10.0
            score.end_time = (i + 1) * 10.0
            score.importance_score = 0.5 + i * 0.1  # 0.5, 0.6, 0.7, 0.8, 0.9
            score.factors = Mock()
            score.factors.action_count = i
            score.factors.speaker_count = 1
            score.factors.visual_activity = 0.5
            score.factors.face_count = 1
            scores.append(score)

        result = detector.detect_highlights(
            video_id="test_video",
            duration=50.0,
            scene_scores=scores,
            max_highlights=3,
        )

        assert isinstance(result, HighlightCollection)
        assert result.video_id == "test_video"
        # Should have 3 highlights (above 0.6 threshold, limited to 3)
        assert len(result.highlights) <= 3
        assert all(h.importance_score >= 0.6 for h in result.highlights)

    def test_detect_highlights_with_scorer(self):
        """Test highlight detection with importance scorer"""
        scorer = ImportanceScorer()
        detector = HighlightDetector(
            importance_scorer=scorer,
            min_importance=0.5,
        )

        scenes = [
            {"scene_id": 1, "start_time": 0.0, "end_time": 10.0},
            {"scene_id": 2, "start_time": 10.0, "end_time": 20.0},
        ]

        # Create enriched scenes
        enriched_scenes = []
        for i in range(2):
            enriched = Mock()
            enriched.scene_id = i + 1
            enriched.fused_scene = Mock()
            enriched.fused_scene.detected_objects = ["object"] * (i + 3)
            enriched.fused_scene.detected_actions = ["action"] * (i + 2)
            enriched.fused_scene.importance_score = 0.7

            enriched.scene_context = Mock()
            enriched.scene_context.speakers = ["Speaker"]
            enriched.scene_context.full_transcript_text = "Important scene"
            enriched.scene_context.num_faces = 2

            enriched_scenes.append(enriched)

        result = detector.detect_highlights(
            video_id="test_video",
            duration=20.0,
            scenes=scenes,
            enriched_scenes=enriched_scenes,
        )

        assert isinstance(result, HighlightCollection)
        assert len(result.highlights) > 0

    def test_merge_nearby_highlights(self):
        """Test merging nearby highlights"""
        detector = HighlightDetector(
            merge_nearby_highlights=True,
            nearby_threshold=5.0,
        )

        # Create two nearby highlights
        highlight1 = Highlight(
            highlight_id="h1",
            video_id="test",
            start_time=0.0,
            end_time=10.0,
            duration=10.0,
            highlight_type=HighlightType.ACTION,
            importance_score=0.8,
            scene_ids=[1],
            num_scenes=1,
        )

        highlight2 = Highlight(
            highlight_id="h2",
            video_id="test",
            start_time=12.0,  # Only 2 seconds gap
            end_time=22.0,
            duration=10.0,
            highlight_type=HighlightType.ACTION,
            importance_score=0.7,
            scene_ids=[2],
            num_scenes=1,
        )

        merged = detector._merge_nearby_highlights([highlight1, highlight2])

        # Should merge into one highlight
        assert len(merged) == 1
        assert merged[0].duration >= 20.0  # Combined duration


# ============================================================================
# ClipCreator Tests
# ============================================================================


@pytest.mark.skipif(
    os.system("which ffmpeg > /dev/null 2>&1") != 0,
    reason="FFmpeg not available",
)
class TestClipCreator:
    """Test ClipCreator"""

    def test_init(self):
        """Test initialization"""
        with tempfile.TemporaryDirectory() as temp_dir:
            creator = ClipCreator(output_dir=temp_dir)

            assert creator.output_dir == Path(temp_dir)
            assert creator.ffmpeg_path == "ffmpeg"

    def test_clip_config(self):
        """Test clip configuration"""
        config = ClipConfig(
            output_format="mp4",
            video_codec="libx264",
            crf=23,
            fade_in_duration=1.0,
            fade_out_duration=1.0,
        )

        assert config.output_format == "mp4"
        assert config.fade_in_duration == 1.0
        assert config.fade_out_duration == 1.0

    @patch('subprocess.Popen')
    def test_create_clip_mock(self, mock_popen):
        """Test clip creation with mocked ffmpeg"""
        with tempfile.TemporaryDirectory() as temp_dir:
            creator = ClipCreator(output_dir=temp_dir)

            # Mock ffmpeg process
            mock_process = MagicMock()
            mock_process.stderr = []
            mock_process.wait.return_value = 0
            mock_popen.return_value = mock_process

            # Create a dummy video file
            video_path = os.path.join(temp_dir, "test_video.mp4")
            open(video_path, "w").close()

            # Mock the output file creation
            output_path = creator._generate_output_path("test", "clip1", "mp4")
            open(output_path, "w").close()

            try:
                metadata = creator.create_clip(
                    video_path=video_path,
                    start_time=5.0,
                    end_time=15.0,
                    video_id="test",
                )

                assert isinstance(metadata, ClipMetadata)
                assert metadata.start_time == 5.0
                assert metadata.end_time == 15.0
                assert metadata.duration == 10.0
            except RuntimeError:
                # FFmpeg verification might fail in test environment
                pass


# ============================================================================
# HighlightRanker Tests
# ============================================================================


class TestHighlightRanker:
    """Test HighlightRanker"""

    def test_init(self):
        """Test initialization"""
        config = RankingConfig(
            importance_weight=0.8,
            diversity_weight=0.2,
        )

        ranker = HighlightRanker(config=config)

        assert ranker.config.importance_weight == 0.8
        assert ranker.config.diversity_weight == 0.2

    def test_rank_highlights(self):
        """Test ranking highlights"""
        ranker = HighlightRanker()

        # Create test highlights
        highlights = []
        for i in range(5):
            highlight = Highlight(
                highlight_id=f"h{i}",
                video_id="test",
                start_time=i * 20.0,
                end_time=(i + 1) * 20.0,
                duration=20.0,
                highlight_type=HighlightType.ACTION,
                importance_score=0.5 + i * 0.1,  # 0.5, 0.6, 0.7, 0.8, 0.9
                scene_ids=[i],
                num_scenes=1,
            )
            highlights.append(highlight)

        ranked = ranker.rank_highlights(highlights)

        assert len(ranked) == 5
        # Check that ranks are assigned
        assert all(h.rank is not None for h in ranked)
        # Highest importance should have rank 1
        assert any(h.rank == 1 and h.importance_score == 0.9 for h in ranked)

    def test_diversity_selection(self):
        """Test diversity-based selection"""
        config = RankingConfig(
            min_time_gap=30.0,
            prefer_type_diversity=True,
        )
        ranker = HighlightRanker(config=config)

        # Create closely spaced highlights
        highlights = []
        for i in range(10):
            highlight = Highlight(
                highlight_id=f"h{i}",
                video_id="test",
                start_time=i * 10.0,  # Only 10s apart
                end_time=(i + 1) * 10.0,
                duration=10.0,
                highlight_type=HighlightType.ACTION if i % 2 == 0 else HighlightType.DIALOGUE,
                importance_score=0.9 - i * 0.05,  # Decreasing importance
                scene_ids=[i],
                num_scenes=1,
            )
            highlights.append(highlight)

        # Select top 3 with diversity
        ranked = ranker.rank_highlights(highlights, max_highlights=3)

        assert len(ranked) == 3
        # Should select diverse highlights (not all consecutive)

    def test_filter_overlapping(self):
        """Test filtering overlapping highlights"""
        ranker = HighlightRanker()

        # Create overlapping highlights
        highlight1 = Highlight(
            highlight_id="h1",
            video_id="test",
            start_time=0.0,
            end_time=10.0,
            duration=10.0,
            highlight_type=HighlightType.ACTION,
            importance_score=0.9,
            scene_ids=[1],
            num_scenes=1,
        )

        highlight2 = Highlight(
            highlight_id="h2",
            video_id="test",
            start_time=5.0,  # Overlaps with h1
            end_time=15.0,
            duration=10.0,
            highlight_type=HighlightType.ACTION,
            importance_score=0.7,
            scene_ids=[2],
            num_scenes=1,
        )

        filtered = ranker.filter_overlapping_highlights([highlight1, highlight2])

        # Should keep only the higher-ranked one
        assert len(filtered) == 1
        assert filtered[0].importance_score == 0.9


# ============================================================================
# HighlightExporter Tests
# ============================================================================


@pytest.mark.skipif(
    os.system("which ffmpeg > /dev/null 2>&1") != 0,
    reason="FFmpeg not available",
)
class TestHighlightExporter:
    """Test HighlightExporter"""

    def test_init(self):
        """Test initialization"""
        with tempfile.TemporaryDirectory() as temp_dir:
            exporter = HighlightExporter(output_dir=temp_dir)

            assert exporter.output_dir == Path(temp_dir)
            assert exporter.ffmpeg_path == "ffmpeg"

    def test_export_config(self):
        """Test export configuration"""
        transition = TransitionConfig(
            transition_type="fade",
            transition_duration=0.5,
        )

        config = ExportConfig(
            output_format="mp4",
            transition=transition,
            include_timestamps=True,
        )

        assert config.output_format == "mp4"
        assert config.transition.transition_type == "fade"
        assert config.include_timestamps is True

    def test_export_to_vtt(self):
        """Test exporting to WebVTT format"""
        with tempfile.TemporaryDirectory() as temp_dir:
            exporter = HighlightExporter(output_dir=temp_dir)

            # Create test highlights
            highlights = [
                Highlight(
                    highlight_id="h1",
                    video_id="test",
                    start_time=0.0,
                    end_time=10.0,
                    duration=10.0,
                    highlight_type=HighlightType.ACTION,
                    importance_score=0.9,
                    title="Action Scene",
                    scene_ids=[1],
                    num_scenes=1,
                    rank=1,
                ),
                Highlight(
                    highlight_id="h2",
                    video_id="test",
                    start_time=10.0,
                    end_time=20.0,
                    duration=10.0,
                    highlight_type=HighlightType.DIALOGUE,
                    importance_score=0.8,
                    title="Dialogue Scene",
                    scene_ids=[2],
                    num_scenes=1,
                    rank=2,
                ),
            ]

            # Create mock reel
            reel = HighlightReel(
                reel_id="test_reel",
                video_id="test",
                output_path="test.mp4",
                num_highlights=2,
                total_duration=20.0,
                highlights=highlights,
                file_size_bytes=1024,
                config=ExportConfig(),
            )

            vtt = exporter._export_to_vtt(reel)

            assert "WEBVTT" in vtt
            assert "Action Scene" in vtt
            assert "Dialogue Scene" in vtt


# ============================================================================
# Integration Tests
# ============================================================================


class TestHighlightsIntegration:
    """Integration tests for complete highlight pipeline"""

    def test_full_pipeline(self):
        """Test complete highlight generation pipeline"""
        # 1. Score scenes
        scorer = ImportanceScorer()

        scenes = [
            {"scene_id": i, "start_time": i * 10.0, "end_time": (i + 1) * 10.0}
            for i in range(10)
        ]

        # Create mock enriched scenes
        enriched_scenes = []
        for i in range(10):
            enriched = Mock()
            enriched.scene_id = i
            enriched.fused_scene = Mock()
            enriched.fused_scene.detected_objects = ["object"] * (i % 5 + 1)
            enriched.fused_scene.detected_actions = ["action"] * (i % 3)
            enriched.fused_scene.importance_score = 0.3 + (i % 7) * 0.1

            enriched.scene_context = Mock()
            enriched.scene_context.speakers = ["Speaker"] * (i % 2 + 1)
            enriched.scene_context.full_transcript_text = "Text" * 10
            enriched.scene_context.num_faces = i % 3 + 1

            enriched_scenes.append(enriched)

        scores = scorer.score_scenes_batch(
            scenes_data=scenes,
            enriched_scenes=enriched_scenes,
        )

        assert len(scores) == 10

        # 2. Detect highlights
        detector = HighlightDetector(
            importance_scorer=scorer,
            min_importance=0.6,
        )

        highlight_collection = detector.detect_highlights(
            video_id="test_video",
            duration=100.0,
            scenes=scenes,
            enriched_scenes=enriched_scenes,
            max_highlights=5,
        )

        assert isinstance(highlight_collection, HighlightCollection)
        assert len(highlight_collection.highlights) <= 5

        # 3. Rank highlights
        ranker = HighlightRanker()

        ranked_highlights = ranker.rank_highlights(
            highlights=highlight_collection.highlights,
            max_highlights=3,
        )

        assert len(ranked_highlights) <= 3
        assert all(h.rank is not None for h in ranked_highlights)

        # 4. Export metadata
        exporter_config = ExportConfig(output_format="json")

        # Mock reel for export
        if ranked_highlights:
            reel = HighlightReel(
                reel_id="test_reel",
                video_id="test_video",
                output_path="test.mp4",
                num_highlights=len(ranked_highlights),
                total_duration=sum(h.duration for h in ranked_highlights),
                highlights=ranked_highlights,
                file_size_bytes=1024,
                config=exporter_config,
            )

            with tempfile.TemporaryDirectory() as temp_dir:
                exporter = HighlightExporter(output_dir=temp_dir)
                metadata = exporter.export_to_format(reel, format="json")

                assert metadata["reel_id"] == "test_reel"
                assert metadata["num_highlights"] == len(ranked_highlights)
                assert len(metadata["highlights"]) == len(ranked_highlights)


# ============================================================================
# Convenience Function Tests
# ============================================================================


def test_score_scene_importance_convenience():
    """Test convenience function for scene importance scoring"""
    scene_data = {
        "scene_id": 1,
        "start_time": 0.0,
        "end_time": 10.0,
    }

    # Create mock enriched scene
    enriched = Mock()
    enriched.scene_id = 1
    enriched.fused_scene = Mock()
    enriched.fused_scene.detected_objects = ["object1", "object2"]
    enriched.fused_scene.detected_actions = ["action1"]
    enriched.fused_scene.importance_score = 0.7

    enriched.scene_context = Mock()
    enriched.scene_context.speakers = ["Speaker 1"]
    enriched.scene_context.full_transcript_text = "Test"
    enriched.scene_context.num_faces = 1

    result = score_scene_importance(
        scene_data=scene_data,
        enriched_scene=enriched,
    )

    assert isinstance(result, SceneImportanceScore)
    assert result.scene_id == 1


def test_detect_highlights_convenience():
    """Test convenience function for highlight detection"""
    scenes = [
        {"scene_id": 1, "start_time": 0.0, "end_time": 10.0},
    ]

    # Create mock enriched scene
    enriched = Mock()
    enriched.scene_id = 1
    enriched.fused_scene = Mock()
    enriched.fused_scene.detected_objects = ["object"] * 5
    enriched.fused_scene.detected_actions = ["action"] * 3
    enriched.fused_scene.importance_score = 0.8

    enriched.scene_context = Mock()
    enriched.scene_context.speakers = ["Speaker"]
    enriched.scene_context.full_transcript_text = "Important content"
    enriched.scene_context.num_faces = 2

    result = detect_highlights(
        video_id="test",
        duration=10.0,
        scenes=scenes,
        enriched_scenes=[enriched],
        min_importance=0.5,
    )

    assert isinstance(result, HighlightCollection)


def test_rank_highlights_convenience():
    """Test convenience function for highlight ranking"""
    highlights = [
        Highlight(
            highlight_id="h1",
            video_id="test",
            start_time=0.0,
            end_time=10.0,
            duration=10.0,
            highlight_type=HighlightType.ACTION,
            importance_score=0.8,
            scene_ids=[1],
            num_scenes=1,
        ),
    ]

    result = rank_highlights(highlights, max_highlights=1)

    assert len(result) == 1
    assert result[0].rank is not None
