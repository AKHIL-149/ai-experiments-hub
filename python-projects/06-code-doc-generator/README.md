# Code Documentation Generator

An AI-powered code documentation generator that analyzes source code in multiple languages and generates comprehensive documentation using AST parsing and LLM-enhanced explanations.

## Project Status

**Current Phase**: Phase 4 - Output Formatters ✅

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

### Upcoming Features

- [ ] CLI interface with command-line tool
- [ ] Web interface with FastAPI
- [ ] Python API (importable package)

## Quick Start

### Installation

```bash
# Clone the repository
cd ai-experiments-hub/python-projects/06-code-doc-generator

# Install dependencies (optional for now - only needed for AI features later)
pip install -r requirements.txt
```

### Testing the Parsers

```bash
# Test all parsers (Python, JavaScript, Java)
python3 tests/test_all_parsers.py

# Test AI-enhanced documentation generation
python3 tests/test_ai_enhancement.py

# Test all output formatters (Markdown, HTML, JSON, Docstring)
python3 tests/test_formatters.py

# Or test individual parsers
python3 tests/test_python_parser.py
```

**Note**: Additional dependencies for full functionality:
```bash
# For JavaScript/TypeScript support
npm install

# For Java support
pip install javalang

# For AI features (choose one):
# Option 1: Ollama (local, free) - Recommended for development
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2

# Option 2: Anthropic Claude (API key required)
pip install anthropic
export ANTHROPIC_API_KEY="your-key-here"

# Option 3: OpenAI (API key required)
pip install openai
export OPENAI_API_KEY="your-key-here"
```

The Python parser will work without any additional dependencies and will display:
- Module docstring
- All imports
- Global variables with type hints
- Functions with parameters, return types, and complexity
- Classes with methods, attributes, and inheritance

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

### Phase 3: AI Enhancement ✅ (CURRENT)
- LLM client integration with multi-backend support
- AI-powered explanations for functions/classes
- Module summary generation
- Parameter description enhancement
- Multi-level caching (AST + AI)

### Phase 4: Output Formatters
- Markdown formatter
- HTML formatter with syntax highlighting
- JSON API reference formatter
- Docstring enhancement formatter

### Phase 5: CLI Interface
- `doc_gen.py generate` - Generate documentation
- `doc_gen.py enhance` - Add docstrings to code
- `doc_gen.py analyze` - Analyze code structure
- `doc_gen.py serve` - Start web UI

### Phase 6: Python API
- Make package installable
- Public API for programmatic use

### Phase 7: Web Interface
- FastAPI web server
- Upload and generate docs
- Preview and download

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
