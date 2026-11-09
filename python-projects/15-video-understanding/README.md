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

## Accounts

Every request to `/api/*` needs a sign-in. Open the app and you land on `/login`:

- **Sign in / Create account** with a username (3-32 letters, digits, `.` `-` `_`, not case-sensitive) and a password (8-128 characters).
- **Continue as guest** needs no details: a throwaway account that can keep `GUEST_MAX_VIDEOS` (3) videos of up to `GUEST_MAX_VIDEO_SIZE_MB` (50) and is deleted, with everything it uploaded, after `GUEST_TTL_HOURS` (24). A guest who then creates an account keeps their videos (the guest account is turned into the real one).
- **Every account only sees its own videos.** Another account's video, clip, frame, thumbnail, transcript, summary, search hit and progress feed answer `404`, exactly like an id that does not exist. Search is filtered inside the vector search, so one person's results never depend on what others uploaded. Administrators see everything.
- The **first real account** is the administrator and adopts the videos that were uploaded before accounts existed (they had no owner). `ADMIN_USERNAMES=name1,name2` makes other names administrators.
- Deleting a video (or an expired guest) removes the upload, frames, clips, thumbnails **and** its search embeddings; before, only the upload went.
- Accounts may keep `MAX_VIDEOS_PER_USER` (100) videos; administrators have no limit.

| Setting | Default | Meaning |
|---|---|---|
| `REQUIRE_LOGIN` | `true` | `false` = single-user mode: no sign-in, everyone is the local administrator (only for `API_HOST=127.0.0.1`) |
| `ALLOW_REGISTRATION` / `ALLOW_GUESTS` | `true` | switch account creation / guest access off |
| `SESSION_DAYS` | `14` | how long a sign-in lasts |
| `COOKIE_SECURE` | `false` | set `true` behind HTTPS so the cookie is never sent over plain HTTP |
| `GUEST_TTL_HOURS`, `GUEST_MAX_VIDEOS`, `GUEST_MAX_VIDEO_SIZE_MB`, `MAX_VIDEOS_PER_USER` | 24, 3, 50, 100 | limits above |

How it is built (and why):

- A sign-in is a random token in an `HttpOnly`, `SameSite=Lax` cookie (a cookie, not a header, because the page loads thumbnails, frames and clip downloads through `<img>` and `<a>` tags that cannot send headers). The database keeps only the SHA-256 of the token, so a leaked database holds nothing a browser can replay; signing out ends that sign-in at once. Passwords are stored with scrypt.
- A write that carries the cookie but comes from another website (`Origin`/`Referer` is not this site or a `CORS_ORIGINS` entry) is refused, and so is a WebSocket from another site, because browsers do not apply CORS to WebSockets.
- Wrong passwords are limited to 8 per 10 minutes per address and per username (`429`), "no such user" and "wrong password" answer identically, and account/guest creation is limited per address.
- `/uploads`, `/clips` and `/thumbnails` used to be mounted as public folders (any file, no sign-in). They are gone: files only leave through the endpoints that check the owner.
- Run `alembic upgrade head` (adds `users`, `user_sessions`, `videos.user_id`); the server also adds them on start-up in debug mode.

From a script, keep the cookie:

```bash
curl -c jar -H 'content-type: application/json' -d '{"username":"me","password":"my-password"}' http://localhost:8000/api/auth/login
curl -b jar http://localhost:8000/api/videos
```

Not built: password change or reset, e-mail, a list of your devices, per-account storage quotas (only video counts), an admin screen.

## Job Queue

Downloads and video analysis do not run inside the request that asked for them. Every upload, YouTube/stream link, `/process` and `/reprocess` puts a **job** in a queue, and a few workers take jobs one by one.

Before this, each upload started its own analysis at once. Five uploads meant five Whisper + CLIP + vision-model runs fighting over one CPU and its memory; a restart left videos "processing" for ever; nothing could be cancelled or retried; and a YouTube download froze the whole server while it ran.

- **How many at once:** `MAX_CONCURRENT_VIDEOS` analyses (default **1**: each loads Whisper, CLIP and a vision model, so more at once is slower, not faster, on a laptop) and `MAX_CONCURRENT_DOWNLOADS` downloads (default 2) in their own lane, so a download never waits for an analysis.
- **Where a video stands:** `status` / `GET /api/videos/{id}` / the list carry `job_id`, `job_status` (`queued` or `running`) and `queue_position` (1 = next). The Videos page shows `queued: #3`, `queued: next` or `processing`, a **Cancel** button on waiting and running videos, **Retry** on failed ones and **Process** on videos that never ran; the WebSocket sends `queued` events with the position.
- **Fair order:** one account with twenty videos queued does not make everyone else wait for all twenty. A job's turn is (jobs its account has running) + (its place in its own line), ties by age: accounts take turns.
- **Limits:** an account may have `MAX_QUEUED_JOBS_PER_USER` (20) jobs waiting or running; more answers `429` before the file is saved.
- **Survives restarts:** a job is a row in the `jobs` table. Waiting jobs are still waiting after a restart. A running job beats a heartbeat every 10 s; if the process is killed, a job whose heartbeat is older than `JOB_STALE_SECONDS` (45) goes back in the queue (`JOB_MAX_ATTEMPTS` (2) tries, then it fails with a message). A clean shutdown (Ctrl-C, SIGTERM) puts the running job back at once without using up a try. Videos left "processing" by a version without the queue are marked failed on start so **Reprocess** is offered.
- **Cancel:** a waiting job is cancelled at once. A running one stops at its next checkpoint (between pipeline stages and before each scene) and the video goes back to "pending" with its partial results removed; a Whisper transcription that is already running finishes first, so on a long video a cancel can take a few minutes. A download is stopped within a second and its partial file removed. Deleting a video stops its job too.
- **API:** `GET /api/jobs` (yours, with the queue summary), `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`, `POST /api/jobs/{id}/retry`. Another account's job answers `404`; administrators see all.
- **Downloads** now run off the event loop (`yt-dlp` used to block the whole server) and are capped by size: `YT_DLP_MAX_FILESIZE_MB` for YouTube, `MAX_VIDEO_SIZE_MB` (or the guest limit) for streams (`ffmpeg -fs`). A finished download queues its analysis as a separate job.
- A job that runs longer than `PROCESSING_TIMEOUT_SECONDS` (3600) is failed and asked to stop.
- Finished jobs older than a week are deleted. `alembic upgrade head` adds the `jobs` table (the server also creates it on start in debug mode).

Limits of this design: the workers live in the API process (run one server process; with several, jobs are still never taken twice, but each process runs its own workers), a running analysis cannot be interrupted inside a single long stage, and the order between accounts is fair but there are no priorities (a guest's job is not slower than an account's).

## Inputs, Limits and What to Expect

Written from running the platform on real videos (a 60 s 1080p explainer, a 4-minute lecture, a 5.8 s phone clip, audio-only and invalid files).

### What the API accepts

| Input | Rule | Answer when it breaks the rule |
|---|---|---|
| Upload | `.mp4 .avi .mov .mkv .webm`, **and** ffprobe must find a video stream with a length. A text file, empty file or random bytes named `.mp4` are not videos | `400` with one line (`The file is not a valid video…`, `The file has no video stream (audio-only files are not supported)`); nothing is left on disk |
| Upload size | `MAX_VIDEO_SIZE_MB` (default 500), read in chunks | `413` |
| Title / description | trimmed, at most 200 / 2000 characters; a directory in the file name (`../../x.mp4`) is dropped (title `x`) | |
| YouTube URL | the **host** must be YouTube (`youtube.com`, `youtu.be`, …); `evil.example/?youtube.com` is refused | `400` |
| Stream URL | `http(s)` only, and every address it resolves to must be public. `127.0.0.1`, `localhost`, `10.x`, `192.168.x`, `169.254.169.254` (cloud credentials) are refused. ffmpeg is also limited to network protocols (current ffmpeg already refuses `file:` entries in a playlist; this is a second layer for other builds) | `400` |
| Clip | `end_time` must not be past the end of the video (up to 0.5 s over is clamped); `format` mp4/webm/gif; `resolution` 480p/720p/1080p/original | `400` / `422` |
| Timeline filter | `event_types` from `scene speech highlight chapter` | `400` |
| Highlights / summary generation | the video must exist and be fully processed (they run in the background and answer immediately) | `404` / `400` |

A stream URL check cannot stop a public host that later redirects to, or re-resolves to, an internal address. Do not give the server access to networks you would not want reached.

### Processing status

`GET /api/videos/{id}/status` returns the live `stage` and `progress` (10 frame extraction, 10-70 per scene, 80 embeddings, 100 done) while a video is processed; it is the same information the WebSocket pushes. `started_at` is when the current run began, `completed_at` when it ended. All stored times are UTC.

A video that is one continuous shot (no cuts) is one scene covering the whole video. A failed video shows one readable line in `error_message`, not a tool dump with server paths.

### Frame descriptions (vision model)

Scene captions come from the model in `VISION_PROVIDER=ollama` / `VISION_MODEL`, with BLIP-base only as the fallback when Ollama or the model is missing (a missing model falls back to any installed vision model, with a warning in the log). Captions that loop ("react react react …") are cut.

Measured on the same four keyframes (slides and photos) on an Apple-silicon laptop:

| Model | Speed per frame | What it did |
|---|---|---|
| `llava:latest` (default) | 3-6 s | Reads slide titles ("HOW DATA BECOMES EVIDENCE") but adds details that are not there (a "navigation bar", a wrong top colour) and ignores "one or two sentences"; can misread a title ("LOCOR MODEL" for "#1 OCR MODEL") |
| `qwen3-vl:8b` | 20-28 s | Accurate: quotes the slide titles and boxes, describes the collage correctly. About 4x slower, so a 4-minute video with 22 scenes takes roughly 8 minutes longer |
| BLIP-base (fallback) | ~1 s | "how to use a data flow chart in java" for a data-flow slide (it went into the summary), "traceability for react react …" for a title slide |

For accurate slide and screen descriptions set `VISION_MODEL=qwen3-vl:8b` (`ollama pull qwen3-vl:8b`) and accept the longer processing time.

### Question answering, summaries, chapters

- Answers use the matching transcript lines **plus the line before and after each**, read in time order. Without the neighbours, a question whose answer ends in the next line ("…stronger evidence. That is" / "the foundation of reliable clinical research.") was answered with the wrong thing.
- The model's own preamble line ("Here is a summary of the video in 2-3 paragraphs:") is removed from summaries and answers.
- Chapter titles come from what is said where the chapter starts ("Welcome to Trial Data Lab"), else from the scene description, and never end on "a" or "of".
- Transcript segments are kept inside the video: Whisper can invent a segment that starts after the audio ends or runs far past it.

### Known limits

- **Faces** use OpenCV's Haar cascade (`FACE` backend `opencv`). It repeats one face as several boxes (now merged) but also reports false faces, e.g. on a blazer, and misses faces in small collage panels or side views, so a face count is only a rough signal. The `mtcnn` backend needs its package installed.
- `scene_type` is always `unknown`; scenes are not classified.
- Highlights are labelled "Action Highlight" from motion energy, which also fires for a talking head.
- Audio-only files are refused; there is no transcribe-only mode.
- Analysis is queued (see Job Queue) but runs inside the API process. A 4-minute 1080p video took about 4.5 minutes, a 60 s video under 2 minutes.
- Sign-in is cookie based and the server speaks plain HTTP: put it behind HTTPS (and set `COOKIE_SECURE=true`) before exposing it beyond your own machine. It listens on `127.0.0.1` by default; with `API_HOST=0.0.0.0` the sign-in page and API are reachable from your network.
- The page shows everything the server sends as text (titles, summaries, answers, errors are never interpreted as HTML).

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

# The checks written from real-video testing (ffmpeg and node are used when installed)
pytest tests/test_input_checks.py tests/test_single_shot_scenes.py tests/test_qa_context.py \
       tests/test_captions.py tests/test_chapter_titles_and_faces.py tests/test_frontend_escaping.py \
       tests/api/test_hardening.py tests/api/test_accounts.py tests/test_frontend_auth.py \
       tests/api/test_job_queue.py tests/test_frontend_queue.py
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
