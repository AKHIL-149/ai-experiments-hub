#!/usr/bin/env python3
"""FastAPI server for Content Analyzer web interface."""
import sys
import os
import base64
from pathlib import Path
from typing import Optional, List
from io import BytesIO

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

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

# Initialize FastAPI app
app = FastAPI(
    title="Content Analyzer API",
    description="Vision AI image analysis with OCR capabilities",
    version="0.7.5"
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


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main HTML page."""
    html_file = project_root / "templates" / "index.html"
    if html_file.exists():
        return html_file.read_text()
    return HTMLResponse(content="<h1>Content Analyzer</h1><p>Frontend not found. Please check templates/index.html</p>")


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.7.5"}


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
    provider: str = Form("anthropic"),
    model: Optional[str] = Form(None),
    temperature: float = Form(0.7),
    max_tokens: int = Form(1000),
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
    provider: str = Form("anthropic"),
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

        # Extract text
        result = ocr_processor.extract_text(
            image=image,
            language=language,
            fallback_to_vision=fallback,
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
    provider: str = Form("anthropic"),
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
