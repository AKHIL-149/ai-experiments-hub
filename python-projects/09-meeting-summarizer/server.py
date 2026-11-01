#!/usr/bin/env python3
"""
Meeting Summarizer Web Server - Phases 4 & 5

FastAPI web server with real-time progress, database persistence,
video support, and advanced features.

Usage:
    python server.py
    # Server runs on http://127.0.0.1:8000
"""

import os
import sys

# macOS/Homebrew: pyannote.audio 4.x's audio backend (torchcodec) needs
# ffmpeg's shared libraries, which live in /opt/homebrew/lib - not on
# the default dylib search path. DYLD_LIBRARY_PATH fixes that, but only
# if it's set *before* the process launches: dyld reads it once at
# process start, so setting os.environ later (e.g. inside
# speaker_diarization.py, right before importing pyannote) does
# nothing - confirmed live, the exact same "Could not load
# libtorchcodec" failure happens either way. Re-exec once, early and
# cheaply, with the var set correctly, rather than requiring every
# operator to remember `export DYLD_LIBRARY_PATH=...` before launching
# (this is a no-op on Linux/Windows, and on a Mac without Homebrew at
# the usual path, or where the var is already set).
#
# Only when run as a script (`python server.py`): importing this module - from a test, or
# another program - must never replace the importing process.
if __name__ == "__main__" and sys.platform == 'darwin':
    _hb_lib = '/opt/homebrew/lib'
    _dyld = os.environ.get('DYLD_LIBRARY_PATH', '')
    if os.path.isdir(_hb_lib) and _hb_lib not in _dyld.split(':'):
        os.environ['DYLD_LIBRARY_PATH'] = f"{_hb_lib}:{_dyld}" if _dyld else _hb_lib
        os.execv(sys.executable, [sys.executable] + sys.argv)

import asyncio
import re
import threading
import uuid
import hashlib
from pathlib import Path
from typing import Dict, Optional, List
from datetime import datetime
from dotenv import load_dotenv
import logging

from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Query
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

# CORS: the page and the API share an origin, so only the app's own origins are allowed by
# default. ALLOWED_ORIGINS="https://a.example,https://b.example" opts others in.
def cors_origins(configured: Optional[str], port: str) -> List[str]:
    """Origins allowed to call the API from another page: the app's own unless configured otherwise"""
    default = f"http://localhost:{port},http://127.0.0.1:{port}"
    return [o.strip() for o in (configured if configured is not None else default).split(",") if o.strip()]


app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(os.getenv("ALLOWED_ORIGINS"), os.getenv("PORT", "8000")),
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
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

# Configuration. Everything lives under DATA_DIR unless a specific directory is set.
_data_dir = os.getenv('DATA_DIR', './data')
config = {
    'transcription_backend': os.getenv('TRANSCRIPTION_BACKEND', 'openai'),
    'openai_api_key': os.getenv('OPENAI_API_KEY'),
    'whisper_model': os.getenv('WHISPER_MODEL', 'whisper-1'),
    'whisper_cpp_path': os.getenv('WHISPER_CPP_PATH'),
    'whisper_model_path': os.getenv('WHISPER_CPP_MODEL'),
    'max_audio_size_mb': int(os.getenv('MAX_AUDIO_SIZE_MB', 500)),
    'data_dir': _data_dir,
    'cache_dir': os.getenv('CACHE_DIR', f'{_data_dir}/cache'),
    'transcription_ttl_days': int(os.getenv('TRANSCRIPTION_CACHE_TTL_DAYS', 30)),
    'summary_ttl_days': int(os.getenv('SUMMARY_CACHE_TTL_DAYS', 7)),
    'enable_cache': os.getenv('ENABLE_CACHE', 'true').lower() == 'true',
    'output_dir': os.getenv('OUTPUT_DIR', f'{_data_dir}/output'),
    'upload_dir': os.getenv('UPLOAD_DIR', f'{_data_dir}/uploads'),
    'temp_dir': os.getenv('TEMP_DIR', f'{_data_dir}/temp'),
    'progress_dir': os.getenv('PROGRESS_DIR', f'{_data_dir}/progress'),
    'default_output_format': os.getenv('DEFAULT_OUTPUT_FORMAT', 'markdown'),
    'max_finished_jobs_in_memory': int(os.getenv('MAX_FINISHED_JOBS_IN_MEMORY', 50)),
}

# Phase 5: Database persistence
db_url = os.getenv('DATABASE_URL', None)  # Default: SQLite in data/database.db
db_manager = DatabaseManager(db_url)

# Phase 5: Video processor
video_processor = VideoProcessor(temp_dir=config['temp_dir'])

# Phase 5: Speaker diarization (optional - needs `pip install pyannote.audio torch`).
# Loading the model takes ~25 s and makes several network requests, so it is loaded the
# first time someone asks for "identify speakers", not at startup. create_speaker_diarization()
# degrades to None gracefully if the import fails or the model can't load.
_speaker_diarizer = None
_speaker_diarizer_loaded = False
_speaker_diarizer_lock = threading.Lock()


def get_speaker_diarizer():
    """The speaker diarizer, loaded on first use (None if it is not available)"""
    global _speaker_diarizer, _speaker_diarizer_loaded
    with _speaker_diarizer_lock:
        if not _speaker_diarizer_loaded:
            _speaker_diarizer = create_speaker_diarization(os.getenv('HF_AUTH_TOKEN'))
            _speaker_diarizer_loaded = True
        return _speaker_diarizer


# Phase 5: Summary templates
template_manager = SummaryTemplateManager(custom_templates_dir='./templates/custom')

# Job storage (in-memory for Phase 4, can be migrated to database in future)
active_jobs: Dict[str, Dict] = {}

# WebSocket connections (still in-memory for real-time)
websocket_connections: Dict[str, List[WebSocket]] = {}

# What the analyze endpoint accepts. Anything else is a 400: these values end up in prompts,
# file names and command lines.
SUMMARY_LEVELS = ('brief', 'standard', 'detailed')
# output format -> file extension of the report
OUTPUT_FORMATS = {'markdown': 'md', 'md': 'md', 'json': 'json', 'html': 'html', 'txt': 'txt'}
AUDIO_EXTENSIONS = ['.mp3', '.wav', '.webm', '.m4a', '.ogg', '.flac']
UPLOAD_CHUNK_BYTES = 1024 * 1024
ACTIVE_STATUSES = ('queued', 'processing')

# Create directories
for _dir in ('upload_dir', 'output_dir', 'temp_dir', 'progress_dir'):
    Path(config[_dir]).mkdir(parents=True, exist_ok=True)


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
        whisper_model_path=config['whisper_model_path'],
        temp_dir=config['temp_dir']
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
        audio_processor=audio_processor,
        video_processor=video_processor
    )

    return meeting_analyzer, audio_processor


# ---------------------------------------------------------------------- helpers

def validate_job_id(job_id: str) -> str:
    """
    Job ids are the UUIDs the upload endpoint hands out. Anything else is refused: the id is
    used to build file names and to look up files, so a value such as "*" must never reach a glob.
    """
    try:
        return str(uuid.UUID(job_id))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid job id")


def safe_filename(name: Optional[str]) -> str:
    """The base name of an uploaded file, without directories or control characters"""
    base = Path((name or '').replace('\\', '/')).name
    base = re.sub(r'[\x00-\x1f\x7f]', '', base).strip()
    if base in ('', '.', '..'):
        base = 'upload'
    return base[:200]


def short_error(error: Exception, limit: int = 300) -> str:
    """One readable line for a failure shown to the user (full details are in the log)"""
    text = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__
    return text if len(text) <= limit else text[:limit - 1] + '…'


def evict_finished_jobs():
    """
    Finished jobs keep their whole result (transcript, speaker segments) in memory so the
    results page is instant; without a limit that grows with every job until the server
    restarts. The oldest finished ones are dropped - the database still has their summary.
    """
    finished = [
        (job.get('completed_at') or '', job_id)
        for job_id, job in active_jobs.items()
        if job.get('status') not in ACTIVE_STATUSES
    ]
    excess = len(finished) - config['max_finished_jobs_in_memory']
    if excess > 0:
        for _, job_id in sorted(finished)[:excess]:
            active_jobs.pop(job_id, None)


def cleanup_stray_upload_files(max_age_seconds: int = 3600):
    """
    Remove leftovers in the upload directory - temporary .wav/.txt files from a run that was
    interrupted. Only files that are not "<job id>.<audio/video extension>" and are older than
    an hour are touched.
    """
    import time
    allowed = set(AUDIO_EXTENSIONS) | set(video_processor.SUPPORTED_VIDEO_FORMATS)
    now = time.time()
    removed = 0
    for path in Path(config['upload_dir']).iterdir():
        if not path.is_file():
            continue
        stem, ext = path.stem, path.suffix.lower()
        try:
            uuid.UUID(stem)
            if ext in allowed:
                continue                 # a real upload
        except ValueError:
            pass
        try:
            if now - path.stat().st_mtime > max_age_seconds:
                path.unlink()
                removed += 1
        except OSError:
            pass
    if removed:
        logger.info(f"Removed {removed} stray file(s) from the upload directory")


async def broadcast_progress(job_id: str, progress_state: Dict):
    """Broadcast progress update to all connected WebSocket clients"""
    if job_id in websocket_connections:
        disconnected = []
        for websocket in list(websocket_connections[job_id]):
            try:
                await websocket.send_json(progress_state)
            except Exception as e:
                logger.error(f"WebSocket send error: {str(e)}")
                disconnected.append(websocket)

        # Remove disconnected clients
        for ws in disconnected:
            if ws in websocket_connections.get(job_id, []):
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
            state_dir=config['progress_dir'],
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
            err = '; '.join(validation['errors'])
            progress_tracker.fail(err, ProcessingStage.VALIDATION)
            active_jobs[job_id]['status'] = 'failed'
            active_jobs[job_id]['error'] = err
            active_jobs[job_id]['completed_at'] = datetime.now().isoformat()
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
            all_levels=options.get('all_levels', False),
            progress_callback=on_stage_event
        )

        # Reports/templates show metadata.source_file as the "real"
        # filename. analyze_meeting() can only see whatever path it was
        # actually called with - /api/upload saves every file to disk as
        # "<job_id>.<ext>" (not the browser's original filename), and for
        # a video upload this function passes analyze_meeting the
        # *already-extracted* temp audio path (needed so the validation
        # step above sees a real audio file), not the original video
        # path either way. Confirmed live: without this, a video's
        # report was titled with its "<job_id>_audio.mp3" temp name, and
        # even a plain audio upload's report showed "<job_id>.mp3"
        # instead of what the user actually uploaded. The real name is
        # only known to the DB row created at upload time.
        db_job = db_manager.get_job(job_id)
        if db_job and db_job.filename:
            result['metadata']['source_file'] = db_job.filename

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

        # Speaker diarization (optional, off by default). Slow on CPU (roughly real-time) but
        # a few seconds on Apple silicon. No dedicated progress stage for it: it runs
        # between action_extraction and report_generation.
        if options.get('identify_speakers'):
            await add_speaker_labels(job_id, audio_path, audio_processor, meeting_analyzer, result)

        # Third cancellation checkpoint. Diarization runs for as long as
        # the audio does (roughly real-time on CPU, seconds on MPS), so
        # this window matters - without this check, a cancel that
        # arrived while it was running would be silently overwritten by
        # the unconditional 'completed' a few lines down, exactly like
        # the gap this mirrors at the transcription checkpoint above.
        if active_jobs[job_id].get('cancel_requested'):
            logger.info(f"Job {job_id} finished diarization after being cancelled - discarding result")
            return

        # Generate report
        progress_tracker.update_stage(ProcessingStage.REPORT_GENERATION, 90, "Generating report")

        template = options.get('template')
        output_format = 'md' if template else OUTPUT_FORMATS[options.get('output_format', 'markdown')]
        output_file = Path(config['output_dir']) / f"{job_id}_analysis.{output_format}"

        await asyncio.to_thread(
            meeting_analyzer.generate_report,
            result,
            format={'md': 'markdown'}.get(output_format, output_format),
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
            summary_text=(result.get('summary') or {}).get('text'),
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
        active_jobs[job_id]['error'] = short_error(e)
        active_jobs[job_id]['completed_at'] = datetime.now().isoformat()
        try:
            db_manager.mark_job_failed(job_id, short_error(e))
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
        evict_finished_jobs()


async def add_speaker_labels(job_id: str, audio_path: str, audio_processor, meeting_analyzer, result: Dict):
    """
    "Identify speakers": diarize the audio and label the transcript with who said what.
    Best-effort - it never fails an otherwise successful analysis; if it cannot be done the
    result says so in result['warnings'].
    """
    warnings = result.setdefault('warnings', [])

    diarizer = await asyncio.to_thread(get_speaker_diarizer)
    if not diarizer:
        warnings.append(
            "Speaker identification was requested but is not available on this server "
            "(it needs the optional pyannote.audio package and access to its model)."
        )
        return

    try:
        logger.info(f"Job {job_id}: running speaker diarization")
        # pyannote needs a real WAV - confirmed live that handing
        # it an mp3 directly fails ("requested chunk [...]
        # resulted in 439895 samples instead of the expected
        # 441000 samples"); mp3's frame-based encoding isn't
        # sample-accurate to seek into.
        audio_segment = await asyncio.to_thread(audio_processor.load_audio, audio_path)
        diarize_wav = str(Path(audio_path).with_suffix('')) + '_diarize.wav'
        await asyncio.to_thread(audio_processor.export_audio, audio_segment, diarize_wav, 'wav')
        try:
            segments = await asyncio.to_thread(diarizer.diarize, diarize_wav)
        finally:
            Path(diarize_wav).unlink(missing_ok=True)

        if not segments:
            warnings.append("Speaker identification ran but found no speakers.")
            return

        transcript_segments = (result.get('transcript') or {}).get('segments') or []
        if transcript_segments:
            # Every transcript segment has real start/end times: match them to the
            # diarization turns they overlap.
            speaker_transcript = diarizer.assign_segments_to_speakers(transcript_segments, segments)
            approximate = False
        else:
            speaker_transcript = diarizer.assign_transcript_to_speakers(result['transcript']['text'], segments)
            approximate = True
            warnings.append(
                "This transcript has no timing information, so speaker labels were spread evenly "
                "over the recording and are only a rough guess."
            )

        result['speaker_diarization'] = {
            'segments': segments,
            'statistics': diarizer.get_speaker_statistics(segments),
            'speaker_transcript': speaker_transcript,
            # True when the labels are an even-spread guess rather than matched to timestamps
            'approximate': approximate,
            # One LLM call per speaker - best-effort, on top of an already best-effort
            # feature, so a failure here shouldn't drop the diarization results we have.
            'key_points': {}
        }
        logger.info(
            f"Job {job_id}: identified "
            f"{result['speaker_diarization']['statistics']['total_speakers']} speaker(s)"
        )

        try:
            result['speaker_diarization']['key_points'] = await asyncio.to_thread(
                meeting_analyzer.summarizer.extract_speaker_key_points,
                speaker_transcript
            )
        except Exception as e:
            logger.warning(f"Job {job_id}: speaker key point extraction failed: {e}")
            warnings.append("Per-speaker key points could not be generated.")

    except Exception as e:
        # Best-effort - never fail an otherwise-successful analysis job just because
        # diarization didn't work.
        logger.warning(f"Job {job_id}: speaker diarization failed: {e}")
        warnings.append(f"Speaker identification failed: {short_error(e)}")


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

    try:
        cleanup_stray_upload_files()
    except Exception:
        logger.exception("Startup upload cleanup failed")


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
            "cache_enabled": config['enable_cache'],
            # None until the first "identify speakers" request has tried to load it
            "speaker_identification": (
                None if not _speaker_diarizer_loaded else _speaker_diarizer is not None
            )
        }
    }


@app.get("/api/templates")
async def list_templates():
    """The report templates the analyze endpoint accepts"""
    return {"templates": template_manager.list_available_templates()}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload audio or video file"""
    # Validate file extension - audio, or a video container we can
    # pull the audio track out of (see VideoProcessor).
    allowed_extensions = AUDIO_EXTENSIONS + [
        e for e in video_processor.SUPPORTED_VIDEO_FORMATS if e not in AUDIO_EXTENSIONS
    ]
    filename = safe_filename(file.filename)
    file_ext = Path(filename).suffix.lower()

    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_extensions)}"
        )

    # Generate unique filename
    job_id = str(uuid.uuid4())
    upload_path = Path(config['upload_dir']) / f"{job_id}{file_ext}"
    max_bytes = config['max_audio_size_mb'] * 1024 * 1024
    size = 0

    try:
        # Stream to disk in pieces, refusing as soon as the limit is passed - reading the
        # whole upload into memory first meant a huge file could exhaust the server before
        # any size check ran.
        with open(upload_path, 'wb') as f:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum size: {config['max_audio_size_mb']} MB"
                    )
                f.write(chunk)

        if size == 0:
            raise HTTPException(status_code=400, detail="The uploaded file is empty")

        logger.info(f"File uploaded: {filename} -> {upload_path}")

        # Persist the job now so its original filename is recorded and it
        # shows up in /api/jobs even before analysis starts / after a
        # server restart.
        db_manager.create_job(
            job_id=job_id,
            filename=filename,
            file_path=str(upload_path)
        )

    except HTTPException:
        upload_path.unlink(missing_ok=True)
        raise
    except Exception:
        upload_path.unlink(missing_ok=True)
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail="The upload could not be saved")

    return {
        "job_id": job_id,
        "filename": filename,
        "upload_path": str(upload_path),
        "size_bytes": size
    }


@app.post("/api/analyze/{job_id}")
async def start_analysis(
    job_id: str,
    background_tasks: BackgroundTasks,
    summary_level: str = 'standard',
    extract_actions: bool = True,
    extract_topics: bool = True,
    output_format: str = 'markdown',
    language: Optional[str] = None,
    template: Optional[str] = None,
    all_levels: bool = False,
    identify_speakers: bool = False
):
    """Start meeting analysis job"""
    job_id = validate_job_id(job_id)

    # Options are checked before anything is queued: they end up in prompts, file names
    # and command lines.
    if summary_level not in SUMMARY_LEVELS:
        raise HTTPException(status_code=400, detail=f"Invalid summary_level. Use one of: {', '.join(SUMMARY_LEVELS)}")
    if output_format not in OUTPUT_FORMATS:
        raise HTTPException(status_code=400, detail=f"Invalid output_format. Use one of: {', '.join(sorted(set(OUTPUT_FORMATS) - {'md'}))}")
    if language is not None and language != '':
        try:
            language = TranscriptionService.validate_language(language)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        language = None
    if template:
        available = template_manager.list_available_templates()
        if template not in available:
            raise HTTPException(status_code=400, detail=f"Unknown template. Use one of: {', '.join(sorted(available))}")
    else:
        template = None

    # The job and its file are looked up by id in the database - never by a glob over the
    # upload directory, which could match another job's file or a leftover temp file.
    db_job = db_manager.get_job(job_id)
    if not db_job:
        raise HTTPException(status_code=404, detail="Uploaded file not found")

    audio_path = db_job.file_path
    if not audio_path or not Path(audio_path).exists():
        raise HTTPException(status_code=404, detail="Uploaded file not found")

    # One run per job at a time: two runs share the job's files and would corrupt each other.
    live = active_jobs.get(job_id)
    if live and live.get('status') in ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="This job is already being analyzed")

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
        error_message=None,
    )

    # Start background processing
    options = {
        'summary_level': summary_level,
        'extract_actions': extract_actions,
        'extract_topics': extract_topics,
        'output_format': output_format,
        'language': language,
        'template': template,
        'all_levels': all_levels,
        'identify_speakers': identify_speakers
    }

    background_tasks.add_task(process_meeting_async, job_id, audio_path, options)

    logger.info(f"Analysis job {job_id} queued")

    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Analysis started"
    }


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
    job_id = validate_job_id(job_id)

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
    job_id = validate_job_id(job_id)

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

        if job['status'] == 'completed' and job.get('result'):
            result = job['result']
            # actions/topics are None (not absent) when that step was switched off
            response['result'] = {
                'summary': (result.get('summary') or {}).get('text', ''),
                'topics': result.get('topics') or [],
                'action_items_count': (result.get('actions') or {}).get('total_actions', 0),
                'statistics': result.get('statistics') or {},
                'warnings': result.get('warnings') or [],
                # the items themselves (the results page lists them; the count alone says nothing)
                'actions': {
                    'action_items': (result.get('actions') or {}).get('action_items') or [],
                    'decisions': (result.get('actions') or {}).get('decisions') or [],
                    'follow_ups': (result.get('actions') or {}).get('follow_ups') or [],
                }
            }
            if result.get('summary_levels'):
                response['result']['summary_levels'] = result['summary_levels']
            if result.get('speaker_diarization'):
                response['result']['speaker_diarization'] = result['speaker_diarization']
            if (result.get('transcript') or {}).get('text'):
                response['result']['transcript'] = result['transcript']['text']
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


DOWNLOAD_MEDIA_TYPES = {
    '.md': 'text/markdown; charset=utf-8',
    '.markdown': 'text/markdown; charset=utf-8',
    '.json': 'application/json',
    '.html': 'text/html; charset=utf-8',
    '.txt': 'text/plain; charset=utf-8',
}


@app.get("/api/jobs/{job_id}/download")
async def download_report(job_id: str):
    """Download analysis report (in-memory job or, after a restart, DB)"""
    job_id = validate_job_id(job_id)
    output_file = None
    original_name = None

    db_job = db_manager.get_job(job_id)
    if db_job:
        original_name = db_job.filename

    if job_id in active_jobs:
        job = active_jobs[job_id]
        if job['status'] != 'completed':
            raise HTTPException(status_code=400, detail="Job not completed")
        output_file = job.get('output_file')
    else:
        if not db_job:
            raise HTTPException(status_code=404, detail="Job not found")
        if db_job.status != 'completed':
            raise HTTPException(status_code=400, detail="Job not completed")
        output_file = db_job.output_file_path

    if not output_file or not Path(output_file).exists():
        raise HTTPException(status_code=404, detail="Report file not found")

    # Name the download after the meeting file the user uploaded, not the job id
    ext = Path(output_file).suffix
    stem = Path(safe_filename(original_name)).stem if original_name else job_id
    return FileResponse(
        output_file,
        media_type=DOWNLOAD_MEDIA_TYPES.get(ext.lower(), 'application/octet-stream'),
        filename=f"{stem}_analysis{ext}"
    )


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """WebSocket for real-time progress updates"""
    try:
        job_id = str(uuid.UUID(job_id))
    except ValueError:
        await websocket.close(code=1008)          # policy violation: not a job id
        return

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
        if websocket in websocket_connections.get(job_id, []):
            websocket_connections[job_id].remove(websocket)
        if job_id in websocket_connections and not websocket_connections[job_id]:
            del websocket_connections[job_id]


@app.get("/api/jobs")
async def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: Optional[str] = None
):
    """List jobs from the database (survives restarts). Live status for
    any still-in-flight job is overlaid from the in-memory registry."""
    if status and status not in ('queued', 'processing', 'completed', 'failed', 'cancelled'):
        raise HTTPException(status_code=400, detail="Invalid status filter")

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
    job_id = validate_job_id(job_id)

    live = active_jobs.get(job_id)
    if live and live.get('status') in ACTIVE_STATUSES:
        # Deleting a job that is still running: stop caring about its result first
        live['cancel_requested'] = True
        live['status'] = 'cancelled'

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

    # the job's saved progress state goes with it
    Path(config['progress_dir'], f"{job_id}.json").unlink(missing_ok=True)

    return {"message": "Job deleted"}


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    """Anything unhandled is logged in full and reported without internals"""
    logger.exception(f"Unhandled error on {request.method} {request.url.path}")
    return JSONResponse(status_code=500, content={"detail": "Something went wrong on the server"})


def main():
    """Run the web server"""
    port = int(os.getenv('PORT', 8000))
    # Loopback by default: there is no login, so it should not be reachable from the network
    # unless HOST=0.0.0.0 says so.
    host = os.getenv('HOST', '127.0.0.1')

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


if __name__ == "__main__":
    main()
