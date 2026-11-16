"""Knowledge Graph Builder - API server"""
import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from src.api import auth as auth_api
from src.api import documents, graph, query, resolution
from src.core.auth import current_caller
from src.core.config import get_settings
from src.core.database import init_db
from src.core.login_gate import LoginGateMiddleware
from src.services.llm import llm_status
from src.services.pipeline import recover_interrupted

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kg")

GUEST_CLEANUP_SECONDS = 3600


async def _guest_cleanup_loop():
    while True:
        try:
            n = await asyncio.to_thread(auth_api.cleanup_expired_guests)
            if n:
                log.info("Removed %d expired guest account(s) and their data", n)
        except Exception:
            log.exception("Guest cleanup failed")
        await asyncio.sleep(GUEST_CLEANUP_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    n = recover_interrupted()
    if n:
        log.warning("%d document(s) were interrupted by the last shutdown and are marked failed", n)
    cleanup = asyncio.create_task(_guest_cleanup_loop())
    try:
        yield
    finally:
        cleanup.cancel()


app = FastAPI(title="Knowledge Graph Builder", version="0.2.0", lifespan=lifespan)
app.add_middleware(LoginGateMiddleware)
app.include_router(auth_api.router)
app.include_router(documents.router)
app.include_router(graph.router)
app.include_router(resolution.router)
app.include_router(query.router)


@app.get("/api/health")
def health():
    """Public: says the server is up. The model's state is shown to signed-in callers only."""
    out = {"status": "ok"}
    if current_caller() is not None:
        out["llm"] = llm_status()
    return out


if __name__ == "__main__":
    s = get_settings()
    uvicorn.run("server:app", host=s.api_host, port=s.api_port, reload=s.debug)
