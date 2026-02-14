#!/usr/bin/env python3
"""
Create a moderator user for accessing the admin dashboard
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.database import DatabaseManager, User, UserRole
from src.core.auth_manager import AuthManager
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize
db_manager = DatabaseManager(os.getenv('DATABASE_URL'))
auth_manager = AuthManager(db_manager, 30)

def create_moderator(username, email, password, role='moderator'):
    """Create a moderator or admin user"""

    with db_manager.get_session() as db:
        # Check if user exists
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            print(f"❌ User '{username}' already exists")
            return False

        # Check email
        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            print(f"❌ Email '{email}' already in use")
            return False

        # Create auth manager with db session
        session_auth = AuthManager(db, 30)

        # Create user
        success, user, error = session_auth.register_user(
            username=username,
            email=email,
            password=password
        )

        if not success:
            print(f"❌ Failed to create user: {error}")
            return False

        # Update role
        user_obj = db.query(User).filter(User.id == user.id).first()
        if role == 'admin':
            user_obj.role = UserRole.ADMIN
        else:
            user_obj.role = UserRole.MODERATOR
        db.commit()

    print(f"✅ Created {role} user: {username}")
    print(f"   Email: {email}")
    print(f"   Password: {password}")
    print(f"   Role: {role.upper()}")
    print(f"\n📍 Access admin dashboard at: http://localhost:{os.getenv('PORT', '8001')}/admin/dashboard")
    print(f"   (Login first at http://localhost:{os.getenv('PORT', '8001')})")

    return True

if __name__ == "__main__":
    import getpass

    print("=== Create Moderator/Admin User ===\n")

    username = input("Username: ").strip()
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ").strip()

    role_choice = input("Role (1=moderator, 2=admin) [1]: ").strip()
    role = 'admin' if role_choice == '2' else 'moderator'

    create_moderator(username, email, password, role)
