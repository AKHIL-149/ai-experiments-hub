"""
Research Orchestrator for Research Assistant.

Main coordinator integrating all research components:
- RAG engine (documents)
- Web search
- ArXiv papers
- Deduplication
- Source ranking
- Synthesis
- Citation management
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path
import hashlib

from .database import DatabaseManager, ResearchQuery, Source, Finding as DBFinding, Citation
from .synthesis_engine import SynthesisEngine, Finding
from .citation_manager import CitationManager
from ..utils.deduplicator import Deduplicator, SourceInfo
from ..utils.source_ranker import SourceRanker, RankedSource


class ResearchOrchestrator:
    """Orchestrates the entire research pipeline."""

    def __init__(
        self,
        db_path: str,
        web_search_client=None,
        arxiv_client=None,
        llm_client=None,
        citation_manager: Optional[CitationManager] = None,
        embedding_model=None,
        cache_manager=None
    ):
        """
        Initialize research orchestrator.

        Args:
            db_path: Path to SQLite database
            web_search_client: WebSearchClient instance
            arxiv_client: ArXivClient instance
            llm_client: LLMClient instance for synthesis
            citation_manager: CitationManager instance
            embedding_model: Embedding model for semantic similarity
            cache_manager: CacheManager instance
        """
        self.db_manager = DatabaseManager(db_path)
        self.web_search_client = web_search_client
        self.arxiv_client = arxiv_client
        self.llm_client = llm_client
        self.embedding_model = embedding_model
        self.cache_manager = cache_manager

        # Initialize sub-components
        self.citation_manager = citation_manager or CitationManager()

        self.deduplicator = Deduplicator(
            exact_match=True,
            semantic_threshold=0.95,
            embedding_model=embedding_model
        )

        self.source_ranker = SourceRanker(
            embedding_model=embedding_model,
            recency_decay_days=365
        )

        self.synthesis_engine = SynthesisEngine(
            llm_client=llm_client,
            min_sources=2,  # Lowered from 3 to allow more findings
            confidence_threshold=0.5,  # Lowered from 0.8 for small models
            detect_contradictions=True
        )

        logging.info("ResearchOrchestrator initialized")

    def conduct_research(
        self,
        user_id: str,
        query: str,
        search_web: bool = True,
        search_arxiv: bool = True,
        search_documents: bool = False,  # RAG not implemented in Phase 3
        max_sources: int = 20,
        citation_style: str = 'APA'
    ) -> Dict[str, Any]:
        """
        Conduct comprehensive research on a query.

        Pipeline:
        1. Create research query in database
        2. Search sources (web, ArXiv, documents)
        3. Deduplicate sources
        4. Rank sources by authority and relevance
        5. Synthesize findings
        6. Generate citations
        7. Save results to database

        Args:
            user_id: User ID
            query: Research query
            search_web: Search web sources
            search_arxiv: Search ArXiv papers
            search_documents: Search user documents (RAG)
            max_sources: Maximum sources to use
            citation_style: Citation style (APA, MLA, Chicago, IEEE)

        Returns:
            Dictionary with research results
        """
        start_time = datetime.utcnow()

        logging.info(f"Starting research for query: '{query}'")

        # Step 1: Create research query in database
        with self.db_manager.get_session() as db_session:
            research_query = ResearchQuery(
                user_id=user_id,
                query_text=query,
                search_web=search_web,
                search_arxiv=search_arxiv,
                search_documents=search_documents,
                max_sources=max_sources,
                status='processing'
            )
            db_session.add(research_query)
            db_session.commit()
            db_session.refresh(research_query)
            query_id = research_query.id

        try:
            # Step 2: Search sources
            logging.info("Step 1/6: Searching sources")
            all_sources = self._search_sources(
                query,
                search_web,
                search_arxiv,
                search_documents,
                max_sources
            )

            if not all_sources:
                logging.warning("No sources found")
                self._update_query_status(query_id, 'completed', "No sources found for the query.", 0.0, start_time)
                return {
                    'query_id': query_id,
                    'query': query,
                    'summary': "No sources found for the query.",
                    'findings': [],
                    'sources': [],
                    'citations': []
                }

            # Step 3: Deduplicate
            logging.info(f"Step 2/6: Deduplicating {len(all_sources)} sources")
            unique_sources = self._deduplicate_sources(all_sources)
            logging.info(f"After deduplication: {len(unique_sources)} unique sources")

            # Step 4: Rank sources
            logging.info(f"Step 3/6: Ranking {len(unique_sources)} sources")
            ranked_sources = self._rank_sources(unique_sources, query)

            # Limit to max_sources
            ranked_sources = ranked_sources[:max_sources]
            logging.info(f"Using top {len(ranked_sources)} sources for synthesis")

            # Step 5: Synthesize findings
            logging.info("Step 4/6: Synthesizing findings")
            summary, findings = self._synthesize_findings(query, ranked_sources)

            # Step 6: Generate citations
            logging.info("Step 5/6: Generating citations")
            citations = self._generate_citations(findings, ranked_sources, citation_style)

            # Step 7: Save to database
            logging.info("Step 6/6: Saving results to database")
            self._save_results(
                query_id,
                summary,
                findings,
                ranked_sources,
                citations,
                start_time
            )

            # Calculate overall confidence (average of finding confidences)
            avg_confidence = sum(f.confidence for f in findings) / len(findings) if findings else 0.0

            logging.info(
                f"Research complete: {len(findings)} findings, "
                f"avg confidence: {avg_confidence:.2f}, "
                f"time: {(datetime.utcnow() - start_time).total_seconds():.1f}s"
            )

            return {
                'query_id': query_id,
                'query': query,
                'summary': summary,
                'findings': [
                    {
                        'text': f.finding_text,
                        'type': f.finding_type,
                        'confidence': f.confidence,
                        'sources': len(f.source_ids)
                    }
                    for f in findings
                ],
                'sources': [
                    {
                        'title': s.title,
                        'url': s.url,
                        'type': s.source_type,
                        'composite_score': s.composite_score
                    }
                    for s in ranked_sources[:10]  # Top 10 for display
                ],
                'citations': citations,
                'stats': {
                    'total_sources': len(all_sources),
                    'unique_sources': len(unique_sources),
                    'used_sources': len(ranked_sources),
                    'findings': len(findings),
                    'avg_confidence': avg_confidence,
                    'processing_time': (datetime.utcnow() - start_time).total_seconds()
                }
            }

        except Exception as e:
            logging.error(f"Research failed: {e}", exc_info=True)
            self._update_query_status(query_id, 'failed', None, None, start_time)
            raise

    def _search_sources(
        self,
        query: str,
        search_web: bool,
        search_arxiv: bool,
        search_documents: bool,
        max_sources: int
    ) -> List[Dict[str, Any]]:
        """Search all enabled sources."""
        all_sources = []

        # Web search
        if search_web and self.web_search_client:
            try:
                logging.info("Searching web sources")
                web_results = self.web_search_client.search(
                    query,
                    max_results=max_sources // 2  # Allocate half to web
                )

                for result in web_results:
                    all_sources.append({
                        'id': self._generate_source_id(result.url),
                        'source_type': 'web',
                        'title': result.title,
                        'content': result.snippet,
                        'url': result.url,
                        'relevance_score': result.relevance_score,
                        'published_date': None  # Web results don't have dates
                    })

                logging.info(f"Found {len(web_results)} web sources")

            except Exception as e:
                logging.error(f"Web search failed: {e}")

        # ArXiv search
        if search_arxiv and self.arxiv_client:
            try:
                logging.info("Searching ArXiv papers")
                arxiv_results = self.arxiv_client.search(
                    query,
                    max_results=max_sources // 2,  # Allocate half to ArXiv
                    extract_text=True
                )

                for paper in arxiv_results:
                    all_sources.append({
                        'id': paper.arxiv_id,
                        'source_type': 'arxiv',
                        'title': paper.title,
                        'content': paper.summary + '\n\n' + (paper.full_text or '')[:2000],
                        'url': paper.pdf_url,
                        'relevance_score': 0.8,  # Default high relevance for academic papers
                        'published_date': paper.published,
                        'authors': paper.authors,
                        'citation_count': paper.citation_count
                    })

                logging.info(f"Found {len(arxiv_results)} ArXiv papers")

            except Exception as e:
                logging.error(f"ArXiv search failed: {e}")

        # Document search (RAG) - not implemented in Phase 3
        if search_documents:
            logging.warning("Document search not implemented in Phase 3")

        return all_sources

    def _deduplicate_sources(self, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Deduplicate sources using exact and semantic matching."""
        # Convert to SourceInfo format
        source_infos = []
        for source in sources:
            content_hash = Deduplicator.calculate_content_hash(source['content'])
            source_infos.append(SourceInfo(
                id=source['id'],
                content=source['content'],
                content_hash=content_hash,
                source_type=source['source_type'],
                title=source['title'],
                url=source.get('url')
            ))

        # Deduplicate
        unique_source_infos = self.deduplicator.deduplicate(source_infos)

        # Convert back to dict format
        unique_ids = {s.id for s in unique_source_infos}
        unique_sources = [s for s in sources if s['id'] in unique_ids]

        return unique_sources

    def _rank_sources(
        self,
        sources: List[Dict[str, Any]],
        query: str
    ) -> List[RankedSource]:
        """Rank sources by composite score."""
        ranked = self.source_ranker.rank_sources(sources, query)
        return ranked

    def _synthesize_findings(
        self,
        query: str,
        ranked_sources: List[RankedSource]
    ) -> Tuple[str, List[Finding]]:
        """Synthesize findings from ranked sources."""
        # Convert RankedSource to dict format for SynthesisEngine
        source_dicts = []
        for source in ranked_sources:
            source_dicts.append({
                'id': source.id,
                'source_type': source.source_type,
                'title': source.title,
                'content': source.content,
                'url': source.url,
                'composite_score': source.composite_score
            })

        summary, findings = self.synthesis_engine.synthesize(
            query,
            source_dicts,
            max_findings=10
        )

        return summary, findings

    def _generate_citations(
        self,
        findings: List[Finding],
        ranked_sources: List[RankedSource],
        citation_style: str
    ) -> List[str]:
        """Generate citations for findings."""
        citations = []

        # Build source map
        source_map = {s.id: s for s in ranked_sources}

        # Generate citations for each unique source used
        cited_source_ids = set()
        for finding in findings:
            cited_source_ids.update(finding.source_ids)

        citation_data = []
        for source_id in cited_source_ids:
            source = source_map.get(source_id)
            if not source:
                continue

            citation_data.append({
                'source_type': source.source_type,
                'title': source.title,
                'url': source.url,
                'published_date': source.published_date,
                'authors': getattr(source, 'authors', None),
                'arxiv_id': source.id if source.source_type == 'arxiv' else None,
                'domain': source.domain
            })

        # Generate bibliography
        bibliography = self.citation_manager.generate_bibliography(
            citation_data,
            style=citation_style
        )

        citations = bibliography.split('\n\n') if '\n\n' in bibliography else bibliography.split('\n')
        return [c.strip() for c in citations if c.strip()]

    def _save_results(
        self,
        query_id: str,
        summary: str,
        findings: List[Finding],
        ranked_sources: List[RankedSource],
        citations: List[str],
        start_time: datetime
    ):
        """Save research results to database."""
        with self.db_manager.get_session() as db_session:
            # Update research query
            query = db_session.query(ResearchQuery).filter_by(id=query_id).first()
            if not query:
                return

            query.summary = summary
            query.confidence_score = sum(f.confidence for f in findings) / len(findings) if findings else 0.0
            query.status = 'completed'
            query.completed_at = datetime.utcnow()
            query.processing_time_seconds = (datetime.utcnow() - start_time).total_seconds()

            # Save sources
            for source in ranked_sources:
                db_source = Source(
                    query_id=query_id,
                    source_type=source.source_type,
                    title=source.title,
                    url=source.url,
                    content=source.content,
                    content_hash=Deduplicator.calculate_content_hash(source.content),
                    relevance_score=source.similarity_score,
                    retrieval_rank=ranked_sources.index(source) + 1
                )
                db_session.add(db_source)

            # Save findings
            for finding in findings:
                db_finding = DBFinding(
                    query_id=query_id,
                    finding_text=finding.finding_text,
                    finding_type=finding.finding_type,
                    confidence=finding.confidence,
                    source_ids=finding.source_ids
                )
                db_session.add(db_finding)

            # Save citations
            source_map = {s.id: s for s in ranked_sources}
            for citation_text in citations:
                # Try to extract source ID from citation (simple heuristic)
                # In production, you'd have better citation-to-source mapping
                for source_id, source in source_map.items():
                    if source.title[:30] in citation_text:
                        db_citation = Citation(
                            query_id=query_id,
                            source_id=source_id,
                            citation_text=citation_text,
                            citation_style=self.citation_manager.default_style,
                            formatted_citation=citation_text
                        )
                        db_session.add(db_citation)
                        break

            db_session.commit()
            logging.info(f"Saved research results for query {query_id}")

    def _update_query_status(
        self,
        query_id: str,
        status: str,
        summary: Optional[str],
        confidence: Optional[float],
        start_time: datetime
    ):
        """Update query status in database."""
        with self.db_manager.get_session() as db_session:
            query = db_session.query(ResearchQuery).filter_by(id=query_id).first()
            if query:
                query.status = status
                query.summary = summary
                query.confidence_score = confidence
                query.completed_at = datetime.utcnow()
                query.processing_time_seconds = (datetime.utcnow() - start_time).total_seconds()
                db_session.commit()

    def _generate_source_id(self, url: str) -> str:
        """Generate unique source ID from URL."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def get_research_query(self, query_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve research query results from database."""
        with self.db_manager.get_session() as db_session:
            query = db_session.query(ResearchQuery).filter_by(id=query_id).first()
            if not query:
                return None

            # Get findings
            findings = db_session.query(DBFinding).filter_by(query_id=query_id).all()

            # Get sources
            sources = db_session.query(Source).filter_by(query_id=query_id).all()

            # Get citations
            citations = db_session.query(Citation).filter_by(query_id=query_id).all()

            return {
                'query_id': query.id,
                'query': query.query_text,
                'status': query.status,
                'summary': query.summary,
                'confidence': query.confidence_score if query.confidence_score is not None else 0.0,
                'avg_confidence': query.confidence_score if query.confidence_score is not None else 0.0,
                'findings': [
                    {
                        'finding_text': f.finding_text,
                        'finding_type': f.finding_type,
                        'confidence': f.confidence,
                        'source_ids': f.source_ids if f.source_ids else [],
                        'num_sources': len(f.source_ids) if f.source_ids else 0
                    }
                    for f in findings
                ],
                'sources': [
                    {
                        'title': s.title,
                        'url': s.url,
                        'source_type': s.source_type,
                        'rank': s.retrieval_rank
                    }
                    for s in sorted(sources, key=lambda x: x.retrieval_rank)
                ],
                'references': '\n'.join([c.formatted_citation for c in citations]),
                'citations': [c.formatted_citation for c in citations],
                'created_at': query.created_at,
                'completed_at': query.completed_at,
                'processing_time': query.processing_time_seconds
            }

    def list_user_queries(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """List all research queries for a user."""
        with self.db_manager.get_session() as db_session:
            queries = (
                db_session.query(ResearchQuery)
                .filter_by(user_id=user_id)
                .order_by(ResearchQuery.created_at.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )

            return [
                {
                    'query_id': q.id,
                    'query': q.query_text,
                    'status': q.status,
                    'confidence': q.confidence_score,
                    'created_at': q.created_at,
                    'completed_at': q.completed_at
                }
                for q in queries
            ]
