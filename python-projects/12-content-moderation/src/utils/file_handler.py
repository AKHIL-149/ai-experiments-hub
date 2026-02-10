"""
File Handler Utility for Content Moderation.

Handles file uploads, storage, thumbnail generation, and validation.
"""

import hashlib
import logging
import os
import uuid
from pathlib import Path
from typing import Tuple, Optional
from PIL import Image


logging.basicConfig(level=logging.INFO)


class FileHandler:
    """Handle file operations for uploaded content."""

    # Supported file types
    ALLOWED_IMAGE_TYPES = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
    ALLOWED_VIDEO_TYPES = {'.mp4', '.mov', '.avi', '.webm'}

    # Size limits (in bytes)
    MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB default

    # Thumbnail settings
    THUMBNAIL_SIZE = (300, 300)  # Max dimensions
    THUMBNAIL_QUALITY = 85

    def __init__(
        self,
        upload_dir: Optional[str] = None,
        thumbnail_dir: Optional[str] = None,
        max_size_mb: Optional[int] = None
    ):
        """
        Initialize file handler.

        Args:
            upload_dir: Directory for uploads
            thumbnail_dir: Directory for thumbnails
            max_size_mb: Maximum file size in MB
        """
        self.upload_dir = Path(upload_dir or os.getenv('UPLOAD_DIR', './data/uploads'))
        self.thumbnail_dir = Path(thumbnail_dir or os.getenv('THUMBNAIL_DIR', './data/thumbnails'))

        # Create directories
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.thumbnail_dir.mkdir(parents=True, exist_ok=True)

        # Set max size
        max_size_mb = max_size_mb or int(os.getenv('MAX_UPLOAD_SIZE_MB', '100'))
        self.max_upload_size = max_size_mb * 1024 * 1024

        logging.info(f"FileHandler initialized: uploads={self.upload_dir}, thumbs={self.thumbnail_dir}")

    def save_upload(
        self,
        file_data: bytes,
        filename: str,
        user_id: str,
        content_type: str
    ) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
        """
        Save uploaded file.

        Args:
            file_data: File bytes
            filename: Original filename
            user_id: User ID
            content_type: Content type (image, video)

        Returns:
            Tuple of (success, file_path, file_hash, error_message)
        """
        # Validate file size
        if len(file_data) > self.max_upload_size:
            max_mb = self.max_upload_size / (1024 * 1024)
            return False, None, None, f"File too large. Maximum size: {max_mb:.0f}MB"

        # Validate file type
        file_ext = Path(filename).suffix.lower() if filename else '.bin'

        if content_type == 'image':
            if file_ext not in self.ALLOWED_IMAGE_TYPES:
                return False, None, None, f"Invalid image type. Allowed: {', '.join(self.ALLOWED_IMAGE_TYPES)}"
        elif content_type == 'video':
            if file_ext not in self.ALLOWED_VIDEO_TYPES:
                return False, None, None, f"Invalid video type. Allowed: {', '.join(self.ALLOWED_VIDEO_TYPES)}"
        else:
            return False, None, None, f"Unsupported content type: {content_type}"

        # Calculate file hash
        file_hash = hashlib.sha256(file_data).hexdigest()

        # Generate unique filename
        unique_name = f"{user_id}_{content_type}_{uuid.uuid4().hex[:8]}{file_ext}"
        file_path = self.upload_dir / unique_name

        # Save file
        try:
            with open(file_path, 'wb') as f:
                f.write(file_data)

            logging.info(f"File saved: {file_path} ({len(file_data)} bytes)")
            return True, str(file_path), file_hash, None

        except Exception as e:
            logging.error(f"Failed to save file: {e}")
            return False, None, None, f"Failed to save file: {str(e)}"

    def generate_thumbnail(
        self,
        image_path: str,
        size: Optional[Tuple[int, int]] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Generate thumbnail for image.

        Args:
            image_path: Path to source image
            size: Thumbnail size (width, height)

        Returns:
            Tuple of (success, thumbnail_path, error_message)
        """
        size = size or self.THUMBNAIL_SIZE

        try:
            # Open image
            with Image.open(image_path) as img:
                # Convert to RGB if needed (for PNG with transparency)
                if img.mode in ('RGBA', 'LA', 'P'):
                    # Create white background
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                    img = background
                elif img.mode != 'RGB':
                    img = img.convert('RGB')

                # Calculate thumbnail size (maintain aspect ratio)
                img.thumbnail(size, Image.Resampling.LANCZOS)

                # Generate thumbnail path
                source_path = Path(image_path)
                thumb_name = f"thumb_{source_path.stem}.jpg"
                thumb_path = self.thumbnail_dir / thumb_name

                # Save thumbnail
                img.save(thumb_path, 'JPEG', quality=self.THUMBNAIL_QUALITY, optimize=True)

                logging.info(f"Thumbnail generated: {thumb_path}")
                return True, str(thumb_path), None

        except Exception as e:
            logging.error(f"Thumbnail generation failed for {image_path}: {e}")
            return False, None, f"Thumbnail generation failed: {str(e)}"

    def delete_file(self, file_path: str) -> bool:
        """
        Delete file and associated thumbnail.

        Args:
            file_path: Path to file

        Returns:
            True if deleted successfully
        """
        try:
            # Delete main file
            path = Path(file_path)
            if path.exists():
                path.unlink()
                logging.info(f"File deleted: {file_path}")

            # Delete thumbnail if exists
            thumb_name = f"thumb_{path.stem}.jpg"
            thumb_path = self.thumbnail_dir / thumb_name
            if thumb_path.exists():
                thumb_path.unlink()
                logging.info(f"Thumbnail deleted: {thumb_path}")

            return True

        except Exception as e:
            logging.error(f"Failed to delete file {file_path}: {e}")
            return False

    def get_thumbnail_path(self, image_path: str) -> Optional[str]:
        """
        Get thumbnail path for image.

        Args:
            image_path: Path to source image

        Returns:
            Thumbnail path if exists, None otherwise
        """
        source_path = Path(image_path)
        thumb_name = f"thumb_{source_path.stem}.jpg"
        thumb_path = self.thumbnail_dir / thumb_name

        if thumb_path.exists():
            return str(thumb_path)
        return None

    def validate_image(self, image_path: str) -> Tuple[bool, Optional[str]]:
        """
        Validate that file is a valid image.

        Args:
            image_path: Path to image

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            with Image.open(image_path) as img:
                # Try to load image data
                img.verify()

            # Re-open to get format info (verify closes the image)
            with Image.open(image_path) as img:
                format_name = img.format
                width, height = img.size

                logging.info(f"Image validated: {format_name} {width}x{height}")
                return True, None

        except Exception as e:
            logging.error(f"Invalid image {image_path}: {e}")
            return False, f"Invalid image file: {str(e)}"

    def get_image_info(self, image_path: str) -> Optional[dict]:
        """
        Get image metadata.

        Args:
            image_path: Path to image

        Returns:
            Dictionary with image info or None if invalid
        """
        try:
            with Image.open(image_path) as img:
                return {
                    'format': img.format,
                    'mode': img.mode,
                    'width': img.size[0],
                    'height': img.size[1],
                    'size_bytes': Path(image_path).stat().st_size
                }
        except Exception as e:
            logging.error(f"Failed to get image info for {image_path}: {e}")
            return None

    @staticmethod
    def calculate_file_hash(file_path: str) -> str:
        """
        Calculate SHA256 hash of file.

        Args:
            file_path: Path to file

        Returns:
            Hex digest of SHA256 hash
        """
        sha256 = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def is_image_file(filename: str) -> bool:
        """Check if filename is an image."""
        ext = Path(filename).suffix.lower()
        return ext in FileHandler.ALLOWED_IMAGE_TYPES

    @staticmethod
    def is_video_file(filename: str) -> bool:
        """Check if filename is a video."""
        ext = Path(filename).suffix.lower()
        return ext in FileHandler.ALLOWED_VIDEO_TYPES


# Global file handler instance
_file_handler_instance = None


def get_file_handler() -> FileHandler:
    """
    Get global FileHandler instance.

    Returns:
        FileHandler singleton
    """
    global _file_handler_instance
    if _file_handler_instance is None:
        _file_handler_instance = FileHandler()
    return _file_handler_instance
