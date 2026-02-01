"""
ArXiv Client for Research Assistant.

Fetches academic papers from ArXiv with PDF download and text extraction.
"""

import logging
import hashlib
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

try:
    import arxiv
    ARXIV_AVAILABLE = True
except ImportError:
    ARXIV_AVAILABLE = False
    logging.warning("arxiv package not installed. ArXiv search will not work.")

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logging.warning("PyMuPDF not installed. PDF extraction will not work.")


@dataclass
class ArXivPaper:
    """ArXiv paper metadata and content."""
    arxiv_id: str
    title: str
    authors: List[str]
    summary: str
    published: datetime
    updated: datetime
    pdf_url: str
    categories: List[str]
    content: Optional[str] = None
    pdf_path: Optional[Path] = None


class ArXivClient:
    """Client for searching and downloading ArXiv papers."""

    def __init__(
        self,
        cache_dir: str = './data/papers',
        max_results_per_query: int = 10
    ):
        """
        Initialize ArXiv client.

        Args:
            cache_dir: Directory to cache downloaded PDFs
            max_results_per_query: Maximum results per search
        """
        if not ARXIV_AVAILABLE:
            raise ValueError("ArXiv client requires 'arxiv' package")

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_results_per_query = max_results_per_query

        logging.info(f"ArXivClient initialized with cache dir: {self.cache_dir}")

    def search(
        self,
        query: str,
        max_results: int = 10,
        sort_by = None,  # arxiv.SortCriterion, defaults to Relevance
        extract_text: bool = True
    ) -> List[ArXivPaper]:
        """
        Search ArXiv for papers matching query.

        Args:
            query: Search query
            max_results: Maximum number of results
            sort_by: Sort criterion (Relevance, LastUpdatedDate, SubmittedDate)
            extract_text: Whether to download PDFs and extract text

        Returns:
            List of ArXivPaper objects
        """
        papers = []

        # Set default sort criterion if not provided
        if sort_by is None:
            sort_by = arxiv.SortCriterion.Relevance

        try:
            search = arxiv.Search(
                query=query,
                max_results=max_results,
                sort_by=sort_by
            )

            for result in search.results():
                paper = ArXivPaper(
                    arxiv_id=self._extract_arxiv_id(result.entry_id),
                    title=result.title,
                    authors=[author.name for author in result.authors],
                    summary=result.summary,
                    published=result.published,
                    updated=result.updated,
                    pdf_url=result.pdf_url,
                    categories=result.categories
                )
                papers.append(paper)

            logging.info(f"ArXiv search returned {len(papers)} papers for: {query[:50]}...")

            # Extract text from PDFs if requested
            if extract_text and PYMUPDF_AVAILABLE:
                papers = self._extract_text_from_papers(papers)

        except Exception as e:
            logging.error(f"ArXiv search failed: {e}")

        return papers

    def download_paper(self, paper: ArXivPaper, force: bool = False) -> Optional[Path]:
        """
        Download PDF for paper.

        Args:
            paper: ArXivPaper object
            force: Force re-download even if cached

        Returns:
            Path to downloaded PDF, or None if failed
        """
        pdf_path = self.cache_dir / f"{paper.arxiv_id}.pdf"

        # Check if already cached
        if pdf_path.exists() and not force:
            logging.info(f"PDF already cached: {pdf_path}")
            paper.pdf_path = pdf_path
            return pdf_path

        try:
            # Download using arxiv library
            search = arxiv.Search(id_list=[paper.arxiv_id])
            result = next(search.results())
            result.download_pdf(filename=str(pdf_path))

            logging.info(f"Downloaded PDF: {pdf_path}")
            paper.pdf_path = pdf_path
            return pdf_path

        except Exception as e:
            logging.error(f"Failed to download PDF for {paper.arxiv_id}: {e}")
            return None

    def extract_text(self, pdf_path: Path) -> str:
        """
        Extract text from PDF using PyMuPDF.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Extracted text content
        """
        if not PYMUPDF_AVAILABLE:
            raise ValueError("PDF extraction requires PyMuPDF (fitz)")

        try:
            doc = fitz.open(str(pdf_path))
            text_parts = []

            for page_num, page in enumerate(doc):
                text = page.get_text()
                if text.strip():
                    text_parts.append(f"--- Page {page_num + 1} ---\n{text}")

            doc.close()

            full_text = '\n\n'.join(text_parts)
            logging.info(f"Extracted {len(full_text)} characters from {pdf_path}")
            return full_text

        except Exception as e:
            logging.error(f"Failed to extract text from {pdf_path}: {e}")
            return ""

    def _extract_text_from_papers(self, papers: List[ArXivPaper]) -> List[ArXivPaper]:
        """
        Download PDFs and extract text for papers.

        Args:
            papers: List of ArXivPaper objects

        Returns:
            Updated list with content extracted
        """
        for paper in papers:
            try:
                # Download PDF
                pdf_path = self.download_paper(paper)

                if pdf_path and pdf_path.exists():
                    # Extract text
                    text = self.extract_text(pdf_path)
                    paper.content = text if text else paper.summary
                else:
                    # Fallback to summary
                    paper.content = paper.summary

            except Exception as e:
                logging.warning(f"Failed to extract text for {paper.arxiv_id}: {e}")
                paper.content = paper.summary

        return papers

    def _extract_arxiv_id(self, entry_id: str) -> str:
        """
        Extract ArXiv ID from entry ID URL.

        Args:
            entry_id: Entry ID (e.g., 'http://arxiv.org/abs/1234.5678v1')

        Returns:
            ArXiv ID (e.g., '1234.5678')
        """
        # Extract ID from URL
        parts = entry_id.split('/')
        arxiv_id = parts[-1]

        # Remove version suffix (e.g., 'v1')
        if 'v' in arxiv_id:
            arxiv_id = arxiv_id.split('v')[0]

        return arxiv_id

    def get_paper_by_id(self, arxiv_id: str, extract_text: bool = True) -> Optional[ArXivPaper]:
        """
        Get a specific paper by ArXiv ID.

        Args:
            arxiv_id: ArXiv ID (e.g., '1234.5678')
            extract_text: Whether to extract PDF text

        Returns:
            ArXivPaper object or None if not found
        """
        try:
            search = arxiv.Search(id_list=[arxiv_id])
            result = next(search.results())

            paper = ArXivPaper(
                arxiv_id=self._extract_arxiv_id(result.entry_id),
                title=result.title,
                authors=[author.name for author in result.authors],
                summary=result.summary,
                published=result.published,
                updated=result.updated,
                pdf_url=result.pdf_url,
                categories=result.categories
            )

            if extract_text and PYMUPDF_AVAILABLE:
                pdf_path = self.download_paper(paper)
                if pdf_path:
                    paper.content = self.extract_text(pdf_path)
                else:
                    paper.content = paper.summary

            return paper

        except Exception as e:
            logging.error(f"Failed to get paper {arxiv_id}: {e}")
            return None

    def get_info(self) -> Dict[str, Any]:
        """Get information about the ArXiv client."""
        return {
            'available': ARXIV_AVAILABLE,
            'pymupdf_available': PYMUPDF_AVAILABLE,
            'cache_dir': str(self.cache_dir),
            'cached_papers': len(list(self.cache_dir.glob('*.pdf'))) if self.cache_dir.exists() else 0,
            'max_results_per_query': self.max_results_per_query
        }
