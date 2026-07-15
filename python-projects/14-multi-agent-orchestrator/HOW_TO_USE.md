# How to Use Multi-Agent Task Orchestrator

**Quick Start Guide** - Get up and running in 2 minutes! 🚀

---

## ✅ Prerequisites (Already Done!)

You already have:
- ✅ Python 3.9+ installed
- ✅ Virtual environment created (`venv/`)
- ✅ Dependencies installed
- ✅ Database configured (SQLite)
- ✅ Server running on port 8001

---

## 🚀 Quick Start: Run the Demo

### Option 1: Database Workflow Demo (Recommended - Works Now!)

This creates sample data and shows you the system in action:

```bash
# Run the demo
python3 demo_database_workflow.py
```

**What This Does**:
1. Creates 3 AI agents (CodeReviewer, DataAnalyst, DocWriter)
2. Creates 5 sample tasks with different statuses
3. Creates an execution record
4. Shows you the database contents
5. Verifies monitoring APIs work with real data

**Expected Output**:
```
✅ Created 3 agents
✅ Created 5 tasks
✅ Created 1 execution record

📊 Dashboard Overview:
   Total Tasks: 5
   Total Agents: 3
   Total Executions: 1

🏥 System Health: HEALTHY
```

### Option 2: View the Web Dashboard

```bash
# Open dashboard in your browser
open http://localhost:8001/dashboard
```

You'll see:
- 📊 Task metrics (pending, running, completed, failed)
- 🤖 Agent status (active, busy, idle)
- 📈 Execution statistics
- ✅ System health indicators

### Option 3: Explore API Documentation

```bash
# Open interactive API docs
open http://localhost:8001/docs
```

This gives you:
- Full API reference
- Try-it-out functionality
- Request/response examples
- Schema definitions

---

## 📊 Verify Everything Works

### Quick Health Check

```bash
# Check server health
curl http://localhost:8001/api/health

# Check monitoring
curl http://localhost:8001/api/monitoring/health | python3 -m json.tool
```

**Expected**:
```json
{
  "status": "healthy",
  "issues": [],
  "metrics": {
    "stuck_tasks": 0,
    "failed_tasks_1h": 1,
    "total_agents": 3,
    "active_agents": 3,
    "agent_availability_percent": 100.0
  }
}
```

### View Dashboard Metrics

```bash
curl http://localhost:8001/api/monitoring/dashboard | python3 -m json.tool
```

---

## 🎯 Common Use Cases

### 1. View All Tasks in Database

```python
# Start Python
python3

# Then run:
from src.core.database import SessionLocal
from src.models.task import Task

db = SessionLocal()
tasks = db.query(Task).all()

for task in tasks:
    print(f"[{task.id}] {task.title} - Status: {task.status.value}")

db.close()
```

### 2. View All Agents

```python
from src.core.database import SessionLocal
from src.models.agent import Agent

db = SessionLocal()
agents = db.query(Agent).all()

for agent in agents:
    print(f"[{agent.id}] {agent.name} ({agent.role.value}) - Status: {agent.status.value}")

db.close()
```

### 3. Create a New Task (Programmatically)

```python
from src.core.database import SessionLocal
from src.models.task import Task, TaskStatus
from datetime import datetime

db = SessionLocal()

new_task = Task(
    title="My Custom Task",
    description="This is a custom task I created",
    task_type="custom",
    priority=5,
    status=TaskStatus.PENDING,
    input_data={"key": "value"}
)

db.add(new_task)
db.commit()

print(f"✅ Created task with ID: {new_task.id}")
db.close()
```

### 4. Monitor System in Real-Time

```bash
# Watch dashboard metrics update every 2 seconds
watch -n 2 'curl -s http://localhost:8001/api/monitoring/dashboard | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(\"📊 Real-time Metrics\")
print(\"=\"*50)
print(f\"Total Tasks: {d[\"overview\"][\"total_tasks\"]}\")
print(f\"Pending: {d[\"tasks\"][\"pending\"]}\")
print(f\"Running: {d[\"tasks\"][\"running\"]}\")
print(f\"Completed: {d[\"tasks\"][\"completed\"]}\")
print(f\"Failed: {d[\"tasks\"][\"failed\"]}\")
print(f\"Agents: {d[\"overview\"][\"total_agents\"]}\")
"'
```

---

## 📖 Learn More

### Step-by-Step Examples

See [QUICK_WORKFLOW_DEMO.md](QUICK_WORKFLOW_DEMO.md) for:
- ✅ 6 different methods to execute workflows
- ✅ Simple API calls with curl
- ✅ Python script examples
- ✅ Interactive Python sessions
- ✅ Bulk task creation
- ✅ Full workflow demonstrations

### System Architecture

See [README.md](README.md) for:
- System architecture overview
- Feature list
- Technology stack
- Agent capabilities

### API Reference

See [API_USAGE.md](API_USAGE.md) for:
- Complete endpoint documentation
- Request/response examples
- Authentication
- Error handling

### Monitoring Features

See [MONITORING.md](MONITORING.md) for:
- Dashboard features
- Metrics collection
- Health checks
- Performance monitoring

### Cloud Deployment

See [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md) for:
- AWS deployment guide
- Google Cloud deployment
- Azure deployment
- Heroku, Render, Railway
- Cost comparisons

---

## 🔥 What You Can Do Right Now

### 1. Run the Demo (1 minute)
```bash
python3 demo_database_workflow.py
```

### 2. View the Dashboard (1 click)
http://localhost:8001/dashboard

### 3. Explore the API (1 click)
http://localhost:8001/docs

### 4. Check System Health
```bash
curl http://localhost:8001/api/monitoring/health | python3 -m json.tool
```

### 5. Create Your Own Task
```python
# See example in "Create a New Task" above
python3
>>> [paste the code example]
```

---

## 🎓 Next Steps

Once you're comfortable with the basics:

1. **Customize the Demo**:
   - Modify `demo_database_workflow.py`
   - Add your own task types
   - Create custom agents

2. **Build a Workflow**:
   - Design multi-step workflows
   - Chain tasks together
   - Implement task dependencies

3. **Deploy to Production**:
   - Choose a cloud platform
   - Follow [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md)
   - Configure PostgreSQL database
   - Set up monitoring

4. **Integrate with Your App**:
   - Use the REST API
   - Implement webhooks
   - Build custom UI

---

## 🆘 Troubleshooting

### Server Not Running?

```bash
# Check if server is running
curl http://localhost:8001/api/health

# If not, start it:
python3 server.py
```

### Database Issues?

```bash
# Check database file exists
ls -la data/orchestrator.db

# Re-run migrations if needed
./migrate.sh upgrade
```

### Import Errors?

```bash
# Make sure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies if needed
pip install -r requirements.txt
```

---

## 📞 Quick Reference

| What | Where |
|------|-------|
| **Dashboard** | http://localhost:8001/dashboard |
| **API Docs** | http://localhost:8001/docs |
| **Health Check** | http://localhost:8001/api/health |
| **Monitoring API** | http://localhost:8001/api/monitoring/* |
| **Run Demo** | `python3 demo_database_workflow.py` |
| **Database** | `./data/orchestrator.db` |
| **Server Logs** | `/tmp/server.log` |

---

## 🎉 You're All Set!

The Multi-Agent Task Orchestrator is ready to use. Start with:

```bash
python3 demo_database_workflow.py
```

Then explore the dashboard at:
**http://localhost:8001/dashboard**

Happy orchestrating! 🚀

---

**Questions?**
- Check [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md) for system status
- Check [SESSION_SUMMARY_14.9.md](SESSION_SUMMARY_14.9.md) for recent changes
- Check [COMPLETION_REPORT.md](COMPLETION_REPORT.md) for full feature list
