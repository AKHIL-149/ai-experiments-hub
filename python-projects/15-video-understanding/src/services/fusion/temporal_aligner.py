"""
Temporal aligner for multi-modal synchronization
Align transcript segments with scenes and frames based on timestamps
"""

import logging
from typing import List, Optional, Dict, Tuple, Any
from dataclasses import dataclass, field
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AlignedSegment:
    """Aligned segment with visual and audio context"""
    scene_id: int
    scene_start: float
    scene_end: float
    transcript_segments: List[Dict[str, Any]]
    frame_indices: List[int]
    frame_timestamps: List[float]
    alignment_quality: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlignmentResult:
    """Result of temporal alignment"""
    video_id: str
    aligned_segments: List[AlignedSegment]
    total_scenes: int
    total_transcript_segments: int
    alignment_coverage: float  # Percentage of transcript aligned
    drift_detected: bool = False
    drift_amount: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


class TemporalAligner:
    """
    Align transcript segments with scenes and frames
    Handle timing drift and synchronization issues
    """

    def __init__(
        self,
        tolerance: float = 0.5,
        drift_threshold: float = 1.0,
        auto_correct_drift: bool = True,
    ):
        """
        Initialize temporal aligner

        Args:
            tolerance: Time tolerance for alignment (seconds)
            drift_threshold: Threshold for detecting drift (seconds)
            auto_correct_drift: Automatically correct timing drift
        """
        self.tolerance = tolerance
        self.drift_threshold = drift_threshold
        self.auto_correct_drift = auto_correct_drift

        logger.info(
            f"Initialized TemporalAligner (tolerance={tolerance}s, "
            f"drift_threshold={drift_threshold}s)"
        )

    def align_transcript_with_scenes(
        self,
        video_id: str,
        scenes: List[Dict[str, Any]],
        transcript_segments: List[Dict[str, Any]],
        frames: Optional[List[Dict[str, Any]]] = None,
    ) -> AlignmentResult:
        """
        Align transcript segments with scenes

        Args:
            video_id: Video identifier
            scenes: List of scene dictionaries with start_time, end_time
            transcript_segments: List of transcript dictionaries with start_time, end_time, text
            frames: Optional list of frame dictionaries with timestamp

        Returns:
            AlignmentResult with aligned segments
        """
        logger.info(
            f"Aligning {len(transcript_segments)} transcript segments "
            f"with {len(scenes)} scenes for video {video_id}"
        )

        # Detect timing drift
        drift_amount = self._detect_drift(scenes, transcript_segments)
        drift_detected = abs(drift_amount) > self.drift_threshold

        if drift_detected:
            logger.warning(f"Detected timing drift of {drift_amount:.2f}s")

            if self.auto_correct_drift:
                logger.info("Auto-correcting drift...")
                transcript_segments = self._correct_drift(
                    transcript_segments, drift_amount
                )

        # Align segments
        aligned_segments = []
        aligned_transcript_count = 0

        for scene in scenes:
            scene_id = scene.get("scene_number", scene.get("scene_id", 0))
            scene_start = scene["start_time"]
            scene_end = scene["end_time"]

            # Find overlapping transcript segments
            overlapping_segments = self._find_overlapping_segments(
                transcript_segments, scene_start, scene_end
            )

            # Find frames in scene
            scene_frames = []
            scene_frame_timestamps = []

            if frames:
                scene_frames, scene_frame_timestamps = self._find_frames_in_range(
                    frames, scene_start, scene_end
                )

            # Calculate alignment quality
            quality = self._calculate_alignment_quality(
                scene_start, scene_end, overlapping_segments
            )

            # Create aligned segment
            aligned_segment = AlignedSegment(
                scene_id=scene_id,
                scene_start=scene_start,
                scene_end=scene_end,
                transcript_segments=overlapping_segments,
                frame_indices=scene_frames,
                frame_timestamps=scene_frame_timestamps,
                alignment_quality=quality,
                metadata={
                    "scene_duration": scene_end - scene_start,
                    "num_transcript_segments": len(overlapping_segments),
                    "num_frames": len(scene_frames),
                },
            )

            aligned_segments.append(aligned_segment)
            aligned_transcript_count += len(overlapping_segments)

        # Calculate coverage
        coverage = (
            aligned_transcript_count / len(transcript_segments)
            if transcript_segments
            else 0.0
        )

        return AlignmentResult(
            video_id=video_id,
            aligned_segments=aligned_segments,
            total_scenes=len(scenes),
            total_transcript_segments=len(transcript_segments),
            alignment_coverage=coverage,
            drift_detected=drift_detected,
            drift_amount=drift_amount,
            metadata={
                "tolerance": self.tolerance,
                "drift_threshold": self.drift_threshold,
            },
        )

    def _find_overlapping_segments(
        self,
        segments: List[Dict[str, Any]],
        start_time: float,
        end_time: float,
    ) -> List[Dict[str, Any]]:
        """
        Find transcript segments overlapping with time range

        Args:
            segments: List of segments
            start_time: Range start
            end_time: Range end

        Returns:
            List of overlapping segments
        """
        overlapping = []

        for segment in segments:
            seg_start = segment["start_time"]
            seg_end = segment["end_time"]

            # Check for overlap (with tolerance)
            if self._ranges_overlap(
                seg_start, seg_end, start_time, end_time, self.tolerance
            ):
                overlapping.append(segment)

        return overlapping

    def _find_frames_in_range(
        self,
        frames: List[Dict[str, Any]],
        start_time: float,
        end_time: float,
    ) -> Tuple[List[int], List[float]]:
        """
        Find frames within time range

        Args:
            frames: List of frames
            start_time: Range start
            end_time: Range end

        Returns:
            Tuple of (frame_indices, frame_timestamps)
        """
        frame_indices = []
        frame_timestamps = []

        for i, frame in enumerate(frames):
            timestamp = frame.get("timestamp", 0.0)

            if start_time <= timestamp <= end_time:
                frame_indices.append(i)
                frame_timestamps.append(timestamp)

        return frame_indices, frame_timestamps

    def _ranges_overlap(
        self,
        start1: float,
        end1: float,
        start2: float,
        end2: float,
        tolerance: float = 0.0,
    ) -> bool:
        """
        Check if two time ranges overlap

        Args:
            start1: First range start
            end1: First range end
            start2: Second range start
            end2: Second range end
            tolerance: Time tolerance

        Returns:
            True if ranges overlap
        """
        # Expand ranges by tolerance
        start1 -= tolerance
        end1 += tolerance
        start2 -= tolerance
        end2 += tolerance

        return not (end1 < start2 or end2 < start1)

    def _detect_drift(
        self,
        scenes: List[Dict[str, Any]],
        transcript_segments: List[Dict[str, Any]],
    ) -> float:
        """
        Detect timing drift between scenes and transcript

        Args:
            scenes: Scene list
            transcript_segments: Transcript segments

        Returns:
            Estimated drift amount in seconds (positive = transcript ahead)
        """
        if not scenes or not transcript_segments:
            return 0.0

        # Compare first and last timestamps
        scene_start = scenes[0]["start_time"]
        scene_end = scenes[-1]["end_time"]
        transcript_start = transcript_segments[0]["start_time"]
        transcript_end = transcript_segments[-1]["end_time"]

        # Calculate drift at start and end
        start_drift = transcript_start - scene_start
        end_drift = transcript_end - scene_end

        # Average drift
        avg_drift = (start_drift + end_drift) / 2

        return avg_drift

    def _correct_drift(
        self,
        segments: List[Dict[str, Any]],
        drift_amount: float,
    ) -> List[Dict[str, Any]]:
        """
        Correct timing drift in segments

        Args:
            segments: Transcript segments
            drift_amount: Drift to correct

        Returns:
            Corrected segments
        """
        corrected = []

        for segment in segments:
            corrected_segment = segment.copy()
            corrected_segment["start_time"] = segment["start_time"] - drift_amount
            corrected_segment["end_time"] = segment["end_time"] - drift_amount

            # Store original times
            corrected_segment["original_start_time"] = segment["start_time"]
            corrected_segment["original_end_time"] = segment["end_time"]
            corrected_segment["drift_corrected"] = True
            corrected_segment["drift_amount"] = drift_amount

            corrected.append(corrected_segment)

        return corrected

    def _calculate_alignment_quality(
        self,
        scene_start: float,
        scene_end: float,
        segments: List[Dict[str, Any]],
    ) -> float:
        """
        Calculate quality of alignment

        Args:
            scene_start: Scene start time
            scene_end: Scene end time
            segments: Aligned transcript segments

        Returns:
            Quality score (0-1)
        """
        if not segments:
            return 0.0

        scene_duration = scene_end - scene_start

        # Calculate transcript coverage of scene
        covered_time = 0.0

        for segment in segments:
            seg_start = max(segment["start_time"], scene_start)
            seg_end = min(segment["end_time"], scene_end)
            covered_time += max(0, seg_end - seg_start)

        # Quality based on coverage
        coverage_ratio = covered_time / scene_duration if scene_duration > 0 else 0.0

        # Penalize if too many gaps
        num_gaps = max(0, len(segments) - 1)
        gap_penalty = min(num_gaps * 0.05, 0.3)

        quality = max(0.0, min(1.0, coverage_ratio - gap_penalty))

        return quality

    def align_frames_with_transcript(
        self,
        frames: List[Dict[str, Any]],
        transcript_segments: List[Dict[str, Any]],
        max_distance: float = 2.0,
    ) -> List[Tuple[int, List[Dict[str, Any]]]]:
        """
        Align frames with transcript segments

        Args:
            frames: List of frame dictionaries
            transcript_segments: List of transcript segments
            max_distance: Maximum time distance for alignment

        Returns:
            List of (frame_index, aligned_segments) tuples
        """
        alignments = []

        for i, frame in enumerate(frames):
            frame_timestamp = frame.get("timestamp", 0.0)

            # Find nearby segments
            aligned_segments = []

            for segment in transcript_segments:
                seg_start = segment["start_time"]
                seg_end = segment["end_time"]

                # Check if frame is within or near segment
                if seg_start <= frame_timestamp <= seg_end:
                    # Frame is within segment
                    aligned_segments.append(segment)
                else:
                    # Check distance to segment
                    distance = min(
                        abs(frame_timestamp - seg_start),
                        abs(frame_timestamp - seg_end),
                    )

                    if distance <= max_distance:
                        aligned_segments.append(segment)

            alignments.append((i, aligned_segments))

        return alignments

    def create_timeline(
        self,
        scenes: List[Dict[str, Any]],
        transcript_segments: List[Dict[str, Any]],
        frames: Optional[List[Dict[str, Any]]] = None,
        events: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Create unified timeline with all elements

        Args:
            scenes: Scene list
            transcript_segments: Transcript segments
            frames: Optional frame list
            events: Optional additional events

        Returns:
            Sorted timeline of all events
        """
        timeline = []

        # Add scenes
        for scene in scenes:
            timeline.append({
                "type": "scene",
                "start_time": scene["start_time"],
                "end_time": scene["end_time"],
                "data": scene,
            })

        # Add transcript segments
        for segment in transcript_segments:
            timeline.append({
                "type": "transcript",
                "start_time": segment["start_time"],
                "end_time": segment["end_time"],
                "data": segment,
            })

        # Add frames
        if frames:
            for frame in frames:
                timeline.append({
                    "type": "frame",
                    "start_time": frame.get("timestamp", 0.0),
                    "end_time": frame.get("timestamp", 0.0),
                    "data": frame,
                })

        # Add events
        if events:
            for event in events:
                timeline.append({
                    "type": event.get("type", "event"),
                    "start_time": event.get("start_time", event.get("timestamp", 0.0)),
                    "end_time": event.get("end_time", event.get("timestamp", 0.0)),
                    "data": event,
                })

        # Sort by start time
        timeline.sort(key=lambda x: x["start_time"])

        return timeline

    def find_synchronization_points(
        self,
        transcript_segments: List[Dict[str, Any]],
        scenes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Find synchronization points between transcript and scenes

        Args:
            transcript_segments: Transcript segments
            scenes: Scene list

        Returns:
            List of synchronization points
        """
        sync_points = []

        # Find scene boundaries that align with transcript boundaries
        for scene in scenes:
            scene_start = scene["start_time"]
            scene_end = scene["end_time"]

            # Check for transcript segments starting/ending near scene boundaries
            for segment in transcript_segments:
                seg_start = segment["start_time"]
                seg_end = segment["end_time"]

                # Check start alignment
                if abs(seg_start - scene_start) < self.tolerance:
                    sync_points.append({
                        "timestamp": scene_start,
                        "type": "scene_start_transcript_start",
                        "scene": scene,
                        "segment": segment,
                        "alignment_error": abs(seg_start - scene_start),
                    })

                # Check end alignment
                if abs(seg_end - scene_end) < self.tolerance:
                    sync_points.append({
                        "timestamp": scene_end,
                        "type": "scene_end_transcript_end",
                        "scene": scene,
                        "segment": segment,
                        "alignment_error": abs(seg_end - scene_end),
                    })

        # Sort by timestamp
        sync_points.sort(key=lambda x: x["timestamp"])

        return sync_points

    def get_context_window(
        self,
        timestamp: float,
        scenes: List[Dict[str, Any]],
        transcript_segments: List[Dict[str, Any]],
        window_size: float = 5.0,
    ) -> Dict[str, Any]:
        """
        Get context around a timestamp

        Args:
            timestamp: Target timestamp
            scenes: Scene list
            transcript_segments: Transcript segments
            window_size: Context window size (seconds)

        Returns:
            Context dictionary
        """
        start_time = timestamp - window_size / 2
        end_time = timestamp + window_size / 2

        # Find scenes in window
        context_scenes = [
            s for s in scenes
            if self._ranges_overlap(
                s["start_time"], s["end_time"],
                start_time, end_time
            )
        ]

        # Find transcript in window
        context_transcript = [
            seg for seg in transcript_segments
            if self._ranges_overlap(
                seg["start_time"], seg["end_time"],
                start_time, end_time
            )
        ]

        return {
            "timestamp": timestamp,
            "window_start": start_time,
            "window_end": end_time,
            "scenes": context_scenes,
            "transcript_segments": context_transcript,
        }


def align_transcript_with_scenes(
    video_id: str,
    scenes: List[Dict[str, Any]],
    transcript_segments: List[Dict[str, Any]],
    tolerance: float = 0.5,
) -> AlignmentResult:
    """
    Convenience function to align transcript with scenes

    Args:
        video_id: Video identifier
        scenes: Scene list
        transcript_segments: Transcript segments
        tolerance: Time tolerance

    Returns:
        AlignmentResult
    """
    aligner = TemporalAligner(tolerance=tolerance)
    return aligner.align_transcript_with_scenes(
        video_id=video_id,
        scenes=scenes,
        transcript_segments=transcript_segments,
    )
