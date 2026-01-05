"""Test all language parsers"""
import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.parsers.parser_registry import ParserRegistry


def print_section(title: str):
    """Print a formatted section header"""
    print(f"\n{'=' * 70}")
    print(f"{title:^70}")
    print('=' * 70)


def print_parsed_module(parsed, language: str):
    """Print parsed module information"""
    print(f"\n📄 Module: {Path(parsed.file_path).name}")
    print(f"   Language: {language.upper()}")
    if parsed.module_docstring:
        doc_preview = parsed.module_docstring[:80].replace('\n', ' ')
        print(f"   Docstring: {doc_preview}...")

    print(f"\n📦 Imports ({len(parsed.imports)}):")
    for imp in parsed.imports[:5]:  # Show first 5
        print(f"   - {imp}")
    if len(parsed.imports) > 5:
        print(f"   ... and {len(parsed.imports) - 5} more")

    if parsed.global_variables:
        print(f"\n🌍 Global Variables ({len(parsed.global_variables)}):")
        for var in parsed.global_variables[:5]:
            type_info = f": {var.get('type', 'unknown')}" if var.get('type') else ""
            value = str(var.get('value', ''))[:30]
            print(f"   - {var['name']}{type_info} = {value}...")

    print(f"\n🔧 Functions ({len(parsed.functions)}):")
    for func in parsed.functions:
        params = ", ".join([p.name for p in func.parameters])
        return_type = f" -> {func.return_type}" if func.return_type else ""
        async_marker = "async " if func.is_async else ""
        print(f"\n   {async_marker}{func.name}({params}){return_type}")
        print(f"      Line: {func.line_number}, Complexity: {func.complexity}")
        if func.decorators:
            print(f"      Decorators: {', '.join(func.decorators)}")

    print(f"\n🏛️  Classes ({len(parsed.classes)}):")
    for cls in parsed.classes[:3]:  # Show first 3 classes
        inheritance = f" extends {', '.join(cls.base_classes)}" if cls.base_classes else ""
        print(f"\n   class {cls.name}{inheritance}:")
        print(f"      Line: {cls.line_number}")
        if cls.decorators:
            print(f"      Decorators: {', '.join(cls.decorators)}")
        if cls.methods:
            print(f"      Methods: {len(cls.methods)} ({', '.join([m.name for m in cls.methods[:3]])}...)")
        if cls.attributes:
            print(f"      Attributes: {len(cls.attributes)}")
    if len(parsed.classes) > 3:
        print(f"\n   ... and {len(parsed.classes) - 3} more classes")


def test_parser_registry():
    """Test the parser registry with all parsers"""
    print_section("PARSER REGISTRY TEST")

    registry = ParserRegistry()

    print(f"\n📚 Available Parsers:")
    for parser_name in registry.list_available_parsers():
        print(f"   - {parser_name}")

    print(f"\n📋 Supported Extensions:")
    for ext in sorted(registry.get_supported_extensions()):
        print(f"   - {ext}")

    print(f"\n✅ Parser registry initialized successfully")


def test_python_parser():
    """Test Python parser"""
    print_section("PYTHON PARSER TEST")

    registry = ParserRegistry()
    sample_file = project_root / "tests" / "fixtures" / "sample.py"

    try:
        parser = registry.get_parser(str(sample_file))
        print(f"✓ Selected parser: {parser.__class__.__name__}")

        parsed = parser.parse_file(str(sample_file))
        print_parsed_module(parsed, "python")

        print(f"\n✅ Python parser test PASSED")
        return True
    except Exception as e:
        print(f"\n❌ Python parser test FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_javascript_parser():
    """Test JavaScript parser"""
    print_section("JAVASCRIPT PARSER TEST")

    try:
        from src.parsers.javascript_parser import JavaScriptParser

        sample_file = project_root / "tests" / "fixtures" / "sample.js"
        parser = JavaScriptParser()

        print(f"✓ Selected parser: {parser.__class__.__name__}")

        # Check if Node.js is available
        try:
            parsed = parser.parse_file(str(sample_file))
            print_parsed_module(parsed, "javascript")
            print(f"\n✅ JavaScript parser test PASSED")
            return True
        except RuntimeError as e:
            if "Node.js" in str(e):
                print(f"\n⚠️  JavaScript parser test SKIPPED: {str(e)}")
                print("   Install Node.js and run: npm install")
                return None  # Skip, not a failure
            raise

    except Exception as e:
        print(f"\n❌ JavaScript parser test FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_java_parser():
    """Test Java parser"""
    print_section("JAVA PARSER TEST")

    try:
        from src.parsers.java_parser import JavaParser

        sample_file = project_root / "tests" / "fixtures" / "Sample.java"

        try:
            parser = JavaParser()
            print(f"✓ Selected parser: {parser.__class__.__name__}")

            parsed = parser.parse_file(str(sample_file))
            print_parsed_module(parsed, "java")
            print(f"\n✅ Java parser test PASSED")
            return True

        except ImportError as e:
            if "javalang" in str(e):
                print(f"\n⚠️  Java parser test SKIPPED: {str(e)}")
                print("   Install javalang: pip install javalang")
                return None  # Skip, not a failure
            raise

    except Exception as e:
        print(f"\n❌ Java parser test FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_parser_selection():
    """Test automatic parser selection"""
    print_section("PARSER SELECTION TEST")

    registry = ParserRegistry()

    test_files = [
        ("example.py", "PythonParser"),
        ("module.js", "JavaScriptParser"),
        ("Component.jsx", "JavaScriptParser"),
        ("app.ts", "JavaScriptParser"),
        ("Main.java", "JavaParser"),
    ]

    all_passed = True
    for filename, expected_parser in test_files:
        try:
            parser = registry.get_parser(filename)
            actual_parser = parser.__class__.__name__

            if actual_parser == expected_parser:
                print(f"✓ {filename:20} -> {actual_parser}")
            else:
                print(f"✗ {filename:20} -> Expected {expected_parser}, got {actual_parser}")
                all_passed = False

        except ValueError as e:
            print(f"✗ {filename:20} -> ERROR: {str(e)}")
            all_passed = False

    # Test unsupported extension
    try:
        registry.get_parser("file.unknown")
        print(f"✗ Should have raised error for unsupported extension")
        all_passed = False
    except ValueError:
        print(f"✓ Correctly raised error for unsupported extension")

    if all_passed:
        print(f"\n✅ Parser selection test PASSED")
    else:
        print(f"\n❌ Parser selection test FAILED")

    return all_passed


def main():
    """Run all tests"""
    print("=" * 70)
    print("CODE DOCUMENTATION GENERATOR - MULTI-LANGUAGE PARSER TESTS".center(70))
    print("=" * 70)

    # Track results
    results = {}

    # Test parser registry
    test_parser_registry()

    # Test parser selection
    results['selection'] = test_parser_selection()

    # Test individual parsers
    results['python'] = test_python_parser()
    results['javascript'] = test_javascript_parser()
    results['java'] = test_java_parser()

    # Print summary
    print_section("TEST SUMMARY")

    passed = sum(1 for r in results.values() if r is True)
    failed = sum(1 for r in results.values() if r is False)
    skipped = sum(1 for r in results.values() if r is None)

    print(f"\n{'Test':<20} {'Result':<15}")
    print("-" * 35)
    for name, result in results.items():
        if result is True:
            status = "✅ PASSED"
        elif result is False:
            status = "❌ FAILED"
        else:
            status = "⚠️  SKIPPED"
        print(f"{name.capitalize():<20} {status:<15}")

    print(f"\n{'Total:':<20} {passed} passed, {failed} failed, {skipped} skipped")

    if failed == 0:
        print("\n🎉 All available parsers are working correctly!")
        if skipped > 0:
            print(f"   (Note: {skipped} test(s) skipped due to missing dependencies)")
        return 0
    else:
        print(f"\n❌ {failed} test(s) failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
