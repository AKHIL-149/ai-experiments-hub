"""
Text Classification Worker.

Handles asynchronous text content classification using LLM providers.
"""

import logging
from celery_app import app
from .base_worker import BaseClassificationTask
from ..services.classification_service import get_classification_service
from ..core.database import DatabaseManager, ContentItem, Classification, ViolationCategory, ContentStatus
from datetime import datetime

logging.basicConfig(level=logging.INFO)


@app.task(base=BaseClassificationTask, bind=True, name='src.workers.text_worker.classify_text_task')
def classify_text_task(self, content_id: str, text_content: str, priority: int = 0):
    """
    Classify text content asynchronously.

    Args:
        self: Task instance
        content_id: Content item ID
        text_content: Text to classify
        priority: Priority level (0=normal, 5=high, 10=critical)

    Returns:
        Classification result dictionary
    """
    task_id = self.request.id
    self.log_classification_start(task_id, 'text', content_id)

    try:
        # Update progress: Starting
        self.update_progress(task_id, 10, 'Initializing classification service')

        # Initialize classification service
        classification_service = get_classification_service()

        # Update progress: Classifying
        self.update_progress(task_id, 30, 'Classifying text with LLM')

        # Classify text
        result = classification_service.classify_text(text_content)

        # Update progress: Saving results
        self.update_progress(task_id, 70, 'Saving classification results')

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
