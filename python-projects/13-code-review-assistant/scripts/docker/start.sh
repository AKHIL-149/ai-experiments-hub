#!/usr/bin/env bash
# Start AI Code Review Assistant in Docker
# Usage: ./scripts/docker/start.sh [--build] [--monitoring]

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

cd "$PROJECT_ROOT"

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}   AI Code Review Assistant - Docker Startup${NC}"
echo -e "${BLUE}====================================================${NC}"

# Check for .env file
if [ ! -f .env ]; then
    echo -e "${YELLOW}Warning: .env file not found. Creating from .env.example...${NC}"
    if [ -f .env.example ]; then
        cp .env.example .env
        echo -e "${GREEN}✓ Created .env file. Please edit it with your configuration.${NC}"
    else
        echo -e "${YELLOW}Error: .env.example not found${NC}"
        exit 1
    fi
fi

# Parse arguments
BUILD_FLAG=""
PROFILE_FLAG=""

for arg in "$@"; do
    case $arg in
        --build)
            BUILD_FLAG="--build"
            echo -e "${BLUE}Building Docker images...${NC}"
            ;;
        --monitoring)
            PROFILE_FLAG="--profile monitoring"
            echo -e "${BLUE}Starting with monitoring (Flower)...${NC}"
            ;;
    esac
done

# Start services
echo -e "${BLUE}Starting Docker services...${NC}"
docker-compose up -d $BUILD_FLAG $PROFILE_FLAG

# Wait for services to be healthy
echo -e "${BLUE}Waiting for services to be healthy...${NC}"
sleep 5

# Check service health
echo -e "${BLUE}Checking service health...${NC}"
docker-compose ps

# Show service URLs
echo -e "${GREEN}====================================================${NC}"
echo -e "${GREEN}   Services Started Successfully!${NC}"
echo -e "${GREEN}====================================================${NC}"
echo -e "${GREEN}Application:${NC}      http://localhost:8000"
echo -e "${GREEN}API Health:${NC}       http://localhost:8000/api/health"
echo -e "${GREEN}API Docs:${NC}         http://localhost:8000/docs"
echo -e "${GREEN}Redis:${NC}            localhost:6379"
echo -e "${GREEN}PostgreSQL:${NC}       localhost:5432"

if [ "$PROFILE_FLAG" != "" ]; then
    echo -e "${GREEN}Flower (Monitor):${NC} http://localhost:5555"
fi

echo -e "${GREEN}====================================================${NC}"
echo -e "${BLUE}View logs:${NC}          ./scripts/docker/logs.sh"
echo -e "${BLUE}Stop services:${NC}      ./scripts/docker/stop.sh"
echo -e "${BLUE}Reset data:${NC}         ./scripts/docker/reset.sh"
echo -e "${GREEN}====================================================${NC}"
