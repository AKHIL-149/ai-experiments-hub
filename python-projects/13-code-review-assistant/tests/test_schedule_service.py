"""
Tests for schedule service
"""

import pytest
from datetime import datetime, timedelta, timezone
from src.core.database import DatabaseManager, Repository, User, AnalysisSchedule, ScheduledRun
from src.services.schedule_service import ScheduleService


@pytest.fixture
def db_manager():
    """Create a test database manager."""
    return DatabaseManager("sqlite:///:memory:")


@pytest.fixture
def session(db_manager):
    """Create a test database session."""
    with db_manager.get_session() as session:
        yield session


@pytest.fixture
def test_user(session):
    """Create a test user."""
    user = User(
        username="testuser",
        email="test@example.com",
        password_hash="hashed_password"
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


@pytest.fixture
def test_repository(session, test_user):
    """Create a test repository."""
    repo = Repository(
        name="test-repo",
        github_url="https://github.com/test/repo",
        clone_path="/tmp/test-repo",
        user_id=test_user.id,
        status="ready"
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)
    return repo


class TestScheduleService:
    """Tests for ScheduleService."""

    def test_create_daily_schedule(self, session, test_user, test_repository):
        """Test creating a daily schedule."""
        service = ScheduleService(session)

        schedule = service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Daily Security Scan",
            schedule_type="daily",
            description="Run security scan daily"
        )

        assert schedule['name'] == "Daily Security Scan"
        assert schedule['schedule_type'] == "daily"
        assert schedule['cron_expression'] == "0 0 * * *"
        assert schedule['enabled'] is True
        assert schedule['next_run_at'] is not None

    def test_create_weekly_schedule(self, session, test_user, test_repository):
        """Test creating a weekly schedule."""
        service = ScheduleService(session)

        schedule = service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Weekly Full Scan",
            schedule_type="weekly"
        )

        assert schedule['schedule_type'] == "weekly"
        assert schedule['cron_expression'] == "0 0 * * 0"

    def test_create_interval_schedule(self, session, test_user, test_repository):
        """Test creating an interval schedule."""
        service = ScheduleService(session)

        schedule = service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Hourly Scan",
            schedule_type="interval",
            interval_minutes=60
        )

        assert schedule['schedule_type'] == "interval"
        assert schedule['interval_minutes'] == 60
        assert schedule['next_run_at'] is not None

    def test_create_cron_schedule(self, session, test_user, test_repository):
        """Test creating a cron schedule."""
        service = ScheduleService(session)

        schedule = service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Custom Schedule",
            schedule_type="cron",
            cron_expression="0 */6 * * *"  # Every 6 hours
        )

        assert schedule['schedule_type'] == "cron"
        assert schedule['cron_expression'] == "0 */6 * * *"

    def test_create_schedule_with_notifications(self, session, test_user, test_repository):
        """Test creating a schedule with notification settings."""
        service = ScheduleService(session)

        schedule = service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Notify Scan",
            schedule_type="daily",
            notify_on_completion=True,
            notify_on_issues=True,
            notification_emails=["admin@example.com", "dev@example.com"],
            slack_webhook_url="https://hooks.slack.com/test"
        )

        assert schedule['notify_on_completion'] is True
        assert schedule['notify_on_issues'] is True
        assert len(schedule['notification_emails']) == 2
        assert schedule['slack_webhook_url'] == "https://hooks.slack.com/test"

    def test_create_schedule_invalid_cron(self, session, test_user, test_repository):
        """Test creating a schedule with invalid cron expression."""
        service = ScheduleService(session)

        with pytest.raises(ValueError, match="Invalid cron expression"):
            service.create_schedule(
                repository_id=test_repository.id,
                user_id=test_user.id,
                name="Bad Cron",
                schedule_type="cron",
                cron_expression="invalid cron"
            )

    def test_create_schedule_missing_interval(self, session, test_user, test_repository):
        """Test creating interval schedule without interval_minutes."""
        service = ScheduleService(session)

        with pytest.raises(ValueError, match="Interval minutes must be"):
            service.create_schedule(
                repository_id=test_repository.id,
                user_id=test_user.id,
                name="Bad Interval",
                schedule_type="interval"
            )

    def test_create_schedule_invalid_repository(self, session, test_user):
        """Test creating schedule for non-existent repository."""
        service = ScheduleService(session)

        with pytest.raises(ValueError, match="Repository not found"):
            service.create_schedule(
                repository_id="invalid-id",
                user_id=test_user.id,
                name="Bad Repo",
                schedule_type="daily"
            )

    def test_get_schedule(self, session, test_user, test_repository):
        """Test getting a schedule by ID."""
        service = ScheduleService(session)

        # Create schedule
        created = service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Test Schedule",
            schedule_type="daily"
        )

        # Get schedule
        schedule = service.get_schedule(created['id'], user_id=test_user.id)

        assert schedule is not None
        assert schedule['id'] == created['id']
        assert schedule['name'] == "Test Schedule"

    def test_get_schedule_not_found(self, session, test_user):
        """Test getting a non-existent schedule."""
        service = ScheduleService(session)
        schedule = service.get_schedule("invalid-id", user_id=test_user.id)
        assert schedule is None

    def test_list_schedules(self, session, test_user, test_repository):
        """Test listing schedules."""
        service = ScheduleService(session)

        # Create multiple schedules
        service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Schedule 1",
            schedule_type="daily"
        )
        service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Schedule 2",
            schedule_type="weekly"
        )

        # List all schedules
        schedules = service.list_schedules(user_id=test_user.id)

        assert len(schedules) == 2
        assert schedules[0]['name'] in ["Schedule 1", "Schedule 2"]

    def test_list_schedules_by_repository(self, session, test_user, test_repository):
        """Test listing schedules filtered by repository."""
        service = ScheduleService(session)

        # Create schedule
        service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Repo Schedule",
            schedule_type="daily"
        )

        # List by repository
        schedules = service.list_schedules(
            user_id=test_user.id,
            repository_id=test_repository.id
        )

        assert len(schedules) == 1
        assert schedules[0]['repository_id'] == test_repository.id

    def test_list_schedules_enabled_only(self, session, test_user, test_repository):
        """Test listing only enabled schedules."""
        service = ScheduleService(session)

        # Create enabled and disabled schedules
        schedule1 = service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Enabled",
            schedule_type="daily"
        )
        schedule2 = service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Disabled",
            schedule_type="daily"
        )

        # Disable second schedule
        service.update_schedule(schedule2['id'], test_user.id, enabled=False)

        # List enabled only
        schedules = service.list_schedules(user_id=test_user.id, enabled_only=True)

        assert len(schedules) == 1
        assert schedules[0]['name'] == "Enabled"

    def test_update_schedule(self, session, test_user, test_repository):
        """Test updating a schedule."""
        service = ScheduleService(session)

        # Create schedule
        schedule = service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Original Name",
            schedule_type="daily"
        )

        # Update schedule
        updated = service.update_schedule(
            schedule['id'],
            test_user.id,
            name="Updated Name",
            description="New description"
        )

        assert updated['name'] == "Updated Name"
        assert updated['description'] == "New description"

    def test_delete_schedule(self, session, test_user, test_repository):
        """Test deleting a schedule."""
        service = ScheduleService(session)

        # Create schedule
        schedule = service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="To Delete",
            schedule_type="daily"
        )

        # Delete schedule
        result = service.delete_schedule(schedule['id'], test_user.id)

        assert result['message'] == 'Schedule deleted successfully'

        # Verify deleted
        deleted = service.get_schedule(schedule['id'], user_id=test_user.id)
        assert deleted is None

    def test_toggle_schedule(self, session, test_user, test_repository):
        """Test toggling schedule enabled status."""
        service = ScheduleService(session)

        # Create enabled schedule
        schedule = service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Toggle Test",
            schedule_type="daily"
        )

        assert schedule['enabled'] is True

        # Disable
        toggled = service.toggle_schedule(schedule['id'], test_user.id, False)
        assert toggled['enabled'] is False

        # Enable
        toggled = service.toggle_schedule(schedule['id'], test_user.id, True)
        assert toggled['enabled'] is True

    def test_trigger_schedule(self, session, test_user, test_repository):
        """Test manually triggering a schedule."""
        service = ScheduleService(session)

        # Create schedule
        schedule = service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Trigger Test",
            schedule_type="daily"
        )

        # Trigger schedule
        run = service.trigger_schedule(schedule['id'], test_user.id)

        assert run['schedule_id'] == schedule['id']
        assert run['status'] == 'pending'

    def test_get_due_schedules(self, session, test_user, test_repository):
        """Test getting due schedules."""
        service = ScheduleService(session)

        # Create schedule with next_run_at in the past
        schedule = service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Due Schedule",
            schedule_type="daily"
        )

        # Update next_run_at to past
        db_schedule = session.query(AnalysisSchedule).filter_by(id=schedule['id']).first()
        db_schedule.next_run_at = datetime.now(timezone.utc) - timedelta(hours=1)
        session.commit()

        # Get due schedules
        due_schedules = service.get_due_schedules()

        assert len(due_schedules) >= 1
        assert any(s['id'] == schedule['id'] for s in due_schedules)

    def test_update_run_status(self, session, test_user, test_repository):
        """Test updating run status."""
        service = ScheduleService(session)

        # Create schedule and run
        schedule = service.create_schedule(
            repository_id=test_repository.id,
            user_id=test_user.id,
            name="Run Test",
            schedule_type="daily"
        )
        run = service.trigger_schedule(schedule['id'], test_user.id)

        # Update run to running
        updated = service.update_run_status(
            run['id'],
            'running',
            started_at=datetime.now(timezone.utc)
        )

        assert updated['status'] == 'running'
        assert updated['started_at'] is not None

        # Update run to completed
        updated = service.update_run_status(
            run['id'],
            'completed',
            files_analyzed=10,
            issues_found=5,
            critical_issues=1,
            error_issues=2,
            warning_issues=2,
            info_issues=0
        )

        assert updated['status'] == 'completed'
        assert updated['files_analyzed'] == 10
        assert updated['issues_found'] == 5
        assert updated['duration_seconds'] is not None
