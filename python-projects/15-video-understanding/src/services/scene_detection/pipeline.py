"""
Scene detection pipeline
Combines multiple detection methods using ensemble approach
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from src.services.scene_detection.base import (
    Scene,
    SceneDetector,
    SceneDetectorConfig
)
from src.services.scene_detection.content_detector import ContentBasedSceneDetector
from src.services.scene_detection.threshold_detector import ThresholdSceneDetector
from src.services.scene_detection.optical_flow_detector import OpticalFlowDetector
from src.services.scene_detection.color_histogram import ColorHistogramAnalyzer
from src.services.scene_detection.audio_detector import AudioBasedSceneDetector
from src.services.scene_detection.boundary_refiner import SceneBoundaryRefiner
from src.services.scene_detection.scene_classifier import SceneClassifier

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Configuration for scene detection pipeline"""
    use_content_detector: bool = True
    use_threshold_detector: bool = True
    use_optical_flow: bool = False  # Computationally expensive
    use_color_histogram: bool = True
    use_audio_detector: bool = True

    classify_scenes: bool = True
    refine_boundaries: bool = True

    voting_threshold: int = 2  # Minimum detectors that must agree
    parallel_execution: bool = True

    # Detector-specific configs
    content_threshold: float = 27.0
    threshold_method: str = "histogram"
    threshold_value: float = 30.0

    min_scene_length: float = 1.0
    max_scene_length: Optional[float] = None


class SceneDetectionPipeline:
    """
    Ensemble scene detection pipeline
    Combines multiple detection methods for robust scene detection
    """

    def __init__(self, config: Optional[PipelineConfig] = None):
        """
        Initialize scene detection pipeline

        Args:
            config: Pipeline configuration
        """
        self.config = config or PipelineConfig()
        self.detectors = self._initialize_detectors()

        self.refiner = SceneBoundaryRefiner(
            min_scene_duration=self.config.min_scene_length
        )
        self.classifier = SceneClassifier()

    def detect_scenes(
        self,
        video_path: Path,
        start_time: Optional[float] = None,
        end_time: Optional[float] = None
    ) -> List[Scene]:
        """
        Detect scenes using ensemble of detectors

        Args:
            video_path: Path to video file
            start_time: Optional start time in seconds
            end_time: Optional end time in seconds

        Returns:
            List of detected scenes
        """
        if not video_path.exists():
            raise ValueError(f"Video not found: {video_path}")

        logger.info(
            f"Starting scene detection pipeline for {video_path} "
            f"using {len(self.detectors)} detectors"
        )

        # Run all detectors
        detection_results = self._run_detectors(
            video_path,
            start_time,
            end_time
        )

        if not detection_results:
            logger.warning("No detection results from any detector")
            return []

        # Merge results from multiple detectors
        merged_scenes = self._merge_detector_results(detection_results)

        logger.info(f"Merged {len(detection_results)} detector results into {len(merged_scenes)} scenes")

        # Refine boundaries
        if self.config.refine_boundaries:
            merged_scenes = self.refiner.refine_scenes(merged_scenes)
            logger.info(f"Refined to {len(merged_scenes)} scenes")

        # Classify scenes
        if self.config.classify_scenes:
            merged_scenes = self.classifier.classify_scenes(
                merged_scenes,
                video_path,
                include_audio=self.config.use_audio_detector
            )

        logger.info(f"Pipeline complete: {len(merged_scenes)} final scenes")

        return merged_scenes

    def _initialize_detectors(self) -> Dict[str, SceneDetector]:
        """
        Initialize enabled detectors

        Returns:
            Dictionary of detector name to detector instance
        """
        detectors = {}

        detector_config = SceneDetectorConfig(
            min_scene_length=self.config.min_scene_length,
            max_scene_length=self.config.max_scene_length,
            detect_transitions=True,
            classify_scenes=False  # We'll do this in pipeline
        )

        if self.config.use_content_detector:
            try:
                detectors['content'] = ContentBasedSceneDetector(
                    config=SceneDetectorConfig(
                        threshold=self.config.content_threshold,
                        min_scene_length=self.config.min_scene_length
                    )
                )
                logger.debug("Initialized ContentBasedSceneDetector")
            except Exception as e:
                logger.warning(f"Failed to initialize ContentBasedSceneDetector: {e}")

        if self.config.use_threshold_detector:
            detectors['threshold'] = ThresholdSceneDetector(
                config=SceneDetectorConfig(
                    threshold=self.config.threshold_value,
                    min_scene_length=self.config.min_scene_length
                ),
                method=self.config.threshold_method
            )
            logger.debug("Initialized ThresholdSceneDetector")

        if self.config.use_optical_flow:
            detectors['optical_flow'] = OpticalFlowDetector(
                config=detector_config
            )
            logger.debug("Initialized OpticalFlowDetector")

        if self.config.use_color_histogram:
            detectors['color_histogram'] = ColorHistogramAnalyzer(
                config=SceneDetectorConfig(
                    threshold=self.config.threshold_value,
                    min_scene_length=self.config.min_scene_length
                )
            )
            logger.debug("Initialized ColorHistogramAnalyzer")

        if self.config.use_audio_detector:
            detectors['audio'] = AudioBasedSceneDetector(
                config=detector_config
            )
            logger.debug("Initialized AudioBasedSceneDetector")

        logger.info(f"Initialized {len(detectors)} detectors: {list(detectors.keys())}")

        return detectors

    def _run_detectors(
        self,
        video_path: Path,
        start_time: Optional[float],
        end_time: Optional[float]
    ) -> Dict[str, List[Scene]]:
        """
        Run all detectors

        Args:
            video_path: Path to video file
            start_time: Optional start time
            end_time: Optional end time

        Returns:
            Dictionary of detector name to scenes
        """
        results = {}

        if self.config.parallel_execution and len(self.detectors) > 1:
            # Run detectors in parallel
            results = self._run_detectors_parallel(video_path, start_time, end_time)
        else:
            # Run detectors sequentially
            results = self._run_detectors_sequential(video_path, start_time, end_time)

        return results

    def _run_detectors_parallel(
        self,
        video_path: Path,
        start_time: Optional[float],
        end_time: Optional[float]
    ) -> Dict[str, List[Scene]]:
        """Run detectors in parallel"""
        results = {}

        with ThreadPoolExecutor(max_workers=len(self.detectors)) as executor:
            # Submit all detector tasks
            future_to_detector = {
                executor.submit(
                    self._run_single_detector,
                    name,
                    detector,
                    video_path,
                    start_time,
                    end_time
                ): name
                for name, detector in self.detectors.items()
            }

            # Collect results as they complete
            for future in as_completed(future_to_detector):
                detector_name = future_to_detector[future]
                try:
                    scenes = future.result()
                    if scenes:
                        results[detector_name] = scenes
                        logger.info(
                            f"Detector '{detector_name}' completed: "
                            f"{len(scenes)} scenes"
                        )
                except Exception as e:
                    logger.error(f"Detector '{detector_name}' failed: {e}")

        return results

    def _run_detectors_sequential(
        self,
        video_path: Path,
        start_time: Optional[float],
        end_time: Optional[float]
    ) -> Dict[str, List[Scene]]:
        """Run detectors sequentially"""
        results = {}

        for name, detector in self.detectors.items():
            try:
                scenes = self._run_single_detector(
                    name,
                    detector,
                    video_path,
                    start_time,
                    end_time
                )
                if scenes:
                    results[name] = scenes
                    logger.info(f"Detector '{name}' completed: {len(scenes)} scenes")
            except Exception as e:
                logger.error(f"Detector '{name}' failed: {e}")

        return results

    def _run_single_detector(
        self,
        name: str,
        detector: SceneDetector,
        video_path: Path,
        start_time: Optional[float],
        end_time: Optional[float]
    ) -> List[Scene]:
        """
        Run a single detector

        Args:
            name: Detector name
            detector: Detector instance
            video_path: Path to video
            start_time: Optional start time
            end_time: Optional end time

        Returns:
            List of detected scenes
        """
        logger.debug(f"Running detector: {name}")

        scenes = detector.detect_scenes(
            video_path,
            start_time=start_time,
            end_time=end_time
        )

        return scenes

    def _merge_detector_results(
        self,
        results: Dict[str, List[Scene]]
    ) -> List[Scene]:
        """
        Merge results from multiple detectors

        Args:
            results: Dictionary of detector name to scenes

        Returns:
            Merged scene list
        """
        if not results:
            return []

        if len(results) == 1:
            # Only one detector, return its results
            return list(results.values())[0]

        # Use boundary refiner to merge multiple detector results
        scene_lists = list(results.values())

        merged = self.refiner.merge_multi_detector_results(
            scene_lists,
            voting_threshold=self.config.voting_threshold
        )

        return merged

    def get_pipeline_info(self) -> Dict[str, any]:
        """
        Get information about pipeline configuration

        Returns:
            Pipeline info dictionary
        """
        return {
            'enabled_detectors': list(self.detectors.keys()),
            'num_detectors': len(self.detectors),
            'voting_threshold': self.config.voting_threshold,
            'parallel_execution': self.config.parallel_execution,
            'classify_scenes': self.config.classify_scenes,
            'refine_boundaries': self.config.refine_boundaries,
            'config': {
                'min_scene_length': self.config.min_scene_length,
                'max_scene_length': self.config.max_scene_length,
                'content_threshold': self.config.content_threshold,
                'threshold_method': self.config.threshold_method,
                'threshold_value': self.config.threshold_value
            }
        }


def detect_scenes_ensemble(
    video_path: Path,
    config: Optional[PipelineConfig] = None
) -> List[Scene]:
    """
    Convenience function for ensemble scene detection

    Args:
        video_path: Path to video file
        config: Pipeline configuration

    Returns:
        List of detected scenes
    """
    pipeline = SceneDetectionPipeline(config)
    return pipeline.detect_scenes(video_path)


def detect_scenes_fast(video_path: Path) -> List[Scene]:
    """
    Fast scene detection using only threshold detector

    Args:
        video_path: Path to video file

    Returns:
        List of detected scenes
    """
    config = PipelineConfig(
        use_content_detector=False,
        use_threshold_detector=True,
        use_optical_flow=False,
        use_color_histogram=False,
        use_audio_detector=False,
        classify_scenes=False,
        refine_boundaries=True
    )

    pipeline = SceneDetectionPipeline(config)
    return pipeline.detect_scenes(video_path)


def detect_scenes_accurate(video_path: Path) -> List[Scene]:
    """
    Accurate scene detection using all detectors

    Args:
        video_path: Path to video file

    Returns:
        List of detected scenes
    """
    config = PipelineConfig(
        use_content_detector=True,
        use_threshold_detector=True,
        use_optical_flow=True,  # Enable optical flow for accuracy
        use_color_histogram=True,
        use_audio_detector=True,
        classify_scenes=True,
        refine_boundaries=True,
        voting_threshold=3,  # Higher threshold for accuracy
        parallel_execution=True
    )

    pipeline = SceneDetectionPipeline(config)
    return pipeline.detect_scenes(video_path)
