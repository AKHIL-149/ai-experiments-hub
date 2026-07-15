#!/bin/bash
# Curl Examples for Multi-Agent Task Orchestrator API
#
# Usage:
#   # Set your API base URL
#   export API_BASE="http://localhost:8001/api"
#
#   # Run all examples
#   ./examples/curl_examples.sh
#
#   # Or copy/paste individual commands

# Configuration
API_BASE="${API_BASE:-http://localhost:8001/api}"
EMAIL="user@example.com"
PASSWORD="password123"

echo "==================================================================="
echo "Multi-Agent Task Orchestrator - Curl API Examples"
echo "==================================================================="
echo ""
echo "API Base: $API_BASE"
echo ""

# ===================================================================
# HEALTH CHECK
# ===================================================================
echo "1. Health Check"
echo "-------------------------------------------------------------------"
curl -s "$API_BASE/../api/health" | python3 -m json.tool
echo ""
echo ""

# ===================================================================
# AUTHENTICATION
# ===================================================================
echo "2. User Signup"
echo "-------------------------------------------------------------------"
signup_response=$(curl -s -X POST "$API_BASE/auth/signup" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$EMAIL\",
    \"username\": \"demo_user\",
    \"password\": \"$PASSWORD\"
  }")
echo "$signup_response" | python3 -m json.tool
echo ""
echo ""

echo "3. User Login"
echo "-------------------------------------------------------------------"
login_response=$(curl -s -X POST "$API_BASE/auth/login" \
  -H "Content-Type: application/json" \
  -d "{
    \"email\": \"$EMAIL\",
    \"password\": \"$PASSWORD\"
  }")
echo "$login_response" | python3 -m json.tool

# Extract token
TOKEN=$(echo "$login_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "⚠️  Warning: Could not extract token. Some examples may fail."
    echo "   This is normal if user already exists. Try logging in manually."
    TOKEN="your_token_here"
fi

echo ""
echo "Access Token: ${TOKEN:0:50}..."
echo ""
echo ""

# ===================================================================
# AGENTS
# ===================================================================
echo "4. List All Agents"
echo "-------------------------------------------------------------------"
curl -s "$API_BASE/agents" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""
echo ""

# ===================================================================
# TASKS
# ===================================================================
echo "5. Create a Task"
echo "-------------------------------------------------------------------"
task_response=$(curl -s -X POST "$API_BASE/tasks" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "title": "Analyze Sales Data",
    "description": "Perform statistical analysis on Q4 2025 sales data",
    "task_type": "data_analysis",
    "priority": 5,
    "metadata": {
      "dataset": "sales_q4_2025.csv",
      "analysis_type": "descriptive_statistics"
    }
  }')
echo "$task_response" | python3 -m json.tool

# Extract task ID
TASK_ID=$(echo "$task_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('id', ''))" 2>/dev/null)
echo ""
echo "Created Task ID: $TASK_ID"
echo ""
echo ""

echo "6. List All Tasks"
echo "-------------------------------------------------------------------"
curl -s "$API_BASE/tasks" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -50
echo ""
echo ""

if [ -n "$TASK_ID" ] && [ "$TASK_ID" != "" ]; then
    echo "7. Get Task Details"
    echo "-------------------------------------------------------------------"
    curl -s "$API_BASE/tasks/$TASK_ID" \
      -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
    echo ""
    echo ""
fi

# ===================================================================
# WORKFLOWS
# ===================================================================
echo "8. Create a Workflow"
echo "-------------------------------------------------------------------"
workflow_response=$(curl -s -X POST "$API_BASE/workflow-engine/workflows" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "Quick Code Review",
    "description": "Fast code review focusing on critical issues",
    "workflow_type": "custom",
    "steps": [
      {
        "step_name": "analyze_code",
        "step_type": "agent",
        "agent_role": "code",
        "config": {
          "task": "Perform quick code analysis",
          "priority": "high"
        },
        "dependencies": []
      },
      {
        "step_name": "generate_feedback",
        "step_type": "agent",
        "agent_role": "writer",
        "config": {
          "task": "Generate concise feedback report",
          "output_format": "bullet_points"
        },
        "dependencies": ["analyze_code"]
      }
    ],
    "metadata": {
      "category": "code_quality",
      "tags": ["code-review", "quick"]
    }
  }')
echo "$workflow_response" | python3 -m json.tool

# Extract workflow ID
WORKFLOW_ID=$(echo "$workflow_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('workflow_id', ''))" 2>/dev/null)
echo ""
echo "Created Workflow ID: $WORKFLOW_ID"
echo ""
echo ""

echo "9. List Workflows"
echo "-------------------------------------------------------------------"
curl -s "$API_BASE/workflow-engine/workflows" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool | head -50
echo ""
echo ""

if [ -n "$WORKFLOW_ID" ] && [ "$WORKFLOW_ID" != "" ]; then
    echo "10. Get Workflow Details"
    echo "-------------------------------------------------------------------"
    curl -s "$API_BASE/workflow-engine/workflows/$WORKFLOW_ID" \
      -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
    echo ""
    echo ""

    echo "11. Execute Workflow"
    echo "-------------------------------------------------------------------"
    execution_response=$(curl -s -X POST "$API_BASE/workflow-engine/workflows/$WORKFLOW_ID/execute" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -d '{
        "input_data": {
          "code": "def hello():\n    print(\"Hello, World!\")\n",
          "language": "python"
        }
      }')
    echo "$execution_response" | python3 -m json.tool
    echo ""
    echo ""

    echo "12. Get Workflow Status"
    echo "-------------------------------------------------------------------"
    curl -s "$API_BASE/workflow-engine/workflows/$WORKFLOW_ID/status" \
      -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
    echo ""
    echo ""
fi

# ===================================================================
# ANALYTICS & MONITORING
# ===================================================================
echo "13. Get System Metrics"
echo "-------------------------------------------------------------------"
curl -s "$API_BASE/metrics" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""
echo ""

echo "14. Get Agent Performance"
echo "-------------------------------------------------------------------"
curl -s "$API_BASE/performance" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""
echo ""

# ===================================================================
# SHARED MEMORY
# ===================================================================
echo "15. Create Shared Memory Entry"
echo "-------------------------------------------------------------------"
curl -s -X POST "$API_BASE/shared-memory" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "key": "project_context",
    "value": {
      "project_name": "AI Orchestrator",
      "version": "1.0.0",
      "stack": ["Python", "FastAPI", "LangGraph"]
    },
    "scope": "global",
    "memory_type": "context"
  }' | python3 -m json.tool
echo ""
echo ""

echo "16. Get Shared Memory"
echo "-------------------------------------------------------------------"
curl -s "$API_BASE/shared-memory/project_context" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""
echo ""

# ===================================================================
# MESSAGES
# ===================================================================
echo "17. List Agent Messages"
echo "-------------------------------------------------------------------"
curl -s "$API_BASE/messages?limit=5" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
echo ""
echo ""

# ===================================================================
# SUMMARY
# ===================================================================
echo "==================================================================="
echo "Examples Complete!"
echo "==================================================================="
echo ""
echo "Next Steps:"
echo "  1. Explore interactive API docs: http://localhost:8001/docs"
echo "  2. Try example workflows: python examples/run_workflow.py --list"
echo "  3. Read API usage guide: examples/API_USAGE.md"
echo "  4. Monitor workflows via WebSocket for real-time updates"
echo ""
echo "Your Access Token (save for future requests):"
echo "  export TOKEN=\"$TOKEN\""
echo ""
echo "Example authenticated request:"
echo "  curl -H \"Authorization: Bearer \$TOKEN\" $API_BASE/tasks"
echo ""
