# Quick Start

Get up and running in 3 minutes.

## Prerequisites

Make sure Ollama is installed and running:
```bash
ollama --version
ollama pull llama3.2
```

## Setup

```bash
# Navigate to project
cd python-projects/01-text-generator

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Try It Out

```bash
# Simple generation
python generate.py "Write a haiku about programming"

# Use a template
python generate.py --template poem "Autumn leaves"

# Generate an email
python generate.py --template email "Thank the team for completing the sprint"

# Creative story with high temperature
python generate.py --template story --temperature 1.2 "A robot learns to paint"

# Save to file
python generate.py "Explain recursion" --output explanation.txt
```

## Using Cloud APIs

If you want to use Anthropic or OpenAI instead of local models:

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your API key
# ANTHROPIC_API_KEY=sk-ant-...

# Use it
python generate.py --backend anthropic "Your prompt here"
```

## Next Steps

- Check `examples/example_usage.py` for programmatic usage
- Read the full README.md for more options
- Experiment with different temperatures and max tokens
- Try different templates
