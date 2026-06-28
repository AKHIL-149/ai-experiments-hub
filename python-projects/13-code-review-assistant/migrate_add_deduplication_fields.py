"""
Database migration: Add deduplication and reappearance tracking fields to Issue model
"""

import os
import sys
from sqlalchemy import create_engine, text

# Add parent directory to path to import database module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.core.database import DatabaseManager

def migrate():
    """Add deduplication and reappearance tracking fields to issues table"""

    db_manager = DatabaseManager()
    engine = db_manager.engine

    print("Starting migration: Adding deduplication and reappearance tracking fields...")

    with engine.connect() as conn:
        try:
            # Check if columns already exist
            result = conn.execute(text("PRAGMA table_info(issues)"))
            columns = [row[1] for row in result]

            fields_to_add = []

            # Deduplication fields
            if 'fingerprint' not in columns:
                fields_to_add.append(('fingerprint', "ALTER TABLE issues ADD COLUMN fingerprint VARCHAR(64)"))
            if 'last_seen_at' not in columns:
                fields_to_add.append(('last_seen_at', "ALTER TABLE issues ADD COLUMN last_seen_at DATETIME"))
            if 'resolved' not in columns:
                fields_to_add.append(('resolved', "ALTER TABLE issues ADD COLUMN resolved BOOLEAN DEFAULT 0"))
            if 'resolved_at' not in columns:
                fields_to_add.append(('resolved_at', "ALTER TABLE issues ADD COLUMN resolved_at DATETIME"))

            # Reappearance tracking fields
            if 'reappeared_count' not in columns:
                fields_to_add.append(('reappeared_count', "ALTER TABLE issues ADD COLUMN reappeared_count INTEGER DEFAULT 0"))
            if 'last_reappeared_at' not in columns:
                fields_to_add.append(('last_reappeared_at', "ALTER TABLE issues ADD COLUMN last_reappeared_at DATETIME"))

            if not fields_to_add:
                print("✓ All deduplication fields already exist. Migration not needed.")
                return

            # Add new columns
            for field_name, sql in fields_to_add:
                print(f"Adding '{field_name}' column...")
                conn.execute(text(sql))

            # Create indexes
            print("Creating indexes...")

            # Check existing indexes
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='issues'"))
            existing_indexes = {row[0] for row in result}

            if 'idx_issue_resolved' not in existing_indexes:
                print("  - Creating index on 'resolved'...")
                conn.execute(text("CREATE INDEX idx_issue_resolved ON issues (resolved)"))

            if 'idx_issue_fingerprint' not in existing_indexes:
                print("  - Creating index on 'fingerprint'...")
                conn.execute(text("CREATE INDEX idx_issue_fingerprint ON issues (fingerprint)"))

            conn.commit()

            print("\n✓ Migration completed successfully!")
            print("\nAdded fields:")
            print("  Deduplication:")
            print("    - fingerprint (VARCHAR(64), indexed)")
            print("    - last_seen_at (DATETIME)")
            print("    - resolved (BOOLEAN, default=False, indexed)")
            print("    - resolved_at (DATETIME)")
            print("  Reappearance Tracking:")
            print("    - reappeared_count (INTEGER, default=0)")
            print("    - last_reappeared_at (DATETIME)")

        except Exception as e:
            print(f"✗ Migration failed: {e}")
            conn.rollback()
            raise

if __name__ == "__main__":
    migrate()
