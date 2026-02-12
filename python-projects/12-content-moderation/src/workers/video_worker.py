"""
Video Classification Worker.

Handles asynchronous video content classification using frame extraction and analysis.
"""

import logging
from celery_app import app
from .base_worker import BaseClassificationTask
from ..services.classification_service import get_classification_service
from ..services.video_processor import get_video_processor
from ..core.database import DatabaseManager, ContentItem, Classification, ViolationCategory, ContentStatus
from datetime import datetime

logging.basicConfig(level=logging.INFO)


@app.task(base=BaseClassificationTask, bind=True, name='src.workers.video_worker.classify_video_task')
def classify_video_task(
    self,
    content_id: str,
    file_path: str,
    max_frames: int = 10,
    use_vision: bool = False,  # Default False for faster processing
    priority: int = 0
):
    """
    Classify video content asynchronously.

    Args:
        self: Task instance
        content_id: Content item ID
        file_path: Path to video file
        max_frames: Maximum frames to analyze
        use_vision: Whether to use vision models (slower, more expensive)
        priority: Priority level

    Returns:
        Classification result dictionary
    """
    task_id = self.request.id
    self.log_classification_start(task_id, 'video', content_id)

    try:
        # Update progress: Starting
        self.update_progress(task_id, 5, 'Initializing classification service')

        # Initialize services
        classification_service = get_classification_service()
        video_processor = get_video_processor(max_frames=max_frames)

        # Update progress: Generating thumbnail
        self.update_progress(task_id, 10, 'Generating video thumbnail')

        # Generate video thumbnail
        thumb_path = None
        success, thumb_path, error = video_processor.generate_video_thumbnail(file_path)
        if not success:
            logging.warning(f"Video thumbnail generation failed: {error}")

        # Update progress: Extracting frames
        self.update_progress(task_id, 20, f'Extracting up to {max_frames} frames')

        # Classify video (includes frame extraction)
        # We'll use a custom progress callback for frame analysis
        result = classification_service.classify_video(
            file_path,
            max_frames=max_frames,
            use_vision=use_vision
        )

        # Update progress based on frames analyzed
        frames_analyzed = result.get('frames_analyzed', 0)
        if frames_analyzed > 0:
            self.update_progress(
                task_id,
                70,
                f'Analyzed {frames_analyzed} frames'
            )

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
            result['frames_analyzed'] = frames_analyzed

        # Update progress: Complete
        self.update_progress(task_id, 100, 'Video classification complete')

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
