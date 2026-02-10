"""
Classification Service for Content Moderation.

Orchestrates NSFW detection and LLM classification for multi-modal content.
"""

import logging
import os
from typing import Dict, Optional
from pathlib import Path

from ..core.llm_client import LLMClient
from ..core.database import ViolationCategory
from .nsfw_detector import get_nsfw_detector


logging.basicConfig(level=logging.INFO)


class ClassificationService:
    """Service for classifying content using multiple detection methods."""

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        nsfw_threshold: Optional[float] = None
    ):
        """
        Initialize classification service.

        Args:
            llm_provider: LLM provider (ollama, openai, anthropic)
            llm_model: LLM model name
            nsfw_threshold: NSFW detection threshold
        """
        # Initialize LLM client
        self.llm_provider = llm_provider or 'ollama'  # Default to ollama
        self.llm_model = llm_model
        self.llm_client = LLMClient(provider=self.llm_provider, model=self.llm_model)

        # Initialize NSFW detector
        self.nsfw_detector = get_nsfw_detector(threshold=nsfw_threshold)

        logging.info(f"ClassificationService initialized: LLM={self.llm_provider}/{self.llm_client.model}, NSFW={self.nsfw_detector.enabled}")

    def classify_text(self, text_content: str) -> Dict:
        """
        Classify text content.

        Args:
            text_content: Text to classify

        Returns:
            Classification result dictionary
        """
        try:
            result = self.llm_client.classify_text(text_content)

            return {
                'provider': self.llm_provider,
                'model': self.llm_client.model,
                'category': result['category'],
                'confidence': result['confidence'],
                'is_violation': result['is_violation'],
                'reasoning': result['reasoning'],
                'processing_time_ms': result.get('processing_time_ms', 0),
                'cost': result.get('cost', 0.0),
                'nsfw_checked': False
            }

        except Exception as e:
            logging.error(f"Text classification failed: {e}")
            return {
                'provider': self.llm_provider,
                'model': self.llm_client.model,
                'category': ViolationCategory.CLEAN.value,
                'confidence': 0.0,
                'is_violation': False,
                'reasoning': f'Classification error: {str(e)}',
                'processing_time_ms': 0,
                'cost': 0.0,
                'nsfw_checked': False,
                'error': str(e)
            }

    def classify_image(
        self,
        image_path: str,
        use_vision: bool = True
    ) -> Dict:
        """
        Classify image content.

        Uses two-stage classification:
        1. Fast NSFW detection with NudeNet (local)
        2. Vision model classification (if needed)

        Args:
            image_path: Path to image file
            use_vision: Whether to use vision models

        Returns:
            Classification result dictionary
        """
        try:
            # Stage 1: NSFW detection
            nsfw_result = self.nsfw_detector.detect(image_path)
            nsfw_detected = nsfw_result['is_nsfw']
            nsfw_confidence = nsfw_result['confidence']
            nsfw_description = nsfw_result['description']

            logging.info(f"NSFW detection: is_nsfw={nsfw_detected}, confidence={nsfw_confidence:.2f}")

            # If NSFW detected with high confidence, return immediately
            if nsfw_detected and nsfw_confidence >= 0.85:
                return {
                    'provider': 'nudenet',
                    'model': 'nudenet',
                    'category': ViolationCategory.NSFW.value,
                    'confidence': nsfw_confidence,
                    'is_violation': True,
                    'reasoning': nsfw_description,
                    'processing_time_ms': 0,
                    'cost': 0.0,
                    'nsfw_checked': True,
                    'nsfw_result': nsfw_result
                }

            # Stage 2: Vision model classification (if enabled and available)
            if use_vision:
                try:
                    vision_result = self.llm_client.classify_image(
                        image_path=image_path,
                        description=nsfw_description if nsfw_detected else None
                    )

                    # Combine NSFW detection with vision model results
                    # If NSFW was detected, boost the confidence
                    if nsfw_detected and vision_result['category'] == ViolationCategory.NSFW.value:
                        vision_result['confidence'] = min(1.0, vision_result['confidence'] * 1.2)

                    vision_result['nsfw_checked'] = True
                    vision_result['nsfw_result'] = nsfw_result

                    return vision_result

                except Exception as e:
                    logging.warning(f"Vision classification failed, falling back to NSFW result: {e}")

            # Fallback: Use NSFW detection result
            return {
                'provider': 'nudenet',
                'model': 'nudenet',
                'category': ViolationCategory.NSFW.value if nsfw_detected else ViolationCategory.CLEAN.value,
                'confidence': nsfw_confidence,
                'is_violation': nsfw_detected,
                'reasoning': nsfw_description,
                'processing_time_ms': 0,
                'cost': 0.0,
                'nsfw_checked': True,
                'nsfw_result': nsfw_result
            }

        except Exception as e:
            logging.error(f"Image classification failed: {e}")
            return {
                'provider': self.llm_provider,
                'model': self.llm_client.model,
                'category': ViolationCategory.CLEAN.value,
                'confidence': 0.0,
                'is_violation': False,
                'reasoning': f'Classification error: {str(e)}',
                'processing_time_ms': 0,
                'cost': 0.0,
                'nsfw_checked': False,
                'error': str(e)
            }

    def classify_video(
        self,
        video_path: str,
        max_frames: int = 10
    ) -> Dict:
        """
        Classify video content.

        For Phase 2, returns placeholder. Full implementation in Phase 3.

        Args:
            video_path: Path to video file
            max_frames: Maximum frames to analyze

        Returns:
            Classification result dictionary
        """
        logging.info(f"Video classification placeholder for: {video_path}")

        return {
            'provider': 'placeholder',
            'model': 'placeholder',
            'category': ViolationCategory.CLEAN.value,
            'confidence': 0.0,
            'is_violation': False,
            'reasoning': 'Video classification not yet implemented (Phase 3)',
            'processing_time_ms': 0,
            'cost': 0.0,
            'nsfw_checked': False
        }

    def classify_content(
        self,
        content_type: str,
        text_content: Optional[str] = None,
        file_path: Optional[str] = None
    ) -> Dict:
        """
        Classify content based on type.

        Args:
            content_type: Type of content (text, image, video)
            text_content: Text content (for text type)
            file_path: File path (for image/video types)

        Returns:
            Classification result dictionary
        """
        if content_type == 'text':
            if not text_content:
                raise ValueError("text_content required for text classification")
            return self.classify_text(text_content)

        elif content_type == 'image':
            if not file_path:
                raise ValueError("file_path required for image classification")
            return self.classify_image(file_path)

        elif content_type == 'video':
            if not file_path:
                raise ValueError("file_path required for video classification")
            return self.classify_video(file_path)

        else:
            raise ValueError(f"Unsupported content type: {content_type}")

    def apply_moderation_policy(
        self,
        classification: Dict,
        auto_approve_threshold: float = 0.95,
        auto_reject_threshold: float = 0.9,
        flag_review_threshold: float = 0.5
    ) -> str:
        """
        Apply moderation policy based on classification.

        Args:
            classification: Classification result
            auto_approve_threshold: Threshold for auto-approval
            auto_reject_threshold: Threshold for auto-rejection
            flag_review_threshold: Threshold for flagging

        Returns:
            Status: 'approved', 'rejected', 'flagged'
        """
        category = classification['category']
        confidence = classification['confidence']
        is_violation = classification['is_violation']

        # Auto-approve if clean with high confidence
        if category == ViolationCategory.CLEAN.value and confidence >= auto_approve_threshold:
            return 'approved'

        # Auto-reject if violation with high confidence
        if is_violation and confidence >= auto_reject_threshold:
            return 'rejected'

        # Flag for review if uncertain or moderate confidence
        if confidence >= flag_review_threshold:
            return 'flagged'

        # Default: flag for review
        return 'flagged'


# Global service instance
_classification_service_instance = None


def get_classification_service(
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None
) -> ClassificationService:
    """
    Get global ClassificationService instance.

    Args:
        llm_provider: Optional LLM provider override
        llm_model: Optional LLM model override

    Returns:
        ClassificationService singleton
    """
    global _classification_service_instance

    # Reinitialize if provider/model changed
    if _classification_service_instance is None or \
       (llm_provider and llm_provider != _classification_service_instance.llm_provider) or \
       (llm_model and llm_model != _classification_service_instance.llm_model):
        _classification_service_instance = ClassificationService(
            llm_provider=llm_provider,
            llm_model=llm_model
        )

    return _classification_service_instance
