# Code Documentation Generator

An AI-powered code documentation generator that analyzes source code in multiple languages and generates comprehensive documentation using AST parsing and LLM-enhanced explanations.

## Project Status

**Current Phase**: Phase 5 - CLI Interface (In Progress)

### Completed Features

**Phase 1 - Core Foundation:**
- ✅ Python AST parser with full code structure extraction
- ✅ Data models for parsed code (functions, classes, parameters, etc.)
- ✅ Parser registry for multi-language support
- ✅ Type hint extraction
- ✅ Docstring parsing
- ✅ Decorator detection
- ✅ Complexity analysis (Simple/Medium/Complex)
- ✅ Support for async functions and methods
- ✅ Class inheritance and attribute extraction

**Phase 2 - Multi-Language Support:**
- ✅ JavaScript/TypeScript parser (via esprima + Node.js)
- ✅ Java parser (via javalang)
- ✅ Node.js bridge for JavaScript parsing
- ✅ Test fixtures for all three languages
- ✅ Graceful handling of missing dependencies

**Phase 3 - AI Enhancement:**
- ✅ LLM client with multi-backend support (Ollama, Anthropic, OpenAI)
- ✅ AI-powered explanations for functions and classes
- ✅ Module summary generation
- ✅ Parameter description enhancement
- ✅ Two-level caching (AST + AI explanations)
- ✅ Graceful degradation when LLM unavailable

**Phase 4 - Output Formatters:**
- ✅ Markdown formatter with table of contents
- ✅ HTML formatter with Bootstrap 5 styling
- ✅ JSON formatter for API reference
- ✅ Docstring formatter for code enhancement
- ✅ Batch processing support for multiple files
- ✅ Syntax highlighting and collapsible sections (HTML)
- ✅ Client-side search functionality (HTML)

**Phase 5 - CLI Interface:**
- ✅ `generate` command - Generate documentation from source code
- ✅ `enhance` command - Add AI-generated docstrings to code
- ✅ `analyze` command - Analyze code structure without generating docs
- ✅ Main orchestrator (DocGenerator class)
- ✅ Comprehensive error handling and validation
- ⏳ `serve` command - Web UI (planned for Phase 7)

### Upcoming Features

- [ ] Web interface with FastAPI (Phase 7)
- [ ] Python API - Make package installable (Phase 6)

## Quick Start

### Installation

```bash
# Clone the repository
cd ai-experiments-hub/python-projects/06-code-doc-generator

# Install dependencies
pip install -r requirements.txt
```

### CLI Usage

The tool provides four main commands:

#### 1. Generate Documentation

Generate comprehensive documentation from source code:

```bash
# Generate Markdown docs for a single file
python doc_gen.py generate src/example.py

# Generate multiple formats for a directory
python doc_gen.py generate src/ --format markdown,html,json --output docs/

# Generate with specific LLM provider
python doc_gen.py generate src/ --provider anthropic --model claude-3-5-sonnet

# Generate without AI enhancement (template-based only)
python doc_gen.py generate src/ --no-ai

# Generate with verbose output
python doc_gen.py generate src/ --format html --verbose
```

#### 2. Enhance Code with Docstrings

Add AI-generated docstrings directly to your source code:

```bash
# Enhance a Python file
python doc_gen.py enhance src/example.py

# Specify output file and docstring style
python doc_gen.py enhance src/example.py --output src/example_documented.py --style google

# Use specific LLM provider
python doc_gen.py enhance src/example.py --provider anthropic --model claude-3-5-sonnet
```

#### 3. Analyze Code Structure

Inspect code structure without generating documentation:

```bash
# Analyze a file
python doc_gen.py analyze src/example.py

# Analyze entire directory with detailed output
python doc_gen.py analyze src/ --details

# Shows: file count, functions, classes, and optionally lists all names
```

#### 4. Web UI (Coming Soon)

Start a web interface for interactive documentation generation:

```bash
python doc_gen.py serve --port 8000
```

### Additional Dependencies

**For JavaScript/TypeScript support:**
```bash
npm install
```

**For Java support:**
```bash
pip install javalang
```

**For AI features (choose one):**

```bash
# Option 1: Ollama (local, free) - Recommended
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2

# Option 2: Anthropic Claude (API key required)
pip install anthropic
export ANTHROPIC_API_KEY="your-key-here"

# Option 3: OpenAI (API key required)
pip install openai
export OPENAI_API_KEY="your-key-here"
```

### Testing

Run the test suite to verify functionality:

```bash
# Test all components
python tests/test_all_parsers.py
python tests/test_ai_enhancement.py
python tests/test_formatters.py
python tests/test_cli_generate.py
python tests/test_cli_commands.py
```

## Usage Examples

### Basic Parsing

```python
from src.parsers.python_parser import PythonParser

# Initialize parser
parser = PythonParser()

# Parse a Python file
parsed = parser.parse_file('path/to/your/file.py')

# Access the parsed information
print(f"Module: {parsed.file_path}")
print(f"Functions: {len(parsed.functions)}")
print(f"Classes: {len(parsed.classes)}")

# Iterate through functions
for func in parsed.functions:
    print(f"{func.name}({', '.join(p.name for p in func.parameters)})")
    print(f"  Line: {func.line_number}")
    print(f"  Complexity: {func.complexity}")
    print(f"  Docstring: {func.docstring}")

# Iterate through classes
for cls in parsed.classes:
    print(f"class {cls.name}:")
    print(f"  Methods: {len(cls.methods)}")
    print(f"  Attributes: {len(cls.attributes)}")
```

### Generating Documentation

```python
from src.parsers.python_parser import PythonParser
from src.core.llm_client import LLMClient
from src.core.ai_explainer import AIExplainer
from src.core.cache_manager import CacheManager
from src.formatters import MarkdownFormatter, HTMLFormatter, JSONFormatter

# Parse code
parser = PythonParser()
parsed = parser.parse_file('mycode.py')

# Add AI enhancements (optional)
llm = LLMClient(backend="ollama", model="llama3.2")
cache = CacheManager()
ai = AIExplainer(llm, cache)

parsed.ai_summary = ai.generate_module_summary(parsed)
for func in parsed.functions:
    func.ai_explanation = ai.explain_function(func)

# Generate Markdown documentation
md_formatter = MarkdownFormatter(include_toc=True)
md_formatter.format(parsed, 'output/docs.md')

# Generate HTML documentation
html_formatter = HTMLFormatter(theme="light", include_search=True)
html_formatter.format(parsed, 'output/docs.html')

# Generate JSON API reference
json_formatter = JSONFormatter(pretty=True)
json_formatter.format(parsed, 'output/api.json')
```

### Batch Processing

```python
from src.parsers.parser_registry import ParserRegistry
from src.formatters import MarkdownFormatter

# Auto-detect and parse multiple files
registry = ParserRegistry()
parsed_modules = []

for file_path in ['file1.py', 'file2.js', 'File3.java']:
    parser = registry.get_parser(file_path)
    parsed = parser.parse_file(file_path)
    parsed_modules.append(parsed)

# Generate combined documentation
formatter = MarkdownFormatter()
formatter.format_batch(parsed_modules, 'output/project_docs.md')
```

### Enhancing Source Code with Docstrings

```python
from src.parsers.python_parser import PythonParser
from src.core.ai_explainer import AIExplainer
from src.formatters import DocstringFormatter

# Parse and enhance
parser = PythonParser()
parsed = parser.parse_file('mycode.py')

ai = AIExplainer()
for func in parsed.functions:
    func.ai_explanation = ai.explain_function(func)

# Generate enhanced source code with docstrings
docstring_formatter = DocstringFormatter(style="google")
docstring_formatter.format(parsed, 'mycode_documented.py')
```

## Project Structure

```
06-code-doc-generator/
├── src/
│   ├── parsers/
│   │   ├── models.py              # Data models (ParsedModule, FunctionInfo, etc.) ✅
│   │   ├── base_parser.py         # Abstract base class for parsers ✅
│   │   ├── python_parser.py       # Python AST parser ✅
│   │   ├── javascript_parser.py   # JavaScript/TypeScript parser ✅
│   │   ├── java_parser.py         # Java parser ✅
│   │   ├── js_parser_helper.js    # Node.js helper for JS parsing ✅
│   │   └── parser_registry.py     # Auto-discovery and selection ✅
│   ├── core/
│   │   ├── llm_client.py          # LLM interface (Ollama/Anthropic/OpenAI) ✅
│   │   ├── ai_explainer.py        # AI-powered explanation generator ✅
│   │   └── cache_manager.py       # Two-level caching system ✅
│   ├── formatters/
│   │   ├── base_formatter.py      # Abstract formatter interface ✅
│   │   ├── markdown_formatter.py  # Markdown output generator ✅
│   │   ├── html_formatter.py      # HTML output with Bootstrap 5 ✅
│   │   ├── json_formatter.py      # JSON API reference ✅
│   │   └── docstring_formatter.py # Code enhancement with docstrings ✅
│   └── utils/                     # Utility functions (future)
├── tests/
│   ├── fixtures/
│   │   ├── sample.py              # Test Python file ✅
│   │   ├── sample.js              # Test JavaScript file ✅
│   │   └── Sample.java            # Test Java file ✅
│   ├── test_python_parser.py      # Python parser tests ✅
│   ├── test_all_parsers.py        # Multi-language tests ✅
│   ├── test_ai_enhancement.py     # AI enhancement tests ✅
│   └── test_formatters.py         # Formatter tests ✅
├── data/
│   ├── cache/
│   │   ├── ast/                   # Parsed AST cache ✅
│   │   └── ai/                    # AI explanation cache ✅
│   └── output/                    # Generated documentation ✅
├── requirements.txt                # Python dependencies ✅
├── package.json                    # Node.js dependencies (for JS parsing) ✅
└── .env.example                    # Environment configuration ✅
```

## Architecture

The project follows a composition pattern with clear separation of concerns:

1. **Parsers**: Language-specific code parsers that convert source code into standardized data models
2. **Core**: Orchestration, LLM integration, and caching (Phase 3)
3. **Formatters**: Output generators for different formats (Phase 4)
4. **CLI/Web**: User interfaces (Phases 5-7)

## Parser Features

The Python parser extracts:

- **Module level**:
  - Module docstring
  - All import statements
  - Global variables with type hints and values

- **Functions**:
  - Name, line number
  - Parameters (with type hints, default values)
  - Return type
  - Docstring
  - Decorators
  - Complexity rating
  - Async/sync indicator

- **Classes**:
  - Name, line number, docstring
  - Base classes (inheritance)
  - Class attributes with type hints
  - All methods (instance, static, class methods)
  - Decorators

## CLI Command Reference

### `generate` - Generate Documentation

Generate documentation from source code in multiple formats.

**Syntax:**
```bash
python doc_gen.py generate <input> [options]
```

**Options:**
- `<input>` - File or directory to document (required)
- `--format`, `-f` - Output format(s): markdown, html, json, docstring, all (default: markdown)
- `--output`, `-o` - Output directory (default: ./data/output)
- `--recursive`, `-r` - Recursively process directories (default: True)
- `--no-recursive` - Do not process directories recursively
- `--provider` - LLM provider: ollama, anthropic, openai (default: ollama)
- `--model` - LLM model to use (uses provider default if not specified)
- `--no-ai` - Disable AI enhancements (faster, template-based docs only)
- `--no-cache` - Disable caching (forces fresh generation)
- `--cache-dir` - Cache directory (default: ./data/cache)
- `--verbose`, `-v` - Verbose output

**Examples:**
```bash
# Single file, Markdown format
python doc_gen.py generate src/example.py

# Directory, multiple formats
python doc_gen.py generate src/ --format markdown,html,json

# With specific AI model
python doc_gen.py generate src/ --provider anthropic --model claude-3-5-sonnet

# Template-based (no AI)
python doc_gen.py generate src/ --no-ai --format markdown
```

### `enhance` - Add Docstrings to Code

Enhance source code with AI-generated docstrings.

**Syntax:**
```bash
python doc_gen.py enhance <input> [options]
```

**Options:**
- `<input>` - Source file to enhance (required, must be a file)
- `--output`, `-o` - Output file path (default: <input>_documented)
- `--style` - Docstring style: auto, google, numpy, jsdoc, javadoc (default: auto)
- `--provider` - LLM provider: ollama, anthropic, openai (default: ollama)
- `--model` - LLM model to use

**Examples:**
```bash
# Enhance with auto output path
python doc_gen.py enhance src/mycode.py

# Specify output and style
python doc_gen.py enhance src/mycode.py --output src/documented.py --style google

# Use Anthropic Claude
python doc_gen.py enhance src/mycode.py --provider anthropic
```

### `analyze` - Analyze Code Structure

Analyze and display code structure without generating documentation.

**Syntax:**
```bash
python doc_gen.py analyze <input> [options]
```

**Options:**
- `<input>` - File or directory to analyze (required)
- `--details` - Show detailed analysis (function/class names)

**Examples:**
```bash
# Basic analysis
python doc_gen.py analyze src/

# Detailed analysis with function/class names
python doc_gen.py analyze src/ --details
```

**Output includes:**
- Total files, functions, classes
- Breakdown by programming language
- With `--details`: Lists all function and class names

### `serve` - Web UI (Coming Soon)

Start web interface for interactive documentation generation.

**Syntax:**
```bash
python doc_gen.py serve [options]
```

**Options:**
- `--host` - Host to bind (default: 127.0.0.1)
- `--port`, `-p` - Port to bind (default: 8000)

## Development Roadmap

### Phase 1: Core Parsing Foundation ✅
- Python AST parser with comprehensive extraction
- Data models for all code structures
- Parser registry system

### Phase 2: Multi-Language Support ✅
- JavaScript/TypeScript parser (via Node.js + esprima)
- Java parser (via javalang)
- Test fixtures for all languages
- Graceful dependency handling

### Phase 3: AI Enhancement ✅
- LLM client integration with multi-backend support
- AI-powered explanations for functions/classes
- Module summary generation
- Parameter description enhancement
- Multi-level caching (AST + AI)

### Phase 4: Output Formatters ✅
- Markdown formatter with table of contents
- HTML formatter with syntax highlighting
- JSON API reference formatter
- Docstring enhancement formatter

### Phase 5: CLI Interface ⏳ (CURRENT)
- ✅ `doc_gen.py generate` - Generate documentation
- ✅ `doc_gen.py enhance` - Add docstrings to code
- ✅ `doc_gen.py analyze` - Analyze code structure
- ✅ Main orchestrator and error handling
- ⏳ `doc_gen.py serve` - Start web UI (Phase 7)

### Phase 6: Python API (NEXT)
- Make package installable with setup.py
- Public API for programmatic use
- Console script entry point

### Phase 7: Web Interface
- FastAPI web server
- Upload and generate docs
- Preview and download
- Implement `serve` command

## Testing

Run the test suite to verify the parser works correctly:

```bash
python3 tests/test_python_parser.py
```

Expected output includes:
- Parsed module information
- List of imports
- Global variables
- Functions with full details
- Classes with methods and attributes
- Parser registry functionality

## Configuration

See [.env.example](.env.example) for configuration options (needed in later phases for LLM integration).

## License

MIT License - Part of the AI Experiments Hub learning repository.

## Next Steps

1. ✅ Phase 1 complete - Python parser working
2. 🔜 Phase 2 - Add JavaScript and Java parsers
3. 🔜 Phase 3 - Integrate LLM for AI explanations
4. 🔜 Phase 4 - Build output formatters
5. 🔜 Phase 5-7 - Create user interfaces

---

*This is a learning project focused on understanding AST parsing, LLM integration, and practical AI applications.*
