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

## Audio Files

Podcasts, lecture recordings, voice memos and audio-only `.mp4` files are processed too. Upload any of `.mp3 .wav .m4a .aac .flac .ogg .opus .wma` (or a video container that holds only sound); what the file really contains decides the type, not its name, so an audio-only `.mp4` is audio and an `.mp3` with cover art is audio (the picture is not a video stream). On YouTube choose **Audio only (mp3)** in the quality list (`download_quality: "audio"`) to download just the sound. `media_type` (`video` or `audio`) is on every video in the API; the Videos page shows a music note instead of a film strip.

With no picture there is no frame extraction, scene detection, captioning, object/face/OCR/CLIP analysis or action recognition. What runs:

- **Transcription** (Whisper), speakers if `HF_TOKEN` is set, and the same checks as for video (segments past the end are dropped).
- **Sections instead of scenes.** The speech is cut into sections at pauses (a pause of 1.5 s or more once the section is 20 s long; never longer than 90 s, so a speaker who does not pause still gets sections; audio with no speech is cut into windows of about a minute). Each section has its audio energy, and the summary, chapters, highlights and timeline work from them unchanged. The `/scenes` endpoint lists the sections.
- **Search and Q&A** use the transcript embeddings (there are no frame embeddings, so frame search finds nothing in audio).
- **Clips of audio are mp3.** `POST /api/videos/{id}/clip` gives an mp3 by default for audio (fades work); asking for mp4, webm or gif is `400`, and an mp3 cannot have `include_audio: false`. For a *video*, `format: "mp3"` takes just the sound. A highlight reel of audio clips is one mp3 (the clips follow each other, no transition); a reel cannot mix sound and picture clips. Audio clips have no thumbnail.
- Highlights are labelled "Dialogue Highlight", never "Action", because there is no motion.

Limits: a recording is only as good as its transcript (Whisper "base" by default); music with no speech gets sections but no chapters of substance; the sections are found from pauses, not from topics, so a topic change in the middle of a long section does not start a new one; transcription is one long step that cannot be interrupted, so cancelling a long recording takes effect after it.

## Faces and Scenes

### Faces

Faces in each scene's keyframe are found with **YuNet**, a 0.2 MB face detector from OpenCV's model zoo that ships in `models/` (see `models/README.md` for its source, license and checksum). It replaced OpenCV's Haar cascade, which on the keyframes of the real test videos reported faces on window frames, chairs and wall patterns (643 "faces" against 452 now) and missed faces with sunglasses, small faces and faces turned away; on the same frames YuNet found those faces and, at a score of 0.7, none of the false ones. `FACE_BACKEND=auto` (default) uses YuNet when the model file is there and falls back to the Haar cascade, with one warning in the log, when it is not; `yunet` and `opencv` force one. `FACE_MIN_CONFIDENCE` (0.7) drops weaker faces, `FACE_MODEL_PATH` points at another copy of the model. Each face has its box, its score and five landmarks (eyes, nose, mouth corners); pictures larger than 1280 px are shrunk for speed and the boxes scaled back, and a face under 16 px is not reported.

### Scenes

Scenes used to come from PySceneDetect's `ContentDetector` alone. Measured on videos with known boundaries it found hard cuts between very different shots and missed **slide changes** (a new layout on the same background), **dissolves and fades**, and it called a one-frame **white flash** a cut. `SCENE_DETECTOR=robust` (default) uses a detector that looks at a small grayscale copy of the video, ten times a second (ffmpeg decodes it, 4-10x faster than `ContentDetector` on the same videos):

- **cuts** are a frame that differs from the one before it while its neighbours do not (a spike); a spike that is undone within a few frames is a flash, not a cut; a small change must stand out clearly (a new slide in a still picture) while a bigger one only a little (a cut in lively footage), so a hand gesture is not a scene;
- **dissolves, fades and wipes** are a bump in the difference between the picture half a second before and half a second after (taken from the middle of five frames so a flash cannot fake it), clearly bigger than that difference anywhere nearby, so a pan or a zoom is not one. A dissolve is found at its middle and `transition_type` says `cut`, `dissolve` or `fade` (a fade through black);
- the keyframe of a scene is the frame closest to its typical picture, taken from its middle part and not from a half-dissolved edge.

| Measured on videos with known boundaries | PySceneDetect `ContentDetector` | `robust` |
|---|---|---|
| ffmpeg-made shots, slides, dissolves, fades, a flash, a zoom (25 boundaries, 3 videos with nothing to find) | precision 0.88, recall 0.60 | precision 1.00, recall 0.84 |
| pieces of the real test videos joined with cuts, dissolves and fades (19 boundaries) | precision 1.00, recall 0.68 | precision 1.00, recall 1.00 |

On the long real videos it found 93-100 % of the boundaries `ContentDetector` found, plus slide changes and builds `ContentDetector` missed (a 7-minute animated explainer: 141 scenes against 85; every one of 6 sampled extra boundaries was a real change of what is on screen) and it missed some cuts in a very fast music video (7 of 96). More scenes means more keyframes to caption, so an animated explainer takes proportionally longer to process; `SCENE_DETECTOR=content` brings the old behaviour back, and it is also the fallback if the robust detector cannot read a video.

Limits: a dissolve between two pictures that both change fast (a zoom into a zoom) is not found (the synthetic fractal cases are the 4 misses in the first row); wipes are found as dissolves; two cuts less than 0.2 s apart count as one; the scene detector sees pictures only, so a change of topic with the same slide is one scene.

### Scene types

`scene_type` was always `unknown`. Each scene now gets one from three things the pipeline knows about it: how much its picture moves (the mean frame-to-frame change the detector measures, about 0.000 for slides and screen recordings, 0.003-0.017 for a person talking to a camera, 0.02-0.05 for a fast-cut music video), how much of it is speech, and whether a face is in it:

| Type | When |
|---|---|
| `static` | the picture does not move (a slide, a screen), with or without narration |
| `dialogue` | a face on screen and speech over at least 40 % of the scene, with the modest movement of a person talking |
| `motion` | lively movement that is neither of the others |
| `action` | fast, high-energy movement (and, when there is speech, loud audio) |
| `unknown` | audio files have sections, not scenes: sections with speech are `dialogue`, music and silence stay `unknown` |

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

Written from running the platform on real videos (a 60 s 1080p explainer, a 4-minute lecture, a 5.8 s phone clip, audio-only and invalid files) and on real audio (a 4-minute lecture recording and speech generated with macOS `say`).

### What the API accepts

| Input | Rule | Answer when it breaks the rule |
|---|---|---|
| Upload | video `.mp4 .avi .mov .mkv .webm` or audio `.mp3 .wav .m4a .aac .flac .ogg .opus .wma`, **and** ffprobe must find a video or audio stream with a length. A text file, empty file or random bytes named `.mp4` or `.mp3` are not media | `400` with one line (`The file is not a valid video or audio file…`, `The file has no video or audio stream`); nothing is left on disk |
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

- **Faces** are found with YuNet (see Faces and Scenes). Without the model file the old Haar cascade runs and a face count is only a rough signal; faces are detected in each scene's keyframe only, so a face that appears in another part of a scene is not counted. The `mtcnn` backend needs its package installed.
- Scene types come from motion, speech and faces with fixed thresholds measured on a handful of real videos; a different kind of footage may sit on the other side of a threshold.
- Highlights are labelled "Action Highlight" from motion energy, which also fires for a talking head.
- Audio files are analysed from the transcript only (see Audio Files): no topics-based sectioning, and no frame search.
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
       tests/api/test_job_queue.py tests/test_frontend_queue.py \
       tests/api/test_audio.py tests/test_audio_sections.py tests/test_frontend_audio.py \
       tests/test_scene_boundaries.py tests/test_scene_typing.py tests/test_faces_yunet.py tests/test_scene_pipeline.py
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
