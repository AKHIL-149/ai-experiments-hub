"""
Citation Manager for Research Assistant.

Generates formatted citations in multiple styles: APA, MLA, Chicago, IEEE.
"""

import logging
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class CitationStyle(Enum):
    """Supported citation styles."""
    APA = "APA"
    MLA = "MLA"
    CHICAGO = "Chicago"
    IEEE = "IEEE"


class CitationManager:
    """Manages citation formatting and bibliography generation."""

    def __init__(self, default_style: str = 'APA'):
        """
        Initialize citation manager.

        Args:
            default_style: Default citation style (APA, MLA, Chicago, IEEE)
        """
        self.default_style = default_style.upper()
        if self.default_style not in [s.value for s in CitationStyle]:
            raise ValueError(f"Unsupported citation style: {default_style}")

        logging.info(f"CitationManager initialized with style: {self.default_style}")

    def generate_citation(
        self,
        source_type: str,
        title: str,
        authors: Optional[List[str]] = None,
        url: Optional[str] = None,
        published_date: Optional[datetime] = None,
        style: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Generate a formatted citation.

        Args:
            source_type: Type of source ('web', 'arxiv', 'document')
            title: Source title
            authors: List of author names
            url: Source URL
            published_date: Publication date
            style: Citation style (overrides default)
            **kwargs: Additional metadata

        Returns:
            Formatted citation string
        """
        citation_style = style.upper() if style else self.default_style

        if source_type == 'arxiv':
            return self._cite_arxiv(title, authors, url, published_date, citation_style, **kwargs)
        elif source_type == 'web':
            return self._cite_web(title, authors, url, published_date, citation_style, **kwargs)
        elif source_type == 'document':
            return self._cite_document(title, authors, published_date, citation_style, **kwargs)
        else:
            return self._cite_generic(title, authors, url, published_date, citation_style)

    def _cite_arxiv(
        self,
        title: str,
        authors: Optional[List[str]],
        url: Optional[str],
        published_date: Optional[datetime],
        style: str,
        **kwargs
    ) -> str:
        """Generate citation for ArXiv paper."""
        arxiv_id = kwargs.get('arxiv_id', self._extract_arxiv_id_from_url(url))

        if style == 'APA':
            return self._cite_arxiv_apa(title, authors, arxiv_id, published_date)
        elif style == 'MLA':
            return self._cite_arxiv_mla(title, authors, arxiv_id, published_date)
        elif style == 'CHICAGO':
            return self._cite_arxiv_chicago(title, authors, arxiv_id, published_date)
        elif style == 'IEEE':
            return self._cite_arxiv_ieee(title, authors, arxiv_id, published_date)
        else:
            return self._cite_arxiv_apa(title, authors, arxiv_id, published_date)

    def _cite_arxiv_apa(
        self,
        title: str,
        authors: Optional[List[str]],
        arxiv_id: str,
        published_date: Optional[datetime]
    ) -> str:
        """
        APA format for ArXiv:
        Author, A. A., & Author, B. B. (Year). Title. arXiv preprint arXiv:1234.5678.
        """
        author_str = self._format_authors_apa(authors) if authors else "Unknown Author"
        year = published_date.year if published_date else datetime.now().year

        return f"{author_str} ({year}). {title}. arXiv preprint arXiv:{arxiv_id}."

    def _cite_arxiv_mla(
        self,
        title: str,
        authors: Optional[List[str]],
        arxiv_id: str,
        published_date: Optional[datetime]
    ) -> str:
        """
        MLA format for ArXiv:
        Author, First. "Title." arXiv preprint arXiv:1234.5678 (Year).
        """
        author_str = self._format_authors_mla(authors) if authors else "Unknown Author"
        year = published_date.year if published_date else datetime.now().year

        return f'{author_str}. "{title}." arXiv preprint arXiv:{arxiv_id} ({year}).'

    def _cite_arxiv_chicago(
        self,
        title: str,
        authors: Optional[List[str]],
        arxiv_id: str,
        published_date: Optional[datetime]
    ) -> str:
        """
        Chicago format for ArXiv:
        Author, First Last. "Title." arXiv preprint arXiv:1234.5678 (Year).
        """
        author_str = self._format_authors_chicago(authors) if authors else "Unknown Author"
        year = published_date.year if published_date else datetime.now().year

        return f'{author_str}. "{title}." arXiv preprint arXiv:{arxiv_id} ({year}).'

    def _cite_arxiv_ieee(
        self,
        title: str,
        authors: Optional[List[str]],
        arxiv_id: str,
        published_date: Optional[datetime]
    ) -> str:
        """
        IEEE format for ArXiv:
        [1] F. Author and S. Author, "Title," arXiv:1234.5678, Year.
        """
        author_str = self._format_authors_ieee(authors) if authors else "Unknown Author"
        year = published_date.year if published_date else datetime.now().year

        return f'{author_str}, "{title}," arXiv:{arxiv_id}, {year}.'

    def _cite_web(
        self,
        title: str,
        authors: Optional[List[str]],
        url: Optional[str],
        published_date: Optional[datetime],
        style: str,
        **kwargs
    ) -> str:
        """Generate citation for web source."""
        domain = kwargs.get('domain', self._extract_domain(url))
        access_date = kwargs.get('access_date', datetime.now())

        if style == 'APA':
            return self._cite_web_apa(title, authors, url, published_date, domain, access_date)
        elif style == 'MLA':
            return self._cite_web_mla(title, authors, url, published_date, domain, access_date)
        elif style == 'CHICAGO':
            return self._cite_web_chicago(title, authors, url, published_date, access_date)
        elif style == 'IEEE':
            return self._cite_web_ieee(title, authors, url, access_date)
        else:
            return self._cite_web_apa(title, authors, url, published_date, domain, access_date)

    def _cite_web_apa(
        self,
        title: str,
        authors: Optional[List[str]],
        url: Optional[str],
        published_date: Optional[datetime],
        domain: str,
        access_date: datetime
    ) -> str:
        """
        APA format for web:
        Author, A. A. (Year, Month Day). Title. Site Name. URL
        """
        author_str = self._format_authors_apa(authors) if authors else domain
        date_str = published_date.strftime("%Y, %B %d") if published_date else "n.d."

        return f"{author_str} ({date_str}). {title}. {domain}. {url}"

    def _cite_web_mla(
        self,
        title: str,
        authors: Optional[List[str]],
        url: Optional[str],
        published_date: Optional[datetime],
        domain: str,
        access_date: datetime
    ) -> str:
        """
        MLA format for web:
        Author. "Title." Website, Day Month Year, URL. Accessed Day Month Year.
        """
        author_str = self._format_authors_mla(authors) if authors else domain
        pub_date_str = published_date.strftime("%d %B %Y") if published_date else "n.d."
        access_date_str = access_date.strftime("%d %B %Y")

        return f'{author_str}. "{title}." {domain}, {pub_date_str}, {url}. Accessed {access_date_str}.'

    def _cite_web_chicago(
        self,
        title: str,
        authors: Optional[List[str]],
        url: Optional[str],
        published_date: Optional[datetime],
        access_date: datetime
    ) -> str:
        """
        Chicago format for web:
        Author. "Title." Website. Published Date. URL.
        """
        author_str = self._format_authors_chicago(authors) if authors else ""
        pub_date_str = published_date.strftime("%B %d, %Y") if published_date else ""

        if author_str:
            return f'{author_str}. "{title}." {pub_date_str}. {url}.'
        else:
            return f'"{title}." {pub_date_str}. {url}.'

    def _cite_web_ieee(
        self,
        title: str,
        authors: Optional[List[str]],
        url: Optional[str],
        access_date: datetime
    ) -> str:
        """
        IEEE format for web:
        [1] F. Author, "Title," URL (accessed Mon. Day, Year).
        """
        author_str = self._format_authors_ieee(authors) if authors else ""
        access_date_str = access_date.strftime("%b. %d, %Y")

        if author_str:
            return f'{author_str}, "{title}," {url} (accessed {access_date_str}).'
        else:
            return f'"{title}," {url} (accessed {access_date_str}).'

    def _cite_document(
        self,
        title: str,
        authors: Optional[List[str]],
        published_date: Optional[datetime],
        style: str,
        **kwargs
    ) -> str:
        """Generate citation for uploaded document."""
        filename = kwargs.get('filename', title)

        author_str = self._format_authors_generic(authors, style) if authors else "Unknown Author"
        year = published_date.year if published_date else "n.d."

        return f"{author_str} ({year}). {title}. [Document: {filename}]"

    def _cite_generic(
        self,
        title: str,
        authors: Optional[List[str]],
        url: Optional[str],
        published_date: Optional[datetime],
        style: str
    ) -> str:
        """Generic citation format."""
        author_str = self._format_authors_generic(authors, style) if authors else "Unknown Author"
        year = published_date.year if published_date else "n.d."
        url_str = f" {url}" if url else ""

        return f"{author_str} ({year}). {title}.{url_str}"

    # Author formatting helpers

    def _format_authors_apa(self, authors: List[str]) -> str:
        """Format authors in APA style: Last, F., & Last, F."""
        if not authors:
            return ""

        formatted = []
        for author in authors[:7]:  # APA limits to 7 authors
            parts = author.split()
            if len(parts) >= 2:
                last = parts[-1]
                initials = '. '.join([p[0] for p in parts[:-1]]) + '.'
                formatted.append(f"{last}, {initials}")
            else:
                formatted.append(author)

        if len(authors) > 7:
            return ', '.join(formatted[:6]) + ', ... ' + formatted[-1]
        elif len(formatted) > 1:
            return ', '.join(formatted[:-1]) + ', & ' + formatted[-1]
        else:
            return formatted[0]

    def _format_authors_mla(self, authors: List[str]) -> str:
        """Format authors in MLA style: Last, First, and First Last."""
        if not authors:
            return ""

        if len(authors) == 1:
            return authors[0]
        elif len(authors) == 2:
            return f"{authors[0]}, and {authors[1]}"
        else:
            return f"{authors[0]}, et al."

    def _format_authors_chicago(self, authors: List[str]) -> str:
        """Format authors in Chicago style."""
        return self._format_authors_mla(authors)

    def _format_authors_ieee(self, authors: List[str]) -> str:
        """Format authors in IEEE style: F. Last and F. Last."""
        if not authors:
            return ""

        formatted = []
        for author in authors:
            parts = author.split()
            if len(parts) >= 2:
                initials = '. '.join([p[0] for p in parts[:-1]]) + '.'
                last = parts[-1]
                formatted.append(f"{initials} {last}")
            else:
                formatted.append(author)

        if len(formatted) > 1:
            return ' and '.join(formatted)
        else:
            return formatted[0]

    def _format_authors_generic(self, authors: List[str], style: str) -> str:
        """Format authors using specified style."""
        if style == 'APA':
            return self._format_authors_apa(authors)
        elif style == 'MLA':
            return self._format_authors_mla(authors)
        elif style == 'CHICAGO':
            return self._format_authors_chicago(authors)
        elif style == 'IEEE':
            return self._format_authors_ieee(authors)
        else:
            return ', '.join(authors)

    # Utility methods

    def _extract_arxiv_id_from_url(self, url: Optional[str]) -> str:
        """Extract ArXiv ID from URL."""
        if not url:
            return "unknown"

        parts = url.split('/')
        arxiv_id = parts[-1] if parts else "unknown"

        # Remove version suffix
        if 'v' in arxiv_id:
            arxiv_id = arxiv_id.split('v')[0]

        return arxiv_id

    def _extract_domain(self, url: Optional[str]) -> str:
        """Extract domain from URL."""
        if not url:
            return "Unknown Source"

        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc.replace('www.', '')
        except Exception:
            return "Unknown Source"

    def generate_bibliography(
        self,
        citations: List[Dict[str, Any]],
        style: Optional[str] = None
    ) -> str:
        """
        Generate a formatted bibliography from citations.

        Args:
            citations: List of citation dictionaries
            style: Citation style (overrides default)

        Returns:
            Formatted bibliography string
        """
        citation_style = style.upper() if style else self.default_style

        formatted_citations = []
        for citation in citations:
            formatted = self.generate_citation(
                source_type=citation.get('source_type', 'web'),
                title=citation.get('title', 'Untitled'),
                authors=citation.get('authors'),
                url=citation.get('url'),
                published_date=citation.get('published_date'),
                style=citation_style,
                **citation
            )
            formatted_citations.append(formatted)

        # Sort alphabetically (by first character, typically author last name)
        formatted_citations.sort()

        # Format as numbered or bulleted list based on style
        if citation_style == 'IEEE':
            # IEEE uses numbered citations
            bibliography = '\n'.join([
                f"[{i+1}] {citation}"
                for i, citation in enumerate(formatted_citations)
            ])
        else:
            # APA, MLA, Chicago use alphabetical order without numbers
            bibliography = '\n\n'.join(formatted_citations)

        return bibliography

    def get_info(self) -> Dict[str, Any]:
        """Get information about the citation manager."""
        return {
            'default_style': self.default_style,
            'supported_styles': [s.value for s in CitationStyle],
            'supported_source_types': ['web', 'arxiv', 'document']
        }
