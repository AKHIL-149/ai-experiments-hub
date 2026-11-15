"""Ask questions, follow chains of relations, find paths, and keep the search index up to date"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.database import get_db
from src.models.embedding import Embedding
from src.models.graph import Chunk, Document, Fact
from src.services import ask as ask_service
from src.services import graph_query as gq
from src.services.embedding import EmbeddingError, ensure_chunk_embeddings, ensure_fact_embeddings, get_embedder
from src.services.llm import LLMError, get_llm

router = APIRouter(prefix="/api", tags=["questions"])


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    mode: str = "auto"
    document_id: str | None = None


@router.post("/ask")
def ask(body: AskIn, db: Session = Depends(get_db)):
    if body.mode not in ask_service.MODES:
        raise HTTPException(422, f"mode must be one of: {', '.join(ask_service.MODES)}")
    if body.document_id and db.get(Document, body.document_id) is None:
        raise HTTPException(404, "Document not found")
    settings = get_settings()
    try:
        llm = get_llm(settings)
        embedder = get_embedder(settings)
        result = ask_service.ask(db, body.question, mode=body.mode, llm=llm, embedder=embedder, settings=settings,
                                 document_id=body.document_id)
        db.commit()  # fact vectors made on the way are kept
    except (LLMError, EmbeddingError) as exc:
        db.rollback()
        raise HTTPException(503, str(exc))
    return result


@router.get("/query/link")
def link(q: str = Query(min_length=1), db: Session = Depends(get_db)):
    """Which entities does this text name? (what a question is matched to)"""
    index = gq.GraphIndex(db)
    return {"entities": [{"entity_id": s.entity_id, "name": s.name, "how": s.how, "matched": s.matched,
                          "confidence": s.confidence, "also_could_be": s.alternatives} for s in index.link(q)]}


def _entity(index: gq.GraphIndex, ref: str):
    if ref in index.entities and ref in index.used:
        return ref
    seeds = index.link(ref)
    if not seeds:
        raise HTTPException(404, f"No entity matches '{ref}'")
    return seeds[0].entity_id


@router.get("/query/path")
def path(source: str = Query(alias="from"), target: str = Query(alias="to"), max_hops: int = Query(4, ge=1, le=6),
         limit: int = Query(3, ge=1, le=10), db: Session = Depends(get_db)):
    """The shortest chains of facts between two entities (ids or names); no language model involved"""
    index = gq.GraphIndex(db)
    a, b = _entity(index, source), _entity(index, target)
    chains = index.paths(a, b, max_hops, limit)
    return {"from": index.name(a), "to": index.name(b),
            "paths": [[{"fact_id": f.id, "text": f.text(), "from": index.name(f.s_id), "predicate": f.predicate,
                        "to": f.o_name, "valid_from": f.valid_from or None, "valid_to": f.valid_to or None} for f in chain if f] for chain in chains]}


class StepIn(BaseModel):
    relation: str = Field(min_length=1)
    direction: str = Field(default="out", pattern="^(out|in)$")


class ChainIn(BaseModel):
    start: str = Field(min_length=1)
    steps: list[StepIn] = Field(min_length=1, max_length=6)


@router.post("/query/chain")
def chain(body: ChainIn, db: Session = Depends(get_db)):
    """Follow a chain of relations from an entity: [{relation: 'founded', direction: 'in'}, ...]. No language model involved."""
    settings = get_settings()
    index = gq.GraphIndex(db)
    start = _entity(index, body.start)
    try:
        matcher = gq.PredicateMatcher(get_embedder(settings), [f.predicate for f in index.facts.values()])
        w = gq.walk(index, [start], [s.model_dump() for s in body.steps], matcher, settings.predicate_threshold)
    except EmbeddingError:
        matcher = gq.PredicateMatcher(None, [f.predicate for f in index.facts.values()])
        w = gq.walk(index, [start], [s.model_dump() for s in body.steps], matcher, settings.predicate_threshold)
    return {"start": index.name(start), "ok": w.ok, "reason": w.reason,
            "answers": [index.name(e) for e in w.final_entities] + list(w.final_values),
            "facts": [{"fact_id": f.id, "text": f.text()} for f in w.facts], "steps": ask_service._step_report(index, w)}


@router.get("/index/status")
def index_status(db: Session = Depends(get_db)):
    settings = get_settings()
    model = get_embedder(settings).name
    chunks = db.scalar(select(func.count()).select_from(Chunk)) or 0
    indexed = db.scalar(select(func.count()).select_from(Embedding).where(Embedding.model == model, Embedding.chunk_id.is_not(None))) or 0
    facts = db.scalar(select(func.count()).select_from(Fact)) or 0
    f_indexed = db.scalar(select(func.count()).select_from(Embedding).where(Embedding.model == model, Embedding.fact_id.is_not(None))) or 0
    return {"model": model, "passages": chunks, "passages_indexed": indexed, "facts": facts, "facts_indexed": f_indexed}


@router.post("/index/rebuild")
def index_rebuild(db: Session = Depends(get_db)):
    """Embed every passage and fact that has no vector yet (after a change of embedding model, or for old documents)"""
    from src.services import pipeline
    settings = get_settings()
    if not pipeline._PROCESS_LOCK.acquire(blocking=False):
        raise HTTPException(409, "A document is being read. Try again when it finishes")
    try:
        embedder = get_embedder(settings)
        added_chunks = ensure_chunk_embeddings(db, embedder)
        facts = db.execute(select(Fact)).scalars().all()
        before = db.scalar(select(func.count()).select_from(Embedding).where(Embedding.fact_id.is_not(None), Embedding.model == embedder.name)) or 0
        ensure_fact_embeddings(db, embedder, facts)
        db.commit()
        after = db.scalar(select(func.count()).select_from(Embedding).where(Embedding.fact_id.is_not(None), Embedding.model == embedder.name)) or 0
    except EmbeddingError as exc:
        db.rollback()
        raise HTTPException(503, str(exc))
    finally:
        pipeline._PROCESS_LOCK.release()
    return {"model": embedder.name, "passages_added": added_chunks, "facts_added": after - before}
