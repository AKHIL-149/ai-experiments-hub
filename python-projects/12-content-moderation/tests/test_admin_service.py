"""
Unit Tests for Admin Service (Phase 5)
"""

import pytest
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.database import (
    DatabaseManager, User, ContentItem, Review, Policy, AuditLog,
    ContentType, ContentStatus, ViolationCategory, UserRole
)
from src.services.admin_service import AdminService


@pytest.fixture
def db_manager():
    """Create test database manager"""
    db = DatabaseManager('sqlite:///:memory:')
    db.create_tables()
    return db


@pytest.fixture
def admin_service(db_manager):
    """Create admin service with test database"""
    return AdminService(db_manager)


@pytest.fixture
def moderator_user(db_manager):
    """Create test moderator user"""
    with db_manager.get_session() as db:
        user = User(
            username='moderator1',
            email='mod@test.com',
            password_hash='hashed',
            role=UserRole.MODERATOR,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture
def admin_user(db_manager):
    """Create test admin user"""
    with db_manager.get_session() as db:
        user = User(
            username='admin1',
            email='admin@test.com',
            password_hash='hashed',
            role=UserRole.ADMIN,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture
def regular_user(db_manager):
    """Create test regular user"""
    with db_manager.get_session() as db:
        user = User(
            username='user1',
            email='user@test.com',
            password_hash='hashed',
            role=UserRole.USER,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture
def flagged_content(db_manager, regular_user):
    """Create test flagged content"""
    with db_manager.get_session() as db:
        content = ContentItem(
            user_id=regular_user.id,
            content_type=ContentType.TEXT,
            text_content='Test content',
            status=ContentStatus.FLAGGED,
            priority=5
        )
        db.add(content)
        db.commit()
        db.refresh(content)
        return content


@pytest.fixture
def rejected_content(db_manager, regular_user):
    """Create test rejected content"""
    with db_manager.get_session() as db:
        content = ContentItem(
            user_id=regular_user.id,
            content_type=ContentType.TEXT,
            text_content='Rejected content',
            status=ContentStatus.REJECTED,
            priority=0
        )
        db.add(content)
        db.commit()
        db.refresh(content)
        return content


# Review Queue Tests

def test_get_review_queue_success(admin_service, moderator_user, flagged_content):
    """Test getting review queue"""
    success, items, total, error = admin_service.get_review_queue(
        moderator=moderator_user
    )

    assert success is True
    assert error is None
    assert total >= 1
    assert len(items) >= 1
    assert items[0].id == flagged_content.id


def test_get_review_queue_with_status_filter(admin_service, moderator_user, flagged_content):
    """Test review queue with status filter"""
    success, items, total, error = admin_service.get_review_queue(
        moderator=moderator_user,
        status='flagged'
    )

    assert success is True
    assert total >= 1
    assert all(item.status == ContentStatus.FLAGGED for item in items)


def test_get_review_queue_with_priority_filter(admin_service, moderator_user, flagged_content):
    """Test review queue with priority filter"""
    success, items, total, error = admin_service.get_review_queue(
        moderator=moderator_user,
        priority=5
    )

    assert success is True
    assert total >= 1
    assert all(item.priority == 5 for item in items)


def test_get_review_queue_pagination(admin_service, moderator_user, db_manager, regular_user):
    """Test review queue pagination"""
    # Create multiple flagged items
    with db_manager.get_session() as db:
        for i in range(10):
            content = ContentItem(
                user_id=regular_user.id,
                content_type=ContentType.TEXT,
                text_content=f'Content {i}',
                status=ContentStatus.FLAGGED,
                priority=0
            )
            db.add(content)
        db.commit()

    # Test pagination
    success, items, total, error = admin_service.get_review_queue(
        moderator=moderator_user,
        limit=5,
        offset=0
    )

    assert success is True
    assert len(items) == 5
    assert total >= 10


# Submit Review Tests

def test_submit_review_approve(admin_service, moderator_user, flagged_content):
    """Test approving content"""
    success, review, error = admin_service.submit_review(
        moderator=moderator_user,
        content_id=flagged_content.id,
        approved=True,
        notes='Looks good'
    )

    assert success is True
    assert error is None
    assert review is not None
    assert review.approved is True
    assert review.action == 'manual_approve'
    assert review.notes == 'Looks good'

    # Verify content status updated
    with admin_service.db_manager.get_session() as db:
        content = db.query(ContentItem).filter(ContentItem.id == flagged_content.id).first()
        assert content.status == ContentStatus.APPROVED


def test_submit_review_reject(admin_service, moderator_user, flagged_content):
    """Test rejecting content"""
    success, review, error = admin_service.submit_review(
        moderator=moderator_user,
        content_id=flagged_content.id,
        approved=False,
        category='spam',
        notes='This is spam'
    )

    assert success is True
    assert error is None
    assert review is not None
    assert review.approved is False
    assert review.action == 'manual_reject'
    assert review.category == ViolationCategory.SPAM

    # Verify content status updated
    with admin_service.db_manager.get_session() as db:
        content = db.query(ContentItem).filter(ContentItem.id == flagged_content.id).first()
        assert content.status == ContentStatus.REJECTED


def test_submit_review_invalid_content(admin_service, moderator_user):
    """Test reviewing non-existent content"""
    success, review, error = admin_service.submit_review(
        moderator=moderator_user,
        content_id='invalid-id',
        approved=True
    )

    assert success is False
    assert error == 'Content not found'
    assert review is None


def test_submit_review_creates_audit_log(admin_service, moderator_user, flagged_content):
    """Test that review creates audit log"""
    success, review, error = admin_service.submit_review(
        moderator=moderator_user,
        content_id=flagged_content.id,
        approved=True
    )

    assert success is True

    # Check audit log created
    with admin_service.db_manager.get_session() as db:
        audit = db.query(AuditLog).filter(
            AuditLog.event_type == 'manual_review',
            AuditLog.resource_id == flagged_content.id
        ).first()

        assert audit is not None
        assert audit.actor_id == moderator_user.id
        assert audit.action == 'approve'


# Appeal Tests

def test_create_appeal_success(admin_service, regular_user, rejected_content):
    """Test creating appeal"""
    success, appeal_id, error = admin_service.create_appeal(
        user=regular_user,
        content_id=rejected_content.id,
        reason='I think this was a mistake'
    )

    assert success is True
    assert error is None
    assert appeal_id is not None

    # Verify appeal created
    with admin_service.db_manager.get_session() as db:
        appeal = db.query(Review).filter(Review.id == appeal_id).first()
        assert appeal is not None
        assert appeal.is_appeal_review is True
        assert appeal.action == 'appeal_submitted'
        assert appeal.notes == 'I think this was a mistake'


def test_create_appeal_invalid_content(admin_service, regular_user):
    """Test creating appeal for non-existent content"""
    success, appeal_id, error = admin_service.create_appeal(
        user=regular_user,
        content_id='invalid-id',
        reason='Test'
    )

    assert success is False
    assert error == 'Content not found'
    assert appeal_id is None


def test_create_appeal_wrong_user(admin_service, regular_user, rejected_content, db_manager):
    """Test creating appeal for content owned by different user"""
    # Create another user
    with db_manager.get_session() as db:
        other_user = User(
            username='other_user',
            email='other@test.com',
            password_hash='hashed',
            role=UserRole.USER,
            is_active=True
        )
        db.add(other_user)
        db.commit()
        db.refresh(other_user)

    success, appeal_id, error = admin_service.create_appeal(
        user=other_user,
        content_id=rejected_content.id,
        reason='Test'
    )

    assert success is False
    assert error == 'Access denied'


def test_create_appeal_not_rejected(admin_service, regular_user, flagged_content):
    """Test creating appeal for non-rejected content"""
    success, appeal_id, error = admin_service.create_appeal(
        user=regular_user,
        content_id=flagged_content.id,
        reason='Test'
    )

    assert success is False
    assert error == 'Can only appeal rejected content'


def test_create_appeal_duplicate(admin_service, regular_user, rejected_content):
    """Test creating duplicate appeal"""
    # Create first appeal
    success1, appeal_id1, error1 = admin_service.create_appeal(
        user=regular_user,
        content_id=rejected_content.id,
        reason='First appeal'
    )
    assert success1 is True

    # Try to create duplicate
    success2, appeal_id2, error2 = admin_service.create_appeal(
        user=regular_user,
        content_id=rejected_content.id,
        reason='Second appeal'
    )

    assert success2 is False
    assert error2 == 'Appeal already exists'


def test_review_appeal_approve(admin_service, moderator_user, regular_user, rejected_content):
    """Test approving an appeal"""
    # Create appeal
    success, appeal_id, error = admin_service.create_appeal(
        user=regular_user,
        content_id=rejected_content.id,
        reason='Mistake'
    )
    assert success is True

    # Review appeal
    success, review, error = admin_service.review_appeal(
        moderator=moderator_user,
        appeal_id=appeal_id,
        approved=True,
        notes='You are right, mistake'
    )

    assert success is True
    assert error is None
    assert review.approved is True
    assert review.action == 'appeal_approved'

    # Verify content restored
    with admin_service.db_manager.get_session() as db:
        content = db.query(ContentItem).filter(ContentItem.id == rejected_content.id).first()
        assert content.status == ContentStatus.APPROVED


def test_review_appeal_reject(admin_service, moderator_user, regular_user, rejected_content):
    """Test rejecting an appeal"""
    # Create appeal
    success, appeal_id, error = admin_service.create_appeal(
        user=regular_user,
        content_id=rejected_content.id,
        reason='Mistake'
    )
    assert success is True

    # Review appeal
    success, review, error = admin_service.review_appeal(
        moderator=moderator_user,
        appeal_id=appeal_id,
        approved=False,
        notes='Decision stands'
    )

    assert success is True
    assert review.approved is False
    assert review.action == 'appeal_rejected'

    # Verify content still rejected
    with admin_service.db_manager.get_session() as db:
        content = db.query(ContentItem).filter(ContentItem.id == rejected_content.id).first()
        assert content.status == ContentStatus.REJECTED


# Policy Tests

def test_list_policies(admin_service, admin_user):
    """Test listing policies"""
    # Create a policy
    admin_service.create_policy(
        admin=admin_user,
        name='Test Policy',
        category='spam',
        severity=5
    )

    success, policies, error = admin_service.list_policies()

    assert success is True
    assert error is None
    assert len(policies) >= 1


def test_list_policies_enabled_only(admin_service, admin_user):
    """Test listing only enabled policies"""
    # Create enabled policy
    admin_service.create_policy(
        admin=admin_user,
        name='Enabled Policy',
        category='spam',
        enabled=True
    )

    # Create disabled policy
    admin_service.create_policy(
        admin=admin_user,
        name='Disabled Policy',
        category='nsfw',
        enabled=False
    )

    success, policies, error = admin_service.list_policies(enabled_only=True)

    assert success is True
    assert all(p.enabled for p in policies)


def test_create_policy_success(admin_service, admin_user):
    """Test creating policy"""
    success, policy, error = admin_service.create_policy(
        admin=admin_user,
        name='NSFW Policy',
        category='nsfw',
        auto_reject_threshold=0.95,
        flag_review_threshold=0.6,
        severity=8,
        enabled=True
    )

    assert success is True
    assert error is None
    assert policy is not None
    assert policy.name == 'NSFW Policy'
    assert policy.category == ViolationCategory.NSFW
    assert policy.auto_reject_threshold == 0.95
    assert policy.severity == 8


def test_create_policy_duplicate_name(admin_service, admin_user):
    """Test creating policy with duplicate name"""
    # Create first policy
    success1, policy1, error1 = admin_service.create_policy(
        admin=admin_user,
        name='Duplicate Test',
        category='spam'
    )
    assert success1 is True

    # Try to create duplicate
    success2, policy2, error2 = admin_service.create_policy(
        admin=admin_user,
        name='Duplicate Test',
        category='nsfw'
    )

    assert success2 is False
    assert 'already exists' in error2


def test_update_policy_success(admin_service, admin_user):
    """Test updating policy"""
    # Create policy
    success, policy, error = admin_service.create_policy(
        admin=admin_user,
        name='Update Test',
        category='spam',
        severity=5
    )
    assert success is True
    policy_id = policy.id

    # Update policy
    success, updated, error = admin_service.update_policy(
        admin=admin_user,
        policy_id=policy_id,
        auto_reject_threshold=0.85,
        severity=7,
        enabled=False
    )

    assert success is True
    assert error is None
    assert updated.auto_reject_threshold == 0.85
    assert updated.severity == 7
    assert updated.enabled is False


def test_update_policy_invalid_id(admin_service, admin_user):
    """Test updating non-existent policy"""
    success, policy, error = admin_service.update_policy(
        admin=admin_user,
        policy_id='invalid-id',
        severity=5
    )

    assert success is False
    assert error == 'Policy not found'


# Dashboard Stats Tests

def test_get_admin_stats(admin_service, db_manager, regular_user, moderator_user, flagged_content):
    """Test getting admin dashboard stats"""
    stats = admin_service.get_admin_stats()

    assert 'content' in stats
    assert 'reviews' in stats
    assert 'users' in stats
    assert 'policies' in stats

    # Content stats
    assert stats['content']['total'] >= 1
    assert stats['content']['flagged'] >= 1

    # User stats
    assert stats['users']['total'] >= 2
    assert stats['users']['moderators'] >= 1
