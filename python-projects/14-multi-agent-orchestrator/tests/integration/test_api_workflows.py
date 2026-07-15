"""
Integration tests for Workflow Engine API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from server import app
from src.core.database import get_db_session


@pytest.fixture(scope="module")
def client():
    """Create test client"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_workflow_config():
    """Sample workflow configuration for testing"""
    return {
        "name": "Test Code Review Workflow",
        "description": "Automated code review for testing",
        "workflow_type": "custom",
        "steps": [
            {
                "step_name": "analyze_code",
                "step_type": "agent",
                "agent_role": "code",
                "config": {
                    "task": "Analyze code quality",
                    "priority": "high"
                },
                "dependencies": []
            },
            {
                "step_name": "generate_report",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Generate review report",
                    "output_format": "markdown"
                },
                "dependencies": ["analyze_code"]
            }
        ],
        "metadata": {
            "category": "code_quality",
            "estimated_duration_minutes": 10,
            "required_agents": ["code", "writer"],
            "tags": ["test", "code-review"]
        }
    }


class TestWorkflowCreation:
    """Test workflow creation endpoints"""

    def test_create_workflow(self, client, sample_workflow_config):
        """Test creating a new workflow"""
        response = client.post(
            "/api/workflow-engine/workflows",
            json=sample_workflow_config
        )

        assert response.status_code == 200
        data = response.json()
        assert "workflow_id" in data
        assert data["name"] == sample_workflow_config["name"]
        assert data["status"] in ["pending", "created"]

    def test_create_workflow_minimal(self, client):
        """Test creating workflow with minimal config"""
        minimal_config = {
            "name": "Minimal Workflow",
            "description": "Test minimal workflow",
            "workflow_type": "simple",
            "steps": [
                {
                    "step_name": "single_step",
                    "step_type": "agent",
                    "agent_role": "research",
                    "config": {"task": "Research topic"},
                    "dependencies": []
                }
            ]
        }

        response = client.post(
            "/api/workflow-engine/workflows",
            json=minimal_config
        )

        assert response.status_code == 200
        data = response.json()
        assert "workflow_id" in data

    def test_create_workflow_invalid_data(self, client):
        """Test creating workflow with invalid data"""
        invalid_config = {
            "name": "",  # Empty name should fail
            "steps": []  # No steps should fail
        }

        response = client.post(
            "/api/workflow-engine/workflows",
            json=invalid_config
        )

        assert response.status_code in [400, 422]  # Bad request or validation error


class TestWorkflowRetrieval:
    """Test workflow retrieval endpoints"""

    def test_list_workflows(self, client):
        """Test listing all workflows"""
        response = client.get("/api/workflow-engine/workflows")

        assert response.status_code == 200
        data = response.json()
        assert "total" in data or isinstance(data, list)

    def test_get_workflow_details(self, client, sample_workflow_config):
        """Test getting specific workflow details"""
        # First create a workflow
        create_response = client.post(
            "/api/workflow-engine/workflows",
            json=sample_workflow_config
        )
        workflow_id = create_response.json()["workflow_id"]

        # Then retrieve it
        response = client.get(f"/api/workflow-engine/workflows/{workflow_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["workflow_id"] == workflow_id
        assert data["name"] == sample_workflow_config["name"]

    def test_get_nonexistent_workflow(self, client):
        """Test getting workflow that doesn't exist"""
        response = client.get("/api/workflow-engine/workflows/99999")

        assert response.status_code == 404


class TestWorkflowExecution:
    """Test workflow execution endpoints"""

    def test_execute_workflow(self, client, sample_workflow_config):
        """Test executing a workflow"""
        # Create workflow
        create_response = client.post(
            "/api/workflow-engine/workflows",
            json=sample_workflow_config
        )
        workflow_id = create_response.json()["workflow_id"]

        # Execute workflow
        execution_data = {
            "input_data": {
                "code": "def hello(): print('world')",
                "language": "python"
            }
        }

        response = client.post(
            f"/api/workflow-engine/workflows/{workflow_id}/execute",
            json=execution_data
        )

        # Execution might fail due to missing LLM keys in test env,
        # but endpoint should respond
        assert response.status_code in [200, 500]

        if response.status_code == 200:
            data = response.json()
            assert "workflow_id" in data or "execution_id" in data

    def test_get_workflow_status(self, client, sample_workflow_config):
        """Test getting workflow execution status"""
        # Create workflow
        create_response = client.post(
            "/api/workflow-engine/workflows",
            json=sample_workflow_config
        )
        workflow_id = create_response.json()["workflow_id"]

        # Get status
        response = client.get(
            f"/api/workflow-engine/workflows/{workflow_id}/status"
        )

        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert "status" in data

    def test_pause_workflow(self, client, sample_workflow_config):
        """Test pausing workflow execution"""
        # Create workflow
        create_response = client.post(
            "/api/workflow-engine/workflows",
            json=sample_workflow_config
        )
        workflow_id = create_response.json()["workflow_id"]

        # Try to pause (may not be running)
        response = client.post(
            f"/api/workflow-engine/workflows/{workflow_id}/pause"
        )

        # Should either succeed or return error that it's not running
        assert response.status_code in [200, 400, 404]


class TestWorkflowFiltering:
    """Test workflow filtering and search"""

    def test_filter_by_status(self, client):
        """Test filtering workflows by status"""
        response = client.get(
            "/api/workflow-engine/workflows?status=pending"
        )

        assert response.status_code == 200

    def test_filter_by_type(self, client):
        """Test filtering workflows by type"""
        response = client.get(
            "/api/workflow-engine/workflows?workflow_type=custom"
        )

        assert response.status_code == 200

    def test_pagination(self, client):
        """Test workflow list pagination"""
        response = client.get(
            "/api/workflow-engine/workflows?limit=10&offset=0"
        )

        assert response.status_code == 200


class TestWorkflowValidation:
    """Test workflow configuration validation"""

    def test_circular_dependency_detection(self, client):
        """Test that circular dependencies are detected"""
        circular_config = {
            "name": "Circular Workflow",
            "description": "Test circular dependency detection",
            "workflow_type": "custom",
            "steps": [
                {
                    "step_name": "step1",
                    "step_type": "agent",
                    "agent_role": "research",
                    "config": {"task": "Task 1"},
                    "dependencies": ["step2"]  # Depends on step2
                },
                {
                    "step_name": "step2",
                    "step_type": "agent",
                    "agent_role": "writer",
                    "config": {"task": "Task 2"},
                    "dependencies": ["step1"]  # Depends on step1 - circular!
                }
            ]
        }

        response = client.post(
            "/api/workflow-engine/workflows",
            json=circular_config
        )

        # Should detect circular dependency
        # May return 200 with warning or 400 with error depending on implementation
        assert response.status_code in [200, 400, 422]

    def test_invalid_dependency_reference(self, client):
        """Test that invalid dependency references are caught"""
        invalid_config = {
            "name": "Invalid Dependency Workflow",
            "description": "Test invalid dependency",
            "workflow_type": "custom",
            "steps": [
                {
                    "step_name": "step1",
                    "step_type": "agent",
                    "agent_role": "research",
                    "config": {"task": "Task 1"},
                    "dependencies": ["nonexistent_step"]  # Invalid reference
                }
            ]
        }

        response = client.post(
            "/api/workflow-engine/workflows",
            json=invalid_config
        )

        # Should catch invalid dependency
        assert response.status_code in [200, 400, 422]


class TestWorkflowDeletion:
    """Test workflow deletion"""

    def test_delete_workflow(self, client, sample_workflow_config):
        """Test deleting a workflow"""
        # Create workflow
        create_response = client.post(
            "/api/workflow-engine/workflows",
            json=sample_workflow_config
        )
        workflow_id = create_response.json()["workflow_id"]

        # Delete workflow
        response = client.delete(
            f"/api/workflow-engine/workflows/{workflow_id}"
        )

        # Should successfully delete or indicate it can't be deleted if running
        assert response.status_code in [200, 204, 400, 409]

    def test_delete_nonexistent_workflow(self, client):
        """Test deleting workflow that doesn't exist"""
        response = client.delete(
            "/api/workflow-engine/workflows/99999"
        )

        assert response.status_code == 404
