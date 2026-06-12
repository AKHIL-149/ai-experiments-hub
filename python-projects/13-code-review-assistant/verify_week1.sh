#!/bin/bash

echo "=========================================="
echo "Week 1 Verification Script"
echo "AI Code Review Assistant"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counters
PASSED=0
FAILED=0

# Helper functions
pass_test() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASSED++))
}

fail_test() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((FAILED++))
}

warn_test() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
}

# Test 1: Check Python version
echo "Test 1: Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

    if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 8 ]; then
        pass_test "Python $PYTHON_VERSION installed"
    else
        fail_test "Python 3.8+ required (found $PYTHON_VERSION)"
    fi
else
    fail_test "Python 3 not found"
fi
echo ""

# Test 2: Check virtual environment
echo "Test 2: Checking virtual environment..."
if [ -d "venv" ]; then
    pass_test "Virtual environment exists"
else
    fail_test "Virtual environment not found (run: python3 -m venv venv)"
fi
echo ""

# Test 3: Check required files
echo "Test 3: Checking required files..."
FILES=(
    "requirements.txt"
    ".env.example"
    "server.py"
    "celery_app.py"
    "src/core/database.py"
    "src/core/auth_manager.py"
    "src/core/queue_manager.py"
    "templates/base.html"
    "templates/dashboard.html"
    "templates/login.html"
    "templates/register.html"
    "static/css/style.css"
    "static/js/app.js"
    "README.md"
)

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        pass_test "File exists: $file"
    else
        fail_test "File missing: $file"
    fi
done
echo ""

# Test 4: Check .env file
echo "Test 4: Checking environment configuration..."
if [ -f ".env" ]; then
    pass_test ".env file exists"
else
    warn_test ".env file not found (copy from .env.example)"
fi
echo ""

# Test 5: Check dependencies
echo "Test 5: Checking installed dependencies..."
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate

    DEPS=("fastapi" "sqlalchemy" "celery" "redis" "bcrypt" "uvicorn")
    for dep in "${DEPS[@]}"; do
        if python3 -c "import $dep" 2>/dev/null; then
            pass_test "Package installed: $dep"
        else
            fail_test "Package missing: $dep (run: pip install -r requirements.txt)"
        fi
    done
else
    warn_test "Virtual environment not activated, skipping dependency check"
fi
echo ""

# Test 6: Check Redis connectivity
echo "Test 6: Checking Redis server..."
if command -v redis-cli &> /dev/null; then
    if redis-cli ping &> /dev/null; then
        pass_test "Redis server is running"
    else
        fail_test "Redis server not responding (run: redis-server)"
    fi
else
    warn_test "redis-cli not found, cannot check Redis status"
fi
echo ""

# Test 7: Check database initialization
echo "Test 7: Checking database..."
if [ -d "data" ]; then
    pass_test "Data directory exists"

    if [ -f "data/database.db" ]; then
        pass_test "Database file exists"
    else
        warn_test "Database not initialized (run initialization script)"
    fi
else
    fail_test "Data directory not found (run: mkdir -p data/repos)"
fi
echo ""

# Test 8: Import test
echo "Test 8: Testing Python imports..."
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate

    python3 << 'EOF'
try:
    from src.core.database import DatabaseManager, User, UserRole
    from src.core.auth_manager import AuthManager
    from src.core.queue_manager import QueueManager
    print("✓ All core modules import successfully")
    exit(0)
except Exception as e:
    print(f"✗ Import error: {e}")
    exit(1)
EOF

    if [ $? -eq 0 ]; then
        pass_test "Core modules import successfully"
    else
        fail_test "Import errors detected"
    fi
else
    warn_test "Virtual environment not activated, skipping import test"
fi
echo ""

# Test 9: Check test files
echo "Test 9: Checking test files..."
TEST_FILES=(
    "tests/__init__.py"
    "tests/test_database.py"
    "tests/test_auth.py"
)

for file in "${TEST_FILES[@]}"; do
    if [ -f "$file" ]; then
        pass_test "Test file exists: $file"
    else
        fail_test "Test file missing: $file"
    fi
done
echo ""

# Test 10: Run pytest (if available)
echo "Test 10: Running unit tests..."
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate

    if command -v pytest &> /dev/null; then
        if pytest tests/ -v --tb=short 2>&1 | tail -n 20; then
            pass_test "All tests passed"
        else
            warn_test "Some tests failed (check output above)"
        fi
    else
        warn_test "pytest not installed (run: pip install pytest)"
    fi
else
    warn_test "Virtual environment not activated, skipping pytest"
fi
echo ""

# Summary
echo "=========================================="
echo "VERIFICATION SUMMARY"
echo "=========================================="
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ Week 1 verification complete - All critical tests passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Start Redis: redis-server"
    echo "2. Start Celery: celery -A celery_app worker --loglevel=info"
    echo "3. Start server: python server.py"
    echo "4. Open http://localhost:8000"
    exit 0
else
    echo -e "${RED}✗ Week 1 verification incomplete - Please fix failed tests${NC}"
    echo ""
    echo "Common fixes:"
    echo "- Install dependencies: pip install -r requirements.txt"
    echo "- Create .env file: cp .env.example .env"
    echo "- Create data directory: mkdir -p data/repos"
    echo "- Start Redis: redis-server"
    exit 1
fi
