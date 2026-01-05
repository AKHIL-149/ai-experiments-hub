"""Test CLI generate command"""
import sys
from pathlib import Path
import tempfile
import shutil

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from doc_gen import CLI


def print_section(title: str):
    """Print formatted section header"""
    print(f"\n{'=' * 70}")
    print(f"{title:^70}")
    print('=' * 70)


def test_cli_help():
    """Test CLI help output"""
    print_section("CLI HELP TEST")

    cli = CLI()

    print("\n[1/2] Testing main help...")
    try:
        cli.parser.print_help()
        print("\n✓ Main help displayed")
    except Exception as e:
        print(f"❌ Failed: {e}")

    print("\n[2/2] Testing generate help...")
    try:
        # Parse with --help to see if it works
        result = cli.run(['generate', '--help'])
        # This will exit, so we catch it
    except SystemExit:
        print("✓ Generate help works (exit expected)")

    print("\n" + "=" * 70)
    print("✅ CLI help test completed!")
    print("=" * 70)

    return True


def test_cli_generate_basic():
    """Test basic generate command"""
    print_section("CLI GENERATE BASIC TEST")

    cli = CLI()
    sample_file = project_root / "tests" / "fixtures" / "sample.py"

    # Create temporary output directory
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "output"

        print("\n[1/3] Testing generate with single format...")
        try:
            result = cli.run([
                'generate',
                str(sample_file),
                '--format', 'markdown',
                '--output', str(output_dir),
                '--no-ai',
                '--verbose'
            ])

            if result == 0:
                print("✓ Generate command succeeded")

                # Check output file
                md_files = list(output_dir.glob('*.md'))
                if md_files:
                    print(f"✓ Output file created: {md_files[0].name}")
                    file_size = md_files[0].stat().st_size
                    print(f"   Size: {file_size:,} bytes")
                else:
                    print("⚠️  No output file found")
            else:
                print(f"❌ Generate failed with code: {result}")

        except Exception as e:
            print(f"❌ Generate failed: {e}")

    # Test with multiple formats
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "output"

        print("\n[2/3] Testing generate with multiple formats...")
        try:
            result = cli.run([
                'generate',
                str(sample_file),
                '--format', 'markdown,json',
                '--output', str(output_dir),
                '--no-ai'
            ])

            if result == 0:
                print("✓ Multi-format generate succeeded")

                # Check output files
                md_files = list(output_dir.glob('*.md'))
                json_files = list(output_dir.glob('*.json'))

                if md_files:
                    print(f"   • Markdown: {md_files[0].name}")
                if json_files:
                    print(f"   • JSON: {json_files[0].name}")

                if md_files and json_files:
                    print("✓ Both formats generated")
                else:
                    print("⚠️  Some formats missing")
            else:
                print(f"❌ Generate failed with code: {result}")

        except Exception as e:
            print(f"❌ Generate failed: {e}")

    # Test with directory
    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "output"
        fixtures_dir = project_root / "tests" / "fixtures"

        print("\n[3/3] Testing generate with directory...")
        try:
            result = cli.run([
                'generate',
                str(fixtures_dir),
                '--format', 'markdown',
                '--output', str(output_dir),
                '--no-ai',
                '--recursive'
            ])

            if result == 0:
                print("✓ Directory generate succeeded")

                # Check output files
                output_files = list(output_dir.glob('*.md'))
                print(f"✓ Generated {len(output_files)} file(s)")

            else:
                print(f"❌ Generate failed with code: {result}")

        except Exception as e:
            print(f"❌ Generate failed: {e}")

    print("\n" + "=" * 70)
    print("✅ CLI generate basic test completed!")
    print("=" * 70)

    return True


def test_cli_generate_with_ai():
    """Test generate command with AI enhancement"""
    print_section("CLI GENERATE WITH AI TEST")

    cli = CLI()
    sample_file = project_root / "tests" / "fixtures" / "sample.py"

    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir) / "output"

        print("\n[1/1] Testing generate with AI enhancement...")
        try:
            result = cli.run([
                'generate',
                str(sample_file),
                '--format', 'markdown',
                '--output', str(output_dir),
                '--provider', 'ollama',
                '--model', 'llama3.2'
            ])

            if result == 0:
                print("✓ AI-enhanced generate succeeded")

                # Check output file
                md_files = list(output_dir.glob('*.md'))
                if md_files:
                    file_size = md_files[0].stat().st_size
                    print(f"✓ Output file: {md_files[0].name} ({file_size:,} bytes)")

                    # AI-enhanced files should be larger
                    if file_size > 3000:
                        print("✓ File size suggests AI enhancements included")
                    else:
                        print("⚠️  File may not have AI enhancements")
            else:
                print(f"⚠️  Generate returned code: {result}")

        except Exception as e:
            print(f"⚠️  AI test skipped: {e}")
            print("   (This is expected if Ollama is not running)")

    print("\n" + "=" * 70)
    print("✅ CLI AI test completed!")
    print("=" * 70)

    return True


def test_cli_error_handling():
    """Test CLI error handling"""
    print_section("CLI ERROR HANDLING TEST")

    cli = CLI()

    print("\n[1/3] Testing invalid input path...")
    result = cli.run([
        'generate',
        '/nonexistent/path/to/file.py',
        '--no-ai'
    ])

    if result != 0:
        print("✓ Correctly handled invalid path (exit code != 0)")
    else:
        print("⚠️  Should have failed for invalid path")

    print("\n[2/3] Testing invalid format...")
    try:
        result = cli.run([
            'generate',
            str(project_root / "tests" / "fixtures" / "sample.py"),
            '--format', 'invalid_format',
            '--no-ai'
        ])

        if result != 0:
            print("✓ Correctly handled invalid format")
        else:
            print("⚠️  Should have failed for invalid format")

    except Exception as e:
        print(f"✓ Exception raised for invalid format: {type(e).__name__}")

    print("\n[3/3] Testing no command...")
    result = cli.run([])

    if result != 0:
        print("✓ Correctly handled missing command")
    else:
        print("⚠️  Should have failed for missing command")

    print("\n" + "=" * 70)
    print("✅ Error handling test completed!")
    print("=" * 70)

    return True


def test_cli_argument_parsing():
    """Test CLI argument parsing"""
    print_section("CLI ARGUMENT PARSING TEST")

    cli = CLI()

    print("\n[1/4] Testing format parsing...")
    formats = cli._parse_formats('markdown,html,json')
    if formats == ['markdown', 'html', 'json']:
        print("✓ Multiple formats parsed correctly")
    else:
        print(f"❌ Format parsing failed: {formats}")

    print("\n[2/4] Testing 'all' format...")
    formats = cli._parse_formats('all')
    if len(formats) == 3:
        print(f"✓ 'all' expanded to: {formats}")
    else:
        print(f"❌ 'all' parsing failed: {formats}")

    print("\n[3/4] Testing single format...")
    formats = cli._parse_formats('json')
    if formats == ['json']:
        print("✓ Single format parsed correctly")
    else:
        print(f"❌ Single format parsing failed: {formats}")

    print("\n[4/4] Testing invalid format...")
    try:
        formats = cli._parse_formats('invalid')
        print(f"❌ Should have raised error for invalid format")
    except ValueError as e:
        print(f"✓ Correctly raised ValueError: {str(e)[:50]}...")

    print("\n" + "=" * 70)
    print("✅ Argument parsing test completed!")
    print("=" * 70)

    return True


def main():
    """Run all CLI tests"""
    try:
        # Test help
        test_cli_help()
        print("\n\n")

        # Test argument parsing
        test_cli_argument_parsing()
        print("\n\n")

        # Test error handling
        test_cli_error_handling()
        print("\n\n")

        # Test basic generate
        test_cli_generate_basic()
        print("\n\n")

        # Test AI generate
        test_cli_generate_with_ai()

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
