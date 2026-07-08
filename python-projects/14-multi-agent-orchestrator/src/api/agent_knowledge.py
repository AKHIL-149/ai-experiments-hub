"""
Agent Knowledge Sharing API

REST API endpoints for sharing, discovering, and validating knowledge.
"""

from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_knowledge import (
    AgentKnowledge,
    KnowledgeType,
    KnowledgeCategory,
    ValidationStatus,
    AccessLevel
)


router = APIRouter()


# Request/Response Models
class ShareKnowledgeRequest(BaseModel):
    knowledge_type: str = Field(..., description="Type of knowledge")
    category: str = Field(..., description="Knowledge category")
    title: str = Field(..., description="Knowledge title")
    content: dict = Field(..., description="Knowledge content")
    tags: Optional[List[str]] = Field(None, description="Tags for categorization")
    access_level: str = Field(AccessLevel.PUBLIC, description="Access level")
    source: Optional[str] = Field(None, description="Source reference")
    confidence: float = Field(0.8, description="Confidence in accuracy (0-1)")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class QueryKnowledgeRequest(BaseModel):
    query_text: str = Field(..., description="Search query")
    categories: Optional[List[str]] = Field(None, description="Filter by categories")
    tags: Optional[List[str]] = Field(None, description="Filter by tags")
    knowledge_types: Optional[List[str]] = Field(None, description="Filter by knowledge types")
    min_confidence: float = Field(0.5, description="Minimum confidence threshold")
    min_rating: float = Field(0.0, description="Minimum average rating")
    validated_only: bool = Field(False, description="Only return validated knowledge")
    limit: int = Field(10, description="Maximum results")


class RateKnowledgeRequest(BaseModel):
    rating: float = Field(..., description="Rating value (1-5)")
    comment: str = Field("", description="Optional comment")
    helpful: bool = Field(True, description="Whether item was helpful")


class ValidateKnowledgeRequest(BaseModel):
    is_valid: bool = Field(..., description="Whether knowledge is valid")
    validation_notes: str = Field("", description="Notes about validation")
    evidence: Optional[dict] = Field(None, description="Supporting evidence")


class RecordUsageRequest(BaseModel):
    usage_context: dict = Field(..., description="Context of usage")
    was_useful: bool = Field(..., description="Whether knowledge was useful")
    outcome: str = Field("", description="Outcome description")


class UpdateKnowledgeRequest(BaseModel):
    updates: dict = Field(..., description="Fields to update")
    update_reason: str = Field("", description="Reason for update")


class SubscribeRequest(BaseModel):
    category: Optional[str] = Field(None, description="Category to subscribe to")
    tags: Optional[List[str]] = Field(None, description="Tags to subscribe to")


@router.post("/share")
def share_knowledge(
    agent_id: int,
    request: ShareKnowledgeRequest,
    session: Session = Depends(get_db_session)
):
    """
    Share a knowledge item.

    Creates a new knowledge entry that can be discovered and used by other agents.
    Knowledge can be facts, procedures, best practices, solutions, or patterns.
    """
    try:
        knowledge_item = AgentKnowledge.share_knowledge(
            session=session,
            agent_id=agent_id,
            knowledge_type=request.knowledge_type,
            category=request.category,
            title=request.title,
            content=request.content,
            tags=request.tags,
            access_level=request.access_level,
            source=request.source,
            confidence=request.confidence,
            metadata=request.metadata
        )

        return {
            "success": True,
            "knowledge_item": knowledge_item,
            "message": f"Knowledge shared: {request.title}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query")
def query_knowledge(
    agent_id: int,
    request: QueryKnowledgeRequest,
    session: Session = Depends(get_db_session)
):
    """
    Query the knowledge base.

    Search for relevant knowledge using text queries, filters, and relevance scoring.
    Returns ranked results based on confidence, ratings, and text matching.
    """
    try:
        results = AgentKnowledge.query_knowledge(
            session=session,
            agent_id=agent_id,
            query_text=request.query_text,
            categories=request.categories,
            tags=request.tags,
            knowledge_types=request.knowledge_types,
            min_confidence=request.min_confidence,
            min_rating=request.min_rating,
            validated_only=request.validated_only,
            limit=request.limit
        )

        return {
            "success": True,
            **results
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/items/{item_id}/rate")
def rate_knowledge(
    item_id: str,
    agent_id: int,
    request: RateKnowledgeRequest,
    session: Session = Depends(get_db_session)
):
    """
    Rate a knowledge item.

    Provide feedback on knowledge quality and usefulness.
    Ratings help other agents assess knowledge value.
    """
    try:
        rating = AgentKnowledge.rate_knowledge(
            session=session,
            item_id=item_id,
            agent_id=agent_id,
            rating=request.rating,
            comment=request.comment,
            helpful=request.helpful
        )

        return {
            "success": True,
            "rating": rating,
            "message": f"Rated {request.rating}/5"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/items/{item_id}/validate")
def validate_knowledge(
    item_id: str,
    validator_agent_id: int,
    request: ValidateKnowledgeRequest,
    session: Session = Depends(get_db_session)
):
    """
    Validate or dispute knowledge.

    Agents can validate knowledge accuracy or mark it as disputed.
    Multiple validations change status to validated or disputed.
    """
    try:
        validation = AgentKnowledge.validate_knowledge(
            session=session,
            item_id=item_id,
            validator_agent_id=validator_agent_id,
            is_valid=request.is_valid,
            validation_notes=request.validation_notes,
            evidence=request.evidence
        )

        return {
            "success": True,
            "validation": validation,
            "message": f"Knowledge {'validated' if request.is_valid else 'disputed'}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/items/{item_id}/usage")
def record_usage(
    item_id: str,
    agent_id: int,
    request: RecordUsageRequest,
    session: Session = Depends(get_db_session)
):
    """
    Record knowledge usage.

    Track when and how knowledge is applied.
    Usage tracking helps measure knowledge effectiveness.
    """
    try:
        usage = AgentKnowledge.record_usage(
            session=session,
            item_id=item_id,
            agent_id=agent_id,
            usage_context=request.usage_context,
            was_useful=request.was_useful,
            outcome=request.outcome
        )

        return {
            "success": True,
            "usage": usage,
            "message": "Usage recorded"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/items/{item_id}")
def update_knowledge(
    item_id: str,
    agent_id: int,
    request: UpdateKnowledgeRequest,
    session: Session = Depends(get_db_session)
):
    """
    Update existing knowledge item.

    Only the original creator can update knowledge.
    Updates increment version and reset validation if content changes.
    """
    try:
        knowledge_item = AgentKnowledge.update_knowledge(
            session=session,
            item_id=item_id,
            agent_id=agent_id,
            updates=request.updates,
            update_reason=request.update_reason
        )

        return {
            "success": True,
            "knowledge_item": knowledge_item,
            "message": "Knowledge updated"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subscribe")
def subscribe_to_category(
    agent_id: int,
    request: SubscribeRequest,
    session: Session = Depends(get_db_session)
):
    """
    Subscribe to knowledge updates.

    Receive notifications when new knowledge is shared in categories or tags.
    """
    try:
        subscription = AgentKnowledge.subscribe_to_category(
            session=session,
            agent_id=agent_id,
            category=request.category,
            tags=request.tags
        )

        return {
            "success": True,
            "subscription": subscription,
            "message": "Subscribed to knowledge updates"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/items/{item_id}")
def get_knowledge_item(
    item_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get knowledge item details.

    Returns complete information including ratings, validations,
    usage history, and effectiveness metrics.
    """
    try:
        knowledge_item = AgentKnowledge.get_knowledge_item(
            session=session,
            item_id=item_id
        )

        return {
            "success": True,
            "knowledge_item": knowledge_item
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}")
def get_agent_knowledge(
    agent_id: int,
    include_shared: bool = True,
    include_accessed: bool = True,
    session: Session = Depends(get_db_session)
):
    """
    Get agent's knowledge activity.

    Returns knowledge shared by agent, knowledge accessed,
    and query history.
    """
    try:
        activity = AgentKnowledge.get_agent_knowledge(
            session=session,
            agent_id=agent_id,
            include_shared=include_shared,
            include_accessed=include_accessed
        )

        return {
            "success": True,
            **activity
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trending")
def get_trending_knowledge(
    timeframe_hours: int = 24,
    limit: int = 10,
    session: Session = Depends(get_db_session)
):
    """
    Get trending knowledge items.

    Returns knowledge with highest recent activity
    based on ratings and usage.
    """
    try:
        trending = AgentKnowledge.get_trending_knowledge(
            session=session,
            timeframe_hours=timeframe_hours,
            limit=limit
        )

        return {
            "success": True,
            **trending
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get knowledge system statistics.

    Returns aggregate data including total items, ratings,
    validations, usage, and effectiveness metrics.
    """
    try:
        stats = AgentKnowledge.get_knowledge_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/knowledge-types")
def list_knowledge_types():
    """
    List all knowledge types.

    Returns all types of knowledge that can be shared.
    """
    return {
        "success": True,
        "knowledge_types": [
            {"type": KnowledgeType.FACT, "description": "Factual information"},
            {"type": KnowledgeType.PROCEDURE, "description": "Step-by-step procedures"},
            {"type": KnowledgeType.BEST_PRACTICE, "description": "Proven best practices"},
            {"type": KnowledgeType.SOLUTION, "description": "Problem solutions"},
            {"type": KnowledgeType.PATTERN, "description": "Recurring patterns"},
            {"type": KnowledgeType.WARNING, "description": "Warnings and pitfalls"},
            {"type": KnowledgeType.TIP, "description": "Helpful tips"}
        ]
    }


@router.get("/categories")
def list_categories():
    """
    List all knowledge categories.

    Returns all available categories for organizing knowledge.
    """
    return {
        "success": True,
        "categories": [
            {"category": KnowledgeCategory.TECHNICAL, "description": "Technical knowledge"},
            {"category": KnowledgeCategory.PROCESS, "description": "Process and workflow knowledge"},
            {"category": KnowledgeCategory.DOMAIN, "description": "Domain-specific knowledge"},
            {"category": KnowledgeCategory.COLLABORATION, "description": "Collaboration knowledge"},
            {"category": KnowledgeCategory.STRATEGY, "description": "Strategic knowledge"},
            {"category": KnowledgeCategory.TOOLING, "description": "Tool usage knowledge"},
            {"category": KnowledgeCategory.GENERAL, "description": "General knowledge"}
        ]
    }


@router.get("/validation-statuses")
def list_validation_statuses():
    """
    List all validation statuses.

    Returns all possible validation statuses for knowledge items.
    """
    return {
        "success": True,
        "validation_statuses": [
            {"status": ValidationStatus.UNVALIDATED, "description": "Not yet validated"},
            {"status": ValidationStatus.PENDING, "description": "Validation in progress"},
            {"status": ValidationStatus.VALIDATED, "description": "Validated by peers (3+ validations)"},
            {"status": ValidationStatus.DISPUTED, "description": "Disputed by peers (2+ disputes)"},
            {"status": ValidationStatus.DEPRECATED, "description": "Marked as outdated"}
        ]
    }


@router.get("/access-levels")
def list_access_levels():
    """
    List all access levels.

    Returns all possible access levels for knowledge sharing.
    """
    return {
        "success": True,
        "access_levels": [
            {"level": AccessLevel.PUBLIC, "description": "Accessible to all agents"},
            {"level": AccessLevel.COALITION, "description": "Accessible to coalition members"},
            {"level": AccessLevel.TRUSTED, "description": "Accessible to trusted agents"},
            {"level": AccessLevel.PRIVATE, "description": "Private to creator"}
        ]
    }
