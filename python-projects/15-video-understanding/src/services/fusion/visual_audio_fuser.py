"""
Visual-Audio fuser for multi-modal scene representation
Combine visual frame analysis with audio transcription context
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FusionWeights:
    """Weights for fusing different modalities"""
    visual: float = 0.5
    audio: float = 0.3
    text: float = 0.2

    def normalize(self):
        """Normalize weights to sum to 1.0"""
        total = self.visual + self.audio + self.text
        if total > 0:
            self.visual /= total
            self.audio /= total
            self.text /= total


@dataclass
class FusedScene:
    """Fused scene representation with visual and audio context"""
    scene_id: int
    start_time: float
    end_time: float

    # Visual context
    keyframe_indices: List[int]
    visual_features: Optional[np.ndarray] = None
    visual_description: Optional[str] = None
    detected_objects: List[str] = field(default_factory=list)
    detected_actions: List[str] = field(default_factory=list)

    # Audio/Text context
    transcript_text: str = ""
    speakers: List[str] = field(default_factory=list)
    audio_features: Optional[Dict[str, Any]] = None

    # Fused representation
    fused_embedding: Optional[np.ndarray] = None
    unified_description: Optional[str] = None
    importance_score: float = 0.0

    # Metadata
    fusion_weights: Optional[FusionWeights] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class VisualAudioFuser:
    """
    Combine visual and audio context for unified scene representation
    Weight and fuse embeddings, descriptions, and features
    """

    def __init__(
        self,
        default_weights: Optional[FusionWeights] = None,
        normalize_embeddings: bool = True,
    ):
        """
        Initialize visual-audio fuser

        Args:
            default_weights: Default fusion weights
            normalize_embeddings: Normalize fused embeddings
        """
        self.default_weights = default_weights or FusionWeights()
        self.default_weights.normalize()
        self.normalize_embeddings = normalize_embeddings

        logger.info(
            f"Initialized VisualAudioFuser "
            f"(visual={self.default_weights.visual:.2f}, "
            f"audio={self.default_weights.audio:.2f}, "
            f"text={self.default_weights.text:.2f})"
        )

    def fuse_scene(
        self,
        scene_data: Dict[str, Any],
        visual_context: Dict[str, Any],
        audio_context: Dict[str, Any],
        weights: Optional[FusionWeights] = None,
    ) -> FusedScene:
        """
        Fuse visual and audio context for a scene

        Args:
            scene_data: Scene information (times, ID)
            visual_context: Visual analysis results
            audio_context: Audio/transcript analysis
            weights: Custom fusion weights

        Returns:
            FusedScene with combined representation
        """
        weights = weights or self.default_weights

        scene_id = scene_data.get("scene_number", scene_data.get("scene_id", 0))
        start_time = scene_data["start_time"]
        end_time = scene_data["end_time"]

        # Extract visual features
        keyframe_indices = visual_context.get("keyframe_indices", [])
        visual_features = visual_context.get("features")
        visual_desc = visual_context.get("description", "")
        detected_objects = visual_context.get("objects", [])
        detected_actions = visual_context.get("actions", [])

        # Extract audio/text features
        transcript_text = audio_context.get("text", "")
        speakers = audio_context.get("speakers", [])
        audio_features = audio_context.get("features")

        # Fuse embeddings if available
        fused_embedding = self._fuse_embeddings(
            visual_embedding=visual_context.get("embedding"),
            audio_embedding=audio_context.get("embedding"),
            text_embedding=audio_context.get("text_embedding"),
            weights=weights,
        )

        # Create unified description
        unified_desc = self._create_unified_description(
            visual_desc, transcript_text, detected_objects, detected_actions, speakers
        )

        # Calculate importance score
        importance = self._calculate_importance_score(
            visual_context, audio_context, weights
        )

        return FusedScene(
            scene_id=scene_id,
            start_time=start_time,
            end_time=end_time,
            keyframe_indices=keyframe_indices,
            visual_features=visual_features,
            visual_description=visual_desc,
            detected_objects=detected_objects,
            detected_actions=detected_actions,
            transcript_text=transcript_text,
            speakers=speakers,
            audio_features=audio_features,
            fused_embedding=fused_embedding,
            unified_description=unified_desc,
            importance_score=importance,
            fusion_weights=weights,
            metadata={
                "duration": end_time - start_time,
                "has_visual": bool(visual_features is not None),
                "has_audio": bool(audio_features is not None),
                "has_transcript": bool(transcript_text),
            },
        )

    def _fuse_embeddings(
        self,
        visual_embedding: Optional[np.ndarray],
        audio_embedding: Optional[np.ndarray],
        text_embedding: Optional[np.ndarray],
        weights: FusionWeights,
    ) -> Optional[np.ndarray]:
        """
        Fuse embeddings from different modalities

        Args:
            visual_embedding: Visual feature embedding
            audio_embedding: Audio feature embedding
            text_embedding: Text embedding
            weights: Fusion weights

        Returns:
            Fused embedding or None
        """
        embeddings = []
        embedding_weights = []

        if visual_embedding is not None:
            embeddings.append(visual_embedding)
            embedding_weights.append(weights.visual)

        if audio_embedding is not None:
            embeddings.append(audio_embedding)
            embedding_weights.append(weights.audio)

        if text_embedding is not None:
            embeddings.append(text_embedding)
            embedding_weights.append(weights.text)

        if not embeddings:
            return None

        # Normalize weights
        total_weight = sum(embedding_weights)
        embedding_weights = [w / total_weight for w in embedding_weights]

        # Ensure same dimension
        target_dim = embeddings[0].shape[0]
        normalized_embeddings = []

        for emb in embeddings:
            if emb.shape[0] != target_dim:
                # Truncate or pad to target dimension
                if emb.shape[0] > target_dim:
                    emb = emb[:target_dim]
                else:
                    emb = np.pad(emb, (0, target_dim - emb.shape[0]))

            normalized_embeddings.append(emb)

        # Weighted fusion
        fused = sum(
            w * emb for w, emb in zip(embedding_weights, normalized_embeddings)
        )

        # Normalize if requested
        if self.normalize_embeddings:
            fused = fused / (np.linalg.norm(fused) + 1e-8)

        return fused

    def _create_unified_description(
        self,
        visual_desc: str,
        transcript_text: str,
        objects: List[str],
        actions: List[str],
        speakers: List[str],
    ) -> str:
        """
        Create unified natural language description

        Args:
            visual_desc: Visual description
            transcript_text: Transcript text
            objects: Detected objects
            actions: Detected actions
            speakers: Speaker IDs

        Returns:
            Unified description
        """
        parts = []

        # Visual context
        if visual_desc:
            parts.append(f"Visual: {visual_desc}")

        if objects:
            obj_str = ", ".join(objects[:5])  # Top 5 objects
            parts.append(f"Objects: {obj_str}")

        if actions:
            action_str = ", ".join(actions[:3])  # Top 3 actions
            parts.append(f"Actions: {action_str}")

        # Audio/text context
        if transcript_text:
            # Truncate if too long
            if len(transcript_text) > 200:
                transcript_text = transcript_text[:197] + "..."
            parts.append(f"Dialogue: \"{transcript_text}\"")

        if speakers:
            speaker_str = ", ".join(set(speakers))
            parts.append(f"Speakers: {speaker_str}")

        return " | ".join(parts)

    def _calculate_importance_score(
        self,
        visual_context: Dict[str, Any],
        audio_context: Dict[str, Any],
        weights: FusionWeights,
    ) -> float:
        """
        Calculate scene importance score

        Args:
            visual_context: Visual context
            audio_context: Audio context
            weights: Fusion weights

        Returns:
            Importance score (0-1)
        """
        visual_score = 0.0
        audio_score = 0.0

        # Visual importance
        num_objects = len(visual_context.get("objects", []))
        num_actions = len(visual_context.get("actions", []))
        has_faces = len(visual_context.get("faces", [])) > 0

        visual_score = min(1.0, (num_objects * 0.1 + num_actions * 0.2 + (0.3 if has_faces else 0)))

        # Audio importance
        has_transcript = bool(audio_context.get("text", ""))
        num_speakers = len(set(audio_context.get("speakers", [])))
        transcript_length = len(audio_context.get("text", ""))

        audio_score = min(1.0, (
            (0.3 if has_transcript else 0) +
            num_speakers * 0.2 +
            min(0.5, transcript_length / 500)
        ))

        # Weighted combination
        total_score = (
            weights.visual * visual_score +
            (weights.audio + weights.text) * audio_score
        )

        return total_score

    def fuse_scenes_batch(
        self,
        scenes_data: List[Dict[str, Any]],
        visual_contexts: List[Dict[str, Any]],
        audio_contexts: List[Dict[str, Any]],
        weights: Optional[FusionWeights] = None,
    ) -> List[FusedScene]:
        """
        Fuse multiple scenes in batch

        Args:
            scenes_data: List of scene data
            visual_contexts: List of visual contexts
            audio_contexts: List of audio contexts
            weights: Fusion weights

        Returns:
            List of FusedScene objects
        """
        if not (len(scenes_data) == len(visual_contexts) == len(audio_contexts)):
            raise ValueError("All lists must have same length")

        fused_scenes = []

        for scene_data, visual_ctx, audio_ctx in zip(
            scenes_data, visual_contexts, audio_contexts
        ):
            fused_scene = self.fuse_scene(
                scene_data=scene_data,
                visual_context=visual_ctx,
                audio_context=audio_ctx,
                weights=weights,
            )
            fused_scenes.append(fused_scene)

        logger.info(f"Fused {len(fused_scenes)} scenes")

        return fused_scenes

    def adaptive_weight_adjustment(
        self,
        visual_context: Dict[str, Any],
        audio_context: Dict[str, Any],
    ) -> FusionWeights:
        """
        Adaptively adjust fusion weights based on content quality

        Args:
            visual_context: Visual context
            audio_context: Audio context

        Returns:
            Adjusted FusionWeights
        """
        weights = FusionWeights()

        # Visual quality indicators
        has_visual = visual_context.get("features") is not None
        num_objects = len(visual_context.get("objects", []))
        visual_quality = visual_context.get("quality", 0.5)

        # Audio quality indicators
        has_audio = bool(audio_context.get("text", ""))
        transcript_confidence = audio_context.get("confidence", 0.5)
        transcript_length = len(audio_context.get("text", ""))

        # Adjust visual weight
        if has_visual:
            weights.visual = 0.5 + (num_objects * 0.05) + (visual_quality * 0.2)
        else:
            weights.visual = 0.1

        # Adjust audio/text weights
        if has_audio:
            base_audio_weight = 0.3 + (transcript_confidence * 0.2)
            weights.audio = base_audio_weight * 0.6  # 60% to audio
            weights.text = base_audio_weight * 0.4   # 40% to text

            # Boost text weight if transcript is substantial
            if transcript_length > 100:
                weights.text += 0.1
        else:
            weights.audio = 0.1
            weights.text = 0.1

        # Normalize
        weights.normalize()

        return weights

    def create_scene_summary(
        self,
        fused_scene: FusedScene,
        max_length: int = 150,
    ) -> str:
        """
        Create concise scene summary

        Args:
            fused_scene: Fused scene
            max_length: Maximum summary length

        Returns:
            Scene summary
        """
        parts = []

        # Time info
        duration = fused_scene.end_time - fused_scene.start_time
        parts.append(f"Scene {fused_scene.scene_id} ({duration:.1f}s)")

        # Visual elements
        if fused_scene.detected_objects:
            obj_str = ", ".join(fused_scene.detected_objects[:3])
            parts.append(f"showing {obj_str}")

        if fused_scene.detected_actions:
            action_str = ", ".join(fused_scene.detected_actions[:2])
            parts.append(f"with {action_str}")

        # Audio elements
        if fused_scene.transcript_text:
            # Take first sentence or 50 chars
            text = fused_scene.transcript_text
            if len(text) > 50:
                text = text[:47] + "..."
            parts.append(f"saying: \"{text}\"")

        summary = " ".join(parts)

        # Truncate if needed
        if len(summary) > max_length:
            summary = summary[:max_length - 3] + "..."

        return summary

    def extract_scene_keywords(
        self,
        fused_scene: FusedScene,
        top_k: int = 10,
    ) -> List[str]:
        """
        Extract keywords from fused scene

        Args:
            fused_scene: Fused scene
            top_k: Number of keywords

        Returns:
            List of keywords
        """
        keywords = []

        # Add objects
        keywords.extend(fused_scene.detected_objects)

        # Add actions
        keywords.extend(fused_scene.detected_actions)

        # Extract keywords from transcript
        if fused_scene.transcript_text:
            # Simple word extraction (in practice, use NLP)
            words = fused_scene.transcript_text.lower().split()
            # Filter common words
            stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for", "of", "with", "is", "was", "are", "were"}
            content_words = [w for w in words if w not in stopwords and len(w) > 3]
            keywords.extend(content_words[:5])

        # Deduplicate and limit
        unique_keywords = []
        seen = set()
        for kw in keywords:
            if kw.lower() not in seen:
                unique_keywords.append(kw)
                seen.add(kw.lower())

        return unique_keywords[:top_k]

    def compute_scene_similarity(
        self,
        scene1: FusedScene,
        scene2: FusedScene,
    ) -> float:
        """
        Compute similarity between two fused scenes

        Args:
            scene1: First scene
            scene2: Second scene

        Returns:
            Similarity score (0-1)
        """
        if scene1.fused_embedding is not None and scene2.fused_embedding is not None:
            # Use embedding similarity
            similarity = np.dot(scene1.fused_embedding, scene2.fused_embedding)
            similarity = max(0.0, min(1.0, similarity))
            return float(similarity)

        # Fallback: keyword overlap
        keywords1 = set(self.extract_scene_keywords(scene1))
        keywords2 = set(self.extract_scene_keywords(scene2))

        if not keywords1 or not keywords2:
            return 0.0

        # Jaccard similarity
        intersection = len(keywords1 & keywords2)
        union = len(keywords1 | keywords2)

        return intersection / union if union > 0 else 0.0


def fuse_visual_audio_context(
    scene_data: Dict[str, Any],
    visual_context: Dict[str, Any],
    audio_context: Dict[str, Any],
    weights: Optional[FusionWeights] = None,
) -> FusedScene:
    """
    Convenience function to fuse visual and audio context

    Args:
        scene_data: Scene data
        visual_context: Visual context
        audio_context: Audio context
        weights: Fusion weights

    Returns:
        FusedScene
    """
    fuser = VisualAudioFuser(default_weights=weights)
    return fuser.fuse_scene(scene_data, visual_context, audio_context)
