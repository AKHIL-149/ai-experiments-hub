"""
Importance scorer for scene importance evaluation
Score scenes based on visual activity, audio energy, objects, faces, and actions
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ImportanceFactors:
    """Factors contributing to scene importance"""
    visual_activity: float = 0.0
    audio_energy: float = 0.0
    object_count: float = 0.0
    face_count: float = 0.0
    action_count: float = 0.0
    speaker_count: float = 0.0
    transcript_length: float = 0.0
    scene_transition: float = 0.0

    # Aggregated
    total_score: float = 0.0


@dataclass
class ScoringWeights:
    """Weights for different importance factors"""
    visual_activity: float = 0.15
    audio_energy: float = 0.10
    object_count: float = 0.10
    face_count: float = 0.15
    action_count: float = 0.20
    speaker_count: float = 0.10
    transcript_length: float = 0.10
    scene_transition: float = 0.10

    def normalize(self):
        """Normalize weights to sum to 1.0"""
        total = (
            self.visual_activity +
            self.audio_energy +
            self.object_count +
            self.face_count +
            self.action_count +
            self.speaker_count +
            self.transcript_length +
            self.scene_transition
        )
        if total > 0:
            self.visual_activity /= total
            self.audio_energy /= total
            self.object_count /= total
            self.face_count /= total
            self.action_count /= total
            self.speaker_count /= total
            self.transcript_length /= total
            self.scene_transition /= total


@dataclass
class SceneImportanceScore:
    """Importance score for a scene"""
    scene_id: int
    start_time: float
    end_time: float
    importance_score: float
    factors: ImportanceFactors
    rank: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ImportanceScorer:
    """
    Score scenes by importance using multiple factors
    Use ML-based or heuristic scoring
    """

    def __init__(
        self,
        weights: Optional[ScoringWeights] = None,
        use_ml_model: bool = False,
        normalize_scores: bool = True,
    ):
        """
        Initialize importance scorer

        Args:
            weights: Custom scoring weights
            use_ml_model: Use ML-based scoring (not implemented yet)
            normalize_scores: Normalize scores to 0-1 range
        """
        self.weights = weights or ScoringWeights()
        self.weights.normalize()
        self.use_ml_model = use_ml_model
        self.normalize_scores = normalize_scores

        logger.info("Initialized ImportanceScorer")

    def score_scene(
        self,
        scene_data: Dict[str, Any],
        enriched_scene: Optional[Any] = None,
        visual_context: Optional[Dict[str, Any]] = None,
        audio_context: Optional[Dict[str, Any]] = None,
        transcript_segments: Optional[List[Dict[str, Any]]] = None,
    ) -> SceneImportanceScore:
        """
        Score a single scene's importance

        Args:
            scene_data: Scene information
            enriched_scene: EnrichedScene object
            visual_context: Visual analysis context
            audio_context: Audio analysis context
            transcript_segments: Transcript segments

        Returns:
            SceneImportanceScore
        """
        scene_id = scene_data.get("scene_number", scene_data.get("scene_id", 0))
        start_time = scene_data["start_time"]
        end_time = scene_data["end_time"]

        # Use enriched scene if available
        if enriched_scene:
            factors = self._extract_factors_from_enriched_scene(enriched_scene)
        else:
            factors = self._extract_factors(
                scene_data=scene_data,
                visual_context=visual_context,
                audio_context=audio_context,
                transcript_segments=transcript_segments,
            )

        # Calculate total importance score
        importance_score = self._calculate_importance_score(factors)

        return SceneImportanceScore(
            scene_id=scene_id,
            start_time=start_time,
            end_time=end_time,
            importance_score=importance_score,
            factors=factors,
        )

    def score_scenes_batch(
        self,
        scenes_data: List[Dict[str, Any]],
        enriched_scenes: Optional[List[Any]] = None,
    ) -> List[SceneImportanceScore]:
        """
        Score multiple scenes in batch

        Args:
            scenes_data: List of scene data
            enriched_scenes: Optional enriched scenes

        Returns:
            List of SceneImportanceScore objects
        """
        scores = []

        # Create lookup for enriched scenes
        enriched_lookup = {}
        if enriched_scenes:
            for enriched in enriched_scenes:
                enriched_lookup[enriched.scene_id] = enriched

        for scene in scenes_data:
            scene_id = scene.get("scene_number", scene.get("scene_id", 0))
            enriched = enriched_lookup.get(scene_id)

            score = self.score_scene(
                scene_data=scene,
                enriched_scene=enriched,
            )
            scores.append(score)

        # Normalize scores if requested
        if self.normalize_scores and scores:
            scores = self._normalize_scene_scores(scores)

        # Rank scenes
        scores = self._rank_scenes(scores)

        return scores

    def _extract_factors_from_enriched_scene(
        self,
        enriched_scene: Any,
    ) -> ImportanceFactors:
        """Extract importance factors from enriched scene"""
        factors = ImportanceFactors()

        # Visual factors
        if hasattr(enriched_scene, "fused_scene") and enriched_scene.fused_scene:
            fused = enriched_scene.fused_scene

            # Objects
            if fused.detected_objects:
                factors.object_count = len(fused.detected_objects)

            # Actions
            if fused.detected_actions:
                factors.action_count = len(fused.detected_actions)

            # Use pre-calculated importance
            if hasattr(fused, "importance_score"):
                # This is a pre-calculated score, use it as baseline
                base_score = fused.importance_score
                factors.visual_activity = base_score

        # Audio/Transcript factors
        if hasattr(enriched_scene, "scene_context") and enriched_scene.scene_context:
            ctx = enriched_scene.scene_context

            # Speakers
            if ctx.speakers:
                factors.speaker_count = len(ctx.speakers)

            # Transcript
            if ctx.full_transcript_text:
                # Normalize by typical sentence length
                factors.transcript_length = min(1.0, len(ctx.full_transcript_text) / 500)

            # Faces
            if hasattr(ctx, "num_faces"):
                factors.face_count = ctx.num_faces

        # Scene transition (assume medium importance for transitions)
        factors.scene_transition = 0.5

        return factors

    def _extract_factors(
        self,
        scene_data: Dict[str, Any],
        visual_context: Optional[Dict[str, Any]],
        audio_context: Optional[Dict[str, Any]],
        transcript_segments: Optional[List[Dict[str, Any]]],
    ) -> ImportanceFactors:
        """Extract importance factors from raw data"""
        factors = ImportanceFactors()

        # Visual factors
        if visual_context:
            # Objects
            objects = visual_context.get("objects", [])
            factors.object_count = len(objects)

            # Actions
            actions = visual_context.get("actions", [])
            factors.action_count = len(actions)

            # Faces
            faces = visual_context.get("faces", [])
            factors.face_count = len(faces)

            # Visual activity (use motion or scene changes as proxy)
            factors.visual_activity = min(1.0, (len(objects) + len(actions)) / 10)

        # Audio factors
        if audio_context:
            # Audio energy
            features = audio_context.get("features", {})
            if isinstance(features, dict):
                energy = features.get("energy", 0.5)
                factors.audio_energy = energy
            else:
                factors.audio_energy = 0.5

        # Transcript factors
        if transcript_segments:
            # Speaker count
            speakers = set()
            total_text = ""
            for seg in transcript_segments:
                if seg.get("speaker"):
                    speakers.add(seg["speaker"])
                total_text += seg.get("text", "")

            factors.speaker_count = len(speakers)
            factors.transcript_length = min(1.0, len(total_text) / 500)

        # Scene transition
        transition_type = scene_data.get("transition_type", "")
        if transition_type in ("fade", "dissolve"):
            factors.scene_transition = 0.7
        elif transition_type == "cut":
            factors.scene_transition = 0.3
        else:
            factors.scene_transition = 0.5

        return factors

    def _calculate_importance_score(
        self,
        factors: ImportanceFactors,
    ) -> float:
        """Calculate total importance score from factors"""
        if self.use_ml_model:
            # TODO: Implement ML-based scoring
            return self._calculate_heuristic_score(factors)
        else:
            return self._calculate_heuristic_score(factors)

    def _calculate_heuristic_score(
        self,
        factors: ImportanceFactors,
    ) -> float:
        """Calculate importance using weighted heuristics"""
        score = 0.0

        # Visual activity
        score += self.weights.visual_activity * min(1.0, factors.visual_activity)

        # Audio energy
        score += self.weights.audio_energy * min(1.0, factors.audio_energy)

        # Object count (normalize to 0-1, assume 10 objects is high)
        score += self.weights.object_count * min(1.0, factors.object_count / 10)

        # Face count (normalize, assume 5 faces is high)
        score += self.weights.face_count * min(1.0, factors.face_count / 5)

        # Action count (normalize, assume 5 actions is high)
        score += self.weights.action_count * min(1.0, factors.action_count / 5)

        # Speaker count (normalize, assume 3 speakers is high)
        score += self.weights.speaker_count * min(1.0, factors.speaker_count / 3)

        # Transcript length (already normalized)
        score += self.weights.transcript_length * factors.transcript_length

        # Scene transition
        score += self.weights.scene_transition * factors.scene_transition

        # Store total
        factors.total_score = score

        return min(1.0, score)

    def _normalize_scene_scores(
        self,
        scores: List[SceneImportanceScore],
    ) -> List[SceneImportanceScore]:
        """Normalize scores to 0-1 range"""
        if not scores:
            return scores

        # Find min and max
        min_score = min(s.importance_score for s in scores)
        max_score = max(s.importance_score for s in scores)

        # Avoid division by zero
        if max_score - min_score < 1e-6:
            return scores

        # Normalize
        for score in scores:
            normalized = (score.importance_score - min_score) / (max_score - min_score)
            score.importance_score = normalized

        return scores

    def _rank_scenes(
        self,
        scores: List[SceneImportanceScore],
    ) -> List[SceneImportanceScore]:
        """Rank scenes by importance"""
        # Sort by score (descending)
        sorted_scores = sorted(scores, key=lambda x: x.importance_score, reverse=True)

        # Assign ranks
        for i, score in enumerate(sorted_scores, 1):
            score.rank = i

        # Return in original order (by scene_id)
        return sorted(sorted_scores, key=lambda x: x.scene_id)

    def get_top_scenes(
        self,
        scores: List[SceneImportanceScore],
        top_k: int = 10,
        min_importance: float = 0.5,
    ) -> List[SceneImportanceScore]:
        """
        Get top K most important scenes

        Args:
            scores: Scene importance scores
            top_k: Number of top scenes
            min_importance: Minimum importance threshold

        Returns:
            List of top scenes
        """
        # Filter by minimum importance
        filtered = [s for s in scores if s.importance_score >= min_importance]

        # Sort by importance
        sorted_scores = sorted(
            filtered,
            key=lambda x: x.importance_score,
            reverse=True
        )

        # Return top K
        return sorted_scores[:top_k]

    def get_importance_distribution(
        self,
        scores: List[SceneImportanceScore],
    ) -> Dict[str, Any]:
        """
        Get statistics about importance distribution

        Args:
            scores: Scene importance scores

        Returns:
            Distribution statistics
        """
        if not scores:
            return {}

        importance_values = [s.importance_score for s in scores]

        return {
            "mean": np.mean(importance_values),
            "median": np.median(importance_values),
            "std": np.std(importance_values),
            "min": np.min(importance_values),
            "max": np.max(importance_values),
            "num_scenes": len(scores),
            "high_importance_count": sum(1 for s in scores if s.importance_score >= 0.7),
            "medium_importance_count": sum(1 for s in scores if 0.3 <= s.importance_score < 0.7),
            "low_importance_count": sum(1 for s in scores if s.importance_score < 0.3),
        }


def score_scene_importance(
    scene_data: Dict[str, Any],
    enriched_scene: Optional[Any] = None,
    weights: Optional[ScoringWeights] = None,
) -> SceneImportanceScore:
    """
    Convenience function to score scene importance

    Args:
        scene_data: Scene data
        enriched_scene: Enriched scene
        weights: Custom scoring weights

    Returns:
        SceneImportanceScore
    """
    scorer = ImportanceScorer(weights=weights)
    return scorer.score_scene(
        scene_data=scene_data,
        enriched_scene=enriched_scene,
    )
