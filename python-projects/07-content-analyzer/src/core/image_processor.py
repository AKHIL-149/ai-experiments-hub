"""Image processing utilities for loading, validation, and preprocessing."""
import io
import base64
from pathlib import Path
from typing import Union, Dict, Any
from PIL import Image
import requests


class ImageProcessor:
    """Image preprocessing and validation."""

    SUPPORTED_FORMATS = ['PNG', 'JPEG', 'JPG', 'WEBP', 'GIF', 'BMP']

    def __init__(self):
        """Initialize image processor."""
        pass

    def load_image(
        self,
        image_input: Union[str, Path, bytes]
    ) -> Image.Image:
        """Load image from various input formats.

        Args:
            image_input: File path, URL, or bytes

        Returns:
            PIL.Image.Image: Loaded image

        Raises:
            ValueError: If image cannot be loaded
        """
        try:
            if isinstance(image_input, bytes):
                # Load from bytes
                return Image.open(io.BytesIO(image_input))

            elif isinstance(image_input, (str, Path)):
                path_str = str(image_input)

                if path_str.startswith(('http://', 'https://')):
                    # Download from URL
                    return self.download_from_url(path_str)
                else:
                    # Load from file path
                    path = Path(path_str)
                    if not path.exists():
                        raise FileNotFoundError(f"Image file not found: {path}")
                    return Image.open(path)
            else:
                raise TypeError(f"Unsupported image input type: {type(image_input)}")

        except Exception as e:
            raise ValueError(f"Failed to load image: {str(e)}")

    def download_from_url(self, url: str) -> Image.Image:
        """Download image from URL.

        Args:
            url: Image URL

        Returns:
            PIL.Image.Image: Downloaded image

        Raises:
            ValueError: If download fails
        """
        try:
            # Add User-Agent header to avoid blocks from sites like Wikipedia
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return Image.open(io.BytesIO(response.content))
        except Exception as e:
            raise ValueError(f"Failed to download image from {url}: {str(e)}")

    def validate_image(self, image: Image.Image) -> Dict[str, Any]:
        """Validate image format and properties.

        Args:
            image: PIL Image

        Returns:
            dict: Validation result with 'valid', 'format', 'size', 'dimensions'
        """
        result = {
            'valid': True,
            'format': image.format,
            'size_bytes': 0,
            'width': image.width,
            'height': image.height,
            'mode': image.mode,
            'errors': []
        }

        # Check format
        if image.format not in self.SUPPORTED_FORMATS:
            result['valid'] = False
            result['errors'].append(f"Unsupported format: {image.format}")

        # Calculate size
        buffer = io.BytesIO()
        image.save(buffer, format=image.format or 'PNG')
        result['size_bytes'] = len(buffer.getvalue())
        result['size_mb'] = result['size_bytes'] / (1024 * 1024)

        return result

    def extract_metadata(self, image: Image.Image) -> Dict[str, Any]:
        """Extract image metadata.

        Args:
            image: PIL Image

        Returns:
            dict: Metadata including format, size, dimensions, mode
        """
        # Get file size
        buffer = io.BytesIO()
        image.save(buffer, format=image.format or 'PNG')
        size_bytes = len(buffer.getvalue())

        metadata = {
            'format': image.format or 'Unknown',
            'mode': image.mode,
            'width': image.width,
            'height': image.height,
            'size_bytes': size_bytes,
            'size_mb': round(size_bytes / (1024 * 1024), 2),
            'dimensions': f"{image.width}x{image.height}"
        }

        # Try to get EXIF data
        try:
            exif = image._getexif()
            if exif:
                metadata['exif'] = {k: v for k, v in exif.items() if isinstance(v, (str, int, float))}
        except:
            pass  # EXIF not available

        return metadata

    def to_base64(
        self,
        image: Image.Image,
        format: str = 'JPEG'
    ) -> str:
        """Convert PIL Image to base64 string.

        Args:
            image: PIL Image
            format: Output format (JPEG, PNG, etc.)

        Returns:
            str: Base64-encoded image
        """
        buffer = io.BytesIO()

        # Convert RGBA to RGB if saving as JPEG
        if format.upper() == 'JPEG' and image.mode == 'RGBA':
            image = image.convert('RGB')

        image.save(buffer, format=format)
        return base64.b64encode(buffer.getvalue()).decode('utf-8')

    def resize_if_needed(
        self,
        image: Image.Image,
        max_dimension: int = 8000
    ) -> Image.Image:
        """Resize image if it exceeds maximum dimension.

        Args:
            image: PIL Image
            max_dimension: Maximum width or height

        Returns:
            PIL.Image.Image: Resized image (or original if within limits)
        """
        if image.width <= max_dimension and image.height <= max_dimension:
            return image

        # Calculate new dimensions maintaining aspect ratio
        if image.width > image.height:
            new_width = max_dimension
            new_height = int(image.height * (max_dimension / image.width))
        else:
            new_height = max_dimension
            new_width = int(image.width * (max_dimension / image.height))

        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
