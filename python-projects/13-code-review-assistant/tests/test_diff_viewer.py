"""Tests for Diff Viewer Component"""
import pytest
import sys
from unittest.mock import Mock
from fastapi.testclient import TestClient

# Mock celery before imports
mock_celery = Mock()
mock_celery.celery_app = Mock()
mock_celery.celery_app.task = lambda *args, **kwargs: lambda f: f
sys.modules['celery'] = Mock()
sys.modules['celery.result'] = Mock()
sys.modules['celery_app'] = mock_celery


def test_diff_viewer_javascript_file_exists():
    """Test that the diff viewer JavaScript file exists"""
    import os
    js_path = os.path.join('static', 'js', 'diff-viewer.js')
    assert os.path.exists(js_path), "Diff viewer JavaScript file should exist"


def test_diff_viewer_css_file_exists():
    """Test that the diff viewer CSS file exists"""
    import os
    css_path = os.path.join('static', 'css', 'diff-viewer.css')
    assert os.path.exists(css_path), "Diff viewer CSS file should exist"


def test_diff_viewer_demo_template_exists():
    """Test that the diff viewer demo template exists"""
    import os
    template_path = os.path.join('templates', 'diff_viewer_demo.html')
    assert os.path.exists(template_path), "Diff viewer demo template should exist"


def test_diff_viewer_javascript_structure():
    """Test that the JavaScript file has the required structure"""
    import os
    js_path = os.path.join('static', 'js', 'diff-viewer.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for class definition
    assert 'class DiffViewer' in content, "Should define DiffViewer class"

    # Check for required methods
    required_methods = [
        'constructor',
        'init',
        'loadDiff',
        'render',
        'renderUnified',
        'renderSplit',
        'switchMode',
        'parseUnifiedDiff',
        'parseSplitDiff'
    ]

    for method in required_methods:
        assert method in content, f"Should have {method} method"

    # Check for comment functionality
    assert 'addComment' in content, "Should support adding comments"
    assert 'showCommentInput' in content, "Should have comment input functionality"


def test_diff_viewer_css_has_required_styles():
    """Test that the CSS file has required style rules"""
    import os
    css_path = os.path.join('static', 'css', 'diff-viewer.css')

    with open(css_path, 'r') as f:
        content = f.read()

    # Check for required CSS classes
    required_classes = [
        '.diff-viewer-container',
        '.diff-viewer-header',
        '.diff-viewer-tabs',
        '.diff-tab',
        '.diff-unified',
        '.diff-split',
        '.diff-line',
        '.diff-line-added',
        '.diff-line-removed',
        '.diff-line-context',
        '.line-number',
        '.line-content',
        '.comment-btn',
        '.diff-comment-form'
    ]

    for css_class in required_classes:
        assert css_class in content, f"CSS should define {css_class}"

    # Check for responsive design
    assert '@media' in content, "CSS should include responsive design rules"

    # Check for theme support
    assert 'data-theme' in content or 'theme' in content.lower(), "CSS should support themes"


def test_diff_viewer_demo_page_accessible():
    """Test that the diff viewer demo page is accessible"""
    from server import app
    client = TestClient(app)

    # Note: This may require authentication, we're just checking the route exists
    response = client.get("/demo/diff-viewer", allow_redirects=False)

    # Either it loads (200) or redirects to login (302/307), but shouldn't 404
    assert response.status_code != 404, "Diff viewer demo route should exist (may require adding to server.py)"
