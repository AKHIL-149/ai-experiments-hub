"""
Specialized storage manager for video frames
Handles organization, cleanup, and management of extracted frames
"""

import logging
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from src.core.storage import storage_manager

logger = logging.getLogger(__name__)


class FrameStorageManager:
    """
    Manage storage and organization of video frames
    """

    def __init__(self, base_storage_manager=None):
        """
        Initialize frame storage manager

        Args:
            base_storage_manager: Base StorageManager instance (uses singleton if not provided)
        """
        self.storage = base_storage_manager or storage_manager

    def get_frame_directory(
        self,
        video_id: int,
        scene_id: Optional[int] = None,
        create: bool = True
    ) -> Path:
        """
        Get directory for storing frames

        Args:
            video_id: Video ID
            scene_id: Optional scene ID
            create: Create directory if it doesn't exist

        Returns:
            Path to frames directory
        """
        return self.storage.get_frames_directory(video_id, scene_id)

    def organize_frames(
        self,
        video_id: int,
        frame_paths: List[Path],
        scene_id: Optional[int] = None,
        rename: bool = True
    ) -> List[Path]:
        """
        Organize frames into proper storage structure

        Args:
            video_id: Video ID
            frame_paths: List of frame file paths
            scene_id: Optional scene ID
            rename: Rename frames to standard naming convention

        Returns:
            List of new frame paths
        """
        frames_dir = self.get_frame_directory(video_id, scene_id, create=True)

        organized_paths = []

        for idx, frame_path in enumerate(frame_paths, start=1):
            if not frame_path.exists():
                logger.warning(f"Frame not found: {frame_path}")
                continue

            # Generate new filename if renaming
            if rename:
                timestamp = idx  # Can be improved with actual timestamp
                new_filename = f"frame_{idx:06d}_{timestamp:06d}.jpg"
                new_path = frames_dir / new_filename
            else:
                new_path = frames_dir / frame_path.name

            # Move or copy frame
            try:
                if frame_path.parent != frames_dir:
                    shutil.move(str(frame_path), str(new_path))
                    logger.debug(f"Moved frame to {new_path}")
                else:
                    new_path = frame_path

                organized_paths.append(new_path)

            except Exception as e:
                logger.error(f"Failed to organize frame {frame_path}: {e}")
                continue

        logger.info(
            f"Organized {len(organized_paths)}/{len(frame_paths)} frames "
            f"for video {video_id}"
        )

        return organized_paths

    def list_frames(
        self,
        video_id: int,
        scene_id: Optional[int] = None,
        pattern: str = "*.jpg"
    ) -> List[Path]:
        """
        List all frames for a video or scene

        Args:
            video_id: Video ID
            scene_id: Optional scene ID
            pattern: Glob pattern for frame files

        Returns:
            List of frame paths, sorted by name
        """
        frames_dir = self.get_frame_directory(video_id, scene_id, create=False)

        if not frames_dir.exists():
            return []

        frames = sorted(frames_dir.glob(pattern))

        logger.debug(f"Found {len(frames)} frames for video {video_id}, scene {scene_id}")

        return frames

    def get_frame_count(
        self,
        video_id: int,
        scene_id: Optional[int] = None
    ) -> int:
        """
        Get count of frames for a video or scene

        Args:
            video_id: Video ID
            scene_id: Optional scene ID

        Returns:
            Number of frames
        """
        frames = self.list_frames(video_id, scene_id)
        return len(frames)

    def get_keyframes(
        self,
        video_id: int,
        scene_id: Optional[int] = None
    ) -> List[Path]:
        """
        Get keyframes for a video or scene

        Args:
            video_id: Video ID
            scene_id: Optional scene ID

        Returns:
            List of keyframe paths
        """
        frames_dir = self.get_frame_directory(video_id, scene_id, create=False)

        if not frames_dir.exists():
            return []

        keyframes = sorted(frames_dir.glob("keyframe_*.jpg"))

        logger.debug(f"Found {len(keyframes)} keyframes for video {video_id}, scene {scene_id}")

        return keyframes

    def get_frame_stats(
        self,
        video_id: int,
        scene_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get statistics about stored frames

        Args:
            video_id: Video ID
            scene_id: Optional scene ID

        Returns:
            Dictionary with frame statistics
        """
        frames_dir = self.get_frame_directory(video_id, scene_id, create=False)

        if not frames_dir.exists():
            return {
                'total_frames': 0,
                'keyframes': 0,
                'regular_frames': 0,
                'total_size_mb': 0.0,
                'directory': str(frames_dir),
                'exists': False
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
            'directory': str(frames_dir),
            'exists': True
        }

    def cleanup_old_frames(
        self,
        video_id: int,
        scene_id: Optional[int] = None,
        older_than_days: int = 30
    ) -> int:
        """
        Remove frames older than specified days

        Args:
            video_id: Video ID
            scene_id: Optional scene ID
            older_than_days: Remove frames older than this many days

        Returns:
            Number of frames removed
        """
        frames = self.list_frames(video_id, scene_id)

        if not frames:
            return 0

        cutoff_time = datetime.now() - timedelta(days=older_than_days)
        removed_count = 0

        for frame_path in frames:
            try:
                modified_time = datetime.fromtimestamp(frame_path.stat().st_mtime)

                if modified_time < cutoff_time:
                    frame_path.unlink()
                    removed_count += 1
                    logger.debug(f"Removed old frame: {frame_path}")

            except Exception as e:
                logger.error(f"Failed to remove frame {frame_path}: {e}")
                continue

        if removed_count > 0:
            logger.info(
                f"Removed {removed_count} frames older than {older_than_days} days "
                f"for video {video_id}"
            )

        return removed_count

    def cleanup_all_frames(
        self,
        video_id: int,
        scene_id: Optional[int] = None
    ) -> bool:
        """
        Remove all frames for a video or scene

        Args:
            video_id: Video ID
            scene_id: Optional scene ID

        Returns:
            True if successful
        """
        frames_dir = self.get_frame_directory(video_id, scene_id, create=False)

        if not frames_dir.exists():
            logger.warning(f"Frames directory doesn't exist: {frames_dir}")
            return True

        try:
            shutil.rmtree(frames_dir)
            logger.info(f"Removed all frames from {frames_dir}")
            return True

        except Exception as e:
            logger.error(f"Failed to remove frames directory {frames_dir}: {e}")
            return False

    def get_frame_by_number(
        self,
        video_id: int,
        frame_number: int,
        scene_id: Optional[int] = None
    ) -> Optional[Path]:
        """
        Get frame by frame number

        Args:
            video_id: Video ID
            frame_number: Frame number to find
            scene_id: Optional scene ID

        Returns:
            Path to frame if found, None otherwise
        """
        frames_dir = self.get_frame_directory(video_id, scene_id, create=False)

        if not frames_dir.exists():
            return None

        # Try different naming patterns
        patterns = [
            f"frame_{frame_number:06d}_*.jpg",
            f"keyframe_{frame_number:06d}_*.jpg",
            f"*_{frame_number:06d}.jpg"
        ]

        for pattern in patterns:
            matches = list(frames_dir.glob(pattern))
            if matches:
                return matches[0]

        return None

    def get_frame_by_timestamp(
        self,
        video_id: int,
        timestamp: float,
        tolerance: float = 0.5,
        scene_id: Optional[int] = None
    ) -> Optional[Path]:
        """
        Get frame closest to a specific timestamp

        Args:
            video_id: Video ID
            timestamp: Target timestamp in seconds
            tolerance: Maximum time difference in seconds
            scene_id: Optional scene ID

        Returns:
            Path to closest frame if within tolerance, None otherwise
        """
        frames = self.list_frames(video_id, scene_id)

        if not frames:
            return None

        closest_frame = None
        closest_diff = float('inf')

        for frame_path in frames:
            # Try to extract timestamp from filename
            # Expected format: frame_NNNNNN_TTTTTT.jpg
            try:
                parts = frame_path.stem.split('_')
                if len(parts) >= 3:
                    # Remove 's' suffix if present
                    frame_time_str = parts[-1].rstrip('s')
                    frame_time = float(frame_time_str)

                    diff = abs(frame_time - timestamp)

                    if diff < closest_diff:
                        closest_diff = diff
                        closest_frame = frame_path

            except (ValueError, IndexError):
                # Skip frames with unexpected naming
                continue

        # Check if within tolerance
        if closest_frame and closest_diff <= tolerance:
            return closest_frame

        return None

    def copy_frames_to_scene(
        self,
        video_id: int,
        source_scene_id: Optional[int],
        target_scene_id: int,
        frame_numbers: Optional[List[int]] = None
    ) -> int:
        """
        Copy frames from one location to a scene directory

        Args:
            video_id: Video ID
            source_scene_id: Source scene ID (None for video-level frames)
            target_scene_id: Target scene ID
            frame_numbers: Optional list of specific frame numbers to copy

        Returns:
            Number of frames copied
        """
        source_dir = self.get_frame_directory(video_id, source_scene_id, create=False)
        target_dir = self.get_frame_directory(video_id, target_scene_id, create=True)

        if not source_dir.exists():
            logger.warning(f"Source directory doesn't exist: {source_dir}")
            return 0

        # Get frames to copy
        if frame_numbers:
            frames_to_copy = []
            for frame_num in frame_numbers:
                frame = self.get_frame_by_number(video_id, frame_num, source_scene_id)
                if frame:
                    frames_to_copy.append(frame)
        else:
            frames_to_copy = self.list_frames(video_id, source_scene_id)

        # Copy frames
        copied_count = 0

        for frame_path in frames_to_copy:
            target_path = target_dir / frame_path.name

            try:
                shutil.copy2(str(frame_path), str(target_path))
                copied_count += 1
                logger.debug(f"Copied frame to {target_path}")

            except Exception as e:
                logger.error(f"Failed to copy frame {frame_path}: {e}")
                continue

        logger.info(
            f"Copied {copied_count}/{len(frames_to_copy)} frames "
            f"to scene {target_scene_id}"
        )

        return copied_count


# Singleton instance
frame_storage = FrameStorageManager()
