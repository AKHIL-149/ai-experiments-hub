"""Tests for Advanced Filters Component"""
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


def test_advanced_filters_javascript_exists():
    """Test that advanced filters JavaScript file exists"""
    import os
    js_path = os.path.join('static', 'js', 'advanced-filters.js')
    assert os.path.exists(js_path), "Advanced filters JavaScript should exist"


def test_advanced_filters_css_exists():
    """Test that advanced filters CSS file exists"""
    import os
    css_path = os.path.join('static', 'css', 'advanced-filters.css')
    assert os.path.exists(css_path), "Advanced filters CSS should exist"


def test_advanced_filters_demo_template_exists():
    """Test that advanced filters demo template exists"""
    import os
    template_path = os.path.join('templates', 'advanced_filters_demo.html')
    assert os.path.exists(template_path), "Advanced filters demo template should exist"


def test_advanced_filters_javascript_structure():
    """Test that JavaScript has required AdvancedFilters class structure"""
    import os
    js_path = os.path.join('static', 'js', 'advanced-filters.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for main class
    assert 'class AdvancedFilters' in content, "Should define AdvancedFilters class"

    # Check for required methods
    required_methods = [
        'constructor',
        'init',
        'render',
        'toggleFilter',
        'applyQuickFilter',
        'clearFilters',
        'saveCurrentAsPreset',
        'applyPreset',
        'deletePreset',
        'loadPresets',
        'savePresets',
        'persistState',
        'loadPersistedState',
        'getActiveFilters'
    ]

    for method in required_methods:
        assert method in content, f"Should have {method} method"

    # Check for filter types
    assert 'severity' in content, "Should support severity filtering"
    assert 'category' in content, "Should support category filtering"
    assert 'search' in content, "Should support search filtering"
    assert 'dateFrom' in content or 'date-from' in content, "Should support date range filtering"
    assert 'filePath' in content or 'file-path' in content, "Should support file path filtering"


def test_advanced_filters_css_has_required_styles():
    """Test that CSS has required style rules"""
    import os
    css_path = os.path.join('static', 'css', 'advanced-filters.css')

    with open(css_path, 'r') as f:
        content = f.read()

    # Check for required CSS classes
    required_classes = [
        '.advanced-filters',
        '.filter-section',
        '.search-bar',
        '.search-input',
        '.filter-chip',
        '.filter-chips',
        '.filter-group',
        '.date-range-inputs',
        '.date-input',
        '.quick-filters',
        '.quick-filter-btn',
        '.presets-list',
        '.preset-btn',
        '.filter-actions'
    ]

    for css_class in required_classes:
        assert css_class in content, f"CSS should define {css_class}"

    # Check for severity badges
    severity_classes = [
        '.severity-critical',
        '.severity-error',
        '.severity-warning',
        '.severity-info'
    ]

    for css_class in severity_classes:
        assert css_class in content, f"CSS should define {css_class}"

    # Check for responsive design
    assert '@media' in content, "CSS should include responsive design rules"

    # Check for dark theme
    assert 'prefers-color-scheme: dark' in content, "CSS should support dark theme"


def test_advanced_filters_supports_multi_criteria():
    """Test that JavaScript supports multiple filter criteria"""
    import os
    js_path = os.path.join('static', 'js', 'advanced-filters.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for multi-criteria support
    filter_criteria = [
        'severity',    # Severity filtering
        'category',    # Category filtering
        'search',      # Full-text search
        'dateFrom',    # Date range start
        'dateTo',      # Date range end
        'filePath'     # File path filtering
    ]

    for criterion in filter_criteria:
        assert criterion in content, f"Should support {criterion} filtering"

    # Check for array handling (multi-select)
    assert 'Array.isArray' in content, "Should handle array filters"


def test_advanced_filters_supports_presets():
    """Test that JavaScript supports filter presets"""
    import os
    js_path = os.path.join('static', 'js', 'advanced-filters.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for preset functionality
    preset_features = [
        'saveCurrentAsPreset',
        'applyPreset',
        'deletePreset',
        'loadPresets',
        'savePresets'
    ]

    for feature in preset_features:
        assert feature in content, f"Should have {feature} functionality"

    # Check for localStorage usage
    assert 'localStorage' in content, "Should use localStorage for presets"


def test_advanced_filters_has_quick_filters():
    """Test that JavaScript includes quick filter presets"""
    import os
    js_path = os.path.join('static', 'js', 'advanced-filters.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for quick filter presets
    quick_filters = [
        'critical-only',
        'recent',
        'security',
        'high-complexity'
    ]

    for quick_filter in quick_filters:
        assert quick_filter in content, f"Should have {quick_filter} quick filter"


def test_advanced_filters_demo_route_exists():
    """Test that advanced filters demo route exists"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user_optional', return_value=mock_user):
        client = TestClient(app)
        response = client.get("/demo/advanced-filters", allow_redirects=False)

        # Should return 200 (page loads) or redirect to login
        assert response.status_code in [200, 302, 307], "Advanced filters demo route should exist"


def test_advanced_filters_has_state_persistence():
    """Test that JavaScript supports state persistence"""
    import os
    js_path = os.path.join('static', 'js', 'advanced-filters.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for state persistence features
    persistence_features = [
        'persistState',
        'loadPersistedState',
        'localStorage.setItem',
        'localStorage.getItem'
    ]

    for feature in persistence_features:
        assert feature in content, f"Should have {feature} for state persistence"

    # Check for storage key configuration
    assert 'storageKey' in content, "Should support configurable storage key"


def test_advanced_filters_has_callback_system():
    """Test that JavaScript supports callback for filter changes"""
    import os
    js_path = os.path.join('static', 'js', 'advanced-filters.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for callback system
    assert 'onFilterChange' in content, "Should have onFilterChange callback"
    assert 'triggerFilterChange' in content, "Should trigger filter change events"

    # Check for debouncing (performance optimization)
    assert 'debounce' in content, "Should have debounce functionality for inputs"
