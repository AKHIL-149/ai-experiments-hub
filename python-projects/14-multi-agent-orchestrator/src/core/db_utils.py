"""
Database utility functions
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from src.core.database import DatabaseManager, Base, engine
from src.models import Task, TaskStatus, TaskDependency, Agent, AgentRole, AgentStatus


class DatabaseUtils:
    """
    Database utility functions for common operations
    """

    def __init__(self):
        self.db_manager = DatabaseManager()

    def initialize_database(self, drop_existing: bool = False):
        """
        Initialize database schema

        Args:
            drop_existing: Drop existing tables before creating
        """
        if drop_existing:
            print("⚠️  Dropping existing tables...")
            Base.metadata.drop_all(bind=engine)

        print("📊 Creating database tables...")
        Base.metadata.create_all(bind=engine)
        print("✅ Database schema initialized")

    def reset_database(self):
        """
        Reset database (drop and recreate all tables)
        """
        print("⚠️  Resetting database...")
        self.initialize_database(drop_existing=True)

    def verify_database(self) -> Dict[str, Any]:
        """
        Verify database connection and schema

        Returns:
            dict: Database status information
        """
        try:
            with self.db_manager.session_scope() as session:
                # Check if tables exist by counting records
                task_count = session.query(Task).count()
                agent_count = session.query(Agent).count()

                return {
                    'status': 'healthy',
                    'tasks_count': task_count,
                    'agents_count': agent_count,
                    'message': 'Database connection successful'
                }
        except Exception as e:
            return {
                'status': 'error',
                'error': str(e),
                'message': 'Database connection failed'
            }

    def get_table_counts(self) -> Dict[str, int]:
        """
        Get row counts for all tables

        Returns:
            dict: Table name to count mapping
        """
        with self.db_manager.session_scope() as session:
            return {
                'tasks': session.query(Task).count(),
                'task_dependencies': session.query(TaskDependency).count(),
                'agents': session.query(Agent).count(),
            }

    def cleanup_old_data(self, days: int = 30):
        """
        Clean up old completed tasks

        Args:
            days: Keep data newer than this many days
        """
        from datetime import datetime, timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        with self.db_manager.session_scope() as session:
            # Delete old completed/failed tasks
            deleted = session.query(Task).filter(
                Task.status.in_([TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]),
                Task.completed_at < cutoff_date
            ).delete()

            print(f"🗑️  Deleted {deleted} old tasks")

            return deleted

    def get_database_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive database statistics

        Returns:
            dict: Database statistics
        """
        with self.db_manager.session_scope() as session:
            # Task statistics by status
            task_stats = {}
            for status in TaskStatus:
                count = session.query(Task).filter(Task.status == status).count()
                task_stats[status.value] = count

            # Agent statistics by role and status
            agent_stats = {
                'by_role': {},
                'by_status': {}
            }

            for role in AgentRole:
                count = session.query(Agent).filter(Agent.role == role).count()
                agent_stats['by_role'][role.value] = count

            for status in AgentStatus:
                count = session.query(Agent).filter(Agent.status == status).count()
                agent_stats['by_status'][status.value] = count

            # Task dependencies
            dependency_count = session.query(TaskDependency).count()

            return {
                'tasks': {
                    'total': session.query(Task).count(),
                    'by_status': task_stats,
                    'dependencies': dependency_count
                },
                'agents': {
                    'total': session.query(Agent).count(),
                    'by_role': agent_stats['by_role'],
                    'by_status': agent_stats['by_status']
                }
            }

    def export_agents_config(self) -> List[Dict[str, Any]]:
        """
        Export all agents as configuration

        Returns:
            list: Agent configurations
        """
        with self.db_manager.session_scope() as session:
            agents = session.query(Agent).all()

            return [
                {
                    'name': agent.name,
                    'role': agent.role.value,
                    'description': agent.description,
                    'llm_provider': agent.llm_provider,
                    'llm_model': agent.llm_model,
                    'system_prompt': agent.system_prompt,
                }
                for agent in agents
            ]


# Singleton instance
db_utils = DatabaseUtils()
