"""
Unit tests for database models.

Tests all 6 tables: User, Session, ResearchQuery, Source, Finding, Citation
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.database import (
    Base,
    User,
    UserSession,
    ResearchQuery,
    Source,
    Finding,
    Citation,
    DatabaseManager
)


@pytest.fixture
def db_session():
    """Create test database session."""
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def test_user(db_session):
    """Create test user."""
    user = User(
        username='testuser',
        email='test@example.com',
        password_hash='hashed_password'
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def test_session(db_session, test_user):
    """Create test session."""
    session = UserSession(
        id='test_token_12345',
        user_id=test_user.id,
        expires_at=datetime.utcnow() + timedelta(days=30)
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


@pytest.fixture
def test_query(db_session, test_user):
    """Create test research query."""
    query = ResearchQuery(
        user_id=test_user.id,
        query_text='What is quantum computing?'
    )
    db_session.add(query)
    db_session.commit()
    db_session.refresh(query)
    return query


class TestUser:
    """Test User model."""

    def test_create_user(self, db_session):
        """Test creating a user."""
        user = User(
            username='john_doe',
            email='john@example.com',
            password_hash='hashed_pw'
        )
        db_session.add(user)
        db_session.commit()

        assert user.id is not None
        assert user.username == 'john_doe'
        assert user.email == 'john@example.com'
        assert user.created_at is not None

    def test_user_to_dict(self, test_user):
        """Test user to_dict method."""
        user_dict = test_user.to_dict()

        assert 'id' in user_dict
        assert user_dict['username'] == 'testuser'
        assert user_dict['email'] == 'test@example.com'
        assert 'password_hash' not in user_dict  # Should be excluded

    def test_unique_username(self, db_session, test_user):
        """Test username uniqueness constraint."""
        duplicate_user = User(
            username='testuser',  # Same as test_user
            email='different@example.com',
            password_hash='hash'
        )
        db_session.add(duplicate_user)

        with pytest.raises(Exception):  # SQLAlchemy IntegrityError
            db_session.commit()

    def test_unique_email(self, db_session, test_user):
        """Test email uniqueness constraint."""
        duplicate_user = User(
            username='different_user',
            email='test@example.com',  # Same as test_user
            password_hash='hash'
        )
        db_session.add(duplicate_user)

        with pytest.raises(Exception):  # SQLAlchemy IntegrityError
            db_session.commit()


class TestUserSession:
    """Test UserSession model."""

    def test_create_session(self, db_session, test_user):
        """Test creating a session."""
        expires_at = datetime.utcnow() + timedelta(days=30)
        session = UserSession(
            id='token_abc123',
            user_id=test_user.id,
            expires_at=expires_at
        )
        db_session.add(session)
        db_session.commit()

        assert session.id == 'token_abc123'
        assert session.user_id == test_user.id
        assert session.created_at is not None

    def test_session_is_expired_false(self, test_session):
        """Test session is not expired."""
        assert not test_session.is_expired()

    def test_session_is_expired_true(self, db_session, test_user):
        """Test session is expired."""
        expired_session = UserSession(
            id='expired_token',
            user_id=test_user.id,
            expires_at=datetime.utcnow() - timedelta(days=1)  # Yesterday
        )
        db_session.add(expired_session)
        db_session.commit()

        assert expired_session.is_expired()

    def test_session_to_dict(self, test_session):
        """Test session to_dict method."""
        session_dict = test_session.to_dict()

        assert 'id' in session_dict
        assert 'user_id' in session_dict
        assert 'expires_at' in session_dict

    def test_session_user_relationship(self, db_session, test_user, test_session):
        """Test session-user relationship."""
        assert test_session.user.id == test_user.id
        assert test_session.user.username == 'testuser'


class TestResearchQuery:
    """Test ResearchQuery model."""

    def test_create_query(self, db_session, test_user):
        """Test creating a research query."""
        query = ResearchQuery(
            user_id=test_user.id,
            query_text='What are the applications of AI?'
        )
        db_session.add(query)
        db_session.commit()

        assert query.id is not None
        assert query.status == 'pending'
        assert query.search_web is True
        assert query.search_arxiv is True
        assert query.max_sources == 20
        assert query.verification_level == 'strict'
        assert query.citation_style == 'APA'

    def test_query_to_dict(self, test_query):
        """Test query to_dict method."""
        query_dict = test_query.to_dict()

        assert 'id' in query_dict
        assert query_dict['query_text'] == 'What is quantum computing?'
        assert query_dict['status'] == 'pending'
        assert 'sources' not in query_dict  # Default: don't include

    def test_query_to_dict_with_sources(self, db_session, test_query):
        """Test query to_dict with sources."""
        # Add a source
        source = Source(
            query_id=test_query.id,
            source_type='web',
            title='Test Source',
            url='https://example.com',
            content='Test content',
            content_hash='abc123',
            relevance_score=0.95,
            retrieval_rank=1
        )
        db_session.add(source)
        db_session.commit()

        query_dict = test_query.to_dict(include_sources=True)
        assert 'sources' in query_dict
        assert len(query_dict['sources']) == 1

    def test_mark_processing(self, test_query):
        """Test marking query as processing."""
        test_query.mark_processing()

        assert test_query.status == 'processing'
        assert test_query.started_at is not None

    def test_mark_completed(self, db_session, test_query):
        """Test marking query as completed."""
        test_query.mark_processing()
        db_session.commit()

        test_query.mark_completed(summary='Test summary', confidence=0.85)

        assert test_query.status == 'completed'
        assert test_query.summary == 'Test summary'
        assert test_query.confidence_score == 0.85
        assert test_query.completed_at is not None
        assert test_query.processing_time_seconds is not None

    def test_mark_failed(self, test_query):
        """Test marking query as failed."""
        test_query.mark_failed(error='Test error')

        assert test_query.status == 'failed'
        assert test_query.error_message == 'Test error'
        assert test_query.completed_at is not None


class TestSource:
    """Test Source model."""

    def test_create_source(self, db_session, test_query):
        """Test creating a source."""
        source = Source(
            query_id=test_query.id,
            source_type='arxiv',
            title='Quantum Computing Paper',
            url='https://arxiv.org/abs/1234.5678',
            authors=['John Doe', 'Jane Smith'],
            content='Full paper content...',
            content_hash='sha256_hash',
            relevance_score=0.92,
            retrieval_rank=1
        )
        db_session.add(source)
        db_session.commit()

        assert source.id is not None
        assert source.source_type == 'arxiv'
        assert source.authors == ['John Doe', 'Jane Smith']

    def test_source_to_dict(self, db_session, test_query):
        """Test source to_dict method."""
        long_content = 'A' * 1000  # 1000 characters
        source = Source(
            query_id=test_query.id,
            source_type='web',
            title='Long Content',
            url='https://example.com',
            content=long_content,
            content_hash='hash',
            relevance_score=0.8,
            retrieval_rank=1
        )
        db_session.add(source)
        db_session.commit()

        source_dict = source.to_dict()

        # Content should be truncated to 500 chars + '...'
        assert len(source_dict['content']) == 503
        assert source_dict['content'].endswith('...')

    def test_source_query_relationship(self, db_session, test_query):
        """Test source-query relationship."""
        source = Source(
            query_id=test_query.id,
            source_type='document',
            title='Test Doc',
            content='Content',
            content_hash='hash',
            relevance_score=0.7,
            retrieval_rank=1
        )
        db_session.add(source)
        db_session.commit()

        assert source.query.id == test_query.id
        assert len(test_query.sources) == 1


class TestFinding:
    """Test Finding model."""

    def test_create_finding(self, db_session, test_query):
        """Test creating a finding."""
        finding = Finding(
            query_id=test_query.id,
            finding_text='Quantum computers use qubits',
            finding_type='fact',
            confidence=0.95,
            source_ids=['source_1', 'source_2', 'source_3']
        )
        db_session.add(finding)
        db_session.commit()

        assert finding.id is not None
        assert finding.confidence == 0.95
        assert len(finding.source_ids) == 3

    def test_finding_to_dict(self, db_session, test_query):
        """Test finding to_dict method."""
        finding = Finding(
            query_id=test_query.id,
            finding_text='AI can process natural language',
            finding_type='fact',
            confidence=0.88,
            source_ids=['src1', 'src2']
        )
        db_session.add(finding)
        db_session.commit()

        finding_dict = finding.to_dict()

        assert finding_dict['finding_text'] == 'AI can process natural language'
        assert finding_dict['source_count'] == 2

    def test_finding_query_relationship(self, db_session, test_query):
        """Test finding-query relationship."""
        finding = Finding(
            query_id=test_query.id,
            finding_text='Test finding',
            confidence=0.9,
            source_ids=['s1']
        )
        db_session.add(finding)
        db_session.commit()

        assert finding.query.id == test_query.id
        assert len(test_query.findings) == 1


class TestCitation:
    """Test Citation model."""

    def test_create_citation(self, db_session, test_query):
        """Test creating a citation."""
        # Create source first
        source = Source(
            query_id=test_query.id,
            source_type='arxiv',
            title='Paper Title',
            content='Content',
            content_hash='hash',
            relevance_score=0.9,
            retrieval_rank=1
        )
        db_session.add(source)
        db_session.commit()

        citation = Citation(
            query_id=test_query.id,
            source_id=source.id,
            citation_text='Quantum computing shows promise',
            citation_style='APA',
            formatted_citation='Author, A. (2024). Paper Title. arXiv:1234.5678.'
        )
        db_session.add(citation)
        db_session.commit()

        assert citation.id is not None
        assert citation.citation_style == 'APA'

    def test_citation_to_dict(self, db_session, test_query):
        """Test citation to_dict method."""
        source = Source(
            query_id=test_query.id,
            source_type='web',
            title='Web Article',
            content='Content',
            content_hash='hash',
            relevance_score=0.8,
            retrieval_rank=1
        )
        db_session.add(source)
        db_session.commit()

        citation = Citation(
            query_id=test_query.id,
            source_id=source.id,
            citation_style='MLA',
            formatted_citation='Smith, John. "Web Article." Example.com, 2024.',
            citation_number=1
        )
        db_session.add(citation)
        db_session.commit()

        citation_dict = citation.to_dict()

        assert citation_dict['citation_style'] == 'MLA'
        assert citation_dict['citation_number'] == 1

    def test_citation_relationships(self, db_session, test_query):
        """Test citation relationships with query and source."""
        source = Source(
            query_id=test_query.id,
            source_type='document',
            title='Doc',
            content='Content',
            content_hash='hash',
            relevance_score=0.7,
            retrieval_rank=1
        )
        db_session.add(source)
        db_session.commit()

        citation = Citation(
            query_id=test_query.id,
            source_id=source.id,
            citation_style='Chicago',
            formatted_citation='Citation text'
        )
        db_session.add(citation)
        db_session.commit()

        assert citation.query.id == test_query.id
        assert citation.source.id == source.id
        assert len(test_query.citations) == 1
        assert len(source.citations) == 1


class TestDatabaseManager:
    """Test DatabaseManager class."""

    def test_create_tables(self):
        """Test creating database tables."""
        db_manager = DatabaseManager('sqlite:///:memory:')
        db_manager.create_tables()

        # Should not raise exception
        assert db_manager.engine is not None

    def test_get_session(self):
        """Test getting database session."""
        db_manager = DatabaseManager('sqlite:///:memory:')
        db_manager.create_tables()

        session = db_manager.get_session()
        assert session is not None
        session.close()

    def test_get_user_by_username(self, db_session, test_user):
        """Test getting user by username."""
        db_manager = DatabaseManager('sqlite:///:memory:')

        user = db_manager.get_user_by_username(db_session, 'testuser')
        assert user is not None
        assert user.username == 'testuser'

    def test_get_user_by_email(self, db_session, test_user):
        """Test getting user by email."""
        db_manager = DatabaseManager('sqlite:///:memory:')

        user = db_manager.get_user_by_email(db_session, 'test@example.com')
        assert user is not None
        assert user.email == 'test@example.com'

    def test_get_research_queries_by_user(self, db_session, test_user, test_query):
        """Test getting research queries by user."""
        db_manager = DatabaseManager('sqlite:///:memory:')

        queries = db_manager.get_research_queries_by_user(db_session, test_user.id)
        assert len(queries) == 1
        assert queries[0].id == test_query.id

    def test_cleanup_expired_sessions(self, db_session, test_user):
        """Test cleaning up expired sessions."""
        db_manager = DatabaseManager('sqlite:///:memory:')

        # Create expired session
        expired = UserSession(
            id='expired',
            user_id=test_user.id,
            expires_at=datetime.utcnow() - timedelta(days=1)
        )
        db_session.add(expired)
        db_session.commit()

        count = db_manager.cleanup_expired_sessions(db_session)
        assert count == 1

        # Verify session is deleted
        remaining = db_session.query(UserSession).filter(UserSession.id == 'expired').first()
        assert remaining is None
