"""
Storage utilities for managing video files, frames, and assets
"""

import hashlib
import logging
import os
import shutil
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from src.core.config import settings

logger = logging.getLogger(__name__)


class StorageManager:
    """
    Manager for organizing and managing storage of videos, frames, clips, and temp files
    """

    def __init__(self):
        """Initialize storage manager with configured paths"""
        self.base_path = Path(settings.storage_base_path)
        self.videos_path = Path(settings.videos_path)
        self.frames_path = Path(settings.frames_path)
        self.clips_path = Path(settings.clips_path)
        self.temp_path = Path(settings.temp_path)
        self.cache_path = Path(settings.cache_path)

        # Create directories
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Create storage directories if they don't exist"""
        for path in [
            self.base_path,
            self.videos_path,
            self.frames_path,
            self.clips_path,
            self.temp_path,
            self.cache_path,
        ]:
            path.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Storage directory ensured: {path}")

    def get_video_path(self, video_id: int, filename: str) -> Path:
        """
        Get storage path for a video file

        Args:
            video_id: Video ID
            filename: Original filename

        Returns:
            Path to store video
        """
        video_dir = self.videos_path / str(video_id)
        video_dir.mkdir(parents=True, exist_ok=True)
        return video_dir / filename

    def get_frames_directory(self, video_id: int, scene_id: Optional[int] = None) -> Path:
        """
        Get directory for storing video frames

        Args:
            video_id: Video ID
            scene_id: Optional scene ID for scene-specific frames

        Returns:
            Path to frames directory
        """
        if scene_id:
            frames_dir = self.frames_path / str(video_id) / f"scene_{scene_id}"
        else:
            frames_dir = self.frames_path / str(video_id)

        frames_dir.mkdir(parents=True, exist_ok=True)
        return frames_dir

    def get_frame_path(
        self,
        video_id: int,
        frame_number: int,
        timestamp: float,
        scene_id: Optional[int] = None,
        is_keyframe: bool = False,
    ) -> Path:
        """
        Get storage path for a frame image

        Args:
            video_id: Video ID
            frame_number: Frame number
            timestamp: Frame timestamp
            scene_id: Optional scene ID
            is_keyframe: Whether this is a keyframe

        Returns:
            Path to store frame image
        """
        frames_dir = self.get_frames_directory(video_id, scene_id)
        prefix = "keyframe" if is_keyframe else "frame"
        filename = f"{prefix}_{frame_number:06d}_{timestamp:.2f}s.jpg"
        return frames_dir / filename

    def get_clip_path(self, video_id: int, clip_id: int, title: str = "") -> Path:
        """
        Get storage path for a video clip

        Args:
            video_id: Parent video ID
            clip_id: Clip ID
            title: Optional clip title for filename

        Returns:
            Path to store clip
        """
        clip_dir = self.clips_path / str(video_id)
        clip_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize title for filename
        safe_title = self._sanitize_filename(title) if title else ""
        filename = f"clip_{clip_id}_{safe_title}.mp4" if safe_title else f"clip_{clip_id}.mp4"

        return clip_dir / filename

    def get_temp_path(self, filename: str) -> Path:
        """
        Get path for temporary file

        Args:
            filename: Temporary filename

        Returns:
            Path to temporary file
        """
        return self.temp_path / filename

    def get_thumbnail_path(self, video_id: int, frame_number: int = 0) -> Path:
        """
        Get storage path for video thumbnail

        Args:
            video_id: Video ID
            frame_number: Frame number for thumbnail

        Returns:
            Path to store thumbnail
        """
        video_dir = self.videos_path / str(video_id)
        video_dir.mkdir(parents=True, exist_ok=True)
        return video_dir / f"thumbnail_{frame_number}.jpg"

    @staticmethod
    def compute_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
        """
        Compute hash of a file

        Args:
            file_path: Path to file
            algorithm: Hash algorithm (md5, sha1, sha256)

        Returns:
            Hex digest of file hash
        """
        hash_obj = hashlib.new(algorithm)
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                hash_obj.update(chunk)
        return hash_obj.hexdigest()

    @staticmethod
    def compute_video_hash(file_path: Path) -> str:
        """
        Compute SHA256 hash of video file for deduplication

        Args:
            file_path: Path to video file

        Returns:
            SHA256 hash of video
        """
        return StorageManager.compute_file_hash(file_path, algorithm="sha256")

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """
        Sanitize filename by removing invalid characters

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        # Remove invalid characters
        invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in invalid_chars:
            filename = filename.replace(char, '_')

        # Limit length
        if len(filename) > 100:
            filename = filename[:100]

        return filename

    def get_directory_size(self, directory: Path) -> int:
        """
        Get total size of directory in bytes

        Args:
            directory: Directory path

        Returns:
            Total size in bytes
        """
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                file_path = Path(dirpath) / filename
                if file_path.exists():
                    total_size += file_path.stat().st_size
        return total_size

    def get_storage_stats(self) -> dict:
        """
        Get storage statistics

        Returns:
            Dictionary with storage stats
        """
        return {
            'base_path': str(self.base_path),
            'videos': {
                'path': str(self.videos_path),
                'size_mb': round(self.get_directory_size(self.videos_path) / (1024 * 1024), 2),
                'count': len(list(self.videos_path.rglob('*.mp4'))) + len(list(self.videos_path.rglob('*.mkv'))),
            },
            'frames': {
                'path': str(self.frames_path),
                'size_mb': round(self.get_directory_size(self.frames_path) / (1024 * 1024), 2),
                'count': len(list(self.frames_path.rglob('*.jpg'))) + len(list(self.frames_path.rglob('*.png'))),
            },
            'clips': {
                'path': str(self.clips_path),
                'size_mb': round(self.get_directory_size(self.clips_path) / (1024 * 1024), 2),
                'count': len(list(self.clips_path.rglob('*.mp4'))),
            },
            'temp': {
                'path': str(self.temp_path),
                'size_mb': round(self.get_directory_size(self.temp_path) / (1024 * 1024), 2),
            },
            'cache': {
                'path': str(self.cache_path),
                'size_mb': round(self.get_directory_size(self.cache_path) / (1024 * 1024), 2),
            },
        }

    def cleanup_temp_files(self, older_than_hours: int = 24) -> int:
        """
        Remove old temporary files

        Args:
            older_than_hours: Remove files older than this many hours

        Returns:
            Number of files removed
        """
        count = 0
        cutoff_time = datetime.now().timestamp() - (older_than_hours * 3600)

        for temp_file in self.temp_path.rglob('*'):
            if temp_file.is_file():
                if temp_file.stat().st_mtime < cutoff_time:
                    temp_file.unlink()
                    count += 1

        if count > 0:
            logger.info(f"Cleaned up {count} temporary files older than {older_than_hours} hours")

        return count

    def cleanup_video_data(self, video_id: int) -> bool:
        """
        Remove all data associated with a video

        Args:
            video_id: Video ID to clean up

        Returns:
            True if successful
        """
        try:
            # Remove video directory
            video_dir = self.videos_path / str(video_id)
            if video_dir.exists():
                shutil.rmtree(video_dir)

            # Remove frames directory
            frames_dir = self.frames_path / str(video_id)
            if frames_dir.exists():
                shutil.rmtree(frames_dir)

            # Remove clips directory
            clips_dir = self.clips_path / str(video_id)
            if clips_dir.exists():
                shutil.rmtree(clips_dir)

            logger.info(f"Cleaned up all data for video {video_id}")
            return True

        except Exception as e:
            logger.error(f"Error cleaning up video {video_id}: {e}")
            return False

    def move_file(self, source: Path, destination: Path) -> bool:
        """
        Move file from source to destination

        Args:
            source: Source file path
            destination: Destination file path

        Returns:
            True if successful
        """
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))
            logger.debug(f"Moved file: {source} -> {destination}")
            return True
        except Exception as e:
            logger.error(f"Error moving file: {e}")
            return False

    def copy_file(self, source: Path, destination: Path) -> bool:
        """
        Copy file from source to destination

        Args:
            source: Source file path
            destination: Destination file path

        Returns:
            True if successful
        """
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(destination))
            logger.debug(f"Copied file: {source} -> {destination}")
            return True
        except Exception as e:
            logger.error(f"Error copying file: {e}")
            return False


# Singleton instance
storage_manager = StorageManager()
