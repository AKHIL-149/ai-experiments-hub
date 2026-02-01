"""
Unit tests for Phase 3 components.

Tests deduplicator, source ranker, synthesis engine, research orchestrator, and report generator.
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

from src.utils.deduplicator import Deduplicator, SourceInfo
from src.utils.source_ranker import SourceRanker, RankedSource
from src.core.synthesis_engine import SynthesisEngine, Finding
from src.utils.report_generator import ReportGenerator


class TestDeduplicator:
    """Test Deduplicator."""

    def test_create_deduplicator(self):
        """Test creating deduplicator."""
        dedup = Deduplicator(exact_match=True, semantic_threshold=0.95)
        assert dedup.exact_match is True
        assert dedup.semantic_threshold == 0.95

    def test_calculate_content_hash(self):
        """Test content hash calculation."""
        content = "This is test content"
        hash1 = Deduplicator.calculate_content_hash(content)
        hash2 = Deduplicator.calculate_content_hash(content)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

    def test_deduplicate_exact_duplicates(self):
        """Test exact duplicate detection."""
        dedup = Deduplicator(exact_match=True, semantic_threshold=0.95)

        content1 = "This is the same content"
        content2 = "This is the same content"
        content3 = "This is different content"

        sources = [
            SourceInfo(
                id='1',
                content=content1,
                content_hash=Deduplicator.calculate_content_hash(content1),
                source_type='web',
                title='Source 1'
            ),
            SourceInfo(
                id='2',
                content=content2,
                content_hash=Deduplicator.calculate_content_hash(content2),
                source_type='web',
                title='Source 2'
            ),
            SourceInfo(
                id='3',
                content=content3,
                content_hash=Deduplicator.calculate_content_hash(content3),
                source_type='arxiv',
                title='Source 3'
            )
        ]

        unique = dedup.deduplicate(sources)

        assert len(unique) == 2  # 1 duplicate removed
        assert unique[0].id == '1'
        assert unique[1].id == '3'

    def test_get_stats(self):
        """Test deduplication statistics."""
        dedup = Deduplicator()

        content = "Same content"
        sources = [
            SourceInfo(
                id=str(i),
                content=content if i < 2 else f"Different {i}",
                content_hash=Deduplicator.calculate_content_hash(content if i < 2 else f"Different {i}"),
                source_type='web',
                title=f'Source {i}'
            )
            for i in range(5)
        ]

        unique = dedup.deduplicate(sources)

        stats = dedup.get_stats()
        assert stats['total_sources'] == 5
        assert stats['exact_duplicates'] == 1
        assert stats['unique_sources'] == 4


class TestSourceRanker:
    """Test SourceRanker."""

    def test_create_ranker(self):
        """Test creating source ranker."""
        ranker = SourceRanker(recency_decay_days=365)
        assert ranker.recency_decay_days == 365

    def test_rank_sources_basic(self):
        """Test basic source ranking."""
        ranker = SourceRanker()

        sources = [
            {
                'id': '1',
                'source_type': 'web',
                'title': 'Machine Learning Basics',
                'content': 'Machine learning is a subset of AI that enables systems to learn.',
                'url': 'https://example.com/ml',
                'published_date': datetime.now() - timedelta(days=30)
            },
            {
                'id': '2',
                'source_type': 'arxiv',
                'title': 'Deep Learning Research',
                'content': 'Deep learning uses neural networks with multiple layers.',
                'url': 'https://arxiv.org/abs/1234.5678',
                'published_date': datetime.now() - timedelta(days=10),
                'citation_count': 100
            },
            {
                'id': '3',
                'source_type': 'web',
                'title': 'AI Overview',
                'content': 'Artificial intelligence is the simulation of human intelligence.',
                'url': 'https://stanford.edu/ai',
                'published_date': datetime.now() - timedelta(days=60)
            }
        ]

        ranked = ranker.rank_sources(sources, query='machine learning')

        assert len(ranked) == 3
        assert all(isinstance(s, RankedSource) for s in ranked)

        # Check scores are calculated
        for source in ranked:
            assert source.similarity_score >= 0
            assert source.authority_score >= 0
            assert source.recency_score >= 0
            assert source.composite_score >= 0

        # ArXiv paper should have high authority
        arxiv_source = [s for s in ranked if s.source_type == 'arxiv'][0]
        assert arxiv_source.authority_score == 1.0

    def test_authority_scores(self):
        """Test authority scoring by source type and domain."""
        ranker = SourceRanker()

        sources = [
            {
                'id': '1',
                'source_type': 'arxiv',
                'title': 'Research Paper',
                'content': 'Academic content',
                'url': 'https://arxiv.org/paper'
            },
            {
                'id': '2',
                'source_type': 'web',
                'title': 'University Article',
                'content': 'Educational content',
                'url': 'https://mit.edu/article'
            },
            {
                'id': '3',
                'source_type': 'web',
                'title': 'Blog Post',
                'content': 'Blog content',
                'url': 'https://blog.example.com/post'
            }
        ]

        ranked = ranker.rank_sources(sources, query='research')

        # ArXiv should have highest authority
        arxiv = [s for s in ranked if s.source_type == 'arxiv'][0]
        assert arxiv.authority_score == 1.0

        # .edu domain should have boosted authority
        edu = [s for s in ranked if '.edu' in s.url][0]
        assert edu.authority_score >= 0.8

        # Regular web should have lower authority
        blog = [s for s in ranked if 'blog' in s.url][0]
        assert blog.authority_score == 0.5

    def test_get_info(self):
        """Test get_info method."""
        ranker = SourceRanker()
        info = ranker.get_info()

        assert 'weights' in info
        assert info['weights']['similarity'] == 0.40
        assert info['weights']['authority'] == 0.30
        assert 'authority_scores' in info
        assert 'domain_authority' in info


class TestSynthesisEngine:
    """Test SynthesisEngine."""

    def test_create_engine(self):
        """Test creating synthesis engine."""
        # Mock LLM client
        class MockLLMClient:
            def generate(self, messages, max_tokens=2000, temperature=0.7):
                return {'content': 'Mock response', 'tokens': 100, 'cost': 0.0}

        engine = SynthesisEngine(
            llm_client=MockLLMClient(),
            min_sources=3,
            confidence_threshold=0.8
        )

        assert engine.min_sources == 3
        assert engine.confidence_threshold == 0.8

    def test_finding_creation(self):
        """Test Finding dataclass."""
        finding = Finding(
            finding_text='Machine learning is widely used in AI.',
            finding_type='fact',
            confidence=0.95,
            source_ids=['1', '2', '3'],
            citations=[
                {'source_id': '1', 'title': 'Source 1', 'url': 'http://example.com/1', 'type': 'web'}
            ]
        )

        assert finding.finding_text == 'Machine learning is widely used in AI.'
        assert finding.confidence == 0.95
        assert len(finding.source_ids) == 3

    def test_get_info(self):
        """Test get_info method."""
        class MockLLMClient:
            def generate(self, messages, max_tokens=2000, temperature=0.7):
                return {'content': 'Mock', 'tokens': 10, 'cost': 0.0}

        engine = SynthesisEngine(MockLLMClient())
        info = engine.get_info()

        assert 'min_sources' in info
        assert 'confidence_threshold' in info
        assert 'confidence_levels' in info
        assert info['confidence_levels']['high'] == 0.8


class TestReportGenerator:
    """Test ReportGenerator."""

    def test_create_generator(self, tmp_path):
        """Test creating report generator."""
        gen = ReportGenerator(output_dir=str(tmp_path))
        assert gen.output_dir == tmp_path
        assert gen.output_dir.exists()

    def test_generate_markdown_report(self, tmp_path):
        """Test Markdown report generation."""
        gen = ReportGenerator(output_dir=str(tmp_path))

        data = {
            'query': 'Test Query',
            'query_id': 'test-123',
            'summary': 'This is a test summary of the research.',
            'findings': [
                {
                    'text': 'Finding 1: Machine learning is important.',
                    'type': 'fact',
                    'confidence': 0.95,
                    'sources': 3
                },
                {
                    'text': 'Finding 2: AI applications are growing.',
                    'type': 'argument',
                    'confidence': 0.85,
                    'sources': 2
                }
            ],
            'sources': [
                {
                    'title': 'Source 1',
                    'url': 'https://example.com/1',
                    'type': 'web',
                    'composite_score': 0.92
                }
            ],
            'citations': [
                'Author, A. (2024). Title. https://example.com/1'
            ],
            'stats': {
                'used_sources': 10,
                'findings': 2,
                'avg_confidence': 0.90,
                'processing_time': 15.5
            }
        }

        report_path = gen.generate_report(data, format='markdown', filename='test_report')

        assert report_path.exists()
        assert report_path.suffix == '.md'

        # Verify content
        content = report_path.read_text()
        assert 'Test Query' in content
        assert 'This is a test summary' in content
        assert 'Finding 1' in content
        assert 'Source 1' in content

    def test_generate_html_report(self, tmp_path):
        """Test HTML report generation."""
        gen = ReportGenerator(output_dir=str(tmp_path))

        data = {
            'query': 'HTML Test Query',
            'query_id': 'html-123',
            'summary': 'HTML test summary.',
            'findings': [],
            'sources': [],
            'citations': []
        }

        report_path = gen.generate_report(data, format='html', filename='test_html')

        assert report_path.exists()
        assert report_path.suffix == '.html'

        # Verify content
        content = report_path.read_text()
        assert '<!DOCTYPE html>' in content
        assert 'HTML Test Query' in content
        assert '<style>' in content

    def test_generate_json_report(self, tmp_path):
        """Test JSON report generation."""
        gen = ReportGenerator(output_dir=str(tmp_path))

        data = {
            'query': 'JSON Test',
            'query_id': 'json-123',
            'summary': 'JSON summary',
            'findings': [{'text': 'Test finding', 'confidence': 0.9}],
            'sources': [],
            'citations': []
        }

        report_path = gen.generate_report(data, format='json', filename='test_json')

        assert report_path.exists()
        assert report_path.suffix == '.json'

        # Verify content
        import json
        with open(report_path) as f:
            loaded = json.load(f)

        assert loaded['query'] == 'JSON Test'
        assert loaded['query_id'] == 'json-123'
        assert len(loaded['findings']) == 1

    def test_sanitize_filename(self, tmp_path):
        """Test filename sanitization."""
        gen = ReportGenerator(output_dir=str(tmp_path))

        # Test invalid characters
        sanitized = gen._sanitize_filename('test<>:"/\\|?*file')
        assert '<' not in sanitized
        assert '>' not in sanitized
        assert ':' not in sanitized

        # Test length limit
        long_name = 'a' * 200
        sanitized = gen._sanitize_filename(long_name)
        assert len(sanitized) <= 100

    def test_escape_html(self, tmp_path):
        """Test HTML escaping."""
        gen = ReportGenerator(output_dir=str(tmp_path))

        text = '<script>alert("XSS")</script>'
        escaped = gen._escape_html(text)

        assert '&lt;' in escaped
        assert '&gt;' in escaped
        assert '<script>' not in escaped

    def test_get_info(self, tmp_path):
        """Test get_info method."""
        gen = ReportGenerator(output_dir=str(tmp_path))
        info = gen.get_info()

        assert 'output_dir' in info
        assert 'supported_formats' in info
        assert 'markdown' in info['supported_formats']
        assert 'html' in info['supported_formats']
        assert 'json' in info['supported_formats']


# Fixtures
@pytest.fixture
def tmp_path():
    """Provide temporary directory for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)
