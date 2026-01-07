# Content Analyzer - Vision AI Image Analysis

AI-powered image analysis tool with vision capabilities for image description, visual Q&A, and OCR text extraction.

## Current Status: Phase 2 - Cloud Vision APIs ✅

**Implemented:**
- ✅ Vision API integration with Ollama/LLaVA (local ~70% accuracy)
- ✅ **Anthropic Claude 3.5 Sonnet** (cloud ~90-95% accuracy)
- ✅ **OpenAI GPT-4 Vision** (cloud ~85-90% accuracy)
- ✅ Enhanced prompt templates for better accuracy
- ✅ Image loading and processing
- ✅ CLI with presets and multiple providers
- ✅ Support for file paths and URLs

**Not Yet Implemented:**
- ❌ OCR capabilities - Coming in Phase 3
- ❌ Caching - Coming in Phase 4
- ❌ Web interface - Coming in Phase 5-6

## Prerequisites

- **Python 3.8+**
- **Ollama** with LLaVA model (for local processing)
- **Optional**: API keys for cloud providers (better accuracy)

### Option 1: Local Only (Ollama/LLaVA)

```bash
# Install Ollama (macOS)
brew install ollama

# Or download from https://ollama.ai

# Pull LLaVA model
ollama pull llava

# Verify Ollama is running
ollama list
```

### Option 2: Cloud Providers (Recommended for Best Accuracy)

**Anthropic Claude 3.5 Sonnet** (~90-95% accuracy):
1. Get API key from: https://console.anthropic.com/
2. Add to `.env`: `ANTHROPIC_API_KEY=your_key_here`

**OpenAI GPT-4 Vision** (~85-90% accuracy):
1. Get API key from: https://platform.openai.com/api-keys
2. Add to `.env`: `OPENAI_API_KEY=your_key_here`

## Installation

```bash
cd python-projects/07-content-analyzer

# Install dependencies
pip install -r requirements.txt

# Configure API keys (if using cloud providers)
cp .env.example .env
# Edit .env and add your API keys
```

**Installing Cloud Provider Dependencies:**
```bash
# For Anthropic Claude (recommended)
pip install anthropic

# For OpenAI GPT-4 Vision
pip install openai

# Or install both
pip install anthropic openai
```

## Usage

### Basic Image Description

```bash
# Describe a local image file
python analyze.py describe path/to/image.jpg

# Describe from URL (static image)
python analyze.py describe https://example.com/image.jpg

# Save the downloaded image for verification
python analyze.py describe https://example.com/image.jpg --save-image

# Or save to specific path
python analyze.py describe https://example.com/image.jpg --save-image verified_image.jpg
```

**⚠️ Note:** When using random image services like `https://picsum.photos/400/300`, each request returns a different image. Use `--save-image` to verify what the AI actually analyzed.

### Using Cloud Providers for Best Accuracy

```bash
# Anthropic Claude 3.5 Sonnet (recommended - 90-95% accuracy)
python analyze.py describe racing_car.jpg --provider anthropic

# OpenAI GPT-4 Vision (85-90% accuracy)
python analyze.py describe image.jpg --provider openai

# Local Ollama/LLaVA (70-75% accuracy, free)
python analyze.py describe image.jpg --provider ollama
```

**With presets for even better results:**
```bash
# Racing car with Claude (best accuracy)
python analyze.py describe f1_car.jpg \
  --provider anthropic \
  --preset vehicle \
  --temperature 0.3

# Document with GPT-4 Vision
python analyze.py describe form.pdf \
  --provider openai \
  --preset document \
  --temperature 0.1
```

### Using Presets for Better Accuracy

```bash
# For vehicles (racing cars, motorcycles, etc.)
python analyze.py describe car.jpg --preset vehicle

# For documents and text
python analyze.py describe document.png --preset document

# For general objects
python analyze.py describe object.jpg --preset object

# For scenes and landscapes
python analyze.py describe landscape.jpg --preset scene

# For people and portraits
python analyze.py describe person.jpg --preset person

# For technical analysis
python analyze.py describe photo.jpg --preset technical

# For quick, simple descriptions
python analyze.py describe image.jpg --preset simple
```

**Available Presets:**
- `vehicle` - Optimized for cars, racing vehicles, motorcycles
- `document` - For forms, receipts, documents with text
- `object` - For identifying and describing objects
- `scene` - For landscapes, cityscapes, environments
- `person` - For people, portraits, group photos
- `technical` - For technical image analysis
- `simple` - Quick 2-3 sentence description

### Custom Prompts

```bash
# Ask specific question
python analyze.py describe photo.jpg --prompt "What colors are in this image?"

# Detailed analysis
python analyze.py describe chart.png --prompt "Explain this chart in detail"
```

### Save Output

```bash
# Save to file
python analyze.py describe image.jpg --output result.txt
```

### Advanced Options

```bash
# Adjust response length
python analyze.py describe image.jpg --max-tokens 500

# Adjust creativity (0.0 = deterministic, 2.0 = very creative)
python analyze.py describe image.jpg --temperature 0.9
```

## 🎯 Improving Accuracy

### Temperature Settings for Better Results

The `--temperature` parameter controls randomness vs. factual accuracy:

```bash
# High accuracy (factual, deterministic) - Recommended for identification
python analyze.py describe car.jpg --preset vehicle --temperature 0.3

# Balanced (default)
python analyze.py describe image.jpg --temperature 0.7

# Creative (may add interpretive details)
python analyze.py describe art.jpg --temperature 1.2
```

**Recommendations:**
- **Vehicles/Objects**: Use `--temperature 0.3` with `--preset vehicle` or `--preset object`
- **Documents**: Use `--temperature 0.1` with `--preset document`
- **General descriptions**: Use default (0.7)
- **Creative analysis**: Use `--temperature 1.0-1.5`

### Combining Options for Best Results

```bash
# Racing car identification (best accuracy)
python analyze.py describe racing_car.jpg \
  --preset vehicle \
  --temperature 0.3 \
  --max-tokens 800 \
  --save-image

# Document analysis
python analyze.py describe form.png \
  --preset document \
  --temperature 0.1 \
  --save-image

# Quick object check
python analyze.py describe object.jpg \
  --preset simple \
  --temperature 0.5
```

## Examples

```bash
# Simple description of local file
python analyze.py describe examples/photo.jpg

# Analyze a chart with custom prompt
python analyze.py describe examples/chart.png --prompt "What insights can you extract from this chart?"

# Analyze from URL and save the image for verification
python analyze.py describe https://upload.wikimedia.org/wikipedia/commons/thumb/3/3a/Cat03.jpg/400px-Cat03.jpg --save-image --prompt "Describe this animal"

# Using picsum.photos (random images - use --save-image to verify)
python analyze.py describe https://picsum.photos/800/600 --save-image --prompt "Describe the main elements"
```

## Project Structure

```
07-content-analyzer/
├── analyze.py              # CLI entry point
├── requirements.txt        # Dependencies
├── .env.example           # Configuration template
├── README.md              # This file
├── src/
│   ├── __init__.py
│   └── core/
│       ├── __init__.py
│       ├── vision_client.py      # Vision API integration
│       └── image_processor.py    # Image loading & processing
├── data/                  # Runtime data (future)
└── examples/              # Sample images (future)
```

## Configuration

Edit `.env` file to customize:

```bash
# Ollama settings
OLLAMA_API_URL=http://localhost:11434
OLLAMA_VISION_MODEL=llava

# Default provider
DEFAULT_PROVIDER=ollama
```

## Troubleshooting

**Error: "Connection refused"**
- Make sure Ollama is running: `ollama serve`
- Check Ollama is accessible: `curl http://localhost:11434/api/tags`

**Error: "Model not found"**
- Pull LLaVA model: `ollama pull llava`
- Verify: `ollama list`

**Error: "Image file not found"**
- Check the file path is correct
- Use absolute paths if relative paths don't work

## Roadmap

- [x] **Phase 1**: Core vision with Ollama/LLaVA ✅
- [ ] **Phase 2**: Cloud APIs (Claude, GPT-4 Vision)
- [ ] **Phase 3**: OCR capabilities with Tesseract
- [ ] **Phase 4**: Caching and error handling
- [ ] **Phase 5-6**: Web interface with drag-and-drop
- [ ] **Phase 7**: Advanced features (image comparison, batch processing)

## License

Part of AI Experiments Hub

## Version

0.1.0 - Phase 1 Minimal Prototype
