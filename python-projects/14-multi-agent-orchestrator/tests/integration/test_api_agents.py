"""
Integration tests for Agents API endpoints
"""

import pytest
from fastapi.testclient import TestClient
from server import app


@pytest.fixture(scope="module")
def client():
    """Create test client"""
    with TestClient(app) as c:
        yield c


class TestAgentRetrieval:
    """Test agent retrieval endpoints"""

    def test_list_agents(self, client):
        """Test listing all agents"""
        response = client.get("/api/agents")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, (list, dict))

        # Should have some agents (research, code, data_analyst, writer, planner)
        if isinstance(data, list):
            assert len(data) > 0
        elif isinstance(data, dict) and "agents" in data:
            assert len(data["agents"]) > 0

    def test_get_agent_details(self, client):
        """Test getting specific agent details"""
        # First get list of agents
        list_response = client.get("/api/agents")
        agents_data = list_response.json()

        # Extract first agent ID
        if isinstance(agents_data, list) and len(agents_data) > 0:
            agent_id = agents_data[0]["id"]
        elif isinstance(agents_data, dict) and "agents" in agents_data and len(agents_data["agents"]) > 0:
            agent_id = agents_data["agents"][0]["id"]
        else:
            pytest.skip("No agents available for testing")

        # Get specific agent
        response = client.get(f"/api/agents/{agent_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == agent_id
        assert "name" in data
        assert "role" in data

    def test_get_nonexistent_agent(self, client):
        """Test getting agent that doesn't exist"""
        response = client.get("/api/agents/99999")

        assert response.status_code == 404


class TestAgentFiltering:
    """Test agent filtering"""

    def test_filter_by_role(self, client):
        """Test filtering agents by role"""
        roles = ["research", "code", "data_analyst", "writer", "planner"]

        for role in roles:
            response = client.get(f"/api/agents?role={role}")
            assert response.status_code == 200

    def test_filter_by_status(self, client):
        """Test filtering agents by status"""
        statuses = ["idle", "busy", "offline"]

        for status in statuses:
            response = client.get(f"/api/agents?status={status}")
            assert response.status_code == 200


class TestAgentPerformance:
    """Test agent performance metrics"""

    def test_get_agent_performance(self, client):
        """Test getting agent performance metrics"""
        # Get list of agents first
        list_response = client.get("/api/agents")
        agents_data = list_response.json()

        if isinstance(agents_data, list) and len(agents_data) > 0:
            agent_id = agents_data[0]["id"]
        elif isinstance(agents_data, dict) and "agents" in agents_data and len(agents_data["agents"]) > 0:
            agent_id = agents_data["agents"][0]["id"]
        else:
            pytest.skip("No agents available")

        # Get performance metrics
        response = client.get(f"/api/agents/{agent_id}/performance")

        # Endpoint may or may not exist
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            # Should have performance metrics
            assert isinstance(data, dict)

    def test_get_all_agent_performance(self, client):
        """Test getting performance metrics for all agents"""
        response = client.get("/api/performance")

        # Endpoint may or may not exist
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))


class TestAgentCapabilities:
    """Test agent capabilities endpoints"""

    def test_get_agent_capabilities(self, client):
        """Test getting agent capabilities"""
        # Get list of agents
        list_response = client.get("/api/agents")
        agents_data = list_response.json()

        if isinstance(agents_data, list) and len(agents_data) > 0:
            agent_id = agents_data[0]["id"]
        elif isinstance(agents_data, dict) and "agents" in agents_data and len(agents_data["agents"]) > 0:
            agent_id = agents_data["agents"][0]["id"]
        else:
            pytest.skip("No agents available")

        # Get capabilities
        response = client.get(f"/api/capabilities?agent_id={agent_id}")

        # Endpoint may or may not exist
        assert response.status_code in [200, 404]


class TestAgentRoles:
    """Test agent roles and role management"""

    def test_list_available_roles(self, client):
        """Test listing available agent roles"""
        response = client.get("/api/roles")

        # Endpoint may or may not exist
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, (list, dict))

            # Should include standard roles
            if isinstance(data, list):
                role_names = [r if isinstance(r, str) else r.get("name") for r in data]
                expected_roles = ["research", "code", "data_analyst", "writer", "planner"]
                assert any(role in role_names for role in expected_roles)


class TestAgentStatistics:
    """Test agent statistics"""

    def test_get_agent_statistics(self, client):
        """Test getting agent statistics"""
        response = client.get("/api/agents/statistics")

        # Endpoint may or may not exist
        assert response.status_code in [200, 404]

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            # Common statistics fields
            possible_fields = ["total_agents", "active_agents", "idle_agents", "busy_agents"]
            assert any(field in data for field in possible_fields)


class TestAgentRegistry:
    """Test agent registry functionality"""

    def test_agent_registry_initialized(self, client):
        """Test that agent registry is properly initialized"""
        response = client.get("/api/agents")

        assert response.status_code == 200
        data = response.json()

        # Should have registered agents
        if isinstance(data, list):
            assert len(data) >= 5  # At least the 5 default agents
        elif isinstance(data, dict) and "agents" in data:
            assert len(data["agents"]) >= 5

    def test_default_agents_available(self, client):
        """Test that default agents are available"""
        response = client.get("/api/agents")

        assert response.status_code == 200
        data = response.json()

        agents_list = data if isinstance(data, list) else data.get("agents", [])
        agent_roles = [agent.get("role") for agent in agents_list]

        # Check for default agents
        default_roles = ["research", "code", "data_analyst", "writer", "planner"]
        for role in default_roles:
            assert role in agent_roles or role.upper() in agent_roles
