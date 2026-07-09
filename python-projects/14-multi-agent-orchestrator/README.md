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

## Agent Capability Management

The Agent Capability Management System provides dynamic capability registration, intelligent matching, and discovery for optimal task-to-agent routing.

### Capability Proficiency Levels

The system supports 4 proficiency levels with weighted scoring:

1. **BASIC** (weight: 1.0) - Fundamental understanding and basic usage
2. **INTERMEDIATE** (weight: 2.0) - Comfortable with common use cases (default)
3. **ADVANCED** (weight: 3.0) - Deep knowledge for complex scenarios
4. **EXPERT** (weight: 4.0) - Mastery with ability to innovate

### Capability Categories

Capabilities are organized into 15 categories:

- **programming** - Languages and paradigms
- **testing** - Testing frameworks and methodologies
- **documentation** - Documentation tools and writing
- **analysis** - Data analysis and research
- **design** - UI/UX and system design
- **deployment** - Deployment and release management
- **monitoring** - Monitoring and observability
- **security** - Security and vulnerability assessment
- **database** - Database systems and query languages
- **api** - API design and integration
- **ui_ux** - User interface and experience
- **machine_learning** - ML frameworks and models
- **data_processing** - Data processing and ETL
- **cloud** - Cloud platforms and services
- **devops** - DevOps tools and practices

### Register a Capability

Add a capability to an agent:

```bash
curl -X POST http://localhost:8001/api/capabilities/register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "capability": "python",
    "level": "expert",
    "category": "programming",
    "metadata": {
      "years_experience": 5,
      "frameworks": ["fastapi", "django", "flask"]
    }
  }'
```

**Response**:
```json
{
  "success": true,
  "capability": {
    "name": "python",
    "level": "expert",
    "category": "programming",
    "registered_at": "2024-01-15T10:30:00",
    "updated_at": "2024-01-15T10:30:00",
    "metadata": {
      "years_experience": 5,
      "frameworks": ["fastapi", "django", "flask"]
    }
  },
  "message": "Capability 'python' registered for agent 1"
}
```

### Batch Register Capabilities

Register multiple capabilities efficiently:

```bash
curl -X POST http://localhost:8001/api/capabilities/batch-register \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 2,
    "capabilities": [
      {"name": "pytest", "level": "expert", "category": "testing"},
      {"name": "selenium", "level": "advanced", "category": "testing"},
      {"name": "python", "level": "intermediate", "category": "programming"},
      {"name": "test_automation", "level": "expert", "category": "testing"}
    ]
  }'
```

**Response**:
```json
{
  "success": true,
  "registered_count": 4,
  "capabilities": [
    {
      "name": "pytest",
      "level": "expert",
      "category": "testing",
      "registered_at": "2024-01-15T10:35:00",
      "updated_at": "2024-01-15T10:35:00",
      "metadata": {}
    }
  ],
  "message": "Registered 4 capabilities for agent 2"
}
```

### Match Capabilities

Find agents matching required capabilities with ranked scoring:

```bash
curl -X POST http://localhost:8001/api/capabilities/match \
  -H "Content-Type: application/json" \
  -d '{
    "required_capabilities": ["python", "pytest", "debugging"],
    "min_level": "intermediate",
    "role": "tester",
    "status": "idle"
  }'
```

**Response**:
```json
{
  "success": true,
  "required_capabilities": ["python", "pytest", "debugging"],
  "min_level": "intermediate",
  "total_matches": 3,
  "matches": [
    {
      "agent_id": 2,
      "agent_name": "TestAgent-01",
      "agent_role": "tester",
      "agent_status": "idle",
      "match_score": 9.0,
      "matched_capabilities": [
        {"name": "python", "level": "intermediate", "category": "programming"},
        {"name": "pytest", "level": "expert", "category": "testing"},
        {"name": "debugging", "level": "advanced", "category": "programming"}
      ],
      "total_capabilities": 8,
      "match_percentage": 1.0
    },
    {
      "agent_id": 5,
      "agent_name": "TestAgent-02",
      "agent_role": "tester",
      "agent_status": "idle",
      "match_score": 5.0,
      "matched_capabilities": [
        {"name": "python", "level": "basic", "category": "programming"},
        {"name": "pytest", "level": "advanced", "category": "testing"}
      ],
      "total_capabilities": 6,
      "match_percentage": 0.67
    }
  ],
  "message": "Found 3 agents matching capabilities"
}
```

**Match Score Calculation**:
- Each capability match contributes: `capability_weight / min_level_weight`
- Expert capability (4.0) vs. intermediate requirement (2.0) = score of 2.0
- Perfect match at required level = score of 1.0
- Below minimum level = not counted

### Find Best Agent

Get single best agent for capabilities:

```bash
curl -X POST http://localhost:8001/api/capabilities/find-best-agent \
  -H "Content-Type: application/json" \
  -d '{
    "required_capabilities": ["code_review", "python", "security"],
    "min_level": "advanced",
    "role": "reviewer",
    "prefer_available": true
  }'
```

**Response**:
```json
{
  "success": true,
  "agent": {
    "agent_id": 3,
    "agent_name": "ReviewAgent-01",
    "agent_role": "reviewer",
    "agent_status": "idle",
    "match_score": 11.0,
    "matched_capabilities": [
      {"name": "code_review", "level": "expert", "category": "programming"},
      {"name": "python", "level": "expert", "category": "programming"},
      {"name": "security", "level": "advanced", "category": "security"}
    ],
    "total_capabilities": 10,
    "match_percentage": 1.0
  },
  "message": "Found best agent: ReviewAgent-01"
}
```

### Get Agent Capabilities

View all capabilities for a specific agent:

```bash
curl http://localhost:8001/api/capabilities/agent/1
```

**Response**:
```json
{
  "success": true,
  "agent_id": 1,
  "total_capabilities": 6,
  "capabilities": [
    {
      "name": "python",
      "level": "expert",
      "category": "programming",
      "registered_at": "2024-01-15T10:30:00",
      "updated_at": "2024-01-15T10:30:00",
      "metadata": {"years_experience": 5}
    },
    {
      "name": "fastapi",
      "level": "advanced",
      "category": "programming",
      "registered_at": "2024-01-15T10:31:00",
      "updated_at": "2024-01-15T10:31:00",
      "metadata": {}
    }
  ],
  "message": "Retrieved 6 capabilities for agent 1"
}
```

### Get All Capabilities

List all unique capabilities across the agent fleet:

```bash
curl "http://localhost:8001/api/capabilities/all?category=testing&min_agents=2"
```

**Response**:
```json
{
  "success": true,
  "total_capabilities": 5,
  "category_filter": "testing",
  "min_agents": 2,
  "capabilities": [
    {
      "name": "pytest",
      "category": "testing",
      "agent_count": 4,
      "levels": {
        "basic": 0,
        "intermediate": 1,
        "advanced": 1,
        "expert": 2
      },
      "agents": [
        {"agent_id": 2, "agent_name": "TestAgent-01", "level": "expert"},
        {"agent_id": 5, "agent_name": "TestAgent-02", "level": "expert"},
        {"agent_id": 7, "agent_name": "CoderAgent-03", "level": "advanced"},
        {"agent_id": 9, "agent_name": "TestAgent-03", "level": "intermediate"}
      ]
    }
  ],
  "message": "Retrieved 5 capabilities"
}
```

### Capability Coverage Analysis

Analyze fleet coverage for required capabilities:

```bash
curl -X POST http://localhost:8001/api/capabilities/coverage \
  -H "Content-Type: application/json" \
  -d '["python", "docker", "kubernetes", "terraform", "ansible"]'
```

**Response**:
```json
{
  "success": true,
  "analysis": {
    "coverage": {
      "python": {
        "total_agents": 8,
        "by_level": {
          "basic": 2,
          "intermediate": 3,
          "advanced": 2,
          "expert": 1
        },
        "agents": [
          {"agent_id": 1, "agent_name": "CoderAgent-01", "level": "expert"}
        ]
      },
      "docker": {
        "total_agents": 5,
        "by_level": {"basic": 1, "intermediate": 3, "advanced": 1, "expert": 0},
        "agents": []
      },
      "terraform": {
        "total_agents": 0,
        "by_level": {"basic": 0, "intermediate": 0, "advanced": 0, "expert": 0},
        "agents": []
      }
    },
    "summary": {
      "total_capabilities": 5,
      "covered_capabilities": 4,
      "uncovered_capabilities": 1,
      "coverage_percentage": 0.8
    }
  },
  "message": "Coverage analysis for 5 capabilities"
}
```

### Suggest Capabilities

Get AI-powered capability suggestions for an agent:

```bash
curl "http://localhost:8001/api/capabilities/suggest/2?based_on_role=true"
```

**Response**:
```json
{
  "success": true,
  "agent_id": 2,
  "total_suggestions": 6,
  "suggestions": [
    {
      "name": "test_automation",
      "level": "advanced",
      "category": "testing",
      "reason": "Recommended for tester role"
    },
    {
      "name": "bug_tracking",
      "level": "intermediate",
      "category": "testing",
      "reason": "Recommended for tester role"
    },
    {
      "name": "selenium",
      "level": "advanced",
      "category": "testing",
      "reason": "Used by 3 similar tester agents"
    }
  ],
  "message": "Generated 6 capability suggestions for agent 2"
}
```

**Suggestion Logic**:
1. **Role-based**: Capabilities typical for agent's role (researcher, coder, tester, etc.)
2. **Peer-based**: Capabilities commonly possessed by similar agents (same role)
3. **Gap analysis**: Only suggests capabilities the agent doesn't already have

### Validate Capability

Validate capability definition before registration:

```bash
curl -X POST http://localhost:8001/api/capabilities/validate \
  -H "Content-Type: application/json" \
  -d '{
    "capability": "python",
    "level": "expert",
    "category": "programming"
  }'
```

**Response**:
```json
{
  "success": true,
  "validation": {
    "valid": true,
    "errors": [],
    "warnings": []
  },
  "message": "Valid capability"
}
```

### Remove Capability

Remove a capability from an agent:

```bash
curl -X DELETE http://localhost:8001/api/capabilities/remove \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "capability": "old_framework"
  }'
```

**Response**:
```json
{
  "success": true,
  "message": "Capability 'old_framework' removed from agent 1"
}
```

### List Levels and Categories

Get reference data for levels and categories:

```bash
# List all proficiency levels
curl http://localhost:8001/api/capabilities/levels

# List all categories
curl http://localhost:8001/api/capabilities/categories
```

### Integration Example

Complete workflow for capability management:

```python
import requests

# 1. Register capabilities for a new agent
response = requests.post(
    "http://localhost:8001/api/capabilities/batch-register",
    json={
        "agent_id": 10,
        "capabilities": [
            {"name": "python", "level": "expert", "category": "programming"},
            {"name": "machine_learning", "level": "advanced", "category": "machine_learning"},
            {"name": "tensorflow", "level": "advanced", "category": "machine_learning"},
            {"name": "data_analysis", "level": "expert", "category": "analysis"}
        ]
    }
)
print(f"Registered {response.json()['registered_count']} capabilities")

# 2. Get suggestions for improving agent capabilities
response = requests.get(
    "http://localhost:8001/api/capabilities/suggest/10",
    params={"based_on_role": True}
)
suggestions = response.json()["suggestions"]
print(f"Suggested capabilities: {[s['name'] for s in suggestions]}")

# 3. Find best agent for a machine learning task
response = requests.post(
    "http://localhost:8001/api/capabilities/find-best-agent",
    json={
        "required_capabilities": ["python", "tensorflow", "data_analysis"],
        "min_level": "advanced",
        "prefer_available": True
    }
)
best_agent = response.json()["agent"]
print(f"Best agent: {best_agent['agent_name']} (score: {best_agent['match_score']})")

# 4. Analyze capability coverage
response = requests.post(
    "http://localhost:8001/api/capabilities/coverage",
    json=["python", "java", "go", "rust", "typescript"]
)
coverage = response.json()["analysis"]["summary"]
print(f"Coverage: {coverage['coverage_percentage']:.1%}")

# 5. Match all agents for specific capabilities
response = requests.post(
    "http://localhost:8001/api/capabilities/match",
    json={
        "required_capabilities": ["python", "testing"],
        "min_level": "intermediate"
    }
)
matches = response.json()["matches"]
print(f"Found {len(matches)} matching agents")
for match in matches[:3]:
    print(f"  - {match['agent_name']}: {match['match_score']}")
```

### Use Cases

**1. Intelligent Task Routing**:
```python
# Route task to best-qualified agent
task_requirements = ["kubernetes", "docker", "helm"]
best_agent = requests.post(
    "http://localhost:8001/api/capabilities/find-best-agent",
    json={
        "required_capabilities": task_requirements,
        "min_level": "intermediate",
        "prefer_available": True
    }
).json()["agent"]
```

**2. Skill Gap Analysis**:
```python
# Identify missing capabilities across fleet
critical_skills = ["security", "monitoring", "incident_response"]
coverage = requests.post(
    "http://localhost:8001/api/capabilities/coverage",
    json=critical_skills
).json()["analysis"]["summary"]

if coverage["coverage_percentage"] < 0.8:
    print("Warning: Insufficient coverage for critical skills!")
```

**3. Agent Onboarding**:
```python
# Set up new agent with role-appropriate capabilities
suggestions = requests.get(
    f"http://localhost:8001/api/capabilities/suggest/{new_agent_id}",
    params={"based_on_role": True}
).json()["suggestions"]

# Register suggested capabilities
requests.post(
    "http://localhost:8001/api/capabilities/batch-register",
    json={
        "agent_id": new_agent_id,
        "capabilities": suggestions
    }
)
```

**4. Team Composition**:
```python
# Find agents with complementary skills for a project
project_needs = {
    "backend": ["python", "fastapi", "postgresql"],
    "frontend": ["react", "typescript", "css"],
    "devops": ["docker", "kubernetes", "ci_cd"]
}

team = {}
for role, skills in project_needs.items():
    agent = requests.post(
        "http://localhost:8001/api/capabilities/find-best-agent",
        json={"required_capabilities": skills, "min_level": "intermediate"}
    ).json()["agent"]
    team[role] = agent["agent_name"]
```

### Best Practices

**Capability Registration**:
- Use consistent naming conventions (lowercase, underscores)
- Assign appropriate proficiency levels honestly
- Include relevant metadata (version, experience, certifications)
- Update capabilities when agent skills improve

**Matching Strategy**:
- Set realistic minimum levels (intermediate for most tasks)
- Use `prefer_available=true` to avoid overloading agents
- Consider match_percentage along with match_score
- Filter by role when skill overlap exists

**Coverage Monitoring**:
- Regularly analyze coverage for critical capabilities
- Track coverage_percentage trend over time
- Address gaps with training or new agent recruitment
- Balance specialization vs. redundancy

**Performance Optimization**:
- Use batch registration for new agents
- Cache capability lookups for frequently accessed data
- Filter by category to reduce search space
- Set min_agents threshold to focus on common capabilities

## Agent Priority Management

The Agent Priority Management System handles task prioritization, queue ordering, SLA tracking, and automatic priority escalation to ensure critical tasks are completed on time.

### Priority Levels

The system supports 4 priority levels with numeric weights:

1. **CRITICAL** (weight: 4) - Urgent, system-critical tasks requiring immediate attention
2. **HIGH** (weight: 3) - Important tasks that should be completed soon
3. **NORMAL** (weight: 2) - Standard tasks with normal urgency (default)
4. **LOW** (weight: 1) - Low-urgency tasks that can wait if needed

### Escalation Policies

Automatic escalation policies increase priority for aging tasks:

- **AGGRESSIVE** - Escalate after 30 minutes (production incidents, real-time systems)
- **MODERATE** - Escalate low/normal after 2h, high after 1h (standard operations)
- **CONSERVATIVE** - Escalate low/normal after 6h, high after 3h (research, batch processing)
- **NONE** - No automatic escalation (manual priority management)

### Set Task Priority

Change task priority level:

```bash
curl -X POST http://localhost:8001/api/priorities/set-priority \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 123,
    "priority": "high",
    "reason": "Customer escalation - production issue"
  }'
```

**Response**:
```json
{
  "success": true,
  "result": {
    "task_id": 123,
    "old_priority": "normal",
    "new_priority": "high",
    "reason": "Customer escalation - production issue",
    "changed_at": "2024-01-15T14:30:00"
  },
  "message": "Priority set to high for task 123"
}
```

### Get Static Priority Queue

Get tasks ordered by priority level only:

```bash
curl "http://localhost:8001/api/priorities/queue?agent_id=1&status_filter=queued&limit=50"
```

**Response**:
```json
{
  "success": true,
  "total_tasks": 15,
  "agent_id_filter": 1,
  "status_filter": "queued",
  "queue": [
    {
      "execution_id": 501,
      "task_id": 201,
      "task_title": "Fix critical database connection issue",
      "priority": "critical",
      "priority_weight": 4,
      "status": "queued",
      "agent_id": 1,
      "created_at": "2024-01-15T14:00:00",
      "age_minutes": 30
    },
    {
      "execution_id": 502,
      "task_id": 202,
      "task_title": "Deploy security patch",
      "priority": "high",
      "priority_weight": 3,
      "status": "queued",
      "agent_id": 1,
      "created_at": "2024-01-15T13:45:00",
      "age_minutes": 45
    }
  ],
  "message": "Retrieved 15 tasks from priority queue"
}
```

### Get Dynamic Priority Queue

Get tasks with dynamic priority considering age and SLA:

```bash
curl "http://localhost:8001/api/priorities/queue/dynamic?agent_id=1&include_sla=true"
```

**Response**:
```json
{
  "success": true,
  "total_tasks": 15,
  "agent_id_filter": 1,
  "include_sla": true,
  "queue": [
    {
      "execution_id": 503,
      "task_id": 203,
      "task_title": "Process payment batch",
      "base_priority": "high",
      "dynamic_score": 450,
      "age_minutes": 85,
      "status": "queued",
      "agent_id": 1,
      "sla_status": {
        "sla_minutes": 120,
        "age_minutes": 85,
        "remaining_minutes": 35,
        "breached": false,
        "at_risk": false,
        "percentage_used": 70.83
      }
    }
  ],
  "message": "Retrieved 15 tasks from dynamic priority queue"
}
```

**Dynamic Score Calculation**:
- Base weight from priority level (1-4)
- Age factor: +0.1 per 30 minutes
- SLA factor: +2.0 if breached, +1.0 if <25% time left, +0.5 if <50% time left
- Final score = (base_weight + age_factor + sla_factor) × 100

### Escalate Priorities

Automatically escalate aging tasks:

```bash
curl -X POST http://localhost:8001/api/priorities/escalate \
  -H "Content-Type: application/json" \
  -d '{
    "policy": "moderate",
    "dry_run": false
  }'
```

**Response**:
```json
{
  "success": true,
  "result": {
    "policy": "moderate",
    "dry_run": false,
    "escalated_count": 5,
    "escalations": [
      {
        "task_id": 150,
        "task_title": "Review code changes",
        "from_priority": "low",
        "to_priority": "normal",
        "age_minutes": 135
      },
      {
        "task_id": 152,
        "task_title": "Update documentation",
        "from_priority": "normal",
        "to_priority": "high",
        "age_minutes": 145
      }
    ],
    "timestamp": "2024-01-15T14:30:00"
  },
  "message": "Escalated 5 tasks"
}
```

**Escalation Thresholds**:

| Policy | Low→Normal | Normal→High | High→Critical |
|--------|------------|-------------|---------------|
| Aggressive | 30 min | 30 min | 30 min |
| Moderate | 2 hours | 2 hours | 1 hour |
| Conservative | 6 hours | 6 hours | 3 hours |

### Set Task SLA

Define deadline for task completion:

```bash
curl -X POST http://localhost:8001/api/priorities/sla/set \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 123,
    "sla_minutes": 240,
    "auto_escalate": true
  }'
```

**Response**:
```json
{
  "success": true,
  "sla": {
    "task_id": 123,
    "sla_minutes": 240,
    "deadline": "2024-01-15T18:30:00",
    "auto_escalate": true
  },
  "message": "SLA set for task 123: 240 minutes"
}
```

### Check SLA Violations

Monitor SLA breaches and at-risk tasks:

```bash
curl http://localhost:8001/api/priorities/sla/violations
```

**Response**:
```json
{
  "success": true,
  "violations": {
    "violations": [
      {
        "task_id": 180,
        "task_title": "Critical bug fix",
        "priority": "high",
        "sla_minutes": 120,
        "age_minutes": 145,
        "remaining_minutes": -25,
        "breached_by_minutes": 25
      }
    ],
    "violations_count": 1,
    "at_risk": [
      {
        "task_id": 181,
        "task_title": "Deploy hotfix",
        "priority": "critical",
        "sla_minutes": 60,
        "age_minutes": 50,
        "remaining_minutes": 10,
        "percentage_remaining": 16.67
      }
    ],
    "at_risk_count": 1,
    "total_checked": 25,
    "timestamp": "2024-01-15T14:30:00"
  },
  "message": "Found 1 violations, 1 at risk"
}
```

**SLA Status Definitions**:
- **Breached**: Age exceeds SLA deadline (remaining ≤ 0)
- **At Risk**: Less than 25% of SLA time remaining
- **Normal**: More than 25% of SLA time remaining

### Reorder Agent Queue

Reorder queue using static or dynamic priority:

```bash
curl -X POST http://localhost:8001/api/priorities/reorder-queue \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "use_dynamic_priority": true
  }'
```

**Response**:
```json
{
  "success": true,
  "result": {
    "agent_id": 1,
    "agent_name": "CoderAgent-01",
    "queue_length": 12,
    "use_dynamic_priority": true,
    "queue": [
      {
        "execution_id": 501,
        "task_id": 201,
        "base_priority": "critical",
        "dynamic_score": 520,
        "age_minutes": 45
      }
    ],
    "reordered_at": "2024-01-15T14:30:00"
  },
  "message": "Reordered queue for agent 1"
}
```

### Get Priority Statistics

Analyze priority distribution and performance:

```bash
curl "http://localhost:8001/api/priorities/statistics?time_range_hours=24"
```

**Response**:
```json
{
  "success": true,
  "statistics": {
    "time_range_hours": 24,
    "priority_distribution": {
      "critical": 5,
      "high": 23,
      "normal": 145,
      "low": 67
    },
    "completion_times": {
      "critical": {
        "average_seconds": 1200,
        "sample_size": 4
      },
      "high": {
        "average_seconds": 2400,
        "sample_size": 18
      },
      "normal": {
        "average_seconds": 5400,
        "sample_size": 120
      },
      "low": {
        "average_seconds": 8600,
        "sample_size": 50
      }
    },
    "currently_queued": {
      "critical": 1,
      "high": 5,
      "normal": 25,
      "low": 17
    },
    "sla_metrics": {
      "breaches": 2,
      "at_risk": 3,
      "total_with_sla": 50
    },
    "total_tasks": 240,
    "timestamp": "2024-01-15T14:30:00"
  },
  "message": "Priority statistics for last 24 hours"
}
```

### Get Priority History

View audit trail of priority changes:

```bash
curl http://localhost:8001/api/priorities/task/123/priority-history
```

**Response**:
```json
{
  "success": true,
  "task_id": 123,
  "current_priority": "critical",
  "history_count": 3,
  "history": [
    {
      "from": null,
      "to": "normal",
      "changed_at": "2024-01-15T10:00:00",
      "reason": null
    },
    {
      "from": "normal",
      "to": "high",
      "changed_at": "2024-01-15T12:00:00",
      "reason": "Auto-escalated by moderate policy after 120 minutes"
    },
    {
      "from": "high",
      "to": "critical",
      "changed_at": "2024-01-15T14:00:00",
      "reason": "Customer escalation - production issue"
    }
  ],
  "message": "Priority history for task 123"
}
```

### List Levels and Policies

Get reference data:

```bash
# List priority levels
curl http://localhost:8001/api/priorities/levels

# List escalation policies
curl http://localhost:8001/api/priorities/policies
```

### Integration Example

Complete workflow for priority management:

```python
import requests

# 1. Set priority and SLA for critical task
response = requests.post(
    "http://localhost:8001/api/priorities/set-priority",
    json={
        "task_id": 501,
        "priority": "critical",
        "reason": "Production database outage"
    }
)
print(f"Priority set: {response.json()['result']['new_priority']}")

# Set 2-hour SLA
response = requests.post(
    "http://localhost:8001/api/priorities/sla/set",
    json={
        "task_id": 501,
        "sla_minutes": 120,
        "auto_escalate": True
    }
)
print(f"SLA deadline: {response.json()['sla']['deadline']}")

# 2. Get dynamic priority queue for agent
response = requests.get(
    "http://localhost:8001/api/priorities/queue/dynamic",
    params={"agent_id": 1, "include_sla": True}
)
queue = response.json()["queue"]
print(f"Top task: {queue[0]['task_title']} (score: {queue[0]['dynamic_score']})")

# 3. Check for SLA violations
response = requests.get("http://localhost:8001/api/priorities/sla/violations")
violations = response.json()["violations"]
if violations["violations_count"] > 0:
    print(f"WARNING: {violations['violations_count']} SLA breaches!")
    for v in violations["violations"]:
        print(f"  - Task {v['task_id']}: breached by {v['breached_by_minutes']} min")

# 4. Run automatic escalation (moderate policy)
response = requests.post(
    "http://localhost:8001/api/priorities/escalate",
    json={
        "policy": "moderate",
        "dry_run": False
    }
)
result = response.json()["result"]
print(f"Escalated {result['escalated_count']} tasks")

# 5. Get priority statistics
response = requests.get(
    "http://localhost:8001/api/priorities/statistics",
    params={"time_range_hours": 24}
)
stats = response.json()["statistics"]
print(f"Total tasks: {stats['total_tasks']}")
print(f"SLA breaches: {stats['sla_metrics']['breaches']}")
print(f"Avg completion time (critical): {stats['completion_times']['critical']['average_seconds']}s")
```

### Use Cases

**1. Production Incident Response**:
```python
# Escalate to critical and set tight SLA
requests.post(
    "http://localhost:8001/api/priorities/set-priority",
    json={"task_id": incident_task_id, "priority": "critical", "reason": "P1 incident"}
)
requests.post(
    "http://localhost:8001/api/priorities/sla/set",
    json={"task_id": incident_task_id, "sla_minutes": 30, "auto_escalate": True}
)
```

**2. SLA Monitoring Dashboard**:
```python
# Check violations every 5 minutes
violations = requests.get(
    "http://localhost:8001/api/priorities/sla/violations"
).json()["violations"]

# Alert if breaches detected
if violations["violations_count"] > 0:
    send_alert(f"{violations['violations_count']} SLA breaches detected!")
```

**3. Automatic Priority Management**:
```python
# Run escalation every hour with moderate policy
import schedule

def escalate_priorities():
    response = requests.post(
        "http://localhost:8001/api/priorities/escalate",
        json={"policy": "moderate", "dry_run": False}
    )
    print(f"Escalated {response.json()['result']['escalated_count']} tasks")

schedule.every().hour.do(escalate_priorities)
```

**4. Queue Optimization**:
```python
# Reorder all agent queues using dynamic priority
for agent_id in active_agent_ids:
    requests.post(
        "http://localhost:8001/api/priorities/reorder-queue",
        json={"agent_id": agent_id, "use_dynamic_priority": True}
    )
```

### Best Practices

**Priority Assignment**:
- Reserve CRITICAL for genuine emergencies (production outages, data loss)
- Use HIGH for important but non-emergency work
- Default to NORMAL for standard tasks
- Use LOW for nice-to-have improvements

**SLA Management**:
- Set realistic SLAs based on task complexity
- Enable auto_escalate for time-sensitive tasks
- Monitor SLA at-risk tasks proactively
- Review breach patterns to adjust SLAs

**Escalation Strategy**:
- Start with MODERATE policy and adjust based on workload
- Use AGGRESSIVE for production/real-time systems
- Use CONSERVATIVE for research/batch workloads
- Review escalation logs to tune thresholds

**Queue Management**:
- Use dynamic priority for better task ordering
- Reorder queues when SLA breaches occur
- Balance agent workloads with scheduler
- Monitor queue depth by priority level

**Monitoring**:
- Track completion times by priority
- Set alerts for SLA violations
- Review priority distribution trends
- Analyze escalation frequency

## Task Dependency Management

The Task Dependency Management System handles task dependencies, validates dependency graphs for cycles, provides topological execution ordering, and enables parallel execution of independent tasks.

### Dependency Types

The system supports 3 dependency relationship types:

- **BLOCKS** - Task A blocks task B (A must complete before B starts)
- **REQUIRES** - Task B requires task A (same as blocks, reverse direction)
- **RELATED** - Tasks are related but not blocking

### Add Task Dependency

Create a dependency relationship between tasks:

```bash
curl -X POST http://localhost:8001/api/dependencies/add \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 102,
    "depends_on_task_id": 101,
    "dependency_type": "blocks"
  }'
```

**Response**:
```json
{
  "success": true,
  "dependency": {
    "task_id": 102,
    "depends_on_task_id": 101,
    "dependency_type": "blocks",
    "task_title": "Deploy to production",
    "depends_on_task_title": "Run integration tests"
  },
  "message": "Dependency added: task 102 depends on 101"
}
```

**Cycle Detection**: The system automatically prevents circular dependencies.

### Add Dependency Chain

Create a sequential chain of dependencies:

```bash
curl -X POST http://localhost:8001/api/dependencies/add-chain \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": [101, 102, 103, 104]
  }'
```

**Response**:
```json
{
  "success": true,
  "total_dependencies": 3,
  "dependencies": [
    {
      "task_id": 102,
      "depends_on_task_id": 101,
      "dependency_type": "blocks",
      "task_title": "Build",
      "depends_on_task_title": "Test"
    },
    {
      "task_id": 103,
      "depends_on_task_id": 102,
      "dependency_type": "blocks",
      "task_title": "Deploy staging",
      "depends_on_task_title": "Build"
    },
    {
      "task_id": 104,
      "depends_on_task_id": 103,
      "dependency_type": "blocks",
      "task_title": "Deploy production",
      "depends_on_task_title": "Deploy staging"
    }
  ],
  "message": "Created dependency chain of 4 tasks"
}
```

Creates: 101 → 102 → 103 → 104

### Get Task Dependencies

View all dependencies for a task:

```bash
curl http://localhost:8001/api/dependencies/task/102
```

**Response**:
```json
{
  "success": true,
  "dependencies": {
    "task_id": 102,
    "task_title": "Deploy to production",
    "task_status": "pending",
    "depends_on": [
      {
        "task_id": 101,
        "task_title": "Run integration tests",
        "task_status": "completed",
        "dependency_type": "blocks",
        "is_completed": true
      }
    ],
    "dependent_tasks": [
      {
        "task_id": 103,
        "task_title": "Smoke tests",
        "task_status": "pending"
      }
    ],
    "total_dependencies": 1,
    "total_dependents": 1
  },
  "message": "Retrieved dependencies for task 102"
}
```

Shows:
- **depends_on**: Tasks that must complete first (prerequisites)
- **dependent_tasks**: Tasks waiting for this task (dependents)

### Check Task Readiness

Determine if a task is ready to execute:

```bash
curl http://localhost:8001/api/dependencies/task/102/ready
```

**Response** (not ready):
```json
{
  "success": true,
  "readiness": {
    "task_id": 102,
    "task_title": "Deploy to production",
    "is_ready": false,
    "blocking_tasks": [
      {
        "task_id": 101,
        "task_title": "Run integration tests",
        "task_status": "in_progress"
      }
    ],
    "total_dependencies": 1,
    "completed_dependencies": 0,
    "completion_percentage": 0,
    "message": "Blocked by 1 tasks"
  },
  "message": "Blocked by 1 tasks"
}
```

**Response** (ready):
```json
{
  "success": true,
  "readiness": {
    "task_id": 102,
    "task_title": "Deploy to production",
    "is_ready": true,
    "blocking_tasks": [],
    "total_dependencies": 1,
    "completed_dependencies": 1,
    "completion_percentage": 100,
    "message": "Ready to execute"
  },
  "message": "Ready to execute"
}
```

### Get Execution Order

Get topological execution order with parallel execution levels:

```bash
curl "http://localhost:8001/api/dependencies/execution-order?task_ids=101,102,103,104,105"
```

**Response**:
```json
{
  "success": true,
  "execution_order": [
    [101, 105],
    [102],
    [103, 104]
  ],
  "total_levels": 3,
  "total_tasks": 5,
  "max_parallelism": 2,
  "message": "Execution order with 3 levels"
}
```

**Execution Order Interpretation**:
- **Level 0** `[101, 105]`: Tasks with no dependencies - can run in parallel
- **Level 1** `[102]`: Tasks depending on Level 0 - runs after Level 0 completes
- **Level 2** `[103, 104]`: Tasks depending on Level 1 - can run in parallel after Level 1

**Max Parallelism**: Maximum number of tasks that can run simultaneously (2 in this case).

### Validate Dependency Graph

Check for cycles and orphaned dependencies:

```bash
curl -X POST http://localhost:8001/api/dependencies/validate \
  -H "Content-Type: application/json" \
  -d '{
    "task_ids": [101, 102, 103, 104]
  }'
```

**Response** (valid):
```json
{
  "success": true,
  "validation": {
    "valid": true,
    "total_tasks": 4,
    "total_errors": 0,
    "total_warnings": 0,
    "errors": [],
    "warnings": []
  },
  "message": "Valid dependency graph"
}
```

**Response** (with cycle):
```json
{
  "success": true,
  "validation": {
    "valid": false,
    "total_tasks": 4,
    "total_errors": 1,
    "total_warnings": 0,
    "errors": [
      {
        "type": "cycle_detected",
        "message": "Dependency cycle detected. Only 3/4 tasks can be ordered",
        "unordered_tasks": 1
      }
    ],
    "warnings": []
  },
  "message": "Validation errors found"
}
```

**Validation Checks**:
- **Cycles**: Circular dependencies that prevent execution
- **Orphaned Dependencies**: References to non-existent tasks
- **Long Chains**: Warning for chains longer than 10 tasks

### Get Dependency Graph

Get graph data for visualization:

```bash
curl "http://localhost:8001/api/dependencies/graph?task_ids=101,102,103"
```

**Response**:
```json
{
  "success": true,
  "graph": {
    "nodes": [
      {
        "id": 101,
        "label": "Run tests",
        "status": "completed",
        "priority": "high"
      },
      {
        "id": 102,
        "label": "Build application",
        "status": "in_progress",
        "priority": "high"
      },
      {
        "id": 103,
        "label": "Deploy",
        "status": "pending",
        "priority": "normal"
      }
    ],
    "edges": [
      {
        "from": 101,
        "to": 102,
        "type": "blocks"
      },
      {
        "from": 102,
        "to": 103,
        "type": "blocks"
      }
    ],
    "total_nodes": 3,
    "total_edges": 2
  },
  "message": "Dependency graph with 3 nodes and 2 edges"
}
```

**Graph Format**: Compatible with visualization libraries (vis.js, d3.js, cytoscape).

### Get Ready Tasks

Find all tasks ready to execute:

```bash
curl http://localhost:8001/api/dependencies/ready-tasks
```

**Response**:
```json
{
  "success": true,
  "total_ready": 3,
  "ready_tasks": [
    {
      "task_id": 105,
      "task_title": "Update documentation",
      "task_status": "pending",
      "priority": "low"
    },
    {
      "task_id": 106,
      "task_title": "Send notifications",
      "task_status": "queued",
      "priority": "normal"
    },
    {
      "task_id": 107,
      "task_title": "Archive logs",
      "task_status": "pending",
      "priority": "low"
    }
  ],
  "message": "Found 3 ready tasks"
}
```

**Use Case**: Schedulers use this to find next tasks to assign to agents.

### Remove Dependency

Remove a dependency relationship:

```bash
curl -X DELETE http://localhost:8001/api/dependencies/remove \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 102,
    "depends_on_task_id": 101
  }'
```

**Response**:
```json
{
  "success": true,
  "message": "Dependency removed: task 102 -> 101"
}
```

### Integration Example

Complete workflow for dependency management:

```python
import requests

# 1. Create a deployment pipeline with dependencies
pipeline_tasks = [101, 102, 103, 104]  # test → build → stage → prod

# Add dependency chain
response = requests.post(
    "http://localhost:8001/api/dependencies/add-chain",
    json={"task_ids": pipeline_tasks}
)
print(f"Created chain: {response.json()['total_dependencies']} dependencies")

# 2. Add parallel tasks (can run alongside main pipeline)
# Documentation task (no dependencies - can run anytime)
# Notification task (depends on production deployment)
response = requests.post(
    "http://localhost:8001/api/dependencies/add",
    json={
        "task_id": 105,  # Notifications
        "depends_on_task_id": 104,  # Production deployment
        "dependency_type": "blocks"
    }
)

# 3. Validate the dependency graph
response = requests.post(
    "http://localhost:8001/api/dependencies/validate",
    json={"task_ids": [101, 102, 103, 104, 105]}
)
validation = response.json()["validation"]
if not validation["valid"]:
    print(f"ERROR: {validation['errors']}")
    exit(1)

# 4. Get execution order with parallelism
response = requests.get(
    "http://localhost:8001/api/dependencies/execution-order",
    params={"task_ids": ",".join(map(str, [101, 102, 103, 104, 105]))}
)
execution_order = response.json()["execution_order"]
print(f"Execution levels: {len(execution_order)}")
print(f"Max parallelism: {response.json()['max_parallelism']}")

# 5. Execute tasks level by level
for level_num, level_tasks in enumerate(execution_order):
    print(f"\nLevel {level_num}: {len(level_tasks)} tasks (parallel)")

    # Start all tasks in this level (they can run in parallel)
    for task_id in level_tasks:
        # Check readiness
        readiness = requests.get(
            f"http://localhost:8001/api/dependencies/task/{task_id}/ready"
        ).json()["readiness"]

        if readiness["is_ready"]:
            print(f"  Starting task {task_id}")
            # Start task execution here
        else:
            print(f"  Task {task_id} blocked by {len(readiness['blocking_tasks'])} tasks")

    # Wait for all tasks in this level to complete before moving to next level

# 6. Get ready tasks for dynamic scheduling
response = requests.get("http://localhost:8001/api/dependencies/ready-tasks")
ready = response.json()["ready_tasks"]
print(f"\n{len(ready)} tasks ready for immediate execution")
```

### Use Cases

**1. CI/CD Pipeline**:
```python
# Create deployment pipeline: test → build → deploy-staging → deploy-prod
pipeline = {
    "test": 201,
    "build": 202,
    "deploy_staging": 203,
    "deploy_prod": 204
}

# Chain dependencies
requests.post(
    "http://localhost:8001/api/dependencies/add-chain",
    json={"task_ids": list(pipeline.values())}
)

# Add parallel smoke tests after staging
requests.post(
    "http://localhost:8001/api/dependencies/add",
    json={
        "task_id": 205,  # Smoke tests
        "depends_on_task_id": pipeline["deploy_staging"],
        "dependency_type": "blocks"
    }
)
```

**2. Data Processing DAG**:
```python
# Extract → [Transform A, Transform B] → Load
extract_task = 301
transform_a = 302
transform_b = 303
load_task = 304

# Both transforms depend on extract
for transform in [transform_a, transform_b]:
    requests.post(
        "http://localhost:8001/api/dependencies/add",
        json={"task_id": transform, "depends_on_task_id": extract_task}
    )

# Load depends on both transforms
for transform in [transform_a, transform_b]:
    requests.post(
        "http://localhost:8001/api/dependencies/add",
        json={"task_id": load_task, "depends_on_task_id": transform}
    )

# Get execution order - transforms will be in same level (parallel)
order = requests.get(
    "http://localhost:8001/api/dependencies/execution-order"
).json()["execution_order"]
# [[301], [302, 303], [304]]
```

**3. Microservice Deployment**:
```python
# Deploy services with dependencies: database → api → web → cache
services = {
    "database": 401,
    "api": 402,
    "web": 403,
    "cache": 404
}

# Database has no dependencies
# API depends on database
requests.post(
    "http://localhost:8001/api/dependencies/add",
    json={"task_id": services["api"], "depends_on_task_id": services["database"]}
)

# Web depends on API
requests.post(
    "http://localhost:8001/api/dependencies/add",
    json={"task_id": services["web"], "depends_on_task_id": services["api"]}
)

# Cache depends on database (can run parallel with API)
requests.post(
    "http://localhost:8001/api/dependencies/add",
    json={"task_id": services["cache"], "depends_on_task_id": services["database"]}
)
```

**4. Dynamic Task Scheduling**:
```python
import time

while True:
    # Get tasks ready for execution
    response = requests.get("http://localhost:8001/api/dependencies/ready-tasks")
    ready_tasks = response.json()["ready_tasks"]

    if not ready_tasks:
        print("No ready tasks, waiting...")
        time.sleep(5)
        continue

    # Assign ready tasks to available agents
    for task in ready_tasks:
        print(f"Scheduling task {task['task_id']}: {task['task_title']}")
        # Schedule to agent here

    time.sleep(10)
```

### Best Practices

**Dependency Design**:
- Keep dependency chains short (< 10 tasks)
- Use parallel execution when tasks are independent
- Group related tasks into sub-workflows
- Avoid unnecessary dependencies that limit parallelism

**Cycle Prevention**:
- Validate graph before execution
- Use add-chain for sequential workflows
- Test complex dependency graphs with validate endpoint
- Review execution order to verify parallelism

**Execution Strategy**:
- Execute tasks level-by-level from execution order
- Run all tasks in same level in parallel
- Wait for level completion before starting next level
- Use ready-tasks endpoint for dynamic scheduling

**Graph Visualization**:
- Use graph endpoint data with visualization libraries
- Highlight blocking tasks in red
- Show execution levels with different colors
- Display task status on nodes

**Performance**:
- Maximize parallelism by minimizing dependencies
- Balance between parallelism and resource usage
- Monitor max_parallelism metric
- Use ready-tasks for efficient scheduling

**Maintenance**:
- Validate graph after adding dependencies
- Check for orphaned dependencies regularly
- Review long chains (warnings)
- Remove dependencies when no longer needed

## Agent Resource Management

The Agent Resource Management System handles resource allocation, monitoring, and limits for agents. It tracks CPU, memory, GPU, disk, and network resources across the agent cluster, enabling efficient resource utilization and preventing overallocation.

### Resource Types

The system tracks 5 resource types:

- **CPU** - CPU cores (decimal values, e.g., 2.5 cores)
- **MEMORY** - RAM in GB
- **GPU** - GPU units (integer values)
- **DISK** - Disk space in GB
- **NETWORK** - Network bandwidth in Mbps

### Set Resource Limits

Configure maximum resources for an agent:

```bash
curl -X POST http://localhost:8001/api/resources/limits/set \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "cpu": 4.0,
    "memory": 16.0,
    "gpu": 1,
    "disk": 500.0,
    "network": 1000.0
  }'
```

**Response**:
```json
{
  "success": true,
  "agent_id": 1,
  "limits": {
    "cpu": 4.0,
    "memory": 16.0,
    "gpu": 1,
    "disk": 500.0,
    "network": 1000.0
  },
  "message": "Resource limits updated for agent 1"
}
```

**Default Limits** (if not set):
- CPU: 2.0 cores
- Memory: 4.0 GB
- GPU: 0 units
- Disk: 100.0 GB
- Network: 100.0 Mbps

### Get Resource Limits

Retrieve configured limits for an agent:

```bash
curl http://localhost:8001/api/resources/limits/1
```

**Response**:
```json
{
  "success": true,
  "agent_id": 1,
  "limits": {
    "cpu": 4.0,
    "memory": 16.0,
    "gpu": 1,
    "disk": 500.0,
    "network": 1000.0
  },
  "message": "Resource limits for agent 1"
}
```

### Update Resource Usage

Report current resource consumption (typically called by monitoring systems):

```bash
curl -X POST http://localhost:8001/api/resources/usage/set \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "cpu": 2.5,
    "memory": 8.0,
    "gpu": 0,
    "disk": 50.0,
    "network": 200.0
  }'
```

**Response**:
```json
{
  "success": true,
  "agent_id": 1,
  "usage": {
    "cpu": 2.5,
    "memory": 8.0,
    "gpu": 0,
    "disk": 50.0,
    "network": 200.0,
    "last_updated": "2024-01-15T10:30:00Z"
  },
  "message": "Resource usage updated for agent 1"
}
```

### Get Resource Usage

Get current usage with utilization percentages:

```bash
curl http://localhost:8001/api/resources/usage/1
```

**Response**:
```json
{
  "success": true,
  "usage_info": {
    "agent_id": 1,
    "usage": {
      "cpu": 2.5,
      "memory": 8.0,
      "gpu": 0,
      "disk": 50.0,
      "network": 200.0,
      "last_updated": "2024-01-15T10:30:00Z"
    },
    "limits": {
      "cpu": 4.0,
      "memory": 16.0,
      "gpu": 1,
      "disk": 500.0,
      "network": 1000.0
    },
    "utilization_percentage": {
      "cpu": 62.5,
      "memory": 50.0,
      "gpu": 0.0,
      "disk": 10.0,
      "network": 20.0
    },
    "is_overloaded": false
  },
  "message": "Resource usage for agent 1"
}
```

**is_overloaded**: True if any resource exceeds 90% utilization.

### Check Resource Availability

Verify if an agent has sufficient resources:

```bash
curl -X POST http://localhost:8001/api/resources/check-availability \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "required_cpu": 1.0,
    "required_memory": 4.0,
    "required_gpu": 0,
    "required_disk": 10.0,
    "required_network": 100.0
  }'
```

**Response**:
```json
{
  "success": true,
  "availability": {
    "agent_id": 1,
    "available": {
      "cpu": 1.5,
      "memory": 8.0,
      "gpu": 1,
      "disk": 450.0,
      "network": 800.0
    },
    "required": {
      "cpu": 1.0,
      "memory": 4.0,
      "gpu": 0,
      "disk": 10.0,
      "network": 100.0
    },
    "sufficient": true,
    "shortfall": null
  },
  "message": "Agent has sufficient resources"
}
```

**If insufficient**:
```json
{
  "success": true,
  "availability": {
    "agent_id": 1,
    "available": {
      "cpu": 0.5,
      "memory": 2.0,
      "gpu": 0,
      "disk": 10.0,
      "network": 50.0
    },
    "required": {
      "cpu": 2.0,
      "memory": 8.0,
      "gpu": 1,
      "disk": 100.0,
      "network": 500.0
    },
    "sufficient": false,
    "shortfall": {
      "cpu": 1.5,
      "memory": 6.0,
      "gpu": 1,
      "disk": 90.0,
      "network": 450.0
    }
  },
  "message": "Insufficient resources"
}
```

### Find Agents with Resources

Search for agents that can accommodate specific resource requirements:

```bash
curl -X POST http://localhost:8001/api/resources/find-agents \
  -H "Content-Type: application/json" \
  -d '{
    "required_cpu": 2.0,
    "required_memory": 8.0,
    "required_gpu": 1,
    "required_disk": 50.0,
    "required_network": 200.0,
    "status": "active"
  }'
```

**Response**:
```json
{
  "success": true,
  "total_agents": 3,
  "agents": [
    {
      "agent_id": 2,
      "agent_name": "Agent-Worker-02",
      "agent_role": "coder",
      "agent_status": "active",
      "available_resources": {
        "cpu": 6.0,
        "memory": 24.0,
        "gpu": 2,
        "disk": 900.0,
        "network": 1500.0
      },
      "utilization": {
        "cpu": 25.0,
        "memory": 33.3,
        "gpu": 0.0,
        "disk": 10.0,
        "network": 13.3
      }
    },
    {
      "agent_id": 3,
      "agent_name": "Agent-Worker-03",
      "agent_role": "researcher",
      "agent_status": "active",
      "available_resources": {
        "cpu": 4.0,
        "memory": 12.0,
        "gpu": 1,
        "disk": 400.0,
        "network": 800.0
      },
      "utilization": {
        "cpu": 50.0,
        "memory": 50.0,
        "gpu": 50.0,
        "disk": 20.0,
        "network": 37.5
      }
    },
    {
      "agent_id": 1,
      "agent_name": "Agent-Worker-01",
      "agent_role": "coder",
      "agent_status": "active",
      "available_resources": {
        "cpu": 1.5,
        "memory": 8.0,
        "gpu": 1,
        "disk": 450.0,
        "network": 800.0
      },
      "utilization": {
        "cpu": 62.5,
        "memory": 50.0,
        "gpu": 0.0,
        "disk": 10.0,
        "network": 20.0
      }
    }
  ],
  "message": "Found 3 suitable agents"
}
```

Agents are **sorted by lowest average utilization** (prefer less loaded agents).

### Reserve Resources

Reserve resources for a task execution:

```bash
curl -X POST http://localhost:8001/api/resources/reserve \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "execution_id": 42,
    "cpu": 2.0,
    "memory": 8.0,
    "gpu": 0,
    "disk": 20.0,
    "network": 500.0
  }'
```

**Response**:
```json
{
  "success": true,
  "reservation": {
    "execution_id": 42,
    "cpu": 2.0,
    "memory": 8.0,
    "gpu": 0,
    "disk": 20.0,
    "network": 500.0,
    "reserved_at": "2024-01-15T10:35:00Z"
  },
  "message": "Resources reserved for execution 42"
}
```

**Failure (insufficient resources)**:
```json
{
  "success": false,
  "detail": "Insufficient resources. Shortfall: {'cpu': 1.0, 'memory': 4.0}"
}
```

The reservation:
- Adds resource amounts to current usage
- Prevents overallocation
- Tracked in agent metadata

### Release Resources

Release reserved resources after task completion:

```bash
curl -X POST http://localhost:8001/api/resources/release \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "execution_id": 42
  }'
```

**Response**:
```json
{
  "success": true,
  "message": "Resources released for execution 42"
}
```

**If not found**:
```json
{
  "success": false,
  "message": "No reservation found for execution 42 on agent 1"
}
```

### Get Cluster Resources

View cluster-wide resource statistics:

```bash
curl http://localhost:8001/api/resources/cluster
```

**Response**:
```json
{
  "success": true,
  "cluster": {
    "total_agents": 5,
    "total_limits": {
      "cpu": 20.0,
      "memory": 80.0,
      "gpu": 5,
      "disk": 2000.0,
      "network": 5000.0
    },
    "total_usage": {
      "cpu": 12.5,
      "memory": 40.0,
      "gpu": 2,
      "disk": 500.0,
      "network": 1500.0
    },
    "total_available": {
      "cpu": 7.5,
      "memory": 40.0,
      "gpu": 3,
      "disk": 1500.0,
      "network": 3500.0
    },
    "cluster_utilization_percentage": {
      "cpu": 62.5,
      "memory": 50.0,
      "gpu": 40.0,
      "disk": 25.0,
      "network": 30.0
    },
    "average_utilization": 41.5
  },
  "message": "Cluster resources for 5 agents"
}
```

### Get Resource Alerts

Find overloaded agents (>90% utilization by default):

```bash
curl "http://localhost:8001/api/resources/alerts?threshold=90.0"
```

**Response**:
```json
{
  "success": true,
  "threshold": 90.0,
  "total_alerts": 2,
  "alerts": [
    {
      "agent_id": 3,
      "agent_name": "Agent-Worker-03",
      "agent_status": "active",
      "overloaded_resources": {
        "cpu": 95.0,
        "memory": 92.5
      },
      "usage": {
        "cpu": 3.8,
        "memory": 14.8,
        "gpu": 0,
        "disk": 50.0,
        "network": 200.0
      },
      "limits": {
        "cpu": 4.0,
        "memory": 16.0,
        "gpu": 1,
        "disk": 500.0,
        "network": 1000.0
      }
    },
    {
      "agent_id": 5,
      "agent_name": "Agent-Worker-05",
      "agent_status": "active",
      "overloaded_resources": {
        "network": 98.0
      },
      "usage": {
        "cpu": 2.0,
        "memory": 8.0,
        "gpu": 0,
        "disk": 100.0,
        "network": 980.0
      },
      "limits": {
        "cpu": 4.0,
        "memory": 16.0,
        "gpu": 0,
        "disk": 500.0,
        "network": 1000.0
      }
    }
  ],
  "message": "Found 2 agents above 90.0% utilization"
}
```

### Use Cases

#### 1. Task Scheduling with Resource Requirements

```python
import requests

# 1. Define task resource requirements
required_resources = {
    "required_cpu": 2.0,
    "required_memory": 8.0,
    "required_gpu": 1,
    "required_disk": 50.0,
    "required_network": 200.0,
    "status": "active"
}

# 2. Find suitable agents
response = requests.post(
    "http://localhost:8001/api/resources/find-agents",
    json=required_resources
)

agents = response.json()["agents"]

if agents:
    # Pick agent with lowest utilization (first in list)
    best_agent = agents[0]
    agent_id = best_agent["agent_id"]

    # 3. Reserve resources before execution
    reservation = requests.post(
        "http://localhost:8001/api/resources/reserve",
        json={
            "agent_id": agent_id,
            "execution_id": 42,
            "cpu": 2.0,
            "memory": 8.0,
            "gpu": 1,
            "disk": 50.0,
            "network": 200.0
        }
    )

    print(f"Resources reserved on agent {agent_id}")

    # 4. Execute task...
    # ... task execution code ...

    # 5. Release resources after completion
    requests.post(
        "http://localhost:8001/api/resources/release",
        json={
            "agent_id": agent_id,
            "execution_id": 42
        }
    )

    print("Resources released")
else:
    print("No agents with sufficient resources available")
```

#### 2. Resource Monitoring Dashboard

```python
import requests
import time

def monitor_cluster():
    while True:
        # Get cluster-wide stats
        cluster = requests.get(
            "http://localhost:8001/api/resources/cluster"
        ).json()["cluster"]

        print(f"\n=== Cluster Resources ===")
        print(f"Total Agents: {cluster['total_agents']}")
        print(f"Average Utilization: {cluster['average_utilization']:.1f}%")

        print(f"\nCPU: {cluster['total_usage']['cpu']}/{cluster['total_limits']['cpu']} cores "
              f"({cluster['cluster_utilization_percentage']['cpu']:.1f}%)")

        print(f"Memory: {cluster['total_usage']['memory']}/{cluster['total_limits']['memory']} GB "
              f"({cluster['cluster_utilization_percentage']['memory']:.1f}%)")

        # Check for overloaded agents
        alerts = requests.get(
            "http://localhost:8001/api/resources/alerts?threshold=90.0"
        ).json()["alerts"]

        if alerts:
            print(f"\n⚠️  {len(alerts)} agents overloaded:")
            for alert in alerts:
                print(f"  Agent {alert['agent_id']} - {alert['overloaded_resources']}")

        time.sleep(30)  # Check every 30 seconds

monitor_cluster()
```

#### 3. Auto-scaling Based on Utilization

```python
import requests

def check_and_scale():
    # Get cluster stats
    cluster = requests.get(
        "http://localhost:8001/api/resources/cluster"
    ).json()["cluster"]

    avg_util = cluster["average_utilization"]

    if avg_util > 80:
        print(f"🔴 High utilization ({avg_util:.1f}%) - scaling up")
        # Add new agent or increase limits

    elif avg_util < 20:
        print(f"🟢 Low utilization ({avg_util:.1f}%) - can scale down")
        # Remove idle agents

    else:
        print(f"✅ Optimal utilization ({avg_util:.1f}%)")
```

#### 4. Resource Limit Configuration

```python
import requests

# Configure limits for different agent types

# High-performance agent
requests.post(
    "http://localhost:8001/api/resources/limits/set",
    json={
        "agent_id": 1,
        "cpu": 8.0,
        "memory": 32.0,
        "gpu": 2,
        "disk": 1000.0,
        "network": 2000.0
    }
)

# Standard agent
requests.post(
    "http://localhost:8001/api/resources/limits/set",
    json={
        "agent_id": 2,
        "cpu": 4.0,
        "memory": 16.0,
        "gpu": 1,
        "disk": 500.0,
        "network": 1000.0
    }
)

# Lightweight agent
requests.post(
    "http://localhost:8001/api/resources/limits/set",
    json={
        "agent_id": 3,
        "cpu": 2.0,
        "memory": 8.0,
        "gpu": 0,
        "disk": 100.0,
        "network": 500.0
    }
)

print("Resource limits configured for all agents")
```

### Best Practices

**Resource Allocation**:
- Always check availability before reserving
- Use find-agents to pick optimal agent (lowest utilization)
- Reserve resources at task start, release on completion
- Set appropriate limits based on agent hardware

**Monitoring**:
- Poll cluster stats regularly
- Set up alerts for >90% utilization
- Track average utilization for capacity planning
- Monitor individual agents for bottlenecks

**Scaling**:
- Scale up when average utilization >80%
- Scale down when average utilization <20%
- Add agents incrementally based on workload
- Remove agents gracefully (wait for tasks to complete)

**Troubleshooting**:
- Check resource alerts for overloaded agents
- Verify reservations are released after task completion
- Review cluster stats for capacity issues
- Check agent limits if tasks fail to schedule

## Agent Collaboration

The Agent Collaboration System enables multiple agents to work together on complex tasks through structured collaboration patterns, role assignments, and handoff mechanisms.

### Collaboration Patterns

- **PARALLEL** - Agents work simultaneously on different parts
- **SEQUENTIAL** - Agents work in sequence, passing work along
- **HIERARCHICAL** - Leader agent coordinates worker agents
- **PEER_TO_PEER** - Agents collaborate as equals without hierarchy

### Create Collaboration

```bash
curl -X POST http://localhost:8001/api/collaboration/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Code Review Collaboration",
    "task_id": 101,
    "agent_ids": [1, 2, 3],
    "pattern": "sequential"
  }'
```

Creates a multi-agent collaboration session with specified pattern and agents.

### Assign Roles

```bash
curl -X POST http://localhost:8001/api/collaboration/assign-role \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 101,
    "collaboration_id": 1,
    "agent_id": 1,
    "role": "leader"
  }'
```

**Roles**: leader, contributor, reviewer, coordinator

### Create Handoff

```bash
curl -X POST http://localhost:8001/api/collaboration/handoff/create \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 101,
    "collaboration_id": 1,
    "from_agent_id": 1,
    "to_agent_id": 2,
    "handoff_type": "work",
    "context": {"work_item": "Implement auth module"}
  }'
```

**Handoff Types**: work, review, approval

### Get Collaboration Metrics

```bash
curl http://localhost:8001/api/collaboration/metrics/101/1
```

Returns metrics including handoff success rate, active agents, and duration.

### Form Team Automatically

```bash
curl -X POST http://localhost:8001/api/collaboration/form-team \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 102,
    "required_roles": ["researcher", "coder", "reviewer"],
    "max_agents": 5
  }'
```

Automatically selects agents with required roles and checks coverage.

## Agent Load Balancing

The Agent Load Balancing System intelligently distributes tasks across agents using various strategies to optimize resource utilization and performance.

### Load Balancing Strategies

- **round_robin** - Distribute evenly in sequence
- **least_loaded** - Pick agent with lowest current load (default)
- **weighted** - Weighted random based on capacity
- **random** - Random selection
- **capability_based** - Best capability match
- **performance_based** - Based on historical performance

### Select Agent for Task

```bash
curl -X POST http://localhost:8001/api/load-balancer/select-agent \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 101,
    "strategy": "least_loaded",
    "required_role": "coder"
  }'
```

Intelligently selects the best agent using the specified strategy.

### Get Load Distribution

```bash
curl http://localhost:8001/api/load-balancer/distribution
```

Returns how tasks are distributed across agents with balance score (0-100).

### Rebalance Tasks

```bash
curl -X POST http://localhost:8001/api/load-balancer/rebalance \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": "least_loaded",
    "dry_run": true
  }'
```

Moves queued tasks from overloaded to underloaded agents. Use `dry_run: true` to preview.

### Get Agent Capacity

```bash
curl http://localhost:8001/api/load-balancer/capacity/1
```

Returns agent's current capacity, utilization, and whether it can accept more tasks.

### Check Health

```bash
curl http://localhost:8001/api/load-balancer/health
```

Returns overall cluster health status (healthy/degraded/unhealthy).

## Agent Health Monitoring

The Agent Health Monitoring System tracks agent health, detects anomalies, analyzes failures, and provides uptime statistics.

### Health Statuses

- **HEALTHY** - Agent is operating normally with no issues
- **DEGRADED** - Agent has warnings but is still functional
- **UNHEALTHY** - Agent has critical issues affecting functionality
- **UNKNOWN** - Agent health cannot be determined

### Check Agent Health

```bash
curl http://localhost:8001/api/health-monitor/check/1
```

Performs comprehensive health check with 5 checks:
- Agent status (active/inactive)
- Heartbeat (last activity < 5 minutes)
- Resource utilization (< 90%)
- Error rate (< 10%)
- Execution performance (avg duration)

Returns overall health status with detailed check results.

### Record Heartbeat

```bash
curl -X POST http://localhost:8001/api/health-monitor/heartbeat \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1
  }'
```

Records heartbeat to indicate agent is alive and responsive. Agents should call this periodically.

### Get Uptime Statistics

```bash
curl http://localhost:8001/api/health-monitor/uptime/1?days=7
```

Returns uptime percentage, total executions (successful/failed), active hours, and failure breakdown.

### Get Cluster Health

```bash
curl http://localhost:8001/api/health-monitor/cluster
```

Returns aggregate health across all agents:
- Cluster health status
- Healthy/degraded/unhealthy agent counts
- Healthy percentage
- Individual agent health summary

### Detect Anomalies

```bash
curl http://localhost:8001/api/health-monitor/anomalies/1?threshold_std_dev=2.0
```

Detects executions with abnormal duration using z-score analysis. Higher threshold = fewer anomalies detected.

### Get Failure Analysis

```bash
curl http://localhost:8001/api/health-monitor/failures/1?days=7
```

Returns failure analysis with:
- Total failures
- Failure categories (timeout/resource/error/unknown)
- Failure timeline with details

### Set Health Threshold

```bash
curl -X POST http://localhost:8001/api/health-monitor/threshold \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "check_type": "error_rate",
    "threshold_value": 15.0
  }'
```

Customizes health check thresholds:
- **error_rate** - Error rate percentage threshold
- **response_time** - Maximum acceptable response time
- **resource_usage** - Resource utilization threshold

## Agent Event System

The Agent Event System tracks and manages agent-related events for monitoring, auditing, and real-time updates.

### Event Categories

- **Lifecycle** - agent.created, agent.activated, agent.deactivated
- **Task** - task.assigned, task.started, task.completed, task.failed
- **Execution** - execution.started, execution.completed, execution.failed
- **Health** - health.degraded, health.unhealthy, health.recovered
- **Resource** - resource.allocated, resource.released, resource.exhausted
- **Collaboration** - collaboration.started, handoff.initiated
- **Load Balancing** - task.rebalanced, agent.overloaded
- **Error** - error.occurred, anomaly.detected, sla.breach

### Event Severities

- **DEBUG** - Detailed debugging information
- **INFO** - General informational events (default)
- **WARNING** - Warning events needing attention
- **ERROR** - Error events indicating failures
- **CRITICAL** - Critical events requiring immediate action

### Emit Event

```bash
curl -X POST http://localhost:8001/api/events/emit \
  -H "Content-Type: application/json" \
  -d '{
    "event_type": "task.completed",
    "agent_id": 1,
    "task_id": 101,
    "severity": "info",
    "message": "Task completed successfully",
    "metadata": {"duration_seconds": 42}
  }'
```

Manually emit events for testing or custom integrations. Events are stored and listeners are notified.

### Get Agent Events

```bash
curl "http://localhost:8001/api/events/agent/1?event_types=task.completed,task.failed&severities=info,error&limit=50"
```

Returns events for a specific agent with optional filtering by event types, severities, and time range.

### Get Recent Events

```bash
curl "http://localhost:8001/api/events/recent?minutes=60&severities=error,critical"
```

Returns recent events across all agents. Useful for monitoring recent activity.

### Get Event Timeline

```bash
curl "http://localhost:8001/api/events/timeline?agent_id=1&hours=24&granularity_minutes=60"
```

Returns events aggregated into time buckets with statistics. Useful for visualizing trends and patterns.

### Get Critical Events

```bash
curl "http://localhost:8001/api/events/critical?hours=24"
```

Returns all ERROR and CRITICAL events for quick problem identification and alerting.

### Clear Agent Events

```bash
curl -X POST http://localhost:8001/api/events/clear \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "older_than_hours": 72
  }'
```

Clears events for an agent. Optionally clear only events older than specified hours.

### List Event Types

```bash
curl http://localhost:8001/api/events/types
```

Returns all available event types organized by category.

### List Event Severities

```bash
curl http://localhost:8001/api/events/severities
```

Returns all event severity levels with descriptions.

## DAG Workflow Engine

The DAG Workflow Engine manages and executes complex multi-step workflows with dependency management and parallel execution.

### Workflow Statuses

- **PENDING** - Workflow created but not started
- **RUNNING** - Workflow is currently executing
- **PAUSED** - Workflow execution is paused
- **COMPLETED** - Workflow completed successfully
- **FAILED** - Workflow failed
- **CANCELLED** - Workflow was cancelled

### Step Statuses

- **PENDING** - Step waiting for dependencies
- **READY** - Step ready to execute
- **RUNNING** - Step is currently executing
- **COMPLETED** - Step completed successfully
- **FAILED** - Step failed
- **SKIPPED** - Step was skipped

### Create Workflow

```bash
curl -X POST http://localhost:8001/api/workflow-engine \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Code Review Pipeline",
    "description": "Automated code review workflow",
    "steps": [
      {
        "step_id": "analyze",
        "name": "Analyze Code",
        "agent_type": "analyzer",
        "task_description": "Analyze code for issues",
        "depends_on": [],
        "timeout_minutes": 30,
        "retry_count": 3
      },
      {
        "step_id": "review",
        "name": "Review Analysis",
        "agent_type": "reviewer",
        "task_description": "Review analysis results",
        "depends_on": ["analyze"],
        "timeout_minutes": 20,
        "retry_count": 2
      },
      {
        "step_id": "report",
        "name": "Generate Report",
        "agent_type": "reporter",
        "task_description": "Generate final report",
        "depends_on": ["review"],
        "timeout_minutes": 10,
        "retry_count": 1
      }
    ]
  }'
```

Creates a DAG workflow with steps and dependencies. Steps execute in dependency order with parallel execution where possible.

### Start Workflow

```bash
curl -X POST http://localhost:8001/api/workflow-engine/1/start
```

Starts workflow execution. Steps with no dependencies execute immediately in parallel.

### Get Workflow Status

```bash
curl http://localhost:8001/api/workflow-engine/1/status
```

Returns detailed workflow status including:
- Overall workflow status
- Progress (completed/total steps, percentage)
- Timeline (created, started, completed times, duration)
- Individual step statuses with results/errors

### Pause Workflow

```bash
curl -X POST http://localhost:8001/api/workflow-engine/1/pause
```

Pauses workflow execution. Currently running steps will complete, but new steps won't start.

### Resume Workflow

```bash
curl -X POST http://localhost:8001/api/workflow-engine/1/resume
```

Resumes paused workflow execution.

### Cancel Workflow

```bash
curl -X POST http://localhost:8001/api/workflow-engine/1/cancel \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "User requested cancellation"
  }'
```

Cancels workflow permanently. Cannot be resumed.

### Update Step Status

```bash
curl -X POST http://localhost:8001/api/workflow-engine/1/steps/update \
  -H "Content-Type: application/json" \
  -d '{
    "step_id": "analyze",
    "status": "completed",
    "result": {"issues_found": 5}
  }'
```

Updates step status. Called when steps complete or fail. Triggers execution of dependent steps.

### List Workflows

```bash
curl "http://localhost:8001/api/workflow-engine?status=running&limit=50"
```

Lists workflows with optional status filtering and pagination.

### Delete Workflow

```bash
curl -X DELETE http://localhost:8001/api/workflow-engine/1
```

Deletes a workflow. Can only delete workflows that are not running.

## Shared Memory System

The Shared Memory System enables agents to share data and coordinate through scoped memory with atomic operations.

### Memory Scopes

- **GLOBAL** - Accessible by all agents globally
- **WORKFLOW** - Scoped to a specific workflow
- **AGENT** - Scoped to a specific agent
- **TASK** - Scoped to a specific task
- **SESSION** - Scoped to a session

### Memory Types

- **PERMANENT** - Never expires, persists indefinitely
- **TEMPORARY** - Expires based on TTL setting
- **SESSION** - Expires when session ends

### Set Memory

```bash
curl -X POST http://localhost:8001/api/shared-memory/set \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "workflow",
    "scope_id": "123",
    "key": "current_step",
    "value": "analysis",
    "memory_type": "temporary",
    "ttl_seconds": 3600
  }'
```

Stores a value in shared memory with optional expiration.

### Get Memory

```bash
curl -X POST http://localhost:8001/api/shared-memory/get \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "workflow",
    "scope_id": "123",
    "key": "current_step",
    "default": "unknown"
  }'
```

Retrieves a value from shared memory. Returns default if not found or expired.

### List Memory

```bash
curl "http://localhost:8001/api/shared-memory/list?scope=workflow&scope_id=123&pattern=step*"
```

Lists memory entries with filtering by scope, scope_id, memory_type, and key pattern (supports wildcards).

### Delete Memory

```bash
curl -X POST http://localhost:8001/api/shared-memory/delete \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "workflow",
    "scope_id": "123",
    "key": "current_step"
  }'
```

Deletes a specific memory key.

### Clear Scope

```bash
curl -X POST http://localhost:8001/api/shared-memory/clear-scope \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "workflow",
    "scope_id": "123"
  }'
```

Clears all memory entries in a scope. Use with caution.

### Memory Statistics

```bash
curl http://localhost:8001/api/shared-memory/stats
```

Returns statistics including total entries, breakdowns by scope/type/scope_id, and expired entries cleaned.

### Create Snapshot

```bash
curl -X POST http://localhost:8001/api/shared-memory/snapshot/create \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "workflow",
    "scope_id": "123",
    "snapshot_name": "before_critical_operation"
  }'
```

Creates a snapshot of memory state for backup/restore scenarios.

### Restore Snapshot

```bash
curl -X POST http://localhost:8001/api/shared-memory/snapshot/restore \
  -H "Content-Type: application/json" \
  -d '{
    "snapshot_key": "snapshot:workflow:123:before_critical_operation",
    "overwrite": false
  }'
```

Restores memory from a snapshot. Set overwrite=true to replace existing entries.

### Atomic Increment

```bash
curl -X POST http://localhost:8001/api/shared-memory/atomic/increment \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "global",
    "key": "task_counter",
    "delta": 1
  }'
```

Thread-safe atomic increment for counters and sequence generation.

### Compare-and-Swap

```bash
curl -X POST http://localhost:8001/api/shared-memory/atomic/cas \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "workflow",
    "scope_id": "123",
    "key": "lock_status",
    "expected_value": "unlocked",
    "new_value": "locked"
  }'
```

Atomically updates value only if current value matches expected. Useful for lock-free synchronization.

### Get-or-Set

```bash
curl -X POST http://localhost:8001/api/shared-memory/get-or-set \
  -H "Content-Type: application/json" \
  -d '{
    "scope": "agent",
    "scope_id": "1",
    "key": "initialized",
    "default_value": true
  }'
```

Returns existing value or sets and returns default. Useful for lazy initialization.

## Agent Communication Protocols

The Agent Communication Protocol system enables structured messaging and coordination between agents using multiple communication patterns.

### Communication Protocols

- **DIRECT** - One-to-one direct messaging
- **BROADCAST** - Message to all active agents
- **MULTICAST** - Message to specific group of agents
- **PUBSUB** - Publish-subscribe topic-based messaging
- **REQUEST_REPLY** - Request-reply pattern with tracking

### Message Types

- **REQUEST** - Request for action or information
- **RESPONSE** - Reply to a request
- **BROADCAST** - General announcement
- **NOTIFICATION** - Event notification
- **COMMAND** - Command to execute
- **QUERY** - Query for information
- **ACKNOWLEDGMENT** - Acknowledgment of receipt

### Send Message

```bash
curl -X POST http://localhost:8001/api/communication/send \
  -H "Content-Type: application/json" \
  -d '{
    "from_agent_id": 1,
    "to_agent_id": 2,
    "message_type": "request",
    "protocol": "direct",
    "content": "Please analyze task #101",
    "priority": "high",
    "requires_ack": true
  }'
```

Sends a message using specified protocol. Supports direct, broadcast, multicast, and pub/sub patterns.

### Get Messages

```bash
curl "http://localhost:8001/api/communication/1/messages?unread_only=true&limit=50"
```

Retrieves messages for an agent with filtering by type, status, sender, and read status.

### Send Request

```bash
curl -X POST http://localhost:8001/api/communication/request \
  -H "Content-Type: application/json" \
  -d '{
    "from_agent_id": 1,
    "to_agent_id": 2,
    "request_content": "What is the status of workflow #5?",
    "timeout_seconds": 300
  }'
```

Sends a request and tracks it for reply. Request expires after timeout if no reply received.

### Send Reply

```bash
curl -X POST http://localhost:8001/api/communication/reply \
  -H "Content-Type: application/json" \
  -d '{
    "request_message_id": 123,
    "from_agent_id": 2,
    "reply_content": "Workflow #5 is 75% complete"
  }'
```

Sends a reply to a request. Links reply to original request message.

### Subscribe to Topic

```bash
curl -X POST http://localhost:8001/api/communication/subscribe \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "topic": "task_updates"
  }'
```

Subscribes an agent to a topic. Agent will receive all messages published to this topic.

### Publish to Topic

```bash
curl -X POST http://localhost:8001/api/communication/send \
  -H "Content-Type: application/json" \
  -d '{
    "from_agent_id": 1,
    "protocol": "pubsub",
    "topic": "task_updates",
    "message_type": "notification",
    "content": "New task assigned: #102"
  }'
```

Publishes a message to a topic. All subscribers receive the message.

### Get Conversation

```bash
curl http://localhost:8001/api/communication/conversation/1/2?limit=50
```

Retrieves conversation history between two agents in chronological order.

### Communication Statistics

```bash
curl "http://localhost:8001/api/communication/stats?agent_id=1&hours=24"
```

Returns statistics on message volume, types, protocols, priorities, and statuses.

### Send Acknowledgment

```bash
curl -X POST http://localhost:8001/api/communication/acknowledge \
  -H "Content-Type: application/json" \
  -d '{
    "original_message_id": 123,
    "agent_id": 2,
    "ack_content": "Message received and processing"
  }'
```

Sends acknowledgment for a message back to original sender.

### Mark Message Read

```bash
curl -X POST http://localhost:8001/api/communication/mark-read \
  -H "Content-Type: application/json" \
  -d '{
    "message_id": 123,
    "agent_id": 2
  }'
```

Marks a message as read and records read timestamp.

## Task Decomposition System

The Task Decomposition System breaks down complex tasks into manageable subtasks with automatic dependency management and intelligent agent assignment.

### Decomposition Strategies

The system supports 5 decomposition strategies:

| Strategy | Description | Use Case |
|----------|-------------|----------|
| **sequential** | Subtasks execute one after another | Ordered workflows |
| **parallel** | Subtasks execute simultaneously | Independent operations |
| **hierarchical** | Root task followed by dependent subtasks | Complex dependencies |
| **pipeline** | Data flows through processing stages | ETL workflows |
| **map_reduce** | Parallel processing + aggregation | Data processing |

### Complexity Levels

Tasks are classified into 4 complexity levels:

| Level | Typical Subtasks | Duration | Description |
|-------|------------------|----------|-------------|
| **simple** | 1 | < 30 min | Straightforward task |
| **moderate** | 2-3 | 30 min - 2 hrs | Requires some planning |
| **complex** | 4-6 | 2-8 hrs | Requires decomposition |
| **very_complex** | 7+ | > 8 hrs | Careful planning needed |

### Key Features

**Auto-Generation**
- Automatically generates subtasks based on task type and description
- Pattern-based subtask creation for common workflows
- Intelligent dependency inference

**Agent Recommendation**
- Matches subtasks to agents based on capabilities
- Considers agent availability and expertise
- Ranked recommendations by match score

**Dependency Management**
- Automatic dependency generation based on strategy
- Cycle detection and validation
- Dependency graph visualization

**Result Merging**
- Aggregates results from completed subtasks
- Updates parent task status automatically
- Preserves subtask execution history

### Example Usage

**1. Decompose a task with auto-generation:**

```bash
curl -X POST http://localhost:8001/api/task-decomposition/decompose \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 123,
    "strategy": "sequential",
    "auto_generate": true
  }'
```

**2. Decompose with custom subtasks:**

```bash
curl -X POST http://localhost:8001/api/task-decomposition/decompose \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 123,
    "strategy": "parallel",
    "subtask_definitions": [
      {
        "title": "Data Collection",
        "description": "Collect data from APIs",
        "type": "data_processor",
        "complexity": "moderate",
        "estimated_duration_minutes": 45,
        "required_capabilities": ["api_integration", "data_validation"]
      },
      {
        "title": "Data Processing",
        "description": "Clean and transform data",
        "type": "data_processor",
        "complexity": "complex",
        "estimated_duration_minutes": 90,
        "required_capabilities": ["data_transformation"],
        "depends_on": [0]
      }
    ]
  }'
```

**3. Estimate task complexity:**

```bash
curl http://localhost:8001/api/task-decomposition/123/complexity
```

Response:
```json
{
  "success": true,
  "complexity": "complex",
  "recommended_subtask_count": 5,
  "recommended_strategy": "hierarchical",
  "estimated_duration_minutes": 240
}
```

**4. Get subtasks with progress:**

```bash
curl http://localhost:8001/api/task-decomposition/123/subtasks?include_status=true
```

Response includes execution status and progress statistics:
```json
{
  "success": true,
  "parent_task_id": 123,
  "strategy": "sequential",
  "total_subtasks": 5,
  "subtasks": [...],
  "progress": {
    "completed": 3,
    "in_progress": 1,
    "pending": 1,
    "completion_percentage": 60
  }
}
```

**5. Get agent recommendations for subtask:**

```bash
curl http://localhost:8001/api/task-decomposition/456/recommend-agents
```

Response ranks agents by capability match:
```json
{
  "success": true,
  "subtask_id": 456,
  "required_capabilities": ["api_integration", "data_validation"],
  "recommendations": [
    {
      "agent_id": 10,
      "agent_name": "DataProcessor-1",
      "match_score": 0.95,
      "matching_capabilities": ["api_integration", "data_validation"],
      "availability": "available"
    }
  ]
}
```

**6. Merge subtask results:**

```bash
curl -X POST http://localhost:8001/api/task-decomposition/123/merge
```

Aggregates results from all completed subtasks:
```json
{
  "success": true,
  "parent_task_id": 123,
  "all_subtasks_completed": true,
  "merged_results": {
    "data_collected": 1500,
    "records_processed": 1450,
    "errors": 2
  },
  "message": "Subtask results merged"
}
```

**7. List all strategies:**

```bash
curl http://localhost:8001/api/task-decomposition/strategies
```

**8. List complexity levels:**

```bash
curl http://localhost:8001/api/task-decomposition/complexity-levels
```

### Decomposition Workflow

1. **Estimate Complexity** - Analyze task to determine complexity level
2. **Choose Strategy** - Select appropriate decomposition strategy
3. **Decompose Task** - Break down into subtasks (auto or manual)
4. **Recommend Agents** - Match subtasks to capable agents
5. **Execute Subtasks** - Agents execute subtasks based on dependencies
6. **Merge Results** - Aggregate results when all subtasks complete

### Integration with Other Systems

**Works with:**
- **Agent Orchestration** - Assigns subtasks to agents automatically
- **Scheduler** - Schedules subtasks based on dependencies
- **Shared Memory** - Shares data between subtasks
- **Communication Protocol** - Coordinates agent collaboration
- **Analytics** - Tracks decomposition and execution metrics

## Agent Conflict Resolution System

The Conflict Resolution System detects and automatically resolves conflicts between agents in multi-agent environments, ensuring smooth coordination and preventing deadlocks.

### Conflict Types

The system handles 6 types of conflicts:

| Type | Description | Example |
|------|-------------|---------|
| **resource** | Multiple agents need same resource | Two agents requesting exclusive database access |
| **decision** | Agents disagree on a decision | Conflicting recommendations from analysis agents |
| **priority** | Task priority conflicts | Multiple high-priority tasks competing for resources |
| **assignment** | Multiple agents assigned same task | Task accidentally assigned to multiple agents |
| **state** | Inconsistent state between agents | Agents have different views of shared data |
| **timing** | Scheduling/timing conflicts | Agents scheduled for conflicting time slots |

### Severity Levels

Conflicts are classified into 4 severity levels:

| Level | Auto-Resolve | Description |
|-------|--------------|-------------|
| **low** | ✅ Yes | Minor conflict, low impact |
| **medium** | ✅ Yes | Moderate conflict, requires attention |
| **high** | ✅ Yes | Significant conflict, priority resolution |
| **critical** | ❌ Manual | Critical conflict, requires human judgment |

### Resolution Strategies

The system supports 7 resolution strategies:

| Strategy | Description | Best For |
|----------|-------------|----------|
| **priority_based** | Winner determined by agent/task priority | Resource conflicts |
| **voting** | Democratic vote among involved agents | Decision conflicts (small groups) |
| **arbitration** | Third-party agent arbitrates | Complex decisions, large groups |
| **fcfs** | First-come-first-served | Fair allocation, simple conflicts |
| **round_robin** | Fair distribution in rotation | Task assignment conflicts |
| **automatic** | System chooses best strategy | General use |
| **manual** | Human intervention required | Critical conflicts |

### Key Features

**Automatic Detection**
- Real-time conflict detection
- Severity assessment
- Involved agent tracking
- Resource and task correlation

**Smart Resolution**
- Strategy recommendation engine
- Multi-strategy support
- Batch conflict resolution
- Preview before applying

**Comprehensive Tracking**
- Conflict history
- Resolution statistics
- Strategy effectiveness metrics
- Agent conflict patterns

### Example Usage

**1. Detect a resource conflict:**

```bash
curl -X POST http://localhost:8001/api/conflict-resolution/detect \
  -H "Content-Type: application/json" \
  -d '{
    "conflict_type": "resource",
    "involved_agents": [10, 15, 22],
    "resource_id": "database-connection-pool",
    "description": "Three agents competing for database connections",
    "metadata": {
      "resource_limit": 2,
      "requests": 3
    }
  }'
```

Response:
```json
{
  "success": true,
  "conflict": {
    "conflict_id": 1,
    "conflict_type": "resource",
    "involved_agents": [10, 15, 22],
    "resource_id": "database-connection-pool",
    "severity": "high",
    "status": "detected",
    "detected_at": "2024-01-15T10:30:00Z"
  },
  "message": "Conflict detected with high severity"
}
```

**2. Get resolution strategy suggestion:**

```bash
curl http://localhost:8001/api/conflict-resolution/1/suggest-strategy
```

Response:
```json
{
  "success": true,
  "conflict_id": 1,
  "suggested_strategy": "priority_based",
  "reasoning": "Resource conflicts best resolved by priority",
  "alternative_strategies": ["priority_based", "voting", "fcfs"]
}
```

**3. Preview resolution outcome:**

```bash
curl -X POST http://localhost:8001/api/conflict-resolution/1/preview \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": "priority_based"
  }'
```

Response:
```json
{
  "success": true,
  "conflict_id": 1,
  "strategy": "priority_based",
  "preview_outcome": {
    "winner_agent_id": 15,
    "method": "priority_based",
    "priority_order": [
      {"agent_id": 15, "priority": 8},
      {"agent_id": 10, "priority": 5},
      {"agent_id": 22, "priority": 3}
    ]
  },
  "note": "This is a preview. Use resolve_conflict to apply."
}
```

**4. Resolve the conflict:**

```bash
curl -X POST http://localhost:8001/api/conflict-resolution/1/resolve \
  -H "Content-Type: application/json" \
  -d '{
    "strategy": "priority_based"
  }'
```

Response:
```json
{
  "success": true,
  "resolution": {
    "conflict_id": 1,
    "status": "resolved",
    "strategy": "priority_based",
    "outcome": {
      "winner_agent_id": 15,
      "method": "priority_based"
    },
    "attempts": 1
  },
  "message": "Conflict resolved using priority_based strategy"
}
```

**5. List all conflicts for an agent:**

```bash
curl http://localhost:8001/api/conflict-resolution/agents/10?status=resolved
```

**6. Get conflict statistics:**

```bash
curl http://localhost:8001/api/conflict-resolution/statistics
```

Response:
```json
{
  "success": true,
  "statistics": {
    "total_conflicts": 45,
    "by_status": {
      "resolved": 40,
      "detected": 3,
      "escalated": 2
    },
    "by_type": {
      "resource": 20,
      "assignment": 15,
      "priority": 10
    },
    "by_severity": {
      "low": 10,
      "medium": 25,
      "high": 8,
      "critical": 2
    },
    "resolution_rate_percent": 88.9,
    "avg_resolution_time_seconds": 2.4,
    "strategy_effectiveness": {
      "priority_based": {
        "count": 20,
        "avg_duration": 1.8
      },
      "round_robin": {
        "count": 15,
        "avg_duration": 1.2
      }
    }
  }
}
```

**7. Batch resolve multiple conflicts:**

```bash
curl -X POST http://localhost:8001/api/conflict-resolution/batch-resolve \
  -H "Content-Type: application/json" \
  -d '{
    "conflict_ids": [1, 2, 3, 4, 5],
    "strategy": "automatic"
  }'
```

**8. Escalate a conflict for manual intervention:**

```bash
curl -X POST http://localhost:8001/api/conflict-resolution/5/escalate \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Involves critical production database, requires DBA approval"
  }'
```

**9. List all conflict types:**

```bash
curl http://localhost:8001/api/conflict-resolution/types
```

**10. List all resolution strategies:**

```bash
curl http://localhost:8001/api/conflict-resolution/strategies
```

### Resolution Workflow

1. **Detect Conflict** - System or agents detect conflicting situations
2. **Assess Severity** - Automatic severity calculation based on type and impact
3. **Suggest Strategy** - AI recommends best resolution approach
4. **Preview Outcome** - Optional preview of resolution result
5. **Resolve Conflict** - Apply chosen strategy
6. **Track Resolution** - Record outcome and metrics

### Strategy Selection Guide

**Use priority_based when:**
- Clear priority hierarchy exists
- Resource allocation needed
- Quick decisions required

**Use voting when:**
- Democratic decision needed
- Small group (2-5 agents)
- Equal stakeholders

**Use arbitration when:**
- Complex conflicts
- Large groups (>5 agents)
- Neutral judgment needed

**Use round_robin when:**
- Fair distribution important
- Repeated conflicts expected
- No clear priority

**Use automatic when:**
- Unsure which strategy to use
- General conflict handling
- System should decide

### Integration with Other Systems

**Works with:**
- **Agent Orchestration** - Prevents assignment conflicts
- **Resource Management** - Resolves resource contention
- **Scheduler** - Handles timing conflicts
- **Shared Memory** - Resolves state inconsistencies
- **Analytics** - Tracks conflict patterns

## Agent Consensus System

The Agent Consensus System enables multiple agents to reach agreement on decisions through democratic voting, weighted voting, quorum-based decisions, and various consensus mechanisms.

### Consensus Mechanisms

The system supports 7 consensus types:

| Type | Threshold | Description | Best For |
|------|-----------|-------------|----------|
| **simple_majority** | >50% | More than half must agree | General decisions |
| **supermajority** | >66% | Two-thirds must agree | Important decisions |
| **unanimous** | 100% | All agents must agree | Critical decisions |
| **weighted_voting** | Varies | Votes weighted by agent priority | Hierarchical teams |
| **quorum_based** | Configurable | Minimum participation required | Large groups |
| **ranked_choice** | Majority | Agents rank options, instant runoff | Multiple options |
| **veto_based** | No vetoes | Any agent can veto | High-stakes decisions |

### Proposal Lifecycle

Proposals progress through these statuses:

| Status | Description |
|--------|-------------|
| **voting** | Active voting period |
| **passed** | Consensus reached, proposal approved |
| **rejected** | Consensus failed or quorum not met |
| **vetoed** | Agent exercised veto power |
| **expired** | Voting deadline passed |

### Key Features

**Democratic Voting**
- Multi-option proposals
- Ranked choice voting
- Abstention support
- Vote reasoning and transparency

**Flexible Mechanisms**
- 7 consensus types
- Configurable quorum thresholds
- Vote weighting by agent priority
- Veto power for critical decisions

**Deadline Management**
- Configurable voting deadlines
- Deadline extension capability
- Automatic expiration handling

**Comprehensive Tracking**
- Vote history per agent
- Participation rate tracking
- Pass rate statistics
- Consensus type effectiveness

### Example Usage

**1. Create a simple majority proposal:**

```bash
curl -X POST http://localhost:8001/api/consensus/proposals \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Select Database Technology",
    "description": "Choose database for new microservice",
    "options": ["PostgreSQL", "MongoDB", "MySQL"],
    "consensus_type": "simple_majority",
    "eligible_agents": [10, 15, 22, 28, 31],
    "proposer_agent_id": 10,
    "voting_deadline_minutes": 120
  }'
```

Response:
```json
{
  "success": true,
  "proposal": {
    "proposal_id": 1,
    "title": "Select Database Technology",
    "options": ["PostgreSQL", "MongoDB", "MySQL"],
    "consensus_type": "simple_majority",
    "eligible_agents": [10, 15, 22, 28, 31],
    "status": "voting",
    "voting_deadline": "2024-01-15T12:30:00Z",
    "vote_counts": {
      "PostgreSQL": 0,
      "MongoDB": 0,
      "MySQL": 0
    }
  },
  "message": "Proposal created with 5 eligible voters"
}
```

**2. Cast a vote:**

```bash
curl -X POST http://localhost:8001/api/consensus/proposals/1/vote \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 15,
    "vote": "yes",
    "option": "PostgreSQL",
    "reasoning": "Best ACID compliance and JSON support"
  }'
```

**3. Create weighted voting proposal:**

```bash
curl -X POST http://localhost:8001/api/consensus/proposals \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Approve Architecture Change",
    "description": "Move to microservices architecture",
    "options": ["Approve", "Reject", "Needs More Study"],
    "consensus_type": "weighted_voting",
    "eligible_agents": [10, 15, 22],
    "voting_deadline_minutes": 60
  }'
```

**4. Cast weighted vote:**

```bash
curl -X POST http://localhost:8001/api/consensus/proposals/2/vote \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 10,
    "vote": "yes",
    "option": "Approve",
    "weight": 2.5,
    "reasoning": "Senior architect approval"
  }'
```

**5. Create ranked choice proposal:**

```bash
curl -X POST http://localhost:8001/api/consensus/proposals \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Select Deployment Strategy",
    "description": "Choose deployment approach",
    "options": ["Blue-Green", "Canary", "Rolling Update", "Recreate"],
    "consensus_type": "ranked_choice",
    "eligible_agents": [10, 15, 22, 28],
    "voting_deadline_minutes": 90
  }'
```

**6. Cast ranked choice vote:**

```bash
curl -X POST http://localhost:8001/api/consensus/proposals/3/vote \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 15,
    "vote": "yes",
    "ranked_options": ["Canary", "Blue-Green", "Rolling Update", "Recreate"],
    "reasoning": "Canary provides best risk mitigation"
  }'
```

**7. Finalize proposal:**

```bash
curl -X POST http://localhost:8001/api/consensus/proposals/1/finalize \
  -H "Content-Type: application/json" \
  -d '{
    "quorum_threshold": 0.6
  }'
```

Response:
```json
{
  "success": true,
  "proposal": {
    "proposal_id": 1,
    "status": "passed",
    "winning_option": "PostgreSQL",
    "participation_count": 4,
    "vote_breakdown": {
      "PostgreSQL": 3,
      "MongoDB": 1,
      "MySQL": 0
    },
    "finalized_at": "2024-01-15T11:45:00Z"
  },
  "message": "Proposal passed: PostgreSQL"
}
```

**8. Get proposal details:**

```bash
curl http://localhost:8001/api/consensus/proposals/1
```

Response includes all votes:
```json
{
  "success": true,
  "proposal": {
    "proposal_id": 1,
    "title": "Select Database Technology",
    "status": "passed",
    "total_votes": 4,
    "votes": [
      {
        "agent_id": 15,
        "agent_name": "DatabaseExpert-1",
        "vote": "yes",
        "option": "PostgreSQL",
        "reasoning": "Best ACID compliance and JSON support",
        "voted_at": "2024-01-15T10:35:00Z"
      }
    ]
  }
}
```

**9. Get agent voting history:**

```bash
curl http://localhost:8001/api/consensus/agents/15/votes
```

**10. Get consensus statistics:**

```bash
curl http://localhost:8001/api/consensus/statistics
```

Response:
```json
{
  "success": true,
  "statistics": {
    "total_proposals": 25,
    "by_status": {
      "passed": 18,
      "rejected": 5,
      "voting": 2
    },
    "by_consensus_type": {
      "simple_majority": 15,
      "supermajority": 6,
      "weighted_voting": 4
    },
    "pass_rate_percent": 72.0,
    "avg_participation_rate": 0.85,
    "total_votes_cast": 142,
    "active_proposals": 2
  }
}
```

**11. Extend voting deadline:**

```bash
curl -X POST http://localhost:8001/api/consensus/proposals/2/extend \
  -H "Content-Type: application/json" \
  -d '{
    "additional_minutes": 30
  }'
```

**12. Cancel a proposal:**

```bash
curl -X POST http://localhost:8001/api/consensus/proposals/3/cancel \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Requirements changed, new proposal needed"
  }'
```

**13. List all consensus types:**

```bash
curl http://localhost:8001/api/consensus/consensus-types
```

**14. List all vote types:**

```bash
curl http://localhost:8001/api/consensus/vote-types
```

### Consensus Workflow

1. **Create Proposal** - Define options, consensus type, eligible voters
2. **Cast Votes** - Eligible agents vote with optional reasoning
3. **Monitor Progress** - Track participation and vote counts
4. **Finalize** - Apply consensus mechanism and determine outcome
5. **Act on Result** - Implement winning option or handle rejection

### Choosing the Right Consensus Type

**Simple Majority** - Best for:
- Routine decisions
- Quick consensus needed
- Clear binary choices
- 3-10 agents

**Supermajority** - Best for:
- Important but not critical decisions
- Policy changes
- Medium-risk decisions
- Need strong support

**Unanimous** - Best for:
- Critical decisions
- Small groups (2-5 agents)
- High-risk changes
- Team commitment essential

**Weighted Voting** - Best for:
- Hierarchical teams
- Expert opinions matter more
- Varying stake in outcome
- Experience-based decisions

**Ranked Choice** - Best for:
- Multiple good options
- Avoid vote splitting
- Fair representation
- 3+ options

**Veto-Based** - Best for:
- Safety-critical decisions
- Compliance requirements
- Any agent can block
- Risk mitigation paramount

### Integration with Other Systems

**Works with:**
- **Conflict Resolution** - Escalate conflicts to voting
- **Agent Collaboration** - Team decision making
- **Task Decomposition** - Decide decomposition strategy
- **Workflow Engine** - Approve workflow changes
- **Analytics** - Track decision patterns

## Agent Coalition Formation System

The Coalition Formation System enables agents to form temporary teams (coalitions) to collaborate on complex tasks, pool resources, and achieve shared goals.

### Coalition Lifecycle

Coalitions progress through these statuses:

| Status | Description |
|--------|-------------|
| **forming** | Coalition being assembled, recruiting members |
| **active** | Coalition actively working on tasks |
| **completed** | Coalition successfully achieved goal |
| **dissolved** | Coalition disbanded before completion |

### Member Roles

Coalition members can have different roles:

| Role | Responsibilities |
|------|------------------|
| **leader** | Makes final decisions, coordinates team |
| **coordinator** | Manages communication and activities |
| **specialist** | Domain expert with specific skills |
| **contributor** | General contributor to coalition work |
| **advisor** | Provides guidance without direct work |

### Formation Strategies

The system supports 5 coalition formation strategies:

| Strategy | Description | Best For |
|----------|-------------|----------|
| **capability_based** | Match agents by required capabilities | Skill-specific tasks |
| **reputation_based** | Select based on agent performance history | Quality-critical work |
| **workload_based** | Choose agents with available capacity | Load balancing |
| **proximity_based** | Group similar/compatible agents | Team cohesion |
| **hybrid** | Combination of multiple factors (70% capability, 30% workload) | Balanced teams |

### Key Features

**Dynamic Team Formation**
- Auto-suggest optimal coalitions for tasks
- Flexible member addition/removal
- Leader succession on departure
- Maximum size enforcement

**Resource Pooling**
- Shared resource contributions
- Individual contribution tracking
- Resource type flexibility
- Transparency and accountability

**Contribution Tracking**
- Individual contribution scores
- Achievement recording
- Performance metrics
- Fair credit attribution

**Goal Alignment**
- Clear coalition objectives
- Required capability definition
- Task assignment
- Outcome tracking

### Example Usage

**1. Create a coalition:**

```bash
curl -X POST http://localhost:8001/api/coalitions/coalitions \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Backend Migration Team",
    "goal": "Migrate legacy backend to microservices",
    "required_capabilities": ["system_architecture", "database_migration", "api_design"],
    "leader_agent_id": 10,
    "initial_members": [10, 15, 22],
    "max_members": 8,
    "duration_hours": 168
  }'
```

Response:
```json
{
  "success": true,
  "coalition": {
    "coalition_id": 1,
    "name": "Backend Migration Team",
    "goal": "Migrate legacy backend to microservices",
    "status": "active",
    "members": [
      {
        "agent_id": 10,
        "agent_name": "ArchitectAgent-1",
        "role": "leader",
        "contribution_score": 0.0,
        "active": true
      }
    ],
    "max_members": 8,
    "expires_at": "2024-01-22T10:30:00Z"
  },
  "message": "Coalition created with 3 members"
}
```

**2. Get AI-suggested coalition for a task:**

```bash
curl -X POST http://localhost:8001/api/coalitions/suggest \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 456,
    "strategy": "hybrid",
    "max_members": 5
  }'
```

Response:
```json
{
  "success": true,
  "task_id": 456,
  "task_title": "Implement OAuth2 Authentication",
  "strategy": "hybrid",
  "suggested_members": [
    {
      "agent_id": 12,
      "agent_name": "SecurityExpert-1",
      "match_score": 0.92,
      "capability_score": 0.95,
      "availability_score": 0.85
    },
    {
      "agent_id": 28,
      "agent_name": "BackendDev-3",
      "match_score": 0.78,
      "capability_score": 0.70,
      "availability_score": 0.95
    }
  ],
  "coalition_size": 2
}
```

**3. Add member to coalition:**

```bash
curl -X POST http://localhost:8001/api/coalitions/coalitions/1/members \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 28,
    "role": "specialist"
  }'
```

**4. Assign task to coalition:**

```bash
curl -X POST http://localhost:8001/api/coalitions/coalitions/1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 789
  }'
```

**5. Pool resources to coalition:**

```bash
curl -X POST http://localhost:8001/api/coalitions/coalitions/1/resources \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 10,
    "resource_type": "compute_credits",
    "amount": 1000.0
  }'
```

**6. Update contribution score:**

```bash
curl -X POST http://localhost:8001/api/coalitions/coalitions/1/contributions \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 15,
    "score_delta": 5.0
  }'
```

**7. Record achievement:**

```bash
curl -X POST http://localhost:8001/api/coalitions/coalitions/1/achievements \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Database Migration Complete",
    "description": "Successfully migrated 50 database tables to PostgreSQL",
    "value": 10.0
  }'
```

**8. Get coalition details:**

```bash
curl http://localhost:8001/api/coalitions/coalitions/1
```

Response:
```json
{
  "success": true,
  "coalition": {
    "coalition_id": 1,
    "name": "Backend Migration Team",
    "status": "active",
    "members": [
      {
        "agent_id": 10,
        "role": "leader",
        "contribution_score": 12.5
      }
    ],
    "tasks": [789, 790],
    "pooled_resources": {
      "compute_credits": {
        "total": 2500.0,
        "contributions": [...]
      }
    },
    "achievements": [
      {
        "title": "Database Migration Complete",
        "value": 10.0,
        "achieved_at": "2024-01-16T14:20:00Z"
      }
    ]
  }
}
```

**9. Remove member from coalition:**

```bash
curl -X DELETE http://localhost:8001/api/coalitions/coalitions/1/members \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 22,
    "reason": "Reassigned to higher priority project"
  }'
```

**10. Complete coalition:**

```bash
curl -X POST http://localhost:8001/api/coalitions/coalitions/1/complete \
  -H "Content-Type: application/json" \
  -d '{
    "outcome": "Successfully migrated all backend services to microservices architecture"
  }'
```

**11. Get coalition statistics:**

```bash
curl http://localhost:8001/api/coalitions/statistics
```

Response:
```json
{
  "success": true,
  "statistics": {
    "total_coalitions": 15,
    "by_status": {
      "active": 4,
      "completed": 9,
      "dissolved": 2
    },
    "avg_coalition_size": 4.2,
    "total_unique_members": 63,
    "total_tasks_assigned": 42,
    "total_achievements": 28,
    "active_coalitions": 4
  }
}
```

**12. List all coalitions:**

```bash
curl http://localhost:8001/api/coalitions/coalitions?status=active
```

**13. List all member roles:**

```bash
curl http://localhost:8001/api/coalitions/roles
```

**14. List formation strategies:**

```bash
curl http://localhost:8001/api/coalitions/strategies
```

### Coalition Workflow

1. **Identify Need** - Task requires multiple agents
2. **Suggest Coalition** - AI suggests optimal team composition
3. **Create Coalition** - Form team with initial members
4. **Recruit Members** - Add specialists as needed
5. **Assign Tasks** - Distribute work among members
6. **Pool Resources** - Share computational/financial resources
7. **Track Progress** - Monitor contributions and achievements
8. **Complete Goal** - Mark coalition as successful
9. **Dissolve** - End coalition after goal achievement

### When to Use Coalitions

**Use coalitions for:**
- Large complex tasks requiring diverse skills
- Projects needing resource pooling
- Long-running multi-phase work
- Cross-functional team collaboration
- Tasks with shared accountability

**Don't use coalitions for:**
- Simple single-agent tasks
- Short-duration operations
- Tasks with single capability requirement
- Individual agent responsibilities

### Integration with Other Systems

**Works with:**
- **Task Decomposition** - Assign subtasks to coalition
- **Consensus** - Make coalition decisions democratically
- **Conflict Resolution** - Resolve member disagreements
- **Shared Memory** - Share data among members
- **Analytics** - Track coalition performance

### API Documentation

Interactive API documentation is available at:
- **Swagger UI**: http://localhost:8001/docs
- **ReDoc**: http://localhost:8001/redoc

## Agent Negotiation System

The Agent Negotiation System enables agents to negotiate agreements through structured offer-counteroffer exchanges using various negotiation strategies and protocols.

### Features

- **6 Negotiation Types**: Resource allocation, task assignment, collaboration terms, priority adjustment, deadline extension, cost sharing
- **5 Negotiation Strategies**: Competitive, cooperative, compromise, accommodating, avoiding
- **Multi-Round Protocol**: Structured offer-counteroffer mechanism with round tracking
- **Compromise Suggestions**: AI-powered middle-ground proposals
- **Deadline Management**: Configurable deadlines with extension capability
- **Withdrawal Mechanism**: Either party can withdraw with reason tracking

### API Endpoints

#### Initiate Negotiation

```bash
curl -X POST http://localhost:8001/api/negotiations \
  -H "Content-Type: application/json" \
  -d '{
    "initiator_agent_id": 1,
    "respondent_agent_id": 2,
    "negotiation_type": "resource_allocation",
    "subject": "GPU allocation for training",
    "initial_proposal": {
      "gpu_count": 4,
      "duration_hours": 8,
      "priority": "high"
    },
    "strategy": "cooperative",
    "deadline_hours": 24
  }'
```

#### Respond to Offer (Accept)

```bash
curl -X POST http://localhost:8001/api/negotiations/1/offers/1/respond \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 2,
    "response": "accept",
    "reasoning": "Resource requirements align with our availability"
  }'
```

#### Respond to Offer (Counter-Offer)

```bash
curl -X POST http://localhost:8001/api/negotiations/1/offers/1/respond \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 2,
    "response": "counter",
    "counter_proposal": {
      "gpu_count": 3,
      "duration_hours": 8,
      "priority": "medium"
    },
    "reasoning": "Can provide 3 GPUs for the same duration"
  }'
```

#### Respond to Offer (Reject)

```bash
curl -X POST http://localhost:8001/api/negotiations/1/offers/1/respond \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 2,
    "response": "reject",
    "reasoning": "Insufficient resources available"
  }'
```

#### Suggest Compromise

```bash
curl -X GET http://localhost:8001/api/negotiations/1/compromise
```

Response:
```json
{
  "success": true,
  "negotiation_id": 1,
  "compromise_proposal": {
    "gpu_count": 3.5,
    "duration_hours": 8,
    "priority": "medium"
  },
  "based_on": {
    "initiator_latest": {"gpu_count": 4, "duration_hours": 8, "priority": "high"},
    "respondent_latest": {"gpu_count": 3, "duration_hours": 8, "priority": "medium"}
  }
}
```

#### Withdraw from Negotiation

```bash
curl -X POST http://localhost:8001/api/negotiations/1/withdraw \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "reason": "Requirements changed, no longer need this resource"
  }'
```

#### Extend Deadline

```bash
curl -X POST http://localhost:8001/api/negotiations/1/extend \
  -H "Content-Type: application/json" \
  -d '{
    "additional_hours": 12
  }'
```

#### Get Negotiation Details

```bash
curl -X GET http://localhost:8001/api/negotiations/1
```

Response:
```json
{
  "success": true,
  "negotiation": {
    "negotiation_id": 1,
    "initiator_agent_id": 1,
    "initiator_name": "Agent-1",
    "respondent_agent_id": 2,
    "respondent_name": "Agent-2",
    "negotiation_type": "resource_allocation",
    "subject": "GPU allocation for training",
    "strategy": "cooperative",
    "status": "agreement_reached",
    "round_count": 3,
    "final_agreement": {"gpu_count": 3, "duration_hours": 8, "priority": "medium"},
    "offers": [...],
    "total_offers": 3
  }
}
```

#### List Negotiations

```bash
# All negotiations
curl -X GET http://localhost:8001/api/negotiations

# Filter by status
curl -X GET "http://localhost:8001/api/negotiations?status=in_progress"

# Filter by agent
curl -X GET "http://localhost:8001/api/negotiations?agent_id=1"

# Filter by type
curl -X GET "http://localhost:8001/api/negotiations?negotiation_type=resource_allocation"
```

#### Get Agent's Negotiations

```bash
curl -X GET http://localhost:8001/api/agents/1/negotiations
```

#### Get Negotiation Statistics

```bash
curl -X GET http://localhost:8001/api/negotiations/statistics
```

Response:
```json
{
  "success": true,
  "statistics": {
    "total_negotiations": 25,
    "by_status": {
      "agreement_reached": 15,
      "in_progress": 5,
      "rejected": 3,
      "withdrawn": 2
    },
    "by_type": {
      "resource_allocation": 10,
      "task_assignment": 8,
      "collaboration_terms": 4,
      "priority_adjustment": 3
    },
    "success_rate_percent": 60.0,
    "avg_rounds_to_agreement": 2.5,
    "total_offers": 75,
    "active_negotiations": 5
  }
}
```

#### Get Specific Offer Details

```bash
curl -X GET http://localhost:8001/api/negotiations/1/offers/2
```

#### List Negotiation Types

```bash
curl -X GET http://localhost:8001/api/negotiations/types
```

#### List Negotiation Strategies

```bash
curl -X GET http://localhost:8001/api/negotiations/strategies
```

#### List Negotiation Statuses

```bash
curl -X GET http://localhost:8001/api/negotiations/statuses
```

### Negotiation Types

- **resource_allocation**: Negotiate distribution of resources (GPUs, memory, compute)
- **task_assignment**: Negotiate task responsibility and ownership
- **collaboration_terms**: Negotiate collaboration conditions and agreements
- **priority_adjustment**: Negotiate changes to task or agent priorities
- **deadline_extension**: Negotiate extensions to task deadlines
- **cost_sharing**: Negotiate distribution of costs and expenses

### Negotiation Strategies

- **competitive**: Win-lose approach, maximize own benefit
- **cooperative**: Win-win approach, maximize joint benefit
- **compromise**: Meet in the middle, balanced approach
- **accommodating**: Yield to other party's interests
- **avoiding**: Withdraw from negotiation

### Negotiation Statuses

- **open**: Negotiation initiated, awaiting first response
- **in_progress**: Active negotiation with ongoing offers
- **agreement_reached**: Successful agreement reached
- **rejected**: Negotiation rejected by respondent
- **expired**: Negotiation deadline passed without agreement
- **withdrawn**: One party withdrew from negotiation

### Use Cases

1. **Resource Contention**: Agents negotiate GPU allocation when multiple need compute
2. **Task Distribution**: Agents negotiate task assignments based on expertise
3. **Priority Conflicts**: Agents negotiate priority changes when schedules conflict
4. **Collaboration Terms**: Agents negotiate partnership conditions for complex tasks
5. **Deadline Adjustments**: Agents negotiate deadline extensions when needed
6. **Cost Optimization**: Agents negotiate cost sharing for shared infrastructure

### Integration

```python
from src.services.agent_negotiation import AgentNegotiation, NegotiationType, NegotiationStrategy

# Initiate negotiation
negotiation = AgentNegotiation.initiate_negotiation(
    session=session,
    initiator_agent_id=1,
    respondent_agent_id=2,
    negotiation_type=NegotiationType.RESOURCE_ALLOCATION,
    subject="GPU allocation",
    initial_proposal={"gpu_count": 4},
    strategy=NegotiationStrategy.COOPERATIVE
)

# Respond with counter-offer
negotiation = AgentNegotiation.respond_to_offer(
    session=session,
    negotiation_id=negotiation["negotiation_id"],
    offer_id=1,
    agent_id=2,
    response="counter",
    counter_proposal={"gpu_count": 3}
)

# Get compromise suggestion
suggestion = AgentNegotiation.suggest_compromise(
    session=session,
    negotiation_id=negotiation["negotiation_id"]
)
```

## Agent Reputation System

The Agent Reputation System tracks agent reliability, performance, and trustworthiness through reputation scores, endorsements, feedback, and trust relationships to inform collaboration decisions.

### Features

- **6 Reputation Categories**: Task completion, collaboration, communication, reliability, expertise, responsiveness
- **5 Trust Levels**: Untrusted (0-25), Low (26-50), Medium (51-75), High (76-90), Verified (91-100)
- **Endorsement System**: Agents endorse peers in specific categories
- **Feedback Mechanism**: Positive, neutral, and negative feedback
- **Trust Relationships**: Directional trust scores between agents
- **Reputation Decay**: Time-based decay toward neutral to prevent stale data

### API Endpoints

#### Initialize Reputation

```bash
curl -X POST http://localhost:8001/api/reputation/reputations \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "initial_score": 50.0
  }'
```

Response:
```json
{
  "success": true,
  "reputation": {
    "agent_id": 1,
    "agent_name": "Agent-1",
    "overall_score": 50.0,
    "category_scores": {
      "task_completion": 50.0,
      "collaboration": 50.0,
      "communication": 50.0,
      "reliability": 50.0,
      "expertise": 50.0,
      "responsiveness": 50.0
    },
    "trust_level": "medium",
    "total_endorsements": 0,
    "total_feedback": 0
  }
}
```

#### Update Reputation Score

```bash
curl -X POST http://localhost:8001/api/reputation/reputations/1/update \
  -H "Content-Type: application/json" \
  -d '{
    "category": "task_completion",
    "score_delta": 5.0,
    "reason": "Completed complex task ahead of schedule"
  }'
```

#### Record Task Completion

```bash
# Successful task
curl -X POST http://localhost:8001/api/reputation/reputations/1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "success": true,
    "rating": 4.5
  }'

# Failed task
curl -X POST http://localhost:8001/api/reputation/reputations/1/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "success": false
  }'
```

#### Add Endorsement

```bash
curl -X POST http://localhost:8001/api/reputation/reputations/1/endorsements \
  -H "Content-Type: application/json" \
  -d '{
    "endorser_agent_id": 2,
    "category": "expertise",
    "comment": "Excellent knowledge in machine learning"
  }'
```

#### Add Feedback

```bash
# Positive feedback
curl -X POST http://localhost:8001/api/reputation/reputations/1/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "from_agent_id": 2,
    "feedback_type": "positive",
    "category": "collaboration",
    "comment": "Great team player, very helpful"
  }'
```

#### Establish Trust Relationship

```bash
curl -X POST http://localhost:8001/api/reputation/reputations/1/trust \
  -H "Content-Type: application/json" \
  -d '{
    "trusted_agent_id": 2,
    "trust_score": 85.0,
    "reason": "Successful collaboration on 5+ projects"
  }'
```

#### Get Reputation

```bash
curl -X GET http://localhost:8001/api/reputation/reputations/1
```

#### Get Trust Relationships

```bash
curl -X GET http://localhost:8001/api/reputation/reputations/1/trust-relationships
```

#### Get Top Agents

```bash
# Overall top agents
curl -X GET "http://localhost:8001/api/reputation/reputations/top?limit=10"

# Top agents in specific category
curl -X GET "http://localhost:8001/api/reputation/reputations/top?limit=5&category=expertise"
```

#### Get Reputation Statistics

```bash
curl -X GET http://localhost:8001/api/reputation/reputations/statistics
```

### Reputation Categories

- **task_completion**: Ability to complete assigned tasks successfully
- **collaboration**: Quality of collaboration with other agents
- **communication**: Effectiveness of communication
- **reliability**: Consistency and dependability
- **expertise**: Domain knowledge and skill level
- **responsiveness**: Speed and timeliness of responses

### Trust Levels

- **untrusted** (0-25): Untrusted agent, avoid collaboration
- **low** (26-50): Low trust, caution required
- **medium** (51-75): Medium trust, normal collaboration
- **high** (76-90): High trust, preferred collaborator
- **verified** (91-100): Verified trusted agent, ideal partner

### Use Cases

1. **Coalition Formation**: Select high-reputation agents for critical coalitions
2. **Conflict Resolution**: Use reputation to weight agent priorities in conflicts
3. **Task Assignment**: Assign tasks to agents with proven expertise
4. **Negotiation**: Trust scores influence negotiation strategies
5. **Performance Monitoring**: Track agent performance over time
6. **Quality Assurance**: Identify and address underperforming agents

### Integration

```python
from src.services.agent_reputation import AgentReputation, ReputationCategory

# Initialize reputation
reputation = AgentReputation.initialize_reputation(
    session=session,
    agent_id=1,
    initial_score=50.0
)

# Record task completion
reputation = AgentReputation.record_task_completion(
    session=session,
    agent_id=1,
    success=True,
    rating=4.5
)

# Get top agents for task
top_agents = AgentReputation.get_top_agents(
    session=session,
    category=ReputationCategory.TASK_COMPLETION,
    limit=5
)
```

## Agent Incentive System

The Agent Incentive System manages rewards, contributions, and economic incentives to encourage high-quality performance, collaboration, and system participation.

### Features

- **Reward Calculation**: Automatic calculation of task rewards with quality and speed bonuses
- **Contribution Tracking**: Records all agent contributions for transparency
- **Balance Management**: Agent balances with transfer capabilities
- **Reward Pools**: Bulk distribution of rewards based on criteria
- **Leaderboards**: Rankings by balance, contributions, or rewards
- **Transaction History**: Complete audit trail of all economic activity

### API Endpoints

#### Initialize Agent

```bash
curl -X POST http://localhost:8001/api/incentives/agents/initialize \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "initial_balance": 100.0
  }'
```

#### Record Contribution

```bash
curl -X POST http://localhost:8001/api/incentives/agents/1/contributions \
  -H "Content-Type: application/json" \
  -d '{
    "contribution_type": "task_completion",
    "value": 10.0,
    "description": "Completed data processing task",
    "metadata": {"task_id": 123}
  }'
```

#### Calculate Task Reward

```bash
curl -X POST http://localhost:8001/api/incentives/agents/1/calculate-task-reward \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 123,
    "completion_time_hours": 6.0,
    "quality_score": 0.95,
    "difficulty_multiplier": 1.5
  }'
```

Response:
```json
{
  "success": true,
  "calculation": {
    "agent_id": 1,
    "task_id": 123,
    "base_reward": 15.0,
    "quality_bonus": 3.375,
    "speed_bonus": 1.875,
    "total_reward": 20.25,
    "breakdown": {
      "difficulty_multiplier": 1.5,
      "quality_score": 0.95,
      "completion_time_hours": 6.0,
      "expected_time_hours": 12.0
    }
  }
}
```

#### Award Reward

```bash
curl -X POST http://localhost:8001/api/incentives/agents/1/rewards \
  -H "Content-Type: application/json" \
  -d '{
    "reward_type": "performance_bonus",
    "amount": 20.25,
    "reason": "Excellent task performance",
    "auto_approve": true
  }'
```

#### Transfer Balance

```bash
curl -X POST http://localhost:8001/api/incentives/agents/1/transfer \
  -H "Content-Type: application/json" \
  -d '{
    "to_agent_id": 2,
    "amount": 10.0,
    "reason": "Payment for assistance"
  }'
```

#### Create Reward Pool

```bash
curl -X POST http://localhost:8001/api/incentives/pools \
  -H "Content-Type: application/json" \
  -d '{
    "pool_name": "Q1 Performance Pool",
    "total_amount": 1000.0,
    "distribution_criteria": {
      "metric": "task_completion",
      "period": "Q1_2024"
    },
    "deadline_hours": 168
  }'
```

#### Distribute from Pool

```bash
curl -X POST http://localhost:8001/api/incentives/pools/pool_1/distribute \
  -H "Content-Type: application/json" \
  -d '{
    "agent_rewards": {
      "1": 250.0,
      "2": 200.0,
      "3": 150.0,
      "4": 100.0
    }
  }'
```

#### Get Agent Balance

```bash
curl -X GET http://localhost:8001/api/incentives/agents/1/balance
```

Response:
```json
{
  "success": true,
  "agent_id": 1,
  "current_balance": 320.25,
  "total_rewards_received": 350.0,
  "pending_rewards": 50.0,
  "total_contributions": 15,
  "total_contribution_value": 180.0
}
```

#### Get Agent History

```bash
curl -X GET "http://localhost:8001/api/incentives/agents/1/history?limit=20"
```

#### Get Leaderboard

```bash
# By balance
curl -X GET "http://localhost:8001/api/incentives/leaderboard?metric=balance&limit=10"

# By contributions
curl -X GET "http://localhost:8001/api/incentives/leaderboard?metric=contributions&limit=10"

# By rewards
curl -X GET "http://localhost:8001/api/incentives/leaderboard?metric=rewards&limit=10"
```

Response:
```json
{
  "success": true,
  "metric": "balance",
  "total_agents": 20,
  "leaderboard": [
    {
      "agent_id": 5,
      "agent_name": "Agent-5",
      "balance": 850.0,
      "total_contributions": 45,
      "total_rewards": 920.0
    },
    {
      "agent_id": 2,
      "agent_name": "Agent-2",
      "balance": 720.0,
      "total_contributions": 38,
      "total_rewards": 780.0
    }
  ]
}
```

#### Get System Statistics

```bash
curl -X GET http://localhost:8001/api/incentives/statistics
```

Response:
```json
{
  "success": true,
  "statistics": {
    "total_agents": 20,
    "total_system_balance": 8500.0,
    "total_contributions": 450,
    "total_rewards_distributed": 9200.0,
    "total_rewards_pending": 300.0,
    "total_transactions": 185,
    "rewards_by_type": {
      "base_reward": 4500.0,
      "performance_bonus": 2800.0,
      "quality_bonus": 1200.0,
      "collaboration_bonus": 700.0
    },
    "active_reward_pools": 2,
    "total_pool_value": 1500.0
  }
}
```

### Reward Calculation

**Base Reward**: `10.0 × difficulty_multiplier`

**Quality Bonus**: If quality_score > 0.8:
- `base_reward × (quality_score - 0.8) × 1.5`

**Speed Bonus**: If completed faster than expected:
- `base_reward × time_saved_ratio × 0.5`

**Example**: Difficulty 1.5, quality 0.95, 6 hours (expected 12)
- Base: 15.0
- Quality: 15.0 × (0.95 - 0.8) × 1.5 = 3.375
- Speed: 15.0 × 0.5 × 0.5 = 3.75
- **Total**: 22.125

### Contribution Types

- **task_completion**: Completed a task
- **collaboration**: Collaborated with other agents
- **endorsement_received**: Received endorsement from peer
- **help_provided**: Helped another agent
- **innovation**: Introduced innovation or improvement
- **quality_work**: High-quality work delivered

### Reward Types

- **base_reward**: Standard task completion reward
- **performance_bonus**: Bonus for exceptional performance
- **quality_bonus**: Bonus for high-quality work
- **collaboration_bonus**: Bonus for collaborative work
- **streak_bonus**: Bonus for consistent performance
- **milestone_reward**: Reward for reaching milestone

### Use Cases

1. **Task Completion**: Automatically reward agents for successful task completion
2. **Quality Incentives**: Bonus rewards for high-quality work
3. **Collaboration Rewards**: Incentivize teamwork and knowledge sharing
4. **Competition Pools**: Distribute rewards based on performance rankings
5. **Peer Payments**: Agents can pay each other for services
6. **Performance Tracking**: Monitor economic activity and agent earnings

### Integration

```python
from src.services.agent_incentive import AgentIncentive, RewardType

# Initialize agent
AgentIncentive.initialize_agent(session=session, agent_id=1)

# Calculate task reward
calculation = AgentIncentive.calculate_task_reward(
    session=session,
    agent_id=1,
    task_id=123,
    completion_time_hours=6.0,
    quality_score=0.95,
    difficulty_multiplier=1.5
)

# Award the calculated reward
reward = AgentIncentive.award_reward(
    session=session,
    agent_id=1,
    reward_type=RewardType.PERFORMANCE_BONUS,
    amount=calculation["total_reward"],
    reason="Task completion with bonuses"
)

# Get leaderboard
leaderboard = AgentIncentive.get_leaderboard(
    session=session,
    metric="balance",
    limit=10
)
```

## Agent Learning System

The Agent Learning System enables agents to learn from past experiences, recognize patterns, adapt strategies, and continuously improve performance over time.

### Features

- **Experience Tracking**: Records all agent experiences for learning
- **Pattern Recognition**: Automatic pattern detection in experiences
- **Skill Development**: Tracks and improves proficiency in multiple skills
- **Strategy Learning**: Learns and refines strategies based on effectiveness
- **Learning Curves**: Monitors progress and improvement over time
- **Recommendations**: Provides data-driven recommendations based on past experiences

### API Endpoints

#### Initialize Learning

```bash
curl -X POST http://localhost:8001/api/learning/agents/initialize \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "initial_skills": {
      "python_programming": 60.0,
      "data_analysis": 45.0,
      "machine_learning": 30.0
    }
  }'
```

#### Record Experience

```bash
curl -X POST http://localhost:8001/api/learning/agents/1/experiences \
  -H "Content-Type: application/json" \
  -d '{
    "experience_type": "task_success",
    "outcome": "success",
    "context": {
      "task_type": "data_processing",
      "complexity": "medium",
      "duration_hours": 4
    },
    "learning_value": 0.8
  }'
```

#### Update Skill Proficiency

```bash
curl -X POST http://localhost:8001/api/learning/agents/1/skills \
  -H "Content-Type: application/json" \
  -d '{
    "skill_name": "python_programming",
    "proficiency_delta": 5.0,
    "reason": "Successfully completed complex Python task"
  }'
```

Response:
```json
{
  "success": true,
  "skill": {
    "agent_id": 1,
    "skill_name": "python_programming",
    "proficiency": 65.0,
    "skill_level": "advanced",
    "change": 5.0,
    "reason": "Successfully completed complex Python task"
  }
}
```

#### Learn Strategy

```bash
curl -X POST http://localhost:8001/api/learning/agents/1/strategies \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_name": "incremental_testing",
    "strategy_details": {
      "approach": "Test each component before integration",
      "applicable_to": ["development", "debugging"]
    },
    "effectiveness": 0.85,
    "learning_strategy": "reinforcement"
  }'
```

#### Apply Strategy

```bash
curl -X POST http://localhost:8001/api/learning/agents/1/strategies/apply \
  -H "Content-Type: application/json" \
  -d '{
    "strategy_name": "incremental_testing",
    "success": true
  }'
```

Response:
```json
{
  "success": true,
  "strategy": {
    "strategy_name": "incremental_testing",
    "times_used": 5,
    "success_count": 4,
    "failure_count": 1,
    "effectiveness": 0.80
  }
}
```

#### Get Recommendations

```bash
curl -X POST http://localhost:8001/api/learning/agents/1/recommendations \
  -H "Content-Type: application/json" \
  -d '{
    "task_context": {
      "task_type": "data_processing",
      "complexity": "high"
    }
  }'
```

Response:
```json
{
  "success": true,
  "agent_id": 1,
  "task_context": {"task_type": "data_processing", "complexity": "high"},
  "recommended_strategies": [
    {
      "strategy_name": "incremental_testing",
      "effectiveness": 0.85,
      "times_used": 5
    }
  ],
  "skills_to_improve": [
    {"skill": "machine_learning", "proficiency": 30.0}
  ],
  "similar_past_experiences": [
    {
      "experience_type": "task_success",
      "outcome": "success",
      "similarity": 0.8
    }
  ],
  "success_probability": 0.75
}
```

#### Get Learning Progress

```bash
curl -X GET http://localhost:8001/api/learning/agents/1/progress
```

Response:
```json
{
  "success": true,
  "agent_id": 1,
  "total_experiences": 45,
  "success_rate": 73.3,
  "recent_success_rate": 80.0,
  "total_skills": 3,
  "average_skill_proficiency": 45.0,
  "strategies_learned": 4,
  "patterns_recognized": 3,
  "learning_curve": [
    {
      "experience_count": 10,
      "success_rate": 60.0,
      "average_skill": 40.0,
      "timestamp": "2024-01-15T10:00:00"
    },
    {
      "experience_count": 20,
      "success_rate": 70.0,
      "average_skill": 42.5,
      "timestamp": "2024-01-16T10:00:00"
    }
  ]
}
```

#### Get Statistics

```bash
curl -X GET http://localhost:8001/api/learning/statistics
```

Response:
```json
{
  "success": true,
  "statistics": {
    "total_agents": 15,
    "total_experiences": 680,
    "total_skills_tracked": 45,
    "total_strategies_learned": 60,
    "average_success_rate": 68.5,
    "experience_types": {
      "task_success": 350,
      "task_failure": 150,
      "collaboration_success": 120,
      "negotiation_success": 60
    }
  }
}
```

### Experience Types

- **task_success**: Successfully completed task
- **task_failure**: Failed to complete task
- **collaboration_success**: Successful collaboration
- **collaboration_failure**: Failed collaboration
- **conflict_resolution**: Resolved conflict
- **negotiation_success**: Successful negotiation
- **negotiation_failure**: Failed negotiation

### Learning Strategies

- **reinforcement**: Learn from rewards and outcomes
- **supervised**: Learn from labeled examples
- **imitation**: Learn by observing others
- **adaptive**: Adapt strategies based on context

### Skill Levels

- **novice** (0-20): Just starting out
- **beginner** (21-40): Basic understanding
- **intermediate** (41-60): Solid competence
- **advanced** (61-80): High proficiency
- **expert** (81-100): Mastery level

### Use Cases

1. **Continuous Improvement**: Agents learn from every task to improve future performance
2. **Strategy Optimization**: Identify and refine effective strategies
3. **Skill Development**: Track proficiency growth across multiple competencies
4. **Success Prediction**: Estimate task success based on similar past experiences
5. **Adaptive Behavior**: Adjust approaches based on learned patterns
6. **Knowledge Transfer**: Learn from observing successful agents

### Integration

```python
from src.services.agent_learning import AgentLearning, ExperienceType

# Initialize learning
AgentLearning.initialize_learning(
    session=session,
    agent_id=1,
    initial_skills={"python": 50.0}
)

# Record experience
experience = AgentLearning.record_experience(
    session=session,
    agent_id=1,
    experience_type=ExperienceType.TASK_SUCCESS,
    outcome="success",
    context={"task_type": "coding"},
    learning_value=0.9
)

# Update skill
skill = AgentLearning.update_skill_proficiency(
    session=session,
    agent_id=1,
    skill_name="python",
    proficiency_delta=5.0
)

# Get recommendations
recommendations = AgentLearning.get_recommendations(
    session=session,
    agent_id=1,
    task_context={"task_type": "coding", "complexity": "high"}
)
```

## Agent Knowledge Sharing System

The Agent Knowledge Sharing System enables collaborative learning through a shared knowledge base. Agents can share, discover, validate, and build upon each other's knowledge.

### Key Features

- **Knowledge Types**: Facts, procedures, best practices, solutions, patterns, warnings, and tips
- **7 Categories**: Technical, process, domain, collaboration, strategy, tooling, and general knowledge
- **Smart Querying**: Text search with relevance scoring based on confidence and ratings
- **Validation System**: Peer validation with validated/disputed statuses (3+ validations = validated, 2+ disputes = disputed)
- **Usage Tracking**: Monitor knowledge effectiveness through usage outcomes
- **Access Levels**: Public, coalition, trusted, or private knowledge sharing
- **Trending Knowledge**: Discover popular knowledge based on recent activity
- **Subscriptions**: Subscribe to categories or tags for automatic updates

### Knowledge Types

1. **FACT** - Factual information
2. **PROCEDURE** - Step-by-step procedures
3. **BEST_PRACTICE** - Proven best practices
4. **SOLUTION** - Problem solutions
5. **PATTERN** - Recurring patterns
6. **WARNING** - Warnings and pitfalls to avoid
7. **TIP** - Helpful tips and tricks

### Categories

- **TECHNICAL** - Technical knowledge
- **PROCESS** - Process and workflow knowledge
- **DOMAIN** - Domain-specific knowledge
- **COLLABORATION** - Collaboration knowledge
- **STRATEGY** - Strategic knowledge
- **TOOLING** - Tool usage knowledge
- **GENERAL** - General knowledge

### Validation Statuses

- **UNVALIDATED** - Not yet validated (0 validations)
- **PENDING** - Validation in progress (1-2 validations)
- **VALIDATED** - Validated by peers (3+ validations)
- **DISPUTED** - Disputed by peers (2+ disputes)
- **DEPRECATED** - Marked as outdated

### REST API Endpoints

**Share Knowledge:**
```bash
POST /api/knowledge/share?agent_id=1
{
  "knowledge_type": "best_practice",
  "category": "technical",
  "title": "Python Error Handling Best Practices",
  "content": {
    "description": "Always use specific exception types",
    "example": "try:\n    process()\nexcept ValueError as e:\n    handle(e)",
    "benefits": ["Better debugging", "Clear intent"]
  },
  "tags": ["python", "error-handling"],
  "confidence": 0.9
}
```

**Query Knowledge Base:**
```bash
POST /api/knowledge/query?agent_id=1
{
  "query_text": "error handling python",
  "categories": ["technical"],
  "tags": ["python"],
  "min_confidence": 0.7,
  "validated_only": false,
  "limit": 10
}
```

**Rate Knowledge:**
```bash
POST /api/knowledge/items/knowledge_1/rate?agent_id=2
{
  "rating": 5,
  "comment": "Very helpful, solved my problem!",
  "helpful": true
}
```

**Validate Knowledge:**
```bash
POST /api/knowledge/items/knowledge_1/validate?validator_agent_id=3
{
  "is_valid": true,
  "validation_notes": "Verified this approach works in production",
  "evidence": {
    "tested_in": "production",
    "success_rate": 0.98
  }
}
```

**Record Usage:**
```bash
POST /api/knowledge/items/knowledge_1/usage?agent_id=2
{
  "usage_context": {
    "task_type": "debugging",
    "problem": "unhandled exceptions"
  },
  "was_useful": true,
  "outcome": "Successfully fixed the bug"
}
```

**Update Knowledge:**
```bash
PUT /api/knowledge/items/knowledge_1?agent_id=1
{
  "updates": {
    "content": {
      "description": "Updated best practice...",
      "example": "..."
    },
    "confidence": 0.95
  },
  "update_reason": "Added more comprehensive examples"
}
```

**Subscribe to Updates:**
```bash
POST /api/knowledge/subscribe?agent_id=1
{
  "category": "technical",
  "tags": ["python", "best-practices"]
}
```

**Get Trending Knowledge:**
```bash
GET /api/knowledge/trending?timeframe_hours=24&limit=10
```

**Get Agent's Knowledge Activity:**
```bash
GET /api/knowledge/agents/1?include_shared=true&include_accessed=true
```

**Get System Statistics:**
```bash
GET /api/knowledge/statistics
```

### Use Cases

**Scenario 1: Share Best Practice**
```python
from src.services.agent_knowledge import AgentKnowledge, KnowledgeType, KnowledgeCategory

# Agent discovers effective approach
knowledge = AgentKnowledge.share_knowledge(
    session=session,
    agent_id=1,
    knowledge_type=KnowledgeType.BEST_PRACTICE,
    category=KnowledgeCategory.TECHNICAL,
    title="Efficient Data Processing Pattern",
    content={
        "pattern": "Use generator expressions for large datasets",
        "code": "data = (process(item) for item in large_list)",
        "benefits": ["Lower memory usage", "Faster iteration"]
    },
    tags=["python", "performance"],
    confidence=0.85
)
```

**Scenario 2: Query and Apply Knowledge**
```python
# Agent searches for solution
results = AgentKnowledge.query_knowledge(
    session=session,
    agent_id=2,
    query_text="data processing performance",
    categories=[KnowledgeCategory.TECHNICAL],
    min_confidence=0.7,
    validated_only=True
)

# Apply knowledge
best_result = results["results"][0]
AgentKnowledge.record_usage(
    session=session,
    item_id=best_result["id"],
    agent_id=2,
    usage_context={"task": "process_large_dataset"},
    was_useful=True,
    outcome="Reduced memory by 60%"
)
```

**Scenario 3: Validate Knowledge**
```python
# Multiple agents validate
AgentKnowledge.validate_knowledge(
    session=session,
    item_id="knowledge_1",
    validator_agent_id=3,
    is_valid=True,
    validation_notes="Tested with 1M records, works perfectly"
)

# After 3 validations, status becomes VALIDATED
item = AgentKnowledge.get_knowledge_item(session, "knowledge_1")
assert item["validation_status"] == "validated"
```

**Scenario 4: Track Effectiveness**
```python
# Get knowledge item with metrics
item = AgentKnowledge.get_knowledge_item(session, "knowledge_1")

print(f"Average Rating: {item['average_rating']}/5")
print(f"Usage Count: {item['usage_count']}")
print(f"Effectiveness: {item['effectiveness']*100}%")
print(f"Validation Status: {item['validation_status']}")
```

### Integration Example

```python
from src.services.agent_knowledge import AgentKnowledge, KnowledgeType

# Share knowledge after successful task
knowledge = AgentKnowledge.share_knowledge(
    session=session,
    agent_id=1,
    knowledge_type=KnowledgeType.SOLUTION,
    category="technical",
    title="API Rate Limiting Solution",
    content={
        "problem": "API rate limit errors",
        "solution": "Implement exponential backoff",
        "code": "retry with delay = 2^attempt"
    },
    tags=["api", "rate-limiting"]
)

# Query before starting similar task
results = AgentKnowledge.query_knowledge(
    session=session,
    agent_id=2,
    query_text="API rate limiting",
    min_confidence=0.7
)

# Rate helpful knowledge
if results["results"]:
    AgentKnowledge.rate_knowledge(
        session=session,
        item_id=results["results"][0]["id"],
        agent_id=2,
        rating=5,
        helpful=True
    )
```

## Agent Performance Tracking System

The Agent Performance Tracking System provides comprehensive metrics, analytics, and trend analysis for monitoring agent performance over time.

### Key Features

- **Task Metrics**: Track completion rate, time, quality, errors, and retries
- **Efficiency Metrics**: Monitor throughput, utilization, response time, and idle time
- **Quality Metrics**: Measure accuracy, consistency, error rate, and defect rate
- **Resource Metrics**: Track CPU, memory, API calls, LLM tokens, and cost
- **Performance Levels**: Classify agents as excellent, good, average, below average, or poor
- **Trend Analysis**: Detect improving, stable, or declining performance trends
- **Agent Comparison**: Rank and compare multiple agents by any metric
- **Automated Alerts**: Receive alerts for low success rate, high errors, or low quality
- **Benchmarking**: Set target values and thresholds for performance standards

### Performance Levels

- **EXCELLENT** - Top 10% performers (score 0.9-1.0)
- **GOOD** - Top 25% performers (score 0.75-0.89)
- **AVERAGE** - Middle 50% (score 0.5-0.74)
- **BELOW_AVERAGE** - Bottom 25% (score 0.25-0.49)
- **POOR** - Bottom 10% (score 0-0.24)

### Metric Types

- **TASK_COMPLETION** - Task success rate and completion metrics
- **EFFICIENCY** - Throughput and resource utilization
- **QUALITY** - Accuracy, consistency, and error rates
- **RESOURCE_USAGE** - CPU, memory, API calls, tokens, cost
- **RESPONSE_TIME** - Average response times
- **THROUGHPUT** - Tasks completed per hour
- **ERROR_RATE** - Error frequency and patterns

### REST API Endpoints

**Record Task Completion:**
```bash
POST /api/performance/agents/1/task-completion
{
  "task_id": 100,
  "success": true,
  "completion_time_seconds": 45.5,
  "quality_score": 0.95,
  "error_count": 0,
  "retry_count": 0,
  "resource_usage": {
    "cpu": 35.5,
    "memory_mb": 512.0
  }
}
```

**Record Efficiency Metrics:**
```bash
POST /api/performance/agents/1/efficiency
{
  "throughput": 12.5,
  "utilization": 85.0,
  "average_response_time": 2.3,
  "idle_time_seconds": 120
}
```

**Record Quality Metrics:**
```bash
POST /api/performance/agents/1/quality
{
  "accuracy": 0.92,
  "consistency": 0.88,
  "error_rate": 0.05,
  "defect_rate": 0.02
}
```

**Record Resource Usage:**
```bash
POST /api/performance/agents/1/resource-usage
{
  "cpu_usage": 45.5,
  "memory_usage_mb": 768.0,
  "api_calls": 150,
  "tokens_used": 25000,
  "cost": 0.35
}
```

**Get Performance Summary:**
```bash
GET /api/performance/agents/1/summary?timeframe_hours=24
```

**Get Performance Trend:**
```bash
GET /api/performance/agents/1/trend?metric_type=task_completion&timeframe_hours=168
```

**Compare Agents:**
```bash
POST /api/performance/compare
{
  "agent_ids": [1, 2, 3, 4, 5],
  "metric_type": "efficiency",
  "timeframe_hours": 24
}
```

**Get Performance Alerts:**
```bash
GET /api/performance/agents/1/alerts
```

**Set Benchmark:**
```bash
POST /api/performance/benchmarks
{
  "metric_type": "task_completion",
  "target_value": 0.95,
  "threshold_warning": 0.85,
  "threshold_critical": 0.70,
  "description": "Task success rate benchmark"
}
```

**Get System Statistics:**
```bash
GET /api/performance/statistics
```

### Use Cases

**Scenario 1: Track Task Performance**
```python
from src.services.agent_performance import AgentPerformance

# Record task completion
AgentPerformance.record_task_completion(
    session=session,
    agent_id=1,
    task_id=100,
    success=True,
    completion_time_seconds=45.5,
    quality_score=0.95,
    error_count=0,
    retry_count=0,
    resource_usage={"cpu": 35.5, "memory_mb": 512.0}
)

# Get summary
summary = AgentPerformance.get_performance_summary(
    session=session,
    agent_id=1,
    timeframe_hours=24
)

print(f"Success Rate: {summary['task_metrics']['success_rate']*100:.1f}%")
print(f"Average Time: {summary['task_metrics']['average_completion_time']:.1f}s")
print(f"Performance Level: {summary['performance_level']}")
```

**Scenario 2: Monitor Trends**
```python
# Get performance trend
trend = AgentPerformance.get_performance_trend(
    session=session,
    agent_id=1,
    metric_type="task_completion",
    timeframe_hours=168  # 1 week
)

if trend["trend"] == "declining":
    print(f"⚠️ Performance declining by {abs(trend['change_percent']):.1f}%")
    # Take corrective action
elif trend["trend"] == "improving":
    print(f"✅ Performance improving by {trend['change_percent']:.1f}%")
```

**Scenario 3: Compare Agent Performance**
```python
# Compare multiple agents
comparison = AgentPerformance.compare_agents(
    session=session,
    agent_ids=[1, 2, 3, 4, 5],
    metric_type="efficiency",
    timeframe_hours=24
)

print("Agent Rankings:")
for ranking in comparison["rankings"]:
    print(f"  Rank {ranking['rank']}: Agent {ranking['agent_id']} - {ranking['value']:.2f}")

best = comparison["best_performer"]
print(f"\nBest Performer: Agent {best['agent_id']} ({best['performance_level']})")
```

**Scenario 4: Set Performance Benchmarks**
```python
# Set benchmark for success rate
AgentPerformance.set_benchmark(
    session=session,
    metric_type="task_completion",
    target_value=0.95,  # Target 95% success rate
    threshold_warning=0.85,  # Warn below 85%
    threshold_critical=0.70,  # Critical below 70%
    description="Task success rate benchmark"
)

# Check alerts
alerts = AgentPerformance.get_performance_alerts(session=session, agent_id=1)
for alert in alerts["alerts"]:
    print(f"[{alert['severity'].upper()}] {alert['message']}")
```

**Scenario 5: Resource Optimization**
```python
# Track resource usage
AgentPerformance.record_resource_usage(
    session=session,
    agent_id=1,
    cpu_usage=45.5,
    memory_usage_mb=768.0,
    api_calls=150,
    tokens_used=25000,
    cost=0.35
)

# Analyze costs
summary = AgentPerformance.get_performance_summary(session=session, agent_id=1)
print(f"Total Cost: ${summary['resource_metrics']['total_cost']:.2f}")
print(f"Tokens Used: {summary['resource_metrics']['total_tokens']:,}")
print(f"Cost per Task: ${summary['resource_metrics']['total_cost'] / summary['task_metrics']['total_tasks']:.4f}")
```

### Integration Example

```python
from src.services.agent_performance import AgentPerformance, MetricType

# After task execution
start_time = time.time()
result = agent.execute_task(task)
completion_time = time.time() - start_time

# Record comprehensive metrics
AgentPerformance.record_task_completion(
    session=session,
    agent_id=agent.id,
    task_id=task.id,
    success=result.success,
    completion_time_seconds=completion_time,
    quality_score=result.quality_score,
    error_count=result.error_count,
    retry_count=result.retry_count,
    resource_usage={
        "cpu": result.cpu_usage,
        "memory_mb": result.memory_mb,
        "api_calls": result.api_calls,
        "tokens": result.tokens_used,
        "cost": result.cost
    }
)

# Check for performance issues
alerts = AgentPerformance.get_performance_alerts(session=session, agent_id=agent.id)
if alerts["total_alerts"] > 0:
    for alert in alerts["alerts"][:3]:  # Show latest 3
        if alert["severity"] == "critical":
            # Take immediate action
            notify_admin(alert)
        else:
            log_warning(alert)

# Periodic trend analysis
trend = AgentPerformance.get_performance_trend(
    session=session,
    agent_id=agent.id,
    metric_type=MetricType.TASK_COMPLETION,
    timeframe_hours=168
)

if trend["trend"] == "declining":
    # Trigger investigation
    schedule_performance_review(agent.id)
```

## Agent Role Management System

The Agent Role Management System provides dynamic role assignment, hierarchies, permissions, and performance tracking. Enables role-based task routing and agent career progression.

### Key Features

- **10 Role Types**: Leader, coordinator, specialist, executor, analyst, reviewer, researcher, developer, tester, support
- **5 Hierarchy Levels**: Executive (L5), senior (L4), intermediate (L3), junior (L2), entry (L1)
- **Dynamic Assignment**: Assign multiple roles to agents with start/end dates
- **Role Promotion**: Automatically promote agents to higher levels based on performance
- **Performance Tracking**: Track role-specific performance and task completion
- **Permissions System**: Define role-based permissions and access control
- **Role Suggestions**: AI-powered role suggestions based on task requirements
- **Capability Matching**: Match roles to tasks based on required capabilities
- **Hierarchy Visualization**: View role structure organized by type and level

### Role Types

1. **LEADER** - Team leader and decision maker
2. **COORDINATOR** - Coordinates tasks and agents
3. **SPECIALIST** - Domain specialist with deep expertise
4. **EXECUTOR** - Task executor and implementer
5. **ANALYST** - Data and information analyst
6. **REVIEWER** - Quality reviewer and validator
7. **RESEARCHER** - Information researcher
8. **DEVELOPER** - Development specialist
9. **TESTER** - Quality assurance tester
10. **SUPPORT** - Support and assistance provider

### Role Levels

- **EXECUTIVE** (Level 5) - Executive level with highest authority
- **SENIOR** (Level 4) - Senior level with experienced leadership
- **INTERMEDIATE** (Level 3) - Intermediate level with solid skills
- **JUNIOR** (Level 2) - Junior level developing expertise
- **ENTRY** (Level 1) - Entry level for beginners

### Assignment Statuses

- **ACTIVE** - Currently active assignment
- **SUSPENDED** - Temporarily suspended
- **COMPLETED** - Successfully completed
- **REVOKED** - Revoked/terminated

### REST API Endpoints

**Define Role:**
```bash
POST /api/roles
{
  "role_type": "specialist",
  "role_name": "Senior Python Specialist",
  "role_level": "senior",
  "description": "Expert in Python development and architecture",
  "responsibilities": [
    "Design Python applications",
    "Code review",
    "Mentor junior developers"
  ],
  "required_capabilities": ["python", "architecture", "testing"],
  "optional_capabilities": ["docker", "kubernetes"],
  "min_experience_hours": 1000,
  "permissions": ["code_review", "deployment"]
}
```

**Assign Role to Agent:**
```bash
POST /api/roles/agents/1/assign
{
  "role_id": "role_1",
  "assigned_by": 5,
  "assignment_reason": "Strong Python skills and performance",
  "start_date": "2024-01-01T00:00:00Z"
}
```

**Revoke Role:**
```bash
POST /api/roles/assignments/assignment_1/revoke
{
  "revoked_by": 5,
  "revocation_reason": "Agent reassigned to different team"
}
```

**Update Assignment:**
```bash
PUT /api/roles/assignments/assignment_1
{
  "status": "suspended",
  "end_date": "2024-12-31T23:59:59Z"
}
```

**Record Role Performance:**
```bash
POST /api/roles/assignments/assignment_1/performance
{
  "task_id": 100,
  "performance_score": 0.92,
  "quality_score": 0.95,
  "completion_time": 3600,
  "notes": "Excellent code quality and documentation"
}
```

**Promote Agent:**
```bash
POST /api/roles/agents/1/promote
{
  "current_assignment_id": "assignment_1",
  "new_role_level": "senior",
  "promoted_by": 5,
  "promotion_reason": "Consistently high performance and mentorship"
}
```

**Get Agent Roles:**
```bash
GET /api/roles/agents/1/roles?active_only=true
```

**Get Agents by Role:**
```bash
GET /api/roles/role_1/agents?active_only=true
```

**Suggest Role for Task:**
```bash
POST /api/roles/suggest
{
  "task_requirements": {
    "capabilities": ["python", "testing", "api-design"],
    "complexity": "high"
  },
  "required_level": "intermediate"
}
```

**Get Role Hierarchy:**
```bash
GET /api/roles/hierarchy
```

**Get Statistics:**
```bash
GET /api/roles/statistics
```

### Use Cases

**Scenario 1: Define and Assign Roles**
```python
from src.services.agent_role import AgentRole, RoleType, RoleLevel

# Define a new role
role = AgentRole.define_role(
    session=session,
    role_type=RoleType.SPECIALIST,
    role_name="Senior Python Specialist",
    role_level=RoleLevel.SENIOR,
    description="Expert Python developer",
    responsibilities=["Design", "Code Review", "Mentoring"],
    required_capabilities=["python", "architecture", "testing"],
    min_experience_hours=1000
)

# Assign to agent
assignment = AgentRole.assign_role(
    session=session,
    agent_id=1,
    role_id=role["id"],
    assigned_by=5,
    assignment_reason="Strong technical skills"
)

print(f"Assigned {role['role_name']} to agent 1")
```

**Scenario 2: Track Performance and Promote**
```python
# Record performance
AgentRole.record_role_performance(
    session=session,
    assignment_id="assignment_1",
    task_id=100,
    performance_score=0.92,
    quality_score=0.95,
    completion_time=3600
)

# Get performance stats
roles = AgentRole.get_agent_roles(session=session, agent_id=1)
assignment = roles["assignments"][0]

if assignment["performance_score"] > 0.9 and assignment["tasks_completed"] > 50:
    # Promote agent
    promotion = AgentRole.promote_agent(
        session=session,
        agent_id=1,
        current_assignment_id=assignment["id"],
        new_role_level=RoleLevel.SENIOR,
        promoted_by=5,
        promotion_reason="Consistently excellent performance"
    )
    print(f"Promoted to {promotion['new_level']}!")
```

**Scenario 3: Role-Based Task Routing**
```python
# Get role suggestion for task
task_requirements = {
    "capabilities": ["python", "testing", "api-design"],
    "complexity": "high"
}

suggestions = AgentRole.suggest_role_for_task(
    session=session,
    task_requirements=task_requirements,
    required_level=RoleLevel.INTERMEDIATE
)

# Get agents with suggested role
best_role = suggestions["suggestions"][0]
agents = AgentRole.get_agents_by_role(
    session=session,
    role_id=best_role["role_id"],
    active_only=True
)

# Assign task to best performer
if agents["agents"]:
    best_agent = max(
        agents["agents"],
        key=lambda a: a["assignment"]["performance_score"]
    )
    print(f"Assign task to agent {best_agent['agent_id']}")
```

**Scenario 4: Role Hierarchy Management**
```python
# View role hierarchy
hierarchy = AgentRole.get_role_hierarchy(session=session)

for role_type, levels in hierarchy["hierarchy"].items():
    print(f"\n{role_type.upper()}:")
    for level in hierarchy["levels"][::-1]:  # Top to bottom
        if level in levels:
            roles = levels[level]
            print(f"  {level}: {len(roles)} roles")

# Get statistics
stats = AgentRole.get_role_statistics(session=session)
print(f"\nTotal roles defined: {stats['total_role_definitions']}")
print(f"Active assignments: {stats['active_assignments']}")
print(f"Agents with roles: {stats['agents_with_roles']}")
```

**Scenario 5: Role Lifecycle Management**
```python
# Assign role with end date
assignment = AgentRole.assign_role(
    session=session,
    agent_id=1,
    role_id="role_1",
    start_date="2024-01-01T00:00:00Z",
    end_date="2024-12-31T23:59:59Z",
    assignment_reason="6-month project assignment"
)

# Update status
AgentRole.update_role_assignment(
    session=session,
    assignment_id=assignment["id"],
    status="suspended",
    metadata={"suspension_reason": "On leave"}
)

# Later, revoke if needed
AgentRole.revoke_role(
    session=session,
    assignment_id=assignment["id"],
    revoked_by=5,
    revocation_reason="Project cancelled"
)
```

### Integration Example

```python
from src.services.agent_role import AgentRole, RoleType, RoleLevel

# Define roles for new team
specialist_role = AgentRole.define_role(
    session=session,
    role_type=RoleType.SPECIALIST,
    role_name="API Specialist",
    role_level=RoleLevel.INTERMEDIATE,
    description="API design and development",
    responsibilities=["API design", "Implementation", "Documentation"],
    required_capabilities=["api-design", "python", "swagger"],
    permissions=["api_deploy", "code_review"]
)

# Assign agents to roles
for agent_id in [1, 2, 3]:
    AgentRole.assign_role(
        session=session,
        agent_id=agent_id,
        role_id=specialist_role["id"],
        assigned_by=team_lead_id
    )

# When task arrives, route by role
task_requirements = {
    "capabilities": ["api-design", "python"],
    "complexity": "medium"
}

suggestions = AgentRole.suggest_role_for_task(
    session=session,
    task_requirements=task_requirements
)

# Get available agents with matching role
best_role = suggestions["suggestions"][0]
agents = AgentRole.get_agents_by_role(
    session=session,
    role_id=best_role["role_id"]
)

# Select agent with best performance
selected_agent = max(
    agents["agents"],
    key=lambda a: a["assignment"]["performance_score"]
)

# Assign task and track performance
result = execute_task(task_id, selected_agent["agent_id"])

AgentRole.record_role_performance(
    session=session,
    assignment_id=selected_agent["assignment"]["id"],
    task_id=task_id,
    performance_score=result.performance_score,
    quality_score=result.quality_score,
    completion_time=result.duration
)
```

## Agent Workflow Templates System

The Agent Workflow Templates System provides reusable workflow patterns for common multi-agent scenarios. Create, instantiate, compose, and version workflow templates.

### Key Features

- **8 Template Categories**: Sequential, parallel, hierarchical, iterative, conditional, map-reduce, pipeline, broadcast
- **Template Library**: Reusable patterns for common multi-agent workflows
- **Parameter Binding**: Parameterized templates for flexible instantiation
- **Role Assignments**: Map workflow roles to specific agents
- **Template Composition**: Combine templates sequentially or in parallel
- **Version Management**: Track template versions and deprecate old ones
- **Validation**: Automatic validation of template structure and dependencies
- **Usage Tracking**: Monitor template usage and popularity
- **Instant Workflow Creation**: Instantiate complex workflows from templates in seconds

### Template Categories

- **SEQUENTIAL** - Steps execute one after another
- **PARALLEL** - Steps execute simultaneously
- **HIERARCHICAL** - Hierarchical task decomposition
- **ITERATIVE** - Loop-based execution patterns
- **CONDITIONAL** - Branching based on conditions
- **MAP_REDUCE** - Distribute work, then aggregate results
- **PIPELINE** - Data processing pipeline
- **BROADCAST** - Send to multiple agents simultaneously

### Template Statuses

- **DRAFT** - Under development
- **ACTIVE** - Available for use
- **DEPRECATED** - Superseded by newer version
- **ARCHIVED** - No longer available

### REST API Endpoints

**Create Template:**
```bash
POST /api/workflow-templates/templates
{
  "template_name": "Code Review Workflow",
  "category": "sequential",
  "description": "Standard code review process",
  "steps": [
    {
      "id": "analyze",
      "type": "task",
      "description": "Analyze code quality",
      "assigned_agent": "@{reviewer}"
    },
    {
      "id": "suggest",
      "type": "task",
      "description": "Suggest improvements",
      "assigned_agent": "@{reviewer}"
    },
    {
      "id": "validate",
      "type": "task",
      "description": "Validate changes",
      "assigned_agent": "@{validator}"
    }
  ],
  "required_roles": ["reviewer", "validator"],
  "parameters": [
    {
      "name": "language",
      "type": "string",
      "required": true,
      "description": "Programming language"
    },
    {
      "name": "severity_threshold",
      "type": "number",
      "default": 0.7,
      "description": "Minimum severity for issues"
    }
  ],
  "version": "1.0.0"
}
```

**Instantiate Template:**
```bash
POST /api/workflow-templates/templates/template_1/instantiate
{
  "instance_name": "Review PR #123",
  "parameter_bindings": {
    "language": "python",
    "severity_threshold": 0.8
  },
  "agent_assignments": {
    "reviewer": 5,
    "validator": 8
  }
}
```

**Compose Templates:**
```bash
POST /api/workflow-templates/templates/compose
{
  "composition_name": "Full CI/CD Pipeline",
  "templates": [
    {"template_id": "template_1"},
    {"template_id": "template_2"},
    {"template_id": "template_3"}
  ],
  "composition_strategy": "sequential"
}
```

**Update Template:**
```bash
PUT /api/workflow-templates/templates/template_1
{
  "updates": {
    "description": "Updated code review process with security scan",
    "steps": [...]
  },
  "create_new_version": true
}
```

**Validate Template:**
```bash
POST /api/workflow-templates/templates/template_1/validate
```

**Get Template:**
```bash
GET /api/workflow-templates/templates/template_1
```

**List Templates:**
```bash
GET /api/workflow-templates/templates?category=sequential&status=active&search=review
```

**Get Template Versions:**
```bash
GET /api/workflow-templates/templates/name/Code%20Review%20Workflow/versions
```

**Get Popular Templates:**
```bash
GET /api/workflow-templates/templates/popular?limit=10
```

**Get Statistics:**
```bash
GET /api/workflow-templates/templates/statistics
```

### Use Cases

**Scenario 1: Create and Use Template**
```python
from src.services.workflow_template import WorkflowTemplate, TemplateCategory

# Create a code review template
template = WorkflowTemplate.create_template(
    session=session,
    template_name="Code Review Workflow",
    category=TemplateCategory.SEQUENTIAL,
    description="Standard code review process",
    steps=[
        {
            "id": "analyze",
            "type": "task",
            "description": "Analyze code quality",
            "assigned_agent": "@{reviewer}"
        },
        {
            "id": "suggest",
            "type": "task",
            "description": "Suggest improvements",
            "assigned_agent": "@{reviewer}"
        }
    ],
    required_roles=["reviewer"],
    parameters=[
        {
            "name": "language",
            "type": "string",
            "required": True
        }
    ]
)

# Instantiate for specific PR
instance = WorkflowTemplate.instantiate_template(
    session=session,
    template_id=template["id"],
    instance_name="Review PR #123",
    parameter_bindings={"language": "python"},
    agent_assignments={"reviewer": 5}
)

print(f"Created workflow: {instance['instance_name']}")
```

**Scenario 2: Compose Templates**
```python
# Create simple templates
analyze_template = WorkflowTemplate.create_template(
    session=session,
    template_name="Static Analysis",
    category=TemplateCategory.SEQUENTIAL,
    description="Run static analysis",
    steps=[{"id": "analyze", "type": "task"}],
    required_roles=["analyzer"]
)

test_template = WorkflowTemplate.create_template(
    session=session,
    template_name="Run Tests",
    category=TemplateCategory.PARALLEL,
    description="Execute test suite",
    steps=[{"id": "test", "type": "task"}],
    required_roles=["tester"]
)

# Compose into CI pipeline
ci_pipeline = WorkflowTemplate.compose_templates(
    session=session,
    composition_name="CI Pipeline",
    templates=[
        {"template_id": analyze_template["id"]},
        {"template_id": test_template["id"]}
    ],
    composition_strategy="sequential"
)

print(f"Created pipeline: {ci_pipeline['template_name']}")
```

**Scenario 3: Version Management**
```python
# Update template with new version
updated = WorkflowTemplate.update_template(
    session=session,
    template_id="template_1",
    updates={
        "description": "Enhanced with security scanning",
        "steps": [...]  # Updated steps
    },
    create_new_version=True  # Creates v1.1.0, deprecates v1.0.0
)

# Get all versions
versions = WorkflowTemplate.get_template_versions(
    session=session,
    template_name="Code Review Workflow"
)

print(f"Latest version: {versions['latest_version']['version']}")
print(f"Total versions: {versions['total_versions']}")
```

**Scenario 4: Validate Before Use**
```python
# Validate template structure
validation = WorkflowTemplate.validate_template(
    session=session,
    template_id="template_1"
)

if validation["is_valid"]:
    print("✅ Template is valid")
else:
    print("❌ Validation errors:")
    for error in validation["errors"]:
        print(f"  - {error}")

if validation["warnings"]:
    print("⚠️  Warnings:")
    for warning in validation["warnings"]:
        print(f"  - {warning}")
```

**Scenario 5: Template Library Usage**
```python
# Find popular templates
popular = WorkflowTemplate.get_popular_templates(
    session=session,
    limit=5
)

print("Most Popular Templates:")
for template in popular["popular_templates"]:
    print(f"  {template['template_name']}: {template['usage_count']} uses")

# Search for specific type
results = WorkflowTemplate.list_templates(
    session=session,
    category=TemplateCategory.PARALLEL,
    status="active",
    search="test"
)

print(f"\nFound {results['total']} parallel testing templates")
```

### Integration Example

```python
from src.services.workflow_template import WorkflowTemplate, TemplateCategory

# Define template library
templates = {
    "data_pipeline": WorkflowTemplate.create_template(
        session=session,
        template_name="Data Pipeline",
        category=TemplateCategory.PIPELINE,
        description="ETL data pipeline",
        steps=[
            {"id": "extract", "type": "task", "assigned_agent": "@{extractor}"},
            {"id": "transform", "type": "task", "assigned_agent": "@{transformer}"},
            {"id": "load", "type": "task", "assigned_agent": "@{loader}"}
        ],
        required_roles=["extractor", "transformer", "loader"],
        parameters=[
            {"name": "source", "type": "string", "required": True},
            {"name": "destination", "type": "string", "required": True}
        ]
    ),

    "parallel_processing": WorkflowTemplate.create_template(
        session=session,
        template_name="Parallel Processing",
        category=TemplateCategory.MAP_REDUCE,
        description="Process items in parallel",
        steps=[
            {"id": "map", "type": "parallel", "assigned_agent": "@{worker}"},
            {"id": "reduce", "type": "task", "assigned_agent": "@{aggregator}"}
        ],
        required_roles=["worker", "aggregator"],
        parameters=[
            {"name": "batch_size", "type": "number", "default": 10}
        ]
    )
}

# User requests workflow
def create_workflow_from_template(template_name, params, agents):
    # Find template
    templates_list = WorkflowTemplate.list_templates(
        session=session,
        search=template_name,
        status="active"
    )

    if not templates_list["templates"]:
        raise ValueError(f"Template '{template_name}' not found")

    template = templates_list["templates"][0]

    # Validate before use
    validation = WorkflowTemplate.validate_template(
        session=session,
        template_id=template["id"]
    )

    if not validation["is_valid"]:
        raise ValueError(f"Template validation failed: {validation['errors']}")

    # Instantiate
    instance = WorkflowTemplate.instantiate_template(
        session=session,
        template_id=template["id"],
        instance_name=f"{template_name}_instance_{datetime.utcnow().timestamp()}",
        parameter_bindings=params,
        agent_assignments=agents
    )

    return instance

# Usage
workflow = create_workflow_from_template(
    template_name="Data Pipeline",
    params={"source": "s3://data", "destination": "postgres://db"},
    agents={"extractor": 1, "transformer": 2, "loader": 3}
)

print(f"Created workflow with {len(workflow['steps'])} steps")
```

## Agent Discovery System

The Agent Discovery System enables agents to register, find each other based on capabilities, and form dynamic service networks. Provides capability-based matchmaking and service directory functionality.

### Key Features

- **Agent Registration**: Register agents with capabilities, categories, and metadata
- **Capability-Based Discovery**: Find agents by required capabilities
- **Service Directory**: Register and discover services provided by agents
- **Status Management**: Track agent availability (available, busy, unavailable, maintenance)
- **Heartbeat Monitoring**: Automatic health checks via heartbeat protocol
- **8 Capability Categories**: Computation, storage, communication, analysis, generation, transformation, validation, orchestration
- **Dynamic Capabilities**: Add/remove capabilities at runtime
- **Relevance Ranking**: Match results ranked by relevance score
- **Multi-Index Search**: Search by capabilities, categories, tags simultaneously

### Discovery Statuses

- **AVAILABLE** - Agent is ready for tasks
- **BUSY** - Agent is currently processing tasks
- **UNAVAILABLE** - Agent is offline or unreachable
- **MAINTENANCE** - Agent is under maintenance

### Capability Categories

- **COMPUTATION** - Computational capabilities (processing, calculation)
- **STORAGE** - Data storage and retrieval
- **COMMUNICATION** - Inter-agent communication
- **ANALYSIS** - Data analysis and insights
- **GENERATION** - Content and code generation
- **TRANSFORMATION** - Data transformation and conversion
- **VALIDATION** - Validation and verification
- **ORCHESTRATION** - Coordination and orchestration

### REST API Endpoints

**Register Agent:**
```bash
POST /api/discovery/register?agent_id=5
{
  "agent_name": "Data Processor Agent",
  "capabilities": ["data_processing", "etl", "transformation"],
  "categories": ["transformation", "storage"],
  "tags": ["fast", "reliable", "python"],
  "endpoint": "http://agent5.example.com:8080",
  "metadata": {
    "version": "2.0",
    "max_concurrent_tasks": 10
  }
}
```

**Discover Agents:**
```bash
POST /api/discovery/discover
{
  "required_capabilities": ["data_processing", "machine_learning"],
  "categories": ["analysis"],
  "tags": ["python"],
  "status": "available",
  "match_all_capabilities": false,
  "limit": 10
}
```

**Update Status:**
```bash
PUT /api/discovery/agents/5/status
{
  "status": "busy",
  "reason": "Processing large dataset"
}
```

**Send Heartbeat:**
```bash
POST /api/discovery/agents/5/heartbeat
{
  "metrics": {
    "load": 0.75,
    "memory_usage": 0.60,
    "active_tasks": 3
  }
}
```

**Register Service:**
```bash
POST /api/discovery/agents/5/services
{
  "service_name": "data_transformation",
  "service_description": "ETL data transformation service",
  "service_metadata": {
    "max_throughput": 1000,
    "supported_formats": ["csv", "json", "parquet"]
  }
}
```

**Discover Service:**
```bash
GET /api/discovery/services/data_transformation?only_available=true
```

**Add Capability:**
```bash
POST /api/discovery/agents/5/capabilities
{
  "capability": "real_time_processing",
  "category": "computation"
}
```

**Remove Capability:**
```bash
DELETE /api/discovery/agents/5/capabilities
{
  "capability": "batch_processing"
}
```

**Unregister Agent:**
```bash
DELETE /api/discovery/agents/5/unregister
```

**Get Agent Info:**
```bash
GET /api/discovery/agents/5
```

**List All Agents:**
```bash
GET /api/discovery/agents?status=available&category=analysis
```

**Get Capabilities Catalog:**
```bash
GET /api/discovery/capabilities
```

**Get Service Directory:**
```bash
GET /api/discovery/services
```

**Check Agent Health:**
```bash
GET /api/discovery/health-check?timeout_seconds=300
```

**Get Statistics:**
```bash
GET /api/discovery/statistics
```

### Use Cases

**Scenario 1: Agent Registration and Discovery**
```python
from src.services.agent_discovery import AgentDiscovery, CapabilityCategory

# Agent registers itself
registration = AgentDiscovery.register_agent(
    session=session,
    agent_id=5,
    agent_name="ML Model Trainer",
    capabilities=["machine_learning", "model_training", "hyperparameter_tuning"],
    categories=[CapabilityCategory.COMPUTATION, CapabilityCategory.ANALYSIS],
    tags=["tensorflow", "pytorch", "gpu"],
    endpoint="http://ml-agent:8080"
)

print(f"Registered: {registration['agent_name']}")

# Another agent searches for ML capabilities
matches = AgentDiscovery.discover_agents(
    session=session,
    required_capabilities=["machine_learning"],
    status="available",
    limit=5
)

print(f"Found {matches['total_matches']} matching agents")
for match in matches['matches']:
    print(f"  - {match['agent_name']}: {match['relevance_score']:.2f}")
```

**Scenario 2: Service Registration and Discovery**
```python
# Agent registers a service
service = AgentDiscovery.register_service(
    session=session,
    agent_id=5,
    service_name="model_inference",
    service_description="Real-time ML model inference",
    service_metadata={
        "models": ["resnet50", "bert-base"],
        "latency_ms": 50,
        "throughput": 100
    }
)

# Client discovers service providers
providers = AgentDiscovery.discover_service(
    session=session,
    service_name="model_inference",
    only_available=True
)

print(f"Service has {providers['total_providers']} providers")
for provider in providers['providers']:
    agent = AgentDiscovery.get_agent_info(session, provider['agent_id'])
    print(f"  - {agent['agent_name']} at {agent['endpoint']}")
```

**Scenario 3: Dynamic Capability Management**
```python
# Agent adds new capability after upgrade
AgentDiscovery.add_capability(
    session=session,
    agent_id=5,
    capability="distributed_training",
    category=CapabilityCategory.COMPUTATION
)

# Agent removes deprecated capability
AgentDiscovery.remove_capability(
    session=session,
    agent_id=5,
    capability="legacy_preprocessing"
)

# Verify updated capabilities
agent_info = AgentDiscovery.get_agent_info(session=session, agent_id=5)
print(f"Current capabilities: {agent_info['capabilities']}")
```

**Scenario 4: Health Monitoring with Heartbeats**
```python
import time

# Agent sends periodic heartbeats
while True:
    heartbeat = AgentDiscovery.heartbeat(
        session=session,
        agent_id=5,
        metrics={
            "load": 0.65,
            "memory_usage": 0.72,
            "active_tasks": 4,
            "completed_tasks": 127
        }
    )

    print(f"Heartbeat acknowledged, status: {heartbeat['current_status']}")
    time.sleep(60)  # Send every 60 seconds

# System checks health
health = AgentDiscovery.check_agent_health(
    session=session,
    timeout_seconds=300
)

print(f"Healthy: {health['healthy_count']}, Unhealthy: {health['unhealthy_count']}")
```

**Scenario 5: Building Agent Networks**
```python
# System maintains service catalog
catalog = AgentDiscovery.get_capabilities_catalog(session=session)

print(f"Total capabilities: {catalog['total_capabilities']}")
for capability, info in catalog['capabilities'].items():
    print(f"{capability}: {info['available_agents']} agents available")

# Discover complementary agents for workflow
data_agents = AgentDiscovery.discover_agents(
    session=session,
    required_capabilities=["data_processing"],
    status="available"
)

ml_agents = AgentDiscovery.discover_agents(
    session=session,
    required_capabilities=["machine_learning"],
    status="available"
)

viz_agents = AgentDiscovery.discover_agents(
    session=session,
    required_capabilities=["visualization"],
    status="available"
)

# Build pipeline from discovered agents
pipeline = {
    "data_processor": data_agents['matches'][0]['agent_id'],
    "ml_trainer": ml_agents['matches'][0]['agent_id'],
    "visualizer": viz_agents['matches'][0]['agent_id']
}

print(f"Assembled pipeline: {pipeline}")
```

## Agent Contract Management System

The Agent Contract Management System manages formal agreements and SLAs between agents, providing contract lifecycle management, performance monitoring, violation detection, and enforcement.

### Key Features

- **6 Contract Types**: SLA, collaboration, resource sharing, data exchange, task delegation, coalition agreements
- **Contract Lifecycle**: Draft → Proposed → Active → Fulfilled/Breached/Terminated
- **SLA Terms**: Define response time, quality, throughput, availability guarantees
- **Performance Monitoring**: Automatic tracking of contract metrics
- **Violation Detection**: Real-time SLA violation detection and recording
- **Compliance Checking**: Validate current performance against SLA requirements
- **Penalty Management**: Automatic penalty application for violations
- **Contract Renewal**: Renewable contracts with updated terms
- **Performance Scoring**: Calculate overall contract performance scores

### Contract Types

- **SERVICE_LEVEL_AGREEMENT** (sla) - Service level agreements with SLA terms
- **COLLABORATION_AGREEMENT** (collaboration) - Collaboration agreements between agents
- **RESOURCE_SHARING** (resource_sharing) - Resource sharing agreements
- **DATA_EXCHANGE** (data_exchange) - Data exchange agreements
- **TASK_DELEGATION** (task_delegation) - Task delegation agreements
- **COALITION_AGREEMENT** (coalition) - Coalition membership agreements

### Contract Statuses

- **DRAFT** - Draft contract, not proposed yet
- **PROPOSED** - Proposed, awaiting activation
- **ACTIVE** - Active and being monitored
- **FULFILLED** - Successfully completed
- **BREACHED** - SLA violations exceeded threshold (3+ violations)
- **TERMINATED** - Terminated before completion
- **EXPIRED** - Expired without renewal

### Violation Types

- **RESPONSE_TIME** - Response time exceeds SLA
- **THROUGHPUT** - Throughput below SLA
- **QUALITY** - Quality score below SLA
- **AVAILABILITY** - Availability below SLA
- **RESOURCE_LIMIT** - Resource limits exceeded
- **DEADLINE** - Deadline missed

### REST API Endpoints

**Create Contract:**
```bash
POST /api/contracts/contracts
{
  "contract_type": "sla",
  "provider_agent_id": 5,
  "consumer_agent_id": 8,
  "title": "ML Model Inference SLA",
  "description": "SLA for real-time ML model inference service",
  "sla_terms": {
    "max_response_time": 0.5,
    "min_quality": 0.95,
    "min_availability": 99.9,
    "max_throughput": 1000
  },
  "obligations": {
    "provider": [
      "Maintain 99.9% uptime",
      "Respond within 500ms",
      "Deliver quality score >= 0.95"
    ],
    "consumer": [
      "Pay usage fees on time",
      "Respect rate limits"
    ]
  },
  "duration_hours": 720,
  "renewable": true,
  "penalty_terms": {
    "early_termination_fee": 1000,
    "violation_penalty": 50
  }
}
```

**Activate Contract:**
```bash
POST /api/contracts/contracts/contract_1/activate
{
  "activating_agent_id": 8
}
```

**Record Performance:**
```bash
POST /api/contracts/contracts/contract_1/performance
{
  "response_time": 0.35,
  "quality_score": 0.97,
  "throughput": 850,
  "success": true,
  "metadata": {
    "model": "resnet50",
    "batch_size": 1
  }
}
```

**Check Compliance:**
```bash
GET /api/contracts/contracts/contract_1/compliance
```

**Terminate Contract:**
```bash
POST /api/contracts/contracts/contract_1/terminate
{
  "terminating_agent_id": 5,
  "reason": "Service migration to new provider",
  "immediate": false
}
```

**Renew Contract:**
```bash
POST /api/contracts/contracts/contract_1/renew
{
  "duration_hours": 720,
  "updated_terms": {
    "max_response_time": 0.4,
    "min_quality": 0.97
  }
}
```

**Get Contract:**
```bash
GET /api/contracts/contracts/contract_1
```

**List Agent Contracts:**
```bash
GET /api/contracts/agents/5/contracts?status=active&contract_type=sla
```

**Get Violations:**
```bash
GET /api/contracts/contracts/contract_1/violations?severity=high
```

**Get Statistics:**
```bash
GET /api/contracts/statistics
```

### Use Cases

**Scenario 1: Creating and Monitoring SLA**
```python
from src.services.agent_contract import AgentContract, ContractType

# Provider and consumer create SLA
contract = AgentContract.create_contract(
    session=session,
    contract_type=ContractType.SERVICE_LEVEL_AGREEMENT,
    provider_agent_id=5,
    consumer_agent_id=8,
    title="ML Model Inference SLA",
    description="SLA for real-time ML model inference service",
    sla_terms={
        "max_response_time": 0.5,  # 500ms max
        "min_quality": 0.95,        # 95% quality minimum
        "min_availability": 99.9     # 99.9% uptime
    },
    duration_hours=720,  # 30 days
    renewable=True
)

print(f"Contract created: {contract['id']}")

# Consumer activates contract
activated = AgentContract.activate_contract(
    session=session,
    contract_id=contract['id'],
    activating_agent_id=8
)

print(f"Contract activated at {activated['activated_at']}")

# Provider records each request
for i in range(100):
    AgentContract.record_performance(
        session=session,
        contract_id=contract['id'],
        response_time=0.45,
        quality_score=0.96,
        success=True
    )

# Check compliance
compliance = AgentContract.check_compliance(
    session=session,
    contract_id=contract['id']
)

print(f"Contract compliant: {compliance['is_compliant']}")
print(f"Compliance score: {compliance['compliance_score']:.2%}")
```

**Scenario 2: Handling SLA Violations**
```python
# Provider has performance degradation
for i in range(10):
    AgentContract.record_performance(
        session=session,
        contract_id=contract['id'],
        response_time=0.8,  # Exceeds 500ms SLA
        quality_score=0.92,  # Below 95% SLA
        success=True
    )

# Check for violations
violations = AgentContract.get_contract_violations(
    session=session,
    contract_id=contract['id']
)

print(f"Total violations: {violations['total_violations']}")
for violation in violations['violations']:
    print(f"  {violation['violation_type']}: expected {violation['expected']}, got {violation['actual']}")

# Get updated contract status
contract_info = AgentContract.get_contract(
    session=session,
    contract_id=contract['id']
)

if contract_info['status'] == 'breached':
    print("Contract breached due to multiple violations!")
    print(f"Performance score: {contract_info['performance_score']:.2f}")
```

**Scenario 3: Contract Renewal**
```python
# Near end of contract period, renew with improved terms
renewed = AgentContract.renew_contract(
    session=session,
    contract_id=contract['id'],
    duration_hours=1440,  # 60 days
    updated_terms={
        "max_response_time": 0.4,  # Improved to 400ms
        "min_quality": 0.97,        # Improved to 97%
        "min_availability": 99.95    # Improved to 99.95%
    }
)

print(f"Contract renewed: {renewed['id']}")
print(f"Previous contract marked as: {contract['status']}")
```

**Scenario 4: Early Termination**
```python
# Consumer terminates contract early
result = AgentContract.terminate_contract(
    session=session,
    contract_id=contract['id'],
    terminating_agent_id=8,
    reason="Migrating to in-house solution",
    immediate=False  # Apply penalties
)

print(f"Contract terminated at {result['terminated_at']}")
print(f"Penalties applied: {result['penalties_applied']}")
```

**Scenario 5: Multi-Agent Contract Management**
```python
# Agent views all their contracts
contracts = AgentContract.list_agent_contracts(
    session=session,
    agent_id=5,
    status="active"
)

print(f"Agent has {contracts['total_contracts']} active contracts")
print(f"As provider: {len(contracts['as_provider'])} contracts")
print(f"As consumer: {len(contracts['as_consumer'])} contracts")

# For each provider contract, check compliance
for contract in contracts['as_provider']:
    compliance = AgentContract.check_compliance(
        session=session,
        contract_id=contract['id']
    )

    if not compliance['is_compliant']:
        print(f"⚠️  Contract {contract['title']} has {len(compliance['violations'])} violations")

        # Take corrective action
        for violation in compliance['violations']:
            if violation['term'] == 'max_response_time':
                print(f"   Optimizing for faster response time...")
            elif violation['term'] == 'min_quality':
                print(f"   Improving quality controls...")

# Get system-wide statistics
stats = AgentContract.get_contract_statistics(session=session)
print(f"\nSystem statistics:")
print(f"Total contracts: {stats['total_contracts']}")
print(f"Average performance: {stats['average_performance_score']:.2%}")
print(f"Total violations: {stats['total_violations']}")
```

## Agent Auction System

The Agent Auction System enables efficient task and resource allocation through competitive bidding using various auction mechanisms (first-price, second-price, English, Dutch, Vickrey).

### Key Features

- **6 Auction Types**: First-price, second-price, English, Dutch, Vickrey, combinatorial
- **Automated Bidding**: Support for proxy bidding with maximum bid limits
- **Real-Time Auctions**: Live auctions with time-based expiration
- **Winner Determination**: Automatic winner selection based on auction rules
- **Reserve Prices**: Minimum acceptable prices for auctioneers
- **Bid Management**: Place, withdraw, and track bids
- **Fair Pricing**: Second-price and Vickrey auctions ensure truthful bidding
- **Auction History**: Complete record of all auctions and outcomes
- **Statistics Tracking**: Win rates, bid values, and auction analytics

### Auction Types

- **FIRST_PRICE** - Highest bidder wins and pays their bid amount
- **SECOND_PRICE** - Highest bidder wins but pays second-highest bid
- **ENGLISH** - Ascending price auction, bidders raise bids incrementally
- **DUTCH** - Descending price auction, first bidder wins at current price
- **VICKREY** - Sealed-bid second-price auction for truthful bidding
- **COMBINATORIAL** - Auction for bundles of items

### Auction Statuses

- **OPEN** - Auction created, accepting bids
- **ACTIVE** - Auction active with bids placed
- **CLOSED** - Auction ended, determining winner
- **AWARDED** - Auction completed, winner determined
- **CANCELLED** - Auction cancelled by auctioneer

### Bid Statuses

- **PENDING** - Bid active, may win auction
- **ACCEPTED** - Winning bid, accepted
- **REJECTED** - Bid rejected or lost
- **OUTBID** - Outbid by higher bid
- **WITHDRAWN** - Bid withdrawn by bidder

### REST API Endpoints

**Create Auction:**
```bash
POST /api/auctions/auctions?auctioneer_agent_id=5
{
  "auction_type": "second_price",
  "item_type": "task",
  "item_description": "High-priority data processing task",
  "reserve_price": 100.0,
  "starting_price": 50.0,
  "duration_minutes": 30,
  "item_metadata": {
    "task_complexity": "high",
    "deadline": "2024-01-15T12:00:00Z",
    "required_capabilities": ["data_processing", "machine_learning"]
  },
  "auction_rules": {
    "min_bid_increment": 5.0,
    "max_participants": 10
  }
}
```

**Place Bid:**
```bash
POST /api/auctions/auctions/auction_1/bids?bidder_agent_id=8
{
  "bid_amount": 120.0,
  "max_bid": 150.0,
  "bid_metadata": {
    "estimated_completion_time": "2h",
    "confidence": 0.95
  }
}
```

**Get Auction:**
```bash
GET /api/auctions/auctions/auction_1
```

**Close Auction:**
```bash
POST /api/auctions/auctions/auction_1/close
{
  "force_close": false
}
```

**Cancel Auction:**
```bash
POST /api/auctions/auctions/auction_1/cancel
{
  "reason": "Task no longer needed"
}
```

**Withdraw Bid:**
```bash
DELETE /api/auctions/auctions/auction_1/bids?bidder_agent_id=8
```

**List Auctions:**
```bash
GET /api/auctions/auctions?status=active&item_type=task
```

**Get Agent Bids:**
```bash
GET /api/auctions/agents/8/bids?status=accepted
```

**Get Statistics:**
```bash
GET /api/auctions/statistics
```

### Use Cases

**Scenario 1: Task Allocation via Auction**
```python
from src.services.agent_auction import AgentAuction, AuctionType

# Auctioneer creates auction for high-priority task
auction = AgentAuction.create_auction(
    session=session,
    auction_type=AuctionType.SECOND_PRICE,
    auctioneer_agent_id=1,
    item_type="task",
    item_description="Process 1M records with ML model",
    reserve_price=100.0,
    starting_price=50.0,
    duration_minutes=30,
    item_metadata={
        "complexity": "high",
        "deadline": "2024-01-15T12:00:00Z"
    }
)

print(f"Auction created: {auction['id']}")

# Multiple agents place bids
agents_bids = [
    (5, 110.0),  # Agent 5 bids $110
    (8, 125.0),  # Agent 8 bids $125
    (12, 115.0), # Agent 12 bids $115
    (8, 140.0),  # Agent 8 raises to $140
]

for agent_id, amount in agents_bids:
    bid = AgentAuction.place_bid(
        session=session,
        auction_id=auction['id'],
        bidder_agent_id=agent_id,
        bid_amount=amount
    )
    print(f"Agent {agent_id} bid ${amount}")

# Wait for auction to end or close manually
result = AgentAuction.close_auction(
    session=session,
    auction_id=auction['id']
)

print(f"Winner: Agent {result['winner_agent_id']}")
print(f"Winning price: ${result['winning_price']}")  # Pays second-highest bid!
```

**Scenario 2: Proxy Bidding**
```python
# Agent uses proxy bidding to automatically outbid others
bid = AgentAuction.place_bid(
    session=session,
    auction_id=auction['id'],
    bidder_agent_id=8,
    bid_amount=100.0,  # Initial bid
    max_bid=200.0      # Maximum willing to pay
)

# System automatically raises bid if outbid, up to max_bid
# Agent doesn't need to monitor auction constantly
```

**Scenario 3: Dutch Auction for Resources**
```python
# Create Dutch auction where price decreases over time
auction = AgentAuction.create_auction(
    session=session,
    auction_type=AuctionType.DUTCH,
    auctioneer_agent_id=5,
    item_type="resource",
    item_description="GPU cluster for 24 hours",
    starting_price=500.0,
    reserve_price=200.0,
    duration_minutes=10  # Price drops from $500 to $200 over 10 min
)

# Agents wait for acceptable price, first to bid wins
auction_details = AgentAuction.get_auction(
    session=session,
    auction_id=auction['id']
)

print(f"Current price: ${auction_details['current_price']}")

# Agent decides current price is good and bids
if auction_details['current_price'] <= 350:
    bid = AgentAuction.place_bid(
        session=session,
        auction_id=auction['id'],
        bidder_agent_id=8,
        bid_amount=auction_details['current_price']
    )
    print(f"Won at ${bid['bid_amount']}")
```

**Scenario 4: Bid Management**
```python
# Agent places bid
bid = AgentAuction.place_bid(
    session=session,
    auction_id=auction['id'],
    bidder_agent_id=8,
    bid_amount=150.0
)

# Agent checks their bidding history
agent_bids = AgentAuction.get_agent_bids(
    session=session,
    agent_id=8
)

print(f"Total bids: {agent_bids['total_bids']}")
print(f"Win rate: {agent_bids['win_rate']:.1%}")
print(f"Total spent: ${agent_bids['total_bid_amount']}")

# Agent withdraws bid before auction closes
withdrawal = AgentAuction.withdraw_bid(
    session=session,
    auction_id=auction['id'],
    bidder_agent_id=8
)

print(f"Bid withdrawn, refund: ${withdrawal['refund_amount']}")
```

**Scenario 5: Auction Analytics**
```python
# List all active auctions
auctions = AgentAuction.list_auctions(
    session=session,
    status="active",
    item_type="task"
)

print(f"Active task auctions: {auctions['total']}")

for auction in auctions['auctions']:
    details = AgentAuction.get_auction(
        session=session,
        auction_id=auction['id']
    )

    print(f"\nAuction: {auction['item_description']}")
    print(f"Current price: ${auction['current_price']}")
    print(f"Bids: {auction['bid_count']}")
    print(f"Time remaining: {details['time_remaining']['minutes']} minutes")

# Get system statistics
stats = AgentAuction.get_auction_statistics(session=session)

print(f"\nAuction System Statistics:")
print(f"Total auctions: {stats['total_auctions']}")
print(f"Total bids: {stats['total_bids']}")
print(f"Total bid value: ${stats['total_bid_value']:.2f}")
print(f"Average winning price: ${stats['average_winning_price']:.2f}")
```

## Agent Trust System

The Agent Trust System enables agents to build and maintain trust relationships, manage reputation, and verify credentials through a decentralized trust network with recommendations and verification.

### Key Features

- **Trust Relationships**: Establish bidirectional trust between agents with scores (0-1)
- **6 Trust Levels**: UNKNOWN, UNTRUSTED, LOW, MEDIUM, HIGH, VERIFIED
- **Interaction Tracking**: Automatic trust adjustment based on interaction outcomes
- **Recommendation System**: Agents vouch for others with weighted recommendations
- **Credential Verification**: Formal verification process with global trust boost
- **Trust Decay**: Trust scores decay over time without interaction
- **Global Trust Score**: Aggregate trust score from all relationships and verifications
- **Trust Networks**: Build networks of trusted agents for collaboration
- **Statistics Tracking**: Success rates, trust distributions, recommendation metrics

### Trust Levels

- **UNKNOWN** - No trust relationship established (score: 0.0)
- **UNTRUSTED** - Negative trust relationship (score: 0.0-0.3)
- **LOW** - Limited trust (score: 0.3-0.5)
- **MEDIUM** - Moderate trust (score: 0.5-0.7)
- **HIGH** - High trust (score: 0.7-0.9)
- **VERIFIED** - Verified and highly trusted (score: 0.9-1.0)

### Recommendation Types

- **POSITIVE** - Positive recommendation for an agent
- **NEUTRAL** - Neutral observation about an agent
- **NEGATIVE** - Warning about an agent

### Verification Statuses

- **UNVERIFIED** - Not yet verified
- **PENDING** - Verification requested, awaiting review
- **VERIFIED** - Successfully verified and approved
- **REJECTED** - Verification rejected

### REST API Endpoints

**Establish Trust Relationship:**
```bash
POST /api/trust/relationships?agent_a_id=5
{
  "agent_b_id": 8,
  "initial_score": 0.5,
  "trust_level": "medium",
  "metadata": {
    "reason": "Successful collaboration on previous task",
    "context": "Data processing project"
  }
}
```

**Update Trust Score:**
```bash
PUT /api/trust/relationships/5/score
{
  "agent_b_id": 8,
  "adjustment": 0.1,
  "reason": "Excellent performance on latest task"
}
```

**Record Interaction:**
```bash
POST /api/trust/relationships/5/interactions
{
  "agent_b_id": 8,
  "success": true,
  "interaction_type": "task_collaboration",
  "metadata": {
    "task_id": "task_123",
    "quality_score": 0.95
  }
}
```

**Add Recommendation:**
```bash
POST /api/trust/recommendations?recommender_agent_id=5
{
  "recommended_agent_id": 12,
  "target_agent_id": 8,
  "recommendation_type": "positive",
  "score": 0.85,
  "comment": "Highly skilled in ML tasks, reliable and fast",
  "evidence": {
    "shared_tasks": 5,
    "average_quality": 0.92
  }
}
```

**Request Verification:**
```bash
POST /api/trust/verifications?agent_id=8
{
  "verification_type": "skill_certification",
  "evidence": {
    "certifications": ["AWS ML Specialist", "Azure AI Engineer"],
    "portfolio_url": "https://agent8.example.com/portfolio",
    "completed_tasks": 150
  },
  "verifier_agent_id": 1
}
```

**Verify Agent:**
```bash
POST /api/trust/verifications/verification_1/verify?verifier_agent_id=1
{
  "approved": true,
  "verifier_notes": "Credentials verified, portfolio demonstrates expertise"
}
```

**Get Trust Score:**
```bash
GET /api/trust/relationships/5/8/score
```

**Get Trust Relationship:**
```bash
GET /api/trust/relationships/5/8
```

**Get Trusted Agents:**
```bash
GET /api/trust/agents/5/trusted?min_trust_level=high&limit=10
```

**Get Recommendations:**
```bash
GET /api/trust/recommendations/8/12
```

**Get Global Trust Score:**
```bash
GET /api/trust/agents/8/global-trust
```

**Get Statistics:**
```bash
GET /api/trust/statistics
```

### Use Cases

**Scenario 1: Building Trust Through Collaboration**
```python
from src.services.agent_trust import AgentTrust, TrustLevel

# Agent 5 and Agent 8 collaborate on a task
# Establish initial trust
relationship = AgentTrust.establish_trust(
    session=session,
    agent_a_id=5,
    agent_b_id=8,
    initial_score=0.5,  # Start with medium trust
    trust_level=TrustLevel.MEDIUM
)

print(f"Trust established: {relationship['trust_score']}")

# Record successful interaction
updated = AgentTrust.record_interaction(
    session=session,
    agent_a_id=5,
    agent_b_id=8,
    success=True,
    interaction_type="task_collaboration"
)

print(f"After success: {updated['trust_score']:.2f}")

# After multiple successful interactions, trust increases
for i in range(5):
    AgentTrust.record_interaction(
        session=session,
        agent_a_id=5,
        agent_b_id=8,
        success=True
    )

# Check new trust level
relationship = AgentTrust.get_trust_relationship(
    session=session,
    agent_a_id=5,
    agent_b_id=8
)

print(f"Trust level now: {relationship['trust_level']}")
print(f"Success rate: {relationship['success_rate']:.1%}")
```

**Scenario 2: Trust Network and Recommendations**
```python
# Agent 5 trusts Agent 8 highly
# Agent 5 recommends Agent 12 to Agent 8
recommendation = AgentTrust.add_recommendation(
    session=session,
    recommender_agent_id=5,
    recommended_agent_id=12,
    target_agent_id=8,
    recommendation_type="positive",
    score=0.85,
    comment="Excellent at data analysis, worked together on 3 projects",
    evidence={
        "shared_tasks": 3,
        "average_completion_time": "2.5 hours",
        "quality_scores": [0.9, 0.88, 0.92]
    }
)

# Agent 8 reviews recommendations for Agent 12
recs = AgentTrust.get_recommendations(
    session=session,
    target_agent_id=8,
    recommended_agent_id=12
)

print(f"Recommendations: {recs['total_recommendations']}")
print(f"Weighted score: {recs['weighted_average_score']:.2f}")

# Agent 8 decides to establish trust based on recommendation
if recs['weighted_average_score'] >= 0.7:
    AgentTrust.establish_trust(
        session=session,
        agent_a_id=8,
        agent_b_id=12,
        initial_score=recs['weighted_average_score']
    )
```

**Scenario 3: Credential Verification**
```python
from src.services.agent_trust import VerificationStatus

# Agent 12 requests verification of skills
verification = AgentTrust.request_verification(
    session=session,
    agent_id=12,
    verification_type="skill_certification",
    evidence={
        "certifications": ["Machine Learning Specialist"],
        "completed_tasks": 150,
        "average_quality_score": 0.92,
        "portfolio_url": "https://agent12.example.com"
    },
    verifier_agent_id=1  # Request Agent 1 as verifier
)

print(f"Verification requested: {verification['id']}")
print(f"Status: {verification['status']}")

# Verifier Agent 1 reviews evidence and approves
approved = AgentTrust.verify_agent(
    session=session,
    verification_id=verification['id'],
    verifier_agent_id=1,
    approved=True,
    verifier_notes="All certifications valid, portfolio demonstrates expertise"
)

print(f"Verification status: {approved['status']}")

# Check Agent 12's global trust score (should increase)
global_trust = AgentTrust.get_global_trust_score(
    session=session,
    agent_id=12
)

print(f"Global trust score: {global_trust['global_trust_score']:.2f}")
print(f"Verified: {global_trust['is_verified']}")
print(f"Verifications: {global_trust['verification_count']}")
```

**Scenario 4: Finding Trusted Collaborators**
```python
# Agent 5 needs to find highly trusted agents for sensitive task
trusted = AgentTrust.get_trusted_agents(
    session=session,
    agent_id=5,
    min_trust_level=TrustLevel.HIGH,
    limit=10
)

print(f"Found {trusted['total']} trusted agents")

for agent in trusted['trusted_agents']:
    print(f"\nAgent {agent['agent_id']}:")
    print(f"  Trust score: {agent['trust_score']:.2f}")
    print(f"  Trust level: {agent['trust_level']}")
    print(f"  Interactions: {agent['interaction_count']}")
    print(f"  Success rate: {agent['success_rate']:.1%}")

    # Check if agent is verified
    global_trust = AgentTrust.get_global_trust_score(
        session=session,
        agent_id=agent['agent_id']
    )

    if global_trust['is_verified']:
        print(f"  ✓ Verified agent")
```

**Scenario 5: Trust Decay and Maintenance**
```python
# Trust decays over time without interaction
# Get relationship after long period of inactivity
relationship = AgentTrust.get_trust_relationship(
    session=session,
    agent_a_id=5,
    agent_b_id=8
)

print(f"Current trust score: {relationship['trust_score']:.2f}")
print(f"Last interaction: {relationship['last_interaction_at']}")
print(f"Days since interaction: {relationship['days_since_interaction']}")

# Update trust score to account for decay
updated = AgentTrust.update_trust_score(
    session=session,
    agent_a_id=5,
    agent_b_id=8,
    adjustment=-0.1,
    reason="Trust decay due to inactivity"
)

print(f"Adjusted trust score: {updated['trust_score']:.2f}")

# Re-establish trust through new interaction
AgentTrust.record_interaction(
    session=session,
    agent_a_id=5,
    agent_b_id=8,
    success=True,
    interaction_type="task_collaboration"
)

print("Trust re-established through successful interaction")
```

**Scenario 6: Trust System Analytics**
```python
# Get comprehensive trust system statistics
stats = AgentTrust.get_trust_statistics(session=session)

print("Trust System Statistics:")
print(f"Total relationships: {stats['total_relationships']}")
print(f"Average trust score: {stats['average_trust_score']:.2f}")
print(f"\nTrust Score Distribution:")
for level, count in stats['trust_score_distribution'].items():
    print(f"  {level}: {count} relationships")

print(f"\nRecommendations:")
print(f"  Total: {stats['total_recommendations']}")
print(f"  Positive: {stats['recommendation_type_distribution']['positive']}")
print(f"  Negative: {stats['recommendation_type_distribution']['negative']}")

print(f"\nVerifications:")
print(f"  Total: {stats['total_verifications']}")
print(f"  Verified: {stats['verification_status_distribution']['verified']}")
print(f"  Pending: {stats['verification_status_distribution']['pending']}")
print(f"  Rejected: {stats['verification_status_distribution']['rejected']}")

print(f"\nInteraction Statistics:")
print(f"  Total interactions: {stats['total_interactions']}")
print(f"  Success rate: {stats['overall_success_rate']:.1%}")
```

## Agent Coordination Engine

The Agent Coordination Engine provides high-level orchestration workflows that integrate all multi-agent coordination mechanisms including consensus, coalitions, negotiations, trust, contracts, and auctions into unified coordination sessions.

### Key Features

- **5 Coordination Strategies**: Hierarchical, democratic, market-based, trust-based, hybrid
- **Multi-Phase Workflows**: Initiation → Coalition Formation → Negotiation → Voting → Execution
- **Integrated Mechanisms**: Combines consensus, negotiations, contracts, auctions, and trust
- **Flexible Participation**: Support for required, minimum, and maximum agent counts
- **Consensus Voting**: Built-in voting mechanisms with configurable thresholds
- **Contract Creation**: Automatic contract generation for coordinating agents
- **Outcome Tracking**: Record individual agent contributions and results
- **History and Analytics**: Complete coordination history and performance metrics
- **Dynamic Cancellation**: Allow agents to cancel coordination with reasons

### Coordination Strategies

- **HIERARCHICAL** - Top-down coordination with clear hierarchy
- **DEMOCRATIC** - Democratic coordination with voting and consensus
- **MARKET_BASED** - Market-based coordination using auctions and negotiations
- **TRUST_BASED** - Trust-based coordination using reputation and relationships
- **HYBRID** - Hybrid approach combining multiple strategies

### Coordination Statuses

- **INITIATED** - Coordination initiated, waiting for agents
- **FORMING_COALITION** - Forming coalition of agents
- **NEGOTIATING** - Negotiating terms and parameters
- **VOTING** - Voting on proposals
- **EXECUTING** - Executing coordinated plan
- **COMPLETED** - Coordination completed successfully
- **FAILED** - Coordination failed
- **CANCELLED** - Coordination cancelled

### REST API Endpoints

**Initiate Coordination:**
```bash
POST /api/coordination/sessions?initiator_agent_id=5
{
  "coordination_type": "complex_task",
  "goal_description": "Analyze large dataset and generate comprehensive report",
  "strategy": "hybrid",
  "min_agents": 3,
  "max_agents": 10,
  "constraints": {
    "deadline": "2024-01-20T12:00:00Z",
    "budget": 1000
  }
}
```

**Join Coordination:**
```bash
POST /api/coordination/sessions/coord_1/join?agent_id=8
{
  "capabilities": ["data_analysis", "visualization"],
  "commitment_level": 0.9
}
```

**Start Negotiation:**
```bash
POST /api/coordination/sessions/coord_1/negotiation
{
  "negotiation_topics": [
    {"topic": "resource_allocation", "parameters": {"cpu_hours": 100}}
  ],
  "timeout_minutes": 30
}
```

**Propose Vote:**
```bash
POST /api/coordination/sessions/coord_1/votes
{
  "proposal_id": "execution_plan_v1",
  "proposal_description": "Execute plan with parallel data processing",
  "voting_type": "majority",
  "required_threshold": 0.67
}
```

**Cast Vote:**
```bash
POST /api/coordination/sessions/coord_1/votes/execution_plan_v1/cast?agent_id=8
{
  "vote": true,
  "weight": 1.0,
  "rationale": "Plan is efficient and aligns with our capabilities"
}
```

**Start Execution:**
```bash
POST /api/coordination/sessions/coord_1/execution
{
  "execution_plan": {
    "phases": [
      {"phase": "data_collection", "assigned_agents": [5, 8]},
      {"phase": "analysis", "assigned_agents": [8, 12]}
    ]
  },
  "monitoring_interval": 300
}
```

**Complete Coordination:**
```bash
POST /api/coordination/sessions/coord_1/complete
{
  "final_result": {
    "report_url": "https://results.example.com/report_123",
    "quality_score": 0.93
  },
  "success": true
}
```

**Get Statistics:**
```bash
GET /api/coordination/statistics
```

### Use Cases

**Scenario 1: Democratic Coordination with Voting**
```python
from src.services.agent_coordination import AgentCoordination, CoordinationStrategy

# Agent 5 initiates democratic coordination
session = AgentCoordination.initiate_coordination(
    session=db_session,
    initiator_agent_id=5,
    coordination_type="decision_making",
    goal_description="Decide on system architecture for new feature",
    strategy=CoordinationStrategy.DEMOCRATIC,
    min_agents=4
)

# Other agents join
for agent_id in [8, 12, 15, 20]:
    AgentCoordination.join_coordination(
        session=db_session,
        session_id=session['id'],
        agent_id=agent_id,
        capabilities=["architecture_design"]
    )

# Propose vote on architecture choice
vote = AgentCoordination.propose_consensus_vote(
    session=db_session,
    session_id=session['id'],
    proposal_id="microservices_architecture",
    proposal_description="Adopt microservices architecture",
    voting_type="supermajority",
    required_threshold=0.75
)

# Agents cast votes
for agent_id in [5, 8, 12, 15, 20]:
    AgentCoordination.cast_vote(
        session=db_session,
        session_id=session['id'],
        proposal_id="microservices_architecture",
        agent_id=agent_id,
        vote=True
    )

print(f"Vote result: {vote['result']['consensus_reached']}")
```

**Scenario 2: Full Coordination Lifecycle**
```python
# 1. Initiate
session = AgentCoordination.initiate_coordination(
    session=db_session,
    initiator_agent_id=5,
    coordination_type="complex_project",
    goal_description="Build and deploy new microservice",
    strategy=CoordinationStrategy.HYBRID,
    min_agents=4
)

# 2. Coalition Formation
for agent_id in [8, 12, 15, 20]:
    AgentCoordination.join_coordination(
        session=db_session,
        session_id=session['id'],
        agent_id=agent_id
    )

# 3. Negotiation
AgentCoordination.start_negotiation_phase(
    session=db_session,
    session_id=session['id'],
    negotiation_topics=[
        {"topic": "timeline", "parameters": {"weeks": 4}}
    ]
)

# 4. Voting
vote = AgentCoordination.propose_consensus_vote(
    session=db_session,
    session_id=session['id'],
    proposal_id="project_plan",
    proposal_description="4-week timeline"
)

# 5. Execution
AgentCoordination.start_execution_phase(
    session=db_session,
    session_id=session['id'],
    execution_plan={
        "week_1": {"phase": "design", "agents": [5, 8]},
        "week_2_3": {"phase": "implementation", "agents": [8, 12, 15]}
    }
)

# 6. Track Outcomes
AgentCoordination.record_coordination_outcome(
    session=db_session,
    session_id=session['id'],
    agent_id=8,
    outcome_type="phase_completion",
    outcome_data={"phase": "implementation", "quality_score": 0.92},
    success=True
)

# 7. Complete
result = AgentCoordination.complete_coordination(
    session=db_session,
    session_id=session['id'],
    final_result={"microservice_deployed": True},
    success=True
)

print(f"Completed in {result['duration_seconds']/3600:.1f} hours")
```

**Scenario 3: Coordination Analytics**
```python
# Get agent's coordination history
history = AgentCoordination.get_agent_coordination_history(
    session=db_session,
    agent_id=8,
    limit=20
)

print(f"Total coordinations: {history['total_coordinations']}")
print(f"Success rate: {history['success_rate']:.1%}")

# Get system-wide statistics
stats = AgentCoordination.get_coordination_statistics(session=db_session)

print(f"\nCoordination System Statistics:")
print(f"Total sessions: {stats['total_sessions']}")
print(f"Success rate: {stats['success_rate']:.1%}")
print(f"Average duration: {stats['average_duration_seconds']/3600:.1f} hours")
print(f"Average agents: {stats['average_participating_agents']:.1f}")

print(f"\nStrategy Distribution:")
for strategy, count in stats['strategy_distribution'].items():
    print(f"  {strategy}: {count}")
```

## Project Status

✅ **Block Phase 1 Complete!** - Foundation & Infrastructure (100% complete)
✅ **Block Phase 2 Complete!** - Basic Agent Implementation (100% complete)
✅ **Block Phase 3 Complete!** - Multi-Agent Coordination (100% complete)

Current Progress: Commit 60/100 - Agent Coordination Engine Complete

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
