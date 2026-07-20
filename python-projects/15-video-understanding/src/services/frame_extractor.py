"""
Frame extraction service for videos
Extracts frames at specified intervals with metadata
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass
from datetime import datetime

from src.core.video_processor import VideoProcessor, ProcessingProgress
from src.core.storage import storage_manager

logger = logging.getLogger(__name__)


@dataclass
class FrameMetadata:
    """Metadata for an extracted frame"""
    frame_number: int
    timestamp: float
    file_path: Path
    is_keyframe: bool
    width: Optional[int] = None
    height: Optional[int] = None
    size_bytes: Optional[int] = None
    extraction_time: Optional[datetime] = None


class ExtractionMode:
    """Frame extraction modes"""
    INTERVAL = "interval"  # Extract at regular intervals (FPS-based)
    KEYFRAMES_ONLY = "keyframes_only"  # Extract only keyframes
    ADAPTIVE = "adaptive"  # Adaptive extraction based on scene changes


class FrameExtractor:
    """
    Service for extracting frames from videos with metadata tracking
    """

    def __init__(
        self,
        video_processor: Optional[VideoProcessor] = None,
        storage_manager_instance: Optional[Any] = None,
        progress_callback: Optional[Callable[[ProcessingProgress], None]] = None
    ):
        """
        Initialize frame extractor

        Args:
            video_processor: VideoProcessor instance
            storage_manager_instance: StorageManager instance
            progress_callback: Optional callback for progress updates
        """
        from src.core.video_processor import create_video_processor

        self.video_processor = video_processor or create_video_processor(
            progress_callback=progress_callback
        )
        self.storage = storage_manager_instance or storage_manager
        self.progress_callback = progress_callback

    def extract_frames(
        self,
        video_path: Path,
        video_id: int,
        fps: float = 1.0,
        mode: str = ExtractionMode.INTERVAL,
        quality: int = 2,
        scene_id: Optional[int] = None,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> List[FrameMetadata]:
        """
        Extract frames from video with metadata

        Args:
            video_path: Path to video file
            video_id: Video ID for storage organization
            fps: Frames per second to extract (for INTERVAL mode)
            mode: Extraction mode (interval, keyframes_only, adaptive)
            quality: JPEG quality (1-31, lower is better)
            scene_id: Optional scene ID for scene-specific extraction
            start_time: Optional start time in seconds
            end_time: Optional end time in seconds

        Returns:
            List of FrameMetadata objects

        Raises:
            ValueError: If video not found or invalid parameters
            RuntimeError: If extraction fails
        """
        if not video_path.exists():
            raise ValueError(f"Video file not found: {video_path}")

        if fps <= 0:
            raise ValueError(f"FPS must be positive, got: {fps}")

        logger.info(
            f"Extracting frames from video {video_id} "
            f"(mode={mode}, fps={fps}, scene_id={scene_id})"
        )

        # Get output directory for frames
        frames_dir = self.storage.get_frames_directory(video_id, scene_id)

        # Report progress
        if self.progress_callback:
            self.progress_callback(ProcessingProgress(
                stage="frame_extraction_setup",
                current=0,
                total=100,
                percentage=0.0,
                message=f"Preparing to extract frames (mode: {mode})"
            ))

        # Extract frames based on mode
        if mode == ExtractionMode.INTERVAL:
            frame_paths = self._extract_interval_frames(
                video_path, frames_dir, fps, quality, start_time, end_time
            )
        elif mode == ExtractionMode.KEYFRAMES_ONLY:
            frame_paths = self._extract_keyframes(
                video_path, frames_dir, quality, start_time, end_time
            )
        elif mode == ExtractionMode.ADAPTIVE:
            frame_paths = self._extract_adaptive_frames(
                video_path, frames_dir, fps, quality, start_time, end_time
            )
        else:
            raise ValueError(f"Unknown extraction mode: {mode}")

        # Generate metadata for extracted frames
        metadata_list = self._generate_metadata(
            frame_paths, video_id, scene_id, fps
        )

        logger.info(
            f"Extracted {len(metadata_list)} frames from video {video_id} "
            f"to {frames_dir}"
        )

        return metadata_list

    def _extract_interval_frames(
        self,
        video_path: Path,
        output_dir: Path,
        fps: float,
        quality: int,
        start_time: Optional[float],
        end_time: Optional[float]
    ) -> List[Path]:
        """Extract frames at regular intervals"""
        if self.progress_callback:
            self.progress_callback(ProcessingProgress(
                stage="interval_extraction",
                current=10,
                total=100,
                percentage=10.0,
                message=f"Extracting frames at {fps} FPS"
            ))

        frame_paths = self.video_processor.extract_frames(
            video_path=video_path,
            output_dir=output_dir,
            fps=fps,
            quality=quality,
            start_time=start_time,
            end_time=end_time,
            filename_pattern="frame_%06d.jpg"
        )

        return frame_paths

    def _extract_keyframes(
        self,
        video_path: Path,
        output_dir: Path,
        quality: int,
        start_time: Optional[float],
        end_time: Optional[float]
    ) -> List[Path]:
        """Extract only keyframes using ffmpeg scene detection"""
        if self.progress_callback:
            self.progress_callback(ProcessingProgress(
                stage="keyframe_extraction",
                current=10,
                total=100,
                percentage=10.0,
                message="Extracting keyframes only"
            ))

        # Use select filter to extract keyframes
        # This will be implemented more robustly in KeyframeDetector
        # For now, use a reasonable FPS for keyframe extraction
        frame_paths = self.video_processor.extract_frames(
            video_path=video_path,
            output_dir=output_dir,
            fps=0.5,  # Extract less frequently for keyframes
            quality=quality,
            start_time=start_time,
            end_time=end_time,
            filename_pattern="keyframe_%06d.jpg"
        )

        return frame_paths

    def _extract_adaptive_frames(
        self,
        video_path: Path,
        output_dir: Path,
        fps: float,
        quality: int,
        start_time: Optional[float],
        end_time: Optional[float]
    ) -> List[Path]:
        """Extract frames adaptively based on content changes"""
        if self.progress_callback:
            self.progress_callback(ProcessingProgress(
                stage="adaptive_extraction",
                current=10,
                total=100,
                percentage=10.0,
                message="Extracting frames adaptively"
            ))

        # Adaptive extraction will be implemented more robustly later
        # For now, use a moderate FPS
        frame_paths = self.video_processor.extract_frames(
            video_path=video_path,
            output_dir=output_dir,
            fps=fps * 1.5,  # Slightly higher FPS for adaptive
            quality=quality,
            start_time=start_time,
            end_time=end_time,
            filename_pattern="frame_%06d.jpg"
        )

        return frame_paths

    def _generate_metadata(
        self,
        frame_paths: List[Path],
        video_id: int,
        scene_id: Optional[int],
        fps: float
    ) -> List[FrameMetadata]:
        """Generate metadata for extracted frames"""
        metadata_list = []

        for idx, frame_path in enumerate(frame_paths, start=1):
            # Calculate timestamp from frame number
            timestamp = (idx - 1) / fps

            # Get file stats
            file_stat = frame_path.stat()

            # Determine if this is a keyframe based on filename
            is_keyframe = "keyframe" in frame_path.name

            metadata = FrameMetadata(
                frame_number=idx,
                timestamp=timestamp,
                file_path=frame_path,
                is_keyframe=is_keyframe,
                size_bytes=file_stat.st_size,
                extraction_time=datetime.now()
            )

            metadata_list.append(metadata)

        # Report progress
        if self.progress_callback:
            self.progress_callback(ProcessingProgress(
                stage="metadata_generation",
                current=100,
                total=100,
                percentage=100.0,
                message=f"Generated metadata for {len(metadata_list)} frames"
            ))

        return metadata_list

    def extract_single_frame(
        self,
        video_path: Path,
        video_id: int,
        timestamp: float,
        quality: int = 2,
        scene_id: Optional[int] = None,
        is_keyframe: bool = False
    ) -> FrameMetadata:
        """
        Extract a single frame at specific timestamp

        Args:
            video_path: Path to video file
            video_id: Video ID for storage
            timestamp: Time in seconds
            quality: JPEG quality
            scene_id: Optional scene ID
            is_keyframe: Mark as keyframe

        Returns:
            FrameMetadata for extracted frame

        Raises:
            ValueError: If video not found
            RuntimeError: If extraction fails
        """
        if not video_path.exists():
            raise ValueError(f"Video file not found: {video_path}")

        logger.debug(f"Extracting single frame at {timestamp}s from video {video_id}")

        # Get storage path
        output_path = self.storage.get_frame_path(
            video_id=video_id,
            frame_number=int(timestamp * 1000),  # Use millisecond-based numbering
            timestamp=timestamp,
            scene_id=scene_id,
            is_keyframe=is_keyframe
        )

        # Extract frame
        self.video_processor.extract_single_frame(
            video_path=video_path,
            output_path=output_path,
            timestamp=timestamp,
            quality=quality
        )

        # Get file stats
        file_stat = output_path.stat()

        # Create metadata
        metadata = FrameMetadata(
            frame_number=int(timestamp * 1000),
            timestamp=timestamp,
            file_path=output_path,
            is_keyframe=is_keyframe,
            size_bytes=file_stat.st_size,
            extraction_time=datetime.now()
        )

        logger.debug(f"Extracted single frame to {output_path}")

        return metadata

    def extract_frames_for_timestamps(
        self,
        video_path: Path,
        video_id: int,
        timestamps: List[float],
        quality: int = 2,
        scene_id: Optional[int] = None,
        mark_as_keyframes: bool = False
    ) -> List[FrameMetadata]:
        """
        Extract frames at specific timestamps

        Args:
            video_path: Path to video file
            video_id: Video ID for storage
            timestamps: List of timestamps in seconds
            quality: JPEG quality
            scene_id: Optional scene ID
            mark_as_keyframes: Mark all as keyframes

        Returns:
            List of FrameMetadata objects

        Raises:
            ValueError: If video not found
        """
        if not video_path.exists():
            raise ValueError(f"Video file not found: {video_path}")

        logger.info(
            f"Extracting {len(timestamps)} frames at specific timestamps "
            f"from video {video_id}"
        )

        metadata_list = []
        total = len(timestamps)

        for idx, timestamp in enumerate(timestamps, start=1):
            # Report progress
            if self.progress_callback:
                self.progress_callback(ProcessingProgress(
                    stage="timestamp_extraction",
                    current=idx,
                    total=total,
                    percentage=(idx / total) * 100,
                    message=f"Extracting frame {idx}/{total} at {timestamp:.2f}s"
                ))

            try:
                metadata = self.extract_single_frame(
                    video_path=video_path,
                    video_id=video_id,
                    timestamp=timestamp,
                    quality=quality,
                    scene_id=scene_id,
                    is_keyframe=mark_as_keyframes
                )
                metadata_list.append(metadata)

            except Exception as e:
                logger.error(f"Failed to extract frame at {timestamp}s: {e}")
                # Continue with other timestamps

        logger.info(
            f"Successfully extracted {len(metadata_list)}/{total} frames "
            f"from video {video_id}"
        )

        return metadata_list

    def get_extraction_stats(
        self,
        video_id: int,
        scene_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get statistics about extracted frames

        Args:
            video_id: Video ID
            scene_id: Optional scene ID

        Returns:
            Dictionary with frame statistics
        """
        frames_dir = self.storage.get_frames_directory(video_id, scene_id)

        if not frames_dir.exists():
            return {
                'total_frames': 0,
                'keyframes': 0,
                'regular_frames': 0,
                'total_size_mb': 0.0,
                'frames_dir': str(frames_dir)
            }

        # Count frames
        all_frames = list(frames_dir.glob("*.jpg"))
        keyframes = [f for f in all_frames if "keyframe" in f.name]
        regular_frames = [f for f in all_frames if "keyframe" not in f.name]

        # Calculate total size
        total_size = sum(f.stat().st_size for f in all_frames)

        return {
            'total_frames': len(all_frames),
            'keyframes': len(keyframes),
            'regular_frames': len(regular_frames),
            'total_size_mb': round(total_size / (1024 * 1024), 2),
            'frames_dir': str(frames_dir)
        }


def extract_frames_from_video(
    video_path: Path,
    video_id: int,
    fps: float = 1.0,
    mode: str = ExtractionMode.INTERVAL,
    quality: int = 2
) -> List[FrameMetadata]:
    """
    Convenience function to extract frames from video

    Args:
        video_path: Path to video file
        video_id: Video ID
        fps: Frames per second to extract
        mode: Extraction mode
        quality: JPEG quality

    Returns:
        List of FrameMetadata objects
    """
    extractor = FrameExtractor()
    return extractor.extract_frames(
        video_path=video_path,
        video_id=video_id,
        fps=fps,
        mode=mode,
        quality=quality
    )
