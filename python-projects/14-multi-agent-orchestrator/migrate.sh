#!/bin/bash
# Database Migration Helper Script
#
# Usage:
#   ./migrate.sh upgrade      # Upgrade to latest
#   ./migrate.sh downgrade    # Downgrade one version
#   ./migrate.sh status       # Show current status
#   ./migrate.sh history      # Show migration history
#   ./migrate.sh create "description"  # Create new migration

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check if alembic is installed
if ! command -v alembic &> /dev/null; then
    echo -e "${RED}Error: alembic is not installed${NC}"
    echo "Install with: pip install alembic"
    exit 1
fi

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo -e "${YELLOW}Warning: DATABASE_URL not set, using default from alembic.ini${NC}"
fi

case "$1" in
    upgrade)
        echo -e "${BLUE}Upgrading database to latest version...${NC}"
        alembic upgrade head
        echo -e "${GREEN}✅ Database upgraded successfully${NC}"
        ;;

    downgrade)
        echo -e "${YELLOW}Downgrading database one version...${NC}"
        alembic downgrade -1
        echo -e "${GREEN}✅ Database downgraded${NC}"
        ;;

    status)
        echo -e "${BLUE}Current database version:${NC}"
        alembic current
        echo ""
        echo -e "${BLUE}Latest available version:${NC}"
        alembic heads
        ;;

    history)
        echo -e "${BLUE}Migration history:${NC}"
        alembic history
        ;;

    create)
        if [ -z "$2" ]; then
            echo -e "${RED}Error: Please provide a migration description${NC}"
            echo "Usage: ./migrate.sh create \"Add new column to workflows\""
            exit 1
        fi

        echo -e "${BLUE}Creating new migration: $2${NC}"
        alembic revision --autogenerate -m "$2"
        echo -e "${GREEN}✅ Migration created${NC}"
        echo -e "${YELLOW}Review the generated file in migrations/versions/${NC}"
        ;;

    test)
        echo -e "${BLUE}Testing migrations (upgrade -> downgrade -> upgrade)...${NC}"

        echo -e "${YELLOW}1. Upgrading to head...${NC}"
        alembic upgrade head
        echo -e "${GREEN}✅ Upgrade successful${NC}"

        echo ""
        echo -e "${YELLOW}2. Downgrading one version...${NC}"
        alembic downgrade -1
        echo -e "${GREEN}✅ Downgrade successful${NC}"

        echo ""
        echo -e "${YELLOW}3. Upgrading back to head...${NC}"
        alembic upgrade head
        echo -e "${GREEN}✅ Re-upgrade successful${NC}"

        echo ""
        echo -e "${GREEN}✅ Migration test completed successfully${NC}"
        ;;

    reset)
        echo -e "${RED}⚠️  WARNING: This will reset the database to base state${NC}"
        read -p "Are you sure? (yes/no): " confirm

        if [ "$confirm" = "yes" ]; then
            echo -e "${YELLOW}Downgrading to base...${NC}"
            alembic downgrade base
            echo -e "${GREEN}✅ Database reset to base${NC}"
        else
            echo "Reset cancelled"
        fi
        ;;

    stamp)
        if [ -z "$2" ]; then
            echo -e "${YELLOW}Stamping database at head...${NC}"
            alembic stamp head
        else
            echo -e "${YELLOW}Stamping database at $2...${NC}"
            alembic stamp "$2"
        fi
        echo -e "${GREEN}✅ Database stamped${NC}"
        ;;

    *)
        echo "Database Migration Helper"
        echo ""
        echo "Usage:"
        echo "  ./migrate.sh upgrade              Upgrade to latest version"
        echo "  ./migrate.sh downgrade            Downgrade one version"
        echo "  ./migrate.sh status               Show current version"
        echo "  ./migrate.sh history              Show migration history"
        echo "  ./migrate.sh create \"description\" Create new migration"
        echo "  ./migrate.sh test                 Test migrations (up/down/up)"
        echo "  ./migrate.sh reset                Reset database to base (⚠️  destructive)"
        echo "  ./migrate.sh stamp [revision]     Stamp database at revision"
        echo ""
        echo "Examples:"
        echo "  ./migrate.sh upgrade"
        echo "  ./migrate.sh create \"Add priority field to workflows\""
        echo "  ./migrate.sh test"
        echo ""
        exit 1
        ;;
esac
