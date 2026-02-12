# Project 12: Content Moderation System

**Version**: 1.3.0 (Phase 4)
**Status**: Phase 4 Complete - Asynchronous Queue System with Celery
**Architecture**: Full-stack AI-powered content moderation platform with distributed workers

## Overview

A production-ready content moderation system that uses AI to classify multi-modal content (text, images, video) for automated and human-assisted review. Built with FastAPI, SQLAlchemy, and multi-provider LLM support.

### Use Cases
- Social media platforms (comment/post moderation)
- E-commerce sites (review moderation)
- Community forums (content safety)
- Content platforms (UGC moderation)
- Enterprise policy enforcement

## Features

### Phase 4 ✅ (Current - Asynchronous Queue System)

**Celery Integration**:
- Distributed task queue with Redis broker
- Priority-based queues (critical, high, default, batch)
- Auto-discovery of worker tasks
- Exponential backoff retry logic with jitter
- Task time limits (5min soft, 10min hard)

**Queue Management**:
- QueueManager for job creation and tracking
- Job status monitoring with Celery task states
- Queue statistics and metrics
- Automatic job routing by priority
- Retry count tracking

**Worker Tasks**:
- Text classification worker (async LLM processing)
- Image classification worker (async NSFW + vision)
- Video classification worker (async frame analysis)
- BaseClassificationTask with common retry logic
- Progress tracking with state updates

**Real-time Updates**:
- WebSocket endpoint for job progress (`/ws/jobs/{job_id}`)
- Live status updates every 1 second
- Progress notifications (10%, 30%, 70%, 100%)
- Job completion/failure notifications

**API Endpoints**:
- `POST /api/content` - Submit content (returns job_id)
- `GET /api/jobs/{job_id}` - Get job status
- `GET /api/jobs/queue/stats` - Queue statistics (moderator)
- `WS /ws/jobs/{job_id}` - Real-time progress updates

**Performance Features**:
- Async processing (non-blocking submissions)
- Horizontal scalability (multiple workers)
- Task prefetch control (1 task per worker)
- Worker max tasks per child (1000 before restart)
- Result expiration (1 hour)

### Phase 3 ✅ (Video Moderation)

**Video Processing**:
- ffmpeg integration for frame extraction
- Configurable frame rate (default 1 fps)
- Maximum frames limit (default 100)
- Automatic video thumbnail generation
- Video metadata extraction (duration, resolution, codec, fps)

**Frame-by-Frame Classification**:
- Extract frames at specified rate
- Classify each frame using NSFW detection + vision models
- Aggregate results with confidence scoring
- Violation percentage calculation
- Category distribution analysis

**Video Classification Pipeline**:
- Frame extraction with ffmpeg
- NSFW detection on each frame
- Optional vision model classification
- Result aggregation strategy:
  - Max confidence for violations
  - Percentage of frames flagged
  - Most severe category selection
- Automatic frame cleanup after processing

**Graceful Degradation**:
- Fallback mode when ffmpeg unavailable
- Clear error messages for dependencies
- Optional video processing

### Phase 2 ✅ (Image Moderation)

**NSFW Detection**:
- Local NudeNet integration for fast NSFW detection
- Explicit content detection (exposed body parts)
- Suggestive content detection (context-based)
- Confidence scoring (0.0-1.0)
- Fallback mode when NudeNet unavailable

**File Handling**:
- Secure file upload with validation
- Automatic thumbnail generation (300x300, JPEG)
- SHA256 deduplication
- Support for JPEG, PNG, GIF, WebP
- File size validation (100MB limit)
- Image metadata extraction

**Enhanced Image Classification**:
- Two-stage classification pipeline:
  1. Fast local NSFW detection (NudeNet)
  2. Vision model classification (GPT-4V, Claude Vision)
- Combined confidence scoring
- Automatic status determination (approved/rejected/flagged)
- Cost tracking per classification

**Classification Service**:
- Unified API for text and image classification
- Multi-provider LLM support with fallback
- Moderation policy engine with configurable thresholds
- Processing time metrics
- Error handling with graceful degradation

### Phase 1 ✅ (Core Foundation)

**Authentication & Authorization**:

**Authentication & Authorization**:
- User registration with bcrypt password hashing (12 rounds)
- Session-based authentication (30-day TTL, HTTPOnly cookies)
- Role-based access control (User, Moderator, Admin)
- IP tracking for sessions
- Multi-session management

**Content Submission**:
- Text content submission
- Image upload (JPEG, PNG, GIF, WebP)
- Video upload (MP4, MOV, AVI, WebM)
- File hash deduplication (SHA256)
- Priority levels (Normal, High, Critical)
- File size limits (100MB default)

**AI Classification**:
- Multi-provider LLM support (Ollama, OpenAI, Anthropic)
- Text classification with 10 violation categories
- Image classification with vision models (GPT-4V, Claude Vision)
- Confidence scoring (0.0-1.0)
- Cost tracking for API usage
- Processing time metrics

**Database**:
- 8 SQLAlchemy models (User, Session, ContentItem, ModerationJob, Classification, Review, Policy, AuditLog)
- SQLite (development) / PostgreSQL (production) support
- Proper indexes for performance
- Cascade delete relationships

**Web Interface**:
- Responsive single-page application
- User authentication UI
- Content submission forms (text/image/video)
- Content list view with filtering
- Moderator review queue
- Admin panel (user management)

**API Endpoints**:
- Authentication: register, login, logout, me
- Content: submit, get, list, delete
- Moderation: queue, stats (moderator only)
- Admin: users, roles, activate/deactivate

## Technology Stack

### Backend
- **FastAPI** (0.109.0) - Async web framework
- **SQLAlchemy** (2.0.25) - ORM
- **bcrypt** (4.1.2) - Password hashing
- **Celery** (5.3.4) - Task queue (Phase 4)
- **Redis** (5.0.1) - Cache & broker (Phase 4)

### AI/ML
- **Ollama** - Local LLM (default: llama3.2:3b)
- **OpenAI** (1.12.0) - GPT-4, GPT-4V (vision)
- **Anthropic** (0.18.0) - Claude 3.5 (vision)
- **NudeNet** (3.4.2) - Local NSFW detection ✅
- **Pillow** (10.2.0) - Image processing and thumbnails ✅
- **ffmpeg** - Video frame extraction and processing ✅
- **ffmpeg-python** (0.2.0) - Python bindings for ffmpeg ✅

### Frontend
- Vanilla JavaScript (ES6+)
- CSS3 with CSS Variables
- No build step required

## Installation

### Prerequisites
- Python 3.9+
- Ollama (for local LLM) or OpenAI/Anthropic API keys
- ffmpeg (for video processing) - Install: `brew install ffmpeg` (macOS) or `apt-get install ffmpeg` (Linux)
- Optional: PostgreSQL (for production), Redis (for Phase 4+)

### Setup

1. **Clone and navigate**:
```bash
cd python-projects/12-content-moderation
```

2. **Create virtual environment**:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Configure environment**:
```bash
cp .env.example .env
# Edit .env with your settings
```

5. **Initialize database**:
```bash
python -c "from src.core.database import DatabaseManager; DatabaseManager().create_tables()"
```

6. **Run Phase 1 tests**:
```bash
python test_phase1.py
```

## Usage

### Start the Server

```bash
python server.py
```

Server runs at: http://localhost:7000

### Using the Web UI

1. **Register**: Create an account at http://localhost:7000
2. **Submit Content**: Use the "Submit Content" tab to submit text, images, or videos
3. **View Results**: Check "My Content" to see submission status
4. **Admin Access**: Create admin user to access user management

### API Examples

**Register User**:
```bash
curl -X POST http://localhost:7000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","email":"test@example.com","password":"password123"}'
```

**Login**:
```bash
curl -X POST http://localhost:7000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"password123"}' \
  -c cookies.txt
```

**Submit Text Content**:
```bash
curl -X POST http://localhost:7000/api/content \
  -H "Content-Type: multipart/form-data" \
  -F "content_type=text" \
  -F "text_content=This is a test message" \
  -F "priority=0" \
  -b cookies.txt
```

**Submit Image**:
```bash
curl -X POST http://localhost:7000/api/content \
  -F "content_type=image" \
  -F "file=@image.jpg" \
  -F "priority=0" \
  -b cookies.txt
```

**List My Content**:
```bash
curl http://localhost:7000/api/content -b cookies.txt
```

## Configuration

### Environment Variables

See [.env.example](.env.example) for all available options.

**Key Settings**:

```bash
# Server
PORT=7000
HOST=0.0.0.0
ENVIRONMENT=development

# Database
DATABASE_URL=sqlite:///./data/database.db

# LLM Provider (choose one)
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2:3b

OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o-mini

ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_MODEL=claude-3-5-sonnet-20241022

# Moderation Thresholds
AUTO_APPROVE_THRESHOLD=0.95
AUTO_REJECT_THRESHOLD=0.9
FLAG_REVIEW_THRESHOLD=0.5
```

### LLM Providers

**Option 1: Ollama (Local, Free)**:
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama
ollama serve

# Pull model
ollama pull llama3.2:3b
```

**Option 2: OpenAI**:
- Sign up at https://platform.openai.com
- Get API key
- Set `OPENAI_API_KEY` in `.env`

**Option 3: Anthropic**:
- Sign up at https://console.anthropic.com
- Get API key
- Set `ANTHROPIC_API_KEY` in `.env`

## Violation Categories

The system classifies content into 10 categories:

1. **clean**: Safe, appropriate content
2. **spam**: Unsolicited advertising, promotional content
3. **nsfw**: Explicit or sexual material
4. **hate_speech**: Hate or discrimination based on protected characteristics
5. **violence**: Content depicting or promoting violence/gore
6. **harassment**: Bullying, threats, targeted harassment
7. **illegal_content**: Content depicting illegal activities
8. **misinformation**: Deliberately false or misleading information
9. **copyright**: Content infringing on copyrights
10. **scam**: Fraudulent or deceptive content

## Database Schema

### Core Models

**User**:
- id, username, email, password_hash
- role (user, moderator, admin)
- is_active, is_verified
- created_at, updated_at

**Session**:
- id (session token), user_id
- expires_at, last_accessed
- ip_address

**ContentItem**:
- id, user_id, content_type
- text_content, file_path, file_hash
- status (pending, processing, approved, rejected, flagged)
- priority, created_at, updated_at

**Classification**:
- id, content_id, job_id
- category, confidence, is_violation
- provider, model_name, reasoning
- processing_time_ms, cost

**Review** (Phase 5):
- id, content_id, moderator_id
- action, approved, category
- notes, created_at

**ModerationJob** (Phase 4):
- id, content_id, status, queue_name
- celery_task_id, retry_count
- result_data

**Policy** (Phase 5):
- id, name, category
- auto_reject_threshold, flag_review_threshold
- enabled, severity

**AuditLog** (Phase 5):
- id, event_type, actor_id
- resource_type, resource_id
- action, details, created_at

## Project Structure

```
12-content-moderation/
├── server.py                        # FastAPI application with WebSocket
├── celery_app.py                    # Celery application entry point ✅
├── test_phase1.py                   # Phase 1 tests
├── test_phase2.py                   # Phase 2 tests ✅
├── test_phase3.py                   # Phase 3 tests ✅
├── test_phase4.py                   # Phase 4 tests ✅
├── requirements.txt                 # Dependencies
├── .env.example / .env              # Configuration
├── README.md                        # Documentation
│
├── src/
│   ├── core/
│   │   ├── database.py              # 8 SQLAlchemy models
│   │   ├── auth_manager.py          # Auth + RBAC
│   │   ├── llm_client.py            # Multi-provider AI
│   │   └── queue_manager.py         # Job creation & tracking ✅
│   │
│   ├── services/
│   │   ├── nsfw_detector.py         # NudeNet NSFW detection ✅
│   │   ├── video_processor.py       # ffmpeg frame extraction ✅
│   │   └── classification_service.py # Unified classification ✅
│   │
│   ├── utils/
│   │   └── file_handler.py          # File ops & thumbnails ✅
│   │
│   └── workers/                     # Celery workers ✅
│       ├── __init__.py              # Worker exports
│       ├── celery_config.py         # Celery configuration
│       ├── base_worker.py           # Base task class with retry
│       ├── text_worker.py           # Text classification task
│       ├── image_worker.py          # Image classification task
│       └── video_worker.py          # Video classification task
│
├── templates/
│   └── index.html                   # Web UI
│
├── static/
│   ├── css/
│   │   └── main.css                 # Styling
│   └── js/
│       └── app.js                   # Client app
│
├── data/
│   ├── database.db                  # SQLite DB
│   ├── uploads/                     # User files ✅
│   ├── thumbnails/                  # Generated thumbnails ✅
│   └── logs/                        # Application logs
│
└── tests/                           # (Phase 6)
```

## Upcoming Phases

### ~~Phase 2: Image Moderation~~ ✅ **COMPLETE**
- ✅ NudeNet NSFW detection
- ✅ Vision model integration (GPT-4V, Claude Vision)
- ✅ Thumbnail generation
- ✅ Image classification service
- ✅ File handler with validation
- ✅ Comprehensive test suite (4/4 passing)

### ~~Phase 3: Video Moderation~~ ✅ **COMPLETE**
- ✅ Frame extraction (ffmpeg-python)
- ✅ Frame-by-frame classification with NSFW detection
- ✅ Result aggregation with confidence scoring
- ✅ Video thumbnails
- ✅ Video processor service with fallback mode
- ✅ Comprehensive test suite (4/4 passing)

### ~~Phase 4: Queue System~~ ✅ **COMPLETE**
- ✅ Celery workers with priority queues (critical, high, default, batch)
- ✅ Redis broker and result backend
- ✅ Retry logic with exponential backoff and jitter
- ✅ Job creation and status tracking via QueueManager
- ✅ WebSocket progress updates (`/ws/jobs/{job_id}`)
- ✅ Worker tasks for text, image, and video classification
- ✅ BaseClassificationTask with auto-retry
- ✅ Comprehensive test suite (5/5 passing without Redis/Celery)

### Phase 5: Admin Dashboard (Weeks 7-8)
- Review queue UI
- Manual review workflow
- Appeal system
- Policy management
- Real-time statistics

### Phase 6: Production Features (Weeks 9-10)
- Analytics dashboard
- Cost tracking and budgets
- Docker deployment
- Load testing
- Monitoring and alerting

## Testing

### Run Phase 1 Tests (Core Foundation)

```bash
python3 test_phase1.py
```

**Tests** (5/5 passing):
1. ✅ Database initialization
2. ✅ User registration and authentication
3. ✅ Role-based access control
4. ✅ Content submission
5. ✅ LLM text classification

### Run Phase 2 Tests (Image Moderation)

```bash
python3 test_phase2.py
```

**Tests** (4/4 passing):
1. ✅ NSFW detector initialization
2. ✅ File handler (save, thumbnails, validation)
3. ✅ Classification service (text, image, policy)
4. ✅ Integration (database + classification pipeline)

**Note**: NudeNet is optional. Tests will use fallback mode if not installed.
```bash
# Optional: Install NudeNet for local NSFW detection
pip3 install nudenet
```

### Run Phase 3 Tests (Video Moderation)

```bash
python3 test_phase3.py
```

**Tests** (4/4 passing):
1. ✅ Video processor initialization
2. ✅ Frame extraction with synthetic video
3. ✅ Video classification service
4. ✅ Integration (database + video classification pipeline)

**Note**: ffmpeg is required for video processing. Tests will use fallback mode if not installed.
```bash
# Install ffmpeg
# macOS:
brew install ffmpeg

# Ubuntu/Debian:
sudo apt-get install ffmpeg

# Verify installation:
ffmpeg -version
```

### Run Phase 4 Tests (Queue System)

```bash
python3 test_phase4.py
```

**Tests** (5/5 passing):
1. ✅ Celery configuration and setup
2. ✅ Queue manager initialization
3. ✅ Worker task imports
4. ✅ Job creation
5. ✅ Base worker class

**Note**: Redis and Celery are required for full functionality. Tests verify code structure without requiring running services.

```bash
# Install Redis
# macOS:
brew install redis

# Ubuntu/Debian:
sudo apt-get install redis

# Start Redis:
redis-server

# Verify Redis:
redis-cli ping
# Should return: PONG

# Start Celery worker (in new terminal):
celery -A celery_app worker -Q critical,high,default,batch -l info

# Optional: Start Flower for monitoring:
celery -A celery_app flower
# Then visit: http://localhost:5555
```

### Manual Testing

1. **Web UI**: Test registration, login, content upload at http://localhost:8001
2. **API**: Test content upload with curl:
```bash
# Image upload
curl -X POST http://localhost:8001/api/content \
  -F "content_type=image" \
  -F "file=@test_image.jpg" \
  -F "priority=0" \
  -b cookies.txt

# Video upload
curl -X POST http://localhost:8001/api/content \
  -F "content_type=video" \
  -F "file=@test_video.mp4" \
  -F "priority=0" \
  -b cookies.txt
```
3. **Database**: Inspect `data/database.db` with SQLite browser
4. **Thumbnails**: Check `data/thumbnails/` for generated thumbnails

## Security Features

### Implemented (Phase 1)
- ✅ bcrypt password hashing (12 rounds)
- ✅ HTTPOnly session cookies
- ✅ SameSite=Strict (CSRF protection)
- ✅ SQLAlchemy ORM (SQL injection protection)
- ✅ File size limits
- ✅ File hash deduplication
- ✅ Role-based access control

### Planned (Future Phases)
- Rate limiting (Phase 6)
- Input sanitization (Phase 5)
- Content Security Policy headers (Phase 6)
- Audit logging (Phase 5)

## Performance

### Current Metrics (Phase 1)
- Text classification: < 5s (Ollama local)
- Image upload: < 2s (100MB max)
- API response time: < 100ms (database queries)

### Target Metrics (Phase 6)
- API response: p95 < 500ms
- Text processing: < 10s
- Image processing: < 30s
- Video processing: < 2 minutes
- 50+ concurrent users

## Troubleshooting

### Ollama Connection Failed
```bash
# Start Ollama service
ollama serve

# Pull required model
ollama pull llama3.2:3b

# Test connection
curl http://localhost:11434/api/tags
```

### Database Locked Error
- SQLite has concurrency limitations
- For multi-user testing, switch to PostgreSQL:
```bash
DATABASE_URL=postgresql://user:password@localhost/moderation_db
```

### Import Errors
```bash
# Ensure in project directory
cd python-projects/12-content-moderation

# Reinstall dependencies
pip install -r requirements.txt
```

## Contributing

Phase 1 is complete. Contributions welcome for Phases 2-6!

See the implementation plan for detailed roadmap: [Implementation Plan](/.claude/plans/purrfect-sparking-mango.md)

## License

MIT License

## Credits

Built with patterns from:
- Project 10: Chat Application (auth, FastAPI, WebSocket)
- Project 11: Research Assistant (multi-provider AI, cost tracking)

---

**Status**: Phase 4 Complete ✅
**Next**: Phase 5 - Admin Dashboard (review queue UI, manual workflow, appeals)
**Last Updated**: 2026-02-11
