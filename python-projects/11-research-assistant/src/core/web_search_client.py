"""
Web Search Client for Research Assistant.

Supports DuckDuckGo (free) with optional future support for Brave/SerpAPI.
Integrates with caching for cost/performance optimization.
"""

import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

try:
    from ddgs import DDGS
    DUCKDUCKGO_AVAILABLE = True
except ImportError:
    DUCKDUCKGO_AVAILABLE = False
    logging.warning("ddgs not installed. Web search will not work. Install with: pip install ddgs")

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


class WebSearchError(RuntimeError):
    """The search provider could not be reached or refused the query"""


# Pages are read up to this much; an article never needs more, and a link to a huge download
# used to be read into memory whole
MAX_PAGE_BYTES = 1_000_000
# How many pages are fetched at once while extracting content
FETCH_WORKERS = 5


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
        max_retries: int = 1,
        timeout: int = 10
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
        extract_content: bool = True,
        raise_on_error: bool = False
    ) -> List[SearchResult]:
        """
        Search the web and return results.

        Args:
            query: Search query
            max_results: Maximum number of results to return
            extract_content: Whether to extract full content from URLs
            raise_on_error: Raise WebSearchError when the provider fails, instead of returning
                an empty list (which looks the same as "nothing found")

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
            results = self._search_duckduckgo(query, max_results, raise_on_error)
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

        # Extract full content if requested
        if extract_content:
            results = self._extract_content(results)

        # Cache results. Not an empty list: a failed search returns one, and caching it made a
        # one-minute outage answer "no results" for this query for a week.
        if self.cache_manager and results:
            cache_key = self._get_cache_key(query, max_results)
            self.cache_manager.set(cache_key, results, category='search', ttl_days=7)

        return results

    def _search_duckduckgo(self, query: str, max_results: int, raise_on_error: bool = False) -> List[SearchResult]:
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
                        relevance_score=1.0 - (idx / max(max_results, 1))  # Simple ranking
                    )
                    results.append(search_result)

            logging.info(f"DuckDuckGo search returned {len(results)} results for: {query[:50]}...")

        except Exception as e:
            logging.error(f"DuckDuckGo search failed: {e}")
            if raise_on_error:
                raise WebSearchError(f"Web search failed: {e}") from e

        return results

    def fetch_contents(self, results: List[SearchResult]) -> List[SearchResult]:
        """Download and extract the page text of results found with extract_content=False"""
        return self._extract_content(results)

    def _extract_content(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        Extract full content from search result URLs.

        Pages are fetched in parallel: one after another, a few slow or dead sites kept a search
        busy for minutes (a timeout and a retry each).
        """
        if not results:
            return results

        def fetch(result: SearchResult) -> None:
            try:
                result.content = self._fetch_and_extract_content(result.url)
            except Exception as e:
                logging.warning(f"Failed to extract content from {result.url}: {e}")
                # Keep snippet as fallback content
                result.content = result.snippet

        with ThreadPoolExecutor(max_workers=min(FETCH_WORKERS, len(results))) as pool:
            list(pool.map(fetch, results))

        return results

    def _fetch_and_extract_content(self, url: str) -> str:
        """
        Fetch URL and extract main content.

        Args:
            url: URL to fetch

        Returns:
            Extracted text content
        """
        if urlparse(url).scheme not in ('http', 'https'):
            raise ValueError(f"Not a web page: {url}")

        # Fetch HTML
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; ResearchBot/1.0; +https://research-assistant.example)'
        }
        with self.session.get(url, headers=headers, timeout=self.timeout, stream=True) as response:
            response.raise_for_status()

            content_type = response.headers.get('Content-Type', '').lower()
            if content_type and not any(kind in content_type for kind in ('html', 'text/plain', 'xml')):
                # A PDF or image decoded as text is noise, and would be sent to the model as such
                raise ValueError(f"Not a text page ({content_type})")

            body = b''
            for chunk in response.iter_content(chunk_size=65536):
                body += chunk
                if len(body) >= MAX_PAGE_BYTES:
                    break
            html = body.decode(response.encoding or response.apparent_encoding or 'utf-8', errors='replace')

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
