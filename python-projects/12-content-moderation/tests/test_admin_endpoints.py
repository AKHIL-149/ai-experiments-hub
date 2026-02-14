"""
Integration Tests for Admin API Endpoints (Phase 5)
"""

import pytest
import sys
from pathlib import Path
from fastapi.testclient import TestClient

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import app
from src.core.database import (
    DatabaseManager, User, ContentItem, Review, Policy,
    ContentType, ContentStatus, ViolationCategory, UserRole
)
from src.core.auth_manager import AuthManager


@pytest.fixture
def client():
    """Create test client"""
    return TestClient(app)


@pytest.fixture
def db_manager():
    """Create test database"""
    db = DatabaseManager('sqlite:///:memory:')
    db.create_tables()
    return db


@pytest.fixture
def auth_manager(db_manager):
    """Create auth manager"""
    return AuthManager(db_manager, 30)


@pytest.fixture
def moderator_session(db_manager, auth_manager):
    """Create moderator user and session"""
    with db_manager.get_session() as db:
        # Create moderator
        user = User(
            username='mod_test',
            email='mod@test.com',
            password_hash='hashed',
            role=UserRole.MODERATOR,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Create session
        session = auth_manager.create_session(user)
        return session.id


@pytest.fixture
def admin_session(db_manager, auth_manager):
    """Create admin user and session"""
    with db_manager.get_session() as db:
        # Create admin
        user = User(
            username='admin_test',
            email='admin@test.com',
            password_hash='hashed',
            role=UserRole.ADMIN,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Create session
        session = auth_manager.create_session(user)
        return session.id


@pytest.fixture
def user_session(db_manager, auth_manager):
    """Create regular user and session"""
    with db_manager.get_session() as db:
        # Create user
        user = User(
            username='user_test',
            email='user@test.com',
            password_hash='hashed',
            role=UserRole.USER,
            is_active=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # Create session
        session = auth_manager.create_session(user)
        return session.id, user.id


@pytest.fixture
def flagged_content_id(db_manager, user_session):
    """Create flagged content"""
    _, user_id = user_session

    with db_manager.get_session() as db:
        content = ContentItem(
            user_id=user_id,
            content_type=ContentType.TEXT,
            text_content='Flagged test content',
            status=ContentStatus.FLAGGED,
            priority=5
        )
        db.add(content)
        db.commit()
        db.refresh(content)
        return content.id


@pytest.fixture
def rejected_content_id(db_manager, user_session):
    """Create rejected content"""
    _, user_id = user_session

    with db_manager.get_session() as db:
        content = ContentItem(
            user_id=user_id,
            content_type=ContentType.TEXT,
            text_content='Rejected test content',
            status=ContentStatus.REJECTED,
            priority=0
        )
        db.add(content)
        db.commit()
        db.refresh(content)
        return content.id


# Review Endpoints Tests

def test_submit_review_success(client, moderator_session, flagged_content_id):
    """Test submitting review as moderator"""
    response = client.post(
        '/api/moderation/review',
        json={
            'content_id': flagged_content_id,
            'approved': True,
            'notes': 'Looks fine'
        },
        cookies={'session_token': moderator_session}
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert 'review' in data
    assert data['message'] == 'Content approved'


def test_submit_review_reject(client, moderator_session, flagged_content_id):
    """Test rejecting content"""
    response = client.post(
        '/api/moderation/review',
        json={
            'content_id': flagged_content_id,
            'approved': False,
            'category': 'spam',
            'notes': 'This is spam'
        },
        cookies={'session_token': moderator_session}
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['message'] == 'Content rejected'


def test_submit_review_unauthorized(client, user_session, flagged_content_id):
    """Test submitting review as regular user (should fail)"""
    session_token, _ = user_session

    response = client.post(
        '/api/moderation/review',
        json={
            'content_id': flagged_content_id,
            'approved': True
        },
        cookies={'session_token': session_token}
    )

    assert response.status_code == 403


def test_submit_review_invalid_content(client, moderator_session):
    """Test reviewing non-existent content"""
    response = client.post(
        '/api/moderation/review',
        json={
            'content_id': 'invalid-id',
            'approved': True
        },
        cookies={'session_token': moderator_session}
    )

    assert response.status_code == 400


# Appeal Endpoints Tests

def test_create_appeal_success(client, user_session, rejected_content_id):
    """Test creating appeal as content owner"""
    session_token, _ = user_session

    response = client.post(
        '/api/appeals',
        json={
            'content_id': rejected_content_id,
            'reason': 'I believe this was rejected incorrectly'
        },
        cookies={'session_token': session_token}
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert 'appeal_id' in data
    assert data['message'] == 'Appeal submitted successfully'


def test_create_appeal_invalid_content(client, user_session):
    """Test creating appeal for non-existent content"""
    session_token, _ = user_session

    response = client.post(
        '/api/appeals',
        json={
            'content_id': 'invalid-id',
            'reason': 'Test'
        },
        cookies={'session_token': session_token}
    )

    assert response.status_code == 400


def test_list_appeals_as_moderator(client, moderator_session, user_session, rejected_content_id):
    """Test listing appeals as moderator"""
    # Create an appeal first
    session_token, _ = user_session
    client.post(
        '/api/appeals',
        json={
            'content_id': rejected_content_id,
            'reason': 'Test appeal'
        },
        cookies={'session_token': session_token}
    )

    # List appeals as moderator
    response = client.get(
        '/api/appeals',
        cookies={'session_token': moderator_session}
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert 'appeals' in data
    assert len(data['appeals']) >= 1


def test_list_appeals_unauthorized(client, user_session):
    """Test listing appeals as regular user (should fail)"""
    session_token, _ = user_session

    response = client.get(
        '/api/appeals',
        cookies={'session_token': session_token}
    )

    assert response.status_code == 403


def test_review_appeal_approve(client, moderator_session, user_session, rejected_content_id, db_manager):
    """Test approving an appeal"""
    # Create appeal
    session_token, _ = user_session
    create_response = client.post(
        '/api/appeals',
        json={
            'content_id': rejected_content_id,
            'reason': 'Test appeal'
        },
        cookies={'session_token': session_token}
    )
    appeal_id = create_response.json()['appeal_id']

    # Review appeal
    response = client.post(
        f'/api/appeals/{appeal_id}/review',
        json={
            'approved': True,
            'notes': 'Mistake, restoring content'
        },
        cookies={'session_token': moderator_session}
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['message'] == 'Appeal approved'

    # Verify content status
    with db_manager.get_session() as db:
        content = db.query(ContentItem).filter(ContentItem.id == rejected_content_id).first()
        assert content.status == ContentStatus.APPROVED


def test_review_appeal_reject(client, moderator_session, user_session, rejected_content_id, db_manager):
    """Test rejecting an appeal"""
    # Create appeal
    session_token, _ = user_session
    create_response = client.post(
        '/api/appeals',
        json={
            'content_id': rejected_content_id,
            'reason': 'Test appeal'
        },
        cookies={'session_token': session_token}
    )
    appeal_id = create_response.json()['appeal_id']

    # Review appeal
    response = client.post(
        f'/api/appeals/{appeal_id}/review',
        json={
            'approved': False,
            'notes': 'Decision stands'
        },
        cookies={'session_token': moderator_session}
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['message'] == 'Appeal rejected'

    # Verify content still rejected
    with db_manager.get_session() as db:
        content = db.query(ContentItem).filter(ContentItem.id == rejected_content_id).first()
        assert content.status == ContentStatus.REJECTED


# Policy Endpoints Tests

def test_list_policies_as_moderator(client, moderator_session):
    """Test listing policies as moderator"""
    response = client.get(
        '/api/admin/policies',
        cookies={'session_token': moderator_session}
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert 'policies' in data


def test_list_policies_unauthorized(client, user_session):
    """Test listing policies as regular user (should fail)"""
    session_token, _ = user_session

    response = client.get(
        '/api/admin/policies',
        cookies={'session_token': session_token}
    )

    assert response.status_code == 403


def test_create_policy_as_admin(client, admin_session):
    """Test creating policy as admin"""
    response = client.post(
        '/api/admin/policies',
        json={
            'name': 'Test NSFW Policy',
            'category': 'nsfw',
            'auto_reject_threshold': 0.9,
            'flag_review_threshold': 0.5,
            'severity': 8,
            'enabled': True
        },
        cookies={'session_token': admin_session}
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert 'policy' in data
    assert data['policy']['name'] == 'Test NSFW Policy'


def test_create_policy_as_moderator_fails(client, moderator_session):
    """Test that moderators cannot create policies"""
    response = client.post(
        '/api/admin/policies',
        json={
            'name': 'Test Policy',
            'category': 'spam'
        },
        cookies={'session_token': moderator_session}
    )

    assert response.status_code == 403


def test_update_policy_as_admin(client, admin_session, db_manager):
    """Test updating policy as admin"""
    # Create policy first
    with db_manager.get_session() as db:
        policy = Policy(
            name='Update Test',
            category=ViolationCategory.SPAM,
            auto_reject_threshold=0.9,
            flag_review_threshold=0.5,
            severity=5,
            enabled=True
        )
        db.add(policy)
        db.commit()
        db.refresh(policy)
        policy_id = policy.id

    # Update policy
    response = client.patch(
        f'/api/admin/policies/{policy_id}',
        json={
            'auto_reject_threshold': 0.85,
            'severity': 7,
            'enabled': False
        },
        cookies={'session_token': admin_session}
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['policy']['auto_reject_threshold'] == 0.85
    assert data['policy']['severity'] == 7
    assert data['policy']['enabled'] is False


def test_update_policy_invalid_id(client, admin_session):
    """Test updating non-existent policy"""
    response = client.patch(
        '/api/admin/policies/invalid-id',
        json={'severity': 5},
        cookies={'session_token': admin_session}
    )

    assert response.status_code == 400


# Admin Stats Tests

def test_get_admin_stats_as_moderator(client, moderator_session):
    """Test getting admin stats as moderator"""
    response = client.get(
        '/api/admin/stats',
        cookies={'session_token': moderator_session}
    )

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert 'stats' in data
    assert 'content' in data['stats']
    assert 'reviews' in data['stats']
    assert 'users' in data['stats']
    assert 'policies' in data['stats']


def test_get_admin_stats_unauthorized(client, user_session):
    """Test getting admin stats as regular user (should fail)"""
    session_token, _ = user_session

    response = client.get(
        '/api/admin/stats',
        cookies={'session_token': session_token}
    )

    assert response.status_code == 403


# Dashboard Page Test

def test_admin_dashboard_page(client):
    """Test admin dashboard page loads"""
    response = client.get('/admin/dashboard')

    assert response.status_code == 200
    assert b'Admin Dashboard' in response.content


# Integration Flow Tests

def test_full_review_workflow(client, moderator_session, user_session, db_manager):
    """Test complete review workflow"""
    session_token, user_id = user_session

    # 1. Create flagged content
    with db_manager.get_session() as db:
        content = ContentItem(
            user_id=user_id,
            content_type=ContentType.TEXT,
            text_content='Test workflow content',
            status=ContentStatus.FLAGGED,
            priority=5
        )
        db.add(content)
        db.commit()
        db.refresh(content)
        content_id = content.id

    # 2. Get review queue
    queue_response = client.get(
        '/api/moderation/queue',
        cookies={'session_token': moderator_session}
    )
    assert queue_response.status_code == 200
    assert len(queue_response.json()['queue']) >= 1

    # 3. Submit review (reject)
    review_response = client.post(
        '/api/moderation/review',
        json={
            'content_id': content_id,
            'approved': False,
            'category': 'spam',
            'notes': 'This is spam'
        },
        cookies={'session_token': moderator_session}
    )
    assert review_response.status_code == 200

    # 4. User creates appeal
    appeal_response = client.post(
        '/api/appeals',
        json={
            'content_id': content_id,
            'reason': 'Not spam, please review again'
        },
        cookies={'session_token': session_token}
    )
    assert appeal_response.status_code == 200
    appeal_id = appeal_response.json()['appeal_id']

    # 5. Moderator reviews appeal (approve)
    appeal_review_response = client.post(
        f'/api/appeals/{appeal_id}/review',
        json={
            'approved': True,
            'notes': 'You are right, restoring'
        },
        cookies={'session_token': moderator_session}
    )
    assert appeal_review_response.status_code == 200

    # 6. Verify final content status
    with db_manager.get_session() as db:
        final_content = db.query(ContentItem).filter(ContentItem.id == content_id).first()
        assert final_content.status == ContentStatus.APPROVED


def test_full_policy_workflow(client, admin_session, moderator_session):
    """Test complete policy management workflow"""
    # 1. Create policy
    create_response = client.post(
        '/api/admin/policies',
        json={
            'name': 'Workflow Test Policy',
            'category': 'hate_speech',
            'auto_reject_threshold': 0.95,
            'flag_review_threshold': 0.6,
            'severity': 9,
            'enabled': True
        },
        cookies={'session_token': admin_session}
    )
    assert create_response.status_code == 200
    policy_id = create_response.json()['policy']['id']

    # 2. List policies (moderator can see)
    list_response = client.get(
        '/api/admin/policies',
        cookies={'session_token': moderator_session}
    )
    assert list_response.status_code == 200
    policies = list_response.json()['policies']
    assert any(p['id'] == policy_id for p in policies)

    # 3. Update policy
    update_response = client.patch(
        f'/api/admin/policies/{policy_id}',
        json={
            'severity': 10,
            'enabled': False
        },
        cookies={'session_token': admin_session}
    )
    assert update_response.status_code == 200
    assert update_response.json()['policy']['severity'] == 10
    assert update_response.json()['policy']['enabled'] is False

    # 4. List enabled policies only (should not include disabled)
    enabled_response = client.get(
        '/api/admin/policies?enabled_only=true',
        cookies={'session_token': moderator_session}
    )
    assert enabled_response.status_code == 200
    enabled_policies = enabled_response.json()['policies']
    assert not any(p['id'] == policy_id for p in enabled_policies)
