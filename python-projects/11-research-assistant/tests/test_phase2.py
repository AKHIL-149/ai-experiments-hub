"""
Unit tests for Phase 2 components.

Tests web search, ArXiv client, citation manager, and cache manager.
"""

import pytest
from datetime import datetime
from pathlib import Path

from src.core.web_search_client import WebSearchClient, SearchResult
from src.core.arxiv_client import ArXivClient, ArXivPaper
from src.core.citation_manager import CitationManager
from src.services.cache_manager import CacheManager


class TestWebSearchClient:
    """Test WebSearchClient."""

    def test_create_client(self):
        """Test creating web search client."""
        client = WebSearchClient(provider='duckduckgo')
        assert client.provider == 'duckduckgo'

    def test_get_info(self):
        """Test get_info method."""
        client = WebSearchClient()
        info = client.get_info()
        assert 'provider' in info
        assert info['provider'] == 'duckduckgo'

    def test_search_result_dataclass(self):
        """Test SearchResult dataclass."""
        result = SearchResult(
            title="Test Article",
            url="https://example.com",
            snippet="Test snippet",
            relevance_score=0.95
        )
        assert result.title == "Test Article"
        assert result.relevance_score == 0.95


class TestArXivClient:
    """Test ArXivClient."""

    def test_create_client(self, tmp_path):
        """Test creating ArXiv client."""
        client = ArXivClient(cache_dir=str(tmp_path))
        assert client.cache_dir == tmp_path
        assert client.cache_dir.exists()

    def test_get_info(self, tmp_path):
        """Test get_info method."""
        client = ArXivClient(cache_dir=str(tmp_path))
        info = client.get_info()
        assert 'available' in info
        assert 'cache_dir' in info
        assert 'cached_papers' in info

    def test_arxiv_paper_dataclass(self):
        """Test ArXivPaper dataclass."""
        paper = ArXivPaper(
            arxiv_id="1234.5678",
            title="Test Paper",
            authors=["John Doe", "Jane Smith"],
            summary="Test summary",
            published=datetime.now(),
            updated=datetime.now(),
            pdf_url="https://arxiv.org/pdf/1234.5678.pdf",
            categories=["cs.AI"]
        )
        assert paper.arxiv_id == "1234.5678"
        assert len(paper.authors) == 2


class TestCitationManager:
    """Test CitationManager."""

    def test_create_manager(self):
        """Test creating citation manager."""
        manager = CitationManager(default_style='APA')
        assert manager.default_style == 'APA'

    def test_get_info(self):
        """Test get_info method."""
        manager = CitationManager()
        info = manager.get_info()
        assert 'default_style' in info
        assert 'supported_styles' in info
        assert len(info['supported_styles']) == 4

    def test_generate_arxiv_citation_apa(self):
        """Test ArXiv citation in APA format."""
        manager = CitationManager(default_style='APA')
        citation = manager.generate_citation(
            source_type='arxiv',
            title='Attention Is All You Need',
            authors=['Vaswani, Ashish', 'Shazeer, Noam'],
            published_date=datetime(2017, 6, 12),
            arxiv_id='1706.03762'
        )
        assert 'Vaswani' in citation
        assert 'Attention Is All You Need' in citation
        assert '2017' in citation
        assert 'arXiv' in citation

    def test_generate_arxiv_citation_mla(self):
        """Test ArXiv citation in MLA format."""
        manager = CitationManager(default_style='MLA')
        citation = manager.generate_citation(
            source_type='arxiv',
            title='Attention Is All You Need',
            authors=['Vaswani, Ashish', 'Shazeer, Noam'],
            published_date=datetime(2017, 6, 12),
            arxiv_id='1706.03762',
            style='MLA'
        )
        assert 'Vaswani' in citation
        assert 'Attention Is All You Need' in citation
        assert '2017' in citation

    def test_generate_web_citation_apa(self):
        """Test web citation in APA format."""
        manager = CitationManager()
        citation = manager.generate_citation(
            source_type='web',
            title='Machine Learning Overview',
            authors=['John Doe'],
            url='https://example.com/ml',
            published_date=datetime(2024, 1, 15),
            domain='example.com'
        )
        assert 'Doe' in citation
        assert 'Machine Learning Overview' in citation
        assert 'example.com' in citation

    def test_generate_bibliography(self):
        """Test bibliography generation."""
        manager = CitationManager(default_style='APA')

        citations = [
            {
                'source_type': 'arxiv',
                'title': 'Paper A',
                'authors': ['Author A'],
                'published_date': datetime(2023, 1, 1),
                'arxiv_id': '2301.00001'
            },
            {
                'source_type': 'web',
                'title': 'Article B',
                'authors': ['Author B'],
                'url': 'https://example.com',
                'published_date': datetime(2023, 2, 1),
                'domain': 'example.com'
            }
        ]

        bibliography = manager.generate_bibliography(citations)
        assert 'Paper A' in bibliography
        assert 'Article B' in bibliography


class TestCacheManager:
    """Test CacheManager."""

    def test_create_manager(self, tmp_path):
        """Test creating cache manager."""
        cache_manager = CacheManager(cache_dir=str(tmp_path / 'cache'))
        assert cache_manager.enable_cache is True
        assert cache_manager.cache_dir.exists()

    def test_set_and_get(self, tmp_path):
        """Test setting and getting cache."""
        cache_manager = CacheManager(cache_dir=str(tmp_path / 'cache'))

        # Set value
        key = "test_key"
        value = {"data": "test_value", "number": 42}
        success = cache_manager.set(key, value, category='search')
        assert success is True

        # Get value
        retrieved = cache_manager.get(key, category='search')
        assert retrieved is not None
        assert retrieved['data'] == "test_value"
        assert retrieved['number'] == 42

    def test_cache_miss(self, tmp_path):
        """Test cache miss."""
        cache_manager = CacheManager(cache_dir=str(tmp_path / 'cache'))

        result = cache_manager.get("nonexistent_key", category='search')
        assert result is None

    def test_delete(self, tmp_path):
        """Test deleting cache entry."""
        cache_manager = CacheManager(cache_dir=str(tmp_path / 'cache'))

        # Set value
        key = "delete_test"
        cache_manager.set(key, "value", category='search')

        # Delete
        deleted = cache_manager.delete(key, category='search')
        assert deleted is True

        # Verify deleted
        result = cache_manager.get(key, category='search')
        assert result is None

    def test_clear(self, tmp_path):
        """Test clearing cache."""
        cache_manager = CacheManager(cache_dir=str(tmp_path / 'cache'))

        # Set multiple values
        cache_manager.set("key1", "value1", category='search')
        cache_manager.set("key2", "value2", category='search')
        cache_manager.set("key3", "value3", category='content')

        # Clear search category
        count = cache_manager.clear(category='search')
        assert count == 2

        # Verify search cleared, content remains
        assert cache_manager.get("key1", category='search') is None
        assert cache_manager.get("key3", category='content') is not None

    def test_get_stats(self, tmp_path):
        """Test cache statistics."""
        cache_manager = CacheManager(cache_dir=str(tmp_path / 'cache'))

        # Generate some activity
        cache_manager.set("key1", "value1", category='search')
        cache_manager.get("key1", category='search')  # hit
        cache_manager.get("key2", category='search')  # miss

        stats = cache_manager.get_stats()
        assert 'hits' in stats
        assert 'misses' in stats
        assert 'hit_rate' in stats
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['hit_rate'] == 0.5

    def test_get_info(self, tmp_path):
        """Test get_info method."""
        cache_manager = CacheManager(cache_dir=str(tmp_path / 'cache'))
        info = cache_manager.get_info()
        assert 'enabled' in info
        assert 'categories' in info
        assert len(info['categories']) == 3


@pytest.fixture
def tmp_path(tmp_path):
    """Provide temporary directory for tests."""
    return tmp_path
