"""
Integration tests for database operations
"""

import pytest
from sqlalchemy.exc import IntegrityError
from src.models.task import Task, TaskStatus, TaskDependency
from src.models.agent import Agent, AgentRole, AgentStatus


@pytest.mark.integration
@pytest.mark.database
class TestTaskDatabaseOperations:
    """Integration tests for Task model database operations"""

    def test_create_task(self, db_session, sample_agent):
        """Test creating a task in the database"""
        task = Task(
            title="Test Task",
            description="Test description",
            task_type="coding",
            status=TaskStatus.PENDING,
            priority=5,
            assigned_agent_id=sample_agent.id
        )

        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.id is not None
        assert task.title == "Test Task"
        assert task.status == TaskStatus.PENDING
        assert task.assigned_agent_id == sample_agent.id

    def test_update_task_status(self, db_session, sample_task):
        """Test updating task status"""
        sample_task.status = TaskStatus.IN_PROGRESS
        sample_task.progress = 50
        db_session.commit()
        db_session.refresh(sample_task)

        assert sample_task.status == TaskStatus.IN_PROGRESS
        assert sample_task.progress == 50

    def test_delete_task(self, db_session, sample_task):
        """Test deleting a task"""
        task_id = sample_task.id

        db_session.delete(sample_task)
        db_session.commit()

        deleted_task = db_session.query(Task).filter_by(id=task_id).first()
        assert deleted_task is None

    def test_query_tasks_by_status(self, db_session, multiple_tasks):
        """Test querying tasks by status"""
        pending_tasks = db_session.query(Task).filter_by(
            status=TaskStatus.PENDING
        ).all()

        assert len(pending_tasks) >= 1
        assert all(task.status == TaskStatus.PENDING for task in pending_tasks)

    def test_task_agent_relationship(self, db_session, sample_task, sample_agent):
        """Test task-agent relationship"""
        assert sample_task.assigned_agent is not None
        assert sample_task.assigned_agent.id == sample_agent.id
        assert sample_task.assigned_agent.name == sample_agent.name

    def test_is_ready_to_execute_no_dependencies(self, db_session, sample_task):
        """Test is_ready_to_execute with no dependencies"""
        assert sample_task.is_ready_to_execute() is True

    def test_is_ready_to_execute_with_completed_dependencies(
        self,
        db_session,
        multiple_tasks
    ):
        """Test is_ready_to_execute with completed dependencies"""
        # Set first task as completed
        multiple_tasks[0].status = TaskStatus.COMPLETED

        # Create second task depending on first
        task = Task(
            title="Dependent Task",
            task_type="coding",
            status=TaskStatus.PENDING,
            priority=5
        )
        db_session.add(task)
        db_session.commit()

        # Add dependency
        dependency = TaskDependency(
            task_id=task.id,
            depends_on_task_id=multiple_tasks[0].id
        )
        db_session.add(dependency)
        db_session.commit()
        db_session.refresh(task)

        assert task.is_ready_to_execute() is True

    def test_is_ready_to_execute_with_pending_dependencies(
        self,
        db_session,
        multiple_tasks
    ):
        """Test is_ready_to_execute with pending dependencies"""
        # First task is pending
        multiple_tasks[0].status = TaskStatus.PENDING

        # Create second task depending on first
        task = Task(
            title="Dependent Task",
            task_type="coding",
            status=TaskStatus.PENDING,
            priority=5
        )
        db_session.add(task)
        db_session.commit()

        # Add dependency
        dependency = TaskDependency(
            task_id=task.id,
            depends_on_task_id=multiple_tasks[0].id
        )
        db_session.add(dependency)
        db_session.commit()
        db_session.refresh(task)

        assert task.is_ready_to_execute() is False


@pytest.mark.integration
@pytest.mark.database
class TestAgentDatabaseOperations:
    """Integration tests for Agent model database operations"""

    def test_create_agent(self, db_session):
        """Test creating an agent in the database"""
        agent = Agent(
            name="Test Agent",
            role=AgentRole.CODER,
            description="Test agent description",
            status=AgentStatus.IDLE,
            llm_provider="openai",
            temperature=0.7
        )

        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        assert agent.id is not None
        assert agent.name == "Test Agent"
        assert agent.role == AgentRole.CODER
        assert agent.status == AgentStatus.IDLE

    def test_unique_agent_name_constraint(self, db_session, sample_agent):
        """Test that agent names must be unique"""
        duplicate_agent = Agent(
            name=sample_agent.name,  # Same name
            role=AgentRole.REVIEWER,
            status=AgentStatus.IDLE
        )

        db_session.add(duplicate_agent)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_update_agent_status(self, db_session, sample_agent):
        """Test updating agent status"""
        sample_agent.status = AgentStatus.BUSY
        db_session.commit()
        db_session.refresh(sample_agent)

        assert sample_agent.status == AgentStatus.BUSY

    def test_agent_tasks_relationship(self, db_session, sample_agent):
        """Test agent-tasks relationship"""
        # Create multiple tasks for the agent
        task1 = Task(
            title="Task 1",
            task_type="coding",
            status=TaskStatus.PENDING,
            assigned_agent_id=sample_agent.id
        )
        task2 = Task(
            title="Task 2",
            task_type="coding",
            status=TaskStatus.IN_PROGRESS,
            assigned_agent_id=sample_agent.id
        )

        db_session.add(task1)
        db_session.add(task2)
        db_session.commit()
        db_session.refresh(sample_agent)

        assert len(sample_agent.tasks) >= 2
        task_titles = [task.title for task in sample_agent.tasks]
        assert "Task 1" in task_titles
        assert "Task 2" in task_titles

    def test_query_agents_by_role(self, db_session, multiple_agents):
        """Test querying agents by role"""
        coder_agents = db_session.query(Agent).filter_by(
            role=AgentRole.CODER
        ).all()

        assert len(coder_agents) >= 1
        assert all(agent.role == AgentRole.CODER for agent in coder_agents)

    def test_query_available_agents(self, db_session, multiple_agents):
        """Test querying available (idle) agents"""
        # Set some agents to idle
        for agent in multiple_agents[:2]:
            agent.status = AgentStatus.IDLE
        db_session.commit()

        available_agents = db_session.query(Agent).filter_by(
            status=AgentStatus.IDLE
        ).all()

        assert len(available_agents) >= 2
        assert all(agent.status == AgentStatus.IDLE for agent in available_agents)


@pytest.mark.integration
@pytest.mark.database
class TestTaskDependencies:
    """Integration tests for task dependencies"""

    def test_create_task_dependency(self, db_session, multiple_tasks):
        """Test creating a task dependency"""
        dependency = TaskDependency(
            task_id=multiple_tasks[1].id,
            depends_on_task_id=multiple_tasks[0].id
        )

        db_session.add(dependency)
        db_session.commit()
        db_session.refresh(dependency)

        assert dependency.id is not None
        assert dependency.task_id == multiple_tasks[1].id
        assert dependency.depends_on_task_id == multiple_tasks[0].id

    def test_task_dependencies_relationship(self, db_session, multiple_tasks):
        """Test task dependencies relationship"""
        # Create dependency: task2 depends on task1
        dependency = TaskDependency(
            task_id=multiple_tasks[1].id,
            depends_on_task_id=multiple_tasks[0].id
        )
        db_session.add(dependency)
        db_session.commit()

        # Refresh task to load relationships
        db_session.refresh(multiple_tasks[1])

        assert len(multiple_tasks[1].dependencies) >= 1
        dependency_ids = [dep.depends_on_task_id for dep in multiple_tasks[1].dependencies]
        assert multiple_tasks[0].id in dependency_ids

    def test_multiple_dependencies(self, db_session, multiple_tasks):
        """Test task with multiple dependencies"""
        # Task 2 depends on both Task 0 and Task 1
        dep1 = TaskDependency(
            task_id=multiple_tasks[2].id,
            depends_on_task_id=multiple_tasks[0].id
        )
        dep2 = TaskDependency(
            task_id=multiple_tasks[2].id,
            depends_on_task_id=multiple_tasks[1].id
        )

        db_session.add(dep1)
        db_session.add(dep2)
        db_session.commit()

        db_session.refresh(multiple_tasks[2])

        assert len(multiple_tasks[2].dependencies) == 2

    def test_delete_task_cascades_dependencies(self, db_session, multiple_tasks):
        """Test that deleting a task cascades to its dependencies"""
        # Create dependency
        dependency = TaskDependency(
            task_id=multiple_tasks[1].id,
            depends_on_task_id=multiple_tasks[0].id
        )
        db_session.add(dependency)
        db_session.commit()

        dependency_id = dependency.id
        task_id = multiple_tasks[1].id

        # Delete the task
        db_session.delete(multiple_tasks[1])
        db_session.commit()

        # Check that dependency was also deleted
        deleted_dependency = db_session.query(TaskDependency).filter_by(
            id=dependency_id
        ).first()

        assert deleted_dependency is None


@pytest.mark.integration
@pytest.mark.database
class TestDatabaseTransactions:
    """Integration tests for database transactions"""

    def test_rollback_on_error(self, db_session):
        """Test that changes are rolled back on error"""
        # Create a task
        task = Task(
            title="Test Task",
            task_type="coding",
            status=TaskStatus.PENDING,
            priority=5
        )
        db_session.add(task)

        # Trigger an error before commit
        with pytest.raises(IntegrityError):
            # Try to create a task with NULL title (not allowed)
            invalid_task = Task(
                title=None,
                task_type="coding"
            )
            db_session.add(invalid_task)
            db_session.commit()

        db_session.rollback()

        # Original task should not be in database
        tasks = db_session.query(Task).filter_by(title="Test Task").all()
        assert len(tasks) == 0

    def test_commit_on_success(self, db_session, sample_agent):
        """Test that changes persist after commit"""
        task = Task(
            title="Persistent Task",
            task_type="coding",
            status=TaskStatus.PENDING,
            priority=5,
            assigned_agent_id=sample_agent.id
        )

        db_session.add(task)
        db_session.commit()

        # Query in new transaction
        db_session.expire_all()
        persisted_task = db_session.query(Task).filter_by(
            title="Persistent Task"
        ).first()

        assert persisted_task is not None
        assert persisted_task.title == "Persistent Task"
