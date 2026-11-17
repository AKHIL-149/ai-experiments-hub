"""Ask questions, follow chains of relations, find paths, and keep the search index up to date"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.deps import get_owner
from src.core.config import get_settings
from src.core.database import get_db
from src.models.embedding import Embedding
from src.models.graph import Chunk, Document, Fact
from src.services import ask as ask_service
from src.services import temporal
from src.services import graph_query as gq
from src.services.embedding import EmbeddingError, ensure_chunk_embeddings, ensure_fact_embeddings, get_embedder
from src.services.llm import LLMError, get_llm

router = APIRouter(prefix="/api", tags=["questions"])


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    mode: str = "auto"
    document_id: str | None = None


@router.post("/ask")
def ask(body: AskIn, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    if body.mode not in ask_service.MODES:
        raise HTTPException(422, f"mode must be one of: {', '.join(ask_service.MODES)}")
    if body.document_id:
        doc = db.get(Document, body.document_id)
        if doc is None or doc.owner_id != owner:
            raise HTTPException(404, "Document not found")
    settings = get_settings()
    try:
        llm = get_llm(settings)
        embedder = get_embedder(settings)
        result = ask_service.ask(db, body.question, mode=body.mode, llm=llm, embedder=embedder, settings=settings,
                                 document_id=body.document_id, owner_id=owner)
        db.commit()  # fact vectors made on the way are kept
    except (LLMError, EmbeddingError) as exc:
        db.rollback()
        raise HTTPException(503, str(exc))
    return result


@router.get("/query/link")
def link(q: str = Query(min_length=1), db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    """Which entities does this text name? (what a question is matched to)"""
    index = gq.GraphIndex(db, owner_id=owner)
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
         limit: int = Query(3, ge=1, le=10), db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    """The shortest chains of facts between two entities (ids or names); no language model involved"""
    index = gq.GraphIndex(db, owner_id=owner)
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
def chain(body: ChainIn, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    """Follow a chain of relations from an entity: [{relation: 'founded', direction: 'in'}, ...]. No language model involved."""
    settings = get_settings()
    index = gq.GraphIndex(db, owner_id=owner)
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


@router.get("/query/at")
def at_time(entity: str, at: str | None = None, start: str | None = Query(None, alias="from"), end: str | None = Query(None, alias="to"),
            relation: str | None = None, direction: str = Query("any", pattern="^(any|out|in)$"),
            db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    """"Who was CTO of Acme in 2021?" without a model: the facts about an entity (optionally of one relation) that can have held in a period,
    each with what its dates say (during / overlaps / open / undated), best-founded first. Facts dated outside are only counted."""
    try:
        window = temporal.window_from_params(at, start, end)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    if window is None:
        raise HTTPException(422, "Give a period: at=2021, or from= and to=")
    index = gq.GraphIndex(db, owner_id=owner, window=window)
    eid = _entity(index, entity)
    facts = (index.out.get(eid, []) if direction in ("any", "out") else []) + (index.inn.get(eid, []) if direction in ("any", "in") else [])
    if relation:
        settings = get_settings()
        try:
            matcher = gq.PredicateMatcher(get_embedder(settings), [f.predicate for f in index.facts.values()])
            scores = matcher.scores(relation)
        except EmbeddingError:
            scores = gq.PredicateMatcher(None, [f.predicate for f in index.facts.values()]).scores(relation)
        facts = [f for f in facts if scores.get(f.predicate, 0.0) >= settings.predicate_threshold]
    order = {"during": 0, "overlaps": 1, "open": 2, "undated": 3}
    facts = sorted({f.id: f for f in facts}.values(), key=lambda f: (order.get(f.time, 9), f.valid_from or "9999", f.id))
    left_out = [f.text() for f in index.excluded_facts if eid in (f.s_id, f.o_id) and direction in ("any", "out" if f.s_id == eid else "in")]
    return {"entity": index.name(eid), "window": window.to_dict(),
            "facts": [{"fact_id": f.id, "text": f.text(), "subject": f.s_name, "predicate": f.predicate, "object": f.o_name, "object_id": f.o_id,
                       "valid_from": f.valid_from or None, "valid_to": f.valid_to or None, "time": f.time,
                       "meaning": temporal.describe(f.time, window)} for f in facts],
            "left_out": len(left_out), "left_out_examples": left_out[:5]}


@router.get("/index/status")
def index_status(db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    settings = get_settings()
    model = get_embedder(settings).name
    mine = select(Chunk.id).join(Document, Document.id == Chunk.document_id).where(Document.owner_id == owner)
    chunks = db.scalar(select(func.count()).select_from(Chunk).join(Document, Document.id == Chunk.document_id).where(Document.owner_id == owner)) or 0
    indexed = db.scalar(select(func.count()).select_from(Embedding).where(Embedding.model == model, Embedding.chunk_id.in_(mine))) or 0
    facts = db.scalar(select(func.count()).select_from(Fact).where(Fact.owner_id == owner)) or 0
    f_indexed = db.scalar(select(func.count()).select_from(Embedding).join(Fact, Fact.id == Embedding.fact_id)
                          .where(Embedding.model == model, Fact.owner_id == owner)) or 0
    return {"model": model, "passages": chunks, "passages_indexed": indexed, "facts": facts, "facts_indexed": f_indexed}


@router.post("/index/rebuild")
def index_rebuild(db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    """Embed every passage and fact of yours that has no vector yet (after a change of embedding model, or for old documents)"""
    from src.services import pipeline
    settings = get_settings()
    lock = pipeline.owner_lock(owner)
    if not lock.acquire(blocking=False):
        raise HTTPException(409, "A document is being read. Try again when it finishes")
    try:
        embedder = get_embedder(settings)
        added_chunks = ensure_chunk_embeddings(db, embedder, owner_id=owner)
        facts = db.execute(select(Fact).where(Fact.owner_id == owner)).scalars().all()
        count = lambda: db.scalar(select(func.count()).select_from(Embedding).join(Fact, Fact.id == Embedding.fact_id)  # noqa: E731
                                  .where(Embedding.model == embedder.name, Fact.owner_id == owner)) or 0
        before = count()
        ensure_fact_embeddings(db, embedder, facts)
        db.commit()
        after = count()
    except EmbeddingError as exc:
        db.rollback()
        raise HTTPException(503, str(exc))
    finally:
        lock.release()
    return {"model": embedder.name, "passages_added": added_chunks, "facts_added": after - before}
