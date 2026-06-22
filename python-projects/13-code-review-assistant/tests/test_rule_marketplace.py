"""
Tests for Rule Marketplace Service
"""

import pytest
import uuid
from datetime import datetime, timezone

from src.core.database import DatabaseManager, CustomRule, RuleRating, User
from src.services.rule_marketplace_service import RuleMarketplaceService


@pytest.fixture
def db_manager():
    """Database manager fixture"""
    db_manager = DatabaseManager()
    # Tables are created automatically in __init__
    yield db_manager
    # Cleanup after tests
    with db_manager.get_session() as db:
        db.query(RuleRating).delete()
        db.query(CustomRule).delete()
        db.query(User).delete()
        db.commit()


@pytest.fixture
def marketplace_service():
    """Marketplace service fixture"""
    return RuleMarketplaceService()


@pytest.fixture
def test_user(db_manager):
    """Create a test user"""
    user_id = f"test_user_{uuid.uuid4().hex[:8]}"
    with db_manager.get_session() as db:
        user = User(
            id=user_id,
            username="testuser",
            email="test@example.com",
            password_hash="hash",
            role="user"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture
def test_user2(db_manager):
    """Create a second test user"""
    user_id = f"test_user2_{uuid.uuid4().hex[:8]}"
    with db_manager.get_session() as db:
        user = User(
            id=user_id,
            username="testuser2",
            email="test2@example.com",
            password_hash="hash",
            role="user"
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture
def test_rule(db_manager, test_user):
    """Create a test custom rule"""
    rule_id = f"test_rule_{uuid.uuid4().hex[:8]}"
    with db_manager.get_session() as db:
        rule = CustomRule(
            id=rule_id,
            user_id=test_user.id,
            name="Test Security Rule",
            description="A test security rule",
            category="security",
            severity="error",
            languages="python,javascript",
            pattern_type="regex",
            pattern_data={"pattern": "eval\\(.*\\)"},
            message="Avoid using eval()",
            fix_suggestion="Use safer alternatives",
            auto_fixable=False,
            tags="security,dangerous",
            visibility="private",
            original_author="testuser",
            enabled=True
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule


@pytest.fixture
def public_rule(db_manager, test_user):
    """Create a public test rule"""
    rule_id = f"public_rule_{uuid.uuid4().hex[:8]}"
    with db_manager.get_session() as db:
        rule = CustomRule(
            id=rule_id,
            user_id=test_user.id,
            name="Public Security Rule",
            description="A public security rule",
            category="security",
            severity="critical",
            languages="python",
            pattern_type="regex",
            pattern_data={"pattern": "password\\s*=\\s*['\"].*['\"]"},
            message="Hardcoded password detected",
            fix_suggestion="Use environment variables",
            auto_fixable=False,
            tags="security,credentials",
            visibility="public",
            original_author="testuser",
            is_featured=True,
            enabled=True
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)
        return rule


class TestExportRule:
    """Test rule export functionality"""

    def test_export_rule_success(self, marketplace_service, test_rule, test_user):
        """Test successful rule export"""
        result = marketplace_service.export_rule(test_rule.id, test_user.id)

        assert result is not None
        assert result['id'] == test_rule.id
        assert result['name'] == test_rule.name
        assert result['description'] == test_rule.description
        assert result['category'] == test_rule.category
        assert result['severity'] == test_rule.severity
        assert result['languages'] == ['python', 'javascript']
        assert result['pattern_type'] == test_rule.pattern_type
        assert result['message'] == test_rule.message
        assert result['fix_suggestion'] == test_rule.fix_suggestion
        assert result['auto_fixable'] == test_rule.auto_fixable
        assert result['tags'] == ['security', 'dangerous']
        assert result['version'] == '1.0'
        assert 'exported_at' in result

    def test_export_rule_not_found(self, marketplace_service, test_user):
        """Test export of non-existent rule"""
        result = marketplace_service.export_rule("nonexistent", test_user.id)
        assert result is None

    def test_export_rule_wrong_user(self, marketplace_service, test_rule, test_user2):
        """Test export rule owned by different user"""
        result = marketplace_service.export_rule(test_rule.id, test_user2.id)
        assert result is None


class TestExportRulesBulk:
    """Test bulk rule export"""

    def test_export_all_user_rules(self, marketplace_service, db_manager, test_user):
        """Test exporting all rules for a user"""
        # Create multiple rules
        with db_manager.get_session() as db:
            for i in range(3):
                rule = CustomRule(
                    id=f"bulk_rule_{i}_{uuid.uuid4().hex[:8]}",
                    user_id=test_user.id,
                    name=f"Rule {i}",
                    description=f"Description {i}",
                    category="security",
                    severity="warning",
                    languages="python",
                    pattern_type="regex",
                    pattern_data={"pattern": "test"},
                    message="Test message",
                    enabled=True
                )
                db.add(rule)
            db.commit()

        result = marketplace_service.export_rules_bulk(test_user.id)
        assert len(result) >= 3
        assert all(r is not None for r in result)

    def test_export_specific_rules(self, marketplace_service, db_manager, test_user):
        """Test exporting specific rules by ID"""
        # Create multiple rules
        rule_ids = []
        with db_manager.get_session() as db:
            for i in range(3):
                rule_id = f"specific_rule_{i}_{uuid.uuid4().hex[:8]}"
                rule_ids.append(rule_id)
                rule = CustomRule(
                    id=rule_id,
                    user_id=test_user.id,
                    name=f"Specific Rule {i}",
                    description=f"Description {i}",
                    category="security",
                    severity="info",
                    languages="python",
                    pattern_type="regex",
                    pattern_data={"pattern": "test"},
                    message="Test message",
                    enabled=True
                )
                db.add(rule)
            db.commit()

        # Export only first 2 rules
        result = marketplace_service.export_rules_bulk(test_user.id, rule_ids[:2])
        assert len(result) == 2


class TestImportRule:
    """Test rule import functionality"""

    def test_import_new_rule(self, marketplace_service, test_user):
        """Test importing a new rule"""
        rule_data = {
            'id': f"import_test_{uuid.uuid4().hex[:8]}",
            'name': 'Imported Rule',
            'description': 'An imported rule',
            'category': 'performance',
            'severity': 'warning',
            'languages': ['python'],
            'pattern_type': 'regex',
            'pattern_data': {'pattern': 'time\\.sleep\\(.*\\)'},
            'message': 'Avoid blocking sleep',
            'fix_suggestion': 'Use async sleep',
            'auto_fixable': False,
            'tags': ['performance', 'async'],
            'original_author': 'original_author'
        }

        result = marketplace_service.import_rule(rule_data, test_user.id)

        assert result['success'] is True
        assert result['action'] == 'created'
        assert result['rule']['name'] == 'Imported Rule'

    def test_import_duplicate_creates_new(self, marketplace_service, test_rule, test_user):
        """Test importing duplicate rule creates new one"""
        rule_data = marketplace_service.export_rule(test_rule.id, test_user.id)

        result = marketplace_service.import_rule(rule_data, test_user.id, overwrite=False)

        assert result['success'] is True
        assert result['action'] == 'created'
        # Should have a different ID
        assert result['rule']['id'] != test_rule.id
        assert '_IMPORTED_' in result['rule']['id']

    def test_import_with_overwrite(self, marketplace_service, test_rule, test_user):
        """Test importing with overwrite updates existing rule"""
        rule_data = marketplace_service.export_rule(test_rule.id, test_user.id)
        rule_data['description'] = 'Updated description'

        result = marketplace_service.import_rule(rule_data, test_user.id, overwrite=True)

        assert result['success'] is True
        assert result['action'] == 'updated'
        assert result['rule']['description'] == 'Updated description'


class TestGetMarketplaceRules:
    """Test marketplace rule browsing"""

    def test_get_all_public_rules(self, marketplace_service, public_rule):
        """Test getting all public rules"""
        result = marketplace_service.get_marketplace_rules()

        assert 'rules' in result
        assert len(result['rules']) >= 1
        assert all(r['visibility'] == 'public' for r in result['rules'])
        assert result['total'] >= 1

    def test_filter_by_category(self, marketplace_service, db_manager, test_user):
        """Test filtering rules by category"""
        # Create public rules with different categories
        with db_manager.get_session() as db:
            for category in ['security', 'performance', 'style']:
                rule = CustomRule(
                    id=f"{category}_rule_{uuid.uuid4().hex[:8]}",
                    user_id=test_user.id,
                    name=f"{category.title()} Rule",
                    description=f"A {category} rule",
                    category=category,
                    severity="warning",
                    languages="python",
                    pattern_type="regex",
                    pattern_data={"pattern": "test"},
                    message="Test",
                    visibility="public",
                    enabled=True
                )
                db.add(rule)
            db.commit()

        result = marketplace_service.get_marketplace_rules(category='security')

        assert all(r['category'] == 'security' for r in result['rules'])

    def test_filter_by_language(self, marketplace_service, public_rule):
        """Test filtering rules by language"""
        result = marketplace_service.get_marketplace_rules(language='python')

        # languages is a list in the dict representation
        assert all('python' in [lang.lower() for lang in r['languages']] for r in result['rules'])

    def test_search_rules(self, marketplace_service, public_rule):
        """Test searching rules"""
        # Search for "security" which is in the public_rule's name and tags
        result = marketplace_service.get_marketplace_rules(search='security')

        # Should find at least the public_rule fixture
        assert len(result['rules']) >= 1
        # Verify the search is working by checking results contain the search term
        assert any('security' in r['name'].lower() or
                  'security' in r['description'].lower() or
                  'security' in ','.join(r['tags']).lower()
                  for r in result['rules'])

    def test_sort_by_popular(self, marketplace_service, db_manager, test_user):
        """Test sorting by popularity"""
        # Create rules with different download counts
        with db_manager.get_session() as db:
            for i in range(3):
                rule = CustomRule(
                    id=f"popular_rule_{i}_{uuid.uuid4().hex[:8]}",
                    user_id=test_user.id,
                    name=f"Popular Rule {i}",
                    description="A rule",
                    category="security",
                    severity="warning",
                    languages="python",
                    pattern_type="regex",
                    pattern_data={"pattern": "test"},
                    message="Test",
                    visibility="public",
                    download_count=i * 10,
                    enabled=True
                )
                db.add(rule)
            db.commit()

        result = marketplace_service.get_marketplace_rules(sort_by='popular')

        # Should be sorted by download_count descending
        if len(result['rules']) >= 2:
            assert result['rules'][0]['download_count'] >= result['rules'][1]['download_count']

    def test_pagination(self, marketplace_service, db_manager, test_user):
        """Test pagination"""
        # Create many rules
        with db_manager.get_session() as db:
            for i in range(15):
                rule = CustomRule(
                    id=f"page_rule_{i}_{uuid.uuid4().hex[:8]}",
                    user_id=test_user.id,
                    name=f"Page Rule {i}",
                    description="A rule",
                    category="security",
                    severity="warning",
                    languages="python",
                    pattern_type="regex",
                    pattern_data={"pattern": "test"},
                    message="Test",
                    visibility="public",
                    enabled=True
                )
                db.add(rule)
            db.commit()

        # Get first page
        result1 = marketplace_service.get_marketplace_rules(limit=10, offset=0)
        assert len(result1['rules']) == 10
        assert result1['has_more'] is True

        # Get second page
        result2 = marketplace_service.get_marketplace_rules(limit=10, offset=10)
        assert len(result2['rules']) >= 5


class TestForkRule:
    """Test rule forking"""

    def test_fork_public_rule(self, marketplace_service, public_rule, test_user2):
        """Test forking a public rule"""
        result = marketplace_service.fork_rule(public_rule.id, test_user2.id)

        assert result['success'] is True
        assert result['rule']['name'].endswith('(Fork)')
        assert result['rule']['user_id'] == test_user2.id
        assert result['rule']['forked_from'] == public_rule.id
        assert result['rule']['visibility'] == 'private'
        assert '_FORK_' in result['rule']['id']

    def test_fork_private_rule_fails(self, marketplace_service, test_rule, test_user2):
        """Test forking a private rule fails"""
        result = marketplace_service.fork_rule(test_rule.id, test_user2.id)

        assert result['success'] is False
        assert 'not found' in result['error'].lower() or 'not public' in result['error'].lower()

    def test_fork_same_rule_twice_fails(self, marketplace_service, public_rule, test_user2):
        """Test forking the same rule twice fails"""
        # First fork
        result1 = marketplace_service.fork_rule(public_rule.id, test_user2.id)
        assert result1['success'] is True

        # Second fork
        result2 = marketplace_service.fork_rule(public_rule.id, test_user2.id)
        assert result2['success'] is False
        assert 'already forked' in result2['error'].lower()

    def test_fork_increments_counts(self, marketplace_service, db_manager, public_rule, test_user2):
        """Test forking increments fork and download counts"""
        # Get initial counts
        with db_manager.get_session() as db:
            original = db.query(CustomRule).filter(CustomRule.id == public_rule.id).first()
            initial_fork_count = original.fork_count
            initial_download_count = original.download_count

        # Fork the rule
        marketplace_service.fork_rule(public_rule.id, test_user2.id)

        # Check counts increased
        with db_manager.get_session() as db:
            original = db.query(CustomRule).filter(CustomRule.id == public_rule.id).first()
            assert original.fork_count == initial_fork_count + 1
            assert original.download_count == initial_download_count + 1


class TestRateRule:
    """Test rule rating"""

    def test_rate_rule_success(self, marketplace_service, public_rule, test_user2):
        """Test rating a public rule"""
        result = marketplace_service.rate_rule(
            public_rule.id,
            test_user2.id,
            rating=5,
            review="Excellent rule!"
        )

        assert result['success'] is True
        assert result['action'] == 'created'
        assert result['rating']['rating'] == 5
        assert result['rating']['review'] == "Excellent rule!"

    def test_rate_private_rule_fails(self, marketplace_service, test_rule, test_user2):
        """Test rating a private rule fails"""
        result = marketplace_service.rate_rule(test_rule.id, test_user2.id, rating=5)

        assert result['success'] is False
        assert 'not found' in result['error'].lower() or 'not public' in result['error'].lower()

    def test_invalid_rating_value(self, marketplace_service, public_rule, test_user2):
        """Test invalid rating value"""
        result = marketplace_service.rate_rule(public_rule.id, test_user2.id, rating=6)

        assert result['success'] is False
        assert 'between 1 and 5' in result['error'].lower()

    def test_update_existing_rating(self, marketplace_service, public_rule, test_user2):
        """Test updating an existing rating"""
        # Create initial rating
        result1 = marketplace_service.rate_rule(public_rule.id, test_user2.id, rating=3)
        assert result1['action'] == 'created'

        # Update rating
        result2 = marketplace_service.rate_rule(
            public_rule.id,
            test_user2.id,
            rating=5,
            review="Much better!"
        )

        assert result2['success'] is True
        assert result2['action'] == 'updated'
        assert result2['rating']['rating'] == 5
        assert result2['rating']['review'] == "Much better!"


class TestGetFeaturedRules:
    """Test getting featured rules"""

    def test_get_featured_rules(self, marketplace_service, public_rule):
        """Test getting featured rules"""
        result = marketplace_service.get_featured_rules(limit=10)

        assert isinstance(result, list)
        assert len(result) >= 1
        assert all(r['is_featured'] is True for r in result)
        assert all(r['visibility'] == 'public' for r in result)

    def test_featured_rules_limit(self, marketplace_service, db_manager, test_user):
        """Test featured rules limit"""
        # Create multiple featured rules
        with db_manager.get_session() as db:
            for i in range(5):
                rule = CustomRule(
                    id=f"featured_{i}_{uuid.uuid4().hex[:8]}",
                    user_id=test_user.id,
                    name=f"Featured Rule {i}",
                    description="A featured rule",
                    category="security",
                    severity="warning",
                    languages="python",
                    pattern_type="regex",
                    pattern_data={"pattern": "test"},
                    message="Test",
                    visibility="public",
                    is_featured=True,
                    enabled=True
                )
                db.add(rule)
            db.commit()

        result = marketplace_service.get_featured_rules(limit=3)
        assert len(result) <= 3


class TestGetRuleRatings:
    """Test getting rule ratings"""

    def test_get_rule_ratings(self, marketplace_service, db_manager, public_rule, test_user2):
        """Test getting ratings for a rule"""
        # Create some ratings
        with db_manager.get_session() as db:
            for i in range(3):
                user = User(
                    id=f"rater_{i}_{uuid.uuid4().hex[:8]}",
                    username=f"rater{i}",
                    email=f"rater{i}@example.com",
                    password_hash="hash",
                    role="user"
                )
                db.add(user)
                db.commit()

                rating = RuleRating(
                    id=uuid.uuid4().hex,
                    rule_id=public_rule.id,
                    user_id=user.id,
                    rating=4 + i % 2,  # 4 or 5
                    review=f"Review {i}"
                )
                db.add(rating)
            db.commit()

        result = marketplace_service.get_rule_ratings(public_rule.id, limit=10)

        assert 'ratings' in result
        assert len(result['ratings']) >= 3
        assert 'avg_rating' in result
        assert result['avg_rating'] >= 4.0
        assert result['total'] >= 3

    def test_ratings_pagination(self, marketplace_service, db_manager, public_rule):
        """Test ratings pagination"""
        # Create many ratings
        with db_manager.get_session() as db:
            for i in range(15):
                user = User(
                    id=f"many_rater_{i}_{uuid.uuid4().hex[:8]}",
                    username=f"many_rater{i}",
                    email=f"many_rater{i}@example.com",
                    password_hash="hash",
                    role="user"
                )
                db.add(user)
                db.commit()

                rating = RuleRating(
                    id=uuid.uuid4().hex,
                    rule_id=public_rule.id,
                    user_id=user.id,
                    rating=5,
                    review=f"Review {i}"
                )
                db.add(rating)
            db.commit()

        # Get first page
        result1 = marketplace_service.get_rule_ratings(public_rule.id, limit=10, offset=0)
        assert len(result1['ratings']) == 10
        assert result1['has_more'] is True

        # Get second page
        result2 = marketplace_service.get_rule_ratings(public_rule.id, limit=10, offset=10)
        assert len(result2['ratings']) >= 5


class TestPublishUnpublish:
    """Test rule publishing and unpublishing"""

    def test_publish_rule(self, marketplace_service, test_rule, test_user):
        """Test publishing a private rule"""
        result = marketplace_service.publish_rule(
            test_rule.id,
            test_user.id,
            tags=['security', 'python', 'best-practice']
        )

        assert result['success'] is True
        assert result['rule']['visibility'] == 'public'
        assert 'security' in result['rule']['tags']

    def test_unpublish_rule(self, marketplace_service, public_rule, test_user):
        """Test unpublishing a public rule"""
        result = marketplace_service.unpublish_rule(public_rule.id, test_user.id)

        assert result['success'] is True
        assert result['rule']['visibility'] == 'private'

    def test_publish_wrong_user(self, marketplace_service, test_rule, test_user2):
        """Test publishing rule owned by different user"""
        result = marketplace_service.publish_rule(test_rule.id, test_user2.id)

        assert result['success'] is False
        assert 'not found' in result['error'].lower()

    def test_unpublish_wrong_user(self, marketplace_service, public_rule, test_user2):
        """Test unpublishing rule owned by different user"""
        result = marketplace_service.unpublish_rule(public_rule.id, test_user2.id)

        assert result['success'] is False
        assert 'not found' in result['error'].lower()
