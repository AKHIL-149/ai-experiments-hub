# Workflow API Usage Guide

Complete guide to using the Multi-Agent Task Orchestrator API for workflow management and execution.

## Table of Contents

- [Quick Start](#quick-start)
- [Authentication](#authentication)
- [Core Endpoints](#core-endpoints)
- [Creating Workflows](#creating-workflows)
- [Executing Workflows](#executing-workflows)
- [Monitoring Workflows](#monitoring-workflows)
- [Advanced Features](#advanced-features)
- [Code Examples](#code-examples)

---

## Quick Start

### 1. Start the Server

```bash
python3 server.py
# Server runs on http://localhost:8001
```

### 2. Verify Server is Running

```bash
curl http://localhost:8001/api/health
```

Expected response:
```json
{
    "status": "healthy",
    "timestamp": "2026-07-14T...",
    "service": "multi-agent-orchestrator"
}
```

### 3. Run Your First Workflow

```bash
# Submit a simple task
curl -X POST http://localhost:8001/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Analyze Sales Data",
    "description": "Perform statistical analysis on Q4 sales data",
    "task_type": "data_analysis",
    "priority": 5
  }'
```

---

## Authentication

### Create a User Account

```bash
curl -X POST http://localhost:8001/api/auth/signup \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "username": "developer",
    "password": "SecurePassword123!"
  }'
```

### Login and Get Token

```bash
curl -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "SecurePassword123!"
  }'
```

Response:
```json
{
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "token_type": "bearer",
    "expires_in": 3600
}
```

### Use Token in Requests

```bash
TOKEN="your_access_token_here"

curl -X GET http://localhost:8001/api/tasks \
  -H "Authorization: Bearer $TOKEN"
```

---

## Core Endpoints

### Workflow Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/workflow-engine/workflows` | Create new workflow |
| `GET` | `/api/workflow-engine/workflows` | List all workflows |
| `GET` | `/api/workflow-engine/workflows/{id}` | Get workflow details |
| `POST` | `/api/workflow-engine/workflows/{id}/execute` | Execute workflow |
| `GET` | `/api/workflow-engine/workflows/{id}/status` | Get execution status |
| `POST` | `/api/workflow-engine/workflows/{id}/pause` | Pause execution |
| `POST` | `/api/workflow-engine/workflows/{id}/resume` | Resume execution |
| `DELETE` | `/api/workflow-engine/workflows/{id}` | Delete workflow |

### Task Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/tasks` | Create task |
| `GET` | `/api/tasks` | List tasks |
| `GET` | `/api/tasks/{id}` | Get task details |
| `PATCH` | `/api/tasks/{id}` | Update task |
| `DELETE` | `/api/tasks/{id}` | Delete task |

### Agent Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/agents` | List all agents |
| `GET` | `/api/agents/{id}` | Get agent details |
| `GET` | `/api/agents/{id}/performance` | Agent performance metrics |

---

## Creating Workflows

### Basic Workflow Creation

```bash
curl -X POST http://localhost:8001/api/workflow-engine/workflows \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "Code Review Workflow",
    "description": "Automated code quality review",
    "workflow_type": "custom",
    "steps": [
      {
        "step_name": "analyze_code",
        "step_type": "agent",
        "agent_role": "code",
        "config": {
          "task": "Analyze code quality and best practices"
        },
        "dependencies": []
      },
      {
        "step_name": "generate_report",
        "step_type": "agent",
        "agent_role": "writer",
        "config": {
          "task": "Create comprehensive review report"
        },
        "dependencies": ["analyze_code"]
      }
    ],
    "metadata": {
      "category": "code_quality",
      "tags": ["review", "quality"]
    }
  }'
```

Response:
```json
{
    "workflow_id": 123,
    "name": "Code Review Workflow",
    "status": "pending",
    "created_at": "2026-07-14T...",
    "total_steps": 2
}
```

### Using Workflow Templates

```python
# Python example using template
import requests
from examples.workflows.code_review_workflow import create_code_review_workflow

# Get workflow template
workflow_config = create_code_review_workflow()

# Submit to API
response = requests.post(
    "http://localhost:8001/api/workflow-engine/workflows",
    json=workflow_config,
    headers={"Authorization": f"Bearer {token}"}
)

workflow_id = response.json()["workflow_id"]
print(f"Workflow created: {workflow_id}")
```

---

## Executing Workflows

### Start Workflow Execution

```bash
curl -X POST http://localhost:8001/api/workflow-engine/workflows/123/execute \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "input_data": {
      "file_path": "/path/to/code.py",
      "options": {
        "check_security": true,
        "check_performance": true
      }
    }
  }'
```

Response:
```json
{
    "execution_id": 456,
    "workflow_id": 123,
    "status": "running",
    "started_at": "2026-07-14T...",
    "current_step": "analyze_code"
}
```

### With Custom Parameters

```bash
curl -X POST http://localhost:8001/api/workflow-engine/workflows/123/execute \
  -H "Content-Type: application/json" \
  -d '{
    "input_data": {
      "code": "def hello(): print(\"world\")",
      "language": "python"
    },
    "priority": 8,
    "timeout_minutes": 30,
    "notification_email": "dev@example.com"
  }'
```

---

## Monitoring Workflows

### Get Workflow Status

```bash
curl http://localhost:8001/api/workflow-engine/workflows/123/status
```

Response:
```json
{
    "workflow_id": 123,
    "status": "running",
    "progress_percent": 50,
    "current_step": "generate_report",
    "steps_completed": 1,
    "steps_total": 2,
    "started_at": "2026-07-14T10:00:00",
    "estimated_completion": "2026-07-14T10:15:00"
}
```

### Get Step Details

```bash
curl http://localhost:8001/api/workflow-engine/workflows/123/steps
```

Response:
```json
{
    "workflow_id": 123,
    "steps": [
        {
            "step_id": 1,
            "step_name": "analyze_code",
            "status": "completed",
            "agent_role": "code",
            "started_at": "2026-07-14T10:00:00",
            "completed_at": "2026-07-14T10:07:30",
            "duration_seconds": 450,
            "result": {
                "quality_score": 85,
                "issues_found": 3,
                "recommendations": [...]
            }
        },
        {
            "step_id": 2,
            "step_name": "generate_report",
            "status": "running",
            "agent_role": "writer",
            "started_at": "2026-07-14T10:07:31",
            "progress_percent": 45
        }
    ]
}
```

### WebSocket Monitoring

```javascript
// JavaScript WebSocket client
const ws = new WebSocket('ws://localhost:8001/ws/workflows/123');

ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    console.log('Status update:', update);

    if (update.status === 'completed') {
        console.log('Workflow completed!');
        console.log('Results:', update.result);
    }
};

ws.onerror = (error) => {
    console.error('WebSocket error:', error);
};
```

### Python WebSocket Client

```python
import asyncio
import websockets
import json

async def monitor_workflow(workflow_id):
    uri = f"ws://localhost:8001/ws/workflows/{workflow_id}"

    async with websockets.connect(uri) as websocket:
        print(f"Connected to workflow {workflow_id}")

        async for message in websocket:
            update = json.loads(message)
            print(f"Update: {update['status']} - {update.get('current_step')}")

            if update['status'] in ['completed', 'failed', 'cancelled']:
                print(f"Final status: {update['status']}")
                break

# Run
asyncio.run(monitor_workflow(123))
```

---

## Advanced Features

### Parallel Step Execution

```json
{
    "steps": [
        {
            "step_name": "prepare_data",
            "dependencies": []
        },
        {
            "step_name": "analyze_quality",
            "dependencies": ["prepare_data"]
        },
        {
            "step_name": "analyze_security",
            "dependencies": ["prepare_data"]
        },
        {
            "step_name": "analyze_performance",
            "dependencies": ["prepare_data"]
        },
        {
            "step_name": "compile_results",
            "dependencies": ["analyze_quality", "analyze_security", "analyze_performance"]
        }
    ]
}
```

Steps `analyze_quality`, `analyze_security`, and `analyze_performance` run in parallel after `prepare_data` completes.

### Human Approval Gates

```json
{
    "step_name": "human_review",
    "step_type": "approval_gate",
    "config": {
        "approval_type": "review_required",
        "timeout_hours": 24,
        "reviewers": ["lead@example.com"],
        "auto_approve_after_timeout": false
    },
    "dependencies": ["generate_report"]
}
```

### Conditional Execution (Coming Soon)

```json
{
    "step_name": "deploy_code",
    "step_type": "conditional",
    "config": {
        "condition": "quality_score >= 90",
        "on_true": "deploy_to_production",
        "on_false": "notify_team"
    },
    "dependencies": ["code_review"]
}
```

### Workflow Scheduling

```bash
# Schedule workflow to run daily at 9 AM
curl -X POST http://localhost:8001/api/scheduler/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": 123,
    "schedule": "cron",
    "cron_expression": "0 9 * * *",
    "timezone": "America/New_York",
    "enabled": true
  }'
```

---

## Code Examples

### Complete Python Example

```python
#!/usr/bin/env python3
"""
Complete workflow execution example
"""

import requests
import time
from datetime import datetime

# Configuration
API_BASE = "http://localhost:8001/api"
EMAIL = "user@example.com"
PASSWORD = "your_password"

def login():
    """Authenticate and get token"""
    response = requests.post(
        f"{API_BASE}/auth/login",
        json={"email": EMAIL, "password": PASSWORD}
    )
    return response.json()["access_token"]

def create_workflow(token):
    """Create a new workflow"""
    workflow_config = {
        "name": "Data Analysis Workflow",
        "description": "Analyze sales data and generate report",
        "workflow_type": "custom",
        "steps": [
            {
                "step_name": "validate_data",
                "step_type": "agent",
                "agent_role": "data_analyst",
                "config": {
                    "task": "Validate data quality"
                },
                "dependencies": []
            },
            {
                "step_name": "analyze_trends",
                "step_type": "agent",
                "agent_role": "data_analyst",
                "config": {
                    "task": "Identify trends and patterns"
                },
                "dependencies": ["validate_data"]
            },
            {
                "step_name": "create_report",
                "step_type": "agent",
                "agent_role": "writer",
                "config": {
                    "task": "Generate comprehensive report"
                },
                "dependencies": ["analyze_trends"]
            }
        ]
    }

    response = requests.post(
        f"{API_BASE}/workflow-engine/workflows",
        json=workflow_config,
        headers={"Authorization": f"Bearer {token}"}
    )
    return response.json()["workflow_id"]

def execute_workflow(token, workflow_id, data_path):
    """Execute the workflow"""
    response = requests.post(
        f"{API_BASE}/workflow-engine/workflows/{workflow_id}/execute",
        json={
            "input_data": {
                "file_path": data_path,
                "format": "csv"
            }
        },
        headers={"Authorization": f"Bearer {token}"}
    )
    return response.json()["execution_id"]

def monitor_workflow(token, workflow_id):
    """Monitor workflow execution"""
    print(f"Monitoring workflow {workflow_id}...")

    while True:
        response = requests.get(
            f"{API_BASE}/workflow-engine/workflows/{workflow_id}/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        status = response.json()

        print(f"[{datetime.now().strftime('%H:%M:%S')}] "
              f"Status: {status['status']} | "
              f"Progress: {status['progress_percent']}% | "
              f"Step: {status.get('current_step', 'N/A')}")

        if status['status'] in ['completed', 'failed', 'cancelled']:
            return status

        time.sleep(5)  # Poll every 5 seconds

def main():
    # Login
    print("Logging in...")
    token = login()
    print("✅ Authenticated")

    # Create workflow
    print("\nCreating workflow...")
    workflow_id = create_workflow(token)
    print(f"✅ Workflow created: {workflow_id}")

    # Execute workflow
    print("\nExecuting workflow...")
    execution_id = execute_workflow(token, workflow_id, "/path/to/sales_data.csv")
    print(f"✅ Execution started: {execution_id}")

    # Monitor execution
    print("\nMonitoring execution...")
    final_status = monitor_workflow(token, workflow_id)

    # Display results
    print(f"\n{'='*60}")
    print(f"Workflow {workflow_id} {final_status['status'].upper()}")
    print(f"Duration: {final_status.get('duration_seconds', 0)} seconds")

    if final_status['status'] == 'completed':
        print("\n✅ Results:")
        # Fetch detailed results
        response = requests.get(
            f"{API_BASE}/workflow-engine/workflows/{workflow_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        results = response.json()
        print(results.get('result', 'No results available'))
    else:
        print(f"\n❌ Error: {final_status.get('error_message', 'Unknown error')}")

if __name__ == "__main__":
    main()
```

### Batch Workflow Execution

```python
import asyncio
import aiohttp

async def execute_workflows_parallel(token, workflow_configs):
    """Execute multiple workflows in parallel"""
    async with aiohttp.ClientSession() as session:
        tasks = []

        for config in workflow_configs:
            task = execute_single_workflow(session, token, config)
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        return results

async def execute_single_workflow(session, token, config):
    """Execute a single workflow"""
    headers = {"Authorization": f"Bearer {token}"}

    # Create workflow
    async with session.post(
        f"{API_BASE}/workflow-engine/workflows",
        json=config,
        headers=headers
    ) as response:
        workflow = await response.json()
        workflow_id = workflow["workflow_id"]

    # Execute workflow
    async with session.post(
        f"{API_BASE}/workflow-engine/workflows/{workflow_id}/execute",
        headers=headers
    ) as response:
        execution = await response.json()

    return {
        "workflow_id": workflow_id,
        "execution_id": execution["execution_id"],
        "name": config["name"]
    }

# Usage
# results = asyncio.run(execute_workflows_parallel(token, [config1, config2, config3]))
```

---

## Error Handling

### Common Errors

| Status Code | Meaning | Solution |
|-------------|---------|----------|
| 400 | Bad Request | Check request payload format |
| 401 | Unauthorized | Verify authentication token |
| 404 | Not Found | Check workflow/task ID |
| 429 | Too Many Requests | Implement rate limiting/backoff |
| 500 | Server Error | Check server logs, report bug |

### Retry Logic

```python
import time
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

def create_session_with_retries():
    """Create session with automatic retries"""
    session = requests.Session()

    retry = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"]
    )

    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    return session

# Usage
session = create_session_with_retries()
response = session.post(API_BASE + "/workflow-engine/workflows", json=config)
```

---

## Performance Tips

1. **Use Parallel Steps**: Define independent steps to run in parallel
2. **Optimize Agent Selection**: Choose the right agent for each task
3. **Set Timeouts**: Prevent workflows from running indefinitely
4. **Batch Operations**: Execute multiple workflows when possible
5. **Monitor Resource Usage**: Check agent performance metrics
6. **Cache Results**: Reuse common research/analysis results

---

## Next Steps

- Explore example workflows in `examples/workflows/`
- Run the interactive helper: `python examples/run_workflow.py --list`
- Check API documentation: http://localhost:8001/docs
- Review monitoring guide in [STARTUP.md](../STARTUP.md)

