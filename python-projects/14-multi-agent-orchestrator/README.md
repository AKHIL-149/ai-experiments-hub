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

🚧 **In Development** - Block Phase 1: Foundation & Infrastructure (90% complete)

Current Progress: Commit 18/100

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
