"""
Web Search Client for Research Assistant.

Supports DuckDuckGo (free) with optional future support for Brave/SerpAPI.
Integrates with caching for cost/performance optimization.
"""

import hashlib
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

try:
    from duckduckgo_search import DDGS
    DUCKDUCKGO_AVAILABLE = True
except ImportError:
    DUCKDUCKGO_AVAILABLE = False
    logging.warning("duckduckgo-search not installed. Web search will not work.")

from bs4 import BeautifulSoup
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    import trafilatura
    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    logging.warning("trafilatura not installed. Will use basic content extraction.")


@dataclass
class SearchResult:
    """Search result from web search."""
    title: str
    url: str
    snippet: str
    content: Optional[str] = None
    published_date: Optional[datetime] = None
    source_domain: Optional[str] = None
    relevance_score: float = 0.0


class WebSearchClient:
    """Web search client with multiple provider support."""

    def __init__(
        self,
        provider: str = 'duckduckgo',
        cache_manager=None,
        max_retries: int = 3,
        timeout: int = 30
    ):
        """
        Initialize web search client.

        Args:
            provider: Search provider ('duckduckgo', 'brave', 'serpapi')
            cache_manager: Optional cache manager for caching results
            max_retries: Maximum number of retries for failed requests
            timeout: Request timeout in seconds
        """
        self.provider = provider.lower()
        self.cache_manager = cache_manager
        self.timeout = timeout

        # Setup requests session with retries
        self.session = requests.Session()
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Verify provider availability
        if self.provider == 'duckduckgo' and not DUCKDUCKGO_AVAILABLE:
            raise ValueError("DuckDuckGo search requires 'duckduckgo-search' package")

        logging.info(f"WebSearchClient initialized with provider: {self.provider}")

    def search(
        self,
        query: str,
        max_results: int = 10,
        extract_content: bool = True
    ) -> List[SearchResult]:
        """
        Search the web and return results.

        Args:
            query: Search query
            max_results: Maximum number of results to return
            extract_content: Whether to extract full content from URLs

        Returns:
            List of SearchResult objects
        """
        # Check cache first
        if self.cache_manager:
            cache_key = self._get_cache_key(query, max_results)
            cached_results = self.cache_manager.get(cache_key, category='search')
            if cached_results:
                logging.info(f"Cache hit for search query: {query[:50]}...")
                return cached_results

        # Perform search based on provider
        if self.provider == 'duckduckgo':
            results = self._search_duckduckgo(query, max_results)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        # Extract full content if requested
        if extract_content:
            results = self._extract_content(results)

        # Cache results
        if self.cache_manager:
            cache_key = self._get_cache_key(query, max_results)
            self.cache_manager.set(cache_key, results, category='search', ttl_days=7)

        return results

    def _search_duckduckgo(self, query: str, max_results: int) -> List[SearchResult]:
        """
        Search using DuckDuckGo.

        Args:
            query: Search query
            max_results: Maximum results

        Returns:
            List of SearchResult objects
        """
        results = []

        try:
            with DDGS() as ddgs:
                ddg_results = ddgs.text(query, max_results=max_results)

                for idx, result in enumerate(ddg_results):
                    search_result = SearchResult(
                        title=result.get('title', ''),
                        url=result.get('href', ''),
                        snippet=result.get('body', ''),
                        source_domain=self._extract_domain(result.get('href', '')),
                        relevance_score=1.0 - (idx / max_results)  # Simple ranking
                    )
                    results.append(search_result)

            logging.info(f"DuckDuckGo search returned {len(results)} results for: {query[:50]}...")

        except Exception as e:
            logging.error(f"DuckDuckGo search failed: {e}")
            # Return empty results rather than raising

        return results

    def _extract_content(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        Extract full content from search result URLs.

        Args:
            results: List of search results

        Returns:
            Updated list with content extracted
        """
        for result in results:
            try:
                content = self._fetch_and_extract_content(result.url)
                result.content = content
            except Exception as e:
                logging.warning(f"Failed to extract content from {result.url}: {e}")
                # Keep snippet as fallback content
                result.content = result.snippet

        return results

    def _fetch_and_extract_content(self, url: str) -> str:
        """
        Fetch URL and extract main content.

        Args:
            url: URL to fetch

        Returns:
            Extracted text content
        """
        # Fetch HTML
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; ResearchBot/1.0; +https://research-assistant.example)'
        }
        response = self.session.get(url, headers=headers, timeout=self.timeout)
        response.raise_for_status()

        html = response.text

        # Use trafilatura for better content extraction
        if TRAFILATURA_AVAILABLE:
            content = trafilatura.extract(html, include_comments=False, include_tables=True)
            if content:
                return content

        # Fallback to BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')

        # Remove script and style elements
        for script in soup(['script', 'style', 'nav', 'footer', 'header']):
            script.decompose()

        # Get text
        text = soup.get_text(separator='\n', strip=True)

        # Clean up excessive whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        content = '\n'.join(lines)

        return content

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return parsed.netloc
        except Exception:
            return ''

    def _get_cache_key(self, query: str, max_results: int) -> str:
        """Generate cache key for search query."""
        key_string = f"{self.provider}:{query}:{max_results}"
        return hashlib.sha256(key_string.encode()).hexdigest()

    def get_info(self) -> Dict[str, Any]:
        """Get information about the search client."""
        return {
            'provider': self.provider,
            'available': DUCKDUCKGO_AVAILABLE if self.provider == 'duckduckgo' else False,
            'cache_enabled': self.cache_manager is not None,
            'timeout': self.timeout
        }
