#!/usr/bin/env python3
"""
Database Workflow Demo - Direct database interaction to demonstrate the system
"""

import sys
from datetime import datetime
from src.core.database import SessionLocal
from src.models.task import Task, TaskStatus, TaskPriority
from src.models.agent import Agent, AgentStatus, AgentRole
from src.models.agent_execution import AgentExecution, ExecutionStatus
import requests

def print_header(text):
    """Print formatted header"""
    print(f"\n{'='*70}")
    print(f"  {text}")
    print(f"{'='*70}\n")

def create_sample_data():
    """Create sample tasks and agents in database"""
    db = SessionLocal()
    try:
        print_header("📊 Creating Sample Data in Database")

        # Create agents
        print("Creating agents...")
        agents = []

        agent1 = Agent(
            name="CodeReviewer",
            role=AgentRole.REVIEWER,
            description="Specialized in code review and security analysis",
            status=AgentStatus.IDLE,
            capabilities={"languages": ["Python", "JavaScript"], "skills": ["security", "performance"]},
            llm_provider="openai",
            llm_model="gpt-4-turbo-preview"
        )
        db.add(agent1)
        agents.append(agent1)

        agent2 = Agent(
            name="DataAnalyst",
            role=AgentRole.RESEARCHER,
            description="Specialized in data analysis and visualization",
            status=AgentStatus.IDLE,
            capabilities={"tools": ["pandas", "matplotlib"], "skills": ["statistics", "visualization"]},
            llm_provider="openai",
            llm_model="gpt-4-turbo-preview"
        )
        db.add(agent2)
        agents.append(agent2)

        agent3 = Agent(
            name="DocWriter",
            role=AgentRole.WRITER,
            description="Specialized in technical documentation",
            status=AgentStatus.IDLE,
            capabilities={"formats": ["markdown", "rst"], "skills": ["technical-writing"]},
            llm_provider="openai",
            llm_model="gpt-4-turbo-preview"
        )
        db.add(agent3)
        agents.append(agent3)

        db.commit()
        print(f"   ✅ Created {len(agents)} agents\n")

        # Create tasks
        print("Creating tasks...")
        tasks = []

        task1 = Task(
            title="Security Review - Authentication Module",
            description="Perform comprehensive security review of the authentication system",
            task_type="code_review",
            priority=3,
            status=TaskStatus.PENDING,
            assigned_agent_id=agent1.id,
            input_data={"file": "auth.py", "focus": ["security", "vulnerabilities"]},
            requires_approval=False
        )
        db.add(task1)
        tasks.append(task1)

        task2 = Task(
            title="Analyze User Engagement Metrics",
            description="Process and analyze last month's user engagement data",
            task_type="data_analysis",
            priority=5,
            status=TaskStatus.IN_PROGRESS,
            assigned_agent_id=agent2.id,
            input_data={"dataset": "user_engagement_2026_06.csv"},
            progress_percentage=45.0
        )
        db.add(task2)
        tasks.append(task2)

        task3 = Task(
            title="Update API Documentation",
            description="Document all new endpoints added in v2.0 release",
            task_type="documentation",
            priority=7,
            status=TaskStatus.PENDING,
            assigned_agent_id=agent3.id,
            input_data={"version": "2.0", "endpoints": ["/api/tasks", "/api/agents"]}
        )
        db.add(task3)
        tasks.append(task3)

        task4 = Task(
            title="Code Optimization - Database Queries",
            description="Optimize slow database queries in the reporting module",
            task_type="optimization",
            priority=4,
            status=TaskStatus.COMPLETED,
            assigned_agent_id=agent1.id,
            progress_percentage=100.0,
            started_at=datetime.now(),
            completed_at=datetime.now()
        )
        db.add(task4)
        tasks.append(task4)

        task5 = Task(
            title="Fix Bug #1234 - Login Timeout",
            description="Fix the login timeout issue reported in production",
            task_type="bugfix",
            priority=2,
            status=TaskStatus.FAILED,
            assigned_agent_id=agent1.id,
            error_message="Unable to reproduce the issue in test environment"
        )
        db.add(task5)
        tasks.append(task5)

        db.commit()
        print(f"   ✅ Created {len(tasks)} tasks\n")

        # Create agent executions
        print("Creating agent execution records...")
        execution = AgentExecution(
            agent_id=agent2.id,
            task_id=task2.id,
            status=ExecutionStatus.RUNNING,
            input_data={"dataset_path": "/data/user_engagement.csv"},
            started_at=datetime.now(),
            llm_provider="openai",
            llm_model="gpt-4-turbo-preview"
        )
        db.add(execution)
        db.commit()
        print(f"   ✅ Created 1 execution record\n")

        return len(tasks), len(agents)

    except Exception as e:
        db.rollback()
        print(f"   ❌ Error: {e}")
        return 0, 0
    finally:
        db.close()

def view_database_status():
    """Display current database status"""
    db = SessionLocal()
    try:
        print_header("📋 Current Database Status")

        # Count records
        task_count = db.query(Task).count()
        agent_count = db.query(Agent).count()
        execution_count = db.query(AgentExecution).count()

        print(f"Total Records:")
        print(f"   Tasks: {task_count}")
        print(f"   Agents: {agent_count}")
        print(f"   Executions: {execution_count}\n")

        # Task breakdown
        print("Task Status Breakdown:")
        for status in TaskStatus:
            count = db.query(Task).filter(Task.status == status).count()
            if count > 0:
                print(f"   {status.value}: {count}")

        print()

        # Agent breakdown
        print("Agent Status Breakdown:")
        for status in AgentStatus:
            count = db.query(Agent).filter(Agent.status == status).count()
            if count > 0:
                print(f"   {status.value}: {count}")

        print()

        # List all tasks
        print("All Tasks:")
        tasks = db.query(Task).all()
        for task in tasks:
            agent_name = db.query(Agent.name).filter(Agent.id == task.assigned_agent_id).scalar() if task.assigned_agent_id else "Unassigned"
            print(f"   [{task.id}] {task.title}")
            print(f"       Status: {task.status.value} | Priority: {task.priority} | Agent: {agent_name}")

    finally:
        db.close()

def check_monitoring_api():
    """Check monitoring API with real data"""
    print_header("🌐 Monitoring API Check")

    try:
        # Dashboard
        print("Fetching dashboard metrics...")
        response = requests.get("http://localhost:8001/api/monitoring/dashboard", timeout=5)
        dashboard = response.json()

        print(f"\n📊 Dashboard Overview:")
        print(f"   Total Tasks: {dashboard['overview']['total_tasks']}")
        print(f"   Total Agents: {dashboard['overview']['total_agents']}")
        print(f"   Total Executions: {dashboard['overview']['total_executions']}")

        print(f"\n📋 Task Metrics:")
        print(f"   Pending: {dashboard['tasks']['pending']}")
        print(f"   Running: {dashboard['tasks']['running']}")
        print(f"   Completed: {dashboard['tasks']['completed']}")
        print(f"   Failed: {dashboard['tasks']['failed']}")
        print(f"   Success Rate: {dashboard['tasks']['success_rate']}%")

        print(f"\n🤖 Agent Metrics:")
        print(f"   Active: {dashboard['agents']['active']}")
        print(f"   Busy: {dashboard['agents']['busy']}")
        print(f"   Idle: {dashboard['agents']['idle']}")
        print(f"   Offline: {dashboard['agents']['offline']}")

        # Health check
        print("\n" + "="*70)
        print("Checking system health...")
        response = requests.get("http://localhost:8001/api/monitoring/health", timeout=5)
        health = response.json()

        print(f"\n🏥 System Health: {health['status'].upper()}")
        if health['issues']:
            print("   Issues:")
            for issue in health['issues']:
                print(f"   - {issue}")
        else:
            print("   ✅ No issues detected")

        print(f"\n   Health Metrics:")
        print(f"   - Stuck Tasks: {health['metrics']['stuck_tasks']}")
        print(f"   - Failed Tasks (1h): {health['metrics']['failed_tasks_1h']}")
        print(f"   - Agent Availability: {health['metrics']['agent_availability_percent']}%")

    except Exception as e:
        print(f"   ❌ Error accessing API: {e}")

def main():
    """Main demonstration"""
    print_header("🚀 Multi-Agent Orchestrator - Database Workflow Demo")

    print("This demo will:")
    print("   1. Create sample tasks and agents in the database")
    print("   2. Display the database status")
    print("   3. Verify monitoring APIs show the data")
    print()

    # Create sample data
    tasks_created, agents_created = create_sample_data()

    if tasks_created > 0:
        # View database
        view_database_status()

        # Check monitoring API
        check_monitoring_api()

        # Summary
        print_header("✅ Demo Complete!")
        print(f"Successfully created:")
        print(f"   ✅ {agents_created} agents")
        print(f"   ✅ {tasks_created} tasks")
        print(f"   ✅ 1 execution record")
        print()
        print("🌐 Next Steps:")
        print("   • View Dashboard: http://localhost:8001/dashboard")
        print("   • API Docs: http://localhost:8001/docs")
        print("   • Monitoring: http://localhost:8001/api/monitoring/dashboard")
        print()
        print("📖 Documentation:")
        print("   • QUICK_WORKFLOW_DEMO.md - More examples")
        print("   • VERIFICATION_CHECKLIST.md - System status")
        print()
    else:
        print("❌ Failed to create sample data")
        print("   Check that the database is properly configured")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Demo interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
