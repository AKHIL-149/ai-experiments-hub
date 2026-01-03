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
4. **Generate**: Click "Generate" or press Ctrl+Enter
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

By default, the following Ollama models are available:
- Llama 3.2 (general purpose)
- Mistral (fast and capable)
- CodeLlama (code-focused)

Pull additional models with:
```bash
ollama pull <model-name>
```

Then add them to the dropdown in `public/index.html`.

## Project Structure

```
01-prompt-playground/
├── public/
│   ├── index.html      # Main UI
│   ├── styles.css      # Styling
│   └── app.js          # Frontend logic
├── src/
│   └── server.js       # Express server + API
├── package.json
└── .env.example
```

## Implementation Notes

This project demonstrates:
- RESTful API design with Express
- Async/await patterns for API calls
- Local storage for client-side persistence
- Responsive UI design
- Error handling and loading states

The code prioritizes simplicity and clarity. No complex build tools or frameworks - just clean vanilla JavaScript.

## Future Enhancements

Potential additions:
- Cloud API support (Anthropic, OpenAI)
- Export conversation history
- Prompt templates library
- Statistics and analytics
- Dark mode
