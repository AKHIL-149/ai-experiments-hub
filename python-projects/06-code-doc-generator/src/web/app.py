"""FastAPI application for code documentation generator web interface"""
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from fastapi import FastAPI, Request
    from fastapi.staticfiles import StaticFiles
    from fastapi.templating import Jinja2Templates
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse
    import uvicorn
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    FastAPI = None
    print("Warning: FastAPI not installed. Install with: pip install fastapi uvicorn")

from src.core import DocGenerator

# Initialize FastAPI app
if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="Code Documentation Generator",
        description="AI-powered code documentation generator with multi-language support",
        version="0.7.2",
        docs_url="/api/docs",
        redoc_url="/api/redoc"
    )

    # CORS middleware - allow all origins for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Templates directory
    templates_dir = Path(__file__).parent / "templates"
    templates_dir.mkdir(exist_ok=True)
    templates = Jinja2Templates(directory=str(templates_dir))

    # Static files directory
    static_dir = Path(__file__).parent / "static"
    static_dir.mkdir(exist_ok=True)
    
    # Mount static files (will be created in later version)
    try:
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    except RuntimeError:
        # Directory might not have files yet
        pass

    # Import routes
    from .routes import router
    app.include_router(router)

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Root endpoint - main web interface"""
        try:
            return templates.TemplateResponse(
                "index.html",
                {"request": request, "title": "Code Documentation Generator"}
            )
        except Exception as e:
            # If template doesn't exist yet, return placeholder
            return HTMLResponse(
                content=f"""
                <html>
                    <head><title>Code Documentation Generator</title></head>
                    <body>
                        <h1>Code Documentation Generator - Web Interface</h1>
                        <p>Template files are being set up...</p>
                        <p>API is available at <a href="/api/docs">/api/docs</a></p>
                        <p>Error: {str(e)}</p>
                    </body>
                </html>
                """
            )

    @app.on_event("startup")
    async def startup_event():
        """Run on application startup"""
        print("🚀 Code Documentation Generator Web Interface")
        print("📚 API Documentation: http://127.0.0.1:8000/api/docs")
        print("🌐 Web Interface: http://127.0.0.1:8000/")

    @app.on_event("shutdown")
    async def shutdown_event():
        """Run on application shutdown"""
        print("\n👋 Shutting down Code Documentation Generator")

else:
    # Dummy app if FastAPI not available
    app = None


def start_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    reload: bool = False,
    log_level: str = "info"
):
    """
    Start the web server.
    
    Args:
        host: Host to bind to
        port: Port to bind to
        reload: Enable auto-reload for development
        log_level: Logging level (debug, info, warning, error)
    """
    if not FASTAPI_AVAILABLE:
        print("❌ Error: FastAPI is not installed")
        print("   Install with: pip install 'fastapi>=0.109.0' 'uvicorn>=0.27.0'")
        print("   Or: pip install -e '.[web]'")
        return 1

    try:
        print(f"\n🌐 Starting server on http://{host}:{port}")
        print(f"📖 Press Ctrl+C to stop the server\n")
        
        uvicorn.run(
            "src.web.app:app",
            host=host,
            port=port,
            reload=reload,
            log_level=log_level,
            access_log=True
        )
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Server stopped by user")
        return 0
    except Exception as e:
        print(f"\n❌ Server error: {str(e)}")
        return 1


if __name__ == "__main__":
    # Run server directly
    start_server(reload=True, log_level="debug")
