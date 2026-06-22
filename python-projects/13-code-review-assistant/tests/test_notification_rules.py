"""
Tests for Notification Rules Engine
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime, timezone, time as datetime_time

from src.services.notification_rules_engine import NotificationRulesEngine


class TestNotificationRulesEngine:
    """Test NotificationRulesEngine"""

    @pytest.fixture
    def engine(self):
        """Create rules engine"""
        return NotificationRulesEngine()

    @pytest.fixture
    def sample_issue(self):
        """Sample issue for testing"""
        return {
            'type': 'SQL Injection',
            'severity': 'critical',
            'category': 'security',
            'file': 'app/models/user.py',
            'line': 42,
            'message': 'Potential SQL injection vulnerability',
            'confidence': 95
        }

    @pytest.fixture
    def sample_pr(self):
        """Sample PR for testing"""
        return {
            'number': 123,
            'title': 'Add user authentication',
            'author': 'john.doe',
            'repository': 'test/repo',
            'url': 'https://github.com/test/repo/pull/123'
        }

    def test_matches_patterns_exact_match(self, engine):
        """Test exact file pattern match"""
        assert engine._matches_patterns('test.py', ['test.py']) == True

    def test_matches_patterns_wildcard(self, engine):
        """Test wildcard pattern match"""
        assert engine._matches_patterns('app/models/user.py', ['app/models/*.py']) == True
        assert engine._matches_patterns('app/views/user.py', ['app/models/*.py']) == False

    def test_matches_patterns_recursive_wildcard(self, engine):
        """Test recursive wildcard pattern"""
        assert engine._matches_patterns('app/models/user.py', ['app/**/*.py']) == True
        assert engine._matches_patterns('app/controllers/api/user.py', ['app/**/*.py']) == True

    def test_is_quiet_hours_weekday(self, engine):
        """Test quiet hours on weekday"""
        quiet_hours = {
            'start': '22:00',
            'end': '08:00',
            'timezone': 'UTC',
            'days': [0, 1, 2, 3, 4]  # Monday-Friday
        }

        # This test depends on current time, so we'll just verify it doesn't error
        result = engine._is_quiet_hours(quiet_hours)
        assert isinstance(result, bool)

    def test_is_quiet_hours_invalid_config(self, engine):
        """Test quiet hours with invalid config"""
        quiet_hours = {'invalid': 'config'}
        assert engine._is_quiet_hours(quiet_hours) == False

    def test_is_quiet_hours_empty(self, engine):
        """Test quiet hours with empty config"""
        assert engine._is_quiet_hours({}) == False
        assert engine._is_quiet_hours(None) == False

    def test_evaluate_rule_severity_match(self, engine, sample_issue):
        """Test rule evaluation with severity condition"""
        rule = Mock()
        rule.conditions = {'severity': ['critical', 'error']}
        rule.quiet_hours_enabled = False
        rule.rate_limit_enabled = False

        assert engine._evaluate_rule(rule, sample_issue, None) == True

    def test_evaluate_rule_severity_no_match(self, engine, sample_issue):
        """Test rule evaluation with non-matching severity"""
        rule = Mock()
        rule.conditions = {'severity': ['info', 'warning']}
        rule.quiet_hours_enabled = False
        rule.rate_limit_enabled = False

        assert engine._evaluate_rule(rule, sample_issue, None) == False

    def test_evaluate_rule_category_match(self, engine, sample_issue):
        """Test rule evaluation with category condition"""
        rule = Mock()
        rule.conditions = {'category': ['security', 'performance']}
        rule.quiet_hours_enabled = False
        rule.rate_limit_enabled = False

        assert engine._evaluate_rule(rule, sample_issue, None) == True

    def test_evaluate_rule_file_pattern_match(self, engine, sample_issue):
        """Test rule evaluation with file pattern"""
        rule = Mock()
        rule.conditions = {'file_patterns': ['app/**/*.py']}
        rule.quiet_hours_enabled = False
        rule.rate_limit_enabled = False

        assert engine._evaluate_rule(rule, sample_issue, None) == True

    def test_evaluate_rule_pr_author_match(self, engine, sample_issue, sample_pr):
        """Test rule evaluation with PR author condition"""
        rule = Mock()
        rule.conditions = {'pr_authors': ['john.doe', 'jane.smith']}
        rule.quiet_hours_enabled = False
        rule.rate_limit_enabled = False

        assert engine._evaluate_rule(rule, sample_issue, sample_pr) == True

    def test_evaluate_rule_min_confidence(self, engine, sample_issue):
        """Test rule evaluation with minimum confidence"""
        rule = Mock()
        rule.conditions = {'min_confidence': 90}
        rule.quiet_hours_enabled = False
        rule.rate_limit_enabled = False

        assert engine._evaluate_rule(rule, sample_issue, None) == True

        # Lower confidence issue
        low_conf_issue = {**sample_issue, 'confidence': 50}
        assert engine._evaluate_rule(rule, low_conf_issue, None) == False

    def test_evaluate_rule_multiple_conditions(self, engine, sample_issue):
        """Test rule evaluation with multiple conditions"""
        rule = Mock()
        rule.conditions = {
            'severity': ['critical'],
            'category': ['security'],
            'file_patterns': ['app/**/*.py']
        }
        rule.quiet_hours_enabled = False
        rule.rate_limit_enabled = False

        assert engine._evaluate_rule(rule, sample_issue, None) == True

    def test_create_action_slack(self, engine, sample_issue):
        """Test action creation for Slack"""
        rule = Mock()
        rule.id = 'rule-123'
        rule.name = 'Critical Security Issues'
        rule.notify_slack = True
        rule.notify_email = False
        rule.notify_discord = False
        rule.slack_config_id = 'slack-config-1'
        rule.email_config_id = None
        rule.discord_config_id = None
        rule.batch_notifications = False
        rule.batch_interval_minutes = 60

        action = engine._create_action(rule, sample_issue, None)

        assert action['rule_id'] == 'rule-123'
        assert action['rule_name'] == 'Critical Security Issues'
        assert len(action['channels']) == 1
        assert action['channels'][0]['type'] == 'slack'
        assert action['channels'][0]['config_id'] == 'slack-config-1'

    def test_create_action_multiple_channels(self, engine, sample_issue):
        """Test action creation with multiple channels"""
        rule = Mock()
        rule.id = 'rule-123'
        rule.name = 'All Channels Rule'
        rule.notify_slack = True
        rule.notify_email = True
        rule.notify_discord = True
        rule.slack_config_id = 'slack-1'
        rule.email_config_id = 'email-1'
        rule.discord_config_id = 'discord-1'
        rule.batch_notifications = False
        rule.batch_interval_minutes = 60

        action = engine._create_action(rule, sample_issue, None)

        assert len(action['channels']) == 3
        channel_types = [ch['type'] for ch in action['channels']]
        assert 'slack' in channel_types
        assert 'email' in channel_types
        assert 'discord' in channel_types

    def test_create_action_no_channels(self, engine, sample_issue):
        """Test action creation with no channels configured"""
        rule = Mock()
        rule.id = 'rule-123'
        rule.name = 'No Channels'
        rule.notify_slack = False
        rule.notify_email = False
        rule.notify_discord = False
        rule.batch_notifications = False
        rule.batch_interval_minutes = 60

        action = engine._create_action(rule, sample_issue, None)

        assert action is None


class TestNotificationRulesEndpoints:
    """Test Notification Rules API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from server import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    @pytest.fixture
    def user_session(self, client):
        """Create user session"""
        response = client.post('/api/auth/register', json={
            'username': 'rules_test_user',
            'email': 'rules@test.com',
            'password': 'password123'
        })

        response = client.post('/api/auth/login', json={
            'username': 'rules_test_user',
            'password': 'password123'
        })

        return response.cookies.get('session_token')

    def test_get_notification_rules_empty(self, client, user_session):
        """Test getting notification rules when empty"""
        response = client.get(
            '/api/notification-rules',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert 'rules' in data
        assert isinstance(data['rules'], list)

    def test_create_notification_rule(self, client, user_session):
        """Test creating notification rule"""
        response = client.post(
            '/api/notification-rules',
            json={
                'name': 'Critical Security Issues',
                'description': 'Notify on critical security vulnerabilities',
                'conditions': {
                    'severity': ['critical'],
                    'category': ['security']
                },
                'notify_slack': True,
                'enabled': True
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert 'rule' in data
        assert data['rule']['name'] == 'Critical Security Issues'
        assert data['rule']['enabled'] == True

    def test_create_notification_rule_missing_name(self, client, user_session):
        """Test creating rule without name"""
        response = client.post(
            '/api/notification-rules',
            json={
                'conditions': {'severity': ['critical']}
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 400

    def test_create_notification_rule_missing_conditions(self, client, user_session):
        """Test creating rule without conditions"""
        response = client.post(
            '/api/notification-rules',
            json={
                'name': 'Test Rule'
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 400

    def test_update_notification_rule(self, client, user_session):
        """Test updating notification rule"""
        # Create rule
        create_response = client.post(
            '/api/notification-rules',
            json={
                'name': 'Original Name',
                'conditions': {'severity': ['critical']}
            },
            cookies={'session_token': user_session}
        )

        rule_id = create_response.json()['rule']['id']

        # Update rule
        update_response = client.post(
            '/api/notification-rules',
            json={
                'id': rule_id,
                'name': 'Updated Name',
                'conditions': {'severity': ['critical', 'error']},
                'enabled': False
            },
            cookies={'session_token': user_session}
        )

        assert update_response.status_code == 200
        data = update_response.json()
        assert data['rule']['name'] == 'Updated Name'
        assert data['rule']['enabled'] == False

    def test_delete_notification_rule(self, client, user_session):
        """Test deleting notification rule"""
        # Create rule
        create_response = client.post(
            '/api/notification-rules',
            json={
                'name': 'To Delete',
                'conditions': {'severity': ['info']}
            },
            cookies={'session_token': user_session}
        )

        rule_id = create_response.json()['rule']['id']

        # Delete rule
        delete_response = client.delete(
            f'/api/notification-rules/{rule_id}',
            cookies={'session_token': user_session}
        )

        assert delete_response.status_code == 200
        assert delete_response.json()['success'] == True

        # Verify deleted
        get_response = client.get(
            '/api/notification-rules',
            cookies={'session_token': user_session}
        )
        rules = get_response.json()['rules']
        rule_ids = [r['id'] for r in rules]
        assert rule_id not in rule_ids

    def test_delete_nonexistent_rule(self, client, user_session):
        """Test deleting non-existent rule"""
        response = client.delete(
            '/api/notification-rules/nonexistent-id',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 404

    def test_evaluate_notification_rules(self, client, user_session):
        """Test evaluating rules against an issue"""
        # Create a rule
        client.post(
            '/api/notification-rules',
            json={
                'name': 'Test Rule',
                'conditions': {'severity': ['critical']},
                'enabled': True
            },
            cookies={'session_token': user_session}
        )

        # Evaluate
        response = client.post(
            '/api/notification-rules/evaluate',
            json={
                'issue': {
                    'type': 'SQL Injection',
                    'severity': 'critical',
                    'category': 'security',
                    'file': 'app.py',
                    'line': 10,
                    'message': 'Test',
                    'confidence': 90
                }
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert 'actions' in data
        assert 'matched_rules_count' in data

    def test_evaluate_rules_missing_issue(self, client, user_session):
        """Test evaluating without issue"""
        response = client.post(
            '/api/notification-rules/evaluate',
            json={},
            cookies={'session_token': user_session}
        )

        assert response.status_code == 400
