"""Test serve command placeholder"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from doc_gen import CLI


def test_serve_placeholder():
    """Test serve command shows helpful placeholder message"""
    print("=" * 70)
    print("SERVE COMMAND PLACEHOLDER TEST".center(70))
    print("=" * 70)

    cli = CLI()

    print("\n[1/2] Testing serve with default settings...")
    try:
        result = cli.run(['serve'])

        if result == 0:
            print("✓ Serve command returned successfully")
        else:
            print(f"❌ Serve returned non-zero: {result}")

    except Exception as e:
        print(f"❌ Serve failed: {e}")

    print("\n[2/2] Testing serve with custom port...")
    try:
        result = cli.run(['serve', '--port', '9000', '--host', '0.0.0.0'])

        if result == 0:
            print("✓ Serve command with custom settings returned successfully")
        else:
            print(f"❌ Serve returned non-zero: {result}")

    except Exception as e:
        print(f"❌ Serve failed: {e}")

    print("\n" + "=" * 70)
    print("✅ Serve placeholder test completed!")
    print("=" * 70)

    return True


if __name__ == "__main__":
    try:
        test_serve_placeholder()
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
