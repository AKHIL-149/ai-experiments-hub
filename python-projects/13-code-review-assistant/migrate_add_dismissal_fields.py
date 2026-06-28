"""
Database migration: Add dismissal tracking fields to Issue model
"""

import os
import sys
from sqlalchemy import create_engine, text

# Add parent directory to path to import database module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.database import DatabaseManager

def migrate():
    """Add dismissal fields to issues table"""

    db_manager = DatabaseManager()
    engine = db_manager.engine

    print("Starting migration: Adding dismissal fields to issues table...")

    with engine.connect() as conn:
        try:
            # Check if columns already exist
            result = conn.execute(text("PRAGMA table_info(issues)"))
            columns = [row[1] for row in result]

            if 'dismissed' in columns:
                print("✓ Dismissal fields already exist. Migration not needed.")
                return

            # Add new columns
            print("Adding 'dismissed' column...")
            conn.execute(text("ALTER TABLE issues ADD COLUMN dismissed BOOLEAN DEFAULT 0"))

            print("Adding 'dismissed_at' column...")
            conn.execute(text("ALTER TABLE issues ADD COLUMN dismissed_at DATETIME"))

            print("Adding 'dismissed_by' column...")
            conn.execute(text("ALTER TABLE issues ADD COLUMN dismissed_by VARCHAR(36)"))

            print("Adding 'dismissal_reason' column...")
            conn.execute(text("ALTER TABLE issues ADD COLUMN dismissal_reason TEXT"))

            # Create index on dismissed field
            print("Creating index on 'dismissed' column...")
            conn.execute(text("CREATE INDEX idx_issue_dismissed ON issues (dismissed)"))

            conn.commit()

            print("✓ Migration completed successfully!")
            print("\nAdded fields:")
            print("  - dismissed (BOOLEAN, default=False, indexed)")
            print("  - dismissed_at (DATETIME)")
            print("  - dismissed_by (VARCHAR(36), foreign key to users.id)")
            print("  - dismissal_reason (TEXT)")

        except Exception as e:
            print(f"✗ Migration failed: {e}")
            conn.rollback()
            raise

if __name__ == "__main__":
    migrate()
