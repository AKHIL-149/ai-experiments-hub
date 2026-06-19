"""
Analytics Service
Provides metrics, trends, and insights for code analysis
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import statistics


class AnalyticsService:
    """Service for calculating analytics and metrics"""

    def __init__(self):
        self.cache = {}
        self.cache_ttl = 300  # 5 minutes

    # ============================================================================
    # Health Score Calculation
    # ============================================================================

    def calculate_health_score(
        self,
        issues: List[Dict],
        code_stats: Optional[Dict] = None
    ) -> Dict:
        """
        Calculate comprehensive health score for code

        Args:
            issues: List of issues found
            code_stats: Optional code statistics (LOC, complexity, etc.)

        Returns:
            Dictionary with score, grade, metrics, and breakdown
        """
        # Start with perfect score
        score = 100.0

        # Count issues by severity
        severity_counts = {
            'critical': 0,
            'error': 0,
            'warning': 0,
            'info': 0
        }

        for issue in issues:
            severity = issue.get('severity', 'info').lower()
            if severity in severity_counts:
                severity_counts[severity] += 1

        # Deduct points based on severity
        score -= severity_counts['critical'] * 10
        score -= severity_counts['error'] * 5
        score -= severity_counts['warning'] * 2
        score -= severity_counts['info'] * 0.5

        # Apply code stats penalties if available
        if code_stats:
            # Complexity penalty
            avg_complexity = code_stats.get('avg_complexity', 0)
            if avg_complexity > 15:
                score -= (avg_complexity - 15) * 0.5
            elif avg_complexity > 10:
                score -= (avg_complexity - 10) * 0.2

            # Test coverage bonus/penalty
            coverage = code_stats.get('test_coverage', 0)
            if coverage >= 80:
                score += 5
            elif coverage < 50:
                score -= 10

        # Ensure score stays in valid range
        score = max(0, min(100, score))

        # Calculate grade
        grade = self._score_to_grade(score)

        # Calculate category breakdown
        category_breakdown = self._calculate_category_breakdown(issues)

        return {
            'score': round(score, 2),
            'grade': grade,
            'color': self._grade_to_color(grade),
            'status': self._score_to_status(score),
            'severity_counts': severity_counts,
            'total_issues': len(issues),
            'category_breakdown': category_breakdown,
            'metrics': {
                'critical_issues': severity_counts['critical'],
                'error_issues': severity_counts['error'],
                'warning_issues': severity_counts['warning'],
                'info_issues': severity_counts['info'],
                'avg_complexity': code_stats.get('avg_complexity', 0) if code_stats else 0,
                'test_coverage': code_stats.get('test_coverage', 0) if code_stats else 0
            }
        }

    def _score_to_grade(self, score: float) -> str:
        """Convert score to letter grade"""
        if score >= 90:
            return 'A'
        elif score >= 80:
            return 'B'
        elif score >= 70:
            return 'C'
        elif score >= 60:
            return 'D'
        else:
            return 'F'

    def _grade_to_color(self, grade: str) -> str:
        """Get color for grade"""
        colors = {
            'A': '#10b981',  # green
            'B': '#3b82f6',  # blue
            'C': '#f59e0b',  # yellow
            'D': '#ef4444',  # orange
            'F': '#dc2626'   # red
        }
        return colors.get(grade, '#6b7280')

    def _score_to_status(self, score: float) -> str:
        """Get status text for score"""
        if score >= 90:
            return 'Excellent'
        elif score >= 80:
            return 'Good'
        elif score >= 70:
            return 'Fair'
        elif score >= 60:
            return 'Needs Improvement'
        else:
            return 'Critical'

    def _calculate_category_breakdown(self, issues: List[Dict]) -> Dict:
        """Calculate issue counts by category"""
        breakdown = defaultdict(int)

        for issue in issues:
            category = issue.get('category', 'other')
            breakdown[category] += 1

        return dict(breakdown)

    # ============================================================================
    # Issue Trends
    # ============================================================================

    def calculate_issue_trends(
        self,
        analyses: List[Dict],
        days: int = 30,
        grouping: str = 'day'
    ) -> List[Dict]:
        """
        Calculate issue trends over time

        Args:
            analyses: List of analysis results with timestamps
            days: Number of days to include
            grouping: 'day', 'week', or 'month'

        Returns:
            List of trend data points with date and issue counts
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Initialize time buckets
        buckets = self._create_time_buckets(start_date, end_date, grouping)

        # Group issues by time bucket
        for analysis in analyses:
            analyzed_at = analysis.get('analyzed_at')
            if not analyzed_at:
                continue

            try:
                if isinstance(analyzed_at, str):
                    analysis_date = datetime.fromisoformat(analyzed_at.replace('Z', '+00:00'))
                else:
                    analysis_date = analyzed_at

                # Check if within range
                if start_date <= analysis_date <= end_date:
                    bucket_key = self._get_bucket_key(analysis_date, grouping)

                    if bucket_key in buckets:
                        # Count issues by severity
                        for issue in analysis.get('issues', []):
                            severity = issue.get('severity', 'info').lower()
                            buckets[bucket_key][severity] += 1
                            buckets[bucket_key]['total'] += 1

            except Exception as e:
                print(f"Error processing analysis date: {e}")
                continue

        # Convert to list format
        trends = [
            {
                'date': date_key,
                'critical': counts['critical'],
                'error': counts['error'],
                'warning': counts['warning'],
                'info': counts['info'],
                'total': counts['total']
            }
            for date_key, counts in sorted(buckets.items())
        ]

        return trends

    def _create_time_buckets(
        self,
        start_date: datetime,
        end_date: datetime,
        grouping: str
    ) -> Dict:
        """Create time buckets for trend calculation"""
        buckets = {}
        current_date = start_date

        while current_date <= end_date:
            bucket_key = self._get_bucket_key(current_date, grouping)

            if bucket_key not in buckets:
                buckets[bucket_key] = {
                    'critical': 0,
                    'error': 0,
                    'warning': 0,
                    'info': 0,
                    'total': 0
                }

            # Increment date based on grouping
            if grouping == 'day':
                current_date += timedelta(days=1)
            elif grouping == 'week':
                current_date += timedelta(weeks=1)
            elif grouping == 'month':
                # Approximate month increment
                current_date += timedelta(days=30)
            else:
                current_date += timedelta(days=1)

        return buckets

    def _get_bucket_key(self, date: datetime, grouping: str) -> str:
        """Get bucket key for a date"""
        if grouping == 'day':
            return date.strftime('%Y-%m-%d')
        elif grouping == 'week':
            return date.strftime('%Y-W%U')
        elif grouping == 'month':
            return date.strftime('%Y-%m')
        else:
            return date.strftime('%Y-%m-%d')

    # ============================================================================
    # Repository Metrics
    # ============================================================================

    def calculate_repository_metrics(
        self,
        analyses: List[Dict],
        code_files: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Calculate comprehensive repository metrics

        Args:
            analyses: List of analysis results
            code_files: Optional list of code file metadata

        Returns:
            Dictionary with repository metrics
        """
        if not analyses:
            return {
                'total_analyses': 0,
                'total_issues': 0,
                'total_files': 0,
                'total_lines_of_code': 0,
                'avg_issues_per_file': 0,
                'avg_complexity': 0,
                'most_common_issues': [],
                'severity_distribution': {},
                'category_distribution': {},
                'health_score': 100
            }

        # Aggregate metrics
        total_issues = 0
        all_issues = []
        total_loc = 0
        complexity_scores = []

        for analysis in analyses:
            issues = analysis.get('issues', [])
            total_issues += len(issues)
            all_issues.extend(issues)

            # Extract LOC
            metadata = analysis.get('metadata', {})
            loc = metadata.get('lines_of_code', 0)
            total_loc += loc

            # Extract complexity
            for issue in issues:
                if issue.get('category') == 'complexity':
                    desc = issue.get('description', '')
                    complexity = self._extract_complexity_value(desc)
                    if complexity:
                        complexity_scores.append(complexity)

        # Calculate distributions
        severity_dist = self._calculate_distribution(all_issues, 'severity')
        category_dist = self._calculate_distribution(all_issues, 'category')

        # Find most common issues
        issue_types = defaultdict(int)
        for issue in all_issues:
            issue_type = f"{issue.get('category', 'other')}:{issue.get('rule_id', 'unknown')}"
            issue_types[issue_type] += 1

        most_common = sorted(
            issue_types.items(),
            key=lambda x: x[1],
            reverse=True
        )[:10]

        # Calculate health score
        health_score = self.calculate_health_score(all_issues)

        # Count unique files
        unique_files = set()
        for analysis in analyses:
            filename = analysis.get('filename', '')
            if filename:
                unique_files.add(filename)

        return {
            'total_analyses': len(analyses),
            'total_issues': total_issues,
            'total_files': len(unique_files),
            'total_lines_of_code': total_loc,
            'avg_issues_per_file': round(total_issues / len(unique_files), 2) if unique_files else 0,
            'avg_complexity': round(statistics.mean(complexity_scores), 2) if complexity_scores else 0,
            'most_common_issues': [
                {'type': issue_type, 'count': count}
                for issue_type, count in most_common
            ],
            'severity_distribution': severity_dist,
            'category_distribution': category_dist,
            'health_score': health_score['score']
        }

    def _calculate_distribution(self, items: List[Dict], key: str) -> Dict:
        """Calculate distribution of values for a key"""
        distribution = defaultdict(int)

        for item in items:
            value = item.get(key, 'unknown')
            distribution[value] += 1

        # Convert to percentages
        total = len(items)
        if total > 0:
            return {
                key: {
                    'count': count,
                    'percentage': round(count / total * 100, 2)
                }
                for key, count in distribution.items()
            }

        return {}

    def _extract_complexity_value(self, description: str) -> Optional[int]:
        """Extract complexity value from description"""
        try:
            import re
            match = re.search(r'(\d+)', description)
            if match:
                return int(match.group(1))
        except:
            pass
        return None

    # ============================================================================
    # Time-Series Aggregation
    # ============================================================================

    def aggregate_time_series(
        self,
        data: List[Dict],
        metric_key: str,
        date_key: str = 'date',
        aggregation: str = 'sum'
    ) -> List[Dict]:
        """
        Aggregate time-series data

        Args:
            data: List of data points with dates
            metric_key: Key for the metric to aggregate
            date_key: Key for the date field
            aggregation: 'sum', 'avg', 'min', 'max', 'count'

        Returns:
            List of aggregated data points
        """
        # Group by date
        grouped = defaultdict(list)

        for item in data:
            date = item.get(date_key)
            metric_value = item.get(metric_key)

            if date and metric_value is not None:
                grouped[date].append(metric_value)

        # Aggregate
        aggregated = []
        for date, values in sorted(grouped.items()):
            if aggregation == 'sum':
                agg_value = sum(values)
            elif aggregation == 'avg':
                agg_value = statistics.mean(values)
            elif aggregation == 'min':
                agg_value = min(values)
            elif aggregation == 'max':
                agg_value = max(values)
            elif aggregation == 'count':
                agg_value = len(values)
            else:
                agg_value = sum(values)

            aggregated.append({
                date_key: date,
                metric_key: agg_value
            })

        return aggregated

    # ============================================================================
    # Comparison Metrics
    # ============================================================================

    def compare_periods(
        self,
        current_period: List[Dict],
        previous_period: List[Dict]
    ) -> Dict:
        """
        Compare metrics between two time periods

        Args:
            current_period: Analysis results from current period
            previous_period: Analysis results from previous period

        Returns:
            Dictionary with comparison metrics and changes
        """
        current_metrics = self.calculate_repository_metrics(current_period)
        previous_metrics = self.calculate_repository_metrics(previous_period)

        def calculate_change(current: float, previous: float) -> Dict:
            """Calculate change and percentage"""
            if previous == 0:
                return {
                    'change': current,
                    'percentage': 100.0 if current > 0 else 0,
                    'direction': 'up' if current > 0 else 'neutral'
                }

            change = current - previous
            percentage = (change / previous) * 100

            return {
                'change': round(change, 2),
                'percentage': round(percentage, 2),
                'direction': 'up' if change > 0 else 'down' if change < 0 else 'neutral'
            }

        return {
            'current': current_metrics,
            'previous': previous_metrics,
            'changes': {
                'total_issues': calculate_change(
                    current_metrics['total_issues'],
                    previous_metrics['total_issues']
                ),
                'health_score': calculate_change(
                    current_metrics['health_score'],
                    previous_metrics['health_score']
                ),
                'avg_complexity': calculate_change(
                    current_metrics['avg_complexity'],
                    previous_metrics['avg_complexity']
                )
            }
        }

    # ============================================================================
    # Insights Generation
    # ============================================================================

    def generate_insights(self, metrics: Dict) -> List[Dict]:
        """
        Generate actionable insights from metrics

        Args:
            metrics: Repository metrics dictionary

        Returns:
            List of insights with severity and recommendations
        """
        insights = []

        # High issue count insight
        if metrics['total_issues'] > 100:
            insights.append({
                'type': 'high_issue_count',
                'severity': 'warning',
                'title': 'High Issue Count',
                'message': f"Found {metrics['total_issues']} issues across {metrics['total_files']} files",
                'recommendation': 'Consider dedicating time to address critical and error issues first'
            })

        # Low health score insight
        if metrics['health_score'] < 70:
            insights.append({
                'type': 'low_health_score',
                'severity': 'error',
                'title': 'Low Code Health Score',
                'message': f"Health score is {metrics['health_score']}/100",
                'recommendation': 'Focus on addressing security and critical issues to improve code health'
            })

        # High complexity insight
        if metrics['avg_complexity'] > 12:
            insights.append({
                'type': 'high_complexity',
                'severity': 'warning',
                'title': 'High Average Complexity',
                'message': f"Average complexity is {metrics['avg_complexity']}",
                'recommendation': 'Refactor complex functions into smaller, more manageable pieces'
            })

        # Security issues insight
        security_count = metrics['category_distribution'].get('security', {}).get('count', 0)
        if security_count > 0:
            insights.append({
                'type': 'security_issues',
                'severity': 'critical',
                'title': 'Security Issues Detected',
                'message': f"Found {security_count} security-related issues",
                'recommendation': 'Address security issues immediately before deploying to production'
            })

        # High code smell count
        smell_count = metrics['category_distribution'].get('smell', {}).get('count', 0)
        if smell_count > metrics['total_issues'] * 0.5:
            insights.append({
                'type': 'code_smells',
                'severity': 'info',
                'title': 'Many Code Smells Detected',
                'message': f"Code smells make up {round(smell_count / metrics['total_issues'] * 100)}% of issues",
                'recommendation': 'Consider refactoring to improve code maintainability'
            })

        return insights


# Global instance
analytics_service = AnalyticsService()
