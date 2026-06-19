"""Tests for Logging API Endpoints"""
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


def test_get_logs_endpoint():
    """Test getting logs via API"""
    from server import app
    from src.services.logging_service import logging_service

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    # Create some test logs
    logging_service.info("Test log 1")
    logging_service.error("Test error 1")

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)
        response = client.get("/api/logs")

        assert response.status_code == 200
        data = response.json()
        assert 'logs' in data
        assert 'count' in data


def test_get_logs_with_level_filter():
    """Test getting logs filtered by level"""
    from server import app
    from src.services.logging_service import logging_service

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    logging_service.info("Info log")
    logging_service.error("Error log")

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)
        response = client.get("/api/logs?level=ERROR")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data['logs'], list)


def test_get_logs_with_correlation_id_filter():
    """Test getting logs filtered by correlation ID"""
    from server import app
    from src.services.logging_service import logging_service

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with logging_service.correlation_context("test-corr-123"):
        logging_service.info("Correlated log")

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)
        response = client.get("/api/logs?correlation_id=test-corr-123")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data['logs'], list)


def test_get_error_logs():
    """Test getting error logs endpoint"""
    from server import app
    from src.services.logging_service import logging_service

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    logging_service.error("Test error")

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)
        response = client.get("/api/logs/errors")

        assert response.status_code == 200
        data = response.json()
        assert 'errors' in data
        assert 'count' in data


def test_get_logging_statistics():
    """Test getting logging statistics"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)
        response = client.get("/api/logs/statistics")

        assert response.status_code == 200
        data = response.json()
        assert 'total_logs' in data
        assert 'total_errors' in data
        assert 'level_counts' in data


def test_export_logs_json():
    """Test exporting logs in JSON format"""
    from server import app
    from src.services.logging_service import logging_service

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    logging_service.info("Export test")

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)
        response = client.get("/api/logs/export?format=json")

        assert response.status_code == 200


def test_export_logs_csv():
    """Test exporting logs in CSV format"""
    from server import app
    from src.services.logging_service import logging_service

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    logging_service.info("CSV export test")

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)
        response = client.get("/api/logs/export?format=csv")

        assert response.status_code == 200
        assert 'text/csv' in response.headers['content-type']


def test_invalid_log_level():
    """Test that invalid log level returns 400"""
    from server import app

    mock_user = Mock()
    mock_user.id = 'test-user'
    mock_user.role = UserRole.USER

    with patch('server.get_current_user', return_value=mock_user):
        client = TestClient(app)
        response = client.get("/api/logs?level=INVALID")

        assert response.status_code == 400


def test_logging_endpoints_require_auth():
    """Test that logging endpoints require authentication"""
    from server import app

    client = TestClient(app)

    endpoints = [
        "/api/logs",
        "/api/logs/errors",
        "/api/logs/statistics",
        "/api/logs/export"
    ]

    for endpoint in endpoints:
        response = client.get(endpoint)
        assert response.status_code == 401, f"{endpoint} should require auth"
