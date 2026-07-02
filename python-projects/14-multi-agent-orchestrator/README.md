# Project 14: Multi-Agent Task Orchestrator

[![CI - Tests and Coverage](https://github.com/yourusername/ai-experiments-hub/actions/workflows/ci.yml/badge.svg)](https://github.com/yourusername/ai-experiments-hub/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An advanced AI-powered system that coordinates multiple specialized agents to autonomously break down, execute, and monitor complex tasks using LangGraph.

## Overview

This system demonstrates sophisticated multi-agent coordination where specialized AI agents work together to accomplish complex tasks:

- **Researcher Agent**: Gathers information and context
- **Coder Agent**: Implements solutions and writes code
- **Reviewer Agent**: Reviews code quality and suggests improvements
- **Tester Agent**: Creates and runs tests
- **Writer Agent**: Generates documentation

## Architecture

- **Framework**: LangGraph for agent orchestration with DAG-based workflows
- **Backend**: FastAPI + Celery + Redis
- **Database**: PostgreSQL with SQLAlchemy ORM
- **AI Models**: OpenAI GPT-4 / Anthropic Claude
- **Real-time**: WebSocket for live progress monitoring

## Features

- Multi-agent task decomposition and execution
- DAG-based workflow orchestration
- Shared memory and context across agents
- Human-in-the-loop approval gates
- Real-time progress monitoring
- Cost tracking and optimization
- Agent performance analytics

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- Redis 7+
- OpenAI or Anthropic API key

### Installation

#### Option 1: Docker (Recommended)

1. Configure environment:
```bash
cd python-projects/14-multi-agent-orchestrator
cp .env.example .env
# Edit .env with your API keys and settings
```

2. Build and start services:
```bash
make build
make up
```

3. View logs:
```bash
make logs
```

4. Access the application:
- API: http://localhost:8001
- PostgreSQL: localhost:5432
- Redis: localhost:6379

#### Option 2: Local Development

1. Install dependencies:
```bash
cd python-projects/14-multi-agent-orchestrator
pip install -r requirements.txt
```

2. Start PostgreSQL and Redis locally

3. Configure environment:
```bash
cp .env.example .env
# Edit .env with your settings
```

4. Initialize database:
```bash
alembic upgrade head
```

5. Start services:
```bash
# Terminal 1: Start Celery worker
celery -A celery_app worker --loglevel=info

# Terminal 2: Start Celery Beat
celery -A celery_app beat --loglevel=info

# Terminal 3: Start FastAPI server
python server.py
```

### Docker Commands

- `make build` - Build Docker images
- `make up` - Start all services
- `make down` - Stop all services
- `make restart` - Restart services
- `make logs` - View logs
- `make shell` - Open app container shell
- `make db-shell` - Open PostgreSQL shell
- `make redis-shell` - Open Redis CLI
- `make clean` - Remove containers and volumes

## Authentication

The system uses JWT (JSON Web Tokens) for authentication and role-based access control.

### Default Users

After running `python scripts/init_db.py`, three default users are created:

| Username | Password | Role | Permissions |
|----------|----------|------|-------------|
| admin | admin123 | ADMIN | Full access, can manage agents |
| user | user123 | USER | Can create and manage tasks |
| viewer | viewer123 | VIEWER | Read-only access |

**⚠️ Change these passwords in production!**

### Authentication Flow

1. **Register** (optional): Create a new user account
2. **Login**: Get access and refresh tokens
3. **Use Token**: Include token in `Authorization: Bearer <token>` header
4. **Refresh**: Get new access token using refresh token

### API Examples

**Register a new user:**
```bash
curl -X POST http://localhost:8001/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "newuser",
    "email": "new@example.com",
    "password": "securepass123",
    "full_name": "New User"
  }'
```

**Login:**
```bash
curl -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "admin123"
  }'

# Response:
# {
#   "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
#   "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
#   "token_type": "bearer"
# }
```

**Get current user info:**
```bash
curl http://localhost:8001/api/auth/me \
  -H "Authorization: Bearer <access_token>"
```

**Use authenticated endpoint:**
```bash
# Create a task (requires authentication)
curl -X POST http://localhost:8001/api/tasks \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "My Task",
    "description": "Task description",
    "task_type": "coding",
    "priority": 5
  }'
```

**Refresh token:**
```bash
curl -X POST http://localhost:8001/api/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{
    "refresh_token": "<refresh_token>"
  }'
```

**Change password:**
```bash
curl -X POST http://localhost:8001/api/auth/change-password \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "current_password": "admin123",
    "new_password": "newsecurepass123"
  }'
```

### Role-Based Access Control

- **VIEWER**: Read-only access to tasks and agents
- **USER**: Can create and manage own tasks
- **ADMIN**: Full access, can manage agents and all tasks

### Environment Variables

Configure JWT settings in `.env`:

```bash
# JWT Configuration
JWT_SECRET_KEY=your-secret-key-change-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7
```

## Workflows

The system uses LangGraph to orchestrate multi-agent workflows with DAG-based execution.

### Workflow Types

**1. Simple Workflow** (Quick execution)
```
research → code → document
```

**2. Default Workflow** (Complete pipeline)
```
research → code → review → test → document
```

**3. Custom Workflow** (User-defined)
- Define your own nodes and edges
- Flexible routing and conditional logic

### Workflow Nodes

| Node | Agent | Purpose |
|------|-------|---------|
| **research** | Researcher | Gather information and context |
| **code** | Coder | Implement solutions and write code |
| **review** | Reviewer | Review code quality and suggest improvements |
| **test** | Tester | Create and run tests |
| **document** | Writer | Generate documentation |

### Execute a Workflow

**Simple workflow example:**
```bash
curl -X POST http://localhost:8001/api/workflows/execute \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 1,
    "task_title": "Build REST API",
    "task_description": "Build a REST API with FastAPI and PostgreSQL",
    "task_type": "coding",
    "priority": 7,
    "workflow_type": "simple",
    "input_data": {
      "framework": "FastAPI",
      "database": "PostgreSQL"
    }
  }'
```

**Response:**
```json
{
  "task_id": 1,
  "status": "completed",
  "progress": 100,
  "workflow_path": ["start", "research", "code", "document"],
  "total_tokens": 2100,
  "total_cost": 0.042,
  "execution_time": 5.2,
  "messages": [
    {
      "role": "assistant",
      "content": "Research completed: Research completed successfully"
    },
    {
      "role": "assistant",
      "content": "Code implementation completed: 50 lines"
    },
    {
      "role": "assistant",
      "content": "Documentation completed: 500 words"
    }
  ],
  "outputs": {
    "research": {
      "findings": "Research findings for: Build a REST API...",
      "sources": ["source1", "source2"],
      "summary": "Research completed successfully",
      "confidence": 0.85
    },
    "code": {
      "code": "# Implementation based on research...",
      "language": "python",
      "files_created": ["main.py"],
      "lines_of_code": 50
    },
    "document": {
      "documentation": "# Build REST API\n\n## Overview...",
      "sections": ["Overview", "Usage", "API Reference"],
      "word_count": 500
    }
  }
}
```

### Custom Workflow

Create a workflow with specific nodes:

```bash
curl -X POST http://localhost:8001/api/workflows/execute/custom \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 2,
    "task_title": "Quick Prototype",
    "task_description": "Create a quick prototype",
    "nodes": ["research", "code", "test"],
    "edges": [
      ["research", "code"],
      ["code", "test"],
      ["test", "END"]
    ],
    "input_data": {
      "prototype": true
    }
  }'
```

### List Available Workflows

```bash
curl http://localhost:8001/api/workflows/workflows \
  -H "Authorization: Bearer <access_token>"
```

**Response:**
```json
[
  {
    "type": "default",
    "description": "Complete workflow with all nodes and routing",
    "nodes": ["research", "code", "review", "test", "document", "approval"]
  },
  {
    "type": "simple",
    "description": "Simple linear workflow for quick execution",
    "nodes": ["research", "code", "document"]
  },
  {
    "type": "custom",
    "description": "Custom workflow with user-defined nodes and edges",
    "nodes": "variable"
  }
]
```

### Workflow State

Each workflow maintains state that includes:
- **Task information**: ID, title, description, type, priority
- **Execution tracking**: Current node, path, progress
- **Node outputs**: Results from each executed node
- **Cost tracking**: Total tokens used and cost
- **Messages**: Conversation history
- **Logs**: Execution logs

### Python SDK Example

```python
import requests

BASE_URL = "http://localhost:8001/api"
headers = {"Authorization": f"Bearer {access_token}"}

# Execute simple workflow
response = requests.post(
    f"{BASE_URL}/workflows/execute",
    headers=headers,
    json={
        "task_id": 1,
        "task_title": "Implement feature X",
        "task_description": "Add authentication to the API",
        "task_type": "coding",
        "priority": 8,
        "workflow_type": "simple"
    }
)

result = response.json()
print(f"Workflow status: {result['status']}")
print(f"Progress: {result['progress']}%")
print(f"Total cost: ${result['total_cost']:.4f}")
print(f"Execution time: {result['execution_time']}s")

# Access outputs
research = result['outputs']['research']
code = result['outputs']['code']
print(f"Research summary: {research['summary']}")
print(f"Lines of code: {code['lines_of_code']}")
```

### Workflow Features

- **DAG-based execution**: Directed acyclic graph ensures proper task ordering
- **State management**: Shared state across all nodes
- **Cost tracking**: Monitor LLM token usage and costs
- **Progress tracking**: Real-time progress updates
- **Error handling**: Built-in error handling and recovery
- **Flexible routing**: Conditional edges based on state
- **Human-in-the-loop**: Approval gates for critical decisions

## Service Layer

The system uses a service layer to abstract business logic and database operations, making the code more maintainable and testable.

### Architecture

```
API Layer (FastAPI)
    ↓
Service Layer (Business Logic)
    ↓
Database Layer (SQLAlchemy ORM)
```

### Available Services

**AgentService** - Agent lifecycle management
- `create_agent()` - Create a new agent
- `get_agent_by_id()` - Retrieve agent by ID
- `get_agents_by_role()` - Get agents by role
- `get_available_agents()` - Get idle agents
- `assign_agent_to_task()` - Assign agent to task
- `update_agent_status()` - Update agent status
- `update_agent_metrics()` - Track performance metrics
- `find_best_agent_for_role()` - Auto-select best agent
- `deactivate_agent()` - Deactivate an agent

**TaskService** - Task orchestration and execution
- `create_task()` - Create a new task
- `get_task_by_id()` - Retrieve task by ID
- `update_task_status()` - Update task status
- `assign_task_to_agent()` - Assign to specific agent
- `auto_assign_task()` - Auto-assign to best agent
- `add_task_dependency()` - Add task dependency
- `get_ready_tasks()` - Get tasks ready to execute
- `execute_task_with_workflow()` - Execute via workflow
- `cancel_task()` - Cancel a task

**WorkflowService** - Workflow execution
- `execute_workflow()` - Execute predefined workflow
- `execute_custom_workflow()` - Execute custom workflow
- `get_workflow_info()` - Get workflow details
- `list_workflows()` - List available workflows

### Usage Examples

#### Using AgentService

```python
from sqlalchemy.orm import Session
from src.core.database import get_db_session
from src.services import AgentService
from src.models import AgentRole

# Create session
with get_db_session() as session:
    # Create a new agent
    agent = AgentService.create_agent(
        session=session,
        name="Code Master",
        role=AgentRole.CODER,
        description="Expert Python developer",
        llm_provider="openai",
        llm_model="gpt-4-turbo-preview",
        temperature=0.3
    )
    print(f"Created agent: {agent.id}")

    # Get available agents for a role
    coders = AgentService.get_available_agents(
        session=session,
        role=AgentRole.CODER
    )
    print(f"Found {len(coders)} available coders")

    # Find best agent for a role (auto-selection)
    best_agent = AgentService.find_best_agent_for_role(
        session=session,
        role=AgentRole.CODER
    )
    print(f"Best agent: {best_agent.name}")

    # Get agent metrics
    metrics = AgentService.get_agent_metrics(session, agent.id)
    print(f"Success rate: {metrics['success_rate']}%")
    print(f"Total cost: ${metrics['total_cost']:.2f}")
```

#### Using TaskService

```python
from src.services import TaskService, AgentService
from src.models import AgentRole

with get_db_session() as session:
    # Create a new task
    task = TaskService.create_task(
        session=session,
        title="Build Authentication API",
        description="Implement JWT-based auth with FastAPI",
        task_type="coding",
        priority=8,
        input_data={"framework": "FastAPI", "auth_type": "JWT"}
    )
    print(f"Created task: {task.id}")

    # Auto-assign task to best available agent
    task = TaskService.auto_assign_task(
        session=session,
        task_id=task.id,
        required_role=AgentRole.CODER
    )
    print(f"Assigned to agent: {task.assigned_agent_id}")

    # Execute task with workflow
    result = TaskService.execute_task_with_workflow(
        session=session,
        task_id=task.id,
        workflow_type="simple"
    )
    print(f"Task status: {result['status']}")
    print(f"Workflow result: {result['workflow_result']}")

    # Check task progress
    task = TaskService.get_task_by_id(session, task.id)
    print(f"Progress: {task.progress_percentage}%")
    print(f"Status: {task.status.value}")
```

#### Managing Task Dependencies

```python
from src.services import TaskService

with get_db_session() as session:
    # Create dependent tasks
    research_task = TaskService.create_task(
        session=session,
        title="Research authentication methods",
        description="Compare JWT vs OAuth",
        task_type="research",
        priority=9
    )

    coding_task = TaskService.create_task(
        session=session,
        title="Implement authentication",
        description="Build JWT authentication",
        task_type="coding",
        priority=8
    )

    # Add dependency: coding depends on research
    TaskService.add_task_dependency(
        session=session,
        task_id=coding_task.id,
        depends_on_task_id=research_task.id,
        dependency_type="completion",
        is_blocking=True
    )

    # Get tasks ready to execute
    ready_tasks = TaskService.get_ready_tasks(session, limit=10)
    print(f"Ready tasks: {[t.title for t in ready_tasks]}")
    # Output: ["Research authentication methods"]
    # (coding_task is not ready until research_task completes)
```

#### Workflow Execution with Services

```python
from src.services import TaskService, WorkflowService

with get_db_session() as session:
    # Create task
    task = TaskService.create_task(
        session=session,
        title="Build user management API",
        description="CRUD endpoints for users",
        task_type="coding",
        priority=7
    )

    # Auto-assign to best agent
    task = TaskService.auto_assign_task(session, task.id)

    # Execute with default workflow (research → code → review → test → document)
    result = TaskService.execute_task_with_workflow(
        session=session,
        task_id=task.id,
        workflow_type="default"
    )

    # Check results
    workflow_state = result['workflow_result']
    print(f"Status: {workflow_state['status']}")
    print(f"Total cost: ${workflow_state['total_cost']:.4f}")
    print(f"Tokens used: {workflow_state['total_tokens']}")
    print(f"Execution time: {workflow_state['execution_time']}s")

    # Access node outputs
    research = workflow_state.get('research_output', {})
    code = workflow_state.get('code_output', {})
    print(f"Research summary: {research.get('summary')}")
    print(f"Code files: {code.get('files_created')}")
```

### Service Layer Benefits

- **Separation of Concerns**: Business logic isolated from API layer
- **Testability**: Services can be tested independently
- **Reusability**: Service methods used by API, Celery workers, and scripts
- **Transaction Management**: Database transactions handled at service level
- **Error Handling**: Consistent error handling across the application
- **Validation**: Input validation before database operations

## Real-Time Notifications with WebSockets

The system provides WebSocket endpoints for real-time updates on tasks, agents, and workflows.

### WebSocket Endpoints

**1. General WebSocket** - Subscribe to all updates
```
ws://localhost:8001/api/ws?token=<access_token>
```

**2. Task-Specific WebSocket** - Updates for a specific task
```
ws://localhost:8001/api/ws/tasks/{task_id}?token=<access_token>
```

**3. Agent-Specific WebSocket** - Updates for a specific agent
```
ws://localhost:8001/api/ws/agents/{agent_id}?token=<access_token>
```

### Event Types

**Task Events:**
- `created` - Task created
- `status_changed` - Task status updated
- `assigned` - Task assigned to agent
- `progress` - Workflow progress update

**Agent Events:**
- `status_changed` - Agent status updated
- `assigned` - Agent assigned to task
- `metrics_updated` - Performance metrics updated

**Workflow Events:**
- `progress` - Node transition in workflow
- `completed` - Workflow completed
- `failed` - Workflow failed

### Message Format

All WebSocket messages follow this format:

```json
{
  "timestamp": "2024-01-15T10:30:00.000Z",
  "data": {
    "type": "task_update",
    "event": "status_changed",
    "task_id": 123,
    "status": "in_progress",
    "progress": 45
  }
}
```

### JavaScript Client Example

```javascript
// Connect to WebSocket
const token = "your_access_token";
const ws = new WebSocket(`ws://localhost:8001/api/ws?token=${token}`);

ws.onopen = () => {
  console.log("WebSocket connected");

  // Subscribe to specific task updates
  ws.send(JSON.stringify({
    type: "subscribe",
    room: "task_123"
  }));

  // Subscribe to all agent updates
  ws.send(JSON.stringify({
    type: "subscribe",
    room: "agents"
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log("Received:", message);

  // Handle different event types
  if (message.data.type === "task_update") {
    if (message.data.event === "status_changed") {
      console.log(`Task ${message.data.task_id} is now ${message.data.status}`);
      updateTaskUI(message.data.task_id, message.data.status);
    } else if (message.data.event === "progress") {
      console.log(`Task ${message.data.task_id} progress: ${message.data.progress}%`);
      updateProgressBar(message.data.task_id, message.data.progress);
    }
  } else if (message.data.type === "agent_update") {
    if (message.data.event === "assigned") {
      console.log(`Agent ${message.data.agent_id} assigned to task ${message.data.task_id}`);
      updateAgentStatus(message.data.agent_id, "busy");
    }
  }
};

ws.onerror = (error) => {
  console.error("WebSocket error:", error);
};

ws.onclose = () => {
  console.log("WebSocket disconnected");
};

// Send heartbeat every 30 seconds
setInterval(() => {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: "ping",
      timestamp: new Date().toISOString()
    }));
  }
}, 30000);

// Unsubscribe from a room
function unsubscribe(room) {
  ws.send(JSON.stringify({
    type: "unsubscribe",
    room: room
  }));
}
```

### Python Client Example

```python
import asyncio
import websockets
import json

async def connect_websocket():
    """Connect to WebSocket and receive real-time updates"""
    token = "your_access_token"
    uri = f"ws://localhost:8001/api/ws?token={token}"

    async with websockets.connect(uri) as websocket:
        print("WebSocket connected")

        # Subscribe to task updates
        await websocket.send(json.dumps({
            "type": "subscribe",
            "room": "tasks"
        }))

        # Subscribe to specific task
        await websocket.send(json.dumps({
            "type": "subscribe",
            "room": "task_123"
        }))

        # Listen for messages
        async for message in websocket:
            data = json.loads(message)
            print(f"Received: {data}")

            # Handle events
            if data.get("data", {}).get("type") == "task_update":
                event = data["data"]["event"]
                task_id = data["data"]["task_id"]

                if event == "status_changed":
                    status = data["data"]["status"]
                    print(f"Task {task_id} status: {status}")

                elif event == "progress":
                    progress = data["data"]["progress"]
                    print(f"Task {task_id} progress: {progress}%")

# Run WebSocket client
asyncio.run(connect_websocket())
```

### Task-Specific WebSocket Example

```python
import asyncio
import websockets
import json

async def monitor_task(task_id: int):
    """Monitor a specific task's progress in real-time"""
    token = "your_access_token"
    uri = f"ws://localhost:8001/api/ws/tasks/{task_id}?token={token}"

    async with websockets.connect(uri) as websocket:
        print(f"Connected to task {task_id} updates")

        async for message in websocket:
            data = json.loads(message)

            if data.get("data", {}).get("event") == "progress":
                node = data["data"].get("node")
                progress = data["data"].get("progress")
                print(f"Task {task_id} at node '{node}': {progress}%")

            elif data.get("data", {}).get("event") == "status_changed":
                status = data["data"]["status"]
                print(f"Task {task_id} completed with status: {status}")

                if status in ["completed", "failed", "cancelled"]:
                    break

# Monitor task execution
asyncio.run(monitor_task(123))
```

### Subscription Rooms

You can subscribe to different "rooms" to receive targeted updates:

| Room | Description |
|------|-------------|
| `tasks` | All task updates |
| `task_{id}` | Specific task updates |
| `agents` | All agent updates |
| `agent_{id}` | Specific agent updates |
| `workflows` | All workflow updates |

### WebSocket Commands

Send these commands to control your subscription:

```javascript
// Subscribe to a room
ws.send(JSON.stringify({
  type: "subscribe",
  room: "task_123"
}));

// Unsubscribe from a room
ws.send(JSON.stringify({
  type: "unsubscribe",
  room: "task_123"
}));

// Ping/heartbeat
ws.send(JSON.stringify({
  type: "ping",
  timestamp: new Date().toISOString()
}));

// Get connection statistics
ws.send(JSON.stringify({
  type: "get_stats"
}));
```

### Integration with Services

The WebSocket notifications are automatically sent when using services:

```python
from src.services import TaskService, AgentService
from src.core.database import get_db_session

# Task updates automatically trigger WebSocket notifications
with get_db_session() as session:
    # Creating a task sends "task_update.created" notification
    task = TaskService.create_task(
        session=session,
        title="Build API",
        description="Create REST API endpoints",
        task_type="coding",
        priority=7
    )
    # WebSocket notification sent: {"type": "task_update", "event": "created", ...}

    # Status changes send "task_update.status_changed" notification
    TaskService.update_task_status(session, task.id, TaskStatus.IN_PROGRESS)
    # WebSocket notification sent: {"type": "task_update", "event": "status_changed", ...}

    # Agent status changes send "agent_update.status_changed" notification
    AgentService.update_agent_status(session, agent_id=1, status=AgentStatus.BUSY)
    # WebSocket notification sent: {"type": "agent_update", "event": "status_changed", ...}
```

### Connection Statistics

Get real-time statistics about active WebSocket connections:

```bash
curl http://localhost:8001/api/ws/stats

# Response:
# {
#   "total_connections": 15,
#   "total_rooms": 8,
#   "total_users": 5,
#   "rooms": {
#     "tasks": 10,
#     "task_123": 3,
#     "agents": 5,
#     "agent_1": 2
#   }
# }
```

## Background Task Scheduler

The system uses Celery Beat for scheduling periodic background tasks that monitor system health, clean up old data, and maintain optimal performance.

### Scheduled Tasks

| Task | Schedule | Description |
|------|----------|-------------|
| **monitor_queue_health** | Every 5 minutes | Monitor Celery queue health and task distribution |
| **check_stalled_tasks** | Every 2 minutes | Find and fail tasks stuck in progress for >1 hour |
| **update_agent_metrics** | Every 10 minutes | Update agent performance metrics |
| **process_pending_tasks** | Every 3 minutes | Auto-assign pending tasks to available agents |
| **check_agent_health** | Every 15 minutes | Mark inactive agents as offline |
| **cleanup_completed_tasks** | Daily at 2 AM UTC | Delete tasks completed >30 days ago |
| **generate_daily_report** | Daily at 9 AM UTC | Generate daily performance statistics |

### Task Details

#### monitor_queue_health
Monitors Celery queue health and worker status:
```python
{
    "success": True,
    "timestamp": "2024-01-15T10:00:00Z",
    "active_tasks": 5,
    "scheduled_tasks": 2,
    "reserved_tasks": 1
}
```

#### check_stalled_tasks
Automatically marks tasks as failed if they've been running for more than 1 hour:
- Updates task status to FAILED
- Sets error message: "Task stalled - exceeded timeout"
- Sends WebSocket notification to subscribers
- Returns stalled task IDs for monitoring

#### update_agent_metrics
Aggregates agent status across the system:
```python
{
    "success": True,
    "timestamp": "2024-01-15T10:00:00Z",
    "metrics": {
        "total_agents": 10,
        "idle_agents": 6,
        "busy_agents": 3,
        "error_agents": 0,
        "offline_agents": 1
    }
}
```

#### process_pending_tasks
Auto-assigns ready tasks to best available agents:
- Gets tasks with satisfied dependencies
- Uses `find_best_agent_for_role()` for smart assignment
- Considers agent success rate and load balancing
- Processes up to 20 tasks per run

#### check_agent_health
Monitors agent responsiveness:
- Marks agents as OFFLINE if inactive for >30 minutes
- Clears current task assignments
- Prevents resource leaks from crashed agents

#### cleanup_completed_tasks
Removes old completed tasks:
- Default: Delete tasks older than 30 days
- Only removes COMPLETED, FAILED, and CANCELLED tasks
- Configurable retention period
- Prevents database bloat

#### generate_daily_report
Creates daily performance summary:
```python
{
    "success": True,
    "date": "2024-01-14",
    "tasks": {
        "total": 150,
        "completed": 142,
        "failed": 8,
        "success_rate": 94.67
    },
    "agents": {
        "total": 10,
        "active": 9
    }
}
```

### Running Celery Beat

**Development:**
```bash
# Start Celery Beat scheduler
celery -A celery_app beat --loglevel=info

# Or use Makefile
make celery-beat
```

**Production (Docker):**
```yaml
# Already configured in docker-compose.yml
services:
  beat:
    command: celery -A celery_app beat --loglevel=info
```

### Monitoring Scheduled Tasks

**Check scheduled tasks:**
```bash
# List all scheduled tasks
celery -A celery_app inspect scheduled

# Check active periodic tasks
celery -A celery_app inspect active
```

**View task results:**
```python
from celery.result import AsyncResult
from celery_app import celery_app

# Get task result
result = AsyncResult('task-id', app=celery_app)
print(result.state)  # SUCCESS, FAILURE, PENDING
print(result.result)  # Task return value
```

### Custom Scheduling

Add custom periodic tasks in [celery_app.py](celery_app.py):

```python
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    # Run every Monday at 8 AM
    'weekly-cleanup': {
        'task': 'src.workers.monitoring_worker.custom_task',
        'schedule': crontab(hour=8, minute=0, day_of_week=1),
    },

    # Run every 30 seconds
    'frequent-check': {
        'task': 'src.workers.monitoring_worker.another_task',
        'schedule': 30.0,
    },
}
```

### Task Logging

All scheduled tasks log their execution:

```
[2024-01-15 10:00:00,123: INFO] Monitoring queue health...
[2024-01-15 10:00:00,456: INFO] Queue health: 5 active, 2 scheduled, 1 reserved
[2024-01-15 10:02:00,789: INFO] Checking for stalled tasks...
[2024-01-15 10:02:00,890: WARNING] Found 2 stalled tasks: [123, 456]
[2024-01-15 10:03:00,012: INFO] Processing pending tasks...
[2024-01-15 10:03:01,234: INFO] Auto-assigned 5 pending tasks
```

### Disabling Scheduled Tasks

To disable specific tasks, comment them out in `celery_app.py`:

```python
celery_app.conf.beat_schedule = {
    # 'task-to-disable': {
    #     'task': 'src.workers.monitoring_worker.some_task',
    #     'schedule': 300.0,
    # },
}
```

Or use environment variables:

```bash
# Disable Celery Beat entirely
CELERY_BEAT_ENABLED=false

# Custom configuration
CELERY_BEAT_SCHEDULE_FILENAME=/path/to/custom/schedule.py
```

## Error Tracking and Logging System

The system includes a comprehensive error tracking and logging system that monitors, aggregates, and reports errors across the entire application.

### Error Severity Levels

| Severity | Description | Action |
|----------|-------------|--------|
| **LOW** | Minor issues that don't affect functionality | Logged only |
| **MEDIUM** | Issues that may impact performance or UX | Logged and tracked |
| **HIGH** | Critical issues affecting functionality | Logged, tracked, and notified |
| **CRITICAL** | System-breaking errors requiring immediate attention | Logged, tracked, notified, and WebSocket alert |

### Error Categories

The system classifies errors into 8 categories for better organization:

- **TASK_EXECUTION** - Errors during task execution
- **AGENT_ERROR** - Agent-related failures
- **WORKFLOW_ERROR** - Workflow orchestration issues
- **DATABASE_ERROR** - Database operation failures
- **API_ERROR** - HTTP API errors
- **VALIDATION_ERROR** - Input validation failures
- **NETWORK_ERROR** - External API and network issues
- **SYSTEM_ERROR** - General system errors

### Error Fingerprinting

The error tracker uses fingerprinting to deduplicate similar errors:

```python
# Errors are fingerprinted using MD5 hash of:
# - Error type (e.g., ValueError, KeyError)
# - Error message
# - Error category

# Same error occurring multiple times gets single fingerprint
# Tracks occurrence count and last occurrence timestamp
```

### API Endpoints

**Get Error Summary:**
```bash
curl http://localhost:8001/api/errors/summary?hours=24&min_occurrences=1

# Response:
# {
#   "time_period_hours": 24,
#   "total_errors": 15,
#   "unique_errors": 8,
#   "errors_by_severity": {
#     "LOW": 5,
#     "MEDIUM": 7,
#     "HIGH": 2,
#     "CRITICAL": 1
#   },
#   "errors_by_category": {
#     "TASK_EXECUTION": 6,
#     "DATABASE_ERROR": 3,
#     "API_ERROR": 4,
#     "VALIDATION_ERROR": 2
#   },
#   "top_errors": [
#     {
#       "fingerprint": "a1b2c3d4...",
#       "error_type": "TaskExecutionError",
#       "error_message": "Task timeout exceeded",
#       "category": "TASK_EXECUTION",
#       "severity": "HIGH",
#       "count": 8,
#       "last_seen": "2024-01-15T14:30:00Z"
#     }
#   ]
# }
```

**Get Error Details:**
```bash
curl http://localhost:8001/api/errors/details/{fingerprint}

# Response includes:
# - Full error details
# - Stack traces
# - All occurrences
# - Context information
# - Associated tasks/agents
```

**Get Recovery Suggestions:**
```bash
curl http://localhost:8001/api/errors/suggestions/{fingerprint}

# Response:
# {
#   "fingerprint": "a1b2c3d4...",
#   "error_type": "TaskExecutionError",
#   "suggestions": [
#     "Check task timeout configuration",
#     "Review agent resource allocation",
#     "Verify database connection pool"
#   ],
#   "documentation_links": [
#     "https://docs.example.com/task-timeouts"
#   ]
# }
```

**Clear Old Errors:**
```bash
curl -X POST http://localhost:8001/api/errors/clear?hours=48

# Response:
# {
#   "cleared_count": 125,
#   "cutoff_time": "2024-01-13T10:00:00Z"
# }
```

**Get Error Categories:**
```bash
curl http://localhost:8001/api/errors/categories

# Response:
# {
#   "categories": [
#     "TASK_EXECUTION",
#     "AGENT_ERROR",
#     ...
#   ],
#   "severities": [
#     "LOW",
#     "MEDIUM",
#     "HIGH",
#     "CRITICAL"
#   ]
# }
```

**Get Error Statistics:**
```bash
curl http://localhost:8001/api/errors/stats

# Response:
# {
#   "total_errors": 342,
#   "unique_fingerprints": 45,
#   "errors_last_hour": 12,
#   "errors_last_24h": 156,
#   "critical_errors_24h": 3,
#   "most_common_category": "TASK_EXECUTION",
#   "average_errors_per_hour": 6.5
# }
```

### Automatic Error Tracking

Errors are automatically tracked via middleware:

```python
# All API errors are automatically tracked
# No manual error tracking needed in route handlers

@router.post("/api/tasks")
async def create_task(task_data: TaskCreate):
    # If this raises an exception, it's automatically tracked
    task = TaskService.create_task(...)
    return task

# Error is logged with:
# - HTTP method and path
# - Request headers
# - Error type and message
# - Full traceback
# - Automatic severity classification
```

### Manual Error Tracking

Track errors manually in your code:

```python
from src.core.error_tracker import error_tracker, ErrorSeverity, ErrorCategory

try:
    # Some operation
    result = risky_operation()
except Exception as e:
    # Track the error with context
    fingerprint = error_tracker.track_error(
        error=e,
        context={
            "operation": "risky_operation",
            "user_id": 123,
            "input_data": {...}
        },
        severity=ErrorSeverity.HIGH,
        category=ErrorCategory.TASK_EXECUTION,
        task_id=456,
        agent_id=789
    )

    # Handle the error
    logger.error(f"Operation failed with fingerprint: {fingerprint}")
```

### Error Recovery Suggestions

The system provides intelligent recovery suggestions based on error type:

```python
# Example suggestions for common errors:

TaskExecutionError:
  - "Increase task timeout in configuration"
  - "Check agent availability"
  - "Review task dependencies"

DatabaseError:
  - "Check database connection"
  - "Verify connection pool settings"
  - "Review database locks"

ValidationError:
  - "Check input data format"
  - "Review API schema"
  - "Verify required fields"

NetworkError:
  - "Check external API status"
  - "Verify network connectivity"
  - "Review timeout settings"
```

### WebSocket Notifications

High and critical errors trigger real-time WebSocket notifications:

```javascript
// Connect to WebSocket
const ws = new WebSocket(`ws://localhost:8001/api/ws?token=${token}`);

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);

  if (message.data.type === "system_event" &&
      message.data.event === "error_occurred") {

    const error = message.data.error;

    if (error.severity === "CRITICAL") {
      // Show critical error alert
      showCriticalAlert(error);
    } else if (error.severity === "HIGH") {
      // Show high priority notification
      showNotification(error);
    }
  }
};
```

### Error Aggregation

View aggregated error metrics:

```python
from src.core.error_tracker import error_tracker

# Get error summary for last 24 hours
summary = error_tracker.get_error_summary(hours=24, min_occurrences=2)

print(f"Total errors: {summary['total_errors']}")
print(f"Unique errors: {summary['unique_errors']}")

# Errors by severity
for severity, count in summary['errors_by_severity'].items():
    print(f"{severity}: {count}")

# Top errors
for error in summary['top_errors']:
    print(f"{error['error_type']}: {error['count']} occurrences")
```

### Error Logging

All errors are logged with structured data:

```json
{
  "timestamp": "2024-01-15T14:30:00.123Z",
  "level": "ERROR",
  "fingerprint": "a1b2c3d4e5f6...",
  "error_type": "TaskExecutionError",
  "error_message": "Task timeout exceeded",
  "severity": "HIGH",
  "category": "TASK_EXECUTION",
  "context": {
    "task_id": 456,
    "agent_id": 789,
    "timeout": 300
  },
  "traceback": "Traceback (most recent call last):\n  File ...",
  "occurrence_count": 8
}
```

### Monitoring Dashboard Integration

The error tracking system exposes metrics for monitoring dashboards:

```bash
# Prometheus metrics
curl http://localhost:8001/api/metrics

# Includes:
# - error_total{severity="HIGH",category="TASK_EXECUTION"}
# - error_unique_total
# - error_occurrence_rate
```

### Error Retention

Configure error retention policy:

```python
# Clear errors older than 48 hours
from src.core.error_tracker import error_tracker

cleared = error_tracker.clear_old_errors(hours=48)
print(f"Cleared {cleared} old errors")

# Or via API
curl -X POST http://localhost:8001/api/errors/clear?hours=48
```

### Production Best Practices

**1. Set up error alerts:**
```python
# Configure webhooks or email for critical errors
CRITICAL_ERROR_WEBHOOK = "https://hooks.slack.com/..."
ERROR_NOTIFICATION_EMAIL = "ops@example.com"
```

**2. Monitor error rates:**
```bash
# Check error stats regularly
curl http://localhost:8001/api/errors/stats

# Set up alerts for error spikes
# Alert if errors_last_hour > threshold
```

**3. Review top errors weekly:**
```bash
# Get most common errors
curl http://localhost:8001/api/errors/summary?hours=168&min_occurrences=5

# Prioritize fixing high-occurrence errors
```

**4. Archive old errors:**
```bash
# Export errors before clearing
curl http://localhost:8001/api/errors/summary?hours=720 > errors_archive.json

# Clear old errors
curl -X POST http://localhost:8001/api/errors/clear?hours=720
```

### Integration with Services

Error tracking is automatically integrated:

```python
from src.services import TaskService
from src.core.database import get_db_session

# Service methods automatically track errors
with get_db_session() as session:
    try:
        # If this fails, error is automatically tracked
        task = TaskService.execute_task_with_workflow(
            session=session,
            task_id=123,
            workflow_type="default"
        )
    except Exception as e:
        # Error already tracked by middleware
        # Can add additional context if needed
        pass
```

## Rate Limiting and Request Throttling

The system includes sophisticated rate limiting to prevent API abuse and ensure fair resource allocation across users.

### Rate Limit Tiers

Different user roles have different rate limits:

| Role | Requests/Minute | Description |
|------|-----------------|-------------|
| **VIEWER** | 60 | Read-only access, limited requests |
| **USER** | 120 | Standard user, moderate requests |
| **ADMIN** | 300 | Administrator, high request limit |

### Endpoint-Specific Limits

Some endpoints have stricter limits regardless of user role:

| Endpoint | Requests/Minute | Reason |
|----------|-----------------|--------|
| **POST /api/workflows/execute** | 10 | Resource-intensive workflow execution |
| **POST /api/tasks** | 30 | Task creation limit |
| **POST /api/agents** | 20 | Agent creation limit |

### How It Works

The rate limiting system uses:

- **Sliding Window Algorithm** - More accurate than fixed windows
- **Redis Backend** - Distributed rate limiting across multiple servers
- **Per-User Tracking** - Each user has independent rate limits
- **IP-Based Fallback** - Unauthenticated requests limited by IP

### Rate Limit Headers

Every API response includes rate limit headers:

```http
HTTP/1.1 200 OK
X-RateLimit-Limit: 120
X-RateLimit-Remaining: 115
X-RateLimit-Reset: 1705334400
```

- **X-RateLimit-Limit** - Maximum requests allowed in the window
- **X-RateLimit-Remaining** - Requests remaining in current window
- **X-RateLimit-Reset** - Unix timestamp when limit resets

### Rate Limit Exceeded Response

When rate limit is exceeded, you receive a `429 Too Many Requests` response:

```bash
curl -X POST http://localhost:8001/api/tasks \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "Test", "description": "Test"}'

# Response (429 Too Many Requests):
# {
#   "error": "Rate limit exceeded",
#   "message": "Rate limit exceeded. Maximum 30 requests per 60 seconds.",
#   "retry_after": 45
# }

# Headers:
# X-RateLimit-Limit: 30
# X-RateLimit-Remaining: 0
# X-RateLimit-Reset: 1705334445
# Retry-After: 45
```

### Check Your Rate Limit Status

Get your current rate limit information:

```bash
# Check overall rate limit
curl http://localhost:8001/api/rate-limits/me \
  -H "Authorization: Bearer <token>"

# Response:
# {
#   "limit": 120,
#   "remaining": 115,
#   "reset": 1705334400,
#   "used": 5
# }

# Check rate limit for specific endpoint
curl "http://localhost:8001/api/rate-limits/me?endpoint=/api/tasks" \
  -H "Authorization: Bearer <token>"

# Response:
# {
#   "limit": 30,
#   "remaining": 28,
#   "reset": 1705334400,
#   "used": 2
# }
```

### View Available Rate Limit Tiers

See all rate limit tiers and your current tier:

```bash
curl http://localhost:8001/api/rate-limits/tiers \
  -H "Authorization: Bearer <token>"

# Response:
# {
#   "role_based": {
#     "viewer": {
#       "max_requests": 60,
#       "window_seconds": 60,
#       "description": "60 requests per minute"
#     },
#     "user": {
#       "max_requests": 120,
#       "window_seconds": 60,
#       "description": "120 requests per minute"
#     },
#     "admin": {
#       "max_requests": 300,
#       "window_seconds": 60,
#       "description": "300 requests per minute"
#     }
#   },
#   "endpoint_specific": {
#     "task_create": {
#       "max_requests": 30,
#       "window_seconds": 60,
#       "description": "30 requests per minute"
#     },
#     "workflow_execute": {
#       "max_requests": 10,
#       "window_seconds": 60,
#       "description": "10 requests per minute"
#     },
#     "agent_create": {
#       "max_requests": 20,
#       "window_seconds": 60,
#       "description": "20 requests per minute"
#     }
#   },
#   "current_user_tier": {
#     "role": "user",
#     "max_requests": 120,
#     "window_seconds": 60
#   }
# }
```

### Reset Rate Limit (Admin)

Administrators can reset rate limits for any user:

```bash
# Reset your own rate limit
curl -X POST http://localhost:8001/api/rate-limits/reset/me \
  -H "Authorization: Bearer <admin_token>"

# Response:
# {
#   "success": true,
#   "message": "Rate limit reset for user 1"
# }

# Reset specific user's rate limit (admin only)
curl -X POST http://localhost:8001/api/rate-limits/reset/user/123 \
  -H "Authorization: Bearer <admin_token>"

# Response:
# {
#   "success": true,
#   "message": "Rate limit reset for user 123"
# }

# Reset specific endpoint rate limit
curl -X POST "http://localhost:8001/api/rate-limits/reset/me?endpoint=/api/tasks" \
  -H "Authorization: Bearer <admin_token>"

# Response:
# {
#   "success": true,
#   "message": "Rate limit reset for user 1 on endpoint /api/tasks"
# }
```

### Exempt Endpoints

The following endpoints are exempt from rate limiting:

- `/api/health/*` - Health check endpoints
- `/docs` - API documentation
- `/redoc` - Alternative API documentation
- `/openapi.json` - OpenAPI specification
- `/` - Root endpoint

### Handling Rate Limits in Client Code

**Python Example:**

```python
import requests
import time

def make_api_request(url, headers, data):
    """Make API request with rate limit handling"""
    while True:
        response = requests.post(url, headers=headers, json=data)

        if response.status_code == 429:
            # Rate limit exceeded
            retry_after = int(response.headers.get('Retry-After', 60))
            print(f"Rate limit exceeded. Retrying after {retry_after} seconds...")
            time.sleep(retry_after)
            continue

        # Check remaining requests
        remaining = int(response.headers.get('X-RateLimit-Remaining', 0))
        if remaining < 10:
            print(f"Warning: Only {remaining} requests remaining")

        return response

# Usage
response = make_api_request(
    url="http://localhost:8001/api/tasks",
    headers={"Authorization": f"Bearer {token}"},
    data={"title": "My Task", "description": "Task description"}
)
```

**JavaScript Example:**

```javascript
async function makeApiRequest(url, options) {
    while (true) {
        const response = await fetch(url, options);

        if (response.status === 429) {
            // Rate limit exceeded
            const retryAfter = parseInt(response.headers.get('Retry-After') || '60');
            console.log(`Rate limit exceeded. Retrying after ${retryAfter} seconds...`);
            await new Promise(resolve => setTimeout(resolve, retryAfter * 1000));
            continue;
        }

        // Check remaining requests
        const remaining = parseInt(response.headers.get('X-RateLimit-Remaining') || '0');
        if (remaining < 10) {
            console.warn(`Warning: Only ${remaining} requests remaining`);
        }

        return response;
    }
}

// Usage
const response = await makeApiRequest('http://localhost:8001/api/tasks', {
    method: 'POST',
    headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        title: 'My Task',
        description: 'Task description'
    })
});
```

### Custom Rate Limits

You can customize rate limits by modifying the tiers in [src/core/rate_limiter.py](src/core/rate_limiter.py):

```python
class RateLimitTier:
    """Predefined rate limit tiers"""

    # Customize role-based limits
    VIEWER = {"max_requests": 100, "window_seconds": 60}  # 100 req/min
    USER = {"max_requests": 200, "window_seconds": 60}    # 200 req/min
    ADMIN = {"max_requests": 500, "window_seconds": 60}   # 500 req/min

    # Customize endpoint-specific limits
    WORKFLOW_EXECUTE = {"max_requests": 20, "window_seconds": 60}  # 20 req/min
```

### Rate Limit Monitoring

Monitor rate limit usage via Prometheus metrics:

```bash
# View metrics
curl http://localhost:8001/api/metrics

# Metrics include:
# - rate_limit_exceeded_total{endpoint="/api/tasks"}
# - rate_limit_remaining{user_id="123",endpoint="/api/tasks"}
# - rate_limit_reset_total{user_id="123"}
```

### Production Best Practices

**1. Monitor rate limit hits:**
```bash
# Check how often users hit rate limits
curl http://localhost:8001/api/errors/summary?hours=24 | \
  jq '.top_errors[] | select(.error_type == "RateLimitExceeded")'
```

**2. Adjust limits for power users:**
```python
# Create custom tiers for high-volume users
# Add to RateLimitTier class:
POWER_USER = {"max_requests": 1000, "window_seconds": 60}
```

**3. Use Redis persistence:**
```bash
# Ensure Redis persistence is enabled
redis-cli CONFIG SET save "900 1 300 10 60 10000"
```

**4. Set up alerts:**
```python
# Alert when users frequently hit rate limits
# This may indicate they need a higher tier or have inefficient code
```

## Caching Layer and Performance Optimization

The system includes a sophisticated caching layer built on Redis for improved performance and reduced database load.

### Caching Features

- **Response Caching** - Automatic HTTP response caching for GET requests
- **Query Result Caching** - Decorator-based caching for expensive database queries
- **TTL Management** - Configurable time-to-live per endpoint or function
- **Cache Invalidation** - Pattern-based and namespace-based invalidation
- **Cache Statistics** - Real-time cache hit/miss rates and memory usage

### Automatic Response Caching

GET requests are automatically cached based on endpoint configuration:

| Endpoint | Cache TTL | Description |
|----------|-----------|-------------|
| `/api/tasks` | 60 seconds | Task list caching |
| `/api/agents` | 120 seconds | Agent list caching |
| `/api/agents/available` | 30 seconds | Available agents (frequently changes) |
| `/api/metrics/summary` | 300 seconds | Metrics summary |
| `/api/workflows/workflows` | 600 seconds | Workflow definitions (rarely change) |
| `/api/rate-limits/tiers` | 3600 seconds | Rate limit tiers (static config) |

### Cache Headers

Cached responses include cache headers:

```http
HTTP/1.1 200 OK
X-Cache: HIT
X-Cache-Key: a1b2c3d4e5f6789a
X-Cache-TTL: 60
```

- **X-Cache**: `HIT` (cached), `MISS` (fresh), `SKIP` (not cacheable)
- **X-Cache-Key**: Cache key for debugging
- **X-Cache-TTL**: Time to live in seconds

### Cache Statistics

View cache performance metrics:

```bash
curl http://localhost:8001/api/cache/stats \
  -H "Authorization: Bearer <token>"

# Response:
# {
#   "cache_keys": 1250,
#   "total_keys": 1500,
#   "hits": 15000,
#   "misses": 3000,
#   "hit_rate": 83.33,
#   "memory_used_mb": 12.5,
#   "memory_peak_mb": 15.2
# }
```

### Clear Cache

Administrators can clear cache:

```bash
# Clear all cache
curl -X POST http://localhost:8001/api/cache/clear \
  -H "Authorization: Bearer <admin_token>"

# Response:
# {
#   "success": true,
#   "message": "Cleared all cache",
#   "keys_affected": null
# }

# Clear specific namespace
curl -X POST "http://localhost:8001/api/cache/clear?namespace=tasks" \
  -H "Authorization: Bearer <admin_token>"

# Response:
# {
#   "success": true,
#   "message": "Cleared namespace 'tasks' (125 keys)",
#   "keys_affected": 125
# }

# Clear by pattern
curl -X POST "http://localhost:8001/api/cache/clear?pattern=task_*" \
  -H "Authorization: Bearer <admin_token>"

# Response:
# {
#   "success": true,
#   "message": "Cleared 87 keys matching 'task_*'",
#   "keys_affected": 87
# }
```

### Invalidate Specific Caches

Invalidate caches after updates:

```bash
# Invalidate task cache (after creating/updating tasks)
curl -X POST http://localhost:8001/api/cache/invalidate/tasks \
  -H "Authorization: Bearer <token>"

# Response:
# {
#   "success": true,
#   "message": "Invalidated task cache",
#   "keys_affected": 45
# }

# Invalidate agent cache (after agent changes)
curl -X POST http://localhost:8001/api/cache/invalidate/agents \
  -H "Authorization: Bearer <token>"

# Response:
# {
#   "success": true,
#   "message": "Invalidated agent cache",
#   "keys_affected": 23
# }
```

### Function-Level Caching

Use the `@cached` decorator for expensive operations:

```python
from src.core.cache import cached

# Cache for 10 minutes
@cached(ttl=600, namespace="tasks")
def get_task_statistics(user_id: int):
    """Expensive database aggregation"""
    # This result will be cached for 10 minutes
    return expensive_database_query(user_id)

# Usage
stats = get_task_statistics(user_id=123)

# Invalidate cache for specific arguments
get_task_statistics.invalidate(user_id=123)

# Invalidate all cached results
get_task_statistics.invalidate_all()
```

### Custom Cache Keys

Build custom cache keys:

```python
from src.core.cache import cache_service

# Set with custom key
cache_service.set(
    key="user_123_tasks",
    value={"tasks": [...]},
    ttl=300,
    namespace="user_data"
)

# Get cached value
cached_tasks = cache_service.get("user_123_tasks", namespace="user_data")

# Delete specific key
cache_service.delete("user_123_tasks", namespace="user_data")

# Check if key exists
exists = cache_service.exists("user_123_tasks", namespace="user_data")
```

### Cache Namespaces

Organize cache with namespaces:

- **tasks** - Task-related cache
- **agents** - Agent-related cache
- **responses** - HTTP response cache
- **workflows** - Workflow definitions
- **user_data** - User-specific data

```python
from src.core.cache import cache_service

# Clear entire namespace
cache_service.clear_namespace("tasks")

# Delete by pattern in namespace
cache_service.delete_pattern("task_*", namespace="tasks")
```

### Cache Warming

Pre-populate cache with frequently accessed data:

```bash
curl -X POST http://localhost:8001/api/cache/warm \
  -H "Authorization: Bearer <admin_token>"

# Response:
# {
#   "success": true,
#   "message": "Cache warming initiated",
#   "keys_affected": 0
# }
```

### Production Best Practices

**1. Monitor cache hit rate:**
```bash
# Aim for >70% hit rate
curl http://localhost:8001/api/cache/stats | jq '.hit_rate'
```

**2. Set appropriate TTLs:**
```python
# Frequently changing data: short TTL
AVAILABLE_AGENTS_TTL = 30  # 30 seconds

# Rarely changing data: long TTL
WORKFLOW_DEFINITIONS_TTL = 3600  # 1 hour

# Static configuration: very long TTL
RATE_LIMIT_TIERS_TTL = 86400  # 24 hours
```

**3. Invalidate on writes:**
```python
from src.core.cache import cache_service

def update_task(task_id: int, updates: dict):
    # Update database
    task = db.update(task_id, updates)

    # Invalidate caches
    cache_service.delete(f"task_{task_id}", namespace="tasks")
    cache_service.clear_namespace("responses")  # Clear response cache

    return task
```

**4. Use Redis persistence:**
```bash
# Enable RDB snapshots
redis-cli CONFIG SET save "900 1 300 10 60 10000"

# Enable AOF for better durability
redis-cli CONFIG SET appendonly yes
```

**5. Monitor memory usage:**
```bash
# Check memory usage
curl http://localhost:8001/api/cache/stats | jq '.memory_used_mb'

# Set max memory limit
redis-cli CONFIG SET maxmemory 2gb
redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

### Cache Invalidation Patterns

**Pattern 1: Time-based (TTL)**
- Automatic expiration after TTL
- Good for data that changes predictably

**Pattern 2: Event-based**
```python
from src.core.cache import cache_service

# After creating a task
task = create_task(...)
cache_service.clear_namespace("tasks")
cache_service.clear_namespace("responses")
```

**Pattern 3: Pattern-based**
```python
# Invalidate all task-related caches
cache_service.delete_pattern("task_*")
```

**Pattern 4: Lazy invalidation**
```python
# Let cache expire naturally, don't invalidate
# Good for non-critical data
```

### Caching Strategy by Endpoint

```python
# High traffic, rarely changes
GET /api/workflows/workflows → Cache 10 min

# High traffic, changes frequently
GET /api/agents/available → Cache 30 sec

# Medium traffic, moderate changes
GET /api/tasks → Cache 1 min

# Low traffic, frequently changes
GET /api/auth/me → No cache (user-specific)

# Write operations
POST /PUT /DELETE → No cache, invalidate related caches
```

### Client-Side Cache Handling

**Respect cache headers:**

```javascript
fetch('http://localhost:8001/api/tasks', {
    headers: {
        'Authorization': `Bearer ${token}`,
        'Cache-Control': 'no-cache'  // Force fresh response
    }
})
.then(response => {
    const cacheStatus = response.headers.get('X-Cache');
    console.log(`Cache status: ${cacheStatus}`);  // HIT, MISS, or SKIP
    return response.json();
});
```

**Handle stale data:**

```python
import requests

response = requests.get(
    'http://localhost:8001/api/tasks',
    headers={'Authorization': f'Bearer {token}'}
)

# Check if data is cached
if response.headers.get('X-Cache') == 'HIT':
    # Data might be stale, consider refreshing
    pass
```

### Performance Impact

Expected performance improvements with caching:

| Metric | Without Cache | With Cache | Improvement |
|--------|---------------|------------|-------------|
| Response Time | 200ms | 5ms | 97.5% faster |
| Database Load | 100% | 20% | 80% reduction |
| API Throughput | 100 req/s | 500 req/s | 5x increase |
| Server CPU | 60% | 25% | 58% reduction |

### Troubleshooting

**Cache not working:**
```bash
# Check Redis connection
redis-cli ping

# Check cache stats
curl http://localhost:8001/api/cache/stats

# Look for cache headers in response
curl -I http://localhost:8001/api/tasks
```

**High memory usage:**
```bash
# Check memory
curl http://localhost:8001/api/cache/stats | jq '.memory_used_mb'

# Reduce TTLs in src/core/cache_middleware.py
# Or clear cache
curl -X POST http://localhost:8001/api/cache/clear
```

**Stale data:**
```bash
# Invalidate specific cache
curl -X POST http://localhost:8001/api/cache/invalidate/tasks

# Or clear all cache
curl -X POST http://localhost:8001/api/cache/clear
```

## Agent System

The Multi-Agent Orchestrator provides a flexible, extensible agent architecture for building AI-powered task automation systems.

### Architecture Overview

The agent system consists of four main components:

1. **Base Agent** (`BaseAgent`) - Abstract base class for all agents
2. **LLM Provider** (`LLMProvider`) - Unified interface for multiple LLM providers
3. **Agent Memory** (`AgentMemory`) - Short-term and long-term memory system
4. **Agent Executor** (`AgentExecutor`) - Execution engine with error handling and retries

### Creating a Custom Agent

**Step 1: Define Agent Class**

```python
from src.agents.base import BaseAgent, AgentConfig, AgentContext, AgentResult, AgentStatus
from src.agents.base import LLMProvider, LLMMessage, LLMRole

class DataAnalystAgent(BaseAgent):
    """Agent specialized in data analysis tasks"""

    def __init__(self, config: AgentConfig, llm_provider: LLMProvider):
        super().__init__(config)
        self.llm = llm_provider

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute data analysis task"""
        started_at = datetime.utcnow()

        try:
            # Process input
            result = await self.process(context.input_data)

            return AgentResult(
                status=AgentStatus.COMPLETED,
                output=result,
                started_at=started_at,
                completed_at=datetime.utcnow()
            )

        except Exception as e:
            return await self.handle_error(e, context)

    async def process(self, input_data: dict) -> Any:
        """Process data analysis request"""
        # Build messages for LLM
        messages = [
            LLMMessage(role=LLMRole.SYSTEM, content=self.get_system_prompt()),
            LLMMessage(
                role=LLMRole.USER,
                content=f"Analyze this data: {input_data['dataset']}"
            )
        ]

        # Call LLM
        response = await self.llm.generate(messages)

        return {
            "analysis": response.content,
            "tokens_used": response.tokens_used,
            "cost": response.cost
        }
```

**Step 2: Configure and Execute**

```python
from src.agents.base import AgentConfig, AgentContext, AgentExecutor
from src.agents.base.llm_provider import create_llm_provider

# Create LLM provider
llm = create_llm_provider(provider="openai", model="gpt-4")

# Configure agent
config = AgentConfig(
    name="Data Analyst",
    description="Analyzes datasets and provides insights",
    model="gpt-4",
    temperature=0.3,
    max_tokens=2000,
    tools=["pandas", "numpy"],
    memory_enabled=True
)

# Create agent
agent = DataAnalystAgent(config, llm)

# Create executor
executor = AgentExecutor(agent)

# Execute
context = AgentContext(
    task_id="task_123",
    input_data={"dataset": "sales_data.csv", "query": "monthly trends"}
)

result = await executor.execute(context)

print(f"Status: {result.status}")
print(f"Output: {result.output}")
print(f"Execution Time: {result.execution_time}s")
```

### LLM Provider Integration

The system supports multiple LLM providers through a unified interface.

**OpenAI Example:**

```python
from src.agents.base.llm_provider import OpenAIProvider, LLMMessage, LLMRole

# Initialize provider
llm = OpenAIProvider(
    model="gpt-4-turbo",
    api_key="sk-...",  # or set OPENAI_API_KEY env var
    temperature=0.7,
    max_tokens=2000
)

# Generate completion
messages = [
    LLMMessage(role=LLMRole.SYSTEM, content="You are a helpful assistant"),
    LLMMessage(role=LLMRole.USER, content="What is machine learning?")
]

response = await llm.generate(messages)

print(response.content)
print(f"Tokens: {response.tokens_used}")
print(f"Cost: ${response.cost}")
```

**Anthropic Claude Example:**

```python
from src.agents.base.llm_provider import AnthropicProvider

# Initialize provider
llm = AnthropicProvider(
    model="claude-3-sonnet-20240229",
    api_key="sk-ant-...",  # or set ANTHROPIC_API_KEY env var
    temperature=0.5
)

# Generate completion
response = await llm.generate(messages)
```

**Streaming Example:**

```python
# Stream tokens as they're generated
async for token in llm.generate_streaming(messages):
    print(token, end='', flush=True)
```

**Factory Pattern:**

```python
from src.agents.base.llm_provider import create_llm_provider

# Create provider using factory
llm = create_llm_provider(
    provider="openai",  # or "anthropic"
    model="gpt-4",
    temperature=0.7
)
```

### Agent Memory System

Agents can maintain short-term and long-term memory for context retention.

**Basic Usage:**

```python
from src.agents.base import AgentMemory, MemoryType

# Initialize memory
memory = AgentMemory(
    max_short_term=10,  # Keep last 10 items
    max_long_term=100,  # Keep up to 100 important items
    importance_threshold=0.7  # Items >= 0.7 go to long-term
)

# Add observations
memory.add(
    content="User requested data analysis for Q4 sales",
    memory_type=MemoryType.OBSERVATION,
    importance=0.8
)

# Add actions
memory.add(
    content="Generated SQL query: SELECT * FROM sales WHERE quarter = 4",
    memory_type=MemoryType.ACTION,
    importance=0.6
)

# Add results
memory.add(
    content="Analysis complete: Revenue increased 23%",
    memory_type=MemoryType.RESULT,
    importance=0.9
)

# Retrieve recent items
recent = memory.get_recent(n=5)
for item in recent:
    print(f"[{item.timestamp}] {item.type}: {item.content}")

# Get important items
important = memory.get_important(n=5, min_importance=0.7)

# Search memory
results = memory.search("sales", n=3)

# Get summary
summary = memory.get_summary(max_items=10)
print(summary)
```

**Memory Statistics:**

```python
stats = memory.get_stats()
print(f"Short-term: {stats['short_term_count']}")
print(f"Long-term: {stats['long_term_count']}")
print(f"Total: {stats['total_items']}")
```

### Agent Executor

The executor handles agent execution with automatic retries, timeouts, and error handling.

**Configuration:**

```python
from src.agents.base import AgentExecutor, AgentConfig

# Configure agent with retry settings
config = AgentConfig(
    name="Researcher",
    description="Researches topics and provides summaries",
    timeout=300,  # 5 minutes
    retry_on_failure=True,
    max_retries=3
)

agent = ResearchAgent(config, llm)
executor = AgentExecutor(agent)
```

**Execution with Context:**

```python
context = AgentContext(
    task_id="task_456",
    workflow_id="workflow_789",
    user_id=123,
    input_data={"topic": "quantum computing", "depth": "detailed"},
    metadata={"priority": "high"}
)

result = await executor.execute(context)

if result.status == AgentStatus.COMPLETED:
    print(f"Success! Output: {result.output}")
    print(f"Execution time: {result.execution_time}s")
    print(f"Tokens used: {result.tokens_used}")
    print(f"Cost: ${result.cost}")
else:
    print(f"Failed: {result.error}")
```

**Memory Integration:**

```python
# Executor automatically manages memory
executor = AgentExecutor(agent, memory=AgentMemory())

# Execute multiple tasks
for task in tasks:
    context = AgentContext(task_id=task.id, input_data=task.data)
    result = await executor.execute(context)

# Memory accumulates across executions
memory = executor.get_memory()
print(f"Total memory items: {len(memory)}")
print(memory.get_summary())

# Clear memory when needed
executor.clear_memory()
```

### Agent Configuration

Fine-tune agent behavior with comprehensive configuration options.

```python
config = AgentConfig(
    # Identity
    name="Code Reviewer",
    description="Reviews code for quality, security, and best practices",

    # LLM Settings
    model="gpt-4",
    temperature=0.3,  # Lower for more deterministic output
    max_tokens=4000,

    # System Prompt (optional)
    system_prompt="""You are an expert code reviewer.
    Focus on: security, performance, maintainability, and best practices.
    Provide actionable feedback with examples.""",

    # Tools
    tools=["ast_parser", "linter", "security_scanner"],

    # Memory
    memory_enabled=True,
    max_memory_items=15,

    # Execution
    timeout=180,  # 3 minutes
    retry_on_failure=True,
    max_retries=2
)
```

### Error Handling

**Custom Error Handling:**

```python
class MyAgent(BaseAgent):
    async def handle_error(self, error: Exception, context: AgentContext) -> AgentResult:
        """Custom error handling"""
        # Log to monitoring system
        logger.error(f"Agent failed: {error}", extra={
            "task_id": context.task_id,
            "input": context.input_data
        })

        # Check error type
        if isinstance(error, TimeoutError):
            return AgentResult(
                status=AgentStatus.FAILED,
                error="Task timed out - please simplify the request",
                metadata={"error_type": "timeout"},
                started_at=datetime.utcnow()
            )

        # Default handling
        return await super().handle_error(error, context)
```

**Retry Strategy:**

```python
# Executor automatically retries with exponential backoff
# Attempt 1: immediate
# Attempt 2: wait 2 seconds
# Attempt 3: wait 4 seconds
# Attempt 4: wait 8 seconds

# Configure retry behavior
config = AgentConfig(
    name="API Agent",
    retry_on_failure=True,
    max_retries=3,
    timeout=60
)
```

### Agent Status Tracking

Monitor agent execution status in real-time.

```python
# Check status
print(f"Agent status: {agent.get_status()}")

# Status transitions:
# IDLE -> RUNNING -> COMPLETED
# IDLE -> RUNNING -> FAILED
# IDLE -> RUNNING -> PAUSED

# Access current context
if agent.current_context:
    print(f"Processing task: {agent.current_context.task_id}")
```

### Cost Tracking

Automatically track LLM API costs.

```python
# After execution
result = await executor.execute(context)

print(f"Tokens used: {result.tokens_used}")
print(f"Prompt tokens: {result.metadata.get('prompt_tokens')}")
print(f"Completion tokens: {result.metadata.get('completion_tokens')}")
print(f"Cost: ${result.cost}")

# Cost is calculated per provider:
# - OpenAI GPT-4: $0.03/1K prompt, $0.06/1K completion
# - OpenAI GPT-3.5: $0.001/1K prompt, $0.002/1K completion
# - Claude 3 Opus: $0.015/1K prompt, $0.075/1K completion
# - Claude 3 Sonnet: $0.003/1K prompt, $0.015/1K completion
```

### Validation

Implement custom input validation.

```python
class ValidatedAgent(BaseAgent):
    async def validate_input(self, input_data: dict) -> bool:
        """Validate input data"""
        required_fields = ["query", "context"]

        # Check required fields
        if not all(field in input_data for field in required_fields):
            logger.error("Missing required fields")
            return False

        # Validate data types
        if not isinstance(input_data["query"], str):
            logger.error("Query must be a string")
            return False

        # Validate constraints
        if len(input_data["query"]) > 1000:
            logger.error("Query too long (max 1000 chars)")
            return False

        return True
```

### Best Practices

**1. Use Appropriate Models:**
```python
# Fast tasks: Use GPT-3.5 or Claude Haiku
fast_config = AgentConfig(name="Classifier", model="gpt-3.5-turbo")

# Complex reasoning: Use GPT-4 or Claude Opus
smart_config = AgentConfig(name="Strategist", model="gpt-4")
```

**2. Optimize Temperature:**
```python
# Deterministic (code, analysis): 0.0 - 0.3
code_config = AgentConfig(name="Coder", temperature=0.2)

# Balanced (general): 0.5 - 0.7
general_config = AgentConfig(name="Assistant", temperature=0.6)

# Creative (writing): 0.8 - 1.0
creative_config = AgentConfig(name="Writer", temperature=0.9)
```

**3. Enable Memory for Context:**
```python
# For multi-turn conversations
config = AgentConfig(
    name="Chatbot",
    memory_enabled=True,
    max_memory_items=20  # Last 20 interactions
)
```

**4. Set Reasonable Timeouts:**
```python
# Quick tasks: 30-60 seconds
quick_config = AgentConfig(name="Classifier", timeout=30)

# Complex tasks: 120-300 seconds
complex_config = AgentConfig(name="Analyst", timeout=180)
```

**5. Handle Errors Gracefully:**
```python
result = await executor.execute(context)

if result.status == AgentStatus.FAILED:
    # Log error
    logger.error(f"Agent failed: {result.error}")

    # Retry with different strategy
    # Or escalate to human
    # Or use fallback agent
```

## Specialized Agents

The system includes pre-built specialized agents for common tasks.

### Available Agent Types

| Agent Type | Purpose | Use Cases |
|------------|---------|-----------|
| **ResearchAgent** | Information gathering | Topic research, fact verification, source synthesis |
| **CodeAgent** | Code generation/analysis | Code writing, review, debugging, refactoring |
| **DataAnalystAgent** | Data analysis | Statistical analysis, insights, trend identification |
| **WriterAgent** | Content creation | Articles, documentation, marketing copy |
| **PlannerAgent** | Task planning | Task decomposition, project planning, workflow design |

### Research Agent

Specializes in information gathering and research tasks.

**Example:**

```python
from src.agents import ResearchAgent, AgentContext, AgentExecutor
from src.agents.base.llm_provider import create_llm_provider

# Create LLM provider
llm = create_llm_provider(provider="openai", model="gpt-4")

# Create research agent
agent = ResearchAgent(llm)

# Create executor
executor = AgentExecutor(agent)

# Execute research task
context = AgentContext(
    task_id="research_001",
    input_data={
        "topic": "quantum computing applications in cryptography",
        "depth": "deep",  # shallow, medium, deep
        "focus_areas": [
            "post-quantum cryptography",
            "quantum key distribution",
            "current implementations"
        ]
    }
)

result = await executor.execute(context)

print(f"Topic: {result.output['topic']}")
print(f"Findings: {len(result.output['findings'])} key points")
print(f"Summary:\n{result.output['summary']}")
print(f"Cost: ${result.cost}")
```

**Input Parameters:**
- `topic` (required): Research topic
- `depth`: `shallow`, `medium`, `deep` (default: `medium`)
- `focus_areas`: List of specific areas to focus on
- `research_type`: Type of research (default: `general`)

**Output:**
- `findings`: Structured list of key findings
- `summary`: Full research summary
- `topic`: Research topic
- `depth`: Research depth used

### Code Agent

Specializes in code generation, analysis, and debugging.

**Example - Code Generation:**

```python
from src.agents import CodeAgent

llm = create_llm_provider(provider="openai", model="gpt-4")
agent = CodeAgent(llm)
executor = AgentExecutor(agent)

context = AgentContext(
    task_id="code_001",
    input_data={
        "task_type": "generate",
        "language": "python",
        "requirements": """
        Create a function that:
        1. Accepts a list of numbers
        2. Removes duplicates
        3. Sorts in descending order
        4. Returns top N items
        Include error handling and type hints.
        """
    }
)

result = await executor.execute(context)

print(f"Generated Code:\n{result.output['code']}")
print(f"Explanation:\n{result.output['explanation']}")
```

**Example - Code Review:**

```python
context = AgentContext(
    task_id="code_002",
    input_data={
        "task_type": "review",
        "language": "python",
        "code": """
def process_data(data):
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
    return result
        """
    }
)

result = await executor.execute(context)
print(result.output['explanation'])  # Security, performance, quality analysis
```

**Task Types:**
- `generate`: Create new code
- `review`: Analyze code quality and security
- `debug`: Find and fix bugs
- `refactor`: Improve code structure
- `document`: Generate documentation

### Data Analyst Agent

Specializes in data analysis and insights generation.

**Example:**

```python
from src.agents import DataAnalystAgent

llm = create_llm_provider(provider="openai", model="gpt-4")
agent = DataAnalystAgent(llm)
executor = AgentExecutor(agent)

context = AgentContext(
    task_id="analysis_001",
    input_data={
        "data": {
            "revenue": [100000, 120000, 115000, 135000, 150000],
            "costs": [60000, 65000, 70000, 72000, 75000],
            "months": ["Jan", "Feb", "Mar", "Apr", "May"]
        },
        "analysis_type": "predictive",  # descriptive, diagnostic, predictive, prescriptive
        "questions": [
            "What is the revenue trend?",
            "What will June revenue be?",
            "What factors are driving growth?"
        ]
    }
)

result = await executor.execute(context)

print(f"Analysis Type: {result.output['analysis_type']}")
print(f"Insights: {len(result.output['insights'])} key insights")
print(f"Recommendations:")
for rec in result.output['recommendations']:
    print(f"  - {rec}")
```

**Analysis Types:**
- `descriptive`: Summarize data characteristics
- `diagnostic`: Explain why trends occur
- `predictive`: Forecast future trends
- `prescriptive`: Recommend actions
- `exploratory`: Discover patterns

### Writer Agent

Specializes in content creation and writing.

**Example:**

```python
from src.agents import WriterAgent

llm = create_llm_provider(provider="openai", model="gpt-4")
agent = WriterAgent(llm)
executor = AgentExecutor(agent)

context = AgentContext(
    task_id="write_001",
    input_data={
        "content_type": "blog_post",
        "topic": "Getting started with microservices architecture",
        "style": "professional",  # creative, conversational, professional, technical
        "audience": "software engineers",
        "length": "medium"  # short, medium, long
    }
)

result = await executor.execute(context)

print(f"Content:\n{result.output['content']}")
print(f"Word Count: {result.output['word_count']}")
print(f"Sections: {len(result.output['sections'])}")
```

**Content Types:**
- `article`: Informative, well-researched pieces
- `blog_post`: Engaging, conversational content
- `documentation`: Clear, detailed instructions
- `marketing_copy`: Persuasive, benefit-focused
- `report`: Structured, analytical content
- `email`: Concise, action-oriented
- `social_media`: Brief, engaging posts

**Styles:**
- `creative` (temp: 0.9)
- `conversational` (temp: 0.8)
- `professional` (temp: 0.6)
- `technical` (temp: 0.3)
- `formal` (temp: 0.4)
- `casual` (temp: 0.7)

### Planner Agent

Specializes in task planning and decomposition.

**Example:**

```python
from src.agents import PlannerAgent

llm = create_llm_provider(provider="openai", model="gpt-4")
agent = PlannerAgent(llm)
executor = AgentExecutor(agent)

context = AgentContext(
    task_id="plan_001",
    input_data={
        "goal": "Build a RESTful API for a task management application",
        "plan_type": "project_plan",  # task_breakdown, project_plan, workflow_design, strategy
        "constraints": {
            "timeline": "2 weeks",
            "team_size": "2 developers",
            "tech_stack": "FastAPI, PostgreSQL, Redis"
        },
        "context": "Starting from scratch, need authentication and real-time updates"
    }
)

result = await executor.execute(context)

print(f"Goal: {result.output['goal']}")
print(f"Tasks: {len(result.output['tasks'])}")
print(f"Estimated Time: {result.output['estimated_total_time']}")

for task in result.output['tasks']:
    print(f"\nTask: {task['name']}")
    print(f"  Priority: {task['priority']}")
    print(f"  Time: {task['estimated_time']}")
    print(f"  Description: {task['description']}")
```

**Plan Types:**
- `task_breakdown`: Break goal into specific tasks
- `project_plan`: Comprehensive project plan
- `workflow_design`: Process workflow design
- `strategy`: Strategic planning

### Agent Registry

The agent registry provides centralized management for all agents.

**Basic Usage:**

```python
from src.agents import agent_registry

# List all available agents
agents = agent_registry.list_agents()
for agent_info in agents:
    print(f"{agent_info['type']}: {agent_info['description']}")

# Create agent from registry
research_agent = agent_registry.create_agent(
    agent_type="research",
    cache_instance=True  # Cache for reuse
)

# Get cached instance
cached_agent = agent_registry.get_agent("research")

# Get detailed info
info = agent_registry.get_agent_info("code")
print(f"Agent: {info['name']}")
print(f"Config: {info['config']}")
```

**Register Custom Agent:**

```python
from src.agents import BaseAgent, AgentConfig

class CustomAgent(BaseAgent):
    """Your custom agent implementation"""
    pass

# Register with the registry
agent_registry.register_agent("custom", CustomAgent)

# Register default configuration
config = AgentConfig(
    name="Custom Agent",
    description="My specialized agent",
    model="gpt-4",
    temperature=0.5
)
agent_registry.register_config("custom", config)

# Create instance
custom_agent = agent_registry.create_agent("custom")
```

**Registry Methods:**

| Method | Description |
|--------|-------------|
| `register_agent(type, class)` | Register a new agent type |
| `register_config(type, config)` | Register default configuration |
| `create_agent(type, llm, config, cache)` | Create agent instance |
| `get_agent(type)` | Get cached agent instance |
| `list_agents()` | List all registered agents |
| `get_agent_info(type)` | Get detailed agent information |
| `clear_cache(type)` | Clear cached instances |
| `is_registered(type)` | Check if agent type exists |

**Factory Pattern with Registry:**

```python
from src.agents.base.llm_provider import create_llm_provider

# Create LLM provider once
llm = create_llm_provider(provider="anthropic", model="claude-3-sonnet-20240229")

# Create multiple agents with same LLM
research_agent = agent_registry.create_agent("research", llm, cache_instance=True)
code_agent = agent_registry.create_agent("code", llm, cache_instance=True)
planner_agent = agent_registry.create_agent("planner", llm, cache_instance=True)

# Reuse cached instances
same_research_agent = agent_registry.get_agent("research")
assert research_agent is same_research_agent  # Same instance
```

### Combining Multiple Agents

Orchestrate multiple specialized agents for complex workflows.

**Example - Research → Plan → Execute:**

```python
from src.agents import agent_registry, AgentContext, AgentExecutor

# Create LLM provider
llm = create_llm_provider(provider="openai", model="gpt-4")

# Step 1: Research
research_agent = agent_registry.create_agent("research", llm)
research_result = await AgentExecutor(research_agent).execute(
    AgentContext(
        task_id="multi_001_research",
        input_data={"topic": "best practices for API rate limiting"}
    )
)

# Step 2: Plan based on research
planner_agent = agent_registry.create_agent("planner", llm)
plan_result = await AgentExecutor(planner_agent).execute(
    AgentContext(
        task_id="multi_001_plan",
        input_data={
            "goal": "Implement rate limiting for our API",
            "context": research_result.output['summary']
        }
    )
)

# Step 3: Generate code
code_agent = agent_registry.create_agent("code", llm)
code_result = await AgentExecutor(code_agent).execute(
    AgentContext(
        task_id="multi_001_code",
        input_data={
            "task_type": "generate",
            "language": "python",
            "requirements": plan_result.output['full_plan']
        }
    )
)

print("Multi-agent workflow complete!")
print(f"Research cost: ${research_result.cost}")
print(f"Planning cost: ${plan_result.cost}")
print(f"Code gen cost: ${code_result.cost}")
print(f"Total cost: ${research_result.cost + plan_result.cost + code_result.cost}")
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run unit tests only
pytest -m unit

# Run integration tests only
pytest -m integration

# Run with coverage
pytest --cov=src --cov-report=html --cov-report=term-missing

# Run specific test file
pytest tests/unit/test_validators.py -v

# Run tests excluding slow/LLM tests
pytest -m "not slow and not llm"
```

### Code Quality

```bash
# Format code with Black
black src/ tests/

# Sort imports with isort
isort src/ tests/

# Run linting checks
flake8 src/ tests/

# Run static analysis
pylint src/

# Run all quality checks
black --check src/ tests/ && \
isort --check-only src/ tests/ && \
flake8 src/ tests/ && \
pytest -m unit
```

### Pre-commit Hooks

Pre-commit hooks automatically run code quality checks before each commit, ensuring consistent code quality.

**Installation:**

```bash
# Install development dependencies (includes pre-commit)
pip install -r requirements-dev.txt

# Install pre-commit hooks
pre-commit install
```

**What Gets Checked:**

The pre-commit hooks run the following checks:
- **Black**: Code formatting (line length 100)
- **isort**: Import sorting (Black-compatible)
- **Flake8**: Linting with additional plugins
- **pyupgrade**: Upgrade syntax to Python 3.11+
- **Bandit**: Security vulnerability scanning
- **Trailing whitespace**: Remove trailing spaces
- **End of file**: Ensure newline at end
- **YAML/JSON/TOML**: Validate file syntax
- **Large files**: Prevent files > 1MB
- **Merge conflicts**: Detect conflict markers
- **Hadolint**: Dockerfile linting
- **ShellCheck**: Shell script analysis
- **Markdownlint**: Markdown formatting

**Manual Execution:**

```bash
# Run on all files
pre-commit run --all-files

# Run specific hook
pre-commit run black --all-files

# Update hook versions
pre-commit autoupdate

# Skip hooks for a commit (use sparingly)
git commit --no-verify
```

**Benefits:**
- Catches issues before CI/CD
- Ensures consistent code style
- Prevents common errors
- Faster feedback loop

### CI/CD

The project uses GitHub Actions for continuous integration:

- **Tests**: Runs on Python 3.11 and 3.12 with PostgreSQL and Redis
- **Code Quality**: Black, isort, Flake8, Pylint checks
- **Security**: Safety (dependency vulnerabilities) and Bandit (security issues)
- **Docker Build**: Validates Docker image builds successfully

All checks must pass before merging pull requests.

## Usage Guide

### Quick Start

After starting the services, initialize the database and seed default agents:

```bash
# Using Docker
make shell
python scripts/init_db.py
python scripts/seed_sample_data.py
exit

# Or locally
python scripts/init_db.py
python scripts/seed_sample_data.py
```

### API Usage Examples

#### 1. Health Check

```bash
# Check overall system health
curl http://localhost:8001/api/health

# Check individual components
curl http://localhost:8001/api/health/db
curl http://localhost:8001/api/health/celery
curl http://localhost:8001/api/health/full
```

#### 2. List Available Agents

```bash
# Get all agents
curl http://localhost:8001/api/agents

# Get only available agents
curl http://localhost:8001/api/agents/available

# Filter by role
curl http://localhost:8001/api/agents?role=coder
```

#### 3. Create a Task

```bash
curl -X POST http://localhost:8001/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Implement user authentication",
    "description": "Add JWT-based authentication to the API",
    "task_type": "coding",
    "priority": 8,
    "input_data": {
      "requirements": [
        "JWT token generation",
        "Password hashing",
        "Login endpoint"
      ]
    }
  }'
```

#### 4. Assign Task to Agent

```bash
# Update task with agent assignment
curl -X PATCH http://localhost:8001/api/tasks/1 \
  -H "Content-Type: application/json" \
  -d '{
    "assigned_agent_id": 2,
    "status": "queued"
  }'
```

#### 5. Create Task Dependencies

```bash
# Task 3 depends on Task 1 and Task 2
curl -X POST http://localhost:8001/api/tasks/3/dependencies \
  -H "Content-Type: application/json" \
  -d '{
    "dependency_ids": [1, 2]
  }'
```

#### 6. Monitor Task Progress

```bash
# Get task details
curl http://localhost:8001/api/tasks/1

# Get task dependencies
curl http://localhost:8001/api/tasks/1/dependencies

# Filter tasks by status
curl http://localhost:8001/api/tasks?status=in_progress
```

#### 7. View Agent Metrics

```bash
# Get agent performance metrics
curl http://localhost:8001/api/agents/1/metrics

# Get system-wide metrics
curl http://localhost:8001/api/metrics/summary
```

### Common Workflows

#### Workflow 1: Simple Task Execution

```python
import requests

BASE_URL = "http://localhost:8001/api"

# 1. Create a task
task_response = requests.post(f"{BASE_URL}/tasks", json={
    "title": "Research Python best practices",
    "description": "Gather information on modern Python development practices",
    "task_type": "research",
    "priority": 5
})
task_id = task_response.json()["id"]

# 2. Get available researcher agent
agents = requests.get(f"{BASE_URL}/agents/available?role=researcher").json()
researcher_id = agents[0]["id"]

# 3. Assign task to agent
requests.patch(f"{BASE_URL}/tasks/{task_id}", json={
    "assigned_agent_id": researcher_id,
    "status": "queued"
})

# 4. Monitor progress
task = requests.get(f"{BASE_URL}/tasks/{task_id}").json()
print(f"Task status: {task['status']}")
print(f"Progress: {task['progress']}%")
```

#### Workflow 2: Multi-Step Task with Dependencies

```python
import requests

BASE_URL = "http://localhost:8001/api"

# 1. Create research task
research_task = requests.post(f"{BASE_URL}/tasks", json={
    "title": "Research authentication methods",
    "task_type": "research",
    "priority": 7
}).json()

# 2. Create coding task (depends on research)
coding_task = requests.post(f"{BASE_URL}/tasks", json={
    "title": "Implement authentication",
    "task_type": "coding",
    "priority": 8,
    "dependency_ids": [research_task["id"]]
}).json()

# 3. Create testing task (depends on coding)
testing_task = requests.post(f"{BASE_URL}/tasks", json={
    "title": "Test authentication",
    "task_type": "testing",
    "priority": 7,
    "dependency_ids": [coding_task["id"]]
}).json()

# 4. Create documentation task (depends on testing)
docs_task = requests.post(f"{BASE_URL}/tasks", json={
    "title": "Document authentication",
    "task_type": "documentation",
    "priority": 6,
    "dependency_ids": [testing_task["id"]]
}).json()

print(f"Created task chain: {research_task['id']} -> {coding_task['id']} -> {testing_task['id']} -> {docs_task['id']}")
```

#### Workflow 3: Agent Configuration

```python
import requests

BASE_URL = "http://localhost:8001/api"

# Create a custom agent
agent = requests.post(f"{BASE_URL}/agents", json={
    "name": "Senior Python Developer",
    "role": "coder",
    "description": "Expert Python developer specializing in backend systems",
    "llm_provider": "anthropic",
    "llm_model": "claude-3-5-sonnet-20241022",
    "temperature": 0.2,
    "max_tokens": 4096,
    "system_prompt": """You are a senior Python developer with expertise in:
- FastAPI and async programming
- SQLAlchemy ORM
- Pytest and testing
- Clean code principles
- Performance optimization

Always write production-ready code with proper error handling and documentation."""
}).json()

print(f"Created agent: {agent['name']} (ID: {agent['id']})")
```

### Architecture Details

#### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                      Client Application                      │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Server                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Tasks API    │  │ Agents API   │  │ Metrics API  │      │
│  └──────────────┘  └──────────────┘  └──────────────┘      │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│ PostgreSQL  │  │   Redis     │  │  Celery     │
│  Database   │  │   Cache     │  │  Workers    │
└─────────────┘  └─────────────┘  └─────────────┘
                                          │
                         ┌────────────────┼────────────────┐
                         ▼                ▼                ▼
                  ┌──────────┐    ���──────────┐    ┌──────────┐
                  │  Task    │    │  Agent   │    │Monitoring│
                  │  Queue   │    │  Queue   │    │  Queue   │
                  └──────────┘    └──────────┘    └──────────┘
```

#### Task Lifecycle

1. **PENDING**: Task created, awaiting dependencies
2. **QUEUED**: Dependencies met, queued for execution
3. **IN_PROGRESS**: Agent actively working on task
4. **WAITING_APPROVAL**: Human review required
5. **COMPLETED**: Task finished successfully
6. **FAILED**: Task execution failed
7. **CANCELLED**: Task manually cancelled

#### Agent Roles and Configurations

| Agent | Role | Temperature | Purpose |
|-------|------|-------------|---------|
| Research Agent | RESEARCHER | 0.7 | Information gathering, analysis |
| Coder Agent | CODER | 0.3 | Code implementation |
| Reviewer Agent | REVIEWER | 0.4 | Code review, suggestions |
| Tester Agent | TESTER | 0.5 | Test creation and execution |
| Writer Agent | WRITER | 0.6 | Documentation generation |
| Coordinator Agent | COORDINATOR | 0.5 | Task orchestration |

### Monitoring and Metrics

#### Prometheus Metrics

The system exposes Prometheus metrics at `/api/metrics`:

```bash
# View metrics in Prometheus format
curl http://localhost:8001/api/metrics

# View metrics summary in JSON
curl http://localhost:8001/api/metrics/summary
```

**Available Metrics**:
- `task_created_total` - Total tasks created by type
- `task_completed_total` - Completed tasks by type and status
- `task_duration_seconds` - Task execution duration histogram
- `agent_active_total` - Currently active agents by role
- `llm_call_total` - LLM API calls by provider and model
- `llm_cost_total` - Total LLM costs by provider
- `http_requests_total` - HTTP requests by method, path, status

#### Logging

Logs are written in structured JSON format:

```bash
# View application logs
tail -f logs/app.log

# View error logs only
tail -f logs/error.log

# View Docker logs
make logs
```

### Troubleshooting

#### Database Connection Issues

```bash
# Check database health
curl http://localhost:8001/api/health/db

# Connect to PostgreSQL shell
make db-shell

# Verify tables exist
\dt

# Check agent count
SELECT COUNT(*) FROM agents;
```

#### Celery Worker Issues

```bash
# Check Celery health
curl http://localhost:8001/api/health/celery

# View Celery logs
docker logs multi-agent-orchestrator-celery_worker-1

# Restart Celery worker
docker restart multi-agent-orchestrator-celery_worker-1
```

#### Task Stuck in PENDING

Tasks remain PENDING if dependencies are not met:

```bash
# Check task dependencies
curl http://localhost:8001/api/tasks/{task_id}/dependencies

# Verify dependency tasks are completed
curl http://localhost:8001/api/tasks/{dependency_id}
```

#### High LLM Costs

Monitor and optimize LLM usage:

```python
# Get cost summary
response = requests.get("http://localhost:8001/api/metrics/summary")
costs = response.json()["llm_costs"]

# Adjust agent temperature (lower = more focused, cheaper)
requests.patch("http://localhost:8001/api/agents/1", json={
    "temperature": 0.2,  # More deterministic
    "max_tokens": 2048   # Limit response length
})
```

### Environment Variables

Key configuration options in `.env`:

```bash
# LLM Provider Selection
LLM_PROVIDER=openai          # or 'anthropic'
LLM_MODEL=gpt-4             # or 'claude-3-5-sonnet-20241022'
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=4096

# Agent Configuration
MAX_CONCURRENT_AGENTS=5
AGENT_TIMEOUT_SECONDS=300
ENABLE_AGENT_MEMORY=true

# Task Configuration
MAX_TASK_RETRIES=3
TASK_TIMEOUT_SECONDS=600
ENABLE_HUMAN_APPROVAL=false

# Cost Tracking
ENABLE_COST_TRACKING=true
COST_ALERT_THRESHOLD=100.0
```

### API Documentation

Interactive API documentation is available at:
- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

## Project Status

✅ **Block Phase 1 Complete!** - Foundation & Infrastructure (100% complete)
🚧 **Block Phase 2 In Progress** - Basic Agent Implementation (10% complete)

Current Progress: Commit 22/100 - Specialized Agents Implemented

## Implementation Roadmap

### Block 1: Foundation & Infrastructure (Commits 1-20)
- Project structure and dependencies
- Database models and migrations
- FastAPI server setup
- Celery task queue configuration
- Basic authentication

### Block 2: Basic Agent Implementation (Commits 21-40)
- Agent base classes
- Individual agent implementations
- LangGraph integration
- Basic task execution

### Block 3: Multi-Agent Coordination (Commits 41-60)
- DAG workflow engine
- Shared memory system
- Agent communication
- Task decomposition

### Block 4: Advanced Features (Commits 61-80)
- Human approval gates
- Cost tracking
- Performance monitoring
- WebSocket real-time updates

### Block 5: Production & Polish (Commits 81-100)
- Frontend interface
- Production deployment
- Documentation
- Testing and optimization

## Tech Stack

- **Backend**: FastAPI, Celery, SQLAlchemy
- **Database**: PostgreSQL
- **Cache**: Redis
- **AI**: LangGraph, LangChain, OpenAI/Anthropic
- **Monitoring**: Prometheus, custom metrics
- **Frontend**: React (coming in Block 5)

## License

MIT License - see main repository LICENSE file
