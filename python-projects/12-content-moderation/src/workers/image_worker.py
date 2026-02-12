"""
Image Classification Worker.

Handles asynchronous image content classification using NSFW detection and vision models.
"""

import logging
from celery_app import app
from .base_worker import BaseClassificationTask
from ..services.classification_service import get_classification_service
from ..utils.file_handler import get_file_handler
from ..core.database import DatabaseManager, ContentItem, Classification, ViolationCategory, ContentStatus
from datetime import datetime

logging.basicConfig(level=logging.INFO)


@app.task(base=BaseClassificationTask, bind=True, name='src.workers.image_worker.classify_image_task')
def classify_image_task(
    self,
    content_id: str,
    file_path: str,
    use_vision: bool = True,
    priority: int = 0
):
    """
    Classify image content asynchronously.

    Args:
        self: Task instance
        content_id: Content item ID
        file_path: Path to image file
        use_vision: Whether to use vision models
        priority: Priority level

    Returns:
        Classification result dictionary
    """
    task_id = self.request.id
    self.log_classification_start(task_id, 'image', content_id)

    try:
        # Update progress: Starting
        self.update_progress(task_id, 10, 'Initializing classification service')

        # Initialize services
        classification_service = get_classification_service()
        file_handler = get_file_handler()

        # Update progress: Generating thumbnail
        self.update_progress(task_id, 20, 'Generating thumbnail')

        # Generate thumbnail if not exists
        thumb_path = file_handler.get_thumbnail_path(file_path)
        if not thumb_path:
            success, thumb_path, error = file_handler.generate_thumbnail(file_path)
            if not success:
                logging.warning(f"Thumbnail generation failed: {error}")

        # Update progress: Running NSFW detection
        self.update_progress(task_id, 30, 'Running NSFW detection')

        # Classify image (NSFW detection is included in classify_image)
        result = classification_service.classify_image(file_path, use_vision=use_vision)

        # Update progress: Saving results
        self.update_progress(task_id, 80, 'Saving classification results')

        # Save to database
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Get content item
            content_item = db.query(ContentItem).filter(ContentItem.id == content_id).first()
            if not content_item:
                raise ValueError(f"Content item {content_id} not found")

            # Create classification record
            classification = Classification(
                content_id=content_id,
                category=ViolationCategory(result['category']),
                confidence=result['confidence'],
                is_violation=result['is_violation'],
                provider=result['provider'],
                model_name=result['model'],
                reasoning=result['reasoning'],
                processing_time_ms=result.get('processing_time_ms', 0),
                cost=result.get('cost', 0.0)
            )

            db.add(classification)

            # Apply moderation policy
            status = classification_service.apply_moderation_policy(result)
            content_item.status = ContentStatus(status)
            content_item.moderated_at = datetime.utcnow()

            db.commit()
            db.refresh(classification)

            # Add classification ID to result
            result['classification_id'] = classification.id
            result['content_status'] = status
            result['thumbnail_path'] = thumb_path

        # Update progress: Complete
        self.update_progress(task_id, 100, 'Classification complete')

        self.log_classification_complete(
            task_id,
            content_id,
            result['category'],
            result['confidence'],
            result['processing_time_ms']
        )

        return result

    except Exception as e:
        self.log_classification_error(task_id, content_id, e)
        raise  # Re-raise for retry mechanism
