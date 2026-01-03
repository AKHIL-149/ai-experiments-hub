# Quick Start

Get the Prompt Playground running in 2 minutes.

## Prerequisites

- Node.js 18+ installed
- Ollama installed and running
- At least one model pulled (e.g., llama3.2)

## Setup

```bash
cd javascript-projects/01-prompt-playground

# Install dependencies
npm install

# Start the server
npm start
```

## Access

Open your browser to:
```
http://localhost:3000
```

## Try It Out

1. Enter a prompt like "Explain quantum computing in simple terms"
2. Select a model (llama3.2)
3. Click "Generate"

## Compare Models

1. Select a second model from the "Model 2" dropdown
2. Click "Generate" to see side-by-side comparison

## Save Prompts

1. Enter a prompt you like
2. Click "Save Prompt"
3. Find it in the "Saved Prompts" section below
4. Click "Load" to reuse it later

## Tips

- Press Ctrl+Enter to generate without clicking the button
- Adjust temperature for more creative (1.0+) or focused (0.3) outputs
- Saved prompts are stored in your browser's local storage

## Troubleshooting

**"Generation failed" error:**
- Make sure Ollama is running: `ollama list`
- Check the model is pulled: `ollama pull llama3.2`

**Server won't start:**
- Port 3000 might be in use: Change PORT in `.env`
- Dependencies not installed: Run `npm install`
