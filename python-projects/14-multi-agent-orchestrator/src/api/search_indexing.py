"""
Search and Indexing API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.core.database import get_db_session
from src.services.search_indexing import SearchService, SearchEntity, SortOrder


router = APIRouter()


# Request Models
class IndexDocumentRequest(BaseModel):
    """Request to index a document"""
    entity_type: SearchEntity
    entity_id: str
    data: Dict
    metadata: Optional[Dict] = None


class SearchRequest(BaseModel):
    """Search request"""
    query: str = Field(..., min_length=1)
    entity_types: Optional[List[SearchEntity]] = None
    filters: Optional[Dict] = None
    sort_by: SortOrder = SortOrder.RELEVANCE
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class SuggestRequest(BaseModel):
    """Autocomplete suggestion request"""
    prefix: str = Field(..., min_length=1)
    entity_types: Optional[List[SearchEntity]] = None
    limit: int = Field(10, ge=1, le=50)


class DeleteFromIndexRequest(BaseModel):
    """Request to delete from index"""
    entity_type: SearchEntity
    entity_id: str


# Response Models
class IndexDocumentResponse(BaseModel):
    """Index document response"""
    entity_type: str
    entity_id: str
    tokens_count: int
    indexed_at: str


class SearchResultItem(BaseModel):
    """Search result item"""
    entity_type: str
    entity_id: str
    data: Dict
    score: float
    highlights: List[str]


class SearchResponse(BaseModel):
    """Search response"""
    query: str
    results: List[SearchResultItem]
    total: int
    limit: int
    offset: int
    facets: Dict


class SuggestionItem(BaseModel):
    """Suggestion item"""
    text: str
    entity_type: str
    field: str


class SuggestResponse(BaseModel):
    """Suggest response"""
    prefix: str
    suggestions: List[SuggestionItem]


class PopularSearchItem(BaseModel):
    """Popular search item"""
    query: str
    count: int


class PopularSearchesResponse(BaseModel):
    """Popular searches response"""
    popular_searches: List[PopularSearchItem]
    time_range_hours: Optional[int]


# Endpoints
@router.post("/search/index", response_model=IndexDocumentResponse)
async def index_document(
    request: IndexDocumentRequest,
    session: Session = Depends(get_db_session)
):
    """
    Index a document for searching.

    Indexes a document with full-text search tokens, facets, and metadata.
    """
    try:
        result = SearchService.index_document(
            session=session,
            entity_type=request.entity_type,
            entity_id=request.entity_id,
            data=request.data,
            metadata=request.metadata
        )
        return IndexDocumentResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search", response_model=SearchResponse)
async def search(
    request: SearchRequest,
    session: Session = Depends(get_db_session)
):
    """
    Perform full-text search across entities.

    Supports:
    - Multiple entity types
    - Faceted filtering
    - Multiple sort orders
    - Pagination
    - Relevance scoring
    """
    try:
        result = SearchService.search(
            session=session,
            query=request.query,
            entity_types=request.entity_types,
            filters=request.filters,
            sort_by=request.sort_by,
            limit=request.limit,
            offset=request.offset
        )
        return SearchResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/suggest", response_model=SuggestResponse)
async def suggest(
    request: SuggestRequest,
    session: Session = Depends(get_db_session)
):
    """
    Get autocomplete suggestions for search.

    Returns suggestions based on indexed document fields.
    """
    try:
        result = SearchService.suggest(
            session=session,
            prefix=request.prefix,
            entity_types=request.entity_types,
            limit=request.limit
        )
        return SuggestResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search/reindex/{entity_type}")
async def reindex_all(
    entity_type: SearchEntity,
    session: Session = Depends(get_db_session)
):
    """
    Reindex all documents of a specific type.

    Useful for rebuilding the search index after schema changes.
    """
    try:
        result = SearchService.reindex_all(
            session=session,
            entity_type=entity_type
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/search/index")
async def delete_from_index(
    request: DeleteFromIndexRequest,
    session: Session = Depends(get_db_session)
):
    """
    Remove a document from the search index.

    Does not delete the actual entity, only removes it from search results.
    """
    try:
        result = SearchService.delete_from_index(
            session=session,
            entity_type=request.entity_type,
            entity_id=request.entity_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/popular", response_model=PopularSearchesResponse)
async def get_popular_searches(
    limit: int = 10,
    time_range: Optional[int] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get most popular search queries.

    Args:
        limit: Maximum number of results
        time_range: Time range in hours (optional)
    """
    try:
        result = SearchService.get_popular_searches(
            session=session,
            limit=limit,
            time_range=time_range
        )
        return PopularSearchesResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/history")
async def get_search_history(
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    Get recent search history.

    Returns the most recent searches with timestamps and result counts.
    """
    try:
        result = SearchService.get_search_history(
            session=session,
            limit=limit
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/stats")
async def get_index_stats(
    session: Session = Depends(get_db_session)
):
    """
    Get comprehensive search index statistics.

    Returns:
    - Total documents indexed
    - Documents by entity type
    - Total search tokens
    - Search history metrics
    - Facet counts
    """
    try:
        result = SearchService.get_index_stats(session=session)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Convenience endpoints for specific entity types
@router.get("/search/tasks")
async def search_tasks(
    query: str,
    limit: int = 20,
    session: Session = Depends(get_db_session)
):
    """Search tasks only."""
    try:
        result = SearchService.search(
            session=session,
            query=query,
            entity_types=[SearchEntity.TASK],
            limit=limit
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/workflows")
async def search_workflows(
    query: str,
    limit: int = 20,
    session: Session = Depends(get_db_session)
):
    """Search workflows only."""
    try:
        result = SearchService.search(
            session=session,
            query=query,
            entity_types=[SearchEntity.WORKFLOW],
            limit=limit
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/agents")
async def search_agents(
    query: str,
    limit: int = 20,
    session: Session = Depends(get_db_session)
):
    """Search agents only."""
    try:
        result = SearchService.search(
            session=session,
            query=query,
            entity_types=[SearchEntity.AGENT],
            limit=limit
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/executions")
async def search_executions(
    query: str,
    limit: int = 20,
    session: Session = Depends(get_db_session)
):
    """Search executions only."""
    try:
        result = SearchService.search(
            session=session,
            query=query,
            entity_types=[SearchEntity.EXECUTION],
            limit=limit
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search/logs")
async def search_logs(
    query: str,
    limit: int = 20,
    session: Session = Depends(get_db_session)
):
    """Search logs only."""
    try:
        result = SearchService.search(
            session=session,
            query=query,
            entity_types=[SearchEntity.LOG],
            limit=limit
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
