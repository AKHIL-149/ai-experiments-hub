#!/usr/bin/env python3
"""FastAPI server for Content Analyzer web interface."""
import sys
import os
import base64
import re
import requests
from pathlib import Path
from typing import Optional, List
from io import BytesIO
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load .env before anything reads os.getenv() - every provider default,
# API key, and model override in this file and src/core/ depends on this
# actually running (confirmed live: without it, .env's DEFAULT_PROVIDER,
# API keys, etc. are silently ignored no matter what's in the file).
load_dotenv(project_root / '.env')

from fastapi import FastAPI, File, UploadFile, Form
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image

from src.core.vision_client import VisionClient, VisionError
from src.core.image_processor import ImageProcessor, ImageError, max_upload_bytes
from src.core.ocr_processor import OCRProcessor
from src.core.cache_manager import CacheManager
from src.core.prompt_templates import get_prompt, PROMPT_TEMPLATES
from src.core.image_comparator import ImageComparator
from src.core.batch_processor import BatchProcessor
from src.version import __version__

PROVIDERS = ("ollama", "anthropic", "openai")
OCR_METHODS = ("auto", "tesseract", "vision")
COMPARE_MODES = ("content", "visual", "detailed")
LANGUAGE_RE = re.compile(r"^[A-Za-z0-9_]+(\+[A-Za-z0-9_]+)*$")


def max_batch_files() -> int:
    """Most files one batch request may hold (MAX_BATCH_FILES, default 50)"""
    try:
        return max(1, int(os.getenv("MAX_BATCH_FILES", "50")))
    except ValueError:
        return 50


class ApiError(Exception):
    """A request that cannot be served; becomes an HTTP error with a one-line message.

    The body keeps the shape the page expects ({"success": false, "error": ...}) and also has
    "detail" (the usual FastAPI field), so scripts and the web page can both read it.
    """

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = " ".join(str(message).split())[:400]


# How a failed model call maps to an HTTP status
_VISION_STATUS = {
    "unavailable": 503, "timeout": 504, "rate_limit": 429, "auth": 502,
    "model": 400, "bad_request": 400, "server": 502, "connection": 503, "empty": 502, "other": 502,
}

# Initialize FastAPI app
app = FastAPI(
    title="Content Analyzer API",
    description="Vision AI image analysis with OCR, comparison, and batch processing",
    version=__version__
)

# The page and the API share an origin, so no cross-origin access is needed. Set
# CORS_ORIGINS="https://a.example,https://b.example" to allow specific other origins.
_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip() and o.strip() != "*"]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )


@app.exception_handler(ApiError)
async def api_error_handler(request, exc: ApiError):
    return JSONResponse(status_code=exc.status_code, content={"success": False, "error": exc.message, "detail": exc.message})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(x) for x in first.get("loc", []) if x != "body")
    message = f"Invalid request: {where + ': ' if where else ''}{first.get('msg', 'bad input')}"
    return JSONResponse(status_code=422, content={"success": False, "error": message, "detail": message})


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request, exc: StarletteHTTPException):
    message = str(exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"success": False, "error": message, "detail": message})


@app.exception_handler(Exception)
async def unexpected_error_handler(request, exc: Exception):
    message = f"Unexpected server error: {type(exc).__name__}"
    return JSONResponse(status_code=500, content={"success": False, "error": message, "detail": message})


# Mount static files
static_dir = project_root / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Initialize components
cache_manager = CacheManager()
image_processor = ImageProcessor()


# ----------------------------------------------------------------------------- helpers

async def read_image(file: UploadFile, label: str = "") -> tuple:
    """(image, size in bytes) from an upload. Raises ApiError with 400 (not an image) or 413 (too big)."""
    prefix = f"{label}: " if label else ""
    limit = max_upload_bytes()
    if file.size is not None and file.size > limit:
        raise ApiError(413, f"{prefix}The file is {file.size / 1024 / 1024:.1f} MB; the limit is {limit / 1024 / 1024:.0f} MB")
    contents = await file.read()
    try:
        image = await run_in_threadpool(image_processor.open_bytes, contents)
    except ImageError as error:
        message = str(error)
        status = 413 if ("limit" in message or "too many pixels" in message) else 400
        raise ApiError(status, f"{prefix}{message}")
    validation = image_processor.validate_image(image, len(contents))
    if not validation["valid"]:
        raise ApiError(400, f"{prefix}Invalid image: {', '.join(validation['errors'])}")
    return image, len(contents)


def check_provider(provider: str) -> str:
    provider = (provider or "").strip().lower()
    if provider not in PROVIDERS:
        raise ApiError(400, f"Unsupported provider '{provider}'. Choose from: {', '.join(PROVIDERS)}")
    return provider


def check_preset(preset: Optional[str]) -> Optional[str]:
    preset = (preset or "").strip() or None
    if preset and preset not in PROMPT_TEMPLATES:
        raise ApiError(400, f"Unknown preset '{preset}'. Choose from: {', '.join(PROMPT_TEMPLATES)}")
    return preset


def check_range(name: str, value: float, low: float, high: float):
    if not (low <= value <= high):
        raise ApiError(422, f"{name} must be between {low:g} and {high:g}")


def check_language(language: str) -> str:
    language = (language or "").strip()
    if not LANGUAGE_RE.match(language):
        raise ApiError(400, f"'{language}' is not a language code (examples: eng, fra, chi_sim, eng+fra)")
    return language


def make_client(provider: str, model: Optional[str], **kwargs) -> VisionClient:
    try:
        return VisionClient(backend=provider, model=(model or "").strip() or None, **kwargs)
    except (ValueError, ImportError) as error:
        raise ApiError(503, str(error))


async def call_model(func, *args, **kwargs):
    """Run a blocking model call in the threadpool and turn its failures into API errors."""
    try:
        return await run_in_threadpool(func, *args, **kwargs)
    except VisionError as error:
        raise ApiError(_VISION_STATUS.get(error.kind, 502), str(error))
    except (ValueError, ImportError) as error:      # missing API key / SDK
        raise ApiError(503, str(error))


class AnalyzeResponse(BaseModel):
    """Response model for image analysis."""
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None
    cached: bool = False
    truncated: bool = False
    metadata: Optional[dict] = None


class OCRResponse(BaseModel):
    """Response model for OCR extraction."""
    success: bool
    text: Optional[str] = None
    confidence: Optional[float] = None
    method: Optional[str] = None
    language: Optional[str] = None
    error: Optional[str] = None
    details: Optional[dict] = None


class CompareResponse(BaseModel):
    """Response model for image comparison."""
    success: bool
    result: Optional[dict] = None
    error: Optional[str] = None


class BatchResponse(BaseModel):
    """Response model for batch processing."""
    success: bool
    total_images: int = 0
    successful: int = 0
    failed: int = 0
    results: List[dict] = []
    errors: List[dict] = []
    elapsed_time: float = 0
    error: Optional[str] = None


@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def root():
    """Serve the main HTML page.

    app.js is referenced with a cache-busting ?v=<mtime> query param -
    confirmed live that without one, the browser's HTTP cache (shared
    across tabs, keyed by URL) can silently keep serving a stale copy
    of app.js indefinitely after any update, even in a brand new tab.
    """
    html_file = project_root / "templates" / "index.html"
    if html_file.exists():
        html = html_file.read_text(encoding="utf-8")
        app_js_file = static_dir / "app.js"
        if app_js_file.exists():
            version = int(app_js_file.stat().st_mtime)
            html = html.replace('src="/static/app.js"', f'src="/static/app.js?v={version}"')
        return html
    return HTMLResponse(content="<h1>Content Analyzer</h1><p>Frontend not found. Please check templates/index.html</p>")


_ocr_status = {}


def ocr_status() -> dict:
    """Whether Tesseract works here and which languages it has (looked up once)."""
    if not _ocr_status:
        info = {"tesseract": False, "languages": [], "problem": None}
        probe = OCRProcessor(use_tesseract=True)
        if probe.use_tesseract:
            try:
                info["languages"] = probe.installed_languages()
                info["tesseract"] = True
            except Exception as error:
                info["problem"] = " ".join(str(error).split())
        else:
            info["problem"] = probe.tesseract_problem
        _ocr_status.update(info)
    return _ocr_status


@app.get("/api/health")
async def health_check():
    """Health check endpoint - also reports the configured default
    provider and which providers are actually usable, so the frontend
    can default its provider dropdowns correctly instead of assuming
    a cloud provider is configured."""
    default_provider = os.getenv("DEFAULT_PROVIDER", "ollama")

    ollama_available = False
    try:
        ollama_url = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
        resp = await run_in_threadpool(requests.get, f"{ollama_url}/api/tags", timeout=2)
        ollama_available = resp.status_code == 200
    except Exception:
        pass

    return {
        "status": "healthy",
        "version": __version__,
        "default_provider": default_provider,
        "providers": {
            "ollama": {"available": ollama_available},
            "anthropic": {"available": bool(os.getenv("ANTHROPIC_API_KEY"))},
            "openai": {"available": bool(os.getenv("OPENAI_API_KEY"))}
        },
        "ocr": await run_in_threadpool(ocr_status),
    }


@app.get("/api/presets")
async def get_presets():
    """Get available prompt presets."""
    presets = {}
    for name, template in PROMPT_TEMPLATES.items():
        # Get first line of template as description
        description = template.split('\n')[0] if template else ""
        presets[name] = {
            "name": name,
            "description": description
        }
    return {"presets": presets}


@app.get("/api/cache/stats")
async def get_cache_stats():
    """Get cache statistics."""
    stats = await run_in_threadpool(cache_manager.get_stats)
    return {
        "success": True,
        "stats": stats
    }


@app.post("/api/cache/cleanup")
async def cleanup_cache(keep_hours: Optional[int] = None):
    """Clean up cache entries."""
    if keep_hours is not None and keep_hours < 0:
        raise ApiError(422, "keep_hours must be 0 or more")
    removed = await run_in_threadpool(cache_manager.cleanup, keep_hours)
    stats = await run_in_threadpool(cache_manager.get_stats)
    return {
        "success": True,
        "removed": removed,
        "cache_size_mb": stats['cache_size_mb']
    }


@app.post("/api/cache/clear")
async def clear_cache():
    """Clear all cache entries."""
    await run_in_threadpool(cache_manager.clear)
    return {
        "success": True,
        "message": "Cache cleared successfully"
    }


@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze_image(
    file: UploadFile = File(...),
    prompt: Optional[str] = Form(None),
    preset: Optional[str] = Form(None),
    provider: str = Form(os.getenv("DEFAULT_PROVIDER", "ollama")),
    model: Optional[str] = Form(None),
    temperature: float = Form(0.7),
    max_tokens: int = Form(300),
    enable_cache: bool = Form(True)
):
    """Analyze image with vision AI.

    Problems with the request are 4xx errors with a one-line "detail"; a model that is down or
    refuses is 5xx (see the status map above).
    """
    provider = check_provider(provider)
    preset = check_preset(preset)
    check_range("temperature", temperature, 0, 2)
    check_range("max_tokens", max_tokens, 1, 8192)
    image, size_bytes = await read_image(file)
    metadata = image_processor.extract_metadata(image, size_bytes)

    final_prompt = get_prompt(
        template_name=preset,
        custom_prompt=(prompt or "").strip() or None
    )

    vision_client = make_client(
        provider, model,
        cache_manager=cache_manager if enable_cache else None,
        enable_cache=enable_cache
    )

    # Model calls block for seconds to minutes. Running them directly in
    # this async handler froze the whole event loop (confirmed live: during a
    # long batch /api/cache/stats hung for 2+ minutes and the UI was dead), so
    # every heavy endpoint runs its blocking work in the threadpool.
    result = await call_model(
        vision_client.analyze,
        prompt=final_prompt,
        images=[image],
        max_tokens=max_tokens,
        temperature=temperature
    )

    return AnalyzeResponse(
        success=True,
        result=result,
        cached=vision_client.last_cached,
        truncated=vision_client.truncated,
        metadata={
            "format": metadata['format'],
            "dimensions": metadata['dimensions'],
            "size_mb": metadata['size_mb'],
            "provider": provider,
            "model": vision_client.model,
            "preset": preset
        }
    )


def build_ocr(method: str, provider: str, model: Optional[str], fallback: bool) -> OCRProcessor:
    """OCR processor with a vision client when the method or the fallback needs one."""
    vision_client = make_client(provider, model) if (fallback or method == 'vision') else None
    return OCRProcessor(use_tesseract=(method != 'vision'), vision_client=vision_client)


def check_ocr_options(method: str, language: str, confidence: float, provider: str):
    method = (method or "auto").strip().lower()
    if method not in OCR_METHODS:
        raise ApiError(400, f"Unsupported method '{method}'. Choose from: {', '.join(OCR_METHODS)}")
    check_range("confidence", confidence, 0, 100)
    return method, check_language(language), check_provider(provider)


@app.post("/api/ocr", response_model=OCRResponse)
async def extract_text(
    file: UploadFile = File(...),
    method: str = Form("auto"),
    language: str = Form("eng"),
    provider: str = Form(os.getenv("DEFAULT_PROVIDER", "ollama")),
    model: Optional[str] = Form(None),
    fallback: bool = Form(True),
    confidence: float = Form(60.0)
):
    """Extract text from image using OCR."""
    method, language, provider = check_ocr_options(method, language, confidence, provider)
    image, _size = await read_image(file)

    ocr_processor = build_ocr(method, provider, model, fallback)

    # fallback_to_vision is the only thing that actually gates whether vision runs at all
    # - method='vision' with fallback left unchecked would otherwise silently return an
    # empty result (method: 'none') despite the vision_client having been built to do this.
    result = await call_model(
        ocr_processor.extract_text,
        image=image,
        language=language,
        fallback_to_vision=(fallback or method == 'vision'),
        confidence_threshold=confidence
    )

    # extract_text() swallows engine failures (timeouts, etc.) into details and returns a result
    # with no method / no text - report that as an error rather than a successful empty extraction.
    details = result.get('details', {})
    engine_error = details.get('vision_error') or details.get('tesseract_error')
    if result['method'] == 'none' and engine_error:
        raise ApiError(502 if details.get('vision_error') else 400, engine_error)

    return OCRResponse(
        success=True,
        text=result['text'],
        confidence=result['confidence'],
        method=result['method'],
        language=result['language'],
        details=details
    )


@app.post("/api/detect-language")
async def detect_language(
    file: UploadFile = File(...),
    use_vision: bool = Form(False),
    provider: str = Form(os.getenv("DEFAULT_PROVIDER", "ollama")),
    model: Optional[str] = Form(None)
):
    """Detect language in image text."""
    provider = check_provider(provider)
    image, _size = await read_image(file)

    vision_client = make_client(provider, model) if use_vision else None
    ocr_processor = OCRProcessor(use_tesseract=True, vision_client=vision_client)

    result = await call_model(ocr_processor.detect_language, image)

    return {
        "success": True,
        "result": result
    }


@app.post("/api/compare", response_model=CompareResponse)
async def compare_images(
    file1: UploadFile = File(...),
    file2: UploadFile = File(...),
    use_ai: bool = Form(False),
    mode: str = Form("content"),
    provider: str = Form(os.getenv("DEFAULT_PROVIDER", "ollama")),
    model: Optional[str] = Form(None),
    temperature: float = Form(0.3),
    # 300 wasn't enough for a multi-point comparison + similarity rating -
    # confirmed live the AI's response got cut off mid-sentence right
    # before it could state a similarity score, silently leaving
    # extracted_similarity null and the reported score structural-only.
    # The CLI's `compare --use-ai` already defaults to 1000; match it.
    max_tokens: int = Form(1000)
):
    """Compare two images."""
    mode = (mode or "content").strip().lower()
    if mode not in COMPARE_MODES:
        raise ApiError(400, f"Unsupported mode '{mode}'. Choose from: {', '.join(COMPARE_MODES)}")
    provider = check_provider(provider)
    check_range("temperature", temperature, 0, 2)
    check_range("max_tokens", max_tokens, 1, 8192)

    image1, _ = await read_image(file1, "Image 1")
    image2, _ = await read_image(file2, "Image 2")

    vision_client = make_client(provider, model) if use_ai else None
    comparator = ImageComparator(vision_client=vision_client)

    result = await call_model(
        comparator.compare_images,
        image1=image1,
        image2=image2,
        mode=mode,
        temperature=temperature,
        max_tokens=max_tokens
    )

    return CompareResponse(
        success=True,
        result=result
    )


async def read_batch(files: List[UploadFile]):
    """Open every uploaded file. Returns (images, names, original indexes, errors).

    A file that cannot be used is reported as an error with its name and the reason (it used to be
    dropped silently), and keeps its place in the numbering.
    """
    if not files:
        raise ApiError(400, "No files provided")
    if len(files) > max_batch_files():
        raise ApiError(413, f"{len(files)} files sent; a batch may hold at most {max_batch_files()}")

    images, names, indexes, errors = [], [], [], []
    for index, file in enumerate(files):
        name = file.filename or f"image_{index + 1}"
        try:
            image, _size = await read_image(file)
        except ApiError as error:
            errors.append({"index": index, "name": name, "success": False, "error": error.message})
            continue
        images.append(image)
        names.append(name)
        indexes.append(index)
    if not images:
        raise ApiError(400, "None of the files could be used. " + "; ".join(f"{e['name']}: {e['error']}" for e in errors[:3]))
    return images, names, indexes, errors


def batch_response(results: dict, indexes: List[int], rejected: List[dict], total: int) -> BatchResponse:
    """Merge the processor's results with the files rejected before processing, in upload order."""
    for item in results['results'] + results['errors']:
        item['index'] = indexes[item['index']]
    errors = sorted(results['errors'] + rejected, key=lambda e: e['index'])
    return BatchResponse(
        success=True,
        total_images=total,
        successful=results['successful'],
        failed=len(errors),
        results=results['results'],
        errors=errors,
        elapsed_time=results['elapsed_time']
    )


@app.post("/api/batch-analyze", response_model=BatchResponse)
async def batch_analyze(
    files: List[UploadFile] = File(...),
    prompt: Optional[str] = Form(None),
    preset: Optional[str] = Form(None),
    provider: str = Form(os.getenv("DEFAULT_PROVIDER", "ollama")),
    model: Optional[str] = Form(None),
    temperature: float = Form(0.7),
    max_tokens: int = Form(300),
    workers: int = Form(4),
    enable_cache: bool = Form(True)
):
    """Batch analyze multiple images."""
    provider = check_provider(provider)
    preset = check_preset(preset)
    check_range("temperature", temperature, 0, 2)
    check_range("max_tokens", max_tokens, 1, 8192)
    check_range("workers", workers, 1, 8)
    images, names, indexes, rejected = await read_batch(files)

    final_prompt = get_prompt(
        template_name=preset,
        custom_prompt=(prompt or "").strip() or None
    )

    vision_client = make_client(
        provider, model,
        cache_manager=cache_manager if enable_cache else None,
        enable_cache=enable_cache
    )
    batch_processor = BatchProcessor(vision_client=vision_client, max_workers=workers)

    results = await call_model(
        batch_processor.batch_analyze,
        images=images,
        image_names=names,
        prompt=final_prompt,
        temperature=temperature,
        max_tokens=max_tokens
    )
    return batch_response(results, indexes, rejected, len(files))


@app.post("/api/batch-ocr", response_model=BatchResponse)
async def batch_ocr(
    files: List[UploadFile] = File(...),
    method: str = Form("auto"),
    language: str = Form("eng"),
    provider: str = Form(os.getenv("DEFAULT_PROVIDER", "ollama")),
    model: Optional[str] = Form(None),
    fallback: bool = Form(True),
    confidence: float = Form(60.0),
    workers: int = Form(4)
):
    """Batch OCR multiple images."""
    method, language, provider = check_ocr_options(method, language, confidence, provider)
    check_range("workers", workers, 1, 8)
    images, names, indexes, rejected = await read_batch(files)

    ocr_processor = build_ocr(method, provider, model, fallback)
    batch_processor = BatchProcessor(ocr_processor=ocr_processor, max_workers=workers)

    results = await call_model(
        batch_processor.batch_ocr,
        images=images,
        image_names=names,
        language=language,
        method=method,
        fallback_to_vision=fallback,
        confidence_threshold=confidence
    )
    return batch_response(results, indexes, rejected, len(files))


if __name__ == "__main__":
    import uvicorn

    # Loopback by default: the API has no login, so it must not be reachable from the network
    # unless you ask for it (HOST=0.0.0.0).
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))

    print("🚀 Starting Content Analyzer Web Server...")
    print(f"📊 Access the web interface at: http://localhost:{port}")
    print(f"📚 API docs at: http://localhost:{port}/docs")

    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info"
    )
