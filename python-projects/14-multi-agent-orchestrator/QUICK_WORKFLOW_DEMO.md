# Quick Workflow Demo - Simple Examples

**Goal**: Execute your first workflow and see the system in action!

---

## 🚀 Method 1: Simple API Task Execution (Easiest)

### Step 1: Create a Simple Task

```bash
# Create a simple task via API
curl -X POST http://localhost:8001/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Hello World Task",
    "description": "My first test task",
    "task_type": "simple",
    "priority": 5
  }'
```

**Expected Response**:
```json
{
  "id": 1,
  "title": "Hello World Task",
  "status": "PENDING",
  "created_at": "2026-07-15T..."
}
```

### Step 2: Check Task Status

```bash
# Get task by ID
curl http://localhost:8001/api/tasks/1 | python3 -m json.tool
```

### Step 3: View in Monitoring Dashboard

```bash
# Open dashboard in browser
open http://localhost:8001/dashboard

# Or check via API
curl http://localhost:8001/api/monitoring/dashboard | python3 -m json.tool
```

You should now see **1 task** in the dashboard metrics! 📊

---

## 🧪 Method 2: Python Script Workflow Test

Create a simple Python script to test the workflow:

### Create Test Script

```python
# test_workflow.py
import requests
import json
import time

BASE_URL = "http://localhost:8001"

def create_task(title, description, task_type="test"):
    """Create a new task"""
    response = requests.post(
        f"{BASE_URL}/api/tasks",
        json={
            "title": title,
            "description": description,
            "task_type": task_type,
            "priority": 5,
            "input_data": {
                "test": True,
                "timestamp": time.time()
            }
        }
    )
    return response.json()

def get_task(task_id):
    """Get task details"""
    response = requests.get(f"{BASE_URL}/api/tasks/{task_id}")
    return response.json()

def get_dashboard():
    """Get dashboard metrics"""
    response = requests.get(f"{BASE_URL}/api/monitoring/dashboard")
    return response.json()

if __name__ == "__main__":
    print("🚀 Starting Workflow Test\n")

    # Create a task
    print("1. Creating test task...")
    task = create_task(
        "Code Review Task",
        "Review Python code for best practices"
    )
    task_id = task.get('id')
    print(f"   ✅ Task created with ID: {task_id}\n")

    # Get task details
    print("2. Retrieving task details...")
    task_details = get_task(task_id)
    print(f"   Status: {task_details.get('status')}")
    print(f"   Title: {task_details.get('title')}\n")

    # Check dashboard
    print("3. Checking dashboard metrics...")
    dashboard = get_dashboard()
    print(f"   Total tasks: {dashboard['overview']['total_tasks']}")
    print(f"   Pending tasks: {dashboard['tasks']['pending']}\n")

    print("✅ Workflow test complete!")
    print(f"\n📊 View dashboard: {BASE_URL}/dashboard")
```

### Run the Test

```bash
# Create the test file
cat > test_workflow.py << 'EOF'
[paste the script above]
EOF

# Install requests if needed
pip install requests

# Run the test
python3 test_workflow.py
```

**Expected Output**:
```
🚀 Starting Workflow Test

1. Creating test task...
   ✅ Task created with ID: 1

2. Retrieving task details...
   Status: PENDING
   Title: Code Review Task

3. Checking dashboard metrics...
   Total tasks: 1
   Pending tasks: 1

✅ Workflow test complete!

📊 View dashboard: http://localhost:8001/dashboard
```

---

## 🎯 Method 3: Interactive Python Session

```python
# Start Python interactive session
python3

# Then run this:
import requests
import json

BASE_URL = "http://localhost:8001"

# Create task
task = requests.post(f"{BASE_URL}/api/tasks", json={
    "title": "My First Task",
    "description": "Testing the system",
    "task_type": "test",
    "priority": 5
}).json()

print(f"Created task ID: {task['id']}")

# Get task
task_details = requests.get(f"{BASE_URL}/api/tasks/{task['id']}").json()
print(json.dumps(task_details, indent=2))

# Check dashboard
dashboard = requests.get(f"{BASE_URL}/api/monitoring/dashboard").json()
print(f"\nTotal tasks in system: {dashboard['overview']['total_tasks']}")
```

---

## 🔥 Method 4: Create Multiple Tasks (Bulk Test)

```bash
# Create 5 test tasks
for i in {1..5}; do
  curl -X POST http://localhost:8001/api/tasks \
    -H "Content-Type: application/json" \
    -d "{
      \"title\": \"Task $i\",
      \"description\": \"Test task number $i\",
      \"task_type\": \"test\",
      \"priority\": $i
    }" \
    -s | python3 -c "import sys, json; print(f\"✅ Created task {json.load(sys.stdin)['id']}\")"
  sleep 0.5
done

# Check how many tasks were created
echo ""
echo "📊 Current metrics:"
curl -s http://localhost:8001/api/monitoring/dashboard | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f\"Total tasks: {data['overview']['total_tasks']}\")
print(f\"Pending: {data['tasks']['pending']}\")
print(f\"Completed: {data['tasks']['completed']}\")
"
```

**Expected Output**:
```
✅ Created task 1
✅ Created task 2
✅ Created task 3
✅ Created task 4
✅ Created task 5

📊 Current metrics:
Total tasks: 5
Pending: 5
Completed: 0
```

---

## 📋 Method 5: Full Workflow with Agents

Create a more complex workflow that involves agents:

### Create Workflow Script

```python
# workflow_demo.py
import requests
import json
import time

BASE_URL = "http://localhost:8001"

def create_agent(name, role):
    """Create a new agent"""
    response = requests.post(
        f"{BASE_URL}/api/agents",
        json={
            "name": name,
            "role": role,
            "description": f"Agent specialized in {role}",
            "capabilities": ["analysis", "execution"],
            "llm_provider": "openai",
            "llm_model": "gpt-4-turbo-preview"
        }
    )
    return response.json()

def assign_task_to_agent(task_id, agent_id):
    """Assign task to agent"""
    response = requests.patch(
        f"{BASE_URL}/api/tasks/{task_id}",
        json={"assigned_agent_id": agent_id}
    )
    return response.json()

def execute_workflow():
    print("🚀 Full Workflow Demo\n")

    # Step 1: Create an agent
    print("1. Creating Code Review Agent...")
    agent = create_agent("CodeReviewer", "reviewer")
    agent_id = agent.get('id')
    print(f"   ✅ Agent created with ID: {agent_id}\n")

    # Step 2: Create a task
    print("2. Creating code review task...")
    task_response = requests.post(
        f"{BASE_URL}/api/tasks",
        json={
            "title": "Review Authentication Module",
            "description": "Perform security review of auth.py",
            "task_type": "code_review",
            "priority": 3
        }
    )
    task = task_response.json()
    task_id = task.get('id')
    print(f"   ✅ Task created with ID: {task_id}\n")

    # Step 3: Assign task to agent
    print("3. Assigning task to agent...")
    assign_task_to_agent(task_id, agent_id)
    print(f"   ✅ Task {task_id} assigned to Agent {agent_id}\n")

    # Step 4: Check dashboard
    print("4. Checking system metrics...\n")
    dashboard = requests.get(f"{BASE_URL}/api/monitoring/dashboard").json()

    print("   📊 System Overview:")
    print(f"   - Total Tasks: {dashboard['overview']['total_tasks']}")
    print(f"   - Total Agents: {dashboard['overview']['total_agents']}")
    print(f"   - Pending Tasks: {dashboard['tasks']['pending']}")
    print(f"   - Active Agents: {dashboard['agents']['active']}")

    print("\n✅ Workflow complete!")
    print(f"\n🌐 View in browser:")
    print(f"   Dashboard: {BASE_URL}/dashboard")
    print(f"   API Docs: {BASE_URL}/docs")

if __name__ == "__main__":
    execute_workflow()
```

### Run the Full Workflow

```bash
# Save the script
cat > workflow_demo.py << 'EOF'
[paste the script above]
EOF

# Run it
python3 workflow_demo.py
```

---

## 🎨 Method 6: Watch Dashboard in Real-Time

Open two terminal windows:

**Terminal 1 - Create Tasks**:
```bash
# Create tasks every 2 seconds
while true; do
  curl -X POST http://localhost:8001/api/tasks \
    -H "Content-Type: application/json" \
    -d "{
      \"title\": \"Auto Task $(date +%H:%M:%S)\",
      \"description\": \"Automatically created task\",
      \"task_type\": \"test\",
      \"priority\": 5
    }" -s > /dev/null
  echo "✅ Created task at $(date +%H:%M:%S)"
  sleep 2
done
```

**Terminal 2 - Monitor Dashboard**:
```bash
# Watch metrics update
watch -n 1 'curl -s http://localhost:8001/api/monitoring/dashboard | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(\"📊 Real-time Metrics\")
print(\"=\"*50)
print(f\"Total Tasks: {data[\"overview\"][\"total_tasks\"]}\")
print(f\"Tasks (24h): {data[\"overview\"][\"tasks_24h\"]}\")
print(f\"Pending: {data[\"tasks\"][\"pending\"]}\")
print(f\"Completed: {data[\"tasks\"][\"completed\"]}\")
print(f\"Failed: {data[\"tasks\"][\"failed\"]}\")
"'
```

---

## 🧪 Verify Everything is Working

### Quick Verification Script

```bash
#!/bin/bash
# verify_system.sh

echo "🔍 System Verification"
echo "====================="

# Check server
echo -n "1. Server health: "
curl -s http://localhost:8001/api/health | python3 -c "import sys, json; print('✅ ' + json.load(sys.stdin)['status'])" || echo "❌ FAILED"

# Create test task
echo -n "2. Task creation: "
TASK_ID=$(curl -s -X POST http://localhost:8001/api/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Test","description":"Test","task_type":"test","priority":5}' | \
  python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "✅ Created task $TASK_ID"

# Retrieve task
echo -n "3. Task retrieval: "
curl -s http://localhost:8001/api/tasks/$TASK_ID | python3 -c "import sys, json; print('✅ ' + json.load(sys.stdin)['title'])" || echo "❌ FAILED"

# Check dashboard
echo -n "4. Dashboard metrics: "
curl -s http://localhost:8001/api/monitoring/dashboard | python3 -c "import sys, json; d=json.load(sys.stdin); print(f'✅ {d[\"overview\"][\"total_tasks\"]} tasks')" || echo "❌ FAILED"

# Check monitoring
echo -n "5. Monitoring health: "
curl -s http://localhost:8001/api/monitoring/health | python3 -c "import sys, json; print('✅ ' + json.load(sys.stdin)['status'])" || echo "❌ FAILED"

echo ""
echo "✅ All systems operational!"
echo ""
echo "🌐 Access Points:"
echo "   Dashboard: http://localhost:8001/dashboard"
echo "   API Docs:  http://localhost:8001/docs"
echo "   Health:    http://localhost:8001/api/health"
```

### Run Verification

```bash
chmod +x verify_system.sh
./verify_system.sh
```

**Expected Output**:
```
🔍 System Verification
=====================
1. Server health: ✅ healthy
2. Task creation: ✅ Created task 1
3. Task retrieval: ✅ Test
4. Dashboard metrics: ✅ 1 tasks
5. Monitoring health: ✅ healthy

✅ All systems operational!

🌐 Access Points:
   Dashboard: http://localhost:8001/dashboard
   API Docs:  http://localhost:8001/docs
   Health:    http://localhost:8001/api/health
```

---

## 📊 Next Steps

After running these examples, you can:

1. **View the Dashboard**:
   ```bash
   open http://localhost:8001/dashboard
   ```

2. **Explore API Documentation**:
   ```bash
   open http://localhost:8001/docs
   ```

3. **Check Database**:
   ```bash
   # View all tasks
   python3 -c "
   from src.core.database import SessionLocal
   from src.models import Task

   db = SessionLocal()
   tasks = db.query(Task).all()
   for task in tasks:
       print(f'ID: {task.id}, Title: {task.title}, Status: {task.status}')
   db.close()
   "
   ```

4. **Run Integration Tests**:
   ```bash
   pytest tests/integration/
   ```

---

## 🎯 Summary

You now have **6 different methods** to execute workflows:

1. ✅ **Simple API calls** (curl)
2. ✅ **Python script** (test_workflow.py)
3. ✅ **Interactive Python** (REPL)
4. ✅ **Bulk tasks** (loop script)
5. ✅ **Full workflow** with agents (workflow_demo.py)
6. ✅ **Real-time monitoring** (watch dashboard)

Pick the method that works best for you and start experimenting! 🚀

---

**Need Help?**
- Check [API_USAGE.md](API_USAGE.md) for detailed API documentation
- Check [MONITORING.md](MONITORING.md) for monitoring features
- Check [VERIFICATION_CHECKLIST.md](VERIFICATION_CHECKLIST.md) for system status
