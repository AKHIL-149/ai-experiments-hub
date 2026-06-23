"""
Basic tests for team management (simplified for current API)
"""

import pytest
import uuid
from src.core.database import DatabaseManager, User
from src.services.team_service import TeamService


@pytest.fixture
def test_user():
    """Create a test user with unique ID."""
    db_manager = DatabaseManager()
    with db_manager.get_session() as session:
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"testuser_{unique_id}",
            email=f"test_{unique_id}@example.com",
            password_hash="hashed_password"
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


@pytest.fixture
def test_user2():
    """Create a second test user with unique ID."""
    db_manager = DatabaseManager()
    with db_manager.get_session() as session:
        unique_id = str(uuid.uuid4())[:8]
        user = User(
            username=f"testuser2_{unique_id}",
            email=f"test2_{unique_id}@example.com",
            password_hash="hashed_password"
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def test_create_team(test_user):
    """Test creating a team."""
    service = TeamService()
    unique_id = str(uuid.uuid4())[:8]

    result = service.create_team(
        name="My Team",
        slug=f"my-team-{unique_id}",
        user_id=test_user.id,
        description="Test description"
    )

    assert result['success'] is True
    assert result['team']['name'] == "My Team"
    assert result['membership']['role'] == 'owner'


def test_get_team(test_user):
    """Test getting a team."""
    service = TeamService()
    unique_id = str(uuid.uuid4())[:8]

    # Create team
    create_result = service.create_team("Test Team", f"test-team-{unique_id}", test_user.id)
    team_id = create_result['team']['id']

    # Get team
    team = service.get_team(team_id, user_id=test_user.id)

    assert team is not None
    assert team['name'] == "Test Team"


def test_get_user_teams(test_user):
    """Test getting all teams for a user."""
    service = TeamService()
    unique_id = str(uuid.uuid4())[:8]

    # Create multiple teams
    service.create_team("Team 1", f"team-1-{unique_id}", test_user.id)
    service.create_team("Team 2", f"team-2-{unique_id}", test_user.id)

    teams = service.get_user_teams(test_user.id)

    assert len(teams) >= 2


def test_add_member(test_user, test_user2):
    """Test adding a member to team."""
    service = TeamService()
    unique_id = str(uuid.uuid4())[:8]

    # Create team
    create_result = service.create_team("Test Team", f"test-team-members-{unique_id}", test_user.id)
    team_id = create_result['team']['id']

    # Add member
    result = service.add_member(team_id, test_user2.id, test_user.id, role='member')

    assert result['success'] is True
    assert result['member']['role'] == 'member'


def test_get_team_members(test_user):
    """Test getting team members."""
    service = TeamService()
    unique_id = str(uuid.uuid4())[:8]

    # Create team
    create_result = service.create_team("Test Team", f"test-team-list-{unique_id}", test_user.id)
    team_id = create_result['team']['id']

    # Get members
    members = service.get_team_members(team_id)

    assert len(members) == 1
    assert members[0]['role'] == 'owner'


def test_update_team(test_user):
    """Test updating team settings."""
    service = TeamService()
    unique_id = str(uuid.uuid4())[:8]

    # Create team
    create_result = service.create_team("Original Name", f"test-update-{unique_id}", test_user.id)
    team_id = create_result['team']['id']

    # Update
    result = service.update_team(team_id, test_user.id, name="Updated Name")

    assert result['success'] is True
    assert result['team']['name'] == "Updated Name"


def test_create_invitation(test_user):
    """Test creating an invitation."""
    service = TeamService()
    unique_id = str(uuid.uuid4())[:8]

    # Create team
    create_result = service.create_team("Test Team", f"test-invite-{unique_id}", test_user.id)
    team_id = create_result['team']['id']

    # Create invitation
    result = service.create_invitation(
        team_id,
        test_user.id,
        email=f"newuser_{unique_id}@example.com"
    )

    assert result['success'] is True
    assert f"newuser_{unique_id}@example.com" in result['invitation']['email']
    assert result['invitation']['token'] is not None


def test_check_permission_owner(test_user):
    """Test owner has all permissions."""
    service = TeamService()
    unique_id = str(uuid.uuid4())[:8]

    # Create team
    create_result = service.create_team("Test Team", f"test-perms-{unique_id}", test_user.id)
    team_id = create_result['team']['id']

    # Check permissions
    assert service.check_permission(team_id, test_user.id, 'can_manage_members')
    assert service.check_permission(team_id, test_user.id, 'can_create_rules')


def test_check_permission_member(test_user, test_user2):
    """Test member permissions."""
    service = TeamService()
    unique_id = str(uuid.uuid4())[:8]

    # Create team
    create_result = service.create_team("Test Team", f"test-member-perms-{unique_id}", test_user.id)
    team_id = create_result['team']['id']

    # Add as member
    service.add_member(team_id, test_user2.id, test_user.id, role='member')

    # Check permissions
    assert not service.check_permission(team_id, test_user2.id, 'can_manage_members')
    assert service.check_permission(team_id, test_user2.id, 'can_create_rules')


def test_delete_team(test_user):
    """Test deleting a team."""
    service = TeamService()
    unique_id = str(uuid.uuid4())[:8]

    # Create team
    create_result = service.create_team("To Delete", f"test-delete-{unique_id}", test_user.id)
    team_id = create_result['team']['id']

    # Delete
    result = service.delete_team(team_id, test_user.id)

    assert result['success'] is True
