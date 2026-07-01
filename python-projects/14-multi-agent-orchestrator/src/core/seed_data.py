"""
Seed data for database initialization
"""

from typing import List, Dict, Any

from src.core.database import DatabaseManager
from src.models import Agent, AgentRole, AgentStatus
from src.models.user import User, UserRole
from src.core.config import settings


# Default agent configurations
DEFAULT_AGENTS = [
    {
        'name': 'Research Agent',
        'role': AgentRole.RESEARCHER,
        'description': 'Gathers information, conducts research, and provides context for tasks',
        'llm_provider': settings.DEFAULT_LLM_PROVIDER,
        'llm_model': settings.DEFAULT_MODEL,
        'temperature': 0.7,
        'max_tokens': 4000,
        'system_prompt': '''You are a Research Agent specialized in gathering and analyzing information.

Your capabilities:
- Search and collect relevant information from various sources
- Analyze and synthesize information into actionable insights
- Provide comprehensive context for decision-making
- Identify key facts, trends, and patterns
- Validate information accuracy and reliability

When given a research task:
1. Understand the research objective and scope
2. Identify information sources and search strategies
3. Collect and organize relevant information
4. Analyze findings and extract key insights
5. Present findings in a clear, structured format

Always cite sources and indicate confidence levels in your findings.'''
    },
    {
        'name': 'Coder Agent',
        'role': AgentRole.CODER,
        'description': 'Writes, modifies, and optimizes code across multiple programming languages',
        'llm_provider': settings.DEFAULT_LLM_PROVIDER,
        'llm_model': settings.DEFAULT_MODEL,
        'temperature': 0.3,
        'max_tokens': 4000,
        'system_prompt': '''You are a Coder Agent specialized in software development.

Your capabilities:
- Write clean, efficient, and maintainable code
- Debug and fix code issues
- Optimize code performance
- Follow best practices and design patterns
- Work with multiple programming languages and frameworks

When given a coding task:
1. Understand requirements and constraints
2. Design the solution architecture
3. Write well-documented code
4. Include error handling and edge cases
5. Ensure code is testable and maintainable

Always write code with clarity, efficiency, and maintainability in mind.'''
    },
    {
        'name': 'Reviewer Agent',
        'role': AgentRole.REVIEWER,
        'description': 'Reviews code quality, identifies issues, and suggests improvements',
        'llm_provider': settings.DEFAULT_LLM_PROVIDER,
        'llm_model': settings.DEFAULT_MODEL,
        'temperature': 0.5,
        'max_tokens': 4000,
        'system_prompt': '''You are a Reviewer Agent specialized in code review and quality assurance.

Your capabilities:
- Review code for bugs, security issues, and performance problems
- Assess code quality and adherence to best practices
- Suggest improvements and refactoring opportunities
- Verify code meets requirements and specifications
- Provide constructive feedback

When reviewing code:
1. Check for correctness and logic errors
2. Identify security vulnerabilities
3. Assess performance implications
4. Verify code style and conventions
5. Suggest specific improvements with examples

Always provide actionable feedback with clear explanations.'''
    },
    {
        'name': 'Tester Agent',
        'role': AgentRole.TESTER,
        'description': 'Creates and executes tests to ensure code quality and functionality',
        'llm_provider': settings.DEFAULT_LLM_PROVIDER,
        'llm_model': settings.DEFAULT_MODEL,
        'temperature': 0.4,
        'max_tokens': 4000,
        'system_prompt': '''You are a Tester Agent specialized in software testing and quality assurance.

Your capabilities:
- Write comprehensive unit, integration, and end-to-end tests
- Design test cases covering edge cases and error conditions
- Execute tests and analyze results
- Identify bugs and create detailed bug reports
- Ensure code coverage and test quality

When creating tests:
1. Understand the code functionality and requirements
2. Design test cases for normal and edge cases
3. Write clear, maintainable test code
4. Include assertions for expected behavior
5. Document test coverage and results

Always aim for comprehensive test coverage and clear test documentation.'''
    },
    {
        'name': 'Writer Agent',
        'role': AgentRole.WRITER,
        'description': 'Generates clear, comprehensive documentation for code and projects',
        'llm_provider': settings.DEFAULT_LLM_PROVIDER,
        'llm_model': settings.DEFAULT_MODEL,
        'temperature': 0.6,
        'max_tokens': 4000,
        'system_prompt': '''You are a Writer Agent specialized in technical documentation.

Your capabilities:
- Write clear, comprehensive documentation
- Create API documentation and user guides
- Generate code comments and docstrings
- Produce README files and tutorials
- Explain complex technical concepts simply

When writing documentation:
1. Understand the audience and their needs
2. Organize information logically
3. Use clear, concise language
4. Include examples and use cases
5. Maintain consistency in style and format

Always prioritize clarity, completeness, and ease of understanding.'''
    },
    {
        'name': 'Coordinator Agent',
        'role': AgentRole.COORDINATOR,
        'description': 'Orchestrates multiple agents and manages complex multi-step workflows',
        'llm_provider': settings.DEFAULT_LLM_PROVIDER,
        'llm_model': settings.DEFAULT_MODEL,
        'temperature': 0.5,
        'max_tokens': 4000,
        'system_prompt': '''You are a Coordinator Agent specialized in task orchestration and agent management.

Your capabilities:
- Break down complex tasks into subtasks
- Assign tasks to appropriate specialist agents
- Monitor task progress and dependencies
- Handle agent communication and coordination
- Ensure task completion and quality

When coordinating tasks:
1. Analyze the overall task and requirements
2. Decompose into logical subtasks
3. Determine task dependencies and order
4. Assign subtasks to appropriate agents
5. Monitor progress and handle issues

Always ensure efficient task execution and quality outcomes.'''
    }
]


class SeedData:
    """
    Database seed data management
    """

    def __init__(self):
        self.db_manager = DatabaseManager()

    def seed_agents(self, force: bool = False) -> Dict[str, Any]:
        """
        Seed database with default agents

        Args:
            force: Re-create agents even if they exist

        Returns:
            dict: Seeding results
        """
        created_count = 0
        skipped_count = 0
        updated_count = 0

        with self.db_manager.session_scope() as session:
            for agent_config in DEFAULT_AGENTS:
                # Check if agent exists
                existing = session.query(Agent).filter(
                    Agent.name == agent_config['name']
                ).first()

                if existing:
                    if force:
                        # Update existing agent
                        for key, value in agent_config.items():
                            if key != 'name':  # Don't update name
                                setattr(existing, key, value)
                        updated_count += 1
                    else:
                        skipped_count += 1
                        continue
                else:
                    # Create new agent
                    agent = Agent(
                        status=AgentStatus.IDLE,
                        is_active=True,
                        **agent_config
                    )
                    session.add(agent)
                    created_count += 1

        result = {
            'success': True,
            'created': created_count,
            'updated': updated_count,
            'skipped': skipped_count,
            'total': len(DEFAULT_AGENTS)
        }

        print(f"✅ Seeded agents: {created_count} created, {updated_count} updated, {skipped_count} skipped")

        return result

    def clear_all_data(self):
        """
        Clear all data from database (keep schema)
        """
        with self.db_manager.session_scope() as session:
            # Delete in order to respect foreign keys
            session.query(TaskDependency).delete()
            session.query(Task).delete()
            session.query(Agent).delete()

        print("🗑️  All data cleared from database")

    def seed_sample_tasks(self) -> Dict[str, Any]:
        """
        Seed database with sample tasks for testing

        Returns:
            dict: Seeding results
        """
        from src.models import Task, TaskStatus

        sample_tasks = [
            {
                'title': 'Research AI Multi-Agent Systems',
                'description': 'Research current state-of-the-art in multi-agent AI systems',
                'task_type': 'research',
                'priority': 3,
                'status': TaskStatus.PENDING,
                'input_data': {
                    'topics': ['multi-agent systems', 'LangGraph', 'agent coordination'],
                    'focus': 'practical implementations'
                }
            },
            {
                'title': 'Implement Task Scheduler',
                'description': 'Build a task scheduler for managing agent workloads',
                'task_type': 'coding',
                'priority': 2,
                'status': TaskStatus.PENDING,
                'input_data': {
                    'language': 'Python',
                    'framework': 'FastAPI',
                    'requirements': ['priority queue', 'task dependencies']
                }
            },
            {
                'title': 'Write API Documentation',
                'description': 'Create comprehensive API documentation for all endpoints',
                'task_type': 'documentation',
                'priority': 4,
                'status': TaskStatus.PENDING,
                'input_data': {
                    'format': 'Markdown',
                    'include': ['endpoints', 'request/response examples', 'authentication']
                }
            }
        ]

        created_count = 0

        with self.db_manager.session_scope() as session:
            for task_config in sample_tasks:
                task = Task(**task_config)
                session.add(task)
                created_count += 1

        print(f"✅ Seeded {created_count} sample tasks")

        return {
            'success': True,
            'created': created_count
        }

    def seed_default_users(self) -> Dict[str, Any]:
        """
        Seed default users for development

        Returns:
            dict: Seeding results
        """
        default_users = [
            {
                'username': 'admin',
                'email': 'admin@example.com',
                'password': 'admin123',  # Change in production!
                'full_name': 'Administrator',
                'role': UserRole.ADMIN,
                'is_superuser': True
            },
            {
                'username': 'user',
                'email': 'user@example.com',
                'password': 'user123',  # Change in production!
                'full_name': 'Regular User',
                'role': UserRole.USER,
                'is_superuser': False
            },
            {
                'username': 'viewer',
                'email': 'viewer@example.com',
                'password': 'viewer123',  # Change in production!
                'full_name': 'View Only User',
                'role': UserRole.VIEWER,
                'is_superuser': False
            }
        ]

        created_count = 0
        skipped_count = 0

        with self.db_manager.session_scope() as session:
            for user_config in default_users:
                # Check if user already exists
                existing = session.query(User).filter(
                    (User.username == user_config['username']) |
                    (User.email == user_config['email'])
                ).first()

                if existing:
                    skipped_count += 1
                    continue

                # Create user with hashed password
                password = user_config.pop('password')
                user = User(
                    **user_config,
                    hashed_password=User.get_password_hash(password),
                    is_active=True
                )
                session.add(user)
                created_count += 1

        print(f"✅ Seeded {created_count} default users (skipped {skipped_count} existing)")

        return {
            'success': True,
            'created': created_count,
            'skipped': skipped_count
        }


# Singleton instance
seed_data = SeedData()
