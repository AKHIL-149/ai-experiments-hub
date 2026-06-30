#!/usr/bin/env python
"""
Seed sample data for testing
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.core.seed_data import seed_data


def main():
    """
    Seed sample data for testing
    """
    print("=" * 60)
    print("Seeding Sample Data")
    print("=" * 60)

    # Seed sample tasks
    print("\n1. Creating sample tasks...")
    task_result = seed_data.seed_sample_tasks()
    print(f"   Created: {task_result['created']} tasks")

    print("\n" + "=" * 60)
    print("✅ Sample data seeded successfully!")
    print("=" * 60)
    print("\nYou can now:")
    print("  - View tasks at: http://localhost:8001/api/tasks")
    print("  - View agents at: http://localhost:8001/api/agents")
    print("  - Check API docs: http://localhost:8001/docs")


if __name__ == '__main__':
    main()
