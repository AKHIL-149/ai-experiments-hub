"""FastAPI application for code documentation generator web interface"""
import html
import os
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from fastapi import FastAPI, Request, Form
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
from src.version import __version__
from .sanitize import sanitize_html


# Utility function for markdown to HTML conversion
def markdown_to_html(markdown_text: str) -> str:
    """
    Convert markdown text to HTML that is safe to show in the page.

    Raw HTML in the markdown (for instance inside a docstring) is not passed through, and the
    result is cleaned with an allowlist sanitizer, because the text comes from user code.
    """
    try:
        import markdown
    except ImportError:
        markdown = None

    if markdown is not None:
        md = markdown.Markdown(extensions=['extra', 'codehilite', 'toc', 'tables'])
        # treat "<script>" typed in the source as text, not as HTML
        md.preprocessors.deregister('html_block')
        md.inlinePatterns.deregister('html')
        return sanitize_html(md.convert(markdown_text or ''))

    # Fallback without the library: escape first, then apply a few simple rules
    import re
    from html import escape
    html = escape(markdown_text or '', quote=False)
    html = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    html = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
    html = re.sub(r'`(.+?)`', r'<code>\1</code>', html)
    html = re.sub(r'\[(.+?)\]\((.+?)\)', r'<a href="\2">\1</a>', html)
    html = re.sub(r'\n\n', r'</p><p>', html)
    return sanitize_html('<p>' + html + '</p>')

# Initialize FastAPI app
if FASTAPI_AVAILABLE:
    app = FastAPI(
        title="Code Documentation Generator",
        description="AI-powered code documentation generator with multi-language support",
        version=__version__,
        docs_url="/api/docs",
        redoc_url="/api/redoc"
    )

    # The page and the API are served from the same origin, so no cross-origin access is needed.
    # Set CORS_ORIGINS="https://a.example,https://b.example" to allow specific other origins.
    allowed_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip() and o.strip() != "*"]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["*"],
        )

    # Templates directory
    templates_dir = Path(__file__).parent / "templates"
    templates_dir.mkdir(exist_ok=True)
    templates = Jinja2Templates(directory=str(templates_dir))

    def static_version() -> str:
        """Changes whenever a static file changes, so browsers do not keep serving an old script"""
        try:
            return str(int(max(f.stat().st_mtime for f in static_dir.rglob("*") if f.is_file())))
        except ValueError:
            return __version__
    templates.env.globals["static_version"] = static_version

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
                request,
                "index.html",
                {"title": "Code Documentation Generator"}
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
                        <p>Error: {html.escape(str(e))}</p>
                    </body>
                </html>
                """
            )

    @app.post("/results", response_class=HTMLResponse)
    async def show_results(
        request: Request,
        code: str = Form(...),
        documentation: str = Form(...),
        raw_documentation: str = Form(""),
        format: str = Form("markdown"),
        language: str = Form("python"),
        ai_enhanced: bool = Form(False),
        stats: str = Form("{}"),
        metadata: str = Form("{}"),
        warnings: str = Form("[]")
    ):
        """Display documentation results page"""
        import json

        # Parse JSON fields
        try:
            stats_data = json.loads(stats) if stats else {}
        except ValueError:
            stats_data = {}

        try:
            metadata_data = json.loads(metadata) if metadata else {}
        except ValueError:
            metadata_data = {}

        try:
            warnings_data = [str(w) for w in json.loads(warnings)] if warnings else []
        except (ValueError, TypeError):
            warnings_data = []

        # Markdown is converted to cleaned HTML. HTML output is shown in a sandboxed frame and
        # everything else as escaped text, so nothing from the form is ever trusted as markup.
        doc_html = documentation
        if format == "markdown":
            doc_html = markdown_to_html(documentation)

        return templates.TemplateResponse(
            request,
            "result.html",
            {
                "code": code,
                "documentation": doc_html,
                "raw_documentation": raw_documentation or documentation,
                "format": format,
                "language": language,
                "ai_enhanced": ai_enhanced,
                "stats": stats_data,
                "metadata": metadata_data,
                "warnings": warnings_data
            }
        )

    @app.on_event("startup")
    async def startup_event():
        """Run on application startup"""
        print(f"🚀 Code Documentation Generator Web Interface v{__version__}")

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
