"""
Frame preprocessing utilities for preparing frames for ML models
Handles resizing, normalization, and aspect ratio management
"""

import logging
from pathlib import Path
from typing import Optional, Tuple, Union, List
from enum import Enum
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class ResizeMode(str, Enum):
    """Frame resizing modes"""
    STRETCH = "stretch"  # Stretch to target size (may distort)
    FIT = "fit"  # Fit inside target size (maintains aspect ratio, may have padding)
    FILL = "fill"  # Fill target size (maintains aspect ratio, may crop)
    CENTER_CROP = "center_crop"  # Crop to target size from center


class NormalizationMode(str, Enum):
    """Pixel value normalization modes"""
    NONE = "none"  # No normalization (0-255)
    ZERO_ONE = "zero_one"  # Scale to [0, 1]
    NEG_ONE_ONE = "neg_one_one"  # Scale to [-1, 1]
    IMAGENET = "imagenet"  # ImageNet normalization (mean/std)
    CLIP = "clip"  # CLIP model normalization


class FramePreprocessor:
    """
    Preprocess video frames for machine learning models
    """

    # ImageNet normalization constants
    IMAGENET_MEAN = np.array([0.485, 0.456, 0.406])
    IMAGENET_STD = np.array([0.229, 0.224, 0.225])

    # CLIP normalization constants
    CLIP_MEAN = np.array([0.48145466, 0.4578275, 0.40821073])
    CLIP_STD = np.array([0.26862954, 0.26130258, 0.27577711])

    def __init__(
        self,
        target_size: Tuple[int, int] = (224, 224),
        resize_mode: ResizeMode = ResizeMode.FIT,
        normalization: NormalizationMode = NormalizationMode.ZERO_ONE,
        convert_to_rgb: bool = True
    ):
        """
        Initialize frame preprocessor

        Args:
            target_size: Target size as (width, height)
            resize_mode: How to resize frames
            normalization: Pixel value normalization method
            convert_to_rgb: Convert images to RGB
        """
        self.target_size = target_size
        self.resize_mode = resize_mode
        self.normalization = normalization
        self.convert_to_rgb = convert_to_rgb

    def preprocess(
        self,
        frame: Union[Path, Image.Image, np.ndarray]
    ) -> np.ndarray:
        """
        Preprocess a single frame

        Args:
            frame: Frame as file path, PIL Image, or numpy array

        Returns:
            Preprocessed frame as numpy array

        Raises:
            ValueError: If frame cannot be loaded or processed
        """
        # Load frame if it's a path
        if isinstance(frame, (Path, str)):
            if not Path(frame).exists():
                raise ValueError(f"Frame file not found: {frame}")
            image = Image.open(frame)
        elif isinstance(frame, np.ndarray):
            image = Image.fromarray(frame)
        elif isinstance(frame, Image.Image):
            image = frame
        else:
            raise ValueError(f"Unsupported frame type: {type(frame)}")

        # Convert to RGB if needed
        if self.convert_to_rgb and image.mode != 'RGB':
            image = image.convert('RGB')

        # Resize
        image = self._resize(image)

        # Convert to numpy array
        array = np.array(image, dtype=np.float32)

        # Normalize
        array = self._normalize(array)

        return array

    def preprocess_batch(
        self,
        frames: List[Union[Path, Image.Image, np.ndarray]]
    ) -> np.ndarray:
        """
        Preprocess multiple frames

        Args:
            frames: List of frames

        Returns:
            Batch of preprocessed frames as numpy array (batch_size, height, width, channels)
        """
        preprocessed = []

        for frame in frames:
            try:
                processed = self.preprocess(frame)
                preprocessed.append(processed)
            except Exception as e:
                logger.error(f"Failed to preprocess frame: {e}")
                continue

        if not preprocessed:
            raise ValueError("No frames were successfully preprocessed")

        # Stack into batch
        batch = np.stack(preprocessed, axis=0)

        logger.debug(f"Preprocessed batch of {len(preprocessed)} frames, shape: {batch.shape}")

        return batch

    def _resize(self, image: Image.Image) -> Image.Image:
        """
        Resize image according to resize mode

        Args:
            image: PIL Image

        Returns:
            Resized PIL Image
        """
        target_width, target_height = self.target_size
        current_width, current_height = image.size

        if self.resize_mode == ResizeMode.STRETCH:
            # Simply resize, ignoring aspect ratio
            return image.resize(self.target_size, Image.Resampling.LANCZOS)

        elif self.resize_mode == ResizeMode.FIT:
            # Resize to fit inside target size, maintaining aspect ratio
            # Then pad if necessary
            aspect_ratio = current_width / current_height
            target_aspect = target_width / target_height

            if aspect_ratio > target_aspect:
                # Width is limiting factor
                new_width = target_width
                new_height = int(target_width / aspect_ratio)
            else:
                # Height is limiting factor
                new_height = target_height
                new_width = int(target_height * aspect_ratio)

            # Resize
            resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Create padded image
            padded = Image.new('RGB', self.target_size, (0, 0, 0))

            # Calculate padding
            x_offset = (target_width - new_width) // 2
            y_offset = (target_height - new_height) // 2

            # Paste resized image onto padded canvas
            padded.paste(resized, (x_offset, y_offset))

            return padded

        elif self.resize_mode == ResizeMode.FILL:
            # Resize to fill target size, maintaining aspect ratio
            # May crop if aspect ratios don't match
            aspect_ratio = current_width / current_height
            target_aspect = target_width / target_height

            if aspect_ratio > target_aspect:
                # Height is limiting factor
                new_height = target_height
                new_width = int(target_height * aspect_ratio)
            else:
                # Width is limiting factor
                new_width = target_width
                new_height = int(target_width / aspect_ratio)

            # Resize
            resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Crop from center
            x_offset = (new_width - target_width) // 2
            y_offset = (new_height - target_height) // 2

            cropped = resized.crop((
                x_offset,
                y_offset,
                x_offset + target_width,
                y_offset + target_height
            ))

            return cropped

        elif self.resize_mode == ResizeMode.CENTER_CROP:
            # First, resize so smaller dimension matches target
            # Then crop from center
            aspect_ratio = current_width / current_height
            target_aspect = target_width / target_height

            if aspect_ratio > target_aspect:
                # Resize based on height
                new_height = target_height
                new_width = int(target_height * aspect_ratio)
            else:
                # Resize based on width
                new_width = target_width
                new_height = int(target_width / aspect_ratio)

            resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Crop from center
            x_offset = (new_width - target_width) // 2
            y_offset = (new_height - target_height) // 2

            cropped = resized.crop((
                x_offset,
                y_offset,
                x_offset + target_width,
                y_offset + target_height
            ))

            return cropped

        else:
            raise ValueError(f"Unknown resize mode: {self.resize_mode}")

    def _normalize(self, array: np.ndarray) -> np.ndarray:
        """
        Normalize pixel values

        Args:
            array: Numpy array with pixel values

        Returns:
            Normalized numpy array
        """
        if self.normalization == NormalizationMode.NONE:
            # No normalization
            return array

        elif self.normalization == NormalizationMode.ZERO_ONE:
            # Scale to [0, 1]
            return array / 255.0

        elif self.normalization == NormalizationMode.NEG_ONE_ONE:
            # Scale to [-1, 1]
            return (array / 127.5) - 1.0

        elif self.normalization == NormalizationMode.IMAGENET:
            # ImageNet normalization
            # First scale to [0, 1]
            array = array / 255.0

            # Then apply ImageNet mean/std
            array = (array - self.IMAGENET_MEAN) / self.IMAGENET_STD

            return array

        elif self.normalization == NormalizationMode.CLIP:
            # CLIP normalization
            # First scale to [0, 1]
            array = array / 255.0

            # Then apply CLIP mean/std
            array = (array - self.CLIP_MEAN) / self.CLIP_STD

            return array

        else:
            raise ValueError(f"Unknown normalization mode: {self.normalization}")

    def denormalize(self, array: np.ndarray) -> np.ndarray:
        """
        Reverse normalization to get original pixel values

        Args:
            array: Normalized numpy array

        Returns:
            Denormalized array with values in [0, 255]
        """
        if self.normalization == NormalizationMode.NONE:
            return array

        elif self.normalization == NormalizationMode.ZERO_ONE:
            return array * 255.0

        elif self.normalization == NormalizationMode.NEG_ONE_ONE:
            return (array + 1.0) * 127.5

        elif self.normalization == NormalizationMode.IMAGENET:
            # Reverse ImageNet normalization
            array = array * self.IMAGENET_STD + self.IMAGENET_MEAN
            return array * 255.0

        elif self.normalization == NormalizationMode.CLIP:
            # Reverse CLIP normalization
            array = array * self.CLIP_STD + self.CLIP_MEAN
            return array * 255.0

        else:
            raise ValueError(f"Unknown normalization mode: {self.normalization}")

    def save_preprocessed(
        self,
        array: np.ndarray,
        output_path: Path,
        denormalize: bool = True
    ) -> Path:
        """
        Save preprocessed frame to file

        Args:
            array: Preprocessed numpy array
            output_path: Path to save image
            denormalize: Whether to denormalize before saving

        Returns:
            Path to saved file
        """
        # Denormalize if requested
        if denormalize:
            array = self.denormalize(array)

        # Ensure values are in valid range
        array = np.clip(array, 0, 255).astype(np.uint8)

        # Convert to PIL Image and save
        image = Image.fromarray(array)
        image.save(output_path)

        logger.debug(f"Saved preprocessed frame to {output_path}")

        return output_path


def preprocess_frame(
    frame: Union[Path, Image.Image, np.ndarray],
    target_size: Tuple[int, int] = (224, 224),
    resize_mode: ResizeMode = ResizeMode.FIT,
    normalization: NormalizationMode = NormalizationMode.ZERO_ONE
) -> np.ndarray:
    """
    Convenience function to preprocess a single frame

    Args:
        frame: Frame to preprocess
        target_size: Target size as (width, height)
        resize_mode: How to resize
        normalization: Normalization method

    Returns:
        Preprocessed frame as numpy array
    """
    preprocessor = FramePreprocessor(
        target_size=target_size,
        resize_mode=resize_mode,
        normalization=normalization
    )
    return preprocessor.preprocess(frame)


def create_preprocessor_for_model(
    model_name: str
) -> FramePreprocessor:
    """
    Create preprocessor with settings for specific models

    Args:
        model_name: Model name (clip, resnet, vit, etc.)

    Returns:
        Configured FramePreprocessor
    """
    model_name = model_name.lower()

    if "clip" in model_name:
        # CLIP models typically use 224x224
        return FramePreprocessor(
            target_size=(224, 224),
            resize_mode=ResizeMode.CENTER_CROP,
            normalization=NormalizationMode.CLIP,
            convert_to_rgb=True
        )

    elif "resnet" in model_name or "vgg" in model_name:
        # ImageNet-pretrained models
        return FramePreprocessor(
            target_size=(224, 224),
            resize_mode=ResizeMode.CENTER_CROP,
            normalization=NormalizationMode.IMAGENET,
            convert_to_rgb=True
        )

    elif "vit" in model_name or "vision" in model_name:
        # Vision Transformer models
        return FramePreprocessor(
            target_size=(224, 224),
            resize_mode=ResizeMode.CENTER_CROP,
            normalization=NormalizationMode.IMAGENET,
            convert_to_rgb=True
        )

    elif "yolo" in model_name:
        # YOLO models typically use 640x640
        return FramePreprocessor(
            target_size=(640, 640),
            resize_mode=ResizeMode.FIT,
            normalization=NormalizationMode.ZERO_ONE,
            convert_to_rgb=True
        )

    else:
        # Default configuration
        logger.warning(f"Unknown model: {model_name}, using default preprocessing")
        return FramePreprocessor(
            target_size=(224, 224),
            resize_mode=ResizeMode.FIT,
            normalization=NormalizationMode.ZERO_ONE,
            convert_to_rgb=True
        )
