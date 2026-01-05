"""Test DocGenerator orchestrator"""
import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.core.doc_generator import DocGenerator
from src.utils.file_utils import FileDiscovery


def print_section(title: str):
    """Print formatted section header"""
    print(f"\n{'=' * 70}")
    print(f"{title:^70}")
    print('=' * 70)


def test_doc_generator_basic():
    """Test basic DocGenerator functionality"""
    print_section("DOC GENERATOR TEST")

    # Test 1: Initialize without AI
    print("\n[1/5] Testing initialization without AI...")
    generator = DocGenerator(use_ai=False)
    print(f"✓ Generator initialized")
    print(f"   Available parsers: {', '.join(generator.get_available_parsers())}")
    print(f"   Supported formats: {', '.join(generator.get_supported_formats())}")

    # Test 2: Analyze structure
    print("\n[2/5] Testing structure analysis...")
    sample_file = project_root / "tests" / "fixtures" / "sample.py"

    analysis = generator.analyze_structure(str(sample_file), show_details=True)

    print(f"✓ Structure analyzed:")
    print(f"   Total files: {analysis['total_files']}")
    print(f"   Total functions: {analysis['total_functions']}")
    print(f"   Total classes: {analysis['total_classes']}")

    for lang, stats in analysis['languages'].items():
        print(f"\n   {lang.upper()}:")
        print(f"     Files: {stats['file_count']}")
        print(f"     Functions: {stats['functions']}")
        print(f"     Classes: {stats['classes']}")

    # Test 3: Generate docs without AI
    print("\n[3/5] Testing documentation generation (no AI)...")
    output_dir = project_root / "data" / "output" / "test_generator"

    try:
        output_files = generator.generate_docs(
            input_path=str(sample_file),
            output_format='markdown',
            output_dir=str(output_dir),
            recursive=False
        )

        print(f"✓ Documentation generated:")
        for file_path in output_files:
            file_size = Path(file_path).stat().st_size
            print(f"   {Path(file_path).name} ({file_size:,} bytes)")

    except Exception as e:
        print(f"❌ Generation failed: {e}")

    # Test 4: Generate multiple formats
    print("\n[4/5] Testing multiple format generation...")
    try:
        output_files = generator.generate_docs(
            input_path=str(sample_file),
            output_format=['markdown', 'json'],
            output_dir=str(output_dir),
            recursive=False
        )

        print(f"✓ Multiple formats generated:")
        for file_path in output_files:
            file_size = Path(file_path).stat().st_size
            print(f"   {Path(file_path).name} ({file_size:,} bytes)")

    except Exception as e:
        print(f"❌ Generation failed: {e}")

    # Test 5: Test with AI (if available)
    print("\n[5/5] Testing with AI enhancements...")
    try:
        generator_ai = DocGenerator(
            llm_provider="ollama",
            model="llama3.2",
            use_ai=True
        )

        if generator_ai.use_ai:
            output_files = generator_ai.generate_docs(
                input_path=str(sample_file),
                output_format='markdown',
                output_dir=str(output_dir / "ai"),
                recursive=False
            )

            print(f"✓ AI-enhanced documentation generated:")
            for file_path in output_files:
                file_size = Path(file_path).stat().st_size
                print(f"   {Path(file_path).name} ({file_size:,} bytes)")
        else:
            print("⚠️  AI features not available, skipped")

    except Exception as e:
        print(f"⚠️  AI test skipped: {e}")

    print("\n" + "=" * 70)
    print("✅ Doc generator test completed!")
    print("=" * 70)

    return True


def test_file_discovery():
    """Test FileDiscovery utility"""
    print_section("FILE DISCOVERY TEST")

    discovery = FileDiscovery()

    # Test single file
    print("\n[1/3] Testing single file discovery...")
    sample_file = project_root / "tests" / "fixtures" / "sample.py"
    files = discovery.discover_files(str(sample_file), recursive=False)
    print(f"✓ Found {len(files)} file(s)")
    for f in files:
        lang = discovery.get_language(f)
        print(f"   {Path(f).name} ({lang})")

    # Test directory
    print("\n[2/3] Testing directory discovery...")
    fixtures_dir = project_root / "tests" / "fixtures"
    files = discovery.discover_files(str(fixtures_dir), recursive=False)
    print(f"✓ Found {len(files)} file(s)")

    grouped = discovery.group_by_language(files)
    for lang, lang_files in grouped.items():
        print(f"   {lang}: {len(lang_files)} file(s)")

    # Test recursive
    print("\n[3/3] Testing recursive discovery...")
    src_dir = project_root / "src"
    files = discovery.discover_files(str(src_dir), recursive=True)
    print(f"✓ Found {len(files)} file(s) recursively")

    grouped = discovery.group_by_language(files)
    for lang, lang_files in grouped.items():
        print(f"   {lang}: {len(lang_files)} file(s)")

    print("\n" + "=" * 70)
    print("✅ File discovery test completed!")
    print("=" * 70)

    return True


def main():
    """Run all tests"""
    try:
        # Test file discovery
        test_file_discovery()

        print("\n\n")

        # Test doc generator
        test_doc_generator_basic()

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
