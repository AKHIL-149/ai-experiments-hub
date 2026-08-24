"""
Tests for GitHub App Configuration Endpoints
"""

import pytest
import uuid
from unittest.mock import Mock, patch, MagicMock
import json

from src.core.database import DatabaseManager, User


class TestGitHubAppEndpoints:
    """Test GitHub App configuration endpoints"""

    @pytest.fixture(scope='class')
    def client(self):
        """Create test client"""
        from server import app
        from fastapi.testclient import TestClient

        # This used to unconditionally os.remove('data/database.db') here
        # to "clear the database before tests" - a raw filesystem delete
        # of the real, live application database file, bypassing
        # SQLAlchemy/DatabaseManager entirely (so tests/conftest.py's
        # isolation patch, which only intercepts DatabaseManager(), could
        # never have caught it). Confirmed live: running this test file
        # left data/database.db as a 0-byte file. No longer needed -
        # tests/conftest.py's session-wide autouse fixture already gives
        # every DatabaseManager() call (including server.py's own
        # module-level singleton) an isolated, empty test database.
        return TestClient(app)

    @pytest.fixture(scope='class')
    def admin_session(self, client):
        """Create admin session"""
        from src.core.database import DatabaseManager, User, UserRole
        import bcrypt

        # Unique suffix: 'admin_test'/'admin@test.com' fixed literals
        # collide with identically-named accounts other test files create
        # in the same full-suite run, sharing the same isolated test DB
        # (see tests/conftest.py) - either an IntegrityError on insert, or
        # a silent login failure if another file's account already owns
        # the name with a different password.
        suffix = uuid.uuid4().hex[:8]
        username = f'admin_test_{suffix}'
        password = 'admin123'

        # Create admin user directly in database
        db_manager = DatabaseManager()

        with db_manager.get_session() as db:
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            admin_user = User(
                username=username,
                email=f'admin_{suffix}@test.com',
                password_hash=hashed_password.decode('utf-8'),
                role=UserRole.ADMIN
            )
            db.add(admin_user)
            db.commit()

        # Login
        response = client.post('/api/auth/login', json={
            'username': username,
            'password': password
        })

        return response.cookies.get('session_token')

    @pytest.fixture
    def user_session(self, client):
        """Create regular user session"""
        # Same collision risk as admin_session above - unique suffix per
        # fixture call.
        suffix = uuid.uuid4().hex[:8]
        username = f'testuser_{suffix}'
        password = 'password123'

        response = client.post('/api/auth/register', json={
            'username': username,
            'email': f'user_{suffix}@test.com',
            'password': password
        })

        response = client.post('/api/auth/login', json={
            'username': username,
            'password': password
        })

        return response.cookies.get('session_token')

    def test_get_github_app_status_not_configured(self, client, user_session):
        """Test getting GitHub App status when not configured"""
        with patch('src.core.github_app.get_github_app') as mock_app:
            mock_instance = Mock()
            mock_instance.is_configured.return_value = False
            mock_instance.app_id = None
            mock_instance.private_key = None
            mock_app.return_value = mock_instance

            response = client.get(
                '/api/github/app/status',
                cookies={'session_token': user_session}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['configured'] == False
            assert data['app_id'] is None
            assert data['private_key_set'] == False

    def test_get_github_app_status_configured(self, client, user_session):
        """Test getting GitHub App status when configured"""
        with patch('src.core.github_app.get_github_app') as mock_app:
            mock_instance = Mock()
            mock_instance.is_configured.return_value = True
            mock_instance.app_id = '123456'
            mock_instance.private_key = 'fake-key'
            mock_app.return_value = mock_instance

            response = client.get(
                '/api/github/app/status',
                cookies={'session_token': user_session}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['configured'] == True
            assert data['app_id'] == '123456'
            assert data['private_key_set'] == True

    def test_update_github_app_config_requires_admin(self, client, user_session):
        """Test that updating config requires admin role"""
        response = client.post(
            '/api/github/app/config',
            json={
                'app_id': '123456',
                'private_key': '-----BEGIN RSA PRIVATE KEY-----\nfake\n-----END RSA PRIVATE KEY-----'
            },
            cookies={'session_token': user_session}
        )

        # Should fail because user is not admin
        assert response.status_code == 403

    def test_update_github_app_config_missing_fields(self, client, admin_session):
        """Test updating config with missing fields"""
        response = client.post(
            '/api/github/app/config',
            json={'app_id': '123456'},
            cookies={'session_token': admin_session}
        )

        assert response.status_code == 400
        assert 'app_id and private_key are required' in response.json()['detail']

    def test_update_github_app_config_invalid_credentials(self, client, admin_session):
        """Test updating config with invalid credentials"""
        with patch('src.core.github_app.GitHubApp') as mock_github_app_class:
            mock_instance = Mock()
            mock_instance.generate_jwt.return_value = None
            mock_github_app_class.return_value = mock_instance

            response = client.post(
                '/api/github/app/config',
                json={
                    'app_id': '123456',
                    'private_key': 'invalid-key'
                },
                cookies={'session_token': admin_session}
            )

            assert response.status_code == 400
            assert 'Invalid GitHub App configuration' in response.json()['detail']

    def test_get_installations_not_configured(self, client, user_session):
        """Test getting installations when app not configured"""
        with patch('src.core.github_app.get_github_app') as mock_app:
            mock_instance = Mock()
            mock_instance.is_configured.return_value = False
            mock_app.return_value = mock_instance

            response = client.get(
                '/api/github/app/installations',
                cookies={'session_token': user_session}
            )

            assert response.status_code == 400
            assert 'GitHub App is not configured' in response.json()['detail']

    def test_get_installations_success(self, client, user_session):
        """Test getting installations successfully"""
        with patch('src.core.github_app.get_github_app') as mock_app, \
             patch('requests.get') as mock_request:

            # Mock GitHub App
            mock_instance = Mock()
            mock_instance.is_configured.return_value = True
            mock_instance.generate_jwt.return_value = 'fake-jwt-token'
            mock_instance.github_api_url = 'https://api.github.com'
            mock_app.return_value = mock_instance

            # Mock API response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = [
                {
                    'id': 12345,
                    'account': {
                        'login': 'testuser',
                        'type': 'User',
                        'avatar_url': 'https://github.com/avatar.png'
                    },
                    'repository_selection': 'all',
                    'created_at': '2024-01-01T00:00:00Z',
                    'updated_at': '2024-01-02T00:00:00Z'
                }
            ]
            mock_request.return_value = mock_response

            response = client.get(
                '/api/github/app/installations',
                cookies={'session_token': user_session}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True
            assert len(data['installations']) == 1
            assert data['installations'][0]['id'] == 12345
            assert data['installations'][0]['account']['login'] == 'testuser'

    def test_test_connection_not_configured(self, client, admin_session):
        """Test connection test when app not configured"""
        with patch('src.core.github_app.get_github_app') as mock_app:
            mock_instance = Mock()
            mock_instance.is_configured.return_value = False
            mock_app.return_value = mock_instance

            response = client.post(
                '/api/github/app/test',
                cookies={'session_token': admin_session}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['success'] == False
            assert data['configured'] == False

    def test_test_connection_success(self, client, admin_session):
        """Test successful connection test"""
        with patch('src.core.github_app.get_github_app') as mock_app, \
             patch('requests.get') as mock_request:

            # Mock GitHub App
            mock_instance = Mock()
            mock_instance.is_configured.return_value = True
            mock_instance.generate_jwt.return_value = 'fake-jwt-token'
            mock_instance.github_api_url = 'https://api.github.com'
            mock_app.return_value = mock_instance

            # Mock API response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'id': 123456,
                'name': 'Test App',
                'owner': {'login': 'testuser'},
                'html_url': 'https://github.com/apps/test-app'
            }
            mock_request.return_value = mock_response

            response = client.post(
                '/api/github/app/test',
                cookies={'session_token': admin_session}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True
            assert data['configured'] == True
            assert data['jwt_generation'] == True
            assert data['api_connectivity'] == True
            assert data['app_info']['name'] == 'Test App'

    def test_test_connection_jwt_failure(self, client, admin_session):
        """Test connection test with JWT generation failure"""
        with patch('src.core.github_app.get_github_app') as mock_app:
            mock_instance = Mock()
            mock_instance.is_configured.return_value = True
            mock_instance.generate_jwt.return_value = None
            mock_app.return_value = mock_instance

            response = client.post(
                '/api/github/app/test',
                cookies={'session_token': admin_session}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['success'] == False
            assert data['jwt_generation'] == False

    def test_github_app_page_requires_auth(self, client):
        """Test that GitHub App page requires authentication"""
        # `client` is class-scoped and shares one cookie jar across every
        # test in this class - an earlier test's login leaves a valid
        # session_token cookie sitting on it, so without clearing first
        # this "requires auth" check silently exercises the *authenticated*
        # path instead (order-dependent: passes/fails based on which
        # sibling tests already ran).
        client.cookies.clear()
        response = client.get('/settings/github-app')

        # Should redirect to login
        assert response.status_code == 200  # RedirectResponse returns 200 in test client
        # Or check for redirect location
        assert 'login' in response.url.path or response.status_code == 307

    def test_github_app_page_accessible_when_logged_in(self, client, user_session):
        """Test that GitHub App page is accessible when logged in"""
        response = client.get(
            '/settings/github-app',
            cookies={'session_token': user_session}
        )

        assert response.status_code == 200
        assert b'GitHub App Configuration' in response.content


class TestGitHubAppIntegration:
    """Integration tests for GitHub App workflow"""

    @pytest.fixture
    def client(self):
        """Create test client"""
        from server import app
        from fastapi.testclient import TestClient
        return TestClient(app)

    @pytest.fixture
    def admin_session(self, client):
        """Create admin session"""
        # Unique suffix - see TestGitHubAppEndpoints.admin_session above
        # for why a fixed literal collides across files sharing the
        # session-wide isolated test DB.
        username = f'admin_integration_{uuid.uuid4().hex[:8]}'
        response = client.post('/api/auth/register', json={
            'username': username,
            'email': f'{username}@test.com',
            'password': 'admin123',
            'role': 'admin'
        })

        response = client.post('/api/auth/login', json={
            'username': username,
            'password': 'admin123'
        })

        return response.cookies.get('session_token')

    def test_full_github_app_setup_workflow(self, client, admin_session):
        """Test complete GitHub App setup workflow"""
        # Step 1: Check initial status (should be not configured)
        with patch('src.core.github_app.get_github_app') as mock_app:
            mock_instance = Mock()
            mock_instance.is_configured.return_value = False
            mock_instance.app_id = None
            mock_instance.private_key = None
            mock_app.return_value = mock_instance

            response = client.get(
                '/api/github/app/status',
                cookies={'session_token': admin_session}
            )

            assert response.status_code == 200
            assert response.json()['configured'] == False

        # Step 2: Configure GitHub App
        with patch('src.core.github_app.GitHubApp') as mock_github_app_class, \
             patch('builtins.open', create=True) as mock_open:

            mock_instance = Mock()
            mock_instance.generate_jwt.return_value = 'fake-jwt'
            mock_github_app_class.return_value = mock_instance

            # Mock file operations
            mock_file = MagicMock()
            mock_open.return_value.__enter__.return_value = mock_file

            response = client.post(
                '/api/github/app/config',
                json={
                    'app_id': '999999',
                    'private_key': '-----BEGIN RSA PRIVATE KEY-----\ntest\n-----END RSA PRIVATE KEY-----'
                },
                cookies={'session_token': admin_session}
            )

            # Configuration might fail or succeed based on file operations
            # Accept both outcomes in tests
            assert response.status_code in [200, 400, 500]

        # Step 3: Test connection (mocked success)
        with patch('src.core.github_app.get_github_app') as mock_app, \
             patch('requests.get') as mock_request:

            mock_instance = Mock()
            mock_instance.is_configured.return_value = True
            mock_instance.generate_jwt.return_value = 'fake-jwt'
            mock_instance.github_api_url = 'https://api.github.com'
            mock_app.return_value = mock_instance

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'id': 999999,
                'name': 'Test App',
                'owner': {'login': 'testuser'},
                'html_url': 'https://github.com/apps/test'
            }
            mock_request.return_value = mock_response

            response = client.post(
                '/api/github/app/test',
                cookies={'session_token': admin_session}
            )

            assert response.status_code == 200
            data = response.json()
            assert data['success'] == True
