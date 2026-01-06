"""Test package installation and imports"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def print_section(title: str):
    """Print formatted section header"""
    print(f"\n{'=' * 70}")
    print(f"{title:^70}")
    print('=' * 70)


def test_core_imports():
    """Test importing core components"""
    print_section("CORE IMPORTS TEST")

    print("\n[1/4] Testing DocGenerator import...")
    try:
        from src.core import DocGenerator
        print(f"✓ DocGenerator imported: {DocGenerator}")
    except ImportError as e:
        print(f"❌ Failed to import DocGenerator: {e}")
        return False

    print("\n[2/4] Testing LLMClient import...")
    try:
        from src.core import LLMClient
        print(f"✓ LLMClient imported: {LLMClient}")
    except ImportError as e:
        print(f"❌ Failed to import LLMClient: {e}")
        return False

    print("\n[3/4] Testing AIExplainer import...")
    try:
        from src.core import AIExplainer
        print(f"✓ AIExplainer imported: {AIExplainer}")
    except ImportError as e:
        print(f"❌ Failed to import AIExplainer: {e}")
        return False

    print("\n[4/4] Testing CacheManager import...")
    try:
        from src.core import CacheManager
        print(f"✓ CacheManager imported: {CacheManager}")
    except ImportError as e:
        print(f"❌ Failed to import CacheManager: {e}")
        return False

    print("\n" + "=" * 70)
    print("✅ Core imports test completed!")
    print("=" * 70)

    return True


def test_parser_imports():
    """Test importing parser components"""
    print_section("PARSER IMPORTS TEST")

    print("\n[1/3] Testing ParserRegistry import...")
    try:
        from src.parsers.parser_registry import ParserRegistry
        registry = ParserRegistry()
        print(f"✓ ParserRegistry imported and instantiated")
        print(f"   Available parsers: {len(registry.parsers)}")
    except ImportError as e:
        print(f"❌ Failed to import ParserRegistry: {e}")
        return False

    print("\n[2/3] Testing data models import...")
    try:
        from src.parsers.models import ParsedModule, FunctionInfo, ClassInfo
        print(f"✓ Data models imported: ParsedModule, FunctionInfo, ClassInfo")
    except ImportError as e:
        print(f"❌ Failed to import models: {e}")
        return False

    print("\n[3/3] Testing individual parsers...")
    try:
        from src.parsers.python_parser import PythonParser
        from src.parsers.javascript_parser import JavaScriptParser
        from src.parsers.java_parser import JavaParser
        print(f"✓ All parsers imported: Python, JavaScript, Java")
    except ImportError as e:
        print(f"❌ Failed to import parsers: {e}")
        return False

    print("\n" + "=" * 70)
    print("✅ Parser imports test completed!")
    print("=" * 70)

    return True


def test_formatter_imports():
    """Test importing formatter components"""
    print_section("FORMATTER IMPORTS TEST")

    print("\n[1/4] Testing MarkdownFormatter import...")
    try:
        from src.formatters import MarkdownFormatter
        formatter = MarkdownFormatter()
        print(f"✓ MarkdownFormatter imported and instantiated")
    except ImportError as e:
        print(f"❌ Failed to import MarkdownFormatter: {e}")
        return False

    print("\n[2/4] Testing HTMLFormatter import...")
    try:
        from src.formatters import HTMLFormatter
        formatter = HTMLFormatter()
        print(f"✓ HTMLFormatter imported and instantiated")
    except ImportError as e:
        print(f"❌ Failed to import HTMLFormatter: {e}")
        return False

    print("\n[3/4] Testing JSONFormatter import...")
    try:
        from src.formatters import JSONFormatter
        formatter = JSONFormatter()
        print(f"✓ JSONFormatter imported and instantiated")
    except ImportError as e:
        print(f"❌ Failed to import JSONFormatter: {e}")
        return False

    print("\n[4/4] Testing DocstringFormatter import...")
    try:
        from src.formatters import DocstringFormatter
        formatter = DocstringFormatter()
        print(f"✓ DocstringFormatter imported and instantiated")
    except ImportError as e:
        print(f"❌ Failed to import DocstringFormatter: {e}")
        return False

    print("\n" + "=" * 70)
    print("✅ Formatter imports test completed!")
    print("=" * 70)

    return True


def test_package_api():
    """Test package-level API imports"""
    print_section("PACKAGE API TEST")

    print("\n[1/3] Testing package __init__ imports...")
    try:
        from src import (
            DocGenerator,
            ParserRegistry,
            MarkdownFormatter,
            FileDiscovery
        )
        print(f"✓ Package-level imports successful")
    except ImportError as e:
        print(f"❌ Failed to import from package: {e}")
        return False

    print("\n[2/3] Testing version and metadata...")
    try:
        from src import __version__, __author__
        print(f"✓ Version: {__version__}")
        print(f"✓ Author: {__author__}")
    except ImportError as e:
        print(f"❌ Failed to import metadata: {e}")
        return False

    print("\n[3/3] Testing __all__ export...")
    try:
        from src import __all__
        print(f"✓ __all__ exports {len(__all__)} items:")
        for item in __all__:
            print(f"   • {item}")
    except ImportError as e:
        print(f"❌ Failed to import __all__: {e}")
        return False

    print("\n" + "=" * 70)
    print("✅ Package API test completed!")
    print("=" * 70)

    return True


def test_cli_module():
    """Test CLI module import"""
    print_section("CLI MODULE TEST")

    print("\n[1/2] Testing doc_gen module import...")
    try:
        import doc_gen
        print(f"✓ doc_gen module imported")
    except ImportError as e:
        print(f"❌ Failed to import doc_gen: {e}")
        return False

    print("\n[2/2] Testing CLI class...")
    try:
        from doc_gen import CLI, main
        cli = CLI()
        print(f"✓ CLI class instantiated")
        print(f"✓ main function available")
    except (ImportError, AttributeError) as e:
        print(f"❌ Failed to import CLI: {e}")
        return False

    print("\n" + "=" * 70)
    print("✅ CLI module test completed!")
    print("=" * 70)

    return True


def main():
    """Run all installation tests"""
    print("\n" + "=" * 70)
    print("PACKAGE INSTALLATION TEST SUITE".center(70))
    print("=" * 70)

    results = []

    # Run all tests
    results.append(("Core Imports", test_core_imports()))
    results.append(("Parser Imports", test_parser_imports()))
    results.append(("Formatter Imports", test_formatter_imports()))
    results.append(("Package API", test_package_api()))
    results.append(("CLI Module", test_cli_module()))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY".center(70))
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {test_name}")

    print("\n" + "=" * 70)
    print(f"Results: {passed}/{total} tests passed".center(70))
    print("=" * 70)

    return 0 if passed == total else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Tests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Test suite failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
