"""
Object detection service
Detects and localizes objects in images using computer vision models
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DetectedObject:
    """A detected object in an image"""
    label: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    class_id: int
    metadata: Optional[Dict[str, any]] = None


@dataclass
class ObjectDetectionResult:
    """Object detection result for an image"""
    image_path: Path
    objects: List[DetectedObject]
    num_objects: int
    model: str
    metadata: Optional[Dict[str, any]] = None


class ObjectDetectionService:
    """
    Detect objects in images using YOLO or other detection models
    """

    def __init__(
        self,
        model_name: str = "yolov8n",
        confidence_threshold: float = 0.25,
        iou_threshold: float = 0.45
    ):
        """
        Initialize object detection service

        Args:
            model_name: Model to use (yolov8n, yolov8s, yolov8m, etc.)
            confidence_threshold: Minimum confidence for detections
            iou_threshold: IOU threshold for NMS
        """
        self.model_name = model_name
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.model = None

    def detect_objects(
        self,
        image_path: Path,
        classes: Optional[List[str]] = None
    ) -> ObjectDetectionResult:
        """
        Detect objects in image

        Args:
            image_path: Path to image file
            classes: Optional list of class names to detect

        Returns:
            ObjectDetectionResult

        Raises:
            ValueError: If image not found
            RuntimeError: If detection fails
        """
        if not image_path.exists():
            raise ValueError(f"Image not found: {image_path}")

        logger.info(f"Detecting objects in {image_path}")

        try:
            # Load model if not loaded
            if self.model is None:
                self._load_model()

            # Run detection
            results = self.model(
                str(image_path),
                conf=self.confidence_threshold,
                iou=self.iou_threshold
            )

            # Parse results
            objects = []
            for result in results:
                boxes = result.boxes

                for i in range(len(boxes)):
                    box = boxes[i]

                    # Get class
                    class_id = int(box.cls[0])
                    label = result.names[class_id]

                    # Filter by classes if specified
                    if classes and label not in classes:
                        continue

                    # Get bbox and confidence
                    bbox = box.xyxy[0].cpu().numpy()
                    confidence = float(box.conf[0])

                    obj = DetectedObject(
                        label=label,
                        confidence=confidence,
                        bbox=(int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])),
                        class_id=class_id
                    )
                    objects.append(obj)

            detection_result = ObjectDetectionResult(
                image_path=image_path,
                objects=objects,
                num_objects=len(objects),
                model=self.model_name,
                metadata={
                    'image_size': results[0].orig_shape if results else None
                }
            )

            logger.info(f"Detected {len(objects)} objects in {image_path.name}")

            return detection_result

        except Exception as e:
            raise RuntimeError(f"Object detection failed: {e}") from e

    def detect_batch(
        self,
        image_paths: List[Path],
        classes: Optional[List[str]] = None
    ) -> List[ObjectDetectionResult]:
        """
        Detect objects in multiple images

        Args:
            image_paths: List of image paths
            classes: Optional list of class names to detect

        Returns:
            List of ObjectDetectionResult
        """
        logger.info(f"Detecting objects in {len(image_paths)} images")

        results = []
        for image_path in image_paths:
            try:
                result = self.detect_objects(image_path, classes)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to detect objects in {image_path}: {e}")
                results.append(ObjectDetectionResult(
                    image_path=image_path,
                    objects=[],
                    num_objects=0,
                    model=self.model_name,
                    metadata={'error': str(e)}
                ))

        return results

    def _load_model(self):
        """Load YOLO model"""
        try:
            from ultralytics import YOLO

            logger.info(f"Loading {self.model_name} model...")
            self.model = YOLO(self.model_name)
            logger.info(f"Model loaded successfully")

        except ImportError:
            raise RuntimeError(
                "ultralytics package required. Install with: pip install ultralytics"
            )

    def count_objects_by_class(
        self,
        result: ObjectDetectionResult
    ) -> Dict[str, int]:
        """
        Count detected objects by class

        Args:
            result: ObjectDetectionResult

        Returns:
            Dictionary mapping class names to counts
        """
        counts = {}
        for obj in result.objects:
            counts[obj.label] = counts.get(obj.label, 0) + 1

        return counts

    def filter_by_confidence(
        self,
        result: ObjectDetectionResult,
        min_confidence: float
    ) -> ObjectDetectionResult:
        """
        Filter detections by minimum confidence

        Args:
            result: ObjectDetectionResult
            min_confidence: Minimum confidence threshold

        Returns:
            Filtered ObjectDetectionResult
        """
        filtered_objects = [
            obj for obj in result.objects
            if obj.confidence >= min_confidence
        ]

        return ObjectDetectionResult(
            image_path=result.image_path,
            objects=filtered_objects,
            num_objects=len(filtered_objects),
            model=result.model,
            metadata=result.metadata
        )

    def filter_by_classes(
        self,
        result: ObjectDetectionResult,
        classes: List[str]
    ) -> ObjectDetectionResult:
        """
        Filter detections by class names

        Args:
            result: ObjectDetectionResult
            classes: List of class names to keep

        Returns:
            Filtered ObjectDetectionResult
        """
        filtered_objects = [
            obj for obj in result.objects
            if obj.label in classes
        ]

        return ObjectDetectionResult(
            image_path=result.image_path,
            objects=filtered_objects,
            num_objects=len(filtered_objects),
            model=result.model,
            metadata=result.metadata
        )

    def get_largest_object(
        self,
        result: ObjectDetectionResult
    ) -> Optional[DetectedObject]:
        """
        Get the largest detected object by area

        Args:
            result: ObjectDetectionResult

        Returns:
            Largest DetectedObject or None
        """
        if not result.objects:
            return None

        largest = max(
            result.objects,
            key=lambda obj: (obj.bbox[2] - obj.bbox[0]) * (obj.bbox[3] - obj.bbox[1])
        )

        return largest

    def visualize_detections(
        self,
        result: ObjectDetectionResult,
        output_path: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Draw bounding boxes on image

        Args:
            result: ObjectDetectionResult
            output_path: Optional output path for annotated image

        Returns:
            Path to annotated image
        """
        try:
            import cv2

            # Read image
            image = cv2.imread(str(result.image_path))

            # Draw each detection
            for obj in result.objects:
                x1, y1, x2, y2 = obj.bbox

                # Draw box
                cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)

                # Draw label
                label = f"{obj.label} {obj.confidence:.2f}"
                cv2.putText(
                    image,
                    label,
                    (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    2
                )

            # Save or display
            if output_path:
                cv2.imwrite(str(output_path), image)
                logger.info(f"Annotated image saved to {output_path}")
                return output_path
            else:
                # Display (if running in environment with display)
                cv2.imshow('Detections', image)
                cv2.waitKey(0)
                cv2.destroyAllWindows()
                return None

        except Exception as e:
            logger.error(f"Visualization failed: {e}")
            return None


def detect_objects_in_image(
    image_path: Path,
    model_name: str = "yolov8n",
    confidence_threshold: float = 0.25
) -> ObjectDetectionResult:
    """
    Convenience function to detect objects in an image

    Args:
        image_path: Path to image file
        model_name: YOLO model name
        confidence_threshold: Minimum confidence

    Returns:
        ObjectDetectionResult
    """
    service = ObjectDetectionService(
        model_name=model_name,
        confidence_threshold=confidence_threshold
    )
    return service.detect_objects(image_path)


def detect_objects_in_frames(
    frame_paths: List[Path],
    model_name: str = "yolov8n",
    classes: Optional[List[str]] = None
) -> List[ObjectDetectionResult]:
    """
    Convenience function to detect objects in multiple frames

    Args:
        frame_paths: List of frame paths
        model_name: YOLO model name
        classes: Optional list of classes to detect

    Returns:
        List of ObjectDetectionResult
    """
    service = ObjectDetectionService(model_name=model_name)
    return service.detect_batch(frame_paths, classes)
