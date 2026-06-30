"""
Agent Worker - Handles agent lifecycle and status management
"""

from celery import shared_task
from datetime import datetime
from typing import Dict, Any, List

from src.core.database import DatabaseManager
from src.models import Agent, AgentRole, AgentStatus


@shared_task(name='agent_worker.create_agent')
def create_agent(
    name: str,
    role: str,
    description: str = None,
    llm_provider: str = "openai",
    llm_model: str = None,
    system_prompt: str = None
) -> Dict[str, Any]:
    """
    Create a new agent

    Args:
        name: Agent name
        role: Agent role (researcher, coder, reviewer, tester, writer, coordinator)
        description: Agent description
        llm_provider: LLM provider (openai, anthropic)
        llm_model: Specific model to use
        system_prompt: Custom system prompt

    Returns:
        dict: Created agent information
    """
    db_manager = DatabaseManager()

    try:
        with db_manager.session_scope() as session:
            # Check if agent with same name already exists
            existing = session.query(Agent).filter(Agent.name == name).first()
            if existing:
                return {
                    'success': False,
                    'error': f'Agent with name {name} already exists'
                }

            agent = Agent(
                name=name,
                role=AgentRole(role),
                description=description,
                status=AgentStatus.IDLE,
                llm_provider=llm_provider,
                llm_model=llm_model,
                system_prompt=system_prompt,
                is_active=True
            )
            session.add(agent)
            session.flush()

            agent_id = agent.id

            return {
                'success': True,
                'agent_id': agent_id,
                'name': name,
                'role': role,
                'status': AgentStatus.IDLE.value
            }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


@shared_task(name='agent_worker.update_agent_status')
def update_agent_status(agent_id: int, status: str, current_task_id: int = None) -> Dict[str, Any]:
    """
    Update agent status

    Args:
        agent_id: Agent ID
        status: New status
        current_task_id: Current task being worked on

    Returns:
        dict: Update result
    """
    db_manager = DatabaseManager()

    try:
        with db_manager.session_scope() as session:
            agent = session.query(Agent).filter(Agent.id == agent_id).first()

            if not agent:
                return {
                    'success': False,
                    'error': f'Agent {agent_id} not found'
                }

            agent.status = AgentStatus(status)
            agent.current_task_id = current_task_id
            agent.last_active_at = datetime.utcnow()

            return {
                'success': True,
                'agent_id': agent_id,
                'status': status
            }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


@shared_task(name='agent_worker.get_available_agents')
def get_available_agents(role: str = None) -> List[Dict[str, Any]]:
    """
    Get list of available agents

    Args:
        role: Optional role filter

    Returns:
        list: Available agents
    """
    db_manager = DatabaseManager()

    try:
        with db_manager.session_scope() as session:
            query = session.query(Agent).filter(
                Agent.is_active == True,
                Agent.status == AgentStatus.IDLE
            )

            if role:
                query = query.filter(Agent.role == AgentRole(role))

            agents = query.all()

            return [
                {
                    'id': agent.id,
                    'name': agent.name,
                    'role': agent.role.value,
                    'status': agent.status.value
                }
                for agent in agents
            ]

    except Exception as e:
        return []


@shared_task(name='agent_worker.assign_task_to_agent')
def assign_task_to_agent(agent_id: int, task_id: int) -> Dict[str, Any]:
    """
    Assign a task to an agent

    Args:
        agent_id: Agent ID
        task_id: Task ID

    Returns:
        dict: Assignment result
    """
    db_manager = DatabaseManager()

    try:
        with db_manager.session_scope() as session:
            from src.models import Task

            agent = session.query(Agent).filter(Agent.id == agent_id).first()
            task = session.query(Task).filter(Task.id == task_id).first()

            if not agent:
                return {'success': False, 'error': f'Agent {agent_id} not found'}

            if not task:
                return {'success': False, 'error': f'Task {task_id} not found'}

            if not agent.is_available():
                return {'success': False, 'error': f'Agent {agent.name} is not available'}

            # Assign task
            task.assigned_agent_id = agent_id
            agent.current_task_id = task_id
            agent.status = AgentStatus.BUSY

            return {
                'success': True,
                'agent_id': agent_id,
                'task_id': task_id,
                'message': f'Task {task_id} assigned to agent {agent.name}'
            }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
