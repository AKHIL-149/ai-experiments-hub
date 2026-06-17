"""
Service for generating code review comments
"""

from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from src.core.database import Review, ReviewComment, PullRequest, PRStatus


class ReviewService:
    """Service for generating and managing code reviews."""

    def __init__(self, db: Session):
        """
        Initialize review service.

        Args:
            db: Database session
        """
        self.db = db

    def generate_review_comments(
        self,
        analysis_results: Dict[str, Any],
        pr_id: str
    ) -> List[Dict[str, Any]]:
        """
        Generate review comments from analysis results.

        Args:
            analysis_results: Analysis results from DiffAnalyzerService
            pr_id: Pull request ID

        Returns:
            List of review comment dictionaries
        """
        comments = []

        # Process each analyzed file
        for file_result in analysis_results.get('files', []):
            file_path = file_result['file_path']

            # Generate comments for each issue
            for issue in file_result.get('issues', []):
                comment = self._create_comment_from_issue(
                    issue,
                    file_path,
                    pr_id
                )
                comments.append(comment)

        return comments

    def _create_comment_from_issue(
        self,
        issue: Dict[str, Any],
        file_path: str,
        pr_id: str
    ) -> Dict[str, Any]:
        """
        Create a review comment from an issue.

        Args:
            issue: Issue dictionary
            file_path: File path where issue was found
            pr_id: Pull request ID

        Returns:
            Review comment dictionary
        """
        severity = issue.get('severity', 'info')
        category = issue.get('category', 'general')
        line_number = issue.get('line_number')

        # Format comment text
        comment_text = self._format_comment_text(issue)

        # Determine severity emoji
        severity_emoji = {
            'critical': '🔴',
            'error': '🟠',
            'warning': '🟡',
            'info': '🔵'
        }.get(severity, '💬')

        return {
            'file_path': file_path,
            'line_number': line_number,
            'comment_text': comment_text,
            'severity': severity,
            'category': category,
            'emoji': severity_emoji,
            'pr_id': pr_id
        }

    def _format_comment_text(self, issue: Dict[str, Any]) -> str:
        """
        Format issue as review comment text.

        Args:
            issue: Issue dictionary

        Returns:
            Formatted comment text
        """
        severity = issue.get('severity', 'info')
        category = issue.get('category', 'general')
        title = issue.get('title', 'Issue found')
        description = issue.get('description', '')
        suggestion = issue.get('suggestion', '')

        # Build comment
        lines = []

        # Header with severity and category
        severity_emoji = {
            'critical': '🔴',
            'error': '🟠',
            'warning': '🟡',
            'info': '🔵'
        }.get(severity, '💬')

        lines.append(f"{severity_emoji} **{severity.upper()}** - {category}")
        lines.append("")

        # Title and description
        lines.append(f"**{title}**")
        if description:
            lines.append("")
            lines.append(description)

        # Suggestion if available
        if suggestion:
            lines.append("")
            lines.append("**Suggestion:**")
            lines.append(suggestion)

        return "\n".join(lines)

    def create_review_summary(
        self,
        analysis_results: Dict[str, Any],
        comments: List[Dict[str, Any]]
    ) -> str:
        """
        Create overall review summary.

        Args:
            analysis_results: Analysis results
            comments: List of review comments

        Returns:
            Summary text
        """
        total_files = analysis_results.get('total_files', 0)
        analyzed_files = analysis_results.get('analyzed_files', 0)
        total_issues = analysis_results.get('total_issues', 0)

        # Count issues by severity
        severity_counts = {
            'critical': 0,
            'error': 0,
            'warning': 0,
            'info': 0
        }

        for comment in comments:
            severity = comment.get('severity', 'info')
            if severity in severity_counts:
                severity_counts[severity] += 1

        # Build summary
        lines = []
        lines.append("## 🤖 Code Review Summary")
        lines.append("")
        lines.append(f"Analyzed {analyzed_files} of {total_files} files and found {total_issues} issues:")
        lines.append("")

        # Issue breakdown
        if severity_counts['critical'] > 0:
            lines.append(f"- 🔴 Critical: {severity_counts['critical']}")
        if severity_counts['error'] > 0:
            lines.append(f"- 🟠 Errors: {severity_counts['error']}")
        if severity_counts['warning'] > 0:
            lines.append(f"- 🟡 Warnings: {severity_counts['warning']}")
        if severity_counts['info'] > 0:
            lines.append(f"- 🔵 Info: {severity_counts['info']}")

        lines.append("")

        # Recommendations
        if severity_counts['critical'] > 0:
            lines.append("**⚠️ Action Required:** Critical issues found that should be addressed before merging.")
        elif severity_counts['error'] > 0:
            lines.append("**⚠️ Recommended:** Errors found that should be reviewed and fixed.")
        elif severity_counts['warning'] > 0:
            lines.append("**✅ Looking Good:** Only minor warnings found. Review suggested improvements.")
        else:
            lines.append("**✅ Excellent:** No significant issues found!")

        return "\n".join(lines)

    def calculate_review_score(
        self,
        analysis_results: Dict[str, Any],
        comments: List[Dict[str, Any]]
    ) -> float:
        """
        Calculate overall review score (0-100).

        Args:
            analysis_results: Analysis results
            comments: List of review comments

        Returns:
            Score between 0 and 100
        """
        if not comments:
            return 100.0

        # Count issues by severity
        severity_weights = {
            'critical': -20,
            'error': -10,
            'warning': -5,
            'info': -1
        }

        total_penalty = 0
        for comment in comments:
            severity = comment.get('severity', 'info')
            penalty = severity_weights.get(severity, -1)
            total_penalty += penalty

        # Calculate score (start at 100, subtract penalties)
        score = max(0, min(100, 100 + total_penalty))

        return round(score, 1)

    def save_review(
        self,
        pr_id: str,
        reviewer_id: str,
        analysis_results: Dict[str, Any],
        comments: List[Dict[str, Any]]
    ) -> Tuple[bool, Optional[Review], Optional[str]]:
        """
        Save review to database.

        Args:
            pr_id: Pull request ID
            reviewer_id: Reviewer user ID
            analysis_results: Analysis results
            comments: Review comments

        Returns:
            Tuple of (success, review, error_message)
        """
        try:
            # Create review
            score = self.calculate_review_score(analysis_results, comments)
            summary = self.create_review_summary(analysis_results, comments)

            review = Review(
                pull_request_id=pr_id,
                reviewer_id=reviewer_id,
                overall_score=score,
                issues_count=len(comments),
                summary=summary,
                approved=(score >= 80)  # Auto-approve if score >= 80
            )

            self.db.add(review)
            self.db.flush()  # Get review ID

            # Create review comments
            for comment_data in comments:
                comment = ReviewComment(
                    review_id=review.id,
                    file_path=comment_data['file_path'],
                    line_number=comment_data.get('line_number'),
                    comment_text=comment_data['comment_text'],
                    severity=comment_data.get('severity', 'info')
                )
                self.db.add(comment)

            # Update PR status to REVIEWED
            pr = self.db.query(PullRequest).filter(PullRequest.id == pr_id).first()
            if pr:
                pr.status = PRStatus.REVIEWED
                pr.reviewed_at = datetime.utcnow()

            self.db.commit()
            self.db.refresh(review)

            return True, review, None

        except Exception as e:
            self.db.rollback()
            return False, None, f"Failed to save review: {str(e)}"

    def get_review(
        self,
        review_id: str
    ) -> Tuple[bool, Optional[Review], Optional[str]]:
        """
        Get review by ID.

        Args:
            review_id: Review ID

        Returns:
            Tuple of (success, review, error_message)
        """
        try:
            review = self.db.query(Review).filter(Review.id == review_id).first()

            if not review:
                return False, None, "Review not found"

            return True, review, None

        except Exception as e:
            return False, None, f"Error: {str(e)}"

    def get_pr_reviews(
        self,
        pr_id: str
    ) -> Tuple[bool, List[Review], Optional[str]]:
        """
        Get all reviews for a pull request.

        Args:
            pr_id: Pull request ID

        Returns:
            Tuple of (success, reviews, error_message)
        """
        try:
            reviews = self.db.query(Review).filter(
                Review.pull_request_id == pr_id
            ).order_by(Review.created_at.desc()).all()

            return True, reviews, None

        except Exception as e:
            return False, [], f"Error: {str(e)}"

    def get_review_comments(
        self,
        review_id: str
    ) -> Tuple[bool, List[ReviewComment], Optional[str]]:
        """
        Get all comments for a review.

        Args:
            review_id: Review ID

        Returns:
            Tuple of (success, comments, error_message)
        """
        try:
            comments = self.db.query(ReviewComment).filter(
                ReviewComment.review_id == review_id
            ).order_by(
                ReviewComment.file_path,
                ReviewComment.line_number
            ).all()

            return True, comments, None

        except Exception as e:
            return False, [], f"Error: {str(e)}"

    def format_comments_for_github(
        self,
        comments: List[Dict[str, Any]],
        commit_id: str
    ) -> List[Dict[str, Any]]:
        """
        Format comments for GitHub PR review API.

        Args:
            comments: Review comments
            commit_id: Commit SHA to comment on

        Returns:
            List of comments formatted for GitHub API
        """
        github_comments = []

        for comment in comments:
            # GitHub review comment format
            github_comment = {
                'path': comment['file_path'],
                'body': comment['comment_text'],
                'commit_id': commit_id
            }

            # Add line number if available
            if comment.get('line_number'):
                github_comment['line'] = comment['line_number']
                github_comment['side'] = 'RIGHT'  # Comment on new version

            github_comments.append(github_comment)

        return github_comments
