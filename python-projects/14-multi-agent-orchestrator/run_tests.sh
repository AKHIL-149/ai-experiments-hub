#!/bin/bash
# Test Runner Script for Multi-Agent Task Orchestrator
#
# Usage:
#   ./run_tests.sh                    # Run all tests
#   ./run_tests.sh unit               # Run only unit tests
#   ./run_tests.sh integration        # Run only integration tests
#   ./run_tests.sh --coverage         # Run with coverage report
#   ./run_tests.sh --fast             # Run fast tests only
#   ./run_tests.sh --verbose          # Run with verbose output

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
TEST_DIR="tests"
COVERAGE_MIN=70

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Multi-Agent Task Orchestrator - Tests${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Parse arguments
TEST_TYPE=""
COVERAGE=false
VERBOSE=false
FAST=false

for arg in "$@"; do
    case $arg in
        unit)
            TEST_TYPE="unit"
            ;;
        integration)
            TEST_TYPE="integration"
            ;;
        --coverage|-c)
            COVERAGE=true
            ;;
        --verbose|-v)
            VERBOSE=true
            ;;
        --fast|-f)
            FAST=true
            ;;
        --help|-h)
            echo "Usage: ./run_tests.sh [TYPE] [OPTIONS]"
            echo ""
            echo "Types:"
            echo "  unit           Run only unit tests"
            echo "  integration    Run only integration tests"
            echo ""
            echo "Options:"
            echo "  --coverage     Generate coverage report"
            echo "  --fast         Skip slow tests"
            echo "  --verbose      Verbose output"
            echo "  --help         Show this help message"
            exit 0
            ;;
    esac
done

# Build pytest command
PYTEST_CMD="pytest"

# Add markers based on test type
if [ "$TEST_TYPE" == "unit" ]; then
    PYTEST_CMD="$PYTEST_CMD -m unit"
    echo -e "${YELLOW}Running unit tests only${NC}"
elif [ "$TEST_TYPE" == "integration" ]; then
    PYTEST_CMD="$PYTEST_CMD -m integration"
    echo -e "${YELLOW}Running integration tests only${NC}"
else
    echo -e "${YELLOW}Running all tests${NC}"
fi

# Add fast filter
if [ "$FAST" == true ]; then
    PYTEST_CMD="$PYTEST_CMD -m 'not slow'"
    echo -e "${YELLOW}Skipping slow tests${NC}"
fi

# Add coverage
if [ "$COVERAGE" == true ]; then
    PYTEST_CMD="$PYTEST_CMD --cov=src --cov-report=html --cov-report=term-missing --cov-fail-under=$COVERAGE_MIN"
    echo -e "${YELLOW}Coverage reporting enabled (minimum: ${COVERAGE_MIN}%)${NC}"
fi

# Add verbose
if [ "$VERBOSE" == true ]; then
    PYTEST_CMD="$PYTEST_CMD -vv"
fi

echo ""
echo -e "${BLUE}Command: $PYTEST_CMD${NC}"
echo ""

# Run tests
if $PYTEST_CMD; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✅ All tests passed!${NC}"
    echo -e "${GREEN}========================================${NC}"

    if [ "$COVERAGE" == true ]; then
        echo ""
        echo -e "${BLUE}Coverage report saved to: htmlcov/index.html${NC}"
        echo -e "${BLUE}Open with: open htmlcov/index.html${NC}"
    fi

    exit 0
else
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}❌ Tests failed!${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
