"""
Tests for Rule Builder Endpoints
"""

import pytest
from fastapi.testclient import TestClient


class TestRuleBuilderUI:
    """Test rule builder UI page"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from server import app
        return TestClient(app)

    @pytest.fixture
    def user_session(self, client):
        """Create user session"""
        response = client.post('/api/auth/register', json={
            'username': 'rule_builder_user',
            'email': 'builder@test.com',
            'password': 'password123'
        })

        response = client.post('/api/auth/login', json={
            'username': 'rule_builder_user',
            'password': 'password123'
        })

        return response.cookies.get('session_token')

    def test_rule_builder_page_requires_auth(self, client):
        """Test rule builder page redirects when not authenticated"""
        response = client.get('/rules/builder', follow_redirects=False)
        assert response.status_code == 307  # Redirect
        assert '/login' in response.headers['location']

    def test_rule_builder_page_renders(self, client, user_session):
        """Test rule builder page renders for authenticated user"""
        response = client.get(
            '/rules/builder',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'Custom Rule Builder' in response.content
        assert b'rule-builder.js' in response.content
        assert b'rule-builder.css' in response.content


class TestCustomRuleAPI:
    """Test custom rule API endpoints"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from server import app
        return TestClient(app)

    @pytest.fixture
    def user_session(self, client):
        """Create user session"""
        response = client.post('/api/auth/register', json={
            'username': 'api_test_user',
            'email': 'api@test.com',
            'password': 'password123'
        })

        response = client.post('/api/auth/login', json={
            'username': 'api_test_user',
            'password': 'password123'
        })

        return response.cookies.get('session_token')

    @pytest.fixture
    def sample_rule(self):
        """Sample custom rule"""
        return {
            'id': 'TEST001',
            'name': 'Test Rule',
            'description': 'Test rule for testing',
            'category': 'security',
            'severity': 'warning',
            'languages': ['python', 'javascript'],
            'pattern_type': 'regex',
            'message': 'Test pattern matched',
            'fix_suggestion': 'Fix the issue',
            'auto_fixable': False,
            'regex_pattern': {
                'pattern': r'test',
                'flags': {'case_insensitive': False}
            }
        }

    def test_save_custom_rule(self, client, user_session, sample_rule):
        """Test saving a custom rule"""
        response = client.post(
            '/api/rules/custom',
            json=sample_rule,
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True

    def test_get_custom_rules(self, client, user_session, sample_rule):
        """Test getting custom rules"""
        # First save a rule
        client.post(
            '/api/rules/custom',
            json=sample_rule,
            cookies={'session_token': user_session}
        )

        # Then get all rules
        response = client.get(
            '/api/rules/custom',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert len(data['rules']) > 0
        assert data['rules'][0]['id'] == 'TEST001'

    def test_get_specific_rule(self, client, user_session, sample_rule):
        """Test getting a specific rule"""
        # Save rule first
        client.post(
            '/api/rules/custom',
            json=sample_rule,
            cookies={'session_token': user_session}
        )

        # Get specific rule
        response = client.get(
            '/api/rules/custom/TEST001',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert data['rule']['name'] == 'Test Rule'

    def test_get_nonexistent_rule(self, client, user_session):
        """Test getting a rule that doesn't exist"""
        response = client.get(
            '/api/rules/custom/NONEXISTENT',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 404

    def test_update_existing_rule(self, client, user_session, sample_rule):
        """Test updating an existing rule"""
        # Save initial rule
        client.post(
            '/api/rules/custom',
            json=sample_rule,
            cookies={'session_token': user_session}
        )

        # Update rule
        updated_rule = sample_rule.copy()
        updated_rule['name'] = 'Updated Test Rule'
        updated_rule['severity'] = 'critical'

        response = client.post(
            '/api/rules/custom',
            json=updated_rule,
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200

        # Verify update
        response = client.get(
            '/api/rules/custom/TEST001',
            cookies={'session_token': user_session}
        )

        data = response.json()
        assert data['rule']['name'] == 'Updated Test Rule'
        assert data['rule']['severity'] == 'critical'

    def test_delete_rule(self, client, user_session, sample_rule):
        """Test deleting a rule"""
        # Save rule first
        client.post(
            '/api/rules/custom',
            json=sample_rule,
            cookies={'session_token': user_session}
        )

        # Delete rule
        response = client.delete(
            '/api/rules/custom/TEST001',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True

        # Verify deletion
        response = client.get(
            '/api/rules/custom/TEST001',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 404

    def test_delete_nonexistent_rule(self, client, user_session):
        """Test deleting a rule that doesn't exist"""
        response = client.delete(
            '/api/rules/custom/NONEXISTENT',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 404

    def test_test_rule(self, client, user_session):
        """Test testing a rule against code"""
        rule = {
            'id': 'TEST002',
            'name': 'Password Detection',
            'category': 'security',
            'severity': 'critical',
            'pattern_type': 'regex',
            'regex_pattern': {
                'pattern': r'password\s*=',
                'flags': {'case_insensitive': True}
            },
            'message': 'Password found'
        }

        code = """
password = "test123"
user = "admin"
"""

        response = client.post(
            '/api/rules/test',
            json={
                'rule': rule,
                'code': code,
                'language': 'python'
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert len(data['matches']) > 0
        assert data['matches'][0]['severity'] == 'critical'

    def test_test_rule_no_matches(self, client, user_session):
        """Test testing a rule with no matches"""
        rule = {
            'id': 'TEST003',
            'name': 'No Match Rule',
            'category': 'custom',
            'severity': 'info',
            'pattern_type': 'regex',
            'regex_pattern': {
                'pattern': r'NONEXISTENT',
                'flags': {}
            },
            'message': 'Pattern found'
        }

        code = "print('hello')"

        response = client.post(
            '/api/rules/test',
            json={
                'rule': rule,
                'code': code,
                'language': 'python'
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert len(data['matches']) == 0

    def test_test_ast_rule(self, client, user_session):
        """Test testing an AST rule"""
        rule = {
            'id': 'TEST004',
            'name': 'Function Call Detection',
            'category': 'custom',
            'severity': 'warning',
            'pattern_type': 'ast',
            'ast_patterns': [
                {
                    'nodeType': 'Call',
                    'attributes': {}
                }
            ],
            'message': 'Function call found'
        }

        code = """
print("hello")
len([1, 2, 3])
"""

        response = client.post(
            '/api/rules/test',
            json={
                'rule': rule,
                'code': code,
                'language': 'python'
            },
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
        assert len(data['matches']) >= 2  # print and len calls

    def test_save_rule_requires_auth(self, client, sample_rule):
        """Test that saving a rule requires authentication"""
        response = client.post(
            '/api/rules/custom',
            json=sample_rule
        )

        assert response.status_code in [401, 403, 307]  # Unauthorized or redirect

    def test_get_rules_requires_auth(self, client):
        """Test that getting rules requires authentication"""
        response = client.get('/api/rules/custom')

        assert response.status_code in [401, 403, 307]

    def test_save_ast_rule(self, client, user_session):
        """Test saving an AST rule"""
        rule = {
            'id': 'AST001',
            'name': 'AST Test Rule',
            'description': 'Test AST rule',
            'category': 'custom',
            'severity': 'info',
            'languages': ['python'],
            'pattern_type': 'ast',
            'message': 'AST pattern matched',
            'ast_patterns': [
                {
                    'nodeType': 'FunctionDef',
                    'attributes': {}
                }
            ]
        }

        response = client.post(
            '/api/rules/custom',
            json=rule,
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True

    def test_save_combined_rule(self, client, user_session):
        """Test saving a rule with both AST and regex patterns"""
        rule = {
            'id': 'COMBINED001',
            'name': 'Combined Rule',
            'description': 'Test combined rule',
            'category': 'security',
            'severity': 'warning',
            'languages': ['python', 'javascript'],
            'pattern_type': 'both',
            'message': 'Pattern matched',
            'ast_patterns': [
                {
                    'nodeType': 'Call',
                    'attributes': {}
                }
            ],
            'regex_pattern': {
                'pattern': r'execute',
                'flags': {'case_insensitive': True}
            }
        }

        response = client.post(
            '/api/rules/custom',
            json=rule,
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] == True
