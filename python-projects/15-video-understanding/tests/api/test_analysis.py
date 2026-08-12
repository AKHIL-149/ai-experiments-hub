"""
Tests for video analysis endpoints (highlights, chapters, timeline)
"""

import pytest


class TestHighlightDetection:
    """Tests for _run_highlight_detection scene scoring/filtering"""

    def test_default_threshold_produces_highlights_for_eventful_scenes(self):
        """Regression test: _run_highlight_detection used to score each scene
        individually via ImportanceScorer.score_scene() without normalizing
        the results, so raw heuristic scores (which realistically top out
        well under 0.7 for genuinely eventful real-world scenes) never
        cleared the default min_importance=0.7 filter - confirmed live,
        every processed video (1, 4, and 97 real scenes) got exactly 0
        highlights regardless of content. The fix normalizes scores to the
        video's own 0-1 range (same as ImportanceScorer.score_scenes_batch
        already does) before filtering."""
        from src.api.analysis import _run_highlight_detection, GenerateHighlightsRequest

        scenes = [
            {"scene_number": i, "start_time": float(i * 10), "end_time": float(i * 10 + 5),
             "transition_type": "cut"}
            for i in range(5)
        ]
        # Magnitudes drawn from a real processed video's DB rows (objects,
        # faces, activity_ratio, audio_energy, transcript length) - the most
        # "eventful" scene (index 2) has real, meaningful signal but nothing
        # close to maxing out every factor.
        visual_contexts = {
            0: {"objects": [], "faces": [], "actions": ["motion"] * 4},
            1: {"objects": ["person"], "faces": [{"bbox": [0, 0, 1, 1]}], "actions": ["motion"] * 5},
            2: {"objects": ["person", "phone"], "faces": [{"bbox": [0, 0, 1, 1]}], "actions": ["motion"] * 10},
            3: {"objects": [], "faces": [], "actions": ["motion"] * 5},
            4: {"objects": [], "faces": [], "actions": []},
        }
        audio_contexts = {i: {"features": {"energy": 0.4 + i * 0.05}} for i in range(5)}
        transcripts = {
            i: [{"text": "x" * 130, "start": float(i * 10), "end": float(i * 10 + 5), "speaker": "SPEAKER_00"}]
            for i in range(5)
        }

        highlights = _run_highlight_detection(
            video_id="test-video",
            duration=50.0,
            scenes=scenes,
            transcripts_by_scene=transcripts,
            visual_contexts_by_scene=visual_contexts,
            audio_contexts_by_scene=audio_contexts,
            keyframe_by_scene={i: f"storage/frames/test/scene_{i:03d}.jpg" for i in range(5)},
            config=GenerateHighlightsRequest(),
        )

        assert len(highlights) > 0
        assert any(h.importance_score >= 0.7 for h in highlights)
        # Each surviving highlight should carry a real keyframe path and a
        # plain-language reason, not just the generic "importance: X.XX"
        # template - that's the whole point of the enrichment step.
        for h in highlights:
            assert h.thumbnail_path is not None
            assert "importance:" not in h.description

    def test_single_uniform_scene_yields_no_highlights(self):
        """When every scene scores the same (e.g. a single-shot video with
        one scene spanning the whole duration), min-max normalization can't
        differentiate anything and correctly falls back to raw scores - so a
        video with nothing to highlight legitimately gets zero highlights,
        rather than crashing or fabricating one."""
        from src.api.analysis import _run_highlight_detection, GenerateHighlightsRequest

        scenes = [{"scene_number": 0, "start_time": 0.0, "end_time": 600.0, "transition_type": "cut"}]

        highlights = _run_highlight_detection(
            video_id="test-video",
            duration=600.0,
            scenes=scenes,
            transcripts_by_scene={0: []},
            visual_contexts_by_scene={0: {"objects": [], "faces": [], "actions": []}},
            audio_contexts_by_scene={0: {"features": {"energy": 0.1}}},
            keyframe_by_scene={0: "storage/frames/test/scene_000.jpg"},
            config=GenerateHighlightsRequest(),
        )

        assert highlights == []


class TestHighlightReasoning:
    """Tests for _describe_highlight_reason plain-language explanations"""

    def test_mentions_real_detected_signals(self):
        from src.api.analysis import _describe_highlight_reason

        reason = _describe_highlight_reason(
            visual_context={"objects": ["person", "laptop"], "faces": [{"bbox": [0, 0, 1, 1]}],
                             "actions": ["motion"] * 8},
            audio_context={"features": {"energy": 0.7}},
            transcript_segments=[{"text": "This is the key insight."}],
        )

        assert "laptop" in reason
        assert "face" in reason
        assert "movement" in reason or "action" in reason
        assert "raised" in reason or "emphatic" in reason
        assert "This is the key insight." in reason

    def test_no_signal_falls_back_to_generic_but_honest_message(self):
        """No fabricated reasoning when there's genuinely nothing notable -
        matches the same "don't invent a reason" principle as the
        highlight-selection fix itself."""
        from src.api.analysis import _describe_highlight_reason

        reason = _describe_highlight_reason(
            visual_context={"objects": [], "faces": [], "actions": []},
            audio_context={"features": {"energy": 0.0}},
            transcript_segments=[],
        )

        assert "importance:" not in reason
        assert reason
