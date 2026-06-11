#!/bin/bash
echo "Testing Project 12 - Content Moderation System"
echo "=============================================="
echo

# Test 1: Health Check
echo "1. Health Check:"
curl -s http://localhost:8001/api/health | python3 -m json.tool
echo

# Test 2: Login as admin
echo "2. Login as Admin:"
curl -s -X POST http://localhost:8001/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' \
  -c cookies.txt | python3 -m json.tool
echo

# Test 3: Get current user
echo "3. Get Current User:"
curl -s http://localhost:8001/api/auth/me -b cookies.txt | python3 -m json.tool
echo

# Test 4: Get analytics overview
echo "4. Analytics Overview:"
curl -s http://localhost:8001/api/analytics/overview -b cookies.txt | python3 -m json.tool
echo

# Test 5: Get policies
echo "5. Get Policies:"
curl -s http://localhost:8001/api/admin/policies -b cookies.txt | python3 -m json.tool
echo

# Test 6: Get review queue
echo "6. Review Queue:"
curl -s "http://localhost:8001/api/moderation/queue?limit=5" -b cookies.txt | python3 -m json.tool
echo

echo "✅ All tests completed!"
echo
echo "Access the admin dashboard at: http://localhost:8001/admin/dashboard"
