# Content Analyzer - Vision AI Image Analysis

AI-powered image analysis tool with vision capabilities for image description, visual Q&A, and OCR text extraction.

## Current Status: Phase 5 - Web Interface ✅

**Implemented:**
- ✅ Vision API integration with Ollama/LLaVA (local ~70% accuracy)
- ✅ **Anthropic Claude 3.5 Sonnet** (cloud ~90-95% accuracy)
- ✅ **OpenAI GPT-4 Vision** (cloud ~85-90% accuracy)
- ✅ Enhanced prompt templates for better accuracy
- ✅ Image loading and processing
- ✅ CLI with presets and multiple providers
- ✅ Support for file paths and URLs
- ✅ **Tesseract OCR** for text extraction
- ✅ **Vision model fallback** for low-confidence OCR results
- ✅ **Language detection** for multilingual documents
- ✅ Structured data extraction from forms, receipts, and invoices
- ✅ **Response caching** with image hash-based keys
- ✅ **Cost tracking** for cloud API usage
- ✅ **Retry logic** with exponential backoff
- ✅ **Rate limiting** for API calls
- ✅ **Web Interface** with drag-and-drop
- ✅ **REST API** with FastAPI
- ✅ **Interactive UI** with Bootstrap 5

**Not Yet Implemented:**
- ❌ Advanced features (image comparison, batch processing)

## Prerequisites

- **Python 3.8+**
- **Ollama** with LLaVA model (for local processing)
- **Optional**: Tesseract OCR (for text extraction - Phase 3)
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

### Option 3: Tesseract OCR (For Text Extraction)

**Tesseract OCR** (open-source, free):
```bash
# macOS
brew install tesseract

# Ubuntu/Debian
sudo apt-get install tesseract-ocr

# Windows
# Download from: https://github.com/UB-Mannheim/tesseract/wiki

# Verify installation
tesseract --version

# Install additional languages (optional)
# macOS
brew install tesseract-lang

# Ubuntu/Debian
sudo apt-get install tesseract-ocr-fra  # French
sudo apt-get install tesseract-ocr-spa  # Spanish
sudo apt-get install tesseract-ocr-deu  # German
```

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

# For OCR capabilities (Phase 3)
pip install pytesseract

# Or install all optional dependencies
pip install anthropic openai pytesseract

# For web interface (Phase 5)
pip install fastapi uvicorn python-multipart
```

## Usage

### 🌐 Web Interface (Recommended)

Start the web server for an interactive, user-friendly experience:

```bash
# Start the web server
python server.py

# Or with custom host/port
uvicorn server:app --host 0.0.0.0 --port 8000
```

**Access the interface:**
- 🌐 Web UI: http://localhost:8000
- 📚 API Docs: http://localhost:8000/docs
- 🔍 OpenAPI Spec: http://localhost:8000/redoc

**Features:**
- ✨ **Drag & Drop** image upload
- 🎨 **Vision Analysis** with real-time results
- 📄 **OCR Text Extraction** from images
- 📊 **Cache Statistics** dashboard
- 🎯 **Provider Selection** (Anthropic, OpenAI, Ollama)
- 🔧 **Preset Templates** for better accuracy
- 💾 **Caching** for faster responses
- 📋 **Copy to Clipboard** functionality

**Web API Endpoints:**
```bash
# Health check
GET /api/health

# Analyze image
POST /api/analyze
- File upload (multipart/form-data)
- Parameters: provider, preset, temperature, max_tokens, enable_cache

# Extract text (OCR)
POST /api/ocr
- File upload (multipart/form-data)
- Parameters: method, language, provider, fallback, confidence

# Detect language
POST /api/detect-language
- File upload (multipart/form-data)
- Parameters: use_vision, provider

# Cache statistics
GET /api/cache/stats

# Cache cleanup
POST /api/cache/cleanup

# Clear cache
POST /api/cache/clear
```

### 💻 CLI (Command Line Interface)

For automation and scripting:

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

## 📝 OCR Text Extraction (Phase 3)

### Basic OCR Usage

```bash
# Extract text from image using Tesseract
python analyze.py ocr document.jpg

# Extract text with specific language
python analyze.py ocr receipt.jpg --language eng

# Extract from French document
python analyze.py ocr french_doc.jpg --language fra

# Extract from Spanish document
python analyze.py ocr spanish_doc.jpg --language spa
```

### OCR with Vision Model Fallback

For best results, combine Tesseract with vision model fallback. If Tesseract has low confidence, the vision model will be used automatically:

```bash
# Auto fallback to vision model if Tesseract confidence < 60%
python analyze.py ocr receipt.jpg --fallback --provider anthropic

# Custom confidence threshold (70%)
python analyze.py ocr form.png --fallback --confidence 70.0 --provider anthropic

# Use OpenAI for fallback
python analyze.py ocr invoice.pdf --fallback --provider openai
```

### Vision-Only OCR

For handwritten text or complex layouts, use vision models directly (no Tesseract):

```bash
# Anthropic Claude (best for complex documents)
python analyze.py ocr handwritten.jpg --method vision --provider anthropic

# OpenAI GPT-4 Vision
python analyze.py ocr sketch.png --method vision --provider openai

# Ollama/LLaVA (local, free)
python analyze.py ocr notes.jpg --method vision --provider ollama
```

### Language Detection

Detect the language(s) in image text:

```bash
# Detect language using Tesseract
python analyze.py detect-language multilingual_doc.jpg

# Detect language using vision model
python analyze.py detect-language document.jpg --use-vision --provider anthropic
```

### Saving OCR Results

```bash
# Save extracted text to file
python analyze.py ocr document.jpg --output-file extracted.txt

# Save full OCR results as JSON (includes confidence, bounding boxes, etc.)
python analyze.py ocr receipt.jpg --output-json results.json --verbose

# Both text and JSON
python analyze.py ocr form.png \
  --output-file text.txt \
  --output-json full_results.json \
  --verbose
```

### OCR Method Comparison

| Method | Accuracy | Speed | Cost | Best For |
|--------|----------|-------|------|----------|
| **Tesseract** | 70-85% | Fast | Free | Printed text, forms, receipts |
| **Tesseract + Fallback** | 85-95% | Medium | Low | Mixed quality documents |
| **Vision (Anthropic)** | 90-95% | Slow | $$$ | Handwriting, complex layouts |
| **Vision (OpenAI)** | 85-90% | Slow | $$ | General documents |
| **Vision (Ollama)** | 70-75% | Medium | Free | Quick local processing |

### OCR Examples

```bash
# Receipt with fallback for best accuracy
python analyze.py ocr receipt.jpg \
  --fallback \
  --provider anthropic \
  --output-file receipt_text.txt

# Multi-language document
python analyze.py ocr multilingual.jpg \
  --language eng+fra \
  --verbose

# Handwritten notes (vision-only)
python analyze.py ocr handwritten_notes.jpg \
  --method vision \
  --provider anthropic \
  --output-file notes.txt

# Form with structured data extraction
python analyze.py ocr tax_form.pdf \
  --method vision \
  --provider anthropic \
  --output-json form_data.json
```

## 💾 Caching & Cost Savings (Phase 4)

### How Caching Works

Content Analyzer automatically caches API responses based on:
- Image content (SHA256 hash)
- Text prompt
- Provider and model

**Benefits:**
- ⚡ Instant responses for repeated queries
- 💰 Significant cost savings on cloud APIs
- 🌍 Reduced API usage and environmental impact

**Default Settings:**
- Cache TTL: 24 hours
- Max cache size: 500 MB
- Auto-cleanup when size limit reached

### Cache Statistics

View cache performance and cost savings:

```bash
# Show cache stats
python analyze.py cache-stats
```

**Output:**
```
📊 Cache Statistics:
============================================================
Hits: 45
Misses: 23
Total Requests: 68
Hit Rate: 66.18%
Cache Saves: 45
Cache Size: 12.5 MB

💰 Cost Savings (Estimated):
Anthropic: $0.1350
OpenAI: $0.0450
Total: $0.1800
============================================================
```

### Cache Management

```bash
# Clean up expired cache entries
python analyze.py cache-cleanup

# Keep only recent entries (last 24 hours)
python analyze.py cache-cleanup --keep-hours 24

# Clear all cache
python analyze.py cache-clear
```

### Disable Caching

For testing or when you need fresh results:

```bash
# Disable cache for single request
python analyze.py describe image.jpg --no-cache

# All subsequent requests will still use cache by default
python analyze.py describe image.jpg
```

### Cost Estimation

The cache manager estimates costs based on:
- **Anthropic Claude 3.5 Sonnet**: ~$3 per 1M tokens
- **OpenAI GPT-4 Vision**: ~$10 per 1M tokens

**Example savings:**
- 100 cached requests with Anthropic: ~$0.30 saved
- 500 cached requests with OpenAI: ~$5.00 saved

### Cache Location

Cache files are stored in:
```
07-content-analyzer/data/cache/
├── responses/     # Cached API responses
├── images/        # Processed images
└── stats.json     # Cache statistics
```

### Best Practices

1. **Regular Cleanup**: Run `cache-cleanup` weekly to remove old entries
2. **Monitor Size**: Check `cache-stats` to ensure cache isn't growing too large
3. **Fresh Results**: Use `--no-cache` when you need latest analysis
4. **Cost Tracking**: Review cost savings monthly to quantify benefits

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
├── server.py               # Web server (FastAPI)
├── requirements.txt        # Dependencies
├── .env.example           # Configuration template
├── README.md              # This file
├── src/
│   ├── __init__.py
│   └── core/
│       ├── __init__.py
│       ├── vision_client.py      # Vision API integration
│       ├── image_processor.py    # Image loading & processing
│       ├── prompt_templates.py   # Enhanced prompt templates
│       ├── ocr_processor.py      # OCR text extraction
│       ├── cache_manager.py      # Response caching
│       ├── retry_handler.py      # Retry logic with backoff
│       └── rate_limiter.py       # API rate limiting
├── templates/
│   └── index.html         # Web UI
├── static/
│   └── app.js             # Frontend JavaScript
├── data/
│   └── cache/             # Cache storage
│       ├── responses/     # Cached API responses
│       ├── images/        # Processed images
│       └── stats.json     # Cache statistics
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

### Ollama Issues

**Error: "Connection refused"**
- Make sure Ollama is running: `ollama serve`
- Check Ollama is accessible: `curl http://localhost:11434/api/tags`

**Error: "Model not found"**
- Pull LLaVA model: `ollama pull llava`
- Verify: `ollama list`

### Image Issues

**Error: "Image file not found"**
- Check the file path is correct
- Use absolute paths if relative paths don't work

### OCR Issues

**Error: "pytesseract is not installed"**
- Install: `pip install pytesseract`
- Install Tesseract binary: `brew install tesseract` (macOS) or see Prerequisites

**Error: "TesseractNotFoundError"**
- Tesseract binary not in PATH
- macOS: `brew install tesseract`
- Ubuntu: `sudo apt-get install tesseract-ocr`
- Windows: Download from [UB-Mannheim](https://github.com/UB-Mannheim/tesseract/wiki)

**Low OCR confidence / Poor results**
- Use `--fallback` flag with vision model: `python analyze.py ocr image.jpg --fallback --provider anthropic`
- Try vision-only mode: `python analyze.py ocr image.jpg --method vision --provider anthropic`
- Check image quality (resolution, contrast, clarity)
- Specify correct language: `--language fra` for French

**Language not supported**
- Install language pack:
  - macOS: `brew install tesseract-lang`
  - Ubuntu: `sudo apt-get install tesseract-ocr-fra` (replace 'fra' with your language)
- List available languages: `tesseract --list-langs`

### Cloud Provider Issues

**Error: "ANTHROPIC_API_KEY not found"**
- Add API key to `.env` file
- Or export: `export ANTHROPIC_API_KEY=your_key_here`

**Error: "OPENAI_API_KEY not found"**
- Add API key to `.env` file
- Or export: `export OPENAI_API_KEY=your_key_here`

## Roadmap

- [x] **Phase 1**: Core vision with Ollama/LLaVA ✅
- [x] **Phase 2**: Cloud APIs (Claude, GPT-4 Vision) ✅
- [x] **Phase 3**: OCR capabilities with Tesseract ✅
- [x] **Phase 4**: Caching and error handling ✅
- [x] **Phase 5**: Web interface with drag-and-drop ✅
- [ ] **Phase 6**: Advanced features (image comparison, batch processing)

## License

Part of AI Experiments Hub

## Version

0.7.5 - Phase 5 Complete: Web Interface with FastAPI, Drag-and-Drop, and Interactive UI
