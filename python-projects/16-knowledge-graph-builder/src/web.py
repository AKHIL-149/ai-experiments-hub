"""Serving the built frontend (frontend/dist) from the same server as the API, so the sign-in cookie is same-origin.

* `/assets/*` are the hashed files Vite built (cached for a year: the name changes when the content does).
* Every other path that is not `/api/*`, `/assets/*`, `/docs`, `/redoc` or `/openapi.json` answers `index.html`, so a reload on
  `#/graph` or a bookmarked address works (the app routes by the #fragment).
* The app page gets a strict Content-Security-Policy: scripts only from this server, no inline script, no framing.
"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; "
       "font-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
PAGE_HEADERS = {"Content-Security-Policy": CSP, "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
                "Referrer-Policy": "same-origin", "Cache-Control": "no-cache"}
RESERVED = ("api", "docs", "redoc", "openapi.json", "assets")   # never answered with the page: a script that got HTML back would only confuse

NOT_BUILT = """<!doctype html><meta charset="utf-8"><title>Knowledge Graph</title>
<body style="font:16px system-ui;max-width:42rem;margin:3rem auto;padding:0 1rem">
<h1>The web app is not built yet</h1>
<p>The API is running (see <a href="/docs">/docs</a>). To build the web app:</p>
<pre>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</pre></body>"""


def mount_frontend(app: FastAPI, dist: Path | None = None) -> None:
    dist = dist or DIST
    index = dist / "index.html"
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.middleware("http")
    async def asset_headers(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/", include_in_schema=False)
    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str = ""):
        first = path.split("/", 1)[0]
        if first in RESERVED:
            raise HTTPException(404, "Not found")
        if not index.is_file():
            return HTMLResponse(NOT_BUILT, status_code=503, headers=PAGE_HEADERS)
        return FileResponse(index, headers=PAGE_HEADERS)
