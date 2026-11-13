"""Browse the stored graph: entities, facts, neighbourhoods and the quotes behind each fact"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.database import get_db
from src.models.graph import ENTITY_TYPES, Chunk, Document, Entity, Fact, FactSource
from src.models.resolution import EntityAlias
from src.services import graph_store

router = APIRouter(prefix="/api", tags=["graph"])


def _check_type(entity_type: str | None) -> None:
    if entity_type and entity_type not in ENTITY_TYPES:
        raise HTTPException(422, f"Unknown entity type. Use one of: {', '.join(ENTITY_TYPES)}")


def _entity(e: Entity) -> dict:
    return {"id": e.id, "name": e.name, "type": e.type}


@router.get("/graph")
def get_graph(document_id: str | None = None, type: str | None = None, limit: int = Query(300, ge=1, le=2000),
              db: Session = Depends(get_db)):
    _check_type(type)
    if document_id and db.get(Document, document_id) is None:
        raise HTTPException(404, "Document not found")
    return graph_store.graph_payload(graph_store.build_graph(db, document_id, type), limit)


@router.get("/graph/stats")
def get_stats(db: Session = Depends(get_db)):
    return graph_store.stats(db)


@router.get("/entities")
def list_entities(q: str = "", type: str | None = None, limit: int = Query(50, ge=1, le=500), db: Session = Depends(get_db)):
    _check_type(type)
    return {"entities": [_entity(e) for e in graph_store.search_entities(db, q, type, limit)]}


@router.get("/entities/{entity_id}")
def get_entity(entity_id: str, db: Session = Depends(get_db)):
    e = db.get(Entity, entity_id)
    if e is None:
        raise HTTPException(404, "Entity not found")
    out = db.execute(select(Fact).where(Fact.subject_id == e.id).order_by(Fact.predicate)).scalars().all()
    inc = db.execute(select(Fact).where(Fact.object_id == e.id).order_by(Fact.predicate)).scalars().all()
    aliases = db.execute(select(EntityAlias.name).where(EntityAlias.entity_id == e.id).order_by(EntityAlias.name)).scalars().all()
    return {**_entity(e), "aliases": list(aliases), "outgoing": [graph_store.fact_to_dict(f) for f in out],
            "incoming": [graph_store.fact_to_dict(f) for f in inc]}


@router.get("/entities/{entity_id}/neighborhood")
def get_neighborhood(entity_id: str, depth: int = Query(1, ge=1, le=3), limit: int = Query(200, ge=1, le=1000),
                     db: Session = Depends(get_db)):
    if db.get(Entity, entity_id) is None:
        raise HTTPException(404, "Entity not found")
    g = graph_store.neighborhood(graph_store.build_graph(db), entity_id, depth)
    return graph_store.graph_payload(g, limit)


@router.get("/facts/{fact_id}")
def get_fact(fact_id: str, db: Session = Depends(get_db)):
    f = db.get(Fact, fact_id)
    if f is None:
        raise HTTPException(404, "Fact not found")
    rows = db.execute(select(FactSource, Document.title, Chunk.text).join(Document, Document.id == FactSource.document_id)
                      .join(Chunk, Chunk.id == FactSource.chunk_id).where(FactSource.fact_id == f.id)).all()
    sources = [{"document_id": s.document_id, "document_title": title, "chunk_id": s.chunk_id, "quote": s.evidence,
                "passage": passage, "verified": s.verified} for s, title, passage in rows]
    return {**graph_store.fact_to_dict(f, len(sources)), "sources": sources}
