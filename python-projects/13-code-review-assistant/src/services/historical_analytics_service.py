"""
Historical Analytics Service
Time-series code quality tracking, repository health trends, and developer analytics
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass

from src.core.database import (
    DatabaseManager, AnalysisJob, Issue, PullRequest,
    Review, CodeFile, User, Repository, IssueSeverity, IssueCategory
)
from sqlalchemy import func, and_, or_


@dataclass
class HealthScore:
    """Repository health score metrics"""
    score: float  # 0-100
    grade: str  # A+, A, B, C, D, F
    issues_per_kloc: float
    critical_issues: int
    total_issues: int
    trend: str  # improving, stable, declining


@dataclass
class TrendPoint:
    """Data point for trend visualization"""
    timestamp: datetime
    value: float
    label: str


class HistoricalAnalyticsService:
    """Service for historical analytics and trend analysis"""

    def __init__(self):
        self.db_manager = DatabaseManager()

    def get_repository_health_score(
        self,
        repository_id: str,
        time_window_days: int = 30
    ) -> HealthScore:
        """
        Calculate repository health score

        Args:
            repository_id: Repository ID
            time_window_days: Days to look back for analysis

        Returns:
            HealthScore object
        """
        with self.db_manager.get_session() as db:
            # Get date threshold
            threshold = datetime.utcnow() - timedelta(days=time_window_days)

            # Get all code files for this repository
            code_files = db.query(CodeFile).join(PullRequest).filter(
                PullRequest.repository_id == repository_id
            ).all()

            if not code_files:
                return HealthScore(
                    score=100.0,
                    grade='A+',
                    issues_per_kloc=0.0,
                    critical_issues=0,
                    total_issues=0,
                    trend='stable'
                )

            # Get total lines of code
            total_loc = sum(cf.lines_of_code or 0 for cf in code_files)

            # Get recent issues
            code_file_ids = [cf.id for cf in code_files]
            recent_issues = db.query(Issue).filter(
                and_(
                    Issue.code_file_id.in_(code_file_ids),
                    Issue.created_at >= threshold
                )
            ).all()

            # Count by severity
            critical_count = sum(1 for i in recent_issues if i.severity == IssueSeverity.CRITICAL)
            error_count = sum(1 for i in recent_issues if i.severity == IssueSeverity.ERROR)
            warning_count = sum(1 for i in recent_issues if i.severity == IssueSeverity.WARNING)
            info_count = sum(1 for i in recent_issues if i.severity == IssueSeverity.INFO)

            total_issues = len(recent_issues)

            # Calculate issues per 1000 LOC
            issues_per_kloc = (total_issues / total_loc * 1000) if total_loc > 0 else 0

            # Calculate health score (0-100)
            # Deduct points based on severity
            score = 100.0
            score -= critical_count * 15  # -15 per critical
            score -= error_count * 5      # -5 per error
            score -= warning_count * 2    # -2 per warning
            score -= info_count * 0.5     # -0.5 per info
            score = max(0, min(100, score))

            # Determine grade
            if score >= 95:
                grade = 'A+'
            elif score >= 90:
                grade = 'A'
            elif score >= 80:
                grade = 'B'
            elif score >= 70:
                grade = 'C'
            elif score >= 60:
                grade = 'D'
            else:
                grade = 'F'

            # Calculate trend (compare to previous period)
            prev_threshold = threshold - timedelta(days=time_window_days)
            prev_issues = db.query(Issue).filter(
                and_(
                    Issue.code_file_id.in_(code_file_ids),
                    Issue.created_at >= prev_threshold,
                    Issue.created_at < threshold
                )
            ).count()

            if prev_issues == 0:
                trend = 'stable'
            elif total_issues < prev_issues * 0.9:
                trend = 'improving'
            elif total_issues > prev_issues * 1.1:
                trend = 'declining'
            else:
                trend = 'stable'

            return HealthScore(
                score=round(score, 1),
                grade=grade,
                issues_per_kloc=round(issues_per_kloc, 2),
                critical_issues=critical_count,
                total_issues=total_issues,
                trend=trend
            )

    def get_quality_trends(
        self,
        repository_id: str,
        days: int = 90,
        granularity: str = 'daily'
    ) -> Dict[str, List[TrendPoint]]:
        """
        Get time-series quality trends

        Args:
            repository_id: Repository ID
            days: Number of days to analyze
            granularity: 'daily', 'weekly', or 'monthly'

        Returns:
            Dictionary with trend data for different metrics
        """
        with self.db_manager.get_session() as db:
            # Get date range
            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            # Get code files for this repository
            code_files = db.query(CodeFile).join(PullRequest).filter(
                PullRequest.repository_id == repository_id
            ).all()
            code_file_ids = [cf.id for cf in code_files]

            # Get all issues in date range
            issues = db.query(Issue).filter(
                and_(
                    Issue.code_file_id.in_(code_file_ids),
                    Issue.created_at >= start_date
                )
            ).all()

            # Group by time periods
            time_buckets = self._create_time_buckets(start_date, end_date, granularity)

            # Initialize trend data
            trends = {
                'total_issues': [],
                'critical_issues': [],
                'health_score': [],
                'issues_per_kloc': []
            }

            for bucket_start, bucket_end, label in time_buckets:
                # Filter issues for this bucket
                bucket_issues = [
                    i for i in issues
                    if bucket_start <= i.created_at < bucket_end
                ]

                total = len(bucket_issues)
                critical = sum(1 for i in bucket_issues if i.severity == IssueSeverity.CRITICAL)

                # Calculate health score for this period
                total_loc = sum(cf.lines_of_code or 0 for cf in code_files)
                issues_per_kloc = (total / total_loc * 1000) if total_loc > 0 else 0

                health_score = 100.0
                health_score -= critical * 15
                health_score -= sum(1 for i in bucket_issues if i.severity == IssueSeverity.ERROR) * 5
                health_score -= sum(1 for i in bucket_issues if i.severity == IssueSeverity.WARNING) * 2
                health_score = max(0, min(100, health_score))

                # Add data points
                trends['total_issues'].append(TrendPoint(
                    timestamp=bucket_start,
                    value=total,
                    label=label
                ))
                trends['critical_issues'].append(TrendPoint(
                    timestamp=bucket_start,
                    value=critical,
                    label=label
                ))
                trends['health_score'].append(TrendPoint(
                    timestamp=bucket_start,
                    value=round(health_score, 1),
                    label=label
                ))
                trends['issues_per_kloc'].append(TrendPoint(
                    timestamp=bucket_start,
                    value=round(issues_per_kloc, 2),
                    label=label
                ))

            return {
                metric: [{'timestamp': p.timestamp.isoformat(), 'value': p.value, 'label': p.label} for p in points]
                for metric, points in trends.items()
            }

    def get_developer_contribution_analysis(
        self,
        repository_id: str,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Analyze developer contributions and code quality

        Args:
            repository_id: Repository ID
            days: Days to analyze

        Returns:
            List of developer statistics
        """
        with self.db_manager.get_session() as db:
            threshold = datetime.utcnow() - timedelta(days=days)

            # Get all PRs for this repository
            prs = db.query(PullRequest).filter(
                and_(
                    PullRequest.repository_id == repository_id,
                    PullRequest.created_at >= threshold
                )
            ).all()

            # Group by author
            author_stats = defaultdict(lambda: {
                'prs_created': 0,
                'prs_reviewed': 0,
                'issues_introduced': 0,
                'issues_by_severity': defaultdict(int),
                'files_modified': 0,
                'avg_review_time': 0.0
            })

            for pr in prs:
                author = pr.author or 'unknown'
                author_stats[author]['prs_created'] += 1

                # Count files in PR
                code_files = db.query(CodeFile).filter(
                    CodeFile.pr_id == pr.id
                ).all()
                author_stats[author]['files_modified'] += len(code_files)

                # Count issues in PR
                for cf in code_files:
                    issues = db.query(Issue).filter(
                        Issue.code_file_id == cf.id
                    ).all()
                    author_stats[author]['issues_introduced'] += len(issues)

                    for issue in issues:
                        severity = issue.severity.value if hasattr(issue.severity, 'value') else issue.severity
                        author_stats[author]['issues_by_severity'][severity] += 1

                # Get reviews for this PR
                reviews = db.query(Review).filter(
                    Review.pr_id == pr.id
                ).all()

                for review in reviews:
                    reviewer_name = f"user_{review.reviewer_id}"
                    author_stats[reviewer_name]['prs_reviewed'] += 1

            # Convert to list and calculate quality score
            result = []
            for author, stats in author_stats.items():
                # Calculate quality score (inverse of issues per PR)
                quality_score = 100.0
                if stats['prs_created'] > 0:
                    issues_per_pr = stats['issues_introduced'] / stats['prs_created']
                    quality_score = max(0, 100 - (issues_per_pr * 10))

                result.append({
                    'developer': author,
                    'prs_created': stats['prs_created'],
                    'prs_reviewed': stats['prs_reviewed'],
                    'files_modified': stats['files_modified'],
                    'issues_introduced': stats['issues_introduced'],
                    'issues_by_severity': dict(stats['issues_by_severity']),
                    'quality_score': round(quality_score, 1),
                    'contribution_score': stats['prs_created'] * 10 + stats['prs_reviewed'] * 5
                })

            # Sort by contribution score
            result.sort(key=lambda x: x['contribution_score'], reverse=True)

            return result

    def get_technical_debt_heatmap(
        self,
        repository_id: str
    ) -> Dict[str, Any]:
        """
        Generate technical debt heatmap showing problem areas

        Args:
            repository_id: Repository ID

        Returns:
            Heatmap data with file paths and debt metrics
        """
        with self.db_manager.get_session() as db:
            # Get all code files for repository
            code_files = db.query(CodeFile).join(PullRequest).filter(
                PullRequest.repository_id == repository_id
            ).all()

            heatmap_data = []

            for cf in code_files:
                # Get issues for this file
                issues = db.query(Issue).filter(
                    Issue.code_file_id == cf.id
                ).all()

                if not issues:
                    continue

                # Calculate debt score
                debt_score = 0.0
                for issue in issues:
                    if issue.severity == IssueSeverity.CRITICAL:
                        debt_score += 4.0
                    elif issue.severity == IssueSeverity.ERROR:
                        debt_score += 2.0
                    elif issue.severity == IssueSeverity.WARNING:
                        debt_score += 1.0
                    else:
                        debt_score += 0.5

                # Calculate debt per LOC
                debt_density = (debt_score / cf.lines_of_code) if cf.lines_of_code else 0

                # Categorize severity
                severity_distribution = {
                    'critical': sum(1 for i in issues if i.severity == IssueSeverity.CRITICAL),
                    'error': sum(1 for i in issues if i.severity == IssueSeverity.ERROR),
                    'warning': sum(1 for i in issues if i.severity == IssueSeverity.WARNING),
                    'info': sum(1 for i in issues if i.severity == IssueSeverity.INFO)
                }

                # Determine debt level
                if debt_density > 0.5:
                    debt_level = 'critical'
                elif debt_density > 0.3:
                    debt_level = 'high'
                elif debt_density > 0.1:
                    debt_level = 'medium'
                else:
                    debt_level = 'low'

                heatmap_data.append({
                    'file_path': cf.file_path,
                    'lines_of_code': cf.lines_of_code,
                    'total_issues': len(issues),
                    'debt_score': round(debt_score, 2),
                    'debt_density': round(debt_density, 3),
                    'debt_level': debt_level,
                    'severity_distribution': severity_distribution,
                    'language': cf.language
                })

            # Sort by debt score (highest first)
            heatmap_data.sort(key=lambda x: x['debt_score'], reverse=True)

            return {
                'files': heatmap_data,
                'total_files': len(heatmap_data),
                'total_debt_score': round(sum(f['debt_score'] for f in heatmap_data), 2),
                'avg_debt_density': round(
                    sum(f['debt_density'] for f in heatmap_data) / len(heatmap_data),
                    3
                ) if heatmap_data else 0
            }

    def get_quality_gate_metrics(
        self,
        repository_id: str
    ) -> Dict[str, Any]:
        """
        Get quality gate metrics and SLOs

        Args:
            repository_id: Repository ID

        Returns:
            Quality gate status and metrics
        """
        with self.db_manager.get_session() as db:
            # Get repository health score
            health_score = self.get_repository_health_score(repository_id)

            # Define SLOs (Service Level Objectives)
            slos = {
                'health_score_min': 80.0,
                'critical_issues_max': 0,
                'error_issues_max': 5,
                'issues_per_kloc_max': 10.0,
                'trend_acceptable': ['improving', 'stable']
            }

            # Check each SLO
            slo_status = {
                'health_score': {
                    'current': health_score.score,
                    'target': slos['health_score_min'],
                    'passing': health_score.score >= slos['health_score_min']
                },
                'critical_issues': {
                    'current': health_score.critical_issues,
                    'target': slos['critical_issues_max'],
                    'passing': health_score.critical_issues <= slos['critical_issues_max']
                },
                'issues_per_kloc': {
                    'current': health_score.issues_per_kloc,
                    'target': slos['issues_per_kloc_max'],
                    'passing': health_score.issues_per_kloc <= slos['issues_per_kloc_max']
                },
                'trend': {
                    'current': health_score.trend,
                    'target': 'improving or stable',
                    'passing': health_score.trend in slos['trend_acceptable']
                }
            }

            # Overall gate status
            all_passing = all(metric['passing'] for metric in slo_status.values())

            return {
                'overall_status': 'passed' if all_passing else 'failed',
                'health_score': health_score.score,
                'grade': health_score.grade,
                'slo_metrics': slo_status,
                'timestamp': datetime.utcnow().isoformat()
            }

    def _create_time_buckets(
        self,
        start_date: datetime,
        end_date: datetime,
        granularity: str
    ) -> List[tuple]:
        """Create time buckets for trend analysis"""
        buckets = []

        if granularity == 'daily':
            delta = timedelta(days=1)
        elif granularity == 'weekly':
            delta = timedelta(weeks=1)
        elif granularity == 'monthly':
            delta = timedelta(days=30)
        else:
            delta = timedelta(days=1)

        current = start_date
        while current < end_date:
            bucket_end = min(current + delta, end_date)
            label = current.strftime('%Y-%m-%d' if granularity == 'daily' else '%Y-%m')
            buckets.append((current, bucket_end, label))
            current = bucket_end

        return buckets


# Global instance
historical_analytics_service = HistoricalAnalyticsService()
