#!/usr/bin/env python3
"""
Personal Knowledge Assistant - RAG-based document Q&A system.
"""

import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

from rag_engine import RAGEngine


def setup_environment():
    """Load environment variables."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
    else:
        root_env = Path(__file__).parent.parent.parent.parent / ".env"
        if root_env.exists():
            load_dotenv(root_env)


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Personal Knowledge Assistant - Chat with your documents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add documents (re-adding a changed file replaces the old version)
  %(prog)s add document.pdf notes.md

  # Ask a question
  %(prog)s query "What are the main findings?"

  # See what is indexed
  %(prog)s stats

  # Remove one document, or everything
  %(prog)s remove notes.md
  %(prog)s clear --yes
        """
    )

    parser.add_argument(
        "command",
        choices=["add", "query", "stats", "remove", "clear"],
        help="Command to execute"
    )

    parser.add_argument(
        "args",
        nargs="*",
        help="Arguments for the command"
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of relevant chunks to retrieve (default: 5)"
    )

    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="LLM temperature (default: 0.7)"
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Document chunk size (default: 500)"
    )

    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=50,
        help="Chunk overlap (default: 50)"
    )

    parser.add_argument(
        "--neighbors",
        type=int,
        default=2,
        help="Chunks on each side of the best matches to include as context, so answers "
             "that span several chunks (lists, steps) are complete; 0 disables (default: 2)"
    )

    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        help="Skip the confirmation prompt for 'clear'"
    )

    parser.add_argument(
        "--plain",
        action="store_true",
        help="Print only the answer, without framing or sources (automatic when piped)"
    )

    return parser.parse_args()


def fail(message: str, code: int = 1):
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(code)


def main():
    """Main entry point."""
    setup_environment()
    args = parse_args()

    if args.top_k < 1:
        fail("--top-k must be at least 1")
    if args.neighbors < 0:
        fail("--neighbors cannot be negative")
    if not 0.0 <= args.temperature <= 2.0:
        fail("--temperature must be between 0.0 and 2.0")

    # Cheap checks first, so a typo does not cost a database open
    if args.command in ("add", "remove") and not args.args:
        fail("No files specified")
    if args.command == "query" and not " ".join(args.args).strip():
        fail("No query provided")

    try:
        rag = RAGEngine(
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
            neighbors=args.neighbors
        )
    except ValueError as e:
        fail(str(e))

    try:
        if args.command == "add":
            total_chunks = 0
            counts = {"added": 0, "updated": 0, "unchanged": 0}
            failed = 0
            for file_path in args.args:
                print(f"Processing: {file_path}", file=sys.stderr)
                try:
                    result = rag.add_document(file_path)
                except Exception as e:
                    failed += 1
                    print(f"  Skipped {file_path}: {e}", file=sys.stderr)
                    continue
                counts[result.status] += 1
                total_chunks += result.chunks
                print(f"  {result.status}: {result.chunks} chunks", file=sys.stderr)

            ok = len(args.args) - failed
            summary = (
                f"Indexed {ok} file(s), {total_chunks} chunks "
                f"({counts['added']} new, {counts['updated']} updated, {counts['unchanged']} unchanged)"
            )
            if failed:
                print(f"\n{summary}; {failed} file(s) failed", file=sys.stderr)
                sys.exit(1)
            print(f"\n✓ {summary}")

        elif args.command == "query":
            question = " ".join(args.args).strip()
            if rag.vector_store.collection.count() == 0:
                fail("The knowledge base is empty. Add documents first: assistant.py add <file>")

            interactive = sys.stdout.isatty() and not args.plain
            if interactive:
                print(f"Question: {question}\n")
                print("Searching knowledge base...", file=sys.stderr)

            answer, sources = rag.query(
                question,
                top_k=args.top_k,
                temperature=args.temperature
            )

            if rag.truncated:
                print("Warning: the answer was cut off by the token limit", file=sys.stderr)

            if not interactive:
                print(answer)
                return

            print("\n" + "=" * 70)
            print("Answer:")
            print("=" * 70)
            print(answer)
            print("=" * 70)

            if sources:
                print("\nSources:")
                for src in sources:
                    if src.get('adjacent'):
                        detail = "adjacent context"
                    else:
                        detail = f"similarity: {src['relevance'] * 100:.0f}%"
                        if src.get('keyword_match'):
                            detail += ", keyword match"
                    print(f"\n  [{src['index']}] {Path(src['source']).name} ({detail})")
                    if 'page' in src:
                        print(f"      Page: {src['page']}")
                    print(f"      Preview: {src['preview']}")

        elif args.command == "stats":
            stats = rag.get_stats()
            print("\nKnowledge Base Statistics:")
            print("=" * 70)
            print(f"Collection: {stats['name']}")
            print(f"Documents: {stats['document_count']}")
            print(f"Chunks: {stats['chunk_count']}")
            print(f"Storage: {stats['persist_directory']}")
            for doc in stats["documents"]:
                print(f"  - {doc['source']} ({doc['chunks']} chunks)")
            print("=" * 70)

        elif args.command == "remove":
            missing = 0
            for file_path in args.args:
                removed = rag.remove_document(file_path)
                if removed:
                    print(f"✓ Removed {file_path} ({removed} chunks)")
                else:
                    missing += 1
                    print(f"Not in the knowledge base: {file_path}", file=sys.stderr)
            if missing:
                sys.exit(1)

        elif args.command == "clear":
            if not args.yes:
                if not sys.stdin.isatty():
                    fail("Refusing to clear without confirmation; pass --yes")
                confirm = input("Are you sure you want to clear the knowledge base? (yes/no): ")
                if confirm.strip().lower() not in ("yes", "y"):
                    print("Operation cancelled")
                    return
            rag.clear_knowledge_base()
            print("✓ Knowledge base cleared")

    except KeyboardInterrupt:
        print("\nOperation cancelled", file=sys.stderr)
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
