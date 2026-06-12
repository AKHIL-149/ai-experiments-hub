"""
Tests for database models and DatabaseManager
"""

import pytest
from datetime import datetime, timedelta
from src.core.database import (
    DatabaseManager,
    User,
    UserSession,
    Repository,
    PullRequest,
    CodeFile,
    AnalysisJob,
    Issue,
    Refactoring,
    Review,
    ReviewComment,
    UserRole,
    RepositoryStatus,
    PRStatus,
    JobStatus,
    IssueCategory,
    IssueSeverity,
    RefactoringStatus
)


@pytest.fixture
def db_manager():
    """Create in-memory database for testing"""
    db = DatabaseManager('sqlite:///:memory:')
    db.init_db()
    yield db
    db.close()


@pytest.fixture
def db_session(db_manager):
    """Get database session"""
    with db_manager.get_session() as session:
        yield session


def test_database_initialization(db_manager):
    """Test database manager initialization"""
    assert db_manager.engine is not None
    assert db_manager.SessionLocal is not None


def test_create_user(db_session):
    """Test user creation"""
    user = User(
        username='testuser',
        email='test@example.com',
        password_hash='hashed_password',
        role=UserRole.USER,
        is_active=True
    )
    db_session.add(user)
    db_session.commit()

    assert user.id is not None
    assert user.username == 'testuser'
    assert user.email == 'test@example.com'
    assert user.role == UserRole.USER
    assert user.is_active is True
    assert user.created_at is not None


def test_user_to_dict(db_session):
    """Test user serialization"""
    user = User(
        username='testuser',
        email='test@example.com',
        password_hash='hashed_password',
        role=UserRole.ADMIN
    )
    db_session.add(user)
    db_session.commit()

    user_dict = user.to_dict()
    assert user_dict['username'] == 'testuser'
    assert user_dict['email'] == 'test@example.com'
    assert user_dict['role'] == 'admin'
    assert 'password_hash' not in user_dict


def test_create_session(db_session):
    """Test session creation"""
    user = User(
        username='testuser',
        email='test@example.com',
        password_hash='hashed_password'
    )
    db_session.add(user)
    db_session.commit()

    session = UserSession(
        id='test_token_123',
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(days=30),
        ip_address='127.0.0.1'
    )
    db_session.add(session)
    db_session.commit()

    assert session.id == 'test_token_123'
    assert session.user_id == user.id
    assert session.ip_address == '127.0.0.1'


def test_user_session_relationship(db_session):
    """Test user-session relationship"""
    user = User(
        username='testuser',
        email='test@example.com',
        password_hash='hashed_password'
    )
    db_session.add(user)
    db_session.commit()

    session1 = UserSession(
        id='token1',
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(days=30)
    )
    session2 = UserSession(
        id='token2',
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(days=30)
    )
    db_session.add_all([session1, session2])
    db_session.commit()

    assert len(user.sessions) == 2


def test_create_repository(db_session):
    """Test repository creation"""
    user = User(
        username='testuser',
        email='test@example.com',
        password_hash='hashed_password'
    )
    db_session.add(user)
    db_session.commit()

    repo = Repository(
        user_id=user.id,
        name='test-repo',
        github_url='https://github.com/user/test-repo',
        default_branch='main',
        status=RepositoryStatus.PENDING
    )
    db_session.add(repo)
    db_session.commit()

    assert repo.id is not None
    assert repo.name == 'test-repo'
    assert repo.status == RepositoryStatus.PENDING


def test_create_pull_request(db_session):
    """Test pull request creation"""
    user = User(username='testuser', email='test@example.com', password_hash='hash')
    db_session.add(user)
    db_session.commit()

    repo = Repository(
        user_id=user.id,
        name='test-repo',
        github_url='https://github.com/user/test-repo'
    )
    db_session.add(repo)
    db_session.commit()

    pr = PullRequest(
        repository_id=repo.id,
        pr_number=42,
        title='Fix bug',
        author='developer',
        status=PRStatus.OPEN,
        source_branch='feature',
        target_branch='main'
    )
    db_session.add(pr)
    db_session.commit()

    assert pr.id is not None
    assert pr.pr_number == 42
    assert pr.status == PRStatus.OPEN


def test_create_code_file(db_session):
    """Test code file creation"""
    user = User(username='testuser', email='test@example.com', password_hash='hash')
    repo = Repository(user_id=user.id, name='repo', github_url='url')
    pr = PullRequest(
        repository_id=repo.id,
        pr_number=1,
        title='Test',
        source_branch='feat',
        target_branch='main'
    )
    db_session.add_all([user, repo, pr])
    db_session.commit()

    code_file = CodeFile(
        pull_request_id=pr.id,
        file_path='src/main.py',
        language='python',
        lines_of_code=150
    )
    db_session.add(code_file)
    db_session.commit()

    assert code_file.id is not None
    assert code_file.file_path == 'src/main.py'
    assert code_file.language == 'python'


def test_create_analysis_job(db_session):
    """Test analysis job creation"""
    user = User(username='testuser', email='test@example.com', password_hash='hash')
    repo = Repository(user_id=user.id, name='repo', github_url='url')
    pr = PullRequest(
        repository_id=repo.id,
        pr_number=1,
        title='Test',
        source_branch='feat',
        target_branch='main'
    )
    db_session.add_all([user, repo, pr])
    db_session.commit()

    job = AnalysisJob(
        pull_request_id=pr.id,
        job_type='full_analysis',
        status=JobStatus.QUEUED
    )
    db_session.add(job)
    db_session.commit()

    assert job.id is not None
    assert job.status == JobStatus.QUEUED


def test_create_issue(db_session):
    """Test issue creation"""
    user = User(username='testuser', email='test@example.com', password_hash='hash')
    repo = Repository(user_id=user.id, name='repo', github_url='url')
    pr = PullRequest(
        repository_id=repo.id,
        pr_number=1,
        title='Test',
        source_branch='feat',
        target_branch='main'
    )
    code_file = CodeFile(
        pull_request_id=pr.id,
        file_path='test.py',
        language='python'
    )
    db_session.add_all([user, repo, pr, code_file])
    db_session.commit()

    issue = Issue(
        code_file_id=code_file.id,
        category=IssueCategory.SECURITY,
        severity=IssueSeverity.CRITICAL,
        rule_id='SEC001',
        title='SQL Injection',
        description='Potential SQL injection vulnerability',
        line_number=42,
        confidence=0.95
    )
    db_session.add(issue)
    db_session.commit()

    assert issue.id is not None
    assert issue.category == IssueCategory.SECURITY
    assert issue.severity == IssueSeverity.CRITICAL


def test_create_refactoring(db_session):
    """Test refactoring suggestion creation"""
    user = User(username='testuser', email='test@example.com', password_hash='hash')
    repo = Repository(user_id=user.id, name='repo', github_url='url')
    pr = PullRequest(
        repository_id=repo.id,
        pr_number=1,
        title='Test',
        source_branch='feat',
        target_branch='main'
    )
    code_file = CodeFile(pull_request_id=pr.id, file_path='test.py', language='python')
    issue = Issue(
        code_file_id=code_file.id,
        category=IssueCategory.SMELL,
        severity=IssueSeverity.WARNING,
        rule_id='SMELL001',
        title='Long method',
        description='Method too long'
    )
    db_session.add_all([user, repo, pr, code_file, issue])
    db_session.commit()

    refactoring = Refactoring(
        issue_id=issue.id,
        code_file_id=code_file.id,
        refactoring_type='extract_method',
        original_code='def long_method(): ...',
        refactored_code='def shorter_method(): ...',
        explanation='Extract into smaller functions',
        confidence=0.85,
        status=RefactoringStatus.SUGGESTED
    )
    db_session.add(refactoring)
    db_session.commit()

    assert refactoring.id is not None
    assert refactoring.refactoring_type == 'extract_method'
    assert refactoring.status == RefactoringStatus.SUGGESTED


def test_create_review(db_session):
    """Test review creation"""
    user = User(username='testuser', email='test@example.com', password_hash='hash')
    repo = Repository(user_id=user.id, name='repo', github_url='url')
    pr = PullRequest(
        repository_id=repo.id,
        pr_number=1,
        title='Test',
        source_branch='feat',
        target_branch='main'
    )
    db_session.add_all([user, repo, pr])
    db_session.commit()

    review = Review(
        pull_request_id=pr.id,
        reviewer_id=user.id,
        overall_score=85,
        issues_count=5,
        summary='Good code with minor issues',
        approved=True
    )
    db_session.add(review)
    db_session.commit()

    assert review.id is not None
    assert review.overall_score == 85
    assert review.approved is True


def test_create_review_comment(db_session):
    """Test review comment creation"""
    user = User(username='testuser', email='test@example.com', password_hash='hash')
    repo = Repository(user_id=user.id, name='repo', github_url='url')
    pr = PullRequest(
        repository_id=repo.id,
        pr_number=1,
        title='Test',
        source_branch='feat',
        target_branch='main'
    )
    review = Review(
        pull_request_id=pr.id,
        reviewer_id=user.id,
        overall_score=80
    )
    db_session.add_all([user, repo, pr, review])
    db_session.commit()

    comment = ReviewComment(
        review_id=review.id,
        file_path='src/main.py',
        line_number=10,
        comment_text='Consider using list comprehension here',
        severity=IssueSeverity.INFO
    )
    db_session.add(comment)
    db_session.commit()

    assert comment.id is not None
    assert comment.line_number == 10
    assert comment.severity == IssueSeverity.INFO


def test_cascade_delete(db_session):
    """Test cascade deletion of related records"""
    user = User(username='testuser', email='test@example.com', password_hash='hash')
    repo = Repository(user_id=user.id, name='repo', github_url='url')
    pr = PullRequest(
        repository_id=repo.id,
        pr_number=1,
        title='Test',
        source_branch='feat',
        target_branch='main'
    )
    code_file = CodeFile(pull_request_id=pr.id, file_path='test.py', language='python')
    db_session.add_all([user, repo, pr, code_file])
    db_session.commit()

    # Delete PR should cascade to code files
    db_session.delete(pr)
    db_session.commit()

    assert db_session.query(CodeFile).filter_by(pull_request_id=pr.id).count() == 0
