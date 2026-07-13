"""
Search and Indexing System

Provides full-text search, faceted filtering, query parsing, autocomplete,
and comprehensive search analytics across all system entities.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from collections import defaultdict
from enum import Enum
import re
import hashlib


class SearchEntity(str, Enum):
    """Searchable entity types"""
    TASK = "task"
    WORKFLOW = "workflow"
    AGENT = "agent"
    EXECUTION = "execution"
    LOG = "log"
    USER = "user"
    ISSUE = "issue"
    REFACTORING = "refactoring"


class SearchOperator(str, Enum):
    """Search query operators"""
    AND = "AND"
    OR = "OR"
    NOT = "NOT"


class SortOrder(str, Enum):
    """Sort order options"""
    RELEVANCE = "relevance"
    DATE_DESC = "date_desc"
    DATE_ASC = "date_asc"
    NAME_ASC = "name_asc"
    NAME_DESC = "name_desc"


class SearchService:
    """Search and Indexing System"""

    # In-memory storage
    _index: Dict[str, Dict[str, Dict]] = defaultdict(lambda: defaultdict(dict))
    _search_history: List[Dict] = []
    _search_suggestions: Dict[str, List[str]] = defaultdict(list)
    _search_analytics: Dict[str, int] = defaultdict(int)
    _facets: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    @staticmethod
    def index_document(
        session,
        entity_type: SearchEntity,
        entity_id: str,
        data: Dict,
        metadata: Optional[Dict] = None
    ) -> dict:
        """Index a document for searching."""
        # Extract searchable text
        searchable_text = SearchService._extract_searchable_text(data)

        # Generate tokens for full-text search
        tokens = SearchService._tokenize(searchable_text)

        document = {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "data": data,
            "metadata": metadata or {},
            "searchable_text": searchable_text,
            "tokens": tokens,
            "indexed_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "search_count": 0
        }

        # Store in index
        SearchService._index[entity_type][entity_id] = document

        # Update facets
        SearchService._update_facets(entity_type, data)

        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "tokens_count": len(tokens),
            "indexed_at": document["indexed_at"]
        }

    @staticmethod
    def _extract_searchable_text(data: Dict) -> str:
        """Extract searchable text from data."""
        searchable_fields = []

        for key, value in data.items():
            if isinstance(value, str):
                searchable_fields.append(value)
            elif isinstance(value, (int, float)):
                searchable_fields.append(str(value))
            elif isinstance(value, list):
                searchable_fields.extend([str(v) for v in value if isinstance(v, (str, int, float))])

        return " ".join(searchable_fields).lower()

    @staticmethod
    def _tokenize(text: str) -> Set[str]:
        """Tokenize text for search."""
        # Remove special characters and split
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        tokens = text.split()

        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}
        tokens = [t for t in tokens if t not in stop_words and len(t) > 2]

        return set(tokens)

    @staticmethod
    def _update_facets(entity_type: str, data: Dict):
        """Update facet counts."""
        # Update entity type facet
        SearchService._facets["entity_type"][entity_type] += 1

        # Update status facet if exists
        if "status" in data:
            SearchService._facets[f"{entity_type}_status"][data["status"]] += 1

        # Update date facet
        if "created_at" in data:
            try:
                date = datetime.fromisoformat(data["created_at"])
                date_key = date.strftime("%Y-%m")
                SearchService._facets[f"{entity_type}_date"][date_key] += 1
            except:
                pass

    @staticmethod
    def search(
        session,
        query: str,
        entity_types: Optional[List[SearchEntity]] = None,
        filters: Optional[Dict] = None,
        sort_by: SortOrder = SortOrder.RELEVANCE,
        limit: int = 20,
        offset: int = 0
    ) -> dict:
        """Perform full-text search."""
        # Parse query
        parsed_query = SearchService._parse_query(query)

        # Get search tokens
        search_tokens = SearchService._tokenize(query)

        # Search across entity types
        if not entity_types:
            entity_types = list(SearchEntity)

        results = []

        for entity_type in entity_types:
            if entity_type not in SearchService._index:
                continue

            for entity_id, document in SearchService._index[entity_type].items():
                # Calculate relevance score
                score = SearchService._calculate_relevance(search_tokens, document)

                if score > 0:
                    # Apply filters
                    if filters and not SearchService._apply_filters(document, filters):
                        continue

                    results.append({
                        "entity_type": document["entity_type"],
                        "entity_id": document["entity_id"],
                        "data": document["data"],
                        "score": score,
                        "highlights": SearchService._get_highlights(query, document)
                    })

        # Sort results
        results = SearchService._sort_results(results, sort_by)

        # Pagination
        total = len(results)
        results = results[offset:offset + limit]

        # Track search
        SearchService._track_search(query, entity_types, total)

        return {
            "query": query,
            "results": results,
            "total": total,
            "limit": limit,
            "offset": offset,
            "facets": SearchService._get_relevant_facets(entity_types)
        }

    @staticmethod
    def _parse_query(query: str) -> Dict:
        """Parse search query for advanced operators."""
        # Simple query parsing - can be enhanced
        return {
            "original": query,
            "terms": query.split(),
            "operators": []
        }

    @staticmethod
    def _calculate_relevance(search_tokens: Set[str], document: Dict) -> float:
        """Calculate relevance score for a document."""
        doc_tokens = document["tokens"]

        if not search_tokens or not doc_tokens:
            return 0.0

        # Calculate token overlap
        overlap = search_tokens.intersection(doc_tokens)

        if not overlap:
            return 0.0

        # TF-IDF-like scoring
        term_frequency = len(overlap) / len(doc_tokens)
        coverage = len(overlap) / len(search_tokens)

        score = (term_frequency * 0.4) + (coverage * 0.6)

        # Boost recent documents
        try:
            indexed_at = datetime.fromisoformat(document["indexed_at"])
            age_days = (datetime.utcnow() - indexed_at).days
            recency_boost = max(0, 1 - (age_days / 365))
            score *= (1 + recency_boost * 0.2)
        except:
            pass

        return score

    @staticmethod
    def _apply_filters(document: Dict, filters: Dict) -> bool:
        """Apply filters to a document."""
        for key, value in filters.items():
            if key in document["data"]:
                if isinstance(value, list):
                    if document["data"][key] not in value:
                        return False
                elif document["data"][key] != value:
                    return False
        return True

    @staticmethod
    def _get_highlights(query: str, document: Dict) -> List[str]:
        """Get text highlights for search results."""
        searchable_text = document["searchable_text"]
        query_tokens = SearchService._tokenize(query)

        highlights = []
        words = searchable_text.split()

        for i, word in enumerate(words):
            if any(token in word.lower() for token in query_tokens):
                # Get context around match
                start = max(0, i - 5)
                end = min(len(words), i + 6)
                context = " ".join(words[start:end])
                highlights.append(f"...{context}...")

                if len(highlights) >= 3:
                    break

        return highlights

    @staticmethod
    def _sort_results(results: List[Dict], sort_by: SortOrder) -> List[Dict]:
        """Sort search results."""
        if sort_by == SortOrder.RELEVANCE:
            return sorted(results, key=lambda x: x["score"], reverse=True)
        elif sort_by == SortOrder.DATE_DESC:
            return sorted(
                results,
                key=lambda x: x["data"].get("created_at", ""),
                reverse=True
            )
        elif sort_by == SortOrder.DATE_ASC:
            return sorted(
                results,
                key=lambda x: x["data"].get("created_at", "")
            )
        elif sort_by == SortOrder.NAME_ASC:
            return sorted(
                results,
                key=lambda x: x["data"].get("name", x["data"].get("title", ""))
            )
        elif sort_by == SortOrder.NAME_DESC:
            return sorted(
                results,
                key=lambda x: x["data"].get("name", x["data"].get("title", "")),
                reverse=True
            )

        return results

    @staticmethod
    def _get_relevant_facets(entity_types: List[str]) -> Dict:
        """Get relevant facets for search results."""
        facets = {
            "entity_type": dict(SearchService._facets["entity_type"])
        }

        for entity_type in entity_types:
            status_key = f"{entity_type}_status"
            if status_key in SearchService._facets:
                facets[status_key] = dict(SearchService._facets[status_key])

        return facets

    @staticmethod
    def _track_search(query: str, entity_types: List[str], results_count: int):
        """Track search for analytics."""
        search_entry = {
            "query": query,
            "entity_types": entity_types,
            "results_count": results_count,
            "timestamp": datetime.utcnow().isoformat()
        }

        SearchService._search_history.append(search_entry)
        SearchService._search_analytics[query] += 1

        # Keep only last 10000 searches
        SearchService._search_history = SearchService._search_history[-10000:]

    @staticmethod
    def suggest(
        session,
        prefix: str,
        entity_types: Optional[List[SearchEntity]] = None,
        limit: int = 10
    ) -> dict:
        """Get search suggestions based on prefix."""
        if not entity_types:
            entity_types = list(SearchEntity)

        suggestions = []
        seen = set()

        # Get suggestions from indexed data
        for entity_type in entity_types:
            if entity_type not in SearchService._index:
                continue

            for document in SearchService._index[entity_type].values():
                # Check name/title fields
                for field in ["name", "title", "description"]:
                    if field in document["data"]:
                        value = document["data"][field]
                        if isinstance(value, str) and value.lower().startswith(prefix.lower()):
                            if value not in seen:
                                suggestions.append({
                                    "text": value,
                                    "entity_type": entity_type,
                                    "field": field
                                })
                                seen.add(value)

                if len(suggestions) >= limit:
                    break

        return {
            "prefix": prefix,
            "suggestions": suggestions[:limit]
        }

    @staticmethod
    def reindex_all(session, entity_type: SearchEntity) -> dict:
        """Reindex all documents of a specific type."""
        if entity_type in SearchService._index:
            count = len(SearchService._index[entity_type])

            # Update all timestamps
            for document in SearchService._index[entity_type].values():
                document["updated_at"] = datetime.utcnow().isoformat()

            return {
                "entity_type": entity_type,
                "reindexed_count": count,
                "reindexed_at": datetime.utcnow().isoformat()
            }

        return {
            "entity_type": entity_type,
            "reindexed_count": 0,
            "reindexed_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def delete_from_index(
        session,
        entity_type: SearchEntity,
        entity_id: str
    ) -> dict:
        """Remove a document from the search index."""
        if entity_type in SearchService._index and entity_id in SearchService._index[entity_type]:
            del SearchService._index[entity_type][entity_id]

            return {
                "entity_type": entity_type,
                "entity_id": entity_id,
                "deleted": True,
                "deleted_at": datetime.utcnow().isoformat()
            }

        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "deleted": False,
            "error": "Document not found in index"
        }

    @staticmethod
    def get_popular_searches(
        session,
        limit: int = 10,
        time_range: Optional[int] = None
    ) -> dict:
        """Get most popular search queries."""
        if time_range:
            cutoff = (datetime.utcnow() - timedelta(hours=time_range)).isoformat()
            recent_searches = [
                s for s in SearchService._search_history
                if s["timestamp"] >= cutoff
            ]

            query_counts = defaultdict(int)
            for search in recent_searches:
                query_counts[search["query"]] += 1
        else:
            query_counts = SearchService._search_analytics

        popular = sorted(
            query_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:limit]

        return {
            "popular_searches": [
                {"query": query, "count": count}
                for query, count in popular
            ],
            "time_range_hours": time_range
        }

    @staticmethod
    def get_search_history(
        session,
        limit: int = 50
    ) -> dict:
        """Get recent search history."""
        recent = SearchService._search_history[-limit:]
        recent.reverse()

        return {
            "searches": recent,
            "total": len(SearchService._search_history)
        }

    @staticmethod
    def get_index_stats(session) -> dict:
        """Get comprehensive index statistics."""
        total_documents = sum(
            len(docs) for docs in SearchService._index.values()
        )

        by_entity_type = {
            entity_type: len(docs)
            for entity_type, docs in SearchService._index.items()
        }

        # Calculate index size (approximate)
        total_tokens = sum(
            len(doc["tokens"])
            for docs in SearchService._index.values()
            for doc in docs.values()
        )

        return {
            "index": {
                "total_documents": total_documents,
                "by_entity_type": by_entity_type,
                "total_tokens": total_tokens,
                "avg_tokens_per_doc": total_tokens / total_documents if total_documents > 0 else 0
            },
            "searches": {
                "total_searches": len(SearchService._search_history),
                "unique_queries": len(SearchService._search_analytics)
            },
            "facets": {
                "total_facets": len(SearchService._facets)
            }
        }
