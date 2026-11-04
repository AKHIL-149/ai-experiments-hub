"""
Team Analytics Service
Provides team-level metrics, leaderboards, and activity feeds

The team's data is that of the repositories shared with it (Repository.team_id): their files, and the
pull requests of those repositories. Issues belong to a file, and analysis jobs and reviews to a pull
request. These queries used Issue.repository_id, Review.repository_id and AnalysisJob.repository_id, none
of which exist, so every dashboard failed as soon as a team had a repository.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy import func, and_, desc, or_, select
from src.core.database import (
    DatabaseManager, Team, TeamMember, Repository, Issue, Review,
    ReviewComment, AnalysisJob, User, CodeFile, PullRequest
)
from src.services.analytics_service import analytics_service

SEVERITIES = ('critical', 'error', 'warning', 'info')


def _file_scope(repo_ids: List[str]):
    """Filter for CodeFile: the files of these repositories, directly or through their pull requests"""
    pull_request_ids = select(PullRequest.id).where(PullRequest.repository_id.in_(repo_ids))
    return or_(CodeFile.repository_id.in_(repo_ids), CodeFile.pull_request_id.in_(pull_request_ids))


def _open_issues(db, repo_ids: List[str]):
    """Issues in these repositories that are still open (not resolved or dismissed)"""
    return db.query(Issue).join(CodeFile, Issue.code_file_id == CodeFile.id).filter(
        _file_scope(repo_ids), Issue.resolved == False, Issue.dismissed == False
    )


def _value(enum_or_text) -> str:
    return str(getattr(enum_or_text, 'value', enum_or_text)).lower()


class TeamAnalyticsService:
    """Service for team-level analytics and insights"""

    def get_team_analytics(self, team_id: str) -> Dict[str, Any]:
        """
        Get comprehensive analytics for a team

        Returns the open issues by severity and category, the health and activity trends of the last 30
        days, and the number of repositories and issues.
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            team = db.query(Team).filter(Team.id == team_id).first()
            if not team:
                return {
                    'error': 'Team not found',
                    'issues_by_severity': {},
                    'issues_by_category': {},
                    'health_trend': [],
                    'activity_trend': []
                }

            repo_ids = [r.id for r in db.query(Repository.id).filter(Repository.team_id == team_id)]

            issues_by_severity = {severity: 0 for severity in SEVERITIES}
            if not repo_ids:
                return {
                    'issues_by_severity': issues_by_severity,
                    'issues_by_category': {},
                    'health_trend': [],
                    'activity_trend': [],
                    'total_repositories': 0,
                    'total_issues': 0
                }

            for severity, count in _open_issues(db, repo_ids).with_entities(
                    Issue.severity, func.count(Issue.id)).group_by(Issue.severity).all():
                if _value(severity) in issues_by_severity:
                    issues_by_severity[_value(severity)] = count

            issues_by_category = {
                _value(category): count
                for category, count in _open_issues(db, repo_ids).with_entities(
                    Issue.category, func.count(Issue.id)).group_by(Issue.category).all()
                if category
            }

            return {
                'issues_by_severity': issues_by_severity,
                'issues_by_category': issues_by_category,
                'health_trend': self._calculate_health_trend(db, repo_ids),
                'activity_trend': self._calculate_activity_trend(db, repo_ids),
                'total_repositories': len(repo_ids),
                'total_issues': sum(issues_by_severity.values())
            }

    def _calculate_health_trend(self, db, repo_ids: List[str], days: int = 30) -> List[Dict]:
        """Health score per day, from the issues found that day"""
        # created_at is stored in UTC: datetime.now() is local time, which on a machine west of UTC
        # left out everything from the last few hours
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        daily_issues = _open_issues(db, repo_ids).filter(
            Issue.created_at >= start_date, Issue.created_at <= end_date
        ).with_entities(
            func.date(Issue.created_at).label('date'), func.count(Issue.id).label('count')
        ).group_by(func.date(Issue.created_at)).order_by(func.date(Issue.created_at)).all()

        trend = []
        for date, count in daily_issues:
            # Simple health score: more issues, lower score
            trend.append({
                'date': date.isoformat() if hasattr(date, 'isoformat') else str(date),
                'score': max(0, 100 - (count * 2)),
                'issues': count
            })
        return trend

    def _calculate_activity_trend(self, db, repo_ids: List[str], days: int = 30) -> List[Dict]:
        """Analyses per day (pull request analyses that have started)"""
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        daily_analyses = db.query(
            func.date(AnalysisJob.started_at).label('date'), func.count(AnalysisJob.id).label('count')
        ).join(PullRequest, AnalysisJob.pull_request_id == PullRequest.id).filter(
            and_(
                PullRequest.repository_id.in_(repo_ids),
                AnalysisJob.started_at >= start_date,
                AnalysisJob.started_at <= end_date
            )
        ).group_by(func.date(AnalysisJob.started_at)).order_by(func.date(AnalysisJob.started_at)).all()

        return [
            {'date': date.isoformat() if hasattr(date, 'isoformat') else str(date), 'analyses': count}
            for date, count in daily_analyses
        ]

    def get_team_repositories(self, team_id: str) -> List[Dict]:
        """Get all repositories shared with a team, with health metrics"""
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            repositories = db.query(Repository).filter(
                Repository.team_id == team_id
            ).order_by(Repository.name).all()

            result = []
            for repo in repositories:
                severity_counts = {severity: 0 for severity in SEVERITIES}
                for severity, count in _open_issues(db, [repo.id]).with_entities(
                        Issue.severity, func.count(Issue.id)).group_by(Issue.severity).all():
                    if _value(severity) in severity_counts:
                        severity_counts[_value(severity)] = count

                health_score = analytics_service.calculate_health_score(
                    [{'severity': severity} for severity in SEVERITIES for _ in range(severity_counts[severity])]
                )
                owner = db.query(User.username).filter(User.id == repo.user_id).first()

                result.append({
                    'id': repo.id,
                    'name': repo.name,
                    'github_url': repo.github_url,
                    'default_branch': repo.default_branch,
                    'status': _value(repo.status),
                    'owner': owner[0] if owner else None,
                    'last_synced_at': repo.last_synced_at.isoformat() if repo.last_synced_at else None,
                    'total_issues': sum(severity_counts.values()),
                    'severity_counts': severity_counts,
                    'health_score': health_score['score'],
                    'health_grade': health_score['grade']
                })
            return result

    def get_team_leaderboard(self, team_id: str) -> List[Dict]:
        """
        Team members ranked by contributions *to this team's repositories*: reviews and comments on their
        pull requests, and the open issues in the repositories they share.
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            members = db.query(TeamMember, User).join(
                User, TeamMember.user_id == User.id
            ).filter(
                TeamMember.team_id == team_id, TeamMember.is_active == True
            ).all()

            repos = db.query(Repository.id, Repository.user_id).filter(Repository.team_id == team_id).all()
            team_repo_ids = [r.id for r in repos]
            team_pr_ids = select(PullRequest.id).where(PullRequest.repository_id.in_(team_repo_ids or ['']))

            leaderboard = []
            for member, user in members:
                review_count = db.query(func.count(Review.id)).filter(
                    Review.reviewer_id == user.id, Review.pull_request_id.in_(team_pr_ids)
                ).scalar() or 0

                own_repo_ids = [r.id for r in repos if r.user_id == user.id]
                issues_found = _open_issues(db, own_repo_ids).count() if own_repo_ids else 0

                comment_count = db.query(func.count(ReviewComment.id)).join(
                    Review, ReviewComment.review_id == Review.id
                ).filter(
                    Review.reviewer_id == user.id, Review.pull_request_id.in_(team_pr_ids)
                ).scalar() or 0

                leaderboard.append({
                    'user_id': user.id,
                    'username': user.username,
                    'role': member.role,
                    'reviews_count': review_count,
                    'issues_found': issues_found,
                    'comments_count': comment_count,
                    'contribution_score': review_count * 10 + issues_found * 2 + comment_count * 5,
                    'joined_at': member.joined_at.isoformat() if member.joined_at else None
                })

            leaderboard.sort(key=lambda x: (-x['contribution_score'], x['username'].lower()))
            for rank, entry in enumerate(leaderboard, 1):
                entry['rank'] = rank

            return leaderboard

    def get_team_activity(self, team_id: str, limit: int = 50) -> List[Dict]:
        """Recent analyses and reviews in the team's repositories"""
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            repo_ids = [r.id for r in db.query(Repository.id).filter(Repository.team_id == team_id)]
            if not repo_ids:
                return []

            activities = []

            analyses = db.query(AnalysisJob, Repository, User).join(
                PullRequest, AnalysisJob.pull_request_id == PullRequest.id
            ).join(
                Repository, PullRequest.repository_id == Repository.id
            ).outerjoin(
                User, Repository.user_id == User.id
            ).filter(
                Repository.id.in_(repo_ids)
            ).order_by(desc(AnalysisJob.started_at)).limit(max(1, limit // 2)).all()

            for job, repo, user in analyses:
                activities.append({
                    'type': 'analysis',
                    'icon': '🔍',
                    'text': f"Analysis of a pull request in {repo.name}",
                    'user': user.username if user else 'System',
                    'repository': repo.name,
                    'timestamp': job.started_at.isoformat() if job.started_at else None,
                    'metadata': {'job_id': job.id, 'status': _value(job.status)}
                })

            reviews = db.query(Review, Repository, User).join(
                PullRequest, Review.pull_request_id == PullRequest.id
            ).join(
                Repository, PullRequest.repository_id == Repository.id
            ).join(
                User, Review.reviewer_id == User.id
            ).filter(
                Repository.id.in_(repo_ids)
            ).order_by(desc(Review.created_at)).limit(max(1, limit // 2)).all()

            for review, repo, user in reviews:
                activities.append({
                    'type': 'review',
                    'icon': '✅',
                    'text': f"{user.username} reviewed a pull request in {repo.name}",
                    'user': user.username,
                    'repository': repo.name,
                    'timestamp': review.created_at.isoformat() if review.created_at else None,
                    'metadata': {
                        'review_id': review.id,
                        'pr_id': review.pull_request_id,
                        'approved': review.approved
                    }
                })

            activities.sort(key=lambda x: x['timestamp'] if x['timestamp'] else '', reverse=True)
            return activities[:limit]


# Global instance
team_analytics_service = TeamAnalyticsService()
