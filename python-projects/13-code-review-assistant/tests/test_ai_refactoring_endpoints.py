"""
Tests for AI Refactoring API Endpoints
Tests multi-step refactoring, automated fixes, technical debt, and AI features
"""

import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient


class TestAIRefactoringEndpoints:
    """Test suite for AI refactoring API endpoints"""

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

        # Create test data
        code_file = CodeFile(
            pr_id='pr_123',
            file_path='app.py',
            file_hash='hash123',
            language='python',
            lines_of_code=1000
        )
        db.add(code_file)

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
        assert data['total_files'] == 1
        assert data['total_loc'] == 1000
        assert data['total_issues'] == 2
        assert 'severity_counts' in data
        assert 'debt_ratio' in data
        assert 'estimated_hours' in data
        assert 'estimated_cost' in data
        assert 'recommendations' in data

    def test_technical_debt_empty(self, client, auth_headers):
        """Test technical debt with no data"""
        response = client.get(
            '/api/technical-debt',
            headers=auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data['total_files'] == 0
        assert data['total_issues'] == 0

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
            assert 'sum()' in data['code']

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
