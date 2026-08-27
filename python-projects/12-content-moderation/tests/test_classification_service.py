"""
Unit tests for resolve_policy_thresholds().

Workers previously called apply_moderation_policy() with no arguments at
all, so every submission was judged against hardcoded defaults regardless
of anything an admin configured via the Policy admin UI. These tests
lock in the fix: an enabled Policy for a category should actually change
the thresholds used, a disabled one should be ignored, and an
unconfigured category should fall back to the same defaults as before.
"""

import pytest

from src.core.database import DatabaseManager, Policy, ViolationCategory
from src.services.classification_service import resolve_policy_thresholds, DEFAULT_THRESHOLDS


@pytest.fixture
def db_manager():
    db = DatabaseManager('sqlite:///:memory:')
    db.create_tables()
    return db


def test_no_policy_falls_back_to_defaults(db_manager):
    with db_manager.get_session() as db:
        thresholds = resolve_policy_thresholds(db, 'spam')
        assert thresholds == DEFAULT_THRESHOLDS


def test_enabled_policy_overrides_defaults(db_manager):
    with db_manager.get_session() as db:
        policy = Policy(
            name='Strict Spam',
            category=ViolationCategory.SPAM,
            auto_reject_threshold=0.3,
            auto_approve_threshold=0.95,
            flag_review_threshold=0.1,
            enabled=True,
            severity=8
        )
        db.add(policy)
        db.commit()

        thresholds = resolve_policy_thresholds(db, 'spam')
        assert thresholds['auto_reject_threshold'] == 0.3
        assert thresholds['flag_review_threshold'] == 0.1


def test_disabled_policy_is_ignored(db_manager):
    with db_manager.get_session() as db:
        policy = Policy(
            name='Disabled Spam Policy',
            category=ViolationCategory.SPAM,
            auto_reject_threshold=0.1,
            enabled=False,
            severity=8
        )
        db.add(policy)
        db.commit()

        thresholds = resolve_policy_thresholds(db, 'spam')
        assert thresholds == DEFAULT_THRESHOLDS


def test_multiple_enabled_policies_uses_highest_severity(db_manager):
    with db_manager.get_session() as db:
        db.add(Policy(
            name='Low Severity Spam',
            category=ViolationCategory.SPAM,
            auto_reject_threshold=0.8,
            enabled=True,
            severity=2
        ))
        db.add(Policy(
            name='High Severity Spam',
            category=ViolationCategory.SPAM,
            auto_reject_threshold=0.2,
            enabled=True,
            severity=9
        ))
        db.commit()

        thresholds = resolve_policy_thresholds(db, 'spam')
        assert thresholds['auto_reject_threshold'] == 0.2


def test_clean_category_policy_controls_auto_approve(db_manager):
    with db_manager.get_session() as db:
        policy = Policy(
            name='Lenient Clean Approval',
            category=ViolationCategory.CLEAN,
            auto_approve_threshold=0.7,
            enabled=True,
            severity=1
        )
        db.add(policy)
        db.commit()

        thresholds = resolve_policy_thresholds(db, 'clean')
        assert thresholds['auto_approve_threshold'] == 0.7


def test_unknown_category_falls_back_to_defaults(db_manager):
    with db_manager.get_session() as db:
        thresholds = resolve_policy_thresholds(db, 'not_a_real_category')
        assert thresholds == DEFAULT_THRESHOLDS
