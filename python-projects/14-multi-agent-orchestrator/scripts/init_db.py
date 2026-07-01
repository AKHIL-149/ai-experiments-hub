#!/usr/bin/env python
"""
Database initialization script
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.db_utils import db_utils
from src.core.seed_data import seed_data


def main():
    """
    Initialize database with schema and seed data
    """
    print("=" * 60)
    print("Database Initialization")
    print("=" * 60)

    # Initialize database schema
    print("\n1. Initializing database schema...")
    db_utils.initialize_database(drop_existing=False)

    # Verify database
    print("\n2. Verifying database connection...")
    status = db_utils.verify_database()
    print(f"   Status: {status['status']}")
    print(f"   Message: {status['message']}")

    if status['status'] == 'healthy':
        # Seed default users
        print("\n3. Seeding default users...")
        user_result = seed_data.seed_default_users()
        print(f"   Created: {user_result['created']}")
        print(f"   Skipped: {user_result['skipped']}")

        # Seed agents
        print("\n4. Seeding default agents...")
        agent_result = seed_data.seed_agents(force=False)
        print(f"   Created: {agent_result['created']}")
        print(f"   Updated: {agent_result['updated']}")
        print(f"   Skipped: {agent_result['skipped']}")

        # Get database stats
        print("\n5. Database statistics:")
        stats = db_utils.get_database_stats()
        print(f"   Total tasks: {stats['tasks']['total']}")
        print(f"   Total agents: {stats['agents']['total']}")
        print(f"   Agents by role: {stats['agents']['by_role']}")

        print("\n" + "=" * 60)
        print("✅ Database initialization complete!")
        print("=" * 60)
    else:
        print(f"\n❌ Database initialization failed: {status.get('error', 'Unknown error')}")
        sys.exit(1)


if __name__ == '__main__':
    main()
