"""
Rule Marketplace Service - Share and discover custom analysis rules
"""

import json
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import func, and_, or_

from src.core.database import DatabaseManager, CustomRule, RuleRating, User


class RuleMarketplaceService:
    """Service for managing rule marketplace and sharing."""

    def export_rule(self, rule_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Export a rule to JSON format.

        Args:
            rule_id: Rule ID to export
            user_id: User ID (must own the rule)

        Returns:
            Rule data as dictionary
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            rule = db.query(CustomRule).filter(
                CustomRule.id == rule_id,
                CustomRule.user_id == user_id
            ).first()

            if not rule:
                return None

            # Create exportable format
            export_data = {
                'id': rule.id,
                'name': rule.name,
                'description': rule.description,
                'category': rule.category,
                'severity': rule.severity,
                'languages': rule.languages.split(',') if rule.languages else [],
                'pattern_type': rule.pattern_type,
                'pattern_data': rule.pattern_data,
                'message': rule.message,
                'fix_suggestion': rule.fix_suggestion,
                'auto_fixable': rule.auto_fixable,
                'tags': rule.tags.split(',') if rule.tags else [],
                'original_author': rule.original_author,
                'version': '1.0',
                'exported_at': datetime.now(timezone.utc).isoformat()
            }

            return export_data

    def export_rules_bulk(self, user_id: str, rule_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """
        Export multiple rules at once.

        Args:
            user_id: User ID
            rule_ids: Optional list of specific rule IDs to export (exports all if None)

        Returns:
            List of exported rule data
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            query = db.query(CustomRule).filter(CustomRule.user_id == user_id)

            if rule_ids:
                query = query.filter(CustomRule.id.in_(rule_ids))

            rules = query.all()

            return [self.export_rule(rule.id, user_id) for rule in rules if rule]

    def import_rule(self, rule_data: Dict[str, Any], user_id: str,
                    overwrite: bool = False) -> Dict[str, Any]:
        """
        Import a rule from JSON data.

        Args:
            rule_data: Rule data dictionary
            user_id: User ID importing the rule
            overwrite: Whether to overwrite if rule ID exists

        Returns:
            Result dictionary with success status and imported rule
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Check if rule already exists
            existing = db.query(CustomRule).filter(
                CustomRule.id == rule_data['id'],
                CustomRule.user_id == user_id
            ).first()

            if existing and not overwrite:
                # Generate new ID if not overwriting
                rule_data['id'] = f"{rule_data['id']}_IMPORTED_{uuid.uuid4().hex[:8]}"

            # Create or update rule
            if existing and overwrite:
                # Update existing
                for key, value in rule_data.items():
                    if key == 'languages' and isinstance(value, list):
                        setattr(existing, key, ','.join(value))
                    elif key == 'tags' and isinstance(value, list):
                        setattr(existing, key, ','.join(value))
                    elif key not in ['version', 'exported_at']:
                        setattr(existing, key, value)

                existing.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(existing)

                return {
                    'success': True,
                    'action': 'updated',
                    'rule': existing.to_dict()
                }
            else:
                # Create new
                new_rule = CustomRule(
                    id=rule_data['id'],
                    user_id=user_id,
                    name=rule_data['name'],
                    description=rule_data['description'],
                    category=rule_data['category'],
                    severity=rule_data['severity'],
                    languages=','.join(rule_data['languages']) if isinstance(rule_data['languages'], list) else rule_data['languages'],
                    pattern_type=rule_data['pattern_type'],
                    pattern_data=rule_data['pattern_data'],
                    message=rule_data['message'],
                    fix_suggestion=rule_data.get('fix_suggestion'),
                    auto_fixable=rule_data.get('auto_fixable', False),
                    tags=','.join(rule_data.get('tags', [])) if isinstance(rule_data.get('tags'), list) else rule_data.get('tags', ''),
                    original_author=rule_data.get('original_author'),
                    enabled=True
                )

                db.add(new_rule)
                db.commit()
                db.refresh(new_rule)

                return {
                    'success': True,
                    'action': 'created',
                    'rule': new_rule.to_dict()
                }

    def get_marketplace_rules(self,
                             category: Optional[str] = None,
                             language: Optional[str] = None,
                             search: Optional[str] = None,
                             sort_by: str = 'popular',
                             limit: int = 50,
                             offset: int = 0) -> Dict[str, Any]:
        """
        Get rules from the marketplace.

        Args:
            category: Filter by category
            language: Filter by language
            search: Search query
            sort_by: Sort order (popular, recent, rating)
            limit: Number of results
            offset: Offset for pagination

        Returns:
            Dictionary with rules and metadata
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Base query for public rules
            query = db.query(
                CustomRule,
                func.coalesce(func.avg(RuleRating.rating), 0).label('avg_rating'),
                func.count(RuleRating.id).label('rating_count')
            ).outerjoin(RuleRating).filter(
                CustomRule.visibility == 'public'
            ).group_by(CustomRule.id)

            # Apply filters
            if category:
                query = query.filter(CustomRule.category == category)

            if language:
                query = query.filter(CustomRule.languages.like(f'%{language}%'))

            if search:
                search_pattern = f'%{search}%'
                query = query.filter(
                    or_(
                        CustomRule.name.like(search_pattern),
                        CustomRule.description.like(search_pattern),
                        CustomRule.tags.like(search_pattern)
                    )
                )

            # Apply sorting
            if sort_by == 'popular':
                query = query.order_by(CustomRule.download_count.desc())
            elif sort_by == 'recent':
                query = query.order_by(CustomRule.created_at.desc())
            elif sort_by == 'rating':
                query = query.order_by(func.avg(RuleRating.rating).desc())
            elif sort_by == 'forks':
                query = query.order_by(CustomRule.fork_count.desc())

            # Get total count
            total = query.count()

            # Apply pagination
            results = query.limit(limit).offset(offset).all()

            # Format results
            rules = []
            for rule, avg_rating, rating_count in results:
                rule_dict = rule.to_dict()
                rule_dict['avg_rating'] = float(avg_rating) if avg_rating else 0.0
                rule_dict['rating_count'] = rating_count
                rules.append(rule_dict)

            return {
                'rules': rules,
                'total': total,
                'limit': limit,
                'offset': offset,
                'has_more': (offset + limit) < total
            }

    def fork_rule(self, rule_id: str, user_id: str) -> Dict[str, Any]:
        """
        Fork/copy a public rule to user's collection.

        Args:
            rule_id: Original rule ID
            user_id: User ID forking the rule

        Returns:
            Result dictionary with forked rule
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Get original rule
            original = db.query(CustomRule).filter(
                CustomRule.id == rule_id,
                CustomRule.visibility == 'public'
            ).first()

            if not original:
                return {
                    'success': False,
                    'error': 'Rule not found or not public'
                }

            # Check if user already forked this rule
            existing_fork = db.query(CustomRule).filter(
                CustomRule.user_id == user_id,
                CustomRule.forked_from == rule_id
            ).first()

            if existing_fork:
                return {
                    'success': False,
                    'error': 'You have already forked this rule',
                    'rule': existing_fork.to_dict()
                }

            # Create forked rule with new ID
            new_id = f"{original.id}_FORK_{uuid.uuid4().hex[:8]}"

            forked_rule = CustomRule(
                id=new_id,
                user_id=user_id,
                name=f"{original.name} (Fork)",
                description=original.description,
                category=original.category,
                severity=original.severity,
                languages=original.languages,
                pattern_type=original.pattern_type,
                pattern_data=original.pattern_data,
                message=original.message,
                fix_suggestion=original.fix_suggestion,
                auto_fixable=original.auto_fixable,
                tags=original.tags,
                visibility='private',
                original_author=original.original_author or db.query(User).filter(User.id == original.user_id).first().username,
                forked_from=rule_id,
                enabled=True
            )

            db.add(forked_rule)

            # Increment fork count on original
            original.fork_count += 1
            original.download_count += 1

            db.commit()
            db.refresh(forked_rule)

            return {
                'success': True,
                'rule': forked_rule.to_dict()
            }

    def rate_rule(self, rule_id: str, user_id: str, rating: int,
                  review: Optional[str] = None) -> Dict[str, Any]:
        """
        Rate a rule in the marketplace.

        Args:
            rule_id: Rule ID to rate
            user_id: User ID rating the rule
            rating: Rating value (1-5)
            review: Optional review text

        Returns:
            Result dictionary
        """
        if not (1 <= rating <= 5):
            return {
                'success': False,
                'error': 'Rating must be between 1 and 5'
            }

        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Check if rule exists and is public
            rule = db.query(CustomRule).filter(
                CustomRule.id == rule_id,
                CustomRule.visibility == 'public'
            ).first()

            if not rule:
                return {
                    'success': False,
                    'error': 'Rule not found or not public'
                }

            # Check for existing rating
            existing_rating = db.query(RuleRating).filter(
                RuleRating.rule_id == rule_id,
                RuleRating.user_id == user_id
            ).first()

            if existing_rating:
                # Update existing rating
                existing_rating.rating = rating
                existing_rating.review = review
                existing_rating.updated_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(existing_rating)

                return {
                    'success': True,
                    'action': 'updated',
                    'rating': existing_rating.to_dict()
                }
            else:
                # Create new rating
                new_rating = RuleRating(
                    rule_id=rule_id,
                    user_id=user_id,
                    rating=rating,
                    review=review
                )

                db.add(new_rating)
                db.commit()
                db.refresh(new_rating)

                return {
                    'success': True,
                    'action': 'created',
                    'rating': new_rating.to_dict()
                }

    def get_featured_rules(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get featured rules from the marketplace.

        Args:
            limit: Number of featured rules to return

        Returns:
            List of featured rules
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            rules = db.query(
                CustomRule,
                func.coalesce(func.avg(RuleRating.rating), 0).label('avg_rating'),
                func.count(RuleRating.id).label('rating_count')
            ).outerjoin(RuleRating).filter(
                CustomRule.visibility == 'public',
                CustomRule.is_featured == True
            ).group_by(CustomRule.id).limit(limit).all()

            result = []
            for rule, avg_rating, rating_count in rules:
                rule_dict = rule.to_dict()
                rule_dict['avg_rating'] = float(avg_rating) if avg_rating else 0.0
                rule_dict['rating_count'] = rating_count
                result.append(rule_dict)

            return result

    def get_rule_ratings(self, rule_id: str, limit: int = 10,
                        offset: int = 0) -> Dict[str, Any]:
        """
        Get ratings for a specific rule.

        Args:
            rule_id: Rule ID
            limit: Number of ratings to return
            offset: Offset for pagination

        Returns:
            Dictionary with ratings and metadata
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Get ratings with user information
            query = db.query(
                RuleRating,
                User.username
            ).join(User).filter(
                RuleRating.rule_id == rule_id
            ).order_by(RuleRating.created_at.desc())

            total = query.count()
            results = query.limit(limit).offset(offset).all()

            ratings = []
            for rating, username in results:
                rating_dict = rating.to_dict()
                rating_dict['username'] = username
                ratings.append(rating_dict)

            # Calculate average rating
            avg_rating = db.query(func.avg(RuleRating.rating)).filter(
                RuleRating.rule_id == rule_id
            ).scalar() or 0.0

            return {
                'ratings': ratings,
                'total': total,
                'avg_rating': float(avg_rating),
                'limit': limit,
                'offset': offset,
                'has_more': (offset + limit) < total
            }

    def publish_rule(self, rule_id: str, user_id: str, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Publish a rule to the marketplace.

        Args:
            rule_id: Rule ID to publish
            user_id: User ID (must own the rule)
            tags: Optional tags for discoverability

        Returns:
            Result dictionary
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            rule = db.query(CustomRule).filter(
                CustomRule.id == rule_id,
                CustomRule.user_id == user_id
            ).first()

            if not rule:
                return {
                    'success': False,
                    'error': 'Rule not found'
                }

            rule.visibility = 'public'
            if tags:
                rule.tags = ','.join(tags)

            db.commit()
            db.refresh(rule)

            return {
                'success': True,
                'rule': rule.to_dict()
            }

    def unpublish_rule(self, rule_id: str, user_id: str) -> Dict[str, Any]:
        """
        Unpublish a rule from the marketplace.

        Args:
            rule_id: Rule ID to unpublish
            user_id: User ID (must own the rule)

        Returns:
            Result dictionary
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            rule = db.query(CustomRule).filter(
                CustomRule.id == rule_id,
                CustomRule.user_id == user_id
            ).first()

            if not rule:
                return {
                    'success': False,
                    'error': 'Rule not found'
                }

            rule.visibility = 'private'
            db.commit()
            db.refresh(rule)

            return {
                'success': True,
                'rule': rule.to_dict()
            }
