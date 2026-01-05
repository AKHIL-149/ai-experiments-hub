"""Test AI-powered code explanation"""
import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.parsers.python_parser import PythonParser
from src.core.ai_explainer import AIExplainer
from src.core.llm_client import LLMClient
from src.core.cache_manager import CacheManager


def print_section(title: str):
    """Print formatted section header"""
    print(f"\n{'=' * 70}")
    print(f"{title:^70}")
    print('=' * 70)


def test_ai_enhancement():
    """Test AI enhancement of parsed code"""
    print_section("AI-ENHANCED CODE DOCUMENTATION TEST")

    # Get sample file
    sample_file = project_root / "tests" / "fixtures" / "sample.py"

    print(f"\n📄 Analyzing: {sample_file.name}")

    # Step 1: Parse the code
    print("\n[1/4] Parsing Python code...")
    parser = PythonParser()
    parsed = parser.parse_file(str(sample_file))
    print(f"✓ Found {len(parsed.functions)} functions and {len(parsed.classes)} classes")

    # Step 2: Initialize AI components
    print("\n[2/4] Initializing AI components...")
    try:
        # Try to use Ollama (local, free)
        llm_client = LLMClient(backend="ollama", model="llama3.2")
        print(f"✓ Using Ollama with model: llama3.2")
    except Exception as e:
        print(f"⚠️  Ollama not available: {str(e)}")
        print("   You can install Ollama from: https://ollama.com/")
        print("   Or set ANTHROPIC_API_KEY or OPENAI_API_KEY to use cloud LLMs")
        return False

    cache_manager = CacheManager()
    ai_explainer = AIExplainer(llm_client, cache_manager)
    print(f"✓ AI explainer ready with caching enabled")

    # Step 3: Generate module summary
    print("\n[3/4] Generating AI-powered module summary...")
    try:
        module_summary = ai_explainer.generate_module_summary(parsed)
        print(f"\n📝 Module Summary:")
        print(f"   {module_summary}")
    except Exception as e:
        print(f"❌ Failed to generate module summary: {str(e)}")
        module_summary = None

    # Step 4: Enhance functions with AI explanations
    print("\n[4/4] Generating AI explanations for functions...")

    if parsed.functions:
        # Explain first 2 functions
        for i, func in enumerate(parsed.functions[:2], 1):
            print(f"\n🔧 Function {i}: {func.name}")
            print(f"   Signature: {func.name}({', '.join([p.name for p in func.parameters])})")

            if func.docstring:
                print(f"   Original docstring: {func.docstring[:60]}...")

            try:
                ai_explanation = ai_explainer.explain_function(func, context=sample_file.stem)
                print(f"\n   🤖 AI Explanation:")
                print(f"   {ai_explanation}")

                # Also enhance parameters
                if func.parameters:
                    enhanced_params = ai_explainer.enhance_parameter_descriptions(
                        func.parameters,
                        function_context=func.name
                    )

                    if any(p.description for p in enhanced_params):
                        print(f"\n   📋 Enhanced Parameters:")
                        for param in enhanced_params:
                            if param.description:
                                type_info = f": {param.type_hint}" if param.type_hint else ""
                                print(f"      • {param.name}{type_info} - {param.description}")

            except Exception as e:
                print(f"   ❌ Failed to generate explanation: {str(e)}")

    # Step 5: Enhance classes
    if parsed.classes:
        print(f"\n🏛️  Enhancing classes...")

        for i, cls in enumerate(parsed.classes[:1], 1):  # Just first class
            print(f"\n   Class {i}: {cls.name}")

            if cls.docstring:
                print(f"   Original docstring: {cls.docstring[:60]}...")

            try:
                ai_explanation = ai_explainer.explain_class(cls, context=sample_file.stem)
                print(f"\n   🤖 AI Explanation:")
                print(f"   {ai_explanation}")

                # Explain first method
                if cls.methods:
                    method = cls.methods[0]
                    print(f"\n   Method: {method.name}")
                    method_explanation = ai_explainer.explain_function(
                        method,
                        context=f"{cls.name}.{method.name}"
                    )
                    print(f"   🤖 {method_explanation}")

            except Exception as e:
                print(f"   ❌ Failed to generate explanation: {str(e)}")

    # Show cache stats
    print_section("CACHE STATISTICS")
    stats = cache_manager.get_cache_stats()
    print(f"\n📦 AST Cache:")
    print(f"   Files: {stats['ast_cache']['total_files']}")
    print(f"   Size: {stats['ast_cache']['total_size_mb']} MB")

    print(f"\n🤖 AI Cache:")
    print(f"   Files: {stats['ai_cache']['total_files']}")
    print(f"   Fresh: {stats['ai_cache']['fresh_files']}")
    print(f"   Size: {stats['ai_cache']['total_size_mb']} MB")

    print("\n" + "=" * 70)
    print("✅ AI enhancement test completed!")
    print("=" * 70)

    return True


def main():
    """Run the test"""
    try:
        success = test_ai_enhancement()
        return 0 if success else 1
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
