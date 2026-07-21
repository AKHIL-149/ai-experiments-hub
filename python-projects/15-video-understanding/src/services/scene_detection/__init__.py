"""
Scene detection services
"""

from src.services.scene_detection.base import (
    SceneDetector,
    Scene,
    SceneBoundary,
    SceneType,
    TransitionType,
    SceneDetectorConfig,
)
from src.services.scene_detection.content_detector import (
    ContentBasedSceneDetector,
    detect_scenes_content,
)
from src.services.scene_detection.threshold_detector import (
    ThresholdSceneDetector,
    detect_scenes_threshold,
)
from src.services.scene_detection.optical_flow_detector import (
    OpticalFlowDetector,
    detect_scenes_optical_flow,
)

__all__ = [
    'SceneDetector',
    'Scene',
    'SceneBoundary',
    'SceneType',
    'TransitionType',
    'SceneDetectorConfig',
    'ContentBasedSceneDetector',
    'detect_scenes_content',
    'ThresholdSceneDetector',
    'detect_scenes_threshold',
    'OpticalFlowDetector',
    'detect_scenes_optical_flow',
]
