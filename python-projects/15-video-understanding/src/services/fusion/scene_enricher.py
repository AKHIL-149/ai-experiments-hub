"""
Scene enricher for comprehensive scene enrichment
Combine all analysis results into enriched scene representation
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from src.services.fusion.temporal_aligner import TemporalAligner, AlignmentResult
from src.services.fusion.visual_audio_fuser import VisualAudioFuser, FusedScene, FusionWeights
from src.services.fusion.context_aggregator import ContextAggregator, SceneContext
from src.services.fusion.timeline_builder import TimelineBuilder, TimelineSegment

logger = logging.getLogger(__name__)


@dataclass
class EnrichedScene:
    """Fully enriched scene with all analysis results"""
    scene_id: int
    start_time: float
    end_time: float
    duration: float

    # Fusion results
    fused_scene: Optional[FusedScene] = None
    scene_context: Optional[SceneContext] = None
    timeline_segment: Optional[TimelineSegment] = None

    # Alignment results
    alignment_quality: float = 0.0
    transcript_segments: List[Dict[str, Any]] = field(default_factory=list)

    # Summary fields
    title: Optional[str] = None
    description: Optional[str] = None
    keywords: List[str] = field(default_factory=list)

    # Database fields
    enrichment_timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoEnrichmentResult:
    """Complete video enrichment result"""
    video_id: str
    enriched_scenes: List[EnrichedScene]
    total_scenes: int
    enrichment_stats: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)


class SceneEnricher:
    """
    Enrich scenes with all available analysis results
    Combines visual, audio, temporal, and contextual data
    """

    def __init__(
        self,
        temporal_aligner: Optional[TemporalAligner] = None,
        visual_audio_fuser: Optional[VisualAudioFuser] = None,
        context_aggregator: Optional[ContextAggregator] = None,
        timeline_builder: Optional[TimelineBuilder] = None,
        auto_generate_titles: bool = True,
    ):
        """
        Initialize scene enricher

        Args:
            temporal_aligner: Temporal alignment service
            visual_audio_fuser: Visual-audio fusion service
            context_aggregator: Context aggregation service
            timeline_builder: Timeline building service
            auto_generate_titles: Auto-generate scene titles
        """
        self.temporal_aligner = temporal_aligner or TemporalAligner()
        self.visual_audio_fuser = visual_audio_fuser or VisualAudioFuser()
        self.context_aggregator = context_aggregator or ContextAggregator()
        self.timeline_builder = timeline_builder or TimelineBuilder()
        self.auto_generate_titles = auto_generate_titles

        logger.info("Initialized SceneEnricher")

    def enrich_scene(
        self,
        scene_data: Dict[str, Any],
        frames: Optional[List[Dict[str, Any]]] = None,
        transcript_segments: Optional[List[Dict[str, Any]]] = None,
        visual_analysis: Optional[Dict[str, Any]] = None,
        audio_analysis: Optional[Dict[str, Any]] = None,
    ) -> EnrichedScene:
        """
        Enrich a single scene with all available data

        Args:
            scene_data: Scene information
            frames: Frame data for the scene
            transcript_segments: Transcript segments
            visual_analysis: Visual analysis results
            audio_analysis: Audio analysis results

        Returns:
            EnrichedScene
        """
        scene_id = scene_data.get("scene_number", scene_data.get("scene_id", 0))
        start_time = scene_data["start_time"]
        end_time = scene_data["end_time"]
        duration = end_time - start_time

        logger.debug(f"Enriching scene {scene_id} ({start_time:.1f}s - {end_time:.1f}s)")

        # Initialize enriched scene
        enriched_scene = EnrichedScene(
            scene_id=scene_id,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            enrichment_timestamp=datetime.now(),
        )

        # Temporal alignment
        if transcript_segments:
            aligned_segments = self._align_transcript_for_scene(
                scene_data, transcript_segments
            )
            enriched_scene.transcript_segments = aligned_segments["segments"]
            enriched_scene.alignment_quality = aligned_segments.get("quality", 0.0)

        # Visual-audio fusion
        if visual_analysis or audio_analysis:
            visual_ctx = visual_analysis or {}
            audio_ctx = audio_analysis or {}

            # Add transcript text to audio context
            if enriched_scene.transcript_segments:
                audio_ctx["text"] = " ".join(
                    seg.get("text", "") for seg in enriched_scene.transcript_segments
                )
                audio_ctx["speakers"] = list(set(
                    seg.get("speaker") for seg in enriched_scene.transcript_segments
                    if seg.get("speaker")
                ))

            fused_scene = self.visual_audio_fuser.fuse_scene(
                scene_data=scene_data,
                visual_context=visual_ctx,
                audio_context=audio_ctx,
            )
            enriched_scene.fused_scene = fused_scene

        # Context aggregation
        scene_context = self.context_aggregator.aggregate_scene_context(
            scene_data=scene_data,
            frames=frames,
            transcript_segments=enriched_scene.transcript_segments,
            visual_analysis=visual_analysis,
            audio_analysis=audio_analysis,
        )
        enriched_scene.scene_context = scene_context

        # Generate title and description
        if self.auto_generate_titles:
            enriched_scene.title = self._generate_scene_title(enriched_scene)
            enriched_scene.description = self._generate_scene_description(enriched_scene)

        # Extract keywords
        enriched_scene.keywords = self._extract_scene_keywords(enriched_scene)

        # Build metadata
        enriched_scene.metadata = self._build_scene_metadata(enriched_scene)

        return enriched_scene

    def enrich_video_scenes(
        self,
        video_id: str,
        scenes: List[Dict[str, Any]],
        all_frames: Optional[List[Dict[str, Any]]] = None,
        all_transcript_segments: Optional[List[Dict[str, Any]]] = None,
        visual_analyses: Optional[Dict[int, Dict[str, Any]]] = None,
        audio_analyses: Optional[Dict[int, Dict[str, Any]]] = None,
    ) -> VideoEnrichmentResult:
        """
        Enrich all scenes in a video

        Args:
            video_id: Video identifier
            scenes: List of scenes
            all_frames: All frames (will be filtered per scene)
            all_transcript_segments: All transcript segments
            visual_analyses: Visual analysis per scene (scene_id -> analysis)
            audio_analyses: Audio analysis per scene (scene_id -> analysis)

        Returns:
            VideoEnrichmentResult
        """
        logger.info(f"Enriching {len(scenes)} scenes for video {video_id}")

        enriched_scenes = []
        errors = []

        for scene in scenes:
            try:
                scene_id = scene.get("scene_number", scene.get("scene_id", 0))

                # Filter frames for this scene
                scene_frames = None
                if all_frames:
                    scene_frames = [
                        f for f in all_frames
                        if scene["start_time"] <= f.get("timestamp", 0) < scene["end_time"]
                    ]

                # Filter transcript segments for this scene
                scene_transcript = None
                if all_transcript_segments:
                    scene_transcript = [
                        seg for seg in all_transcript_segments
                        if scene["start_time"] <= seg.get("start_time", 0) < scene["end_time"]
                    ]

                # Get scene-specific analyses
                visual_analysis = visual_analyses.get(scene_id) if visual_analyses else None
                audio_analysis = audio_analyses.get(scene_id) if audio_analyses else None

                # Enrich scene
                enriched_scene = self.enrich_scene(
                    scene_data=scene,
                    frames=scene_frames,
                    transcript_segments=scene_transcript,
                    visual_analysis=visual_analysis,
                    audio_analysis=audio_analysis,
                )

                enriched_scenes.append(enriched_scene)

            except Exception as e:
                logger.error(f"Error enriching scene {scene_id}: {e}")
                errors.append({
                    "scene_id": scene_id,
                    "error": str(e),
                })

        # Calculate enrichment stats
        stats = self._calculate_enrichment_stats(enriched_scenes)

        return VideoEnrichmentResult(
            video_id=video_id,
            enriched_scenes=enriched_scenes,
            total_scenes=len(scenes),
            enrichment_stats=stats,
            errors=errors,
        )

    def _align_transcript_for_scene(
        self,
        scene_data: Dict[str, Any],
        transcript_segments: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Align transcript segments for a single scene

        Args:
            scene_data: Scene data
            transcript_segments: All transcript segments

        Returns:
            Dict with aligned segments and quality score
        """
        start_time = scene_data["start_time"]
        end_time = scene_data["end_time"]

        # Filter segments overlapping with scene
        overlapping_segments = []
        for seg in transcript_segments:
            seg_start = seg.get("start_time", 0)
            seg_end = seg.get("end_time", seg_start)

            # Check for overlap
            if seg_start < end_time and seg_end > start_time:
                overlapping_segments.append(seg)

        # Calculate alignment quality
        if overlapping_segments:
            total_overlap = sum(
                min(seg.get("end_time", 0), end_time) - max(seg.get("start_time", 0), start_time)
                for seg in overlapping_segments
            )
            scene_duration = end_time - start_time
            quality = total_overlap / scene_duration if scene_duration > 0 else 0.0
        else:
            quality = 0.0

        return {
            "segments": overlapping_segments,
            "quality": quality,
        }

    def _generate_scene_title(self, enriched_scene: EnrichedScene) -> str:
        """
        Generate title for enriched scene

        Args:
            enriched_scene: Enriched scene

        Returns:
            Scene title
        """
        scene_id = enriched_scene.scene_id

        # Try to use context
        if enriched_scene.scene_context:
            ctx = enriched_scene.scene_context

            # Use dominant object or action
            if ctx.detected_objects:
                dominant_object = ctx.detected_objects[0]
                return f"Scene {scene_id}: {dominant_object}"

            if ctx.detected_actions:
                dominant_action = ctx.detected_actions[0]
                return f"Scene {scene_id}: {dominant_action}"

            # Use speaker
            if ctx.speakers:
                speaker = ctx.speakers[0]
                return f"Scene {scene_id}: {speaker} speaking"

        # Try fused scene
        if enriched_scene.fused_scene and enriched_scene.fused_scene.visual_description:
            desc = enriched_scene.fused_scene.visual_description
            # Take first few words
            words = desc.split()[:4]
            return f"Scene {scene_id}: {' '.join(words)}"

        # Default
        return f"Scene {scene_id}"

    def _generate_scene_description(self, enriched_scene: EnrichedScene) -> str:
        """
        Generate description for enriched scene

        Args:
            enriched_scene: Enriched scene

        Returns:
            Scene description
        """
        parts = []

        # Use fused scene unified description
        if enriched_scene.fused_scene and enriched_scene.fused_scene.unified_description:
            return enriched_scene.fused_scene.unified_description

        # Build from context
        if enriched_scene.scene_context:
            ctx = enriched_scene.scene_context

            # Visual elements
            if ctx.detected_objects:
                obj_str = ", ".join(ctx.detected_objects[:3])
                parts.append(f"Objects: {obj_str}")

            if ctx.detected_actions:
                action_str = ", ".join(ctx.detected_actions[:2])
                parts.append(f"Actions: {action_str}")

            # Audio elements
            if ctx.full_transcript_text:
                text = ctx.full_transcript_text
                if len(text) > 100:
                    text = text[:97] + "..."
                parts.append(f"Dialogue: \"{text}\"")

            if ctx.speakers:
                speaker_str = ", ".join(ctx.speakers)
                parts.append(f"Speakers: {speaker_str}")

        if parts:
            return " | ".join(parts)

        return f"Scene from {enriched_scene.start_time:.1f}s to {enriched_scene.end_time:.1f}s"

    def _extract_scene_keywords(self, enriched_scene: EnrichedScene) -> List[str]:
        """
        Extract keywords from enriched scene

        Args:
            enriched_scene: Enriched scene

        Returns:
            List of keywords
        """
        keywords = []

        # From fused scene
        if enriched_scene.fused_scene:
            keywords.extend(enriched_scene.fused_scene.detected_objects)
            keywords.extend(enriched_scene.fused_scene.detected_actions)

        # From context
        if enriched_scene.scene_context:
            keywords.extend(enriched_scene.scene_context.detected_objects)
            keywords.extend(enriched_scene.scene_context.detected_actions)

            # Extract from transcript (simple word extraction)
            if enriched_scene.scene_context.full_transcript_text:
                text = enriched_scene.scene_context.full_transcript_text.lower()
                words = text.split()

                # Filter stopwords
                stopwords = {
                    "the", "a", "an", "and", "or", "but", "in", "on", "at",
                    "to", "for", "of", "with", "is", "was", "are", "were",
                    "been", "be", "have", "has", "had", "do", "does", "did",
                    "will", "would", "should", "could", "may", "might", "must",
                    "can", "this", "that", "these", "those", "i", "you", "he",
                    "she", "it", "we", "they", "what", "which", "who", "when",
                    "where", "why", "how",
                }

                content_words = [
                    w for w in words
                    if w not in stopwords and len(w) > 3
                ]

                keywords.extend(content_words[:5])

        # Deduplicate while preserving order
        seen = set()
        unique_keywords = []
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower not in seen:
                unique_keywords.append(kw)
                seen.add(kw_lower)

        return unique_keywords[:10]  # Top 10

    def _build_scene_metadata(self, enriched_scene: EnrichedScene) -> Dict[str, Any]:
        """
        Build metadata dictionary for scene

        Args:
            enriched_scene: Enriched scene

        Returns:
            Metadata dictionary
        """
        metadata = {
            "duration": enriched_scene.duration,
            "enrichment_timestamp": enriched_scene.enrichment_timestamp.isoformat() if enriched_scene.enrichment_timestamp else None,
        }

        # Alignment info
        metadata["alignment_quality"] = enriched_scene.alignment_quality
        metadata["num_transcript_segments"] = len(enriched_scene.transcript_segments)

        # Fusion info
        if enriched_scene.fused_scene:
            metadata["importance_score"] = enriched_scene.fused_scene.importance_score
            metadata["num_keyframes"] = len(enriched_scene.fused_scene.keyframe_indices)
            metadata["has_visual"] = enriched_scene.fused_scene.metadata.get("has_visual", False)
            metadata["has_audio"] = enriched_scene.fused_scene.metadata.get("has_audio", False)
            metadata["has_transcript"] = enriched_scene.fused_scene.metadata.get("has_transcript", False)

        # Context info
        if enriched_scene.scene_context:
            metadata["num_frames"] = enriched_scene.scene_context.num_frames
            metadata["num_objects"] = len(enriched_scene.scene_context.detected_objects)
            metadata["num_actions"] = len(enriched_scene.scene_context.detected_actions)
            metadata["num_speakers"] = len(enriched_scene.scene_context.speakers)
            metadata["has_faces"] = enriched_scene.scene_context.num_faces > 0
            metadata["has_text"] = enriched_scene.scene_context.num_text_regions > 0

        return metadata

    def _calculate_enrichment_stats(
        self,
        enriched_scenes: List[EnrichedScene],
    ) -> Dict[str, Any]:
        """
        Calculate enrichment statistics

        Args:
            enriched_scenes: List of enriched scenes

        Returns:
            Statistics dictionary
        """
        if not enriched_scenes:
            return {}

        stats = {
            "total_scenes": len(enriched_scenes),
            "scenes_with_transcript": 0,
            "scenes_with_visual": 0,
            "scenes_with_audio": 0,
            "avg_alignment_quality": 0.0,
            "avg_importance_score": 0.0,
            "total_keywords": 0,
        }

        total_alignment_quality = 0.0
        total_importance = 0.0

        for scene in enriched_scenes:
            if scene.transcript_segments:
                stats["scenes_with_transcript"] += 1

            if scene.fused_scene:
                if scene.fused_scene.metadata.get("has_visual"):
                    stats["scenes_with_visual"] += 1
                if scene.fused_scene.metadata.get("has_audio"):
                    stats["scenes_with_audio"] += 1

                total_importance += scene.fused_scene.importance_score

            total_alignment_quality += scene.alignment_quality
            stats["total_keywords"] += len(scene.keywords)

        # Calculate averages
        stats["avg_alignment_quality"] = total_alignment_quality / len(enriched_scenes)
        stats["avg_importance_score"] = total_importance / len(enriched_scenes)

        return stats

    def export_enriched_scene_to_dict(
        self,
        enriched_scene: EnrichedScene,
    ) -> Dict[str, Any]:
        """
        Export enriched scene to dictionary for database storage

        Args:
            enriched_scene: Enriched scene

        Returns:
            Dictionary representation
        """
        return {
            "scene_id": enriched_scene.scene_id,
            "start_time": enriched_scene.start_time,
            "end_time": enriched_scene.end_time,
            "duration": enriched_scene.duration,
            "title": enriched_scene.title,
            "description": enriched_scene.description,
            "keywords": enriched_scene.keywords,
            "alignment_quality": enriched_scene.alignment_quality,
            "importance_score": enriched_scene.fused_scene.importance_score if enriched_scene.fused_scene else 0.0,
            "metadata": enriched_scene.metadata,
            "enrichment_timestamp": enriched_scene.enrichment_timestamp.isoformat() if enriched_scene.enrichment_timestamp else None,
        }

    def export_video_enrichment_to_dict(
        self,
        video_enrichment: VideoEnrichmentResult,
    ) -> Dict[str, Any]:
        """
        Export video enrichment result to dictionary

        Args:
            video_enrichment: Video enrichment result

        Returns:
            Dictionary representation
        """
        return {
            "video_id": video_enrichment.video_id,
            "total_scenes": video_enrichment.total_scenes,
            "enriched_scenes": [
                self.export_enriched_scene_to_dict(scene)
                for scene in video_enrichment.enriched_scenes
            ],
            "enrichment_stats": video_enrichment.enrichment_stats,
            "errors": video_enrichment.errors,
        }


def enrich_scene(
    scene_data: Dict[str, Any],
    frames: Optional[List[Dict[str, Any]]] = None,
    transcript_segments: Optional[List[Dict[str, Any]]] = None,
    visual_analysis: Optional[Dict[str, Any]] = None,
    audio_analysis: Optional[Dict[str, Any]] = None,
) -> EnrichedScene:
    """
    Convenience function to enrich a scene

    Args:
        scene_data: Scene data
        frames: Frame data
        transcript_segments: Transcript segments
        visual_analysis: Visual analysis
        audio_analysis: Audio analysis

    Returns:
        EnrichedScene
    """
    enricher = SceneEnricher()
    return enricher.enrich_scene(
        scene_data=scene_data,
        frames=frames,
        transcript_segments=transcript_segments,
        visual_analysis=visual_analysis,
        audio_analysis=audio_analysis,
    )
