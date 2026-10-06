#!/usr/bin/env python3
"""FastAPI server for Content Analyzer web interface."""
import sys
import os
import base64
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

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image

from src.core.vision_client import VisionClient
from src.core.image_processor import ImageProcessor
from src.core.ocr_processor import OCRProcessor
from src.core.cache_manager import CacheManager
from src.core.prompt_templates import get_prompt, PROMPT_TEMPLATES
from src.core.image_comparator import ImageComparator
from src.core.batch_processor import BatchProcessor

# Initialize FastAPI app
app = FastAPI(
    title="Content Analyzer API",
    description="Vision AI image analysis with OCR, comparison, and batch processing",
    version="0.7.7"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_dir = project_root / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Initialize components
cache_manager = CacheManager()
image_processor = ImageProcessor()


# Pydantic models
class AnalyzeRequest(BaseModel):
    """Request model for image analysis."""
    prompt: Optional[str] = None
    preset: Optional[str] = None
    provider: str = "anthropic"
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 1000
    enable_cache: bool = True


class OCRRequest(BaseModel):
    """Request model for OCR extraction."""
    method: str = "auto"
    language: str = "eng"
    provider: str = "anthropic"
    model: Optional[str] = None
    fallback: bool = True
    confidence: float = 60.0


class AnalyzeResponse(BaseModel):
    """Response model for image analysis."""
    success: bool
    result: Optional[str] = None
    error: Optional[str] = None
    cached: bool = False
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


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main HTML page.

    app.js is referenced with a cache-busting ?v=<mtime> query param -
    confirmed live that without one, the browser's HTTP cache (shared
    across tabs, keyed by URL) can silently keep serving a stale copy
    of app.js indefinitely after any update, even in a brand new tab.
    """
    html_file = project_root / "templates" / "index.html"
    if html_file.exists():
        html = html_file.read_text()
        app_js_file = static_dir / "app.js"
        if app_js_file.exists():
            version = int(app_js_file.stat().st_mtime)
            html = html.replace('src="/static/app.js"', f'src="/static/app.js?v={version}"')
        return html
    return HTMLResponse(content="<h1>Content Analyzer</h1><p>Frontend not found. Please check templates/index.html</p>")


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
        resp = requests.get(f"{ollama_url}/api/tags", timeout=2)
        ollama_available = resp.status_code == 200
    except Exception:
        pass

    return {
        "status": "healthy",
        "version": "0.7.7",
        "default_provider": default_provider,
        "providers": {
            "ollama": {"available": ollama_available},
            "anthropic": {"available": bool(os.getenv("ANTHROPIC_API_KEY"))},
            "openai": {"available": bool(os.getenv("OPENAI_API_KEY"))}
        }
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
    try:
        stats = cache_manager.get_stats()
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cache/cleanup")
async def cleanup_cache(keep_hours: Optional[int] = None):
    """Clean up cache entries."""
    try:
        removed = cache_manager.cleanup(keep_recent_hours=keep_hours)
        stats = cache_manager.get_stats()
        return {
            "success": True,
            "removed": removed,
            "cache_size_mb": stats['cache_size_mb']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cache/clear")
async def clear_cache():
    """Clear all cache entries."""
    try:
        cache_manager.clear()
        return {
            "success": True,
            "message": "Cache cleared successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
    """Analyze image with vision AI."""
    try:
        # Read and validate image
        contents = await file.read()
        image = Image.open(BytesIO(contents))

        # Validate image
        validation = image_processor.validate_image(image)
        if not validation['valid']:
            return AnalyzeResponse(
                success=False,
                error=f"Invalid image: {', '.join(validation['errors'])}"
            )

        # Get metadata
        metadata = image_processor.extract_metadata(image)

        # Get prompt
        final_prompt = get_prompt(
            template_name=preset,
            custom_prompt=prompt
        )

        # Initialize vision client with cache
        client_cache = cache_manager if enable_cache else None
        vision_client = VisionClient(
            backend=provider,
            model=model,
            cache_manager=client_cache,
            enable_cache=enable_cache
        )

        # Analyze image
        result = vision_client.analyze(
            prompt=final_prompt,
            images=[image],
            max_tokens=max_tokens,
            temperature=temperature
        )

        # Check if cached
        cached = False
        if enable_cache:
            # This is a simplified check - in production you'd track this better
            cached = False  # Would need to track in vision_client

        return AnalyzeResponse(
            success=True,
            result=result,
            cached=cached,
            metadata={
                "format": metadata['format'],
                "dimensions": metadata['dimensions'],
                "size_mb": metadata['size_mb'],
                "provider": provider,
                "model": model or vision_client.model,
                "preset": preset
            }
        )

    except Exception as e:
        return AnalyzeResponse(
            success=False,
            error=str(e)
        )


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
    try:
        # Read and validate image
        contents = await file.read()
        image = Image.open(BytesIO(contents))

        # Validate image
        validation = image_processor.validate_image(image)
        if not validation['valid']:
            return OCRResponse(
                success=False,
                error=f"Invalid image: {', '.join(validation['errors'])}"
            )

        # Initialize vision client for fallback if needed
        vision_client = None
        if fallback or method == 'vision':
            vision_client = VisionClient(
                backend=provider,
                model=model
            )

        # Initialize OCR processor
        ocr_processor = OCRProcessor(
            use_tesseract=(method != 'vision'),
            vision_client=vision_client
        )

        # Extract text. fallback_to_vision is the only thing that
        # actually gates whether vision runs at all - method='vision'
        # with fallback left unchecked would otherwise silently return
        # an empty result (method: 'none') despite the vision_client
        # above having been constructed specifically to do this.
        result = ocr_processor.extract_text(
            image=image,
            language=language,
            fallback_to_vision=(fallback or method == 'vision'),
            confidence_threshold=confidence
        )

        return OCRResponse(
            success=True,
            text=result['text'],
            confidence=result['confidence'],
            method=result['method'],
            language=result['language'],
            details=result.get('details', {})
        )

    except Exception as e:
        return OCRResponse(
            success=False,
            error=str(e)
        )


@app.post("/api/detect-language")
async def detect_language(
    file: UploadFile = File(...),
    use_vision: bool = Form(False),
    provider: str = Form(os.getenv("DEFAULT_PROVIDER", "ollama")),
    model: Optional[str] = Form(None)
):
    """Detect language in image text."""
    try:
        # Read and validate image
        contents = await file.read()
        image = Image.open(BytesIO(contents))

        # Initialize vision client if needed
        vision_client = None
        if use_vision:
            vision_client = VisionClient(
                backend=provider,
                model=model
            )

        # Initialize OCR processor
        ocr_processor = OCRProcessor(
            use_tesseract=True,
            vision_client=vision_client
        )

        # Detect language
        result = ocr_processor.detect_language(image)

        return {
            "success": True,
            "result": result
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
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
    try:
        # Read and validate images
        contents1 = await file1.read()
        contents2 = await file2.read()
        image1 = Image.open(BytesIO(contents1))
        image2 = Image.open(BytesIO(contents2))

        # Validate images
        validation1 = image_processor.validate_image(image1)
        validation2 = image_processor.validate_image(image2)

        if not validation1['valid']:
            return CompareResponse(
                success=False,
                error=f"Invalid image 1: {', '.join(validation1['errors'])}"
            )
        if not validation2['valid']:
            return CompareResponse(
                success=False,
                error=f"Invalid image 2: {', '.join(validation2['errors'])}"
            )

        # Initialize vision client if needed
        vision_client = None
        if use_ai:
            vision_client = VisionClient(
                backend=provider,
                model=model
            )

        # Initialize comparator
        comparator = ImageComparator(vision_client=vision_client)

        # Compare images
        result = comparator.compare_images(
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

    except Exception as e:
        return CompareResponse(
            success=False,
            error=str(e)
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
    try:
        # Read and validate images
        images = []
        image_names = []

        for file in files:
            try:
                contents = await file.read()
                image = Image.open(BytesIO(contents))

                validation = image_processor.validate_image(image)
                if validation['valid']:
                    images.append(image)
                    image_names.append(file.filename or f"image_{len(images)}")
            except Exception as e:
                # Skip invalid images
                continue

        if not images:
            return BatchResponse(
                success=False,
                error="No valid images provided"
            )

        # Get prompt
        final_prompt = get_prompt(
            template_name=preset,
            custom_prompt=prompt
        )

        # Initialize vision client with cache
        client_cache = cache_manager if enable_cache else None
        vision_client = VisionClient(
            backend=provider,
            model=model,
            cache_manager=client_cache,
            enable_cache=enable_cache
        )

        # Initialize batch processor
        batch_processor = BatchProcessor(
            vision_client=vision_client,
            max_workers=workers
        )

        # Process images
        results = batch_processor.batch_analyze(
            images=images,
            image_names=image_names,
            prompt=final_prompt,
            temperature=temperature,
            max_tokens=max_tokens
        )

        return BatchResponse(
            success=True,
            total_images=results['total_images'],
            successful=results['successful'],
            failed=results['failed'],
            results=results['results'],
            errors=results['errors'],
            elapsed_time=results['elapsed_time']
        )

    except Exception as e:
        return BatchResponse(
            success=False,
            error=str(e)
        )


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
    try:
        # Read and validate images
        images = []
        image_names = []

        for file in files:
            try:
                contents = await file.read()
                image = Image.open(BytesIO(contents))

                validation = image_processor.validate_image(image)
                if validation['valid']:
                    images.append(image)
                    image_names.append(file.filename or f"image_{len(images)}")
            except Exception as e:
                # Skip invalid images
                continue

        if not images:
            return BatchResponse(
                success=False,
                error="No valid images provided"
            )

        # Initialize vision client for fallback if needed
        vision_client = None
        if fallback or method == 'vision':
            vision_client = VisionClient(
                backend=provider,
                model=model
            )

        # Initialize OCR processor
        ocr_processor = OCRProcessor(
            use_tesseract=(method != 'vision'),
            vision_client=vision_client
        )

        # Initialize batch processor
        batch_processor = BatchProcessor(
            ocr_processor=ocr_processor,
            max_workers=workers
        )

        # Process images
        results = batch_processor.batch_ocr(
            images=images,
            image_names=image_names,
            language=language,
            method=method,
            fallback_to_vision=fallback,
            confidence_threshold=confidence
        )

        return BatchResponse(
            success=True,
            total_images=results['total_images'],
            successful=results['successful'],
            failed=results['failed'],
            results=results['results'],
            errors=results['errors'],
            elapsed_time=results['elapsed_time']
        )

    except Exception as e:
        return BatchResponse(
            success=False,
            error=str(e)
        )


if __name__ == "__main__":
    import uvicorn

    print("🚀 Starting Content Analyzer Web Server...")
    print("📊 Access the web interface at: http://localhost:8000")
    print("📚 API docs at: http://localhost:8000/docs")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
