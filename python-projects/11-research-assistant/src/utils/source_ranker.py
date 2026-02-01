"""
Source Ranker for Research Assistant.

Ranks sources by composite score:
- 40% semantic similarity to query
- 30% authority (source type + domain reputation)
- 20% recency (publication freshness)
- 10% citation count (academic citations)
"""

import logging
import re
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class RankedSource:
    """Source with ranking scores."""
    id: str
    source_type: str
    title: str
    content: str
    url: Optional[str] = None

    # Scores
    similarity_score: float = 0.0
    authority_score: float = 0.0
    recency_score: float = 0.0
    citation_score: float = 0.0
    composite_score: float = 0.0

    # Metadata
    published_date: Optional[datetime] = None
    citation_count: Optional[int] = None
    domain: Optional[str] = None


class SourceRanker:
    """Ranks sources by authority, relevance, and recency."""

    # Weights for composite score
    WEIGHT_SIMILARITY = 0.40
    WEIGHT_AUTHORITY = 0.30
    WEIGHT_RECENCY = 0.20
    WEIGHT_CITATIONS = 0.10

    # Authority scores by source type
    AUTHORITY_SCORES = {
        'arxiv': 1.0,      # Academic papers highest priority
        'document': 0.9,   # User documents
        'web': 0.5         # General web (default)
    }

    # Domain-based authority boosts
    DOMAIN_AUTHORITY = {
        '.edu': 0.8,
        '.gov': 0.8,
        'arxiv.org': 1.0,
        'wikipedia.org': 0.7,
        'britannica.com': 0.7,
        'scholar.google.com': 0.9,
        'sciencedirect.com': 0.8,
        'springer.com': 0.8,
        'nature.com': 0.9,
        'science.org': 0.9,
        'ieee.org': 0.8,
        'acm.org': 0.8
    }

    def __init__(
        self,
        embedding_model=None,
        recency_decay_days: int = 365
    ):
        """
        Initialize source ranker.

        Args:
            embedding_model: Optional embedding model for semantic similarity
            recency_decay_days: Days for recency score decay (default: 1 year)
        """
        self.embedding_model = embedding_model
        self.recency_decay_days = recency_decay_days

        logging.info(
            f"SourceRanker initialized (recency decay: {recency_decay_days} days)"
        )

    def rank_sources(
        self,
        sources: List[Dict[str, Any]],
        query: str,
        query_embedding: Optional[Any] = None
    ) -> List[RankedSource]:
        """
        Rank sources by composite score.

        Args:
            sources: List of source dictionaries
            query: Original search query
            query_embedding: Optional pre-computed query embedding

        Returns:
            List of RankedSource objects sorted by composite_score (descending)
        """
        if not sources:
            return []

        # Convert to RankedSource objects
        ranked_sources = []

        for source in sources:
            ranked = RankedSource(
                id=source.get('id', ''),
                source_type=source.get('source_type', 'web'),
                title=source.get('title', ''),
                content=source.get('content', ''),
                url=source.get('url'),
                published_date=source.get('published_date'),
                citation_count=source.get('citation_count')
            )

            # Calculate domain from URL
            if ranked.url:
                ranked.domain = self._extract_domain(ranked.url)

            ranked_sources.append(ranked)

        # Calculate individual scores
        self._calculate_similarity_scores(ranked_sources, query, query_embedding)
        self._calculate_authority_scores(ranked_sources)
        self._calculate_recency_scores(ranked_sources)
        self._calculate_citation_scores(ranked_sources)

        # Calculate composite scores
        for source in ranked_sources:
            source.composite_score = (
                self.WEIGHT_SIMILARITY * source.similarity_score +
                self.WEIGHT_AUTHORITY * source.authority_score +
                self.WEIGHT_RECENCY * source.recency_score +
                self.WEIGHT_CITATIONS * source.citation_score
            )

        # Sort by composite score (descending)
        ranked_sources.sort(key=lambda x: x.composite_score, reverse=True)

        logging.info(
            f"Ranked {len(ranked_sources)} sources "
            f"(top score: {ranked_sources[0].composite_score:.3f})"
        )

        return ranked_sources

    def _calculate_similarity_scores(
        self,
        sources: List[RankedSource],
        query: str,
        query_embedding: Optional[Any] = None
    ):
        """Calculate semantic similarity scores."""
        if not self.embedding_model:
            # Fallback: basic keyword matching
            query_lower = query.lower()
            query_words = set(query_lower.split())

            for source in sources:
                # Count query word matches in title and content
                title_lower = source.title.lower()
                content_lower = source.content.lower()

                title_matches = sum(1 for word in query_words if word in title_lower)
                content_matches = sum(1 for word in query_words if word in content_lower)

                # Weighted: title matches count more
                match_score = (title_matches * 2 + content_matches) / (len(query_words) * 3)
                source.similarity_score = min(1.0, match_score)

            logging.debug("Used keyword matching for similarity (no embedding model)")
            return

        # Use embedding model for semantic similarity
        try:
            # Generate query embedding if not provided
            if query_embedding is None:
                query_embedding = self.embedding_model.encode(query, convert_to_tensor=False)

            # Generate embeddings for sources (combine title + snippet of content)
            source_texts = []
            for source in sources:
                # Use title + first 500 chars of content
                text = f"{source.title}. {source.content[:500]}"
                source_texts.append(text)

            source_embeddings = self.embedding_model.encode(
                source_texts,
                convert_to_tensor=False,
                show_progress_bar=False
            )

            # Calculate cosine similarity
            import numpy as np

            for i, source in enumerate(sources):
                similarity = self._cosine_similarity(query_embedding, source_embeddings[i])
                source.similarity_score = max(0.0, min(1.0, similarity))

            logging.debug("Used embedding model for similarity scores")

        except Exception as e:
            logging.error(f"Failed to calculate embedding similarity: {e}")
            # Fallback to keyword matching
            self._calculate_similarity_scores(sources, query, None)

    def _calculate_authority_scores(self, sources: List[RankedSource]):
        """Calculate authority scores based on source type and domain."""
        for source in sources:
            # Base score from source type
            base_score = self.AUTHORITY_SCORES.get(
                source.source_type,
                self.AUTHORITY_SCORES['web']
            )

            # Domain-based boost
            domain_boost = 0.0
            if source.domain:
                # Check for exact domain matches
                for domain_key, score in self.DOMAIN_AUTHORITY.items():
                    if domain_key in source.domain:
                        domain_boost = max(domain_boost, score)
                        break

            # Final authority score is max of base and domain
            source.authority_score = max(base_score, domain_boost)

            logging.debug(
                f"Authority score for {source.title[:50]}: {source.authority_score:.2f} "
                f"(type={source.source_type}, domain={source.domain})"
            )

    def _calculate_recency_scores(self, sources: List[RankedSource]):
        """Calculate recency scores with exponential decay."""
        now = datetime.utcnow()

        for source in sources:
            if not source.published_date:
                # No publication date: default to 0.5
                source.recency_score = 0.5
                continue

            # Calculate days since publication
            days_old = (now - source.published_date).days

            if days_old < 0:
                # Future date (error): treat as very recent
                source.recency_score = 1.0
                continue

            # Exponential decay: score = e^(-days / decay_period)
            import math
            decay_rate = days_old / self.recency_decay_days
            source.recency_score = math.exp(-decay_rate)

            logging.debug(
                f"Recency score for {source.title[:50]}: {source.recency_score:.2f} "
                f"({days_old} days old)"
            )

    def _calculate_citation_scores(self, sources: List[RankedSource]):
        """Calculate citation scores (normalized)."""
        # Find max citations for normalization
        citation_counts = [
            s.citation_count for s in sources
            if s.citation_count is not None and s.citation_count > 0
        ]

        if not citation_counts:
            # No citation data available
            for source in sources:
                source.citation_score = 0.0
            return

        max_citations = max(citation_counts)

        for source in sources:
            if source.citation_count is None or source.citation_count <= 0:
                source.citation_score = 0.0
            else:
                # Logarithmic normalization (citations have diminishing returns)
                import math
                normalized = math.log1p(source.citation_count) / math.log1p(max_citations)
                source.citation_score = normalized

            logging.debug(
                f"Citation score for {source.title[:50]}: {source.citation_score:.2f} "
                f"({source.citation_count} citations)"
            )

    def _cosine_similarity(self, embedding1, embedding2) -> float:
        """Calculate cosine similarity between embeddings."""
        try:
            import numpy as np

            # Normalize
            norm1 = np.linalg.norm(embedding1)
            norm2 = np.linalg.norm(embedding2)

            if norm1 == 0 or norm2 == 0:
                return 0.0

            # Cosine similarity
            similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)

            return float(similarity)

        except Exception as e:
            logging.error(f"Failed to calculate cosine similarity: {e}")
            return 0.0

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.replace('www.', '')
            return domain
        except Exception:
            return ""

    def get_info(self) -> Dict[str, Any]:
        """Get information about the ranker."""
        return {
            'weights': {
                'similarity': self.WEIGHT_SIMILARITY,
                'authority': self.WEIGHT_AUTHORITY,
                'recency': self.WEIGHT_RECENCY,
                'citations': self.WEIGHT_CITATIONS
            },
            'authority_scores': self.AUTHORITY_SCORES,
            'domain_authority': self.DOMAIN_AUTHORITY,
            'recency_decay_days': self.recency_decay_days,
            'embedding_model_available': self.embedding_model is not None
        }
