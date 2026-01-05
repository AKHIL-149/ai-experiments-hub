"""Test all documentation formatters"""
import sys
from pathlib import Path
import json

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.parsers.python_parser import PythonParser
from src.core.ai_explainer import AIExplainer
from src.core.llm_client import LLMClient
from src.core.cache_manager import CacheManager
from src.formatters import (
    MarkdownFormatter,
    HTMLFormatter,
    JSONFormatter,
    DocstringFormatter
)


def print_section(title: str):
    """Print formatted section header"""
    print(f"\n{'=' * 70}")
    print(f"{title:^70}")
    print('=' * 70)


def test_all_formatters():
    """Test all formatters with AI-enhanced code"""
    print_section("FORMATTER TEST")

    # Get sample file
    sample_file = project_root / "tests" / "fixtures" / "sample.py"
    output_dir = project_root / "data" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📄 Analyzing: {sample_file.name}")

    # Step 1: Parse the code
    print("\n[1/5] Parsing Python code...")
    parser = PythonParser()
    parsed = parser.parse_file(str(sample_file))
    print(f"✓ Found {len(parsed.functions)} functions and {len(parsed.classes)} classes")

    # Step 2: Add AI enhancements
    print("\n[2/5] Adding AI enhancements...")
    try:
        llm_client = LLMClient(backend="ollama", model="llama3.2")
        cache_manager = CacheManager()
        ai_explainer = AIExplainer(llm_client, cache_manager)

        # Generate module summary
        parsed.ai_summary = ai_explainer.generate_module_summary(parsed)

        # Enhance first 2 functions
        for func in parsed.functions[:2]:
            func.ai_explanation = ai_explainer.explain_function(func, context=sample_file.stem)
            if func.parameters:
                enhanced_params = ai_explainer.enhance_parameter_descriptions(
                    func.parameters,
                    function_context=func.name
                )
                func.parameters = enhanced_params

        # Enhance first class
        if parsed.classes:
            cls = parsed.classes[0]
            cls.ai_explanation = ai_explainer.explain_class(cls, context=sample_file.stem)
            if cls.methods:
                method = cls.methods[0]
                method.ai_explanation = ai_explainer.explain_function(
                    method,
                    context=f"{cls.name}.{method.name}"
                )

        print("✓ AI enhancements added")

    except Exception as e:
        print(f"⚠️  AI enhancements skipped: {str(e)}")
        print("   Continuing with basic documentation...")

    # Step 3: Test Markdown formatter
    print("\n[3/5] Testing Markdown formatter...")
    try:
        md_formatter = MarkdownFormatter(include_toc=True)
        md_output = output_dir / "sample_docs.md"
        result_path = md_formatter.format(parsed, str(md_output))
        print(f"✓ Markdown documentation generated: {result_path}")

        # Show preview
        content = Path(result_path).read_text()
        lines = content.split('\n')
        print(f"\n   Preview (first 15 lines):")
        for line in lines[:15]:
            print(f"   {line}")
        if len(lines) > 15:
            print(f"   ... and {len(lines) - 15} more lines")

    except Exception as e:
        print(f"❌ Markdown formatter failed: {str(e)}")

    # Step 4: Test HTML formatter
    print("\n[4/5] Testing HTML formatter...")
    try:
        html_formatter = HTMLFormatter(theme="light", include_search=True)
        html_output = output_dir / "sample_docs.html"
        result_path = html_formatter.format(parsed, str(html_output))
        print(f"✓ HTML documentation generated: {result_path}")

        # Show file size
        file_size = Path(result_path).stat().st_size
        print(f"   File size: {file_size:,} bytes")
        print(f"   Open in browser: file://{result_path}")

    except Exception as e:
        print(f"❌ HTML formatter failed: {str(e)}")

    # Step 5: Test JSON formatter
    print("\n[5/5] Testing JSON formatter...")
    try:
        json_formatter = JSONFormatter(pretty=True, include_metadata=True)
        json_output = output_dir / "sample_api.json"
        result_path = json_formatter.format(parsed, str(json_output))
        print(f"✓ JSON API reference generated: {result_path}")

        # Show preview
        with open(result_path, 'r') as f:
            data = json.load(f)

        print(f"\n   Metadata:")
        if 'metadata' in data:
            for key, value in data['metadata'].items():
                print(f"   - {key}: {value}")

        module_data = data.get('module', data)
        print(f"\n   Module statistics:")
        if 'statistics' in module_data:
            for key, value in module_data['statistics'].items():
                print(f"   - {key}: {value}")

    except Exception as e:
        print(f"❌ JSON formatter failed: {str(e)}")

    # Bonus: Test docstring formatter (optional)
    print("\n[Bonus] Testing Docstring formatter...")
    try:
        docstring_formatter = DocstringFormatter(style="google", create_backup=True)
        enhanced_output = output_dir / "sample_enhanced.py"
        result_path = docstring_formatter.format(parsed, str(enhanced_output))
        print(f"✓ Enhanced source code generated: {result_path}")

        # Show preview of first enhanced function
        content = Path(result_path).read_text()
        lines = content.split('\n')

        # Find first docstring
        for i, line in enumerate(lines):
            if '"""' in line and i > 0:
                # Show context around docstring
                start = max(0, i - 2)
                end = min(len(lines), i + 15)
                print(f"\n   Preview of enhanced code (lines {start+1}-{end}):")
                for j in range(start, end):
                    print(f"   {j+1:3d} | {lines[j]}")
                break

    except Exception as e:
        print(f"⚠️  Docstring formatter skipped: {str(e)}")

    # Summary
    print_section("FORMATTER TEST COMPLETE")
    print(f"\n📁 All outputs saved to: {output_dir}")
    print(f"\n✅ Available documentation formats:")
    print(f"   • Markdown: sample_docs.md")
    print(f"   • HTML:     sample_docs.html")
    print(f"   • JSON:     sample_api.json")
    print(f"   • Enhanced: sample_enhanced.py")

    print("\n" + "=" * 70)

    return True


def test_batch_formatting():
    """Test batch formatting with multiple files"""
    print_section("BATCH FORMATTING TEST")

    sample_dir = project_root / "tests" / "fixtures"
    output_dir = project_root / "data" / "output"

    # Parse all sample files
    print("\n📚 Parsing all sample files...")
    parser = PythonParser()

    parsed_modules = []
    for sample_file in sample_dir.glob("*.py"):
        try:
            parsed = parser.parse_file(str(sample_file))
            parsed_modules.append(parsed)
            print(f"   ✓ {sample_file.name}")
        except Exception as e:
            print(f"   ✗ {sample_file.name}: {str(e)}")

    if not parsed_modules:
        print("⚠️  No Python files found to process")
        return False

    print(f"\n✓ Parsed {len(parsed_modules)} file(s)")

    # Test batch Markdown
    print("\n[1/3] Testing batch Markdown formatter...")
    try:
        md_formatter = MarkdownFormatter(include_toc=True)
        md_output = output_dir / "project_docs.md"
        result_path = md_formatter.format_batch(parsed_modules, str(md_output))
        print(f"✓ Batch Markdown generated: {result_path}")

        # Show file size
        file_size = Path(result_path).stat().st_size
        print(f"   File size: {file_size:,} bytes")

    except Exception as e:
        print(f"❌ Batch Markdown failed: {str(e)}")

    # Test batch HTML
    print("\n[2/3] Testing batch HTML formatter...")
    try:
        html_formatter = HTMLFormatter(theme="light", include_search=True)
        html_output = output_dir / "project_docs.html"
        result_path = html_formatter.format_batch(parsed_modules, str(html_output))
        print(f"✓ Batch HTML generated: {result_path}")

        # Show file size
        file_size = Path(result_path).stat().st_size
        print(f"   File size: {file_size:,} bytes")

    except Exception as e:
        print(f"❌ Batch HTML failed: {str(e)}")

    # Test batch JSON
    print("\n[3/3] Testing batch JSON formatter...")
    try:
        json_formatter = JSONFormatter(pretty=True, include_metadata=True)
        json_output = output_dir / "project_api.json"
        result_path = json_formatter.format_batch(parsed_modules, str(json_output))
        print(f"✓ Batch JSON generated: {result_path}")

        # Show file size and statistics
        file_size = Path(result_path).stat().st_size
        print(f"   File size: {file_size:,} bytes")

        with open(result_path, 'r') as f:
            data = json.load(f)

        if 'metadata' in data:
            print(f"\n   Statistics:")
            print(f"   - Total modules: {data['metadata'].get('total_modules', 0)}")
            print(f"   - Total functions: {data['metadata'].get('total_functions', 0)}")
            print(f"   - Total classes: {data['metadata'].get('total_classes', 0)}")

    except Exception as e:
        print(f"❌ Batch JSON failed: {str(e)}")

    print("\n" + "=" * 70)
    print("✅ Batch formatting test completed!")
    print("=" * 70)

    return True


def main():
    """Run all formatter tests"""
    try:
        # Test single file formatting
        test_all_formatters()

        # Test batch formatting
        print("\n\n")
        test_batch_formatting()

        return 0

    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        return 1
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
