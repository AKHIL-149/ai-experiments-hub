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
