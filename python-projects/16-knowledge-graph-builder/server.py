"""Knowledge Graph Builder - API server"""
import asyncio
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from src.api import auth as auth_api
from src.api import conflicts as conflicts_api
from src.api import documents, graph, jobs, query, resolution
from src.core.auth import current_caller
from src.core.config import get_settings
from src.core.database import init_db
from src.core.login_gate import LoginGateMiddleware
from src.services.llm import llm_status
from src.services import job_queue
from src.web import mount_frontend

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kg")

GUEST_CLEANUP_SECONDS = 3600


async def _guest_cleanup_loop():
    while True:
        try:
            n = await asyncio.to_thread(auth_api.cleanup_expired_guests)
            if n:
                log.info("Removed %d expired guest account(s) and their data", n)
            old = await asyncio.to_thread(job_queue.purge_old_jobs)
            if old:
                log.info("Forgot %d finished job(s) older than 30 days", old)
        except Exception:
            log.exception("Guest cleanup failed")
        await asyncio.sleep(GUEST_CLEANUP_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    recovered = job_queue.recover_orphans()
    if any(recovered.values()):
        log.warning("Recovered after the last shutdown: %s", recovered)
    if get_settings().job_workers_enabled:
        job_queue.start()
    cleanup = asyncio.create_task(_guest_cleanup_loop())
    try:
        yield
    finally:
        cleanup.cancel()
        await asyncio.to_thread(job_queue.stop)


app = FastAPI(title="Knowledge Graph Builder", version="0.3.0", lifespan=lifespan)
app.add_middleware(LoginGateMiddleware)
app.include_router(auth_api.router)
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(graph.router)
app.include_router(resolution.router)
app.include_router(conflicts_api.router)
app.include_router(query.router)


@app.get("/api/health")
def health():
    """Public: says the server is up. The model's state is shown to signed-in callers only."""
    out = {"status": "ok"}
    if current_caller() is not None:
        out["llm"] = llm_status()
    return out


mount_frontend(app)   # last: its catch-all route must come after every API route


if __name__ == "__main__":
    s = get_settings()
    uvicorn.run("server:app", host=s.api_host, port=s.api_port, reload=s.debug)
