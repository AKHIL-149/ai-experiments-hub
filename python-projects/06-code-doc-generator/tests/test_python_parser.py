"""Test the Python parser"""
import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.parsers.python_parser import PythonParser
from src.parsers.parser_registry import ParserRegistry


def test_python_parser():
    """Test parsing the sample Python file"""
    print("=" * 60)
    print("Testing Python Parser")
    print("=" * 60)

    # Get sample file path
    sample_file = project_root / "tests" / "fixtures" / "sample.py"

    # Initialize parser
    parser = PythonParser()

    # Parse the file
    print(f"\nParsing: {sample_file}")
    parsed = parser.parse_file(str(sample_file))

    # Print results
    print(f"\n📄 Module: {parsed.file_path}")
    print(f"   Language: {parsed.language}")
    print(f"   Docstring: {parsed.module_docstring[:80]}..." if parsed.module_docstring else "   No module docstring")

    print(f"\n📦 Imports ({len(parsed.imports)}):")
    for imp in parsed.imports:
        print(f"   - {imp}")

    print(f"\n🌍 Global Variables ({len(parsed.global_variables)}):")
    for var in parsed.global_variables:
        type_info = f": {var['type']}" if var.get('type') else ""
        print(f"   - {var['name']}{type_info} = {var['value'][:30]}...")

    print(f"\n🔧 Functions ({len(parsed.functions)}):")
    for func in parsed.functions:
        params = ", ".join([
            f"{p.name}: {p.type_hint}" if p.type_hint else p.name
            for p in func.parameters
        ])
        return_type = f" -> {func.return_type}" if func.return_type else ""
        async_marker = "async " if func.is_async else ""
        print(f"\n   {async_marker}def {func.name}({params}){return_type}")
        print(f"      Line: {func.line_number}")
        print(f"      Complexity: {func.complexity}")
        if func.decorators:
            print(f"      Decorators: {', '.join(func.decorators)}")
        if func.docstring:
            print(f"      Docstring: {func.docstring[:60]}...")

    print(f"\n🏛️  Classes ({len(parsed.classes)}):")
    for cls in parsed.classes:
        inheritance = f"({', '.join(cls.base_classes)})" if cls.base_classes else ""
        print(f"\n   class {cls.name}{inheritance}:")
        print(f"      Line: {cls.line_number}")
        if cls.docstring:
            print(f"      Docstring: {cls.docstring[:60]}...")

        if cls.attributes:
            print(f"      Attributes ({len(cls.attributes)}):")
            for attr in cls.attributes:
                type_info = f": {attr['type']}" if attr.get('type') else ""
                print(f"         - {attr['name']}{type_info}")

        if cls.methods:
            print(f"      Methods ({len(cls.methods)}):")
            for method in cls.methods:
                async_marker = "async " if method.is_async else ""
                static_marker = "@staticmethod " if method.is_static else ""
                class_marker = "@classmethod " if method.is_classmethod else ""
                print(f"         - {static_marker}{class_marker}{async_marker}{method.name}()")

    print("\n" + "=" * 60)
    print("✅ Parser test completed successfully!")
    print("=" * 60)


def test_parser_registry():
    """Test the parser registry"""
    print("\n" + "=" * 60)
    print("Testing Parser Registry")
    print("=" * 60)

    registry = ParserRegistry()

    print(f"\n📚 Available parsers: {registry.list_available_parsers()}")
    print(f"📋 Supported extensions: {registry.get_supported_extensions()}")

    # Test getting parser for Python file
    sample_file = project_root / "tests" / "fixtures" / "sample.py"
    parser = registry.get_parser(str(sample_file))
    print(f"\n✅ Found parser for sample.py: {parser.__class__.__name__}")

    # Test error for unsupported extension
    try:
        registry.get_parser("test.unsupported")
        print("❌ Should have raised ValueError")
    except ValueError as e:
        print(f"✅ Correctly raised error: {str(e)[:60]}...")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    test_python_parser()
    test_parser_registry()
