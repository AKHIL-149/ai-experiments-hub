# Example Files

This directory contains example code files for testing the Code Documentation Generator.

## Available Examples

### example.py (Python)
Comprehensive Python example featuring:
- Class with multiple methods
- Decorators and type hints
- Statistical calculations
- File I/O operations
- Algorithm implementations (Fibonacci, Prime numbers)
- Error handling

**Usage:**
```bash
# Generate markdown documentation
python ../doc_gen.py generate example.py

# Generate HTML documentation
python ../doc_gen.py generate example.py --format html

# Add AI docstrings
python ../doc_gen.py enhance example.py --output example_documented.py

# Analyze structure
python ../doc_gen.py analyze example.py
```

### example.js (JavaScript)
Modern JavaScript/ES6 example featuring:
- ES6 classes with async methods
- Promise-based authentication
- Task queue implementation
- Utility functions
- Functional programming patterns
- JSDoc comments

**Usage:**
```bash
# Generate documentation (requires Node.js)
python ../doc_gen.py generate example.js

# Generate all formats
python ../doc_gen.py generate example.js --format all
```

**Note:** JavaScript parsing requires Node.js to be installed.

## Testing Documentation Generation

### Test All Examples

```bash
# From the examples directory
cd examples

# Test Python
python ../doc_gen.py generate example.py --output ../data/output/

# Test JavaScript
python ../doc_gen.py generate example.js --output ../data/output/
```

### Compare Formats

```bash
# Generate all formats for comparison
python ../doc_gen.py generate example.py --format markdown,html,json
```

Output files will be in `../data/output/`:
- `example.md` - Markdown documentation
- `example.html` - HTML documentation with Bootstrap styling
- `example.json` - JSON API reference

### Test AI Enhancement

```bash
# Test with different LLM providers
python ../doc_gen.py generate example.py --provider ollama
python ../doc_gen.py generate example.py --provider anthropic
python ../doc_gen.py generate example.py --provider openai

# Test without AI
python ../doc_gen.py generate example.py --no-ai
```

## Web Interface Testing

Start the web server and test with example files:

```bash
# Start server
python doc_gen.py serve

# Open http://localhost:8000
# Drag and drop example.py or example.js
# Try different formats and providers
```

## Expected Output

### Markdown Example (excerpt)
```markdown
# Module: example

AI-generated module summary here...

## Functions

### `fibonacci(n: int) -> List[int]`
**Line**: 152

**Description**: Generate Fibonacci sequence up to n terms.

**Parameters**:
- `n` (int): Number of terms to generate

**Returns**: List[int] - List containing Fibonacci sequence
```

### HTML Example
Bootstrap 5 styled HTML with:
- Collapsible sections
- Syntax highlighting
- Table of contents
- Responsive design

### JSON Example (excerpt)
```json
{
  "module": "example.py",
  "language": "python",
  "functions": [
    {
      "name": "fibonacci",
      "line": 152,
      "signature": "fibonacci(n: int) -> List[int]",
      "parameters": [
        {"name": "n", "type": "int", "description": "..."}
      ]
    }
  ]
}
```

## Creating Your Own Examples

Want to test with your own code? Here's how:

1. **Copy your code** to this directory
2. **Run generator**: `python ../doc_gen.py generate yourcode.py`
3. **View output**: Check `../data/output/yourcode.md`

## Benchmarking

Test performance with different file sizes:

```bash
# Small file (example.py: ~200 lines)
time python ../doc_gen.py generate example.py

# Medium project
time python ../doc_gen.py generate ../src/ --recursive

# Without cache
time python ../doc_gen.py generate example.py --no-cache
```

## Common Issues

**JavaScript parsing fails:**
```bash
# Install Node.js
brew install node  # macOS
sudo apt install nodejs npm  # Ubuntu
```

**Import errors:**
```bash
# Install all dependencies
cd ..
pip install -e ".[all]"
```

**LLM not responding:**
```bash
# Check Ollama is running
ollama list

# Or verify API keys
echo $ANTHROPIC_API_KEY
```

## Integration Testing

Use these examples in your CI/CD pipeline:

```yaml
# .github/workflows/test-docs.yml
name: Test Documentation Generation

on: [push]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
      - name: Install dependencies
        run: |
          pip install -e ".[all]"
      - name: Test examples
        run: |
          python doc_gen.py generate examples/example.py --no-ai
          python doc_gen.py analyze examples/
```

## Contributing Examples

Want to add more examples? We welcome:
- **More languages**: TypeScript, Java examples
- **Different patterns**: Design patterns, frameworks
- **Complex projects**: Multi-file examples
- **Edge cases**: Unusual code structures

See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.
