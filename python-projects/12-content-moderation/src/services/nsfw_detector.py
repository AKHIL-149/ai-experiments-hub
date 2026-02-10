"""
NSFW Detection Service using NudeNet.

Provides local, fast NSFW detection for images before sending to vision models.
"""

import logging
import os
from typing import Dict, List, Tuple, Optional
from pathlib import Path


logging.basicConfig(level=logging.INFO)


class NSFWDetector:
    """NSFW detection using NudeNet classifier."""

    # NudeNet label categories
    NSFW_LABELS = {
        'FEMALE_GENITALIA_EXPOSED',
        'FEMALE_BREAST_EXPOSED',
        'MALE_GENITALIA_EXPOSED',
        'ANUS_EXPOSED',
        'BUTTOCKS_EXPOSED'
    }

    # Labels that might be NSFW depending on context
    SUGGESTIVE_LABELS = {
        'FEMALE_BREAST_COVERED',
        'BUTTOCKS_COVERED',
        'BELLY_EXPOSED',
        'ARMPITS_EXPOSED'
    }

    def __init__(self, threshold: float = 0.6):
        """
        Initialize NSFW detector.

        Args:
            threshold: Detection threshold (0.0-1.0)
        """
        self.threshold = threshold
        self.enabled = os.getenv('NSFW_DETECTOR', 'nudenet').lower() == 'nudenet'

        if self.enabled:
            try:
                from nudenet import NudeDetector
                self.detector = NudeDetector()
                logging.info("NudeNet detector initialized")
            except ImportError:
                logging.warning("NudeNet not installed. NSFW detection disabled.")
                self.enabled = False
                self.detector = None
        else:
            self.detector = None
            logging.info("NSFW detection disabled")

    def detect(self, image_path: str) -> Dict:
        """
        Detect NSFW content in image.

        Args:
            image_path: Path to image file

        Returns:
            Dictionary with detection results:
            {
                'is_nsfw': bool,
                'confidence': float (0.0-1.0),
                'labels': List[str],
                'details': List[Dict],
                'description': str
            }
        """
        if not self.enabled or not self.detector:
            return {
                'is_nsfw': False,
                'confidence': 0.0,
                'labels': [],
                'details': [],
                'description': 'NSFW detection disabled'
            }

        try:
            # Run NudeNet detection
            detections = self.detector.detect(image_path)

            # Analyze detections
            is_nsfw, confidence, labels = self._analyze_detections(detections)

            # Build description
            description = self._build_description(detections, is_nsfw)

            return {
                'is_nsfw': is_nsfw,
                'confidence': confidence,
                'labels': labels,
                'details': detections,
                'description': description
            }

        except Exception as e:
            logging.error(f"NSFW detection failed for {image_path}: {e}")
            return {
                'is_nsfw': False,
                'confidence': 0.0,
                'labels': [],
                'details': [],
                'description': f'Detection error: {str(e)}'
            }

    def _analyze_detections(
        self,
        detections: List[Dict]
    ) -> Tuple[bool, float, List[str]]:
        """
        Analyze NudeNet detections to determine NSFW status.

        Args:
            detections: List of detection dictionaries from NudeNet

        Returns:
            Tuple of (is_nsfw, confidence, labels)
        """
        if not detections:
            return False, 0.0, []

        nsfw_labels = []
        max_nsfw_confidence = 0.0
        suggestive_count = 0

        for detection in detections:
            label = detection['class']
            confidence = detection['score']

            # Check for explicit NSFW content
            if label in self.NSFW_LABELS:
                nsfw_labels.append(label)
                max_nsfw_confidence = max(max_nsfw_confidence, confidence)

            # Count suggestive content
            elif label in self.SUGGESTIVE_LABELS:
                suggestive_count += 1

        # Determine NSFW status
        if nsfw_labels and max_nsfw_confidence >= self.threshold:
            # Explicit NSFW content detected
            return True, max_nsfw_confidence, nsfw_labels

        elif suggestive_count >= 3:
            # Multiple suggestive elements might indicate NSFW
            # Lower confidence since it's not explicit
            return True, 0.5, ['SUGGESTIVE_CONTENT']

        else:
            return False, 0.0, []

    def _build_description(
        self,
        detections: List[Dict],
        is_nsfw: bool
    ) -> str:
        """
        Build human-readable description of detections.

        Args:
            detections: List of detection dictionaries
            is_nsfw: Whether content is NSFW

        Returns:
            Description string
        """
        if not detections:
            return "No concerning content detected"

        if is_nsfw:
            labels = [d['class'] for d in detections if d['class'] in self.NSFW_LABELS]
            if labels:
                return f"Explicit content detected: {', '.join(labels)}"
            else:
                return "Suggestive content detected (multiple indicators)"

        # Safe content
        label_counts = {}
        for detection in detections:
            label = detection['class']
            label_counts[label] = label_counts.get(label, 0) + 1

        if label_counts:
            summary = ', '.join([f"{count}x {label}" for label, count in label_counts.items()])
            return f"Image analyzed: {summary}"
        else:
            return "Image appears safe"

    def classify_with_confidence(self, image_path: str) -> Tuple[bool, float, str]:
        """
        Classify image and return simple result.

        Args:
            image_path: Path to image file

        Returns:
            Tuple of (is_nsfw, confidence, description)
        """
        result = self.detect(image_path)
        return result['is_nsfw'], result['confidence'], result['description']


class NSFWDetectorFallback:
    """
    Fallback NSFW detector when NudeNet is not available.

    Always returns safe classification. Used for development/testing.
    """

    def __init__(self, threshold: float = 0.6):
        """Initialize fallback detector."""
        self.threshold = threshold
        self.enabled = False
        logging.warning("Using fallback NSFW detector (always returns safe)")

    def detect(self, image_path: str) -> Dict:
        """Return safe classification."""
        return {
            'is_nsfw': False,
            'confidence': 0.0,
            'labels': [],
            'details': [],
            'description': 'Fallback detector - image not analyzed'
        }

    def classify_with_confidence(self, image_path: str) -> Tuple[bool, float, str]:
        """Return safe classification."""
        return False, 0.0, 'Fallback detector - image not analyzed'


def get_nsfw_detector(threshold: Optional[float] = None) -> NSFWDetector:
    """
    Get NSFW detector instance.

    Args:
        threshold: Optional custom threshold

    Returns:
        NSFWDetector instance
    """
    if threshold is None:
        threshold = float(os.getenv('NSFW_THRESHOLD', '0.6'))

    try:
        return NSFWDetector(threshold)
    except Exception as e:
        logging.error(f"Failed to initialize NSFWDetector: {e}")
        return NSFWDetectorFallback(threshold)
