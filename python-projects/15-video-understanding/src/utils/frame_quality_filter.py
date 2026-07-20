"""
Frame quality filtering utilities
Filter out low-quality frames (blurry, dark, blank, etc.)
"""

import logging
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass
import numpy as np
from PIL import Image
import cv2

logger = logging.getLogger(__name__)


@dataclass
class QualityMetrics:
    """Quality metrics for a frame"""
    frame_path: Path
    blur_score: float  # Laplacian variance (higher = sharper)
    brightness: float  # Average pixel intensity (0-255)
    contrast: float  # Standard deviation of pixel intensity
    is_blank: bool  # Nearly uniform color
    is_blurry: bool  # Below blur threshold
    is_too_dark: bool  # Below brightness threshold
    is_too_bright: bool  # Above brightness threshold
    overall_quality: float  # Combined quality score (0-1)


class FrameQualityFilter:
    """
    Filter frames based on quality metrics
    """

    def __init__(
        self,
        blur_threshold: float = 100.0,
        brightness_min: float = 20.0,
        brightness_max: float = 235.0,
        contrast_min: float = 10.0,
        blank_threshold: float = 5.0,
        quality_threshold: float = 0.5
    ):
        """
        Initialize frame quality filter

        Args:
            blur_threshold: Minimum Laplacian variance (lower = more blurry)
            brightness_min: Minimum average brightness
            brightness_max: Maximum average brightness
            contrast_min: Minimum contrast (std dev of pixels)
            blank_threshold: Maximum std dev for blank frames
            quality_threshold: Minimum overall quality score to pass
        """
        self.blur_threshold = blur_threshold
        self.brightness_min = brightness_min
        self.brightness_max = brightness_max
        self.contrast_min = contrast_min
        self.blank_threshold = blank_threshold
        self.quality_threshold = quality_threshold

    def compute_metrics(self, frame_path: Path) -> QualityMetrics:
        """
        Compute quality metrics for a frame

        Args:
            frame_path: Path to frame image

        Returns:
            QualityMetrics object

        Raises:
            ValueError: If frame cannot be loaded
        """
        if not frame_path.exists():
            raise ValueError(f"Frame not found: {frame_path}")

        try:
            # Load image
            image = cv2.imread(str(frame_path))
            if image is None:
                raise ValueError(f"Failed to load image: {frame_path}")

            # Convert to grayscale for some metrics
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # Compute blur score (Laplacian variance)
            blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()

            # Compute brightness (average pixel intensity)
            brightness = float(np.mean(gray))

            # Compute contrast (standard deviation)
            contrast = float(np.std(gray))

            # Check if blank (very low std dev)
            is_blank = contrast < self.blank_threshold

            # Check if blurry
            is_blurry = blur_score < self.blur_threshold

            # Check if too dark or bright
            is_too_dark = brightness < self.brightness_min
            is_too_bright = brightness > self.brightness_max

            # Compute overall quality score (0-1)
            overall_quality = self._compute_quality_score(
                blur_score, brightness, contrast
            )

            return QualityMetrics(
                frame_path=frame_path,
                blur_score=blur_score,
                brightness=brightness,
                contrast=contrast,
                is_blank=is_blank,
                is_blurry=is_blurry,
                is_too_dark=is_too_dark,
                is_too_bright=is_too_bright,
                overall_quality=overall_quality
            )

        except Exception as e:
            raise ValueError(f"Failed to compute metrics for {frame_path}: {e}") from e

    def _compute_quality_score(
        self,
        blur_score: float,
        brightness: float,
        contrast: float
    ) -> float:
        """
        Compute normalized quality score (0-1)

        Args:
            blur_score: Laplacian variance
            brightness: Average pixel intensity
            contrast: Std dev of pixel intensity

        Returns:
            Quality score between 0 and 1
        """
        # Normalize blur score (0-1)
        blur_norm = min(blur_score / (self.blur_threshold * 2), 1.0)

        # Normalize brightness (0-1, penalize extremes)
        brightness_optimal = 127.5  # Mid-gray
        brightness_range = 127.5
        brightness_dist = abs(brightness - brightness_optimal)
        brightness_norm = max(0, 1 - (brightness_dist / brightness_range))

        # Normalize contrast (0-1)
        contrast_norm = min(contrast / (self.contrast_min * 5), 1.0)

        # Weighted average
        quality = (
            0.4 * blur_norm +
            0.3 * brightness_norm +
            0.3 * contrast_norm
        )

        return quality

    def is_high_quality(self, metrics: QualityMetrics) -> bool:
        """
        Check if frame meets quality criteria

        Args:
            metrics: QualityMetrics object

        Returns:
            True if frame passes quality checks
        """
        return (
            not metrics.is_blank and
            not metrics.is_blurry and
            not metrics.is_too_dark and
            not metrics.is_too_bright and
            metrics.overall_quality >= self.quality_threshold
        )

    def filter_frames(
        self,
        frame_paths: List[Path],
        return_metrics: bool = False
    ) -> Tuple[List[Path], List[Path]]:
        """
        Filter frames by quality

        Args:
            frame_paths: List of frame paths
            return_metrics: Also return metrics for all frames

        Returns:
            Tuple of (high_quality_frames, low_quality_frames)
            If return_metrics is True, returns tuple of
            (high_quality, low_quality, all_metrics)
        """
        high_quality = []
        low_quality = []
        all_metrics = []

        for frame_path in frame_paths:
            try:
                metrics = self.compute_metrics(frame_path)
                all_metrics.append(metrics)

                if self.is_high_quality(metrics):
                    high_quality.append(frame_path)
                    logger.debug(
                        f"High quality: {frame_path.name} "
                        f"(blur={metrics.blur_score:.1f}, "
                        f"quality={metrics.overall_quality:.2f})"
                    )
                else:
                    low_quality.append(frame_path)
                    logger.debug(
                        f"Low quality: {frame_path.name} "
                        f"(blur={metrics.blur_score:.1f}, "
                        f"blank={metrics.is_blank}, "
                        f"blurry={metrics.is_blurry})"
                    )

            except Exception as e:
                logger.error(f"Failed to process frame {frame_path}: {e}")
                low_quality.append(frame_path)

        logger.info(
            f"Quality filtering: {len(high_quality)} high quality, "
            f"{len(low_quality)} low quality "
            f"({len(high_quality) / len(frame_paths) * 100:.1f}% pass rate)"
        )

        if return_metrics:
            return high_quality, low_quality, all_metrics
        else:
            return high_quality, low_quality

    def find_blurry_frames(
        self,
        frame_paths: List[Path],
        threshold: Optional[float] = None
    ) -> List[Path]:
        """
        Find blurry frames

        Args:
            frame_paths: List of frame paths
            threshold: Optional custom blur threshold

        Returns:
            List of blurry frame paths
        """
        threshold = threshold or self.blur_threshold
        blurry = []

        for frame_path in frame_paths:
            try:
                metrics = self.compute_metrics(frame_path)
                if metrics.blur_score < threshold:
                    blurry.append(frame_path)

            except Exception as e:
                logger.error(f"Failed to check frame {frame_path}: {e}")

        logger.info(
            f"Found {len(blurry)} blurry frames "
            f"(threshold={threshold})"
        )

        return blurry

    def find_blank_frames(
        self,
        frame_paths: List[Path],
        threshold: Optional[float] = None
    ) -> List[Path]:
        """
        Find blank/nearly uniform frames

        Args:
            frame_paths: List of frame paths
            threshold: Optional custom blank threshold

        Returns:
            List of blank frame paths
        """
        threshold = threshold or self.blank_threshold
        blank = []

        for frame_path in frame_paths:
            try:
                metrics = self.compute_metrics(frame_path)
                if metrics.contrast < threshold:
                    blank.append(frame_path)

            except Exception as e:
                logger.error(f"Failed to check frame {frame_path}: {e}")

        logger.info(
            f"Found {len(blank)} blank frames "
            f"(threshold={threshold})"
        )

        return blank

    def rank_by_quality(
        self,
        frame_paths: List[Path],
        ascending: bool = False
    ) -> List[Tuple[Path, float]]:
        """
        Rank frames by quality score

        Args:
            frame_paths: List of frame paths
            ascending: If True, rank from worst to best

        Returns:
            List of (frame_path, quality_score) tuples, sorted by quality
        """
        scored_frames = []

        for frame_path in frame_paths:
            try:
                metrics = self.compute_metrics(frame_path)
                scored_frames.append((frame_path, metrics.overall_quality))

            except Exception as e:
                logger.error(f"Failed to score frame {frame_path}: {e}")
                # Assign zero quality for failed frames
                scored_frames.append((frame_path, 0.0))

        # Sort by quality score
        scored_frames.sort(key=lambda x: x[1], reverse=not ascending)

        return scored_frames

    def get_best_frames(
        self,
        frame_paths: List[Path],
        count: int = 10
    ) -> List[Path]:
        """
        Get the N best quality frames

        Args:
            frame_paths: List of frame paths
            count: Number of frames to return

        Returns:
            List of best quality frame paths
        """
        ranked = self.rank_by_quality(frame_paths, ascending=False)
        best_frames = [path for path, score in ranked[:count]]

        logger.info(
            f"Selected {len(best_frames)} best frames from {len(frame_paths)}"
        )

        return best_frames


def filter_high_quality_frames(
    frame_paths: List[Path],
    blur_threshold: float = 100.0,
    brightness_min: float = 20.0,
    brightness_max: float = 235.0
) -> List[Path]:
    """
    Convenience function to filter high-quality frames

    Args:
        frame_paths: List of frame paths
        blur_threshold: Minimum blur score
        brightness_min: Minimum brightness
        brightness_max: Maximum brightness

    Returns:
        List of high-quality frame paths
    """
    filter = FrameQualityFilter(
        blur_threshold=blur_threshold,
        brightness_min=brightness_min,
        brightness_max=brightness_max
    )

    high_quality, _ = filter.filter_frames(frame_paths)
    return high_quality


def remove_blurry_frames(
    frame_paths: List[Path],
    blur_threshold: float = 100.0
) -> List[Path]:
    """
    Convenience function to remove blurry frames

    Args:
        frame_paths: List of frame paths
        blur_threshold: Minimum blur score

    Returns:
        List of sharp frame paths
    """
    filter = FrameQualityFilter(blur_threshold=blur_threshold)
    blurry = filter.find_blurry_frames(frame_paths)

    # Return frames that are not blurry
    blurry_set = set(blurry)
    sharp_frames = [path for path in frame_paths if path not in blurry_set]

    return sharp_frames
