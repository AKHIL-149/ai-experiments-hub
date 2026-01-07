# Code Documentation Generator - Usage Guide

## Table of Contents
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Usage](#cli-usage)
- [Web Interface](#web-interface)
- [Python API](#python-api)
- [Configuration](#configuration)
- [Examples](#examples)

## Installation

### Basic Installation
```bash
cd python-projects/06-code-doc-generator
pip install -e .
```

### With AI Support
```bash
pip install -e ".[ai]"
```

### With Web Interface
```bash
pip install -e ".[web]"
```

### Full Installation
```bash
pip install -e ".[all]"
```

## Quick Start

### Generate Documentation from Command Line
```bash
# Basic usage - generate markdown documentation
python doc_gen.py generate mycode.py

# Generate HTML documentation
python doc_gen.py generate mycode.py --format html --output docs/

# Without AI enhancement
python doc_gen.py generate mycode.py --no-ai

# Using specific LLM provider
python doc_gen.py generate mycode.py --provider anthropic --model claude-3-5-sonnet-20241022
```

### Start Web Interface
```bash
python doc_gen.py serve --port 8000
```

Then open http://localhost:8000 in your browser.

## CLI Usage

### Generate Command

Generate documentation from code files.

```bash
python doc_gen.py generate <input> [options]
```

**Options:**
- `--format, -f`: Output format(s) - markdown, html, json, or comma-separated list
- `--output, -o`: Output directory (default: ./data/output)
- `--provider`: LLM provider - ollama (default), anthropic, openai
- `--model, -m`: Specific model to use
- `--no-ai`: Disable AI enhancement
- `--no-cache`: Disable caching
- `--recursive, -r`: Process directories recursively

**Examples:**

```bash
# Single file to markdown
python doc_gen.py generate src/example.py

# Directory with multiple formats
python doc_gen.py generate src/ --format markdown,html,json --output docs/

# Using Claude AI
python doc_gen.py generate src/ --provider anthropic --model claude-3-5-sonnet-20241022

# Large codebase without caching
python doc_gen.py generate src/ --no-cache --recursive
```

### Enhance Command

Add or update docstrings in source code.

```bash
python doc_gen.py enhance <input> [options]
```

**Options:**
- `--output, -o`: Output file path (default: <input>_documented)
- `--style`: Docstring style - auto, google, numpy, sphinx
- `--provider`: LLM provider
- `--model, -m`: Specific model to use

**Examples:**

```bash
# Enhance with Google-style docstrings
python doc_gen.py enhance mycode.py --style google

# Save to specific file
python doc_gen.py enhance src/utils.py --output src/utils_docs.py

# Using OpenAI
python doc_gen.py enhance mycode.py --provider openai --model gpt-4
```

### Analyze Command

Analyze code structure without generating documentation.

```bash
python doc_gen.py analyze <input>
```

**Example:**

```bash
python doc_gen.py analyze src/

# Output:
# 📊 Code Analysis Results
#
# Language: Python
# Files: 15
# Functions: 42
# Classes: 8
# Total Lines: 1,234
```

### Serve Command

Start the web interface.

```bash
python doc_gen.py serve [options]
```

**Options:**
- `--host`: Host to bind to (default: 127.0.0.1)
- `--port`: Port to bind to (default: 8000)

**Example:**

```bash
# Start on custom port
python doc_gen.py serve --port 5000

# Allow external connections
python doc_gen.py serve --host 0.0.0.0 --port 8000
```

## Web Interface

### Uploading Code

1. **File Upload**: Drag and drop a code file or click to browse
2. **Paste Code**: Switch to "Paste Code" tab and paste your code

### Configuration Options

- **Language**: Auto-detect or manually select (Python, JavaScript, TypeScript, Java)
- **Output Format**: Choose between Markdown, HTML, or JSON
- **AI Enhancement**: Toggle AI-powered explanations on/off
- **LLM Provider**: Select Ollama (local), Anthropic, or OpenAI
- **Model**: Optionally specify a model (e.g., llama3.2, claude-3-5-sonnet)

### Viewing Results

The results page shows:
- **Original Code**: Syntax-highlighted source code
- **Generated Documentation**: Formatted documentation
- **Statistics**: Functions, classes, and line counts
- **Metadata**: Timestamp, provider, model, processing time

### Actions

- **Copy**: Copy code or documentation to clipboard
- **Download**: Download documentation in selected format
- **Generate Another**: Return to upload page

## Python API

### Basic Usage

```python
from src import DocGenerator

# Initialize generator
generator = DocGenerator(
    llm_provider='ollama',
    model='llama3.2',
    use_ai=True
)

# Generate documentation
generator.generate_docs(
    input_path='src/myproject',
    output_format='markdown',
    output_dir='docs/'
)
```

### Advanced Usage

```python
from src import DocGenerator, ParserRegistry
from src.parsers.models import ParsedModule

# Get specific parser
registry = ParserRegistry()
parser = registry.get_parser('example.py')

# Parse file
parsed: ParsedModule = parser.parse_file('example.py')

# Access parsed data
print(f"Functions: {len(parsed.functions)}")
print(f"Classes: {len(parsed.classes)}")

# Generate with custom settings
generator = DocGenerator(
    llm_provider='anthropic',
    model='claude-3-5-sonnet-20241022',
    use_ai=True,
    enable_cache=False
)

# Generate multiple formats
for fmt in ['markdown', 'html', 'json']:
    generator.generate_docs(
        input_path='mycode.py',
        output_format=fmt,
        output_dir=f'docs/{fmt}/'
    )
```

### Enhance Code Programmatically

```python
from src import DocGenerator

generator = DocGenerator(use_ai=True)

# Add docstrings to code
generator.enhance_code(
    input_path='src/utils.py',
    output_path='src/utils_documented.py'
)
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# LLM Configuration
LLM_PROVIDER=ollama
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# Anthropic
ANTHROPIC_API_KEY=your_api_key_here

# OpenAI
OPENAI_API_KEY=your_api_key_here
OPENAI_MODEL=gpt-4

# Cache Settings
ENABLE_CACHE=true
CACHE_DIR=./data/cache
CACHE_EXPIRY_DAYS=7

# Output Settings
DEFAULT_OUTPUT_DIR=./data/output
DEFAULT_FORMAT=markdown

# Web Server
WEB_HOST=127.0.0.1
WEB_PORT=8000
```

### LLM Provider Setup

#### Ollama (Local)
```bash
# Install Ollama
curl https://ollama.ai/install.sh | sh

# Pull a model
ollama pull llama3.2

# Verify
ollama list
```

#### Anthropic (Claude)
```bash
# Set API key
export ANTHROPIC_API_KEY="your-key-here"
```

#### OpenAI (GPT)
```bash
# Set API key
export OPENAI_API_KEY="your-key-here"
```

## Examples

### Example 1: Document Entire Project

```bash
# Generate comprehensive documentation for a project
python doc_gen.py generate src/ \
  --format markdown,html \
  --output docs/ \
  --provider ollama \
  --model llama3.2 \
  --recursive
```

### Example 2: Quick Analysis

```bash
# Analyze code structure without AI
python doc_gen.py analyze src/ --no-ai
```

### Example 3: Enhance Legacy Code

```bash
# Add docstrings to legacy Python code
python doc_gen.py enhance legacy/old_module.py \
  --output legacy/old_module_documented.py \
  --style google \
  --provider anthropic
```

### Example 4: Web UI for Team

```bash
# Start web interface for team use
python doc_gen.py serve \
  --host 0.0.0.0 \
  --port 8080
```

### Example 5: API Integration

```python
# Integration in CI/CD pipeline
import os
from src import DocGenerator

def document_on_commit():
    """Generate docs on git commit"""
    generator = DocGenerator(
        llm_provider=os.getenv('LLM_PROVIDER', 'ollama'),
        use_ai=True
    )

    # Document changed files
    generator.generate_docs(
        input_path='src/',
        output_format='markdown',
        output_dir='docs/api/',
        recursive=True
    )

    print("✅ Documentation updated")

if __name__ == '__main__':
    document_on_commit()
```

## Troubleshooting

### Common Issues

**1. Import Errors**
```bash
# Install all dependencies
pip install -e ".[all]"
```

**2. LLM Connection Failed**
```bash
# For Ollama, ensure service is running
ollama serve

# For API providers, check environment variables
echo $ANTHROPIC_API_KEY
```

**3. Node.js Required for JavaScript**
```bash
# Install Node.js for JavaScript/TypeScript parsing
# macOS
brew install node

# Ubuntu
sudo apt install nodejs npm
```

**4. Cache Issues**
```bash
# Clear cache
rm -rf data/cache/

# Disable cache
python doc_gen.py generate src/ --no-cache
```

### Performance Tips

1. **Use Caching**: Enable caching for faster repeated generations
2. **Local LLM**: Use Ollama for offline/faster processing
3. **Batch Processing**: Process multiple files in one command
4. **Disable AI**: Use `--no-ai` for structure-only documentation

## Support

- **Issues**: https://github.com/AKHIL-149/ai-experiments-hub/issues
- **Documentation**: See README.md
- **Source Code**: https://github.com/AKHIL-149/ai-experiments-hub/tree/main/python-projects/06-code-doc-generator
