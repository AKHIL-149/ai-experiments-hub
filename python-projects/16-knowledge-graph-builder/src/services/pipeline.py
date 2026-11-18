"""Document -> chunks -> checked facts -> stored graph"""
import logging
import threading
from collections import Counter
from typing import Callable
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.core import database
from src.core.config import Settings, get_settings
from src.models.graph import Chunk, Document, DocumentStatus, Entity, Fact, FactSource
from src.services.cancel import JobCancelled
from src.services.chunker import chunk_text
from src.services.embedding import Embedder, EmbeddingError, ensure_chunk_embeddings, get_embedder
from src.services.extraction import ExtractedFact, extract_chunk
from src.services.llm import LLMClient, LLMError, get_llm
from src.services.conflicts import run_detection
from src.services.resolution import find_by_alias, run_resolution
from src.services.text_utils import entity_key, strip_article

log = logging.getLogger(__name__)

# One document at a time per owner: reading writes that owner's entities and facts, and merges / index rebuilds by the same
# owner wait for it (HTTP 409). Different owners never touch each other's rows, so they do not block each other.
_LOCKS: dict = {}
_LOCKS_GUARD = threading.Lock()


def owner_lock(owner_id) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(owner_id, threading.Lock())


def _now():
    return datetime.now(timezone.utc)


def get_or_create_entity(db: Session, name: str, etype: str, owner_id: int | None = None) -> Entity:
    name = strip_article(" ".join(name.split()))
    key = entity_key(name)
    entity = db.execute(select(Entity).where(Entity.owner_id == owner_id, Entity.key == key)).scalar_one_or_none()
    if entity is None:
        entity = find_by_alias(db, key, owner_id)  # a name that was merged into another entity earlier
    if entity is None:
        entity = Entity(owner_id=owner_id, name=name[:300], key=key[:300], type=etype)
        db.add(entity)
        db.flush()
    elif entity.type == "concept" and etype != "concept":
        entity.type = etype  # a later, more specific type wins over the vague default
    return entity


def store_fact(db: Session, fact: ExtractedFact, document_id: str, chunk_id: str, owner_id: int | None = None) -> tuple[Fact, bool]:
    """Save a checked fact. The same statement found again only adds another source. Returns (fact, is_new)."""
    subject = get_or_create_entity(db, fact.subject, fact.subject_type, owner_id)
    if fact.object_type == "value":
        obj, value = None, " ".join(fact.object.split())[:300]
    else:
        obj, value = get_or_create_entity(db, fact.object, fact.object_type, owner_id), ""
    q = select(Fact).where(
        Fact.subject_id == subject.id, Fact.predicate == fact.predicate, Fact.object_value == value,
        Fact.valid_from == fact.valid_from, Fact.valid_to == fact.valid_to,
        Fact.object_id.is_(None) if obj is None else Fact.object_id == obj.id,
    )
    row = db.execute(q).scalar_one_or_none()
    if row is None:
        # The same statement already stored with different dates: an undated sighting joins the dated fact,
        # and a dated sighting fills in the dates of an undated one. Two different periods stay two facts.
        same = Fact.object_id.is_(None) if obj is None else Fact.object_id == obj.id
        others = db.execute(select(Fact).where(Fact.subject_id == subject.id, Fact.predicate == fact.predicate,
                                                Fact.object_value == value, same)).scalars().all()
        if not (fact.valid_from or fact.valid_to):
            row = others[0] if others else None
        else:
            row = next((o for o in others if not (o.valid_from or o.valid_to)), None)
            if row is not None:
                row.valid_from, row.valid_to = fact.valid_from, fact.valid_to
    is_new = row is None
    if is_new:
        row = Fact(owner_id=owner_id, subject_id=subject.id, predicate=fact.predicate, object_id=obj.id if obj else None,
                   object_value=value, valid_from=fact.valid_from, valid_to=fact.valid_to)
        db.add(row)
        db.flush()
    exists = db.execute(select(FactSource.id).where(
        FactSource.fact_id == row.id, FactSource.chunk_id == chunk_id, FactSource.evidence == fact.evidence)).first()
    if not exists:
        db.add(FactSource(fact_id=row.id, document_id=document_id, chunk_id=chunk_id, evidence=fact.evidence,
                          verified=fact.verified))
        db.flush()  # so a second identical statement in the same batch finds it
    return row, is_new


def prune_orphans(db: Session) -> None:
    """Remove facts nobody reads any more, then entities with no facts"""
    db.execute(delete(Fact).where(~Fact.id.in_(select(FactSource.fact_id))))
    used = select(Fact.subject_id).union(select(Fact.object_id).where(Fact.object_id.is_not(None)))
    db.execute(delete(Entity).where(~Entity.id.in_(used)))


def delete_document(db: Session, doc: Document) -> None:
    db.delete(doc)
    db.flush()
    prune_orphans(db)


def clear_analysis(db: Session, doc: Document) -> None:
    """Forget what was read from this document (before reading it again)"""
    db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    db.flush()
    prune_orphans(db)
    doc.chunk_count = doc.chunks_done = 0
    doc.stats = {}
    doc.error = None


def process_document(document_id: str, llm: LLMClient | None = None, settings: Settings | None = None,
                     verify: bool | None = None, checkpoint: Callable[[], None] | None = None) -> str:
    """Read one document into its owner's graph. Never raises: problems end up in the document's status and error.

    `checkpoint` is called between the steps (before every passage); it raises JobCancelled to stop the work. A stopped
    document keeps nothing it had read so far. Returns what happened: completed, failed, cancelled, shutdown, lost,
    deleted or missing."""
    settings = settings or get_settings()
    with database.SessionLocal() as probe:
        doc = probe.get(Document, document_id)
        if doc is None:
            return "missing"
        owner_id = doc.owner_id
    with owner_lock(owner_id):
        db = database.SessionLocal()
        try:
            doc = db.get(Document, document_id)
            if doc is None:
                return "missing"
            return _run(db, doc, llm, settings, settings.verify_facts if verify is None else verify, checkpoint or (lambda: None))
        except JobCancelled as stop:
            db.rollback()
            _undo_partial(db, document_id, stop.reason)
            return stop.reason
        except Exception:  # last resort: never leave a document stuck in "processing"
            log.exception("Unexpected failure while processing document %s", document_id)
            db.rollback()
            _fail(db, document_id, "Unexpected error while reading the document (see the server log)")
            return "failed"
        finally:
            db.close()


def _undo_partial(db: Session, document_id: str, reason: str) -> None:
    """A stopped read leaves nothing behind. A cancelled document is marked as such; one stopped by a shutdown waits to run again."""
    doc = db.get(Document, document_id)
    if doc is None:
        return
    clear_analysis(db, doc)
    if reason == "cancelled":
        doc.status, doc.error, doc.finished_at = DocumentStatus.FAILED, "Cancelled", _now()
    else:
        doc.status, doc.error, doc.finished_at = DocumentStatus.PENDING, None, None
    db.commit()


def _fail(db: Session, document_id: str, message: str) -> None:
    doc = db.get(Document, document_id)
    if doc is not None:
        doc.status, doc.error, doc.finished_at = DocumentStatus.FAILED, message, _now()
        db.commit()


def _run(db: Session, doc: Document, llm: LLMClient | None, settings: Settings, verify: bool, checkpoint: Callable[[], None]) -> str:
    try:
        llm = llm or get_llm(settings)
    except LLMError as exc:
        _fail(db, doc.id, str(exc))
        return "failed"
    checkpoint()
    clear_analysis(db, doc)
    doc.status, doc.model, doc.finished_at = DocumentStatus.PROCESSING, llm.name, None
    chunks = chunk_text(doc.text, settings.chunk_chars, settings.chunk_overlap_chars)
    rows = [Chunk(document_id=doc.id, index=c.index, start=c.start, end=c.end, text=c.text) for c in chunks]
    db.add_all(rows)
    doc.chunk_count = len(rows)
    db.commit()

    totals, rejected, adjusted = Counter(), Counter(), Counter()
    for row in rows:
        checkpoint()
        try:
            result = extract_chunk(llm, row.text, verify, gleaning_passes=settings.gleaning_passes, checkpoint=checkpoint)
        except LLMError as exc:  # model unreachable / timed out / unknown model: stop and say why
            db.rollback()
            _fail(db, doc.id, str(exc))
            return "failed"
        totals["candidates"] += result.candidates
        rejected.update(result.rejected)
        adjusted.update(result.adjusted)
        if result.error:
            totals["chunk_errors"] += 1
        for fact in result.facts:
            _, is_new = store_fact(db, fact, doc.id, row.id, doc.owner_id)
            totals["accepted"] += 1
            totals["new_facts"] += is_new
        doc.chunks_done += 1
        doc.stats = {**totals, "rejected": dict(rejected), "adjusted": dict(adjusted)}
        db.commit()

    doc.status, doc.finished_at = DocumentStatus.COMPLETED, _now()
    doc.stats = {**totals, "rejected": dict(rejected), "adjusted": dict(adjusted)}
    db.commit()
    checkpoint()
    if settings.index_chunks:
        embedder = get_embedder(settings)
        if embedder is not None:
            try:  # passage search needs these; a missing embedding model must not fail a document that is already read
                ensure_chunk_embeddings(db, embedder, doc.id)
                db.commit()
            except EmbeddingError as exc:
                db.rollback()
                doc.stats = {**doc.stats, "embedding_error": str(exc)}
                db.commit()
    checkpoint()
    if settings.auto_resolve:
        try:
            summary = run_resolution(db, auto=True, owner_id=doc.owner_id)
            db.commit()
            doc.stats = {**doc.stats, "resolution": {"auto_merged": summary.auto_merged, "suggestions": summary.suggestions_new}}
            db.commit()
        except Exception:  # resolution is a bonus step: the document is already read and stored
            log.exception("Entity resolution failed after document %s", doc.id)
            db.rollback()
    if settings.auto_detect_conflicts:
        try:                                    # code only (no model): relation words nobody classified are never flagged
            found = run_detection(db, owner_id=doc.owner_id)
            db.commit()
            doc.stats = {**doc.stats, "conflicts": {"open": found.open, "new": found.new}}
            db.commit()
        except Exception:
            log.exception("Conflict detection failed after document %s", doc.id)
            db.rollback()
    return "completed"
