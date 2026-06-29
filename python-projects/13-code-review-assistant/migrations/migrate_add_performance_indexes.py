#!/usr/bin/env python3
"""
Migration: Add performance optimization indexes
Adds composite indexes for common query patterns to improve query performance
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.database import DatabaseManager
from sqlalchemy import text


def migrate():
    """Add performance optimization indexes"""
    db_manager = DatabaseManager()
    engine = db_manager.engine

    with engine.connect() as conn:
        print("Adding performance optimization indexes...")

        # Issue table indexes
        print("  - Creating idx_issue_dismissed_resolved...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_issue_dismissed_resolved
            ON issues (dismissed, resolved)
        """))

        print("  - Creating idx_issue_severity_dismissed...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_issue_severity_dismissed
            ON issues (severity, dismissed, resolved)
        """))

        print("  - Creating idx_issue_created_desc...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_issue_created_desc
            ON issues (created_at)
        """))

        # Repository table indexes
        print("  - Creating idx_repo_user_created...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_repo_user_created
            ON repositories (user_id, created_at)
        """))

        print("  - Creating idx_repo_user_status...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_repo_user_status
            ON repositories (user_id, status)
        """))

        print("  - Creating idx_repo_team_created...")
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_repo_team_created
            ON repositories (team_id, created_at)
        """))

        conn.commit()
        print("✅ Performance indexes added successfully")


def rollback():
    """Remove performance optimization indexes"""
    db_manager = DatabaseManager()
    engine = db_manager.engine

    with engine.connect() as conn:
        print("Removing performance optimization indexes...")

        # Drop Issue table indexes
        conn.execute(text("DROP INDEX IF EXISTS idx_issue_dismissed_resolved"))
        conn.execute(text("DROP INDEX IF EXISTS idx_issue_severity_dismissed"))
        conn.execute(text("DROP INDEX IF EXISTS idx_issue_created_desc"))

        # Drop Repository table indexes
        conn.execute(text("DROP INDEX IF EXISTS idx_repo_user_created"))
        conn.execute(text("DROP INDEX IF EXISTS idx_repo_user_status"))
        conn.execute(text("DROP INDEX IF EXISTS idx_repo_team_created"))

        conn.commit()
        print("✅ Performance indexes removed successfully")


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == 'rollback':
        rollback()
    else:
        migrate()
