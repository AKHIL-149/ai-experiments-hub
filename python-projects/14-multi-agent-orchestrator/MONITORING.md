# Monitoring Dashboard

The Multi-Agent Orchestrator includes a comprehensive monitoring system for tracking system health, agent performance, and task execution metrics.

## Features

### Real-time Metrics
- **Task Statistics**: Track task counts by status, priority, and time range
- **Agent Performance**: Monitor agent execution success rates and response times
- **Workflow Status**: View workflow execution metrics and completion rates
- **System Health**: Real-time health checks with issue detection

### Dashboard UI
Access the interactive web dashboard at:
```
http://localhost:8001/dashboard
```

The dashboard provides:
- Auto-refreshing metrics (every 30 seconds)
- Visual cards showing key performance indicators
- Agent performance leaderboard
- System health status with warnings
- Time-range selectors (24h, 7d, 30d)

## API Endpoints

All monitoring endpoints are available at `/api/monitoring/`:

### 1. Dashboard Overview
```bash
GET /api/monitoring/dashboard
```

Returns high-level overview including:
- Total tasks, agents, executions, workflows
- Task counts by status (pending, running, completed, failed)
- Agent availability (active, busy, idle, offline)
- Success rates for tasks and executions

**Example Response**:
```json
{
  "overview": {
    "total_tasks": 150,
    "total_agents": 5,
    "total_executions": 287,
    "total_workflows": 23,
    "tasks_24h": 42
  },
  "tasks": {
    "pending": 12,
    "running": 8,
    "completed": 125,
    "failed": 5,
    "success_rate": 96.15
  },
  "agents": {
    "active": 3,
    "busy": 2,
    "idle": 0,
    "offline": 0
  },
  "executions": {
    "running": 8,
    "completed": 270,
    "failed": 9,
    "success_rate": 94.06
  },
  "workflows": {
    "total": 23,
    "running": 2,
    "completed": 20
  },
  "timestamp": "2026-07-14T12:00:00"
}
```

### 2. Task Metrics
```bash
GET /api/monitoring/tasks?time_range=24h
```

Query parameters:
- `time_range`: "24h" | "7d" | "30d" (default: "24h")

Returns:
- Task counts by status in time range
- Task counts by priority
- Average task duration

**Example Response**:
```json
{
  "time_range": "24h",
  "start_time": "2026-07-13T12:00:00",
  "end_time": "2026-07-14T12:00:00",
  "by_status": {
    "COMPLETED": 35,
    "RUNNING": 5,
    "PENDING": 2,
    "FAILED": 0
  },
  "by_priority": {
    "HIGH": 15,
    "NORMAL": 20,
    "LOW": 7
  },
  "average_duration_seconds": 45.32,
  "timestamp": "2026-07-14T12:00:00"
}
```

### 3. Agent Performance
```bash
GET /api/monitoring/agents
```

Returns performance metrics for each agent:
- Execution counts (total, completed, failed)
- Success rates
- Average execution duration
- Current status
- Capabilities

**Example Response**:
```json
[
  {
    "agent_id": 1,
    "agent_name": "Research Agent",
    "agent_role": "RESEARCH",
    "status": "ACTIVE",
    "total_executions": 87,
    "completed_executions": 84,
    "failed_executions": 3,
    "success_rate": 96.55,
    "average_duration_seconds": 23.45,
    "capabilities": ["research", "web_search", "data_analysis"],
    "last_active": "2026-07-14T11:58:00"
  },
  {
    "agent_id": 2,
    "agent_name": "Code Agent",
    "agent_role": "CODE",
    "status": "BUSY",
    "total_executions": 120,
    "completed_executions": 115,
    "failed_executions": 5,
    "success_rate": 95.83,
    "average_duration_seconds": 67.89,
    "capabilities": ["code_generation", "code_review", "debugging"],
    "last_active": "2026-07-14T12:00:00"
  }
]
```

### 4. Workflow Metrics
```bash
GET /api/monitoring/workflows
```

Returns:
- Workflow counts by status
- Workflow counts by type
- Average workflow duration
- Recent workflow executions (last 10)

**Example Response**:
```json
{
  "by_status": {
    "COMPLETED": 18,
    "RUNNING": 2,
    "FAILED": 3
  },
  "by_type": {
    "SIMPLE": 10,
    "DAG": 8,
    "CUSTOM": 5
  },
  "average_duration_seconds": 156.78,
  "recent_workflows": [
    {
      "id": 23,
      "name": "Code Review Workflow",
      "type": "DAG",
      "status": "RUNNING",
      "created_at": "2026-07-14T11:45:00",
      "completed_at": null
    }
  ],
  "timestamp": "2026-07-14T12:00:00"
}
```

### 5. System Health
```bash
GET /api/monitoring/health
```

Returns overall system health status with issue detection:
- Health status: "healthy", "warning", or "critical"
- List of detected issues
- Key health metrics

**Example Response**:
```json
{
  "status": "healthy",
  "issues": [],
  "metrics": {
    "stuck_tasks": 0,
    "failed_tasks_1h": 1,
    "total_agents": 5,
    "active_agents": 5,
    "agent_availability_percent": 100.0
  },
  "timestamp": "2026-07-14T12:00:00"
}
```

**Warning Status Example**:
```json
{
  "status": "warning",
  "issues": [
    "2 tasks running for over 1 hour",
    "8 tasks failed in last hour"
  ],
  "metrics": {
    "stuck_tasks": 2,
    "failed_tasks_1h": 8,
    "total_agents": 5,
    "active_agents": 4,
    "agent_availability_percent": 80.0
  },
  "timestamp": "2026-07-14T12:00:00"
}
```

## Usage Examples

### Python Example
```python
import requests

# Get dashboard overview
response = requests.get("http://localhost:8001/api/monitoring/dashboard")
data = response.json()

print(f"Total Tasks: {data['overview']['total_tasks']}")
print(f"Task Success Rate: {data['tasks']['success_rate']}%")
print(f"Active Agents: {data['agents']['active']}")

# Get agent performance
agents = requests.get("http://localhost:8001/api/monitoring/agents").json()
for agent in agents:
    print(f"{agent['agent_name']}: {agent['success_rate']}% success rate")
```

### curl Examples
```bash
# Dashboard overview
curl http://localhost:8001/api/monitoring/dashboard

# Task metrics for last 7 days
curl "http://localhost:8001/api/monitoring/tasks?time_range=7d"

# Agent performance
curl http://localhost:8001/api/monitoring/agents

# System health check
curl http://localhost:8001/api/monitoring/health
```

### JavaScript Example
```javascript
// Fetch dashboard data
async function loadMetrics() {
  const response = await fetch('/api/monitoring/dashboard');
  const data = await response.json();

  console.log('Overview:', data.overview);
  console.log('Task Success Rate:', data.tasks.success_rate);
  console.log('Active Agents:', data.agents.active);
}

// Auto-refresh every 30 seconds
setInterval(loadMetrics, 30000);
```

## Monitoring Service

The monitoring functionality is implemented in the `MonitoringService` class:

```python
from src.services.monitoring_service import MonitoringService
from src.core.database import get_db

# Create service instance
service = MonitoringService()

# Get metrics
with get_db() as db:
    overview = service.get_dashboard_overview(db)
    agent_perf = service.get_agent_performance(db)
    health = service.get_system_health(db)
```

## Health Status Conditions

The system health endpoint uses the following rules:

### Healthy
- No tasks stuck for over 1 hour
- Fewer than 5 failed tasks in last hour
- At least 50% of agents available

### Warning
- 1+ tasks running for over 1 hour
- 5+ failed tasks in last hour

### Critical
- Less than 50% agent availability
- Critical system errors detected

## Integration with Alerts

You can integrate monitoring with alerting systems:

```python
import requests
import time

def check_health():
    response = requests.get("http://localhost:8001/api/monitoring/health")
    health = response.json()

    if health['status'] == 'critical':
        send_alert(f"CRITICAL: {', '.join(health['issues'])}")
    elif health['status'] == 'warning':
        send_warning(f"WARNING: {', '.join(health['issues'])}")

# Run health check every 5 minutes
while True:
    check_health()
    time.sleep(300)
```

## Performance Considerations

- Metrics are calculated on-demand from database
- Dashboard auto-refreshes every 30 seconds
- For high-load systems, consider:
  - Caching metric results (Redis)
  - Pre-aggregating metrics in background jobs
  - Using read replicas for metric queries

## Troubleshooting

### Dashboard Not Loading
1. Check server is running: `curl http://localhost:8001/api/health`
2. Check monitoring endpoints: `curl http://localhost:8001/api/monitoring/dashboard`
3. Check browser console for JavaScript errors

### Metrics Showing Zero
1. Ensure tasks have been created and executed
2. Check database connection: `psql -U postgres -d multi_agent_orchestrator -c "SELECT COUNT(*) FROM tasks;"`
3. Verify agents are registered: `curl http://localhost:8001/api/agents`

### Slow Dashboard Performance
1. Check database query performance
2. Add indexes on frequently queried columns:
   ```sql
   CREATE INDEX idx_tasks_status_created ON tasks(status, created_at);
   CREATE INDEX idx_executions_agent_status ON agent_executions(agent_id, status);
   ```
3. Consider implementing metric caching

## Next Steps

1. **Set up alerting**: Integrate with PagerDuty, Slack, or email
2. **Export metrics**: Send to Prometheus, Datadog, or CloudWatch
3. **Custom dashboards**: Build domain-specific monitoring views
4. **Historical analysis**: Store aggregated metrics for trend analysis
5. **SLA tracking**: Monitor against defined service level objectives

## Related Documentation

- [API Usage Guide](API_USAGE.md)
- [Health Check Endpoint](STARTUP.md#verify-server-is-running)
- [Agent Management](API_USAGE.md#agent-management)
- [Task Orchestration](API_USAGE.md#task-orchestration)
