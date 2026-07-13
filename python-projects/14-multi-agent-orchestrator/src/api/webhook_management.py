"""
Webhook Management API

REST API endpoints for webhook registration, event triggering, delivery tracking,
and webhook lifecycle management.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from sqlalchemy.orm import Session

from src.database import get_db_session
from src.services.webhook_management import (
    WebhookManagement,
    WebhookStatus,
    EventType,
    DeliveryStatus,
    RetryStrategy
)


router = APIRouter()


# Request/Response Models
class RegisterWebhookRequest(BaseModel):
    """Request model for registering a webhook"""
    webhook_id: str = Field(..., description="Unique webhook identifier")
    url: str = Field(..., description="Webhook URL endpoint")
    event_types: List[EventType] = Field(..., description="Event types to subscribe to", min_items=1)
    description: Optional[str] = Field(default=None, description="Webhook description")
    secret: Optional[str] = Field(default=None, description="Webhook secret (auto-generated if not provided)")
    headers: Optional[Dict] = Field(default=None, description="Custom HTTP headers")
    retry_strategy: RetryStrategy = Field(default=RetryStrategy.EXPONENTIAL, description="Retry strategy")
    max_retries: int = Field(default=3, description="Maximum retry attempts", ge=0, le=10)
    metadata: Optional[Dict] = Field(default=None, description="Additional metadata")


class TriggerEventRequest(BaseModel):
    """Request model for triggering an event"""
    event_type: EventType = Field(..., description="Type of event")
    payload: Dict = Field(..., description="Event payload data")
    metadata: Optional[Dict] = Field(default=None, description="Event metadata")


class UpdateWebhookRequest(BaseModel):
    """Request model for updating a webhook"""
    url: Optional[str] = Field(default=None, description="New webhook URL")
    event_types: Optional[List[EventType]] = Field(default=None, description="New event types")
    status: Optional[WebhookStatus] = Field(default=None, description="New status")
    retry_strategy: Optional[RetryStrategy] = Field(default=None, description="New retry strategy")
    max_retries: Optional[int] = Field(default=None, description="New max retries", ge=0, le=10)


class VerifySignatureRequest(BaseModel):
    """Request model for verifying webhook signature"""
    payload: str = Field(..., description="Webhook payload")
    signature: str = Field(..., description="Signature to verify")


# API Endpoints
@router.post("/webhooks")
def register_webhook(
    request: RegisterWebhookRequest,
    session: Session = Depends(get_db_session)
):
    """
    Register webhook.
    Registers a webhook endpoint to receive event notifications.
    """
    try:
        result = WebhookManagement.register_webhook(
            session=session,
            webhook_id=request.webhook_id,
            url=request.url,
            event_types=request.event_types,
            description=request.description,
            secret=request.secret,
            headers=request.headers,
            retry_strategy=request.retry_strategy,
            max_retries=request.max_retries,
            metadata=request.metadata
        )
        return {
            "success": True,
            "webhook": result,
            "message": f"Webhook registered: {request.url}"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error registering webhook: {str(e)}")


@router.get("/webhooks")
def list_webhooks(session: Session = Depends(get_db_session)):
    """
    List webhooks.
    Returns all registered webhook endpoints.
    """
    try:
        webhooks = list(WebhookManagement._webhooks.values())
        return {
            "success": True,
            "webhooks": webhooks,
            "count": len(webhooks)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing webhooks: {str(e)}")


@router.get("/webhooks/{webhook_id}")
def get_webhook(
    webhook_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get webhook details.
    Returns detailed information about a specific webhook.
    """
    try:
        webhook = WebhookManagement._webhooks.get(webhook_id)
        if not webhook:
            raise HTTPException(status_code=404, detail=f"Webhook not found: {webhook_id}")

        return {
            "success": True,
            "webhook": webhook
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting webhook: {str(e)}")


@router.put("/webhooks/{webhook_id}")
def update_webhook(
    webhook_id: str,
    request: UpdateWebhookRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update webhook.
    Updates webhook configuration including URL, event types, and status.
    """
    try:
        result = WebhookManagement.update_webhook(
            session=session,
            webhook_id=webhook_id,
            url=request.url,
            event_types=request.event_types,
            status=request.status,
            retry_strategy=request.retry_strategy,
            max_retries=request.max_retries
        )
        return {
            "success": True,
            "webhook": result,
            "message": "Webhook updated successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating webhook: {str(e)}")


@router.delete("/webhooks/{webhook_id}")
def delete_webhook(
    webhook_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Delete webhook.
    Removes a webhook endpoint and all its subscriptions.
    """
    try:
        webhook = WebhookManagement._webhooks.get(webhook_id)
        if not webhook:
            raise HTTPException(status_code=404, detail=f"Webhook not found: {webhook_id}")

        # Remove subscriptions
        for event_type in webhook["event_types"]:
            if webhook_id in WebhookManagement._subscriptions[event_type]:
                WebhookManagement._subscriptions[event_type].remove(webhook_id)

        # Delete webhook
        del WebhookManagement._webhooks[webhook_id]

        return {
            "success": True,
            "message": f"Webhook deleted: {webhook_id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting webhook: {str(e)}")


@router.get("/webhooks/{webhook_id}/stats")
def get_webhook_stats(
    webhook_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get webhook statistics.
    Returns delivery statistics and performance metrics for a webhook.
    """
    try:
        stats = WebhookManagement.get_webhook_stats(
            session=session,
            webhook_id=webhook_id
        )
        return {
            "success": True,
            "stats": stats
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting stats: {str(e)}")


@router.post("/webhooks/{webhook_id}/test")
def test_webhook(
    webhook_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Test webhook.
    Sends a test event to verify webhook endpoint connectivity.
    """
    try:
        result = WebhookManagement.test_webhook(
            session=session,
            webhook_id=webhook_id
        )
        return {
            "success": True,
            "test": result,
            "message": "Test delivery sent"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error testing webhook: {str(e)}")


@router.post("/webhooks/{webhook_id}/verify-signature")
def verify_signature(
    webhook_id: str,
    request: VerifySignatureRequest,
    session: Session = Depends(get_db_session)
):
    """
    Verify webhook signature.
    Verifies HMAC signature for webhook payload authentication.
    """
    try:
        is_valid = WebhookManagement.verify_signature(
            webhook_id=webhook_id,
            payload=request.payload,
            signature=request.signature
        )
        return {
            "success": True,
            "is_valid": is_valid,
            "message": "Signature valid" if is_valid else "Signature invalid"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error verifying signature: {str(e)}")


@router.post("/events")
def trigger_event(
    request: TriggerEventRequest,
    session: Session = Depends(get_db_session)
):
    """
    Trigger event.
    Triggers an event and delivers it to all subscribed webhooks.
    """
    try:
        result = WebhookManagement.trigger_event(
            session=session,
            event_type=request.event_type,
            payload=request.payload,
            metadata=request.metadata
        )
        return {
            "success": True,
            "event": result,
            "message": f"Event triggered: {request.event_type}"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error triggering event: {str(e)}")


@router.get("/events")
def list_events(
    limit: int = 100,
    session: Session = Depends(get_db_session)
):
    """
    List events.
    Returns recent events that were triggered.
    """
    try:
        events = WebhookManagement._events[-limit:]
        return {
            "success": True,
            "events": events,
            "count": len(events)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing events: {str(e)}")


@router.get("/deliveries")
def get_delivery_history(
    webhook_id: Optional[str] = None,
    event_type: Optional[EventType] = None,
    status: Optional[DeliveryStatus] = None,
    limit: int = 100,
    session: Session = Depends(get_db_session)
):
    """
    Get delivery history.
    Returns webhook delivery history with optional filtering.
    """
    try:
        deliveries = WebhookManagement.get_delivery_history(
            session=session,
            webhook_id=webhook_id,
            event_type=event_type,
            status=status,
            limit=limit
        )
        return {
            "success": True,
            "deliveries": deliveries,
            "count": len(deliveries)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting delivery history: {str(e)}")


@router.get("/deliveries/{delivery_id}")
def get_delivery(
    delivery_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get delivery details.
    Returns detailed information about a specific webhook delivery.
    """
    try:
        delivery = WebhookManagement._deliveries.get(delivery_id)
        if not delivery:
            raise HTTPException(status_code=404, detail=f"Delivery not found: {delivery_id}")

        return {
            "success": True,
            "delivery": delivery
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting delivery: {str(e)}")


@router.post("/deliveries/{delivery_id}/retry")
def retry_delivery(
    delivery_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Retry delivery.
    Manually retries a failed webhook delivery.
    """
    try:
        result = WebhookManagement.retry_delivery(
            session=session,
            delivery_id=delivery_id
        )
        return {
            "success": True,
            "delivery": result,
            "message": "Delivery retried"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrying delivery: {str(e)}")


@router.get("/statistics")
def get_statistics(session: Session = Depends(get_db_session)):
    """
    Get statistics.
    Returns comprehensive webhook management statistics.
    """
    try:
        stats = WebhookManagement.get_statistics(session)
        return {
            "success": True,
            "statistics": stats,
            "message": "Statistics retrieved successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting statistics: {str(e)}")
