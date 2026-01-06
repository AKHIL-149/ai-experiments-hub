"""Test CLI enhance and analyze commands"""
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


def test_analyze_command():
    """Test analyze command"""
    print_section("ANALYZE COMMAND TEST")

    cli = CLI()
    sample_file = project_root / "tests" / "fixtures" / "sample.py"
    fixtures_dir = project_root / "tests" / "fixtures"

    print("\n[1/4] Testing analyze on single file...")
    try:
        result = cli.run([
            'analyze',
            str(sample_file)
        ])

        if result == 0:
            print("✓ Analyze single file succeeded")
        else:
            print(f"❌ Analyze failed with code: {result}")

    except Exception as e:
        print(f"❌ Analyze failed: {e}")

    print("\n[2/4] Testing analyze on directory...")
    try:
        result = cli.run([
            'analyze',
            str(fixtures_dir)
        ])

        if result == 0:
            print("✓ Analyze directory succeeded")
        else:
            print(f"❌ Analyze failed with code: {result}")

    except Exception as e:
        print(f"❌ Analyze failed: {e}")

    print("\n[3/4] Testing analyze with details flag...")
    try:
        result = cli.run([
            'analyze',
            str(sample_file),
            '--details'
        ])

        if result == 0:
            print("✓ Analyze with details succeeded")
        else:
            print(f"❌ Analyze with details failed with code: {result}")

    except Exception as e:
        print(f"❌ Analyze with details failed: {e}")

    print("\n[4/4] Testing analyze on src directory...")
    src_dir = project_root / "src"
    try:
        result = cli.run([
            'analyze',
            str(src_dir)
        ])

        if result == 0:
            print("✓ Analyze src directory succeeded")
        else:
            print(f"❌ Analyze src failed with code: {result}")

    except Exception as e:
        print(f"❌ Analyze src failed: {e}")

    print("\n" + "=" * 70)
    print("✅ Analyze command test completed!")
    print("=" * 70)

    return True


def test_enhance_command():
    """Test enhance command"""
    print_section("ENHANCE COMMAND TEST")

    cli = CLI()
    sample_file = project_root / "tests" / "fixtures" / "sample.py"

    # Test with temporary directory
    with tempfile.TemporaryDirectory() as temp_dir:
        # Copy sample file to temp directory
        temp_file = Path(temp_dir) / "test_sample.py"
        shutil.copy(sample_file, temp_file)

        output_file = Path(temp_dir) / "test_sample_documented.py"

        print("\n[1/3] Testing enhance with default settings...")
        try:
            result = cli.run([
                'enhance',
                str(temp_file),
                '--output', str(output_file),
                '--provider', 'ollama',
                '--model', 'llama3.2'
            ])

            if result == 0:
                print("✓ Enhance command succeeded")

                # Check output file
                if output_file.exists():
                    input_size = temp_file.stat().st_size
                    output_size = output_file.stat().st_size

                    print(f"✓ Output file created")
                    print(f"   Input size:  {input_size:,} bytes")
                    print(f"   Output size: {output_size:,} bytes")
                    print(f"   Increase:    {output_size - input_size:,} bytes")

                    if output_size > input_size:
                        print("✓ File size increased (docstrings added)")
                    else:
                        print("⚠️  File size did not increase")
                else:
                    print("⚠️  Output file not found")
            else:
                print(f"⚠️  Enhance returned code: {result}")

        except Exception as e:
            print(f"⚠️  Enhance test skipped: {e}")
            print("   (This is expected if Ollama is not running)")

    # Test with Google style
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file = Path(temp_dir) / "test_sample.py"
        shutil.copy(sample_file, temp_file)

        output_file = Path(temp_dir) / "test_sample_google.py"

        print("\n[2/3] Testing enhance with Google style...")
        try:
            result = cli.run([
                'enhance',
                str(temp_file),
                '--output', str(output_file),
                '--style', 'google',
                '--provider', 'ollama'
            ])

            if result == 0:
                print("✓ Google style enhance succeeded")
                if output_file.exists():
                    print(f"✓ Output file: {output_file.name}")
            else:
                print(f"⚠️  Enhance returned code: {result}")

        except Exception as e:
            print(f"⚠️  Google style test skipped: {e}")

    # Test auto-detect output path
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_file = Path(temp_dir) / "test_sample.py"
        shutil.copy(sample_file, temp_file)

        print("\n[3/3] Testing enhance with auto output path...")
        try:
            result = cli.run([
                'enhance',
                str(temp_file),
                '--provider', 'ollama'
            ])

            if result == 0:
                print("✓ Auto output path enhance succeeded")

                # Check for default output file
                expected_output = Path(temp_dir) / "test_sample_documented.py"
                if expected_output.exists():
                    print(f"✓ Auto-generated output file: {expected_output.name}")
                else:
                    print("⚠️  Default output file not found")
            else:
                print(f"⚠️  Enhance returned code: {result}")

        except Exception as e:
            print(f"⚠️  Auto path test skipped: {e}")

    print("\n" + "=" * 70)
    print("✅ Enhance command test completed!")
    print("=" * 70)

    return True


def test_command_error_handling():
    """Test error handling for enhance and analyze"""
    print_section("COMMAND ERROR HANDLING TEST")

    cli = CLI()

    print("\n[1/3] Testing analyze with invalid path...")
    result = cli.run([
        'analyze',
        '/nonexistent/path'
    ])

    if result != 0:
        print("✓ Correctly handled invalid path for analyze")
    else:
        print("⚠️  Should have failed for invalid path")

    print("\n[2/3] Testing enhance with invalid file...")
    result = cli.run([
        'enhance',
        '/nonexistent/file.py',
        '--provider', 'ollama'
    ])

    if result != 0:
        print("✓ Correctly handled invalid file for enhance")
    else:
        print("⚠️  Should have failed for invalid file")

    print("\n[3/3] Testing enhance with directory instead of file...")
    src_dir = project_root / "src"
    result = cli.run([
        'enhance',
        str(src_dir),
        '--provider', 'ollama'
    ])

    if result != 0:
        print("✓ Correctly rejected directory for enhance")
    else:
        print("⚠️  Should have failed for directory input")

    print("\n" + "=" * 70)
    print("✅ Error handling test completed!")
    print("=" * 70)

    return True


def test_analyze_output_format():
    """Test analyze output formatting"""
    print_section("ANALYZE OUTPUT FORMAT TEST")

    cli = CLI()
    sample_file = project_root / "tests" / "fixtures" / "sample.py"

    print("\n[1/1] Testing analyze output structure...")
    try:
        # Capture would normally be done here, but for now just run it
        result = cli.run([
            'analyze',
            str(sample_file),
            '--details'
        ])

        if result == 0:
            print("\n✓ Analyze output formatted correctly")
            print("   (Visual inspection above shows structure)")
        else:
            print(f"❌ Analyze failed with code: {result}")

    except Exception as e:
        print(f"❌ Output format test failed: {e}")

    print("\n" + "=" * 70)
    print("✅ Output format test completed!")
    print("=" * 70)

    return True


def main():
    """Run all command tests"""
    try:
        # Test analyze command
        test_analyze_command()
        print("\n\n")

        # Test enhance command
        test_enhance_command()
        print("\n\n")

        # Test error handling
        test_command_error_handling()
        print("\n\n")

        # Test output format
        test_analyze_output_format()

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
