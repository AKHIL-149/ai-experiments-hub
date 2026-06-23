#!/usr/bin/env bash
# Stop AI Code Review Assistant Docker services
# Usage: ./scripts/docker/stop.sh [--remove]

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
echo -e "${BLUE}   AI Code Review Assistant - Docker Shutdown${NC}"
echo -e "${BLUE}====================================================${NC}"

# Parse arguments
REMOVE_FLAG=""

for arg in "$@"; do
    case $arg in
        --remove)
            REMOVE_FLAG="--remove-orphans -v"
            echo -e "${YELLOW}Removing containers and volumes...${NC}"
            ;;
    esac
done

# Stop services
if [ "$REMOVE_FLAG" != "" ]; then
    echo -e "${YELLOW}Stopping and removing Docker services...${NC}"
    docker-compose down $REMOVE_FLAG
else
    echo -e "${BLUE}Stopping Docker services...${NC}"
    docker-compose stop
fi

echo -e "${GREEN}====================================================${NC}"
echo -e "${GREEN}   Services Stopped Successfully!${NC}"
echo -e "${GREEN}====================================================${NC}"

if [ "$REMOVE_FLAG" != "" ]; then
    echo -e "${YELLOW}Note: Containers and volumes have been removed.${NC}"
    echo -e "${YELLOW}Data has been preserved in Docker volumes.${NC}"
    echo -e "${BLUE}To completely reset data, run: ./scripts/docker/reset.sh${NC}"
else
    echo -e "${BLUE}To restart services: ./scripts/docker/start.sh${NC}"
    echo -e "${BLUE}To remove containers: ./scripts/docker/stop.sh --remove${NC}"
fi

echo -e "${GREEN}====================================================${NC}"
