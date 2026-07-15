#!/bin/bash

cat <<'EOF'
╔══════════════════════════════════════════════════════════════╗
║          LIVE SYSTEM TEST - QUICK VERIFICATION               ║
╚══════════════════════════════════════════════════════════════╝

Testing Multi-Agent Task Orchestrator endpoints...

EOF

BASE_URL="http://localhost:8001"
PASS="✅"
FAIL="❌"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 1: Health Check Endpoint"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

RESPONSE=$(curl -s "${BASE_URL}/api/health")
if echo "$RESPONSE" | grep -q "healthy"; then
    echo "$PASS Health check passed"
    echo "Response: $RESPONSE"
else
    echo "$FAIL Health check failed"
    echo "Response: $RESPONSE"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 2: Root Endpoint"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

RESPONSE=$(curl -s "${BASE_URL}/")
if echo "$RESPONSE" | grep -q "Multi-Agent"; then
    echo "$PASS Root endpoint passed"
    echo "Response: $RESPONSE"
else
    echo "$FAIL Root endpoint failed"
    echo "Response: $RESPONSE"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 3: API Documentation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/docs")
if [ "$STATUS" = "200" ]; then
    echo "$PASS API docs accessible at ${BASE_URL}/docs"
else
    echo "$FAIL API docs not accessible (HTTP $STATUS)"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 4: Dashboard"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/dashboard")
if [ "$STATUS" = "200" ]; then
    echo "$PASS Dashboard accessible at ${BASE_URL}/dashboard"
else
    echo "$FAIL Dashboard not accessible (HTTP $STATUS)"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 5: Create a Simple Task"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

RESPONSE=$(curl -s -X POST "${BASE_URL}/api/tasks" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Test Task",
    "description": "System verification test",
    "task_type": "simple",
    "priority": "NORMAL"
  }' 2>&1)

if echo "$RESPONSE" | grep -q -E "(id|task_id|title)"; then
    echo "$PASS Task creation successful"
    echo "Response: $RESPONSE" | head -c 200
    echo "..."
else
    echo "$FAIL Task creation failed"
    echo "Response: $RESPONSE"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "TEST 6: Monitoring Dashboard API"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

RESPONSE=$(curl -s "${BASE_URL}/api/monitoring/dashboard" 2>&1)
if echo "$RESPONSE" | grep -q -E "(overview|tasks|agents)"; then
    echo "$PASS Monitoring API accessible"
    echo "Response: $RESPONSE" | head -c 200
    echo "..."
else
    echo "$FAIL Monitoring API failed"
    echo "Response: $RESPONSE"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "✓ Server is running at: ${BASE_URL}"
echo "✓ API Documentation: ${BASE_URL}/docs"
echo "✓ Monitoring Dashboard: ${BASE_URL}/dashboard"
echo "✓ ReDoc: ${BASE_URL}/redoc"
echo ""
echo "📚 Next Steps:"
echo "   1. Open ${BASE_URL}/docs in your browser to explore all endpoints"
echo "   2. Open ${BASE_URL}/dashboard to see real-time metrics"
echo "   3. Read WORKFLOW_GUIDE.md for use cases and testing scenarios"
echo "   4. Try: python3 examples/run_workflow.py --template code_review"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
