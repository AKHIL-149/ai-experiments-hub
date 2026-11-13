"""Knowledge Graph Builder - API server"""
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from src.api import documents, graph
from src.core.config import get_settings
from src.core.database import init_db
from src.services.llm import llm_status
from src.services.pipeline import recover_interrupted

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("kg")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    n = recover_interrupted()
    if n:
        log.warning("%d document(s) were interrupted by the last shutdown and are marked failed", n)
    yield


app = FastAPI(title="Knowledge Graph Builder", version="0.1.0", lifespan=lifespan)
app.include_router(documents.router)
app.include_router(graph.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "llm": llm_status()}


if __name__ == "__main__":
    s = get_settings()
    uvicorn.run("server:app", host=s.api_host, port=s.api_port, reload=s.debug)
