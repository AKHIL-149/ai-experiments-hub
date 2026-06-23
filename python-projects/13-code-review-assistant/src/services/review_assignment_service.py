"""
Review Assignment Service
Handles automated reviewer assignment, code ownership, and review workflows
"""

import re
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set
from collections import defaultdict, Counter
from sqlalchemy import func, and_, desc

from src.core.database import (
    DatabaseManager, PullRequest, Review, ReviewComment, Repository,
    Team, TeamMember, User, CodeFile
)


class ReviewAssignmentService:
    """Service for managing review assignments and workflows"""

    def __init__(self):
        self.db_manager = DatabaseManager()

    def assign_reviewers(
        self,
        pr_id: str,
        strategy: str = 'balanced',
        num_reviewers: int = 2,
        exclude_author: bool = True
    ) -> Dict[str, Any]:
        """
        Automatically assign reviewers to a pull request

        Args:
            pr_id: Pull request ID
            strategy: Assignment strategy ('balanced', 'expertise', 'round_robin')
            num_reviewers: Number of reviewers to assign
            exclude_author: Whether to exclude PR author from assignment

        Returns:
            Dictionary with assigned reviewers and reason
        """
        with self.db_manager.get_session() as db:
            # Get PR and repository
            pr = db.query(PullRequest).filter(PullRequest.id == pr_id).first()
            if not pr:
                return {
                    'success': False,
                    'error': 'Pull request not found'
                }

            repo = db.query(Repository).filter(Repository.id == pr.repository_id).first()
            if not repo:
                return {
                    'success': False,
                    'error': 'Repository not found'
                }

            # Get changed files in PR
            changed_files = db.query(CodeFile).filter(
                CodeFile.pull_request_id == pr_id
            ).all()

            file_paths = [f.file_path for f in changed_files]

            # Get candidate reviewers
            candidates = self._get_candidate_reviewers(
                db, repo, pr, exclude_author
            )

            if not candidates:
                return {
                    'success': False,
                    'error': 'No available reviewers found'
                }

            # Apply assignment strategy
            if strategy == 'expertise':
                assigned = self._assign_by_expertise(
                    db, candidates, file_paths, num_reviewers
                )
            elif strategy == 'round_robin':
                assigned = self._assign_round_robin(
                    db, candidates, num_reviewers
                )
            else:  # balanced (default)
                assigned = self._assign_balanced(
                    db, candidates, num_reviewers
                )

            return {
                'success': True,
                'reviewers': assigned,
                'strategy': strategy,
                'candidates_considered': len(candidates)
            }

    def _get_candidate_reviewers(
        self,
        db,
        repo: Repository,
        pr: PullRequest,
        exclude_author: bool
    ) -> List[Dict]:
        """Get list of candidate reviewers for a PR"""
        candidates = []

        # If repo has a team, get team members
        if repo.team_id:
            members = db.query(TeamMember, User).join(
                User, TeamMember.user_id == User.id
            ).filter(
                TeamMember.team_id == repo.team_id
            ).all()

            for member, user in members:
                # Exclude PR author if requested
                if exclude_author and user.id == pr.author_id:
                    continue

                # Only include members with review permissions
                if member.role in ['owner', 'admin', 'member']:
                    candidates.append({
                        'user_id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'role': member.role
                    })
        else:
            # For repos without teams, use repository owner
            if repo.user_id and (not exclude_author or repo.user_id != pr.author_id):
                owner = db.query(User).filter(User.id == repo.user_id).first()
                if owner:
                    candidates.append({
                        'user_id': owner.id,
                        'username': owner.username,
                        'email': owner.email,
                        'role': 'owner'
                    })

        return candidates

    def _assign_by_expertise(
        self,
        db,
        candidates: List[Dict],
        file_paths: List[str],
        num_reviewers: int
    ) -> List[Dict]:
        """Assign reviewers based on file expertise"""
        expertise_scores = defaultdict(int)

        # Calculate expertise score for each candidate
        for candidate in candidates:
            # Count reviews on similar files
            review_count = db.query(func.count(Review.id)).join(
                PullRequest, Review.pull_request_id == PullRequest.id
            ).join(
                CodeFile, CodeFile.pull_request_id == PullRequest.id
            ).filter(
                Review.reviewer_id == candidate['user_id'],
                CodeFile.file_path.in_(file_paths)
            ).scalar() or 0

            expertise_scores[candidate['user_id']] = review_count

        # Sort candidates by expertise score
        sorted_candidates = sorted(
            candidates,
            key=lambda c: expertise_scores[c['user_id']],
            reverse=True
        )

        # Assign top N reviewers
        assigned = []
        for candidate in sorted_candidates[:num_reviewers]:
            assigned.append({
                **candidate,
                'reason': 'file expertise',
                'expertise_score': expertise_scores[candidate['user_id']]
            })

        return assigned

    def _assign_balanced(
        self,
        db,
        candidates: List[Dict],
        num_reviewers: int
    ) -> List[Dict]:
        """Assign reviewers based on current workload (balanced)"""
        workload_scores = {}

        # Calculate current workload for each candidate
        for candidate in candidates:
            # Count pending/in-progress reviews in last 7 days
            week_ago = datetime.now() - timedelta(days=7)
            active_reviews = db.query(func.count(Review.id)).filter(
                and_(
                    Review.reviewer_id == candidate['user_id'],
                    Review.created_at >= week_ago,
                    Review.approved == None  # Pending reviews
                )
            ).scalar() or 0

            workload_scores[candidate['user_id']] = active_reviews

        # Sort candidates by workload (ascending - least busy first)
        sorted_candidates = sorted(
            candidates,
            key=lambda c: workload_scores[c['user_id']]
        )

        # Assign to least busy reviewers
        assigned = []
        for candidate in sorted_candidates[:num_reviewers]:
            assigned.append({
                **candidate,
                'reason': 'balanced workload',
                'current_workload': workload_scores[candidate['user_id']]
            })

        return assigned

    def _assign_round_robin(
        self,
        db,
        candidates: List[Dict],
        num_reviewers: int
    ) -> List[Dict]:
        """Assign reviewers using round-robin rotation"""
        # Get last review counts for each candidate
        review_counts = {}

        for candidate in candidates:
            count = db.query(func.count(Review.id)).filter(
                Review.reviewer_id == candidate['user_id']
            ).scalar() or 0
            review_counts[candidate['user_id']] = count

        # Sort candidates by total reviews (ascending)
        sorted_candidates = sorted(
            candidates,
            key=lambda c: review_counts[c['user_id']]
        )

        # Assign to reviewers with fewest total reviews
        assigned = []
        for candidate in sorted_candidates[:num_reviewers]:
            assigned.append({
                **candidate,
                'reason': 'round robin',
                'total_reviews': review_counts[candidate['user_id']]
            })

        return assigned

    def parse_codeowners(self, content: str) -> Dict[str, List[str]]:
        """
        Parse CODEOWNERS file content

        Args:
            content: CODEOWNERS file content

        Returns:
            Dictionary mapping file patterns to owner usernames
        """
        owners_map = {}

        for line in content.split('\n'):
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue

            # Parse pattern and owners
            # Format: pattern @owner1 @owner2
            parts = line.split()
            if len(parts) < 2:
                continue

            pattern = parts[0]
            owners = [o.lstrip('@') for o in parts[1:] if o.startswith('@')]

            if owners:
                owners_map[pattern] = owners

        return owners_map

    def get_file_owners(
        self,
        file_path: str,
        codeowners_map: Dict[str, List[str]]
    ) -> List[str]:
        """
        Get owners for a specific file path based on CODEOWNERS

        Args:
            file_path: File path to check
            codeowners_map: Parsed CODEOWNERS mapping

        Returns:
            List of owner usernames
        """
        owners = []

        # Check each pattern (most specific first)
        patterns = sorted(
            codeowners_map.keys(),
            key=len,
            reverse=True
        )

        for pattern in patterns:
            # Convert glob pattern to regex
            regex_pattern = pattern.replace('*', '.*').replace('?', '.')
            if re.match(regex_pattern, file_path):
                owners.extend(codeowners_map[pattern])
                break  # Use most specific match

        return list(set(owners))  # Remove duplicates

    def check_review_approval(
        self,
        pr_id: str,
        required_approvals: int = 1,
        require_owner_approval: bool = False
    ) -> Dict[str, Any]:
        """
        Check if PR has sufficient approvals for merge

        Args:
            pr_id: Pull request ID
            required_approvals: Minimum number of approvals required
            require_owner_approval: Whether code owner approval is required

        Returns:
            Dictionary with approval status and details
        """
        with self.db_manager.get_session() as db:
            # Get PR
            pr = db.query(PullRequest).filter(PullRequest.id == pr_id).first()
            if not pr:
                return {
                    'success': False,
                    'error': 'Pull request not found'
                }

            # Get approved reviews
            approved_reviews = db.query(Review, User).join(
                User, Review.reviewer_id == User.id
            ).filter(
                and_(
                    Review.pull_request_id == pr_id,
                    Review.approved == True
                )
            ).all()

            approval_count = len(approved_reviews)
            reviewers = [
                {'username': user.username, 'user_id': user.id}
                for review, user in approved_reviews
            ]

            # Check if minimum approvals met
            has_min_approvals = approval_count >= required_approvals

            # Check code owner approval if required
            has_owner_approval = True
            if require_owner_approval:
                # This would need to check against CODEOWNERS
                # For now, just check if repo owner approved
                repo = db.query(Repository).filter(
                    Repository.id == pr.repository_id
                ).first()

                has_owner_approval = any(
                    reviewer['user_id'] == repo.user_id
                    for reviewer in reviewers
                )

            can_merge = has_min_approvals and has_owner_approval

            return {
                'success': True,
                'can_merge': can_merge,
                'approval_count': approval_count,
                'required_approvals': required_approvals,
                'has_owner_approval': has_owner_approval,
                'reviewers': reviewers
            }

    def get_reviewer_stats(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Get review statistics for a user

        Args:
            user_id: User ID
            days: Number of days to analyze

        Returns:
            Dictionary with reviewer statistics
        """
        with self.db_manager.get_session() as db:
            start_date = datetime.now() - timedelta(days=days)

            # Count reviews
            total_reviews = db.query(func.count(Review.id)).filter(
                and_(
                    Review.reviewer_id == user_id,
                    Review.created_at >= start_date
                )
            ).scalar() or 0

            # Count approvals
            approvals = db.query(func.count(Review.id)).filter(
                and_(
                    Review.reviewer_id == user_id,
                    Review.created_at >= start_date,
                    Review.approved == True
                )
            ).scalar() or 0

            # Count rejections
            rejections = db.query(func.count(Review.id)).filter(
                and_(
                    Review.reviewer_id == user_id,
                    Review.created_at >= start_date,
                    Review.approved == False
                )
            ).scalar() or 0

            # Count pending
            pending = db.query(func.count(Review.id)).filter(
                and_(
                    Review.reviewer_id == user_id,
                    Review.created_at >= start_date,
                    Review.approved == None
                )
            ).scalar() or 0

            # Count comments
            comments = db.query(func.count(ReviewComment.id)).join(
                Review, ReviewComment.review_id == Review.id
            ).filter(
                and_(
                    Review.reviewer_id == user_id,
                    Review.created_at >= start_date
                )
            ).scalar() or 0

            # Calculate average time to review
            # This would need Review.completed_at field which doesn't exist yet
            avg_review_time_hours = 0

            return {
                'user_id': user_id,
                'period_days': days,
                'total_reviews': total_reviews,
                'approvals': approvals,
                'rejections': rejections,
                'pending': pending,
                'comments_count': comments,
                'approval_rate': round(approvals / total_reviews * 100, 2) if total_reviews > 0 else 0,
                'avg_review_time_hours': avg_review_time_hours,
                'avg_comments_per_review': round(comments / total_reviews, 2) if total_reviews > 0 else 0
            }


# Global instance
review_assignment_service = ReviewAssignmentService()
