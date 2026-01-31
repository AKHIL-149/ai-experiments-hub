#!/usr/bin/env python3
"""
Research Assistant CLI

Phase 1: User registration and authentication
Phase 2+: Research query operations
"""

import argparse
import sys
import os
from pathlib import Path
import getpass
from dotenv import load_dotenv

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.core.database import DatabaseManager
from src.core.auth_manager import AuthManager

# Load environment variables
load_dotenv()


def init_managers():
    """Initialize database and auth managers."""
    database_url = os.getenv('DATABASE_URL', 'sqlite:///./data/database.db')
    session_ttl = int(os.getenv('SESSION_TTL_DAYS', '30'))

    db_manager = DatabaseManager(database_url)
    auth_manager = AuthManager(session_ttl_days=session_ttl)

    return db_manager, auth_manager


def cmd_init(args):
    """Initialize database tables."""
    print("Initializing database...")
    db_manager, _ = init_managers()
    db_manager.create_tables()
    print("✓ Database tables created successfully")


def cmd_register(args):
    """Register a new user."""
    print("=== User Registration ===\n")

    # Get credentials
    username = args.username or input("Username: ")
    email = args.email or input("Email: ")

    if args.password:
        password = args.password
    else:
        password = getpass.getpass("Password: ")
        password_confirm = getpass.getpass("Confirm password: ")

        if password != password_confirm:
            print("✗ Error: Passwords do not match")
            sys.exit(1)

    # Register user
    db_manager, auth_manager = init_managers()
    db_session = db_manager.get_session()

    try:
        success, user, error = auth_manager.register_user(
            db_session,
            username=username,
            email=email,
            password=password
        )

        if success:
            print(f"\n✓ User '{user.username}' registered successfully!")
            print(f"  User ID: {user.id}")
            print(f"  Email: {user.email}")
        else:
            print(f"\n✗ Registration failed: {error}")
            sys.exit(1)

    finally:
        db_session.close()


def cmd_login(args):
    """Login and create session."""
    print("=== User Login ===\n")

    # Get credentials
    username = args.username or input("Username: ")

    if args.password:
        password = args.password
    else:
        password = getpass.getpass("Password: ")

    # Authenticate
    db_manager, auth_manager = init_managers()
    db_session = db_manager.get_session()

    try:
        # Authenticate user
        success, user, error = auth_manager.authenticate(
            db_session,
            username=username,
            password=password
        )

        if not success:
            print(f"\n✗ Login failed: {error}")
            sys.exit(1)

        # Create session
        success, session, error = auth_manager.create_session(db_session, user)

        if success:
            print(f"\n✓ Login successful!")
            print(f"  User: {user.username}")
            print(f"  Session token: {session.id}")
            print(f"  Expires: {session.expires_at.strftime('%Y-%m-%d %H:%M:%S')}")

            # Save session token to file for CLI usage
            session_file = Path.home() / '.research_session'
            session_file.write_text(session.id)
            print(f"\n  Session saved to: {session_file}")
        else:
            print(f"\n✗ Failed to create session: {error}")
            sys.exit(1)

    finally:
        db_session.close()


def cmd_logout(args):
    """Logout and delete session."""
    print("=== User Logout ===\n")

    # Read session token
    session_file = Path.home() / '.research_session'

    if not session_file.exists():
        print("✗ No active session found")
        sys.exit(1)

    token = session_file.read_text().strip()

    # Delete session
    db_manager, auth_manager = init_managers()
    db_session = db_manager.get_session()

    try:
        success, error = auth_manager.delete_session(db_session, token)

        if success:
            session_file.unlink()
            print("✓ Logged out successfully")
        else:
            print(f"✗ Logout failed: {error}")
            sys.exit(1)

    finally:
        db_session.close()


def cmd_whoami(args):
    """Show current logged-in user."""
    print("=== Current User ===\n")

    # Read session token
    session_file = Path.home() / '.research_session'

    if not session_file.exists():
        print("✗ No active session. Please login first.")
        sys.exit(1)

    token = session_file.read_text().strip()

    # Validate session
    db_manager, auth_manager = init_managers()
    db_session = db_manager.get_session()

    try:
        valid, user, error = auth_manager.validate_session(db_session, token)

        if valid:
            print(f"Username: {user.username}")
            print(f"Email: {user.email}")
            print(f"User ID: {user.id}")
            print(f"Created: {user.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print(f"✗ Session invalid: {error}")
            session_file.unlink()
            sys.exit(1)

    finally:
        db_session.close()


def cmd_query(args):
    """Perform research query (Phase 2+)."""
    print("✗ Research query command not yet implemented (Phase 2)")
    print("  Coming soon: web search, ArXiv, and document synthesis")
    sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Research Assistant CLI - Multi-source AI research with citations',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize database
  python research.py init

  # Register new user
  python research.py register --username myuser --email user@example.com

  # Login
  python research.py login --username myuser

  # Check current user
  python research.py whoami

  # Logout
  python research.py logout

  # Research query (Phase 2+)
  python research.py query "quantum computing applications" --sources web,arxiv

Phase 1 Status: ✓ Authentication & Database
Phase 2 Status: 🚧 Research Operations (coming soon)
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Init command
    parser_init = subparsers.add_parser('init', help='Initialize database tables')
    parser_init.set_defaults(func=cmd_init)

    # Register command
    parser_register = subparsers.add_parser('register', help='Register new user')
    parser_register.add_argument('--username', help='Username (3-50 characters)')
    parser_register.add_argument('--email', help='Email address')
    parser_register.add_argument('--password', help='Password (min 8 characters) - will prompt if not provided')
    parser_register.set_defaults(func=cmd_register)

    # Login command
    parser_login = subparsers.add_parser('login', help='Login and create session')
    parser_login.add_argument('--username', help='Username')
    parser_login.add_argument('--password', help='Password - will prompt if not provided')
    parser_login.set_defaults(func=cmd_login)

    # Logout command
    parser_logout = subparsers.add_parser('logout', help='Logout and delete session')
    parser_logout.set_defaults(func=cmd_logout)

    # Whoami command
    parser_whoami = subparsers.add_parser('whoami', help='Show current logged-in user')
    parser_whoami.set_defaults(func=cmd_whoami)

    # Query command (Phase 2+)
    parser_query = subparsers.add_parser('query', help='Perform research query (Phase 2+)')
    parser_query.add_argument('query_text', help='Research question')
    parser_query.add_argument('--sources', default='web,arxiv,documents',
                              help='Comma-separated: web, arxiv, documents')
    parser_query.add_argument('--max-results', type=int, default=20,
                              help='Maximum number of sources (default: 20)')
    parser_query.add_argument('--citations', default='APA',
                              choices=['APA', 'MLA', 'Chicago', 'IEEE'],
                              help='Citation style (default: APA)')
    parser_query.add_argument('--output', help='Output file path')
    parser_query.add_argument('--format', default='markdown',
                              choices=['markdown', 'html', 'json', 'pdf'],
                              help='Output format (default: markdown)')
    parser_query.set_defaults(func=cmd_query)

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Execute command
    args.func(args)


if __name__ == '__main__':
    main()
