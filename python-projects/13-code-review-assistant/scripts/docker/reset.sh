#!/usr/bin/env bash
# Reset AI Code Review Assistant Docker environment
# WARNING: This will delete all data, volumes, and images
# Usage: ./scripts/docker/reset.sh [--yes]

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../.." && pwd )"

cd "$PROJECT_ROOT"

echo -e "${RED}====================================================${NC}"
echo -e "${RED}   AI Code Review Assistant - Docker Reset${NC}"
echo -e "${RED}====================================================${NC}"
echo -e "${YELLOW}WARNING: This will:${NC}"
echo -e "${YELLOW}  - Stop all running containers${NC}"
echo -e "${YELLOW}  - Remove all containers${NC}"
echo -e "${YELLOW}  - Delete all volumes (DATABASE, REPOS, LOGS)${NC}"
echo -e "${YELLOW}  - Remove Docker images${NC}"
echo -e "${YELLOW}  - Remove Docker network${NC}"
echo -e "${RED}====================================================${NC}"

# Check for --yes flag
AUTO_YES=false
for arg in "$@"; do
    case $arg in
        --yes|-y)
            AUTO_YES=true
            ;;
    esac
done

if [ "$AUTO_YES" = false ]; then
    read -p "Are you sure you want to continue? (yes/no): " -r
    echo
    if [[ ! $REPLY =~ ^[Yy][Ee][Ss]$ ]]; then
        echo -e "${BLUE}Reset cancelled.${NC}"
        exit 0
    fi
fi

echo -e "${BLUE}Stopping all services...${NC}"
docker-compose down --remove-orphans || true

echo -e "${BLUE}Removing volumes...${NC}"
docker volume rm code-review-redis-data || true
docker volume rm code-review-postgres-data || true
docker volume rm code-review-app-data || true
docker volume rm code-review-app-logs || true

echo -e "${BLUE}Removing Docker images...${NC}"
docker-compose down --rmi all --volumes --remove-orphans || true

echo -e "${BLUE}Removing Docker network...${NC}"
docker network rm code-review-network || true

echo -e "${BLUE}Pruning Docker system...${NC}"
docker system prune -f

echo -e "${GREEN}====================================================${NC}"
echo -e "${GREEN}   Docker Environment Reset Complete!${NC}"
echo -e "${GREEN}====================================================${NC}"
echo -e "${BLUE}To start fresh:${NC}"
echo -e "  1. Check your .env configuration"
echo -e "  2. Run: ./scripts/docker/start.sh --build"
echo -e "${GREEN}====================================================${NC}"
