"""
Scene summarizer for generating scene-level summaries
Include visual and audio context with key moment identification
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class KeyMoment:
    """Key moment within a scene"""
    timestamp: float
    description: str
    importance: float = 0.0
    moment_type: str = "general"  # general, action, dialogue, transition


@dataclass
class SceneSummary:
    """Scene-level summary"""
    scene_id: int
    start_time: float
    end_time: float
    duration: float

    # Summary
    summary_text: str
    key_moments: List[KeyMoment] = field(default_factory=list)

    # Context
    visual_summary: Optional[str] = None
    audio_summary: Optional[str] = None
    speakers: List[str] = field(default_factory=list)
    detected_objects: List[str] = field(default_factory=list)
    detected_actions: List[str] = field(default_factory=list)

    # Importance
    importance_score: float = 0.0

    # LLM info
    tokens_used: Dict[str, int] = field(default_factory=dict)

    metadata: Dict[str, Any] = field(default_factory=dict)


class SceneSummarizer:
    """
    Generate scene-level summaries
    Combine visual, audio, and transcript context
    """

    def __init__(
        self,
        llm_client=None,
        identify_key_moments: bool = True,
        min_importance_threshold: float = 0.5,
    ):
        """
        Initialize scene summarizer

        Args:
            llm_client: LLMClient instance
            identify_key_moments: Identify key moments in scenes
            min_importance_threshold: Minimum importance for key moments
        """
        self.llm_client = llm_client
        self.identify_key_moments = identify_key_moments
        self.min_importance_threshold = min_importance_threshold

        logger.info("Initialized SceneSummarizer")

    def summarize_scene(
        self,
        scene_data: Dict[str, Any],
        enriched_scene: Optional[Any] = None,
        transcript_segments: Optional[List[Dict[str, Any]]] = None,
        visual_context: Optional[Dict[str, Any]] = None,
        audio_context: Optional[Dict[str, Any]] = None,
    ) -> SceneSummary:
        """
        Generate summary for a single scene

        Args:
            scene_data: Scene information
            enriched_scene: EnrichedScene object
            transcript_segments: Transcript segments for scene
            visual_context: Visual analysis context
            audio_context: Audio analysis context

        Returns:
            SceneSummary
        """
        scene_id = scene_data.get("scene_number", scene_data.get("scene_id", 0))
        start_time = scene_data["start_time"]
        end_time = scene_data["end_time"]
        duration = end_time - start_time

        logger.debug(f"Summarizing scene {scene_id} ({duration:.1f}s)")

        # Use enriched scene if available
        if enriched_scene:
            return self._summarize_from_enriched_scene(enriched_scene)

        # Otherwise build summary from components
        context = self._prepare_scene_context(
            scene_data=scene_data,
            transcript_segments=transcript_segments,
            visual_context=visual_context,
            audio_context=audio_context,
        )

        # Generate summary
        if self.llm_client and context.get("has_content"):
            summary_text = self._generate_summary_with_llm(context)
            tokens_used = context.get("tokens_used", {})
        else:
            summary_text = self._generate_fallback_summary(context)
            tokens_used = {}

        # Extract visual and audio summaries
        visual_summary = self._create_visual_summary(context)
        audio_summary = self._create_audio_summary(context)

        # Identify key moments
        key_moments = []
        if self.identify_key_moments:
            key_moments = self._identify_key_moments_in_scene(
                scene_data=scene_data,
                context=context,
            )

        # Calculate importance
        importance_score = self._calculate_scene_importance(context, key_moments)

        return SceneSummary(
            scene_id=scene_id,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            summary_text=summary_text,
            key_moments=key_moments,
            visual_summary=visual_summary,
            audio_summary=audio_summary,
            speakers=context.get("speakers", []),
            detected_objects=context.get("objects", []),
            detected_actions=context.get("actions", []),
            importance_score=importance_score,
            tokens_used=tokens_used,
            metadata=context.get("metadata", {}),
        )

    def _summarize_from_enriched_scene(self, enriched_scene: Any) -> SceneSummary:
        """Create summary from enriched scene"""
        # Extract key moments from enriched scene
        key_moments = []
        if hasattr(enriched_scene, "fused_scene") and enriched_scene.fused_scene:
            # Check for important actions/events
            if enriched_scene.fused_scene.detected_actions:
                for action in enriched_scene.fused_scene.detected_actions[:3]:
                    key_moments.append(KeyMoment(
                        timestamp=enriched_scene.start_time,
                        description=action,
                        importance=0.7,
                        moment_type="action",
                    ))

        # Visual summary
        visual_summary = None
        if enriched_scene.fused_scene and enriched_scene.fused_scene.visual_description:
            visual_summary = enriched_scene.fused_scene.visual_description

        # Audio summary
        audio_summary = None
        if enriched_scene.fused_scene and enriched_scene.fused_scene.transcript_text:
            audio_summary = enriched_scene.fused_scene.transcript_text

        return SceneSummary(
            scene_id=enriched_scene.scene_id,
            start_time=enriched_scene.start_time,
            end_time=enriched_scene.end_time,
            duration=enriched_scene.duration,
            summary_text=enriched_scene.description or "No description available",
            key_moments=key_moments,
            visual_summary=visual_summary,
            audio_summary=audio_summary,
            speakers=enriched_scene.scene_context.speakers if hasattr(enriched_scene, "scene_context") else [],
            detected_objects=enriched_scene.fused_scene.detected_objects if enriched_scene.fused_scene else [],
            detected_actions=enriched_scene.fused_scene.detected_actions if enriched_scene.fused_scene else [],
            importance_score=enriched_scene.fused_scene.importance_score if enriched_scene.fused_scene else 0.0,
            tokens_used={},
            metadata=enriched_scene.metadata if hasattr(enriched_scene, "metadata") else {},
        )

    def _prepare_scene_context(
        self,
        scene_data: Dict[str, Any],
        transcript_segments: Optional[List[Dict[str, Any]]],
        visual_context: Optional[Dict[str, Any]],
        audio_context: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Prepare context for scene summarization"""
        context = {
            "scene_id": scene_data.get("scene_number", scene_data.get("scene_id", 0)),
            "start_time": scene_data["start_time"],
            "end_time": scene_data["end_time"],
            "duration": scene_data["end_time"] - scene_data["start_time"],
        }

        # Transcript
        if transcript_segments:
            texts = [seg.get("text", "") for seg in transcript_segments]
            context["transcript"] = " ".join(texts)
            context["speakers"] = list(set(
                seg.get("speaker") for seg in transcript_segments if seg.get("speaker")
            ))
        else:
            context["transcript"] = ""
            context["speakers"] = []

        # Visual context
        if visual_context:
            context["objects"] = visual_context.get("objects", [])
            context["actions"] = visual_context.get("actions", [])
            context["visual_description"] = visual_context.get("description", "")
        else:
            context["objects"] = []
            context["actions"] = []
            context["visual_description"] = ""

        # Audio context
        if audio_context:
            context["audio_features"] = audio_context.get("features", {})
        else:
            context["audio_features"] = {}

        # Check if we have content
        context["has_content"] = bool(
            context["transcript"] or context["visual_description"] or
            context["objects"] or context["actions"]
        )

        return context

    def _generate_summary_with_llm(self, context: Dict[str, Any]) -> str:
        """Generate summary using LLM"""
        prompt_parts = []

        prompt_parts.append(
            f"Scene {context['scene_id']} "
            f"({context['start_time']:.1f}s - {context['end_time']:.1f}s, "
            f"{context['duration']:.1f}s)"
        )

        if context.get("visual_description"):
            prompt_parts.append(f"Visual: {context['visual_description']}")

        if context.get("objects"):
            prompt_parts.append(f"Objects: {', '.join(context['objects'][:5])}")

        if context.get("actions"):
            prompt_parts.append(f"Actions: {', '.join(context['actions'][:3])}")

        if context.get("transcript"):
            transcript = context["transcript"]
            if len(transcript) > 500:
                transcript = transcript[:500] + "..."
            prompt_parts.append(f"Dialogue: {transcript}")

        if context.get("speakers"):
            prompt_parts.append(f"Speakers: {', '.join(context['speakers'])}")

        prompt = "\n".join(prompt_parts)
        prompt += "\n\nProvide a concise 2-3 sentence summary of this scene:"

        try:
            response = self.llm_client.generate(
                prompt=prompt,
                max_tokens=200,
                temperature=0.3,
                system_prompt="You are summarizing a video scene. Be concise and factual.",
            )
            context["tokens_used"] = response.get("tokens", {})
            return response["text"]
        except Exception as e:
            logger.warning(f"LLM generation failed: {e}")
            return self._generate_fallback_summary(context)

    def _generate_fallback_summary(self, context: Dict[str, Any]) -> str:
        """Generate fallback summary without LLM"""
        parts = []

        if context.get("visual_description"):
            parts.append(context["visual_description"])
        elif context.get("objects"):
            parts.append(f"Scene shows {', '.join(context['objects'][:3])}")

        if context.get("actions"):
            parts.append(f"with {', '.join(context['actions'][:2])}")

        if context.get("transcript"):
            transcript = context["transcript"]
            if len(transcript) > 100:
                transcript = transcript[:100] + "..."
            parts.append(f"Dialogue: '{transcript}'")

        if not parts:
            return f"Scene {context['scene_id']} ({context['duration']:.1f}s)"

        return " ".join(parts)

    def _create_visual_summary(self, context: Dict[str, Any]) -> Optional[str]:
        """Create visual summary"""
        parts = []

        if context.get("visual_description"):
            parts.append(context["visual_description"])

        if context.get("objects"):
            parts.append(f"Objects: {', '.join(context['objects'][:5])}")

        if context.get("actions"):
            parts.append(f"Actions: {', '.join(context['actions'][:3])}")

        return " | ".join(parts) if parts else None

    def _create_audio_summary(self, context: Dict[str, Any]) -> Optional[str]:
        """Create audio summary"""
        if context.get("transcript"):
            transcript = context["transcript"]
            if len(transcript) > 200:
                transcript = transcript[:200] + "..."
            return transcript

        return None

    def _identify_key_moments_in_scene(
        self,
        scene_data: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[KeyMoment]:
        """Identify key moments within scene"""
        key_moments = []

        # Action-based moments
        for action in context.get("actions", [])[:3]:
            key_moments.append(KeyMoment(
                timestamp=context["start_time"],
                description=action,
                importance=0.7,
                moment_type="action",
            ))

        # Speaker transitions
        speakers = context.get("speakers", [])
        if len(speakers) > 1:
            key_moments.append(KeyMoment(
                timestamp=context["start_time"],
                description=f"Dialogue between {', '.join(speakers)}",
                importance=0.6,
                moment_type="dialogue",
            ))

        # Filter by importance threshold
        key_moments = [
            m for m in key_moments
            if m.importance >= self.min_importance_threshold
        ]

        return key_moments

    def _calculate_scene_importance(
        self,
        context: Dict[str, Any],
        key_moments: List[KeyMoment],
    ) -> float:
        """Calculate scene importance score"""
        score = 0.0

        # Key moments contribute
        if key_moments:
            score += 0.3

        # Actions contribute
        num_actions = len(context.get("actions", []))
        score += min(0.3, num_actions * 0.1)

        # Dialogue contributes
        if context.get("transcript"):
            score += 0.2

        # Objects contribute
        num_objects = len(context.get("objects", []))
        score += min(0.2, num_objects * 0.05)

        return min(1.0, score)

    def summarize_scenes_batch(
        self,
        scenes_data: List[Dict[str, Any]],
        enriched_scenes: Optional[List[Any]] = None,
    ) -> List[SceneSummary]:
        """
        Summarize multiple scenes in batch

        Args:
            scenes_data: List of scene data dicts
            enriched_scenes: Optional enriched scenes

        Returns:
            List of SceneSummary objects
        """
        summaries = []

        # Create lookup for enriched scenes
        enriched_lookup = {}
        if enriched_scenes:
            for enriched in enriched_scenes:
                enriched_lookup[enriched.scene_id] = enriched

        for scene in scenes_data:
            try:
                scene_id = scene.get("scene_number", scene.get("scene_id", 0))
                enriched = enriched_lookup.get(scene_id)

                summary = self.summarize_scene(
                    scene_data=scene,
                    enriched_scene=enriched,
                )
                summaries.append(summary)
            except Exception as e:
                logger.error(f"Failed to summarize scene {scene.get('scene_id')}: {e}")

        return summaries

    def export_summary_to_dict(self, summary: SceneSummary) -> Dict[str, Any]:
        """Export summary to dictionary"""
        return {
            "scene_id": summary.scene_id,
            "start_time": summary.start_time,
            "end_time": summary.end_time,
            "duration": summary.duration,
            "summary_text": summary.summary_text,
            "key_moments": [
                {
                    "timestamp": m.timestamp,
                    "description": m.description,
                    "importance": m.importance,
                    "moment_type": m.moment_type,
                }
                for m in summary.key_moments
            ],
            "visual_summary": summary.visual_summary,
            "audio_summary": summary.audio_summary,
            "speakers": summary.speakers,
            "detected_objects": summary.detected_objects,
            "detected_actions": summary.detected_actions,
            "importance_score": summary.importance_score,
            "tokens_used": summary.tokens_used,
            "metadata": summary.metadata,
        }


def summarize_scene(
    scene_data: Dict[str, Any],
    enriched_scene: Optional[Any] = None,
    llm_client=None,
) -> SceneSummary:
    """
    Convenience function to summarize scene

    Args:
        scene_data: Scene data
        enriched_scene: Enriched scene
        llm_client: LLMClient instance

    Returns:
        SceneSummary
    """
    summarizer = SceneSummarizer(llm_client=llm_client)
    return summarizer.summarize_scene(
        scene_data=scene_data,
        enriched_scene=enriched_scene,
    )
