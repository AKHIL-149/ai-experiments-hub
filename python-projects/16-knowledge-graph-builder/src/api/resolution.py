"""Entity resolution: run it, review the suggestions, merge by hand, undo"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from src.core.config import get_settings
from src.core.database import get_db
from src.models.graph import Entity, Fact
from src.models.resolution import EntityAlias, MergeRecord, MergeSuggestion, SuggestionStatus
from src.services import pipeline, resolution
from src.services.llm import LLMError, get_llm

router = APIRouter(prefix="/api", tags=["resolution"])


def _entity_summary(db: Session, entity_id: str) -> dict | None:
    e = db.get(Entity, entity_id)
    if e is None:
        return None
    facts = db.execute(select(Fact).where(or_(Fact.subject_id == e.id, Fact.object_id == e.id)).limit(3)).scalars().all()
    count = db.scalar(select(func.count()).select_from(Fact).where(or_(Fact.subject_id == e.id, Fact.object_id == e.id)))
    aliases = db.execute(select(EntityAlias.name).where(EntityAlias.entity_id == e.id)).scalars().all()
    return {"id": e.id, "name": e.name, "type": e.type, "fact_count": count, "aliases": list(aliases),
            "sample_facts": [f"{f.subject.name} {f.predicate} {f.object.name if f.object else f.object_value}" for f in facts]}


def _suggestion(db: Session, s: MergeSuggestion) -> dict:
    return {"id": s.id, "score": s.score, "reasons": s.reasons, "llm_verdict": s.llm_verdict, "status": s.status.value,
            "a": _entity_summary(db, s.entity_a_id), "b": _entity_summary(db, s.entity_b_id)}


def _record(r: MergeRecord) -> dict:
    return {"id": r.id, "kept": r.keep_name, "keep_id": r.keep_id, "absorbed": r.absorbed_name, "how": r.how,
            "reasons": r.reasons, "created_at": r.created_at.isoformat(), "undone": r.undone_at is not None}


class _Writer:
    """Merges and undos change entities and facts, so they must not overlap with a document being read"""

    def __enter__(self):
        if not pipeline._PROCESS_LOCK.acquire(blocking=False):
            raise HTTPException(409, "A document is being read. Try again when it finishes")
        return self

    def __exit__(self, *exc):
        pipeline._PROCESS_LOCK.release()


class RunIn(BaseModel):
    use_llm: bool | None = None
    auto: bool = True


@router.post("/resolution/run")
def run(body: RunIn | None = None, db: Session = Depends(get_db)):
    body = body or RunIn()
    settings = get_settings()
    use_llm = settings.resolution_use_llm if body.use_llm is None else body.use_llm
    llm = None
    if use_llm:
        try:
            llm = get_llm(settings)
        except LLMError as exc:
            raise HTTPException(503, str(exc))
    with _Writer():
        summary = resolution.run_resolution(db, auto=body.auto, llm=llm)
        db.commit()
    return summary.as_dict()


@router.get("/resolution/suggestions")
def suggestions(status: str = "pending", db: Session = Depends(get_db)):
    try:
        st = SuggestionStatus(status)
    except ValueError:
        raise HTTPException(422, "status must be pending, accepted or rejected")
    rows = db.execute(select(MergeSuggestion).where(MergeSuggestion.status == st).order_by(MergeSuggestion.score.desc())).scalars().all()
    return {"suggestions": [_suggestion(db, s) for s in rows]}


class AcceptIn(BaseModel):
    keep_id: str | None = None


@router.post("/resolution/suggestions/{suggestion_id}/accept")
def accept(suggestion_id: str, body: AcceptIn | None = None, db: Session = Depends(get_db)):
    with _Writer():
        try:
            rec = resolution.accept_suggestion(db, suggestion_id, body.keep_id if body else None)
            db.commit()
        except resolution.MergeError as exc:
            db.rollback()
            raise HTTPException(404 if "not found" in str(exc) else 409, str(exc))
    return _record(rec)


@router.post("/resolution/suggestions/{suggestion_id}/reject", status_code=204)
def reject(suggestion_id: str, db: Session = Depends(get_db)):
    with _Writer():
        try:
            resolution.reject_suggestion(db, suggestion_id)
            db.commit()
        except resolution.MergeError as exc:
            db.rollback()
            raise HTTPException(404 if "not found" in str(exc) else 409, str(exc))


class MergeIn(BaseModel):
    keep_id: str
    absorb_id: str


@router.post("/entities/merge")
def merge(body: MergeIn, db: Session = Depends(get_db)):
    with _Writer():
        try:
            rec = resolution.merge_entities(db, body.keep_id, body.absorb_id, "manual")
            db.commit()
        except resolution.MergeError as exc:
            db.rollback()
            raise HTTPException(404 if "not found" in str(exc) else 409, str(exc))
    return _record(rec)


@router.get("/resolution/merges")
def merges(include_undone: bool = False, db: Session = Depends(get_db)):
    q = select(MergeRecord).order_by(MergeRecord.created_at.desc())
    if not include_undone:
        q = q.where(MergeRecord.undone_at.is_(None))
    return {"merges": [_record(r) for r in db.execute(q).scalars()]}


@router.post("/resolution/merges/{record_id}/undo")
def undo(record_id: str, db: Session = Depends(get_db)):
    with _Writer():
        try:
            rec = resolution.undo_merge(db, record_id)
            db.commit()
        except resolution.MergeError as exc:
            db.rollback()
            raise HTTPException(404 if "not found" in str(exc) else 409, str(exc))
    return _record(rec)
