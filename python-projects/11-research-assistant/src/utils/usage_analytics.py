"""
Usage Analytics for Research Assistant.

Tracks and analyzes user activity:
- Query patterns
- Source preferences
- Cost analysis
- Performance metrics
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict


class UsageAnalytics:
    """Tracks and analyzes usage patterns."""

    def __init__(self, db_manager: Any):
        """
        Initialize usage analytics.

        Args:
            db_manager: DatabaseManager instance
        """
        self.db_manager = db_manager
        logging.info("UsageAnalytics initialized")

    def get_user_stats(
        self,
        user_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get usage statistics for a user.

        Args:
            user_id: User ID
            days: Number of days to analyze

        Returns:
            Dict with usage statistics
        """
        from src.core.database import ResearchQuery, Source, Finding

        with self.db_manager.get_session() as session:
            # Get date range
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Total queries
            total_queries = session.query(ResearchQuery).filter(
                ResearchQuery.user_id == user_id,
                ResearchQuery.created_at >= cutoff_date
            ).count()

            # Completed queries
            completed_queries = session.query(ResearchQuery).filter(
                ResearchQuery.user_id == user_id,
                ResearchQuery.status == 'completed',
                ResearchQuery.created_at >= cutoff_date
            ).count()

            # Get all completed queries for detailed stats
            queries = session.query(ResearchQuery).filter(
                ResearchQuery.user_id == user_id,
                ResearchQuery.status == 'completed',
                ResearchQuery.created_at >= cutoff_date
            ).all()

            # Calculate averages
            total_sources = 0
            total_findings = 0
            total_processing_time = 0
            total_confidence = 0
            source_type_counts = defaultdict(int)
            citation_styles = defaultdict(int)

            for query in queries:
                # Count sources
                sources = session.query(Source).filter(
                    Source.query_id == query.id
                ).all()
                total_sources += len(sources)

                # Source types
                for source in sources:
                    source_type_counts[source.source_type] += 1

                # Count findings
                findings = session.query(Finding).filter(
                    Finding.query_id == query.id
                ).all()
                total_findings += len(findings)

                # Accumulate confidence
                if query.confidence_score:
                    total_confidence += query.confidence_score

                # Accumulate processing time
                if query.processing_time_seconds:
                    total_processing_time += query.processing_time_seconds

            # Calculate averages
            avg_sources = total_sources / completed_queries if completed_queries > 0 else 0
            avg_findings = total_findings / completed_queries if completed_queries > 0 else 0
            avg_confidence = total_confidence / completed_queries if completed_queries > 0 else 0
            avg_processing_time = total_processing_time / completed_queries if completed_queries > 0 else 0

            # Most used sources
            most_used_sources = dict(sorted(
                source_type_counts.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5])

            return {
                'user_id': user_id,
                'period_days': days,
                'total_queries': total_queries,
                'completed_queries': completed_queries,
                'failed_queries': total_queries - completed_queries,
                'success_rate': (completed_queries / total_queries * 100) if total_queries > 0 else 0,
                'total_sources_retrieved': total_sources,
                'total_findings_generated': total_findings,
                'avg_sources_per_query': round(avg_sources, 2),
                'avg_findings_per_query': round(avg_findings, 2),
                'avg_confidence_score': round(avg_confidence, 3),
                'avg_processing_time_seconds': round(avg_processing_time, 2),
                'source_type_distribution': most_used_sources,
                'queries_by_day': self._get_queries_by_day(user_id, days)
            }

    def get_cost_analysis(
        self,
        user_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get cost analysis for a user.

        Args:
            user_id: User ID
            days: Number of days to analyze

        Returns:
            Dict with cost analysis
        """
        # This would require cost tracking integration
        # For now, return estimated costs based on usage
        stats = self.get_user_stats(user_id, days)

        # Rough cost estimates (assuming GPT-4)
        # Input: ~2000 tokens per source
        # Output: ~500 tokens per query
        avg_input_tokens = stats['avg_sources_per_query'] * 2000
        avg_output_tokens = 500

        # GPT-4 pricing: $0.03/1K input, $0.06/1K output
        estimated_cost_per_query = (
            (avg_input_tokens / 1000 * 0.03) +
            (avg_output_tokens / 1000 * 0.06)
        )

        total_estimated_cost = estimated_cost_per_query * stats['completed_queries']

        return {
            'user_id': user_id,
            'period_days': days,
            'total_queries': stats['completed_queries'],
            'estimated_cost_per_query': round(estimated_cost_per_query, 4),
            'estimated_total_cost': round(total_estimated_cost, 2),
            'avg_input_tokens': int(avg_input_tokens),
            'avg_output_tokens': int(avg_output_tokens),
            'note': 'Estimates based on GPT-4 pricing. Actual costs may vary.'
        }

    def get_popular_queries(
        self,
        limit: int = 10,
        days: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get most popular/common query patterns.

        Args:
            limit: Maximum number of results
            days: Number of days to analyze

        Returns:
            List of popular query patterns
        """
        from src.core.database import ResearchQuery

        with self.db_manager.get_session() as session:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            queries = session.query(ResearchQuery).filter(
                ResearchQuery.created_at >= cutoff_date,
                ResearchQuery.status == 'completed'
            ).order_by(
                ResearchQuery.created_at.desc()
            ).limit(limit * 3).all()  # Get more to find patterns

            # Extract keywords and patterns
            query_patterns = defaultdict(int)
            for query in queries:
                # Simple keyword extraction (first 3 words)
                words = query.query_text.lower().split()[:3]
                pattern = ' '.join(words)
                query_patterns[pattern] += 1

            # Sort by frequency
            popular = sorted(
                query_patterns.items(),
                key=lambda x: x[1],
                reverse=True
            )[:limit]

            return [
                {'pattern': pattern, 'count': count}
                for pattern, count in popular
            ]

    def get_performance_metrics(
        self,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Get system-wide performance metrics.

        Args:
            days: Number of days to analyze

        Returns:
            Dict with performance metrics
        """
        from src.core.database import ResearchQuery

        with self.db_manager.get_session() as session:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            queries = session.query(ResearchQuery).filter(
                ResearchQuery.created_at >= cutoff_date
            ).all()

            total = len(queries)
            completed = sum(1 for q in queries if q.status == 'completed')
            failed = sum(1 for q in queries if q.status == 'failed')
            pending = sum(1 for q in queries if q.status == 'pending')

            # Processing times for completed queries
            processing_times = [
                q.processing_time_seconds
                for q in queries
                if q.status == 'completed' and q.processing_time_seconds
            ]

            avg_processing_time = (
                sum(processing_times) / len(processing_times)
                if processing_times else 0
            )

            # Confidence scores
            confidence_scores = [
                q.confidence_score
                for q in queries
                if q.confidence_score is not None
            ]

            avg_confidence = (
                sum(confidence_scores) / len(confidence_scores)
                if confidence_scores else 0
            )

            return {
                'period_days': days,
                'total_queries': total,
                'completed': completed,
                'failed': failed,
                'pending': pending,
                'success_rate': (completed / total * 100) if total > 0 else 0,
                'avg_processing_time_seconds': round(avg_processing_time, 2),
                'avg_confidence_score': round(avg_confidence, 3),
                'queries_per_day': round(total / days, 2) if days > 0 else 0
            }

    def _get_queries_by_day(
        self,
        user_id: str,
        days: int
    ) -> List[Dict[str, Any]]:
        """Get query counts by day."""
        from src.core.database import ResearchQuery

        with self.db_manager.get_session() as session:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            queries = session.query(ResearchQuery).filter(
                ResearchQuery.user_id == user_id,
                ResearchQuery.created_at >= cutoff_date
            ).all()

            # Group by day
            queries_by_day = defaultdict(int)
            for query in queries:
                day_str = query.created_at.strftime('%Y-%m-%d')
                queries_by_day[day_str] += 1

            # Convert to list
            result = [
                {'date': day, 'count': count}
                for day, count in sorted(queries_by_day.items())
            ]

            return result

    def get_source_effectiveness(
        self,
        user_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Analyze source effectiveness.

        Args:
            user_id: User ID
            days: Number of days to analyze

        Returns:
            Dict with source effectiveness metrics
        """
        from src.core.database import ResearchQuery, Source

        with self.db_manager.get_session() as session:
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            # Get completed queries
            queries = session.query(ResearchQuery).filter(
                ResearchQuery.user_id == user_id,
                ResearchQuery.status == 'completed',
                ResearchQuery.created_at >= cutoff_date
            ).all()

            source_stats = defaultdict(lambda: {
                'count': 0,
                'avg_relevance': 0,
                'total_relevance': 0
            })

            for query in queries:
                sources = session.query(Source).filter(
                    Source.query_id == query.id
                ).all()

                for source in sources:
                    source_type = source.source_type
                    source_stats[source_type]['count'] += 1

                    if source.relevance_score:
                        source_stats[source_type]['total_relevance'] += source.relevance_score

            # Calculate averages
            for source_type, stats in source_stats.items():
                if stats['count'] > 0:
                    stats['avg_relevance'] = round(
                        stats['total_relevance'] / stats['count'], 3
                    )
                del stats['total_relevance']  # Remove temporary field

            return {
                'user_id': user_id,
                'period_days': days,
                'source_statistics': dict(source_stats)
            }
