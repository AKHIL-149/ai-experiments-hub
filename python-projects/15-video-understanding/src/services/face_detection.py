"""
Face detection and recognition service
Detects faces in images using computer vision
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DetectedFace:
    """A detected face in an image"""
    bbox: Tuple[int, int, int, int]  # x, y, width, height
    confidence: float
    landmarks: Optional[Dict[str, Tuple[int, int]]] = None
    embedding: Optional[np.ndarray] = None
    metadata: Optional[Dict[str, any]] = None


@dataclass
class FaceDetectionResult:
    """Face detection result for an image"""
    image_path: Path
    faces: List[DetectedFace]
    num_faces: int
    model: str
    metadata: Optional[Dict[str, any]] = None


class FaceDetectionService:
    """
    Detect and analyze faces in images
    Supports multiple face detection backends
    """

    def __init__(
        self,
        backend: str = "opencv",
        min_confidence: float = 0.5
    ):
        """
        Initialize face detection service

        Args:
            backend: Detection backend (opencv, mtcnn, retinaface)
            min_confidence: Minimum detection confidence
        """
        self.backend = backend
        self.min_confidence = min_confidence
        self.detector = None

    def detect_faces(
        self,
        image_path: Path,
        extract_landmarks: bool = False,
        extract_embeddings: bool = False
    ) -> FaceDetectionResult:
        """
        Detect faces in image

        Args:
            image_path: Path to image file
            extract_landmarks: Extract facial landmarks
            extract_embeddings: Extract face embeddings

        Returns:
            FaceDetectionResult

        Raises:
            ValueError: If image not found
            RuntimeError: If detection fails
        """
        if not image_path.exists():
            raise ValueError(f"Image not found: {image_path}")

        logger.info(f"Detecting faces in {image_path}")

        try:
            if self.backend == "opencv":
                result = self._detect_opencv(image_path)
            elif self.backend == "mtcnn":
                result = self._detect_mtcnn(image_path, extract_landmarks)
            else:
                result = self._detect_opencv(image_path)

            logger.info(f"Detected {result.num_faces} faces in {image_path.name}")

            return result

        except Exception as e:
            raise RuntimeError(f"Face detection failed: {e}") from e

    def detect_batch(
        self,
        image_paths: List[Path]
    ) -> List[FaceDetectionResult]:
        """
        Detect faces in multiple images

        Args:
            image_paths: List of image paths

        Returns:
            List of FaceDetectionResult
        """
        logger.info(f"Detecting faces in {len(image_paths)} images")

        results = []
        for image_path in image_paths:
            try:
                result = self.detect_faces(image_path)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to detect faces in {image_path}: {e}")
                results.append(FaceDetectionResult(
                    image_path=image_path,
                    faces=[],
                    num_faces=0,
                    model=self.backend,
                    metadata={'error': str(e)}
                ))

        return results

    def _detect_opencv(self, image_path: Path) -> FaceDetectionResult:
        """Detect faces using OpenCV Haar Cascade"""
        import cv2

        # Load cascade if not loaded
        if self.detector is None:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self.detector = cv2.CascadeClassifier(cascade_path)

        # Read image
        image = cv2.imread(str(image_path))
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Detect faces
        detected = self.detector.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30)
        )

        # Convert to DetectedFace objects
        faces = []
        for (x, y, w, h) in detected:
            face = DetectedFace(
                bbox=(int(x), int(y), int(w), int(h)),
                confidence=1.0  # OpenCV doesn't provide confidence
            )
            faces.append(face)

        return FaceDetectionResult(
            image_path=image_path,
            faces=faces,
            num_faces=len(faces),
            model="opencv-haar",
            metadata={'image_size': image.shape[:2]}
        )

    def _detect_mtcnn(
        self,
        image_path: Path,
        extract_landmarks: bool
    ) -> FaceDetectionResult:
        """Detect faces using MTCNN"""
        try:
            from mtcnn import MTCNN
            import cv2

            # Load detector if not loaded
            if self.detector is None:
                self.detector = MTCNN()

            # Read image
            image = cv2.imread(str(image_path))
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

            # Detect faces
            detections = self.detector.detect_faces(image_rgb)

            # Convert to DetectedFace objects
            faces = []
            for detection in detections:
                if detection['confidence'] < self.min_confidence:
                    continue

                box = detection['box']
                landmarks = None

                if extract_landmarks and 'keypoints' in detection:
                    landmarks = {
                        'left_eye': tuple(detection['keypoints']['left_eye']),
                        'right_eye': tuple(detection['keypoints']['right_eye']),
                        'nose': tuple(detection['keypoints']['nose']),
                        'mouth_left': tuple(detection['keypoints']['mouth_left']),
                        'mouth_right': tuple(detection['keypoints']['mouth_right'])
                    }

                face = DetectedFace(
                    bbox=(box[0], box[1], box[2], box[3]),
                    confidence=detection['confidence'],
                    landmarks=landmarks
                )
                faces.append(face)

            return FaceDetectionResult(
                image_path=image_path,
                faces=faces,
                num_faces=len(faces),
                model="mtcnn",
                metadata={'image_size': image.shape[:2]}
            )

        except ImportError:
            logger.warning("MTCNN not available, falling back to OpenCV")
            return self._detect_opencv(image_path)

    def count_faces_in_frames(
        self,
        frame_paths: List[Path]
    ) -> Dict[int, int]:
        """
        Count faces in each frame

        Args:
            frame_paths: List of frame paths

        Returns:
            Dictionary mapping frame index to face count
        """
        results = self.detect_batch(frame_paths)

        counts = {
            idx: result.num_faces
            for idx, result in enumerate(results)
        }

        return counts

    def find_frames_with_faces(
        self,
        frame_paths: List[Path],
        min_faces: int = 1,
        max_faces: Optional[int] = None
    ) -> List[Path]:
        """
        Find frames containing specific number of faces

        Args:
            frame_paths: List of frame paths
            min_faces: Minimum number of faces
            max_faces: Maximum number of faces

        Returns:
            List of frame paths matching criteria
        """
        results = self.detect_batch(frame_paths)

        matching_frames = []
        for result in results:
            if result.num_faces >= min_faces:
                if max_faces is None or result.num_faces <= max_faces:
                    matching_frames.append(result.image_path)

        return matching_frames

    def get_largest_face(
        self,
        result: FaceDetectionResult
    ) -> Optional[DetectedFace]:
        """
        Get the largest detected face

        Args:
            result: FaceDetectionResult

        Returns:
            Largest DetectedFace or None
        """
        if not result.faces:
            return None

        largest = max(
            result.faces,
            key=lambda face: face.bbox[2] * face.bbox[3]  # width * height
        )

        return largest

    def visualize_faces(
        self,
        result: FaceDetectionResult,
        output_path: Optional[Path] = None,
        draw_landmarks: bool = False
    ) -> Optional[Path]:
        """
        Draw bounding boxes around detected faces

        Args:
            result: FaceDetectionResult
            output_path: Optional output path
            draw_landmarks: Draw facial landmarks if available

        Returns:
            Path to annotated image
        """
        try:
            import cv2

            # Read image
            image = cv2.imread(str(result.image_path))

            # Draw each face
            for face in result.faces:
                x, y, w, h = face.bbox

                # Draw box
                cv2.rectangle(image, (x, y), (x + w, y + h), (0, 255, 0), 2)

                # Draw confidence
                label = f"{face.confidence:.2f}"
                cv2.putText(
                    image,
                    label,
                    (x, y - 10),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    2
                )

                # Draw landmarks if available
                if draw_landmarks and face.landmarks:
                    for landmark_name, (lx, ly) in face.landmarks.items():
                        cv2.circle(image, (lx, ly), 2, (0, 0, 255), -1)

            # Save or display
            if output_path:
                cv2.imwrite(str(output_path), image)
                logger.info(f"Annotated image saved to {output_path}")
                return output_path
            else:
                cv2.imshow('Face Detection', image)
                cv2.waitKey(0)
                cv2.destroyAllWindows()
                return None

        except Exception as e:
            logger.error(f"Visualization failed: {e}")
            return None


def detect_faces_in_image(
    image_path: Path,
    backend: str = "opencv",
    min_confidence: float = 0.5
) -> FaceDetectionResult:
    """
    Convenience function to detect faces in an image

    Args:
        image_path: Path to image file
        backend: Detection backend
        min_confidence: Minimum confidence

    Returns:
        FaceDetectionResult
    """
    service = FaceDetectionService(backend=backend, min_confidence=min_confidence)
    return service.detect_faces(image_path)


def detect_faces_in_frames(
    frame_paths: List[Path],
    backend: str = "opencv"
) -> List[FaceDetectionResult]:
    """
    Convenience function to detect faces in multiple frames

    Args:
        frame_paths: List of frame paths
        backend: Detection backend

    Returns:
        List of FaceDetectionResult
    """
    service = FaceDetectionService(backend=backend)
    return service.detect_batch(frame_paths)
