"""Tests for Progress Tracker Component"""
import pytest
import sys
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient

# Mock celery before imports
mock_celery = Mock()
mock_celery.celery_app = Mock()
mock_celery.celery_app.task = lambda *args, **kwargs: lambda f: f
sys.modules['celery'] = Mock()
sys.modules['celery.result'] = Mock()
sys.modules['celery_app'] = mock_celery

from src.core.database import UserRole


def test_progress_tracker_javascript_exists():
    """Test that progress tracker JavaScript file exists"""
    import os
    js_path = os.path.join('static', 'js', 'progress-tracker.js')
    assert os.path.exists(js_path), "Progress tracker JavaScript should exist"


def test_progress_tracker_css_exists():
    """Test that progress tracker CSS file exists"""
    import os
    css_path = os.path.join('static', 'css', 'progress-tracker.css')
    assert os.path.exists(css_path), "Progress tracker CSS should exist"


def test_progress_tracker_has_required_classes():
    """Test that JavaScript defines required classes"""
    import os
    js_path = os.path.join('static', 'js', 'progress-tracker.js')

    with open(js_path, 'r') as f:
        content = f.read()

    # Check for main classes
    assert 'class ProgressTracker' in content, "Should define ProgressTracker class"
    assert 'class ToastNotification' in content, "Should define ToastNotification class"

    # Check for key methods
    required_methods = [
        'start',
        'stop',
        'startSSE',
        'startPolling',
        'handleProgressUpdate',
        'handleComplete',
        'handleError',
        'updateProgressBar'
    ]

    for method in required_methods:
        assert method in content, f"Should have {method} method"


def test_progress_tracker_supports_sse_and_polling():
    """Test that both SSE and polling are supported"""
    import os
    js_path = os.path.join('static', 'js', 'progress-tracker.js')

    with open(js_path, 'r') as f:
        content = f.read()

    assert 'EventSource' in content, "Should support Server-Sent Events"
    assert 'setInterval' in content, "Should support polling"
    assert 'fetch' in content, "Should use fetch for polling"


def test_toast_notification_styles():
    """Test that CSS has toast notification styles"""
    import os
    css_path = os.path.join('static', 'css', 'progress-tracker.css')

    with open(css_path, 'r') as f:
        content = f.read()

    toast_classes = [
        '.toast-container',
        '.toast',
        '.toast-info',
        '.toast-success',
        '.toast-error',
        '.toast-warning'
    ]

    for css_class in toast_classes:
        assert css_class in content, f"CSS should define {css_class}"


def test_progress_bar_styles():
    """Test that CSS has progress bar styles"""
    import os
    css_path = os.path.join('static', 'css', 'progress-tracker.css')

    with open(css_path, 'r') as f:
        content = f.read()

    progress_classes = [
        '.progress-container',
        '.progress-bar',
        '.progress-bar-wrapper',
        '.progress-message',
        '.progress-percentage'
    ]

    for css_class in progress_classes:
        assert css_class in content, f"CSS should define {css_class}"

    # Check for animations
    assert 'animation' in content or '@keyframes' in content, "Should have animations"


def test_task_status_endpoint_exists():
    """Test that task status polling endpoint exists"""
    from server import app
    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        with patch('server.AsyncResult') as mock_result:
            # Mock a pending task
            mock_task = Mock()
            mock_task.state = 'PENDING'
            mock_task.info = None
            mock_result.return_value = mock_task

            client = TestClient(app)
            response = client.get("/api/tasks/test-task-id/status")

            assert response.status_code == 200
            data = response.json()
            assert "task_id" in data
            assert "status" in data
            assert "progress" in data


def test_task_progress_stream_endpoint_exists():
    """Test that SSE progress endpoint exists"""
    from server import app
    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        with patch('server.AsyncResult') as mock_result:
            # Mock a completed task to end stream quickly
            mock_task = Mock()
            mock_task.state = 'SUCCESS'
            mock_task.result = {"test": "data"}
            mock_task.info = None
            mock_result.return_value = mock_task

            client = TestClient(app)
            response = client.get("/api/tasks/test-task-id/progress")

            # SSE endpoint should return 200
            assert response.status_code == 200
            # Should have SSE content type
            assert "text/event-stream" in response.headers.get("content-type", "")


def test_global_notification_function():
    """Test that global showNotification function is defined"""
    import os
    js_path = os.path.join('static', 'js', 'progress-tracker.js')

    with open(js_path, 'r') as f:
        content = f.read()

    assert 'window.showNotification' in content, "Should define global showNotification"
    assert 'toast.show' in content, "Should have toast.show method"
