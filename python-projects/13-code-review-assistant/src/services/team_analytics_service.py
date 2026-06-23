"""
Team Analytics Service
Provides team-level metrics, leaderboards, and activity feeds
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict
from sqlalchemy import func, and_, desc

from src.core.database import (
    DatabaseManager, Team, TeamMember, Repository, Issue, Review,
    ReviewComment, AnalysisJob, User
)
from src.services.analytics_service import analytics_service


class TeamAnalyticsService:
    """Service for team-level analytics and insights"""

    def get_team_analytics(self, team_id: str) -> Dict[str, Any]:
        """
        Get comprehensive analytics for a team

        Args:
            team_id: Team ID

        Returns:
            Dictionary with team analytics including:
            - Issue counts by severity and category
            - Health trends over time
            - Activity metrics
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Get team repositories
            team = db.query(Team).filter(Team.id == team_id).first()
            if not team:
                return {
                    'error': 'Team not found',
                    'issues_by_severity': {},
                    'issues_by_category': {},
                    'health_trend': [],
                    'activity_trend': []
                }

            # Get all repositories for this team
            repositories = db.query(Repository).filter(
                Repository.team_id == team_id
            ).all()

            if not repositories:
                return {
                    'issues_by_severity': {
                        'critical': 0,
                        'error': 0,
                        'warning': 0,
                        'info': 0
                    },
                    'issues_by_category': {},
                    'health_trend': [],
                    'activity_trend': [],
                    'total_repositories': 0,
                    'total_issues': 0
                }

            repo_ids = [r.id for r in repositories]

            # Aggregate issues by severity across all team repos
            severity_counts = db.query(
                Issue.severity,
                func.count(Issue.id).label('count')
            ).join(
                Repository, Issue.repository_id == Repository.id
            ).filter(
                Repository.id.in_(repo_ids)
            ).group_by(
                Issue.severity
            ).all()

            issues_by_severity = {
                'critical': 0,
                'error': 0,
                'warning': 0,
                'info': 0
            }
            for severity, count in severity_counts:
                if severity and severity.lower() in issues_by_severity:
                    issues_by_severity[severity.lower()] = count

            # Aggregate issues by category
            category_counts = db.query(
                Issue.category,
                func.count(Issue.id).label('count')
            ).join(
                Repository, Issue.repository_id == Repository.id
            ).filter(
                Repository.id.in_(repo_ids)
            ).group_by(
                Issue.category
            ).all()

            issues_by_category = {}
            for category, count in category_counts:
                if category:
                    issues_by_category[category] = count

            # Calculate health trend (last 30 days)
            health_trend = self._calculate_health_trend(db, repo_ids)

            # Calculate activity trend (last 30 days)
            activity_trend = self._calculate_activity_trend(db, repo_ids)

            # Total issues
            total_issues = sum(issues_by_severity.values())

            return {
                'issues_by_severity': issues_by_severity,
                'issues_by_category': issues_by_category,
                'health_trend': health_trend,
                'activity_trend': activity_trend,
                'total_repositories': len(repositories),
                'total_issues': total_issues
            }

    def _calculate_health_trend(
        self,
        db,
        repo_ids: List[str],
        days: int = 30
    ) -> List[Dict]:
        """Calculate health score trend over time"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Get issues created in time range
        daily_issues = db.query(
            func.date(Issue.created_at).label('date'),
            func.count(Issue.id).label('count')
        ).join(
            Repository, Issue.repository_id == Repository.id
        ).filter(
            and_(
                Repository.id.in_(repo_ids),
                Issue.created_at >= start_date,
                Issue.created_at <= end_date
            )
        ).group_by(
            func.date(Issue.created_at)
        ).all()

        # Convert to health scores (simple calculation)
        trend = []
        for date, count in daily_issues:
            # Simple health score: max(0, 100 - count)
            # More issues = lower score
            health_score = max(0, 100 - (count * 2))
            trend.append({
                'date': date.isoformat() if hasattr(date, 'isoformat') else str(date),
                'score': health_score,
                'issues': count
            })

        return trend

    def _calculate_activity_trend(
        self,
        db,
        repo_ids: List[str],
        days: int = 30
    ) -> List[Dict]:
        """Calculate activity metrics over time"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        # Count analyses per day
        daily_analyses = db.query(
            func.date(AnalysisJob.created_at).label('date'),
            func.count(AnalysisJob.id).label('count')
        ).filter(
            and_(
                AnalysisJob.repository_id.in_(repo_ids),
                AnalysisJob.created_at >= start_date,
                AnalysisJob.created_at <= end_date
            )
        ).group_by(
            func.date(AnalysisJob.created_at)
        ).all()

        trend = []
        for date, count in daily_analyses:
            trend.append({
                'date': date.isoformat() if hasattr(date, 'isoformat') else str(date),
                'analyses': count
            })

        return trend

    def get_team_repositories(self, team_id: str) -> List[Dict]:
        """
        Get all repositories for a team with health metrics

        Args:
            team_id: Team ID

        Returns:
            List of repository dictionaries with metrics
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            repositories = db.query(Repository).filter(
                Repository.team_id == team_id
            ).all()

            result = []
            for repo in repositories:
                # Count issues for this repo
                issue_counts = db.query(
                    Issue.severity,
                    func.count(Issue.id).label('count')
                ).filter(
                    Issue.repository_id == repo.id
                ).group_by(
                    Issue.severity
                ).all()

                severity_counts = {
                    'critical': 0,
                    'error': 0,
                    'warning': 0,
                    'info': 0
                }
                total_issues = 0
                for severity, count in issue_counts:
                    if severity and severity.lower() in severity_counts:
                        severity_counts[severity.lower()] = count
                        total_issues += count

                # Calculate simple health score
                health_score = analytics_service.calculate_health_score(
                    [{'severity': sev} for sev in
                     (['critical'] * severity_counts['critical'] +
                      ['error'] * severity_counts['error'] +
                      ['warning'] * severity_counts['warning'] +
                      ['info'] * severity_counts['info'])]
                )

                result.append({
                    'id': repo.id,
                    'name': repo.name,
                    'description': repo.description,
                    'github_url': repo.github_url,
                    'default_branch': repo.default_branch,
                    'status': repo.status,
                    'last_synced_at': repo.last_synced_at.isoformat() if repo.last_synced_at else None,
                    'total_issues': total_issues,
                    'severity_counts': severity_counts,
                    'health_score': health_score['score'],
                    'health_grade': health_score['grade']
                })

            return result

    def get_team_leaderboard(self, team_id: str) -> List[Dict]:
        """
        Get team member leaderboard ranked by contributions

        Args:
            team_id: Team ID

        Returns:
            List of team members with ranking and metrics
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Get team members
            members = db.query(TeamMember, User).join(
                User, TeamMember.user_id == User.id
            ).filter(
                TeamMember.team_id == team_id
            ).all()

            leaderboard = []
            for member, user in members:
                # Count reviews by this user
                review_count = db.query(func.count(Review.id)).filter(
                    Review.reviewer_id == user.id
                ).scalar() or 0

                # Count issues found in their reviews
                issues_found = db.query(func.count(Issue.id)).join(
                    Repository, Issue.repository_id == Repository.id
                ).filter(
                    Repository.user_id == user.id
                ).scalar() or 0

                # Count comments
                comment_count = db.query(func.count(ReviewComment.id)).join(
                    Review, ReviewComment.review_id == Review.id
                ).filter(
                    Review.reviewer_id == user.id
                ).scalar() or 0

                # Calculate contribution score
                contribution_score = (
                    review_count * 10 +
                    issues_found * 2 +
                    comment_count * 5
                )

                leaderboard.append({
                    'user_id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'role': member.role,
                    'reviews_count': review_count,
                    'issues_found': issues_found,
                    'comments_count': comment_count,
                    'contribution_score': contribution_score,
                    'joined_at': member.created_at.isoformat() if member.created_at else None
                })

            # Sort by contribution score
            leaderboard.sort(key=lambda x: x['contribution_score'], reverse=True)

            # Add rank
            for i, member in enumerate(leaderboard, 1):
                member['rank'] = i

            return leaderboard

    def get_team_activity(
        self,
        team_id: str,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get recent team activity feed

        Args:
            team_id: Team ID
            limit: Maximum number of activities to return

        Returns:
            List of activity items
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Get team repositories
            repo_ids = [r.id for r in db.query(Repository.id).filter(
                Repository.team_id == team_id
            ).all()]

            if not repo_ids:
                return []

            activities = []

            # Recent analysis jobs
            analyses = db.query(AnalysisJob, Repository, User).join(
                Repository, AnalysisJob.repository_id == Repository.id
            ).outerjoin(
                User, Repository.user_id == User.id
            ).filter(
                Repository.id.in_(repo_ids)
            ).order_by(
                desc(AnalysisJob.created_at)
            ).limit(limit // 2).all()

            for job, repo, user in analyses:
                activities.append({
                    'type': 'analysis',
                    'icon': '🔍',
                    'text': f"Analysis completed on {repo.name}",
                    'user': user.username if user else 'System',
                    'repository': repo.name,
                    'timestamp': job.created_at.isoformat() if job.created_at else None,
                    'metadata': {
                        'job_id': job.id,
                        'status': job.status
                    }
                })

            # Recent reviews
            reviews = db.query(Review, Repository, User).join(
                Repository, Review.repository_id == Repository.id
            ).join(
                User, Review.reviewer_id == User.id
            ).filter(
                Repository.id.in_(repo_ids)
            ).order_by(
                desc(Review.created_at)
            ).limit(limit // 2).all()

            for review, repo, user in reviews:
                activities.append({
                    'type': 'review',
                    'icon': '✅',
                    'text': f"{user.username} reviewed PR in {repo.name}",
                    'user': user.username,
                    'repository': repo.name,
                    'timestamp': review.created_at.isoformat() if review.created_at else None,
                    'metadata': {
                        'review_id': review.id,
                        'pr_id': review.pull_request_id,
                        'approved': review.approved
                    }
                })

            # Sort all activities by timestamp
            activities.sort(
                key=lambda x: x['timestamp'] if x['timestamp'] else '',
                reverse=True
            )

            return activities[:limit]


# Global instance
team_analytics_service = TeamAnalyticsService()
