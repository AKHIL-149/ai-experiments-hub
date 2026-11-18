"""Browse the stored graph: entities, facts, neighbourhoods and the quotes behind each fact"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_owner
from src.core.database import get_db
from src.models.graph import ENTITY_TYPES, Chunk, Document, Entity, Fact, FactSource
from src.models.resolution import EntityAlias
from src.services import graph_store, temporal
from src.services.conflicts import open_conflicts_for, overruled_ids

router = APIRouter(prefix="/api", tags=["graph"])


def _check_type(entity_type: str | None) -> None:
    if entity_type and entity_type not in ENTITY_TYPES:
        raise HTTPException(422, f"Unknown entity type. Use one of: {', '.join(ENTITY_TYPES)}")


def _window(at: str | None, start: str | None, end: str | None):
    """The period named by ?at= or ?from=&to= (None when neither is given)"""
    try:
        return temporal.window_from_params(at, start, end)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


def _entity(e: Entity) -> dict:
    return {"id": e.id, "name": e.name, "type": e.type}


@router.get("/graph")
def get_graph(document_id: str | None = None, type: str | None = None, limit: int = Query(300, ge=1, le=2000),
              at: str | None = None, start: str | None = Query(None, alias="from"), end: str | None = Query(None, alias="to"),
              db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    """With ?at=2021 (or 2021-03, 2021-03-15, now) or ?from=2015&to=2018 every fact says what its dates say about that period (`time`)"""
    _check_type(type)
    window = _window(at, start, end)
    if document_id:
        doc = db.get(Document, document_id)
        if doc is None or doc.owner_id != owner:
            raise HTTPException(404, "Document not found")
    return graph_store.graph_payload(graph_store.build_graph(db, document_id, type, owner_id=owner), limit, window)


@router.get("/graph/stats")
def get_stats(db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    return graph_store.stats(db, owner_id=owner)


@router.get("/entities")
def list_entities(q: str = "", type: str | None = None, limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
                  owner: int | None = Depends(get_owner)):
    _check_type(type)
    return {"entities": [_entity(e) for e in graph_store.search_entities(db, q, type, limit, owner_id=owner)]}


@router.get("/entities/{entity_id}")
def get_entity(entity_id: str, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    e = db.get(Entity, entity_id)
    if e is None or e.owner_id != owner:
        raise HTTPException(404, "Entity not found")
    left_out = overruled_ids(db, owner)
    out = [f for f in db.execute(select(Fact).where(Fact.subject_id == e.id).order_by(Fact.predicate)).scalars().all() if f.id not in left_out]
    inc = [f for f in db.execute(select(Fact).where(Fact.object_id == e.id).order_by(Fact.predicate)).scalars().all() if f.id not in left_out]
    aliases = db.execute(select(EntityAlias.name).where(EntityAlias.entity_id == e.id).order_by(EntityAlias.name)).scalars().all()
    return {**_entity(e), "aliases": list(aliases), "outgoing": [graph_store.fact_to_dict(f) for f in out],
            "incoming": [graph_store.fact_to_dict(f) for f in inc]}


@router.get("/entities/{entity_id}/neighborhood")
def get_neighborhood(entity_id: str, depth: int = Query(1, ge=1, le=3), limit: int = Query(200, ge=1, le=1000),
                     at: str | None = None, start: str | None = Query(None, alias="from"), end: str | None = Query(None, alias="to"),
                     db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    window = _window(at, start, end)
    e = db.get(Entity, entity_id)
    if e is None or e.owner_id != owner:
        raise HTTPException(404, "Entity not found")
    g = graph_store.neighborhood(graph_store.build_graph(db, owner_id=owner), entity_id, depth)
    return graph_store.graph_payload(g, limit, window)


@router.get("/facts/{fact_id}")
def get_fact(fact_id: str, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    f = db.get(Fact, fact_id)
    if f is None or f.owner_id != owner:
        raise HTTPException(404, "Fact not found")
    rows = db.execute(select(FactSource, Document.title, Chunk.text).join(Document, Document.id == FactSource.document_id)
                      .join(Chunk, Chunk.id == FactSource.chunk_id).where(FactSource.fact_id == f.id)).all()
    sources = [{"document_id": s.document_id, "document_title": title, "chunk_id": s.chunk_id, "quote": s.evidence,
                "passage": passage, "verified": s.verified} for s, title, passage in rows]
    clashes = []
    for c in open_conflicts_for(db, [f.id], owner):
        other = db.get(Fact, c.fact_b_id if c.fact_a_id == f.id else c.fact_a_id)
        if other is not None:
            clashes.append({"id": c.id, "kind": c.kind, "severity": c.severity,
                            "other": {"id": other.id, "text": f"{other.subject.name} {other.predicate} {other.object.name if other.object else other.object_value}",
                                      "valid_from": other.valid_from or None, "valid_to": other.valid_to or None}})
    return {**graph_store.fact_to_dict(f, len(sources)), "sources": sources, "conflicts": clashes,
            "left_out": f.id in overruled_ids(db, owner)}


@router.get("/entities/{entity_id}/timeline")
def get_timeline(entity_id: str, at: str | None = None, start: str | None = Query(None, alias="from"), end: str | None = Query(None, alias="to"),
                 db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    """Every fact about an entity in time order (by start, then end; undated ones last). With a period, each says what its dates
    say about it. Nothing is guessed: a fact without a stated end has none here."""
    window = _window(at, start, end)
    e = db.get(Entity, entity_id)
    if e is None or e.owner_id != owner:
        raise HTTPException(404, "Entity not found")
    left_out = overruled_ids(db, owner)
    facts = [f for f in db.execute(select(Fact).where((Fact.subject_id == e.id) | (Fact.object_id == e.id))).scalars().all() if f.id not in left_out]
    rows = []
    for f in facts:
        d = graph_store.fact_to_dict(f)
        d["direction"] = "out" if f.subject_id == e.id else "in"
        if window:
            d["time"] = temporal.classify(f.valid_from, f.valid_to, window)
        rows.append(d)
    undated = lambda d: not (d["valid_from"] or d["valid_to"])  # noqa: E731
    rows.sort(key=lambda d: (undated(d), d["valid_from"] or d["valid_to"] or "", d["valid_to"] or "9999", d["predicate"], d["id"]))
    out = {"entity": _entity(e), "facts": rows}
    if window:
        out["window"] = window.to_dict()
    return out
