"""
Timeline builder for annotated video timeline
Create comprehensive timeline with all events, scenes, and annotations
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field
from datetime import timedelta

logger = logging.getLogger(__name__)


@dataclass
class TimelineEvent:
    """Single event in timeline"""
    timestamp: float
    event_type: str  # scene_start, scene_end, transcript, object, action, etc.
    duration: float = 0.0  # For events with duration
    description: str = ""
    importance: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TimelineSegment:
    """Timeline segment with overlapping events"""
    start_time: float
    end_time: float
    duration: float
    events: List[TimelineEvent] = field(default_factory=list)
    scene_id: Optional[int] = None
    summary: str = ""
    importance: float = 0.0


@dataclass
class VideoTimeline:
    """Complete annotated video timeline"""
    video_id: str
    duration: float
    segments: List[TimelineSegment]
    events: List[TimelineEvent]
    key_moments: List[Dict[str, Any]] = field(default_factory=list)
    chapters: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class TimelineBuilder:
    """
    Build annotated timeline from all video analysis components
    """

    def __init__(
        self,
        segment_duration: float = 5.0,
        min_event_importance: float = 0.3,
    ):
        """
        Initialize timeline builder

        Args:
            segment_duration: Default segment duration for timeline
            min_event_importance: Minimum importance for including events
        """
        self.segment_duration = segment_duration
        self.min_event_importance = min_event_importance

        logger.info(
            f"Initialized TimelineBuilder "
            f"(segment_duration={segment_duration}s)"
        )

    def build_timeline(
        self,
        video_id: str,
        duration: float,
        scenes: List[Dict[str, Any]],
        transcript_segments: Optional[List[Dict[str, Any]]] = None,
        visual_events: Optional[List[Dict[str, Any]]] = None,
        audio_events: Optional[List[Dict[str, Any]]] = None,
    ) -> VideoTimeline:
        """
        Build complete video timeline

        Args:
            video_id: Video identifier
            duration: Video duration
            scenes: Scene list
            transcript_segments: Transcript segments
            visual_events: Visual events (objects, actions detected)
            audio_events: Audio events


        Returns:
            VideoTimeline
        """
        logger.info(f"Building timeline for video {video_id} ({duration:.1f}s)")

        all_events = []

        # Add scene events
        all_events.extend(self._create_scene_events(scenes))

        # Add transcript events
        if transcript_segments:
            all_events.extend(self._create_transcript_events(transcript_segments))

        # Add visual events
        if visual_events:
            all_events.extend(self._create_visual_events(visual_events))

        # Add audio events
        if audio_events:
            all_events.extend(self._create_audio_events(audio_events))

        # Sort by timestamp
        all_events.sort(key=lambda x: x.timestamp)

        # Create timeline segments
        segments = self._create_timeline_segments(
            all_events, duration, scenes
        )

        # Identify key moments
        key_moments = self._identify_key_moments(all_events, segments)

        # Create chapters
        chapters = self._create_chapters(scenes, segments)

        return VideoTimeline(
            video_id=video_id,
            duration=duration,
            segments=segments,
            events=all_events,
            key_moments=key_moments,
            chapters=chapters,
            metadata={
                "num_events": len(all_events),
                "num_segments": len(segments),
                "num_key_moments": len(key_moments),
                "num_chapters": len(chapters),
            },
        )

    def _create_scene_events(
        self,
        scenes: List[Dict[str, Any]],
    ) -> List[TimelineEvent]:
        """Create events for scene boundaries"""
        events = []

        for scene in scenes:
            scene_id = scene.get("scene_number", scene.get("scene_id", 0))
            start_time = scene["start_time"]
            end_time = scene["end_time"]
            duration = end_time - start_time

            # Scene start event
            events.append(TimelineEvent(
                timestamp=start_time,
                event_type="scene_start",
                duration=duration,
                description=f"Scene {scene_id} begins",
                importance=0.5,
                metadata={
                    "scene_id": scene_id,
                    "scene_type": scene.get("scene_type"),
                    "transition": scene.get("transition_type"),
                },
            ))

            # Scene end event
            events.append(TimelineEvent(
                timestamp=end_time,
                event_type="scene_end",
                description=f"Scene {scene_id} ends",
                importance=0.3,
                metadata={"scene_id": scene_id},
            ))

        return events

    def _create_transcript_events(
        self,
        transcript_segments: List[Dict[str, Any]],
    ) -> List[TimelineEvent]:
        """Create events for transcript segments"""
        events = []

        for segment in transcript_segments:
            start_time = segment["start_time"]
            duration = segment["end_time"] - start_time
            text = segment.get("text", "")
            speaker = segment.get("speaker")

            # Determine importance based on length and speaker changes
            importance = min(1.0, len(text) / 200 + 0.3)

            desc = f"{speaker}: {text[:50]}..." if speaker else f"{text[:50]}..."

            events.append(TimelineEvent(
                timestamp=start_time,
                event_type="transcript",
                duration=duration,
                description=desc,
                importance=importance,
                metadata={
                    "text": text,
                    "speaker": speaker,
                    "confidence": segment.get("confidence"),
                },
            ))

        return events

    def _create_visual_events(
        self,
        visual_events: List[Dict[str, Any]],
    ) -> List[TimelineEvent]:
        """Create events for visual detections"""
        events = []

        for event in visual_events:
            timestamp = event.get("timestamp", event.get("start_time", 0.0))
            event_type = event.get("type", "visual")
            description = event.get("description", "")

            # Determine importance
            importance = event.get("importance", 0.5)
            if "object" in event:
                importance = 0.4
            if "action" in event:
                importance = 0.7
            if "face" in event:
                importance = 0.6

            events.append(TimelineEvent(
                timestamp=timestamp,
                event_type=f"visual_{event_type}",
                description=description,
                importance=importance,
                metadata=event,
            ))

        return events

    def _create_audio_events(
        self,
        audio_events: List[Dict[str, Any]],
    ) -> List[TimelineEvent]:
        """Create events for audio features"""
        events = []

        for event in audio_events:
            timestamp = event.get("timestamp", 0.0)
            event_type = event.get("type", "audio")
            description = event.get("description", "")

            events.append(TimelineEvent(
                timestamp=timestamp,
                event_type=f"audio_{event_type}",
                description=description,
                importance=event.get("importance", 0.4),
                metadata=event,
            ))

        return events

    def _create_timeline_segments(
        self,
        events: List[TimelineEvent],
        duration: float,
        scenes: List[Dict[str, Any]],
    ) -> List[TimelineSegment]:
        """Create timeline segments"""
        segments = []

        # Use scenes as primary segmentation
        for scene in scenes:
            scene_id = scene.get("scene_number", scene.get("scene_id", 0))
            start_time = scene["start_time"]
            end_time = scene["end_time"]

            # Find events in this scene
            scene_events = [
                e for e in events
                if start_time <= e.timestamp < end_time
            ]

            # Calculate segment importance
            importance = 0.0
            if scene_events:
                importance = sum(e.importance for e in scene_events) / len(scene_events)

            # Create summary
            summary = self._create_segment_summary(scene_events)

            segment = TimelineSegment(
                start_time=start_time,
                end_time=end_time,
                duration=end_time - start_time,
                events=scene_events,
                scene_id=scene_id,
                summary=summary,
                importance=importance,
            )

            segments.append(segment)

        return segments

    def _create_segment_summary(
        self,
        events: List[TimelineEvent],
    ) -> str:
        """Create summary for timeline segment"""
        if not events:
            return ""

        # Get most important events
        important_events = [e for e in events if e.importance >= 0.5]
        if not important_events:
            important_events = events[:3]  # Top 3 by order

        # Create summary
        descriptions = [e.description for e in important_events[:3]]
        return "; ".join(descriptions)

    def _identify_key_moments(
        self,
        events: List[TimelineEvent],
        segments: List[TimelineSegment],
    ) -> List[Dict[str, Any]]:
        """Identify key moments in timeline"""
        key_moments = []

        # High importance segments
        for segment in segments:
            if segment.importance >= 0.7:
                key_moments.append({
                    "timestamp": segment.start_time,
                    "type": "important_scene",
                    "description": segment.summary,
                    "importance": segment.importance,
                    "duration": segment.duration,
                })

        # High importance individual events
        for event in events:
            if event.importance >= 0.8:
                key_moments.append({
                    "timestamp": event.timestamp,
                    "type": event.event_type,
                    "description": event.description,
                    "importance": event.importance,
                    "duration": event.duration,
                })

        # Sort by importance
        key_moments.sort(key=lambda x: x["importance"], reverse=True)

        # Limit to top moments
        return key_moments[:20]

    def _create_chapters(
        self,
        scenes: List[Dict[str, Any]],
        segments: List[TimelineSegment],
    ) -> List[Dict[str, Any]]:
        """Create chapter divisions"""
        chapters = []

        # Group scenes into chapters based on importance changes
        current_chapter_start = 0.0
        current_chapter_scenes = []
        importance_threshold = 0.1

        for i, segment in enumerate(segments):
            current_chapter_scenes.append(segment)

            # Check if we should end chapter
            end_chapter = False

            # End chapter if importance changes significantly
            if i < len(segments) - 1:
                importance_diff = abs(
                    segment.importance - segments[i + 1].importance
                )
                if importance_diff > importance_threshold:
                    end_chapter = True

            # End chapter every ~5 scenes
            if len(current_chapter_scenes) >= 5:
                end_chapter = True

            # Last segment
            if i == len(segments) - 1:
                end_chapter = True

            if end_chapter and current_chapter_scenes:
                chapter_start = current_chapter_scenes[0].start_time
                chapter_end = current_chapter_scenes[-1].end_time

                # Create chapter title
                chapter_num = len(chapters) + 1
                title = f"Chapter {chapter_num}"

                # Create description from scene summaries
                summaries = [s.summary for s in current_chapter_scenes if s.summary]
                description = summaries[0] if summaries else ""

                chapters.append({
                    "chapter_number": chapter_num,
                    "title": title,
                    "start_time": chapter_start,
                    "end_time": chapter_end,
                    "duration": chapter_end - chapter_start,
                    "description": description,
                    "num_scenes": len(current_chapter_scenes),
                })

                current_chapter_scenes = []

        return chapters

    def export_timeline_json(
        self,
        timeline: VideoTimeline,
    ) -> Dict[str, Any]:
        """
        Export timeline to JSON format

        Args:
            timeline: Video timeline

        Returns:
            JSON-serializable dictionary
        """
        return {
            "video_id": timeline.video_id,
            "duration": timeline.duration,
            "segments": [
                {
                    "start_time": seg.start_time,
                    "end_time": seg.end_time,
                    "duration": seg.duration,
                    "scene_id": seg.scene_id,
                    "summary": seg.summary,
                    "importance": seg.importance,
                    "num_events": len(seg.events),
                }
                for seg in timeline.segments
            ],
            "key_moments": timeline.key_moments,
            "chapters": timeline.chapters,
            "metadata": timeline.metadata,
        }

    def export_timeline_vtt(
        self,
        timeline: VideoTimeline,
    ) -> str:
        """
        Export timeline to WebVTT format for video players

        Args:
            timeline: Video timeline

        Returns:
            WebVTT formatted string
        """
        lines = ["WEBVTT", ""]

        # Add chapters
        for chapter in timeline.chapters:
            start = self._format_timestamp(chapter["start_time"])
            end = self._format_timestamp(chapter["end_time"])

            lines.append(f"{start} --> {end}")
            lines.append(chapter["title"])
            if chapter["description"]:
                lines.append(chapter["description"])
            lines.append("")

        return "\n".join(lines)

    def _format_timestamp(self, seconds: float) -> str:
        """Format seconds to HH:MM:SS.mmm"""
        td = timedelta(seconds=seconds)
        hours = td.seconds // 3600
        minutes = (td.seconds % 3600) // 60
        secs = td.seconds % 60
        millis = td.microseconds // 1000

        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    def get_events_at_timestamp(
        self,
        timeline: VideoTimeline,
        timestamp: float,
        window: float = 1.0,
    ) -> List[TimelineEvent]:
        """
        Get events around a timestamp

        Args:
            timeline: Video timeline
            timestamp: Target timestamp
            window: Time window (seconds)

        Returns:
            List of events
        """
        start = timestamp - window / 2
        end = timestamp + window / 2

        events = [
            e for e in timeline.events
            if start <= e.timestamp <= end
        ]

        return events

    def get_segment_at_timestamp(
        self,
        timeline: VideoTimeline,
        timestamp: float,
    ) -> Optional[TimelineSegment]:
        """
        Get timeline segment at timestamp

        Args:
            timeline: Video timeline
            timestamp: Timestamp

        Returns:
            TimelineSegment or None
        """
        for segment in timeline.segments:
            if segment.start_time <= timestamp < segment.end_time:
                return segment

        return None


def build_video_timeline(
    video_id: str,
    duration: float,
    scenes: List[Dict[str, Any]],
    transcript_segments: Optional[List[Dict[str, Any]]] = None,
) -> VideoTimeline:
    """
    Convenience function to build video timeline

    Args:
        video_id: Video identifier
        duration: Video duration
        scenes: Scene list
        transcript_segments: Transcript segments

    Returns:
        VideoTimeline
    """
    builder = TimelineBuilder()
    return builder.build_timeline(
        video_id=video_id,
        duration=duration,
        scenes=scenes,
        transcript_segments=transcript_segments,
    )
