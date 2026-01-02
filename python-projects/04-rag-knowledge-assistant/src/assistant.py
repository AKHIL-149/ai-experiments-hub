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
  # Add a document to knowledge base
  %(prog)s add document.pdf

  # Ask a question
  %(prog)s query "What are the main findings?"

  # Add multiple documents
  %(prog)s add doc1.txt doc2.pdf doc3.md

  # View statistics
  %(prog)s stats

  # Clear knowledge base
  %(prog)s clear
        """
    )

    parser.add_argument(
        "command",
        choices=["add", "query", "stats", "clear"],
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

    return parser.parse_args()


def main():
    """Main entry point."""
    setup_environment()
    args = parse_args()

    # Initialize RAG engine
    rag = RAGEngine(
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap
    )

    try:
        if args.command == "add":
            if not args.args:
                print("Error: No files specified", file=sys.stderr)
                sys.exit(1)

            total_chunks = 0
            for file_path in args.args:
                try:
                    chunks = rag.add_document(file_path)
                    total_chunks += chunks
                except Exception as e:
                    print(f"Error processing {file_path}: {e}", file=sys.stderr)

            print(f"\n✓ Added {total_chunks} total chunks from {len(args.args)} file(s)")

        elif args.command == "query":
            if not args.args:
                print("Error: No query provided", file=sys.stderr)
                sys.exit(1)

            question = " ".join(args.args)
            print(f"Question: {question}\n")
            print("Searching knowledge base...")

            answer, sources = rag.query(
                question,
                top_k=args.top_k,
                temperature=args.temperature
            )

            print("\n" + "=" * 70)
            print("Answer:")
            print("=" * 70)
            print(answer)
            print("=" * 70)

            if sources:
                print("\nSources:")
                for src in sources:
                    relevance_pct = src['relevance'] * 100
                    print(f"\n  [{src['index']}] {Path(src['source']).name} "
                          f"(relevance: {relevance_pct:.1f}%)")
                    if 'page' in src:
                        print(f"      Page: {src['page']}")
                    print(f"      Preview: {src['preview']}")

        elif args.command == "stats":
            stats = rag.get_stats()
            print("\nKnowledge Base Statistics:")
            print("=" * 70)
            print(f"Collection: {stats['name']}")
            print(f"Total documents: {stats['document_count']}")
            print(f"Storage: {stats['persist_directory']}")
            print("=" * 70)

        elif args.command == "clear":
            confirm = input("Are you sure you want to clear the knowledge base? (yes/no): ")
            if confirm.lower() == "yes":
                rag.clear_knowledge_base()
                print("✓ Knowledge base cleared")
            else:
                print("Operation cancelled")

    except KeyboardInterrupt:
        print("\nOperation cancelled", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
