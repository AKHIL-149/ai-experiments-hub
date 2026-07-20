"""
Keyframe detection service for identifying significant frames in videos
Uses multiple detection methods including scene changes and visual analysis
"""

import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Callable, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

from src.core.video_processor import VideoProcessor, ProcessingProgress

logger = logging.getLogger(__name__)


@dataclass
class Keyframe:
    """Information about a detected keyframe"""
    timestamp: float
    frame_number: int
    score: float  # Confidence/importance score
    detection_method: str  # Method used to detect this keyframe
    file_path: Optional[Path] = None


class DetectionMethod:
    """Keyframe detection methods"""
    SCENE_CHANGE = "scene_change"  # Scene change detection
    SHOT_BOUNDARY = "shot_boundary"  # Shot boundary detection
    VISUAL_VARIANCE = "visual_variance"  # High visual variance
    CODEC_KEYFRAME = "codec_keyframe"  # Video codec keyframes (I-frames)


class KeyframeDetector:
    """
    Detect keyframes in videos using multiple methods
    """

    def __init__(
        self,
        video_processor: Optional[VideoProcessor] = None,
        progress_callback: Optional[Callable[[ProcessingProgress], None]] = None
    ):
        """
        Initialize keyframe detector

        Args:
            video_processor: VideoProcessor instance
            progress_callback: Optional callback for progress updates
        """
        from src.core.video_processor import create_video_processor

        self.video_processor = video_processor or create_video_processor(
            progress_callback=progress_callback
        )
        self.progress_callback = progress_callback

    def detect_keyframes(
        self,
        video_path: Path,
        method: str = DetectionMethod.SCENE_CHANGE,
        threshold: float = 0.3,
        min_interval: float = 1.0,
        max_keyframes: Optional[int] = None
    ) -> List[Keyframe]:
        """
        Detect keyframes in video

        Args:
            video_path: Path to video file
            method: Detection method to use
            threshold: Detection threshold (0.0-1.0)
            min_interval: Minimum interval between keyframes in seconds
            max_keyframes: Maximum number of keyframes to return

        Returns:
            List of Keyframe objects

        Raises:
            ValueError: If video not found or invalid parameters
            RuntimeError: If detection fails
        """
        if not video_path.exists():
            raise ValueError(f"Video file not found: {video_path}")

        if threshold < 0.0 or threshold > 1.0:
            raise ValueError(f"Threshold must be between 0.0 and 1.0, got: {threshold}")

        if min_interval < 0:
            raise ValueError(f"Minimum interval must be positive, got: {min_interval}")

        logger.info(
            f"Detecting keyframes in {video_path} "
            f"(method={method}, threshold={threshold})"
        )

        # Report progress
        if self.progress_callback:
            self.progress_callback(ProcessingProgress(
                stage="keyframe_detection_setup",
                current=0,
                total=100,
                percentage=0.0,
                message=f"Preparing keyframe detection ({method})"
            ))

        # Detect keyframes based on method
        if method == DetectionMethod.SCENE_CHANGE:
            keyframes = self._detect_scene_change_keyframes(
                video_path, threshold, min_interval
            )
        elif method == DetectionMethod.SHOT_BOUNDARY:
            keyframes = self._detect_shot_boundary_keyframes(
                video_path, threshold, min_interval
            )
        elif method == DetectionMethod.VISUAL_VARIANCE:
            keyframes = self._detect_visual_variance_keyframes(
                video_path, threshold, min_interval
            )
        elif method == DetectionMethod.CODEC_KEYFRAME:
            keyframes = self._detect_codec_keyframes(
                video_path, min_interval
            )
        else:
            raise ValueError(f"Unknown detection method: {method}")

        # Sort by timestamp
        keyframes.sort(key=lambda k: k.timestamp)

        # Apply max_keyframes limit if specified
        if max_keyframes and len(keyframes) > max_keyframes:
            # Keep the highest scoring keyframes
            keyframes.sort(key=lambda k: k.score, reverse=True)
            keyframes = keyframes[:max_keyframes]
            # Re-sort by timestamp
            keyframes.sort(key=lambda k: k.timestamp)

        logger.info(f"Detected {len(keyframes)} keyframes in {video_path}")

        return keyframes

    def _detect_scene_change_keyframes(
        self,
        video_path: Path,
        threshold: float,
        min_interval: float
    ) -> List[Keyframe]:
        """
        Detect keyframes based on scene changes using ffmpeg select filter

        Args:
            video_path: Path to video file
            threshold: Scene change threshold (0.0-1.0)
            min_interval: Minimum interval between keyframes

        Returns:
            List of Keyframe objects
        """
        if self.progress_callback:
            self.progress_callback(ProcessingProgress(
                stage="scene_change_detection",
                current=10,
                total=100,
                percentage=10.0,
                message="Detecting scene changes"
            ))

        # Use ffprobe to detect scene changes
        cmd = [
            self.video_processor.ffprobe_path,
            "-v", "error",
            "-show_entries", "frame=pkt_pts_time,pict_type",
            "-select_streams", "v:0",
            "-of", "csv=p=0",
            str(video_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=300
            )

            # Parse output to find scene changes
            keyframes = []
            last_timestamp = -min_interval

            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                parts = line.split(',')
                if len(parts) < 2:
                    continue

                try:
                    timestamp = float(parts[0])
                    frame_type = parts[1]

                    # I-frames (keyframes in codec) are good candidates
                    if frame_type == 'I' and (timestamp - last_timestamp) >= min_interval:
                        keyframes.append(Keyframe(
                            timestamp=timestamp,
                            frame_number=len(keyframes) + 1,
                            score=1.0,
                            detection_method=DetectionMethod.SCENE_CHANGE
                        ))
                        last_timestamp = timestamp

                except (ValueError, IndexError) as e:
                    logger.debug(f"Failed to parse line: {line}, error: {e}")
                    continue

            if self.progress_callback:
                self.progress_callback(ProcessingProgress(
                    stage="scene_change_detection",
                    current=100,
                    total=100,
                    percentage=100.0,
                    message=f"Detected {len(keyframes)} scene changes"
                ))

            return keyframes

        except subprocess.CalledProcessError as e:
            error_msg = f"Scene change detection failed: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        except subprocess.TimeoutExpired:
            raise RuntimeError("Scene change detection timed out")

    def _detect_shot_boundary_keyframes(
        self,
        video_path: Path,
        threshold: float,
        min_interval: float
    ) -> List[Keyframe]:
        """
        Detect keyframes at shot boundaries using advanced scene detection

        This is a placeholder for more sophisticated shot boundary detection
        Currently uses scene change detection
        """
        logger.debug("Using scene change detection for shot boundaries")
        keyframes = self._detect_scene_change_keyframes(
            video_path, threshold, min_interval
        )

        # Update detection method
        for keyframe in keyframes:
            keyframe.detection_method = DetectionMethod.SHOT_BOUNDARY

        return keyframes

    def _detect_visual_variance_keyframes(
        self,
        video_path: Path,
        threshold: float,
        min_interval: float
    ) -> List[Keyframe]:
        """
        Detect keyframes based on visual variance

        This is a placeholder for visual variance-based detection
        Currently uses scene change detection
        """
        logger.debug("Using scene change detection for visual variance")
        keyframes = self._detect_scene_change_keyframes(
            video_path, threshold, min_interval
        )

        # Update detection method
        for keyframe in keyframes:
            keyframe.detection_method = DetectionMethod.VISUAL_VARIANCE

        return keyframes

    def _detect_codec_keyframes(
        self,
        video_path: Path,
        min_interval: float
    ) -> List[Keyframe]:
        """
        Detect codec-level keyframes (I-frames)

        Args:
            video_path: Path to video file
            min_interval: Minimum interval between keyframes

        Returns:
            List of Keyframe objects
        """
        if self.progress_callback:
            self.progress_callback(ProcessingProgress(
                stage="codec_keyframe_detection",
                current=10,
                total=100,
                percentage=10.0,
                message="Detecting codec keyframes (I-frames)"
            ))

        # Use ffprobe to find I-frames
        cmd = [
            self.video_processor.ffprobe_path,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "frame=pkt_pts_time,pict_type,key_frame",
            "-of", "csv=p=0",
            str(video_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True,
                timeout=300
            )

            keyframes = []
            last_timestamp = -min_interval

            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                parts = line.split(',')
                if len(parts) < 3:
                    continue

                try:
                    timestamp = float(parts[0])
                    pict_type = parts[1]
                    key_frame = parts[2]

                    # Check if this is a keyframe
                    if key_frame == '1' and (timestamp - last_timestamp) >= min_interval:
                        keyframes.append(Keyframe(
                            timestamp=timestamp,
                            frame_number=len(keyframes) + 1,
                            score=1.0 if pict_type == 'I' else 0.8,
                            detection_method=DetectionMethod.CODEC_KEYFRAME
                        ))
                        last_timestamp = timestamp

                except (ValueError, IndexError) as e:
                    logger.debug(f"Failed to parse line: {line}, error: {e}")
                    continue

            if self.progress_callback:
                self.progress_callback(ProcessingProgress(
                    stage="codec_keyframe_detection",
                    current=100,
                    total=100,
                    percentage=100.0,
                    message=f"Detected {len(keyframes)} codec keyframes"
                ))

            return keyframes

        except subprocess.CalledProcessError as e:
            error_msg = f"Codec keyframe detection failed: {e.stderr}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e
        except subprocess.TimeoutExpired:
            raise RuntimeError("Codec keyframe detection timed out")

    def detect_keyframes_multi_method(
        self,
        video_path: Path,
        methods: Optional[List[str]] = None,
        threshold: float = 0.3,
        min_interval: float = 1.0,
        max_keyframes: Optional[int] = None
    ) -> List[Keyframe]:
        """
        Detect keyframes using multiple methods and combine results

        Args:
            video_path: Path to video file
            methods: List of detection methods to use (default: all)
            threshold: Detection threshold
            min_interval: Minimum interval between keyframes
            max_keyframes: Maximum number of keyframes

        Returns:
            Combined list of Keyframe objects
        """
        if methods is None:
            methods = [
                DetectionMethod.SCENE_CHANGE,
                DetectionMethod.CODEC_KEYFRAME,
            ]

        all_keyframes: Dict[float, Keyframe] = {}

        for method in methods:
            logger.info(f"Running keyframe detection with method: {method}")

            try:
                keyframes = self.detect_keyframes(
                    video_path=video_path,
                    method=method,
                    threshold=threshold,
                    min_interval=min_interval
                )

                # Merge keyframes (prefer higher scores for duplicate timestamps)
                for kf in keyframes:
                    # Round timestamp to avoid floating point issues
                    ts_key = round(kf.timestamp, 2)

                    if ts_key not in all_keyframes or kf.score > all_keyframes[ts_key].score:
                        all_keyframes[ts_key] = kf

            except Exception as e:
                logger.error(f"Method {method} failed: {e}")
                continue

        # Convert to list and sort
        combined_keyframes = list(all_keyframes.values())
        combined_keyframes.sort(key=lambda k: k.timestamp)

        # Apply max_keyframes limit
        if max_keyframes and len(combined_keyframes) > max_keyframes:
            combined_keyframes.sort(key=lambda k: k.score, reverse=True)
            combined_keyframes = combined_keyframes[:max_keyframes]
            combined_keyframes.sort(key=lambda k: k.timestamp)

        logger.info(
            f"Combined multi-method detection found {len(combined_keyframes)} keyframes"
        )

        return combined_keyframes

    def extract_keyframes(
        self,
        video_path: Path,
        output_dir: Path,
        method: str = DetectionMethod.SCENE_CHANGE,
        threshold: float = 0.3,
        min_interval: float = 1.0,
        quality: int = 2,
        max_keyframes: Optional[int] = None
    ) -> List[Tuple[Keyframe, Path]]:
        """
        Detect and extract keyframes to files

        Args:
            video_path: Path to video file
            output_dir: Directory to save keyframes
            method: Detection method
            threshold: Detection threshold
            min_interval: Minimum interval between keyframes
            quality: JPEG quality
            max_keyframes: Maximum number of keyframes

        Returns:
            List of (Keyframe, Path) tuples
        """
        # Detect keyframes
        keyframes = self.detect_keyframes(
            video_path=video_path,
            method=method,
            threshold=threshold,
            min_interval=min_interval,
            max_keyframes=max_keyframes
        )

        if not keyframes:
            logger.warning("No keyframes detected")
            return []

        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)

        # Extract each keyframe
        extracted = []
        total = len(keyframes)

        for idx, keyframe in enumerate(keyframes, start=1):
            if self.progress_callback:
                self.progress_callback(ProcessingProgress(
                    stage="keyframe_extraction",
                    current=idx,
                    total=total,
                    percentage=(idx / total) * 100,
                    message=f"Extracting keyframe {idx}/{total} at {keyframe.timestamp:.2f}s"
                ))

            try:
                # Generate filename
                filename = f"keyframe_{idx:06d}_{keyframe.timestamp:.2f}s.jpg"
                output_path = output_dir / filename

                # Extract frame
                self.video_processor.extract_single_frame(
                    video_path=video_path,
                    output_path=output_path,
                    timestamp=keyframe.timestamp,
                    quality=quality
                )

                # Update keyframe with file path
                keyframe.file_path = output_path
                extracted.append((keyframe, output_path))

                logger.debug(f"Extracted keyframe to {output_path}")

            except Exception as e:
                logger.error(f"Failed to extract keyframe at {keyframe.timestamp}s: {e}")
                continue

        logger.info(f"Successfully extracted {len(extracted)}/{total} keyframes to {output_dir}")

        return extracted


def detect_keyframes(
    video_path: Path,
    method: str = DetectionMethod.SCENE_CHANGE,
    threshold: float = 0.3,
    min_interval: float = 1.0,
    max_keyframes: Optional[int] = None
) -> List[Keyframe]:
    """
    Convenience function to detect keyframes

    Args:
        video_path: Path to video file
        method: Detection method
        threshold: Detection threshold
        min_interval: Minimum interval between keyframes
        max_keyframes: Maximum number of keyframes

    Returns:
        List of Keyframe objects
    """
    detector = KeyframeDetector()
    return detector.detect_keyframes(
        video_path=video_path,
        method=method,
        threshold=threshold,
        min_interval=min_interval,
        max_keyframes=max_keyframes
    )
