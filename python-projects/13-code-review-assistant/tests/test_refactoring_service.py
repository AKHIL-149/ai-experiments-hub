"""Tests for Refactoring Service"""
import pytest
from unittest.mock import Mock
from src.core.database import (
    DatabaseManager,
    User,
    Repository,
    PullRequest,
    CodeFile,
    Issue,
    Refactoring,
    RefactoringStatus,
    RepositoryStatus,
    PRStatus
)
from src.services.refactoring_service import RefactoringService


@pytest.fixture
def db_manager():
    """Create test database manager"""
    return DatabaseManager('sqlite:///:memory:')


@pytest.fixture
def test_user(db_manager):
    """Create test user"""
    with db_manager.get_session() as db:
        user = User(
            username='testuser',
            email='test@test.com',
            password_hash='hashed'
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


@pytest.fixture
def test_repo(db_manager, test_user):
    """Create test repository"""
    with db_manager.get_session() as db:
        repo = Repository(
            user_id=test_user.id,
            name='test-repo',
            github_url='https://github.com/user/repo',
            status=RepositoryStatus.READY
        )
        db.add(repo)
        db.commit()
        db.refresh(repo)
        return repo


@pytest.fixture
def test_pr(db_manager, test_repo):
    """Create test pull request"""
    with db_manager.get_session() as db:
        pr = PullRequest(
            repository_id=test_repo.id,
            pr_number=1,
            title='Test PR',
            author='author',
            source_branch='feature',
            target_branch='main',
            status=PRStatus.OPEN
        )
        db.add(pr)
        db.commit()
        db.refresh(pr)
        return pr


@pytest.fixture
def test_code_file(db_manager, test_pr):
    """Create test code file"""
    with db_manager.get_session() as db:
        code_file = CodeFile(
            pull_request_id=test_pr.id,
            file_path='app.py',
            file_hash='abc123',
            language='python',
            lines_of_code=100
        )
        db.add(code_file)
        db.commit()
        db.refresh(code_file)
        return code_file


@pytest.fixture
def test_issue(db_manager, test_code_file):
    """Create test issue"""
    with db_manager.get_session() as db:
        issue = Issue(
            code_file_id=test_code_file.id,
            category='complexity',
            severity='warning',
            rule_id='complexity_high',
            title='High complexity',
            description='Function is too complex',
            line_number=10
        )
        db.add(issue)
        db.commit()
        db.refresh(issue)
        return issue


def test_create_refactoring(db_manager, test_issue, test_code_file):
    """Test creating a refactoring suggestion"""
    with db_manager.get_session() as db:
        service = RefactoringService(db)

        original_code = "def foo():\n    pass"
        refactored_code = "def foo():\n    return None"

        success, refactoring, error = service.create_refactoring(
            issue_id=test_issue.id,
            code_file_id=test_code_file.id,
            refactoring_type='simplify',
            original_code=original_code,
            refactored_code=refactored_code,
            explanation='Simplified function',
            benefits='More explicit',
            confidence=0.8
        )

        assert success is True
        assert error is None
        assert refactoring is not None
        assert refactoring.status == RefactoringStatus.SUGGESTED
        assert refactoring.confidence == 0.8
        assert refactoring.diff is not None


def test_get_refactoring(db_manager, test_issue, test_code_file):
    """Test getting refactoring by ID"""
    with db_manager.get_session() as db:
        service = RefactoringService(db)

        # Create refactoring
        success, refactoring, _ = service.create_refactoring(
            issue_id=test_issue.id,
            code_file_id=test_code_file.id,
            refactoring_type='simplify',
            original_code='old',
            refactored_code='new',
            explanation='test'
        )

        # Get refactoring
        success, retrieved, error = service.get_refactoring(refactoring.id)

        assert success is True
        assert retrieved.id == refactoring.id


def test_get_refactoring_not_found(db_manager):
    """Test getting non-existent refactoring"""
    with db_manager.get_session() as db:
        service = RefactoringService(db)

        success, refactoring, error = service.get_refactoring('nonexistent')

        assert success is False
        assert refactoring is None
        assert 'not found' in error.lower()


def test_get_issue_refactorings(db_manager, test_issue, test_code_file):
    """Test getting all refactorings for an issue"""
    with db_manager.get_session() as db:
        service = RefactoringService(db)

        # Create multiple refactorings
        for i in range(3):
            service.create_refactoring(
                issue_id=test_issue.id,
                code_file_id=test_code_file.id,
                refactoring_type='test',
                original_code=f'code{i}',
                refactored_code=f'refactored{i}',
                explanation='test'
            )

        success, refactorings, error = service.get_issue_refactorings(test_issue.id)

        assert success is True
        assert len(refactorings) == 3


def test_get_file_refactorings(db_manager, test_issue, test_code_file):
    """Test getting all refactorings for a file"""
    with db_manager.get_session() as db:
        service = RefactoringService(db)

        # Create refactorings
        service.create_refactoring(
            issue_id=test_issue.id,
            code_file_id=test_code_file.id,
            refactoring_type='test',
            original_code='old',
            refactored_code='new',
            explanation='test'
        )

        success, refactorings, error = service.get_file_refactorings(test_code_file.id)

        assert success is True
        assert len(refactorings) >= 1


def test_get_file_refactorings_with_status_filter(db_manager, test_issue, test_code_file):
    """Test getting file refactorings filtered by status"""
    with db_manager.get_session() as db:
        service = RefactoringService(db)

        # Create and accept one refactoring
        success, refactoring, _ = service.create_refactoring(
            issue_id=test_issue.id,
            code_file_id=test_code_file.id,
            refactoring_type='test',
            original_code='old',
            refactored_code='new',
            explanation='test'
        )

        service.accept_refactoring(refactoring.id)

        # Query with status filter
        success, accepted_refactorings, _ = service.get_file_refactorings(
            test_code_file.id,
            status=RefactoringStatus.ACCEPTED
        )

        assert success is True
        assert len(accepted_refactorings) >= 1
        assert all(r.status == RefactoringStatus.ACCEPTED for r in accepted_refactorings)


def test_update_refactoring_status(db_manager, test_issue, test_code_file):
    """Test updating refactoring status"""
    with db_manager.get_session() as db:
        service = RefactoringService(db)

        # Create refactoring
        success, refactoring, _ = service.create_refactoring(
            issue_id=test_issue.id,
            code_file_id=test_code_file.id,
            refactoring_type='test',
            original_code='old',
            refactored_code='new',
            explanation='test'
        )

        # Update status
        success, updated, error = service.update_refactoring_status(
            refactoring.id,
            RefactoringStatus.ACCEPTED
        )

        assert success is True
        assert updated.status == RefactoringStatus.ACCEPTED


def test_accept_refactoring(db_manager, test_issue, test_code_file):
    """Test accepting a refactoring"""
    with db_manager.get_session() as db:
        service = RefactoringService(db)

        success, refactoring, _ = service.create_refactoring(
            issue_id=test_issue.id,
            code_file_id=test_code_file.id,
            refactoring_type='test',
            original_code='old',
            refactored_code='new',
            explanation='test'
        )

        success, accepted, error = service.accept_refactoring(refactoring.id)

        assert success is True
        assert accepted.status == RefactoringStatus.ACCEPTED


def test_reject_refactoring(db_manager, test_issue, test_code_file):
    """Test rejecting a refactoring"""
    with db_manager.get_session() as db:
        service = RefactoringService(db)

        success, refactoring, _ = service.create_refactoring(
            issue_id=test_issue.id,
            code_file_id=test_code_file.id,
            refactoring_type='test',
            original_code='old',
            refactored_code='new',
            explanation='test'
        )

        success, rejected, error = service.reject_refactoring(refactoring.id)

        assert success is True
        assert rejected.status == RefactoringStatus.REJECTED


def test_mark_refactoring_applied(db_manager, test_issue, test_code_file):
    """Test marking refactoring as applied"""
    with db_manager.get_session() as db:
        service = RefactoringService(db)

        success, refactoring, _ = service.create_refactoring(
            issue_id=test_issue.id,
            code_file_id=test_code_file.id,
            refactoring_type='test',
            original_code='old',
            refactored_code='new',
            explanation='test'
        )

        success, applied, error = service.mark_refactoring_applied(refactoring.id)

        assert success is True
        assert applied.status == RefactoringStatus.APPLIED


def test_generate_diff():
    """Test diff generation"""
    service = RefactoringService.__new__(RefactoringService)

    original = "line1\nline2\nline3"
    refactored = "line1\nmodified_line2\nline3"

    diff = service._generate_diff(original, refactored)

    assert diff is not None
    assert "line2" in diff
    assert "modified_line2" in diff


def test_get_refactoring_type():
    """Test refactoring type determination"""
    service = RefactoringService.__new__(RefactoringService)

    # Test extract method
    assert service._get_refactoring_type("smell", "Long method") == "extract_method"

    # Test simplify
    assert service._get_refactoring_type("complexity", "Too complex") == "simplify"

    # Test rename
    assert service._get_refactoring_type("style", "Rename variable") == "rename"

    # Test general
    assert service._get_refactoring_type("other", "Some issue") == "general_refactoring"


def test_extract_benefits():
    """Test benefits extraction"""
    service = RefactoringService.__new__(RefactoringService)

    text = """
This refactoring improves code quality.
It has the following benefits:
- Better readability
- Improved maintainability
"""

    benefits = service._extract_benefits(text)

    assert "improve" in benefits.lower() or "benefit" in benefits.lower()


def test_get_stats(db_manager, test_issue, test_code_file):
    """Test getting refactoring statistics"""
    with db_manager.get_session() as db:
        service = RefactoringService(db)

        # Create refactorings with different statuses
        for i in range(5):
            success, refactoring, _ = service.create_refactoring(
                issue_id=test_issue.id,
                code_file_id=test_code_file.id,
                refactoring_type='test',
                original_code=f'old{i}',
                refactored_code=f'new{i}',
                explanation='test'
            )

            # Accept some, reject others
            if i % 2 == 0:
                service.accept_refactoring(refactoring.id)
            else:
                service.reject_refactoring(refactoring.id)

        stats = service.get_stats()

        assert stats["total"] == 5
        assert stats["accepted"] >= 2
        assert stats["rejected"] >= 2
        assert "acceptance_rate" in stats
        assert "application_rate" in stats


def test_generate_refactoring_from_issue_without_ai(db_manager, test_issue, test_code_file):
    """Test generating refactoring without AI service"""
    with db_manager.get_session() as db:
        service = RefactoringService(db)  # No AI service

        success, refactoring, error = service.generate_refactoring_from_issue(
            issue_id=test_issue.id,
            code_file_id=test_code_file.id,
            code_snippet='def foo(): pass'
        )

        assert success is False
        assert "AI service not configured" in error


def test_generate_refactoring_from_issue_with_ai(db_manager, test_issue, test_code_file):
    """Test generating refactoring with AI service"""
    with db_manager.get_session() as db:
        # Mock AI service
        mock_ai = Mock()
        mock_ai.suggest_refactoring.return_value = {
            "refactored_code": "def foo():\n    return None",
            "explanation": "More explicit",
            "refactoring_suggestion": "Improves clarity. Better readability.",
            "confidence_score": 0.85
        }

        service = RefactoringService(db, ai_service=mock_ai)

        success, refactoring, error = service.generate_refactoring_from_issue(
            issue_id=test_issue.id,
            code_file_id=test_code_file.id,
            code_snippet='def foo(): pass'
        )

        assert success is True
        assert refactoring is not None
        assert refactoring.confidence == 0.85
