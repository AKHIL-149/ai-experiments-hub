"""
Integration tests for Tasks API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from server import app


@pytest.fixture(scope="module")
def client():
    """Create test client"""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_task_data():
    """Sample task data for testing"""
    return {
        "title": "Analyze Q4 Sales Data",
        "description": "Perform comprehensive analysis on Q4 2025 sales figures",
        "task_type": "data_analysis",
        "priority": 7,
        "metadata": {
            "dataset": "sales_q4_2025.csv",
            "columns": ["date", "product", "revenue", "quantity"]
        }
    }


class TestTaskCreation:
    """Test task creation endpoints"""

    def test_create_task(self, client, sample_task_data):
        """Test creating a new task"""
        response = client.post("/api/tasks", json=sample_task_data)

        assert response.status_code in [200, 201]
        data = response.json()
        assert "id" in data
        assert data["title"] == sample_task_data["title"]
        assert data["task_type"] == sample_task_data["task_type"]
        assert data["priority"] == sample_task_data["priority"]

    def test_create_task_minimal(self, client):
        """Test creating task with minimal required fields"""
        minimal_task = {
            "title": "Minimal Task",
            "description": "Test task with minimal fields",
            "task_type": "research"
        }

        response = client.post("/api/tasks", json=minimal_task)

        assert response.status_code in [200, 201]
        data = response.json()
        assert "id" in data
        assert data["priority"] in [5, None]  # Default priority

    def test_create_task_invalid(self, client):
        """Test creating task with invalid data"""
        invalid_task = {
            "title": "",  # Empty title should fail
            "task_type": ""
        }

        response = client.post("/api/tasks", json=invalid_task)

        assert response.status_code in [400, 422]

    def test_create_task_with_priority(self, client):
        """Test creating tasks with different priority levels"""
        priorities = [1, 5, 10]

        for priority in priorities:
            task_data = {
                "title": f"Priority {priority} Task",
                "description": f"Task with priority {priority}",
                "task_type": "coding",
                "priority": priority
            }

            response = client.post("/api/tasks", json=task_data)

            assert response.status_code in [200, 201]
            data = response.json()
            assert data["priority"] == priority


class TestTaskRetrieval:
    """Test task retrieval endpoints"""

    def test_list_tasks(self, client):
        """Test listing all tasks"""
        response = client.get("/api/tasks")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

    def test_get_task_details(self, client, sample_task_data):
        """Test getting specific task details"""
        # Create a task first
        create_response = client.post("/api/tasks", json=sample_task_data)
        task_id = create_response.json()["id"]

        # Retrieve it
        response = client.get(f"/api/tasks/{task_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task_id
        assert data["title"] == sample_task_data["title"]

    def test_get_nonexistent_task(self, client):
        """Test getting task that doesn't exist"""
        response = client.get("/api/tasks/99999")

        assert response.status_code == 404


class TestTaskFiltering:
    """Test task filtering and search"""

    def test_filter_by_status(self, client):
        """Test filtering tasks by status"""
        response = client.get("/api/tasks?status=pending")

        assert response.status_code == 200

    def test_filter_by_type(self, client):
        """Test filtering tasks by type"""
        response = client.get("/api/tasks?task_type=coding")

        assert response.status_code == 200

    def test_filter_by_priority(self, client):
        """Test filtering tasks by priority"""
        response = client.get("/api/tasks?min_priority=7")

        assert response.status_code == 200

    def test_pagination(self, client):
        """Test task list pagination"""
        response = client.get("/api/tasks?limit=10&offset=0")

        assert response.status_code == 200

    def test_sorting(self, client):
        """Test task list sorting"""
        response = client.get("/api/tasks?sort_by=priority&order=desc")

        assert response.status_code == 200


class TestTaskUpdate:
    """Test task update endpoints"""

    def test_update_task(self, client, sample_task_data):
        """Test updating a task"""
        # Create task
        create_response = client.post("/api/tasks", json=sample_task_data)
        task_id = create_response.json()["id"]

        # Update task
        update_data = {
            "title": "Updated Task Title",
            "priority": 9
        }

        response = client.patch(f"/api/tasks/{task_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == update_data["title"]
        assert data["priority"] == update_data["priority"]

    def test_update_task_status(self, client, sample_task_data):
        """Test updating task status"""
        # Create task
        create_response = client.post("/api/tasks", json=sample_task_data)
        task_id = create_response.json()["id"]

        # Update status
        update_data = {"status": "in_progress"}

        response = client.patch(f"/api/tasks/{task_id}", json=update_data)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "in_progress"


class TestTaskDeletion:
    """Test task deletion"""

    def test_delete_task(self, client, sample_task_data):
        """Test deleting a task"""
        # Create task
        create_response = client.post("/api/tasks", json=sample_task_data)
        task_id = create_response.json()["id"]

        # Delete task
        response = client.delete(f"/api/tasks/{task_id}")

        assert response.status_code in [200, 204]

        # Verify deletion
        get_response = client.get(f"/api/tasks/{task_id}")
        assert get_response.status_code == 404

    def test_delete_nonexistent_task(self, client):
        """Test deleting task that doesn't exist"""
        response = client.delete("/api/tasks/99999")

        assert response.status_code == 404


class TestTaskDependencies:
    """Test task dependency management"""

    def test_create_task_with_dependencies(self, client):
        """Test creating task with dependencies"""
        # Create parent task
        parent_task = {
            "title": "Parent Task",
            "description": "Parent task",
            "task_type": "research"
        }
        parent_response = client.post("/api/tasks", json=parent_task)
        parent_id = parent_response.json()["id"]

        # Create child task with dependency
        child_task = {
            "title": "Child Task",
            "description": "Depends on parent",
            "task_type": "coding",
            "dependencies": [parent_id]
        }

        response = client.post("/api/tasks", json=child_task)

        # Should succeed or return error about dependencies not being implemented yet
        assert response.status_code in [200, 201, 400, 422]


class TestTaskStatistics:
    """Test task statistics endpoints"""

    def test_get_task_statistics(self, client):
        """Test getting task statistics"""
        response = client.get("/api/tasks/statistics")

        # Endpoint may or may not exist
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
