# AI Text Generator

A CLI tool for generating various types of content using LLMs. Supports both local models via Ollama and cloud APIs (Anthropic Claude, OpenAI).

## Features

- Generate stories, poems, emails, and other creative content
- Support for multiple LLM backends (local and cloud)
- Simple command-line interface
- Template-based generation for common use cases

## Setup

Create and activate a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure your environment:

```bash
cp ../../.env.example .env
# Edit .env with your API keys if using cloud models
```

## Usage

Basic text generation:

```bash
python src/generator.py "Write a haiku about coding"
```

Using a template:

```bash
python src/generator.py --template email "Respond to client about project delay"
```

Specify a model:

```bash
# Use Ollama (local)
python src/generator.py --backend ollama --model llama3.2 "Your prompt"

# Use Anthropic Claude
python src/generator.py --backend anthropic --model claude-3-5-sonnet-20241022 "Your prompt"

# Use OpenAI
python src/generator.py --backend openai --model gpt-4 "Your prompt"
```

Options:
- `--max-tokens N` - output limit (default 1000). A warning is printed if the output was cut off.
- `--temperature T` - 0.0-2.0 (0.0-1.0 for Anthropic)
- `-o FILE` - save to a file (parent folders are created)
- `--plain` - print only the text, without the `====` frame. This happens automatically when output is piped, so `python generate.py "..." > out.txt` and `| pbcopy` work as expected.

Thinking models (e.g. `qwen3`) spend tokens on hidden reasoning, so give them a larger `--max-tokens`.

Available templates:
- `email` - Professional email writing
- `story` - Creative storytelling
- `poem` - Poetry generation
- `code` - Code explanation or generation

## Examples

See the `examples/` directory for more usage patterns.

## Implementation Notes

This project demonstrates:
- Basic LLM API integration
- Prompt engineering fundamentals
- CLI design patterns
- Environment-based configuration
- Error handling for API calls

The code prioritizes clarity and simplicity over advanced features.

## Tests

```bash
pip install pytest
python -m pytest tests -q
```

The suite mocks the backends, so it needs no Ollama or API keys.
