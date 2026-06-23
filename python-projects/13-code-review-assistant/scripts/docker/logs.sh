#!/usr/bin/env bash
# View logs for AI Code Review Assistant Docker services
# Usage: ./scripts/docker/logs.sh [service-name] [--follow]

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

# Parse arguments
SERVICE=""
FOLLOW_FLAG=""

for arg in "$@"; do
    case $arg in
        --follow|-f)
            FOLLOW_FLAG="-f"
            ;;
        app|worker|beat|redis|postgres|flower)
            SERVICE="$arg"
            ;;
    esac
done

echo -e "${BLUE}====================================================${NC}"
echo -e "${BLUE}   AI Code Review Assistant - Docker Logs${NC}"
echo -e "${BLUE}====================================================${NC}"

if [ "$SERVICE" == "" ]; then
    echo -e "${BLUE}Showing logs for all services...${NC}"
    echo -e "${YELLOW}Tip: Specify a service (app, worker, beat, redis, postgres, flower)${NC}"
    echo -e "${YELLOW}Example: ./scripts/docker/logs.sh app --follow${NC}"
    echo ""
    docker-compose logs --tail=50 $FOLLOW_FLAG
else
    echo -e "${BLUE}Showing logs for service: ${SERVICE}${NC}"
    if [ "$FOLLOW_FLAG" != "" ]; then
        echo -e "${YELLOW}Following logs (Ctrl+C to exit)...${NC}"
    fi
    echo ""
    docker-compose logs --tail=100 $FOLLOW_FLAG $SERVICE
fi
