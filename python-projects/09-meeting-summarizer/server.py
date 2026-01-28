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
    try:
        # Update job status
        active_jobs[job_id]['status'] = 'processing'
        active_jobs[job_id]['started_at'] = datetime.now().isoformat()

        # Create progress tracker
        progress_tracker = ProgressTracker(
            job_id=job_id,
            state_dir="./data/progress",
            enable_persistence=True
        )

        # Progress callback
        def on_progress(state):
            active_jobs[job_id]['progress'] = state
            asyncio.create_task(broadcast_progress(job_id, state))

        progress_tracker.add_callback(on_progress)
        progress_tracker.start(metadata={
            'audio_file': os.path.basename(audio_path),
            'options': options
        })

        # Create meeting analyzer
        meeting_analyzer, audio_processor = create_meeting_analyzer()

        # Validation stage
        progress_tracker.update_stage(ProcessingStage.VALIDATION, 10, "Validating audio file")
        validation = audio_processor.validate_audio(audio_path)

        if not validation['valid']:
            progress_tracker.fail(
                f"Audio validation failed: {', '.join(validation['errors'])}",
                ProcessingStage.VALIDATION
            )
            active_jobs[job_id]['status'] = 'failed'
            active_jobs[job_id]['error'] = validation['errors']
            return

        progress_tracker.complete_stage(ProcessingStage.VALIDATION)

        # Transcription stage
        progress_tracker.update_stage(ProcessingStage.TRANSCRIPTION, 30, "Transcribing audio")

        # Run analysis
        result = meeting_analyzer.analyze_meeting(
            audio_path,
            summary_level=options.get('summary_level', 'standard'),
            extract_actions=options.get('extract_actions', True),
            extract_topics=options.get('extract_topics', True),
            language=options.get('language')
        )

        progress_tracker.complete_stage(ProcessingStage.TRANSCRIPTION)
        progress_tracker.update_stage(ProcessingStage.SUMMARIZATION, 60, "Generating summary")
        progress_tracker.complete_stage(ProcessingStage.SUMMARIZATION)
        progress_tracker.update_stage(ProcessingStage.ACTION_EXTRACTION, 80, "Extracting action items")
        progress_tracker.complete_stage(ProcessingStage.ACTION_EXTRACTION)

        # Generate report
        progress_tracker.update_stage(ProcessingStage.REPORT_GENERATION, 90, "Generating report")

        output_format = options.get('output_format', 'markdown')
        output_file = Path(config['output_dir']) / f"{job_id}_analysis.{output_format}"

        meeting_analyzer.generate_report(
            result,
            format=output_format,
            output_path=str(output_file)
        )

        progress_tracker.complete_stage(ProcessingStage.REPORT_GENERATION)

        # Complete
        progress_tracker.complete(result={'output_file': str(output_file)})

        active_jobs[job_id]['status'] = 'completed'
        active_jobs[job_id]['result'] = result
        active_jobs[job_id]['output_file'] = str(output_file)
        active_jobs[job_id]['completed_at'] = datetime.now().isoformat()

        logger.info(f"Job {job_id} completed successfully")

    except Exception as e:
        logger.exception(f"Job {job_id} failed")
        active_jobs[job_id]['status'] = 'failed'
        active_jobs[job_id]['error'] = str(e)
        active_jobs[job_id]['completed_at'] = datetime.now().isoformat()


# Routes

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serve the main web UI"""
    return templates.TemplateResponse("index.html", {"request": request})


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
        # Validate file extension
        allowed_extensions = ['.mp3', '.wav', '.webm', '.m4a', '.ogg', '.flac']
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
    language: Optional[str] = None
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

        # Start background processing
        options = {
            'summary_level': summary_level,
            'extract_actions': extract_actions,
            'extract_topics': extract_topics,
            'output_format': output_format,
            'language': language
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


@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status and results"""
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

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


@app.get("/api/jobs/{job_id}/download")
async def download_report(job_id: str):
    """Download analysis report"""
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = active_jobs[job_id]

    if job['status'] != 'completed':
        raise HTTPException(status_code=400, detail="Job not completed")

    output_file = job.get('output_file')

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
async def list_jobs(limit: int = 50):
    """List all jobs"""
    jobs = sorted(
        active_jobs.values(),
        key=lambda x: x.get('created_at', ''),
        reverse=True
    )[:limit]

    return {
        "total": len(active_jobs),
        "jobs": [
            {
                "job_id": job['job_id'],
                "status": job['status'],
                "created_at": job.get('created_at'),
                "completed_at": job.get('completed_at')
            }
            for job in jobs
        ]
    }


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete job and associated files"""
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = active_jobs[job_id]

    # Delete uploaded file
    if 'audio_path' in job and Path(job['audio_path']).exists():
        Path(job['audio_path']).unlink()

    # Delete output file
    if 'output_file' in job and Path(job['output_file']).exists():
        Path(job['output_file']).unlink()

    # Remove from active jobs
    del active_jobs[job_id]

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
