#!/usr/bin/env python3
"""
Phase 1 Verification Test Script

Tests:
1. Database initialization
2. User registration and authentication
3. Session management
4. Text content submission
5. LLM text classification
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.database import DatabaseManager
from src.core.auth_manager import AuthManager, UserRole
from src.core.llm_client import LLMClient
from dotenv import load_dotenv


def test_database():
    """Test 1: Database initialization"""
    print("\n=== Test 1: Database Initialization ===")

    try:
        db_manager = DatabaseManager()
        db_manager.create_tables()
        print("✓ Database tables created successfully")

        # Verify tables
        with db_manager.get_session() as db:
            from src.core.database import User
            count = db.query(User).count()
            print(f"✓ User table accessible (count: {count})")

        return True
    except Exception as e:
        print(f"✗ Database test failed: {e}")
        return False


def test_authentication():
    """Test 2: User registration and authentication"""
    print("\n=== Test 2: Authentication ===")

    try:
        db_manager = DatabaseManager()

        with db_manager.get_session() as db:
            auth_manager = AuthManager(db)

            # Register user
            success, user, error = auth_manager.register_user(
                username="testuser",
                email="test@example.com",
                password="password123"
            )

            if success:
                print(f"✓ User registered: {user.username}")
            else:
                # User might already exist
                print(f"  User registration: {error}")

            # Authenticate
            success, auth_user, error = auth_manager.authenticate(
                username="testuser",
                password="password123"
            )

            if success:
                print(f"✓ Authentication successful: {auth_user.username}")
            else:
                print(f"✗ Authentication failed: {error}")
                return False

            # Create session
            session_token = auth_manager.create_session(auth_user, "127.0.0.1")
            print(f"✓ Session created: {session_token[:20]}...")

            # Validate session
            success, validated_user, error = auth_manager.validate_session(session_token)

            if success:
                print(f"✓ Session validated: {validated_user.username}")
            else:
                print(f"✗ Session validation failed: {error}")
                return False

            # Cleanup expired sessions
            count = auth_manager.cleanup_expired_sessions()
            print(f"✓ Cleaned up {count} expired sessions")

        return True
    except Exception as e:
        print(f"✗ Authentication test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_rbac():
    """Test 3: Role-based access control"""
    print("\n=== Test 3: Role-Based Access Control ===")

    try:
        db_manager = DatabaseManager()

        with db_manager.get_session() as db:
            auth_manager = AuthManager(db)

            # Create admin user
            success, admin, error = auth_manager.register_user(
                username="admin",
                email="admin@example.com",
                password="admin123",
                role=UserRole.ADMIN
            )

            if success:
                print(f"✓ Admin user created: {admin.username} ({admin.role})")
            else:
                # Might already exist
                admin = auth_manager.get_user_by_username("admin")
                if admin:
                    print(f"  Admin user exists: {admin.username} ({admin.role})")
                else:
                    print(f"✗ Failed to create admin: {error}")
                    return False

            # Test role hierarchy
            regular_user = auth_manager.get_user_by_username("testuser")

            is_admin = auth_manager.is_admin(admin)
            is_moderator = auth_manager.is_moderator(admin)

            print(f"✓ Admin role check: is_admin={is_admin}, is_moderator={is_moderator}")

            is_admin = auth_manager.is_admin(regular_user)
            is_moderator = auth_manager.is_moderator(regular_user)

            print(f"✓ User role check: is_admin={is_admin}, is_moderator={is_moderator}")

        return True
    except Exception as e:
        print(f"✗ RBAC test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_content_submission():
    """Test 4: Content submission"""
    print("\n=== Test 4: Content Submission ===")

    try:
        db_manager = DatabaseManager()

        with db_manager.get_session() as db:
            from src.core.database import ContentItem, ContentType, ContentStatus

            # Get user
            from src.core.database import User
            user = db.query(User).filter(User.username == "testuser").first()

            if not user:
                print("✗ Test user not found")
                return False

            # Create content item
            content = ContentItem(
                user_id=user.id,
                content_type=ContentType.TEXT,
                text_content="This is a test message for content moderation.",
                status=ContentStatus.PENDING,
                priority=0
            )

            db.add(content)
            db.commit()
            db.refresh(content)

            print(f"✓ Content submitted: {content.id}")
            print(f"  Type: {content.content_type}, Status: {content.status}")
            print(f"  Preview: {content.text_content[:50]}...")

        return True
    except Exception as e:
        print(f"✗ Content submission test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_llm_classification():
    """Test 5: LLM text classification"""
    print("\n=== Test 5: LLM Classification ===")

    try:
        # Initialize LLM client (Ollama by default)
        llm_client = LLMClient(provider='ollama')
        print(f"✓ LLM client initialized: {llm_client.provider}/{llm_client.model}")

        # Test clean content
        print("\nTest 5a: Clean Content")
        result = llm_client.classify_text(
            "Hello! This is a friendly message. How are you doing today?"
        )

        print(f"  Category: {result['category']}")
        print(f"  Confidence: {result['confidence']:.2f}")
        print(f"  Is Violation: {result['is_violation']}")
        print(f"  Reasoning: {result['reasoning']}")
        print(f"  Processing Time: {result.get('processing_time_ms', 0):.0f}ms")

        # Test spam content
        print("\nTest 5b: Spam Content")
        result = llm_client.classify_text(
            "BUY NOW! Click here for amazing deals! Limited time offer! www.spam.com"
        )

        print(f"  Category: {result['category']}")
        print(f"  Confidence: {result['confidence']:.2f}")
        print(f"  Is Violation: {result['is_violation']}")
        print(f"  Reasoning: {result['reasoning']}")

        print("\n✓ LLM classification working")

        return True
    except Exception as e:
        print(f"✗ LLM classification test failed: {e}")
        print("  Note: This requires Ollama to be running locally")
        print("  Start Ollama: ollama serve")
        print("  Pull model: ollama pull llama3.2:3b")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all Phase 1 tests"""
    print("=" * 60)
    print("Phase 1 Verification Tests")
    print("=" * 60)

    # Load environment
    load_dotenv()

    # Run tests
    results = {
        "Database": test_database(),
        "Authentication": test_authentication(),
        "RBAC": test_rbac(),
        "Content Submission": test_content_submission(),
        "LLM Classification": test_llm_classification()
    }

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name:.<40} {status}")

    total = len(results)
    passed = sum(1 for p in results.values() if p)

    print("=" * 60)
    print(f"Total: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print("\n✓ Phase 1 verification complete!")
        print("\nNext steps:")
        print("1. Start the server: python server.py")
        print("2. Open browser: http://localhost:8000")
        print("3. Register a user and test the UI")
        return 0
    else:
        print("\n✗ Some tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
