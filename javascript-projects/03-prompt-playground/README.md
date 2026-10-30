# Prompt Playground

Web interface for testing and comparing prompts across different LLM models. Experiment with different prompts, models, and parameters side-by-side.

## Features

- Clean, intuitive web interface
- Side-by-side model comparison
- Support for local models via Ollama
- Adjustable temperature and max tokens
- Save and load favorite prompts
- Real-time generation with progress indication

## Setup

Install dependencies:

```bash
npm install
```

Configure environment (optional):

```bash
cp .env.example .env
# Edit .env if needed (defaults work with standard Ollama setup)
```

## Usage

Start the server:

```bash
npm start
```

Open your browser to:
```
http://localhost:3000
```

## How to Use

1. **Enter a Prompt**: Type your prompt in the text area
2. **Select Model(s)**: Choose one or two models to compare
3. **Adjust Parameters**: Set temperature (creativity) and max tokens
4. **Generate**: Click "Generate" or press Ctrl+Enter (Cmd+Enter on Mac)
5. **Save Prompts**: Save good prompts for later use

## Tips

**Temperature:**
- `0.0-0.3`: Focused, deterministic outputs
- `0.7-0.9`: Balanced creativity
- `1.0-2.0`: Highly creative, varied outputs

**Comparison Mode:**
- Select a second model to see responses side-by-side
- Great for evaluating different models on the same prompt
- Compare creativity, accuracy, and style

**Saved Prompts:**
- Click "Save Prompt" to store prompts locally
- Saved prompts persist in browser storage
- Click "Load" to reuse a saved prompt

## Available Models

The dropdowns list whatever is installed in your Ollama (embedding models are hidden), so there is nothing to edit. Pull more with:
```bash
ollama pull <model-name>
```
then reload the page. If Ollama is not reachable, a banner explains how to start it.

## Comparing Models

With two models selected they run one after the other, not at the same time, so they don't fight over the same GPU/CPU. Each panel shows time, tokens, **tokens/s** (measured by Ollama, so it is a fair speed comparison), and a note when the output stopped at the Max Tokens limit.

Thinking models (e.g. `qwen3`) spend tokens on hidden reasoning; with a small Max Tokens they can return no text, and the panel says so.

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `PORT` | `3000` | Port to listen on |
| `HOST` | `127.0.0.1` | Interface to bind. Loopback only, so other machines on your network cannot use your Ollama |
| `OLLAMA_API_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_TIMEOUT` | `300` | Seconds to wait for one generation |
| `CORS_ORIGIN` | (none) | Allow another web origin to call the API |

Temperature accepts 0-2 (0 is respected and gives repeatable output); Max Tokens accepts 1-8192.

## Tests

```bash
npm test
```

The tests run the real server against a fake Ollama, so no model is needed.
