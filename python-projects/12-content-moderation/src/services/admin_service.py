"""
Admin Service for Content Moderation.

Handles review workflows, appeals, policy management, and admin operations.
"""

import logging
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime

from ..core.database import (
    DatabaseManager, User, ContentItem, Review, Policy, AuditLog,
    ContentStatus, ViolationCategory, UserRole
)

logging.basicConfig(level=logging.INFO)


class AdminService:
    """Service for admin and moderator operations."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """
        Initialize admin service.

        Args:
            db_manager: Database manager instance
        """
        self.db_manager = db_manager or DatabaseManager()
        logging.info("AdminService initialized")

    def get_review_queue(
        self,
        moderator: User,
        status: Optional[str] = None,
        priority: Optional[int] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[bool, List[ContentItem], int, Optional[str]]:
        """
        Get content items for review.

        Args:
            moderator: Moderator user
            status: Filter by status (flagged, pending, etc.)
            priority: Filter by priority
            limit: Page size
            offset: Page offset

        Returns:
            Tuple of (success, items, total_count, error_message)
        """
        try:
            with self.db_manager.get_session() as db:
                # Build query for flagged or pending content
                query = db.query(ContentItem)

                if status:
                    try:
                        status_enum = ContentStatus(status)
                        query = query.filter(ContentItem.status == status_enum)
                    except ValueError:
                        return False, [], 0, f"Invalid status: {status}"
                else:
                    # Default: show flagged and pending items
                    query = query.filter(
                        ContentItem.status.in_([ContentStatus.FLAGGED, ContentStatus.PENDING])
                    )

                if priority is not None:
                    query = query.filter(ContentItem.priority == priority)

                # Order by priority (high first), then creation date
                query = query.order_by(
                    ContentItem.priority.desc(),
                    ContentItem.created_at.desc()
                )

                total = query.count()
                items = query.limit(limit).offset(offset).all()

                logging.info(f"Retrieved {len(items)} items for review (total: {total})")
                return True, items, total, None

        except Exception as e:
            logging.error(f"Failed to get review queue: {e}")
            return False, [], 0, str(e)

    def submit_review(
        self,
        moderator: User,
        content_id: str,
        approved: bool,
        category: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Tuple[bool, Optional[Review], Optional[str]]:
        """
        Submit manual review decision.

        Args:
            moderator: Moderator user
            content_id: Content item ID
            approved: Whether content is approved
            category: Violation category if rejected
            notes: Review notes

        Returns:
            Tuple of (success, review, error_message)
        """
        try:
            with self.db_manager.get_session() as db:
                # Get content item
                content = db.query(ContentItem).filter(ContentItem.id == content_id).first()

                if not content:
                    return False, None, "Content not found"

                # Create review record
                review = Review(
                    content_id=content_id,
                    moderator_id=moderator.id,
                    action='manual_approve' if approved else 'manual_reject',
                    approved=approved,
                    category=ViolationCategory(category) if category else None,
                    notes=notes or '',
                    is_appeal_review=False
                )

                db.add(review)

                # Update content status
                if approved:
                    content.status = ContentStatus.APPROVED
                else:
                    content.status = ContentStatus.REJECTED

                content.moderated_at = datetime.utcnow()

                # Create audit log
                audit = AuditLog(
                    event_type='manual_review',
                    actor_id=moderator.id,
                    resource_type='content',
                    resource_id=content_id,
                    action='approve' if approved else 'reject',
                    details={
                        'category': category,
                        'notes': notes,
                        'moderator_username': moderator.username
                    }
                )

                db.add(audit)
                db.commit()
                db.refresh(review)

                logging.info(
                    f"Review submitted by {moderator.username} for content {content_id}: "
                    f"{'approved' if approved else 'rejected'}"
                )

                return True, review, None

        except Exception as e:
            logging.error(f"Failed to submit review: {e}")
            return False, None, str(e)

    def create_appeal(
        self,
        user: User,
        content_id: str,
        reason: str
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Create appeal for rejected content.

        Args:
            user: User submitting appeal
            content_id: Content item ID
            reason: Appeal reason

        Returns:
            Tuple of (success, appeal_id, error_message)
        """
        try:
            with self.db_manager.get_session() as db:
                # Get content item
                content = db.query(ContentItem).filter(ContentItem.id == content_id).first()

                if not content:
                    return False, None, "Content not found"

                # Verify ownership
                if content.user_id != user.id:
                    return False, None, "Access denied"

                # Check if content is rejected
                if content.status != ContentStatus.REJECTED:
                    return False, None, "Can only appeal rejected content"

                # Check for existing appeal
                existing_appeal = db.query(Review).filter(
                    Review.content_id == content_id,
                    Review.is_appeal_review == True
                ).first()

                if existing_appeal:
                    return False, None, "Appeal already exists"

                # Create appeal review record (pending moderator action)
                appeal = Review(
                    content_id=content_id,
                    moderator_id=None,  # Not yet assigned
                    action='appeal_submitted',
                    approved=False,
                    notes=reason,
                    is_appeal_review=True
                )

                db.add(appeal)

                # Update content status to pending review
                content.status = ContentStatus.FLAGGED  # Flag for appeal review

                # Create audit log
                audit = AuditLog(
                    event_type='appeal_created',
                    actor_id=user.id,
                    resource_type='content',
                    resource_id=content_id,
                    action='submit_appeal',
                    details={
                        'reason': reason,
                        'username': user.username
                    }
                )

                db.add(audit)
                db.commit()
                db.refresh(appeal)

                logging.info(f"Appeal created by {user.username} for content {content_id}")

                return True, appeal.id, None

        except Exception as e:
            logging.error(f"Failed to create appeal: {e}")
            return False, None, str(e)

    def review_appeal(
        self,
        moderator: User,
        appeal_id: str,
        approved: bool,
        notes: Optional[str] = None
    ) -> Tuple[bool, Optional[Review], Optional[str]]:
        """
        Review an appeal.

        Args:
            moderator: Moderator user
            appeal_id: Appeal review ID
            approved: Whether to approve the appeal
            notes: Review notes

        Returns:
            Tuple of (success, review, error_message)
        """
        try:
            with self.db_manager.get_session() as db:
                # Get appeal
                appeal = db.query(Review).filter(Review.id == appeal_id).first()

                if not appeal or not appeal.is_appeal_review:
                    return False, None, "Appeal not found"

                # Get content
                content = db.query(ContentItem).filter(
                    ContentItem.id == appeal.content_id
                ).first()

                if not content:
                    return False, None, "Content not found"

                # Update appeal
                appeal.moderator_id = moderator.id
                appeal.action = 'appeal_approved' if approved else 'appeal_rejected'
                appeal.approved = approved

                if notes:
                    appeal.notes = f"{appeal.notes}\n\nModerator response: {notes}"

                # Update content status
                if approved:
                    content.status = ContentStatus.APPROVED
                else:
                    content.status = ContentStatus.REJECTED

                content.moderated_at = datetime.utcnow()

                # Create audit log
                audit = AuditLog(
                    event_type='appeal_reviewed',
                    actor_id=moderator.id,
                    resource_type='content',
                    resource_id=content.id,
                    action='approve_appeal' if approved else 'reject_appeal',
                    details={
                        'appeal_id': appeal_id,
                        'notes': notes,
                        'moderator_username': moderator.username
                    }
                )

                db.add(audit)
                db.commit()
                db.refresh(appeal)

                logging.info(
                    f"Appeal {appeal_id} reviewed by {moderator.username}: "
                    f"{'approved' if approved else 'rejected'}"
                )

                return True, appeal, None

        except Exception as e:
            logging.error(f"Failed to review appeal: {e}")
            return False, None, str(e)

    def list_policies(
        self,
        enabled_only: bool = False
    ) -> Tuple[bool, List[Policy], Optional[str]]:
        """
        List moderation policies.

        Args:
            enabled_only: Only return enabled policies

        Returns:
            Tuple of (success, policies, error_message)
        """
        try:
            with self.db_manager.get_session() as db:
                query = db.query(Policy)

                if enabled_only:
                    query = query.filter(Policy.enabled == True)

                policies = query.order_by(Policy.severity.desc()).all()

                return True, policies, None

        except Exception as e:
            logging.error(f"Failed to list policies: {e}")
            return False, [], str(e)

    def create_policy(
        self,
        admin: User,
        name: str,
        category: str,
        auto_reject_threshold: float = 0.9,
        flag_review_threshold: float = 0.5,
        severity: int = 5,
        enabled: bool = True
    ) -> Tuple[bool, Optional[Policy], Optional[str]]:
        """
        Create moderation policy.

        Args:
            admin: Admin user
            name: Policy name
            category: Violation category
            auto_reject_threshold: Auto-reject threshold
            flag_review_threshold: Flag for review threshold
            severity: Severity level (1-10)
            enabled: Whether policy is enabled

        Returns:
            Tuple of (success, policy, error_message)
        """
        try:
            with self.db_manager.get_session() as db:
                # Check if policy already exists
                existing = db.query(Policy).filter(Policy.name == name).first()

                if existing:
                    return False, None, f"Policy '{name}' already exists"

                # Create policy
                policy = Policy(
                    name=name,
                    category=ViolationCategory(category),
                    auto_reject_threshold=auto_reject_threshold,
                    flag_review_threshold=flag_review_threshold,
                    enabled=enabled,
                    severity=severity
                )

                db.add(policy)

                # Create audit log
                audit = AuditLog(
                    event_type='policy_created',
                    actor_id=admin.id,
                    resource_type='policy',
                    resource_id=None,  # Will be set after commit
                    action='create',
                    details={
                        'name': name,
                        'category': category,
                        'severity': severity,
                        'admin_username': admin.username
                    }
                )

                db.add(audit)
                db.commit()
                db.refresh(policy)

                # Update audit log with policy ID
                audit.resource_id = policy.id
                db.commit()

                logging.info(f"Policy '{name}' created by {admin.username}")

                return True, policy, None

        except Exception as e:
            logging.error(f"Failed to create policy: {e}")
            return False, None, str(e)

    def update_policy(
        self,
        admin: User,
        policy_id: str,
        auto_reject_threshold: Optional[float] = None,
        flag_review_threshold: Optional[float] = None,
        severity: Optional[int] = None,
        enabled: Optional[bool] = None
    ) -> Tuple[bool, Optional[Policy], Optional[str]]:
        """
        Update moderation policy.

        Args:
            admin: Admin user
            policy_id: Policy ID
            auto_reject_threshold: New auto-reject threshold
            flag_review_threshold: New flag threshold
            severity: New severity level
            enabled: New enabled status

        Returns:
            Tuple of (success, policy, error_message)
        """
        try:
            with self.db_manager.get_session() as db:
                policy = db.query(Policy).filter(Policy.id == policy_id).first()

                if not policy:
                    return False, None, "Policy not found"

                # Track changes
                changes = {}

                if auto_reject_threshold is not None:
                    changes['auto_reject_threshold'] = {
                        'old': policy.auto_reject_threshold,
                        'new': auto_reject_threshold
                    }
                    policy.auto_reject_threshold = auto_reject_threshold

                if flag_review_threshold is not None:
                    changes['flag_review_threshold'] = {
                        'old': policy.flag_review_threshold,
                        'new': flag_review_threshold
                    }
                    policy.flag_review_threshold = flag_review_threshold

                if severity is not None:
                    changes['severity'] = {
                        'old': policy.severity,
                        'new': severity
                    }
                    policy.severity = severity

                if enabled is not None:
                    changes['enabled'] = {
                        'old': policy.enabled,
                        'new': enabled
                    }
                    policy.enabled = enabled

                policy.updated_at = datetime.utcnow()

                # Create audit log
                audit = AuditLog(
                    event_type='policy_updated',
                    actor_id=admin.id,
                    resource_type='policy',
                    resource_id=policy_id,
                    action='update',
                    details={
                        'policy_name': policy.name,
                        'changes': changes,
                        'admin_username': admin.username
                    }
                )

                db.add(audit)
                db.commit()
                db.refresh(policy)

                logging.info(f"Policy '{policy.name}' updated by {admin.username}")

                return True, policy, None

        except Exception as e:
            logging.error(f"Failed to update policy: {e}")
            return False, None, str(e)

    def get_admin_stats(self) -> Dict[str, Any]:
        """
        Get admin dashboard statistics.

        Returns:
            Statistics dictionary
        """
        try:
            with self.db_manager.get_session() as db:
                stats = {
                    'content': {
                        'total': db.query(ContentItem).count(),
                        'pending': db.query(ContentItem).filter(
                            ContentItem.status == ContentStatus.PENDING
                        ).count(),
                        'flagged': db.query(ContentItem).filter(
                            ContentItem.status == ContentStatus.FLAGGED
                        ).count(),
                        'approved': db.query(ContentItem).filter(
                            ContentItem.status == ContentStatus.APPROVED
                        ).count(),
                        'rejected': db.query(ContentItem).filter(
                            ContentItem.status == ContentStatus.REJECTED
                        ).count()
                    },
                    'reviews': {
                        'total': db.query(Review).count(),
                        'manual': db.query(Review).filter(
                            Review.action.in_(['manual_approve', 'manual_reject'])
                        ).count(),
                        'appeals_pending': db.query(Review).filter(
                            Review.is_appeal_review == True,
                            Review.moderator_id == None
                        ).count(),
                        'appeals_resolved': db.query(Review).filter(
                            Review.is_appeal_review == True,
                            Review.moderator_id != None
                        ).count()
                    },
                    'users': {
                        'total': db.query(User).count(),
                        'active': db.query(User).filter(User.is_active == True).count(),
                        'moderators': db.query(User).filter(
                            User.role.in_([UserRole.MODERATOR, UserRole.ADMIN])
                        ).count()
                    },
                    'policies': {
                        'total': db.query(Policy).count(),
                        'enabled': db.query(Policy).filter(Policy.enabled == True).count()
                    }
                }

                return stats

        except Exception as e:
            logging.error(f"Failed to get admin stats: {e}")
            return {}


# Global admin service instance
_admin_service_instance = None


def get_admin_service() -> AdminService:
    """
    Get global AdminService instance.

    Returns:
        AdminService singleton
    """
    global _admin_service_instance
    if _admin_service_instance is None:
        _admin_service_instance = AdminService()
    return _admin_service_instance
