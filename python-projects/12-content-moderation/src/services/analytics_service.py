"""
Analytics Service for Content Moderation.

Provides metrics, trends, and insights for the moderation system.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict
from sqlalchemy import func, and_, or_

from ..core.database import (
    DatabaseManager, User, ContentItem, Classification, Review, ModerationJob,
    ContentType, ContentStatus, ViolationCategory, UserRole, JobStatus
)

logging.basicConfig(level=logging.INFO)


class AnalyticsService:
    """Service for analytics and reporting."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize analytics service.

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager or DatabaseManager()
        logging.info("AnalyticsService initialized")

    def get_overview_metrics(self) -> Dict[str, Any]:
        """
        Get high-level overview metrics.

        Returns:
            Dictionary with overview metrics
        """
        try:
            with self.db_manager.get_session() as db:
                # Content metrics
                total_content = db.query(ContentItem).count()
                approved_content = db.query(ContentItem).filter(
                    ContentItem.status == ContentStatus.APPROVED
                ).count()
                rejected_content = db.query(ContentItem).filter(
                    ContentItem.status == ContentStatus.REJECTED
                ).count()
                flagged_content = db.query(ContentItem).filter(
                    ContentItem.status == ContentStatus.FLAGGED
                ).count()

                # Calculate approval rate
                moderated_count = approved_content + rejected_content
                approval_rate = (approved_content / moderated_count * 100) if moderated_count > 0 else 0

                # Review metrics
                total_reviews = db.query(Review).count()
                manual_reviews = db.query(Review).filter(
                    Review.action.in_(['manual_approve', 'manual_reject'])
                ).count()

                # Classification metrics
                total_classifications = db.query(Classification).count()
                violations_detected = db.query(Classification).filter(
                    Classification.is_violation == True
                ).count()

                # Job metrics
                total_jobs = db.query(ModerationJob).count()
                completed_jobs = db.query(ModerationJob).filter(
                    ModerationJob.status == JobStatus.COMPLETED
                ).count()
                failed_jobs = db.query(ModerationJob).filter(
                    ModerationJob.status == JobStatus.FAILED
                ).count()

                # Average processing time
                avg_processing = db.query(
                    func.avg(ModerationJob.processing_time_seconds)
                ).filter(
                    ModerationJob.status == JobStatus.COMPLETED,
                    ModerationJob.processing_time_seconds.isnot(None)
                ).scalar() or 0

                return {
                    'content': {
                        'total': total_content,
                        'approved': approved_content,
                        'rejected': rejected_content,
                        'flagged': flagged_content,
                        'approval_rate': round(approval_rate, 2)
                    },
                    'reviews': {
                        'total': total_reviews,
                        'manual': manual_reviews
                    },
                    'classifications': {
                        'total': total_classifications,
                        'violations': violations_detected
                    },
                    'jobs': {
                        'total': total_jobs,
                        'completed': completed_jobs,
                        'failed': failed_jobs,
                        'success_rate': round((completed_jobs / total_jobs * 100) if total_jobs > 0 else 0, 2),
                        'avg_processing_time': round(avg_processing, 2)
                    }
                }

        except Exception as e:
            logging.error(f"Failed to get overview metrics: {e}")
            return {}

    def get_time_series(
        self,
        days: int = 30,
        granularity: str = 'day'
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get time-series data for content submissions.

        Args:
            days: Number of days to look back
            granularity: 'hour', 'day', or 'week'

        Returns:
            Time-series data with submissions, approvals, rejections
        """
        try:
            with self.db_manager.get_session() as db:
                start_date = datetime.utcnow() - timedelta(days=days)

                # Get content submissions over time
                submissions = db.query(
                    func.date(ContentItem.created_at).label('date'),
                    func.count(ContentItem.id).label('count')
                ).filter(
                    ContentItem.created_at >= start_date
                ).group_by(
                    func.date(ContentItem.created_at)
                ).all()

                # Get approvals over time
                approvals = db.query(
                    func.date(ContentItem.moderated_at).label('date'),
                    func.count(ContentItem.id).label('count')
                ).filter(
                    ContentItem.moderated_at >= start_date,
                    ContentItem.status == ContentStatus.APPROVED
                ).group_by(
                    func.date(ContentItem.moderated_at)
                ).all()

                # Get rejections over time
                rejections = db.query(
                    func.date(ContentItem.moderated_at).label('date'),
                    func.count(ContentItem.id).label('count')
                ).filter(
                    ContentItem.moderated_at >= start_date,
                    ContentItem.status == ContentStatus.REJECTED
                ).group_by(
                    func.date(ContentItem.moderated_at)
                ).all()

                # Format results
                submissions_data = [
                    {'date': str(item.date), 'count': item.count}
                    for item in submissions
                ]

                approvals_data = [
                    {'date': str(item.date), 'count': item.count}
                    for item in approvals
                ]

                rejections_data = [
                    {'date': str(item.date), 'count': item.count}
                    for item in rejections
                ]

                return {
                    'submissions': submissions_data,
                    'approvals': approvals_data,
                    'rejections': rejections_data,
                    'period': {
                        'start': start_date.isoformat(),
                        'end': datetime.utcnow().isoformat(),
                        'days': days
                    }
                }

        except Exception as e:
            logging.error(f"Failed to get time series: {e}")
            return {'submissions': [], 'approvals': [], 'rejections': []}

    def get_category_breakdown(self) -> Dict[str, Any]:
        """
        Get breakdown of violations by category.

        Returns:
            Category statistics
        """
        try:
            with self.db_manager.get_session() as db:
                # Get violations by category
                category_counts = db.query(
                    Classification.category,
                    func.count(Classification.id).label('count')
                ).filter(
                    Classification.is_violation == True
                ).group_by(
                    Classification.category
                ).all()

                # Calculate total violations
                total_violations = sum(item.count for item in category_counts)

                # Format results with percentages
                categories = []
                for item in category_counts:
                    percentage = (item.count / total_violations * 100) if total_violations > 0 else 0
                    categories.append({
                        'category': item.category.value,
                        'count': item.count,
                        'percentage': round(percentage, 2)
                    })

                # Sort by count descending
                categories.sort(key=lambda x: x['count'], reverse=True)

                return {
                    'total_violations': total_violations,
                    'categories': categories
                }

        except Exception as e:
            logging.error(f"Failed to get category breakdown: {e}")
            return {'total_violations': 0, 'categories': []}

    def get_content_type_stats(self) -> Dict[str, Any]:
        """
        Get statistics by content type.

        Returns:
            Content type statistics
        """
        try:
            with self.db_manager.get_session() as db:
                # Count by content type
                type_counts = db.query(
                    ContentItem.content_type,
                    func.count(ContentItem.id).label('count')
                ).group_by(
                    ContentItem.content_type
                ).all()

                # Get approval rates by type
                stats = []
                for item in type_counts:
                    content_type = item.content_type
                    total = item.count

                    approved = db.query(ContentItem).filter(
                        ContentItem.content_type == content_type,
                        ContentItem.status == ContentStatus.APPROVED
                    ).count()

                    rejected = db.query(ContentItem).filter(
                        ContentItem.content_type == content_type,
                        ContentItem.status == ContentStatus.REJECTED
                    ).count()

                    moderated = approved + rejected
                    approval_rate = (approved / moderated * 100) if moderated > 0 else 0

                    stats.append({
                        'type': content_type.value,
                        'total': total,
                        'approved': approved,
                        'rejected': rejected,
                        'approval_rate': round(approval_rate, 2)
                    })

                return {'content_types': stats}

        except Exception as e:
            logging.error(f"Failed to get content type stats: {e}")
            return {'content_types': []}

    def get_moderator_performance(self) -> List[Dict[str, Any]]:
        """
        Get moderator performance metrics.

        Returns:
            List of moderator statistics
        """
        try:
            with self.db_manager.get_session() as db:
                # Get all moderators
                moderators = db.query(User).filter(
                    User.role.in_([UserRole.MODERATOR, UserRole.ADMIN])
                ).all()

                stats = []
                for moderator in moderators:
                    # Count reviews
                    total_reviews = db.query(Review).filter(
                        Review.moderator_id == moderator.id
                    ).count()

                    # Count approvals
                    approvals = db.query(Review).filter(
                        Review.moderator_id == moderator.id,
                        Review.approved == True
                    ).count()

                    # Count rejections
                    rejections = db.query(Review).filter(
                        Review.moderator_id == moderator.id,
                        Review.approved == False
                    ).count()

                    # Count appeals reviewed
                    appeals = db.query(Review).filter(
                        Review.moderator_id == moderator.id,
                        Review.is_appeal_review == True
                    ).count()

                    # Get recent activity
                    last_review = db.query(Review).filter(
                        Review.moderator_id == moderator.id
                    ).order_by(Review.created_at.desc()).first()

                    stats.append({
                        'moderator_id': moderator.id,
                        'username': moderator.username,
                        'role': moderator.role.value,
                        'total_reviews': total_reviews,
                        'approvals': approvals,
                        'rejections': rejections,
                        'appeals_reviewed': appeals,
                        'last_activity': last_review.created_at.isoformat() if last_review else None
                    })

                # Sort by total reviews descending
                stats.sort(key=lambda x: x['total_reviews'], reverse=True)

                return stats

        except Exception as e:
            logging.error(f"Failed to get moderator performance: {e}")
            return []

    def get_cost_analysis(self) -> Dict[str, Any]:
        """
        Get cost analysis for AI processing.

        Returns:
            Cost breakdown and totals
        """
        try:
            with self.db_manager.get_session() as db:
                # Total cost
                total_cost = db.query(
                    func.sum(Classification.cost)
                ).scalar() or 0

                # Cost by provider
                provider_costs = db.query(
                    Classification.provider,
                    func.sum(Classification.cost).label('cost'),
                    func.count(Classification.id).label('count')
                ).group_by(
                    Classification.provider
                ).all()

                # Cost by content type
                type_costs = db.query(
                    ContentItem.content_type,
                    func.sum(Classification.cost).label('cost')
                ).join(
                    Classification, ContentItem.id == Classification.content_id
                ).group_by(
                    ContentItem.content_type
                ).all()

                # Average cost per classification
                avg_cost = db.query(
                    func.avg(Classification.cost)
                ).scalar() or 0

                # Format provider costs
                providers = [
                    {
                        'provider': item.provider,
                        'cost': round(float(item.cost or 0), 4),
                        'requests': item.count,
                        'avg_cost': round(float(item.cost or 0) / item.count, 4) if item.count > 0 else 0
                    }
                    for item in provider_costs
                ]

                # Format type costs
                types = [
                    {
                        'type': item.content_type.value,
                        'cost': round(float(item.cost or 0), 4)
                    }
                    for item in type_costs
                ]

                return {
                    'total_cost': round(float(total_cost), 4),
                    'average_cost': round(float(avg_cost), 4),
                    'by_provider': providers,
                    'by_content_type': types,
                    'currency': 'USD'
                }

        except Exception as e:
            logging.error(f"Failed to get cost analysis: {e}")
            return {'total_cost': 0, 'average_cost': 0, 'by_provider': [], 'by_content_type': []}

    def get_performance_metrics(self) -> Dict[str, Any]:
        """
        Get system performance metrics.

        Returns:
            Performance statistics
        """
        try:
            with self.db_manager.get_session() as db:
                # Average processing time by content type
                type_performance = db.query(
                    ContentItem.content_type,
                    func.avg(ModerationJob.processing_time_seconds).label('avg_time')
                ).join(
                    ModerationJob, ContentItem.id == ModerationJob.content_id
                ).filter(
                    ModerationJob.status == JobStatus.COMPLETED
                ).group_by(
                    ContentItem.content_type
                ).all()

                # Queue performance
                queue_stats = db.query(
                    ModerationJob.queue_name,
                    func.avg(ModerationJob.processing_time_seconds).label('avg_time'),
                    func.count(ModerationJob.id).label('count')
                ).filter(
                    ModerationJob.status == JobStatus.COMPLETED
                ).group_by(
                    ModerationJob.queue_name
                ).all()

                # Format results
                type_perf = [
                    {
                        'type': item.content_type.value,
                        'avg_processing_time': round(float(item.avg_time or 0), 2)
                    }
                    for item in type_performance
                ]

                queue_perf = [
                    {
                        'queue': item.queue_name,
                        'avg_processing_time': round(float(item.avg_time or 0), 2),
                        'jobs_processed': item.count
                    }
                    for item in queue_stats
                ]

                return {
                    'by_content_type': type_perf,
                    'by_queue': queue_perf
                }

        except Exception as e:
            logging.error(f"Failed to get performance metrics: {e}")
            return {'by_content_type': [], 'by_queue': []}

    def export_analytics_data(
        self,
        format: str = 'json',
        days: int = 30
    ) -> Tuple[bool, Optional[Dict[str, Any]], Optional[str]]:
        """
        Export comprehensive analytics data.

        Args:
            format: Export format ('json' or 'csv')
            days: Number of days to include

        Returns:
            Tuple of (success, data, error_message)
        """
        try:
            # Gather all analytics
            data = {
                'generated_at': datetime.utcnow().isoformat(),
                'period_days': days,
                'overview': self.get_overview_metrics(),
                'time_series': self.get_time_series(days=days),
                'categories': self.get_category_breakdown(),
                'content_types': self.get_content_type_stats(),
                'moderators': self.get_moderator_performance(),
                'costs': self.get_cost_analysis(),
                'performance': self.get_performance_metrics()
            }

            return True, data, None

        except Exception as e:
            logging.error(f"Failed to export analytics: {e}")
            return False, None, str(e)


# Global analytics service instance
_analytics_service_instance = None


def get_analytics_service() -> AnalyticsService:
    """
    Get global AnalyticsService instance.

    Returns:
        AnalyticsService singleton
    """
    global _analytics_service_instance
    if _analytics_service_instance is None:
        _analytics_service_instance = AnalyticsService()
    return _analytics_service_instance
