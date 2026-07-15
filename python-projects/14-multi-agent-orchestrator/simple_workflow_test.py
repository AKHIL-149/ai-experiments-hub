#!/usr/bin/env python3
"""
Simple Workflow Test - Demonstrates the Multi-Agent Orchestrator in action
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:8001"

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")

def create_task(title, description, task_type="test", priority=5):
    """Create a new task"""
    print(f"📝 Creating task: {title}")
    try:
        response = requests.post(
            f"{BASE_URL}/api/tasks",
            json={
                "title": title,
                "description": description,
                "task_type": task_type,
                "priority": priority,
                "input_data": {
                    "created_at": datetime.now().isoformat(),
                    "demo": True
                }
            },
            timeout=5
        )
        response.raise_for_status()
        task = response.json()
        print(f"   ✅ Task created successfully!")
        print(f"   - ID: {task.get('id')}")
        print(f"   - Status: {task.get('status')}")
        return task
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Error creating task: {e}")
        return None

def get_task(task_id):
    """Get task details"""
    try:
        response = requests.get(f"{BASE_URL}/api/tasks/{task_id}", timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Error getting task: {e}")
        return None

def get_dashboard_metrics():
    """Get dashboard metrics"""
    try:
        response = requests.get(f"{BASE_URL}/api/monitoring/dashboard", timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Error getting dashboard: {e}")
        return None

def check_server_health():
    """Check if server is running"""
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=5)
        response.raise_for_status()
        health = response.json()
        return health.get('status') == 'healthy'
    except:
        return False

def main():
    """Main workflow demonstration"""
    print_section("🚀 Multi-Agent Orchestrator - Simple Workflow Demo")

    # Step 1: Check server health
    print("Step 1: Checking server health...")
    if not check_server_health():
        print("   ❌ Server is not running!")
        print("   💡 Start the server with: python3 server.py")
        return
    print("   ✅ Server is healthy and running\n")

    # Step 2: Create sample tasks
    print_section("Step 2: Creating Sample Tasks")

    tasks_created = []

    # Task 1: Code Review
    task1 = create_task(
        "Code Review - Authentication Module",
        "Review auth.py for security vulnerabilities and best practices",
        "code_review",
        priority=3
    )
    if task1:
        tasks_created.append(task1['id'])

    time.sleep(0.5)

    # Task 2: Data Analysis
    task2 = create_task(
        "Analyze User Engagement Data",
        "Process last month's user engagement metrics",
        "data_analysis",
        priority=5
    )
    if task2:
        tasks_created.append(task2['id'])

    time.sleep(0.5)

    # Task 3: Documentation
    task3 = create_task(
        "Update API Documentation",
        "Document new endpoints added in v2.0",
        "documentation",
        priority=7
    )
    if task3:
        tasks_created.append(task3['id'])

    # Step 3: Retrieve task details
    print_section("Step 3: Verifying Tasks Were Created")

    for task_id in tasks_created:
        task = get_task(task_id)
        if task:
            print(f"✅ Task {task_id}:")
            print(f"   Title: {task.get('title')}")
            print(f"   Status: {task.get('status')}")
            print(f"   Priority: {task.get('priority')}")
            print()

    # Step 4: Check dashboard metrics
    print_section("Step 4: Dashboard Metrics")

    dashboard = get_dashboard_metrics()
    if dashboard:
        print("📊 System Overview:")
        print(f"   Total Tasks: {dashboard['overview']['total_tasks']}")
        print(f"   Total Agents: {dashboard['overview']['total_agents']}")
        print(f"   Total Executions: {dashboard['overview']['total_executions']}")
        print(f"   Total Workflows: {dashboard['overview']['total_workflows']}")
        print()

        print("📋 Task Breakdown:")
        print(f"   Pending: {dashboard['tasks']['pending']}")
        print(f"   Running: {dashboard['tasks']['running']}")
        print(f"   Completed: {dashboard['tasks']['completed']}")
        print(f"   Failed: {dashboard['tasks']['failed']}")
        print()

        print("🤖 Agent Status:")
        print(f"   Active: {dashboard['agents']['active']}")
        print(f"   Busy: {dashboard['agents']['busy']}")
        print(f"   Idle: {dashboard['agents']['idle']}")
        print(f"   Offline: {dashboard['agents']['offline']}")

    # Step 5: Summary
    print_section("✅ Workflow Test Complete!")

    print(f"Created {len(tasks_created)} tasks successfully!")
    print()
    print("🌐 Next Steps:")
    print(f"   • View Dashboard: {BASE_URL}/dashboard")
    print(f"   • API Docs: {BASE_URL}/docs")
    print(f"   • Health Check: {BASE_URL}/api/health")
    print()
    print("📖 For more examples, see:")
    print("   • QUICK_WORKFLOW_DEMO.md - Detailed examples")
    print("   • API_USAGE.md - Complete API reference")
    print("   • MONITORING.md - Monitoring features")
    print()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Workflow test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
