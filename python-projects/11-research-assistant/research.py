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
    """Perform research query (Phase 3)."""
    print("=== Research Query ===\n")

    # Validate session
    session_file = Path.home() / '.research_session'

    if not session_file.exists():
        print("✗ No active session. Please login first.")
        print("  Run: python research.py login")
        sys.exit(1)

    token = session_file.read_text().strip()

    # Initialize managers
    db_manager, auth_manager = init_managers()
    db_session = db_manager.get_session()

    try:
        # Validate session
        valid, user, error = auth_manager.validate_session(db_session, token)

        if not valid:
            print(f"✗ Session invalid: {error}")
            session_file.unlink()
            sys.exit(1)

        print(f"User: {user.username}")
        print(f"Query: {args.query_text}\n")

        # Parse source options
        sources = [s.strip().lower() for s in args.sources.split(',')]
        search_web = 'web' in sources
        search_arxiv = 'arxiv' in sources
        search_documents = 'documents' in sources

        print(f"Sources: {', '.join(sources)}")
        print(f"Max results: {args.max_results}")
        print(f"Citation style: {args.citations}")
        print()

        # Initialize research components
        print("Initializing research components...")

        from src.core.web_search_client import WebSearchClient
        from src.core.arxiv_client import ArXivClient
        from src.core.llm_client import LLMClient
        from src.core.research_orchestrator import ResearchOrchestrator
        from src.services.cache_manager import CacheManager
        from src.utils.report_generator import ReportGenerator

        # Initialize cache manager
        cache_dir = os.getenv('CACHE_DIR', './data/cache')
        cache_enabled = os.getenv('ENABLE_CACHE', 'true').lower() == 'true'
        cache_manager = CacheManager(cache_dir=cache_dir, enable_cache=cache_enabled)

        # Initialize web search client
        web_client = None
        if search_web:
            web_client = WebSearchClient(
                provider='duckduckgo',
                cache_manager=cache_manager
            )

        # Initialize ArXiv client
        arxiv_client = None
        if search_arxiv:
            arxiv_cache_dir = os.getenv('ARXIV_CACHE_DIR', './data/papers')
            arxiv_client = ArXivClient(cache_dir=arxiv_cache_dir)

        # Initialize LLM client
        llm_provider = os.getenv('LLM_PROVIDER', 'ollama').lower()
        llm_model = os.getenv('LLM_MODEL')
        llm_api_key = os.getenv('OPENAI_API_KEY') if llm_provider == 'openai' else os.getenv('ANTHROPIC_API_KEY')

        llm_client = LLMClient(
            provider=llm_provider,
            model=llm_model,
            api_key=llm_api_key
        )

        # Initialize embedding model (optional)
        embedding_model = None
        try:
            from sentence_transformers import SentenceTransformer
            embedding_model_name = os.getenv('EMBEDDING_MODEL', 'all-MiniLM-L6-v2')
            print(f"Loading embedding model: {embedding_model_name}")
            embedding_model = SentenceTransformer(embedding_model_name)
        except Exception as e:
            print(f"Warning: Failed to load embedding model: {e}")
            print("Continuing without semantic similarity (using keyword matching)")

        # Initialize research orchestrator
        database_url = os.getenv('DATABASE_URL', 'sqlite:///./data/database.db')
        orchestrator = ResearchOrchestrator(
            db_path=database_url,
            web_search_client=web_client,
            arxiv_client=arxiv_client,
            llm_client=llm_client,
            embedding_model=embedding_model,
            cache_manager=cache_manager
        )

        print("✓ Components initialized\n")

        # Conduct research
        print("Starting research...\n")

        results = orchestrator.conduct_research(
            user_id=user.id,
            query=args.query_text,
            search_web=search_web,
            search_arxiv=search_arxiv,
            search_documents=search_documents,
            max_sources=args.max_results,
            citation_style=args.citations
        )

        # Display results
        print("\n" + "="*80)
        print("RESEARCH RESULTS")
        print("="*80 + "\n")

        print(f"Query ID: {results['query_id']}\n")

        print("Summary:")
        print("-" * 80)
        print(results['summary'])
        print()

        if results['findings']:
            print(f"\nFindings ({len(results['findings'])}):")
            print("-" * 80)
            for i, finding in enumerate(results['findings'], 1):
                print(f"\n{i}. {finding['text']}")
                print(f"   Type: {finding['type']} | Confidence: {finding['confidence']:.2f} | Sources: {finding['sources']}")

        if results.get('stats'):
            stats = results['stats']
            print(f"\n\nStatistics:")
            print("-" * 80)
            print(f"Total sources found: {stats.get('total_sources', 0)}")
            print(f"Unique sources: {stats.get('unique_sources', 0)}")
            print(f"Sources used: {stats.get('used_sources', 0)}")
            print(f"Findings generated: {stats.get('findings', 0)}")
            print(f"Average confidence: {stats.get('avg_confidence', 0):.2f}")
            print(f"Processing time: {stats.get('processing_time', 0):.1f}s")

        # Generate report
        if args.output:
            print(f"\n\nGenerating {args.format} report...")

            output_dir = os.getenv('OUTPUT_DIR', './data/output')
            report_gen = ReportGenerator(output_dir=output_dir)

            # Use custom filename if provided
            filename = Path(args.output).stem if args.output else None

            report_path = report_gen.generate_report(
                research_data=results,
                format=args.format,
                filename=filename
            )

            print(f"✓ Report saved to: {report_path}")

        print("\n✓ Research complete!")

    except Exception as e:
        print(f"\n✗ Research failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        db_session.close()


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

  # Research query (Phase 3)
  python research.py query "quantum computing applications" --sources web,arxiv
  python research.py query "climate change impacts" --sources web,arxiv --output report --format html

Phase 1 Status: ✓ Authentication & Database
Phase 2 Status: ✓ Web Search, ArXiv, Citations, Caching
Phase 3 Status: ✓ Synthesis, Deduplication, Ranking, Report Generation
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
