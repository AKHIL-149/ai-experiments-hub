# Quick Start Guide

Get up and running with Code Documentation Generator in 5 minutes!

## 1. Installation (30 seconds)

```bash
cd python-projects/06-code-doc-generator
pip install -e ".[all]"
```

This installs the package with all optional dependencies (AI, Web, Utils).

## 2. Setup LLM (Optional - 2 minutes)

### Option A: Ollama (Recommended - Free & Local)

```bash
# Install Ollama
curl https://ollama.ai/install.sh | sh

# Pull a model
ollama pull llama3.2

# Verify
ollama list
```

### Option B: Use API Keys

```bash
# For Anthropic Claude
export ANTHROPIC_API_KEY="your-key-here"

# For OpenAI GPT
export OPENAI_API_KEY="your-key-here"
```

## 3. Generate Your First Documentation (10 seconds)

### Using the Web Interface (Easiest!)

```bash
python doc_gen.py serve
```

Then open http://localhost:8000 and:
1. Drag & drop a code file
2. Click "Generate Documentation"
3. View results!

### Using the CLI

```bash
# Generate markdown documentation
python doc_gen.py generate examples/example.py

# Output will be in data/output/
```

## 4. Try Different Formats

```bash
# Generate HTML documentation
python doc_gen.py generate examples/example.py --format html

# Generate all formats
python doc_gen.py generate examples/example.py --format all

# Without AI (faster, template-only)
python doc_gen.py generate examples/example.py --no-ai
```

## 5. Use as Python Library

```python
from src import DocGenerator

# Initialize
generator = DocGenerator(use_ai=True)

# Generate docs
generator.generate_docs(
    input_path='mycode.py',
    output_format='markdown',
    output_dir='docs/'
)
```

## Common Commands

```bash
# Analyze code structure
python doc_gen.py analyze mycode.py

# Enhance code with docstrings
python doc_gen.py enhance mycode.py --output mycode_documented.py

# Process entire directory
python doc_gen.py generate src/ --recursive --format markdown,html

# Start web interface on different port
python doc_gen.py serve --port 5000
```

## Testing with Examples

We've included example files for testing:

```bash
# Python example
python doc_gen.py generate examples/example.py

# JavaScript example
python doc_gen.py generate examples/example.js

# View generated docs
ls data/output/
```

## What's Next?

- **Full Documentation**: See [USAGE.md](USAGE.md) for comprehensive guide
- **API Reference**: See [API.md](API.md) for REST API details
- **Changelog**: See [CHANGELOG.md](CHANGELOG.md) for version history

## Troubleshooting

**Problem:** `ModuleNotFoundError: No module named 'fastapi'`
**Solution:** Install web dependencies: `pip install -e ".[web]"`

**Problem:** `Connection refused` for Ollama
**Solution:** Start Ollama service: `ollama serve`

**Problem:** JavaScript/TypeScript parsing fails
**Solution:** Install Node.js: `brew install node` (macOS) or `sudo apt install nodejs` (Ubuntu)

**Problem:** Need help
**Solution:** Run `python doc_gen.py --help` or check [USAGE.md](USAGE.md)

## 5-Minute Tutorial

### Step 1: Create a simple Python file

```python
# test.py
def greet(name):
    return f"Hello, {name}!"

class Calculator:
    def add(self, a, b):
        return a + b
```

### Step 2: Generate documentation

```bash
python doc_gen.py generate test.py
```

### Step 3: View the output

```bash
cat data/output/test.md
```

### Step 4: Try HTML format

```bash
python doc_gen.py generate test.py --format html
open data/output/test.html  # macOS
# or
xdg-open data/output/test.html  # Linux
```

### Step 5: Add AI-generated docstrings

```bash
python doc_gen.py enhance test.py --output test_documented.py
cat test_documented.py
```

## Web Interface Features

When using `python doc_gen.py serve`:

- **Drag & Drop**: Just drag your code file into the browser
- **Paste Code**: Or paste code directly
- **Multiple Formats**: Choose Markdown, HTML, or JSON
- **AI Providers**: Select Ollama (local), Claude, or GPT
- **Live Preview**: See results instantly
- **Download**: Download documentation in any format
- **Copy**: Copy to clipboard with one click

## Need More Help?

- **GitHub Issues**: https://github.com/AKHIL-149/ai-experiments-hub/issues
- **Full Guide**: [USAGE.md](USAGE.md)
- **API Docs**: [API.md](API.md)

Happy documenting! 🚀📚
