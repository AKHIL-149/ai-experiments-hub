"""
Unit tests for Phase 5 - Production Features

Tests:
- Analytics endpoints (usage, costs, sources, performance)
- Cost tracking integration
- Export formats (PDF, DOCX)
- Session cost breakdown
"""

import pytest
from fastapi.testclient import TestClient
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import app, db_manager
from src.core.database import User
from src.utils.cost_tracker import CostTracker
from src.utils.usage_analytics import UsageAnalytics

# Clean up test users before running tests
@pytest.fixture(scope="session", autouse=True)
def cleanup_database():
    """Clean up test users before running tests."""
    with db_manager.get_session() as db_session:
        # Delete test users from previous runs
        test_usernames = [
            'phase5_user',
            'analytics_user',
            'cost_test_user'
        ]
        db_session.query(User).filter(User.username.in_(test_usernames)).delete(synchronize_session=False)
        db_session.commit()
    yield

# Test client
client = TestClient(app)


class TestAnalyticsEndpoints:
    """Test analytics API endpoints."""

    @pytest.fixture
    def authenticated_client(self):
        """Create authenticated client."""
        # Register and login
        client.post("/api/auth/register", json={
            "username": "analytics_user",
            "email": "analytics@example.com",
            "password": "password123"
        })

        login_response = client.post("/api/auth/login", json={
            "username": "analytics_user",
            "password": "password123"
        })

        return login_response.cookies

    def test_get_usage_stats(self, authenticated_client):
        """Test getting usage statistics."""
        response = client.get("/api/analytics/usage?days=30", cookies=authenticated_client)

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert 'user_id' in data
        assert 'period_days' in data
        assert 'total_queries' in data
        assert 'completed_queries' in data
        assert 'success_rate' in data
        assert 'avg_sources_per_query' in data

    def test_get_usage_stats_unauthenticated(self):
        """Test that usage stats require authentication."""
        # Use fresh client to ensure no cookies from previous tests
        fresh_client = TestClient(app)
        response = fresh_client.get("/api/analytics/usage")

        assert response.status_code == 401

    def test_get_cost_analysis(self, authenticated_client):
        """Test getting cost analysis."""
        response = client.get("/api/analytics/costs?days=30", cookies=authenticated_client)

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert 'user_id' in data
        assert 'period_days' in data
        assert 'total_queries' in data
        assert 'estimated_cost_per_query' in data
        assert 'estimated_total_cost' in data

    def test_get_source_effectiveness(self, authenticated_client):
        """Test getting source effectiveness analysis."""
        response = client.get("/api/analytics/sources?days=30", cookies=authenticated_client)

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert 'user_id' in data
        assert 'period_days' in data
        assert 'source_statistics' in data

    def test_get_performance_metrics(self, authenticated_client):
        """Test getting performance metrics."""
        response = client.get("/api/analytics/performance?days=30", cookies=authenticated_client)

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert 'period_days' in data
        assert 'total_queries' in data
        assert 'success_rate' in data
        assert 'avg_processing_time_seconds' in data

    def test_get_session_costs(self, authenticated_client):
        """Test getting session cost breakdown."""
        response = client.get("/api/analytics/session-costs", cookies=authenticated_client)

        assert response.status_code == 200
        data = response.json()

        # Check structure
        assert 'total_cost' in data
        assert 'total_calls' in data
        assert 'by_provider' in data
        assert 'by_service' in data


class TestCostTracker:
    """Test cost tracking functionality."""

    def test_track_llm_call_ollama(self):
        """Test tracking Ollama (free) LLM call."""
        tracker = CostTracker()

        record = tracker.track_llm_call(
            provider='ollama',
            model='llama3.2:3b',
            input_tokens=1000,
            output_tokens=500
        )

        assert record['provider'] == 'ollama'
        assert record['total_cost'] == 0.0  # Local, free
        assert record['input_tokens'] == 1000
        assert record['output_tokens'] == 500

    def test_track_llm_call_openai(self):
        """Test tracking OpenAI LLM call."""
        tracker = CostTracker()

        record = tracker.track_llm_call(
            provider='openai',
            model='gpt-4',
            input_tokens=1000,
            output_tokens=500
        )

        assert record['provider'] == 'openai'
        assert record['total_cost'] > 0  # Should have cost
        assert record['input_cost'] > 0
        assert record['output_cost'] > 0

    def test_track_llm_call_anthropic(self):
        """Test tracking Anthropic LLM call."""
        tracker = CostTracker()

        record = tracker.track_llm_call(
            provider='anthropic',
            model='claude-3-5-sonnet-20241022',
            input_tokens=1000,
            output_tokens=500
        )

        assert record['provider'] == 'anthropic'
        assert record['total_cost'] > 0
        assert record['model'] == 'claude-3-5-sonnet-20241022'

    def test_session_total(self):
        """Test session total cost calculation."""
        tracker = CostTracker()

        # Track multiple calls
        tracker.track_llm_call('ollama', 'llama3.2:3b', 1000, 500)
        tracker.track_llm_call('openai', 'gpt-4', 1000, 500)
        tracker.track_llm_call('anthropic', 'claude-3-5-sonnet', 1000, 500)

        total = tracker.get_session_total()
        assert total > 0  # Should have cost from OpenAI and Anthropic

    def test_session_breakdown(self):
        """Test session cost breakdown."""
        tracker = CostTracker()

        tracker.track_llm_call('ollama', 'llama3.2:3b', 1000, 500)
        tracker.track_llm_call('openai', 'gpt-4', 1000, 500)

        breakdown = tracker.get_session_breakdown()

        assert 'total_cost' in breakdown
        assert 'total_calls' in breakdown
        assert breakdown['total_calls'] == 2
        assert 'by_provider' in breakdown
        assert 'ollama' in breakdown['by_provider']
        assert 'openai' in breakdown['by_provider']

    def test_estimate_research_cost(self):
        """Test research cost estimation."""
        tracker = CostTracker()

        estimate = tracker.estimate_research_cost(
            provider='openai',
            model='gpt-4',
            num_sources=20,
            avg_source_length=2000
        )

        assert 'estimated_total_cost' in estimate
        assert 'estimated_input_tokens' in estimate
        assert 'estimated_output_tokens' in estimate
        assert estimate['estimated_total_cost'] > 0


class TestUsageAnalytics:
    """Test usage analytics functionality."""

    def test_get_user_stats(self):
        """Test getting user statistics."""
        analytics = UsageAnalytics(db_manager)

        # Create test user
        with db_manager.get_session() as session:
            from src.core.auth_manager import AuthManager
            auth = AuthManager()

            # Register user if not exists
            success, user, error = auth.register_user(
                session,
                username='phase5_user',
                email='phase5@example.com',
                password='password123'
            )

            if success:
                user_id = user.id
            else:
                # User already exists, get it
                user = session.query(User).filter_by(username='phase5_user').first()
                user_id = user.id

        stats = analytics.get_user_stats(user_id, days=30)

        assert 'user_id' in stats
        assert 'total_queries' in stats
        assert 'success_rate' in stats
        assert 'avg_sources_per_query' in stats

    def test_get_performance_metrics(self):
        """Test getting performance metrics."""
        analytics = UsageAnalytics(db_manager)

        metrics = analytics.get_performance_metrics(days=30)

        assert 'period_days' in metrics
        assert 'total_queries' in metrics
        assert 'success_rate' in metrics
        assert 'avg_processing_time_seconds' in metrics


class TestExportFormats:
    """Test export format generation."""

    def test_markdown_export_available(self):
        """Test that Markdown export is available."""
        from src.utils.report_generator import ReportGenerator

        gen = ReportGenerator()
        info = gen.get_info()

        assert 'markdown' in info['supported_formats']

    def test_html_export_available(self):
        """Test that HTML export is available."""
        from src.utils.report_generator import ReportGenerator

        gen = ReportGenerator()
        info = gen.get_info()

        assert 'html' in info['supported_formats']

    def test_json_export_available(self):
        """Test that JSON export is available."""
        from src.utils.report_generator import ReportGenerator

        gen = ReportGenerator()
        info = gen.get_info()

        assert 'json' in info['supported_formats']

    def test_pdf_export_check(self):
        """Test PDF export availability check."""
        from src.utils.report_generator import ReportGenerator

        gen = ReportGenerator()
        info = gen.get_info()

        # PDF might not be available in test environment
        assert 'pdf_available' in info

    def test_docx_export_check(self):
        """Test DOCX export availability check."""
        from src.utils.report_generator import ReportGenerator

        gen = ReportGenerator()
        info = gen.get_info()

        # DOCX might not be available in test environment
        assert 'docx_available' in info


class TestHealthEndpoint:
    """Test health check includes Phase 5 info."""

    def test_health_check(self):
        """Test health check response."""
        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()

        assert data['status'] == 'ok'
        assert 'database' in data
        assert 'cache_enabled' in data
        assert 'llm_provider' in data
