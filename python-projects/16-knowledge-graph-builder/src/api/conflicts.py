"""Conflicts between facts, and checking a claim against the documents"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.api.deps import get_owner
from src.core.config import get_settings
from src.core.database import get_db
from src.models.conflict import Conflict, ConflictStatus
from src.models.graph import Document, Fact, FactSource
from src.services import conflicts as cf
from src.services import factcheck, pipeline
from src.services.embedding import get_embedder
from src.services.llm import LLMError, get_llm

router = APIRouter(prefix="/api", tags=["conflicts"])


def _fact(db: Session, fact_id: str) -> dict | None:
    f = db.get(Fact, fact_id)
    if f is None:
        return None
    src = db.execute(select(FactSource, Document.title).join(Document, Document.id == FactSource.document_id)
                     .where(FactSource.fact_id == f.id)).all()
    return {"id": f.id, "text": f"{f.subject.name} {f.predicate} {f.object.name if f.object else f.object_value}",
            "subject": f.subject.name, "predicate": f.predicate, "object": f.object.name if f.object else f.object_value,
            "valid_from": f.valid_from or None, "valid_to": f.valid_to or None,
            "sources": [{"document_title": title, "quote": s.evidence, "verified": s.verified} for s, title in src[:3]]}


def _conflict(db: Session, c: Conflict) -> dict:
    a, b = db.get(Fact, c.fact_a_id), db.get(Fact, c.fact_b_id)
    return {"id": c.id, "kind": c.kind, "severity": c.severity, "reasons": c.reasons, "llm_verdict": c.llm_verdict,
            "status": c.status.value, "resolution": c.resolution, "a": _fact(db, c.fact_a_id), "b": _fact(db, c.fact_b_id),
            "can_end_earlier": bool(a and b and cf.succession_order(a, b)),
            "decided_at": c.decided_at.isoformat() if c.decided_at else None}


class _Writer:
    """Settling a conflict changes facts, so it must not overlap with one of this person's documents being read"""

    def __init__(self, owner: int | None):
        self.lock = pipeline.owner_lock(owner)

    def __enter__(self):
        if not self.lock.acquire(blocking=False):
            raise HTTPException(409, "A document is being read. Try again when it finishes")
        return self

    def __exit__(self, *exc):
        self.lock.release()


class RunIn(BaseModel):
    use_llm: bool = False


@router.post("/conflicts/run")
def run(body: RunIn | None = None, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    """Look for facts that cannot both be true. With use_llm the model classifies unfamiliar relation words (once each) and gives an opinion on each new pair."""
    body = body or RunIn()
    llm = None
    if body.use_llm:
        try:
            llm = get_llm(get_settings())
        except LLMError as exc:
            raise HTTPException(503, str(exc))
    with _Writer(owner):
        summary = cf.run_detection(db, owner_id=owner, llm=llm, judge=body.use_llm)
        db.commit()
    return summary.as_dict()


@router.get("/conflicts")
def list_conflicts(status: str = "open", db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    try:
        st = ConflictStatus(status)
    except ValueError:
        raise HTTPException(422, "status must be open, resolved or dismissed")
    rows = db.execute(select(Conflict).where(Conflict.owner_id == owner, Conflict.status == st).order_by(Conflict.severity, Conflict.created_at)).scalars().all()
    return {"conflicts": [_conflict(db, c) for c in rows]}


class ResolveIn(BaseModel):
    resolution: str


@router.post("/conflicts/{conflict_id}/resolve")
def resolve(conflict_id: str, body: ResolveIn, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    with _Writer(owner):
        try:
            c = cf.resolve(db, conflict_id, body.resolution, owner_id=owner)
            db.commit()
        except cf.ConflictError as exc:
            db.rollback()
            raise HTTPException(404 if "not found" in str(exc) else 409 if "already" in str(exc) else 422, str(exc))
    return _conflict(db, c)


@router.post("/conflicts/{conflict_id}/reopen")
def reopen(conflict_id: str, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    with _Writer(owner):
        try:
            c = cf.reopen(db, conflict_id, owner_id=owner)
            db.commit()
        except cf.ConflictError as exc:
            db.rollback()
            raise HTTPException(404 if "not found" in str(exc) else 409, str(exc))
    return _conflict(db, c)


class CheckIn(BaseModel):
    claim: str = Field(min_length=5, max_length=500)


@router.post("/check")
def check(body: CheckIn, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    """Is this claim supported, contradicted, or not stated in your documents? The model only reads the claim; code checks it."""
    settings = get_settings()
    try:
        llm = get_llm(settings)
        result = factcheck.check(db, body.claim.strip(), llm=llm, embedder=get_embedder(settings), settings=settings, owner_id=owner)
    except LLMError as exc:
        db.rollback()
        raise HTTPException(503, str(exc))
    return result
