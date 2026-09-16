#!/usr/bin/env python3
"""
Meeting Summarizer Web Server - Phases 4 & 5

FastAPI web server with real-time progress, database persistence,
video support, and advanced features.

Usage:
    python server.py
    # Server runs on http://localhost:8000
"""

import os
import sys
import asyncio
import uuid
import hashlib
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
from dotenv import load_dotenv
import logging

from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
import uvicorn

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core.audio_processor import AudioProcessor
from core.transcription_service import TranscriptionService
from core.cache_manager import CacheManager
from core.llm_client import LLMClient
from core.meeting_analyzer import MeetingAnalyzer
from core.database import DatabaseManager, Job
from utils.progress_tracker import ProgressTracker, ProcessingStage
from utils.video_processor import VideoProcessor
from utils.speaker_diarization import create_speaker_diarization
from utils.summary_templates import SummaryTemplateManager

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Meeting Summarizer API",
    description="AI-powered meeting transcription and summarization",
    version="5.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "http://localhost:8000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and templates
static_dir = Path(__file__).parent / "static"
templates_dir = Path(__file__).parent / "templates"
static_dir.mkdir(exist_ok=True)
templates_dir.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))


def static_version(rel_path: str) -> str:
    """
    Short cache-busting token for a static asset, from its mtime.

    StaticFiles sends no Cache-Control header, so browsers fall back to
    heuristic caching and can serve a stale app.js/styles.css for a long
    time after an edit. Appending ?v=<mtime-hash> changes the URL
    whenever the file changes so the new version is always fetched.
    """
    try:
        mtime = os.path.getmtime(static_dir / rel_path)
        return hashlib.md5(str(mtime).encode()).hexdigest()[:8]
    except OSError:
        return "0"


templates.env.globals["static_version"] = static_version

# Phase 5: Database persistence
db_url = os.getenv('DATABASE_URL', None)  # Default: SQLite in data/database.db
db_manager = DatabaseManager(db_url)

# Phase 5: Video processor
video_processor = VideoProcessor()

# Phase 5: Speaker diarization (optional)
hf_token = os.getenv('HF_AUTH_TOKEN')
speaker_diarizer = create_speaker_diarization(hf_token) if hf_token else None

# Phase 5: Summary templates
template_manager = SummaryTemplateManager(custom_templates_dir='./templates/custom')

# Job storage (in-memory for Phase 4, can be migrated to database in future)
active_jobs: Dict[str, Dict] = {}

# WebSocket connections (still in-memory for real-time)
websocket_connections: Dict[str, List[WebSocket]] = {}

# Configuration
config = {
    'transcription_backend': os.getenv('TRANSCRIPTION_BACKEND', 'openai'),
    'openai_api_key': os.getenv('OPENAI_API_KEY'),
    'whisper_model': os.getenv('WHISPER_MODEL', 'whisper-1'),
    'whisper_cpp_path': os.getenv('WHISPER_CPP_PATH'),
    'whisper_model_path': os.getenv('WHISPER_CPP_MODEL'),
    'max_audio_size_mb': int(os.getenv('MAX_AUDIO_SIZE_MB', 500)),
    'cache_dir': os.getenv('CACHE_DIR', './data/cache'),
    'transcription_ttl_days': int(os.getenv('TRANSCRIPTION_CACHE_TTL_DAYS', 30)),
    'summary_ttl_days': int(os.getenv('SUMMARY_CACHE_TTL_DAYS', 7)),
    'enable_cache': os.getenv('ENABLE_CACHE', 'true').lower() == 'true',
    'output_dir': os.getenv('OUTPUT_DIR', './data/output'),
    'upload_dir': os.getenv('UPLOAD_DIR', './data/uploads'),
    'default_output_format': os.getenv('DEFAULT_OUTPUT_FORMAT', 'markdown')
}

# Create directories
Path(config['upload_dir']).mkdir(parents=True, exist_ok=True)
Path(config['output_dir']).mkdir(parents=True, exist_ok=True)


def create_meeting_analyzer():
    """Create meeting analyzer instance"""
    audio_processor = AudioProcessor(max_size_mb=config['max_audio_size_mb'])

    cache_manager = None
    if config['enable_cache']:
        cache_manager = CacheManager(
            cache_dir=config['cache_dir'],
            transcription_ttl_days=config['transcription_ttl_days'],
            summary_ttl_days=config['summary_ttl_days']
        )

    transcription_service = TranscriptionService(
        backend=config['transcription_backend'],
        api_key=config['openai_api_key'],
        model=config['whisper_model'],
        cache_manager=cache_manager,
        audio_processor=audio_processor,
        whisper_cpp_path=config['whisper_cpp_path'],
        whisper_model_path=config['whisper_model_path']
    )

    # Initialize LLM client
    llm_provider = os.getenv('LLM_PROVIDER', 'openai')
    llm_model = os.getenv('LLM_MODEL')

    if llm_provider == 'openai':
        api_key = config['openai_api_key']
    elif llm_provider == 'anthropic':
        api_key = os.getenv('ANTHROPIC_API_KEY')
    else:
        api_key = None

    llm_client = LLMClient(
        backend=llm_provider,
        model=llm_model,
        api_key=api_key
    )

    meeting_analyzer = MeetingAnalyzer(
        transcription_service=transcription_service,
        llm_client=llm_client,
        cache_manager=cache_manager,
        audio_processor=audio_processor
    )

    return meeting_analyzer, audio_processor


async def broadcast_progress(job_id: str, progress_state: Dict):
    """Broadcast progress update to all connected WebSocket clients"""
    if job_id in websocket_connections:
        disconnected = []
        for websocket in websocket_connections[job_id]:
            try:
                await websocket.send_json(progress_state)
            except Exception as e:
                logger.error(f"WebSocket send error: {str(e)}")
                disconnected.append(websocket)

        # Remove disconnected clients
        for ws in disconnected:
            websocket_connections[job_id].remove(ws)


async def process_meeting_async(job_id: str, audio_path: str, options: Dict):
    """Process meeting in background with progress tracking"""
    # The heavy work (analyze_meeting / generate_report) is fully
    # synchronous and CPU/subprocess-bound - whisper.cpp, Ollama, ffmpeg.
    # It used to run inline on the event loop here, which froze the whole
    # server for the duration of every job (confirmed live: a concurrent
    # /api/health took 16s, and the WebSocket could deliver no progress
    # until the job finished). It now runs in a worker thread via
    # asyncio.to_thread, so we grab the loop up front to marshal progress
    # callbacks (fired from that thread) back onto it.
    loop = asyncio.get_running_loop()
    extracted_audio = None  # set if the upload was a video we transcoded

    try:
        # Update job status
        active_jobs[job_id]['status'] = 'processing'
        active_jobs[job_id]['started_at'] = datetime.now().isoformat()
        db_manager.mark_job_processing(job_id)

        # Create progress tracker
        progress_tracker = ProgressTracker(
            job_id=job_id,
            state_dir="./data/progress",
            enable_persistence=True
        )

        # Progress callback - now genuinely invoked from the worker
        # thread once analyze_meeting() reports real per-stage progress
        # (see progress_callback below), not just from this function's
        # own loop-thread calls to progress_tracker. Both the WebSocket
        # broadcast and the DB write have to be marshalled onto the
        # event loop thread accordingly: run_coroutine_threadsafe for
        # the coroutine, call_soon_threadsafe for the plain db_manager
        # call (SQLite connections aren't safe to touch from a thread
        # other than the one that opened them).
        def on_progress(state):
            active_jobs[job_id]['progress'] = state
            asyncio.run_coroutine_threadsafe(broadcast_progress(job_id, state), loop)

            def _persist_progress():
                try:
                    db_manager.update_job_progress(
                        job_id,
                        progress_percent=state.get('progress_percent', 0),
                        current_stage=state.get('current_stage')
                    )
                except Exception as e:  # never let a DB hiccup kill the job
                    logger.warning(f"Job {job_id}: progress DB update failed: {e}")

            loop.call_soon_threadsafe(_persist_progress)

        progress_tracker.add_callback(on_progress)
        progress_tracker.start(metadata={
            'audio_file': os.path.basename(audio_path),
            'options': options
        })

        # Create meeting analyzer
        meeting_analyzer, audio_processor = create_meeting_analyzer()

        # If the upload is a video file, extract its audio track before
        # validating (audio_processor.validate_audio only understands
        # audio containers). Done here rather than inside analyze_meeting
        # so the validation step below sees a real audio file.
        if video_processor.is_video_file(audio_path):
            progress_tracker.update_stage(
                ProcessingStage.VALIDATION, 5, "Extracting audio from video"
            )
            audio_path = await asyncio.to_thread(video_processor.extract_audio, audio_path)
            extracted_audio = audio_path
            logger.info(f"Job {job_id}: extracted audio -> {audio_path}")

        # Validation stage
        progress_tracker.update_stage(ProcessingStage.VALIDATION, 10, "Validating audio file")
        validation = audio_processor.validate_audio(audio_path)

        if not validation['valid']:
            err = f"Audio validation failed: {', '.join(validation['errors'])}"
            progress_tracker.fail(err, ProcessingStage.VALIDATION)
            active_jobs[job_id]['status'] = 'failed'
            active_jobs[job_id]['error'] = validation['errors']
            db_manager.mark_job_failed(job_id, err)
            return

        progress_tracker.complete_stage(ProcessingStage.VALIDATION)

        # Cancellation checkpoint. analyze_meeting() below is one
        # monolithic blocking call (whisper.cpp + Ollama, no internal
        # checkpoints), so once it starts there's no cooperative way to
        # stop it short of killing the subprocess - this is the last
        # point where a cancel request actually prevents work from
        # happening, rather than just being honored after the fact.
        if active_jobs[job_id].get('cancel_requested'):
            logger.info(f"Job {job_id} cancelled before transcription started")
            return

        # Transcription stage
        progress_tracker.update_stage(ProcessingStage.TRANSCRIPTION, 30, "Transcribing audio")

        # analyze_meeting() reports real stage-completion events as it
        # goes (from the worker thread analyze_meeting itself runs on -
        # progress_tracker.update_stage()/complete_stage() call the
        # on_progress callback above, which is already thread-safe).
        # Without this, the progress bar used to sit at 30% for the
        # entire transcription+summarization+extraction run and then
        # jump straight to 100% - cosmetic, not real progress.
        def on_stage_event(event: str):
            if event == "transcription_done":
                progress_tracker.complete_stage(ProcessingStage.TRANSCRIPTION)
                progress_tracker.update_stage(ProcessingStage.SUMMARIZATION, 60, "Generating summary")
            elif event == "summarization_done":
                progress_tracker.complete_stage(ProcessingStage.SUMMARIZATION)
                progress_tracker.update_stage(ProcessingStage.ACTION_EXTRACTION, 80, "Extracting action items")

        # Run analysis in a worker thread so the event loop stays free
        # to serve other requests and flush WebSocket progress messages.
        result = await asyncio.to_thread(
            meeting_analyzer.analyze_meeting,
            audio_path,
            summary_level=options.get('summary_level', 'standard'),
            extract_actions=options.get('extract_actions', True),
            extract_topics=options.get('extract_topics', True),
            language=options.get('language'),
            progress_callback=on_stage_event
        )

        # A cancel that arrived while analyze_meeting() was running
        # couldn't stop it, but it should still keep this job out of
        # "completed" - the caller asked us to stop caring about the
        # result, so skip report generation and leave status as
        # 'cancelled' (already set by /cancel) rather than overwriting it.
        if active_jobs[job_id].get('cancel_requested'):
            logger.info(f"Job {job_id} finished analysis after being cancelled - discarding result")
            return

        # transcription/summarization stages were already completed by
        # on_stage_event as they actually finished; action_extraction
        # (and topic extraction, which shares its window - there's no
        # separate UI stage for it) are done now that analyze_meeting()
        # has returned.
        progress_tracker.complete_stage(ProcessingStage.ACTION_EXTRACTION)

        # Generate report
        progress_tracker.update_stage(ProcessingStage.REPORT_GENERATION, 90, "Generating report")

        template = options.get('template')
        output_format = 'md' if template else options.get('output_format', 'markdown')
        output_file = Path(config['output_dir']) / f"{job_id}_analysis.{output_format}"

        await asyncio.to_thread(
            meeting_analyzer.generate_report,
            result,
            format=output_format,
            output_path=str(output_file),
            template=template
        )

        progress_tracker.complete_stage(ProcessingStage.REPORT_GENERATION)

        # Complete
        progress_tracker.complete(result={'output_file': str(output_file)})

        active_jobs[job_id]['status'] = 'completed'
        active_jobs[job_id]['result'] = result
        active_jobs[job_id]['output_file'] = str(output_file)
        active_jobs[job_id]['completed_at'] = datetime.now().isoformat()

        stats = result.get('statistics', {})
        db_manager.mark_job_completed(
            job_id,
            output_file_path=str(output_file),
            summary_text=result.get('summary', {}).get('text'),
            topics=result.get('topics') or [],
            action_items_count=(result.get('actions') or {}).get('total_actions', 0),
            processing_time_seconds=stats.get('processing_time_seconds'),
            estimated_cost_usd=stats.get('total_cost_usd'),
            cache_hits=stats.get('cache_hits', 0),
        )

        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        logger.exception(f"Job {job_id} failed")
        active_jobs[job_id]['status'] = 'failed'
        active_jobs[job_id]['error'] = str(e)
        active_jobs[job_id]['completed_at'] = datetime.now().isoformat()
        try:
            db_manager.mark_job_failed(job_id, str(e))
        except Exception:
            logger.exception(f"Job {job_id}: failed to record failure in DB")

    finally:
        # Drop the audio track we pulled out of an uploaded video - the
        # transcript is cached by content hash, not by this temp path.
        if extracted_audio:
            try:
                Path(extracted_audio).unlink(missing_ok=True)
            except OSError as e:
                logger.warning(f"Job {job_id}: could not remove temp audio: {e}")


@app.on_event("startup")
async def _reconcile_interrupted_jobs():
    """A job left 'processing' in the DB was running when a previous
    server instance died - mark it failed so it doesn't show as
    forever-in-progress. ('queued' jobs are left alone: their upload is
    still on disk and analysis can still be started.)"""
    try:
        stale = db_manager.list_jobs(limit=1000, status='processing')
        for j in stale:
            db_manager.mark_job_failed(j.id, "Interrupted by server restart")
        if stale:
            logger.info(f"Marked {len(stale)} interrupted job(s) as failed on startup")
    except Exception:
        logger.exception("Startup job reconciliation failed")


# Routes

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main web UI"""
    # New-style signature (request first). The old
    # TemplateResponse("index.html", {"request": request}) form raises
    # "TypeError: unhashable type: 'dict'" on the Starlette version this
    # project resolves to (fastapi/starlette are unpinned in
    # requirements.txt) - confirmed live, every homepage load 500'd.
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "version": "4.0.0",
        "services": {
            "transcription": config['transcription_backend'],
            "llm_provider": os.getenv('LLM_PROVIDER', 'openai'),
            "cache_enabled": config['enable_cache']
        }
    }


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload audio file"""
    try:
        # Validate file extension - audio, or a video container we can
        # pull the audio track out of (see VideoProcessor).
        audio_extensions = ['.mp3', '.wav', '.webm', '.m4a', '.ogg', '.flac']
        allowed_extensions = audio_extensions + [
            e for e in video_processor.SUPPORTED_VIDEO_FORMATS if e not in audio_extensions
        ]
        file_ext = Path(file.filename).suffix.lower()

        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
            )

        # Generate unique filename
        job_id = str(uuid.uuid4())
        upload_path = Path(config['upload_dir']) / f"{job_id}{file_ext}"

        # Save file
        with open(upload_path, 'wb') as f:
            content = await file.read()
            f.write(content)

        logger.info(f"File uploaded: {file.filename} -> {upload_path}")

        # Persist the job now so its original filename is recorded and it
        # shows up in /api/jobs even before analysis starts / after a
        # server restart.
        db_manager.create_job(
            job_id=job_id,
            filename=file.filename,
            file_path=str(upload_path)
        )

        return {
            "job_id": job_id,
            "filename": file.filename,
            "upload_path": str(upload_path),
            "size_bytes": len(content)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze/{job_id}")
async def start_analysis(
    job_id: str,
    background_tasks: BackgroundTasks,
    summary_level: str = 'standard',
    extract_actions: bool = True,
    extract_topics: bool = True,
    output_format: str = 'markdown',
    language: Optional[str] = None,
    template: Optional[str] = None
):
    """Start meeting analysis job"""
    try:
        # Find uploaded file
        upload_files = list(Path(config['upload_dir']).glob(f"{job_id}.*"))

        if not upload_files:
            raise HTTPException(status_code=404, detail="Uploaded file not found")

        audio_path = str(upload_files[0])

        # Create job entry
        active_jobs[job_id] = {
            'job_id': job_id,
            'status': 'queued',
            'audio_path': audio_path,
            'created_at': datetime.now().isoformat(),
            'progress': {}
        }

        # Persist the chosen options (row was created at upload time).
        db_manager.update_job(
            job_id,
            summary_level=summary_level,
            extract_actions=extract_actions,
            extract_topics=extract_topics,
            output_format=('md' if template else output_format),
            language=language,
            status='queued',
        )

        # Start background processing
        options = {
            'summary_level': summary_level,
            'extract_actions': extract_actions,
            'extract_topics': extract_topics,
            'output_format': output_format,
            'language': language,
            'template': template or None
        }

        background_tasks.add_task(process_meeting_async, job_id, audio_path, options)

        logger.info(f"Analysis job {job_id} queued")

        return {
            "job_id": job_id,
            "status": "queued",
            "message": "Analysis started"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to start analysis")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    """
    Cancel a queued or in-progress job ("soft" cancel).

    Takes effect immediately: the job stops being tracked as live and its
    status flips to 'cancelled' right away. analyze_meeting() has no
    internal checkpoints (it's one blocking call covering transcription,
    summarization, and extraction), so if the job was already past
    validation, the underlying whisper.cpp/Ollama work keeps running in
    its worker thread to completion - but the result is discarded rather
    than saved, and the job will not flip to 'completed'.
    """
    if job_id not in active_jobs:
        # Not running - maybe queued-but-not-yet-started (rare race) or
        # already finished/gone. Either way there's nothing live to stop.
        db_job = db_manager.get_job(job_id)
        if not db_job:
            raise HTTPException(status_code=404, detail="Job not found")
        if db_job.status not in ('queued', 'processing'):
            raise HTTPException(status_code=400, detail=f"Job is already {db_job.status}")
        db_manager.update_job(job_id, status='cancelled', completed_at=datetime.now())
        return {"job_id": job_id, "status": "cancelled"}

    job = active_jobs[job_id]
    if job['status'] not in ('queued', 'processing'):
        raise HTTPException(status_code=400, detail=f"Job is already {job['status']}")

    job['cancel_requested'] = True
    job['status'] = 'cancelled'
    job['completed_at'] = datetime.now().isoformat()
    db_manager.update_job(job_id, status='cancelled', completed_at=datetime.now())

    await broadcast_progress(job_id, {**job.get('progress', {}), 'status': 'cancelled'})

    logger.info(f"Job {job_id} cancel requested")
    return {"job_id": job_id, "status": "cancelled"}


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status and results.

    Serves an in-flight job from the in-memory registry (has live
    progress + the full result object); falls back to the database for
    jobs that finished before a restart.
    """
    if job_id in active_jobs:
        job = active_jobs[job_id]

        response = {
            "job_id": job_id,
            "status": job['status'],
            "created_at": job.get('created_at'),
            "started_at": job.get('started_at'),
            "completed_at": job.get('completed_at'),
            "progress": job.get('progress', {})
        }

        if job['status'] == 'completed':
            response['result'] = {
                'summary': job['result'].get('summary', {}).get('text', ''),
                'topics': job['result'].get('topics', []),
                'action_items_count': job['result'].get('actions', {}).get('total_actions', 0),
                'statistics': job['result'].get('statistics', {})
            }
            response['download_url'] = f"/api/jobs/{job_id}/download"
        elif job['status'] == 'failed':
            response['error'] = job.get('error')

        return response

    # Not in memory - look it up in the database
    db_job = db_manager.get_job(job_id)
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")

    d = db_job.to_dict()
    response = {
        "job_id": job_id,
        "status": d['status'],
        "created_at": d['created_at'],
        "started_at": d['started_at'],
        "completed_at": d['completed_at'],
        "progress": {
            "progress_percent": d['progress_percent'],
            "current_stage": d['current_stage'],
        },
    }
    if d['status'] == 'completed':
        response['result'] = {
            'summary': d['summary_text'] or '',
            'topics': d['topics'] or [],
            'action_items_count': d['action_items_count'] or 0,
            'statistics': {
                'processing_time_seconds': d['processing_time_seconds'],
                'total_cost_usd': d['estimated_cost_usd'],
                'cache_hits': d['cache_hits'],
            },
        }
        response['download_url'] = f"/api/jobs/{job_id}/download"
    elif d['status'] == 'failed':
        response['error'] = d['error_message']

    return response


@app.get("/api/jobs/{job_id}/download")
async def download_report(job_id: str):
    """Download analysis report (in-memory job or, after a restart, DB)"""
    output_file = None

    if job_id in active_jobs:
        job = active_jobs[job_id]
        if job['status'] != 'completed':
            raise HTTPException(status_code=400, detail="Job not completed")
        output_file = job.get('output_file')
    else:
        db_job = db_manager.get_job(job_id)
        if not db_job:
            raise HTTPException(status_code=404, detail="Job not found")
        if db_job.status != 'completed':
            raise HTTPException(status_code=400, detail="Job not completed")
        output_file = db_job.output_file_path

    if not output_file or not Path(output_file).exists():
        raise HTTPException(status_code=404, detail="Report file not found")

    return FileResponse(
        output_file,
        media_type='application/octet-stream',
        filename=Path(output_file).name
    )


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """WebSocket for real-time progress updates"""
    await websocket.accept()

    # Register connection
    if job_id not in websocket_connections:
        websocket_connections[job_id] = []
    websocket_connections[job_id].append(websocket)

    logger.info(f"WebSocket connected for job {job_id}")

    try:
        # Send current progress if job exists
        if job_id in active_jobs and 'progress' in active_jobs[job_id]:
            await websocket.send_json(active_jobs[job_id]['progress'])

        # Keep connection alive
        while True:
            # Wait for messages (ping/pong)
            await websocket.receive_text()

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for job {job_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
    finally:
        # Cleanup
        if job_id in websocket_connections:
            websocket_connections[job_id].remove(websocket)
            if not websocket_connections[job_id]:
                del websocket_connections[job_id]


@app.get("/api/jobs")
async def list_jobs(limit: int = 50, offset: int = 0, status: Optional[str] = None):
    """List jobs from the database (survives restarts). Live status for
    any still-in-flight job is overlaid from the in-memory registry."""
    db_jobs = db_manager.list_jobs(limit=limit, offset=offset, status=status)

    jobs = []
    for j in db_jobs:
        d = j.to_dict()
        live = active_jobs.get(j.id)
        jobs.append({
            "job_id": d['job_id'],
            "filename": d['filename'],
            "status": (live['status'] if live else d['status']),
            "created_at": d['created_at'],
            "completed_at": d['completed_at'],
            "progress_percent": (
                live.get('progress', {}).get('progress_percent', d['progress_percent'])
                if live else d['progress_percent']
            ),
        })

    return {
        "total": db_manager.get_statistics().get('total_jobs', len(jobs)),
        "jobs": jobs,
    }


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job (DB row, uploaded file, and report)"""
    # db_manager.delete_job also unlinks the upload + output files
    deleted = db_manager.delete_job(job_id)
    in_memory = active_jobs.pop(job_id, None)

    if in_memory:
        for key in ('audio_path', 'output_file'):
            p = in_memory.get(key)
            if p and Path(p).exists():
                try:
                    Path(p).unlink()
                except OSError:
                    pass

    if not deleted and not in_memory:
        raise HTTPException(status_code=404, detail="Job not found")

    return {"message": "Job deleted"}


def main():
    """Run the web server"""
    port = int(os.getenv('PORT', 8000))
    host = os.getenv('HOST', '0.0.0.0')

    logger.info(f"Starting Meeting Summarizer Web Server on {host}:{port}")
    logger.info(f"Transcription backend: {config['transcription_backend']}")
    logger.info(f"LLM provider: {os.getenv('LLM_PROVIDER', 'openai')}")

    uvicorn.run(
        "server:app",
        host=host,
        port=port,
        reload=os.getenv('RELOAD', 'false').lower() == 'true',
        log_level="info"
    )


if __name__ == '__main__':
    main()
