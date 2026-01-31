#!/usr/bin/env python3
"""
Phase 1 Verification Script

Tests that all Phase 1 components are working correctly:
- Database models and connections
- User registration
- Authentication
- Session management
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.database import DatabaseManager
from src.core.auth_manager import AuthManager


def test_database():
    """Test database initialization."""
    print("\n1. Testing Database...")
    try:
        db_manager = DatabaseManager('sqlite:///:memory:')
        db_manager.create_tables()
        print("   ✓ Database tables created successfully")
        return db_manager
    except Exception as e:
        print(f"   ✗ Database test failed: {e}")
        return None


def test_registration(db_manager):
    """Test user registration."""
    print("\n2. Testing User Registration...")
    try:
        auth_manager = AuthManager()
        db_session = db_manager.get_session()

        success, user, error = auth_manager.register_user(
            db_session,
            username='test_user',
            email='test@example.com',
            password='testpassword123'
        )

        if success:
            print(f"   ✓ User registered: {user.username}")
            return auth_manager, user
        else:
            print(f"   ✗ Registration failed: {error}")
            return None, None

    except Exception as e:
        print(f"   ✗ Registration test failed: {e}")
        return None, None


def test_authentication(db_manager, auth_manager):
    """Test user authentication."""
    print("\n3. Testing Authentication...")
    try:
        db_session = db_manager.get_session()

        success, user, error = auth_manager.authenticate(
            db_session,
            username='test_user',
            password='testpassword123'
        )

        if success:
            print(f"   ✓ Authentication successful for: {user.username}")
            return user
        else:
            print(f"   ✗ Authentication failed: {error}")
            return None

    except Exception as e:
        print(f"   ✗ Authentication test failed: {e}")
        return None


def test_session_management(db_manager, auth_manager, user):
    """Test session creation and validation."""
    print("\n4. Testing Session Management...")
    try:
        db_session = db_manager.get_session()

        # Create session
        success, session, error = auth_manager.create_session(db_session, user)

        if not success:
            print(f"   ✗ Session creation failed: {error}")
            return False

        print(f"   ✓ Session created: {session.id[:16]}...")

        # Validate session
        valid, validated_user, error = auth_manager.validate_session(db_session, session.id)

        if valid:
            print(f"   ✓ Session validation successful")
        else:
            print(f"   ✗ Session validation failed: {error}")
            return False

        # Delete session
        success, error = auth_manager.delete_session(db_session, session.id)

        if success:
            print(f"   ✓ Session deletion successful")
        else:
            print(f"   ✗ Session deletion failed: {error}")
            return False

        return True

    except Exception as e:
        print(f"   ✗ Session management test failed: {e}")
        return False


def test_password_hashing(db_manager):
    """Test bcrypt password hashing."""
    print("\n5. Testing Password Security...")
    try:
        auth_manager = AuthManager()
        db_session = db_manager.get_session()

        # Register user
        success, user, error = auth_manager.register_user(
            db_session,
            username='hash_test',
            email='hash@example.com',
            password='mypassword'
        )

        if not success:
            print(f"   ✗ User creation failed: {error}")
            return False

        # Verify password is hashed
        if user.password_hash.startswith('$2b$'):
            print(f"   ✓ Password properly hashed with bcrypt")
        else:
            print(f"   ✗ Password not properly hashed")
            return False

        # Verify cannot login with wrong password
        success, _, error = auth_manager.authenticate(
            db_session,
            username='hash_test',
            password='wrongpassword'
        )

        if not success:
            print(f"   ✓ Wrong password rejected")
        else:
            print(f"   ✗ Wrong password accepted (security issue!)")
            return False

        return True

    except Exception as e:
        print(f"   ✗ Password hashing test failed: {e}")
        return False


def main():
    """Run all Phase 1 verification tests."""
    print("=" * 60)
    print("Phase 1 Verification - Database & Authentication")
    print("=" * 60)

    all_passed = True

    # Test database
    db_manager = test_database()
    if not db_manager:
        all_passed = False
        print("\n✗ Database test failed. Cannot continue.")
        return

    # Test registration
    auth_manager, user = test_registration(db_manager)
    if not auth_manager or not user:
        all_passed = False
        print("\n✗ Registration test failed. Cannot continue.")
        return

    # Test authentication
    authenticated_user = test_authentication(db_manager, auth_manager)
    if not authenticated_user:
        all_passed = False

    # Test session management
    if not test_session_management(db_manager, auth_manager, user):
        all_passed = False

    # Test password security
    if not test_password_hashing(db_manager):
        all_passed = False

    # Summary
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL PHASE 1 TESTS PASSED")
        print("\nPhase 1 is ready for review and git commit!")
        print("\nNext steps:")
        print("  1. Review the implementation")
        print("  2. Run unit tests: pytest tests/ -v")
        print("  3. Try the CLI: python research.py --help")
        print("  4. Commit to git when ready")
    else:
        print("✗ SOME TESTS FAILED")
        print("\nPlease review the failures above before proceeding.")
    print("=" * 60)


if __name__ == '__main__':
    main()
