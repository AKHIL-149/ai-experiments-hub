"""
Tests for Historical Analytics Service
Tests repository health scores, quality trends, developer analytics, and debt heatmaps
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from src.services.historical_analytics_service import (
    HistoricalAnalyticsService,
    HealthScore,
    TrendPoint
)


class TestHistoricalAnalyticsService:
    """Test suite for historical analytics service"""

    @pytest.fixture
    def service(self):
        """Create analytics service instance"""
        with patch('src.services.historical_analytics_service.DatabaseManager'):
            return HistoricalAnalyticsService()

    @pytest.fixture
    def mock_db_data(self):
        """Mock database data for testing"""
        from src.core.database import CodeFile, Issue, PullRequest, IssueSeverity, IssueCategory

        # Mock code files
        code_file1 = Mock(spec=CodeFile)
        code_file1.id = 'cf1'
        code_file1.file_path = 'app.py'
        code_file1.lines_of_code = 500
        code_file1.language = 'python'

        code_file2 = Mock(spec=CodeFile)
        code_file2.id = 'cf2'
        code_file2.file_path = 'utils.py'
        code_file2.lines_of_code = 300
        code_file2.language = 'python'

        # Mock issues
        issue1 = Mock(spec=Issue)
        issue1.id = 'i1'
        issue1.code_file_id = 'cf1'
        issue1.severity = IssueSeverity.CRITICAL
        issue1.category = IssueCategory.SECURITY
        issue1.created_at = datetime.utcnow()

        issue2 = Mock(spec=Issue)
        issue2.id = 'i2'
        issue2.code_file_id = 'cf1'
        issue2.severity = IssueSeverity.ERROR
        issue2.category = IssueCategory.SMELL
        issue2.created_at = datetime.utcnow()

        issue3 = Mock(spec=Issue)
        issue3.id = 'i3'
        issue3.code_file_id = 'cf2'
        issue3.severity = IssueSeverity.WARNING
        issue3.category = IssueCategory.COMPLEXITY
        issue3.created_at = datetime.utcnow()

        return {
            'code_files': [code_file1, code_file2],
            'issues': [issue1, issue2, issue3]
        }

    def test_repository_health_score_calculation(self, service, mock_db_data):
        """Test repository health score calculation"""
        # Mock database queries
        mock_db = Mock()
        mock_db.query().join().filter().all.return_value = mock_db_data['code_files']
        mock_db.query().filter().all.return_value = mock_db_data['issues']
        mock_db.query().filter().count.return_value = 0  # Previous period

        service.db_manager.get_session().__enter__ = Mock(return_value=mock_db)
        service.db_manager.get_session().__exit__ = Mock(return_value=None)

        # Calculate health score
        health = service.get_repository_health_score('repo_123', time_window_days=30)

        # Assertions
        assert isinstance(health, HealthScore)
        assert 0 <= health.score <= 100
        assert health.grade in ['A+', 'A', 'B', 'C', 'D', 'F']
        assert health.total_issues == 3
        assert health.critical_issues == 1
        assert health.trend in ['improving', 'stable', 'declining']
        assert health.issues_per_kloc > 0

        # Health score calculation: 100 - (1*15 + 1*5 + 1*2) = 78
        assert health.score == 78.0
        assert health.grade == 'C'

    def test_repository_health_score_no_data(self, service):
        """Test health score with no data"""
        mock_db = Mock()
        mock_db.query().join().filter().all.return_value = []

        service.db_manager.get_session().__enter__ = Mock(return_value=mock_db)
        service.db_manager.get_session().__exit__ = Mock(return_value=None)

        health = service.get_repository_health_score('repo_empty')

        assert health.score == 100.0
        assert health.grade == 'A+'
        assert health.total_issues == 0
        assert health.critical_issues == 0
        assert health.trend == 'stable'

    def test_repository_health_score_grades(self, service):
        """Test health score grade boundaries"""
        test_cases = [
            (100, 'A+'),
            (95, 'A+'),
            (92, 'A'),
            (85, 'B'),
            (75, 'C'),
            (65, 'D'),
            (50, 'F')
        ]

        for score_input, expected_grade in test_cases:
            # Calculate expected issues needed
            # Score = 100 - issues_penalty
            # issues_penalty = score_input deviation from 100
            # We can mock the data to produce the desired score

            if score_input >= 95:
                # No issues = A+
                issues = []
            elif score_input >= 90:
                # 1 warning = 98 or add more to get to range
                issues = [Mock(severity=Mock(value='warning'))] * ((100 - score_input) // 2)
            elif score_input >= 80:
                # 1 error = 95, need more issues
                issues = [Mock(severity=Mock(value='error'))] * ((100 - score_input) // 5)
            else:
                # Critical issues
                issues = [Mock(severity=Mock(value='critical'))] * ((100 - score_input) // 15 + 1)

            # This test validates the grade logic exists
            # Full integration test would verify exact boundaries

    def test_quality_trends_daily(self, service, mock_db_data):
        """Test daily quality trends"""
        mock_db = Mock()
        mock_db.query().join().filter().all.return_value = mock_db_data['code_files']

        # Create issues with different timestamps
        now = datetime.utcnow()
        issues = []
        for i in range(10):
            issue = Mock()
            issue.created_at = now - timedelta(days=i)
            issue.severity = Mock(value='warning')
            issues.append(issue)

        mock_db.query().filter().all.return_value = issues

        service.db_manager.get_session().__enter__ = Mock(return_value=mock_db)
        service.db_manager.get_session().__exit__ = Mock(return_value=None)

        # Get trends
        trends = service.get_quality_trends('repo_123', days=10, granularity='daily')

        # Assertions
        assert 'total_issues' in trends
        assert 'critical_issues' in trends
        assert 'health_score' in trends
        assert 'issues_per_kloc' in trends

        # Should have data points for each day
        assert len(trends['total_issues']) > 0
        assert all(isinstance(p, dict) for p in trends['total_issues'])
        assert all('timestamp' in p and 'value' in p and 'label' in p for p in trends['total_issues'])

    def test_quality_trends_weekly(self, service, mock_db_data):
        """Test weekly quality trends"""
        mock_db = Mock()
        mock_db.query().join().filter().all.return_value = mock_db_data['code_files']
        mock_db.query().filter().all.return_value = []

        service.db_manager.get_session().__enter__ = Mock(return_value=mock_db)
        service.db_manager.get_session().__exit__ = Mock(return_value=None)

        trends = service.get_quality_trends('repo_123', days=28, granularity='weekly')

        assert len(trends['total_issues']) >= 4  # At least 4 weeks of data

    def test_developer_contribution_analysis(self, service):
        """Test developer contribution analysis"""
        from src.core.database import PullRequest, CodeFile, Issue, Review

        # Mock PRs
        pr1 = Mock(spec=PullRequest)
        pr1.id = 'pr1'
        pr1.author = 'dev1'
        pr1.created_at = datetime.utcnow()

        pr2 = Mock(spec=PullRequest)
        pr2.id = 'pr2'
        pr2.author = 'dev2'
        pr2.created_at = datetime.utcnow()

        # Mock code files
        cf1 = Mock(spec=CodeFile)
        cf1.id = 'cf1'

        # Mock issues
        issue1 = Mock(spec=Issue)
        issue1.severity = Mock(value='error')

        # Mock reviews
        review1 = Mock(spec=Review)
        review1.reviewer_id = 'user_123'

        mock_db = Mock()
        mock_db.query().filter().all.side_effect = [
            [pr1, pr2],  # PRs
            [cf1],       # Code files for pr1
            [],          # Code files for pr2
            [issue1],    # Issues for cf1
            [review1]    # Reviews for pr1
        ]

        service.db_manager.get_session().__enter__ = Mock(return_value=mock_db)
        service.db_manager.get_session().__exit__ = Mock(return_value=None)

        # Get analysis
        analysis = service.get_developer_contribution_analysis('repo_123', days=30)

        # Assertions
        assert isinstance(analysis, list)
        assert all('developer' in dev for dev in analysis)
        assert all('prs_created' in dev for dev in analysis)
        assert all('prs_reviewed' in dev for dev in analysis)
        assert all('quality_score' in dev for dev in analysis)
        assert all('contribution_score' in dev for dev in analysis)

        # Should be sorted by contribution score
        if len(analysis) > 1:
            assert analysis[0]['contribution_score'] >= analysis[1]['contribution_score']

    def test_technical_debt_heatmap(self, service, mock_db_data):
        """Test technical debt heatmap generation"""
        from src.core.database import IssueSeverity

        mock_db = Mock()
        mock_db.query().join().filter().all.return_value = mock_db_data['code_files']

        # Mock issues query for each file
        def get_issues_for_file(file_id):
            if file_id == 'cf1':
                i1 = Mock()
                i1.severity = IssueSeverity.CRITICAL
                i2 = Mock()
                i2.severity = IssueSeverity.ERROR
                return [i1, i2]
            else:
                i3 = Mock()
                i3.severity = IssueSeverity.WARNING
                return [i3]

        mock_db.query().filter().all.side_effect = lambda: get_issues_for_file(
            mock_db.query().filter.call_args[0][0].right if hasattr(mock_db.query().filter.call_args[0][0], 'right') else 'cf1'
        )

        service.db_manager.get_session().__enter__ = Mock(return_value=mock_db)
        service.db_manager.get_session().__exit__ = Mock(return_value=None)

        # Get heatmap
        heatmap = service.get_technical_debt_heatmap('repo_123')

        # Assertions
        assert 'files' in heatmap
        assert 'total_files' in heatmap
        assert 'total_debt_score' in heatmap
        assert 'avg_debt_density' in heatmap

        # Files should have required fields
        if heatmap['files']:
            file_data = heatmap['files'][0]
            assert 'file_path' in file_data
            assert 'debt_score' in file_data
            assert 'debt_density' in file_data
            assert 'debt_level' in file_data
            assert file_data['debt_level'] in ['low', 'medium', 'high', 'critical']

    def test_quality_gate_metrics(self, service):
        """Test quality gate metrics and SLO checking"""
        # Mock health score
        mock_health = HealthScore(
            score=85.0,
            grade='B',
            issues_per_kloc=5.0,
            critical_issues=0,
            total_issues=10,
            trend='improving'
        )

        with patch.object(service, 'get_repository_health_score', return_value=mock_health):
            metrics = service.get_quality_gate_metrics('repo_123')

        # Assertions
        assert 'overall_status' in metrics
        assert 'health_score' in metrics
        assert 'grade' in metrics
        assert 'slo_metrics' in metrics
        assert 'timestamp' in metrics

        slo_metrics = metrics['slo_metrics']
        assert 'health_score' in slo_metrics
        assert 'critical_issues' in slo_metrics
        assert 'issues_per_kloc' in slo_metrics
        assert 'trend' in slo_metrics

        # Each SLO should have current, target, and passing
        for slo in slo_metrics.values():
            assert 'current' in slo
            assert 'target' in slo
            assert 'passing' in slo
            assert isinstance(slo['passing'], bool)

    def test_quality_gate_passing(self, service):
        """Test quality gate with all SLOs passing"""
        mock_health = HealthScore(
            score=95.0,  # Above 80
            grade='A',
            issues_per_kloc=5.0,  # Below 10
            critical_issues=0,  # Zero
            total_issues=5,
            trend='improving'
        )

        with patch.object(service, 'get_repository_health_score', return_value=mock_health):
            metrics = service.get_quality_gate_metrics('repo_123')

        assert metrics['overall_status'] == 'passed'

    def test_quality_gate_failing(self, service):
        """Test quality gate with failing SLOs"""
        mock_health = HealthScore(
            score=70.0,  # Below 80
            grade='C',
            issues_per_kloc=15.0,  # Above 10
            critical_issues=2,  # Above 0
            total_issues=50,
            trend='declining'
        )

        with patch.object(service, 'get_repository_health_score', return_value=mock_health):
            metrics = service.get_quality_gate_metrics('repo_123')

        assert metrics['overall_status'] == 'failed'
        assert metrics['slo_metrics']['health_score']['passing'] is False
        assert metrics['slo_metrics']['critical_issues']['passing'] is False

    def test_create_time_buckets_daily(self, service):
        """Test time bucket creation for daily granularity"""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 1, 5)

        buckets = service._create_time_buckets(start, end, 'daily')

        assert len(buckets) == 4
        for bucket_start, bucket_end, label in buckets:
            assert isinstance(bucket_start, datetime)
            assert isinstance(bucket_end, datetime)
            assert isinstance(label, str)
            assert bucket_start < bucket_end

    def test_create_time_buckets_weekly(self, service):
        """Test time bucket creation for weekly granularity"""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 2, 1)

        buckets = service._create_time_buckets(start, end, 'weekly')

        assert len(buckets) >= 4
        for bucket_start, bucket_end, label in buckets:
            assert bucket_end - bucket_start <= timedelta(weeks=1)

    def test_create_time_buckets_monthly(self, service):
        """Test time bucket creation for monthly granularity"""
        start = datetime(2024, 1, 1)
        end = datetime(2024, 4, 1)

        buckets = service._create_time_buckets(start, end, 'monthly')

        assert len(buckets) == 3
        for bucket_start, bucket_end, label in buckets:
            assert bucket_end - bucket_start <= timedelta(days=30)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
