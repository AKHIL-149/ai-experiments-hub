# Video Understanding & Summarization Platform

A comprehensive multi-modal AI platform for video analysis that combines visual understanding, audio transcription, and contextual intelligence to enable semantic search, automated highlighting, and intelligent summarization of video content.

## Features

### 🎥 Video Processing
- **Multi-source support**: YouTube URLs, local files, streaming URLs
- **Frame extraction**: Intelligent keyframe detection and quality filtering
- **Scene detection**: Multiple algorithms (content-based, optical flow, audio-based)
- **Video validation**: Format verification and codec compatibility checks

### 🎙️ Audio Analysis
- **Transcription**: OpenAI Whisper (API + local)
- **Speaker diarization**: Automatic speaker detection and labeling
- **Language detection**: Auto-detect spoken language
- **Audio features**: Music vs speech detection, emotion analysis

### 👁️ Visual Understanding
- **Object detection**: YOLO-based object recognition
- **Face detection**: Face recognition and tracking across frames
- **OCR**: Extract text from video frames
- **Action recognition**: Classify activities and actions
- **Natural language descriptions**: Generate frame descriptions using vision models

### 🔍 Semantic Search
- **CLIP embeddings**: Vision-language semantic similarity
- **Multi-modal retrieval**: Search using text across visual and audio content
- **Natural language queries**: Ask questions about video content
- **Timestamp-based results**: Precise temporal localization

### ✨ Intelligent Features
- **Highlight detection**: Automatically identify key moments
- **Video summarization**: Generate timestamped summaries
- **Chapter generation**: Detect natural chapter boundaries
- **Clip creation**: Extract and export highlight reels

### 🗄️ Storage & Retrieval
- **PostgreSQL**: Metadata and relational data
- **ChromaDB**: Vector embeddings for semantic search
- **Efficient caching**: Hash-based caching with TTL
- **Scalable storage**: Organized file structure for videos and frames

## Tech Stack

- **Web Framework**: FastAPI, WebSockets
- **Database**: PostgreSQL, SQLAlchemy, Alembic
- **Vector Store**: ChromaDB, FAISS
- **Video Processing**: ffmpeg, OpenCV, PySceneDetect
- **AI Models**:
  - CLIP (vision-language understanding)
  - Whisper (audio transcription)
  - LLaVA/GPT-4V (visual analysis)
  - pyannote.audio (speaker diarization)
- **ML Libraries**: transformers, sentence-transformers, torch

## Quick Start

### Prerequisites

- Python 3.9+
- ffmpeg (system package)
- PostgreSQL (or Docker)
- GPU (optional, for faster processing)

### Installation

```bash
# Clone the repository
cd /path/to/ai-experiments-hub/python-projects/15-video-understanding

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Install development dependencies
pip install -e ".[dev]"

# Copy environment template
cp .env.template .env
# Edit .env with your configuration

# Install ffmpeg (if not already installed)
# macOS:
brew install ffmpeg

# Ubuntu/Debian:
sudo apt-get install ffmpeg

# Windows:
# Download from https://ffmpeg.org/download.html
```

### Database Setup

```bash
# Option 1: Docker (recommended)
docker-compose up -d

# Option 2: Local PostgreSQL
createdb video_understanding

# Run migrations
alembic upgrade head
```

### Start the Server

```bash
# Start FastAPI server
python server.py

# Server will be available at http://localhost:8000
# API documentation: http://localhost:8000/docs
```

## Usage Examples

### 1. Process a Local Video

```bash
curl -X POST http://localhost:8000/api/videos/upload \
  -F "file=@video.mp4" \
  -F "title=My Video"

# Start processing
curl -X POST http://localhost:8000/api/videos/{video_id}/process
```

### 2. Process a YouTube Video

```bash
curl -X POST http://localhost:8000/api/videos/youtube \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://www.youtube.com/watch?v=VIDEO_ID",
    "title": "YouTube Video"
  }'
```

### 3. Semantic Search

```bash
# Search for visual content
curl -X POST http://localhost:8000/api/search/semantic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "person walking in a park",
    "top_k": 10
  }'
```

### 4. Ask Questions About a Video

```bash
curl -X POST http://localhost:8000/api/videos/{video_id}/ask \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What are the main topics discussed?"
  }'
```

### 5. Generate Highlights

```bash
curl -X POST http://localhost:8000/api/videos/{video_id}/highlights/generate \
  -H "Content-Type: application/json" \
  -d '{
    "max_highlights": 5,
    "min_importance": 0.7
  }'
```

## Project Structure

```
15-video-understanding/
├── src/
│   ├── core/          # Core utilities (database, video processing, caching)
│   ├── models/        # SQLAlchemy database models
│   ├── schemas/       # Pydantic schemas for validation
│   ├── sources/       # Video source handlers (YouTube, local, streaming)
│   ├── services/      # Business logic services
│   │   ├── scene_detection/
│   │   ├── clip/
│   │   ├── vector/
│   │   ├── fusion/
│   │   ├── summarization/
│   │   ├── highlights/
│   │   └── search/
│   ├── api/           # FastAPI endpoints
│   └── utils/         # Helper utilities
├── tests/             # Unit and integration tests
├── docs/              # Documentation
├── examples/          # Jupyter notebooks
├── alembic/           # Database migrations
├── server.py          # Main application entry point
└── pyproject.toml     # Project configuration
```

## Performance

### Processing Speed (10-minute video)
- Frame extraction: 1-2 minutes
- Scene detection: 30-60 seconds
- Transcription: 2-3 minutes (API) / 5-10 minutes (local)
- Full pipeline: 10-15 minutes (with parallel processing)
- Search query: <1 second

### Storage Requirements (per 10-minute video)
- Frames (1fps): 50-100 MB
- Database metadata: 10-20 MB
- CLIP embeddings: 1-2 MB
- Total: ~200-300 MB

## Architecture

The platform uses a multi-modal fusion architecture that combines:

1. **Visual Pipeline**: Frame extraction → Scene detection → CLIP embeddings
2. **Audio Pipeline**: Audio extraction → Whisper transcription → Speaker diarization
3. **Multi-Modal Fusion**: Temporal alignment → Context aggregation → Unified representation
4. **Search & Retrieval**: ChromaDB vector search → Multi-modal ranking → Results

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture documentation.

## API Documentation

Full API documentation is available at `/docs` when the server is running.

Key endpoints:
- `/api/videos/*` - Video management
- `/api/search/*` - Search and query
- `/api/clips/*` - Clip creation and export
- `/ws/process/{video_id}` - Real-time processing updates

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_scene_detection.py
```

### Code Formatting

```bash
# Format code
black src/ tests/

# Check linting
flake8 src/ tests/

# Type checking
mypy src/
```

## Deployment

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for production deployment guides:
- Docker deployment
- Kubernetes setup
- Environment configuration
- Model downloads
- Performance tuning

## Contributing

This project is part of the AI Experiments Hub. Contributions are welcome!

## License

MIT License

## Acknowledgments

Built with components from:
- Project 7: Content Analyzer (VisionClient, CacheManager)
- Project 9: Meeting Summarizer (VideoProcessor, TranscriptionService)
- Project 4: RAG Knowledge Assistant (VectorStore, ChromaDB integration)
- Project 14: Multi-Agent Orchestrator (FastAPI structure, database patterns)

## Roadmap

- [x] Phase 1: Foundation & Infrastructure
- [ ] Phase 2: Video Source Handlers
- [ ] Phase 3: Frame Extraction & Processing
- [ ] Phase 4: Scene Detection
- [ ] Phase 5: Audio Processing & Transcription
- [ ] Phase 6: Visual Analysis
- [ ] Phase 7: CLIP Integration
- [ ] Phase 8: Vector Storage
- [ ] Phase 9: Multi-Modal Fusion
- [ ] Phase 10: Summary Generation
- [ ] Phase 11: Highlight Detection
- [ ] Phase 12: Search & Query System
- [ ] Phase 13-14: API & Documentation

## Support

For questions or issues, please check the documentation or create an issue in the repository.

---

**Version**: 15.1.1
**Status**: In Development
**Last Updated**: 2026-07-19
