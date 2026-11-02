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
import os
from typing import List, Dict, Any, Optional, Tuple, Callable
from datetime import datetime
from pathlib import Path
import hashlib

from .database import DatabaseManager, ResearchQuery, Source, Finding as DBFinding, Citation
from .synthesis_engine import SynthesisEngine, Finding
from .citation_manager import CitationManager
from ..utils.deduplicator import Deduplicator, SourceInfo
from ..utils.source_ranker import SourceRanker, RankedSource
from ..utils.query_builder import build_web_query, build_arxiv_queries


class ResearchOrchestrator:
    """Orchestrates the entire research pipeline."""

    # Text kept per source for ranking and for the model (the map step cuts it again to fit)
    MAX_SOURCE_CHARS = 4000

    def __init__(
        self,
        db_path: str,
        web_search_client=None,
        arxiv_client=None,
        llm_client=None,
        citation_manager: Optional[CitationManager] = None,
        embedding_model=None,
        cache_manager=None,
        vector_store=None,
        embedding_service=None
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
                (used for dedup/ranking, unrelated to document RAG)
            cache_manager: CacheManager instance
            vector_store: VectorStore instance (src/services/vector_store.py)
                for 'My Documents' RAG search. None disables it even if
                search_documents=True is requested.
            embedding_service: EmbeddingService instance (src/services/
                embedding_service.py) used to embed the query text for
                document search. Deliberately separate from
                embedding_model above - that one is the (optional, often
                None) model used for dedup/ranking similarity, while this
                one must always match whatever model the documents were
                embedded with at upload time.
        """
        self.db_manager = DatabaseManager(db_path)
        self.web_search_client = web_search_client
        self.arxiv_client = arxiv_client
        self.llm_client = llm_client
        self.embedding_model = embedding_model
        self.cache_manager = cache_manager
        self.vector_store = vector_store
        self.embedding_service = embedding_service

        # Sources scoring below this similarity to the question are left out. Measured with the
        # default embedding model: the sources that answer the question score 0.4-0.5, a
        # dictionary page for one of its words about 0.0.
        self.min_relevance = float(os.getenv('RESEARCH_MIN_RELEVANCE', 0.15))

        # Web results of the current search by source id, to fetch the page text of the kept ones
        self._web_results: Dict[str, Any] = {}

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
        search_documents: bool = False,
        max_sources: int = 20,
        citation_style: str = 'APA',
        progress: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Any]:
        """
        Conduct comprehensive research on a query.

        Pipeline:
        1. Create research query in database
        2. Search sources (web, ArXiv, documents)
        3. Deduplicate sources
        4. Rank sources by authority and relevance, drop the ones unrelated to the question
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
            progress: Called as progress(step, total_steps, message) as each stage starts

        Returns:
            Dictionary with research results, in the shape get_research_query() returns, plus
            `stats` and `warnings` (anything that went wrong without stopping the research)
        """
        start_time = datetime.utcnow()
        warnings: List[str] = []
        errors: List[str] = []
        total_steps = 6

        def report(step: int, message: str):
            if progress:
                try:
                    progress(step, total_steps, message)
                except Exception:
                    logging.debug("progress callback failed", exc_info=True)

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
                citation_style=citation_style.upper(),
                status='processing',
                started_at=start_time
            )
            db_session.add(research_query)
            db_session.commit()
            db_session.refresh(research_query)
            query_id = research_query.id

        try:
            # Step 2: Search sources
            logging.info("Step 1/6: Searching sources")
            report(1, "Searching the web, ArXiv and your documents")
            all_sources = self._search_sources(
                query,
                search_web,
                search_arxiv,
                search_documents,
                max_sources,
                user_id,
                warnings,
                errors
            )

            if not all_sources:
                logging.warning("No sources found")
                if errors:
                    # A search that failed is not "nothing found": say which
                    raise RuntimeError("; ".join(errors))
                message = "No sources found for the query."
                self._update_query_status(query_id, 'completed', message, 0.0, start_time)
                return self._finish(query_id, start_time, warnings, total_found=0, unique=0, used=0)

            # Step 3: Deduplicate
            logging.info(f"Step 2/6: Deduplicating {len(all_sources)} sources")
            report(2, f"Removing duplicates from {len(all_sources)} sources")
            unique_sources = self._deduplicate_sources(all_sources)
            logging.info(f"After deduplication: {len(unique_sources)} unique sources")

            # Step 4: Rank sources
            logging.info(f"Step 3/6: Ranking {len(unique_sources)} sources")
            report(3, f"Ranking {len(unique_sources)} sources")
            ranked_sources = self._rank_sources(unique_sources, query)

            # Sources that have nothing to do with the question (a dictionary page for "main", an
            # arcade chain) were handed to the model like any other and cited as evidence
            relevant = [s for s in ranked_sources if s.similarity_score >= self.min_relevance]
            ignored = len(ranked_sources) - len(relevant)
            if ignored:
                warnings.append(f"Ignored {ignored} source(s) that did not match the question.")
            if not relevant:
                message = "No relevant sources found: everything the searches returned was unrelated to the question."
                self._update_query_status(query_id, 'completed', message, 0.0, start_time)
                return self._finish(query_id, start_time, warnings,
                                    total_found=len(all_sources), unique=len(unique_sources), used=0)
            ranked_sources = relevant

            # Limit to max_sources
            ranked_sources = ranked_sources[:max_sources]
            logging.info(f"Using top {len(ranked_sources)} sources for synthesis")
            self._load_web_pages(ranked_sources)

            # Step 5: Synthesize findings
            logging.info("Step 4/6: Synthesizing findings")
            report(4, f"Reading {len(ranked_sources)} sources and writing findings (the slow step)")
            summary, findings = self._synthesize_findings(query, ranked_sources)
            if self.synthesis_engine.errors:
                warnings.append(
                    f"The language model failed on part of the work: {self.synthesis_engine.errors[0]}"
                )

            # Step 6: Generate citations
            logging.info("Step 5/6: Generating citations")
            report(5, "Formatting citations")
            citations = self._generate_citations(findings, ranked_sources, citation_style)

            # Step 7: Save to database
            logging.info("Step 6/6: Saving results to database")
            report(6, "Saving results")
            self._save_results(
                query_id,
                summary,
                findings,
                ranked_sources,
                citations,
                start_time,
                citation_style
            )

            avg_confidence = sum(f.confidence for f in findings) / len(findings) if findings else 0.0

            logging.info(
                f"Research complete: {len(findings)} findings, "
                f"avg confidence: {avg_confidence:.2f}, "
                f"time: {(datetime.utcnow() - start_time).total_seconds():.1f}s"
            )

            return self._finish(query_id, start_time, warnings, total_found=len(all_sources),
                                unique=len(unique_sources), used=len(ranked_sources))

        except Exception as e:
            logging.error(f"Research failed: {e}", exc_info=True)
            self._update_query_status(query_id, 'failed', None, None, start_time, error=str(e))
            raise

    def _finish(
        self,
        query_id: str,
        start_time: datetime,
        warnings: List[str],
        total_found: int,
        unique: int,
        used: int
    ) -> Dict[str, Any]:
        """
        The result as it is stored, plus this run's `stats` and `warnings`.

        The result used to be built twice, once here and once when loading a saved query, in two
        different shapes (`text`/`sources` against `finding_text`/`num_sources`, `type` against
        `source_type`): the page and the report generator each understood only one, so a saved
        research downloaded with no findings in it.
        """
        result = self.get_research_query(query_id) or {'query_id': query_id}
        result['warnings'] = warnings
        result['stats'] = {
            'total_sources': total_found,
            'unique_sources': unique,
            'used_sources': used,
            'findings': len(result.get('findings', [])),
            'avg_confidence': result.get('avg_confidence', 0.0),
            'processing_time': (datetime.utcnow() - start_time).total_seconds()
        }
        return result

    def _search_sources(
        self,
        query: str,
        search_web: bool,
        search_arxiv: bool,
        search_documents: bool,
        max_sources: int,
        user_id: Optional[str] = None,
        warnings: Optional[List[str]] = None,
        errors: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Search all enabled sources. `errors` gets the searches that failed (also added to `warnings`)."""
        all_sources = []
        warnings = warnings if warnings is not None else []
        errors = errors if errors is not None else []

        # Split the budget between the sources that are really searched. It used to be max_sources // 2
        # for each regardless: with one source ticked only half was ever asked for, and
        # max_sources=1 asked for 0 and always answered "No sources found".
        active = [
            bool(search_web and self.web_search_client),
            bool(search_arxiv and self.arxiv_client),
            bool(search_documents and self.vector_store and self.embedding_service and user_id),
        ]
        shares = max(1, sum(active))
        per_source = max(1, -(-max_sources // shares))  # ceiling

        # Web search
        if search_web and self.web_search_client:
            try:
                logging.info("Searching web sources")
                # The search service answers the same question differently depending on its
                # wording, and sometimes with nothing: the question as typed gave 0 results where
                # its keywords gave 5, and the other way round. Try both, keep what is new.
                web_results = []
                seen_urls = set()
                for web_query in dict.fromkeys([query, build_web_query(query)]):
                    # Page text is fetched later, only for the sources that are kept
                    for result in self.web_search_client.search(
                        web_query,
                        max_results=per_source,
                        extract_content=False,
                        raise_on_error=True
                    ):
                        if result.url and result.url not in seen_urls:
                            seen_urls.add(result.url)
                            web_results.append(result)
                    if len(web_results) >= per_source:
                        break
                web_results = web_results[:per_source * 2]

                if not web_results:
                    warnings.append(
                        "The web search returned no results (it often does when the search service is busy)."
                    )

                for result in web_results:
                    source_id = self._generate_source_id(result.url)
                    self._web_results[source_id] = result
                    all_sources.append({
                        'id': source_id,
                        'source_type': 'web',
                        'title': result.title,
                        'content': (result.snippet or '')[:self.MAX_SOURCE_CHARS],
                        'url': result.url,
                        'relevance_score': result.relevance_score,
                        'published_date': None  # Web results don't have dates
                    })

                logging.info(f"Found {len(web_results)} web sources")

            except Exception as e:
                logging.error(f"Web search failed: {e}")
                warnings.append(str(e))
                errors.append(str(e))

        # ArXiv search
        if search_arxiv and self.arxiv_client:
            try:
                logging.info("Searching ArXiv papers")
                arxiv_results = []
                seen_papers = set()
                # Keywords joined with AND first; the sentence itself only as a last resort. Each
                # broader query only adds what the narrower ones did not find.
                for arxiv_query in build_arxiv_queries(query):
                    for paper in self.arxiv_client.search(
                        arxiv_query,
                        max_results=per_source,
                        extract_text=False,
                        raise_on_error=True
                    ):
                        if paper.arxiv_id not in seen_papers:
                            seen_papers.add(paper.arxiv_id)
                            arxiv_results.append(paper)
                    if len(arxiv_results) >= per_source:
                        break
                arxiv_results = arxiv_results[:per_source]

                for paper in arxiv_results:
                    all_sources.append({
                        'id': paper.arxiv_id,
                        'source_type': 'arxiv',
                        'title': paper.title,
                        'content': ((paper.summary or '') + '\n\n' + (paper.content or ''))[:self.MAX_SOURCE_CHARS],
                        'url': paper.pdf_url,
                        'relevance_score': 0.8,  # Default high relevance for academic papers
                        'published_date': paper.published,
                        'authors': paper.authors,
                        'citation_count': paper.citation_count
                    })

                logging.info(f"Found {len(arxiv_results)} ArXiv papers")

            except Exception as e:
                logging.error(f"ArXiv search failed: {e}")
                warnings.append(str(e))
                errors.append(str(e))

        # Document search (RAG) - searches the user's own uploaded
        # documents (My Documents), scoped by user_id so one user's
        # uploads never surface in another user's research.
        if search_documents:
            if not self.vector_store or not self.embedding_service:
                logging.warning(
                    "Document search requested but vector_store/embedding_service "
                    "not configured on this orchestrator - skipping"
                )
            elif not user_id:
                logging.warning("Document search requested but no user_id provided - skipping")
            else:
                try:
                    logging.info("Searching user documents")
                    query_embedding = self.embedding_service.embed_query(query)
                    doc_results = self.vector_store.search(
                        query_embedding,
                        user_id=user_id,
                        top_k=per_source
                    )

                    for chunk in doc_results:
                        all_sources.append({
                            # document_id + chunk_index keeps chunks from
                            # the same document distinct - dedup/citation
                            # both key off 'id', and different chunks of
                            # one document are legitimately different
                            # evidence, not duplicates.
                            'id': f"doc:{chunk['document_id']}:{chunk['chunk_index']}",
                            'source_type': 'document',
                            'title': chunk['filename'],
                            'content': chunk['chunk_text'],
                            'url': None,
                            'relevance_score': chunk['similarity'],
                            'published_date': None
                        })

                    logging.info(f"Found {len(doc_results)} document chunks")

                except Exception as e:
                    logging.error(f"Document search failed: {e}")
                    warnings.append(f"Searching your documents failed: {e}")
                    errors.append(f"Searching your documents failed: {e}")

        return all_sources

    def _load_web_pages(self, ranked_sources: List[RankedSource]) -> None:
        """Replace a web source's snippet with the page text where the page could be read"""
        pending = [self._web_results[s.id] for s in ranked_sources
                   if s.source_type == 'web' and s.id in self._web_results]
        if not pending or not self.web_search_client:
            return
        try:
            self.web_search_client.fetch_contents(pending)
        except Exception as e:
            logging.warning(f"Could not read web pages: {e}")
            return
        for source in ranked_sources:
            result = self._web_results.get(source.id)
            page = (result.content or '').strip() if result else ''
            if page and len(page) > len(source.content):
                source.content = page[:self.MAX_SOURCE_CHARS]

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
    ) -> List[Tuple[str, str]]:
        """
        One formatted citation per source the findings use, as (source_id, text) pairs sorted as a
        bibliography is. The pairing used to be guessed afterwards by looking for the first 30
        characters of the title inside the text, which lost any citation whose title was shortened.
        """
        source_map = {s.id: s for s in ranked_sources}

        cited_source_ids = []
        for finding in findings:
            for source_id in finding.source_ids:
                if source_id not in cited_source_ids:
                    cited_source_ids.append(source_id)

        style = (citation_style or self.citation_manager.default_style).upper()
        pairs = []
        for source_id in cited_source_ids:
            source = source_map.get(source_id)
            if not source:
                continue
            text = self.citation_manager.generate_citation(
                source_type=source.source_type,
                title=source.title,
                authors=getattr(source, 'authors', None),
                url=source.url,
                published_date=source.published_date,
                style=style,
                arxiv_id=source.id if source.source_type == 'arxiv' else None,
                domain=source.domain
            ).strip()
            if text:
                pairs.append((source_id, text))

        pairs.sort(key=lambda pair: pair[1])
        if style == 'IEEE':
            pairs = [(sid, f"[{i + 1}] {text}") for i, (sid, text) in enumerate(pairs)]
        return pairs

    def _save_results(
        self,
        query_id: str,
        summary: str,
        findings: List[Finding],
        ranked_sources: List[RankedSource],
        citations: List[Tuple[str, str]],
        start_time: datetime,
        citation_style: str = 'APA'
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
            db_source_ids = {}
            for rank, source in enumerate(ranked_sources, start=1):
                db_source = Source(
                    query_id=query_id,
                    source_type=source.source_type,
                    title=source.title,
                    url=source.url,
                    content=source.content,
                    content_hash=Deduplicator.calculate_content_hash(source.content),
                    relevance_score=source.similarity_score,
                    retrieval_rank=rank
                )
                db_session.add(db_source)
                db_session.flush()
                db_source_ids[source.id] = db_source.id

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

            # Save citations: each one belongs to the stored source row it was made from (they
            # pointed at the search engine's id, which is not a key of the sources table), in the
            # style that was asked for (it was always saved as the default, APA)
            for number, (source_id, citation_text) in enumerate(citations, start=1):
                if source_id not in db_source_ids:
                    continue
                db_session.add(Citation(
                    query_id=query_id,
                    source_id=db_source_ids[source_id],
                    citation_text=citation_text,
                    citation_style=(citation_style or 'APA').upper(),
                    formatted_citation=citation_text,
                    citation_number=number
                ))

            db_session.commit()
            logging.info(f"Saved research results for query {query_id}")

    def _update_query_status(
        self,
        query_id: str,
        status: str,
        summary: Optional[str],
        confidence: Optional[float],
        start_time: datetime,
        error: Optional[str] = None
    ):
        """Update query status in database."""
        with self.db_manager.get_session() as db_session:
            query = db_session.query(ResearchQuery).filter_by(id=query_id).first()
            if query:
                query.status = status
                query.error_message = error
                query.summary = summary
                query.confidence_score = confidence
                query.completed_at = datetime.utcnow()
                query.processing_time_seconds = (datetime.utcnow() - start_time).total_seconds()
                db_session.commit()

    def _generate_source_id(self, url: str) -> str:
        """Generate unique source ID from URL."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def get_research_query(self, query_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Retrieve research query results from database.

        With `user_id`, only that user's queries are found: another user's id answers None, the
        same as an id that does not exist.
        """
        with self.db_manager.get_session() as db_session:
            query = db_session.query(ResearchQuery).filter_by(id=query_id).first()
            if not query or (user_id is not None and query.user_id != user_id):
                return None

            # Get findings, sources and citations
            findings = db_session.query(DBFinding).filter_by(query_id=query_id).all()
            sources = db_session.query(Source).filter_by(query_id=query_id).all()
            citations = (
                db_session.query(Citation).filter_by(query_id=query_id)
                .order_by(Citation.citation_number).all()
            )
            confidence = query.confidence_score if query.confidence_score is not None else 0.0

            return {
                'query_id': query.id,
                'query': query.query_text,
                'status': query.status,
                'error_message': query.error_message,
                'summary': query.summary,
                'confidence': confidence,
                'avg_confidence': confidence,
                'findings': [
                    {
                        'finding_text': f.finding_text,
                        'finding_type': f.finding_type,
                        'confidence': f.confidence,
                        'source_ids': f.source_ids if f.source_ids else [],
                        'num_sources': len(f.source_ids) if f.source_ids else 0,
                        # the names the report generator reads
                        'text': f.finding_text,
                        'type': f.finding_type,
                        'sources': len(f.source_ids) if f.source_ids else 0
                    }
                    for f in findings
                ],
                'sources': [
                    {
                        'title': s.title,
                        'url': s.url,
                        'source_type': s.source_type,
                        'type': s.source_type,
                        'rank': s.retrieval_rank,
                        'relevance': s.relevance_score
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

    def count_user_queries(self, user_id: str) -> int:
        """How many research queries a user has (the page count is not the total)"""
        with self.db_manager.get_session() as db_session:
            return db_session.query(ResearchQuery).filter_by(user_id=user_id).count()

    def fail_interrupted_queries(self) -> int:
        """
        Mark queries left 'processing' as failed. A server that stopped mid-research never got to
        update them, so they stayed "processing" in the list for ever.
        """
        with self.db_manager.get_session() as db_session:
            stuck = db_session.query(ResearchQuery).filter_by(status='processing').all()
            for q in stuck:
                q.status = 'failed'
                q.error_message = 'Interrupted: the server stopped before this research finished.'
                q.completed_at = datetime.utcnow()
            db_session.commit()
            return len(stuck)
