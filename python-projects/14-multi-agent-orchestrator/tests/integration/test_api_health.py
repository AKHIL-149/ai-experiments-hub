"""
Integration tests for Health API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from server import app


@pytest.fixture(scope="module")
def client():
    """Create test client"""
    with TestClient(app) as c:
        yield c


class TestHealthEndpoints:
    """Test health check endpoints"""

    def test_health_check(self, client):
        """Test basic health check endpoint"""
        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["service"] == "multi-agent-orchestrator"

    def test_root_endpoint(self, client):
        """Test root endpoint"""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Multi-Agent Task Orchestrator"
        assert data["version"] == "0.1.0"
        assert data["status"] == "running"
        assert data["docs"] == "/docs"

    def test_docs_available(self, client):
        """Test that API documentation is available"""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_redoc_available(self, client):
        """Test that ReDoc documentation is available"""
        response = client.get("/redoc")
        assert response.status_code == 200
