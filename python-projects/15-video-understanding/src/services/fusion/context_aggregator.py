"""
Context aggregator for comprehensive scene understanding
Aggregate all available context: visual, audio, text, objects, actions, speakers
"""

import logging
from typing import List, Optional, Dict, Any, Set
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class SceneContext:
    """Comprehensive context for a scene"""
    scene_id: int
    start_time: float
    end_time: float
    duration: float

    # Visual elements
    frames: List[Dict[str, Any]] = field(default_factory=list)
    keyframes: List[Dict[str, Any]] = field(default_factory=list)
    objects: List[str] = field(default_factory=list)
    object_counts: Dict[str, int] = field(default_factory=dict)
    actions: List[str] = field(default_factory=list)
    faces: List[Dict[str, Any]] = field(default_factory=list)
    text_regions: List[Dict[str, Any]] = field(default_factory=list)
    visual_summary: str = ""

    # Audio/transcript elements
    transcript_segments: List[Dict[str, Any]] = field(default_factory=list)
    full_transcript: str = ""
    speakers: List[str] = field(default_factory=list)
    speaker_turns: int = 0
    audio_features: Optional[Dict[str, Any]] = None
    language: Optional[str] = None

    # Scene classification
    scene_type: Optional[str] = None  # static, motion, dialogue, action
    transition_type: Optional[str] = None  # cut, fade, dissolve

    # Importance metrics
    visual_complexity: float = 0.0
    audio_activity: float = 0.0
    overall_importance: float = 0.0

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VideoContext:
    """Aggregated context for entire video"""
    video_id: str
    duration: float
    scene_contexts: List[SceneContext]

    # Global statistics
    total_scenes: int = 0
    total_frames: int = 0
    total_transcript_segments: int = 0

    # Unique elements across video
    all_objects: Set[str] = field(default_factory=set)
    all_actions: Set[str] = field(default_factory=set)
    all_speakers: Set[str] = field(default_factory=set)

    # Video-level summaries
    video_summary: str = ""
    key_moments: List[Dict[str, Any]] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)


class ContextAggregator:
    """
    Aggregate all available context for scenes
    Build comprehensive multi-modal understanding
    """

    def __init__(
        self,
        include_frame_details: bool = False,
        max_objects_per_scene: int = 20,
        max_actions_per_scene: int = 10,
    ):
        """
        Initialize context aggregator

        Args:
            include_frame_details: Include detailed frame information
            max_objects_per_scene: Maximum objects to keep per scene
            max_actions_per_scene: Maximum actions to keep per scene
        """
        self.include_frame_details = include_frame_details
        self.max_objects_per_scene = max_objects_per_scene
        self.max_actions_per_scene = max_actions_per_scene

        logger.info("Initialized ContextAggregator")

    def aggregate_scene_context(
        self,
        scene_data: Dict[str, Any],
        frames: Optional[List[Dict[str, Any]]] = None,
        transcript_segments: Optional[List[Dict[str, Any]]] = None,
        visual_analysis: Optional[Dict[str, Any]] = None,
        audio_analysis: Optional[Dict[str, Any]] = None,
    ) -> SceneContext:
        """
        Aggregate all context for a single scene

        Args:
            scene_data: Basic scene information
            frames: Frame data for this scene
            transcript_segments: Transcript segments in this scene
            visual_analysis: Visual analysis results
            audio_analysis: Audio analysis results

        Returns:
            SceneContext with aggregated information
        """
        scene_id = scene_data.get("scene_number", scene_data.get("scene_id", 0))
        start_time = scene_data["start_time"]
        end_time = scene_data["end_time"]
        duration = end_time - start_time

        context = SceneContext(
            scene_id=scene_id,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
        )

        # Aggregate frames
        if frames:
            context.frames = frames if self.include_frame_details else []
            context.keyframes = [
                f for f in frames if f.get("is_keyframe", False)
            ]

        # Aggregate visual elements
        if visual_analysis:
            context = self._aggregate_visual_elements(context, visual_analysis)

        # Aggregate audio/transcript
        if transcript_segments:
            context.transcript_segments = transcript_segments
            context = self._aggregate_transcript_elements(context, transcript_segments)

        if audio_analysis:
            context.audio_features = audio_analysis.get("features")
            context.language = audio_analysis.get("language")

        # Scene classification
        context.scene_type = scene_data.get("scene_type")
        context.transition_type = scene_data.get("transition_type")

        # Calculate importance metrics
        context = self._calculate_importance_metrics(context)

        # Add metadata
        context.metadata = {
            "num_frames": len(frames) if frames else 0,
            "num_keyframes": len(context.keyframes),
            "num_transcript_segments": len(context.transcript_segments),
            "has_faces": len(context.faces) > 0,
            "has_text": len(context.text_regions) > 0,
            "num_speakers": len(set(context.speakers)),
        }

        return context

    def _aggregate_visual_elements(
        self,
        context: SceneContext,
        visual_analysis: Dict[str, Any],
    ) -> SceneContext:
        """
        Aggregate visual elements from analysis

        Args:
            context: Scene context to update
            visual_analysis: Visual analysis results

        Returns:
            Updated context
        """
        # Objects
        if "objects" in visual_analysis:
            objects = visual_analysis["objects"]

            # Count object occurrences
            object_counts = defaultdict(int)
            all_objects = []

            if isinstance(objects, list):
                for obj in objects:
                    if isinstance(obj, dict):
                        obj_name = obj.get("label", obj.get("name", ""))
                    else:
                        obj_name = str(obj)

                    if obj_name:
                        all_objects.append(obj_name)
                        object_counts[obj_name] += 1

            # Sort by frequency and limit
            sorted_objects = sorted(
                object_counts.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:self.max_objects_per_scene]

            context.objects = [obj for obj, _ in sorted_objects]
            context.object_counts = dict(sorted_objects)

        # Actions
        if "actions" in visual_analysis:
            actions = visual_analysis["actions"]
            if isinstance(actions, list):
                context.actions = actions[:self.max_actions_per_scene]

        # Faces
        if "faces" in visual_analysis:
            context.faces = visual_analysis["faces"]

        # Text regions (OCR)
        if "text_regions" in visual_analysis:
            context.text_regions = visual_analysis["text_regions"]

        # Visual summary/description
        if "description" in visual_analysis:
            context.visual_summary = visual_analysis["description"]
        elif "caption" in visual_analysis:
            context.visual_summary = visual_analysis["caption"]

        return context

    def _aggregate_transcript_elements(
        self,
        context: SceneContext,
        transcript_segments: List[Dict[str, Any]],
    ) -> SceneContext:
        """
        Aggregate transcript elements

        Args:
            context: Scene context to update
            transcript_segments: Transcript segments

        Returns:
            Updated context
        """
        # Combine all text
        texts = [seg.get("text", "") for seg in transcript_segments]
        context.full_transcript = " ".join(texts)

        # Extract speakers
        speakers = []
        for seg in transcript_segments:
            speaker = seg.get("speaker")
            if speaker:
                speakers.append(speaker)

        context.speakers = speakers

        # Count speaker turns (changes)
        if len(speakers) > 1:
            turns = 1
            for i in range(1, len(speakers)):
                if speakers[i] != speakers[i - 1]:
                    turns += 1
            context.speaker_turns = turns

        return context

    def _calculate_importance_metrics(
        self,
        context: SceneContext,
    ) -> SceneContext:
        """
        Calculate importance metrics for scene

        Args:
            context: Scene context

        Returns:
            Updated context with importance scores
        """
        # Visual complexity
        visual_score = 0.0

        # More objects = more complex
        num_objects = len(context.objects)
        visual_score += min(1.0, num_objects / 10) * 0.3

        # Actions indicate activity
        num_actions = len(context.actions)
        visual_score += min(1.0, num_actions / 5) * 0.3

        # Faces indicate people/importance
        if context.faces:
            visual_score += 0.2

        # Text regions indicate information
        if context.text_regions:
            visual_score += 0.2

        context.visual_complexity = min(1.0, visual_score)

        # Audio activity
        audio_score = 0.0

        # Transcript presence
        if context.full_transcript:
            # Longer transcript = more activity
            words = len(context.full_transcript.split())
            audio_score += min(1.0, words / 100) * 0.4

        # Multiple speakers = dialogue
        num_speakers = len(set(context.speakers))
        if num_speakers > 1:
            audio_score += 0.3

        # Speaker turns indicate conversation
        if context.speaker_turns > 0:
            audio_score += min(1.0, context.speaker_turns / 5) * 0.3

        context.audio_activity = min(1.0, audio_score)

        # Overall importance (weighted combination)
        context.overall_importance = (
            0.5 * context.visual_complexity +
            0.5 * context.audio_activity
        )

        return context

    def aggregate_video_context(
        self,
        video_id: str,
        scene_contexts: List[SceneContext],
        video_metadata: Optional[Dict[str, Any]] = None,
    ) -> VideoContext:
        """
        Aggregate context across entire video

        Args:
            video_id: Video identifier
            scene_contexts: List of scene contexts
            video_metadata: Optional video metadata

        Returns:
            VideoContext with aggregated information
        """
        if not scene_contexts:
            return VideoContext(
                video_id=video_id,
                duration=0.0,
                scene_contexts=[],
            )

        # Calculate total duration
        duration = max(sc.end_time for sc in scene_contexts)

        # Count totals
        total_frames = sum(sc.metadata.get("num_frames", 0) for sc in scene_contexts)
        total_transcript_segments = sum(
            sc.metadata.get("num_transcript_segments", 0)
            for sc in scene_contexts
        )

        # Collect unique elements
        all_objects = set()
        all_actions = set()
        all_speakers = set()

        for sc in scene_contexts:
            all_objects.update(sc.objects)
            all_actions.update(sc.actions)
            all_speakers.update(sc.speakers)

        # Identify key moments (high importance scenes)
        key_moments = []
        threshold = 0.7  # Importance threshold

        for sc in scene_contexts:
            if sc.overall_importance >= threshold:
                key_moments.append({
                    "scene_id": sc.scene_id,
                    "start_time": sc.start_time,
                    "end_time": sc.end_time,
                    "importance": sc.overall_importance,
                    "summary": sc.visual_summary or sc.full_transcript[:100],
                })

        # Sort key moments by importance
        key_moments.sort(key=lambda x: x["importance"], reverse=True)

        # Create video-level summary
        video_summary = self._create_video_summary(scene_contexts)

        return VideoContext(
            video_id=video_id,
            duration=duration,
            scene_contexts=scene_contexts,
            total_scenes=len(scene_contexts),
            total_frames=total_frames,
            total_transcript_segments=total_transcript_segments,
            all_objects=all_objects,
            all_actions=all_actions,
            all_speakers=all_speakers,
            video_summary=video_summary,
            key_moments=key_moments,
            metadata=video_metadata or {},
        )

    def _create_video_summary(
        self,
        scene_contexts: List[SceneContext],
        max_length: int = 300,
    ) -> str:
        """
        Create high-level video summary

        Args:
            scene_contexts: Scene contexts
            max_length: Maximum summary length

        Returns:
            Video summary
        """
        # Get top scenes by importance
        top_scenes = sorted(
            scene_contexts,
            key=lambda x: x.overall_importance,
            reverse=True,
        )[:5]

        # Combine summaries
        parts = []
        for sc in top_scenes:
            if sc.visual_summary:
                parts.append(sc.visual_summary)
            elif sc.full_transcript:
                # Take first sentence
                text = sc.full_transcript
                if "." in text:
                    text = text.split(".")[0] + "."
                parts.append(text[:100])

        summary = " ".join(parts)

        # Truncate if needed
        if len(summary) > max_length:
            summary = summary[:max_length - 3] + "..."

        return summary

    def get_scene_timeline(
        self,
        video_context: VideoContext,
    ) -> List[Dict[str, Any]]:
        """
        Create timeline view of scenes

        Args:
            video_context: Video context

        Returns:
            List of timeline entries
        """
        timeline = []

        for sc in video_context.scene_contexts:
            entry = {
                "scene_id": sc.scene_id,
                "start_time": sc.start_time,
                "end_time": sc.end_time,
                "duration": sc.duration,
                "type": sc.scene_type,
                "importance": sc.overall_importance,
                "objects": sc.objects[:5],  # Top 5
                "speakers": list(set(sc.speakers)),
                "summary": sc.visual_summary or sc.full_transcript[:100],
            }
            timeline.append(entry)

        return timeline

    def get_context_statistics(
        self,
        video_context: VideoContext,
    ) -> Dict[str, Any]:
        """
        Get statistical summary of video context

        Args:
            video_context: Video context

        Returns:
            Statistics dictionary
        """
        scene_contexts = video_context.scene_contexts

        # Duration statistics
        scene_durations = [sc.duration for sc in scene_contexts]

        stats = {
            "video_id": video_context.video_id,
            "total_duration": video_context.duration,
            "num_scenes": video_context.total_scenes,
            "num_frames": video_context.total_frames,
            "num_transcript_segments": video_context.total_transcript_segments,

            # Scene statistics
            "avg_scene_duration": sum(scene_durations) / len(scene_durations) if scene_durations else 0,
            "min_scene_duration": min(scene_durations) if scene_durations else 0,
            "max_scene_duration": max(scene_durations) if scene_durations else 0,

            # Content statistics
            "unique_objects": len(video_context.all_objects),
            "unique_actions": len(video_context.all_actions),
            "unique_speakers": len(video_context.all_speakers),
            "num_key_moments": len(video_context.key_moments),

            # Scene type distribution
            "scene_types": self._count_scene_types(scene_contexts),

            # Importance distribution
            "high_importance_scenes": sum(
                1 for sc in scene_contexts if sc.overall_importance >= 0.7
            ),
            "medium_importance_scenes": sum(
                1 for sc in scene_contexts if 0.4 <= sc.overall_importance < 0.7
            ),
            "low_importance_scenes": sum(
                1 for sc in scene_contexts if sc.overall_importance < 0.4
            ),
        }

        return stats

    def _count_scene_types(
        self,
        scene_contexts: List[SceneContext],
    ) -> Dict[str, int]:
        """Count scenes by type"""
        type_counts = defaultdict(int)

        for sc in scene_contexts:
            scene_type = sc.scene_type or "unknown"
            type_counts[scene_type] += 1

        return dict(type_counts)

    def find_scenes_with_object(
        self,
        video_context: VideoContext,
        object_name: str,
    ) -> List[SceneContext]:
        """
        Find scenes containing a specific object

        Args:
            video_context: Video context
            object_name: Object to search for

        Returns:
            List of matching scene contexts
        """
        matching_scenes = []
        object_lower = object_name.lower()

        for sc in video_context.scene_contexts:
            if any(object_lower in obj.lower() for obj in sc.objects):
                matching_scenes.append(sc)

        return matching_scenes

    def find_scenes_with_speaker(
        self,
        video_context: VideoContext,
        speaker: str,
    ) -> List[SceneContext]:
        """
        Find scenes with specific speaker

        Args:
            video_context: Video context
            speaker: Speaker identifier

        Returns:
            List of matching scene contexts
        """
        matching_scenes = []

        for sc in video_context.scene_contexts:
            if speaker in sc.speakers:
                matching_scenes.append(sc)

        return matching_scenes


def aggregate_scene_context(
    scene_data: Dict[str, Any],
    frames: Optional[List[Dict[str, Any]]] = None,
    transcript_segments: Optional[List[Dict[str, Any]]] = None,
    visual_analysis: Optional[Dict[str, Any]] = None,
    audio_analysis: Optional[Dict[str, Any]] = None,
) -> SceneContext:
    """
    Convenience function to aggregate scene context

    Args:
        scene_data: Scene data
        frames: Frame data
        transcript_segments: Transcript segments
        visual_analysis: Visual analysis
        audio_analysis: Audio analysis

    Returns:
        SceneContext
    """
    aggregator = ContextAggregator()
    return aggregator.aggregate_scene_context(
        scene_data=scene_data,
        frames=frames,
        transcript_segments=transcript_segments,
        visual_analysis=visual_analysis,
        audio_analysis=audio_analysis,
    )
