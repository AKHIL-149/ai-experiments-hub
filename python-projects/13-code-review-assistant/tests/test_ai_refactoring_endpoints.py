"""
Tests for AI Refactoring API Endpoints
Tests multi-step refactoring, automated fixes, technical debt, and AI features
"""

import sys
import uuid
import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

# Mock celery before server.py (and everything it imports) gets loaded -
# see tests/_celery_helpers.py for why the decorator has to preserve a
# working .delay()/.apply_async() rather than being a bare identity
# decorator (that silently breaks any route that calls task.delay(...),
# and since celery_app is cached in sys.modules process-wide, whichever
# test file's mock happens to be active when it's first imported wins
# for the rest of the session - every file that imports server.py needs
# its own copy of this, not just one file in the suite).
from tests._celery_helpers import mock_task_decorator
mock_celery = Mock()
mock_celery.celery_app = Mock()
mock_celery.celery_app.task = mock_task_decorator
sys.modules['celery'] = Mock()
sys.modules['celery.result'] = Mock()
sys.modules['celery_app'] = mock_celery


class TestAIRefactoringEndpoints:
    """Test suite for AI refactoring API endpoints"""

    @pytest.fixture
    def client(self):
        """Real, unauthenticated TestClient.

        Deliberately NOT wired through app.dependency_overrides (the
        pattern used elsewhere in this suite, see tests/_auth_helpers.py)
        because test_all_ai_endpoints_require_auth needs requests made
        with no auth_headers to genuinely 401 - a global dependency
        override would authenticate every request regardless of what
        headers it carries, and that test would never be able to fail.
        """
        from server import app
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self, client):
        """A real session, obtained through the actual register+login
        flow, carried as a raw Cookie header.

        server.py's auth is cookie-based (get_current_user reads a
        session_token cookie), not bearer-token based, but an HTTP
        cookie is just a header under the hood - so
        {'Cookie': 'session_token=...'} works with every test body's
        existing `headers=auth_headers` call as-is, without needing to
        rewrite them to `cookies=auth_headers`. A unique username per
        call avoids the cross-test collisions documented at length in
        tests/conftest.py and tests/test_rule_marketplace.py - this
        fixture is function-scoped, so every test gets its own account.
        """
        suffix = uuid.uuid4().hex[:8]
        username = f'ai_refactor_test_{suffix}'
        password = 'TestPass123!'

        client.post('/api/auth/register', json={
            'username': username,
            'email': f'{username}@test.com',
            'password': password
        })
        response = client.post('/api/auth/login', json={
            'username': username,
            'password': password
        })
        token = response.cookies.get('session_token')
        return {'Cookie': f'session_token={token}'}

    @pytest.fixture
    def db(self):
        """Database session for tests that seed CodeFile/Issue rows
        directly. Deliberately bare DatabaseManager() - tests/conftest.py's
        session-wide patch redirects that to the same isolated test
        database server.py's own module-level db_manager singleton
        reads from; an explicit sqlite:///:memory: here would be
        invisible to the running app the test calls into.
        """
        from src.core.database import DatabaseManager
        db_manager = DatabaseManager()
        with db_manager.get_session() as session:
            yield session

    @pytest.fixture
    def sample_code(self):
        """Sample code for testing"""
        return '''
def vulnerable_function(user_input):
    query = "SELECT * FROM users WHERE id = " + user_input
    return execute_query(query)
'''

    @pytest.fixture
    def sample_issues(self):
        """Sample issues for testing"""
        return [
            {
                'severity': 'critical',
                'category': 'security',
                'title': 'SQL Injection vulnerability',
                'line_number': 3
            }
        ]

    def test_multi_step_refactoring_success(self, client, auth_headers, sample_code, sample_issues):
        """Test successful multi-step refactoring generation"""
        # Mock the AI service
        with patch('src.services.ai_refactoring_service.ai_refactoring_service') as mock_service:
            from src.services.ai_refactoring_service import RefactoringChain

            mock_chain = RefactoringChain(
                steps=[
                    {
                        'step_number': 1,
                        'type': 'security_fix',
                        'description': 'Use parameterized query',
                        'code_after': 'query = "SELECT * FROM users WHERE id = ?"',
                        'issues_addressed': ['SQL Injection vulnerability'],
                        'confidence': 0.95
                    }
                ],
                original_code=sample_code,
                final_code='query = "SELECT * FROM users WHERE id = ?"',
                confidence=0.95,
                explanation='Fixed SQL injection by using parameterized query',
                estimated_time='10 minutes'
            )
            mock_service.generate_multi_step_refactoring.return_value = mock_chain

            # Make request
            response = client.post(
                '/api/refactor/multi-step',
                json={
                    'code': sample_code,
                    'language': 'python',
                    'issues': sample_issues,
                    'max_steps': 3
                },
                headers=auth_headers
            )

            # Assertions
            assert response.status_code == 200
            data = response.json()
            assert data['success'] is True
            assert len(data['steps']) == 1
            assert data['confidence'] == 0.95
            assert 'parameterized' in data['steps'][0]['description']
            assert data['estimated_time'] == '10 minutes'

    def test_multi_step_refactoring_missing_field(self, client, auth_headers):
        """Test multi-step refactoring with missing required field"""
        response = client.post(
            '/api/refactor/multi-step',
            json={
                'code': 'def test(): pass',
                'language': 'python'
                # Missing 'issues' field
            },
            headers=auth_headers
        )

        assert response.status_code == 400
        assert 'Missing required field: issues' in response.json()['detail']

    def test_multi_step_refactoring_error(self, client, auth_headers, sample_code, sample_issues):
        """Test multi-step refactoring with service error"""
        with patch('src.services.ai_refactoring_service.ai_refactoring_service') as mock_service:
            mock_service.generate_multi_step_refactoring.side_effect = Exception("LLM error")

            response = client.post(
                '/api/refactor/multi-step',
                json={
                    'code': sample_code,
                    'language': 'python',
                    'issues': sample_issues
                },
                headers=auth_headers
            )

            assert response.status_code == 500
            assert 'Error generating refactoring' in response.json()['detail']

    def test_auto_fix_success(self, client, auth_headers):
        """Test successful automated fix application"""
        with patch('src.services.ai_refactoring_service.ai_refactoring_service') as mock_service:
            mock_service.apply_automated_fix.return_value = {
                'success': True,
                'refactoring_id': 'ref_123',
                'fixed_code': 'query = "SELECT * FROM users WHERE id = ?"',
                'explanation': 'Use parameterized queries',
                'test_code': 'def test_query(): assert "?" in query',
                'confidence': 0.95
            }

            response = client.post(
                '/api/refactor/auto-fix/issue_123?generate_test=true',
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data['success'] is True
            assert 'fixed_code' in data
            assert 'test_code' in data
            assert data['confidence'] == 0.95

    def test_auto_fix_no_test(self, client, auth_headers):
        """Test automated fix without test generation"""
        with patch('src.services.ai_refactoring_service.ai_refactoring_service') as mock_service:
            mock_service.apply_automated_fix.return_value = {
                'success': True,
                'refactoring_id': 'ref_123',
                'fixed_code': 'def clean(): pass',
                'explanation': 'Simplified method',
                'test_code': None,
                'confidence': 0.85
            }

            response = client.post(
                '/api/refactor/auto-fix/issue_123?generate_test=false',
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data['test_code'] is None

    def test_auto_fix_issue_not_found(self, client, auth_headers):
        """Test automated fix with non-existent issue"""
        with patch('src.services.ai_refactoring_service.ai_refactoring_service') as mock_service:
            mock_service.apply_automated_fix.return_value = {
                'success': False,
                'error': 'Issue not found'
            }

            response = client.post(
                '/api/refactor/auto-fix/nonexistent',
                headers=auth_headers
            )

            assert response.status_code == 404
            assert 'Issue not found' in response.json()['detail']

    def test_technical_debt_estimation(self, client, auth_headers, db):
        """Test technical debt estimation"""
        from src.core.database import CodeFile, Issue, IssueSeverity, IssueCategory

        # /api/technical-debt queries CodeFile/Issue globally (no
        # user/repo filter - see server.py), and this test's `db` session
        # is deliberately the same session-wide isolated database every
        # other test in the suite shares (see the `db` fixture above), so
        # baseline counts aren't reliably 0 by the time this test runs.
        # Measure the delta this test's own data causes instead of
        # asserting an absolute total.
        baseline = client.get('/api/technical-debt', headers=auth_headers).json()

        # Create test data. code_file.id is a SQLAlchemy column default
        # applied at flush/commit, not at construction - reading it
        # beforehand (as the issues below originally did) writes NULL
        # into a NOT NULL foreign key column.
        code_file = CodeFile(
            pull_request_id='pr_123',  # was the nonexistent field 'pr_id'
            file_path='app.py',
            file_hash='hash123',
            language='python',
            lines_of_code=1000
        )
        db.add(code_file)
        db.commit()
        db.refresh(code_file)

        issue1 = Issue(
            code_file_id=code_file.id,
            category=IssueCategory.SECURITY,
            severity=IssueSeverity.CRITICAL,
            rule_id='SEC001',
            title='SQL Injection',
            description='Unsafe SQL query',
            line_number=10,
            code_snippet='query = "SELECT * FROM users"'
        )
        issue2 = Issue(
            code_file_id=code_file.id,
            category=IssueCategory.SMELL,
            severity=IssueSeverity.ERROR,
            rule_id='SMELL001',
            title='Long method',
            description='Method too long',
            line_number=20,
            code_snippet='def long(): pass'
        )
        db.add(issue1)
        db.add(issue2)
        db.commit()

        # Make request
        response = client.get(
            '/api/technical-debt',
            headers=auth_headers
        )

        # Assertions
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['total_files'] == baseline['total_files'] + 1
        assert data['total_loc'] == baseline['total_loc'] + 1000
        assert data['total_issues'] == baseline['total_issues'] + 2
        assert 'severity_counts' in data
        assert 'debt_ratio' in data
        assert 'estimated_hours' in data
        assert 'estimated_cost' in data
        assert 'recommendations' in data

    def test_technical_debt_empty(self, client, auth_headers):
        """Test technical debt endpoint responds correctly with no data
        of its own added (see test_technical_debt_estimation above for
        why this can't assert an absolute zero total)."""
        response = client.get(
            '/api/technical-debt',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data['total_files'] >= 0
        assert data['total_issues'] >= 0

    def test_ai_pair_programming_success(self, client, auth_headers):
        """Test successful AI pair programming interaction"""
        with patch('src.services.ai_refactoring_service.ai_refactoring_service') as mock_service:
            mock_service.ai_pair_programming.return_value = {
                'success': True,
                'code': 'def calculate(nums):\n    return sum(nums)',
                'explanation': 'Use built-in sum() function',
                'warnings': ['Ensure nums is iterable'],
                'alternatives': ['Use reduce()', 'Use loop'],
                'confidence': 0.9
            }

            response = client.post(
                '/api/ai/pair-programming',
                json={
                    'prompt': 'How to sum numbers?',
                    'language': 'python'
                },
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data['success'] is True
            assert 'code' in data
            assert 'explanation' in data
            # Mocked code is `sum(nums)`, not a literal empty-paren call.
            assert 'sum(' in data['code']

    def test_ai_pair_programming_with_context(self, client, auth_headers):
        """Test AI pair programming with context"""
        with patch('src.services.ai_refactoring_service.ai_refactoring_service') as mock_service:
            mock_service.ai_pair_programming.return_value = {
                'success': True,
                'code': 'refactored code',
                'explanation': 'Based on your current file...',
                'warnings': [],
                'alternatives': [],
                'confidence': 0.85
            }

            response = client.post(
                '/api/ai/pair-programming',
                json={
                    'prompt': 'Improve this code',
                    'context': {
                        'current_file': 'app.py',
                        'issues': ['Long method']
                    },
                    'language': 'python'
                },
                headers=auth_headers
            )

            assert response.status_code == 200
            assert response.json()['success'] is True

    def test_ai_pair_programming_missing_prompt(self, client, auth_headers):
        """Test AI pair programming without prompt"""
        response = client.post(
            '/api/ai/pair-programming',
            json={'language': 'python'},
            headers=auth_headers
        )

        assert response.status_code == 400
        assert 'Missing required field: prompt' in response.json()['detail']

    def test_predict_smells_success(self, client, auth_headers):
        """Test successful code smell prediction"""
        with patch('src.services.ai_refactoring_service.ai_refactoring_service') as mock_service:
            mock_service.predict_code_smells.return_value = [
                {
                    'smell_type': 'long_method',
                    'location': 'line 10-50',
                    'description': 'Method is too long',
                    'severity': 'warning',
                    'confidence': 0.9,
                    'refactoring_suggestion': 'Extract methods'
                },
                {
                    'smell_type': 'duplicate_code',
                    'location': 'line 60-80',
                    'description': 'Duplicate code block',
                    'severity': 'info',
                    'confidence': 0.85,
                    'refactoring_suggestion': 'Extract common function'
                }
            ]

            response = client.post(
                '/api/ai/predict-smells',
                json={
                    'code': 'def long_function():\n    pass',
                    'language': 'python'
                },
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data['success'] is True
            assert data['count'] == 2
            assert len(data['code_smells']) == 2
            assert data['code_smells'][0]['smell_type'] == 'long_method'

    def test_predict_smells_no_smells(self, client, auth_headers):
        """Test code smell prediction with clean code"""
        with patch('src.services.ai_refactoring_service.ai_refactoring_service') as mock_service:
            mock_service.predict_code_smells.return_value = []

            response = client.post(
                '/api/ai/predict-smells',
                json={
                    'code': 'def clean(): pass',
                    'language': 'python'
                },
                headers=auth_headers
            )

            assert response.status_code == 200
            data = response.json()
            assert data['count'] == 0
            assert data['code_smells'] == []

    def test_predict_smells_missing_code(self, client, auth_headers):
        """Test code smell prediction without code"""
        response = client.post(
            '/api/ai/predict-smells',
            json={'language': 'python'},
            headers=auth_headers
        )

        assert response.status_code == 400
        assert 'Missing required field: code' in response.json()['detail']

    def test_predict_smells_missing_language(self, client, auth_headers):
        """Test code smell prediction without language"""
        response = client.post(
            '/api/ai/predict-smells',
            json={'code': 'def test(): pass'},
            headers=auth_headers
        )

        assert response.status_code == 400
        assert 'Missing required field: language' in response.json()['detail']

    def test_predict_smells_error(self, client, auth_headers):
        """Test code smell prediction with service error"""
        with patch('src.services.ai_refactoring_service.ai_refactoring_service') as mock_service:
            mock_service.predict_code_smells.side_effect = Exception("LLM timeout")

            response = client.post(
                '/api/ai/predict-smells',
                json={
                    'code': 'def test(): pass',
                    'language': 'python'
                },
                headers=auth_headers
            )

            assert response.status_code == 500
            assert 'Error predicting code smells' in response.json()['detail']

    def test_all_ai_endpoints_require_auth(self, client):
        """Test that all AI endpoints require authentication"""
        endpoints = [
            ('POST', '/api/refactor/multi-step', {'code': 'x', 'language': 'py', 'issues': []}),
            ('POST', '/api/refactor/auto-fix/test', None),
            ('GET', '/api/technical-debt', None),
            ('POST', '/api/ai/pair-programming', {'prompt': 'test'}),
            ('POST', '/api/ai/predict-smells', {'code': 'x', 'language': 'py'})
        ]

        for method, endpoint, data in endpoints:
            if method == 'POST':
                response = client.post(endpoint, json=data)
            else:
                response = client.get(endpoint)

            assert response.status_code == 401, f"{method} {endpoint} should require auth"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
