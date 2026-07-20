"""
Frame analyzer service - coordinates the complete frame extraction pipeline
Orchestrates extraction, deduplication, quality filtering, and storage
"""

import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass

from src.core.video_processor import ProcessingProgress
from src.services.frame_extractor import FrameExtractor, FrameMetadata, ExtractionMode
from src.services.keyframe_detector import KeyframeDetector, DetectionMethod
from src.utils.frame_hasher import FrameHasher, FrameHash
from src.utils.frame_quality_filter import FrameQualityFilter, QualityMetrics
from src.core.frame_storage import frame_storage

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Results from frame analysis pipeline"""
    video_id: int
    total_extracted: int
    after_deduplication: int
    after_quality_filter: int
    keyframes_detected: int
    final_frame_count: int
    frame_metadata: List[FrameMetadata]
    quality_metrics: List[QualityMetrics]
    storage_path: Path
    processing_time_seconds: float


class FrameAnalysisPipeline:
    """Configuration for frame analysis pipeline"""

    # Extraction settings
    extract_frames: bool = True
    extraction_fps: float = 1.0
    extraction_mode: str = ExtractionMode.INTERVAL

    # Keyframe detection settings
    detect_keyframes: bool = True
    keyframe_method: str = DetectionMethod.SCENE_CHANGE
    keyframe_threshold: float = 0.3

    # Deduplication settings
    deduplicate: bool = True
    deduplication_exact_only: bool = False
    deduplication_threshold: int = 5

    # Quality filtering settings
    quality_filter: bool = True
    blur_threshold: float = 100.0
    brightness_min: float = 20.0
    brightness_max: float = 235.0

    # Storage settings
    organize_frames: bool = True
    remove_originals: bool = False


class FrameAnalyzer:
    """
    Coordinate complete frame extraction and analysis pipeline
    """

    def __init__(
        self,
        frame_extractor: Optional[FrameExtractor] = None,
        keyframe_detector: Optional[KeyframeDetector] = None,
        frame_hasher: Optional[FrameHasher] = None,
        quality_filter: Optional[FrameQualityFilter] = None,
        progress_callback: Optional[Callable[[ProcessingProgress], None]] = None
    ):
        """
        Initialize frame analyzer

        Args:
            frame_extractor: FrameExtractor instance
            keyframe_detector: KeyframeDetector instance
            frame_hasher: FrameHasher instance
            quality_filter: FrameQualityFilter instance
            progress_callback: Optional progress callback
        """
        self.frame_extractor = frame_extractor or FrameExtractor(
            progress_callback=progress_callback
        )
        self.keyframe_detector = keyframe_detector or KeyframeDetector(
            progress_callback=progress_callback
        )
        self.frame_hasher = frame_hasher or FrameHasher()
        self.quality_filter = quality_filter or FrameQualityFilter()
        self.progress_callback = progress_callback
        self.storage = frame_storage

    def analyze_video(
        self,
        video_path: Path,
        video_id: int,
        pipeline: Optional[FrameAnalysisPipeline] = None,
        scene_id: Optional[int] = None
    ) -> AnalysisResult:
        """
        Run complete frame analysis pipeline

        Args:
            video_path: Path to video file
            video_id: Video ID for storage
            pipeline: Pipeline configuration
            scene_id: Optional scene ID

        Returns:
            AnalysisResult with all processing metrics

        Raises:
            ValueError: If video not found
            RuntimeError: If processing fails
        """
        import time
        start_time = time.time()

        if not video_path.exists():
            raise ValueError(f"Video not found: {video_path}")

        pipeline = pipeline or FrameAnalysisPipeline()

        logger.info(
            f"Starting frame analysis for video {video_id} "
            f"(scene_id={scene_id})"
        )

        # Step 1: Extract frames
        if pipeline.extract_frames:
            self._report_progress("frame_extraction", 10, "Extracting frames")

            frame_metadata = self.frame_extractor.extract_frames(
                video_path=video_path,
                video_id=video_id,
                fps=pipeline.extraction_fps,
                mode=pipeline.extraction_mode,
                scene_id=scene_id
            )

            frame_paths = [fm.file_path for fm in frame_metadata]
            total_extracted = len(frame_paths)

            logger.info(f"Extracted {total_extracted} frames")
        else:
            # Use existing frames
            frame_paths = self.storage.list_frames(video_id, scene_id)
            total_extracted = len(frame_paths)
            frame_metadata = []

        # Step 2: Detect keyframes
        keyframes_detected = 0
        if pipeline.detect_keyframes and frame_paths:
            self._report_progress("keyframe_detection", 30, "Detecting keyframes")

            keyframes = self.keyframe_detector.detect_keyframes(
                video_path=video_path,
                method=pipeline.keyframe_method,
                threshold=pipeline.keyframe_threshold
            )

            keyframes_detected = len(keyframes)
            logger.info(f"Detected {keyframes_detected} keyframes")

        # Step 3: Deduplicate frames
        after_dedup = total_extracted
        if pipeline.deduplicate and frame_paths:
            self._report_progress("deduplication", 50, "Removing duplicates")

            # Compute hashes
            frame_hashes = self.frame_hasher.compute_hashes_batch(frame_paths)

            # Deduplicate
            unique_hashes, removed_hashes = self.frame_hasher.deduplicate_frames(
                frame_hashes,
                exact_only=pipeline.deduplication_exact_only,
                similarity_threshold=pipeline.deduplication_threshold
            )

            frame_paths = [fh.frame_path for fh in unique_hashes]
            after_dedup = len(frame_paths)

            logger.info(
                f"Deduplication: {after_dedup} unique frames, "
                f"{len(removed_hashes)} removed"
            )

        # Step 4: Quality filtering
        quality_metrics = []
        after_quality = after_dedup
        if pipeline.quality_filter and frame_paths:
            self._report_progress("quality_filtering", 70, "Filtering by quality")

            high_quality, low_quality, metrics = self.quality_filter.filter_frames(
                frame_paths,
                return_metrics=True
            )

            quality_metrics = metrics
            frame_paths = high_quality
            after_quality = len(frame_paths)

            logger.info(
                f"Quality filtering: {after_quality} high quality, "
                f"{len(low_quality)} low quality"
            )

        # Step 5: Organize storage
        if pipeline.organize_frames and frame_paths:
            self._report_progress("storage_organization", 90, "Organizing storage")

            organized_paths = self.storage.organize_frames(
                video_id=video_id,
                frame_paths=frame_paths,
                scene_id=scene_id,
                rename=True
            )

            frame_paths = organized_paths

        # Get final storage path
        storage_path = self.storage.get_frame_directory(video_id, scene_id)

        # Calculate processing time
        processing_time = time.time() - start_time

        # Report completion
        self._report_progress("complete", 100, "Frame analysis complete")

        result = AnalysisResult(
            video_id=video_id,
            total_extracted=total_extracted,
            after_deduplication=after_dedup,
            after_quality_filter=after_quality,
            keyframes_detected=keyframes_detected,
            final_frame_count=len(frame_paths),
            frame_metadata=frame_metadata,
            quality_metrics=quality_metrics,
            storage_path=storage_path,
            processing_time_seconds=processing_time
        )

        logger.info(
            f"Frame analysis complete for video {video_id}: "
            f"{result.final_frame_count} final frames "
            f"({processing_time:.1f}s)"
        )

        return result

    def extract_and_analyze_keyframes(
        self,
        video_path: Path,
        video_id: int,
        method: str = DetectionMethod.SCENE_CHANGE,
        threshold: float = 0.3,
        quality_filter: bool = True,
        scene_id: Optional[int] = None
    ) -> AnalysisResult:
        """
        Extract and analyze only keyframes

        Args:
            video_path: Path to video
            video_id: Video ID
            method: Keyframe detection method
            threshold: Detection threshold
            quality_filter: Apply quality filtering
            scene_id: Optional scene ID

        Returns:
            AnalysisResult
        """
        pipeline = FrameAnalysisPipeline()
        pipeline.extract_frames = False  # Will detect keyframes directly
        pipeline.detect_keyframes = True
        pipeline.keyframe_method = method
        pipeline.keyframe_threshold = threshold
        pipeline.deduplicate = True
        pipeline.quality_filter = quality_filter

        # Extract keyframes using detector
        self._report_progress("keyframe_extraction", 10, "Extracting keyframes")

        keyframes = self.keyframe_detector.extract_keyframes(
            video_path=video_path,
            output_dir=self.storage.get_frame_directory(video_id, scene_id),
            method=method,
            threshold=threshold
        )

        # Get keyframe paths
        frame_paths = [kf.file_path for kf, path in keyframes]

        # Apply quality filter if requested
        if quality_filter:
            self._report_progress("quality_filtering", 50, "Filtering keyframes")

            high_quality, low_quality = self.quality_filter.filter_frames(frame_paths)
            frame_paths = high_quality

        processing_time = 0  # Would need to track actual time

        result = AnalysisResult(
            video_id=video_id,
            total_extracted=len(keyframes),
            after_deduplication=len(keyframes),
            after_quality_filter=len(frame_paths),
            keyframes_detected=len(keyframes),
            final_frame_count=len(frame_paths),
            frame_metadata=[],
            quality_metrics=[],
            storage_path=self.storage.get_frame_directory(video_id, scene_id),
            processing_time_seconds=processing_time
        )

        return result

    def get_analysis_statistics(
        self,
        video_id: int,
        scene_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get statistics about analyzed frames

        Args:
            video_id: Video ID
            scene_id: Optional scene ID

        Returns:
            Dictionary with frame statistics
        """
        return self.storage.get_frame_stats(video_id, scene_id)

    def cleanup_low_quality_frames(
        self,
        video_id: int,
        scene_id: Optional[int] = None,
        blur_threshold: float = 100.0
    ) -> int:
        """
        Remove low quality frames from storage

        Args:
            video_id: Video ID
            scene_id: Optional scene ID
            blur_threshold: Blur threshold

        Returns:
            Number of frames removed
        """
        logger.info(f"Cleaning up low quality frames for video {video_id}")

        # Get all frames
        frame_paths = self.storage.list_frames(video_id, scene_id)

        if not frame_paths:
            return 0

        # Find low quality frames
        _, low_quality = self.quality_filter.filter_frames(frame_paths)

        # Remove low quality frames
        removed_count = 0
        for frame_path in low_quality:
            try:
                frame_path.unlink()
                removed_count += 1
            except Exception as e:
                logger.error(f"Failed to remove {frame_path}: {e}")

        logger.info(f"Removed {removed_count} low quality frames")

        return removed_count

    def _report_progress(self, stage: str, percentage: float, message: str):
        """Report progress via callback"""
        if self.progress_callback:
            self.progress_callback(ProcessingProgress(
                stage=stage,
                current=int(percentage),
                total=100,
                percentage=percentage,
                message=message
            ))


def analyze_video_frames(
    video_path: Path,
    video_id: int,
    fps: float = 1.0,
    deduplicate: bool = True,
    quality_filter: bool = True,
    detect_keyframes: bool = True
) -> AnalysisResult:
    """
    Convenience function to analyze video frames

    Args:
        video_path: Path to video
        video_id: Video ID
        fps: Extraction FPS
        deduplicate: Remove duplicates
        quality_filter: Apply quality filtering
        detect_keyframes: Detect keyframes

    Returns:
        AnalysisResult
    """
    pipeline = FrameAnalysisPipeline()
    pipeline.extraction_fps = fps
    pipeline.deduplicate = deduplicate
    pipeline.quality_filter = quality_filter
    pipeline.detect_keyframes = detect_keyframes

    analyzer = FrameAnalyzer()
    return analyzer.analyze_video(
        video_path=video_path,
        video_id=video_id,
        pipeline=pipeline
    )
