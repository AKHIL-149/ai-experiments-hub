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

## LangGraph Workflows

The Multi-Agent Orchestrator uses [LangGraph](https://github.com/langchain-ai/langgraph) for building sophisticated multi-agent workflows with conditional routing, parallel execution, and state management.

### Core Concepts

**StateGraph**: LangGraph's graph execution engine that passes state between nodes
**Nodes**: Execution points (agents, conditional logic, parallel execution)
**Edges**: Connections between nodes (direct or conditional)
**State**: Shared data structure passed between nodes
**Conditional Routing**: Dynamic path selection based on state

### BaseWorkflow

All workflows inherit from `BaseWorkflow` and implement `build_graph()`.

**Example - Custom Workflow:**

```python
from src.workflows import BaseWorkflow, WorkflowConfig, WorkflowState
from src.workflows.agent_graph import AgentGraph
from langgraph.graph import END

class CustomWorkflow(BaseWorkflow):
    def __init__(self):
        config = WorkflowConfig(
            name="Custom Workflow",
            description="My custom multi-agent workflow",
            version="1.0.0",
            timeout_seconds=600,
            max_retries=2,
            parallel_execution=True
        )
        super().__init__(config)

    def build_graph(self):
        # Create agent graph
        agent_graph = AgentGraph("custom_workflow")

        # Add agent nodes
        agent_graph.add_agent_node(
            name="research",
            agent_type="research",
            description="Research the topic"
        )

        agent_graph.add_agent_node(
            name="write",
            agent_type="writer",
            description="Write content based on research"
        )

        # Add edges
        agent_graph.add_edge("research", "write")
        agent_graph.add_edge("write", END)

        # Build and set entry point
        graph = agent_graph.build()
        graph.set_entry_point("research")

        return graph

# Use the workflow
workflow = CustomWorkflow()
result = await workflow.execute(
    input_data={"topic": "quantum computing basics"},
    workflow_id="custom_001"
)

print(f"Status: {result.status}")
print(f"Output: {result.output_data}")
print(f"Total Cost: ${result.total_cost}")
print(f"Duration: {result.execution_time_seconds}s")
```

### AgentGraph Builder

`AgentGraph` provides a fluent API for building LangGraph StateGraphs.

**Adding Agent Nodes:**

```python
from src.workflows.agent_graph import AgentGraph

agent_graph = AgentGraph("my_workflow")

# Add single agent node
agent_graph.add_agent_node(
    name="research",
    agent_type="research",
    description="Research the topic"
)

# Add multiple nodes
agent_graph.add_agent_node("code", "code", "Generate code")
agent_graph.add_agent_node("review", "code", "Review generated code")
```

**Adding Edges:**

```python
# Direct edge (always goes to next node)
agent_graph.add_edge("research", "code")
agent_graph.add_edge("code", "review")
agent_graph.add_edge("review", END)
```

**Conditional Routing:**

```python
def check_quality(state: Dict[str, Any]) -> str:
    """Route based on agent output"""
    workflow_state = WorkflowState(**state)

    review_result = workflow_state.agent_results.get("review", {})
    review_output = review_result.get("output", {})

    # Check if review found issues
    explanation = review_output.get("explanation", "")
    if any(word in explanation.lower() for word in ["issue", "problem", "bug"]):
        return "needs_fix"

    return "approved"

# Add conditional edge
agent_graph.add_conditional_edge(
    source="review",
    condition=check_quality,
    condition_map={
        "approved": END,
        "needs_fix": "fix"
    }
)
```

**Parallel Execution:**

```python
# Execute multiple agents in parallel
agent_graph.add_parallel_node(
    name="parallel_analysis",
    agent_types=["research", "data_analyst"],
    description="Research and analyze in parallel"
)

# Results aggregated in state.agent_results
agent_graph.add_edge("parallel_analysis", "planning")
```

**Conditional Nodes:**

```python
def evaluate_complexity(state: Dict[str, Any]) -> str:
    """Evaluate plan complexity"""
    workflow_state = WorkflowState(**state)
    plan = workflow_state.agent_results.get("planning", {})
    tasks = plan.get("output", {}).get("tasks", [])

    return "complex" if len(tasks) > 5 else "simple"

agent_graph.add_conditional_node(
    name="complexity_check",
    condition=evaluate_complexity,
    description="Route based on plan complexity"
)

agent_graph.add_conditional_edge(
    source="complexity_check",
    condition=evaluate_complexity,
    condition_map={
        "simple": "simple_execution",
        "complex": "complex_execution"
    }
)
```

### Pre-Built Workflow Templates

The system includes three production-ready workflow templates.

#### ResearchWriteWorkflow

Sequential workflow: Research → Write

**Use Case**: Generate well-researched content

```python
from src.workflows import ResearchWriteWorkflow

workflow = ResearchWriteWorkflow()
result = await workflow.execute(
    input_data={
        "topic": "advantages of microservices architecture",
        "depth": "deep",
        "content_type": "blog_post",
        "style": "professional"
    }
)

# Workflow automatically:
# 1. Research agent researches the topic
# 2. Writer agent creates content based on research
print(result.agent_results["research"]["output"]["findings"])
print(result.agent_results["write"]["output"]["content"])
```

#### CodeReviewWorkflow

Code generation with automatic review and fixes.

**Flow**: Generate → Review → (Conditionally) Fix

**Use Case**: Generate production-quality code

```python
from src.workflows import CodeReviewWorkflow

workflow = CodeReviewWorkflow()
result = await workflow.execute(
    input_data={
        "task_type": "generate",
        "language": "python",
        "requirements": """
        Create a REST API endpoint for user authentication
        with JWT tokens, rate limiting, and input validation.
        """
    }
)

# Workflow automatically:
# 1. Code agent generates code
# 2. Review agent checks for issues
# 3. If issues found, fix agent applies corrections
# 4. If no issues, workflow completes

code = result.agent_results["code_generation"]["output"]["code"]
review = result.agent_results["code_review"]["output"]

if "apply_fixes" in result.agent_results:
    fixed_code = result.agent_results["apply_fixes"]["output"]["code"]
    print(f"Code was fixed:\n{fixed_code}")
else:
    print(f"Code approved on first pass:\n{code}")
```

**Conditional Logic:**

```python
# Review decision function
def check_review_result(state: Dict[str, Any]) -> str:
    workflow_state = WorkflowState(**state)
    review = workflow_state.agent_results.get("code_review", {})

    # Check for error in review
    if review.get("error"):
        return "needs_fix"

    # Check explanation for issues
    explanation = review.get("output", {}).get("explanation", "")
    issue_keywords = ["issue", "problem", "bug", "error", "fix"]

    if any(word in explanation.lower() for word in issue_keywords):
        return "needs_fix"

    return "approved"
```

#### AnalysisPlanningWorkflow

Parallel analysis with conditional execution.

**Flow**: (Research + Analysis in Parallel) → Plan → (Conditionally) Execute

**Use Case**: Complex projects requiring thorough analysis

```python
from src.workflows import AnalysisPlanningWorkflow

workflow = AnalysisPlanningWorkflow()
result = await workflow.execute(
    input_data={
        "goal": "Build a scalable chat application",
        "data": {
            "expected_users": 100000,
            "concurrent_connections": 5000,
            "message_volume": "1M/day"
        }
    }
)

# Workflow automatically:
# 1. Research and data analysis run in PARALLEL
# 2. Planner creates execution plan
# 3. Routes to simple or complex execution based on plan size

research = result.agent_results["parallel_analysis"]["research"]["output"]
analysis = result.agent_results["parallel_analysis"]["data_analyst"]["output"]
plan = result.agent_results["planning"]["output"]

# Check which execution path was taken
if "simple_execution" in result.agent_results:
    print("Simple execution path")
else:
    print("Complex execution path (>5 tasks)")
```

**Complexity Routing:**

```python
def check_plan_complexity(state: Dict[str, Any]) -> str:
    workflow_state = WorkflowState(**state)
    plan = workflow_state.agent_results.get("planning", {})
    tasks = plan.get("output", {}).get("tasks", [])

    # Route based on task count
    return "complex" if len(tasks) > 5 else "simple"
```

### Workflow State Management

`WorkflowState` tracks execution state throughout the workflow.

**State Fields:**

```python
@dataclass
class WorkflowState:
    workflow_id: str                          # Unique workflow ID
    input_data: Dict[str, Any]                # Original input
    output_data: Optional[Dict[str, Any]]     # Final output
    agent_results: Dict[str, Any]             # Results from each agent
    current_node: Optional[str]               # Current execution node
    status: WorkflowStatus                    # PENDING/RUNNING/COMPLETED/FAILED
    error: Optional[str]                      # Error message if failed
    started_at: datetime                      # Start timestamp
    completed_at: Optional[datetime]          # Completion timestamp
    total_cost: float                         # Accumulated cost
    total_tokens: int                         # Accumulated tokens
    execution_time_seconds: Optional[float]   # Total duration
```

**Accessing State:**

```python
# In condition functions
def my_condition(state: Dict[str, Any]) -> str:
    workflow_state = WorkflowState(**state)

    # Access agent results
    research_output = workflow_state.agent_results.get("research", {})
    findings = research_output.get("output", {}).get("findings", [])

    # Access metadata
    print(f"Workflow ID: {workflow_state.workflow_id}")
    print(f"Current cost: ${workflow_state.total_cost}")
    print(f"Tokens used: {workflow_state.total_tokens}")

    # Make routing decision
    return "detailed" if len(findings) > 10 else "summary"
```

### Using Workflow Templates

**List Available Templates:**

```python
from src.workflows import list_workflow_templates

templates = list_workflow_templates()
for name, description in templates.items():
    print(f"{name}: {description}")

# Output:
# research_write: Research a topic then write content about it
# code_review: Generate code, review it, and apply fixes
# analysis_planning: Analyze data, create plan, and execute
```

**Get Template by Name:**

```python
from src.workflows import get_workflow_template

workflow = get_workflow_template("code_review")
result = await workflow.execute(
    input_data={
        "task_type": "generate",
        "language": "python",
        "requirements": "Create a binary search function"
    }
)
```

### Workflow Visualization

Visualize workflow graphs for debugging and documentation.

```python
from src.workflows import CodeReviewWorkflow

workflow = CodeReviewWorkflow()
graph = workflow.build_graph()

# Generate visualization
visualization = workflow.graph_builder.visualize()
print(visualization)
```

**Output:**

```
Workflow: code_review
Nodes: 3
Edges: 3

Graph Structure:
  code_generation (agent: code)
    └─> code_review (agent: code)
        ├─> [approved] END
        └─> [needs_fix] apply_fixes (agent: code)
            └─> END
```

### Advanced Workflow Patterns

**Multi-Stage Conditional Workflow:**

```python
class MultiStageWorkflow(BaseWorkflow):
    def build_graph(self):
        agent_graph = AgentGraph("multi_stage")

        # Stage 1: Initial research
        agent_graph.add_agent_node("initial_research", "research")

        # Stage 2: Depth decision
        def check_research_depth(state):
            results = WorkflowState(**state).agent_results["initial_research"]
            findings = results.get("output", {}).get("findings", [])
            return "deep_dive" if len(findings) < 5 else "proceed"

        agent_graph.add_conditional_edge(
            "initial_research",
            check_research_depth,
            {
                "deep_dive": "additional_research",
                "proceed": "planning"
            }
        )

        # Stage 3: Optional additional research
        agent_graph.add_agent_node("additional_research", "research")
        agent_graph.add_edge("additional_research", "planning")

        # Stage 4: Planning
        agent_graph.add_agent_node("planning", "planner")
        agent_graph.add_edge("planning", END)

        graph = agent_graph.build()
        graph.set_entry_point("initial_research")
        return graph
```

**Parallel Processing with Aggregation:**

```python
class ParallelAggregationWorkflow(BaseWorkflow):
    def build_graph(self):
        agent_graph = AgentGraph("parallel_aggregation")

        # Parallel stage
        agent_graph.add_parallel_node(
            "parallel_analysis",
            agent_types=["research", "data_analyst", "code"],
            description="Multi-faceted analysis"
        )

        # Aggregation stage
        agent_graph.add_agent_node(
            "aggregation",
            "planner",
            description="Synthesize results"
        )

        # Final output
        agent_graph.add_agent_node("writer", "writer")

        # Connect stages
        agent_graph.add_edge("parallel_analysis", "aggregation")
        agent_graph.add_edge("aggregation", "writer")
        agent_graph.add_edge("writer", END)

        graph = agent_graph.build()
        graph.set_entry_point("parallel_analysis")
        return graph
```

### Workflow Error Handling

Workflows automatically handle errors and retries.

```python
# Configure retry behavior
config = WorkflowConfig(
    name="Resilient Workflow",
    timeout_seconds=900,
    max_retries=3,           # Retry failed nodes up to 3 times
    retry_on_failure=True,   # Enable automatic retries
    parallel_execution=True
)

workflow = MyWorkflow(config)

# Execute with error handling
try:
    result = await workflow.execute(input_data=data)

    if result.status == WorkflowStatus.COMPLETED:
        print("Success!")
    elif result.status == WorkflowStatus.FAILED:
        print(f"Failed: {result.error}")

except TimeoutError:
    print("Workflow exceeded timeout")
except Exception as e:
    print(f"Unexpected error: {e}")
```

### Workflow Metrics

Track performance and costs across workflow execution.

```python
result = await workflow.execute(input_data=data)

# Execution metrics
print(f"Status: {result.status}")
print(f"Duration: {result.execution_time_seconds}s")
print(f"Total Cost: ${result.total_cost:.4f}")
print(f"Total Tokens: {result.total_tokens}")

# Per-agent metrics
for agent_name, agent_result in result.agent_results.items():
    output = agent_result.get("output", {})
    print(f"\n{agent_name}:")
    print(f"  Cost: ${agent_result.get('cost', 0):.4f}")
    print(f"  Tokens: {agent_result.get('tokens_used', 0)}")
    print(f"  Output keys: {list(output.keys())}")

# Workflow timeline
print(f"\nStarted: {result.started_at}")
print(f"Completed: {result.completed_at}")
```

### Integration with Database

Workflows can be linked to tasks for full persistence.

```python
from src.services.agent_service import AgentService

# Execute workflow and persist to database
async with db_session() as session:
    # Get agent for workflow
    agent = AgentService.get_agent_by_id(session, agent_id=1)

    # Execute via agent service (auto-persists)
    execution = await AgentService.execute_agent(
        session=session,
        agent_id=agent.id,
        input_data={
            "topic": "machine learning basics",
            "workflow": "research_write"
        },
        workflow_id="rw_001",
        task_id=123
    )

    # Execution record saved to database
    print(f"Execution ID: {execution.id}")
    print(f"Status: {execution.status}")
    print(f"Cost: ${execution.cost}")
```

## Agent Communication

The Multi-Agent Orchestrator includes a comprehensive inter-agent communication system for coordinating multi-agent workflows.

### Message Types

Agents can send different types of messages:

- **REQUEST** - Request for action or information (requires response)
- **RESPONSE** - Response to a request
- **BROADCAST** - Broadcast to all agents
- **NOTIFICATION** - One-way notification
- **ERROR** - Error message
- **TASK_ASSIGNMENT** - Task delegation

### Sending Messages

**Direct Message:**

```python
from src.services.agent_communication import AgentCommunicationService
from src.models.agent_message import MessageType, MessagePriority

# Send a message from agent 1 to agent 2
message = AgentCommunicationService.send_message(
    session=db,
    sender_agent_id=1,
    receiver_agent_id=2,
    content="Please analyze the authentication requirements",
    message_type=MessageType.REQUEST,
    priority=MessagePriority.HIGH,
    subject="Auth Requirements Analysis",
    payload={
        "requirements": ["JWT", "OAuth2", "MFA"],
        "deadline": "2024-01-15"
    },
    workflow_id="wf_auth_001",
    requires_response=True,
    response_timeout_seconds=300
)

print(f"Message {message.id} sent")
```

**Broadcast Message:**

```python
# Broadcast to all agents in a workflow
message = AgentCommunicationService.broadcast_message(
    session=db,
    sender_agent_id=1,
    content="Code review phase starting in 5 minutes",
    subject="Workflow Update",
    workflow_id="wf_project_001",
    priority=MessagePriority.NORMAL
)
```

**Send Response:**

```python
# Respond to a message
response = AgentCommunicationService.send_response(
    session=db,
    sender_agent_id=2,
    original_message_id=message.id,
    content="Analysis complete. Recommending JWT with refresh tokens.",
    payload={
        "recommendation": "JWT",
        "security_level": "high",
        "implementation_time": "2 weeks"
    }
)
```

### Message Threading

Group related messages into threads:

```python
import uuid

# Create a thread ID
thread_id = f"thread_{uuid.uuid4().hex[:8]}"

# Send initial message
msg1 = AgentCommunicationService.send_message(
    session=db,
    sender_agent_id=1,
    receiver_agent_id=2,
    content="What's the best database for this project?",
    thread_id=thread_id,
    requires_response=True
)

# Response in same thread
msg2 = AgentCommunicationService.send_response(
    session=db,
    sender_agent_id=2,
    original_message_id=msg1.id,
    content="I recommend PostgreSQL for ACID compliance"
)

# Get entire thread
thread_messages = AgentCommunicationService.get_thread(
    session=db,
    thread_id=thread_id
)

for msg in thread_messages:
    print(f"{msg.sender_agent_id}: {msg.content}")
```

### Reading Messages

**Get Inbox:**

```python
# Get all messages for an agent
inbox = AgentCommunicationService.get_inbox(
    session=db,
    agent_id=2,
    unread_only=False,
    limit=50
)

for message in inbox:
    print(f"From: Agent {message.sender_agent_id}")
    print(f"Subject: {message.subject}")
    print(f"Content: {message.content}")
    print(f"Status: {message.status}")
    print("---")
```

**Get Unread Messages:**

```python
# Get only unread messages
unread = AgentCommunicationService.get_inbox(
    session=db,
    agent_id=2,
    unread_only=True
)

print(f"You have {len(unread)} unread messages")
```

**Mark as Read:**

```python
# Mark message as read
AgentCommunicationService.mark_as_read(
    session=db,
    message_id=message.id,
    agent_id=2
)
```

### Message API Endpoints

**Send Message via API:**

```bash
curl -X POST http://localhost:8001/api/messages/send?sender_agent_id=1 \
  -H "Content-Type: application/json" \
  -d '{
    "receiver_agent_id": 2,
    "content": "Please review the authentication code",
    "message_type": "request",
    "priority": "high",
    "subject": "Code Review Request",
    "requires_response": true,
    "workflow_id": "wf_001"
  }'
```

**Get Inbox via API:**

```bash
# Get all messages
curl http://localhost:8001/api/messages/inbox/2

# Get unread only
curl http://localhost:8001/api/messages/inbox/2?unread_only=true
```

**Send Response via API:**

```bash
curl -X POST http://localhost:8001/api/messages/respond/123?sender_agent_id=2 \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Review complete. Code looks good!",
    "payload": {
      "status": "approved",
      "issues_found": 0
    }
  }'
```

**Broadcast via API:**

```bash
curl -X POST "http://localhost:8001/api/messages/broadcast?sender_agent_id=1&content=Workflow%20complete&priority=normal"
```

**Get Thread via API:**

```bash
curl http://localhost:8001/api/messages/thread/thread_abc123
```

**Mark as Read via API:**

```bash
curl -X PATCH "http://localhost:8001/api/messages/123/read?agent_id=2"
```

**Get Message Statistics:**

```bash
# Overall statistics
curl http://localhost:8001/api/messages/statistics

# Agent-specific statistics
curl http://localhost:8001/api/messages/statistics?agent_id=2

# Workflow-specific statistics
curl http://localhost:8001/api/messages/statistics?workflow_id=wf_001
```

### Workflow Integration

Agents can communicate during workflow execution:

```python
from src.workflows import BaseWorkflow, WorkflowConfig, WorkflowState
from src.workflows.agent_graph import AgentGraph
from src.services.agent_communication import AgentCommunicationService
from langgraph.graph import END

class CollaborativeWorkflow(BaseWorkflow):
    """Workflow with agent communication"""

    def __init__(self):
        config = WorkflowConfig(
            name="Collaborative Workflow",
            description="Agents communicate during execution"
        )
        super().__init__(config)

    def build_graph(self):
        agent_graph = AgentGraph("collaborative")

        # Research agent sends findings to code agent
        agent_graph.add_agent_node("research", "research")
        agent_graph.add_agent_node("code", "code")

        # Custom node to send message
        async def send_research_results(state):
            workflow_state = WorkflowState(**state)
            research_output = workflow_state.agent_results.get("research", {})

            # Send message from research agent to code agent
            with db_session() as db:
                message = AgentCommunicationService.send_message(
                    session=db,
                    sender_agent_id=1,  # Research agent
                    receiver_agent_id=2,  # Code agent
                    content="Research complete. Key findings attached.",
                    message_type=MessageType.NOTIFICATION,
                    payload=research_output.get("output"),
                    workflow_id=workflow_state.workflow_id
                )
                db.commit()

            return state

        agent_graph.graph.add_node("send_message", send_research_results)
        agent_graph.add_edge("research", "send_message")
        agent_graph.add_edge("send_message", "code")
        agent_graph.add_edge("code", END)

        graph = agent_graph.build()
        graph.set_entry_point("research")
        return graph
```

### Message Priorities

Messages support four priority levels:

- **LOW** - Background notifications
- **NORMAL** - Standard communication (default)
- **HIGH** - Important requests requiring attention
- **URGENT** - Critical messages requiring immediate response

Agents can process high-priority messages first:

```python
# Get high-priority messages
high_priority = AgentCommunicationService.get_messages(
    session=db,
    agent_id=2,
    priority=MessagePriority.HIGH,
    unread_only=True
)
```

### Message Expiration

Set expiration times for time-sensitive messages:

```python
# Message expires in 1 hour
message = AgentCommunicationService.send_message(
    session=db,
    sender_agent_id=1,
    receiver_agent_id=2,
    content="Please respond within 1 hour",
    expires_in_seconds=3600  # 1 hour
)

# Clean up expired messages
deleted_count = AgentCommunicationService.delete_expired_messages(session=db)
print(f"Deleted {deleted_count} expired messages")
```

### Communication Patterns

**Request-Response Pattern:**

```python
# Agent 1 requests information
request = AgentCommunicationService.send_message(
    session=db,
    sender_agent_id=1,
    receiver_agent_id=2,
    content="What database schema do you recommend?",
    message_type=MessageType.REQUEST,
    requires_response=True,
    response_timeout_seconds=300
)

# Agent 2 responds
response = AgentCommunicationService.send_response(
    session=db,
    sender_agent_id=2,
    original_message_id=request.id,
    content="I recommend a normalized schema with...",
    payload={"schema": "..."}
)

# Check if response received
if request.response_received:
    print("Request answered!")
```

**Task Delegation Pattern:**

```python
# Coordinator delegates task to specialist
delegation = AgentCommunicationService.send_message(
    session=db,
    sender_agent_id=1,  # Coordinator
    receiver_agent_id=3,  # Specialist
    content="Please implement user authentication",
    message_type=MessageType.TASK_ASSIGNMENT,
    priority=MessagePriority.HIGH,
    payload={
        "task_id": 123,
        "requirements": ["JWT", "OAuth2"],
        "deadline": "2024-01-20"
    },
    requires_response=True
)
```

**Broadcast Notification Pattern:**

```python
# Workflow coordinator broadcasts status update
broadcast = AgentCommunicationService.broadcast_message(
    session=db,
    sender_agent_id=1,
    content="Phase 1 complete. Starting Phase 2.",
    subject="Workflow Progress Update",
    workflow_id="wf_project_001",
    payload={
        "phase": 2,
        "completion_percentage": 33,
        "next_milestone": "Code review"
    }
)
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

#### 8. Workflow Template APIs

```bash
# List all available workflow templates
curl http://localhost:8001/api/workflows/templates

# Get template information
curl http://localhost:8001/api/workflows/templates/research_write

# Execute a workflow template
curl -X POST http://localhost:8001/api/workflows/templates/research_write/execute \
  -H "Content-Type: application/json" \
  -d '{
    "input_data": {
      "topic": "microservices architecture",
      "depth": "deep",
      "content_type": "blog_post",
      "style": "professional"
    },
    "workflow_id": "wf_001"
  }'

# Execute code review workflow
curl -X POST http://localhost:8001/api/workflows/templates/code_review/execute \
  -H "Content-Type: application/json" \
  -d '{
    "input_data": {
      "task_type": "generate",
      "language": "python",
      "requirements": "Create a binary search function with tests"
    }
  }'

# Execute analysis planning workflow
curl -X POST http://localhost:8001/api/workflows/templates/analysis_planning/execute \
  -H "Content-Type: application/json" \
  -d '{
    "input_data": {
      "goal": "Build a real-time chat application",
      "data": {
        "expected_users": 50000,
        "concurrent_connections": 2000
      }
    }
  }'
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

#### Workflow 4: Using LangGraph Templates

```python
import requests

BASE_URL = "http://localhost:8001/api"

# 1. List available workflow templates
templates = requests.get(f"{BASE_URL}/workflows/templates").json()
print(f"Available templates: {list(templates['templates'].keys())}")

# 2. Execute ResearchWrite workflow
research_write_result = requests.post(
    f"{BASE_URL}/workflows/templates/research_write/execute",
    json={
        "input_data": {
            "topic": "quantum computing applications in cryptography",
            "depth": "deep",
            "focus_areas": ["quantum key distribution", "post-quantum cryptography"],
            "content_type": "technical_article",
            "style": "technical",
            "audience": "security professionals"
        },
        "workflow_id": "rw_quantum_crypto_001"
    }
).json()

print(f"Workflow ID: {research_write_result['workflow_id']}")
print(f"Status: {research_write_result['status']}")
print(f"Total Cost: ${research_write_result['total_cost']:.4f}")
print(f"Execution Time: {research_write_result['execution_time_seconds']}s")

# Access agent results
research_output = research_write_result['agent_results']['research']['output']
write_output = research_write_result['agent_results']['write']['output']

print(f"\nResearch Findings: {len(research_output['findings'])} key points")
print(f"Article Word Count: {write_output['word_count']}")
print(f"Article Preview:\n{write_output['content'][:200]}...")

# 3. Execute CodeReview workflow
code_review_result = requests.post(
    f"{BASE_URL}/workflows/templates/code_review/execute",
    json={
        "input_data": {
            "task_type": "generate",
            "language": "python",
            "requirements": """
            Create a REST API endpoint for file uploads with:
            - Size validation (max 10MB)
            - Type validation (images only)
            - Async processing
            - S3 storage integration
            - Progress tracking
            """
        }
    }
).json()

# Check if code was fixed
if "apply_fixes" in code_review_result['agent_results']:
    print("Code was reviewed and fixed automatically")
    fixed_code = code_review_result['agent_results']['apply_fixes']['output']['code']
else:
    print("Code passed review on first attempt")
    fixed_code = code_review_result['agent_results']['code_generation']['output']['code']

print(f"\nFinal Code:\n{fixed_code}")

# 4. Execute AnalysisPlanning workflow
analysis_result = requests.post(
    f"{BASE_URL}/workflows/templates/analysis_planning/execute",
    json={
        "input_data": {
            "goal": "Build a distributed task queue system",
            "data": {
                "expected_tasks_per_second": 10000,
                "task_types": ["email", "pdf_generation", "data_sync"],
                "max_task_duration": "5 minutes",
                "budget": "$30,000"
            },
            "constraints": [
                "Must support priority queues",
                "Need dead letter queues",
                "Require visibility into queue depths"
            ]
        }
    }
).json()

# Check execution path
plan = analysis_result['agent_results']['planning']['output']
if "simple_execution" in analysis_result['agent_results']:
    print(f"Simple execution path (plan has {len(plan['tasks'])} tasks)")
else:
    print(f"Complex execution path (plan has {len(plan['tasks'])} tasks)")

print(f"\nParallel Analysis Results:")
print(f"- Research insights: {len(analysis_result['agent_results']['parallel_analysis']['research']['output']['findings'])}")
print(f"- Data analysis insights: {len(analysis_result['agent_results']['parallel_analysis']['data_analyst']['output']['insights'])}")
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

## Agent Orchestration

The orchestration service coordinates multiple agents to work together on complex tasks using different execution patterns.

### Orchestration Patterns

The system supports five orchestration patterns:

1. **Sequential**: Agents execute one after another in sequence
2. **Parallel**: Agents execute simultaneously in parallel
3. **Hierarchical**: Supervisor agent delegates tasks to worker agents
4. **Pipeline**: Output of one agent feeds into the next agent
5. **Broadcast**: Same task distributed to all agents

### Agent Discovery

Find available agents based on role, capabilities, and status:

```bash
# Discover all available agents
curl -X POST http://localhost:8001/api/orchestration/discover \
  -H "Content-Type: application/json" \
  -d '{
    "status": "idle",
    "limit": 10
  }'

# Discover agents by role
curl -X POST http://localhost:8001/api/orchestration/discover \
  -H "Content-Type: application/json" \
  -d '{
    "role": "worker",
    "status": "idle",
    "limit": 5
  }'

# Discover agents by capabilities
curl -X POST http://localhost:8001/api/orchestration/discover \
  -H "Content-Type: application/json" \
  -d '{
    "capabilities": ["code_analysis", "testing"],
    "status": "idle"
  }'
```

Response:
```json
{
  "agents": [
    {
      "id": 1,
      "name": "worker-agent-1",
      "role": "worker",
      "status": "idle",
      "capabilities": ["code_analysis", "testing"],
      "successful_tasks": 42,
      "average_response_time": 1.5
    }
  ],
  "count": 1
}
```

### Task Assignment

Assign a task to a specific agent:

```bash
curl -X POST http://localhost:8001/api/orchestration/assign \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 1,
    "agent_id": 2,
    "priority": "high",
    "context": {
      "deadline": "2024-01-15",
      "requires_review": true
    }
  }'
```

Response:
```json
{
  "execution": {
    "id": 10,
    "agent_id": 2,
    "task_id": 1,
    "status": "assigned",
    "started_at": "2024-01-10T10:00:00"
  },
  "message": {
    "id": 25,
    "message_type": "task_assignment",
    "priority": "high",
    "content": "Task assigned: Implement feature X"
  }
}
```

### Sequential Orchestration

Execute tasks one after another:

```bash
curl -X POST http://localhost:8001/api/orchestration/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": [1, 2, 3],
    "pattern": "sequential",
    "workflow_id": "workflow-123",
    "auto_assign": true
  }'
```

Response:
```json
{
  "pattern": "sequential",
  "task_count": 3,
  "execution_count": 3,
  "executions": [
    {
      "id": 10,
      "agent_id": 1,
      "task_id": 1,
      "status": "assigned"
    },
    {
      "id": 11,
      "agent_id": 2,
      "task_id": 2,
      "status": "assigned"
    },
    {
      "id": 12,
      "agent_id": 3,
      "task_id": 3,
      "status": "assigned"
    }
  ]
}
```

Features:
- Tasks execute in order with each task receiving the previous task's result
- Context includes `previous_execution_id` and `previous_result`
- Perfect for workflows where each step depends on the previous one

### Parallel Orchestration

Execute tasks simultaneously:

```bash
curl -X POST http://localhost:8001/api/orchestration/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": [4, 5, 6],
    "pattern": "parallel",
    "workflow_id": "workflow-124",
    "auto_assign": true
  }'
```

Response:
```json
{
  "pattern": "parallel",
  "task_count": 3,
  "execution_count": 3,
  "executions": [
    {
      "id": 13,
      "agent_id": 1,
      "task_id": 4,
      "status": "assigned"
    },
    {
      "id": 14,
      "agent_id": 2,
      "task_id": 5,
      "status": "assigned"
    },
    {
      "id": 15,
      "agent_id": 3,
      "task_id": 6,
      "status": "assigned"
    }
  ]
}
```

Features:
- All tasks start simultaneously
- Each agent works independently
- Context includes `task_ids` of all parallel tasks
- Ideal for independent tasks that can run concurrently

### Hierarchical Orchestration

Supervisor delegates to workers:

```bash
curl -X POST http://localhost:8001/api/orchestration/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": [7, 8, 9],
    "pattern": "hierarchical",
    "workflow_id": "workflow-125",
    "supervisor_agent_id": 1
  }'
```

Response:
```json
{
  "pattern": "hierarchical",
  "supervisor": {
    "id": 1,
    "name": "supervisor-agent",
    "role": "supervisor"
  },
  "worker_count": 3,
  "workers": [
    {
      "id": 2,
      "name": "worker-1",
      "role": "worker"
    },
    {
      "id": 3,
      "name": "worker-2",
      "role": "worker"
    },
    {
      "id": 4,
      "name": "worker-3",
      "role": "worker"
    }
  ],
  "execution_count": 3,
  "executions": [
    {
      "id": 16,
      "agent_id": 2,
      "task_id": 7,
      "status": "assigned"
    },
    {
      "id": 17,
      "agent_id": 3,
      "task_id": 8,
      "status": "assigned"
    },
    {
      "id": 18,
      "agent_id": 4,
      "task_id": 9,
      "status": "assigned"
    }
  ]
}
```

Features:
- Supervisor agent coordinates worker agents
- Workers send notifications to supervisor
- Context includes `supervisor_agent_id`
- Perfect for complex workflows requiring coordination

### Result Aggregation

Aggregate results from multiple executions:

```bash
# Collect all results
curl -X POST http://localhost:8001/api/orchestration/aggregate \
  -H "Content-Type: application/json" \
  -d '{
    "execution_ids": [10, 11, 12],
    "strategy": "collect"
  }'

# Merge results into single dictionary
curl -X POST http://localhost:8001/api/orchestration/aggregate \
  -H "Content-Type: application/json" \
  -d '{
    "execution_ids": [13, 14, 15],
    "strategy": "merge"
  }'

# Majority voting (for classification)
curl -X POST http://localhost:8001/api/orchestration/aggregate \
  -H "Content-Type: application/json" \
  -d '{
    "execution_ids": [16, 17, 18],
    "strategy": "vote"
  }'

# Average numeric results
curl -X POST http://localhost:8001/api/orchestration/aggregate \
  -H "Content-Type: application/json" \
  -d '{
    "execution_ids": [19, 20, 21],
    "strategy": "average"
  }'
```

Aggregation strategies:

**Collect**: Returns all results in a list
```json
{
  "strategy": "collect",
  "count": 3,
  "results": [
    {"result": "success", "data": "..."},
    {"result": "success", "data": "..."},
    {"result": "success", "data": "..."}
  ]
}
```

**Merge**: Merges all dictionaries into one
```json
{
  "strategy": "merge",
  "count": 3,
  "result": {
    "key1": "value1",
    "key2": "value2",
    "key3": "value3"
  }
}
```

**Vote**: Majority voting
```json
{
  "strategy": "vote",
  "count": 5,
  "winner": "category_A",
  "votes": {
    "category_A": 3,
    "category_B": 2
  }
}
```

**Average**: Average of numeric values
```json
{
  "strategy": "average",
  "count": 3,
  "average": 42.5,
  "min": 40.0,
  "max": 45.0
}
```

### Orchestration Status

Check orchestration status for a workflow:

```bash
curl http://localhost:8001/api/orchestration/status/workflow-123
```

Response:
```json
{
  "workflow_id": "workflow-123",
  "orchestrations": [
    {
      "pattern": "sequential",
      "task_count": 3,
      "execution_count": 3,
      "execution_statuses": {
        "assigned": 1,
        "running": 1,
        "completed": 1
      },
      "started_at": "2024-01-10T10:00:00",
      "metadata": {
        "pattern": "sequential",
        "task_ids": [1, 2, 3],
        "execution_ids": [10, 11, 12]
      }
    }
  ]
}
```

### List Orchestration Patterns

Get all available orchestration patterns:

```bash
curl http://localhost:8001/api/orchestration/patterns
```

Response:
```json
{
  "patterns": [
    {
      "name": "sequential",
      "description": "Agents execute one after another in sequence"
    },
    {
      "name": "parallel",
      "description": "Agents execute simultaneously in parallel"
    },
    {
      "name": "hierarchical",
      "description": "Supervisor agent delegates tasks to worker agents"
    },
    {
      "name": "pipeline",
      "description": "Output of one agent feeds into the next agent"
    },
    {
      "name": "broadcast",
      "description": "Same task distributed to all agents"
    }
  ]
}
```

### Orchestration Use Cases

**Sequential Pattern**:
- Data processing pipeline
- Multi-step workflow where each step depends on previous
- Code generation → Testing → Deployment

**Parallel Pattern**:
- Independent task execution
- Batch processing
- Multiple data sources analysis

**Hierarchical Pattern**:
- Complex project management
- Supervisor coordinates multiple teams
- Quality control with review hierarchy

**Pipeline Pattern**:
- ETL workflows
- Data transformation chains
- Multi-stage processing

**Broadcast Pattern**:
- Same task to multiple agents for consensus
- Distributed testing
- Redundancy for critical tasks

## Execution Management

The execution management system handles task queues, execution lifecycle, error recovery, and monitoring for agent executions.

### Task Queue Management

#### Enqueue a Task

Add a task to an agent's queue:

```bash
curl -X POST http://localhost:8001/api/executions/enqueue \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "task_id": 5,
    "priority": 10,
    "scheduled_at": "2024-01-15T10:00:00Z",
    "context": {
      "retry_limit": 3,
      "timeout_seconds": 300
    }
  }'
```

Response:
```json
{
  "id": 42,
  "agent_id": 1,
  "task_id": 5,
  "status": "queued",
  "priority": 10,
  "scheduled_at": "2024-01-15T10:00:00",
  "created_at": "2024-01-10T09:00:00"
}
```

Features:
- **Priority-based scheduling**: Higher priority tasks execute first
- **Scheduled execution**: Tasks can be scheduled for future execution
- **Context passing**: Additional context data for execution

#### Get Next Task

Get the next task from an agent's queue:

```bash
curl http://localhost:8001/api/executions/next/1
```

Response:
```json
{
  "execution": {
    "id": 42,
    "agent_id": 1,
    "task_id": 5,
    "status": "queued",
    "priority": 10,
    "scheduled_at": "2024-01-15T10:00:00",
    "created_at": "2024-01-10T09:00:00",
    "task": {
      "id": 5,
      "title": "Process data batch",
      "description": "Process batch of 1000 records"
    }
  }
}
```

Queue prioritization:
1. Priority (descending)
2. Scheduled time (ascending)
3. Creation time (ascending)

#### View Agent Queue

Get all tasks in an agent's queue:

```bash
# Active tasks only
curl http://localhost:8001/api/executions/queue/1

# Include completed tasks
curl http://localhost:8001/api/executions/queue/1?include_completed=true&limit=50
```

Response:
```json
{
  "agent_id": 1,
  "count": 5,
  "executions": [
    {
      "id": 42,
      "task_id": 5,
      "status": "queued",
      "priority": 10,
      "attempts": 0,
      "created_at": "2024-01-10T09:00:00",
      "task_title": "Process data batch"
    },
    {
      "id": 43,
      "task_id": 6,
      "status": "running",
      "priority": 5,
      "attempts": 1,
      "started_at": "2024-01-10T09:15:00",
      "task_title": "Generate report"
    }
  ]
}
```

### Execution Lifecycle

#### Start Execution

Start a queued or paused execution:

```bash
curl -X POST http://localhost:8001/api/executions/start/42
```

Response:
```json
{
  "id": 42,
  "agent_id": 1,
  "task_id": 5,
  "status": "running",
  "started_at": "2024-01-10T10:00:00",
  "attempts": 1
}
```

Automatic updates:
- Agent status → BUSY
- Task status → IN_PROGRESS
- Execution attempts incremented

#### Complete Execution

Mark execution as successfully completed:

```bash
curl -X POST http://localhost:8001/api/executions/complete \
  -H "Content-Type: application/json" \
  -d '{
    "execution_id": 42,
    "output_data": {
      "records_processed": 1000,
      "errors": 0,
      "result": "success"
    },
    "metrics": {
      "processing_time_ms": 5432,
      "memory_used_mb": 128
    }
  }'
```

Response:
```json
{
  "id": 42,
  "status": "completed",
  "completed_at": "2024-01-10T10:05:32",
  "metrics": {
    "processing_time_ms": 5432,
    "memory_used_mb": 128,
    "duration_seconds": 332
  },
  "output_data": {
    "records_processed": 1000,
    "errors": 0,
    "result": "success"
  }
}
```

Automatic updates:
- Agent status → IDLE
- Agent successful_tasks incremented
- Agent average_response_time updated
- Task status → COMPLETED

#### Fail Execution

Mark execution as failed with automatic retry:

```bash
curl -X POST http://localhost:8001/api/executions/fail \
  -H "Content-Type: application/json" \
  -d '{
    "execution_id": 42,
    "error": "Database connection timeout",
    "error_details": {
      "error_code": "DB_TIMEOUT",
      "timeout_seconds": 30,
      "retry_recommended": true
    },
    "retry": true
  }'
```

Response:
```json
{
  "id": 42,
  "status": "failed",
  "error_message": "Database connection timeout",
  "error_details": {
    "error_code": "DB_TIMEOUT",
    "timeout_seconds": 30,
    "retry_recommended": true
  },
  "retry_created": true,
  "retry_execution": {
    "id": 50,
    "status": "queued",
    "scheduled_at": "2024-01-10T10:10:00"
  }
}
```

Retry logic:
- Maximum 3 attempts per task
- Retry execution created with context from failed attempt
- Previous error included in retry context
- Task status updated to PENDING for retry

#### Pause Execution

Pause a running execution:

```bash
curl -X POST http://localhost:8001/api/executions/pause/42?reason=User%20requested%20pause
```

Response:
```json
{
  "id": 42,
  "status": "paused",
  "reason": "User requested pause"
}
```

#### Resume Execution

Resume a paused execution:

```bash
curl -X POST http://localhost:8001/api/executions/resume/42
```

Response:
```json
{
  "id": 42,
  "status": "running"
}
```

#### Cancel Execution

Cancel a queued, running, or paused execution:

```bash
curl -X POST http://localhost:8001/api/executions/cancel \
  -H "Content-Type: application/json" \
  -d '{
    "execution_id": 42,
    "reason": "Task no longer needed"
  }'
```

Response:
```json
{
  "id": 42,
  "status": "cancelled",
  "reason": "Task no longer needed"
}
```

### Execution Monitoring

#### Get Execution Details

Get detailed information about an execution:

```bash
curl http://localhost:8001/api/executions/42
```

Response:
```json
{
  "id": 42,
  "agent_id": 1,
  "task_id": 5,
  "status": "completed",
  "priority": 10,
  "attempts": 1,
  "input_data": {
    "retry_limit": 3,
    "timeout_seconds": 300
  },
  "output_data": {
    "records_processed": 1000,
    "result": "success"
  },
  "metrics": {
    "duration_seconds": 332,
    "processing_time_ms": 5432
  },
  "error_message": null,
  "error_details": null,
  "created_at": "2024-01-10T09:00:00",
  "started_at": "2024-01-10T10:00:00",
  "completed_at": "2024-01-10T10:05:32",
  "scheduled_at": "2024-01-15T10:00:00"
}
```

#### Get Execution Metrics

Get aggregated metrics across executions:

```bash
# All executions in last 24 hours
curl http://localhost:8001/api/executions/metrics

# Agent-specific metrics
curl http://localhost:8001/api/executions/metrics?agent_id=1&time_range_hours=168

# Task-specific metrics
curl http://localhost:8001/api/executions/metrics?task_id=5&time_range_hours=72
```

Response:
```json
{
  "total_executions": 150,
  "by_status": {
    "completed": 120,
    "failed": 15,
    "running": 10,
    "queued": 5
  },
  "success_rate": 0.8,
  "failure_rate": 0.1,
  "average_duration_seconds": 245.5,
  "min_duration_seconds": 10.2,
  "max_duration_seconds": 1200.0,
  "time_range_hours": 24,
  "agent_id": 1,
  "task_id": null
}
```

### Error Recovery

#### Find Stuck Executions

Identify executions running longer than expected:

```bash
# Find executions running > 1 hour
curl http://localhost:8001/api/executions/stuck?timeout_hours=1

# Find executions running > 6 hours
curl http://localhost:8001/api/executions/stuck?timeout_hours=6
```

Response:
```json
{
  "count": 2,
  "executions": [
    {
      "id": 45,
      "agent_id": 2,
      "task_id": 8,
      "started_at": "2024-01-10T08:00:00",
      "attempts": 1
    },
    {
      "id": 48,
      "agent_id": 3,
      "task_id": 10,
      "started_at": "2024-01-10T07:30:00",
      "attempts": 2
    }
  ]
}
```

#### Recover Stuck Executions

Automatically recover stuck executions:

```bash
curl -X POST http://localhost:8001/api/executions/recover-stuck?timeout_hours=1
```

Response:
```json
{
  "recovered_count": 2,
  "retry_executions": [
    {
      "id": 51,
      "agent_id": 2,
      "task_id": 8,
      "status": "queued"
    },
    {
      "id": 52,
      "agent_id": 3,
      "task_id": 10,
      "status": "queued"
    }
  ]
}
```

Recovery process:
1. Mark stuck execution as FAILED with timeout error
2. Create retry execution if attempts < 3
3. Free up agent to process new tasks
4. Log warning for monitoring

### Cleanup and Maintenance

#### Clean Up Old Executions

Remove completed/failed executions older than specified days:

```bash
# Delete executions older than 30 days
curl -X POST http://localhost:8001/api/executions/cleanup?days_old=30

# Delete executions older than 90 days
curl -X POST http://localhost:8001/api/executions/cleanup?days_old=90
```

Response:
```json
{
  "deleted": 450
}
```

Cleanup behavior:
- Only deletes COMPLETED, FAILED, CANCELLED executions
- Preserves QUEUED, RUNNING, PAUSED executions
- Helps maintain database performance

### Execution States

The execution lifecycle supports these states:

1. **QUEUED**: Task in queue, waiting to start
2. **ASSIGNED**: Task assigned to agent (via orchestration)
3. **RUNNING**: Task currently executing
4. **PAUSED**: Task temporarily suspended
5. **COMPLETED**: Task finished successfully
6. **FAILED**: Task failed (may retry)
7. **CANCELLED**: Task cancelled by user

### Best Practices

**Queue Management**:
- Use priority for time-sensitive tasks
- Schedule non-urgent tasks during off-peak hours
- Monitor queue depth to prevent bottlenecks

**Error Handling**:
- Set appropriate retry limits in context
- Include detailed error information for debugging
- Use error codes for categorization

**Monitoring**:
- Check execution metrics regularly
- Set up alerts for high failure rates
- Monitor stuck executions proactively

**Cleanup**:
- Run cleanup regularly (daily/weekly)
- Adjust retention period based on storage capacity
- Archive important execution data before cleanup

## Agent Analytics

The analytics system provides comprehensive performance tracking, metrics aggregation, and insights into agent effectiveness.

### Agent Performance Metrics

Get detailed performance metrics for a specific agent:

```bash
# Last 24 hours
curl http://localhost:8001/api/analytics/performance/1

# Last 7 days
curl http://localhost:8001/api/analytics/performance/1?time_range_hours=168
```

Response:
```json
{
  "agent_id": 1,
  "agent_name": "worker-agent-1",
  "agent_role": "worker",
  "agent_status": "idle",
  "time_range_hours": 24,

  "total_executions": 150,
  "executions_by_status": {
    "completed": 120,
    "failed": 15,
    "running": 10,
    "queued": 5
  },

  "success_rate": 0.8,
  "failure_rate": 0.1,
  "completed_count": 120,
  "failed_count": 15,

  "duration_metrics": {
    "average_duration_seconds": 245.5,
    "min_duration_seconds": 10.2,
    "max_duration_seconds": 1200.0,
    "median_duration_seconds": 180.0
  },

  "total_retries": 8,
  "average_attempts": 1.05,

  "lifetime_successful_tasks": 1250,
  "lifetime_failed_tasks": 150,
  "lifetime_total_tasks": 1400,
  "lifetime_success_rate": 0.893,

  "average_response_time": 240.3,
  "current_task_id": null,
  "last_active": "2024-01-10T15:30:00",
  "created_at": "2024-01-01T00:00:00"
}
```

Metrics include:
- **Execution counts**: Total, by status
- **Success rates**: Current period and lifetime
- **Duration statistics**: Average, min, max, median
- **Retry analysis**: Total retries, average attempts
- **Agent info**: Response time, activity timestamps

### Agent Ranking

Rank agents by various performance metrics:

```bash
# Rank by success rate
curl http://localhost:8001/api/analytics/ranking?metric=success_rate&limit=10

# Rank by speed (fastest agents)
curl http://localhost:8001/api/analytics/ranking?metric=speed&limit=5

# Rank by total tasks
curl http://localhost:8001/api/analytics/ranking?metric=total_tasks

# Rank by reliability (success rate * low retry rate)
curl http://localhost:8001/api/analytics/ranking?metric=reliability

# Filter by role
curl http://localhost:8001/api/analytics/ranking?metric=success_rate&role=worker
```

Response:
```json
{
  "metric": "success_rate",
  "role": null,
  "time_range_hours": 24,
  "count": 5,
  "ranking": [
    {
      "rank": 1,
      "agent_id": 3,
      "agent_name": "worker-agent-3",
      "success_rate": 0.95,
      "total_executions": 100,
      "duration_metrics": {
        "average_duration_seconds": 200.0
      }
    },
    {
      "rank": 2,
      "agent_id": 1,
      "agent_name": "worker-agent-1",
      "success_rate": 0.90,
      "total_executions": 150
    }
  ]
}
```

Available metrics:
- **success_rate**: Highest completion rate
- **speed**: Fastest average execution time
- **total_tasks**: Most active agents
- **lifetime_success_rate**: All-time success rate
- **reliability**: Combined success rate and retry rate

### Agent Comparison

Compare performance of multiple agents side-by-side:

```bash
curl -X POST http://localhost:8001/api/analytics/compare \
  -H "Content-Type: application/json" \
  -d '{
    "agent_ids": [1, 2, 3],
    "time_range_hours": 24
  }'
```

Response:
```json
{
  "time_range_hours": 24,
  "agent_count": 3,
  "comparisons": [
    {
      "agent_id": 1,
      "agent_name": "worker-agent-1",
      "success_rate": 0.8,
      "total_executions": 150,
      "duration_metrics": {
        "average_duration_seconds": 245.5
      }
    },
    {
      "agent_id": 2,
      "agent_name": "worker-agent-2",
      "success_rate": 0.85,
      "total_executions": 120
    },
    {
      "agent_id": 3,
      "agent_name": "worker-agent-3",
      "success_rate": 0.95,
      "total_executions": 100
    }
  ],
  "best_success_rate": {
    "agent_id": 3,
    "agent_name": "worker-agent-3",
    "success_rate": 0.95
  },
  "best_speed": {
    "agent_id": 2,
    "agent_name": "worker-agent-2",
    "average_duration_seconds": 200.0
  },
  "most_active": {
    "agent_id": 1,
    "agent_name": "worker-agent-1",
    "total_executions": 150
  }
}
```

Comparison highlights:
- Side-by-side performance metrics
- Best performer in each category
- Easy identification of strengths/weaknesses

### Execution Trends

Track execution trends over time:

```bash
# Daily trends for last 7 days
curl http://localhost:8001/api/analytics/trends?time_range_hours=168&interval_hours=24

# Hourly trends for last 24 hours
curl http://localhost:8001/api/analytics/trends?time_range_hours=24&interval_hours=1

# Agent-specific trends
curl http://localhost:8001/api/analytics/trends?agent_id=1&time_range_hours=168

# Role-based trends
curl http://localhost:8001/api/analytics/trends?role=worker&time_range_hours=168
```

Response:
```json
{
  "time_range_hours": 168,
  "interval_hours": 24,
  "bucket_count": 7,
  "agent_id": null,
  "role": null,
  "trends": [
    {
      "period_start": "2024-01-04T00:00:00",
      "period_end": "2024-01-05T00:00:00",
      "total_executions": 150,
      "completed": 120,
      "failed": 15,
      "success_rate": 0.8
    },
    {
      "period_start": "2024-01-05T00:00:00",
      "period_end": "2024-01-06T00:00:00",
      "total_executions": 180,
      "completed": 150,
      "failed": 12,
      "success_rate": 0.833
    }
  ]
}
```

Use cases:
- Identify performance trends
- Spot degradation early
- Validate optimization impact
- Capacity planning

### Task Distribution

Analyze task distribution across various dimensions:

```bash
# Overall distribution
curl http://localhost:8001/api/analytics/distribution

# Agent-specific distribution
curl http://localhost:8001/api/analytics/distribution?agent_id=1

# Custom time range
curl http://localhost:8001/api/analytics/distribution?time_range_hours=168
```

Response:
```json
{
  "time_range_hours": 24,
  "total_executions": 150,
  "by_status": {
    "completed": 120,
    "failed": 15,
    "running": 10,
    "queued": 5
  },
  "by_priority": {
    "0": 50,
    "5": 60,
    "10": 40
  },
  "by_agent": {
    "worker-agent-1": 80,
    "worker-agent-2": 40,
    "worker-agent-3": 30
  },
  "by_attempts": {
    "1_attempts": 135,
    "2_attempts": 10,
    "3_attempts": 5
  }
}
```

Distributions:
- **by_status**: Execution state breakdown
- **by_priority**: Priority level distribution
- **by_agent**: Workload per agent
- **by_attempts**: Retry pattern analysis

### Error Analysis

Analyze errors and failure patterns:

```bash
# System-wide error analysis
curl http://localhost:8001/api/analytics/errors?time_range_hours=168

# Agent-specific errors
curl http://localhost:8001/api/analytics/errors?agent_id=1&time_range_hours=168
```

Response:
```json
{
  "time_range_hours": 168,
  "total_failures": 45,
  "unique_error_types": 8,
  "retry_rate": 0.33,
  "agent_id": null,
  "top_errors": [
    {
      "error_message": "Database connection timeout",
      "count": 15,
      "execution_ids": [42, 48, 55, 62, 70],
      "agent_ids": [1, 2, 3]
    },
    {
      "error_message": "API rate limit exceeded",
      "count": 12,
      "execution_ids": [43, 50, 58],
      "agent_ids": [1, 4]
    },
    {
      "error_message": "Memory allocation failed",
      "count": 8,
      "execution_ids": [44, 52],
      "agent_ids": [2]
    }
  ]
}
```

Error insights:
- Most common error types
- Affected agents and executions
- Retry effectiveness
- Pattern identification

### Agent Utilization

Track how efficiently agents are being used:

```bash
# Last 24 hours
curl http://localhost:8001/api/analytics/utilization

# Last 7 days
curl http://localhost:8001/api/analytics/utilization?time_range_hours=168
```

Response:
```json
{
  "time_range_hours": 24,
  "total_agents": 5,
  "average_utilization_rate": 0.65,
  "agents": [
    {
      "agent_id": 1,
      "agent_name": "worker-agent-1",
      "agent_role": "worker",
      "agent_status": "idle",
      "busy_time_hours": 18.5,
      "utilization_rate": 0.77,
      "executions_count": 150
    },
    {
      "agent_id": 2,
      "agent_name": "worker-agent-2",
      "agent_role": "worker",
      "agent_status": "busy",
      "busy_time_hours": 20.0,
      "utilization_rate": 0.83,
      "executions_count": 120
    }
  ]
}
```

Utilization metrics:
- Busy time vs. total time
- Utilization rate per agent
- Average system utilization
- Capacity insights

Use for:
- Identify underutilized agents
- Capacity planning
- Load balancing optimization
- Cost optimization

### Performance Summary

Get overall system performance at a glance:

```bash
curl http://localhost:8001/api/analytics/summary?time_range_hours=24
```

Response:
```json
{
  "time_range_hours": 24,
  "timestamp": "2024-01-10T16:00:00",

  "total_agents": 5,
  "active_agents": 5,
  "busy_agents": 2,
  "idle_agents": 3,

  "total_executions": 450,
  "completed_executions": 360,
  "failed_executions": 45,
  "running_executions": 30,
  "queued_executions": 15,

  "success_rate": 0.8,
  "failure_rate": 0.1,
  "average_response_time_seconds": 240.5,

  "executions_per_hour": 18.75,
  "completions_per_hour": 15.0
}
```

Summary includes:
- Agent availability
- Execution throughput
- Success/failure rates
- System capacity

Perfect for:
- Dashboards
- Monitoring alerts
- Quick health checks
- Executive reports

### Analytics Best Practices

**Performance Monitoring**:
- Track success rates daily
- Set alerts for drops below threshold
- Monitor response time trends
- Review error patterns weekly

**Capacity Planning**:
- Monitor utilization rates
- Scale when average utilization > 80%
- Identify underutilized agents
- Balance workload distribution

**Optimization**:
- Compare agent performance regularly
- Identify and investigate slow agents
- Analyze error patterns for improvements
- Use trends to validate changes

**Reporting**:
- Use summary for daily standup
- Review rankings for team performance
- Share trends in weekly reports
- Deep-dive errors in retrospectives

## Agent Lifecycle Management

The lifecycle management system handles agent registration, health monitoring, state transitions, and recovery.

### Agent Registration

Register a new agent in the system:

```bash
curl -X POST http://localhost:8001/api/lifecycle/register \
  -H "Content-Type: application/json" \
  -d '{
    "name": "worker-agent-5",
    "role": "worker",
    "capabilities": ["code_analysis", "testing", "documentation"],
    "config": {
      "max_concurrent_tasks": 3,
      "timeout_seconds": 300
    },
    "metadata": {
      "version": "1.0.0",
      "environment": "production"
    }
  }'
```

Response:
```json
{
  "id": 5,
  "name": "worker-agent-5",
  "role": "worker",
  "status": "idle",
  "capabilities": ["code_analysis", "testing", "documentation"],
  "created_at": "2024-01-10T16:00:00"
}
```

Registration automatically:
- Assigns unique agent ID
- Sets initial status to IDLE
- Logs registration event
- Makes agent available for tasks

### Agent Deregistration

Remove an agent from the system:

```bash
# Deregister with reason
curl -X DELETE http://localhost:8001/api/lifecycle/deregister/5?reason=Agent%20upgrade

# Simple deregistration
curl -X DELETE http://localhost:8001/api/lifecycle/deregister/5
```

Response:
```json
{
  "deregistered": true
}
```

Deregistration automatically:
- Cancels running executions
- Logs deregistration event
- Removes agent from database
- Frees allocated resources

### Agent State Management

#### Start Agent

Activate a stopped or newly registered agent:

```bash
curl -X POST http://localhost:8001/api/lifecycle/start/5
```

Response:
```json
{
  "id": 5,
  "name": "worker-agent-5",
  "status": "idle",
  "last_active": "2024-01-10T16:05:00"
}
```

#### Stop Agent

Gracefully stop an agent:

```bash
curl -X POST http://localhost:8001/api/lifecycle/stop/5?reason=Maintenance
```

Response:
```json
{
  "id": 5,
  "name": "worker-agent-5",
  "status": "offline"
}
```

Stop automatically:
- Cancels current task execution
- Sets status to OFFLINE
- Logs stop event with reason

#### Pause Agent

Temporarily pause an agent:

```bash
curl -X POST http://localhost:8001/api/lifecycle/pause/5?reason=Resource%20constraints
```

Response:
```json
{
  "id": 5,
  "name": "worker-agent-5",
  "status": "offline"
}
```

Pause behavior:
- Pauses current execution (can be resumed)
- Sets agent to OFFLINE
- Preserves execution state

#### Resume Agent

Resume a paused agent:

```bash
curl -X POST http://localhost:8001/api/lifecycle/resume/5
```

Response:
```json
{
  "id": 5,
  "name": "worker-agent-5",
  "status": "idle",
  "last_active": "2024-01-10T16:10:00"
}
```

### Health Monitoring

#### Heartbeat

Agents send periodic heartbeats to indicate they're alive:

```bash
curl -X POST http://localhost:8001/api/lifecycle/heartbeat/5 \
  -H "Content-Type: application/json" \
  -d '{
    "status": "idle",
    "metrics": {
      "memory_usage_mb": 256,
      "cpu_usage_percent": 15,
      "active_threads": 3
    }
  }'
```

Response:
```json
{
  "id": 5,
  "name": "worker-agent-5",
  "status": "idle",
  "last_active": "2024-01-10T16:15:00"
}
```

Heartbeat tracking:
- Updates `last_active` timestamp
- Optionally updates agent status
- Stores metrics in agent metadata
- Used for health checks

#### Health Check (Single Agent)

Check health of a specific agent:

```bash
curl http://localhost:8001/api/lifecycle/health/5
```

Response:
```json
{
  "agent_id": 5,
  "agent_name": "worker-agent-5",
  "is_healthy": true,
  "status": "idle",
  "last_active": "2024-01-10T16:15:00",
  "last_active_seconds_ago": 30,
  "current_task_id": null,
  "issues": [],
  "checked_at": "2024-01-10T16:15:30"
}
```

Health criteria:
- **Activity**: Last active within 5 minutes
- **Status**: Not OFFLINE
- **Execution**: Not stuck on a task

Unhealthy example:
```json
{
  "agent_id": 3,
  "agent_name": "worker-agent-3",
  "is_healthy": false,
  "status": "busy",
  "last_active": "2024-01-10T15:00:00",
  "last_active_seconds_ago": 4530,
  "current_task_id": 42,
  "issues": [
    "No activity for 4530 seconds",
    "Stuck on task 42"
  ],
  "checked_at": "2024-01-10T16:15:30"
}
```

#### Health Check (All Agents)

Check health of entire agent fleet:

```bash
curl http://localhost:8001/api/lifecycle/health
```

Response:
```json
{
  "total_agents": 5,
  "healthy": 4,
  "unhealthy": 1,
  "health_rate": 0.8,
  "agents": [
    {
      "agent_id": 1,
      "agent_name": "worker-agent-1",
      "is_healthy": true,
      "status": "idle",
      "last_active": "2024-01-10T16:14:00",
      "issues": []
    },
    {
      "agent_id": 3,
      "agent_name": "worker-agent-3",
      "is_healthy": false,
      "status": "busy",
      "issues": ["No activity for 4530 seconds", "Stuck on task 42"]
    }
  ],
  "checked_at": "2024-01-10T16:15:30"
}
```

Use for:
- System health dashboards
- Monitoring alerts
- Automated health checks
- Fleet status overview

### Inactive Agent Detection

Find agents that haven't been active recently:

```bash
# Find agents inactive > 5 minutes (default)
curl http://localhost:8001/api/lifecycle/inactive

# Custom threshold (30 minutes)
curl http://localhost:8001/api/lifecycle/inactive?inactive_threshold_minutes=30
```

Response:
```json
{
  "inactive_threshold_minutes": 5,
  "count": 2,
  "agents": [
    {
      "id": 3,
      "name": "worker-agent-3",
      "status": "busy",
      "last_active": "2024-01-10T15:00:00"
    },
    {
      "id": 4,
      "name": "worker-agent-4",
      "status": "offline",
      "last_active": "2024-01-10T14:30:00"
    }
  ]
}
```

Use cases:
- Identify stale agents
- Detect crashed agents
- Trigger recovery procedures
- Clean up zombie processes

### Agent Recovery

Automatically recover an unhealthy agent:

```bash
curl -X POST http://localhost:8001/api/lifecycle/recover/3
```

Response:
```json
{
  "id": 3,
  "name": "worker-agent-3",
  "status": "idle",
  "last_active": "2024-01-10T16:20:00",
  "recovered": true
}
```

Recovery process:
1. Cancel stuck executions
2. Create retry executions (if attempts < 3)
3. Reset agent to IDLE status
4. Clear current task
5. Update last_active timestamp
6. Log recovery event

### Lifecycle Events

View lifecycle event history for an agent:

```bash
# Last 50 events (default)
curl http://localhost:8001/api/lifecycle/events/5

# Custom limit
curl http://localhost:8001/api/lifecycle/events/5?limit=100
```

Response:
```json
{
  "agent_id": 5,
  "count": 8,
  "events": [
    {
      "event_type": "registered",
      "timestamp": "2024-01-10T16:00:00",
      "details": {
        "name": "worker-agent-5",
        "role": "worker"
      }
    },
    {
      "event_type": "started",
      "timestamp": "2024-01-10T16:05:00",
      "details": {}
    },
    {
      "event_type": "health_check_passed",
      "timestamp": "2024-01-10T16:15:30",
      "details": {
        "is_healthy": true,
        "issues": []
      }
    },
    {
      "event_type": "paused",
      "timestamp": "2024-01-10T16:18:00",
      "details": {
        "reason": "Resource constraints"
      }
    },
    {
      "event_type": "resumed",
      "timestamp": "2024-01-10T16:20:00",
      "details": {}
    }
  ]
}
```

Event types:
- `registered` - Agent added to system
- `started` - Agent activated
- `stopped` - Agent stopped
- `paused` - Agent temporarily paused
- `resumed` - Agent resumed from pause
- `health_check_passed` - Health check succeeded
- `health_check_failed` - Health check failed
- `heartbeat_missed` - Heartbeat not received
- `crashed` - Agent crashed unexpectedly
- `recovered` - Agent recovered from failure
- `deregistered` - Agent removed from system

### Lifecycle Best Practices

**Registration**:
- Use descriptive agent names
- Set appropriate capabilities
- Include version in metadata
- Configure reasonable timeouts

**Health Monitoring**:
- Send heartbeats every 30-60 seconds
- Include resource metrics in heartbeats
- Run health checks every 5 minutes
- Set up alerts for health_rate < 80%

**State Management**:
- Always provide stop/pause reasons
- Use pause for temporary issues
- Use stop for maintenance
- Deregister only when permanently removing

**Recovery**:
- Check inactive agents regularly
- Recover unhealthy agents automatically
- Review recovery events for patterns
- Update agents to prevent failures

**Event Tracking**:
- Review lifecycle events for debugging
- Monitor event patterns for issues
- Archive events for compliance
- Use events for capacity planning

## Agent Scheduler and Load Balancer

The Agent Scheduler provides intelligent task scheduling and load balancing across your agent fleet using multiple strategies optimized for different use cases.

### Scheduling Strategies

The scheduler supports 6 different scheduling strategies:

1. **ROUND_ROBIN** - Distributes tasks evenly in rotation
2. **LEAST_LOADED** - Assigns to agent with lowest current load (default)
3. **CAPABILITY_BASED** - Matches task requirements to agent capabilities
4. **PERFORMANCE_BASED** - Selects based on success rate and response time
5. **RANDOM** - Random assignment for testing
6. **PRIORITY_QUEUE** - Respects task priority ordering

### Schedule a Single Task

Schedule a task using a specific strategy:

```bash
curl -X POST http://localhost:8001/api/scheduler/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 123,
    "strategy": "least_loaded",
    "required_capabilities": ["python", "testing"],
    "preferred_role": "tester"
  }'
```

**Response**:
```json
{
  "success": true,
  "task_id": 123,
  "agent_id": 5,
  "agent_name": "TestAgent-01",
  "agent_role": "tester",
  "agent_status": "idle",
  "strategy": "least_loaded",
  "message": "Task 123 scheduled to agent TestAgent-01"
}
```

### Batch Schedule Multiple Tasks

Efficiently schedule multiple tasks with load balancing:

```bash
curl -X POST http://localhost:8001/api/scheduler/batch-schedule \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": [101, 102, 103, 104, 105],
    "strategy": "least_loaded",
    "balance_load": true
  }'
```

**Response**:
```json
{
  "success": true,
  "total_tasks": 5,
  "assigned": 5,
  "unassigned": 0,
  "assignment_rate": 1.0,
  "strategy": "least_loaded",
  "balance_load": true,
  "assignments": {
    "101": 1,
    "102": 2,
    "103": 1,
    "104": 3,
    "105": 2
  },
  "agent_task_counts": {
    "1": 2,
    "2": 2,
    "3": 1
  },
  "message": "Scheduled 5/5 tasks successfully"
}
```

### Get Load Distribution

View current load distribution across all agents:

```bash
curl http://localhost:8001/api/scheduler/load-distribution
```

**Response**:
```json
{
  "success": true,
  "distribution": {
    "total_agents": 5,
    "total_load": 12,
    "average_load": 2.4,
    "balance_score": 0.87,
    "agents": [
      {
        "agent_id": 1,
        "agent_name": "ResearchAgent-01",
        "role": "researcher",
        "status": "busy",
        "current_load": 4,
        "queued_tasks": 2
      },
      {
        "agent_id": 2,
        "agent_name": "CoderAgent-01",
        "role": "coder",
        "status": "idle",
        "current_load": 2,
        "queued_tasks": 0
      }
    ]
  },
  "message": "Load distribution for 5 agents"
}
```

**Understanding Balance Score**:
- Score ranges from 0 to 1
- 1.0 = perfectly balanced load
- < 0.7 = consider rebalancing
- Based on coefficient of variation

### Rebalance Load

Dynamically move queued tasks from overloaded to underloaded agents:

```bash
curl -X POST http://localhost:8001/api/scheduler/rebalance \
  -H "Content-Type: application/json" \
  -d '{
    "threshold": 0.3
  }'
```

**Response**:
```json
{
  "success": true,
  "result": {
    "rebalanced": true,
    "tasks_moved": 3,
    "old_balance_score": 0.65,
    "new_balance_score": 0.89,
    "improvement": 0.24
  },
  "message": "Rebalanced 3 tasks"
}
```

**Threshold Parameter**:
- Determines when rebalancing triggers
- 0.3 = 30% deviation from average load
- Lower threshold = more aggressive rebalancing
- Higher threshold = less frequent rebalancing

### List Available Strategies

Get detailed information about all scheduling strategies:

```bash
curl http://localhost:8001/api/scheduler/strategies
```

**Response** (excerpt):
```json
{
  "success": true,
  "total_strategies": 6,
  "default_strategy": "least_loaded",
  "strategies": [
    {
      "name": "round_robin",
      "description": "Distributes tasks evenly in rotation across all available agents",
      "use_case": "Simple fair distribution when all agents are equivalent",
      "pros": ["Fair distribution", "Simple", "Predictable"],
      "cons": ["Ignores agent load", "Ignores agent capabilities"]
    },
    {
      "name": "least_loaded",
      "description": "Assigns tasks to the agent with the lowest current load",
      "use_case": "Load balancing when agents have similar capabilities",
      "pros": ["Balances load", "Maximizes throughput", "Reduces wait times"],
      "cons": ["May overload slow agents", "Doesn't consider capabilities"]
    }
  ]
}
```

### Get Agent Load

Check current load for a specific agent:

```bash
curl http://localhost:8001/api/scheduler/agent-load/1
```

**Response**:
```json
{
  "success": true,
  "agent_id": 1,
  "agent_name": "ResearchAgent-01",
  "agent_role": "researcher",
  "agent_status": "busy",
  "current_load": 4,
  "queued_tasks": 2,
  "running_tasks": 2,
  "message": "Load information for agent ResearchAgent-01"
}
```

### Get Scheduling Statistics

Analyze scheduling patterns and trends:

```bash
curl "http://localhost:8001/api/scheduler/scheduling-stats?time_range_hours=24"
```

**Response**:
```json
{
  "success": true,
  "time_range_hours": 24,
  "total_executions": 156,
  "status_distribution": {
    "completed": 120,
    "running": 15,
    "queued": 12,
    "failed": 9
  },
  "agent_execution_counts": {
    "1": 35,
    "2": 42,
    "3": 38,
    "4": 25,
    "5": 16
  },
  "total_agents": 5,
  "active_agents": 5,
  "agent_utilization_rate": 1.0,
  "current_load_balance_score": 0.85,
  "average_executions_per_agent": 31.2,
  "message": "Scheduling statistics for last 24 hours"
}
```

### Strategy Comparison

Here's how to choose the right strategy:

**Use ROUND_ROBIN when**:
- All agents have identical capabilities
- Simple fair distribution is needed
- Predictability is important
- Example: Distributing similar research tasks

**Use LEAST_LOADED when**:
- Maximizing throughput is critical
- Agents have similar capabilities
- Want to minimize wait times
- Example: Processing large batch of similar tasks

**Use CAPABILITY_BASED when**:
- Tasks require specific skills
- Agents have diverse capabilities
- Task-agent alignment is critical
- Example: Routing code tasks to coder agents

**Use PERFORMANCE_BASED when**:
- Quality and speed are priorities
- Historical data is available
- Want to optimize success rate
- Example: Critical production workloads

**Use PRIORITY_QUEUE when**:
- Task priority must be respected
- Some tasks are more urgent
- Want strict priority ordering
- Example: User-facing vs. background tasks

**Use RANDOM when**:
- Testing different scenarios
- Avoiding patterns
- No optimization needed
- Example: Load testing, experimentation

### Integration Example

Complete workflow using scheduler:

```python
import requests

# 1. Schedule high-priority task with capability requirements
response = requests.post(
    "http://localhost:8001/api/scheduler/schedule",
    json={
        "task_id": 101,
        "strategy": "capability_based",
        "required_capabilities": ["python", "testing", "pytest"],
        "preferred_role": "tester"
    }
)
assigned_agent = response.json()["agent_id"]

# 2. Batch schedule related tasks
response = requests.post(
    "http://localhost:8001/api/scheduler/batch-schedule",
    json={
        "task_ids": [102, 103, 104, 105],
        "strategy": "least_loaded",
        "balance_load": True
    }
)
assignments = response.json()["assignments"]

# 3. Monitor load distribution
response = requests.get("http://localhost:8001/api/scheduler/load-distribution")
balance_score = response.json()["distribution"]["balance_score"]

# 4. Rebalance if needed
if balance_score < 0.7:
    response = requests.post(
        "http://localhost:8001/api/scheduler/rebalance",
        json={"threshold": 0.3}
    )
    print(f"Moved {response.json()['result']['tasks_moved']} tasks")

# 5. Check scheduling stats
response = requests.get(
    "http://localhost:8001/api/scheduler/scheduling-stats",
    params={"time_range_hours": 24}
)
stats = response.json()
print(f"Utilization: {stats['agent_utilization_rate']:.1%}")
```

### Load Balancing Best Practices

**Proactive Load Management**:
- Monitor balance score regularly
- Set up alerts when balance_score < 0.7
- Schedule rebalancing during low-activity periods
- Use batch scheduling for efficiency

**Strategy Selection**:
- Start with LEAST_LOADED as default
- Use CAPABILITY_BASED when skills matter
- Switch to PERFORMANCE_BASED for production
- Test with RANDOM to validate robustness

**Performance Optimization**:
- Batch schedule when possible (more efficient)
- Enable balance_load for batch operations
- Monitor agent utilization rates
- Adjust thresholds based on workload patterns

**Capacity Planning**:
- Track agent_utilization_rate over time
- Add agents when utilization > 80%
- Remove agents when utilization < 30%
- Balance agent capabilities across roles

**Monitoring**:
- Check load distribution hourly
- Review scheduling stats daily
- Analyze agent execution counts
- Identify bottlenecks early

### Common Use Cases

**1. Processing File Upload Batches**:
```bash
# Upload 100 files for analysis
# Batch schedule with load balancing
curl -X POST http://localhost:8001/api/scheduler/batch-schedule \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": [1001, 1002, ..., 1100],
    "strategy": "least_loaded",
    "balance_load": true
  }'
```

**2. Urgent Task Prioritization**:
```bash
# Schedule critical task to best-performing agent
curl -X POST http://localhost:8001/api/scheduler/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 5001,
    "strategy": "performance_based"
  }'
```

**3. Specialized Task Routing**:
```bash
# Route ML task to agents with GPU capabilities
curl -X POST http://localhost:8001/api/scheduler/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 6001,
    "strategy": "capability_based",
    "required_capabilities": ["gpu", "tensorflow", "python"]
  }'
```

**4. Load Balancing During Peak Hours**:
```bash
# Check if rebalancing is needed
curl http://localhost:8001/api/scheduler/load-distribution

# Rebalance if score < 0.7
curl -X POST http://localhost:8001/api/scheduler/rebalance \
  -H "Content-Type: application/json" \
  -d '{"threshold": 0.25}'
```

### API Documentation

Interactive API documentation is available at:
- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

## Project Status

✅ **Block Phase 1 Complete!** - Foundation & Infrastructure (100% complete)
🚧 **Block Phase 2 In Progress** - Basic Agent Implementation (60% complete)

Current Progress: Commit 32/100 - Agent Scheduler and Load Balancer Complete

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
