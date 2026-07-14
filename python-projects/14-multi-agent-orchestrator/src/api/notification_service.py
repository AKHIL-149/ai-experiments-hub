"""
Notification Service API

REST API endpoints for multi-channel notifications, template management,
delivery tracking, and user notification preferences.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.notification_service import (
    NotificationService,
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    TemplateType
)


router = APIRouter()


# Request/Response Models
class CreateTemplateRequest(BaseModel):
    """Request model for creating a template"""
    template_id: str = Field(..., description="Unique template identifier")
    name: str = Field(..., description="Template name")
    channel: NotificationChannel = Field(..., description="Notification channel")
    template_type: TemplateType = Field(..., description="Template type")
    subject: Optional[str] = Field(default=None, description="Subject line (for email)")
    body: str = Field(..., description="Template body with {{variable}} placeholders")
    variables: Optional[List[str]] = Field(default=None, description="List of template variables")
    metadata: Optional[Dict] = Field(default=None, description="Additional metadata")


class SendNotificationRequest(BaseModel):
    """Request model for sending a notification"""
    notification_id: str = Field(..., description="Unique notification identifier")
    user_id: str = Field(..., description="User identifier")
    channel: NotificationChannel = Field(..., description="Notification channel")
    template_id: Optional[str] = Field(default=None, description="Template to use")
    subject: Optional[str] = Field(default=None, description="Notification subject")
    body: Optional[str] = Field(default=None, description="Notification body")
    data: Optional[Dict] = Field(default=None, description="Template variables data")
    priority: NotificationPriority = Field(default=NotificationPriority.NORMAL, description="Priority level")
    scheduled_at: Optional[str] = Field(default=None, description="Schedule for later (ISO timestamp)")
    metadata: Optional[Dict] = Field(default=None, description="Additional metadata")


class SendBatchRequest(BaseModel):
    """Request model for sending batch notifications"""
    batch_id: str = Field(..., description="Unique batch identifier")
    user_ids: List[str] = Field(..., description="List of user IDs", min_items=1)
    channel: NotificationChannel = Field(..., description="Notification channel")
    template_id: str = Field(..., description="Template to use")
    data: Optional[Dict] = Field(default=None, description="Template variables data")
    priority: NotificationPriority = Field(default=NotificationPriority.NORMAL, description="Priority level")


class TrackEventRequest(BaseModel):
    """Request model for tracking notification events"""
    event_type: str = Field(..., description="Event type (opened, clicked)")


class SetPreferencesRequest(BaseModel):
    """Request model for setting user preferences"""
    channels: Optional[Dict[str, bool]] = Field(default=None, description="Channel enablement")
    quiet_hours: Optional[Dict] = Field(default=None, description="Quiet hours configuration")
    metadata: Optional[Dict] = Field(default=None, description="Additional metadata")


# API Endpoints
@router.post("/templates")
def create_template(
    request: CreateTemplateRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create notification template.
    Creates a reusable template for notifications with variable placeholders.
    """
    try:
        result = NotificationService.create_template(
            session=session,
            template_id=request.template_id,
            name=request.name,
            channel=request.channel,
            template_type=request.template_type,
            subject=request.subject,
            body=request.body,
            variables=request.variables,
            metadata=request.metadata
        )
        return {
            "success": True,
            "template": result,
            "message": f"Template created: {request.name}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating template: {str(e)}")


@router.get("/templates")
def list_templates(session: Session = Depends(get_db_session)):
    """
    List templates.
    Returns all notification templates.
    """
    try:
        templates = list(NotificationService._templates.values())
        return {
            "success": True,
            "templates": templates,
            "count": len(templates)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing templates: {str(e)}")


@router.get("/templates/{template_id}")
def get_template(
    template_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get template details.
    Returns detailed information about a specific template.
    """
    try:
        template = NotificationService._templates.get(template_id)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template not found: {template_id}")

        return {
            "success": True,
            "template": template
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting template: {str(e)}")


@router.get("/templates/{template_id}/analytics")
def get_template_analytics(
    template_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get template analytics.
    Returns delivery and engagement metrics for a template.
    """
    try:
        analytics = NotificationService.get_template_analytics(
            session=session,
            template_id=template_id
        )
        return {
            "success": True,
            "analytics": analytics
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting analytics: {str(e)}")


@router.post("/notifications")
def send_notification(
    request: SendNotificationRequest,
    session: Session = Depends(get_db_session)
):
    """
    Send notification.
    Sends a notification to a user via the specified channel.
    """
    try:
        result = NotificationService.send_notification(
            session=session,
            notification_id=request.notification_id,
            user_id=request.user_id,
            channel=request.channel,
            template_id=request.template_id,
            subject=request.subject,
            body=request.body,
            data=request.data,
            priority=request.priority,
            scheduled_at=request.scheduled_at,
            metadata=request.metadata
        )
        return {
            "success": True,
            "notification": result,
            "message": f"Notification {result['status']}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending notification: {str(e)}")


@router.get("/notifications")
def list_notifications(
    limit: int = 100,
    session: Session = Depends(get_db_session)
):
    """
    List notifications.
    Returns recent notifications.
    """
    try:
        notifications = list(NotificationService._notifications.values())
        notifications.sort(key=lambda x: x["created_at"], reverse=True)
        return {
            "success": True,
            "notifications": notifications[:limit],
            "count": len(notifications[:limit])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing notifications: {str(e)}")


@router.get("/notifications/{notification_id}")
def get_notification(
    notification_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get notification details.
    Returns detailed information about a specific notification.
    """
    try:
        notification = NotificationService._notifications.get(notification_id)
        if not notification:
            raise HTTPException(status_code=404, detail=f"Notification not found: {notification_id}")

        return {
            "success": True,
            "notification": notification
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting notification: {str(e)}")


@router.post("/notifications/{notification_id}/track")
def track_event(
    notification_id: str,
    request: TrackEventRequest,
    session: Session = Depends(get_db_session)
):
    """
    Track notification event.
    Tracks engagement events (opened, clicked) for a notification.
    """
    try:
        result = NotificationService.track_event(
            session=session,
            notification_id=notification_id,
            event_type=request.event_type
        )
        return {
            "success": True,
            "notification": result,
            "message": f"Event tracked: {request.event_type}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error tracking event: {str(e)}")


@router.post("/notifications/{notification_id}/retry")
def retry_notification(
    notification_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Retry failed notification.
    Attempts to resend a failed notification.
    """
    try:
        result = NotificationService.retry_failed_notification(
            session=session,
            notification_id=notification_id
        )
        return {
            "success": True,
            "notification": result,
            "message": "Notification retried"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrying notification: {str(e)}")


@router.post("/batch")
def send_batch(
    request: SendBatchRequest,
    session: Session = Depends(get_db_session)
):
    """
    Send batch notifications.
    Sends notifications to multiple users in a batch.
    """
    try:
        result = NotificationService.send_batch(
            session=session,
            batch_id=request.batch_id,
            user_ids=request.user_ids,
            channel=request.channel,
            template_id=request.template_id,
            data=request.data,
            priority=request.priority
        )
        return {
            "success": True,
            "batch": result,
            "message": f"Batch sent to {result['total_recipients']} users"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error sending batch: {str(e)}")


@router.get("/batch/{batch_id}")
def get_batch(
    batch_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get batch details.
    Returns information about a notification batch.
    """
    try:
        batch = NotificationService._notification_batches.get(batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail=f"Batch not found: {batch_id}")

        return {
            "success": True,
            "batch": batch
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting batch: {str(e)}")


@router.get("/users/{user_id}/notifications")
def get_user_notifications(
    user_id: str,
    channel: Optional[NotificationChannel] = None,
    status: Optional[NotificationStatus] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    Get user notifications.
    Returns notifications for a specific user with optional filtering.
    """
    try:
        notifications = NotificationService.get_user_notifications(
            session=session,
            user_id=user_id,
            channel=channel,
            status=status,
            limit=limit
        )
        return {
            "success": True,
            "notifications": notifications,
            "count": len(notifications)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting user notifications: {str(e)}")


@router.post("/users/{user_id}/preferences")
def set_user_preferences(
    user_id: str,
    request: SetPreferencesRequest,
    session: Session = Depends(get_db_session)
):
    """
    Set user preferences.
    Configures notification preferences for a user.
    """
    try:
        result = NotificationService.set_user_preferences(
            session=session,
            user_id=user_id,
            channels=request.channels,
            quiet_hours=request.quiet_hours,
            metadata=request.metadata
        )
        return {
            "success": True,
            "preferences": result,
            "message": "Preferences updated"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error setting preferences: {str(e)}")


@router.get("/users/{user_id}/preferences")
def get_user_preferences(
    user_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get user preferences.
    Returns notification preferences for a user.
    """
    try:
        preferences = NotificationService._user_preferences.get(user_id)
        if not preferences:
            # Return default preferences
            preferences = {
                "user_id": user_id,
                "channels": {
                    "email": True,
                    "sms": True,
                    "push": True,
                    "in_app": True
                },
                "quiet_hours": None,
                "metadata": {}
            }

        return {
            "success": True,
            "preferences": preferences
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting preferences: {str(e)}")


@router.get("/statistics")
def get_statistics(session: Session = Depends(get_db_session)):
    """
    Get statistics.
    Returns comprehensive notification service statistics.
    """
    try:
        stats = NotificationService.get_statistics(session)
        return {
            "success": True,
            "statistics": stats,
            "message": "Statistics retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")
