"""Tests for Settings & Configuration Component"""
import pytest
import sys
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

# Mock celery before imports
mock_celery = Mock()
mock_celery.celery_app = Mock()
mock_celery.celery_app.task = lambda *args, **kwargs: lambda f: f
sys.modules['celery'] = Mock()
sys.modules['celery.result'] = Mock()
sys.modules['celery_app'] = mock_celery

from src.core.database import UserRole


def test_settings_javascript_exists():
    """Test that settings JavaScript file exists"""
    import os
    js_path = os.path.join('static', 'js', 'settings.js')
    assert os.path.exists(js_path), "Settings JavaScript should exist"


def test_settings_css_exists():
    """Test that settings CSS file exists"""
    import os
    css_path = os.path.join('static', 'css', 'settings.css')
    assert os.path.exists(css_path), "Settings CSS should exist"


def test_settings_template_exists():
    """Test that settings template exists"""
    import os
    template_path = os.path.join('templates', 'settings.html')
    assert os.path.exists(template_path), "Settings template should exist"


def test_settings_javascript_has_required_structure():
    """Test that JavaScript has SettingsManager class with required methods"""
    import os
    js_path = os.path.join('static', 'js', 'settings.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for main class
    assert 'class SettingsManager' in content, "Should define SettingsManager class"

    # Check for required methods
    required_methods = [
        'constructor',
        'init',
        'loadSettings',
        'renderSettings',
        'attachEventListeners',
        'updateSetting',
        'saveSettings',
        'resetToDefaults',
        'exportSettings',
        'importSettings',
        'applyTheme'
    ]

    for method in required_methods:
        assert method in content, f"Should have {method} method"


def test_settings_supports_all_configuration_sections():
    """Test that JavaScript supports all required configuration sections"""
    import os
    js_path = os.path.join('static', 'js', 'settings.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for configuration sections
    config_sections = [
        'rules',        # Analysis rules
        'thresholds',   # Threshold values
        'ai',           # AI configuration
        'ui',           # UI preferences
        'github'        # GitHub integration
    ]

    for section in config_sections:
        assert section in content, f"Should support {section} configuration"

    # Check for specific rule categories
    assert 'security' in content, "Should support security rules"
    assert 'smell' in content, "Should support code smell rules"
    assert 'complexity' in content, "Should support complexity rules"


def test_settings_supports_rule_toggles():
    """Test that settings support enabling/disabling analysis rules"""
    import os
    js_path = os.path.join('static', 'js', 'settings.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for specific security rules
    security_rules = [
        'sqlInjection',
        'commandInjection',
        'hardcodedSecrets',
        'pathTraversal',
        'unsafeDeserialization',
        'weakCrypto'
    ]

    for rule in security_rules:
        assert rule in content, f"Should support {rule} toggle"

    # Check for code smell rules
    smell_rules = [
        'longMethods',
        'longParameters',
        'godClasses',
        'deepNesting',
        'magicNumbers',
        'duplicateCode'
    ]

    for rule in smell_rules:
        assert rule in content, f"Should support {rule} toggle"


def test_settings_supports_threshold_adjustment():
    """Test that settings support threshold adjustments"""
    import os
    js_path = os.path.join('static', 'js', 'settings.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for threshold settings
    thresholds = [
        'complexityWarn',
        'complexityError',
        'methodLengthWarn',
        'methodLengthError',
        'parameterCountWarn',
        'parameterCountError'
    ]

    for threshold in thresholds:
        assert threshold in content, f"Should support {threshold} adjustment"

    # Check for slider rendering
    assert 'threshold-slider' in content or 'renderThreshold' in content, "Should have threshold slider UI"


def test_settings_supports_ai_provider_selection():
    """Test that settings support AI provider selection"""
    import os
    js_path = os.path.join('static', 'js', 'settings.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for AI providers
    providers = ['ollama', 'anthropic', 'openai']

    for provider in providers:
        assert provider in content, f"Should support {provider} AI provider"

    # Check for AI configuration options
    ai_options = [
        'enableExplanations',
        'enableRefactoring',
        'autoApplyFixes'
    ]

    for option in ai_options:
        assert option in content, f"Should support {option} AI option"


def test_settings_css_has_required_styles():
    """Test that CSS has required style rules"""
    import os
    css_path = os.path.join('static', 'css', 'settings.css')

    with open(css_path, 'r') as f:
        content = f.read()

    # Check for required CSS classes
    required_classes = [
        '.settings-container',
        '.settings-section',
        '.setting-group',
        '.setting-toggle',
        '.toggle-switch',
        '.toggle-slider',
        '.threshold-slider',
        '.threshold-grid',
        '.settings-actions'
    ]

    for css_class in required_classes:
        assert css_class in content, f"CSS should define {css_class}"

    # Check for theme support
    assert 'data-theme' in content or 'prefers-color-scheme' in content, "CSS should support themes"

    # Check for responsive design
    assert '@media' in content, "CSS should include responsive design rules"


def test_settings_has_import_export_functionality():
    """Test that settings support import/export"""
    import os
    js_path = os.path.join('static', 'js', 'settings.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for export functionality
    assert 'exportSettings' in content, "Should have exportSettings method"
    assert 'Blob' in content or 'download' in content, "Should create downloadable file"

    # Check for import functionality
    assert 'importSettings' in content, "Should have importSettings method"
    assert 'FileReader' in content or 'readAsText' in content, "Should read uploaded file"

    # Check for JSON handling
    assert 'JSON.stringify' in content, "Should serialize settings to JSON"
    assert 'JSON.parse' in content, "Should deserialize settings from JSON"


def test_settings_has_state_persistence():
    """Test that settings support localStorage persistence"""
    import os
    js_path = os.path.join('static', 'js', 'settings.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for localStorage operations
    assert 'localStorage' in content, "Should use localStorage"
    assert 'localStorage.setItem' in content, "Should save to localStorage"
    assert 'localStorage.getItem' in content, "Should load from localStorage"

    # Check for storage key
    assert 'storageKey' in content, "Should use configurable storage key"


def test_settings_page_route_exists():
    """Test that settings page route exists"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user_optional', return_value=mock_user):
        client = TestClient(app)
        response = client.get("/settings", allow_redirects=False)

        # Should return 200 (page loads) or redirect to login
        assert response.status_code in [200, 302, 307], "Settings page route should exist"


def test_settings_api_endpoints_exist():
    """Test that settings API endpoints exist"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)

        # Test GET endpoint
        response = client.get("/api/settings")
        assert response.status_code == 200, "GET /api/settings should exist"

        # Test POST endpoint
        response = client.post("/api/settings", json={
            "rules": {"security": {"sqlInjection": True}},
            "thresholds": {"complexityWarn": 10}
        })
        assert response.status_code == 200, "POST /api/settings should exist"
        data = response.json()
        assert "success" in data, "Should return success message"


def test_settings_has_theme_switching():
    """Test that settings support theme switching"""
    import os
    js_path = os.path.join('static', 'js', 'settings.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for theme application
    assert 'applyTheme' in content, "Should have applyTheme method"
    assert 'data-theme' in content, "Should set data-theme attribute"

    # Check for theme options
    themes = ['light', 'dark', 'auto']
    for theme in themes:
        assert theme in content, f"Should support {theme} theme"
