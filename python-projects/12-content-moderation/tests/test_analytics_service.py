"""
Unit Tests for Analytics Service (Phase 6)
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.database import (
    DatabaseManager, User, ContentItem, Classification, Review, ModerationJob,
    ContentType, ContentStatus, ViolationCategory, UserRole, JobStatus
)
from src.services.analytics_service import AnalyticsService


@pytest.fixture
def db_manager():
    """Create test database manager"""
    db = DatabaseManager('sqlite:///:memory:')
    db.create_tables()
    return db


@pytest.fixture
def analytics_service(db_manager):
    """Create analytics service with test database"""
    return AnalyticsService(db_manager)


@pytest.fixture
def sample_data(db_manager):
    """Create sample data for testing"""
    with db_manager.get_session() as db:
        # Create users
        user = User(
            username='testuser',
            email='test@example.com',
            password_hash='hashed',
            role=UserRole.USER,
            is_active=True
        )
        db.add(user)

        moderator = User(
            username='moderator',
            email='mod@example.com',
            password_hash='hashed',
            role=UserRole.MODERATOR,
            is_active=True
        )
        db.add(moderator)
        db.commit()
        db.refresh(user)
        db.refresh(moderator)

        # Create content items
        for i in range(10):
            status = ContentStatus.APPROVED if i < 6 else ContentStatus.REJECTED
            content = ContentItem(
                user_id=user.id,
                content_type=ContentType.TEXT,
                text_content=f'Test content {i}',
                status=status,
                priority=0,
                moderated_at=datetime.utcnow() if status != ContentStatus.PENDING else None
            )
            db.add(content)
        db.commit()

        # Create classifications
        contents = db.query(ContentItem).all()
        for i, content in enumerate(contents[:5]):
            classification = Classification(
                content_id=content.id,
                category=ViolationCategory.SPAM if i < 2 else ViolationCategory.CLEAN,
                confidence=0.8 + (i * 0.02),
                is_violation=(i < 2),
                provider='ollama',
                model_name='llama3.2:3b',
                reasoning='Test classification',
                processing_time_ms=500,
                cost=0.0
            )
            db.add(classification)
        db.commit()

        # Create reviews
        for content in contents[:3]:
            review = Review(
                content_id=content.id,
                moderator_id=moderator.id,
                action='manual_approve',
                approved=True,
                notes='Test review'
            )
            db.add(review)
        db.commit()

        # Create moderation jobs
        for content in contents[:5]:
            job = ModerationJob(
                content_id=content.id,
                status=JobStatus.COMPLETED,
                queue_name='default',
                celery_task_id=f'task-{content.id}',
                started_at=datetime.utcnow() - timedelta(minutes=10),
                completed_at=datetime.utcnow(),
                processing_time_seconds=5.5,
                retry_count=0
            )
            db.add(job)
        db.commit()

    return user, moderator


# Overview Metrics Tests

def test_get_overview_metrics(analytics_service, sample_data):
    """Test getting overview metrics"""
    metrics = analytics_service.get_overview_metrics()

    assert 'content' in metrics
    assert 'reviews' in metrics
    assert 'classifications' in metrics
    assert 'jobs' in metrics

    # Check content metrics
    assert metrics['content']['total'] == 10
    assert metrics['content']['approved'] == 6
    assert metrics['content']['rejected'] == 4
    assert metrics['content']['approval_rate'] == 60.0

    # Check review metrics
    assert metrics['reviews']['total'] == 3
    assert metrics['reviews']['manual'] == 3

    # Check classification metrics
    assert metrics['classifications']['total'] == 5
    assert metrics['classifications']['violations'] == 2

    # Check job metrics
    assert metrics['jobs']['total'] == 5
    assert metrics['jobs']['completed'] == 5
    assert metrics['jobs']['success_rate'] == 100.0


def test_get_overview_metrics_empty_db(analytics_service):
    """Test overview metrics with empty database"""
    metrics = analytics_service.get_overview_metrics()

    assert metrics['content']['total'] == 0
    assert metrics['content']['approval_rate'] == 0
    assert metrics['reviews']['total'] == 0
    assert metrics['jobs']['success_rate'] == 0


# Time Series Tests

def test_get_time_series(analytics_service, sample_data):
    """Test getting time series data"""
    series = analytics_service.get_time_series(days=30)

    assert 'submissions' in series
    assert 'approvals' in series
    assert 'rejections' in series
    assert 'period' in series

    assert series['period']['days'] == 30
    assert isinstance(series['submissions'], list)
    assert isinstance(series['approvals'], list)
    assert isinstance(series['rejections'], list)


def test_get_time_series_custom_days(analytics_service, sample_data):
    """Test time series with custom days"""
    series = analytics_service.get_time_series(days=7)

    assert series['period']['days'] == 7


# Category Breakdown Tests

def test_get_category_breakdown(analytics_service, sample_data):
    """Test category breakdown"""
    breakdown = analytics_service.get_category_breakdown()

    assert 'total_violations' in breakdown
    assert 'categories' in breakdown

    assert breakdown['total_violations'] == 2
    assert len(breakdown['categories']) > 0

    # Check first category
    if breakdown['categories']:
        cat = breakdown['categories'][0]
        assert 'category' in cat
        assert 'count' in cat
        assert 'percentage' in cat


def test_get_category_breakdown_empty(analytics_service):
    """Test category breakdown with no violations"""
    breakdown = analytics_service.get_category_breakdown()

    assert breakdown['total_violations'] == 0
    assert breakdown['categories'] == []


# Content Type Stats Tests

def test_get_content_type_stats(analytics_service, sample_data):
    """Test content type statistics"""
    stats = analytics_service.get_content_type_stats()

    assert 'content_types' in stats
    assert len(stats['content_types']) > 0

    # Check first type
    type_stat = stats['content_types'][0]
    assert 'type' in type_stat
    assert 'total' in type_stat
    assert 'approved' in type_stat
    assert 'rejected' in type_stat
    assert 'approval_rate' in type_stat


def test_get_content_type_stats_with_multiple_types(db_manager, analytics_service):
    """Test content type stats with multiple types"""
    with db_manager.get_session() as db:
        user = User(
            username='user',
            email='user@test.com',
            password_hash='hash',
            role=UserRole.USER
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Add different content types
        for content_type in [ContentType.TEXT, ContentType.IMAGE, ContentType.VIDEO]:
            for i in range(3):
                content = ContentItem(
                    user_id=user.id,
                    content_type=content_type,
                    text_content='Test',
                    status=ContentStatus.APPROVED if i < 2 else ContentStatus.REJECTED
                )
                db.add(content)
        db.commit()

    stats = analytics_service.get_content_type_stats()
    assert len(stats['content_types']) == 3


# Moderator Performance Tests

def test_get_moderator_performance(analytics_service, sample_data):
    """Test moderator performance metrics"""
    performance = analytics_service.get_moderator_performance()

    assert isinstance(performance, list)
    assert len(performance) > 0

    # Check moderator data
    mod = performance[0]
    assert 'moderator_id' in mod
    assert 'username' in mod
    assert 'role' in mod
    assert 'total_reviews' in mod
    assert 'approvals' in mod
    assert 'rejections' in mod
    assert 'appeals_reviewed' in mod


def test_get_moderator_performance_no_moderators(db_manager, analytics_service):
    """Test moderator performance with no moderators"""
    performance = analytics_service.get_moderator_performance()

    assert performance == []


# Cost Analysis Tests

def test_get_cost_analysis(analytics_service, sample_data):
    """Test cost analysis"""
    costs = analytics_service.get_cost_analysis()

    assert 'total_cost' in costs
    assert 'average_cost' in costs
    assert 'by_provider' in costs
    assert 'by_content_type' in costs
    assert 'currency' in costs

    assert costs['currency'] == 'USD'
    assert costs['total_cost'] >= 0
    assert costs['average_cost'] >= 0


def test_get_cost_analysis_with_costs(db_manager, analytics_service):
    """Test cost analysis with actual costs"""
    with db_manager.get_session() as db:
        user = User(username='user', email='user@test.com', password_hash='hash', role=UserRole.USER)
        db.add(user)
        db.commit()
        db.refresh(user)

        content = ContentItem(
            user_id=user.id,
            content_type=ContentType.TEXT,
            text_content='Test',
            status=ContentStatus.APPROVED
        )
        db.add(content)
        db.commit()
        db.refresh(content)

        classification = Classification(
            content_id=content.id,
            category=ViolationCategory.CLEAN,
            confidence=0.9,
            is_violation=False,
            provider='openai',
            model_name='gpt-4o-mini',
            reasoning='Clean',
            cost=0.00025
        )
        db.add(classification)
        db.commit()

    costs = analytics_service.get_cost_analysis()
    assert costs['total_cost'] > 0


# Performance Metrics Tests

def test_get_performance_metrics(analytics_service, sample_data):
    """Test performance metrics"""
    metrics = analytics_service.get_performance_metrics()

    assert 'by_content_type' in metrics
    assert 'by_queue' in metrics

    assert isinstance(metrics['by_content_type'], list)
    assert isinstance(metrics['by_queue'], list)


def test_get_performance_metrics_with_data(analytics_service, sample_data):
    """Test performance metrics with actual data"""
    metrics = analytics_service.get_performance_metrics()

    # Should have at least some data from sample_data
    if metrics['by_content_type']:
        perf = metrics['by_content_type'][0]
        assert 'type' in perf
        assert 'avg_processing_time' in perf

    if metrics['by_queue']:
        queue = metrics['by_queue'][0]
        assert 'queue' in queue
        assert 'avg_processing_time' in queue
        assert 'jobs_processed' in queue


# Export Analytics Tests

def test_export_analytics_data(analytics_service, sample_data):
    """Test exporting analytics data"""
    success, data, error = analytics_service.export_analytics_data(format='json', days=30)

    assert success is True
    assert error is None
    assert data is not None

    # Check exported data structure
    assert 'generated_at' in data
    assert 'period_days' in data
    assert 'overview' in data
    assert 'time_series' in data
    assert 'categories' in data
    assert 'content_types' in data
    assert 'moderators' in data
    assert 'costs' in data
    assert 'performance' in data


def test_export_analytics_custom_days(analytics_service, sample_data):
    """Test export with custom days"""
    success, data, error = analytics_service.export_analytics_data(days=7)

    assert success is True
    assert data['period_days'] == 7


# Edge Cases and Error Handling

def test_analytics_with_none_values(db_manager, analytics_service):
    """Test analytics handles None values correctly"""
    with db_manager.get_session() as db:
        user = User(username='user', email='user@test.com', password_hash='hash', role=UserRole.USER)
        db.add(user)
        db.commit()
        db.refresh(user)

        # Create content with minimal data
        content = ContentItem(
            user_id=user.id,
            content_type=ContentType.TEXT,
            text_content='Test',
            status=ContentStatus.PENDING
        )
        db.add(content)
        db.commit()

    # Should not raise errors
    metrics = analytics_service.get_overview_metrics()
    assert metrics is not None


def test_analytics_service_singleton():
    """Test analytics service singleton pattern"""
    from src.services.analytics_service import get_analytics_service

    service1 = get_analytics_service()
    service2 = get_analytics_service()

    assert service1 is service2
