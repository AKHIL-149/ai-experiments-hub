#!/usr/bin/env python3
"""
Test Dashboard Task Creation Feature
Verifies that tasks can be created via the dashboard API
"""

import requests
import time
import sys
from datetime import datetime

BASE_URL = "http://localhost:8001"

def print_section(title):
    """Print formatted section header"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}\n")

def check_server_health():
    """Check if server is running"""
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=5)
        return response.status_code == 200
    except:
        return False

def create_task_via_api(title, description, task_type, priority, agent_id=None):
    """Create a task using the dashboard API"""
    task_data = {
        "title": title,
        "description": description,
        "task_type": task_type,
        "priority": priority,
        "input_data": {
            "created_from": "dashboard",
            "timestamp": datetime.now().isoformat(),
            "test": True
        }
    }

    if agent_id:
        task_data["assigned_agent_id"] = agent_id

    try:
        response = requests.post(
            f"{BASE_URL}/api/tasks",
            json=task_data,
            timeout=10
        )

        if response.status_code == 200:
            return True, response.json()
        else:
            return False, response.json()
    except Exception as e:
        return False, str(e)

def get_available_agents():
    """Get list of available agents"""
    try:
        response = requests.get(f"{BASE_URL}/api/agents", timeout=5)
        if response.status_code == 200:
            return response.json()
        return []
    except:
        return []

def get_dashboard_metrics():
    """Get dashboard metrics"""
    try:
        response = requests.get(f"{BASE_URL}/api/monitoring/dashboard", timeout=5)
        if response.status_code == 200:
            return response.json()
        return None
    except:
        return None

def main():
    """Main test function"""
    print_section("🧪 Dashboard Task Creation Feature Test")

    # Step 1: Check server health
    print("Step 1: Checking server health...")
    if not check_server_health():
        print("   ❌ Server is not running!")
        print("   💡 Start the server with: python3 server.py")
        sys.exit(1)
    print("   ✅ Server is healthy and running\n")

    # Step 2: Get initial metrics
    print("Step 2: Getting baseline metrics...")
    initial_metrics = get_dashboard_metrics()
    if initial_metrics:
        initial_count = initial_metrics['overview']['total_tasks']
        print(f"   ✅ Current task count: {initial_count}\n")
    else:
        print("   ⚠️  Could not fetch initial metrics\n")
        initial_count = 0

    # Step 3: Get available agents
    print("Step 3: Loading available agents...")
    agents = get_available_agents()
    if agents:
        print(f"   ✅ Found {len(agents)} agents:")
        for agent in agents:
            print(f"      - {agent['name']} ({agent['role']})")
        print()
        first_agent_id = agents[0]['id']
    else:
        print("   ⚠️  No agents found (will create unassigned task)")
        print("   💡 Run: python3 demo_database_workflow.py to create sample agents\n")
        first_agent_id = None

    # Step 4: Create test tasks
    print_section("Step 4: Creating Test Tasks")

    test_tasks = [
        {
            "title": "Dashboard Test - Code Review",
            "description": "Testing dashboard task creation with code review type",
            "task_type": "code_review",
            "priority": 7,
            "agent_id": first_agent_id
        },
        {
            "title": "Dashboard Test - Data Analysis",
            "description": "Testing dashboard task creation with data analysis type",
            "task_type": "data_analysis",
            "priority": 5,
            "agent_id": None
        },
        {
            "title": "Dashboard Test - Documentation",
            "description": "Testing dashboard task creation with documentation type",
            "task_type": "documentation",
            "priority": 3,
            "agent_id": first_agent_id if first_agent_id else None
        }
    ]

    created_tasks = []

    for i, task_config in enumerate(test_tasks, 1):
        print(f"Creating task {i}/{len(test_tasks)}: {task_config['title']}")

        success, result = create_task_via_api(
            task_config['title'],
            task_config['description'],
            task_config['task_type'],
            task_config['priority'],
            task_config['agent_id']
        )

        if success:
            print(f"   ✅ Created successfully!")
            print(f"      ID: {result['id']}")
            print(f"      Status: {result['status']}")
            print(f"      Priority: {result['priority']}")
            created_tasks.append(result['id'])
        else:
            print(f"   ❌ Failed to create task")
            print(f"      Error: {result}")

        print()
        time.sleep(0.5)

    # Step 5: Verify tasks were created
    print_section("Step 5: Verifying Task Creation")

    final_metrics = get_dashboard_metrics()
    if final_metrics:
        final_count = final_metrics['overview']['total_tasks']
        tasks_created = final_count - initial_count

        print(f"Initial task count: {initial_count}")
        print(f"Final task count: {final_count}")
        print(f"Tasks created: {tasks_created}\n")

        if tasks_created == len(created_tasks):
            print("✅ All tasks successfully created and visible in dashboard!")
        else:
            print(f"⚠️  Expected {len(created_tasks)} tasks, but count increased by {tasks_created}")

        print("\n📊 Updated Dashboard Metrics:")
        print(f"   Total Tasks: {final_metrics['overview']['total_tasks']}")
        print(f"   Tasks (24h): {final_metrics['overview']['tasks_24h']}")
        print(f"   Pending: {final_metrics['tasks']['pending']}")
        print(f"   Running: {final_metrics['tasks']['running']}")
        print(f"   Completed: {final_metrics['tasks']['completed']}")
        print(f"   Failed: {final_metrics['tasks']['failed']}")
    else:
        print("❌ Could not fetch final metrics")

    # Step 6: Summary
    print_section("✅ Test Complete!")

    print(f"Successfully created {len(created_tasks)} tasks:")
    for task_id in created_tasks:
        print(f"   ✅ Task ID: {task_id}")

    print("\n🌐 Next Steps:")
    print(f"   • View Dashboard: {BASE_URL}/dashboard")
    print(f"   • Click '➕ Create Task' button to test the UI")
    print(f"   • Check task details: {BASE_URL}/api/tasks/<task_id>")
    print("\n📖 Documentation:")
    print("   • See DASHBOARD_TASK_CREATION.md for full feature guide")
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
