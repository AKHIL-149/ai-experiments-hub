"""Image processing utilities for loading, validation, and preprocessing."""
import io
import os
import base64
from pathlib import Path
from typing import Union, Dict, Any, Optional, Tuple
from PIL import Image, ImageOps
import requests


class ImageError(ValueError):
    """An image that cannot be used; the message is one line a user can act on."""


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return float(default)


def max_upload_bytes() -> int:
    """Largest file accepted (MAX_UPLOAD_MB, default 25)."""
    return int(_env_float('MAX_UPLOAD_MB', 25) * 1024 * 1024)


def max_pixels() -> int:
    """Most pixels accepted (MAX_IMAGE_PIXELS, default 80 million). Guards memory against 'decompression bombs'."""
    return int(_env_float('MAX_IMAGE_PIXELS', 80_000_000))


class ImageProcessor:
    """Image preprocessing and validation."""

    # MPO is what many phone cameras write into .jpg files
    SUPPORTED_FORMATS = ['PNG', 'JPEG', 'JPG', 'MPO', 'WEBP', 'GIF', 'BMP', 'TIFF']

    def __init__(self):
        """Initialize image processor."""
        pass

    # ------------------------------------------------------------------ opening

    def open_bytes(self, data: bytes, max_bytes: Optional[int] = None) -> Image.Image:
        """Open uploaded bytes as an image, refusing anything unsafe or unreadable.

        Checks the size and the pixel count before decoding, then fully decodes once so a truncated
        file fails here (with a clear message) and not later inside a model call. The image is
        returned upright (EXIF orientation applied) and, for animations, as the first frame.

        Raises:
            ImageError: with a one-line reason
        """
        limit = max_bytes if max_bytes is not None else max_upload_bytes()
        if not data:
            raise ImageError("The file is empty")
        if len(data) > limit:
            raise ImageError(f"The file is {len(data) / 1024 / 1024:.1f} MB; the limit is {limit / 1024 / 1024:.0f} MB")

        try:
            image = Image.open(io.BytesIO(data))
        except Image.DecompressionBombError:
            raise ImageError("The image has too many pixels to open safely")
        except Exception:
            raise ImageError("The file is not an image Pillow can read (supported: PNG, JPEG, WebP, GIF, BMP, TIFF)")

        if image.width * image.height > max_pixels():
            raise ImageError(
                f"The image is {image.width}x{image.height} ({image.width * image.height / 1e6:.0f} megapixels); "
                f"the limit is {max_pixels() / 1e6:.0f} megapixels"
            )
        fmt = image.format
        try:
            image.load()
        except Image.DecompressionBombError:
            raise ImageError("The image has too many pixels to open safely")
        except Exception as error:
            raise ImageError(f"The image file is damaged or cut off ({' '.join(str(error).split())[:80]})")
        image.format = fmt          # load() can drop it for some formats
        result = self.normalize(image)
        result.source_bytes = len(data)       # for reporting; the original file size is not recoverable later
        return result

    def normalize(self, image: Image.Image) -> Image.Image:
        """The image as people see it: upright, and in a mode every consumer understands.

        Applies the EXIF orientation (phone photos are often stored sideways), keeps only the first
        frame of an animation, and converts palette / CMYK / 16-bit / transparent images to RGB
        (transparency is composited on white, not turned black).
        """
        fmt = image.format
        try:
            image.seek(0)
        except EOFError:
            pass
        upright = ImageOps.exif_transpose(image)
        if upright is None:
            upright = image

        mode = upright.mode
        if mode in ('RGB', 'L'):
            result = upright
        elif mode in ('RGBA', 'LA') or (mode == 'P' and 'transparency' in upright.info):
            rgba = upright.convert('RGBA')
            background = Image.new('RGB', rgba.size, 'white')
            background.paste(rgba, mask=rgba.getchannel('A'))
            result = background
        elif mode in ('I;16', 'I;16L', 'I;16B', 'I'):
            result = upright.point(lambda v: v / 256).convert('L')
        else:                                              # P, 1, CMYK, YCbCr, LAB, HSV, F ...
            result = upright.convert('RGB')
        if result is image:
            return image
        result.format = fmt
        return result

    # ------------------------------------------------------------------ loading (CLI)

    def load_image(
        self,
        image_input: Union[str, Path, bytes]
    ) -> Image.Image:
        """Load image from various input formats.

        Args:
            image_input: File path, URL, or bytes

        Returns:
            PIL.Image.Image: Loaded image (upright, first frame)

        Raises:
            ValueError: If image cannot be loaded
        """
        try:
            if isinstance(image_input, bytes):
                return self.open_bytes(image_input)

            elif isinstance(image_input, (str, Path)):
                path_str = str(image_input)

                if path_str.startswith(('http://', 'https://')):
                    return self.download_from_url(path_str)
                path = Path(path_str).expanduser()
                if not path.exists():
                    raise FileNotFoundError(f"Image file not found: {path}")
                if not path.is_file():
                    raise ImageError(f"{path} is not a file")
                return self.open_bytes(path.read_bytes())
            else:
                raise TypeError(f"Unsupported image input type: {type(image_input)}")

        except Exception as e:
            raise ValueError(f"Failed to load image: {str(e)}")

    def download_from_url(self, url: str) -> Image.Image:
        """Download image from URL (size-limited while streaming).

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
            limit = max_upload_bytes()
            with requests.get(url, headers=headers, timeout=30, stream=True) as response:
                response.raise_for_status()
                chunks, total = [], 0
                for chunk in response.iter_content(chunk_size=65536):
                    total += len(chunk)
                    if total > limit:
                        raise ImageError(f"The download is larger than the {limit / 1024 / 1024:.0f} MB limit")
                    chunks.append(chunk)
            return self.open_bytes(b''.join(chunks))
        except Exception as e:
            raise ValueError(f"Failed to download image from {url}: {str(e)}")

    # ------------------------------------------------------------------ validation

    def validate_image(self, image: Image.Image, size_bytes: Optional[int] = None) -> Dict[str, Any]:
        """Validate image format and properties.

        Args:
            image: PIL Image
            size_bytes: Size of the original file when known (otherwise it is not measured: encoding
                the image again just to learn a size is slow and gives a made-up number)

        Returns:
            dict: Validation result with 'valid', 'format', 'size', 'dimensions'
        """
        result = {
            'valid': True,
            'format': image.format,
            'size_bytes': size_bytes or getattr(image, 'source_bytes', 0),
            'width': image.width,
            'height': image.height,
            'mode': image.mode,
            'errors': []
        }
        result['size_mb'] = result['size_bytes'] / (1024 * 1024)

        # Check format
        if image.format not in self.SUPPORTED_FORMATS:
            result['valid'] = False
            result['errors'].append(f"Unsupported format: {image.format}")

        if image.width < 1 or image.height < 1:
            result['valid'] = False
            result['errors'].append("The image has no pixels")

        return result

    def extract_metadata(self, image: Image.Image, size_bytes: Optional[int] = None) -> Dict[str, Any]:
        """Extract image metadata.

        Args:
            image: PIL Image
            size_bytes: Size of the original file when known

        Returns:
            dict: Metadata including format, size, dimensions, mode
        """
        metadata = {
            'format': image.format or 'Unknown',
            'mode': image.mode,
            'width': image.width,
            'height': image.height,
            'size_bytes': size_bytes or getattr(image, 'source_bytes', 0),
            'size_mb': round((size_bytes or getattr(image, 'source_bytes', 0)) / (1024 * 1024), 2),
            'dimensions': f"{image.width}x{image.height}"
        }

        # EXIF values that are plain text or numbers (Pillow's public API, not the private _getexif)
        try:
            exif = image.getexif()
            if exif:
                metadata['exif'] = {k: v for k, v in exif.items() if isinstance(v, (str, int, float))}
        except Exception:
            pass  # EXIF not available

        return metadata

    # ------------------------------------------------------------------ preparing for a model

    def encode_for_model(
        self,
        image: Image.Image,
        max_dimension: Optional[int] = None,
        max_encoded_mb: Optional[float] = None
    ) -> Tuple[bytes, str]:
        """The image as bytes a model accepts, and the media type those bytes really are.

        Scaled down to MAX_IMAGE_DIMENSION (default 2048; local vision models shrink images far
        below that anyway) and, if needed, compressed to fit MAX_IMAGE_SIZE_MB (default 3.75, what
        the hosted providers' 5 MB limit allows after base64). Small images stay lossless PNG;
        bigger ones become JPEG.
        """
        max_dimension = max_dimension or int(_env_float('MAX_IMAGE_DIMENSION', 2048))
        limit = int((max_encoded_mb or _env_float('MAX_IMAGE_SIZE_MB', 3.75)) * 1024 * 1024)

        image = self.normalize(image)
        image = self.resize_if_needed(image, max_dimension)

        if image.width * image.height <= 1_500_000:
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            if buffer.tell() <= limit:
                return buffer.getvalue(), 'image/png'

        rgb = image if image.mode == 'RGB' else image.convert('RGB')
        quality = 90
        while True:
            buffer = io.BytesIO()
            rgb.save(buffer, format='JPEG', quality=quality)
            if buffer.tell() <= limit or (quality <= 40 and max(rgb.size) <= 512):
                return buffer.getvalue(), 'image/jpeg'
            if quality > 40:
                quality -= 15
            else:
                rgb = rgb.resize((max(1, int(rgb.width * 0.75)), max(1, int(rgb.height * 0.75))), Image.Resampling.LANCZOS)

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

        # JPEG has no transparency or palette
        if format.upper() in ('JPEG', 'JPG') and image.mode != 'RGB':
            image = self.normalize(image).convert('RGB')

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
        scale = max_dimension / max(image.width, image.height)
        new_width = max(1, int(image.width * scale))
        new_height = max(1, int(image.height * scale))

        return image.resize((new_width, new_height), Image.Resampling.LANCZOS)
